/* GuOnco Registry frontend. Vanilla JS, no build step.
   All labels/options come from /api — nothing clinical is hard-coded here. */

const $ = (sel) => document.querySelector(sel);

const state = {
  pathologies: [],
  active: null,        // pathology spec {key, fields:[...], ...}
  mediaRecorder: null,
  audioCtx: null,
  analyser: null,
  rafId: null,
};

const SECTION_TITLES = {
  paciente: ["Paciente", "Patient"],
  diagnostico: ["Diagnóstico y extensión", "Diagnosis & staging"],
  tratamiento: ["Tratamiento", "Treatment"],
  seguimiento: ["Seguimiento y estado", "Follow-up & status"],
};

async function api(path, opts) {
  const res = await fetch(path, {
    headers: opts?.body instanceof FormData ? {} : { "Content-Type": "application/json" },
    ...opts,
  });
  const data = await res.json().catch(() => ({}));
  if (!res.ok) {
    const detail = data.detail;
    const msg =
      data.error ||
      (typeof detail === "string" ? detail : null) ||
      (detail?.errors ? `invalid: ${Object.keys(detail.errors).join(", ")}` : null) ||
      `${res.status} ${res.statusText}`;
    throw Object.assign(new Error(msg), { detail });
  }
  return data;
}

function toast(msg, isError = false) {
  const el = $("#toast");
  el.textContent = msg;
  el.classList.toggle("error", isError);
  el.classList.add("show");
  clearTimeout(el._t);
  el._t = setTimeout(() => el.classList.remove("show"), 3200);
}

/* ------------------------------------------------------------ pathologies */
async function loadPathologies() {
  state.pathologies = (await api("/api/pathologies")).pathologies;
  renderChips();
}

function renderChips() {
  const nav = $("#chips");
  nav.innerHTML = "";
  for (const p of state.pathologies) {
    const btn = document.createElement("button");
    btn.type = "button";
    btn.className = "chip";
    btn.dataset.key = p.key;
    btn.style.setProperty("--chip-color", p.color);
    btn.innerHTML = `<span class="swatch"></span>${p.nombre_es} · ${p.nombre_en} <span class="cie">${p.cie10}</span>`;
    btn.addEventListener("click", () => selectPathology(p.key));
    nav.appendChild(btn);
  }
}

async function selectPathology(key) {
  const spec = await api(`/api/pathologies/${key}/fields`);
  state.active = { ...spec, key };
  document.documentElement.style.setProperty("--accent", state.active.color);
  for (const chip of $("#chips").children) {
    chip.classList.toggle("active", chip.dataset.key === key);
  }
  $("#empty-state").hidden = true;
  $("#dictation").hidden = false;
  $("#record-form").hidden = false;
  $("#actionbar").hidden = false;
  $("#cie-tag").textContent = `${state.active.cie10} · ${state.active.nombre_en}`;
  renderForm();
  resetTranscript();
  refreshPending();
}

/* ------------------------------------------------------------------- form */
function renderForm() {
  const form = $("#record-form");
  form.innerHTML = "";
  const groups = new Map();
  for (const f of state.active.fields) {
    if (!groups.has(f.group)) groups.set(f.group, []);
    groups.get(f.group).push(f);
  }

  for (const [group, fields] of groups) {
    const [es, en] = SECTION_TITLES[group] || [group, ""];
    const section = document.createElement("div");
    section.className = "section";
    section.innerHTML = `
      <h3 class="section-title"><span class="es">${es}</span><span class="en">${en}</span></h3>
      <div class="field-grid"></div>`;
    const grid = section.querySelector(".field-grid");
    for (const f of fields) grid.appendChild(renderField(f));
    form.appendChild(section);
  }
}

const WIDE = new Set(["textarea"]);

function renderField(field) {
  const node = $("#tpl-field").content.cloneNode(true);
  const wrap = node.querySelector(".field");
  if (WIDE.has(field.type)) wrap.classList.add("wide");

  const lblEs = node.querySelector(".lbl-es");
  const lblEn = node.querySelector(".lbl-en");
  lblEs.textContent = field.label_es;
  const unit = field.unit && !field.label_en.includes(field.unit) ? ` (${field.unit})` : "";
  lblEn.textContent = field.label_en + unit;

  const control = node.querySelector(".control");
  const id = `f-${field.id}`;

  switch (field.type) {
    case "select": {
      const sel = document.createElement("select");
      sel.id = id;
      sel.dataset.fieldId = field.id;
      sel.append(Object.assign(document.createElement("option"), { value: "", text: "—" }));
      for (const o of field.options || []) {
        const opt = document.createElement("option");
        opt.value = o.code;
        opt.textContent = o.es === o.en ? o.es : `${o.es} · ${o.en}`;
        sel.appendChild(opt);
      }
      control.appendChild(sel);
      break;
    }
    case "boolean": {
      const seg = document.createElement("div");
      seg.className = "boolean-seg";
      seg.dataset.fieldId = field.id;
      for (const [val, label] of [[0, "No"], [1, "Sí"]]) {
        const b = document.createElement("button");
        b.type = "button";
        b.textContent = label;
        b.dataset.val = val;
        b.addEventListener("click", () => {
          for (const x of seg.children) x.classList.remove("on");
          b.classList.add("on");
          seg.dataset.value = val;
        });
        seg.appendChild(b);
      }
      control.appendChild(seg);
      break;
    }
    case "number": {
      control.appendChild(mkInput(field, "number", "step=any"));
      break;
    }
    case "date":
      control.appendChild(mkInput(field, "date"));
      break;
    case "textarea": {
      const ta = document.createElement("textarea");
      ta.id = id;
      ta.rows = 2;
      ta.dataset.fieldId = field.id;
      control.appendChild(ta);
      break;
    }
    default:
      control.appendChild(mkInput(field, "text"));
  }
  return node;
}

function mkInput(field, type) {
  const input = document.createElement("input");
  input.type = type;
  input.id = `f-${field.id}`;
  input.dataset.fieldId = field.id;
  if (field.default) input.value = field.default;
  else if (field.auto === "today") input.value = new Date().toISOString().slice(0, 10);
  return input;
}

function collectFields() {
  const out = {};
  for (const el of $("#record-form").querySelectorAll("[data-field-id]")) {
    let value;
    if (el.classList.contains("boolean-seg")) {
      if (el.dataset.value === undefined) continue;
      value = Number(el.dataset.value);
    } else {
      value = el.value.trim();
      if (value === "") continue;
      if (el.type === "number") value = Number(value);
    }
    out[el.dataset.fieldId] = value;
  }
  return out;
}

function applyExtraction(fields) {
  const filled = [];
  for (const [fid, value] of Object.entries(fields || {})) {
    if (value === null || value === undefined) continue;
    const el = $(`#record-form [data-field-id="${CSS.escape(fid)}"]`);
    if (!el) continue;
    if (el.classList.contains("boolean-seg")) {
      el.dataset.value = value ? "1" : "0";
      for (const x of el.children) {
        x.classList.toggle("on", Number(x.dataset.val) === Number(value));
      }
    } else if (el.tagName === "SELECT") {
      el.value = String(value);
    } else {
      el.value = value;
    }
    const field = el.closest(".field");
    if (field && !WIDE.has(state.active.fields.find((f) => f.id === fid)?.type)) {
      field.style.animationDelay = `${Math.min(filled.length * 60, 900)}ms`;
      field.classList.add("filled");
      filled.push(field);
    }
  }
}

/* --------------------------------------------------------------- dictation */
function resetTranscript() {
  $("#transcript-wrap").hidden = true;
  $("#transcript").value = "";
  setRecording(false);
}

async function toggleMic() {
  if (state.mediaRecorder?.state === "recording") {
    state.mediaRecorder.stop();
    return;
  }
  try {
    const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
    startLevelMeter(stream);
    const rec = new MediaRecorder(stream);
    const chunks = [];
    rec.ondataavailable = (e) => chunks.push(e.data);
    rec.onstop = () => {
      stopLevelMeter();
      stream.getTracks().forEach((t) => t.stop());
      setRecording(false);
      sendAudio(new Blob(chunks));
    };
    rec.start();
    state.mediaRecorder = rec;
    setRecording(true);
  } catch {
    toast("No hay acceso al micrófono / No microphone access", true);
  }
}

function setRecording(on) {
  $("#mic").classList.toggle("recording", on);
  $("#mic-hint").innerHTML = on
    ? "Escuchando…<br /><span class='en'>Listening…</span>"
    : "Toca y dicta<br /><span class='en'>Tap and dictate</span>";
}

async function sendAudio(blob) {
  toast("Transcribiendo… / Transcribing…");
  const fd = new FormData();
  fd.append("file", blob, "dictation.webm");
  try {
    const { transcript } = await api("/api/transcribe", { method: "POST", body: fd });
    $("#transcript-wrap").hidden = false;
    $("#transcript").value = transcript;
    $("#extract-btn").disabled = !transcript;
    if (!transcript) toast("No se escuchó nada / Nothing was heard", true);
  } catch (e) {
    toast(`Error: ${e.message}`, true);
  }
}

function startLevelMeter(stream) {
  const mic = $("#mic");
  state.audioCtx = new (window.AudioContext || window.webkitAudioContext)();
  const src = state.audioCtx.createMediaStreamSource(stream);
  state.analyser = state.audioCtx.createAnalyser();
  state.analyser.fftSize = 512;
  src.connect(state.analyser);
  const buf = new Uint8Array(state.analyser.frequencyBinCount);
  const tick = () => {
    state.analyser.getByteTimeDomainData(buf);
    let peak = 0;
    for (let i = 0; i < buf.length; i++) peak = Math.max(peak, Math.abs(buf[i] - 128));
    mic.style.setProperty("--level", (peak / 128).toFixed(2));
    state.rafId = requestAnimationFrame(tick);
  };
  tick();
}

function stopLevelMeter() {
  cancelAnimationFrame(state.rafId);
  state.audioCtx?.close();
  state.audioCtx = state.analyser = null;
  $("#mic").style.removeProperty("--level");
}

async function extractVariables() {
  const transcript = $("#transcript").value.trim();
  if (!transcript || !state.active) return;
  $("#extract-btn").disabled = true;
  $("#extract-btn").textContent = "Extrayendo… / Extracting…";
  try {
    const { fields, unmapped_notes } = await api("/api/extract", {
      method: "POST",
      body: JSON.stringify({ pathology: state.active.key, transcript }),
    });
    applyExtraction(fields);
    const n = Object.values(fields || {}).filter((v) => v != null).length;
    toast(
      n > 0
        ? `${n} variables extraídas — revisa antes de guardar / extracted — review before saving`
        : "Sin variables reconocidas / no variables recognized",
      n === 0,
    );
    if (unmapped_notes?.length && window.console) console.info(unmapped_notes.join("\n"));
  } catch (e) {
    toast(`Error: ${e.message}`, true);
  } finally {
    $("#extract-btn").disabled = false;
    $("#extract-btn").innerHTML =
      'Extraer variables <span class="en">Extract variables</span>';
  }
}

/* ------------------------------------------------------------ save / sync */
async function saveRecord() {
  if (!state.active) return;
  const fields = collectFields();
  if (!fields.historia_clinica) {
    toast(
      "Falta el ID / historia clínica / missing medical record ID",
      true,
    );
    return;
  }
  try {
    await api("/api/records", {
      method: "POST",
      body: JSON.stringify({ pathology: state.active.key, fields }),
    });
    toast("Paciente guardado ✓ / Patient saved ✓");
    resetTranscript();
    renderForm();
    refreshPending();
  } catch (e) {
    const errors = e.detail?.errors;
    toast(errors ? `Revisa: ${Object.keys(errors).join(", ")}` : e.message, true);
  }
}

async function syncNow() {
  try {
    const out = await api("/api/sync", { method: "POST" });
    toast(out.synced ? `Sincronizados ${out.synced} registros ✓` : out.message || "Nada pendiente / nothing pending");
    refreshPending();
  } catch (e) {
    toast(e.message, true);
  }
}

async function refreshPending() {
  try {
    const st = await api("/api/sync/status");
    const dot = $("#sync-dot");
    dot.className = "sync-dot " + (st.pending > 0 ? "pending" : st.synced > 0 ? "ok" : "");
    dot.title = `Pendientes ${st.pending} · Sincronizados ${st.synced}`;
    $("#pending-note").textContent =
      st.pending > 0 ? `${st.pending} pendiente(s)` : "";
  } catch {
    /* status endpoint failing should not block UI */
  }
}

/* ------------------------------------------------------------------ boot */
$("#mic").addEventListener("click", toggleMic);
$("#extract-btn").addEventListener("click", extractVariables);
$("#save-btn").addEventListener("click", saveRecord);
$("#sync-btn").addEventListener("click", syncNow);

loadPathologies()
  .then(() => {
    const p = new URLSearchParams(location.search).get("p");
    if (p && state.pathologies.some((x) => x.key === p)) return selectPathology(p);
  })
  .catch(() => toast("Backend no disponible — ¿está corriendo el servidor? / backend unavailable, is the server running?", true));
refreshPending();
