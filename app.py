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
    conn = g.pop('conn', None)
    cursor = g.pop('cursor', None)
    if cursor:
        cursor.close()
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
    conn.commit()


def login_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not session.get('logged_in'):
            return redirect(url_for('login'))
        return f(*args, **kwargs)
    return decorated_function


@app.route('/')
def index():
    return render_template('index.html')


@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        if request.form['username'] == 'admin' and request.form['password'] == 'password':
            session['logged_in'] = True
            return redirect(url_for('dashboard'))
        flash('Invalid Credentials')
    return render_template('login.html')


@app.route('/logout')
def logout():
    session.clear()
    return redirect(url_for('index'))


@app.route('/dashboard')
@login_required
def dashboard():
    conn, cursor = get_db_connection()
    cursor.execute("SELECT * FROM animals;")
    animals = cursor.fetchall()
    return render_template('dashboard.html', animals=animals)


@app.route('/register', methods=['GET', 'POST'])
@login_required
def register():
    if request.method == 'POST':
        name = request.form['name']
        species = request.form['species']
        owner = request.form['owner']
        contact = request.form['contact']
        conn, cursor = get_db_connection()
        cursor.execute("INSERT INTO animals (name, species, owner, contact) VALUES (%s, %s, %s, %s) RETURNING id;",
                       (name, species, owner, contact))
        animal_id = cursor.fetchone()[0]
        conn.commit()

        # Generate QR code
        qr_data = f"http://yourdomain.com/animal/{animal_id}"
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
        flash("Animal not found")
        return redirect(url_for('dashboard'))
    return render_template('animal_profile.html', animal=animal)

@app.route('/init')
def init():
    init_db()
    return "Database initialized."

if __name__ == '__main__':
    app.run(debug=True)
