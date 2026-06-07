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

async function loadDevicePill() {
  const pill = document.getElementById("device-pill");
  if (!pill) return;
  try {
    const info = await api("/api/devices");
    const a = info.active;
    pill.textContent = `device: ${a.name} (${a.state})`;
    pill.classList.toggle("ok", a.state === "connected");
  } catch (e) {
    pill.textContent = "device: unavailable";
  }
}

/* Group an exam's waveforms by protocol step and draw each step. */
function renderExam(exam, container) {
  container.innerHTML = "";
  const steps = [];
  const byStep = {};
  for (const wf of exam.waveforms) {
    if (!byStep[wf.step]) { byStep[wf.step] = []; steps.push(wf.step); }
    byStep[wf.step].push(wf);
  }

  for (const step of steps) {
    const traces = byStep[step].map((wf) => ({
      label: wf.eye,
      color: wf.eye === "OD" ? "#2563eb" : "#dc2626",
      samples: wf.samples,
      duration_ms: wf.duration_ms,
      measurements: wf.measurements,
    }));

    const block = document.createElement("section");
    block.className = "card waveform-block";
    block.innerHTML = `
      <div class="row-between">
        <h3>${step}</h3>
        <span class="legend">
          <i class="dot od"></i>OD <i class="dot os"></i>OS
        </span>
      </div>
      <canvas width="820" height="300"></canvas>
      <div class="markers"></div>`;
    container.appendChild(block);

    drawTraces(block.querySelector("canvas"), traces);
    block.querySelector(".markers").innerHTML = markerTable(traces);
  }
}

document.addEventListener("DOMContentLoaded", loadDevicePill);
