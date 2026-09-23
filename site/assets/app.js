/* NK15068 — page wiring */
(function () {
  "use strict";
  const { GROUP_COLORS, getJSON, getTerrain, loadWorld, loadBuildings, Map2D, dec, css } = window.NK;
  const $ = (s, r = document) => r.querySelector(s);
  const esc = (s) => String(s ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
  const fmt = (n) => Number(n).toLocaleString("en-US");
  const reduced = matchMedia("(prefers-reduced-motion: reduce)").matches;
  const host = (u) => { try { return new URL(u).hostname.replace(/^www\./, ""); } catch (e) { return "source"; } };
  const srcLink = (u) => u ? `<a class="src" href="${esc(u)}" target="_blank" rel="noopener">↗ ${esc(host(u))}</a>` : "";
  const DOWNTOWN = [-3350, -40];

  /* ---------------- theme toggle ---------------- */
  const root = document.documentElement;
  try { const t = localStorage.getItem("nk-theme"); if (t) root.dataset.theme = t; } catch (e) { /* storage unavailable */ }
  $("#ttheme").addEventListener("click", () => {
    const dark = root.dataset.theme ? root.dataset.theme === "dark" : matchMedia("(prefers-color-scheme: dark)").matches;
    root.dataset.theme = dark ? "light" : "dark";
    try { localStorage.setItem("nk-theme", root.dataset.theme); } catch (e) { /* ignore */ }
    if (map3d) rebuild3D();
    hero?.redraw();
  });

  /* ---------------- hero: the real road network drawing itself ---------------- */
  let hero = null;
  function startHero(W) {
    const c = $("#hero-canvas"), ctx = c.getContext("2d");
    const lines = W.lines.map((l) => {
      let d = Infinity;
      for (let i = 0; i < l.pts.length; i += 2) d = Math.min(d, Math.hypot(l.pts[i] - DOWNTOWN[0], l.pts[i + 1] - DOWNTOWN[1]));
      return { ...l, d };
    }).filter((l) => l.rank <= 5).sort((a, b) => a.d - b.d);
    let w, h, s, ox, oy, drawn = 0, t0 = null, raf;
    function view() {
      const r = c.getBoundingClientRect(), dpr = Math.min(2, devicePixelRatio || 1);
      w = r.width; h = r.height;
      c.width = w * dpr; c.height = h * dpr;
      s = Math.max(w / 9000, h / 7000);
      const shift = w > 800 ? w * 0.18 : 0;
      ox = w / 2 + shift - DOWNTOWN[0] * s; oy = h * 0.55 - DOWNTOWN[1] * s;
      ctx.setTransform(dpr * s, 0, 0, dpr * s, dpr * ox, dpr * oy);
      ctx.lineCap = ctx.lineJoin = "round";
    }
    function ground() {
      ctx.save(); ctx.setTransform(1, 0, 0, 1, 0, 0);
      ctx.fillStyle = css("--map-bg"); ctx.fillRect(0, 0, c.width, c.height); ctx.restore();
      ctx.fillStyle = css("--map-land"); ctx.fill(W.zip);
      ctx.fillStyle = css("--river-soft"); ctx.fill(W.water);
      ctx.lineWidth = 2.5 / s; ctx.strokeStyle = css("--ember"); ctx.globalAlpha = .5; ctx.stroke(W.zip); ctx.globalAlpha = 1;
    }
    function drawLine(l) {
      const major = l.rank <= 2;
      ctx.strokeStyle = major ? css("--ember") : css("--muted");
      ctx.globalAlpha = major ? .85 : (l.rank >= 5 ? .22 : .42);
      ctx.lineWidth = (major ? 2.2 : l.rank >= 5 ? .6 : 1) / s;
      ctx.beginPath();
      ctx.moveTo(l.pts[0], l.pts[1]);
      for (let i = 2; i < l.pts.length; i += 2) ctx.lineTo(l.pts[i], l.pts[i + 1]);
      ctx.stroke();
      ctx.globalAlpha = 1;
    }
    function frame(t) {
      if (t0 === null) t0 = t;
      const radius = reduced ? Infinity : ((t - t0) / 3200) ** 1.4 * 11000;
      while (drawn < lines.length && lines[drawn].d <= radius) drawLine(lines[drawn++]);
      if (drawn < lines.length) raf = requestAnimationFrame(frame);
    }
    function redraw(full) {
      cancelAnimationFrame(raf);
      view(); ground();
      const upto = full ? lines.length : drawn;
      for (let i = 0; i < upto; i++) drawLine(lines[i]);
      drawn = upto;
      if (drawn < lines.length) raf = requestAnimationFrame(frame);
    }
    view(); ground();
    raf = requestAnimationFrame(frame);
    let rt;
    new ResizeObserver(() => { clearTimeout(rt); rt = setTimeout(() => redraw(false), 120); }).observe(c);
    hero = { redraw: () => redraw(false) };
  }

  /* ---------------- data ---------------- */
  let W, meta, places = [], streets = [], history = {}, civic = {}, safety = {}, map2d, map3d;
  const INC_COLORS = () => ({ violent: css("--inc-violent"), property: css("--inc-property"), police: css("--inc-police") });
  const soft = (p) => p.catch((e) => { console.warn(e); return {}; });

  async function boot() {
    [meta, W] = await Promise.all([getJSON("meta.json"), loadWorld({ keepLines: true })]);
    startHero(W);
    [places, streets, history, civic, safety] = await Promise.all([
      getJSON("places.json"), getJSON("streets.json"), soft(getJSON("history.json")), soft(getJSON("civic.json")), soft(getJSON("safety.json"))]);
    places.forEach((p, i) => { p.id = i; p.key = norm(p.n); });
    renderLedger(); initMap(); renderTowns(); renderSafety(); renderStory(); renderEat(); renderDirectory(); renderPeople(); renderNews(); renderSources();
  }

  const norm = (s) => String(s || "").toLowerCase().replace(/\b(new kensington|lower burrell|arnold|the|pa)\b/g, "").replace(/[^a-z0-9]/g, "");
  function matchPlace(name, address) {
    const k = norm(String(name).split(/ [–-] /)[0]);
    if (k.length < 4) return null;
    const hits = places.filter((p) => p.key && (p.key === k || (k.length >= 6 && (p.key.startsWith(k) || k.startsWith(p.key) && p.key.length >= 6))));
    if (!hits.length) return null;
    if (address) {
      const num = (address.match(/^\d+/) || [])[0];
      const byNum = num && hits.find((p) => (p.a || "").startsWith(num + " "));
      if (byNum) return byNum;
    }
    return hits.sort((a, b) => b.q - a.q)[0];
  }

  /* ---------------- ledger ---------------- */
  function renderLedger() {
    const s = meta.stats, d = civic.demographics || {};
    const pop = d.zcta_15068?.population;
    const items = [
      [fmt(s.buildings), "buildings"],
      [fmt(s.addresses), "address points"],
      [fmt(Math.round(s.road_km)), "km of road"],
      [fmt(s.streets), "named streets"],
      [fmt(s.places), "places & businesses"],
      [Math.round(s.local_share * 100) + "%", "independent, not chains"],
      [s.area_km2 + "", "km² of land & river"],
      [(s.elev_max_m - s.elev_min_m) + " m", "river to ridgetop"],
    ];
    if (pop) items.splice(0, 0, [fmt(pop), "residents (ACS)"]);
    $("#ledger-grid").innerHTML = items.map(([b, t]) => `<div><b>${esc(b)}</b><span>${esc(t)}</span></div>`).join("");
    $("#ledger-note").innerHTML = `Map data: Overture Maps release ${esc(meta.sources[0].release)}, built ${esc(meta.generated)}. ` +
      (pop ? `Population is from the Census Bureau's American Community Survey (${srcLink(d.zcta_15068.source)}). ` : "") +
      `"Independent" counts listings without a chain brand.`;
    $("#hero-elev").textContent = `Allegheny River ≈ ${s.elev_min_m} m · highest ground ≈ ${s.elev_max_m} m above sea level`;
  }

  /* ---------------- map ---------------- */
  function initMap() {
    const canvas = $("#map-canvas");
    map2d = new Map2D(canvas, W, {
      initial: [-5200, -1700, -1400, 1700],
      scaleEl: $("#scale"),
      onSelect: showCard,
    });
    map2d.setData(places, streets);
    getTerrain(meta).then((T) => { map2d.terrain = T; map2d.dirty = true; });
    loadBuildings(W).then((b) => { map2d.bld = b; map2d.dirty = true; $("#map-loading").hidden = true; });

    // chips
    const chips = $("#chips");
    const counts = {};
    places.forEach((p) => { counts[p.g] = (counts[p.g] || 0) + 1; });
    chips.innerHTML = `<button class="chip" type="button" data-g="*" aria-pressed="true">All ${fmt(places.length)}</button>` +
      Object.entries(meta.groups).filter(([k]) => counts[k]).map(([k, v]) =>
        `<button class="chip" type="button" data-g="${k}" aria-pressed="false"><i style="background:${GROUP_COLORS[k]}"></i>${esc(v)}</button>`).join("");
    chips.addEventListener("click", (e) => {
      const b = e.target.closest(".chip"); if (!b) return;
      const g = b.dataset.g;
      chips.querySelectorAll(".chip").forEach((x) => x.setAttribute("aria-pressed", String(x === b)));
      map2d.filter = new Set(g === "*" ? Object.keys(GROUP_COLORS) : [g]);
      map2d.dirty = true;
      sync3DPins();
    });

    // search
    const q = $("#q"), res = $("#results");
    q.addEventListener("input", () => {
      const t = q.value.trim().toLowerCase();
      if (t.length < 2) { res.innerHTML = ""; return; }
      const ps = places.filter((p) => p.n.toLowerCase().includes(t) || (p.c || "").toLowerCase().includes(t)).slice(0, 8)
        .map((p) => `<button type="button" data-p="${p.id}"><i style="background:${GROUP_COLORS[p.g]}"></i><b>${esc(p.n)}</b><small>${esc(p.c)}${p.t ? " · " + esc(p.t) : ""}</small></button>`);
      const ss = streets.filter((s) => s.n.toLowerCase().includes(t)).slice(0, 5)
        .map((s) => `<button type="button" data-s="${esc(s.n)}"><i style="background:var(--muted)"></i><b>${esc(s.n)}</b><small>Street · ${fmt(s.m)} m${s.t[0] ? " · " + esc(s.t.join(", ")) : ""}</small></button>`);
      res.innerHTML = ps.concat(ss).join("") || `<small style="padding:8px;color:var(--muted)">Nothing named “${esc(q.value)}” in 15068.</small>`;
    });
    res.addEventListener("click", (e) => {
      const b = e.target.closest("button"); if (!b) return;
      if (b.dataset.p) focusPlace(places[+b.dataset.p]);
      else focusStreet(streets.find((s) => s.n === b.dataset.s));
      res.innerHTML = ""; q.value = "";
    });

    // tools
    $("#zin").onclick = () => map2d.zoomAt(1.6, map2d.w / 2, map2d.h / 2);
    $("#zout").onclick = () => map2d.zoomAt(1 / 1.6, map2d.w / 2, map2d.h / 2);
    $("#home").onclick = () => { set3D(false); const b = meta.bounds; map2d.fitView([b[0] + 300, b[1] + 300, b[2] - 300, b[3] - 300]); };
    $("#dt").onclick = () => { if (map3d && !$("#gl-host").hidden) map3d.flyTo(DOWNTOWN[0], DOWNTOWN[1]); else map2d.flyTo(DOWNTOWN[0], DOWNTOWN[1], 1.3); };
    const toggle = (id, key) => {
      const b = $(id);
      b.onclick = () => { map2d.layers[key] = !map2d.layers[key]; b.setAttribute("aria-pressed", String(map2d.layers[key])); map2d.dirty = true; };
    };
    toggle("#tbld", "buildings"); toggle("#trel", "relief");
    $("#t3d").onclick = () => set3D($("#gl-host").hidden);
    $("#tinc").onclick = () => setIncidents(!map2d.layers.incidents);
    $("#tcr").onclick = () => setCrashes(!map2d.layers.crashes);
  }

  async function set3D(on) {
    const gl = $("#gl-host"), b = $("#t3d");
    if (on && !window.THREE) { showCard({ msg: "3D needs the three.js library, which didn't load. Check your connection and reload the page." }); return; }
    gl.hidden = !on; b.setAttribute("aria-pressed", String(on));
    $("#map-canvas").hidden = on;
    syncLegend();
    ["#tbld", "#trel", "#zin", "#zout", "#scale"].forEach((s) => { $(s).hidden = on; });
    if (on && !map3d) {
      $("#map-loading").hidden = false; $("#map-loading").textContent = "Raising the terrain…";
      await new Promise((r) => setTimeout(r, 30));
      map3d = new window.NK.Map3D(gl, W, { onSelect: showCard });
      const [T, bld] = await Promise.all([getTerrain(meta), loadBuildings(W)]);
      await map3d.build(T, bld);
      sync3DPins();
      map3d.target.x = map2d.cx; map3d.target.z = map2d.cy;
      $("#map-loading").hidden = true;
    } else if (on && map3d) { map3d.resize(); }
  }
  function sync3DPins() {
    if (!map3d) return;
    if (map2d.layers.incidents || map2d.layers.crashes) {
      const list = [];
      if (map2d.layers.incidents) list.push(...map2d.incidents.filter(map2d.incVisible).map((i) => Object.assign(Object.create(i), { g: i.c })));
      if (map2d.layers.crashes) list.push(...map2d.crashes.map((c) => Object.assign(Object.create(c), { g: "crash" })));
      map3d.setPlaces(list, { ...INC_COLORS(), crash: css("--ink") });
    }
    else map3d.setPlaces(places.filter((p) => map2d.filter.has(p.g)), GROUP_COLORS);
  }
  function syncLegend() {
    const inc = map2d.layers.incidents, cr = map2d.layers.crashes;
    $("#inc-legend").hidden = !(inc || cr);
    const in3d = !$("#gl-host").hidden;
    document.querySelectorAll("#inc-legend [data-l]").forEach((el) => {
      el.hidden = (el.dataset.l === "inc" ? !inc : !cr) || (in3d && !!el.dataset.shape) || (!in3d && !!el.dataset["3d"]);
    });
  }
  function setCrashes(on) {
    map2d.layers.crashes = on;
    $("#tcr").setAttribute("aria-pressed", String(on));
    syncLegend();
    map2d.hover = null; map2d.dirty = true;
    if (!on && map2d.sel && map2d.sel.yr != null) { map2d.sel = null; $("#card").hidden = true; }
    sync3DPins();
  }
  function setIncidents(on) {
    map2d.layers.incidents = on;
    $("#tinc").setAttribute("aria-pressed", String(on));
    syncLegend();
    map2d.hover = null; map2d.dirty = true;
    if (!on && map2d.sel && map2d.sel.d && map2d.sel.k && map2d.sel.yr == null) { map2d.sel = null; $("#card").hidden = true; }
    sync3DPins();
  }
  function focusIncident(i) {
    if (!i) return;
    scrollToMap();
    setIncidents(true);
    if (!map2d.incVisible(i)) map2d.incVisible = () => true;
    if (map3d && !$("#gl-host").hidden) map3d.flyTo(i.x, i.y); else map2d.flyTo(i.x, i.y, 2.2);
    map2d.select(i);
  }
  function renderSafety() {
    if (!window.NKSafety) return;
    map2d.setIncidents(safety.incidents || []);
    map2d.setCrashes(safety.crashes?.points || []);
    window.NKSafety.render(safety, {
      setFilter: (fn) => { map2d.incVisible = fn; map2d.dirty = true; if (map2d.layers.incidents) sync3DPins(); },
      focus: focusIncident,
      showLayer: () => { scrollToMap(); set3D(false); setIncidents(true); map2d.fitView([-6200, -2600, 1800, 2600]); },
      showCrashes: () => { scrollToMap(); set3D(false); setCrashes(true); map2d.fitView([-6200, -2600, 3200, 3600]); },
    });
  }

  async function rebuild3D() {
    if (!map3d) return;
    map3d.stopped = true;
    map3d.renderer.dispose();
    $("#gl-host").innerHTML = "";
    const wasOn = !$("#gl-host").hidden;
    map3d = null;
    if (wasOn) { $("#gl-host").hidden = true; set3D(true); }
  }

  function scrollToMap() { $("#map").scrollIntoView({ behavior: reduced ? "auto" : "smooth" }); }
  function focusPlace(p) {
    if (!p) return;
    if (!map2d.filter.has(p.g)) { $("#chips .chip").click(); }
    if (map3d && !$("#gl-host").hidden) map3d.flyTo(p.x, p.y); else map2d.flyTo(p.x, p.y, 2.6);
    map2d.select(p);
  }
  function focusStreet(s) {
    if (!s) return;
    set3D(false);
    map2d.flyTo(s.x, s.y, s.m > 3000 ? 0.6 : 1.4);
    showCard({ street: s });
  }

  function showCard(p) {
    const card = $("#card");
    if (!p) { card.hidden = true; return; }
    let html = `<button class="close" type="button" aria-label="Close">×</button>`;
    if (p.msg) html += `<p>${esc(p.msg)}</p>`;
    else if (p.yr != null && p.col) {
      const mo = p.mo ? new Date(p.yr, p.mo - 1).toLocaleString("en-US", { month: "long" }) + " " : "";
      html += `<p class="eyebrow">Police-reported crash</p><h3>${p.f ? "Fatal crash" : "Serious-injury crash"}</h3>
        <div class="meta">${esc(mo)}${p.yr} · ${esc(p.t)}</div>
        <div class="lines"><span>${esc(p.col)}</span>
          <span>${p.f ? `${p.f} killed` : ""}${p.f && p.s ? " · " : ""}${p.s ? `${p.s} seriously injured` : ""}</span>
          <a href="${esc(safety.crashes?.source || "")}" target="_blank" rel="noopener">PennDOT crash data ↗</a></div>
        <div class="meta">Location as recorded by the investigating police agency.</div>`;
    }
    else if (p.d && p.k && p.c) {
      const S = window.NKSafety;
      html += `<p class="eyebrow" style="color:var(--ink-2)"><span class="inc-key${p.pi ? " pi" : ""}" style="background:var(--inc-${esc(p.c)})"></span>${esc(S.CAT[p.c] || "")}${p.pi ? " · police involved" : ""}</p>
        <h3>${esc(S.TYPE[p.k] || p.k)}</h3>
        <div class="meta">${esc(S.monthName(p.d))} · ${esc(p.t)}</div>
        <div class="lines"><span class="mono" style="font-size:13px">${esc(p.l)}</span><span>${esc(p.s)}</span>
          <a href="${esc(p.src)}" target="_blank" rel="noopener">Source: ${esc(host(p.src))} ↗</a></div>
        <div class="meta">Location precision: ${esc(S.PREC[p.p] || p.p)}. Reported in the news; not a complete record.</div>`;
    }
    else if (p.street) {
      const s = p.street;
      html += `<p class="eyebrow">Street</p><h3>${esc(s.n)}</h3>
        <div class="meta">${fmt(s.m)} m (${(s.m / 1609).toFixed(2)} mi) inside 15068${s.a ? ` · ${fmt(s.a)} addresses` : ""}${s.ref.length ? " · Route " + esc(s.ref.join(", ")) : ""}</div>
        <div class="lines">${s.t.length ? "Runs through " + esc(s.t.join(", ")) : ""}</div>`;
    } else {
      const col = GROUP_COLORS[p.g];
      html += `<p class="eyebrow" style="color:${col}">${esc(meta.groups[p.g])} · ${esc(p.c)}</p><h3>${esc(p.n)}</h3>
        <div class="lines">
          ${p.a ? `<span>${esc(p.a)}</span>` : ""}
          ${p.ph ? `<span class="mono">${esc(p.ph)}</span>` : ""}
          ${p.w ? `<a href="${esc(p.w)}" target="_blank" rel="noopener">${esc(host(p.w))}</a>` : ""}
          ${p.s ? `<a href="${esc(p.s)}" target="_blank" rel="noopener">${esc(host(p.s))}</a>` : ""}
          <a href="https://www.google.com/maps/search/?api=1&query=${encodeURIComponent(p.n + " " + p.lat + "," + p.lon)}" target="_blank" rel="noopener">Directions ↗</a>
        </div>
        <div class="meta">${esc(p.t || "")} · ${p.lat.toFixed(5)}, ${p.lon.toFixed(5)}${p.b ? " · chain: " + esc(p.b) : ""}</div>`;
    }
    card.innerHTML = html;
    card.hidden = false;
    card.querySelector(".close").onclick = () => { card.hidden = true; map2d.sel = null; map2d.dirty = true; };
  }

  /* ---------------- towns ---------------- */
  function renderTowns() {
    const d = civic.demographics || {}, f = history.facts || {};
    const info = {
      "New Kensington": { demo: d.new_kensington_city, inc: "Borough 1892 · city 1934",
        text: "The river-flat street grid, laid out for the 1891 land sale and the first Alcoa works. Downtown sits along Fifth Avenue." },
      "Arnold": { demo: d.arnold_city, inc: "Borough 1896 · city 1939",
        text: "The smaller city just upriver, sharing New Ken's school district and its Alcoa-era mill history." },
      "Lower Burrell": { demo: d.lower_burrell_city, inc: "City 1959",
        text: "Hilltop suburbs and ravines above the valley, split from old Burrell Township in 1879." },
    };
    const byTown = {};
    places.forEach((p) => { byTown[p.t] = (byTown[p.t] || 0) + 1; });
    const grid = $("#towns-grid");
    const order = ["New Kensington", "Arnold", "Lower Burrell"];
    grid.innerHTML = meta.towns.filter((t) => t.core).sort((a, b) => order.indexOf(a.n) - order.indexOf(b.n)).map((t) => {
      const i = info[t.n] || {}, dm = i.demo || {};
      return `<article class="town">
        <canvas data-town="${esc(t.n)}" aria-label="Street map of ${esc(t.n)}"></canvas>
        <h3>${esc(t.n)}</h3>
        <p>${esc(i.text || "")}</p>
        <dl>
          ${dm.population_2020 ? `<dt>Population (2020)</dt><dd>${fmt(dm.population_2020)}</dd>` : ""}
          ${dm.median_household_income ? `<dt>Median household income</dt><dd>$${fmt(dm.median_household_income)}</dd>` : ""}
          <dt>Buildings mapped</dt><dd>${fmt(meta.stats.buildings_by_town[t.n] || 0)}</dd>
          <dt>Address points</dt><dd>${fmt(meta.stats.addresses_by_town[t.n] || 0)}</dd>
          <dt>Places listed</dt><dd>${fmt(byTown[t.n] || 0)}</dd>
          ${i.inc ? `<dt>Incorporated</dt><dd>${esc(i.inc)}</dd>` : ""}
        </dl>
        ${dm.source ? srcLink(dm.source) : ""}
      </article>`;
    }).join("");
    const draw = () => grid.querySelectorAll("canvas").forEach((c) => drawTown(c, W.towns.find((t) => t.n === c.dataset.town)));
    draw();
    new ResizeObserver(() => draw()).observe(grid);
    new MutationObserver(draw).observe(root, { attributes: true, attributeFilter: ["data-theme"] });
  }
  function drawTown(c, t) {
    if (!t) return;
    const raw = W.base.towns.find((x) => x.n === t.n);
    let x0 = Infinity, y0 = Infinity, x1 = -Infinity, y1 = -Infinity;
    raw.r.forEach((r) => { const p = dec(r, W.q); for (let i = 0; i < p.length; i += 2) { x0 = Math.min(x0, p[i]); x1 = Math.max(x1, p[i]); y0 = Math.min(y0, p[i + 1]); y1 = Math.max(y1, p[i + 1]); } });
    const r = c.getBoundingClientRect(), dpr = Math.min(2, devicePixelRatio || 1);
    c.width = r.width * dpr; c.height = r.height * dpr;
    const ctx = c.getContext("2d");
    const s = Math.min(r.width / (x1 - x0), r.height / (y1 - y0)) * 0.9;
    ctx.setTransform(dpr * s, 0, 0, dpr * s, dpr * (r.width / 2 - (x0 + x1) / 2 * s), dpr * (r.height / 2 - (y0 + y1) / 2 * s));
    ctx.fillStyle = css("--map-bg"); ctx.fillRect(x0 - 1e4, y0 - 1e4, 3e4, 3e4);
    ctx.fillStyle = css("--river-soft"); ctx.fill(W.water);
    ctx.save(); ctx.clip(t.p);
    ctx.fillStyle = css("--map-land"); ctx.fill(t.p);
    ctx.lineCap = ctx.lineJoin = "round";
    for (let k = 5; k >= 0; k--) {
      ctx.strokeStyle = k <= 2 ? css("--ember") : css("--ink-2");
      ctx.globalAlpha = k <= 2 ? .9 : .55;
      ctx.lineWidth = (k <= 2 ? 1.8 : k === 5 ? .5 : .9) / s;
      ctx.stroke(W.roads[k]);
    }
    ctx.restore();
    ctx.globalAlpha = 1; ctx.lineWidth = 1.5 / s; ctx.strokeStyle = css("--ink"); ctx.stroke(t.p);
  }

  /* ---------------- story ---------------- */
  function renderStory() {
    const tl = history.timeline || [];
    const f = history.facts || {};
    const pops = Object.entries(f.population_by_census || {}).map(([y, v]) => [+y, v]).sort((a, b) => a[0] - b[0]);
    if (pops.length) {
      const Wd = 720, H = 220, pad = 34, max = Math.max(...pops.map((p) => p[1]));
      const yr0 = 1920, yr1 = 2030, x = (y) => pad + (y - yr0) / (yr1 - yr0) * (Wd - pad * 2), y = (v) => H - 30 - v / max * (H - 70);
      const bars = pops.map(([yr, v]) => `<rect x="${x(yr) - 14}" y="${y(v)}" width="28" height="${H - 30 - y(v)}" fill="var(--river)" rx="1"/>
        <text x="${x(yr)}" y="${y(v) - 7}" text-anchor="middle" fill="var(--ink)" font-size="12" font-family="var(--f-mono)">${fmt(v)}</text>
        <text x="${x(yr)}" y="${H - 12}" text-anchor="middle" fill="var(--muted)" font-size="12" font-family="var(--f-mono)">${yr}</text>`).join("");
      $("#pop-chart").innerHTML = `<p class="eyebrow" style="margin:0 0 6px">New Kensington population, census years</p>
        <div style="overflow-x:auto"><svg viewBox="0 0 ${Wd} ${H}" width="100%" style="max-width:${Wd}px;min-width:520px;display:block" role="img" aria-label="New Kensington population by census year">
        <line x1="${pad}" x2="${Wd - pad}" y1="${H - 30}" y2="${H - 30}" stroke="var(--line)"/>${bars}</svg></div>
        <p class="ledger-note" style="margin:4px 0 36px">${esc(f.population_note || "")}</p>`;
    }
    const item = (e) => `<div class="tl-item"><div class="yr">${esc(e.year)}</div><div><h3>${esc(e.title)}</h3><p>${esc(e.text)}</p>${e.note ? `<p class="ledger-note">Note: ${esc(e.note)}</p>` : ""}${srcLink(e.source)}</div></div>`;
    const sorted = [...tl].sort((a, b) => a.year - b.year);
    let open = false;
    const draw = () => {
      $("#timeline").innerHTML = (open ? sorted : sorted.filter((_, i) => i % Math.ceil(sorted.length / 14) === 0)).map(item).join("") || `<p class="empty">Timeline data not available.</p>`;
      $("#tl-more").textContent = open ? "Show fewer entries" : `Show all ${sorted.length} entries`;
    };
    draw();
    $("#tl-more").onclick = () => { open = !open; draw(); };
    const lm = [...(history.neighborhoods || []).map((n) => ({ ...n, kind: "Neighborhood" })), ...(history.landmarks || []).map((n) => ({ ...n, kind: "Landmark" }))];
    $("#landmarks").innerHTML = lm.map((l) => {
      const hit = matchPlace(l.name, l.address);
      return `<div class="row-item"><span class="eyebrow">${l.kind}</span><b>${esc(l.name)}</b><span>${esc(l.text)}</span>
        ${l.address ? `<span class="mono" style="font-size:12px">${esc(l.address)}</span>` : ""}
        <span>${hit ? `<a href="#map" data-go="${hit.id}">Show on map</a> · ` : ""}${srcLink(l.source)}</span></div>`;
    }).join("");
  }

  /* ---------------- eat + events ---------------- */
  function renderEat() {
    const list = civic.food_and_culture || [];
    $("#eat-list").innerHTML = list.map((f) => {
      const hit = matchPlace(f.name, f.address);
      return `<div class="row-item"><span class="eyebrow">${esc(f.type || "")}</span><b>${esc(f.name)}</b><span>${esc(f.text)}</span>
        ${f.address ? `<span class="mono" style="font-size:12px">${esc(f.address)}</span>` : ""}
        <span>${hit ? `<a href="#map" data-go="${hit.id}">Show on map</a> · ` : ""}${srcLink(f.source)}</span></div>`;
    }).join("") || `<p class="empty">No local picks loaded.</p>`;
    $("#events").innerHTML = (history.events || []).map((e) => `<div class="row-item"><span class="eyebrow">${esc(e.when)}</span><b>${esc(e.name)}</b>
      <span>${esc(e.text)}</span>${e.where ? `<span class="mono" style="font-size:12px">${esc(e.where)}</span>` : ""}${srcLink(e.source)}</div>`).join("");
  }
  document.addEventListener("click", (e) => {
    const a = e.target.closest("[data-go]");
    if (!a) return;
    e.preventDefault();
    const go = a.dataset.go;
    scrollToMap();
    if (go.startsWith("s:")) focusStreet(streets.find((s) => s.n === go.slice(2)));
    else if (go.startsWith("xy:")) { const [x, y] = go.slice(3).split(",").map(Number); set3D(false); map2d.flyTo(x, y, 2); }
    else focusPlace(places[+go]);
  });

  /* ---------------- directory ---------------- */
  function renderDirectory() {
    const tabs = [["places", `Places (${fmt(places.length)})`], ["streets", `Streets (${fmt(streets.length)})`], ["civic", "Public offices"]];
    let tab = "places", limit = 60;
    $("#dir-tabs").innerHTML = tabs.map(([k, v], i) => `<button class="chip" type="button" role="tab" data-t="${k}" aria-pressed="${i === 0}" aria-selected="${i === 0}">${esc(v)}</button>`).join("");
    const offices = [...(civic.government || []), ...(civic.parks_and_rec || []).map((p) => ({ ...p, role: p.text }))];
    const q = $("#dir-q");
    function draw() {
      const t = q.value.trim().toLowerCase();
      let rows, head;
      if (tab === "places") {
        head = "<tr><th>Name</th><th>Type</th><th>Town</th><th>Address</th><th>Phone</th></tr>";
        const f = places.filter((p) => !t || (p.n + " " + p.c + " " + (p.t || "") + " " + (p.a || "") + " " + meta.groups[p.g]).toLowerCase().includes(t));
        rows = [f.length, f.slice(0, limit).map((p) => `<tr data-go="${p.id}"><td><span class="dot" style="background:${GROUP_COLORS[p.g]}"></span>${esc(p.n)}<span class="sub">${esc(meta.groups[p.g])}</span></td><td>${esc(p.c)}</td><td>${esc(p.t || "")}</td><td>${esc(p.a || "")}</td><td class="mono">${esc(p.ph || "")}</td></tr>`)];
      } else if (tab === "streets") {
        head = `<tr><th>Street</th><th>Town</th><th class="num">Length</th><th class="num">Addresses</th></tr>`;
        const f = streets.filter((s) => !t || (s.n + " " + s.t.join(" ")).toLowerCase().includes(t));
        rows = [f.length, f.slice(0, limit).map((s) => `<tr data-go="s:${esc(s.n)}"><td>${esc(s.n)}${s.ref.length ? `<span class="sub">Route ${esc(s.ref.join(", "))}</span>` : ""}</td><td>${esc(s.t.join(", "))}</td><td class="num">${fmt(s.m)} m</td><td class="num">${s.a ? fmt(s.a) : "–"}</td></tr>`)];
      } else {
        head = "<tr><th>Office</th><th>What</th><th>Address</th><th>Phone</th></tr>";
        const f = offices.filter((o) => !t || JSON.stringify(o).toLowerCase().includes(t));
        rows = [f.length, f.slice(0, limit).map((o) => `<tr><td>${o.url || o.source ? `<a href="${esc(o.url || o.source)}" target="_blank" rel="noopener">${esc(o.name)}</a>` : esc(o.name)}</td><td>${esc(o.role || "")}</td><td>${esc(o.address || "")}</td><td class="mono">${esc(o.phone || "")}</td></tr>`)];
      }
      $("#dir-table").innerHTML = `<thead>${head}</thead><tbody>${rows[1].join("") || `<tr><td colspan="5" class="empty">Nothing matches “${esc(q.value)}”.</td></tr>`}</tbody>`;
      $("#dir-count").textContent = `${fmt(Math.min(limit, rows[0]))} of ${fmt(rows[0])}`;
      $("#dir-more").hidden = rows[0] <= limit;
    }
    $("#dir-tabs").addEventListener("click", (e) => {
      const b = e.target.closest(".chip"); if (!b) return;
      tab = b.dataset.t; limit = 60;
      $("#dir-tabs").querySelectorAll(".chip").forEach((x) => { x.setAttribute("aria-pressed", String(x === b)); x.setAttribute("aria-selected", String(x === b)); });
      draw();
    });
    q.addEventListener("input", () => { limit = 60; draw(); });
    $("#dir-more").onclick = () => { limit += 120; draw(); };
    draw();
  }

  /* ---------------- people / news / sources ---------------- */
  function renderPeople() {
    $("#people-list").innerHTML = (history.people || []).map((p) => `<div class="row-item"><b>${esc(p.name)}</b><span>${esc(p.known_for)}</span>
      <span class="mono" style="font-size:12px;color:var(--muted)">${esc(p.connection || "")}</span>${srcLink(p.source)}</div>`).join("") || `<p class="empty">No people loaded.</p>`;
  }
  function renderNews() {
    const n = [...(civic.news_2025_2026 || [])].sort((a, b) => String(b.date).localeCompare(String(a.date)));
    const month = (d) => { const [y, m] = String(d).split("-"); return m ? new Date(+y, +m - 1).toLocaleString("en-US", { month: "long", year: "numeric" }) : d; };
    $("#news-list").innerHTML = n.map((a) => `<article><time>${esc(month(a.date))}${a.date_note ? " (approx.)" : ""}</time><h3>${esc(a.headline)}</h3><p>${esc(a.text)}</p>${srcLink(a.source)}</article>`).join("") || `<p class="empty">No news loaded.</p>`;
  }
  function renderSources() {
    const r = [history._meta, civic._meta].filter(Boolean);
    $("#src-list").innerHTML = meta.sources.map((s) => `<div><a href="${esc(s.url)}" target="_blank" rel="noopener">${esc(s.name)}</a> · ${esc(s.license)}</div>`).join("") +
      r.map((m) => `<div>Research compiled ${esc(m.compiled)}: ${esc(m.method)}</div>`).join("");
  }

  boot().catch((e) => {
    console.error(e);
    $("#map-loading").textContent = "The map data didn't load. Serve this folder over HTTP (for example: python -m http.server) and reload.";
  });
})();
