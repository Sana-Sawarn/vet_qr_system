from flask import Flask, render_template, request, redirect, url_for
import qrcode
import sqlite3
import os
from datetime import datetime

app = Flask(__name__)

QR_FOLDER = os.path.join('static', 'qrcodes')
os.makedirs(QR_FOLDER, exist_ok=True)

def init_db():
    conn = sqlite3.connect('database.db')
    c = conn.cursor()
    c.execute('''CREATE TABLE IF NOT EXISTS animals (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT, species TEXT, owner TEXT, contact TEXT, qr_path TEXT
    )''')
    c.execute('''CREATE TABLE IF NOT EXISTS treatments (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        animal_id INTEGER,
        date TEXT,
        diagnosis TEXT,
        treatment TEXT,
        FOREIGN KEY(animal_id) REFERENCES animals(id)
    )''')
    conn.commit()
    conn.close()

@app.route('/')
def index():
    conn = sqlite3.connect('database.db')
    c = conn.cursor()
    c.execute("SELECT * FROM animals")
    animals = c.fetchall()
    conn.close()
    return render_template('index.html', animals=animals)

@app.route('/add', methods=['POST'])
def add_animal():
    name = request.form['name']
    species = request.form['species']
    owner = request.form['owner']
    contact = request.form['contact']

    base_url = request.host_url

    conn = sqlite3.connect('database.db')
    c = conn.cursor()
    c.execute("INSERT INTO animals (name, species, owner, contact, qr_path) VALUES (?, ?, ?, ?, '')",
              (name, species, owner, contact))
    animal_id = c.lastrowid
    conn.commit()

    qr_url = f"{base_url}animal/{animal_id}"
    qr_img = qrcode.make(qr_url)

    filename = f"{name}_{owner}_{animal_id}.png"
    qr_path = os.path.join(QR_FOLDER, filename)
    qr_img.save(qr_path)

    c.execute("UPDATE animals SET qr_path = ? WHERE id = ?", (qr_path, animal_id))
    conn.commit()
    conn.close()

    return redirect(url_for('index'))

@app.route('/animal/<int:animal_id>', methods=['GET', 'POST'])
def animal_detail(animal_id):
    conn = sqlite3.connect('database.db')
    c = conn.cursor()

    if request.method == 'POST':
        date = request.form['date']
        diagnosis = request.form['diagnosis']
        treatment = request.form['treatment']
        c.execute("INSERT INTO treatments (animal_id, date, diagnosis, treatment) VALUES (?, ?, ?, ?)",
                  (animal_id, date, diagnosis, treatment))
        conn.commit()

    c.execute("SELECT * FROM animals WHERE id = ?", (animal_id,))
    animal = c.fetchone()

    c.execute("SELECT id, date, diagnosis, treatment FROM treatments WHERE animal_id = ? ORDER BY date DESC", (animal_id,))
    history = c.fetchall()

    conn.close()

    current_date = datetime.now().strftime('%Y-%m-%d')
    return render_template('animal.html', animal=animal, history=history, current_date=current_date)

@app.route('/animal/<int:animal_id>/edit/<int:treatment_id>', methods=['GET', 'POST'])
def edit_treatment(animal_id, treatment_id):
    conn = sqlite3.connect('database.db')
    c = conn.cursor()

    if request.method == 'POST':
        date = request.form['date']
        diagnosis = request.form['diagnosis']
        treatment = request.form['treatment']
        c.execute("UPDATE treatments SET date = ?, diagnosis = ?, treatment = ? WHERE id = ?",
                  (date, diagnosis, treatment, treatment_id))
        conn.commit()
        conn.close()
        return redirect(url_for('animal_detail', animal_id=animal_id))

    c.execute("SELECT date, diagnosis, treatment FROM treatments WHERE id = ?", (treatment_id,))
    record = c.fetchone()
    conn.close()
    return render_template('edit_treatment.html', animal_id=animal_id, treatment_id=treatment_id, record=record)

@app.route('/animal/<int:animal_id>/delete/<int:treatment_id>')
def delete_treatment(animal_id, treatment_id):
    conn = sqlite3.connect('database.db')
    c = conn.cursor()
    c.execute("DELETE FROM treatments WHERE id = ?", (treatment_id,))
    conn.commit()
    conn.close()
    return redirect(url_for('animal_detail', animal_id=animal_id))

@app.route('/scan')
def scan_qr():
    return render_template('scan.html')

if __name__ == '__main__':
    init_db()
    app.run(debug=True)
