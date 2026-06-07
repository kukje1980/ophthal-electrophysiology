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

function drawTraces(canvas, traces) {
  const ctx = canvas.getContext("2d");
  const W = canvas.width, H = canvas.height;
  const padL = 52, padR = 16, padT = 16, padB = 30;
  const plotW = W - padL - padR, plotH = H - padT - padB;

  ctx.clearRect(0, 0, W, H);

  let maxT = 0, ymin = Infinity, ymax = -Infinity;
  for (const tr of traces) {
    maxT = Math.max(maxT, tr.duration_ms);
    for (const v of tr.samples) {
      if (v < ymin) ymin = v;
      if (v > ymax) ymax = v;
    }
  }
  if (!isFinite(ymin)) { ymin = -1; ymax = 1; }
  ymin = Math.min(ymin, 0); ymax = Math.max(ymax, 0);
  const pad = (ymax - ymin) * 0.12 || 1;
  ymin -= pad; ymax += pad;

  const X = (t) => padL + (t / maxT) * plotW;
  const Y = (v) => padT + (ymax - v) / (ymax - ymin) * plotH;

  // Grid -----------------------------------------------------------------
  ctx.font = "11px system-ui, sans-serif";
  ctx.lineWidth = 1;

  const tStep = _niceStep(maxT, 8);
  ctx.strokeStyle = "#eef1f6";
  ctx.fillStyle = "#94a3b8";
  ctx.textAlign = "center";
  for (let t = 0; t <= maxT + 1e-6; t += tStep) {
    const x = X(t);
    ctx.beginPath(); ctx.moveTo(x, padT); ctx.lineTo(x, padT + plotH); ctx.stroke();
    ctx.fillText(Math.round(t), x, H - 10);
  }

  const vStep = _niceStep(ymax - ymin, 6);
  ctx.textAlign = "right";
  for (let v = Math.ceil(ymin / vStep) * vStep; v <= ymax; v += vStep) {
    const y = Y(v);
    ctx.strokeStyle = Math.abs(v) < 1e-9 ? "#cbd5e1" : "#eef1f6";
    ctx.beginPath(); ctx.moveTo(padL, y); ctx.lineTo(padL + plotW, y); ctx.stroke();
    ctx.fillStyle = "#94a3b8";
    ctx.fillText(v.toFixed(vStep < 1 ? 1 : 0), padL - 6, y + 3);
  }

  // Axis labels ----------------------------------------------------------
  ctx.fillStyle = "#64748b";
  ctx.textAlign = "center";
  ctx.fillText("time (ms)", padL + plotW / 2, H - 0);
  ctx.save();
  ctx.translate(12, padT + plotH / 2);
  ctx.rotate(-Math.PI / 2);
  ctx.fillText("amplitude (µV)", 0, 0);
  ctx.restore();

  // Traces + markers -----------------------------------------------------
  for (const tr of traces) {
    const n = tr.samples.length;
    const dt = tr.duration_ms / n;
    ctx.strokeStyle = tr.color;
    ctx.lineWidth = 1.6;
    ctx.beginPath();
    for (let i = 0; i < n; i++) {
      const x = X(i * dt), y = Y(tr.samples[i]);
      i === 0 ? ctx.moveTo(x, y) : ctx.lineTo(x, y);
    }
    ctx.stroke();

    for (const m of tr.measurements || []) {
      const idx = Math.min(n - 1, Math.round(m.latency_ms / dt));
      const x = X(m.latency_ms), y = Y(tr.samples[idx]);
      ctx.fillStyle = tr.color;
      ctx.beginPath(); ctx.arc(x, y, 3.2, 0, 2 * Math.PI); ctx.fill();
      ctx.fillStyle = "#334155";
      ctx.textAlign = "center";
      ctx.fillText(m.marker, x, y - 7);
    }
  }
}
