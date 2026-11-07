"use strict";

// ---------- CABECERA ----------
(() => {
  const barra = document.querySelector(".topbar");
  if (!barra) return;
  let pendiente = false;
  const pintar = () => { barra.classList.toggle("is-scrolled", scrollY > 4); pendiente = false; };
  addEventListener("scroll", () => { if (!pendiente) { pendiente = true; requestAnimationFrame(pintar); } }, { passive: true });
  pintar();
})();

// ---------- AVISOS ----------
document.querySelectorAll(".aviso").forEach((aviso, i) => {
  const cerrar = () => {
    aviso.classList.add("is-saliendo");
    aviso.classList.remove("is-visible");
    setTimeout(() => aviso.remove(), 160);
  };
  requestAnimationFrame(() => setTimeout(() => aviso.classList.add("is-visible"), i * 60));
  aviso.querySelector(".aviso__cerrar")?.addEventListener("click", cerrar);
  if (!aviso.classList.contains("aviso--ok")) return;
  let restante = 4000, inicio, reloj;
  const correr = () => { inicio = Date.now(); reloj = setTimeout(cerrar, restante); };
  const pausar = () => { clearTimeout(reloj); restante -= Date.now() - inicio; };
  aviso.addEventListener("pointerenter", pausar);
  aviso.addEventListener("pointerleave", correr);
  aviso.addEventListener("focusin", pausar);
  aviso.addEventListener("focusout", correr);
  correr();
});

// ---------- FILTROS ----------
document.querySelectorAll("[data-autoenvio]").forEach(sel =>
  sel.addEventListener("change", () => sel.form.requestSubmit()));

// ---------- BÚSQUEDA ----------
(() => {
  const campo = document.getElementById("buscar");
  const filas = [...document.querySelectorAll("tr[data-fila]")];
  if (!campo || !filas.length) return;
  const contador = document.querySelector("[data-contador]");
  const vacio = document.querySelector("[data-vacio-busqueda]");
  const tabla = filas[0].closest("table");
  const normal = t => t.normalize("NFD").replace(/[̀-ͯ]/g, "").toLowerCase().trim();
  const textos = filas.map(f => normal(f.dataset.fila));
  campo.addEventListener("keydown", ev => { if (ev.key === "Enter") ev.preventDefault(); });
  campo.addEventListener("input", () => {
    const q = normal(campo.value);
    let n = 0;
    filas.forEach((f, i) => {
      const ver = !q || textos[i].includes(q);
      f.hidden = !ver;
      if (ver) f.classList.toggle("alt", n++ % 2 === 1);
    });
    contador.textContent = q ? `${n} de ${filas.length}` : filas.length;
    tabla.hidden = n === 0;
    vacio.hidden = n !== 0;
    vacio.querySelector("q").textContent = campo.value.trim();
  });
})();

// ---------- ELIMINAR ----------
(() => {
  const dlg = document.querySelector("dialog.confirmar");
  if (!dlg) return;
  let form = null;
  const cerrar = () => {
    dlg.classList.remove("is-visible");
    setTimeout(() => dlg.close(), 150);
  };
  document.querySelectorAll(".form-eliminar").forEach(f => f.addEventListener("submit", ev => {
    if (f.dataset.confirmado) return;
    ev.preventDefault();
    form = f;
    dlg.querySelector("[data-nombre]").textContent = f.dataset.nombre;
    dlg.showModal();
    const r = f.querySelector("button").getBoundingClientRect();
    const d = dlg.getBoundingClientRect();
    dlg.style.transformOrigin = `${r.left + r.width / 2 - d.left}px ${r.top + r.height / 2 - d.top}px`;
    dlg.querySelector("[data-cancelar]").focus();
    requestAnimationFrame(() => dlg.classList.add("is-visible"));
  }));
  dlg.querySelector("[data-cancelar]").addEventListener("click", cerrar);
  dlg.addEventListener("cancel", ev => { ev.preventDefault(); cerrar(); });
  dlg.addEventListener("click", ev => { if (ev.target === dlg) cerrar(); });
  dlg.querySelector("[data-confirmar]").addEventListener("click", () => {
    if (!form) return;
    form.dataset.confirmado = "1";
    dlg.querySelector("[data-confirmar]").disabled = true;
    form.requestSubmit();
  });
})();

// ---------- FORMULARIO ----------
function prepararFormulario(form) {
  if (!form) return;

  form.querySelectorAll("[data-salta]").forEach(c => c.addEventListener("input", () => {
    c.value = c.value.replace(/\D/g, "");
    if (c.value.length >= c.maxLength) c.closest("label").nextElementSibling?.querySelector("input")?.focus();
  }));
  form.querySelector("[name=anio]")?.addEventListener("input", ev => { ev.target.value = ev.target.value.replace(/\D/g, ""); });

  const grupo = form.querySelector("#id_grupo");
  const bloque = form.querySelector("[data-requiere-grupo]");
  const causa = form.querySelector("[data-solo-retirado]");
  const selCausa = form.querySelector("#id_causa");
  const sincronizar = () => {
    const conGrupo = !!grupo?.value;
    if (bloque) bloque.hidden = !conGrupo;
    const retirado = conGrupo && form.querySelector("[name=estado]:checked")?.value === "RETIRADO";
    if (causa) causa.hidden = !retirado;
    if (selCausa) selCausa.required = retirado;
  };
  grupo?.addEventListener("change", sincronizar);
  form.querySelectorAll("[name=estado]").forEach(r => r.addEventListener("change", sincronizar));
  sincronizar();

  // Enter y flechas ↑/↓ pasan de campo; Enter en el último guarda.
  // ←/→ cruzan al campo vecino sólo desde el borde del texto, como una sola línea.
  // Selects y opciones conservan sus flechas; de cada grupo sólo cuenta la marcada.
  const campos = () => [...form.querySelectorAll("input:not([type=hidden]), select, textarea")].filter(c =>
    !c.disabled && c.getClientRects().length && !c.closest("[hidden]") &&
    (c.type !== "radio" || c.checked || !form.querySelector(`[name="${c.name}"]:checked`) && c === form.querySelector(`[name="${c.name}"]`)));
  const enBorde = (c, fin) => {
    const a = c.selectionStart, b = c.selectionEnd;
    if (a == null) return true;
    return fin ? a === c.value.length && b === a : b === 0;
  };
  form.addEventListener("keydown", ev => {
    const c = ev.target, texto = c.matches("input:not([type=checkbox], [type=radio])");
    const k = ev.key;
    const paso = k === "Enter" && !c.matches("textarea") ? 1
      : !texto ? 0
      : k === "ArrowDown" ? 1 : k === "ArrowUp" ? -1
      : k === "ArrowRight" && enBorde(c, true) ? 1 : k === "ArrowLeft" && enBorde(c, false) ? -1 : 0;
    if (!paso || ev.isComposing || ev.altKey || ev.ctrlKey || ev.metaKey || ev.shiftKey || !c.matches("input, select")) return;
    const lista = campos(), sig = lista[lista.indexOf(c) + paso];
    if (!sig && (paso < 0 || k !== "Enter")) return;
    ev.preventDefault();
    if (!sig) return form.requestSubmit();
    sig.focus();
    if (!sig.setSelectionRange || sig.type === "checkbox" || sig.type === "radio") return;
    try {
      if (k === "ArrowRight") sig.setSelectionRange(0, 0);
      else if (k === "ArrowLeft") sig.setSelectionRange(sig.value.length, sig.value.length);
      else sig.select();
    } catch { sig.select?.(); }
  });

  form.addEventListener("submit", () => {
    const b = form.querySelector("button[data-texto]");
    if (!b) return;
    b.disabled = true;
    b.textContent = b.dataset.texto;
  });
}
prepararFormulario(document.querySelector("form[data-guardar]"));

// ---------- MODAL ESTUDIANTE ----------
(() => {
  const dlg = document.querySelector("dialog.modal");
  if (!dlg) return;
  const cuerpo = dlg.querySelector("[data-modal-cuerpo]");
  const pedir = (url, op = {}) => fetch(url, { ...op, headers: { "X-Modal": "1" } });
  const cerrar = () => {
    dlg.classList.remove("is-visible");
    setTimeout(() => { dlg.close(); cuerpo.replaceChildren(); }, 150);
  };
  const pintar = html => {
    cuerpo.innerHTML = html;
    const form = cuerpo.querySelector("form[data-guardar]");
    prepararFormulario(form);
    form.addEventListener("submit", enviar);
    cuerpo.querySelectorAll("[data-cerrar]").forEach(b => b.addEventListener("click", ev => { ev.preventDefault(); cerrar(); }));
  };
  async function enviar(ev) {
    ev.preventDefault();
    const form = ev.currentTarget;
    try {
      const r = await pedir(form.action, { method: "POST", body: new FormData(form) });
      if (r.status === 204) return location.reload();
      pintar(await r.text());
      cuerpo.querySelector("[aria-invalid=true]")?.focus();
    } catch { form.submit(); }
  }
  document.querySelectorAll("a[data-modal]").forEach(a => a.addEventListener("click", async ev => {
    if (ev.metaKey || ev.ctrlKey || ev.shiftKey || ev.button) return;
    ev.preventDefault();
    try {
      const r = await pedir(a.href);
      if (!r.ok) throw r;
      pintar(await r.text());
    } catch { return location.assign(a.href); }
    dlg.showModal();
    dlg.scrollTop = 0;
    const o = a.getBoundingClientRect(), d = dlg.getBoundingClientRect();
    dlg.style.transformOrigin = `${o.left + o.width / 2 - d.left}px ${o.top + o.height / 2 - d.top}px`;
    cuerpo.querySelector("#nombres")?.focus();
    requestAnimationFrame(() => dlg.classList.add("is-visible"));
  }));
  dlg.addEventListener("cancel", ev => { ev.preventDefault(); cerrar(); });
  dlg.addEventListener("click", ev => { if (ev.target === dlg) cerrar(); });
})();

// ---------- IMPRIMIR ----------
document.querySelectorAll("[data-imprimir]").forEach(b => b.addEventListener("click", () => print()));

// ---------- API ----------
(() => {
  const formas = document.querySelectorAll("form[data-api]");
  if (!formas.length) return;
  const base = document.querySelector("[data-base]").textContent;
  const esc = t => t.replace(/[&<>]/g, c => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;" })[c]);
  // Colorea el JSON ya indentado: claves, textos, números y true/false/null.
  const pintarJson = t => esc(t).replace(
    /("(?:\\.|[^"\\])*")(\s*:)?|\b(true|false|null)\b|-?\d+(?:\.\d+)?(?:[eE][+-]?\d+)?/g,
    (m, cad, dos, lit) => cad ? `<span class="${dos ? "j-clave" : "j-texto"}">${cad}</span>${dos || ""}`
      : `<span class="${lit ? "j-lit" : "j-num"}">${m}</span>`);
  const copiar = async (texto, boton) => {
    try { await navigator.clipboard.writeText(texto); } catch { return; }
    const tip = boton.dataset.tip;
    if (tip) { boton.dataset.tip = "Copiado"; setTimeout(() => { boton.dataset.tip = tip; }, 1200); }
  };
  const kb = n => n < 1024 ? `${n} B` : `${(n / 1024).toFixed(1).replace(".", ",")} KB`;
  const NOMBRE = { 200: "OK", 201: "Creado", 400: "Petición incorrecta", 404: "No existe", 405: "Método no permitido",
    409: "Conflicto", 422: "Datos no válidos", 500: "Error del servidor", 503: "Sin base de datos" };
  const etiqueta = o => o.grado ? `${o.grado} · ${o.institucion} · ${o.anio_lectivo}` : o.nombre || o.descripcion;

  // Tras crear, cambiar o borrar, los desplegables de id de ese recurso se ponen al día.
  const reflejar = (recurso, metodo, o) => {
    document.querySelectorAll(`select[data-recurso="${recurso}"]`).forEach(s => {
      const op = [...s.options].find(x => x.value === String(o.id));
      if (metodo === "DELETE") op?.remove();
      else if (op) op.textContent = `${o.id} · ${etiqueta(o)}`;
      else s.insertBefore(new Option(`${o.id} · ${etiqueta(o)}`, o.id), s.lastElementChild);
    });
  };

  document.querySelectorAll("[data-copiar]").forEach(b => b.addEventListener("click", () => copiar(b.dataset.copiar, b)));

  formas.forEach(form => {
    const { api: ruta, metodo, recurso } = form.dataset;
    const urlEl = form.querySelector("[data-url]");
    const editor = form.querySelector("[data-cuerpo]");
    const salida = form.nextElementSibling;
    const json = salida.querySelector("[data-json]");
    const codigo = salida.querySelector("[data-codigo]");
    const medida = salida.querySelector("[data-medida]");
    const boton = form.querySelector("button[data-texto]");
    const texto = boton.innerHTML;
    let ultimo = "", armado = 0;

    const url = () => {
      let r = ruta;
      const q = new URLSearchParams();
      form.querySelectorAll("[data-en]").forEach(c => {
        if (c.dataset.en === "path") r = r.replace(`{${c.name}}`, encodeURIComponent(c.value));
        else if (c.value) q.set(c.name, c.value);
      });
      return r + (q.size ? `?${q}` : "");
    };
    const actualizar = () => { urlEl.textContent = metodo === "GET" ? url() : `${metodo} ${url()}`; };
    form.addEventListener("change", actualizar);
    actualizar();

    const curl = () => {
      let c = `curl -X ${metodo} "${base}${url()}"`;
      if (editor) c += ` -H "Content-Type: application/json" -d '${editor.value.replace(/\s*\n\s*/g, " ").trim()}'`;
      return c;
    };
    form.querySelector("[data-copiar-url]").addEventListener("click", ev =>
      copiar(metodo === "GET" ? base + url() : curl(), ev.currentTarget));
    salida.querySelector("[data-copiar-json]").addEventListener("click", ev => copiar(ultimo, ev.currentTarget));

    const mostrar = (estado, ok, detalle, cuerpo, pintado) => {
      codigo.textContent = estado;
      codigo.dataset.ok = ok;
      medida.textContent = detalle;
      ultimo = cuerpo;
      json.innerHTML = pintado ? pintarJson(cuerpo) : esc(cuerpo);
      salida.hidden = false;
      salida.querySelector("pre").scrollTop = 0;
    };

    // Borrar pide un segundo clic en menos de 4 s.
    const desarmar = () => { clearTimeout(armado); armado = 0; boton.innerHTML = texto; boton.dataset.armado = ""; };

    form.addEventListener("submit", async ev => {
      ev.preventDefault();
      if (metodo === "DELETE" && !armado) {
        boton.textContent = boton.dataset.armar;
        boton.dataset.armado = "si";
        armado = setTimeout(desarmar, 4000);
        return;
      }
      if (armado) { clearTimeout(armado); armado = 0; boton.dataset.armado = ""; }

      const pedido = { method: metodo, headers: { Accept: "application/json" } };
      if (editor) {
        try { JSON.parse(editor.value); } catch (e) {
          mostrar("JSON no válido", false, "Revisa el cuerpo antes de enviarlo", e.message, false);
          editor.focus();
          return;
        }
        pedido.headers["Content-Type"] = "application/json";
        pedido.body = editor.value;
      }

      boton.disabled = true;
      boton.textContent = boton.dataset.texto;
      const inicio = performance.now();
      try {
        const r = await fetch(url(), pedido);
        const crudo = await r.text();
        const ms = Math.round(performance.now() - inicio);
        let datos;
        try { datos = JSON.parse(crudo); } catch { datos = undefined; }
        const cuantos = Array.isArray(datos) ? ` · ${datos.length} ${datos.length === 1 ? "elemento" : "elementos"}` : "";
        mostrar(`${r.status} ${NOMBRE[r.status] || r.statusText}`, r.ok,
          `${ms} ms · ${kb(new Blob([crudo]).size)}${cuantos}`,
          datos === undefined ? crudo : JSON.stringify(datos, null, 2), datos !== undefined);
        if (r.ok && recurso && metodo !== "GET") reflejar(recurso, metodo, metodo === "DELETE" ? datos.eliminado : datos);
      } catch {
        mostrar("Sin respuesta", false, "No se pudo conectar con el servidor", "", false);
      }
      boton.disabled = false;
      boton.innerHTML = texto;
    });
  });

  // Abre la consulta enlazada con #id al cargar.
  const destino = location.hash && document.querySelector(`details.api${CSS.escape(location.hash)}`);
  if (destino) destino.open = true;
})();
