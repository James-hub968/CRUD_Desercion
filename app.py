import csv
import io
import os
from datetime import date

from flask import Flask, Response, flash, jsonify, redirect, render_template, request, url_for
from sqlalchemy import case, func
from sqlalchemy.exc import IntegrityError, OperationalError
from sqlalchemy.orm import contains_eager, selectinload

from config import Config
from models import CausaRetiro, Estudiante, Grupo, Institucion, Matricula, ProgramaApoyo, db

# ---------- CONEXIÓN ----------
app = Flask(__name__)
app.config.from_object(Config)
if os.environ.get("DATABASE_URL"):
    app.config["SQLALCHEMY_DATABASE_URI"] = os.environ["DATABASE_URL"]
    app.config["SQLALCHEMY_ENGINE_OPTIONS"] = {}
app.json.ensure_ascii = False
app.json.sort_keys = False
db.init_app(app)

# ---------- CATÁLOGOS ----------
SEXOS = ("Femenino", "Masculino")
ZONAS = ("Urbana", "Rural")
ESTRATOS = tuple(range(0, 7))
ESTADOS = ("ACTIVA", "RETIRADO", "GRADUADO")
ESTADO_TEXTO = {"ACTIVA": "Activa", "RETIRADO": "Retirado", "GRADUADO": "Graduado", None: "Sin matrícula"}


def estatico(archivo):
    # La fecha del archivo en la URL obliga al navegador a bajar la versión nueva
    v = int(os.path.getmtime(os.path.join(app.static_folder, archivo)))
    return url_for("static", filename=archivo, v=v)


@app.context_processor
def catalogos():
    return {"SEXOS": SEXOS, "ZONAS": ZONAS, "ESTRATOS": ESTRATOS,
            "ESTADOS": ESTADOS, "ESTADO_TEXTO": ESTADO_TEXTO, "estatico": estatico}


@app.template_filter("pct")
def pct(valor):
    return f"{valor:.1f} %".replace(".", ",")


# ---------- FILTROS ----------
def leer_filtros():
    zona = request.args.get("zona")
    inst = request.args.get("institucion", type=int)
    return (zona if zona in ZONAS else None), inst


def institucion_o_none(id_institucion):
    return db.session.get(Institucion, id_institucion) if id_institucion else None


# ---------- CONSULTAS: ESTUDIANTES (CASO DE USO 1) ----------
def matricula_actual(e):
    return max(e.matriculas, key=lambda m: (m.fecha, m.id_matricula), default=None)


def fila_estudiante(e):
    m = matricula_actual(e)
    g = m.grupo if m else None
    return {
        "id": e.id_estudiante,
        "nombre": f"{e.nombres} {e.apellidos}",
        "sexo": e.sexo,
        "zona": e.zona,
        "estrato": e.estrato,
        "discapacidad": bool(e.discapacidad),
        "id_institucion": g.id_institucion if g else None,
        "institucion": g.institucion.nombre if g else None,
        "grado": g.grado if g else None,
        "jornada": g.jornada if g else None,
        "estado": m.estado if m else None,
        "causa": m.causa.descripcion if m and m.causa else None,
        "programa": m.programa.nombre if m and m.programa else None,
    }


def estudiantes(zona=None, id_institucion=None):
    q = (Estudiante.query
         .options(selectinload(Estudiante.matriculas).options(
             selectinload(Matricula.grupo).selectinload(Grupo.institucion),
             selectinload(Matricula.causa),
             selectinload(Matricula.programa)))
         .order_by(Estudiante.apellidos, Estudiante.nombres))
    if zona:
        q = q.filter(Estudiante.zona == zona)
    filas = [fila_estudiante(e) for e in q]
    if id_institucion:
        filas = [f for f in filas if f["id_institucion"] == id_institucion]
    return filas


def estados_por_zona(filas):
    resumen = []
    for zona in ZONAS:
        de_zona = [f for f in filas if f["zona"] == zona]
        conteo = {estado: sum(f["estado"] == estado for f in de_zona) for estado in (*ESTADOS, None)}
        total = len(de_zona) or 1
        resumen.append({
            "zona": zona,
            "total": len(de_zona),
            "segmentos": [{"estado": estado, "n": n, "ancho": 100 * n / total}
                          for estado, n in conteo.items() if n],
        })
    return resumen


# ---------- CONSULTAS: DESERCIÓN (CASO DE USO 2) ----------
RETIRADOS = func.sum(case((Matricula.estado == "RETIRADO", 1), else_=0))


def matriculas_base(*columnas, zona=None, id_institucion=None):
    q = (db.session.query(*columnas).select_from(Matricula)
         .join(Matricula.estudiante).join(Matricula.grupo).join(Grupo.institucion))
    if zona:
        q = q.filter(Estudiante.zona == zona)
    if id_institucion:
        q = q.filter(Grupo.id_institucion == id_institucion)
    return q


def tasa_por(columna, **filtros):
    q = (matriculas_base(columna.label("nombre"), func.count(Matricula.id_matricula), RETIRADOS, **filtros)
         .group_by(columna))
    filas = []
    for nombre, matriculados, retirados in q:
        retirados = int(retirados or 0)
        filas.append({"nombre": "Sin dato" if nombre is None else str(nombre),
                      "matriculados": matriculados, "retirados": retirados,
                      "tasa": 100 * retirados / matriculados})
    return sorted(filas, key=lambda f: (-f["tasa"], f["nombre"]))


def retiros_por(columna, relacion, vacio, **filtros):
    q = (matriculas_base(columna, func.count(Matricula.id_matricula), **filtros)
         .outerjoin(relacion).filter(Matricula.estado == "RETIRADO").group_by(columna))
    filas = [{"nombre": nombre or vacio, "retirados": n} for nombre, n in q]
    return sorted(filas, key=lambda f: (-f["retirados"], f["nombre"]))


def lista_retirados(**filtros):
    q = (matriculas_base(Matricula, **filtros)
         .filter(Matricula.estado == "RETIRADO")
         .options(contains_eager(Matricula.estudiante),
                  contains_eager(Matricula.grupo).contains_eager(Grupo.institucion),
                  selectinload(Matricula.causa), selectinload(Matricula.programa))
         .order_by(Matricula.fecha.desc(), Estudiante.apellidos))
    return [{
        "id": m.id_estudiante,
        "nombre": f"{m.estudiante.nombres} {m.estudiante.apellidos}",
        "zona": m.estudiante.zona,
        "estrato": m.estudiante.estrato,
        "institucion": m.grupo.institucion.nombre,
        "grado": m.grupo.grado,
        "fecha": m.fecha.isoformat(),
        "causa": m.causa.descripcion if m.causa else None,
        "programa": m.programa.nombre if m.programa else None,
    } for m in q]


def desercion(zona=None, id_institucion=None):
    filtros = {"zona": zona, "id_institucion": id_institucion}
    total, retirados = matriculas_base(func.count(Matricula.id_matricula), RETIRADOS, **filtros).one()
    retirados = int(retirados or 0)
    activas = matriculas_base(func.count(Matricula.id_matricula), **filtros).filter(
        Matricula.estado == "ACTIVA").scalar()
    return {
        "totales": {"matriculas": total, "retirados": retirados, "activas": activas,
                    "tasa": 100 * retirados / total if total else 0},
        "por_institucion": tasa_por(Institucion.nombre, **filtros),
        "por_zona": tasa_por(Estudiante.zona, **filtros),
        "por_estrato": sorted(({**f, "nombre": f"Estrato {f['nombre']}"}
                               for f in tasa_por(Estudiante.estrato, **filtros)),
                              key=lambda f: f["nombre"]),
        "por_causa": retiros_por(CausaRetiro.descripcion, Matricula.causa, "Sin causa", **filtros),
        "por_programa": retiros_por(ProgramaApoyo.nombre, Matricula.programa, "Sin programa", **filtros),
        "retirados": lista_retirados(**filtros),
    }


def hallazgos(d):
    t = d["totales"]
    if not t["retirados"]:
        return ["No hay retiros registrados con estos filtros."]
    texto = [f"{t['retirados']} de {t['matriculas']} matrículas terminaron en retiro ({pct(t['tasa'])})."]
    if d["por_causa"]:
        c = d["por_causa"][0]
        texto.append(f"La causa más frecuente es «{c['nombre']}»: {c['retirados']} de {t['retirados']} retiros.")
    if len(d["por_institucion"]) > 1:
        i = d["por_institucion"][0]
        texto.append(f"{i['nombre']} tiene la tasa más alta: {pct(i['tasa'])} "
                     f"({i['retirados']} de {i['matriculados']}).")
    zonas = {z["nombre"]: z for z in d["por_zona"]}
    if "Rural" in zonas and "Urbana" in zonas:
        texto.append(f"Zona rural: {pct(zonas['Rural']['tasa'])} frente a {pct(zonas['Urbana']['tasa'])} en la urbana.")
    if d["por_estrato"]:
        e = max(d["por_estrato"], key=lambda f: f["tasa"])
        texto.append(f"{e['nombre']} concentra la tasa más alta: {pct(e['tasa'])}.")
    sin_apoyo = next((p for p in d["por_programa"] if p["nombre"] == "Sin programa"), None)
    if sin_apoyo:
        n = sin_apoyo["retirados"]
        texto.append(f"{n} {'retirado no recibía' if n == 1 else 'retirados no recibían'} ningún programa de apoyo.")
    return texto


# ---------- GRÁFICOS ----------
def barras_tasa(filas):
    tope = max((f["tasa"] for f in filas), default=0) or 1
    return [{"nombre": f["nombre"], "ancho": 100 * f["tasa"] / tope, "valor": pct(f["tasa"]),
             "detalle": f"{f['retirados']} de {f['matriculados']} matrículas"} for f in filas]


def barras_conteo(filas):
    tope = max((f["retirados"] for f in filas), default=0) or 1
    return [{"nombre": f["nombre"], "ancho": 100 * f["retirados"] / tope, "valor": str(f["retirados"]),
             "detalle": f"{f['retirados']} {'retiro' if f['retirados'] == 1 else 'retiros'}"} for f in filas]


# ---------- FORMULARIO ----------
def valores_de(e):
    if e is None:
        return {"estado": "ACTIVA"}
    m = matricula_actual(e)
    fn = e.fecha_nacimiento
    return {
        "nombres": e.nombres, "apellidos": e.apellidos,
        "dia": f"{fn.day:02d}" if fn else "", "mes": f"{fn.month:02d}" if fn else "",
        "anio": str(fn.year) if fn else "",
        "sexo": e.sexo or "", "zona": e.zona or "",
        "estrato": "" if e.estrato is None else str(e.estrato),
        "discapacidad": bool(e.discapacidad),
        "id_grupo": str(m.id_grupo) if m else "",
        "estado": m.estado if m else "ACTIVA",
        "id_causa": str(m.id_causa or "") if m else "",
        "id_programa": str(m.id_programa or "") if m else "",
    }


def entero(texto):
    try:
        return int(texto)
    except (TypeError, ValueError):
        return None


def leer_formulario(f):
    d, err = {}, {}

    for campo in ("nombres", "apellidos"):
        d[campo] = f.get(campo, "").strip()
        if not d[campo]:
            err[campo] = "Escriba los " + campo
        elif len(d[campo]) > 100:
            err[campo] = "Máximo 100 caracteres"

    dia, mes, anio = (f.get(k, "").strip() for k in ("dia", "mes", "anio"))
    d["fecha_nacimiento"] = None
    if dia or mes or anio:
        try:
            d["fecha_nacimiento"] = date(int(anio), int(mes), int(dia))
        except ValueError:
            err["fecha"] = "Fecha no válida"
        else:
            if d["fecha_nacimiento"] > date.today():
                err["fecha"] = "La fecha no puede ser futura"

    d["sexo"] = f.get("sexo") or None
    if d["sexo"] and d["sexo"] not in SEXOS:
        err["sexo"] = "Opción no válida"
    d["zona"] = f.get("zona") or None
    if d["zona"] and d["zona"] not in ZONAS:
        err["zona"] = "Opción no válida"
    d["estrato"] = entero(f.get("estrato")) if f.get("estrato") else None
    if f.get("estrato") and d["estrato"] not in ESTRATOS:
        err["estrato"] = "El estrato va de 0 a 6"
    d["discapacidad"] = "discapacidad" in f

    d["id_grupo"] = entero(f.get("id_grupo"))
    if f.get("id_grupo") and not (d["id_grupo"] and db.session.get(Grupo, d["id_grupo"])):
        err["id_grupo"] = "Grupo no válido"
    if d["id_grupo"]:
        d["estado"] = f.get("estado")
        if d["estado"] not in ESTADOS:
            err["estado"] = "Elija un estado"
        d["id_causa"] = entero(f.get("id_causa")) if d["estado"] == "RETIRADO" else None
        if d["estado"] == "RETIRADO" and not (d["id_causa"] and db.session.get(CausaRetiro, d["id_causa"])):
            err["id_causa"] = "Indique la causa del retiro"
        d["id_programa"] = entero(f.get("id_programa"))
        if f.get("id_programa") and not (d["id_programa"] and db.session.get(ProgramaApoyo, d["id_programa"])):
            err["id_programa"] = "Programa no válido"
    return d, err


def guardar_estudiante(e, d):
    for campo in ("nombres", "apellidos", "fecha_nacimiento", "sexo", "zona", "estrato", "discapacidad"):
        setattr(e, campo, d[campo])
    if not d["id_grupo"]:
        return
    m = matricula_actual(e)
    if m is None:
        m = Matricula(fecha=date.today())
        e.matriculas.append(m)
    m.id_grupo, m.estado, m.id_causa, m.id_programa = d["id_grupo"], d["estado"], d["id_causa"], d["id_programa"]


def pintar_formulario(e, valores, errores=None, codigo=200):
    grupos = (Grupo.query.join(Grupo.institucion)
              .options(selectinload(Grupo.institucion))
              .order_by(Institucion.nombre, Grupo.anio_lectivo.desc(), Grupo.grado).all())
    return render_template(
        "estudiante_modal.html" if request.headers.get("X-Modal") else "estudiante_form.html", e=e, v=valores, errores=errores or {},
        grupos=grupos,
        causas=CausaRetiro.query.order_by(CausaRetiro.descripcion).all(),
        programas=ProgramaApoyo.query.order_by(ProgramaApoyo.nombre).all(),
    ), codigo


def procesar_formulario(e, mensaje):
    d, errores = leer_formulario(request.form)
    valores = {**request.form.to_dict(), "discapacidad": "discapacidad" in request.form}
    if errores:
        return pintar_formulario(e, valores, errores, 422)
    nuevo = e is None
    e = e or Estudiante()
    guardar_estudiante(e, d)
    if nuevo:
        db.session.add(e)
    try:
        db.session.commit()
    except IntegrityError:
        db.session.rollback()
        return pintar_formulario(None if nuevo else e, valores, {"id_grupo": "Ya tiene una matrícula en ese grupo"}, 409)
    flash(f"{e.nombres} {e.apellidos}: {mensaje}", "ok")
    if request.headers.get("X-Modal"):
        return "", 204
    return redirect(url_for("listar"))


# ---------- PÁGINAS ----------
@app.route("/")
def index():
    return redirect(url_for("listar"))


@app.route("/estudiantes")
def listar():
    zona, id_inst = leer_filtros()
    filas = estudiantes(zona, id_inst)
    return render_template(
        "estudiantes.html", filas=filas, zona=zona, inst=institucion_o_none(id_inst),
        instituciones=Institucion.query.order_by(Institucion.nombre).all(),
        resumen=estados_por_zona(filas if not zona else estudiantes(None, id_inst)),
    )


@app.route("/estudiantes/nuevo", methods=["GET", "POST"])
def crear():
    if request.method == "POST":
        return procesar_formulario(None, "registrado")
    return pintar_formulario(None, valores_de(None))


@app.route("/estudiantes/<int:id>/editar", methods=["GET", "POST"])
def editar(id):
    e = db.get_or_404(Estudiante, id)
    if request.method == "POST":
        return procesar_formulario(e, "cambios guardados")
    return pintar_formulario(e, valores_de(e))


@app.route("/estudiantes/<int:id>/eliminar", methods=["POST"])
def eliminar(id):
    e = db.get_or_404(Estudiante, id)
    nombre, n = f"{e.nombres} {e.apellidos}", len(e.matriculas)
    try:
        db.session.delete(e)
        db.session.commit()
        flash(f"{nombre}: eliminado", "ok")
    except IntegrityError:
        db.session.rollback()
        flash(f"No se puede eliminar a {nombre}: tiene {n} {'matrícula' if n == 1 else 'matrículas'}. "
              "Si dejó de estudiar, márquelo como Retirado.", "error")
    return redirect(url_for("listar"))


@app.route("/desercion")
def ver_desercion():
    zona, id_inst = leer_filtros()
    d = desercion(zona, id_inst)
    return render_template(
        "desercion.html", d=d, zona=zona, inst=institucion_o_none(id_inst),
        instituciones=Institucion.query.order_by(Institucion.nombre).all(),
        hallazgos=hallazgos(d), hoy=date.today(),
        graficos=[
            ("Tasa de deserción por institución", barras_tasa(d["por_institucion"])),
            ("Retiros por causa", barras_conteo(d["por_causa"])),
            ("Tasa de deserción por zona", barras_tasa(d["por_zona"])),
            ("Tasa de deserción por estrato", barras_tasa(d["por_estrato"])),
            ("Retiros por programa de apoyo", barras_conteo(d["por_programa"])),
        ],
    )


@app.route("/desercion/reporte")
def reporte():
    zona, id_inst = leer_filtros()
    d = desercion(zona, id_inst)
    inst = institucion_o_none(id_inst)
    alcance = " · ".join([f"zona {zona.lower()}" if zona else "todas las zonas",
                          inst.nombre if inst else "todas las instituciones"])
    nombre = f"reporte_desercion_{date.today().isoformat()}"
    filas = [[r["nombre"], r["institucion"], r["grado"], r["zona"] or "Sin dato",
              "Sin dato" if r["estrato"] is None else r["estrato"], date.fromisoformat(r["fecha"]),
              r["causa"] or "Sin causa", r["programa"] or "Ninguno"] for r in d["retirados"]]
    try:
        return Response(libro_excel(d, filas, alcance), headers={"Content-Disposition": f"attachment; filename={nombre}.xlsx"},
                        mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
    except ImportError:
        salida = io.StringIO()
        w = csv.writer(salida, delimiter=";")
        w.writerow(COLUMNAS_REPORTE)
        w.writerows([*f[:5], f[5].strftime("%d/%m/%Y"), *f[6:]] for f in filas)
        return Response("﻿" + salida.getvalue(), mimetype="text/csv",
                        headers={"Content-Disposition": f"attachment; filename={nombre}.csv"})


# ---------- REPORTE EXCEL ----------
COLUMNAS_REPORTE = ["Estudiante", "Institución", "Grado", "Zona", "Estrato", "Fecha de retiro", "Causa", "Programa de apoyo"]


def libro_excel(d, filas, alcance):
    from openpyxl import Workbook
    from openpyxl.styles import Alignment, Font, PatternFill
    from openpyxl.utils import get_column_letter

    negrita, tenue = Font(bold=True, color="FFFFFF"), Font(color="5D6662")
    fondo = PatternFill("solid", fgColor="165C4B")
    libro = Workbook()

    def tabla(hoja, fila, titulo, cabecera, datos, formatos=None):
        hoja.cell(fila, 1, titulo).font = Font(bold=True, size=12, color="165C4B")
        for c, texto in enumerate(cabecera, 1):
            celda = hoja.cell(fila + 1, c, texto)
            celda.font, celda.fill = negrita, fondo
        for i, datos_fila in enumerate(datos, fila + 2):
            for c, valor in enumerate(datos_fila, 1):
                celda = hoja.cell(i, c, valor)
                if formatos and c in formatos:
                    celda.number_format = formatos[c]
        return fila + len(datos) + 3

    def anchos(hoja):
        for col in hoja.iter_cols(min_row=3):
            largo = max((len(str(c.value)) for c in col if c.value is not None), default=8)
            hoja.column_dimensions[get_column_letter(col[0].column)].width = min(max(largo + 2, 10), 42)

    # Hoja 1: retirados
    hoja = libro.active
    hoja.title = "Retirados"
    hoja["A1"] = "Reporte de deserción escolar"
    hoja["A1"].font = Font(bold=True, size=14, color="165C4B")
    hoja["A2"] = f"{date.today().strftime('%d/%m/%Y')} · {alcance}"
    hoja["A2"].font = tenue
    t = d["totales"]
    for c, (texto, valor) in enumerate([("Matrículas", t["matriculas"]), ("Activas", t["activas"]),
                                        ("Retirados", t["retirados"]), ("Tasa de deserción", t["tasa"] / 100)], 1):
        hoja.cell(4, c, texto).font = tenue
        celda = hoja.cell(5, c, valor)
        celda.font = Font(bold=True, size=13)
        if c == 4:
            celda.number_format = "0.0 %"
    fin = tabla(hoja, 7, f"Estudiantes retirados · {len(filas)}", COLUMNAS_REPORTE, filas, {6: "DD/MM/YYYY"})
    if filas:
        hoja.auto_filter.ref = f"A8:H{fin - 3}"
    hoja.freeze_panes = "A9"
    for fila in hoja.iter_rows(min_row=9):
        for celda in fila:
            celda.alignment = Alignment(vertical="top", wrap_text=True)
    anchos(hoja)
    hoja.column_dimensions["A"].width = max(hoja.column_dimensions["A"].width, 18)

    # Hoja 2: estadísticas
    hoja = libro.create_sheet("Estadísticas")
    fila = 1
    for titulo, clave in [("Tasa por institución", "por_institucion"), ("Tasa por zona", "por_zona"),
                          ("Tasa por estrato", "por_estrato")]:
        datos = [[f["nombre"], f["matriculados"], f["retirados"], f["tasa"] / 100] for f in d[clave]]
        fila = tabla(hoja, fila, titulo, ["Grupo", "Matrículas", "Retirados", "Tasa"], datos, {4: "0.0 %"})
    for titulo, clave in [("Retiros por causa", "por_causa"), ("Retiros por programa de apoyo", "por_programa")]:
        fila = tabla(hoja, fila, titulo, ["Grupo", "Retiros"], [[f["nombre"], f["retirados"]] for f in d[clave]])
    anchos(hoja)

    salida = io.BytesIO()
    libro.save(salida)
    return salida.getvalue()


# ---------- API: LECTURA ----------
def json_institucion(i):
    return {"id": i.id_institucion, "nombre": i.nombre, "tipo": i.tipo, "municipio": i.municipio, "zona": i.zona}


def json_grupo(g):
    return {"id": g.id_grupo, "grado": g.grado, "jornada": g.jornada, "anio_lectivo": g.anio_lectivo,
            "id_institucion": g.id_institucion, "institucion": g.institucion.nombre}


def json_causa(c):
    return {"id": c.id_causa, "descripcion": c.descripcion}


def json_programa(p):
    return {"id": p.id_programa, "nombre": p.nombre, "tipo": p.tipo}


@app.get("/api/instituciones")
def api_instituciones():
    return jsonify([json_institucion(i) for i in Institucion.query.order_by(Institucion.nombre)])


@app.get("/api/estudiantes")
def api_estudiantes():
    zona, id_inst = leer_filtros()
    return jsonify(estudiantes(zona, id_inst))


@app.get("/api/estudiantes/<int:id>")
def api_estudiante(id):
    return jsonify(fila_estudiante(db.get_or_404(Estudiante, id)))


@app.get("/api/zonas")
def api_zonas():
    _, id_inst = leer_filtros()
    return jsonify([{"zona": z["zona"], "total": z["total"],
                     "estados": {ESTADO_TEXTO[s["estado"]]: s["n"] for s in z["segmentos"]}}
                    for z in estados_por_zona(estudiantes(None, id_inst))])


@app.get("/api/desercion")
def api_desercion():
    zona, id_inst = leer_filtros()
    d = desercion(zona, id_inst)
    return jsonify({**d, "hallazgos": hallazgos(d)})


@app.get("/api/grupos")
def api_grupos():
    _, id_inst = leer_filtros()
    q = Grupo.query.options(selectinload(Grupo.institucion)).order_by(Grupo.anio_lectivo.desc(), Grupo.grado)
    if id_inst:
        q = q.filter(Grupo.id_institucion == id_inst)
    return jsonify([json_grupo(g) for g in q])


@app.get("/api/causas")
def api_causas():
    return jsonify([json_causa(c) for c in CausaRetiro.query.order_by(CausaRetiro.descripcion)])


@app.get("/api/programas")
def api_programas():
    return jsonify([json_programa(p) for p in ProgramaApoyo.query.order_by(ProgramaApoyo.nombre)])


# ---------- API: ESCRITURA ----------
# POST crea, PUT cambia sólo los campos enviados y DELETE borra si nada lo usa.
def error_json(mensaje, codigo, campos=None):
    cuerpo = {"error": mensaje}
    if campos:
        cuerpo["campos"] = campos
    return jsonify(cuerpo), codigo


def cuerpo_json():
    cuerpo = request.get_json(silent=True)
    return cuerpo if isinstance(cuerpo, dict) else None


def confirmar(obj, nuevo, choque):
    if nuevo:
        db.session.add(obj)
    try:
        db.session.commit()
    except IntegrityError:
        db.session.rollback()
        return False, error_json(choque, 409)
    return True, None


def eliminar_api(obj, datos, n, uno, varios):
    if n:
        return error_json(f"No se puede eliminar: aparece en {n} {uno if n == 1 else varios}", 409)
    db.session.delete(obj)
    ok, fallo = confirmar(obj, False, "No se puede eliminar: otros registros lo usan")
    return jsonify({"eliminado": datos}) if ok else fallo


CAMPOS_ESTUDIANTE = ("nombres", "apellidos", "fecha_nacimiento", "sexo", "zona", "estrato", "discapacidad",
                     "id_grupo", "estado", "id_causa", "id_programa")


def leer_estudiante_json(e, cuerpo):
    # Traduce el JSON al formato del formulario para validar con las mismas reglas.
    err = {k: "Campo desconocido" for k in cuerpo if k not in CAMPOS_ESTUDIANTE}
    f = valores_de(e)
    for k, v in cuerpo.items():
        if k == "fecha_nacimiento":
            f["dia"] = f["mes"] = f["anio"] = ""
            if v:
                try:
                    fn = date.fromisoformat(str(v))
                    f["dia"], f["mes"], f["anio"] = str(fn.day), str(fn.month), str(fn.year)
                except ValueError:
                    err[k] = "Use el formato AAAA-MM-DD"
        elif k == "discapacidad":
            f[k] = bool(v)
        elif k in CAMPOS_ESTUDIANTE:
            f[k] = "" if v is None else str(v)
    if f.pop("discapacidad", False):
        f["discapacidad"] = "on"
    d, errores = leer_formulario(f)
    if "fecha" in errores:
        errores["fecha_nacimiento"] = errores.pop("fecha")
    return d, {**err, **errores}


def escribir_estudiante(e):
    cuerpo = cuerpo_json()
    if cuerpo is None:
        return error_json("El cuerpo debe ser un objeto JSON", 400)
    d, err = leer_estudiante_json(e, cuerpo)
    if err:
        return error_json("Datos no válidos", 422, err)
    nuevo = e is None
    e = e or Estudiante()
    guardar_estudiante(e, d)
    ok, fallo = confirmar(e, nuevo, "Ya tiene una matrícula en ese grupo")
    return (jsonify(fila_estudiante(e)), 201 if nuevo else 200) if ok else fallo


@app.post("/api/estudiantes")
def api_crear_estudiante():
    return escribir_estudiante(None)


@app.put("/api/estudiantes/<int:id>")
def api_editar_estudiante(id):
    return escribir_estudiante(db.get_or_404(Estudiante, id))


@app.delete("/api/estudiantes/<int:id>")
def api_eliminar_estudiante(id):
    e = db.get_or_404(Estudiante, id)
    return eliminar_api(e, fila_estudiante(e), len(e.matriculas), "matrícula", "matrículas")


# Catálogos: campo -> (tipo, largo máximo, obligatorio).
CATALOGOS = {
    "instituciones": {"modelo": Institucion, "json": json_institucion, "uso": ("grupos", "grupo", "grupos"),
                      "campos": {"nombre": ("texto", 150, True), "tipo": ("texto", 20, False),
                                 "municipio": ("texto", 100, False), "zona": ("zona", None, False)}},
    "grupos": {"modelo": Grupo, "json": json_grupo, "uso": ("matriculas", "matrícula", "matrículas"),
               "campos": {"grado": ("texto", 20, True), "jornada": ("texto", 30, False),
                          "anio_lectivo": ("anio", None, True), "id_institucion": ("institucion", None, True)}},
    "causas": {"modelo": CausaRetiro, "json": json_causa, "uso": ("matriculas", "matrícula", "matrículas"),
               "campos": {"descripcion": ("texto", 255, True)}},
    "programas": {"modelo": ProgramaApoyo, "json": json_programa, "uso": ("matriculas", "matrícula", "matrículas"),
                  "campos": {"nombre": ("texto", 150, True), "tipo": ("texto", 30, False)}},
}
CATALOGO = "any(instituciones, grupos, causas, programas)"


def leer_catalogo(campos, cuerpo, nuevo):
    d = {}
    err = {k: "Campo desconocido" for k in cuerpo if k not in campos}
    for k, (tipo, largo, requerido) in campos.items():
        if k not in cuerpo:
            if nuevo and requerido:
                err[k] = "Obligatorio"
            continue
        v = cuerpo[k].strip() if isinstance(cuerpo[k], str) else cuerpo[k]
        n = None if isinstance(v, bool) else entero(v)
        if v in (None, ""):
            if requerido:
                err[k] = "Obligatorio"
            else:
                d[k] = None
        elif tipo == "texto":
            if not isinstance(v, str):
                err[k] = "Debe ser texto"
            elif len(v) > largo:
                err[k] = f"Máximo {largo} caracteres"
            else:
                d[k] = v
        elif tipo == "zona":
            if v in ZONAS:
                d[k] = v
            else:
                err[k] = "Urbana o Rural"
        elif tipo == "anio":
            if n and 1990 <= n <= 2100:
                d[k] = n
            else:
                err[k] = "Año entre 1990 y 2100"
        elif tipo == "institucion":
            if n and db.session.get(Institucion, n):
                d[k] = n
            else:
                err[k] = "No existe esa institución"
    return d, err


def escribir_catalogo(ruta, obj):
    c = CATALOGOS[ruta]
    cuerpo = cuerpo_json()
    if cuerpo is None:
        return error_json("El cuerpo debe ser un objeto JSON", 400)
    nuevo = obj is None
    d, err = leer_catalogo(c["campos"], cuerpo, nuevo)
    if err:
        return error_json("Datos no válidos", 422, err)
    obj = obj or c["modelo"]()
    for k, v in d.items():
        setattr(obj, k, v)
    ok, fallo = confirmar(obj, nuevo, "Choca con un registro que ya existe")
    return (jsonify(c["json"](obj)), 201 if nuevo else 200) if ok else fallo


@app.get(f"/api/<{CATALOGO}:ruta>/<int:id>")
def api_catalogo_uno(ruta, id):
    c = CATALOGOS[ruta]
    return jsonify(c["json"](db.get_or_404(c["modelo"], id)))


@app.post(f"/api/<{CATALOGO}:ruta>")
def api_catalogo_crear(ruta):
    return escribir_catalogo(ruta, None)


@app.put(f"/api/<{CATALOGO}:ruta>/<int:id>")
def api_catalogo_editar(ruta, id):
    return escribir_catalogo(ruta, db.get_or_404(CATALOGOS[ruta]["modelo"], id))


@app.delete(f"/api/<{CATALOGO}:ruta>/<int:id>")
def api_catalogo_eliminar(ruta, id):
    c = CATALOGOS[ruta]
    obj = db.get_or_404(c["modelo"], id)
    relacion, uno, varios = c["uso"]
    return eliminar_api(obj, c["json"](obj), len(getattr(obj, relacion)), uno, varios)


# ---------- DOCUMENTACIÓN DE LA API ----------
# Valores de ejemplo que se cambian por ids reales al pintar la página.
UN_GRUPO, UNA_INSTITUCION = "<grupo>", "<institucion>"

P_ZONA = {"nombre": "zona", "en": "query", "tipo": "zona", "desc": "Urbana o Rural. Si no se envía, trae las dos."}
P_INST = {"nombre": "institucion", "en": "query", "tipo": "institucion", "desc": "id de la institución. Si no se envía, trae todas."}

R_LISTA = [(200, "Lista JSON")]
R_UNO = [(200, "El objeto"), (404, "No existe ese id")]
R_CREAR = [(201, "Creado: devuelve el objeto nuevo con su id"), (400, "El cuerpo no es un objeto JSON"),
           (422, "Datos no válidos: «campos» dice qué falló en cada uno"), (409, "Choca con un registro que ya existe")]
R_EDITAR = [(200, "Guardado: devuelve el objeto actualizado"), (400, "El cuerpo no es un objeto JSON"),
            (404, "No existe ese id"), (422, "Datos no válidos: «campos» dice qué falló en cada uno")]
R_BORRAR = [(200, "Eliminado: devuelve lo que se borró"), (404, "No existe ese id"),
            (409, "No se puede: otros registros lo usan")]


def p_id(recurso, que):
    return {"nombre": "id", "en": "path", "tipo": recurso, "desc": f"id {que}.", "requerido": True}


def crud(recurso, grupo, que, campos, cuerpo, crear, editar, uso):
    # Las cuatro consultas por id de un recurso: leer uno, crear, cambiar y borrar.
    ruta, uno = f"/api/{recurso}", f"/api/{recurso}/{{id}}"
    base = {"grupo": grupo, "recurso": recurso}
    return [
        {**base, "id": f"{recurso}-uno", "metodo": "GET", "ruta": uno, "params": [p_id(recurso, que)],
         "resumen": f"Leer {que} por su id", "desc": f"Mismos campos que la lista. Si el id no existe responde 404.",
         "campos": [("…", "", f"Igual que GET {ruta}")], "codigos": R_UNO},
        {**base, "id": f"{recurso}-crear", "metodo": "POST", "ruta": ruta, "params": [], "cuerpo": cuerpo,
         "ejemplo": crear, "resumen": f"Crear {que}",
         "desc": "Envía el cuerpo en JSON. Los campos obligatorios deben ir; los demás pueden faltar o ser null.",
         "campos": campos, "codigos": R_CREAR},
        {**base, "id": f"{recurso}-editar", "metodo": "PUT", "ruta": uno, "params": [p_id(recurso, que)],
         "cuerpo": cuerpo, "ejemplo": editar, "resumen": f"Cambiar {que}",
         "desc": "Envía sólo los campos que quieres cambiar; los demás se quedan como están.",
         "campos": campos, "codigos": R_EDITAR},
        {**base, "id": f"{recurso}-borrar", "metodo": "DELETE", "ruta": uno, "params": [p_id(recurso, que)],
         "resumen": f"Eliminar {que}",
         "desc": f"Borra el registro. Si {uso}, responde 409 y no borra nada.",
         "campos": [("eliminado", "objeto", "El registro tal como estaba")], "codigos": R_BORRAR},
    ]


C_ESTUDIANTE = [("id", "entero", "id_estudiante"), ("nombre", "texto", "Nombres y apellidos"),
                ("sexo", "texto", "Femenino, Masculino o null"), ("zona", "texto", "Urbana, Rural o null"),
                ("estrato", "entero", "0 a 6 o null"), ("discapacidad", "booleano", ""),
                ("id_institucion · institucion", "entero · texto", "Institución de la matrícula"),
                ("grado · jornada", "texto", "Grupo de la matrícula"),
                ("estado", "texto", "ACTIVA, RETIRADO, GRADUADO o null"),
                ("causa · programa", "texto", "Causa del retiro y programa de apoyo, o null")]
B_ESTUDIANTE = [("nombres", "texto", True, "Hasta 100 caracteres"), ("apellidos", "texto", True, "Hasta 100 caracteres"),
                ("fecha_nacimiento", "texto", False, "AAAA-MM-DD, no futura"), ("sexo", "texto", False, "Femenino o Masculino"),
                ("zona", "texto", False, "Urbana o Rural"), ("estrato", "entero", False, "0 a 6"),
                ("discapacidad", "booleano", False, "true o false"),
                ("id_grupo", "entero", False, "Grupo de la matrícula; ver GET /api/grupos"),
                ("estado", "texto", False, "ACTIVA, RETIRADO o GRADUADO; obligatorio si hay id_grupo"),
                ("id_causa", "entero", False, "Obligatorio si el estado es RETIRADO; ver GET /api/causas"),
                ("id_programa", "entero", False, "Programa de apoyo; ver GET /api/programas")]
C_INSTITUCION = [("id", "entero", "id_institucion"), ("nombre", "texto", ""), ("tipo", "texto", ""),
                 ("municipio", "texto", ""), ("zona", "texto", "Urbana o Rural")]
B_INSTITUCION = [("nombre", "texto", True, "Hasta 150 caracteres"), ("tipo", "texto", False, "Oficial, Privado… hasta 20"),
                 ("municipio", "texto", False, "Hasta 100 caracteres"), ("zona", "texto", False, "Urbana o Rural")]
C_GRUPO = [("id", "entero", "id_grupo"), ("grado · jornada", "texto", ""), ("anio_lectivo", "entero", ""),
           ("id_institucion · institucion", "entero · texto", "")]
B_GRUPO = [("grado", "texto", True, "Hasta 20 caracteres, p. ej. 7B"), ("jornada", "texto", False, "Mañana, Tarde, Única…"),
           ("anio_lectivo", "entero", True, "1990 a 2100"), ("id_institucion", "entero", True, "Ver GET /api/instituciones")]
C_CAUSA = [("id", "entero", "id_causa"), ("descripcion", "texto", "")]
B_CAUSA = [("descripcion", "texto", True, "Hasta 255 caracteres")]
C_PROGRAMA = [("id", "entero", "id_programa"), ("nombre", "texto", ""), ("tipo", "texto", "")]
B_PROGRAMA = [("nombre", "texto", True, "Hasta 150 caracteres"), ("tipo", "texto", False, "Económico, Transporte… hasta 30")]

API = [
    {"id": "estudiantes", "grupo": "Estudiantes", "recurso": "estudiantes", "metodo": "GET", "ruta": "/api/estudiantes",
     "params": [P_ZONA, P_INST], "resumen": "Lista de estudiantes con su matrícula más reciente",
     "desc": "Un objeto por estudiante, ordenados por apellido. Los datos de matrícula salen en null si no tiene ninguna.",
     "campos": C_ESTUDIANTE, "codigos": R_LISTA},
    *crud("estudiantes", "Estudiantes", "un estudiante", C_ESTUDIANTE, B_ESTUDIANTE,
          {"nombres": "Laura", "apellidos": "Gómez Ruiz", "fecha_nacimiento": "2012-03-14", "sexo": "Femenino",
           "zona": "Rural", "estrato": 2, "discapacidad": False, "id_grupo": UN_GRUPO, "estado": "ACTIVA",
           "id_causa": None, "id_programa": None},
          {"zona": "Urbana", "estrato": 3}, "tiene matrículas"),
    {"id": "zonas", "grupo": "Estudiantes", "metodo": "GET", "ruta": "/api/zonas", "params": [P_INST],
     "resumen": "Estudiantes por zona y estado de matrícula",
     "desc": "Cuenta a los estudiantes de cada zona según el estado de su matrícula más reciente.",
     "campos": [("zona", "texto", "Urbana, Rural o Sin dato"), ("total", "entero", "Estudiantes de la zona"),
                ("estados", "objeto", "Estado → número de estudiantes")], "codigos": R_LISTA},
    {"id": "desercion", "grupo": "Deserción", "metodo": "GET", "ruta": "/api/desercion", "params": [P_ZONA, P_INST],
     "resumen": "Reporte de deserción completo",
     "desc": "Lo mismo que muestra la pantalla Deserción: totales, tasas por grupo, causas, programas y la lista de retirados. "
             "Sólo se lee: cambia al crear, editar o borrar estudiantes.",
     "campos": [("totales", "objeto", "matriculas, activas, retirados y tasa (%)"),
                ("por_institucion · por_zona · por_estrato", "lista", "nombre, matriculados, retirados y tasa (%)"),
                ("por_causa · por_programa", "lista", "nombre y retirados"),
                ("retirados", "lista", "Estudiantes retirados: institución, grado, fecha, causa y programa"),
                ("hallazgos", "lista", "Frases que resumen el reporte")], "codigos": R_LISTA},
    {"id": "instituciones", "grupo": "Instituciones", "recurso": "instituciones", "metodo": "GET",
     "ruta": "/api/instituciones", "params": [], "resumen": "Lista de instituciones educativas",
     "desc": "Ordenadas por nombre.", "campos": C_INSTITUCION, "codigos": R_LISTA},
    *crud("instituciones", "Instituciones", "una institución", C_INSTITUCION, B_INSTITUCION,
          {"nombre": "IE Los Almendros", "tipo": "Oficial", "municipio": "Santa Rosa", "zona": "Rural"},
          {"municipio": "La Virginia"}, "tiene grupos"),
    {"id": "grupos", "grupo": "Grupos", "recurso": "grupos", "metodo": "GET", "ruta": "/api/grupos", "params": [P_INST],
     "resumen": "Lista de grupos por institución y año", "desc": "Del año lectivo más reciente al más antiguo.",
     "campos": C_GRUPO, "codigos": R_LISTA},
    *crud("grupos", "Grupos", "un grupo", C_GRUPO, B_GRUPO,
          {"grado": "7B", "jornada": "Tarde", "anio_lectivo": 2026, "id_institucion": UNA_INSTITUCION},
          {"jornada": "Mañana"}, "tiene matrículas"),
    {"id": "causas", "grupo": "Causas de retiro", "recurso": "causas", "metodo": "GET", "ruta": "/api/causas",
     "params": [], "resumen": "Lista de causas de retiro",
     "desc": "Las opciones que se eligen al marcar a un estudiante como retirado.", "campos": C_CAUSA, "codigos": R_LISTA},
    *crud("causas", "Causas de retiro", "una causa", C_CAUSA, B_CAUSA,
          {"descripcion": "Distancia al colegio"}, {"descripcion": "Distancia entre la casa y el colegio"},
          "alguna matrícula la usa"),
    {"id": "programas", "grupo": "Programas de apoyo", "recurso": "programas", "metodo": "GET", "ruta": "/api/programas",
     "params": [], "resumen": "Lista de programas de apoyo", "desc": "Programas que se pueden asignar a una matrícula.",
     "campos": C_PROGRAMA, "codigos": R_LISTA},
    *crud("programas", "Programas de apoyo", "un programa", C_PROGRAMA, B_PROGRAMA,
          {"nombre": "Útiles escolares", "tipo": "Económico"}, {"tipo": "Material"}, "alguna matrícula lo usa"),
]


@app.get("/api")
def api_docs():
    grupos_bd = Grupo.query.join(Grupo.institucion).options(contains_eager(Grupo.institucion)) \
        .order_by(Institucion.nombre, Grupo.anio_lectivo.desc(), Grupo.grado).all()
    instituciones = Institucion.query.order_by(Institucion.nombre).all()
    opciones = {
        "estudiantes": [(e.id_estudiante, f"{e.nombres} {e.apellidos}")
                        for e in Estudiante.query.order_by(Estudiante.apellidos, Estudiante.nombres)],
        "instituciones": [(i.id_institucion, i.nombre) for i in instituciones],
        "grupos": [(g.id_grupo, f"{g.grado} · {g.institucion.nombre} · {g.anio_lectivo}") for g in grupos_bd],
        "causas": [(c.id_causa, c.descripcion) for c in CausaRetiro.query.order_by(CausaRetiro.descripcion)],
        "programas": [(p.id_programa, p.nombre) for p in ProgramaApoyo.query.order_by(ProgramaApoyo.nombre)],
    }
    ids = {UN_GRUPO: grupos_bd[0].id_grupo if grupos_bd else None,
           UNA_INSTITUCION: instituciones[0].id_institucion if instituciones else None}
    api = [{**a, "ejemplo": {k: ids.get(v, v) if isinstance(v, str) else v for k, v in a["ejemplo"].items()}}
           if "ejemplo" in a else a for a in API]
    grupos = {}
    for a in api:
        grupos.setdefault(a["grupo"], []).append(a)
    return render_template("api.html", api=api, grupos=grupos.items(), opciones=opciones)


# ---------- ERRORES ----------
@app.errorhandler(OperationalError)
def sin_base(e):
    db.session.rollback()
    if request.path.startswith("/api/"):
        return jsonify({"error": "Sin conexión con la base de datos"}), 503
    return render_template("sin_base.html", detalle=str(e.orig)), 503


@app.errorhandler(404)
def no_existe(e):
    if request.path.startswith("/api/"):
        return jsonify({"error": "No existe ese recurso"}), 404
    return e


@app.errorhandler(405)
def metodo_no_permitido(e):
    if request.path.startswith("/api/"):
        return jsonify({"error": f"{request.method} no se puede usar en esta ruta"}), 405
    return e


if __name__ == "__main__":
    app.run(debug=True)
