/* NK15068 map engine — draws the scraped 15068 dataset on a canvas.
   World units are metres on a local grid (x east, y south) centred on the ZIP.
   Every fetch is prefixed with <html data-root> so pages at any depth find data/. */
(function () {
  "use strict";
  const ROOT = () => (typeof document !== "undefined" && document.documentElement.dataset.root) || "";

  const GROUP_COLORS = {
    eat: "#e0743a", shop: "#c9a227", health: "#d4455b", faith: "#8b6fc6",
    learn: "#3c8dbc", play: "#3f9a5b", civic: "#5c7cfa", culture: "#b0508f",
    auto: "#7a8a99", services: "#8c7b6b", stay: "#1aa39a",
  };

  const cache = {};
  /* a failed fetch is forgotten so the next call can try again */
  const keep = (k, p) => { cache[k] = p; p.catch(() => { if (cache[k] === p) delete cache[k]; }); return p; };
  function getJSON(name) {
    if (!cache[name]) keep(name, fetch(ROOT() + "data/" + name).then((r) => {
      if (!r.ok) throw new Error(name + " " + r.status);
      return r.json();
    }));
    return cache[name];
  }
  function getTerrain(meta) {
    // heightmap PNG: elevation in decimetres = R*256 + G
    if (!cache.terrain) keep("terrain", fetch(ROOT() + "data/terrain.png").then((r) => { if (!r.ok) throw new Error("terrain.png " + r.status); return r.blob(); })
      .then((b) => createImageBitmap(b, { colorSpaceConversion: "none", premultiplyAlpha: "none" }))
      .then((img) => {
        const c = document.createElement("canvas");
        c.width = img.width; c.height = img.height;
        const ctx = c.getContext("2d", { willReadFrequently: true });
        ctx.drawImage(img, 0, 0);
        const px = ctx.getImageData(0, 0, img.width, img.height).data;
        const f = new Float32Array(img.width * img.height);
        for (let i = 0; i < f.length; i++) f[i] = (px[i * 4] * 256 + px[i * 4 + 1]) / 10;
        return { data: f, ...meta.terrain };
      }));
    return cache.terrain;
  }

  /* road lines without Path2D: [{n, rank, bridge, pts: flat x,y Float32Array}] (pets, blotter and near-me use it) */
  function loadLines() {
    if (!cache["lines"]) keep("lines", Promise.all([getJSON("meta.json"), getJSON("roads.json")]).then(([meta, roads]) =>
      roads.r.map(([rank, ni, brg, c]) => ({ n: ni >= 0 ? roads.names[ni] : null, rank, bridge: !!brg, pts: dec(c, meta.q) }))));
    return cache["lines"];
  }

  /* decode a delta/quantised int list to a Float32Array of metres */
  function dec(arr, q) {
    const out = new Float32Array(arr.length);
    let x = 0, y = 0;
    for (let i = 0; i < arr.length; i += 2) {
      x += arr[i]; y += arr[i + 1];
      out[i] = x / q; out[i + 1] = y / q;
    }
    return out;
  }
  function addPoly(path, pts, close) {
    path.moveTo(pts[0], pts[1]);
    for (let i = 2; i < pts.length; i += 2) path.lineTo(pts[i], pts[i + 1]);
    if (close) path.closePath();
  }

  function css(name) {
    return getComputedStyle(document.documentElement).getPropertyValue(name).trim();
  }

  function heightAt(T, x, y) {
    const fx = (x - T.x0) / T.cell, fy = (y - T.y0) / T.cell;
    const i = Math.max(0, Math.min(T.w - 2, Math.floor(fx)));
    const j = Math.max(0, Math.min(T.h - 2, Math.floor(fy)));
    const u = Math.min(1, Math.max(0, fx - i)), v = Math.min(1, Math.max(0, fy - j));
    const d = T.data, w = T.w;
    return d[j * w + i] * (1 - u) * (1 - v) + d[j * w + i + 1] * u * (1 - v) +
      d[(j + 1) * w + i] * (1 - u) * v + d[(j + 1) * w + i + 1] * u * v;
  }

  /* shaded-relief image of the real terrain */
  function hillshade(T, dark) {
    const c = document.createElement("canvas");
    c.width = T.w; c.height = T.h;
    const ctx = c.getContext("2d");
    const img = ctx.createImageData(T.w, T.h);
    const d = T.data, w = T.w, h = T.h, cell = T.cell;
    const lx = -0.5, ly = -0.6, lz = 0.62;
    let lo = Infinity, hi = -Infinity;
    for (let i = 0; i < d.length; i++) { if (d[i] < lo) lo = d[i]; if (d[i] > hi) hi = d[i]; }
    for (let j = 0; j < h; j++) {
      for (let i = 0; i < w; i++) {
        const k = j * w + i;
        const l = d[j * w + Math.max(0, i - 1)], r = d[j * w + Math.min(w - 1, i + 1)];
        const t = d[Math.max(0, j - 1) * w + i], b = d[Math.min(h - 1, j + 1) * w + i];
        const nx = (l - r) * 2.2 / (2 * cell), ny = (t - b) * 2.2 / (2 * cell);
        const len = Math.hypot(nx, ny, 1);
        const s = (nx * lx + ny * ly + lz) / len;
        const e = (d[k] - lo) / (hi - lo);
        const o = k * 4;
        if (dark) {
          img.data[o] = 0; img.data[o + 1] = 0; img.data[o + 2] = 0;
          img.data[o + 3] = Math.max(0, Math.min(255, (0.62 - s) * 330));
          if (s > 0.62) { img.data[o] = 120 + e * 60; img.data[o + 1] = 140 + e * 40; img.data[o + 2] = 160; img.data[o + 3] = (s - 0.62) * 260; }
        } else {
          const sh = Math.max(0, Math.min(1, s));
          img.data[o] = 60; img.data[o + 1] = 70; img.data[o + 2] = 60;
          img.data[o + 3] = Math.max(0, Math.min(255, (0.8 - sh) * 260 + (1 - e) * 10));
        }
      }
    }
    ctx.putImageData(img, 0, 0);
    return c;
  }

  /* Build every Path2D once; the renderer only swaps transforms. */
  async function loadWorld(opts = {}) {
    const meta = await getJSON("meta.json");
    const q = meta.q;
    const [base, roads] = await Promise.all([getJSON("base.json"), getJSON("roads.json")]);
    const W = { meta, q, base, roadsRaw: roads };
    W.zip = new Path2D();
    base.zip.forEach((r) => addPoly(W.zip, dec(r, q), true));
    W.water = new Path2D();
    base.water.forEach((r) => addPoly(W.water, dec(r, q), true));
    W.green = new Path2D();
    base.green.forEach((r) => addPoly(W.green, dec(r, q), true));
    W.use = {};
    base.use.forEach((u) => {
      const p = W.use[u.k] || (W.use[u.k] = new Path2D());
      u.r.forEach((r) => addPoly(p, dec(r, q), true));
    });
    W.streams = [new Path2D(), new Path2D(), new Path2D()];
    base.streams.forEach((s) => addPoly(W.streams[s.w - 1], dec(s.c, q), false));
    W.rail = new Path2D();
    base.rail.forEach((r) => addPoly(W.rail, dec(r, q), false));
    W.bridges = new Path2D();
    base.bridges.forEach((r) => addPoly(W.bridges, dec(r, q), true));
    W.towns = base.towns.map((t) => {
      const p = new Path2D();
      t.r.forEach((r) => addPoly(p, dec(r, q), true));
      return { n: t.n, core: t.core, p };
    });
    // roads grouped by rank; also keep decoded lines for the hero animation
    W.roads = Array.from({ length: 8 }, () => new Path2D());
    W.bridgeRoads = new Path2D();
    W.lines = [];
    for (const [rank, ni, brg, c] of roads.r) {
      const pts = dec(c, q);
      addPoly(W.roads[rank], pts, false);
      if (brg) addPoly(W.bridgeRoads, pts, false);
      if (opts.keepLines) W.lines.push({ n: ni >= 0 ? roads.names[ni] : null, rank, bridge: !!brg, pts });
    }
    if (opts.keepLines && !cache["lines"]) cache["lines"] = Promise.resolve(W.lines);
    return W;
  }

  async function loadBuildings(W) {
    if (W.bld) return W.bld;
    const B = await getJSON("buildings.json");
    const byK = {};
    const cent = new Float32Array(B.p.length * 2);
    B.p.forEach((e, i) => {
      const pts = dec(e, W.q);
      const k = B.k[i];
      const p = byK[k] || (byK[k] = new Path2D());
      addPoly(p, pts, true);
      let sx = 0, sy = 0;
      for (let j = 0; j < pts.length; j += 2) { sx += pts[j]; sy += pts[j + 1]; }
      cent[i * 2] = sx / (pts.length / 2); cent[i * 2 + 1] = sy / (pts.length / 2);
    });
    W.bld = { raw: B, byK, cent };
    return W.bld;
  }

  /* ---------------------------------------------------------------- */
  /* Interactive 2D map                                                */
  /* ---------------------------------------------------------------- */
  /* distance from (px, py) to a flat x,y polyline, and the nearest point on it */
  function nearOnLine(px, py, pts) {
    let best = null;
    for (let i = 0; i + 3 < pts.length; i += 2) {
      const ax = pts[i], ay = pts[i + 1], dx = pts[i + 2] - ax, dy = pts[i + 3] - ay, L = dx * dx + dy * dy;
      const t = L ? Math.max(0, Math.min(1, ((px - ax) * dx + (py - ay) * dy) / L)) : 0;
      const x = ax + t * dx, y = ay + t * dy, d = Math.hypot(px - x, py - y);
      if (!best || d < best.d) best = { d, x, y };
    }
    if (!best && pts.length >= 2) best = { d: Math.hypot(px - pts[0], py - pts[1]), x: pts[0], y: pts[1] };
    return best || { d: Infinity, x: px, y: py };
  }
  const lineDist = (px, py, pts) => nearOnLine(px, py, pts).d;

  class Map2D {
    constructor(canvas, W, opts = {}) {
      this.c = canvas; this.ctx = canvas.getContext("2d");
      this.W = W; this.opts = opts;
      this.scale = 0.05; this.cx = -3300; this.cy = 0; // centre on downtown New Ken
      this.places = []; this.streets = []; this.streetsByRank = [];
      this.filter = new Set(Object.keys(GROUP_COLORS));
      this.layers = { buildings: true, relief: true, towns: true, places: true, incidents: false, crashes: false, pets: false };
      this.pets = []; this.pickMode = null;
      this.incidents = []; this.incVisible = () => true; this.crashes = [];
      this.sel = null; this.hover = null;
      this.focus = null;        // {x, y}: label the streets around this point
      this.here = null;         // {x, y}: a "you are here" / corner ring
      this.hl = null;           // the highlighted street {name, town, lines, path}
      this.hold = !!opts.hold;  // true: don't draw yet (an arrival view is still being worked out)
      this.touched = false;     // the person has panned or zoomed (only then is ?at= written)
      this.drawnLabels = [];    // street names drawn as labels in the last frame
      this.petDrawn = new Map(); // post id -> dots drawn in the last frame
      this.townBoxes = [];
      this.pointers = new Map();
      this.dirty = true;
      this._bind();
      this.resize();
      const loop = () => { if (this.dirty && !this.hold) { this.dirty = false; this.draw(); } this.raf = requestAnimationFrame(loop); };
      loop();
      new ResizeObserver(() => this.resize()).observe(canvas);
      this.themeMQ = matchMedia("(prefers-color-scheme: dark)");
      this.themeMQ.addEventListener?.("change", () => this.retheme());
      new MutationObserver(() => this.retheme()).observe(document.documentElement, { attributes: true, attributeFilter: ["data-theme"] });
    }
    retheme() { this.relief = null; this.dirty = true; }
    isDark() {
      const g = css("--map-bg");
      const m = g.match(/#(..)(..)(..)/);
      return m ? (parseInt(m[1], 16) + parseInt(m[2], 16) + parseInt(m[3], 16)) < 200 : false;
    }
    resize() {
      const r = this.c.getBoundingClientRect();
      this.dpr = Math.min(2, window.devicePixelRatio || 1);
      this.c.width = Math.max(1, Math.round(r.width * this.dpr));
      this.c.height = Math.max(1, Math.round(r.height * this.dpr));
      this.w = r.width; this.h = r.height;
      if (!this.fitted && this.w > 0) { this.fitted = true; this.fitView(); }
      else this.clampView();
      this.dirty = true;
    }

    /* ---------- the view: centre (cx, cy) in metres and scale in px per metre ---------- */
    view() { return { x: this.cx, y: this.cy, s: this.scale }; }
    /* the scale that fits the whole ZIP (the Whole ZIP button's view) */
    zipScale() {
      const b = this.W.meta.bounds, pad = 300;
      return Math.min(this.w / (b[2] - b[0] - 2 * pad), this.h / (b[3] - b[1] - 2 * pad));
    }
    /* the centre stays within the ZIP's bounds plus 1 km; zooming out stops at 0.8 x the whole-ZIP fit */
    clampView() {
      const b = this.W.meta && this.W.meta.bounds;
      if (!b || !(this.w > 0)) return;
      const lo = 0.8 * this.zipScale();
      this.scale = Math.max(lo, Math.min(12, this.scale));
      this.cx = Math.max(b[0] - 1000, Math.min(b[2] + 1000, this.cx));
      this.cy = Math.max(b[1] - 1000, Math.min(b[3] + 1000, this.cy));
    }
    _viewChanged() {
      this.dirty = true;
      if (!this.touched || !this.opts.onView) return;
      clearTimeout(this._vt);
      this._vt = setTimeout(() => this.opts.onView(this.view()), 300);
    }
    setView(x, y, s) {
      this._fly = null;
      this.cx = x; this.cy = y; if (s) this.scale = s;
      this.clampView();
      this._viewChanged();
    }
    /* inset {top, bottom, left, right} in px keeps the box clear of panels or a bottom sheet */
    fitView(b, inset = {}, maxScale = 12) {
      this._fly = null;
      b = b || this.opts.initial || [-6500, -3200, 1200, 3600];
      const { top = 0, bottom = 0, left = 0, right = 0 } = inset;
      const hh = Math.max(60, this.h - top - bottom), ww = Math.max(60, this.w - left - right);
      const s = Math.min(maxScale, ww / (b[2] - b[0]), hh / (b[3] - b[1]));
      this.scale = s; this.cx = (b[0] + b[2]) / 2 - (left - right) / 2 / s; this.cy = (b[1] + b[3]) / 2 + (bottom - top) / 2 / s;
      this.clampView();
      this._viewChanged();
    }
    toScreen(x, y) { return [(x - this.cx) * this.scale + this.w / 2, (y - this.cy) * this.scale + this.h / 2]; }
    toWorld(sx, sy) { return [(sx - this.w / 2) / this.scale + this.cx, (sy - this.h / 2) / this.scale + this.cy]; }
    zoomAt(f, sx, sy) {
      this._fly = null;
      const [wx, wy] = this.toWorld(sx, sy);
      this.scale = Math.max(0.012, Math.min(12, this.scale * f));
      this.clampView();
      const [nx, ny] = this.toWorld(sx, sy);
      this.cx += wx - nx; this.cy += wy - ny;
      this.clampView();
      this._viewChanged();
    }
    /* offsetY (px): how far above the middle the target sits (0.15 * h puts it at 35% of the height);
       offsetX (px): how far right of the middle */
    flyTo(x, y, scale, { offsetX = 0, offsetY = 0 } = {}) {
      const s0 = this.scale, x0 = this.cx, y0 = this.cy, s1 = scale || Math.max(this.scale, 2.2);
      const ty = y + offsetY / s1, tx = x - offsetX / s1;
      const t0 = performance.now(), dur = matchMedia("(prefers-reduced-motion: reduce)").matches ? 1 : 900;
      const id = this._fly = {};
      const step = (t) => {
        if (this._fly !== id) return;
        const k = Math.min(1, (t - t0) / dur), e = k < .5 ? 4 * k * k * k : 1 - Math.pow(-2 * k + 2, 3) / 2;
        this.cx = x0 + (tx - x0) * e; this.cy = y0 + (ty - y0) * e;
        this.scale = Math.exp(Math.log(s0) + (Math.log(s1) - Math.log(s0)) * e);
        this.clampView();
        this.dirty = true;
        if (k < 1) requestAnimationFrame(step); else { this._fly = null; this._viewChanged(); }
      };
      requestAnimationFrame(step);
    }

    /* ---------- a street in --map-focus: every line with that name (inside the town, when given) ---------- */
    streetLines(name, town) {
      const tp = town ? (this.W.towns || []).find((t) => t.n === town) : null;
      const inTown = (l) => {
        if (!tp) return true;
        const n = l.pts.length / 2, a = Math.floor((n - 1) / 2), b = Math.ceil((n - 1) / 2);
        const mx = (l.pts[a * 2] + l.pts[b * 2]) / 2, my = (l.pts[a * 2 + 1] + l.pts[b * 2 + 1]) / 2;
        this.ctx.save(); this.ctx.setTransform(1, 0, 0, 1, 0, 0);
        const ok = this.ctx.isPointInPath(tp.p, mx, my);
        this.ctx.restore();
        return ok;
      };
      return (this.W.lines || []).filter((l) => l.n === name && inTown(l));
    }
    highlightStreet(name, town) {
      if (!name) { this.hl = null; this.dirty = true; return 0; }
      let lines = this.streetLines(name, town);
      if (!lines.length && town) lines = this.streetLines(name);
      const path = new Path2D();
      lines.forEach((l) => addPoly(path, l.pts, false));
      this.hl = { name, town: town || null, lines, path };
      this.dirty = true;
      return lines.length;
    }
    /* fit the highlighted street (or every line named `name`) plus 80 m */
    fitStreet(name, inset = {}) {
      const lines = this.hl && (!name || this.hl.name === name) ? this.hl.lines : this.streetLines(name);
      if (!lines.length) return false;
      let x0 = Infinity, y0 = Infinity, x1 = -Infinity, y1 = -Infinity;
      for (const l of lines) for (let i = 0; i < l.pts.length; i += 2) {
        x0 = Math.min(x0, l.pts[i]); x1 = Math.max(x1, l.pts[i]); y0 = Math.min(y0, l.pts[i + 1]); y1 = Math.max(y1, l.pts[i + 1]);
      }
      this.fitView([x0 - 80, y0 - 80, x1 + 80, y1 + 80], inset, 3);
      return true;
    }

    _bind() {
      const c = this.c;
      const touch = () => { this.touched = true; this._fly = null; };
      c.addEventListener("wheel", (e) => {
        e.preventDefault(); touch();
        const r = c.getBoundingClientRect();
        this.zoomAt(Math.exp(-e.deltaY * (e.ctrlKey ? 0.01 : 0.0022)), e.clientX - r.left, e.clientY - r.top);
      }, { passive: false });
      c.addEventListener("pointerdown", (e) => {
        c.setPointerCapture(e.pointerId);
        this.pointers.set(e.pointerId, { x: e.clientX, y: e.clientY });
        this.moved = 0; c.classList.add("drag");
      });
      c.addEventListener("pointermove", (e) => {
        const r = c.getBoundingClientRect();
        const p = this.pointers.get(e.pointerId);
        if (!p) { this._hover(e.clientX - r.left, e.clientY - r.top); return; }
        if (this.pointers.size === 1) {
          const dx = e.clientX - p.x, dy = e.clientY - p.y;
          if (dx || dy) touch();
          this.cx -= dx / this.scale; this.cy -= dy / this.scale;
          this.clampView();
          this.moved += Math.abs(dx) + Math.abs(dy);
          this.dirty = true;
        } else if (this.pointers.size === 2) {
          touch();
          const [a, b] = [...this.pointers.values()];
          const other = a === p ? b : a;
          const d0 = Math.hypot(p.x - other.x, p.y - other.y);
          const d1 = Math.hypot(e.clientX - other.x, e.clientY - other.y);
          if (d0 > 0) this.zoomAt(d1 / d0, (e.clientX + other.x) / 2 - r.left, (e.clientY + other.y) / 2 - r.top);
          this.moved += 10;
        }
        p.x = e.clientX; p.y = e.clientY;
      });
      const up = (e) => {
        const r = c.getBoundingClientRect();
        if (this.pointers.has(e.pointerId) && this.pointers.size === 1 && this.moved < 6 && e.type === "pointerup") {
          this._click(e.clientX - r.left, e.clientY - r.top);
        }
        this.pointers.delete(e.pointerId);
        if (!this.pointers.size) { c.classList.remove("drag"); if (this.moved >= 6) this._viewChanged(); }
      };
      c.addEventListener("pointerup", up);
      c.addEventListener("pointercancel", up);
      c.addEventListener("dblclick", (e) => {
        touch();
        const r = c.getBoundingClientRect();
        this.zoomAt(2, e.clientX - r.left, e.clientY - r.top);
      });
      c.tabIndex = 0;
      c.addEventListener("keydown", (e) => {
        const k = e.key, step = 80 / this.scale;
        if (k === "+" || k === "=") this.zoomAt(1.4, this.w / 2, this.h / 2);
        else if (k === "-") this.zoomAt(1 / 1.4, this.w / 2, this.h / 2);
        else if (k === "ArrowLeft") this.cx -= step;
        else if (k === "ArrowRight") this.cx += step;
        else if (k === "ArrowUp") this.cy -= step;
        else if (k === "ArrowDown") this.cy += step;
        else return;
        e.preventDefault(); touch(); this.clampView(); this._viewChanged();
      });
    }
    /* incidents and crashes take every tap; with only pets on, a tap that misses a pet falls through to places */
    _pick(sx, sy) {
      const L = this.layers;
      if (L.incidents || L.crashes || L.pets) {
        let best = null, bd = 16 * 16;
        if (L.pets) for (const p of this.pets) {
          if (typeof p.x !== "number" || p.prec === "street") continue;
          const [x, y] = this.toScreen(p.x, p.y);
          const d = (x - sx) ** 2 + (y - sy) ** 2;
          if (d < bd) { bd = d; best = p; }
        }
        if (L.crashes) for (const p of this.crashes) {
          const [x, y] = this.toScreen(p.x, p.y);
          const d = (x - sx) ** 2 + (y - sy) ** 2;
          if (d < bd) { bd = d; best = p; }
        }
        if (L.incidents) {
          for (const p of this.incidents) {
            if (!this.incVisible(p)) continue;
            const [x, y] = this._incPos(p);
            const d = (x - sx) ** 2 + (y - sy) ** 2;
            if (d < bd) { bd = d; best = p; }
          }
        }
        if (best || L.incidents || L.crashes) return best;
      }
      if (!L.places) return null;
      let best = null, bd = 14 * 14;
      for (const p of this.places) {
        if (!this.filter.has(p.g)) continue;
        const [x, y] = this.toScreen(p.x, p.y);
        const d = (x - sx) ** 2 + (y - sy) ** 2;
        if (d < bd) { bd = d; best = p; }
      }
      return best;
    }
    _hover(sx, sy) {
      const p = this._pick(sx, sy);
      if (p !== this.hover) { this.hover = p; this.c.style.cursor = p ? "pointer" : ""; this.dirty = true; }
    }
    _click(sx, sy) {
      if (this.pickMode) { const [wx, wy] = this.toWorld(sx, sy); const f = this.pickMode; this.pickMode = null; this.c.style.cursor = ""; f(wx, wy); this.dirty = true; return; }
      const p = this._pick(sx, sy);
      this.select(p);
    }
    select(p) { this.sel = p; this.dirty = true; this.opts.onSelect?.(p); }
    /* places are dimmed only under incidents or crashes; pets alone leave them readable */
    _dimPlaces() { return this.layers.incidents || this.layers.crashes; }

    draw() {
      const { ctx, W, dpr } = this;
      const s = this.scale;
      const dark = this.isDark();
      ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
      ctx.fillStyle = css("--map-bg");
      ctx.fillRect(0, 0, this.w, this.h);
      // world transform
      ctx.setTransform(dpr * s, 0, 0, dpr * s, dpr * (this.w / 2 - this.cx * s), dpr * (this.h / 2 - this.cy * s));
      const px = 1 / s; // one screen pixel in world units
      ctx.lineJoin = "round"; ctx.lineCap = "round";

      ctx.fillStyle = css("--map-land");
      ctx.fill(W.zip);
      ctx.fillStyle = css("--map-green");
      ctx.globalAlpha = dark ? 1 : .8;
      ctx.fill(W.green);
      ctx.globalAlpha = 1;
      const useCol = dark
        ? { park: "#173524", golf: "#1a3a25", cemetery: "#1b2a22", school: "#1f2a38", industrial: "#262229", retail: "#2a2320", farm: "#22281a" }
        : { park: "#bfd8b8", golf: "#c7e0bd", cemetery: "#cdd6c5", school: "#d9dfe8", industrial: "#ddd6dc", retail: "#ecdcd0", farm: "#e3e4c9" };
      for (const k in W.use) { ctx.fillStyle = useCol[k] || useCol.park; ctx.fill(W.use[k]); }

      // relief
      if (this.layers.relief && this.terrain) {
        if (!this.relief) this.relief = hillshade(this.terrain, dark);
        const T = this.terrain;
        ctx.imageSmoothingEnabled = true;
        ctx.globalAlpha = dark ? .9 : .55;
        ctx.drawImage(this.relief, T.x0 - T.cell / 2, T.y0 - T.cell / 2, T.w * T.cell, T.h * T.cell);
        ctx.globalAlpha = 1;
      }

      // water
      ctx.fillStyle = dark ? "#123150" : "#9fc2e2";
      ctx.fill(W.water);
      ctx.strokeStyle = dark ? "#1d4a78" : "#86b0d8";
      [1.2, 2.5, 5].forEach((w, i) => { ctx.lineWidth = Math.max(w * px, w * .6); ctx.stroke(W.streams[i]); });

      // town lines
      if (this.layers.towns) {
        ctx.setLineDash([6 * px, 5 * px]);
        ctx.lineWidth = 1.2 * px;
        ctx.strokeStyle = dark ? "rgba(200,210,220,.28)" : "rgba(40,50,60,.3)";
        W.towns.forEach((t) => ctx.stroke(t.p));
        ctx.setLineDash([]);
        ctx.lineWidth = 1.5 * px;
        ctx.strokeStyle = css("--boundary");
        ctx.setLineDash([6 * px, 4 * px]);
        ctx.stroke(W.zip);
        ctx.setLineDash([]);
      }

      // roads: casing then fill, minor to major
      const widthM = [16, 13, 11, 9, 7, 4.5, 3, 1.6];
      const minPx = [2.4, 2.0, 1.6, 1.2, .8, .55, .5, .5];
      const road = css("--map-road"), major = css("--map-major"), edge = css("--map-road-edge");
      const majorEdge = css("--map-major-edge"), secondary = css("--map-secondary");
      for (let r = 7; r >= 0; r--) {
        if (r >= 6 && s < 0.35) continue;
        if (r === 5 && s < 0.12) continue;
        const w = Math.max(widthM[r], minPx[r] * px);
        if (r <= 1) { ctx.strokeStyle = majorEdge; ctx.lineWidth = w + 2 * px; ctx.stroke(W.roads[r]); }
        else if (s > 0.6 && r < 7) { ctx.strokeStyle = edge; ctx.lineWidth = w + 2 * px; ctx.stroke(W.roads[r]); }
        ctx.strokeStyle = r <= 1 ? major : (r === 2 ? secondary : (r === 7 ? (dark ? "#4a5560" : "#aab3ba") : road));
        if (r === 7) ctx.setLineDash([2 * px, 2 * px]);
        ctx.lineWidth = w;
        ctx.stroke(W.roads[r]);
        ctx.setLineDash([]);
      }
      // rail
      ctx.strokeStyle = dark ? "#5b6670" : "#7d8791";
      ctx.lineWidth = Math.max(2, 1.4 * px);
      ctx.setLineDash([6 * px, 4 * px]);
      ctx.stroke(W.rail);
      ctx.setLineDash([]);

      // buildings
      if (this.layers.buildings && this.bld && s > 0.18) {
        const cols = dark
          ? ["#27313a", "#2b343d", "#3a3f4f", "#3b3530", "#233449", "#35294a", "#2b3452", "#4a2a33", "#232a31"]
          : ["#c2c6cb", "#bfc4c9", "#b5b0c2", "#c4b7ab", "#a9bcd1", "#bcaed3", "#aab4d6", "#d4a9b3", "#cdd1d4"];
        ctx.globalAlpha = Math.min(1, (s - 0.18) * 4);
        for (const k in this.bld.byK) { ctx.fillStyle = cols[k] || cols[0]; ctx.fill(this.bld.byK[k]); }
        if (s > 1.2) { ctx.strokeStyle = dark ? "#11161b" : "#9aa1a8"; ctx.lineWidth = .7 * px; for (const k in this.bld.byK) ctx.stroke(this.bld.byK[k]); }
        ctx.globalAlpha = 1;
      }

      // the highlighted street, over the roads and buildings: 5 px of --map-focus on a halo
      if (this.hl && this.hl.lines.length) {
        ctx.strokeStyle = css("--map-halo"); ctx.lineWidth = 9 * px; ctx.stroke(this.hl.path);
        ctx.strokeStyle = css("--map-focus") || "#0b63c4"; ctx.lineWidth = 5 * px; ctx.stroke(this.hl.path);
      }

      // ---------- screen-space overlays ----------
      ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
      this._labels(ctx, dark);
      if (this.layers.places) {
        ctx.globalAlpha = this._dimPlaces() ? 0.18 : 1;
        this._pins(ctx);
        ctx.globalAlpha = 1;
        this._pinRings(ctx);
      }
      if (this.here) this._here(ctx);
      if (this.layers.crashes) this._crashes(ctx);
      this.petDrawn = new Map();
      if (this.layers.pets) this._pets(ctx);
      if (this.layers.incidents) this._incidents(ctx);
      this._scaleBar();
    }
    _text(ctx, t, x, y, font, color, halo) {
      ctx.font = font;
      ctx.lineWidth = 3.5; ctx.strokeStyle = halo; ctx.lineJoin = "round";
      ctx.strokeText(t, x, y);
      ctx.fillStyle = color;
      ctx.fillText(t, x, y);
    }
    _labels(ctx, dark) {
      const s = this.scale, lab = css("--map-label"), halo = css("--map-halo");
      ctx.textAlign = "center"; ctx.textBaseline = "middle";
      const boxes = [], drawn = [];
      const fits = (x, y, w, h) => {
        for (const b of boxes) if (x < b[0] + b[2] && x + w > b[0] && y < b[1] + b[3] && y + h > b[1]) return false;
        boxes.push([x, y, w, h]); return true;
      };
      // the streets around a focus point (a pet's pin, an incident, a corner) come first
      if (this.focus && s >= 0.8) this._focusLabels(ctx, fits, drawn, lab, halo);
      // towns
      this.townBoxes = [];
      for (const l of this.W.base.labels) {
        if (l.k !== "town") continue;
        const [x, y] = this.toScreen(l.x, l.y);
        const f = this.w < 700 ? 14 : s < .3 ? 20 : 14;
        if (s > 1.5) continue;
        ctx.font = `800 ${f}px ${css("--f-display")}`;
        const w = ctx.measureText(l.n.toUpperCase()).width;
        if (fits(x - w / 2, y - f / 2, w, f)) {
          this._text(ctx, l.n.toUpperCase(), x, y, ctx.font, lab, halo);
          this.townBoxes.push([x - w / 2 - 4, y - f / 2 - 3, w + 8, f + 6]);
        }
      }
      // streets (by rank, visible at zoom)
      if (this.streetsByRank.length && s > 0.09) {
        const maxRank = s > 1.2 ? 5 : s > 0.5 ? 4 : s > 0.25 ? 3 : 2;
        const fz = s > 1.2 ? 12 : 11;
        const font = `500 ${fz}px ${css("--f-body")}`;
        ctx.font = font;
        for (const st of this.streetsByRank) {
          if (st.r > maxRank) continue;
          if (drawn.includes(st.n)) continue;
          const [x, y] = this.toScreen(st.x, st.y);
          if (x < -50 || y < -20 || x > this.w + 50 || y > this.h + 20) continue;
          const t = st.ref && st.ref.length && st.r <= 1 ? st.n + " · " + st.ref[0] : st.n;
          const w = ctx.measureText(t).width;
          if (!fits(x - w / 2 - 4, y - fz / 2 - 2, w + 8, fz + 4)) continue;
          this._text(ctx, t, x, y, font, css("--map-street-label"), halo);
          drawn.push(st.n);
        }
      }
      // parks & named land use
      if (s > 0.25) {
        ctx.font = `italic 500 11px ${css("--f-body")}`;
        for (const l of this.W.base.labels) {
          if (l.k === "town") continue;
          const [x, y] = this.toScreen(l.x, l.y);
          if (x < 0 || y < 0 || x > this.w || y > this.h) continue;
          const w = ctx.measureText(l.n).width;
          if (!fits(x - w / 2, y - 7, w, 14)) continue;
          this._text(ctx, l.n, x, y, ctx.font, css("--map-park-label"), halo);
        }
      }
      this.labelBoxes = boxes;
      this.drawnLabels = drawn;
    }
    /* up to 4 distinct named lines within 150 m of the focus, each labelled at its point nearest the focus that
       leaves the pin itself clear */
    _focusLabels(ctx, fits, drawn, lab, halo) {
      const f = this.focus, lines = this.W.lines || [];
      if (!lines.length) return;
      const near = new Map();
      for (const l of lines) {
        if (!l.n) continue;
        const d = lineDist(f.x, f.y, l.pts);
        if (d <= 150 && (!near.has(l.n) || d < near.get(l.n))) near.set(l.n, d);
      }
      const names = [...near.entries()].sort((a, b) => a[1] - b[1]).slice(0, 4).map((e) => e[0]);
      const [fx, fy] = this.toScreen(f.x, f.y);
      fits(fx - 16, fy - 16, 32, 32); // keep the pin clear
      const fz = 12.5, font = `700 ${fz}px ${css("--f-body")}`, step = 12 / this.scale;
      ctx.font = font;
      for (const n of names) {
        const cands = [];
        for (const l of lines) {
          if (l.n !== n) continue;
          for (let i = 0; i + 1 < l.pts.length; i += 2) {
            const ax = l.pts[i], ay = l.pts[i + 1];
            cands.push([ax, ay]);
            if (i + 3 < l.pts.length) {
              const bx = l.pts[i + 2], by = l.pts[i + 3], k = Math.floor(Math.hypot(bx - ax, by - ay) / step);
              for (let j = 1; j < k; j++) cands.push([ax + (bx - ax) * j / k, ay + (by - ay) * j / k]);
            }
          }
        }
        cands.sort((a, b) => Math.hypot(a[0] - f.x, a[1] - f.y) - Math.hypot(b[0] - f.x, b[1] - f.y));
        const w = ctx.measureText(n).width;
        for (const [x, y] of cands) {
          const [sx, sy] = this.toScreen(x, y);
          if (Math.hypot(sx - fx, sy - fy) < 34 + w / 2) continue;
          if (sx - w / 2 < 4 || sx + w / 2 > this.w - 4 || sy < 10 || sy > this.h - 10) continue;
          if (Math.hypot(sx - fx, sy - fy) > 260) break;
          if (fits(sx - w / 2 - 4, sy - fz / 2 - 3, w + 8, fz + 6)) {
            this._text(ctx, n, sx, sy, font, lab, halo);
            drawn.push(n);
            break;
          }
        }
      }
    }
    _pins(ctx) {
      const s = this.scale;
      const r = s < .15 ? 2.2 : s < .6 ? 3.2 : s < 2 ? 4.5 : 6;
      const halo = css("--map-halo");
      const under = s < 0.3 ? this.townBoxes : [];
      for (const p of this.places) {
        if (!this.filter.has(p.g)) continue;
        const [x, y] = this.toScreen(p.x, p.y);
        if (x < -10 || y < -10 || x > this.w + 10 || y > this.h + 10) continue;
        if (under.length && under.some((b) => x > b[0] && x < b[0] + b[2] && y > b[1] && y < b[1] + b[3])) continue;
        ctx.beginPath(); ctx.arc(x, y, r, 0, 7);
        ctx.fillStyle = GROUP_COLORS[p.g]; ctx.fill();
        ctx.lineWidth = 1.2; ctx.strokeStyle = halo; ctx.stroke();
      }
      // names at close zoom
      if (s > 1.6 && !this._dimPlaces()) {
        ctx.textAlign = "left"; ctx.textBaseline = "middle";
        const font = `600 11.5px ${css("--f-body")}`;
        ctx.font = font;
        const boxes = this.labelBoxes || [];
        for (const p of this.places) {
          if (!this.filter.has(p.g)) continue;
          const [x, y] = this.toScreen(p.x, p.y);
          if (x < 0 || y < 0 || x > this.w || y > this.h) continue;
          const w = ctx.measureText(p.n).width;
          const bx = x + r + 3, by = y - 7;
          if (boxes.some((b) => bx < b[0] + b[2] && bx + w > b[0] && by < b[1] + b[3] && by + 14 > b[1])) continue;
          boxes.push([bx, by, w, 14]);
          this._text(ctx, p.n, bx, y, font, css("--map-label"), halo);
        }
      }
    }
    _pinRings(ctx) {
      const s = this.scale, r = s < .15 ? 2.2 : s < .6 ? 3.2 : s < 2 ? 4.5 : 6;
      for (const p of [this.hover, this.sel]) {
        if (!p || !p.g || !this.filter.has(p.g) || p.yr != null || (p.d && p.k) || p.status) continue;
        const [x, y] = this.toScreen(p.x, p.y);
        ctx.beginPath(); ctx.arc(x, y, r + 5, 0, 7);
        ctx.lineWidth = 4.5; ctx.strokeStyle = css("--map-bg"); ctx.stroke();
        ctx.lineWidth = 2.5; ctx.strokeStyle = css("--here"); ctx.stroke();
      }
    }
    /* a corner or "my location": an open ring with a dot, in --here */
    _here(ctx) {
      const [x, y] = this.toScreen(this.here.x, this.here.y);
      if (x < -20 || y < -20 || x > this.w + 20 || y > this.h + 20) return;
      ctx.beginPath(); ctx.arc(x, y, 11, 0, 7);
      ctx.lineWidth = 5; ctx.strokeStyle = css("--map-halo"); ctx.stroke();
      ctx.lineWidth = 2.5; ctx.strokeStyle = css("--here"); ctx.stroke();
      ctx.beginPath(); ctx.arc(x, y, 3.5, 0, 7); ctx.fillStyle = css("--here"); ctx.fill();
    }
    _scaleBar() {
      if (!this.opts.scaleEl) return;
      const targetPx = 110, m = targetPx / this.scale;
      const nice = [10, 20, 50, 100, 200, 500, 1000, 2000, 5000, 10000];
      const v = nice.find((n) => n >= m * 0.6) || 10000;
      const px = v * this.scale;
      const ft = v * 3.28084;
      this.opts.scaleEl.innerHTML = `<span>${v >= 1000 ? v / 1000 + " km" : v + " m"} · ${ft >= 5280 ? (ft / 5280).toFixed(1) + " mi" : Math.round(ft) + " ft"}</span><i style="width:${px.toFixed(0)}px"></i>`;
    }
    /* crime & police incidents: circle = reported incident, diamond = police-involved,
       dashed halo = located to the street only (approximate) */
    _incR() { const s = this.scale; return s < .15 ? 4 : s < .6 ? 5 : 6.5; }
    _incPos(p) {
      const [x, y] = this.toScreen(p.x, p.y);
      if (!p._n || p._n < 2) return [x, y];
      const r = this._incR() * 2.4, a = (p._i / p._n) * Math.PI * 2 - Math.PI / 2;
      return [x + Math.cos(a) * r, y + Math.sin(a) * r];
    }
    _incidents(ctx) {
      const r = this._incR();
      const halo = css("--map-halo"), ground = css("--map-bg");
      const col = { violent: css("--inc-violent"), property: css("--inc-property"), police: css("--inc-police") };
      const shape = (x, y, rr, pi) => {
        ctx.beginPath();
        if (pi) { ctx.moveTo(x, y - rr * 1.3); ctx.lineTo(x + rr * 1.3, y); ctx.lineTo(x, y + rr * 1.3); ctx.lineTo(x - rr * 1.3, y); ctx.closePath(); }
        else ctx.arc(x, y, rr, 0, 7);
      };
      for (const p of this.incidents) {
        if (!this.incVisible(p)) continue;
        const [x, y] = this._incPos(p);
        if (x < -20 || y < -20 || x > this.w + 20 || y > this.h + 20) continue;
        if (p.p === "street") {
          ctx.setLineDash([2, 2]); ctx.lineWidth = 1.2; ctx.strokeStyle = css("--muted");
          ctx.beginPath(); ctx.arc(x, y, r + 5, 0, 7); ctx.stroke(); ctx.setLineDash([]);
        }
        shape(x, y, r, p.pi);
        ctx.lineWidth = 4; ctx.strokeStyle = ground; ctx.stroke();
        ctx.fillStyle = col[p.c] || col.police; ctx.fill();
        ctx.lineWidth = 1; ctx.strokeStyle = this.isDark() ? halo : "rgba(20,25,30,.65)"; ctx.stroke();
      }
      for (const p of [this.hover, this.sel]) {
        if (!p || p.g || p.yr != null || p.status || !p.k || !this.incVisible(p)) continue;
        const [x, y] = this._incPos(p);
        shape(x, y, r + 4, p.pi);
        ctx.lineWidth = 4.5; ctx.strokeStyle = ground; ctx.stroke();
        ctx.lineWidth = 2.5; ctx.strokeStyle = css("--here"); ctx.stroke();
      }
    }
    /* police-reported serious crashes: ink triangles, filled = fatal, hollow = serious injury */
    _crashes(ctx) {
      const r = this._incR() + 1, ink = css("--ink"), ground = css("--map-bg");
      const tri = (x, y, rr) => { ctx.beginPath(); ctx.moveTo(x, y - rr); ctx.lineTo(x + rr * 0.95, y + rr * 0.7); ctx.lineTo(x - rr * 0.95, y + rr * 0.7); ctx.closePath(); };
      for (const p of this.crashes) {
        const [x, y] = this.toScreen(p.x, p.y);
        if (x < -20 || y < -20 || x > this.w + 20 || y > this.h + 20) continue;
        tri(x, y, r);
        ctx.lineWidth = 4; ctx.strokeStyle = ground; ctx.stroke();
        if (p.f) { ctx.fillStyle = ink; ctx.fill(); }
        else { ctx.fillStyle = ground; ctx.fill(); ctx.lineWidth = 1.6; ctx.strokeStyle = ink; ctx.stroke(); }
      }
      for (const p of [this.hover, this.sel]) {
        if (!p || p.yr == null) continue;
        const [x, y] = this.toScreen(p.x, p.y);
        tri(x, y, r + 5); ctx.lineWidth = 4.5; ctx.strokeStyle = ground; ctx.stroke();
        ctx.lineWidth = 2.5; ctx.strokeStyle = css("--here"); ctx.stroke();
      }
    }
    setCrashes(list) { this.crashes = list; this.dirty = true; }
    /* lost & found pets: lost = filled pin, found = ring, spotted = small dot; the letter keeps it readable without color.
       A post that gives only a street gets no dot (its street is highlighted instead). */
    petPin(p) {
      if (!p || typeof p.x !== "number" || p.prec === "street") return null;
      const [x, y] = this.toScreen(p.x, p.y);
      return { x, y };
    }
    _pets(ctx) {
      const r = this._incR() + 2.5, ground = css("--map-bg");
      const col = { lost: css("--pet-lost"), found: css("--pet-found"), spotted: css("--pet-spotted") };
      for (const p of this.pets) {
        const pin = this.petPin(p);
        if (!pin) continue;
        const { x, y } = pin;
        if (x < -20 || y < -20 || x > this.w + 20 || y > this.h + 20) continue;
        const c = col[p.status] || col.spotted;
        ctx.beginPath(); ctx.arc(x, y, r, 0, 7);
        ctx.lineWidth = 4; ctx.strokeStyle = ground; ctx.stroke();
        if (p.status === "found") { ctx.fillStyle = ground; ctx.fill(); ctx.lineWidth = 2.5; ctx.strokeStyle = c; ctx.stroke(); }
        else { ctx.fillStyle = c; ctx.fill(); }
        ctx.fillStyle = p.status === "found" ? c : ground;
        ctx.font = `700 ${Math.round(r * 1.1)}px ${css("--f-body")}`;
        ctx.textAlign = "center"; ctx.textBaseline = "middle";
        ctx.fillText(p.status === "lost" ? "L" : p.status === "found" ? "F" : "S", x, y + 0.5);
        if (p.id) this.petDrawn.set(p.id, (this.petDrawn.get(p.id) || 0) + 1);
      }
      for (const p of [this.hover, this.sel]) {
        if (!p || !p.status) continue;
        const pin = this.petPin(p);
        if (!pin) continue;
        ctx.beginPath(); ctx.arc(pin.x, pin.y, r + 5, 0, 7); ctx.lineWidth = 4.5; ctx.strokeStyle = ground; ctx.stroke();
        ctx.lineWidth = 2.5; ctx.strokeStyle = css("--here"); ctx.stroke();
      }
    }
    setPets(list) { this.pets = list; this.dirty = true; }
    setIncidents(list) {
      const groups = new Map();
      for (const p of list) {
        const k = Math.round(p.x / 4) + "," + Math.round(p.y / 4);
        (groups.get(k) || groups.set(k, []).get(k)).push(p);
      }
      for (const g of groups.values()) g.forEach((p, i) => { p._i = i; p._n = g.length; });
      this.incidents = list; this.dirty = true;
    }
    setData(places, streets) {
      this.places = places; this.streets = streets;
      this.streetsByRank = [...streets].sort((a, b) => a.r - b.r || b.m - a.m);
      this.dirty = true;
    }
  }

  window.NK = { GROUP_COLORS, getJSON, getTerrain, loadLines, dec, addPoly, loadWorld, loadBuildings, Map2D, heightAt, css, hillshade, nearOnLine, lineDist };
})();
