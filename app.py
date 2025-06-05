import os
import io
import base64
import qrcode
import psycopg2
from datetime import date
from flask import Flask, render_template, request, redirect, url_for, flash, g
from flask_wtf import FlaskForm
from wtforms import StringField, DateField, HiddenField
from wtforms.validators import DataRequired
from dotenv import load_dotenv

load_dotenv()

app = Flask(__name__)
app.secret_key = os.getenv("SECRET_KEY")

# ---------- DB Connection ----------
def get_db_connection():
    if 'conn' not in g:
        g.conn = psycopg2.connect(
            dbname=os.getenv("DB_NAME"),
            user=os.getenv("DB_USER"),
            password=os.getenv("DB_PASSWORD"),
            host=os.getenv("DB_HOST"),
            port=os.getenv("DB_PORT")
        )
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

# ---------- Forms ----------
class TreatmentForm(FlaskForm):
    type = HiddenField(default="treatment")
    date = DateField('Date', validators=[DataRequired()])
    diagnosis = StringField('Diagnosis', validators=[DataRequired()])
    treatment = StringField('Treatment', validators=[DataRequired()])

class VaccinationForm(FlaskForm):
    type = HiddenField(default="vaccination")
    date = DateField('Date', validators=[DataRequired()])
    vaccine = StringField('Vaccine', validators=[DataRequired()])
    due_date = DateField('Due Date', validators=[DataRequired()])

# ---------- Init Tables ----------
def init_db():
    conn, cursor = get_db_connection()
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS animals (
            id SERIAL PRIMARY KEY,
            name TEXT NOT NULL,
            species TEXT NOT NULL,
            owner TEXT NOT NULL,
            contact TEXT NOT NULL
        )
    """)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS treatment_records (
            id SERIAL PRIMARY KEY,
            animal_id INTEGER REFERENCES animals(id) ON DELETE CASCADE,
            date DATE NOT NULL,
            diagnosis TEXT NOT NULL,
            treatment TEXT NOT NULL
        )
    """)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS vaccination_records (
            id SERIAL PRIMARY KEY,
            animal_id INTEGER REFERENCES animals(id) ON DELETE CASCADE,
            date DATE NOT NULL,
            vaccine TEXT NOT NULL,
            due_date DATE NOT NULL
        )
    """)
    conn.commit()

# Initialize on first run
with app.app_context():
    init_db()

# ---------- Routes ----------
@app.route("/")
def index():
    conn, cursor = get_db_connection()
    cursor.execute("SELECT * FROM animals ORDER BY id DESC")
    animals = cursor.fetchall()
    return render_template("index.html", animals=animals)

@app.route("/add_animal", methods=["POST"])
def add_animal():
    conn, cursor = get_db_connection()
    name = request.form.get("name", "").strip()
    species = request.form.get("species", "").strip()
    owner = request.form.get("owner", "").strip()
    contact = request.form.get("contact", "").strip()

    if not (name and species and owner and contact):
        flash("All fields are required.", "danger")
        return redirect(url_for("index"))

    cursor.execute(
        "INSERT INTO animals (name, species, owner, contact) VALUES (%s, %s, %s, %s)",
        (name, species, owner, contact)
    )
    conn.commit()
    flash(f"Animal '{name}' added successfully.", "success")
    return redirect(url_for("index"))

@app.route("/delete_animal/<int:animal_id>", methods=["POST"])
def delete_animal(animal_id):
    conn, cursor = get_db_connection()
    cursor.execute("DELETE FROM animals WHERE id = %s", (animal_id,))
    conn.commit()
    flash("Animal deleted successfully.", "success")
    return redirect(url_for("index"))

@app.route("/animal/<int:animal_id>", methods=["GET", "POST"])
def animal_detail(animal_id):
    conn, cursor = get_db_connection()
    cursor.execute("SELECT * FROM animals WHERE id = %s", (animal_id,))
    animal = cursor.fetchone()
    if not animal:
        flash("Animal not found.", "danger")
        return redirect(url_for("index"))

    treatment_form = TreatmentForm(prefix="treatment")
    vaccination_form = VaccinationForm(prefix="vaccination")

    if request.method == "POST":
        if treatment_form.validate_on_submit() and treatment_form.type.data == "treatment":
            cursor.execute("""
                INSERT INTO treatment_records (animal_id, date, diagnosis, treatment)
                VALUES (%s, %s, %s, %s)
            """, (
                animal_id,
                treatment_form.date.data,
                treatment_form.diagnosis.data.strip(),
                treatment_form.treatment.data.strip()
            ))
            conn.commit()
            flash("Treatment record added successfully", "success")
            return redirect(url_for("animal_detail", animal_id=animal_id))

        elif vaccination_form.validate_on_submit() and vaccination_form.type.data == "vaccination":
            cursor.execute("""
                INSERT INTO vaccination_records (animal_id, date, vaccine, due_date)
                VALUES (%s, %s, %s, %s)
            """, (
                animal_id,
                vaccination_form.date.data,
                vaccination_form.vaccine.data.strip(),
                vaccination_form.due_date.data
            ))
            conn.commit()
            flash("Vaccination record added successfully", "success")
            return redirect(url_for("animal_detail", animal_id=animal_id))

        flash("Invalid form submission.", "danger")
        return redirect(url_for("animal_detail", animal_id=animal_id))

    # Generate QR Code
    url_for_detail = url_for('animal_detail', animal_id=animal_id, _external=True)
    qr = qrcode.make(url_for_detail)
    buffer = io.BytesIO()
    qr.save(buffer, format="PNG")
    qr_base64 = base64.b64encode(buffer.getvalue()).decode("utf-8")

    cursor.execute("SELECT id, date, diagnosis, treatment FROM treatment_records WHERE animal_id = %s ORDER BY date DESC", (animal_id,))
    treatment_history = cursor.fetchall()

    cursor.execute("SELECT id, date, vaccine, due_date FROM vaccination_records WHERE animal_id = %s ORDER BY date DESC", (animal_id,))
    vaccination_history = cursor.fetchall()

    return render_template(
        "animal.html",
        animal=animal,
        qr_base64=qr_base64,
        treatment_history=treatment_history,
        vaccination_history=vaccination_history,
        treatment_form=treatment_form,
        vaccination_form=vaccination_form,
        current_date=date.today().isoformat()
    )

if __name__ == "__main__":
    app.run(debug=True)
