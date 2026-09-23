/* NK15068 3D — real terrain + extruded buildings, rendered with three.js (global THREE).
   Map3D: build(T, bld), setPlaces, flyTo, goTo(view) for the presets, project(x, y) for HTML labels,
   snapshot(scale) for "Save as image" (the drawing buffer is kept for it), opts.onFrame after each render. */
(function () {
  "use strict";
  const EX = 1.5;           // vertical exaggeration for the valley
  const { dec, addPoly, heightAt, css } = window.NK;

  function paintTexture(W, bld, T, size, dark) {
    const c = document.createElement("canvas");
    c.width = c.height = size;
    const ctx = c.getContext("2d");
    const x0 = T.x0, y0 = T.y0, ww = (T.w - 1) * T.cell, hh = (T.h - 1) * T.cell;
    const sx = size / ww, sy = size / hh;
    ctx.fillStyle = dark ? "#10161b" : "#dfe3dc";
    ctx.fillRect(0, 0, size, size);
    ctx.setTransform(sx, 0, 0, sy, -x0 * sx, -y0 * sy);
    ctx.lineJoin = ctx.lineCap = "round";
    ctx.fillStyle = dark ? "#132219" : "#c3d6bb";
    ctx.fill(W.green);
    const useCol = dark
      ? { park: "#18361f", golf: "#1a3a22", cemetery: "#1c2b22", school: "#1f2a38", industrial: "#29242c", retail: "#2c2521", farm: "#232a1b" }
      : { park: "#b5d3aa", golf: "#bfdcb3", cemetery: "#c8d3bf", school: "#d6dce6", industrial: "#dcd4da", retail: "#ead8ca", farm: "#e0e2c3" };
    for (const k in W.use) { ctx.fillStyle = useCol[k] || useCol.park; ctx.fill(W.use[k]); }
    // hillshade
    const hs = window.NK.hillshade(T, dark);
    ctx.globalAlpha = dark ? .7 : .45;
    ctx.drawImage(hs, x0 - T.cell / 2, y0 - T.cell / 2, T.w * T.cell, T.h * T.cell);
    ctx.globalAlpha = 1;
    ctx.fillStyle = dark ? "#0f2d4b" : "#8fb8dc";
    ctx.fill(W.water);
    ctx.strokeStyle = ctx.fillStyle;
    [2, 4, 7].forEach((w, i) => { ctx.lineWidth = w; ctx.stroke(W.streams[i]); });
    const widthM = [18, 14, 12, 10, 8, 5, 3, 2];
    for (let r = 7; r >= 0; r--) {
      ctx.strokeStyle = r <= 1 ? (dark ? "#ee8f45" : "#e79a55") : r === 2 ? (dark ? "#9c6a41" : "#f3c996") : (dark ? "#3b4650" : "#fbfbfb");
      ctx.lineWidth = widthM[r];
      ctx.stroke(W.roads[r]);
    }
    ctx.strokeStyle = dark ? "#58636d" : "#88929b";
    ctx.lineWidth = 3; ctx.stroke(W.rail);
    ctx.strokeStyle = dark ? "rgba(238,143,69,.8)" : "rgba(184,86,26,.8)";
    ctx.lineWidth = 10; ctx.stroke(W.zip);
    return c;
  }

  class Map3D {
    constructor(host, W, opts = {}) {
      this.host = host; this.W = W; this.opts = opts;
      this.yaw = -0.6; this.pitch = 0.62; this.dist = 3200;
      this.target = new THREE.Vector3(-3300, 0, 0);
      this.auto = !matchMedia("(prefers-reduced-motion: reduce)").matches;
      this.places = [];
      this.renderer = new THREE.WebGLRenderer({ antialias: true, powerPreference: "high-performance", preserveDrawingBuffer: true });
      this.renderer.setPixelRatio(Math.min(2, window.devicePixelRatio || 1));
      host.appendChild(this.renderer.domElement);
      this.scene = new THREE.Scene();
      this.camera = new THREE.PerspectiveCamera(42, 1, 5, 60000);
      this.sun = new THREE.DirectionalLight(0xffffff, 0.85);
      this.sun.position.set(-4000, 6000, -3000);
      this.hemi = new THREE.HemisphereLight(0xbfd6ee, 0x3a342c, 0.55);
      this.scene.add(this.sun, this.hemi, new THREE.AmbientLight(0xffffff, 0.15));
      this._bind();
      new ResizeObserver(() => this.resize()).observe(host);
      this.resize();
    }
    async build(T, bld) {
      this.T = T;
      const dark = document.documentElement.dataset.theme === "dark" ||
        (document.documentElement.dataset.theme !== "light" && matchMedia("(prefers-color-scheme: dark)").matches);
      this.dark = dark;
      const sky = dark ? 0x0b0f13 : 0xdfe6ec;
      this.scene.background = new THREE.Color(sky);
      this.scene.fog = new THREE.Fog(sky, 7000, 22000);

      // terrain
      const g = new THREE.PlaneGeometry((T.w - 1) * T.cell, (T.h - 1) * T.cell, T.w - 1, T.h - 1);
      g.rotateX(-Math.PI / 2);
      const pos = g.attributes.position;
      const cx = T.x0 + (T.w - 1) * T.cell / 2, cz = T.y0 + (T.h - 1) * T.cell / 2;
      for (let j = 0; j < T.h; j++) for (let i = 0; i < T.w; i++) {
        const k = j * T.w + i;
        pos.setXYZ(k, pos.getX(k) + cx, T.data[k] * EX, pos.getZ(k) + cz);
      }
      g.computeVertexNormals();
      const tex = new THREE.CanvasTexture(paintTexture(this.W, bld, T, 4096, dark));
      tex.anisotropy = this.renderer.capabilities.getMaxAnisotropy();
      tex.flipY = true;
      const terrain = new THREE.Mesh(g, new THREE.MeshLambertMaterial({ map: tex }));
      this.scene.add(terrain);
      this.terrainMesh = terrain;

      // buildings
      const B = bld.raw, q = this.W.q;
      const P = [], C = [];
      const col = new THREE.Color();
      const pal = dark
        ? [0x3a4652, 0x3c4854, 0x4b4d63, 0x544a40, 0x345070, 0x4f3d6b, 0x3c4a78, 0x6a3a46, 0x333b44]
        : [0xd9dde2, 0xd6dadf, 0xc9c3d8, 0xd9cbbd, 0xbcd0e6, 0xcfc0e6, 0xbdc7ea, 0xe8bcc6, 0xe2e5e8];
      for (let i = 0; i < B.p.length; i++) {
        const pts = dec(B.p[i], q);
        const n = pts.length / 2;
        if (n < 3) continue;
        let ground = Infinity;
        for (let j = 0; j < pts.length; j += 2) ground = Math.min(ground, heightAt(T, pts[j], pts[j + 1]));
        const y0 = ground * EX - 2, y1 = ground * EX + B.h[i] * 1.25;
        col.setHex(pal[B.k[i]] || pal[0]);
        for (let j = 0; j < n; j++) {
          const a = j * 2, b = ((j + 1) % n) * 2;
          const ax = pts[a], az = pts[a + 1], bx = pts[b], bz = pts[b + 1];
          P.push(ax, y0, az, bx, y0, bz, bx, y1, bz, ax, y0, az, bx, y1, bz, ax, y1, az);
          for (let t = 0; t < 6; t++) C.push(col.r * .82, col.g * .82, col.b * .82);
        }
        const contour = [];
        for (let j = 0; j < pts.length; j += 2) contour.push(new THREE.Vector2(pts[j], pts[j + 1]));
        const tris = THREE.ShapeUtils.triangulateShape(contour, []);
        for (const t of tris) for (const v of t) {
          P.push(pts[v * 2], y1, pts[v * 2 + 1]);
          C.push(col.r, col.g, col.b);
        }
      }
      const bg = new THREE.BufferGeometry();
      bg.setAttribute("position", new THREE.Float32BufferAttribute(P, 3));
      bg.setAttribute("color", new THREE.Float32BufferAttribute(C, 3));
      bg.computeVertexNormals();
      this.scene.add(new THREE.Mesh(bg, new THREE.MeshLambertMaterial({ vertexColors: true, side: THREE.DoubleSide })));
      this.target.y = heightAt(T, this.target.x, this.target.z) * EX;
      this.ready = true;
      this.loop();
    }
    setPlaces(places, colors) {
      if (!this.T) return;
      if (this.pinObj) this.scene.remove(this.pinObj);
      const P = [], C = [];
      const col = new THREE.Color();
      this.places = places;
      for (const p of places) {
        P.push(p.x, heightAt(this.T, p.x, p.y) * EX + 30, p.y);
        col.set(colors[p.g]); C.push(col.r, col.g, col.b);
      }
      const g = new THREE.BufferGeometry();
      g.setAttribute("position", new THREE.Float32BufferAttribute(P, 3));
      g.setAttribute("color", new THREE.Float32BufferAttribute(C, 3));
      if (!this.dotTex) {
        const c = document.createElement("canvas"); c.width = c.height = 64;
        const x = c.getContext("2d");
        x.beginPath(); x.arc(32, 32, 26, 0, 7); x.fillStyle = "#fff"; x.fill();
        x.lineWidth = 8; x.strokeStyle = "rgba(0,0,0,.55)"; x.stroke();
        this.dotTex = new THREE.CanvasTexture(c);
      }
      this.pinObj = new THREE.Points(g, new THREE.PointsMaterial({ size: 10, sizeAttenuation: false, vertexColors: true, map: this.dotTex, alphaTest: 0.5, transparent: true }));
      this.scene.add(this.pinObj);
    }
    flyTo(x, y) {
      this.auto = false;
      const t0 = performance.now(), from = this.target.clone(), d0 = this.dist;
      const to = new THREE.Vector3(x, heightAt(this.T, x, y) * EX, y);
      const step = (t) => {
        const k = Math.min(1, (t - t0) / 1100), e = k < .5 ? 4 * k * k * k : 1 - Math.pow(-2 * k + 2, 3) / 2;
        this.target.lerpVectors(from, to, e);
        this.dist = d0 + (650 - d0) * e;
        if (k < 1) requestAnimationFrame(step);
      };
      requestAnimationFrame(step);
    }
    /* animate to a view {x, y, dist, pitch, yaw}; any value left out stays */
    goTo(v, ms = 1400) {
      this.auto = false;
      const t0 = performance.now(), from = { t: this.target.clone(), dist: this.dist, pitch: this.pitch, yaw: this.yaw };
      const tx = v.x ?? this.target.x, tz = v.y ?? this.target.z;
      const to = new THREE.Vector3(tx, this.T ? heightAt(this.T, tx, tz) * EX : 0, tz);
      let dyaw = (v.yaw ?? this.yaw) - this.yaw;
      dyaw = Math.atan2(Math.sin(dyaw), Math.cos(dyaw)); // the short way round
      const dur = matchMedia("(prefers-reduced-motion: reduce)").matches ? 1 : ms;
      const id = this._go = {};
      const step = (t) => {
        if (this._go !== id) return;
        const k = Math.min(1, (t - t0) / dur), e = k < .5 ? 4 * k * k * k : 1 - Math.pow(-2 * k + 2, 3) / 2;
        this.target.lerpVectors(from.t, to, e);
        this.dist = Math.exp(Math.log(from.dist) + (Math.log(v.dist ?? from.dist) - Math.log(from.dist)) * e);
        this.pitch = from.pitch + ((v.pitch ?? from.pitch) - from.pitch) * e;
        this.yaw = from.yaw + dyaw * e;
        if (k < 1) requestAnimationFrame(step);
      };
      requestAnimationFrame(step);
    }
    /* screen position (CSS px in the host) of a ground point lifted by `lift` metres; visible = in front of the camera */
    project(x, y, lift = 0) {
      const h = this.T ? heightAt(this.T, x, y) * EX : 0;
      const v = new THREE.Vector3(x, h + lift, y).project(this.camera);
      const r = this.host.getBoundingClientRect();
      return { x: (v.x + 1) / 2 * r.width, y: (1 - v.y) / 2 * r.height, visible: v.z > -1 && v.z < 1 };
    }
    /* a PNG data URL of the current view drawn at `scale` device pixels per CSS pixel */
    snapshot(scale = 2) {
      const r = this.host.getBoundingClientRect(), prev = this.renderer.getPixelRatio();
      this.renderer.setPixelRatio(scale);
      this.renderer.setSize(r.width, r.height, false);
      this.renderer.render(this.scene, this.camera);
      const url = this.renderer.domElement.toDataURL("image/png");
      this.renderer.setPixelRatio(prev);
      this.renderer.setSize(r.width, r.height, false);
      this.renderer.render(this.scene, this.camera);
      return url;
    }
    resize() {
      const r = this.host.getBoundingClientRect();
      this.renderer.setSize(r.width, r.height, false);
      this.camera.aspect = r.width / Math.max(1, r.height);
      this.camera.updateProjectionMatrix();
    }
    _bind() {
      const el = this.renderer.domElement;
      const ptrs = new Map();
      let mode = null;
      el.addEventListener("contextmenu", (e) => e.preventDefault());
      el.addEventListener("pointerdown", (e) => {
        el.setPointerCapture(e.pointerId);
        this._go = null;
        ptrs.set(e.pointerId, { x: e.clientX, y: e.clientY, x0: e.clientX, y0: e.clientY });
        mode = (e.button === 2 || e.shiftKey) ? "pan" : "rot";
        this.auto = false;
      });
      el.addEventListener("pointermove", (e) => {
        const p = ptrs.get(e.pointerId);
        if (!p) return;
        const dx = e.clientX - p.x, dy = e.clientY - p.y;
        if (ptrs.size === 2) {
          const [a, b] = [...ptrs.values()];
          const o = a === p ? b : a;
          const d0 = Math.hypot(p.x - o.x, p.y - o.y), d1 = Math.hypot(e.clientX - o.x, e.clientY - o.y);
          if (d0) this.dist = Math.max(120, Math.min(26000, this.dist * d0 / d1));
          this._pan(dx / 2, dy / 2);
        } else if (mode === "pan") this._pan(dx, dy);
        else {
          this.yaw -= dx * 0.005;
          this.pitch = Math.max(0.12, Math.min(1.45, this.pitch + dy * 0.004));
        }
        p.x = e.clientX; p.y = e.clientY;
      });
      const up = (e) => {
        const p = ptrs.get(e.pointerId);
        if (p && ptrs.size === 1 && Math.hypot(e.clientX - p.x0, e.clientY - p.y0) < 5) this._click(e);
        ptrs.delete(e.pointerId);
      };
      el.addEventListener("pointerup", up);
      el.addEventListener("pointercancel", up);
      el.addEventListener("wheel", (e) => {
        e.preventDefault(); this.auto = false; this._go = null;
        this.dist = Math.max(120, Math.min(26000, this.dist * Math.exp(e.deltaY * 0.0012)));
      }, { passive: false });
    }
    _pan(dx, dy) {
      const k = this.dist / 900;
      const s = Math.sin(this.yaw), c = Math.cos(this.yaw);
      this.target.x += (-dx * c - dy * s) * k;
      this.target.z += (dx * s - dy * c) * k;
      if (this.T) this.target.y = heightAt(this.T, this.target.x, this.target.z) * EX;
    }
    _click(e) {
      if (!this.pinObj) return;
      const r = this.renderer.domElement.getBoundingClientRect();
      const m = new THREE.Vector2(((e.clientX - r.left) / r.width) * 2 - 1, -((e.clientY - r.top) / r.height) * 2 + 1);
      const rc = new THREE.Raycaster();
      rc.params.Points.threshold = this.dist / 90;
      rc.setFromCamera(m, this.camera);
      const hit = rc.intersectObject(this.pinObj)[0];
      this.opts.onSelect?.(hit ? this.places[hit.index] : null);
    }
    loop() {
      if (this.stopped) return;
      if (this.auto) this.yaw += 0.0009;
      const cp = Math.cos(this.pitch);
      this.camera.position.set(
        this.target.x + this.dist * cp * Math.sin(this.yaw),
        this.target.y + this.dist * Math.sin(this.pitch),
        this.target.z + this.dist * cp * Math.cos(this.yaw));
      this.camera.lookAt(this.target);
      if (this.scene.fog) { this.scene.fog.near = Math.max(7000, this.dist * 1.3); this.scene.fog.far = Math.max(22000, this.dist * 3); }
      if (this.renderer.domElement.isConnected && this.host.offsetParent !== null) {
        this.renderer.render(this.scene, this.camera);
        if (this.opts.onFrame) this.opts.onFrame(this);
      }
      requestAnimationFrame(() => this.loop());
    }
  }
  window.NK.Map3D = Map3D;
})();
