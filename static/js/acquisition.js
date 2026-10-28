/* Shared API helpers, device status, and exam rendering. */

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

const escHtml = (s) => String(s == null ? "" : s).replace(/&/g, "&amp;")
  .replace(/</g, "&lt;").replace(/>/g, "&gt;").replace(/"/g, "&quot;");

/* Uniform clinical timestamp: YYYY-MM-DD HH:MM (local time). */
function fmtDateTime(value) {
  if (!value) return "—";
  const d = new Date(value);
  if (isNaN(d)) return String(value);
  const pad = (n) => String(n).padStart(2, "0");
  return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())} ` +
    `${pad(d.getHours())}:${pad(d.getMinutes())}`;
}

/* Fill every [data-dev=…] slot (rail module, dashboard console) from the
   active device status; .device / [data-dev-led] get ok / err state. */
async function loadDevicePill() {
  const slots = (k) => document.querySelectorAll(`[data-dev="${k}"]`);
  const put = (k, v) => slots(k).forEach((el) => { el.textContent = v; });
  const leds = document.querySelectorAll("#device-pill, [data-dev-led]");
  try {
    const info = await api("/api/devices");
    const a = info.active || {};
    const ok = a.state === "connected";
    put("name", a.name || "—");
    put("state", a.state || "—");
    put("amp", (a.amplifier && a.amplifier.state) || "—");
    put("stim", (a.stimulator && a.stimulator.state) || "—");
    const z = a.impedance && a.impedance.max_kohm;
    put("imp", z != null ? `${Number(z).toFixed(1)} kΩ` : "—");
    put("conn", a.connection || "—");
    leds.forEach((el) => { el.classList.toggle("ok", ok); el.classList.toggle("err", !ok); });
  } catch (e) {
    put("name", "unavailable");
    put("state", "offline");
    leds.forEach((el) => { el.classList.remove("ok"); el.classList.add("err"); });
  }
}

function startClock() {
  const el = document.getElementById("clock");
  if (!el) return;
  const tick = () => { el.textContent = fmtDateTime(new Date()); };
  tick();
  setInterval(tick, 15000);
}

const EYE_COLOR = () => {
  const cs = getComputedStyle(document.documentElement);
  return { OD: cs.getPropertyValue("--od").trim() || "#1f6fe0",
           OS: cs.getPropertyValue("--os").trim() || "#e0473c" };
};

/* Group an exam's waveforms by protocol step and draw each step.
   `stepLabels` (optional) maps step key → human label for the card header. */
function renderExam(exam, container, stepLabels) {
  container.innerHTML = "";
  const steps = [];
  const byStep = {};
  for (const wf of exam.waveforms) {
    if (!byStep[wf.step]) { byStep[wf.step] = []; steps.push(wf.step); }
    byStep[wf.step].push(wf);
  }
  const colors = EYE_COLOR();

  for (const step of steps) {
    const wfs = byStep[step];
    const traces = wfs.map((wf) => ({
      label: wf.eye,
      color: colors[wf.eye] || colors.OD,
      samples: wf.samples,
      duration_ms: wf.duration_ms,
      measurements: wf.measurements,
    }));
    const eyes = wfs.map((wf) => wf.eye);
    const first = wfs[0] || {};
    const meta = [
      first.duration_ms ? `${first.duration_ms} ms` : null,
      first.sampling_rate ? `${first.sampling_rate} Hz` : null,
    ].filter(Boolean).join(" · ");
    const label = stepLabels && stepLabels[step];

    const block = document.createElement("section");
    block.className = "card waveform-block";
    block.innerHTML = `
      <div class="wf-head">
        <span class="wf-key">${escHtml(step)}</span>
        ${label ? `<span class="wf-title">${escHtml(label)}</span>` : ""}
        ${meta ? `<span class="wf-meta">${meta}</span>` : ""}
        <span class="legend">
          ${eyes.includes("OD") ? '<span><i class="sw od"></i>OD</span>' : ""}
          ${eyes.includes("OS") ? '<span><i class="sw os"></i>OS</span>' : ""}
        </span>
      </div>
      <div class="wf-body">
        <div class="wf-plot"><canvas width="820" height="300"></canvas></div>
        <div class="wf-markers"></div>
      </div>`;
    container.appendChild(block);

    // Match the canvas' logical width to its box (within limits) so axis and
    // marker text stays legible on narrow screens.
    const canvas = block.querySelector("canvas");
    const boxW = canvas.parentElement.clientWidth - 28;
    if (boxW > 0 && boxW < 820) {
      canvas.width = Math.max(420, Math.round(boxW));
      canvas.height = canvas.width < 600 ? 280 : 300;
    }
    drawTraces(canvas, traces);
    block.querySelector(".wf-markers").innerHTML = markerTable(traces);
  }
}

document.addEventListener("DOMContentLoaded", () => { loadDevicePill(); startClock(); });
