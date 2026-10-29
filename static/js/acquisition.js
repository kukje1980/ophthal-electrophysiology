/* Shared API helpers, device status, and exam rendering (incl. cursor editing). */

/* ---- Network-resilient API client --------------------------------------
   * every request has a timeout, so a dead network never hangs the page;
   * GETs are retried with backoff on network errors and 502/503/504;
   * writes carry an Idempotency-Key and are retried with the SAME key, so a
     save whose response was lost is never stored twice;
   * a 401 (session expired) sends the user to the login page;
   * a banner shows when the server is unreachable.                        */

const API_TIMEOUT_MS = 30000;

function newIdempotencyKey() {
  if (window.crypto && crypto.randomUUID) return crypto.randomUUID();
  return Date.now().toString(36) + "-" + Math.random().toString(36).slice(2) +
         Math.random().toString(36).slice(2);
}

const _sleep = (ms) => new Promise((r) => setTimeout(r, ms));
const _backoff = (attempt) =>
  Math.min(8000, 500 * 2 ** attempt) * (0.75 + Math.random() * 0.5);

function _errorText(data, res) {
  const d = data && data.detail;
  if (!d) return res.statusText || `HTTP ${res.status}`;
  if (typeof d === "string") return d;
  if (Array.isArray(d))  // FastAPI validation errors
    return d.map((e) => `${(e.loc || []).slice(1).join(".") || "입력"}: ${e.msg}`).join("; ");
  return JSON.stringify(d);
}

/* opts: method, body, timeout (ms), retries, idempotencyKey,
         withMeta (resolve {data, total} using X-Total-Count) */
async function api(path, opts = {}) {
  const method = (opts.method || "GET").toUpperCase();
  const isWrite = method !== "GET" && method !== "HEAD";
  const headers = {};
  if (opts.body !== undefined) headers["Content-Type"] = "application/json";
  if (isWrite) headers["Idempotency-Key"] = opts.idempotencyKey || newIdempotencyKey();
  const body = opts.body !== undefined ? JSON.stringify(opts.body) : undefined;
  const retries = opts.retries != null ? opts.retries : 4;
  const timeout = opts.timeout || API_TIMEOUT_MS;

  for (let attempt = 0; ; attempt++) {
    const ctrl = new AbortController();
    const timer = setTimeout(() => ctrl.abort(), timeout);
    let res;
    try {
      res = await fetch(path, { method, headers, body, signal: ctrl.signal,
                                credentials: "same-origin" });
    } catch (e) {
      clearTimeout(timer);
      netStatus(false);
      // Writes are safe to resend: the Idempotency-Key makes the server
      // return the first attempt's result instead of saving twice.
      if (attempt < retries) { await _sleep(_backoff(attempt)); continue; }
      throw new Error(e.name === "AbortError"
        ? "서버 응답 시간 초과 — 네트워크 상태를 확인하세요."
        : "서버에 연결할 수 없습니다 — 네트워크 상태를 확인하세요.");
    }
    clearTimeout(timer);
    netStatus(true);

    if (res.status === 401 && !opts.noAuthRedirect) {
      location.href = "/login?next=" + encodeURIComponent(location.pathname + location.search);
      throw new Error("로그인이 만료되었습니다.");
    }
    // Retry when the server says so (Retry-After: busy device / database),
    // or on gateway errors that mean the request may never have arrived.
    const retryAfter = res.headers.get("Retry-After");
    const gateway = res.status === 502 || res.status === 504 ||
                    (res.status === 503 && !isWrite);
    if (attempt < retries && (retryAfter || gateway) && res.status >= 409) {
      await _sleep(retryAfter ? Math.min(30, +retryAfter || 1) * 1000 : _backoff(attempt));
      continue;
    }

    if (res.status === 204) return opts.withMeta ? { data: null, total: 0 } : null;
    const text = await res.text();
    let data = null;
    try { data = text ? JSON.parse(text) : null; }
    catch (e) { data = { detail: text.slice(0, 200) }; }  // e.g. a proxy's HTML error page
    if (!res.ok) throw new Error(_errorText(data, res));
    if (opts.withMeta) {
      const total = parseInt(res.headers.get("X-Total-Count"), 10);
      return { data, total: Number.isNaN(total) ? (data ? data.length : 0) : total };
    }
    return data;
  }
}

/* Escape text for innerHTML templates (names, notes, … are user input). */
function esc(v) {
  return String(v == null ? "" : v).replace(/&/g, "&amp;").replace(/</g, "&lt;")
    .replace(/>/g, "&gt;").replace(/"/g, "&quot;").replace(/'/g, "&#39;");
}

/* Run fn only after the input has been quiet for `ms` (search boxes). */
function debounce(fn, ms = 250) {
  let t = null;
  return (...args) => { clearTimeout(t); t = setTimeout(() => fn(...args), ms); };
}

/* ---- Connection indicator ------------------------------------------- */
let _netOk = true;
function netStatus(ok) {
  if (ok === _netOk) return;
  _netOk = ok;
  let bar = document.getElementById("net-banner");
  if (!bar) {
    bar = document.createElement("div");
    bar.id = "net-banner";
    bar.className = "net-banner hidden";
    document.body.prepend(bar);
  }
  bar.textContent = ok ? "" : "⚠ 서버와의 연결이 끊겼습니다 — 자동으로 다시 연결하는 중입니다. " +
                              "입력한 내용은 그대로 유지됩니다.";
  bar.classList.toggle("hidden", ok);
}

async function _heartbeat() {
  if (document.hidden) return;
  const ctrl = new AbortController();
  const timer = setTimeout(() => ctrl.abort(), 5000);
  try {
    const r = await fetch("/health", { signal: ctrl.signal, cache: "no-store" });
    netStatus(r.ok);
  } catch (e) { netStatus(false); }
  finally { clearTimeout(timer); }
}
setInterval(_heartbeat, 15000);
window.addEventListener("online", _heartbeat);
window.addEventListener("offline", () => netStatus(false));

/* Server timestamps are naive UTC ("2026-10-28T05:59:35"); show them in the
   PC's local time (a bare ISO string would otherwise be read as local). */
function fmtDateTime(iso, opts) {
  if (!iso) return "-";
  const s = /[zZ]|[+-]\d\d:?\d\d$/.test(iso) ? iso : iso + "Z";
  const d = new Date(s);
  return isNaN(d) ? iso : d.toLocaleString("ko-KR", opts || {
    year: "numeric", month: "2-digit", day: "2-digit", hour: "2-digit", minute: "2-digit" });
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
          ${opts.editable ? `<span class="edit-hint muted">마커 클릭 → 파형 클릭으로 이동 · * 수동</span>
            <label class="inline edit-snap-label" title="클릭한 곳 ±4 ms 안의 가장 가까운 정점/골로 커서를 옮깁니다">
              <input type="checkbox" class="edit-snap" checked> 피크에 맞춤</label>` : ""}
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
          const snap = block.querySelector(".edit-snap").checked;
          try { await api(`/api/measurements/${m.id}`, { method: "PUT", body: { latency_ms: +t.toFixed(1), snap } }); await done(); }
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
