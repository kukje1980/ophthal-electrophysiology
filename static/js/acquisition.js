/* Shared API helpers, device status, and exam rendering (incl. cursor editing). */

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

   opts.editable  : allow cursor editing (click a marker, then click the
                    waveform to move it; edit the ms field; add / delete /
                    auto re-detect). Calls opts.onChange() after every edit.
   opts.analysis  : result of /api/exams/{id}/analysis — adds the
                    interocular comparison under each step.
   opts.markers   : list of marker names offered by the "add marker" select. */
function renderExam(exam, container, opts = {}) {
  container.innerHTML = "";
  container._states = [];
  const steps = [];
  const byStep = {};
  for (const wf of exam.waveforms) {
    if (!byStep[wf.step]) { byStep[wf.step] = []; steps.push(wf.step); }
    byStep[wf.step].push(wf);
  }
  const stepAnalysis = {};
  for (const s of ((opts.analysis && opts.analysis.steps) || [])) stepAnalysis[s.step] = s;

  for (const step of steps) {
    const wfs = byStep[step].slice().sort((a, b) => (a.eye === "OD" ? -1 : 1) - (b.eye === "OD" ? -1 : 1));
    const traces = wfs.map((wf) => ({
      label: wf.eye,
      color: wf.eye === "OD" ? "#2563eb" : "#dc2626",
      samples: wf.samples,
      duration_ms: wf.duration_ms,
      measurements: wf.measurements,
      waveform_id: wf.id,
    }));

    const block = document.createElement("section");
    block.className = "card waveform-block";
    block.innerHTML = `
      <div class="row-between">
        <h3>${step}</h3>
        <span class="legend">
          <i class="dot od"></i>OD <i class="dot os"></i>OS
          ${opts.editable ? `<span class="edit-hint muted">마커 클릭 → 파형 클릭으로 이동 · * 수동</span>` : ""}
        </span>
      </div>
      <canvas width="820" height="300" class="${opts.editable ? "editable" : ""}"></canvas>
      <p class="msg err wf-msg"></p>
      <div class="markers"></div>
      <div class="inter-wrap"></div>`;
    container.appendChild(block);

    const canvas = block.querySelector("canvas");
    const state = { armed: null };
    const redraw = () => {
      drawTraces(canvas, traces, { armed: state.armed });
      block.querySelector(".markers").innerHTML = markerTable(traces, {
        editable: opts.editable, armed: state.armed, markers: opts.markers || [],
      });
      block.querySelector(".inter-wrap").innerHTML = interocularTable(stepAnalysis[step]);
      if (opts.editable) wire();
    };

    const fail = (e) => { block.querySelector(".wf-msg").textContent = e.message; };
    const done = async () => { if (opts.onChange) await opts.onChange(); };

    function wire() {
      // click a marker name to arm it
      block.querySelectorAll(".mk.clickable").forEach((el) => {
        el.onclick = () => {
          const ti = +el.dataset.ti, marker = el.dataset.marker;
          state.armed = (state.armed && state.armed.traceIndex === ti && state.armed.marker === marker)
            ? null : { traceIndex: ti, marker };
          redraw();
        };
      });
      // edit the implicit time directly
      block.querySelectorAll(".lat-input").forEach((inp) => {
        const apply = async () => {
          const v = parseFloat(inp.value);
          if (!isFinite(v)) return;
          try { await api(`/api/measurements/${inp.dataset.mid}`, { method: "PUT", body: { latency_ms: v } }); await done(); }
          catch (e) { fail(e); }
        };
        inp.onkeydown = (ev) => { if (ev.key === "Enter") { ev.preventDefault(); apply(); } };
        inp.onchange = apply;
      });
      block.querySelectorAll("[data-del]").forEach((b) => {
        b.onclick = async () => {
          try { await api(`/api/measurements/${b.dataset.del}`, { method: "DELETE" }); await done(); }
          catch (e) { fail(e); }
        };
      });
      block.querySelectorAll("[data-add]").forEach((b) => {
        b.onclick = async () => {
          const ti = +b.dataset.add;
          const sel = block.querySelector(`.add-marker-sel[data-ti="${ti}"]`);
          const ms = parseFloat(block.querySelector(`.add-marker-ms[data-ti="${ti}"]`).value);
          if (!isFinite(ms)) return fail(new Error("잠복기(ms)를 입력하세요."));
          try {
            await api(`/api/waveforms/${traces[ti].waveform_id}/measurements`,
              { method: "POST", body: { marker: sel.value, latency_ms: ms } });
            await done();
          } catch (e) { fail(e); }
        };
      });
      block.querySelectorAll("[data-redetect]").forEach((b) => {
        b.onclick = async () => {
          const ti = +b.dataset.redetect;
          if (!confirm(`${traces[ti].label} 트레이스의 모든 커서를 지우고 자동 검출을 다시 실행할까요?`)) return;
          try { await api(`/api/waveforms/${traces[ti].waveform_id}/redetect`, { method: "POST" }); await done(); }
          catch (e) { fail(e); }
        };
      });
    }

    if (opts.editable) {
      canvas.addEventListener("click", async (ev) => {
        const p = canvasPoint(canvas, ev);
        if (state.armed) {
          // place the armed cursor at the clicked time
          const t = canvas._plot.toTime(p.x);
          const tr = traces[state.armed.traceIndex];
          const m = (tr.measurements || []).find((x) => x.marker === state.armed.marker);
          state.armed = null;
          if (!m) return redraw();
          try { await api(`/api/measurements/${m.id}`, { method: "PUT", body: { latency_ms: +t.toFixed(1) } }); await done(); }
          catch (e) { fail(e); redraw(); }
          return;
        }
        const hit = nearestMarker(canvas, traces, p.x, p.y);
        if (hit) { state.armed = { traceIndex: hit.traceIndex, marker: hit.marker }; redraw(); }
      });
      canvas.addEventListener("mousemove", (ev) => {
        const p = canvasPoint(canvas, ev);
        canvas.style.cursor = state.armed ? "crosshair"
          : (nearestMarker(canvas, traces, p.x, p.y) ? "pointer" : "default");
      });
      // one Escape handler per container (renderExam may run many times)
      (container._states = container._states || []).push({ state, redraw });
      if (!container._escBound) {
        container._escBound = true;
        document.addEventListener("keydown", (ev) => {
          if (ev.key !== "Escape") return;
          for (const b of container._states) if (b.state.armed) { b.state.armed = null; b.redraw(); }
        });
      }
    }

    redraw();
  }
}

document.addEventListener("DOMContentLoaded", loadDevicePill);
