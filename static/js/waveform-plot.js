/* Canvas waveform plotting for ERG/VEP traces — oscilloscope-style, theme
   aware (colours come from the CSS custom properties on <html>) and HiDPI
   crisp. Every drawn canvas remembers its traces so it can be redrawn on
   resize, theme change and before printing. */

function _niceStep(range, target) {
  const raw = range / target;
  const mag = Math.pow(10, Math.floor(Math.log10(raw)));
  const norm = raw / mag;
  let step;
  if (norm < 1.5) step = 1;
  else if (norm < 3) step = 2;
  else if (norm < 7) step = 5;
  else step = 10;
  return step * mag;
}

/* Theme palette read from CSS variables (falls back to the dark theme). */
function plotPalette() {
  const cs = getComputedStyle(document.documentElement);
  const v = (name, fb) => (cs.getPropertyValue(name) || "").trim() || fb;
  return {
    bg: v("--plot-bg", "#070b11"),
    grid: v("--grid", "#141d29"),
    grid2: v("--grid-2", "#1d2a39"),
    zero: v("--zero", "#3b4d63"),
    axis: v("--axis", "#71859d"),
    ink: v("--marker-ink", "#e3eaf3"),
    od: v("--od", "#3fb6ff"),
    os: v("--os", "#ff6b6b"),
    accent: v("--accent", "#22d3ee"),
    mono: v("--mono", "ui-monospace, Menlo, Consolas, monospace"),
  };
}

const _plotted = new Set();

function drawTraces(canvas, traces) {
  canvas._traces = traces;
  _plotted.add(canvas);

  const pal = plotPalette();
  const dpr = window.devicePixelRatio || 1;
  // Size to the CSS box (falls back to the width/height attributes when the
  // canvas is not laid out yet, e.g. in a hidden container).
  const cssW = canvas.clientWidth || canvas.width || 820;
  const cssH = parseInt(canvas.dataset.h || "", 10) || canvas.clientHeight || canvas.height || 300;
  canvas.width = Math.round(cssW * dpr);
  canvas.height = Math.round(cssH * dpr);
  canvas.style.height = cssH + "px";

  const ctx = canvas.getContext("2d");
  ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
  const W = cssW, H = cssH;
  const padL = 54, padR = 36, padT = 14, padB = 30;
  const plotW = W - padL - padR, plotH = H - padT - padB;

  ctx.fillStyle = pal.bg;
  ctx.fillRect(0, 0, W, H);

  let maxT = 0, ymin = Infinity, ymax = -Infinity;
  for (const tr of traces) {
    maxT = Math.max(maxT, tr.duration_ms);
    for (const v of tr.samples) {
      if (v < ymin) ymin = v;
      if (v > ymax) ymax = v;
    }
  }
  if (!isFinite(ymin)) { ymin = -1; ymax = 1; }
  if (!(maxT > 0)) maxT = 1;
  ymin = Math.min(ymin, 0); ymax = Math.max(ymax, 0);
  const pad = (ymax - ymin) * 0.2 || 1;
  ymin -= pad; ymax += pad;

  const X = (t) => padL + (t / maxT) * plotW;
  const Y = (v) => padT + (ymax - v) / (ymax - ymin) * plotH;

  // Grid -----------------------------------------------------------------
  ctx.font = `10.5px ${pal.mono}`;
  ctx.lineWidth = 1;
  const tStep = _niceStep(maxT, 8);
  const vStep = _niceStep(ymax - ymin, 6);

  // minor grid (dotted)
  ctx.save();
  ctx.setLineDash([1, 3]);
  ctx.strokeStyle = pal.grid;
  for (let t = tStep / 2; t <= maxT + 1e-6; t += tStep) {
    const x = Math.round(X(t)) + .5;
    ctx.beginPath(); ctx.moveTo(x, padT); ctx.lineTo(x, padT + plotH); ctx.stroke();
  }
  for (let v = Math.ceil(ymin / vStep) * vStep - vStep / 2; v <= ymax; v += vStep) {
    const y = Math.round(Y(v)) + .5;
    ctx.beginPath(); ctx.moveTo(padL, y); ctx.lineTo(padL + plotW, y); ctx.stroke();
  }
  ctx.restore();

  // major grid + tick labels
  ctx.strokeStyle = pal.grid2;
  ctx.fillStyle = pal.axis;
  ctx.textAlign = "center";
  for (let t = 0; t <= maxT + 1e-6; t += tStep) {
    const x = Math.round(X(t)) + .5;
    ctx.beginPath(); ctx.moveTo(x, padT); ctx.lineTo(x, padT + plotH); ctx.stroke();
    ctx.fillText(Math.round(t), x, H - 9);
  }
  ctx.textAlign = "right";
  for (let v = Math.ceil(ymin / vStep) * vStep; v <= ymax; v += vStep) {
    const y = Math.round(Y(v)) + .5;
    const isZero = Math.abs(v) < 1e-9;
    ctx.strokeStyle = isZero ? pal.zero : pal.grid2;
    ctx.lineWidth = isZero ? 1.2 : 1;
    ctx.beginPath(); ctx.moveTo(padL, y); ctx.lineTo(padL + plotW, y); ctx.stroke();
    ctx.fillStyle = pal.axis;
    ctx.fillText(v.toFixed(vStep < 1 ? 1 : 0), padL - 7, y + 3.5);
  }
  ctx.lineWidth = 1;

  // plot frame
  ctx.strokeStyle = pal.grid2;
  ctx.strokeRect(padL + .5, padT + .5, plotW - 1, plotH - 1);

  // Axis labels ----------------------------------------------------------
  ctx.fillStyle = pal.axis;
  ctx.textAlign = "right";
  ctx.fillText("ms", W - 3, H - 9);
  ctx.save();
  ctx.translate(11, padT + plotH / 2);
  ctx.rotate(-Math.PI / 2);
  ctx.textAlign = "center";
  ctx.fillText("µV", 0, 0);
  ctx.restore();

  // Traces ---------------------------------------------------------------
  ctx.save();
  ctx.beginPath(); ctx.rect(padL, padT, plotW, plotH); ctx.clip();
  for (const tr of traces) {
    const n = tr.samples.length;
    const dt = tr.duration_ms / n;
    const color = tr.color || (tr.label === "OS" ? pal.os : pal.od);
    tr._color = color;
    ctx.lineJoin = "round";
    // soft glow pass
    ctx.strokeStyle = color; ctx.globalAlpha = 0.22; ctx.lineWidth = 5;
    ctx.beginPath();
    for (let i = 0; i < n; i++) {
      const x = X(i * dt), y = Y(tr.samples[i]);
      i === 0 ? ctx.moveTo(x, y) : ctx.lineTo(x, y);
    }
    ctx.stroke();
    // crisp pass
    ctx.globalAlpha = 1; ctx.lineWidth = 1.6;
    ctx.stroke();
  }
  ctx.restore();

  // Markers --------------------------------------------------------------
  ctx.font = `bold 10.5px ${pal.mono}`;
  const placed = [];  // label boxes already drawn, for collision avoidance
  const collides = (a) => placed.some((b) => a.x < b.x + b.w && a.x + a.w > b.x && a.y < b.y + b.h && a.y + a.h > b.y);
  for (let ti = 0; ti < traces.length; ti++) {
    const tr = traces[ti];
    const n = tr.samples.length;
    const dt = tr.duration_ms / n;
    const color = tr._color;
    for (const m of tr.measurements || []) {
      const idx = Math.max(0, Math.min(n - 1, Math.round(m.latency_ms / dt)));
      const x = X(m.latency_ms), y = Y(tr.samples[idx]);
      // vertical tick to the time axis
      ctx.save();
      ctx.setLineDash([2, 3]); ctx.strokeStyle = color; ctx.globalAlpha = .45;
      ctx.beginPath(); ctx.moveTo(x, y); ctx.lineTo(x, padT + plotH); ctx.stroke();
      ctx.restore();
      // dot
      ctx.fillStyle = pal.bg;
      ctx.beginPath(); ctx.arc(x, y, 4.5, 0, 2 * Math.PI); ctx.fill();
      ctx.fillStyle = color;
      ctx.beginPath(); ctx.arc(x, y, 3, 0, 2 * Math.PI); ctx.fill();
      // label chip (above positive peaks, below negative troughs)
      const above = tr.samples[idx] >= 0;
      const label = m.marker;
      const tw = ctx.measureText(label).width + 8;
      const lx = Math.min(Math.max(x - tw / 2, padL + 2), padL + plotW - tw - 2);
      // stack labels that would overprint one another (coincident OD/OS peaks)
      let ly = above ? y - 20 : y + 9;
      for (let k = 0; k < 6 && collides({ x: lx, y: ly, w: tw, h: 13 }); k++) ly += above ? -14 : 14;
      ly = Math.min(Math.max(ly, padT + 1), padT + plotH - 14);
      placed.push({ x: lx, y: ly, w: tw, h: 13 });
      ctx.fillStyle = pal.bg; ctx.globalAlpha = .85;
      ctx.fillRect(lx, ly, tw, 13);
      ctx.globalAlpha = 1;
      ctx.strokeStyle = color; ctx.lineWidth = 1;
      ctx.strokeRect(lx + .5, ly + .5, tw - 1, 12);
      ctx.fillStyle = color; ctx.textAlign = "center";
      ctx.fillText(label, lx + tw / 2, ly + 10);
    }
  }
}

/* Redraw every plotted canvas that is still in the document. */
function redrawAllTraces() {
  for (const c of Array.from(_plotted)) {
    if (!c.isConnected) { _plotted.delete(c); continue; }
    if (c._traces) drawTraces(c, c._traces);
  }
}

let _rsz = null;
window.addEventListener("resize", () => {
  clearTimeout(_rsz); _rsz = setTimeout(redrawAllTraces, 120);
});
window.addEventListener("erg-theme", redrawAllTraces);
/* Print with the light palette regardless of the on-screen theme. */
window.addEventListener("beforeprint", () => {
  document.documentElement.dataset.printTheme = document.documentElement.dataset.theme || "";
  document.documentElement.dataset.theme = "light";
  redrawAllTraces();
});
window.addEventListener("afterprint", () => {
  const prev = document.documentElement.dataset.printTheme;
  if (prev) document.documentElement.dataset.theme = prev;
  else delete document.documentElement.dataset.theme;
  delete document.documentElement.dataset.printTheme;
  redrawAllTraces();
});
