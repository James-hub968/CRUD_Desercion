# validators.py
from datetime import date, datetime

SEXOS_VALIDOS = {"Femenino", "Masculino", "Otro", "Sin dato"}
ZONAS_VALIDAS = {"Urbana", "Rural", "Sin dato"}

def _leer_fecha(form):
    raw = (form.get("fecha_nacimiento") or "").strip()
    if not raw: return None, None
    try:
        f = datetime.strptime(raw, "%Y-%m-%d").date()
        if f > date.today(): return None, "La fecha no puede ser futura"
        return f, None
    except ValueError:
        return None, "Fecha no válida"

def leer_formulario(e, form):
    errores = {}
    nombres = (form.get("nombres") or "").strip()
    apellidos = (form.get("apellidos") or "").strip()
    
    if not nombres: errores["nombres"] = "Obligatorio"
    if not apellidos: errores["apellidos"] = "Obligatorio"

    fecha, error_fecha = _leer_fecha(form)
    if error_fecha: errores["fecha_nacimiento"] = error_fecha

    sexo = (form.get("sexo") or "").strip() or None
    if sexo and sexo not in SEXOS_VALIDOS: errores["sexo"] = "No permitido"

    zona = (form.get("zona") or "").strip() or None
    if zona and zona not in ZONAS_VALIDAS: errores["zona"] = "No permitido"

    estrato_raw = (form.get("estrato") or "").strip()
    estrato = None
    if estrato_raw:
        try:
            estrato = int(estrato_raw)
            if not (0 <= estrato <= 6): errores["estrato"] = "Entre 0 y 6"
        except ValueError:
            errores["estrato"] = "Debe ser número"

    if "nombres" not in errores: e.nombres = nombres
    if "apellidos" not in errores: e.apellidos = apellidos
    if "fecha_nacimiento" not in errores: e.fecha_nacimiento = fecha
    if "sexo" not in errores: e.sexo = sexo
    if "zona" not in errores: e.zona = zona
    if "estrato" not in errores: e.estrato = estrato
    e.discapacidad = "discapacidad" in form
    
    return errores