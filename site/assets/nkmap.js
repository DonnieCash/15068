/* NK15068 map engine — draws the scraped 15068 dataset on a canvas.
   World units are metres on a local grid (x east, y south) centred on the ZIP. */
(function () {
  "use strict";

  const GROUP_COLORS = {
    eat: "#e0743a", shop: "#c9a227", health: "#d4455b", faith: "#8b6fc6",
    learn: "#3c8dbc", play: "#3f9a5b", civic: "#5c7cfa", culture: "#b0508f",
    auto: "#7a8a99", services: "#8c7b6b", stay: "#1aa39a",
  };

  const cache = {};
  function getJSON(name) {
    if (!cache[name]) cache[name] = fetch("data/" + name).then((r) => {
      if (!r.ok) throw new Error(name + " " + r.status);
      return r.json();
    });
    return cache[name];
  }
  function getTerrain(meta) {
    // heightmap PNG: elevation in decimetres = R*256 + G
    if (!cache.terrain) cache.terrain = fetch("data/terrain.png").then((r) => r.blob())
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
      });
    return cache.terrain;
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
      if (opts.keepLines) W.lines.push({ rank, pts, n: ni >= 0 ? roads.names[ni] : null });
    }
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
  class Map2D {
    constructor(canvas, W, opts = {}) {
      this.c = canvas; this.ctx = canvas.getContext("2d");
      this.W = W; this.opts = opts;
      this.scale = 0.05; this.cx = -3300; this.cy = 0; // centre on downtown New Ken
      this.places = []; this.streets = [];
      this.filter = new Set(Object.keys(GROUP_COLORS));
      this.layers = { buildings: true, relief: true, towns: true, places: true, incidents: false, crashes: false, pets: false };
      this.pets = []; this.pickMode = null;
      this.incidents = []; this.incVisible = () => true; this.crashes = [];
      this.sel = null; this.hover = null;
      this.pointers = new Map();
      this.dirty = true;
      this._bind();
      this.resize();
      const loop = () => { if (this.dirty) { this.dirty = false; this.draw(); } this.raf = requestAnimationFrame(loop); };
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
      this.dirty = true;
    }
    fitView(b) {
      b = b || this.opts.initial || [-6500, -3200, 1200, 3600];
      const s = Math.min(this.w / (b[2] - b[0]), this.h / (b[3] - b[1]));
      this.scale = s; this.cx = (b[0] + b[2]) / 2; this.cy = (b[1] + b[3]) / 2;
      this.dirty = true;
    }
    toScreen(x, y) { return [(x - this.cx) * this.scale + this.w / 2, (y - this.cy) * this.scale + this.h / 2]; }
    toWorld(sx, sy) { return [(sx - this.w / 2) / this.scale + this.cx, (sy - this.h / 2) / this.scale + this.cy]; }
    zoomAt(f, sx, sy) {
      const [wx, wy] = this.toWorld(sx, sy);
      this.scale = Math.max(0.012, Math.min(12, this.scale * f));
      const [nx, ny] = this.toWorld(sx, sy);
      this.cx += wx - nx; this.cy += wy - ny;
      this.dirty = true;
      this.opts.onView?.();
    }
    flyTo(x, y, scale) {
      const s0 = this.scale, x0 = this.cx, y0 = this.cy, s1 = scale || Math.max(this.scale, 2.2);
      const t0 = performance.now(), dur = matchMedia("(prefers-reduced-motion: reduce)").matches ? 1 : 900;
      const step = (t) => {
        const k = Math.min(1, (t - t0) / dur), e = k < .5 ? 4 * k * k * k : 1 - Math.pow(-2 * k + 2, 3) / 2;
        this.cx = x0 + (x - x0) * e; this.cy = y0 + (y - y0) * e;
        this.scale = Math.exp(Math.log(s0) + (Math.log(s1) - Math.log(s0)) * e);
        this.dirty = true;
        if (k < 1) requestAnimationFrame(step);
      };
      requestAnimationFrame(step);
    }
    _bind() {
      const c = this.c;
      c.addEventListener("wheel", (e) => {
        e.preventDefault();
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
          this.cx -= dx / this.scale; this.cy -= dy / this.scale;
          this.moved += Math.abs(dx) + Math.abs(dy);
          this.dirty = true;
        } else if (this.pointers.size === 2) {
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
        if (!this.pointers.size) { c.classList.remove("drag"); this.opts.onView?.(); }
      };
      c.addEventListener("pointerup", up);
      c.addEventListener("pointercancel", up);
      c.addEventListener("dblclick", (e) => {
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
        e.preventDefault(); this.dirty = true;
      });
    }
    _pick(sx, sy) {
      if (this.layers.incidents || this.layers.crashes || this.layers.pets) {
        let best = null, bd = 16 * 16;
        if (this.layers.pets) for (const p of this.pets) {
          if (typeof p.x !== "number") continue;
          const [x, y] = this.toScreen(p.x, p.y);
          const d = (x - sx) ** 2 + (y - sy) ** 2;
          if (d < bd) { bd = d; best = p; }
        }
        if (this.layers.crashes) for (const p of this.crashes) {
          const [x, y] = this.toScreen(p.x, p.y);
          const d = (x - sx) ** 2 + (y - sy) ** 2;
          if (d < bd) { bd = d; best = p; }
        }
        if (this.layers.incidents) {
          for (const p of this.incidents) {
            if (!this.incVisible(p)) continue;
            const [x, y] = this._incPos(p);
            const d = (x - sx) ** 2 + (y - sy) ** 2;
            if (d < bd) { bd = d; best = p; }
          }
        }
        return best;
      }
      if (!this.layers.places) return null;
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

      // ---------- screen-space overlays ----------
      ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
      this._labels(ctx, dark);
      if (this.layers.places) {
        ctx.globalAlpha = this.layers.incidents || this.layers.crashes || this.layers.pets ? 0.18 : 1;
        this._pins(ctx);
        ctx.globalAlpha = 1;
        this._pinRings(ctx);
      }
      if (this.layers.crashes) this._crashes(ctx);
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
      const boxes = [];
      const fits = (x, y, w, h) => {
        for (const b of boxes) if (x < b[0] + b[2] && x + w > b[0] && y < b[1] + b[3] && y + h > b[1]) return false;
        boxes.push([x, y, w, h]); return true;
      };
      // towns
      for (const l of this.W.base.labels) {
        if (l.k !== "town") continue;
        const [x, y] = this.toScreen(l.x, l.y);
        const f = s < .3 ? 20 : 14;
        if (s > 1.5) continue;
        ctx.font = `800 ${f}px ${css("--f-display")}`;
        const w = ctx.measureText(l.n.toUpperCase()).width;
        if (fits(x - w / 2, y - f / 2, w, f)) this._text(ctx, l.n.toUpperCase(), x, y, ctx.font, lab, halo);
      }
      // streets (by rank, visible at zoom)
      if (this.streets.length && s > 0.09) {
        const maxRank = s > 1.2 ? 5 : s > 0.5 ? 4 : s > 0.25 ? 3 : 2;
        const fz = s > 1.2 ? 12 : 11;
        const font = `500 ${fz}px ${css("--f-body")}`;
        ctx.font = font;
        for (const st of this.streetsByRank) {
          if (st.r > maxRank) continue;
          const [x, y] = this.toScreen(st.x, st.y);
          if (x < -50 || y < -20 || x > this.w + 50 || y > this.h + 20) continue;
          const t = st.ref && st.ref.length && st.r <= 1 ? st.n + " · " + st.ref[0] : st.n;
          const w = ctx.measureText(t).width;
          if (!fits(x - w / 2 - 4, y - fz / 2 - 2, w + 8, fz + 4)) continue;
          this._text(ctx, t, x, y, font, css("--map-street-label"), halo);
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
    }
    _pins(ctx) {
      const s = this.scale;
      const r = s < .15 ? 2.2 : s < .6 ? 3.2 : s < 2 ? 4.5 : 6;
      const halo = css("--map-halo");
      for (const p of this.places) {
        if (!this.filter.has(p.g)) continue;
        const [x, y] = this.toScreen(p.x, p.y);
        if (x < -10 || y < -10 || x > this.w + 10 || y > this.h + 10) continue;
        ctx.beginPath(); ctx.arc(x, y, r, 0, 7);
        ctx.fillStyle = GROUP_COLORS[p.g]; ctx.fill();
        ctx.lineWidth = 1.2; ctx.strokeStyle = halo; ctx.stroke();
      }
      // names at close zoom
      if (s > 1.6 && !this.layers.incidents && !this.layers.crashes && !this.layers.pets) {
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
        if (!p || p.g || p.yr != null || p.status || !this.incVisible(p)) continue;
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
    /* lost & found pets: lost = filled pin, found = ring, spotted = small dot; the letter keeps it readable without color */
    _pets(ctx) {
      const r = this._incR() + 2.5, ground = css("--map-bg");
      const col = { lost: css("--pet-lost"), found: css("--pet-found"), spotted: css("--pet-spotted") };
      for (const p of this.pets) {
        if (typeof p.x !== "number") continue;
        const [x, y] = this.toScreen(p.x, p.y);
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
      }
      for (const p of [this.hover, this.sel]) {
        if (!p || !p.status || typeof p.x !== "number") continue;
        const [x, y] = this.toScreen(p.x, p.y);
        ctx.beginPath(); ctx.arc(x, y, r + 5, 0, 7); ctx.lineWidth = 4.5; ctx.strokeStyle = ground; ctx.stroke();
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

  window.NK = { GROUP_COLORS, getJSON, getTerrain, dec, addPoly, loadWorld, loadBuildings, Map2D, heightAt, css, hillshade };
})();
