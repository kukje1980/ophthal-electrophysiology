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

/* Group an exam's waveforms by protocol step and draw each step.

   opts.editable turns on manual marker review: pick "eye · marker", click the
   waveform to place it (optionally snapped to the nearest peak/trough), remove
   a marker with ×, or re-run automatic detection. opts.stepMarkers maps a
   step key to its marker names; opts.onMessage(text, cls) reports results. */
function renderExam(exam, container, opts = {}) {
  container.innerHTML = "";
  const steps = [];
  const byStep = {};
  for (const wf of exam.waveforms) {
    if (!byStep[wf.step]) { byStep[wf.step] = []; steps.push(wf.step); }
    byStep[wf.step].push(wf);
  }
  const say = opts.onMessage || (() => {});

  for (const step of steps) {
    const block = document.createElement("section");
    block.className = "card waveform-block";
    container.appendChild(block);

    const draw = (selected) => {
      const traces = byStep[step].map((wf) => ({
        id: wf.id,
        label: wf.eye,
        color: wf.eye === "OD" ? "#2563eb" : "#dc2626",
        samples: wf.samples,
        duration_ms: wf.duration_ms,
        measurements: wf.measurements,
      }));
      const markers = (opts.stepMarkers || {})[step] || [];
      const choices = opts.editable ? byStep[step].flatMap((wf) =>
        markers.map((m) => `<option value="${wf.id}|${m}">${wf.eye} · ${m}</option>`)) : [];
      block.innerHTML = `
        <div class="row-between">
          <h3>${step}</h3>
          <span class="legend">
            <i class="dot od"></i>OD <i class="dot os"></i>OS
          </span>
        </div>
        ${choices.length ? `<div class="edit-bar no-print">
          <label>Marker <select class="edit-target">${choices.join("")}</select></label>
          <label class="inline"><input type="checkbox" class="edit-snap" checked> snap to peak</label>
          <button class="btn small edit-reset" type="button">Re-detect (auto)</button>
          <span class="muted">Click the waveform to place the selected marker.</span>
        </div>` : ""}
        <canvas width="820" height="300"${choices.length ? ' class="editable"' : ""}></canvas>
        <div class="markers"></div>`;

      const canvas = block.querySelector("canvas");
      const geo = drawTraces(canvas, traces);
      block.querySelector(".markers").innerHTML = markerTable(traces, opts);
      if (!choices.length) return;

      const target = block.querySelector(".edit-target");
      if (selected) target.value = selected;

      const update = async (wfId, path, init, done) => {
        try {
          const wf = await api(`/api/exams/${exam.id}/waveforms/${wfId}/markers${path}`, init);
          byStep[step] = byStep[step].map((w) => (w.id === wf.id ? wf : w));
          exam.waveforms = exam.waveforms.map((w) => (w.id === wf.id ? wf : w));
          draw(target.value);
          say(done, "ok");
        } catch (e) {
          say(e.message, "err");
        }
      };

      canvas.addEventListener("click", (ev) => {
        const r = canvas.getBoundingClientRect();
        const x = (ev.clientX - r.left) * (canvas.width / r.width);
        const t = (x - geo.padL) / geo.plotW * geo.maxT;
        if (t < 0 || t > geo.maxT) return;
        const [wfId, marker] = target.value.split("|");
        update(wfId, `/${encodeURIComponent(marker)}`, { method: "PUT", body: {
          latency_ms: Math.round(t * 100) / 100,
          snap: block.querySelector(".edit-snap").checked,
        }}, `${step} ${marker} updated.`);
      });
      block.querySelector(".edit-reset").addEventListener("click", () => {
        const [wfId] = target.value.split("|");
        update(wfId, "/reset", { method: "POST" }, `${step}: automatic markers restored.`);
      });
      block.querySelectorAll(".btn-x").forEach((b) => b.addEventListener("click", () =>
        update(b.dataset.wf, `/${encodeURIComponent(b.dataset.marker)}`,
               { method: "DELETE" }, `${step} ${b.dataset.marker} removed.`)));
    };
    draw();
  }
}

document.addEventListener("DOMContentLoaded", loadDevicePill);
