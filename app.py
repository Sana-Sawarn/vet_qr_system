from flask import Flask, render_template, request, redirect, url_for, session, flash, g
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
    if 'conn' not in g:
        if not DATABASE_URL:
            raise ValueError("DATABASE_URL is not set")
        g.conn = psycopg2.connect(DATABASE_URL)
        g.cursor = g.conn.cursor()
    return g.conn, g.cursor

@app.teardown_appcontext
def close_db_connection(exception):
    cursor = g.pop('cursor', None)
    if cursor:
        cursor.close()
    conn = g.pop('conn', None)
    if conn:
        conn.close()

def init_db():
    conn, cursor = get_db_connection()

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS animals (
            id SERIAL PRIMARY KEY,
            name TEXT NOT NULL,
            species TEXT NOT NULL,
            owner TEXT NOT NULL,
            contact TEXT NOT NULL
        );
    """)

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS users (
            id SERIAL PRIMARY KEY,
            username TEXT UNIQUE NOT NULL,
            password TEXT NOT NULL
        );
    """)

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS vaccinations (
            id SERIAL PRIMARY KEY,
            animal_id INTEGER REFERENCES animals(id) ON DELETE CASCADE,
            vaccine TEXT NOT NULL,
            vaccination_date DATE NOT NULL,
            due_date DATE NOT NULL
        );
    """)

    cursor.execute("SELECT * FROM users WHERE username = %s;", ('buddy pet care and clinic',))
    if not cursor.fetchone():
        cursor.execute("INSERT INTO users (username, password) VALUES (%s, %s);",
                       ('buddy pet care and clinic', 'baborajss'))

    conn.commit()

def login_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not session.get('logged_in'):
            flash('Please log in to access this page.', 'warning')
            return redirect(url_for('login'))
        return f(*args, **kwargs)
    return decorated_function

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form.get('username', '')
        password = request.form.get('password', '')

        conn, cursor = get_db_connection()
        cursor.execute("SELECT * FROM users WHERE username = %s AND password = %s;", (username, password))
        user = cursor.fetchone()

        if user:
            session['logged_in'] = True
            flash('Logged in successfully!', 'success')
            return redirect(url_for('dashboard'))
        else:
            flash('Invalid username or password.', 'danger')

    return render_template('login.html')

@app.route('/logout')
@login_required
def logout():
    session.clear()
    flash('You have been logged out.', 'info')
    return redirect(url_for('index'))

@app.route('/dashboard')
@login_required
def dashboard():
    conn, cursor = get_db_connection()
    cursor.execute("SELECT * FROM animals ORDER BY id DESC;")
    animals = cursor.fetchall()
    return render_template('dashboard.html', animals=animals)

@app.route('/register', methods=['GET', 'POST'])
@login_required
def register():
    if request.method == 'POST':
        name = request.form.get('name')
        species = request.form.get('species')
        owner = request.form.get('owner')
        contact = request.form.get('contact')

        if not all([name, species, owner, contact]):
            flash('Please fill out all fields.', 'warning')
            return render_template('register.html')

        try:
            conn, cursor = get_db_connection()
            cursor.execute(
                "INSERT INTO animals (name, species, owner, contact) VALUES (%s, %s, %s, %s) RETURNING id;",
                (name, species, owner, contact)
            )
            animal_id = cursor.fetchone()[0]
            conn.commit()
        except Exception as e:
            flash(f"Error saving to database: {e}", 'danger')
            return render_template('register.html')

        qr_data = url_for('view_animal', animal_id=animal_id, _external=True)
        qr_img = qrcode.make(qr_data)
        buf = io.BytesIO()
        qr_img.save(buf, format='PNG')
        qr_base64 = base64.b64encode(buf.getvalue()).decode('utf-8')

        return render_template('qr_display.html', qr_code=qr_base64, animal_id=animal_id)

    return render_template('register.html')

@app.route('/animal/<int:animal_id>')
@login_required
def view_animal(animal_id):
    conn, cursor = get_db_connection()
    cursor.execute("SELECT * FROM animals WHERE id = %s;", (animal_id,))
    animal = cursor.fetchone()
    if not animal:
        flash("Animal not found.", "warning")
        return redirect(url_for('dashboard'))

    cursor.execute("SELECT * FROM vaccinations WHERE animal_id = %s ORDER BY vaccination_date DESC;", (animal_id,))
    vaccinations = cursor.fetchall()

    return render_template('animal_profile.html', animal=animal, vaccinations=vaccinations)

@app.route('/animal/<int:animal_id>/vaccinate', methods=['GET', 'POST'])
@login_required
def add_vaccination(animal_id):
    if request.method == 'POST':
        vaccine = request.form['vaccine']
        vaccination_date = request.form['vaccination_date']
        due_date = request.form['due_date']

        conn, cursor = get_db_connection()
        cursor.execute("INSERT INTO vaccinations (animal_id, vaccine, vaccination_date, due_date) VALUES (%s, %s, %s, %s)",
                       (animal_id, vaccine, vaccination_date, due_date))
        conn.commit()
        flash('Vaccination record added.', 'success')
        return redirect(url_for('view_animal', animal_id=animal_id))

    return render_template('add_vaccination.html', animal_id=animal_id)

@app.route('/init')
def init():
    try:
        init_db()
        return "Database initialized."
    except Exception as e:
        return f"Error initializing database: {e}"

if __name__ == '__main__':
    app.run(debug=True)