/* Multi-photo viewer for clinical images (fundus, OCT, ...).

   Shows the selected photos side by side and lets each viewport be examined
   and edited non-destructively: zoom / pan / magnifier lens, 90° rotation and
   flips, brightness / contrast / gamma / saturation / sharpen, red-free and
   other single-channel views, invert, length measurement, and a WebGL 3-D
   surface (image intensity as height). Zoom and pan can be synchronised
   across viewports for side-by-side comparison (OD vs OS, follow-ups).

   Framework-free and server-agnostic: the page passes photo descriptors
   ({id, src, thumb, title, label, short, info, contentType, downloadUrl}),
   optionally an onSaveEdited(photo, blob, meta) callback that stores an
   edited copy and returns its descriptor, and download: false to hide the
   download button where the host blocks downloads.
   Used by /photos/viewer and by the standalone preview. */
(function (global) {
  "use strict";

  const DEFAULT_ADJ = Object.freeze({
    brightness: 0, contrast: 0, gamma: 1, saturation: 0, sharpen: 0,
    channel: "rgb", invert: false, lo: 0, hi: 255,  // lo/hi: input levels
  });
  const CHANNELS = [["rgb", "컬러"], ["green", "Red-free"], ["red", "R"],
                    ["blue", "B"], ["gray", "흑백"]];
  // Layout key -> label (rows × columns); GRID gives [columns, rows].
  const LAYOUTS = [["auto", "자동"], ["1", "1"], ["2", "1×2"], ["4", "2×2"],
                   ["6", "2×3"], ["9", "3×3"]];
  const GRID = { 1: [1, 1], 2: [2, 1], 4: [2, 2], 6: [3, 2], 9: [3, 3] };
  const ZOOM_MAX = 32;     // original pixels magnified up to 3200 %
  const LENS_R = 90;       // magnifier radius, CSS px
  const TEX_MAX = 2048;    // 3-D texture size cap
  const PROXY_PIXELS = 1.5e6;  // live-adjustment proxy for large images

  const clamp = (v, lo, hi) => Math.min(hi, Math.max(lo, v));
  const isIdentity = (a) => Object.keys(DEFAULT_ADJ).every((k) => a[k] === DEFAULT_ADJ[k]);
  const esc = (s) => String(s == null ? "" : s).replace(/[&<>"']/g, (c) => (
    { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
  const signed = (v) => (v > 0 ? "+" : "") + v;

  // Rotate (x, y) by k quarter turns clockwise (screen coordinates, y down).
  function rot90(x, y, k) {
    switch (k) {
      case 1: return [-y, x];
      case 2: return [-x, -y];
      case 3: return [y, -x];
      default: return [x, y];
    }
  }

  function makeCanvas(w, h) {
    const c = document.createElement("canvas");
    c.width = w; c.height = h;
    return c;
  }

  /* ---------------------------------------------------------------------
     Pixel processing (pure functions on RGBA byte arrays)
     ------------------------------------------------------------------- */

  function buildLut(adj) {
    const lut = new Uint8ClampedArray(256);
    const k = Math.tan((clamp(adj.contrast, -99, 99) / 100 + 1) * Math.PI / 4);
    const b = adj.brightness / 200;
    const g = 1 / adj.gamma;
    const span = Math.max(1, adj.hi - adj.lo);
    for (let i = 0; i < 256; i++) {
      const x = (Math.pow(clamp((i - adj.lo) / span, 0, 1), g) - 0.5) * k + 0.5 + b;
      lut[i] = Math.round(clamp(x, 0, 1) * 255);
    }
    return lut;
  }

  // Laplacian sharpen, in place, keeping only two rows of extra memory.
  // Fixed-point (amount × 256) and unrolled over R, G, B; alpha untouched.
  function sharpenInPlace(d, w, h, amount) {
    const stride = w * 4, a = Math.round(amount * 256);
    let prev = d.slice(0, stride);
    let cur = new Uint8ClampedArray(stride);
    for (let y = 1; y < h - 1; y++) {
      const row = y * stride, next = row + stride;
      cur.set(d.subarray(row, next));
      for (let x = 4; x < stride - 4; x += 4) {
        const i = row + x, j = next + x;
        let c = cur[x];
        d[i] = c + ((a * (4 * c - prev[x] - d[j] - cur[x - 4] - cur[x + 4])) >> 8);
        c = cur[x + 1];
        d[i + 1] = c + ((a * (4 * c - prev[x + 1] - d[j + 1] - cur[x - 3] - cur[x + 5])) >> 8);
        c = cur[x + 2];
        d[i + 2] = c + ((a * (4 * c - prev[x + 2] - d[j + 2] - cur[x - 2] - cur[x + 6])) >> 8);
      }
      const t = prev; prev = cur; cur = t;
    }
  }

  function processPixels(src, dst, w, h, adj) {
    const lut = buildLut(adj);
    const n = w * h * 4;
    const inv = adj.invert;
    if (adj.channel === "rgb") {
      const sat = 1 + adj.saturation / 100;
      for (let i = 0; i < n; i += 4) {
        let r = lut[src[i]], g = lut[src[i + 1]], b = lut[src[i + 2]];
        if (sat !== 1) {
          const y = 0.299 * r + 0.587 * g + 0.114 * b;
          r = y + (r - y) * sat; g = y + (g - y) * sat; b = y + (b - y) * sat;
        }
        if (inv) { r = 255 - r; g = 255 - g; b = 255 - b; }
        dst[i] = r; dst[i + 1] = g; dst[i + 2] = b; dst[i + 3] = src[i + 3];
      }
    } else {
      // Single channel shown as grey: red-free = green channel.
      const off = { red: 0, green: 1, blue: 2 }[adj.channel];
      for (let i = 0; i < n; i += 4) {
        let v = lut[off === undefined
          ? (src[i] * 77 + src[i + 1] * 150 + src[i + 2] * 29) >> 8
          : src[i + off]];
        if (inv) v = 255 - v;
        dst[i] = dst[i + 1] = dst[i + 2] = v; dst[i + 3] = src[i + 3];
      }
    }
    if (adj.sharpen > 0) sharpenInPlace(dst, w, h, adj.sharpen / 100 * 1.5);
  }

  // Input levels that stretch the 0.5–99.5th percentile of the channel shown,
  // ignoring the black surround of fundus images when it dominates.
  function autoLevels(data, channel) {
    const off = { red: 0, green: 1, blue: 2 }[channel];
    const hist = new Uint32Array(256);
    const step = 4 * Math.max(1, Math.floor(data.length / 4 / 400000));
    for (let i = 0; i < data.length; i += step) {
      hist[off === undefined ? (data[i] * 77 + data[i + 1] * 150 + data[i + 2] * 29) >> 8 : data[i + off]]++;
    }
    let total = 0, dark = 0;
    for (let v = 0; v < 256; v++) { total += hist[v]; if (v < 12) dark += hist[v]; }
    const from = total - dark > total * 0.05 ? 12 : 0;
    const n = total - (from ? dark : 0);
    let lo = from, hi = 255, acc = 0;
    for (let v = from; v < 256; v++) { acc += hist[v]; if (acc >= n * 0.005) { lo = v; break; } }
    acc = 0;
    for (let v = 255; v >= from; v--) { acc += hist[v]; if (acc >= n * 0.005) { hi = v; break; } }
    return hi - lo < 8 ? [0, 255] : [lo, hi];
  }

  function histogram(data) {
    const hist = new Uint32Array(256);
    const step = 4 * Math.max(1, Math.floor(data.length / 4 / 250000));
    for (let i = 0; i < data.length; i += step) {
      hist[(data[i] * 77 + data[i + 1] * 150 + data[i + 2] * 29) >> 8]++;
    }
    return hist;
  }

  /* ---------------------------------------------------------------------
     WebGL 3-D surface: the (processed, oriented) image as a height map
     ------------------------------------------------------------------- */

  const VS = `
    attribute vec3 aPos; attribute vec3 aNrm; attribute vec2 aUV; attribute float aH;
    uniform mat4 uMVP;
    varying vec3 vN; varying vec2 vUV; varying float vH;
    void main() { vN = aNrm; vUV = aUV; vH = aH; gl_Position = uMVP * vec4(aPos, 1.0); }`;
  const FS = `
    #ifdef GL_FRAGMENT_PRECISION_HIGH
    precision highp float;
    #else
    precision mediump float;
    #endif
    uniform sampler2D uTex; uniform float uMode; uniform float uLines; uniform vec3 uLight;
    varying vec3 vN; varying vec2 vUV; varying float vH;
    vec3 turbo(float x) {
      x = clamp(x, 0.0, 1.0);
      vec4 v4 = vec4(1.0, x, x * x, x * x * x);
      vec2 v2 = v4.zw * v4.z;
      return vec3(
        dot(v4, vec4(0.13572138, 4.61539260, -42.66032258, 132.13108234)) + dot(v2, vec2(-152.94239396, 59.28637943)),
        dot(v4, vec4(0.09140261, 2.19418839, 4.84296658, -14.18503333)) + dot(v2, vec2(4.27729857, 2.82956604)),
        dot(v4, vec4(0.10667330, 12.64194608, -60.58204836, 110.36276771)) + dot(v2, vec2(-89.90310912, 27.34824973)));
    }
    void main() {
      if (uLines > 0.5) { gl_FragColor = vec4(0.75, 0.9, 1.0, 1.0); return; }
      vec3 base = uMode < 0.5 ? texture2D(uTex, vUV).rgb : (uMode < 1.5 ? turbo(vH) : vec3(0.85));
      float diff = max(dot(normalize(vN), uLight), 0.0);
      gl_FragColor = vec4(base * (0.42 + 0.68 * diff), 1.0);
    }`;

  function perspective(fovy, aspect, near, far) {
    const f = 1 / Math.tan(fovy / 2), nf = 1 / (near - far);
    return new Float32Array([f / aspect, 0, 0, 0, 0, f, 0, 0,
      0, 0, (far + near) * nf, -1, 0, 0, 2 * far * near * nf, 0]);
  }

  function lookAt(e, t, u) {
    const sub = (a, b) => [a[0] - b[0], a[1] - b[1], a[2] - b[2]];
    const cross = (a, b) => [a[1] * b[2] - a[2] * b[1], a[2] * b[0] - a[0] * b[2], a[0] * b[1] - a[1] * b[0]];
    const norm = (a) => { const l = Math.hypot(a[0], a[1], a[2]) || 1; return [a[0] / l, a[1] / l, a[2] / l]; };
    const dot = (a, b) => a[0] * b[0] + a[1] * b[1] + a[2] * b[2];
    const z = norm(sub(e, t)), x = norm(cross(u, z)), y = cross(z, x);
    return new Float32Array([x[0], y[0], z[0], 0, x[1], y[1], z[1], 0,
      x[2], y[2], z[2], 0, -dot(x, e), -dot(y, e), -dot(z, e), 1]);
  }

  function mul4(a, b) {  // column-major a·b
    const o = new Float32Array(16);
    for (let i = 0; i < 4; i++) {
      for (let j = 0; j < 4; j++) {
        let s = 0;
        for (let k = 0; k < 4; k++) s += a[k * 4 + j] * b[i * 4 + k];
        o[i * 4 + j] = s;
      }
    }
    return o;
  }

  function compile(gl, type, src) {
    const s = gl.createShader(type);
    gl.shaderSource(s, src);
    gl.compileShader(s);
    if (!gl.getShaderParameter(s, gl.COMPILE_STATUS)) throw new Error(gl.getShaderInfoLog(s));
    return s;
  }

  class Surface3D {
    constructor(canvas) {
      const gl = canvas.getContext("webgl", { antialias: true });
      if (!gl) throw new Error("이 브라우저는 WebGL(3D)을 지원하지 않습니다");
      this.gl = gl;
      this.canvas = canvas;
      this.uint = !!gl.getExtension("OES_element_index_uint");
      const p = gl.createProgram();
      gl.attachShader(p, compile(gl, gl.VERTEX_SHADER, VS));
      gl.attachShader(p, compile(gl, gl.FRAGMENT_SHADER, FS));
      gl.linkProgram(p);
      if (!gl.getProgramParameter(p, gl.LINK_STATUS)) throw new Error(gl.getProgramInfoLog(p));
      this.prog = p;
      this.a = {};
      for (const n of ["aPos", "aNrm", "aUV", "aH"]) this.a[n] = gl.getAttribLocation(p, n);
      this.u = {};
      for (const n of ["uMVP", "uTex", "uMode", "uLines", "uLight"]) this.u[n] = gl.getUniformLocation(p, n);
      this.vbo = gl.createBuffer();
      this.ibo = gl.createBuffer();
      this.lbo = gl.createBuffer();
      this.tex = gl.createTexture();
      this.opts = { height: 35, smooth: 1, res: 256, color: "texture", wire: false, auto: false };
      this.resetView();
      this.src = null;
      this._raf = 0;
    }

    resetView() {
      this.cam = { yaw: 0, pitch: 0.85, dist: 3.3, tx: 0, ty: 0 };
    }

    setSource(canvas) {
      const gl = this.gl;
      this.src = canvas;
      const lim = Math.min(TEX_MAX, gl.getParameter(gl.MAX_TEXTURE_SIZE));
      let tex = canvas;
      if (Math.max(canvas.width, canvas.height) > lim) {
        const s = lim / Math.max(canvas.width, canvas.height);
        tex = makeCanvas(Math.round(canvas.width * s), Math.round(canvas.height * s));
        const tc = tex.getContext("2d");
        tc.imageSmoothingQuality = "high";
        tc.drawImage(canvas, 0, 0, tex.width, tex.height);
      }
      gl.bindTexture(gl.TEXTURE_2D, this.tex);
      gl.pixelStorei(gl.UNPACK_FLIP_Y_WEBGL, false);
      gl.texImage2D(gl.TEXTURE_2D, 0, gl.RGBA, gl.RGBA, gl.UNSIGNED_BYTE, tex);
      gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_MIN_FILTER, gl.LINEAR);
      gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_MAG_FILTER, gl.LINEAR);
      gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_WRAP_S, gl.CLAMP_TO_EDGE);
      gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_WRAP_T, gl.CLAMP_TO_EDGE);
      this.sampleHeights();
    }

    // Down-sample the image to the mesh grid; luminance becomes height.
    sampleHeights() {
      if (!this.src) return;
      const aspect = this.src.width / this.src.height;
      let cols, rows;
      if (aspect >= 1) { cols = this.opts.res; rows = Math.max(2, Math.round(cols / aspect)); }
      else { rows = this.opts.res; cols = Math.max(2, Math.round(rows * aspect)); }
      if (!this.uint && cols * rows > 65535) {
        const f = Math.sqrt(65535 / (cols * rows));
        cols = Math.floor(cols * f); rows = Math.floor(rows * f);
      }
      const c = makeCanvas(cols, rows);
      const ctx = c.getContext("2d", { willReadFrequently: true });
      ctx.imageSmoothingQuality = "high";
      ctx.drawImage(this.src, 0, 0, cols, rows);
      const d = ctx.getImageData(0, 0, cols, rows).data;
      let h = new Float32Array(cols * rows);
      for (let i = 0; i < h.length; i++) {
        h[i] = (d[i * 4] * 0.299 + d[i * 4 + 1] * 0.587 + d[i * 4 + 2] * 0.114) / 255;
      }
      for (let pass = 0; pass < this.opts.smooth; pass++) {  // 3×3 box blur
        const o = new Float32Array(h.length);
        for (let r = 0; r < rows; r++) {
          for (let k = 0; k < cols; k++) {
            let s = 0, n = 0;
            for (let dr = -1; dr <= 1; dr++) {
              const rr = r + dr;
              if (rr < 0 || rr >= rows) continue;
              for (let dk = -1; dk <= 1; dk++) {
                const kk = k + dk;
                if (kk < 0 || kk >= cols) continue;
                s += h[rr * cols + kk]; n++;
              }
            }
            o[r * cols + k] = s / n;
          }
        }
        h = o;
      }
      let lo = Infinity, hi = -Infinity;
      for (const v of h) { if (v < lo) lo = v; if (v > hi) hi = v; }
      const span = hi - lo || 1;
      for (let i = 0; i < h.length; i++) h[i] = (h[i] - lo) / span;
      this.heights = h; this.cols = cols; this.rows = rows; this.aspect = aspect;
      this.buildMesh();
    }

    buildMesh() {
      const gl = this.gl, { cols, rows, heights: H } = this;
      const hs = this.opts.height / 100 * 0.8;
      const halfW = this.aspect >= 1 ? 1 : this.aspect, halfH = this.aspect >= 1 ? 1 / this.aspect : 1;
      const dx = 2 * halfW / (cols - 1), dy = 2 * halfH / (rows - 1);
      const v = new Float32Array(cols * rows * 9);
      for (let r = 0; r < rows; r++) {
        for (let c = 0; c < cols; c++) {
          const i = r * cols + c, o = i * 9;
          const hl = H[r * cols + Math.max(c - 1, 0)], hr = H[r * cols + Math.min(c + 1, cols - 1)];
          const hu = H[Math.max(r - 1, 0) * cols + c], hd = H[Math.min(r + 1, rows - 1) * cols + c];
          const nx = -(hr - hl) * hs / (2 * dx), ny = -(hu - hd) * hs / (2 * dy);
          const nl = Math.hypot(nx, ny, 1);
          v[o] = -halfW + c * dx; v[o + 1] = halfH - r * dy; v[o + 2] = H[i] * hs;
          v[o + 3] = nx / nl; v[o + 4] = ny / nl; v[o + 5] = 1 / nl;
          v[o + 6] = c / (cols - 1); v[o + 7] = r / (rows - 1); v[o + 8] = H[i];
        }
      }
      const Idx = this.uint ? Uint32Array : Uint16Array;
      const idx = new Idx((cols - 1) * (rows - 1) * 6);
      let k = 0;
      for (let r = 0; r < rows - 1; r++) {
        for (let c = 0; c < cols - 1; c++) {
          const i = r * cols + c;
          idx[k++] = i; idx[k++] = i + cols; idx[k++] = i + 1;
          idx[k++] = i + 1; idx[k++] = i + cols; idx[k++] = i + cols + 1;
        }
      }
      gl.bindBuffer(gl.ARRAY_BUFFER, this.vbo);
      gl.bufferData(gl.ARRAY_BUFFER, v, gl.STATIC_DRAW);
      gl.bindBuffer(gl.ELEMENT_ARRAY_BUFFER, this.ibo);
      gl.bufferData(gl.ELEMENT_ARRAY_BUFFER, idx, gl.STATIC_DRAW);
      this.nIdx = idx.length;
      this.idxType = this.uint ? gl.UNSIGNED_INT : gl.UNSIGNED_SHORT;
      this._linesFor = null;
      this.draw();
    }

    // Grid lines draped over the surface (~48 lines across).
    _buildLines() {
      const gl = this.gl, { cols, rows } = this;
      const step = Math.max(1, Math.round(Math.max(cols, rows) / 48));
      const out = [];
      for (let r = 0; r < rows; r += step) {
        for (let c = 0; c < cols - 1; c++) out.push(r * cols + c, r * cols + c + 1);
      }
      for (let c = 0; c < cols; c += step) {
        for (let r = 0; r < rows - 1; r++) out.push(r * cols + c, (r + 1) * cols + c);
      }
      const Idx = this.uint ? Uint32Array : Uint16Array;
      gl.bindBuffer(gl.ELEMENT_ARRAY_BUFFER, this.lbo);
      gl.bufferData(gl.ELEMENT_ARRAY_BUFFER, new Idx(out), gl.STATIC_DRAW);
      this.nLines = out.length;
      this._linesFor = this.vbo;
    }

    resize(w, h) {
      this.canvas.width = Math.max(1, w);
      this.canvas.height = Math.max(1, h);
      this.draw();
    }

    draw() {
      const gl = this.gl;
      if (!this.nIdx || gl.isContextLost()) return;
      const W = this.canvas.width, H = this.canvas.height, cam = this.cam;
      gl.viewport(0, 0, W, H);
      gl.clearColor(0.03, 0.05, 0.09, 1);
      gl.clear(gl.COLOR_BUFFER_BIT | gl.DEPTH_BUFFER_BIT);
      gl.enable(gl.DEPTH_TEST);
      const cp = Math.cos(cam.pitch);
      const eye = [cam.tx + cam.dist * cp * Math.sin(cam.yaw),
        cam.ty - cam.dist * cp * Math.cos(cam.yaw), cam.dist * Math.sin(cam.pitch)];
      const mvp = mul4(perspective(0.7, W / H, 0.05, 50),
        lookAt(eye, [cam.tx, cam.ty, 0.1], [0, 0, 1]));

      gl.useProgram(this.prog);
      gl.bindBuffer(gl.ARRAY_BUFFER, this.vbo);
      const F = 4 * 9;
      gl.enableVertexAttribArray(this.a.aPos);
      gl.vertexAttribPointer(this.a.aPos, 3, gl.FLOAT, false, F, 0);
      gl.enableVertexAttribArray(this.a.aNrm);
      gl.vertexAttribPointer(this.a.aNrm, 3, gl.FLOAT, false, F, 12);
      gl.enableVertexAttribArray(this.a.aUV);
      gl.vertexAttribPointer(this.a.aUV, 2, gl.FLOAT, false, F, 24);
      gl.enableVertexAttribArray(this.a.aH);
      gl.vertexAttribPointer(this.a.aH, 1, gl.FLOAT, false, F, 32);
      gl.uniformMatrix4fv(this.u.uMVP, false, mvp);
      gl.activeTexture(gl.TEXTURE0);
      gl.bindTexture(gl.TEXTURE_2D, this.tex);
      gl.uniform1i(this.u.uTex, 0);
      gl.uniform1f(this.u.uMode, { texture: 0, heat: 1, mono: 2 }[this.opts.color]);
      gl.uniform3f(this.u.uLight, -0.38, -0.52, 0.76);

      gl.uniform1f(this.u.uLines, 0);
      gl.enable(gl.POLYGON_OFFSET_FILL);
      gl.polygonOffset(1, 1);
      gl.bindBuffer(gl.ELEMENT_ARRAY_BUFFER, this.ibo);
      gl.drawElements(gl.TRIANGLES, this.nIdx, this.idxType, 0);
      gl.disable(gl.POLYGON_OFFSET_FILL);

      if (this.opts.wire) {
        if (this._linesFor !== this.vbo) this._buildLines();
        gl.uniform1f(this.u.uLines, 1);
        gl.bindBuffer(gl.ELEMENT_ARRAY_BUFFER, this.lbo);
        gl.drawElements(gl.LINES, this.nLines, this.idxType, 0);
      }
    }

    orbit(dx, dy) {
      this.cam.yaw -= dx * 0.008;
      this.cam.pitch = clamp(this.cam.pitch + dy * 0.008, 0.05, 1.55);
      this.draw();
    }

    pan(dx, dy) {
      const k = this.cam.dist * 0.0016, y = this.cam.yaw;
      // grab-style: the surface follows the pointer
      this.cam.tx = clamp(this.cam.tx - (Math.cos(y) * dx + Math.sin(y) * dy) * k, -2, 2);
      this.cam.ty = clamp(this.cam.ty - (Math.sin(y) * dx - Math.cos(y) * dy) * k, -2, 2);
      this.draw();
    }

    zoom(f) {
      this.cam.dist = clamp(this.cam.dist * f, 0.6, 8);
      this.draw();
    }

    setAuto(on) {
      this.opts.auto = on;
      cancelAnimationFrame(this._raf);
      if (!on) return;
      const tick = () => {
        this.cam.yaw += 0.006;
        this.draw();
        this._raf = requestAnimationFrame(tick);
      };
      this._raf = requestAnimationFrame(tick);
    }

    snapshot(type) {
      this.draw();  // toBlob must follow the draw in the same task
      return new Promise((res) => this.canvas.toBlob(res, type || "image/png"));
    }

    dispose() {
      cancelAnimationFrame(this._raf);
      const gl = this.gl;
      gl.deleteBuffer(this.vbo); gl.deleteBuffer(this.ibo); gl.deleteBuffer(this.lbo);
      gl.deleteTexture(this.tex); gl.deleteProgram(this.prog);
      const lose = gl.getExtension("WEBGL_lose_context");
      if (lose) lose.loseContext();
    }
  }

  /* ---------------------------------------------------------------------
     Viewport: one photo with its own view transform and adjustments
     ------------------------------------------------------------------- */

  class Viewport {
    constructor(viewer, index) {
      this.viewer = viewer;
      this.index = index;
      this.el = document.createElement("div");
      this.el.className = "pv-vp";
      this.el.innerHTML = `
        <canvas class="pv-2d"></canvas>
        <div class="pv-vp-label"></div>
        <div class="pv-vp-badge"></div>
        <button type="button" class="pv-vp-max" title="크게 보기 / 되돌리기 (더블클릭)"
                aria-label="크게 보기">⤢</button>
        <div class="pv-vp-msg">아래 목록에서 사진을 선택하세요</div>`;
      this.canvas = this.el.querySelector(".pv-2d");
      this.ctx = this.canvas.getContext("2d", { alpha: false });
      this.labelEl = this.el.querySelector(".pv-vp-label");
      this.badgeEl = this.el.querySelector(".pv-vp-badge");
      this.msgEl = this.el.querySelector(".pv-vp-msg");
      this.el.querySelector(".pv-vp-max").addEventListener("click", () => viewer.toggleMaximize(this));
      this.cssW = 0; this.cssH = 0;
      this.photo = null; this.disp = null;
      this._ptrs = new Map();
      this._loadToken = 0;
      this._reset();
      this._bindPointer(this.canvas);
    }

    _reset() {
      this.adj = { ...DEFAULT_ADJ };
      this.view = { z: 1, px: 0, py: 0, rot: 0, fh: false, fv: false };
      this.measures = [];
      this.umPerPx = null;
      this.srcData = null; this.outBuf = null; this.hist = null;
      this._pvSrc = null; this._pvCanvas = null; this._pvBuf = null; this._proxy = false;
      clearTimeout(this._fullT);
      this._draft = null; this._drag = null; this._hover = null;
    }

    destroy() {
      this.set3D(false);
      this._loadToken++;
      this.el.remove();
    }

    async setPhoto(photo) {
      this.set3D(false);
      this.photo = photo;
      this.disp = null;
      this._reset();
      this.labelEl.innerHTML = `<b>${this.index + 1}</b> ${esc(photo.label || photo.title || "")}`;
      this.msgEl.textContent = "불러오는 중…";
      this.msgEl.hidden = false;
      this.invalidate();
      this.viewer._photoChanged(this);
      const token = ++this._loadToken;
      try {
        const img = await this.viewer.loadImage(photo);
        if (token !== this._loadToken) return;
        this._setImage(img);
        this.msgEl.hidden = true;
      } catch (e) {
        if (token !== this._loadToken) return;
        this.msgEl.textContent = e.message || "이미지를 불러오지 못했습니다";
      }
      this.invalidate();
      this.viewer._photoChanged(this);
    }

    _setImage(img) {
      const w0 = img.naturalWidth || img.width, h0 = img.naturalHeight || img.height;
      const ws = Math.min(1, Math.sqrt(this.viewer.maxWorkPixels / (w0 * h0)));
      const c = makeCanvas(Math.max(1, Math.round(w0 * ws)), Math.max(1, Math.round(h0 * ws)));
      const cx = c.getContext("2d");
      cx.imageSmoothingQuality = "high";
      cx.drawImage(img, 0, 0, c.width, c.height);
      this.disp = c;            // displayed (processed) working image
      this.ws = c.width / w0;   // working / original scale (≤ 1)
      this.origW = w0; this.origH = h0;
    }

    // Original pixels, captured before the first adjustment touches `disp`
    // (plus a down-scaled copy of them for large images, see scheduleProcess).
    _ensureSrc() {
      if (!this.srcData && this.disp) {
        const { width: w, height: h } = this.disp;
        this.srcData = this.disp.getContext("2d").getImageData(0, 0, w, h);
        if (w * h > PROXY_PIXELS * 2) {
          const s = Math.sqrt(PROXY_PIXELS / (w * h));
          const c = makeCanvas(Math.round(w * s), Math.round(h * s)), cx = c.getContext("2d");
          cx.imageSmoothingQuality = "high";
          cx.drawImage(this.disp, 0, 0, c.width, c.height);
          this._pvSrc = cx.getImageData(0, 0, c.width, c.height);
          this._pvCanvas = c;
        }
      }
      return this.srcData;
    }

    ensureHist() {
      if (!this.hist && this._ensureSrc()) this.hist = histogram(this.srcData.data);
      return this.hist;
    }

    process() {
      if (!this.disp) return;
      clearTimeout(this._fullT);
      this._proxy = false;
      this._ensureSrc();
      const { width: w, height: h } = this.disp;
      const ctx = this.disp.getContext("2d");
      if (isIdentity(this.adj)) {
        ctx.putImageData(this.srcData, 0, 0);
        this.hist = histogram(this.srcData.data);
      } else {
        if (!this.outBuf) this.outBuf = new ImageData(w, h);
        processPixels(this.srcData.data, this.outBuf.data, w, h, this.adj);
        ctx.putImageData(this.outBuf, 0, 0);
        this.hist = histogram(this.outBuf.data);
      }
      this.invalidate();
      this.refresh3D();
      this.viewer._processed(this);
    }

    // Large images: while a slider moves, only the ≤1.5 MP proxy is processed
    // and shown so the control stays responsive; the full-resolution pass
    // runs once the input rests.
    scheduleProcess() {
      if (this._procPending) return;
      this._procPending = true;
      requestAnimationFrame(() => {
        this._procPending = false;
        if (!this.disp) return;
        this._ensureSrc();
        if (!this._pvCanvas) { this.process(); return; }
        const c = this._pvCanvas, src = this._pvSrc;
        let out = src;
        if (!isIdentity(this.adj)) {
          if (!this._pvBuf) this._pvBuf = new ImageData(c.width, c.height);
          processPixels(src.data, this._pvBuf.data, c.width, c.height, this.adj);
          out = this._pvBuf;
        }
        c.getContext("2d").putImageData(out, 0, 0);
        this.hist = histogram(out.data);
        this._proxy = true;
        this.invalidate();
        this.viewer._processed(this);
        clearTimeout(this._fullT);
        this._fullT = setTimeout(() => this.process(), 250);
      });
    }

    flush() {
      if (this._proxy || this._procPending) this.process();
    }

    resize() {
      const r = this.el.getBoundingClientRect();
      const dpr = window.devicePixelRatio || 1;
      this.cssW = r.width; this.cssH = r.height;
      this.canvas.width = Math.max(1, Math.round(r.width * dpr));
      this.canvas.height = Math.max(1, Math.round(r.height * dpr));
      if (this.surface) this.surface.resize(this.canvas.width, this.canvas.height);
      this.invalidate();
    }

    /* -- view transform ------------------------------------------------ */

    visible() { return this.cssW > 1 && this.cssH > 1; }

    dims() {  // displayed (rotated) image size in working pixels
      const w = this.disp.width, h = this.disp.height;
      return this.view.rot % 2 ? [h, w] : [w, h];
    }

    fitAbs() {
      const [dw, dh] = this.dims();
      return Math.max(1e-6, Math.min(this.cssW / dw, this.cssH / dh) * 0.98);
    }

    zoomAbs() { return this.view.z * this.fitAbs(); }

    zoomPct() { return this.disp ? this.zoomAbs() * this.ws * 100 : 0; }

    panAbs() {
      const z = this.zoomAbs(), [dw, dh] = this.dims();
      return [this.view.px * z * dw, this.view.py * z * dh];
    }

    setPanAbs(x, y) {
      const z = this.zoomAbs(), [dw, dh] = this.dims();
      // keep at least 24 px of the image on screen
      const mx = Math.max(0, (this.cssW + z * dw) / 2 - 24), my = Math.max(0, (this.cssH + z * dh) / 2 - 24);
      this.view.px = clamp(x, -mx, mx) / (z * dw);
      this.view.py = clamp(y, -my, my) / (z * dh);
    }

    setZoomAbs(zA, sx, sy) {
      if (!this.disp || !this.visible()) return;
      const fit = this.fitAbs();
      zA = clamp(zA, fit * 0.1, ZOOM_MAX / this.ws);
      const z0 = this.zoomAbs(), [pX, pY] = this.panAbs();
      const cx = this.cssW / 2, cy = this.cssH / 2;
      if (sx == null) { sx = cx; sy = cy; }
      const k = zA / z0;
      this.view.z = zA / fit;
      this.setPanAbs((sx - cx) - k * (sx - cx - pX), (sy - cy) - k * (sy - cy - pY));
      this.changed();
    }

    zoomAt(f, sx, sy) { this.setZoomAbs(this.zoomAbs() * f, sx, sy); }

    fit() {
      this.view.z = 1; this.view.px = 0; this.view.py = 0;
      this.changed();
    }

    actualSize() { this.setZoomAbs(1 / this.ws); }

    panBy(dx, dy) {
      if (!this.disp || !this.visible()) return;
      const [x, y] = this.panAbs();
      this.setPanAbs(x + dx, y + dy);
      this.changed();
    }

    rotate(dir) {
      if (!this.disp) return;
      const v = this.view, fitted = v.z === 1 && !v.px && !v.py;
      const zA = this.zoomAbs(), [x, y] = this.panAbs();
      v.rot = (v.rot + dir + 4) % 4;
      if (!fitted && this.visible()) {  // keep the region of interest in place
        v.z = zA / this.fitAbs();
        this.setPanAbs(dir > 0 ? -y : y, dir > 0 ? x : -x);
      }
      this.changed();
      this.refresh3D();
    }

    flip(axis) {  // axis "h" | "v" on screen
      if (!this.disp) return;
      const imgAxis = (axis === "h") !== (this.view.rot % 2 === 1) ? "fh" : "fv";
      this.view[imgAxis] = !this.view[imgAxis];
      if (axis === "h") this.view.px = -this.view.px; else this.view.py = -this.view.py;
      this.changed();
      this.refresh3D();
    }

    changed() {
      this.invalidate();
      this.viewer._viewChanged(this);
    }

    screenToImage(sx, sy) {
      const zA = this.zoomAbs(), [pX, pY] = this.panAbs();
      let [x, y] = rot90((sx - this.cssW / 2 - pX) / zA, (sy - this.cssH / 2 - pY) / zA,
        (4 - this.view.rot) % 4);
      if (this.view.fh) x = -x;
      if (this.view.fv) y = -y;
      return [x + this.disp.width / 2, y + this.disp.height / 2];
    }

    imageToScreen(u, v) {
      let x = u - this.disp.width / 2, y = v - this.disp.height / 2;
      if (this.view.fh) x = -x;
      if (this.view.fv) y = -y;
      [x, y] = rot90(x, y, this.view.rot);
      const zA = this.zoomAbs(), [pX, pY] = this.panAbs();
      return [this.cssW / 2 + pX + x * zA, this.cssH / 2 + pY + y * zA];
    }

    _clampImg([u, v]) {
      return [clamp(u, 0, this.disp.width), clamp(v, 0, this.disp.height)];
    }

    /* -- drawing --------------------------------------------------------- */

    invalidate() {
      if (this._raf) return;
      this._raf = requestAnimationFrame(() => { this._raf = 0; this.render(); });
    }

    _imageTransform(ctx) {
      const zA = this.zoomAbs(), [pX, pY] = this.panAbs();
      ctx.translate(this.cssW / 2 + pX, this.cssH / 2 + pY);
      ctx.scale(zA, zA);
      ctx.rotate(this.view.rot * Math.PI / 2);
      ctx.scale(this.view.fh ? -1 : 1, this.view.fv ? -1 : 1);
    }

    render() {
      const ctx = this.ctx, dpr = window.devicePixelRatio || 1;
      ctx.setTransform(1, 0, 0, 1, 0, 0);
      ctx.fillStyle = "#000";
      ctx.fillRect(0, 0, this.canvas.width, this.canvas.height);
      this.badgeEl.textContent = this.disp ? (this.is3d ? "3D" : `${Math.round(this.zoomPct())}%`) : "";
      if (!this.disp || !this.visible() || this.is3d) return;
      ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
      ctx.save();
      this._imageTransform(ctx);
      ctx.imageSmoothingEnabled = this.zoomPct() < 400;
      ctx.imageSmoothingQuality = "high";
      this._drawImage(ctx);
      ctx.restore();
      this._drawMeasures(ctx);
      if (this.viewer.tool === "magnifier" && this._hover && !this._drag) this._drawLens(ctx);
    }

    _drawImage(ctx) {
      const w = this.disp.width, h = this.disp.height;
      ctx.drawImage(this._proxy ? this._pvCanvas : this.disp, -w / 2, -h / 2, w, h);
    }

    _drawLens(ctx) {
      const [mx, my] = this._hover, mag = this.viewer.lensMag;
      ctx.save();
      ctx.beginPath();
      ctx.arc(mx, my, LENS_R, 0, 2 * Math.PI);
      ctx.clip();
      ctx.fillStyle = "#000";
      ctx.fill();
      ctx.translate(mx, my); ctx.scale(mag, mag); ctx.translate(-mx, -my);
      this._imageTransform(ctx);
      ctx.imageSmoothingEnabled = this.zoomPct() * mag < 400;
      this._drawImage(ctx);
      ctx.restore();
      ctx.beginPath();
      ctx.arc(mx, my, LENS_R, 0, 2 * Math.PI);
      ctx.lineWidth = 2;
      ctx.strokeStyle = "rgba(56,189,248,.95)";
      ctx.stroke();
      this._tag(ctx, `×${mag.toFixed(1)}`, mx, my + LENS_R + 14, "#7dd3fc");
    }

    _tag(ctx, text, x, y, color) {
      ctx.font = "12px system-ui, sans-serif";
      const w = ctx.measureText(text).width + 10;
      ctx.fillStyle = "rgba(0,0,0,.7)";
      ctx.fillRect(x - w / 2, y - 9, w, 18);
      ctx.fillStyle = color;
      ctx.textAlign = "center";
      ctx.textBaseline = "middle";
      ctx.fillText(text, x, y);
    }

    measureLength(m) {  // in original pixels
      return Math.hypot(m.x2 - m.x1, m.y2 - m.y1) / this.ws;
    }

    formatLength(m) {
      const px = this.measureLength(m);
      if (!this.umPerPx) return `${px.toFixed(1)} px`;
      const um = px * this.umPerPx;
      return um >= 1000 ? `${(um / 1000).toFixed(2)} mm` : `${Math.round(um)} µm`;
    }

    _drawMeasures(ctx) {
      const list = this._draft ? this.measures.concat([this._draft]) : this.measures;
      for (const m of list) {
        const a = this.imageToScreen(m.x1, m.y1), b = this.imageToScreen(m.x2, m.y2);
        ctx.strokeStyle = "#facc15";
        ctx.lineWidth = 2;
        ctx.beginPath(); ctx.moveTo(a[0], a[1]); ctx.lineTo(b[0], b[1]); ctx.stroke();
        ctx.fillStyle = "#facc15";
        for (const p of [a, b]) { ctx.beginPath(); ctx.arc(p[0], p[1], 4, 0, 2 * Math.PI); ctx.fill(); }
        this._tag(ctx, this.formatLength(m), (a[0] + b[0]) / 2, (a[1] + b[1]) / 2 - 14, "#fde68a");
      }
    }

    _hitEndpoint(p) {
      for (let i = this.measures.length - 1; i >= 0; i--) {
        const m = this.measures[i];
        for (const end of [1, 2]) {
          const s = this.imageToScreen(m["x" + end], m["y" + end]);
          if (Math.hypot(s[0] - p[0], s[1] - p[1]) <= 9) return { m, end };
        }
      }
      return null;
    }

    /* -- export ---------------------------------------------------------- */

    // The edited image at working resolution, rotation/flip applied.
    renderOriented(maxDim, withMeasures) {
      const iw = this.disp.width, ih = this.disp.height, v = this.view;
      const s = Math.min(1, (maxDim || Infinity) / Math.max(iw, ih));
      const odd = v.rot % 2;
      const W = Math.max(1, Math.round((odd ? ih : iw) * s)), H = Math.max(1, Math.round((odd ? iw : ih) * s));
      const c = makeCanvas(W, H), ctx = c.getContext("2d");
      ctx.translate(W / 2, H / 2);
      ctx.scale(s, s);
      ctx.rotate(v.rot * Math.PI / 2);
      ctx.scale(v.fh ? -1 : 1, v.fv ? -1 : 1);
      ctx.imageSmoothingQuality = "high";
      ctx.drawImage(this.disp, -iw / 2, -ih / 2);
      if (withMeasures && this.measures.length) {
        const t = ctx.getTransform();
        const map = (u, vv) => { const p = t.transformPoint({ x: u - iw / 2, y: vv - ih / 2 }); return [p.x, p.y]; };
        ctx.setTransform(1, 0, 0, 1, 0, 0);
        const lw = Math.max(2, Math.round(Math.max(W, H) / 600));
        const fs = Math.max(12, lw * 7);
        for (const m of this.measures) {
          const a = map(m.x1, m.y1), b = map(m.x2, m.y2);
          ctx.strokeStyle = ctx.fillStyle = "#facc15";
          ctx.lineWidth = lw;
          ctx.beginPath(); ctx.moveTo(a[0], a[1]); ctx.lineTo(b[0], b[1]); ctx.stroke();
          for (const p of [a, b]) { ctx.beginPath(); ctx.arc(p[0], p[1], lw * 2, 0, 2 * Math.PI); ctx.fill(); }
          ctx.font = `${fs}px system-ui, sans-serif`;
          ctx.textAlign = "center";
          ctx.lineWidth = Math.max(2, fs / 5);
          ctx.strokeStyle = "rgba(0,0,0,.8)";
          const tx = (a[0] + b[0]) / 2, ty = (a[1] + b[1]) / 2 - fs * 0.8;
          ctx.strokeText(this.formatLength(m), tx, ty);
          ctx.fillStyle = "#fde68a";
          ctx.fillText(this.formatLength(m), tx, ty);
        }
      }
      return c;
    }

    exportType() {
      return this.photo && this.photo.contentType === "image/png" ? "image/png" : "image/jpeg";
    }

    exportBlob() {
      this.flush();
      if (this.is3d) return this.surface.snapshot("image/png");
      const c = this.renderOriented(0, true), type = this.exportType();
      return new Promise((res) => c.toBlob(res, type, 0.95));
    }

    editSummary() {
      const a = this.adj, v = this.view, parts = [];
      if (a.brightness) parts.push(`밝기 ${signed(a.brightness)}`);
      if (a.contrast) parts.push(`대비 ${signed(a.contrast)}`);
      if (a.lo !== 0 || a.hi !== 255) parts.push(`레벨 ${a.lo}–${a.hi}`);
      if (a.gamma !== 1) parts.push(`감마 ${a.gamma.toFixed(2)}`);
      if (a.saturation) parts.push(`채도 ${signed(a.saturation)}`);
      if (a.sharpen) parts.push(`선명도 ${a.sharpen}`);
      if (a.channel !== "rgb") parts.push(CHANNELS.find((c) => c[0] === a.channel)[1]);
      if (a.invert) parts.push("색반전");
      if (v.rot) parts.push(`회전 ${v.rot * 90}°`);
      if (v.fh) parts.push("좌우반전");
      if (v.fv) parts.push("상하반전");
      if (this.measures.length) parts.push(`측정 ${this.measures.map((m) => this.formatLength(m)).join(", ")}`);
      if (this.is3d) parts.push("3D 캡처");
      return parts.join(", ") || "편집 없음";
    }

    /* -- 3-D ------------------------------------------------------------- */

    set3D(on) {
      if (on === !!this.is3d) return;
      if (on) {
        if (!this.disp) return;
        const c = document.createElement("canvas");
        c.className = "pv-3d";
        this.el.insertBefore(c, this.labelEl);
        try {
          this.surface = new Surface3D(c);
        } catch (e) {
          c.remove();
          this.viewer._status(e.message, "err");
          return;
        }
        Object.assign(this.surface.opts, this.viewer.opts3d);
        this.canvas3d = c;
        this._bindPointer(c);
        this.is3d = true;
        this.canvas.hidden = true;
        this.surface.resize(this.canvas.width, this.canvas.height);
        this.surface.setSource(this.renderOriented(TEX_MAX));
        this.surface.setAuto(this.surface.opts.auto);
      } else {
        clearTimeout(this._t3d);
        if (this.surface) this.surface.dispose();
        if (this.canvas3d) this.canvas3d.remove();
        this.surface = null; this.canvas3d = null;
        this.is3d = false;
        this.canvas.hidden = false;
      }
      this._drag = null; this._ptrs.clear();
      this.invalidate();
    }

    refresh3D() {
      if (!this.is3d) return;
      clearTimeout(this._t3d);
      this._t3d = setTimeout(() => {
        if (this.surface) this.surface.setSource(this.renderOriented(TEX_MAX));
      }, 60);
    }

    /* -- pointer / wheel ------------------------------------------------- */

    _bindPointer(target) {
      target.addEventListener("pointerdown", (e) => this._down(e));
      target.addEventListener("pointermove", (e) => this._move(e));
      target.addEventListener("pointerup", (e) => this._up(e));
      target.addEventListener("pointercancel", (e) => this._up(e));
      target.addEventListener("pointerleave", () => {
        if (this._ptrs.size) return;
        this._hover = null;
        this.invalidate();
        this.viewer._readout(this, null);
      });
      target.addEventListener("wheel", (e) => this._wheel(e), { passive: false });
      target.addEventListener("dblclick", (e) => { e.preventDefault(); this.viewer.toggleMaximize(this); });
      target.addEventListener("contextmenu", (e) => e.preventDefault());
    }

    _pos(e) {
      const r = e.currentTarget.getBoundingClientRect();
      return [e.clientX - r.left, e.clientY - r.top];
    }

    _down(e) {
      this.viewer.setActive(this);
      e.currentTarget.setPointerCapture(e.pointerId);
      const p = this._pos(e);
      this._ptrs.set(e.pointerId, p);
      if (this._ptrs.size === 2) {
        const [a, b] = [...this._ptrs.values()];
        this._pinch = { d: Math.hypot(a[0] - b[0], a[1] - b[1]) || 1, m: [(a[0] + b[0]) / 2, (a[1] + b[1]) / 2] };
        this._drag = null; this._draft = null;
        return;
      }
      if (this._ptrs.size > 2) return;
      if (this.is3d) {
        this._drag = { kind: e.button === 2 || e.shiftKey ? "pan3d" : "orbit", x: p[0], y: p[1] };
        return;
      }
      if (!this.disp) return;
      if (this.viewer.tool === "measure" && e.button === 0) {
        const hit = this._hitEndpoint(p);
        if (hit) {
          this._drag = { kind: "endpoint", m: hit.m, end: hit.end };
        } else {
          const [u, v] = this._clampImg(this.screenToImage(p[0], p[1]));
          this._draft = { x1: u, y1: v, x2: u, y2: v };
          this._drag = { kind: "measure", x: p[0], y: p[1] };
        }
      } else {
        this._drag = { kind: "pan", x: p[0], y: p[1] };
      }
      this.el.classList.add("is-dragging");
    }

    _move(e) {
      const p = this._pos(e);
      if (this._ptrs.has(e.pointerId)) this._ptrs.set(e.pointerId, p);
      this._hover = p;
      if (this._pinch && this._ptrs.size === 2) {
        const [a, b] = [...this._ptrs.values()];
        const d = Math.hypot(a[0] - b[0], a[1] - b[1]) || 1, m = [(a[0] + b[0]) / 2, (a[1] + b[1]) / 2];
        if (this.is3d) {
          this.surface.zoom(this._pinch.d / d);
        } else {
          this.zoomAt(d / this._pinch.d, m[0], m[1]);
          this.panBy(m[0] - this._pinch.m[0], m[1] - this._pinch.m[1]);
        }
        this._pinch = { d, m };
        return;
      }
      const g = this._drag;
      if (g && g.kind === "pan") {
        this.panBy(p[0] - g.x, p[1] - g.y);
      } else if (g && g.kind === "orbit") {
        this.surface.orbit(p[0] - g.x, p[1] - g.y);
      } else if (g && g.kind === "pan3d") {
        this.surface.pan(p[0] - g.x, p[1] - g.y);
      } else if (g && g.kind === "measure") {
        [this._draft.x2, this._draft.y2] = this._clampImg(this.screenToImage(p[0], p[1]));
      } else if (g && g.kind === "endpoint") {
        [g.m["x" + g.end], g.m["y" + g.end]] = this._clampImg(this.screenToImage(p[0], p[1]));
      }
      if (g) { g.x = p[0]; g.y = p[1]; }
      if (!this.is3d) {
        this.viewer._readout(this, p);
        this.invalidate();
      }
    }

    _up(e) {
      if (!this._ptrs.delete(e.pointerId)) return;
      const g = this._drag;
      if (this._pinch) {
        this._pinch = null;
        if (this._ptrs.size === 1) {  // continue with the remaining finger
          const [p] = [...this._ptrs.values()];
          this._drag = { kind: this.is3d ? "orbit" : "pan", x: p[0], y: p[1] };
        }
        return;
      }
      if (g && g.kind === "measure" && this._draft) {
        const m = this._draft;
        const a = this.imageToScreen(m.x1, m.y1), b = this.imageToScreen(m.x2, m.y2);
        if (Math.hypot(a[0] - b[0], a[1] - b[1]) >= 4) this.measures.push(m);
        this._draft = null;
      }
      if (g && (g.kind === "measure" || g.kind === "endpoint")) this.viewer._measuresChanged(this);
      if (!this._ptrs.size) {
        this._drag = null;
        this.el.classList.remove("is-dragging");
      }
      this.invalidate();
    }

    _wheel(e) {
      e.preventDefault();
      const f = Math.exp(-e.deltaY * (e.deltaMode === 1 ? 0.05 : 0.0015));
      if (this.is3d) { if (this.surface) this.surface.zoom(1 / f); return; }
      if (!this.disp) return;
      if (this.viewer.tool === "magnifier" && !e.ctrlKey) {
        this.viewer.lensMag = clamp(this.viewer.lensMag * f, 1.5, 10);
        this.invalidate();
        return;
      }
      const p = this._pos(e);
      this.zoomAt(f, p[0], p[1]);
    }
  }

  /* ---------------------------------------------------------------------
     PhotoViewer: toolbar, viewport grid, side panel and filmstrip
     ------------------------------------------------------------------- */

  const SLIDERS = [
    ["brightness", "밝기", -100, 100, 1],
    ["contrast", "대비", -100, 100, 1],
    ["gamma", "감마", 0.2, 3, 0.05],
    ["saturation", "채도", -100, 100, 1],
    ["sharpen", "선명도", 0, 100, 1],
  ];

  const SHORTCUTS = [
    ["휠 / 핀치", "확대·축소 (커서 위치 기준)"], ["드래그", "이동 · 3D에서는 회전 (Shift+드래그: 이동)"],
    ["더블클릭", "선택 화면 크게 보기 / 되돌리기"], ["+ / −", "확대 / 축소"], ["0", "화면 맞춤"],
    ["1", "원본 크기 (100%)"], ["R / Shift+R", "오른쪽 / 왼쪽 90° 회전"], ["H / V", "좌우 / 상하 반전"],
    ["P · M · L", "이동 · 돋보기 · 측정 도구"], ["G", "Red-free 켜기/끄기"], ["A", "자동 레벨"],
    ["I", "색반전"],
    ["3", "3D 보기"], ["S", "확대·이동 동기화"], ["← / →", "선택 화면에 이전 / 다음 사진"],
    ["[ / ]", "이전 / 다음 화면 선택"], ["Delete", "마지막 측정 삭제"], ["F", "전체화면"],
    ["Esc", "3D·크게 보기 해제"],
  ];

  class PhotoViewer {
    constructor(root, opts) {
      this.root = root;
      this.opts = opts || {};
      this.photos = (this.opts.photos || []).slice();
      this.layout = "auto";
      this.tool = "pan";
      this.sync = false;
      this.lensMag = 3;
      this.opts3d = { height: 35, smooth: 1, res: 256, color: "texture", wire: false, auto: false };
      this.viewports = [];
      this.active = null;
      this.maximized = null;
      const cells = Math.min(9, Math.max(1, this.photos.length));
      this.maxWorkPixels = clamp(Math.floor(40e6 / cells), 4e6, 16777216);
      this._imgCache = new Map();
      this._build();
      this._bindKeys();
      this._ro = new ResizeObserver((entries) => {
        for (const en of entries) {
          const vp = this.viewports.find((v) => v.el === en.target);
          if (vp) vp.resize();
          if (en.target === this.gridEl) this._orientGrid();
        }
      });
      this._ro.observe(this.gridEl);
      this.applyLayout();
      if (!this.photos.length) this._status("선택된 사진이 없습니다. 전체사진에서 사진을 선택하세요.", "err");
    }

    loadImage(photo) {
      if (!this._imgCache.has(photo.id)) {
        const pr = new Promise((res, rej) => {
          const img = new Image();
          img.decoding = "async";
          img.onload = () => res(img);
          img.onerror = () => rej(new Error("이미지를 불러오지 못했습니다"));
          img.src = photo.src;
        });
        pr.catch(() => this._imgCache.delete(photo.id));
        this._imgCache.set(photo.id, pr);
      }
      return this._imgCache.get(photo.id);
    }

    /* -- DOM ------------------------------------------------------------- */

    _build() {
      const canSave = typeof this.opts.onSaveEdited === "function";
      const btn = (act, label, title, extra) =>
        `<button type="button" class="pv-btn" data-act="${act}" title="${title}" aria-label="${title}"${extra || ""}>${label}</button>`;
      const tool = (t, label, title) =>
        `<button type="button" class="pv-btn" data-tool="${t}" title="${title}" aria-label="${title}" aria-pressed="false">${label}</button>`;
      this.root.classList.add("pv");
      this.root.innerHTML = `
        <div class="pv-toolbar" role="toolbar" aria-label="뷰어 도구">
          <div class="pv-group">
            <label class="pv-select">배열
              <select data-ctl="layout">${LAYOUTS.map(([k, l]) => `<option value="${k}">${l}</option>`).join("")}</select>
            </label>
          </div>
          <div class="pv-group">
            ${tool("pan", "✋ 이동", "이동 (P)")}
            ${tool("magnifier", "🔍 돋보기", "돋보기 (M) — 휠로 배율 조절")}
            ${tool("measure", "📏 측정", "길이 측정 (L) — 끝점을 끌어 수정")}
          </div>
          <div class="pv-group">
            ${btn("zoom-out", "−", "축소 (−)")}
            <span class="pv-zoom" data-out="zoom">–</span>
            ${btn("zoom-in", "+", "확대 (+)")}
            ${btn("fit", "맞춤", "화면 맞춤 (0)")}
            ${btn("actual", "1:1", "원본 크기 100% (1)")}
          </div>
          <div class="pv-group">
            ${btn("rot-ccw", "⟲", "왼쪽 90° 회전 (Shift+R)")}
            ${btn("rot-cw", "⟳", "오른쪽 90° 회전 (R)")}
            ${btn("flip-h", "↔", "좌우 반전 (H)")}
            ${btn("flip-v", "↕", "상하 반전 (V)")}
          </div>
          <div class="pv-group">
            ${btn("3d", "3D", "3D 입체 보기 (3) — 밝기를 높이로 표시", ' aria-pressed="false"')}
            ${btn("sync", "🔗 동기화", "모든 화면 확대·이동 동기화 (S)", ' aria-pressed="false"')}
          </div>
          <div class="pv-group">
            ${btn("reset", "↺ 초기화", "선택 화면의 보기·조정 초기화")}
            ${this.opts.download === false ? "" : btn("download", "⬇ 내려받기", "편집한 이미지 내려받기")}
            ${canSave ? btn("save", "💾 편집본 저장", "편집본을 새 사진으로 저장 (원본은 그대로 유지)") : ""}
          </div>
          <div class="pv-group pv-right">
            ${btn("panel", "☰ 조정", "조정 패널 열기/닫기", ' aria-pressed="true"')}
            ${btn("fullscreen", "⛶", "전체화면 (F)")}
            ${btn("help", "?", "단축키 도움말")}
          </div>
        </div>
        <div class="pv-body">
          <div class="pv-stage">
            <div class="pv-grid"></div>
            <div class="pv-film" aria-label="선택한 사진"></div>
          </div>
          <aside class="pv-side">
            <section>
              <h4>영상 조정</h4>
              ${SLIDERS.map(([k, l, mn, mx, st]) => `
                <label class="pv-slider"><span>${l}</span>
                  <input type="range" data-adj="${k}" min="${mn}" max="${mx}" step="${st}">
                  <output data-adj-out="${k}"></output></label>`).join("")}
              <div class="pv-seg" role="group" aria-label="채널">
                ${CHANNELS.map(([k, l]) => `<button type="button" class="pv-btn" data-channel="${k}" aria-pressed="false">${l}</button>`).join("")}
              </div>
              <div class="pv-row pv-levels">
                ${btn("auto-levels", "◐ 자동 레벨", "밝기 범위를 자동으로 펼침 (A)")}
                <span data-out="levels"></span>
              </div>
              <label class="pv-check"><input type="checkbox" data-adj="invert"> 색반전 (I)</label>
              <canvas class="pv-hist" width="240" height="56" aria-label="히스토그램"></canvas>
              <div class="pv-row">
                ${btn("adj-reset", "조정 초기화", "선택 화면의 영상 조정만 초기화")}
                ${btn("adj-all", "모든 사진에 적용", "현재 조정값을 모든 화면에 적용")}
              </div>
            </section>
            <section data-sec="3d">
              <h4>3D 보기 <small>밝기 → 높이</small></h4>
              <label class="pv-slider"><span>높이</span>
                <input type="range" data-3d="height" min="0" max="100" step="1"><output data-3d-out="height"></output></label>
              <label class="pv-slider"><span>스무딩</span>
                <input type="range" data-3d="smooth" min="0" max="6" step="1"><output data-3d-out="smooth"></output></label>
              <label class="pv-field">메쉬
                <select data-3d="res"><option value="128">128</option><option value="256">256</option><option value="512">512</option></select></label>
              <label class="pv-field">표면 색
                <select data-3d="color"><option value="texture">원본 영상</option><option value="heat">높이 컬러맵</option><option value="mono">단색 음영</option></select></label>
              <label class="pv-check"><input type="checkbox" data-3d="wire"> 격자 표시</label>
              <label class="pv-check"><input type="checkbox" data-3d="auto"> 자동 회전</label>
              <div class="pv-row">${btn("3d-view", "시점 초기화", "3D 시점 초기화")}</div>
              <p class="pv-hint">드래그: 회전 · Shift/오른쪽 드래그: 이동 · 휠: 거리</p>
            </section>
            <section>
              <h4>측정</h4>
              <label class="pv-field">축척 (µm/px)
                <input type="number" data-ctl="scale" min="0" step="0.1" placeholder="비우면 px"></label>
              <ul class="pv-measures"></ul>
              <div class="pv-row">${btn("measure-clear", "측정 모두 지우기", "선택 화면의 측정 모두 삭제")}</div>
            </section>
            <section>
              <h4>사진 정보</h4>
              <dl class="pv-info"></dl>
              <p class="pv-readout" data-out="readout">커서를 사진 위에 올리면 좌표와 픽셀값이 표시됩니다.</p>
            </section>
          </aside>
        </div>
        <div class="pv-status" role="status" aria-live="polite"></div>
        <div class="pv-help" hidden>
          <div class="pv-help-card" role="dialog" aria-label="단축키">
            <div class="pv-help-head"><b>단축키</b>${btn("help", "✕", "닫기")}</div>
            <dl>${SHORTCUTS.map(([k, d]) => `<dt>${k}</dt><dd>${d}</dd>`).join("")}</dl>
          </div>
        </div>`;
      const $ = (s) => this.root.querySelector(s);
      this.gridEl = $(".pv-grid");
      this.filmEl = $(".pv-film");
      this.sideEl = $(".pv-side");
      this.statusEl = $(".pv-status");
      this.helpEl = $(".pv-help");
      this.histEl = $(".pv-hist");

      this.root.addEventListener("click", (e) => {
        const b = e.target.closest("[data-act],[data-tool],[data-channel]");
        if (!b || !this.root.contains(b)) return;
        if (b.dataset.tool) this.setTool(b.dataset.tool);
        else if (b.dataset.channel) this.setAdj("channel", b.dataset.channel);
        else this.action(b.dataset.act);
      });
      $('[data-ctl="layout"]').addEventListener("change", (e) => { this.layout = e.target.value; this.applyLayout(); });
      this.root.querySelectorAll("input[data-adj]").forEach((inp) => {
        inp.addEventListener("input", () => this.setAdj(inp.dataset.adj,
          inp.type === "checkbox" ? inp.checked : parseFloat(inp.value)));
      });
      this.root.querySelectorAll("[data-adj-out]").forEach((out) => {
        out.title = "더블클릭: 기본값";
        out.addEventListener("dblclick", () => this.setAdj(out.dataset.adjOut, DEFAULT_ADJ[out.dataset.adjOut]));
      });
      this.root.querySelectorAll("[data-3d]").forEach((inp) => {
        inp.addEventListener(inp.tagName === "SELECT" || inp.type === "checkbox" ? "change" : "input", () => {
          const k = inp.dataset["3d"];
          const v = inp.type === "checkbox" ? inp.checked : inp.tagName === "SELECT" && k === "color" ? inp.value : parseFloat(inp.value);
          this.set3DOpt(k, v);
        });
      });
      $('[data-ctl="scale"]').addEventListener("input", (e) => {
        const vp = this.active;
        if (!vp) return;
        const v = parseFloat(e.target.value);
        vp.umPerPx = v > 0 ? v : null;
        vp.invalidate();
        this._measuresChanged(vp);
      });
      this.root.querySelector(".pv-measures").addEventListener("click", (e) => {
        const b = e.target.closest("[data-del]");
        if (!b || !this.active) return;
        this.active.measures.splice(+b.dataset.del, 1);
        this.active.invalidate();
        this._measuresChanged(this.active);
      });
      this.filmEl.addEventListener("click", (e) => {
        const b = e.target.closest("[data-photo]");
        if (!b || !this.active) return;
        const photo = this.photos.find((p) => String(p.id) === b.dataset.photo);
        if (photo) this.active.setPhoto(photo);
      });
      this.helpEl.addEventListener("click", (e) => { if (e.target === this.helpEl) this.helpEl.hidden = true; });
      this._onFullscreen = () => this.viewports.forEach((v) => v.resize());
      document.addEventListener("fullscreenchange", this._onFullscreen);
      if (window.matchMedia("(max-width: 900px)").matches) {  // panel overlays the images there
        this.root.classList.add("pv-side-closed");
        this._btn("panel").setAttribute("aria-pressed", "false");
      }
      this._syncPanel();
    }

    _cellsFor(n) {
      if (this.layout !== "auto") return +this.layout;
      return n <= 1 ? 1 : n === 2 ? 2 : n <= 4 ? 4 : n <= 6 ? 6 : 9;
    }

    applyLayout() {
      const n = this._cellsFor(this.photos.length);
      while (this.viewports.length > n) {
        const vp = this.viewports.pop();
        this._ro.unobserve(vp.el);
        vp.destroy();
      }
      while (this.viewports.length < n) {
        const vp = new Viewport(this, this.viewports.length);
        this.viewports.push(vp);
        this.gridEl.appendChild(vp.el);
        this._ro.observe(vp.el);
        const next = this.photos.find((p) => !this.viewports.some((v) => v.photo === p));
        if (next) vp.setPhoto(next);
      }
      if (!this.viewports.includes(this.maximized)) this.maximized = null;
      this._orientGrid();
      this._applyMax();
      this.setActive(this.viewports.includes(this.active) ? this.active : this.viewports[0]);
      this._renderFilm();
    }

    // Lay cells out to suit the stage: 1×2 becomes 2×1 on a portrait screen.
    _orientGrid() {
      let [cols, rows] = GRID[this.viewports.length] || [1, 1];
      const r = this.gridEl.getBoundingClientRect();
      if (r.height > r.width * 1.15 && cols > rows) [cols, rows] = [rows, cols];
      this.gridEl.style.gridTemplateColumns = `repeat(${cols}, minmax(0, 1fr))`;
      this.gridEl.style.gridTemplateRows = `repeat(${rows}, minmax(0, 1fr))`;
    }

    toggleMaximize(vp) {
      this.maximized = this.maximized === vp || this.viewports.length === 1 ? null : vp;
      this._applyMax();
      this.setActive(vp);
    }

    _applyMax() {
      this.gridEl.classList.toggle("is-max", !!this.maximized);
      for (const v of this.viewports) v.el.classList.toggle("is-max", v === this.maximized);
    }

    setActive(vp) {
      if (!vp) return;
      const changed = this.active !== vp;
      this.active = vp;
      for (const v of this.viewports) v.el.classList.toggle("is-active", v === vp);
      if (changed) this._syncPanel();
    }

    setTool(tool) {
      this.tool = tool;
      this.root.querySelectorAll("[data-tool]").forEach((b) =>
        b.setAttribute("aria-pressed", String(b.dataset.tool === tool)));
      this.gridEl.dataset.tool = tool;
      this.viewports.forEach((v) => v.invalidate());
      if (tool === "magnifier") this._status(`돋보기 ×${this.lensMag.toFixed(1)} — 휠로 배율을 바꿉니다`);
      if (tool === "measure") this._status("드래그해서 길이를 잽니다. 끝점을 끌면 수정됩니다.");
    }

    setAdj(key, value) {
      const vp = this.active;
      if (!vp || !vp.disp) return;
      vp.adj[key] = value;
      vp.scheduleProcess();
      this._syncAdj();
    }

    set3DOpt(key, value) {
      this.opts3d[key] = value;
      const s = this.active && this.active.surface;
      if (s) {
        s.opts[key] = value;
        if (key === "auto") s.setAuto(value);
        else if (key === "height") s.buildMesh();
        else if (key === "smooth" || key === "res") s.sampleHeights();
        else s.draw();
      }
      this._sync3D();
    }

    action(act) {
      const vp = this.active;
      const has = vp && vp.disp;
      switch (act) {
        case "zoom-in": if (has) vp.zoomAt(1.25); break;
        case "zoom-out": if (has) vp.zoomAt(0.8); break;
        case "fit": if (has) vp.fit(); break;
        case "actual": if (has) vp.actualSize(); break;
        case "rot-cw": if (has) vp.rotate(1); break;
        case "rot-ccw": if (has) vp.rotate(-1); break;
        case "flip-h": if (has) vp.flip("h"); break;
        case "flip-v": if (has) vp.flip("v"); break;
        case "3d":
          if (has) { vp.set3D(!vp.is3d); this._sync3D(); }
          break;
        case "3d-view":
          if (vp && vp.surface) { vp.surface.resetView(); vp.surface.draw(); }
          break;
        case "sync":
          this.sync = !this.sync;
          this._btn("sync").setAttribute("aria-pressed", String(this.sync));
          if (this.sync && has) this._viewChanged(vp);
          this._status(this.sync ? "확대·이동이 모든 화면에 동기화됩니다" : "동기화 해제");
          break;
        case "reset":
          if (!has) break;
          vp.set3D(false);
          vp.adj = { ...DEFAULT_ADJ };
          vp.view = { z: 1, px: 0, py: 0, rot: 0, fh: false, fv: false };
          vp.process();
          vp.changed();
          this._syncPanel();
          break;
        case "auto-levels": {
          if (!has) break;
          const [lo, hi] = autoLevels(vp._ensureSrc().data, vp.adj.channel);
          vp.adj.lo = lo; vp.adj.hi = hi;
          vp.scheduleProcess();
          this._syncAdj();
          break;
        }
        case "adj-reset":
          if (!has) break;
          vp.adj = { ...DEFAULT_ADJ };
          vp.scheduleProcess();
          this._syncAdj();
          break;
        case "adj-all":
          if (!has) break;
          for (const o of this.viewports) {
            if (o === vp || !o.disp) continue;
            o.adj = { ...vp.adj };
            o.scheduleProcess();
          }
          this._status("현재 영상 조정을 모든 화면에 적용했습니다", "ok");
          break;
        case "measure-clear":
          if (!vp) break;
          vp.measures = [];
          vp.invalidate();
          this._measuresChanged(vp);
          break;
        case "download": this.download(); break;
        case "save": this.saveEdited(); break;
        case "panel": {
          const open = this.root.classList.toggle("pv-side-closed") === false;
          this._btn("panel").setAttribute("aria-pressed", String(open));
          break;
        }
        case "fullscreen":
          if (document.fullscreenElement) document.exitFullscreen();
          else if (this.root.requestFullscreen) this.root.requestFullscreen().catch(() => {});
          break;
        case "help": this.helpEl.hidden = !this.helpEl.hidden; break;
      }
    }

    _btn(act, scope) { return this.root.querySelector(`${scope || ".pv-toolbar"} [data-act="${act}"]`); }

    async download() {
      const vp = this.active;
      if (!vp || !vp.disp) return;
      const blob = await vp.exportBlob();
      if (!blob) { this._status("이미지를 만들지 못했습니다", "err"); return; }
      const ext = blob.type === "image/png" ? "png" : "jpg";
      const a = document.createElement("a");
      a.href = URL.createObjectURL(blob);
      a.download = `${(vp.photo.title || "photo").replace(/[\\/:*?"<>|]+/g, "_")}_${vp.is3d ? "3d" : "edited"}.${ext}`;
      document.body.appendChild(a);
      a.click();
      a.remove();
      setTimeout(() => URL.revokeObjectURL(a.href), 4000);
    }

    async saveEdited() {
      const vp = this.active;
      if (!vp || !vp.disp || !this.opts.onSaveEdited) return;
      const summary = vp.editSummary();
      if (summary === "편집 없음") {
        this._status("변경된 내용이 없습니다. 조정·회전·측정 후 저장하세요.", "err");
        return;
      }
      const saveBtn = this._btn("save");
      saveBtn.disabled = true;
      this._status("편집본 저장 중…");
      try {
        const blob = await vp.exportBlob();
        if (!blob) throw new Error("이미지를 만들지 못했습니다");
        const added = await this.opts.onSaveEdited(vp.photo, blob, { summary });
        if (added) {
          this.photos.push(added);
          this._renderFilm();
        }
        this._status(`편집본이 새 사진으로 저장되었습니다 (${summary})`, "ok");
      } catch (e) {
        this._status(`저장 실패: ${e.message}`, "err");
      } finally {
        saveBtn.disabled = false;
      }
    }

    /* -- callbacks from viewports -------------------------------------- */

    _viewChanged(vp) {
      if (this.sync) {
        for (const o of this.viewports) {
          if (o === vp || !o.disp) continue;
          o.view.z = vp.view.z; o.view.px = vp.view.px; o.view.py = vp.view.py;
          o.invalidate();
        }
      }
      if (vp === this.active) this._syncZoom();
    }

    _processed(vp) {
      if (vp === this.active) this._drawHist();
    }

    _photoChanged(vp) {
      this._renderFilm();
      if (vp === this.active) this._syncPanel();
    }

    _measuresChanged(vp) {
      if (vp !== this.active) return;
      const ul = this.root.querySelector(".pv-measures");
      ul.innerHTML = vp.measures.map((m, i) =>
        `<li><span>#${i + 1}</span> ${esc(vp.formatLength(m))}
           <button type="button" class="pv-x" data-del="${i}" title="삭제" aria-label="측정 ${i + 1} 삭제">✕</button></li>`).join("")
        || `<li class="pv-empty">측정 도구(📏)로 드래그하세요</li>`;
    }

    _readout(vp, p) {
      const out = this.root.querySelector('[data-out="readout"]');
      if (!p || !vp.disp || vp !== this.active) {
        if (!p) out.textContent = "커서를 사진 위에 올리면 좌표와 픽셀값이 표시됩니다.";
        return;
      }
      const [u, v] = vp.screenToImage(p[0], p[1]);
      if (u < 0 || v < 0 || u >= vp.disp.width || v >= vp.disp.height) {
        out.textContent = "사진 밖";
        return;
      }
      const src = vp._ensureSrc();
      const i = (Math.floor(v) * vp.disp.width + Math.floor(u)) * 4;
      out.textContent = `x ${Math.floor(u / vp.ws)}, y ${Math.floor(v / vp.ws)} · ` +
        `원본 RGB ${src.data[i]}/${src.data[i + 1]}/${src.data[i + 2]}`;
    }

    /* -- panel sync ------------------------------------------------------ */

    _syncPanel() {
      this._syncAdj();
      this._sync3D();
      this._syncZoom();
      const vp = this.active;
      const scale = this.root.querySelector('[data-ctl="scale"]');
      scale.value = vp && vp.umPerPx ? vp.umPerPx : "";
      if (vp) this._measuresChanged(vp);
      const info = this.root.querySelector(".pv-info");
      const p = vp && vp.photo;
      if (!p) { info.innerHTML = `<dd class="pv-empty">사진 없음</dd>`; return; }
      const rows = (p.info || []).slice();
      if (vp.disp) {
        rows.push(["해상도", `${vp.origW} × ${vp.origH}` + (vp.ws < 1 ? ` (작업 ${vp.disp.width} × ${vp.disp.height})` : "")]);
      }
      info.innerHTML = rows.map(([k, v]) => `<dt>${esc(k)}</dt><dd>${esc(v)}</dd>`).join("") +
        (p.downloadUrl ? `<dt>원본</dt><dd><a href="${esc(p.downloadUrl)}">원본 파일 내려받기</a></dd>` : "");
    }

    _syncAdj() {
      const vp = this.active, a = vp ? vp.adj : DEFAULT_ADJ, enabled = !!(vp && vp.disp);
      for (const [k] of SLIDERS) {
        const inp = this.root.querySelector(`input[data-adj="${k}"]`);
        inp.value = a[k];
        inp.disabled = !enabled;
        this.root.querySelector(`[data-adj-out="${k}"]`).textContent =
          k === "gamma" ? a[k].toFixed(2) : signed(a[k]);
      }
      this.root.querySelector('[data-out="levels"]').textContent =
        a.lo !== 0 || a.hi !== 255 ? `레벨 ${a.lo}–${a.hi}` : "";
      this._btn("auto-levels", ".pv-side").disabled = !enabled;
      const inv = this.root.querySelector('input[data-adj="invert"]');
      inv.checked = a.invert;
      inv.disabled = !enabled;
      this.root.querySelectorAll("[data-channel]").forEach((b) => {
        b.setAttribute("aria-pressed", String(b.dataset.channel === a.channel));
        b.disabled = !enabled;
      });
      this._drawHist();
    }

    _sync3D() {
      const vp = this.active, on = !!(vp && vp.is3d);
      this._btn("3d").setAttribute("aria-pressed", String(on));
      const sec = this.root.querySelector('[data-sec="3d"]');
      sec.classList.toggle("is-off", !on);
      const o = on ? vp.surface.opts : this.opts3d;
      sec.querySelectorAll("[data-3d]").forEach((inp) => {
        const k = inp.dataset["3d"];
        if (inp.type === "checkbox") inp.checked = !!o[k]; else inp.value = o[k];
      });
      sec.querySelectorAll("[data-3d-out]").forEach((out) => { out.textContent = o[out.dataset["3dOut"]]; });
    }

    _syncZoom() {
      const vp = this.active;
      this.root.querySelector('[data-out="zoom"]').textContent =
        vp && vp.disp ? (vp.is3d ? "3D" : `${Math.round(vp.zoomPct())}%`) : "–";
    }

    _drawHist() {
      const c = this.histEl, ctx = c.getContext("2d");
      ctx.clearRect(0, 0, c.width, c.height);
      const vp = this.active;
      const hist = vp && vp.disp && vp.ensureHist();
      if (!hist) return;
      let max = 1;
      for (let i = 1; i < 255; i++) max = Math.max(max, hist[i]);  // ignore clipped ends
      ctx.fillStyle = "#38bdf8";
      const bw = c.width / 256;
      for (let i = 0; i < 256; i++) {
        const h = Math.min(1, hist[i] / max) * (c.height - 2);
        ctx.fillRect(i * bw, c.height - h, Math.max(1, bw), h);
      }
    }

    _renderFilm() {
      this.filmEl.innerHTML = this.photos.map((p) => {
        const slots = this.viewports.filter((v) => v.photo === p).map((v) => v.index + 1);
        return `<button type="button" class="pv-thumb${slots.length ? " is-shown" : ""}" data-photo="${esc(p.id)}"
                  title="${esc(p.label || p.title || "")} — 클릭: 선택 화면에 표시">
                  <img src="${esc(p.thumb || p.src)}" alt="" loading="lazy">
                  ${slots.length ? `<i>${slots.join(",")}</i>` : ""}
                  <span>${esc(p.short || p.title || "")}</span>
                </button>`;
      }).join("");
    }

    _status(msg, kind) {
      this.statusEl.textContent = msg || "";
      this.statusEl.className = "pv-status" + (kind ? " " + kind : "");
      clearTimeout(this._statusT);
      if (msg) this._statusT = setTimeout(() => { this.statusEl.textContent = ""; }, 6000);
    }

    /* -- keyboard -------------------------------------------------------- */

    _bindKeys() {
      this._onKey = (e) => {
        if (e.ctrlKey || e.metaKey || e.altKey) return;
        if (e.target.closest && e.target.closest("input, select, textarea")) return;
        const vp = this.active, k = e.key;
        const step = (d) => {
          if (!vp || !this.photos.length) return;
          const i = this.photos.indexOf(vp.photo);
          vp.setPhoto(this.photos[(i + d + this.photos.length) % this.photos.length]);
        };
        const cycle = (d) => {
          const n = this.viewports.length, i = this.viewports.indexOf(vp);
          this.setActive(this.viewports[(i + d + n) % n]);
        };
        const map = {
          "+": () => this.action("zoom-in"), "=": () => this.action("zoom-in"),
          "-": () => this.action("zoom-out"), "_": () => this.action("zoom-out"),
          "0": () => this.action("fit"), "1": () => this.action("actual"),
          r: () => this.action("rot-cw"), R: () => this.action("rot-ccw"),
          h: () => this.action("flip-h"), v: () => this.action("flip-v"),
          p: () => this.setTool("pan"), m: () => this.setTool("magnifier"), l: () => this.setTool("measure"),
          g: () => vp && this.setAdj("channel", vp.adj.channel === "green" ? "rgb" : "green"),
          i: () => vp && this.setAdj("invert", !vp.adj.invert),
          a: () => this.action("auto-levels"),
          3: () => this.action("3d"), s: () => this.action("sync"), f: () => this.action("fullscreen"),
          "?": () => this.action("help"),
          ArrowLeft: () => step(-1), ArrowRight: () => step(1),
          "[": () => cycle(-1), "]": () => cycle(1),
          Delete: () => { if (vp && vp.measures.pop()) { vp.invalidate(); this._measuresChanged(vp); } },
          Escape: () => {
            if (!this.helpEl.hidden) this.helpEl.hidden = true;
            else if (vp && vp.is3d) this.action("3d");
            else if (this.maximized) this.toggleMaximize(this.maximized);
          },
        };
        map.Backspace = map.Delete;
        const fn = map[k] || (k.length === 1 ? map[k.toLowerCase()] : null);
        if (!fn) return;
        e.preventDefault();
        fn();
      };
      document.addEventListener("keydown", this._onKey);
    }

    // Detach from the page (for pages that open the viewer more than once).
    destroy() {
      document.removeEventListener("keydown", this._onKey);
      document.removeEventListener("fullscreenchange", this._onFullscreen);
      this._ro.disconnect();
      this.viewports.forEach((v) => v.destroy());
      this.viewports = [];
      this.root.innerHTML = "";
      this.root.classList.remove("pv", "pv-side-closed");
    }
  }

  global.PhotoViewer = PhotoViewer;
})(window);
