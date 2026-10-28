/* Canvas waveform plotting for ERG/VEP traces. */

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

/* Plot colours come from the stylesheet (--plot-* tokens). */
function _plotPalette() {
  const cs = getComputedStyle(document.documentElement);
  const v = (k, d) => cs.getPropertyValue(k).trim() || d;
  return {
    bg: v("--plot-bg", "#ffffff"), minor: v("--plot-minor", "#f2f5f8"),
    major: v("--plot-major", "#e2e7ed"), zero: v("--plot-zero", "#a9b4c2"),
    axis: v("--plot-axis", "#6b7789"), ink: v("--plot-ink", "#1b2533"),
    stim: v("--plot-stim", "#12b4d8"), mono: v("--mono", "ui-monospace, monospace"),
  };
}

/* Scale the backing store for crisp lines on HiDPI screens and print; drawing
   then uses the canvas' original (attribute) size as logical coordinates. */
function hidpiCanvas(canvas) {
  if (!canvas.dataset.w) { canvas.dataset.w = canvas.width; canvas.dataset.h = canvas.height; }
  const W = +canvas.dataset.w, H = +canvas.dataset.h;
  const dpr = Math.max(2, Math.ceil(window.devicePixelRatio || 1));
  if (canvas.width !== W * dpr) { canvas.width = W * dpr; canvas.height = H * dpr; }
  const ctx = canvas.getContext("2d");
  ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
  return { ctx, W, H };
}

/* ISCEV negative components (a-wave, N35, N75, N95, N1, …) are labelled
   below the trace, positive ones (b-wave, OPs, P50, P100, …) above it. */
const _isNegative = (marker) => /^(a|N)/.test(marker);

function drawTraces(canvas, traces) {
  const { ctx, W, H } = hidpiCanvas(canvas);
  const C = _plotPalette();
  const padL = 50, padR = 14, padT = 20, padB = 34;
  const plotW = W - padL - padR, plotH = H - padT - padB;

  ctx.clearRect(0, 0, W, H);
  ctx.fillStyle = C.bg;
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
  if (!maxT) maxT = 1;
  ymin = Math.min(ymin, 0); ymax = Math.max(ymax, 0);
  const pad = (ymax - ymin) * 0.2 || 1;  // headroom for marker labels
  ymin -= pad; ymax += pad;

  const X = (t) => padL + (t / maxT) * plotW;
  const Y = (v) => padT + (ymax - v) / (ymax - ymin) * plotH;
  const crisp = (p) => Math.round(p) + 0.5;

  const tStep = _niceStep(maxT, 8);
  const vStep = _niceStep(ymax - ymin, 6);
  const vDec = Math.max(0, -Math.floor(Math.log10(vStep)));

  // Grid: minor (fifths) then major lines, like calibrated chart paper ------
  ctx.lineWidth = 1;
  ctx.strokeStyle = C.minor;
  ctx.beginPath();
  for (let i = 0; i * tStep / 5 <= maxT + 1e-9; i++) {
    const x = crisp(X(i * tStep / 5));
    ctx.moveTo(x, padT); ctx.lineTo(x, padT + plotH);
  }
  for (let i = Math.ceil(ymin / (vStep / 5)); i * vStep / 5 <= ymax + 1e-9; i++) {
    const y = crisp(Y(i * vStep / 5));
    ctx.moveTo(padL, y); ctx.lineTo(padL + plotW, y);
  }
  ctx.stroke();

  ctx.font = `500 10.5px ${C.mono}`;
  ctx.strokeStyle = C.major;
  ctx.fillStyle = C.axis;
  ctx.beginPath();
  ctx.textAlign = "center";
  for (let i = 0; i * tStep <= maxT + 1e-9; i++) {
    const t = i * tStep, x = crisp(X(t));
    ctx.moveTo(x, padT); ctx.lineTo(x, padT + plotH);
    ctx.fillText(String(Math.round(t)), x, padT + plotH + 15);
  }
  ctx.textAlign = "right";
  for (let i = Math.ceil(ymin / vStep); i * vStep <= ymax + 1e-9; i++) {
    const v = i * vStep, y = crisp(Y(v));
    ctx.moveTo(padL, y); ctx.lineTo(padL + plotW, y);
    ctx.fillText((Math.abs(v) < 1e-9 ? 0 : v).toFixed(vDec), padL - 8, y + 3.5);
  }
  ctx.stroke();

  // Zero line + frame ------------------------------------------------------
  ctx.strokeStyle = C.zero;
  ctx.beginPath();
  ctx.moveTo(padL, crisp(Y(0))); ctx.lineTo(padL + plotW, crisp(Y(0)));
  ctx.stroke();
  ctx.strokeStyle = C.major;
  ctx.strokeRect(crisp(padL), crisp(padT), Math.round(plotW) - 1, Math.round(plotH) - 1);

  // Stimulus onset (t = 0) -------------------------------------------------
  ctx.fillStyle = C.stim;
  ctx.beginPath();
  ctx.moveTo(padL - 5, padT - 9); ctx.lineTo(padL + 5, padT - 9); ctx.lineTo(padL, padT - 2);
  ctx.closePath(); ctx.fill();
  ctx.font = `700 9.5px ${C.mono}`;
  ctx.textAlign = "left";
  ctx.fillText("STIM", padL + 9, padT - 3);

  // Axis titles --------------------------------------------------------------
  ctx.fillStyle = C.axis;
  ctx.font = `500 10.5px ${C.mono}`;
  ctx.textAlign = "right";
  ctx.fillText("ms", padL + plotW, H - 4);
  ctx.textAlign = "left";
  ctx.fillText("µV", 6, padT - 3);

  // Traces -----------------------------------------------------------------
  ctx.save();
  ctx.beginPath();
  ctx.rect(padL, padT, plotW, plotH);
  ctx.clip();
  for (const tr of traces) {
    const n = tr.samples.length;
    const dt = tr.duration_ms / n;
    ctx.strokeStyle = tr.color;
    ctx.lineWidth = 1.7;
    ctx.lineJoin = "round";
    ctx.lineCap = "round";
    ctx.beginPath();
    for (let i = 0; i < n; i++) {
      const x = X(i * dt), y = Y(tr.samples[i]);
      i === 0 ? ctx.moveTo(x, y) : ctx.lineTo(x, y);
    }
    ctx.stroke();
  }
  ctx.restore();

  // Markers: dot on each trace, then one label per eye stacked away from the
  // waveform so OD/OS labels for the same component never collide. ---------
  const groups = {};
  traces.forEach((tr, ti) => {
    const n = tr.samples.length;
    const dt = tr.duration_ms / n;
    for (const m of tr.measurements || []) {
      const idx = Math.min(n - 1, Math.max(0, Math.round(m.latency_ms / dt)));
      const pt = { x: X(m.latency_ms), y: Y(tr.samples[idx]), color: tr.color, ti };
      ctx.fillStyle = tr.color;
      ctx.strokeStyle = C.bg;
      ctx.lineWidth = 2;
      ctx.beginPath(); ctx.arc(pt.x, pt.y, 3.6, 0, 2 * Math.PI); ctx.fill(); ctx.stroke();
      (groups[m.marker] = groups[m.marker] || []).push(pt);
    }
  });
  ctx.font = `700 11px ${C.mono}`;
  ctx.textAlign = "center";
  ctx.lineJoin = "round";
  for (const [marker, pts] of Object.entries(groups)) {
    const below = _isNegative(marker);
    pts.sort((p, q) => p.ti - q.ti);
    // Anchor on the outermost point of the group (lowest trough / highest peak).
    const edge = below ? Math.max(...pts.map((p) => p.y)) : Math.min(...pts.map((p) => p.y));
    pts.forEach((pt, k) => {
      let ly = below ? edge + 17 + k * 13 : edge - 9 - k * 13;
      ly = Math.min(padT + plotH - 4, Math.max(padT + 11, ly));
      ctx.lineWidth = 3.5;
      ctx.strokeStyle = C.bg;
      ctx.strokeText(marker, pt.x, ly);
      ctx.fillStyle = pt.color;
      ctx.fillText(marker, pt.x, ly);
    });
  }
}
