/* Shared API helpers, device status, and exam rendering. */

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
