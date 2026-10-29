/* Shared API helpers, device status, clock, theme toggle and exam rendering. */

async function api(path, opts = {}) {
  const init = { method: opts.method || "GET", headers: {} };
  if (opts.body !== undefined) {
    init.headers["Content-Type"] = "application/json";
    init.body = JSON.stringify(opts.body);
  }
  const res = await fetch(path, init);
  if (res.status === 204) return null;
  const text = await res.text();
  const data = text ? JSON.parse(text) : null;
  if (!res.ok) {
    const detail = data && data.detail ? data.detail : res.statusText;
    throw new Error(typeof detail === "string" ? detail : JSON.stringify(detail));
  }
  return data;
}

function setMsg(id, text, cls) {
  const el = document.getElementById(id);
  if (!el) return;
  el.textContent = text;
  el.className = "msg " + (cls || "");
}

function _esc(s) {
  return String(s == null ? "" : s).replace(/&/g, "&amp;").replace(/</g, "&lt;")
    .replace(/>/g, "&gt;").replace(/"/g, "&quot;");
}

/* Compact local date-time, e.g. 2026-10-29 15:05 (optionally with seconds). */
function fmtDT(d, seconds) {
  d = d instanceof Date ? d : new Date(d);
  if (isNaN(d)) return "-";
  const p = (n) => String(n).padStart(2, "0");
  return `${d.getFullYear()}-${p(d.getMonth() + 1)}-${p(d.getDate())} ${p(d.getHours())}:${p(d.getMinutes())}` +
    (seconds ? `:${p(d.getSeconds())}` : "");
}

/* Device status → topbar pill + status bar. */
async function loadDevicePill() {
  const pill = document.getElementById("device-pill");
  const txt = document.getElementById("device-text");
  const sbLed = document.getElementById("sb-led");
  const sbDev = document.getElementById("sb-device");
  const sbAmp = document.getElementById("sb-amp");
  const sbImp = document.getElementById("sb-imp");
  if (!pill && !sbDev) return;
  try {
    const info = await api("/api/devices");
    const a = info.active;
    const ok = a.state === "connected";
    if (txt) txt.textContent = `${a.name} · ${a.state}`;
    if (pill) pill.classList.toggle("ok", ok);
    if (sbLed) sbLed.className = "led " + (ok ? "on" : "off");
    if (sbDev) sbDev.innerHTML = `<b>${_esc(a.name)}</b> ${_esc(a.connection || "")} · ${_esc(a.state)}`;
    if (sbAmp && a.amplifier) sbAmp.textContent = `AMP ${a.amplifier.name} · ${a.amplifier.state}` +
      (a.stimulator ? ` · STIM ${a.stimulator.name} · ${a.stimulator.state}` : "");
    if (sbImp && a.impedance) {
      const z = a.impedance;
      sbImp.innerHTML = `Z <b>${z.max_kohm != null ? z.max_kohm.toFixed(1) : "–"} kΩ</b> ` +
        (z.ok ? `<i class="led on"></i>` : `<i class="led warn"></i>`);
    }
  } catch (e) {
    if (txt) txt.textContent = "device unavailable";
    if (sbLed) sbLed.className = "led off";
    if (sbDev) sbDev.textContent = "device unavailable";
  }
}

/* Topbar clock. */
function _tickClock() {
  const el = document.getElementById("clock");
  if (!el) return;
  const d = new Date();
  const p = (n) => String(n).padStart(2, "0");
  el.textContent = `${d.getFullYear()}-${p(d.getMonth() + 1)}-${p(d.getDate())}  ${p(d.getHours())}:${p(d.getMinutes())}:${p(d.getSeconds())}`;
}

/* Theme toggle (dark instrument theme ⇄ light). */
function _initTheme() {
  const btn = document.getElementById("theme-btn");
  if (!btn) return;
  const apply = () => {
    const light = document.documentElement.dataset.theme === "light";
    btn.innerHTML = `<svg><use href="#${light ? "i-moon" : "i-sun"}"/></svg>`;
  };
  apply();
  btn.addEventListener("click", () => {
    const light = document.documentElement.dataset.theme === "light";
    if (light) delete document.documentElement.dataset.theme;
    else document.documentElement.dataset.theme = "light";
    try { localStorage.setItem("erg-theme", light ? "dark" : "light"); } catch (e) {}
    apply();
    window.dispatchEvent(new Event("erg-theme"));
  });
}

/* Group an exam's waveforms by protocol step and draw each step as a panel.
   `proto` (optional) is the /api/protocols/{key} object, used for step labels;
   it is fetched when not supplied. */
async function renderExam(exam, container, proto) {
  container.innerHTML = "";
  if (!proto) {
    try { proto = await api(`/api/protocols/${encodeURIComponent(exam.protocol)}`); }
    catch (e) { proto = null; }
  }
  const stepInfo = {};
  for (const s of (proto && proto.steps) || []) stepInfo[s.key] = s;

  const steps = [];
  const byStep = {};
  for (const wf of exam.waveforms) {
    if (!byStep[wf.step]) { byStep[wf.step] = []; steps.push(wf.step); }
    byStep[wf.step].push(wf);
  }
  if (!steps.length) {
    container.innerHTML = `<p class="empty">No waveforms stored for this exam.</p>`;
    return;
  }

  const pal = plotPalette();
  for (const step of steps) {
    const wfs = byStep[step];
    const traces = wfs.map((wf) => ({
      label: wf.eye,
      color: wf.eye === "OD" ? pal.od : pal.os,
      samples: wf.samples,
      duration_ms: wf.duration_ms,
      measurements: wf.measurements,
    }));
    const info = stepInfo[step] || {};
    const fs = wfs[0].sampling_rate, dur = wfs[0].duration_ms;
    const stim = info.stimulus || {};
    const stimBits = [];
    if (stim.cd_s_m2 != null) stimBits.push(`${stim.cd_s_m2} cd·s·m⁻²`);
    if (stim.check_deg != null) stimBits.push(`${stim.check_deg}° checks`);
    if (stim.contrast != null) stimBits.push(`${Math.round(stim.contrast * 100)}%`);
    if (stim.rate_hz != null) stimBits.push(`${stim.rate_hz} Hz`);
    if (stim.reversal_hz != null) stimBits.push(`${stim.reversal_hz} rev/s`);
    if (stim.hexagons != null) stimBits.push(`${stim.hexagons} hex`);
    if (stim.filter) stimBits.push(stim.filter);

    const block = document.createElement("section");
    block.className = "panel wf waveform-block";
    block.innerHTML = `
      <div class="panel-h">
        <span class="step">${_esc(step)}</span>
        <span class="sub">${_esc(info.label || "")}</span>
        <span class="grow"></span>
        <span class="meta">${stimBits.map(_esc).join(" · ")}${stimBits.length ? " · " : ""}${fs} Hz · ${dur} ms</span>
        <span class="legend"><i class="dot od"></i>OD <i class="dot os"></i>OS</span>
      </div>
      <div class="wf-plot"><canvas data-h="300"></canvas></div>
      <div class="markers"></div>`;
    container.appendChild(block);

    drawTraces(block.querySelector("canvas"), traces);
    block.querySelector(".markers").innerHTML = markerTable(traces);
  }
}

document.addEventListener("DOMContentLoaded", () => {
  loadDevicePill();
  _tickClock(); setInterval(_tickClock, 1000);
  _initTheme();
});
