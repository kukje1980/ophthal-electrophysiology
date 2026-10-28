/* Live-stream helpers for the Live page: trigger-locked multi-channel
   averaging with artifact rejection, and the bench checks used to commission
   a real amplifier + DAQ (noise / mains hum, trigger timing, CAL-pulse gain).
   Pure functions, so they also load under node for testing. */
(function (root) {
  "use strict";

  const mean = (a) => a.reduce((p, q) => p + q, 0) / a.length;

  function median(a) {
    if (!a.length) return NaN;
    const s = Array.from(a).sort((x, y) => x - y), m = s.length >> 1;
    return s.length % 2 ? s[m] : (s[m - 1] + s[m]) / 2;
  }

  /* Trigger-locked averager for `nch` channels. An epoch starts only on a
     trigger (so untriggered data is never averaged) and is accepted when the
     peak-to-peak of every channel stays within `rejectUv` (0 = off), so
     blinks and movement are dropped instead of smearing the average. */
  class EpochAverager {
    constructor(nch, len, rejectUv = 0) {
      this.nch = Math.max(1, nch); this.len = Math.max(2, len);
      this.rejectUv = rejectUv || 0;
      this.reset();
    }
    reset() {
      const mk = () => Array.from({ length: this.nch }, () => new Float64Array(this.len));
      this.sum = mk(); this.cur = mk();
      this.fill = 0; this.capturing = false; this.count = 0; this.rejected = 0;
    }
    /* rows: one sample array per channel; triggers: sample indices in rows. */
    feed(rows, triggers) {
      const trig = new Set(triggers || []);
      const n = rows.length ? rows[0].length : 0;
      for (let i = 0; i < n; i++) {
        if (trig.has(i)) { this.capturing = true; this.fill = 0; }  // phase-lock
        if (!this.capturing) continue;
        for (let c = 0; c < this.nch; c++) this.cur[c][this.fill] = rows[c] ? rows[c][i] : 0;
        if (++this.fill === this.len) this._close();
      }
    }
    _close() {
      this.capturing = false; this.fill = 0;
      if (this.rejectUv > 0) {
        for (const row of this.cur) {
          let lo = Infinity, hi = -Infinity;
          for (const v of row) { if (v < lo) lo = v; if (v > hi) hi = v; }
          if (hi - lo > this.rejectUv) { this.rejected++; return; }
        }
      }
      for (let c = 0; c < this.nch; c++)
        for (let j = 0; j < this.len; j++) this.sum[c][j] += this.cur[c][j];
      this.count++;
    }
    mean(c) { const k = this.count || 1; return Array.from(this.sum[c], v => v / k); }
  }

  /* RMS and peak-to-peak (µV, mean removed) of a segment, plus the peak
     amplitude of its mains component (single-bin DFT over whole cycles). */
  function noiseStats(x, fs, mains = 60) {
    const n = x.length;
    if (n < 8) return null;
    let mean = 0; for (const v of x) mean += v; mean /= n;
    let ss = 0, lo = Infinity, hi = -Infinity;
    for (const v of x) { ss += (v - mean) ** 2; if (v < lo) lo = v; if (v > hi) hi = v; }
    const m = Math.round(Math.floor(n * mains / fs) * fs / mains) || n;
    let re = 0, im = 0;
    for (let i = n - m; i < n; i++) {
      const w = 2 * Math.PI * mains * i / fs, v = x[i] - mean;
      re += v * Math.cos(w); im -= v * Math.sin(w);
    }
    return { rms: Math.sqrt(ss / n), p2p: hi - lo, hum: 2 * Math.hypot(re, im) / m };
  }

  /* Timing of recent triggers given their absolute sample indices. */
  function triggerStats(idx, fs, nowIdx) {
    if (!idx.length) return { count: 0, rate: null, meanMs: null, sdMs: null, sinceMs: null };
    const iv = [];
    for (let i = 1; i < idx.length; i++) iv.push((idx[i] - idx[i - 1]) / fs * 1000);
    const sinceMs = (nowIdx - idx[idx.length - 1]) / fs * 1000;
    if (!iv.length) return { count: idx.length, rate: null, meanMs: null, sdMs: null, sinceMs };
    const meanMs = iv.reduce((a, b) => a + b, 0) / iv.length;
    const sdMs = Math.sqrt(iv.reduce((a, b) => a + (b - meanMs) ** 2, 0) / iv.length);
    return { count: idx.length, rate: 1000 / meanMs, meanMs, sdMs, sinceMs };
  }

  /* Amplitude (µV) of a square calibration pulse — the median jump (mean
     level after − mean level before) across its edges, using only edges with
     flat levels on both sides (so ERG slopes or noise are not mistaken for a
     pulse). With the amplifier's CAL voltage
     known this checks the gain conversion: true gain = gain × measured /
     expected. Returns null when fewer than two clean edges are found. */
  function calStep(x, fs) {
    const n = x.length;
    const w = Math.max(2, Math.round(0.005 * fs));      // edge detector half-width
    const guard = Math.max(1, Math.round(0.003 * fs));  // skip the rise time
    const win = Math.max(3, Math.round(0.010 * fs));    // level windows
    if (n < 2 * (guard + win) + 2 * w) return null;
    const P = new Float64Array(n + 1);
    for (let i = 0; i < n; i++) P[i + 1] = P[i] + x[i];
    const d = new Float64Array(n);
    let dmax = 0;
    for (let i = w; i <= n - w; i++) {
      d[i] = (P[i + w] - P[i]) / w - (P[i] - P[i - w]) / w;
      dmax = Math.max(dmax, Math.abs(d[i]));
    }
    // a pulse edge must stand far above the detector's noise floor
    const noise = median(Array.from(d.subarray(w, n - w + 1), Math.abs)) / 0.6745;
    if (!(dmax > 8 * noise)) return null;
    const thr = 0.5 * dmax, minGap = Math.round(0.05 * fs), edges = [];
    for (let i = w; i <= n - w; i++) {
      const a = Math.abs(d[i]);
      if (a < thr) continue;
      const last = edges.length - 1;
      if (last >= 0 && i - edges[last] < minGap) {
        if (a > Math.abs(d[edges[last]])) edges[last] = i;
      } else edges.push(i);
    }
    const spread = (seg) => {
      const s = Array.from(seg).sort((p, q) => p - q);
      return s[Math.floor(s.length * 0.9)] - s[Math.floor(s.length * 0.1)];
    };
    const jumps = [];
    for (const e of edges) {
      if (e - guard - win < 0 || e + guard + win > n) continue;
      const before = x.slice(e - guard - win, e - guard), after = x.slice(e + guard, e + guard + win);
      const jump = Math.abs(mean(after) - mean(before));
      if (spread(before) < 0.3 * jump && spread(after) < 0.3 * jump) jumps.push(jump);
    }
    if (jumps.length < 2) return null;
    return { uv: median(jumps), edges: jumps.length };
  }

  /* NI-DAQ connection string from the builder fields (full physical channel
     names, e.g. "Dev1/ai0"). */
  function buildDaqConnection(o) {
    const sig = [o.od, o.os].filter(Boolean);
    let s = `${sig.join(",")}@${o.rate || 2000}`;
    if (o.gain) s += `;gain=${o.gain}`;
    if (!o.od && o.os) s += ";eyes=OS";
    if (o.trig) s += `;trig=${o.trig};thr=${o.thr || 1}` + (o.edge === "fall" ? ";edge=fall" : "");
    if (o.range) s += `;range=${o.range}`;
    if (o.diff) s += ";diff=1";
    if (o.notch) s += `;notch=${o.notch}`;
    if (o.hp) s += `;hp=${o.hp}`;
    return s;
  }

  /* Per-channel gains currently in a connection string (default 1). */
  function getGains(conn, nch) {
    const m = /(?:^|;)\s*gain=([^;]*)/.exec(conn || "");
    const g = m ? m[1].split(",").map(Number).filter(v => v > 0) : [];
    return Array.from({ length: nch }, (_, i) => g.length === 1 ? g[0] : (g[i] || 1));
  }

  /* Connection string with its gain option replaced by `gains`. */
  function withGain(conn, gains) {
    const parts = (conn || "").split(";").filter(p => !/^\s*gain=/.test(p));
    const same = gains.every(g => g === gains[0]);
    parts.splice(1, 0, "gain=" + (same ? [gains[0]] : gains).join(","));
    return parts.join(";");
  }

  const api = { median, EpochAverager, noiseStats, triggerStats, calStep,
                buildDaqConnection, getGains, withGain };
  if (typeof module !== "undefined" && module.exports) module.exports = api;
  else root.LiveTools = api;
})(this);
