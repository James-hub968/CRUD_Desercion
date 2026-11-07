# models.py
from extensions import db

class Institucion(db.Model):
    __tablename__ = "institucion"
    id_institucion = db.Column(db.Integer, primary_key=True)
    nombre = db.Column(db.String(150), nullable=False)
    tipo = db.Column(db.String(20))
    municipio = db.Column(db.String(100))
    zona = db.Column(db.String(10))
    grupos = db.relationship("Grupo", back_populates="institucion")

class Estudiante(db.Model):
    __tablename__ = "estudiante"
    id_estudiante = db.Column(db.Integer, primary_key=True)
    nombres = db.Column(db.String(100), nullable=False)
    apellidos = db.Column(db.String(100), nullable=False)
    fecha_nacimiento = db.Column(db.Date)
    sexo = db.Column(db.String(20))
    zona = db.Column(db.String(10))
    estrato = db.Column(db.SmallInteger)
    discapacidad = db.Column(db.Boolean)
    matriculas = db.relationship("Matricula", back_populates="estudiante")

class CausaRetiro(db.Model):
    __tablename__ = "causa_retiro"
    id_causa = db.Column(db.Integer, primary_key=True)
    descripcion = db.Column(db.String(255), nullable=False)
    matriculas = db.relationship("Matricula", back_populates="causa")

class ProgramaApoyo(db.Model):
    __tablename__ = "programa_apoyo"
    id_programa = db.Column(db.Integer, primary_key=True)
    nombre = db.Column(db.String(150), nullable=False)
    tipo = db.Column(db.String(30))
    matriculas = db.relationship("Matricula", back_populates="programa")

class Asignatura(db.Model):
    __tablename__ = "asignatura"
    id_asignatura = db.Column(db.Integer, primary_key=True)
    nombre = db.Column(db.String(100), nullable=False)
    notas = db.relationship("Nota", back_populates="asignatura")

class Grupo(db.Model):
    __tablename__ = "grupo"
    id_grupo = db.Column(db.Integer, primary_key=True)
    grado = db.Column(db.String(20), nullable=False)
    jornada = db.Column(db.String(30))
    anio_lectivo = db.Column("año_lectivo", db.SmallInteger, nullable=False)
    id_institucion = db.Column(db.Integer, db.ForeignKey("institucion.id_institucion"), nullable=False)
    institucion = db.relationship("Institucion", back_populates="grupos")
    matriculas = db.relationship("Matricula", back_populates="grupo")

class Matricula(db.Model):
    __tablename__ = "matricula"
    id_matricula = db.Column(db.Integer, primary_key=True)
    fecha = db.Column(db.Date, nullable=False)
    estado = db.Column(db.String(20), nullable=False)
    id_estudiante = db.Column(db.Integer, db.ForeignKey("estudiante.id_estudiante"), nullable=False)
    id_grupo = db.Column(db.Integer, db.ForeignKey("grupo.id_grupo"), nullable=False)
    id_causa = db.Column(db.Integer, db.ForeignKey("causa_retiro.id_causa"))
    id_programa = db.Column(db.Integer, db.ForeignKey("programa_apoyo.id_programa"))
    
    estudiante = db.relationship("Estudiante", back_populates="matriculas")
    grupo = db.relationship("Grupo", back_populates="matriculas")
    causa = db.relationship("CausaRetiro", back_populates="matriculas")
    programa = db.relationship("ProgramaApoyo", back_populates="matriculas")
    
    # En la BD las notas se borran en cascada con la matrícula
    notas = db.relationship("Nota", back_populates="matricula",
                            cascade="all, delete-orphan", passive_deletes=True)

class Nota(db.Model):
    __tablename__ = "nota"
    id_nota = db.Column(db.Integer, primary_key=True)
    periodo = db.Column(db.String(30), nullable=False)
    valor = db.Column(db.Numeric(5, 2))
    id_matricula = db.Column(db.Integer, db.ForeignKey("matricula.id_matricula"), nullable=False)
    id_asignatura = db.Column(db.Integer, db.ForeignKey("asignatura.id_asignatura"), nullable=False)
    
    matricula = db.relationship("Matricula", back_populates="notas")
    asignatura = db.relationship("Asignatura", back_populates="notas")