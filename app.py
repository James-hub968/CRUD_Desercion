import os
from datetime import datetime
from flask import Flask, render_template, request, redirect, url_for, flash
from sqlalchemy.exc import IntegrityError
from models import db, Estudiante

app = Flask(__name__)
clave = os.environ.get("DB_PASSWORD", "Ingresar_clave")
app.config["SQLALCHEMY_DATABASE_URI"] = (
    f"mysql+pymysql://root:{clave}@127.0.0.1:3306/desercion_escolar?charset=utf8mb4"
)
app.config["SECRET_KEY"] = "Ingresar-algo"   # necesario para los mensajes flash
db.init_app(app)

def leer_formulario(e):
    f = request.form
    e.nombres = f["nombres"]
    e.apellidos = f["apellidos"]
    e.fecha_nacimiento = (datetime.strptime(f["fecha_nacimiento"], "%Y-%m-%d").date()
                          if f["fecha_nacimiento"] else None)
    e.sexo = f["sexo"] or None
    e.zona = f["zona"] or None
    e.estrato = int(f["estrato"]) if f["estrato"] else None
    e.discapacidad = "discapacidad" in f

@app.route("/")
def index():
    return redirect(url_for("listar"))

@app.route("/estudiantes")                       # READ
def listar():
    return render_template("estudiantes.html", estudiantes=Estudiante.query.all())

@app.route("/estudiantes/nuevo", methods=["GET", "POST"])   # CREATE
def crear():
    if request.method == "POST":
        e = Estudiante()
        leer_formulario(e)
        db.session.add(e)
        db.session.commit()
        flash("Estudiante creado")
        return redirect(url_for("listar"))
    return render_template("estudiante_form.html", e=None)

@app.route("/estudiantes/<int:id>/editar", methods=["GET", "POST"])   # UPDATE
def editar(id):
    e = db.get_or_404(Estudiante, id)
    if request.method == "POST":
        leer_formulario(e)
        db.session.commit()
        flash("Estudiante actualizado")
        return redirect(url_for("listar"))
    return render_template("estudiante_form.html", e=e)

@app.route("/estudiantes/<int:id>/eliminar", methods=["POST"])   # DELETE
def eliminar(id):
    e = db.get_or_404(Estudiante, id)
    try:
        db.session.delete(e)
        db.session.commit()
        flash("Estudiante eliminado")
    except IntegrityError:
        db.session.rollback()
        flash("No se puede eliminar: tiene matrículas asociadas")   # por el ON DELETE RESTRICT
    return redirect(url_for("listar"))

if __name__ == "__main__":
    app.run(debug=True)