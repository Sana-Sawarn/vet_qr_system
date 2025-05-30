from flask import Flask, render_template, request, redirect, url_for, session, flash
import qrcode
import os
from datetime import datetime
from functools import wraps
import psycopg2
from dotenv import load_dotenv
import io
import base64

load_dotenv()

app = Flask(__name__)
app.secret_key = os.environ.get('SECRET_KEY', 'fallback_secret_key')

DATABASE_URL = os.environ.get('DATABASE_URL')

def get_db_connection():
    return psycopg2.connect(DATABASE_URL)

USERS = {
    "buddy pet care and clinic": "baborajss"
}

def login_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'username' not in session:
            flash("Please log in first.", "warning")
            return redirect(url_for('login'))
        return f(*args, **kwargs)
    return decorated_function

def init_db():
    conn = get_db_connection()
    c = conn.cursor()
    c.execute('''CREATE TABLE IF NOT EXISTS animals (
        id SERIAL PRIMARY KEY,
        name TEXT,
        species TEXT,
        owner TEXT,
        contact TEXT,
        qr_image BYTEA
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

def generate_qr_bytes(url):
    qr_img = qrcode.make(url)
    img_bytes = io.BytesIO()
    qr_img.save(img_bytes, format='PNG')
    img_bytes.seek(0)
    return img_bytes.read()

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
    c.execute("SELECT id, name, species, owner, contact FROM animals")
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
    c.execute("SELECT id FROM animals WHERE name = %s AND owner = %s", (name, owner))
    existing = c.fetchone()

    if existing:
        animal_id = existing[0]
        flash("Animal already exists. Redirecting to the existing record.", "info")
        conn.close()
        return redirect(url_for('animal_detail', animal_id=animal_id))

    c.execute("INSERT INTO animals (name, species, owner, contact, qr_image) VALUES (%s, %s, %s, %s, %s)",
              (name, species, owner, contact, None))
    conn.commit()

    c.execute("SELECT id FROM animals WHERE name = %s AND owner = %s ORDER BY id DESC LIMIT 1", (name, owner))
    animal_id = c.fetchone()[0]

    base_url = os.environ.get("BASE_URL", "http://localhost:5000")
    qr_url = f"{base_url}/public/animal/{animal_id}"

    qr_bytes = generate_qr_bytes(qr_url)
    c.execute("UPDATE animals SET qr_image = %s WHERE id = %s", (psycopg2.Binary(qr_bytes), animal_id))
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
            c.execute("INSERT INTO treatments (animal_id, date, diagnosis, treatment) VALUES (%s, %s, %s, %s)",
                      (animal_id, request.form['date'], request.form['diagnosis'], request.form['treatment']))
        elif 'vaccine' in request.form:
            c.execute("INSERT INTO vaccinations (animal_id, date, vaccine, due_date) VALUES (%s, %s, %s, %s)",
                      (animal_id, request.form['date'], request.form['vaccine'], request.form['due_date']))
        conn.commit()

    c.execute("SELECT id, name, species, owner, contact, qr_image FROM animals WHERE id = %s", (animal_id,))
    animal = c.fetchone()

    c.execute("SELECT id, date, diagnosis, treatment FROM treatments WHERE animal_id = %s ORDER BY date DESC", (animal_id,))
    treatment_history = c.fetchall()

    c.execute("SELECT id, date, vaccine, due_date FROM vaccinations WHERE animal_id = %s ORDER BY date DESC", (animal_id,))
    vaccination_history = c.fetchall()
    conn.close()

    qr_base64 = base64.b64encode(animal[5]).decode('utf-8') if animal and animal[5] else None
    current_date = datetime.now().strftime('%Y-%m-%d')

    return render_template('animal.html', animal=animal, treatment_history=treatment_history,
                           vaccination_history=vaccination_history, current_date=current_date, qr_base64=qr_base64)

@app.route('/delete_animal/<int:animal_id>', methods=['POST'])
@login_required
def delete_animal(animal_id):
    conn = get_db_connection()
    c = conn.cursor()
    # Delete dependent records first due to foreign key constraints
    c.execute("DELETE FROM treatments WHERE animal_id = %s", (animal_id,))
    c.execute("DELETE FROM vaccinations WHERE animal_id = %s", (animal_id,))
    c.execute("DELETE FROM animals WHERE id = %s", (animal_id,))
    conn.commit()
    conn.close()
    flash("Animal and related records deleted successfully.", "success")
    return redirect(url_for('index'))

@app.route('/delete_treatment/<int:treatment_id>', methods=['POST'])
@login_required
def delete_treatment(treatment_id):
    conn = get_db_connection()
    c = conn.cursor()
    c.execute("DELETE FROM treatments WHERE id = %s", (treatment_id,))
    conn.commit()
    conn.close()
    flash("Treatment record deleted.", "success")
    return redirect(request.referrer or url_for('index'))

@app.route('/delete_vaccination/<int:vaccination_id>', methods=['POST'])
@login_required
def delete_vaccination(vaccination_id):
    conn = get_db_connection()
    c = conn.cursor()
    c.execute("DELETE FROM vaccinations WHERE id = %s", (vaccination_id,))
    conn.commit()
    conn.close()
    flash("Vaccination record deleted.", "success")
    return redirect(request.referrer or url_for('index'))

@app.route('/public/animal/<int:animal_id>')
def public_animal_view(animal_id):
    conn = get_db_connection()
    c = conn.cursor()
    c.execute("SELECT id, name, species, owner, contact, qr_image FROM animals WHERE id = %s", (animal_id,))
    animal = c.fetchone()
    c.execute("SELECT date, diagnosis, treatment FROM treatments WHERE animal_id = %s ORDER BY date DESC", (animal_id,))
    treatment_history = c.fetchall()
    c.execute("SELECT date, vaccine, due_date FROM vaccinations WHERE animal_id = %s ORDER BY date DESC", (animal_id,))
    vaccination_history = c.fetchall()
    conn.close()

    if not animal:
        return "Animal not found", 404

    qr_base64 = base64.b64encode(animal[5]).decode('utf-8') if animal and animal[5] else None

    return render_template('public_animal.html', animal=animal, treatment_history=treatment_history,
                           vaccination_history=vaccination_history, qr_base64=qr_base64)

if __name__ == '__main__':
    # For production, debug should be False
    app.run(host='0.0.0.0', port=int(os.environ.get('PORT', 5000)), debug=False)
