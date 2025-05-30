from flask import Flask, render_template, request, redirect, url_for, session, flash
import qrcode
import os
from datetime import datetime
from functools import wraps
import psycopg2
from dotenv import load_dotenv

load_dotenv()

app = Flask(__name__)
app.secret_key = os.environ.get('SECRET_KEY', 'fallback_secret_key')

# Folder to save QR codes
QR_FOLDER = os.path.join('static', 'qrcodes')
os.makedirs(QR_FOLDER, exist_ok=True)

# Get DATABASE_URL from environment
DATABASE_URL = os.environ.get('DATABASE_URL')

# Simplified DB connection
def get_db_connection():
    return psycopg2.connect(DATABASE_URL)

# Simple user store
USERS = {
    "buddy pet care and clinic": "baborajss"
}

# Login required decorator
def login_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'username' not in session:
            flash("Please log in first.", "warning")
            return redirect(url_for('login'))
        return f(*args, **kwargs)
    return decorated_function

# Initialize DB tables
def init_db():
    conn = get_db_connection()
    c = conn.cursor()
    c.execute('''CREATE TABLE IF NOT EXISTS animals (
        id SERIAL PRIMARY KEY,
        name TEXT,
        species TEXT,
        owner TEXT,
        contact TEXT,
        qr_path TEXT
    )''')
    c.execute('''CREATE TABLE IF NOT EXISTS treatments (
        id SERIAL PRIMARY KEY,
        animal_id INTEGER REFERENCES animals(id),
        date TEXT,
        diagnosis TEXT,
        treatment TEXT
    )''')
    c.execute('''CREATE TABLE IF NOT EXISTS vaccinations (
        id SERIAL PRIMARY KEY,
        animal_id INTEGER REFERENCES animals(id),
        date TEXT,
        vaccine TEXT,
        due_date TEXT
    )''')
    conn.commit()
    conn.close()
    print("✅ Database initialized")

init_db()

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form['username'].strip().lower()
        password = request.form['password']
        if username in USERS and USERS[username] == password:
            session['username'] = username
            flash(f"Welcome, {username}!", "success")
            return redirect(url_for('index'))
        else:
            flash("Invalid username or password", "danger")
    return render_template('login.html')

@app.route('/logout')
def logout():
    session.pop('username', None)
    flash("You have been logged out.", "info")
    return redirect(url_for('login'))

@app.route('/')
@login_required
def index():
    conn = get_db_connection()
    c = conn.cursor()
    c.execute("SELECT * FROM animals")
    animals = c.fetchall()
    conn.close()
    return render_template('index.html', animals=animals)

@app.route('/add', methods=['POST'])
@login_required
def add_animal():
    name = request.form['name'].strip()
    species = request.form['species'].strip()
    owner = request.form['owner'].strip()
    contact = request.form['contact'].strip()

    conn = get_db_connection()
    c = conn.cursor()
    c.execute("SELECT id, qr_path FROM animals WHERE name = %s AND owner = %s", (name, owner))
    existing = c.fetchone()

    if existing:
        animal_id, _ = existing
        flash("Animal already exists. Redirecting to the existing record.", "info")
        conn.close()
        return redirect(url_for('animal_detail', animal_id=animal_id))

    c.execute("INSERT INTO animals (name, species, owner, contact, qr_path) VALUES (%s, %s, %s, %s, '')",
              (name, species, owner, contact))
    conn.commit()

    c.execute("SELECT id FROM animals WHERE name = %s AND owner = %s ORDER BY id DESC LIMIT 1", (name, owner))
    animal_id = c.fetchone()[0]

    safe_name = "_".join(name.title().split())
    safe_owner = "_".join(owner.title().split())
    filename = f"{safe_name}_{safe_owner}_{animal_id}.png"
    qr_relative_path = f"qrcodes/{filename}"
    qr_full_path = os.path.join(QR_FOLDER, filename)

    base_url = os.environ.get("BASE_URL", "http://localhost:5000")
    qr_url = f"{base_url}/public/animal/{animal_id}"

    qr_img = qrcode.make(qr_url)
    qr_img.save(qr_full_path)

    c.execute("UPDATE animals SET qr_path = %s WHERE id = %s", (qr_relative_path, animal_id))
    conn.commit()
    conn.close()

    flash("Animal added successfully!", "success")
    return redirect(url_for('index'))

@app.route('/animal/<int:animal_id>', methods=['GET', 'POST'])
@login_required
def animal_detail(animal_id):
    conn = get_db_connection()
    c = conn.cursor()

    if request.method == 'POST':
        if 'diagnosis' in request.form:
            date = request.form['date']
            diagnosis = request.form['diagnosis']
            treatment = request.form['treatment']
            c.execute("INSERT INTO treatments (animal_id, date, diagnosis, treatment) VALUES (%s, %s, %s, %s)",
                      (animal_id, date, diagnosis, treatment))
        elif 'vaccine' in request.form:
            date = request.form['date']
            vaccine = request.form['vaccine']
            due_date = request.form['due_date']
            c.execute("INSERT INTO vaccinations (animal_id, date, vaccine, due_date) VALUES (%s, %s, %s, %s)",
                      (animal_id, date, vaccine, due_date))
        conn.commit()

    c.execute("SELECT * FROM animals WHERE id = %s", (animal_id,))
    animal = c.fetchone()

    c.execute("SELECT id, date, diagnosis, treatment FROM treatments WHERE animal_id = %s ORDER BY date DESC", (animal_id,))
    treatment_history = c.fetchall()

    c.execute("SELECT id, date, vaccine, due_date FROM vaccinations WHERE animal_id = %s ORDER BY date DESC", (animal_id,))
    vaccination_history = c.fetchall()

    conn.close()
    current_date = datetime.now().strftime('%Y-%m-%d')
    return render_template('animal.html', animal=animal, treatment_history=treatment_history,
                           vaccination_history=vaccination_history, current_date=current_date)

@app.route('/animal/<int:animal_id>/edit_treatment/<int:treatment_id>', methods=['GET', 'POST'])
@login_required
def edit_treatment(animal_id, treatment_id):
    conn = get_db_connection()
    c = conn.cursor()

    if request.method == 'POST':
        date = request.form['date']
        diagnosis = request.form['diagnosis']
        treatment = request.form['treatment']
        c.execute("UPDATE treatments SET date = %s, diagnosis = %s, treatment = %s WHERE id = %s",
                  (date, diagnosis, treatment, treatment_id))
        conn.commit()
        conn.close()
        return redirect(url_for('animal_detail', animal_id=animal_id))

    c.execute("SELECT * FROM treatments WHERE id = %s", (treatment_id,))
    record = c.fetchone()
    conn.close()

    return render_template('edit_treatment.html', animal_id=animal_id, treatment_id=treatment_id, record=record)

@app.route('/animal/<int:animal_id>/edit_vaccination/<int:vaccination_id>', methods=['GET', 'POST'])
@login_required
def edit_vaccination(animal_id, vaccination_id):
    conn = get_db_connection()
    c = conn.cursor()

    if request.method == 'POST':
        date = request.form['date']
        vaccine = request.form['vaccine']
        due_date = request.form['due_date']
        c.execute("UPDATE vaccinations SET date = %s, vaccine = %s, due_date = %s WHERE id = %s",
                  (date, vaccine, due_date, vaccination_id))
        conn.commit()
        conn.close()
        return redirect(url_for('animal_detail', animal_id=animal_id))

    c.execute("SELECT * FROM vaccinations WHERE id = %s", (vaccination_id,))
    record = c.fetchone()
    conn.close()

    if not record:
        return "Vaccination record not found", 404

    return render_template('edit_vaccine.html', animal_id=animal_id, vaccination_id=vaccination_id, record=record)

@app.route('/animal/<int:animal_id>/delete_treatment/<int:treatment_id>')
@login_required
def delete_treatment(animal_id, treatment_id):
    conn = get_db_connection()
    c = conn.cursor()
    c.execute("DELETE FROM treatments WHERE id = %s", (treatment_id,))
    conn.commit()
    conn.close()
    return redirect(url_for('animal_detail', animal_id=animal_id))

@app.route('/animal/<int:animal_id>/delete_vaccination/<int:vaccination_id>')
@login_required
def delete_vaccination(animal_id, vaccination_id):
    conn = get_db_connection()
    c = conn.cursor()
    c.execute("DELETE FROM vaccinations WHERE id = %s", (vaccination_id,))
    conn.commit()
    conn.close()
    return redirect(url_for('animal_detail', animal_id=animal_id))

@app.route('/animal/<int:animal_id>/delete', methods=['POST'])
@login_required
def delete_animal(animal_id):
    conn = get_db_connection()
    c = conn.cursor()
    c.execute("DELETE FROM treatments WHERE animal_id = %s", (animal_id,))
    c.execute("DELETE FROM vaccinations WHERE animal_id = %s", (animal_id,))
    c.execute("DELETE FROM animals WHERE id = %s", (animal_id,))
    conn.commit()
    conn.close()
    flash("Animal deleted successfully.", "success")
    return redirect(url_for('index'))

@app.route('/public/animal/<int:animal_id>')
def public_animal_view(animal_id):
    conn = get_db_connection()
    c = conn.cursor()
    c.execute("SELECT * FROM animals WHERE id = %s", (animal_id,))
    animal = c.fetchone()
    c.execute("SELECT date, diagnosis, treatment FROM treatments WHERE animal_id = %s ORDER BY date DESC", (animal_id,))
    treatment_history = c.fetchall()
    c.execute("SELECT date, vaccine, due_date FROM vaccinations WHERE animal_id = %s ORDER BY date DESC", (animal_id,))
    vaccination_history = c.fetchall()
    conn.close()
    if not animal:
        return "Animal not found", 404
    return render_template('public_animal.html', animal=animal, treatment_history=treatment_history,
                           vaccination_history=vaccination_history)

# ✅ DEBUG ROUTE TO CHECK DATABASE
@app.route('/debug_db')
def debug_db():
    conn = get_db_connection()
    c = conn.cursor()
    c.execute("SELECT current_database();")
    db_name = c.fetchone()[0]
    c.execute("SELECT COUNT(*) FROM animals;")
    count = c.fetchone()[0]
    conn.close()
    return f"✅ Connected to DB: <b>{db_name}</b><br>🐾 Total animals in DB: <b>{count}</b>"

# Run app
if __name__ == '__main__':
    app.run(host='0.0.0.0', port=int(os.environ.get('PORT', 5000)), debug=True)
