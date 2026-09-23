/* NK15068 — page wiring */
(function () {
  "use strict";
  const { GROUP_COLORS, getJSON, getTerrain, loadWorld, loadBuildings, Map2D, dec, css } = window.NK;
  const $ = (s, r = document) => r.querySelector(s);
  const $$ = (s, r = document) => [...r.querySelectorAll(s)];
  const esc = (s) => String(s ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
  const fmt = (n) => Number(n).toLocaleString("en-US");
  const reduced = matchMedia("(prefers-reduced-motion: reduce)").matches;
  const DOWNTOWN = [-3350, -40];
  const ISSUES = "https://github.com/DonnieCash/15068/issues";

  /* ---------------- credits: publication names, never bare domains when we know the outlet ---------------- */
  const PUBS = {
    "wpxi.com": "WPXI", "cbsnews.com": "CBS News Pittsburgh", "post-gazette.com": "Pittsburgh Post-Gazette", "wesa.fm": "WESA",
    "spotlightpa.org": "Spotlight PA", "pittsburghmagazine.com": "Pittsburgh Magazine", "en.wikipedia.org": "Wikipedia",
    "britannica.com": "Britannica", "loc.gov": "Library of Congress", "hmdb.org": "Historical Marker Database",
    "parnassuspen.com": "Parnassus Pen", "crimewatch.net": "CrimeWatch", "policescorecard.org": "Police Scorecard",
    "census.gov": "Census Bureau", "censusreporter.org": "Census Reporter", "datausa.io": "Data USA",
    "cityofarnoldpa.org": "City of Arnold", "cityoflowerburrell.com": "City of Lower Burrell",
    "westmorelandcountypa.gov": "Westmoreland County", "engage.rideprt.org": "Pittsburgh Regional Transit",
  };
  function pubName(u) {
    let url;
    try { url = new URL(u); } catch (e) { return ""; }
    const h = url.hostname.replace(/^www\./, ""), path = url.pathname.toLowerCase();
    if (h === "triblive.com" && path.includes("/valley-news-dispatch/")) return "Valley News Dispatch (TribLive)";
    if (h === "community.triblive.com") return "TribLive community news";
    if (h === "archive.triblive.com") return "Tribune-Review archive";
    if (h === "triblive.com" || h.endsWith(".triblive.com")) return "TribLive";
    if (PUBS[h]) return PUBS[h];
    if (h.endsWith(".crimewatchpa.com")) return "CrimeWatch";
    if (h === "github.com" || h === "raw.githubusercontent.com") {
      if (path.startsWith("/jacobkap/")) return "FBI UCR via Jacob Kaplan";
      if (path.startsWith("/bencarneiro/ntsb")) return "PennDOT crash data";
      if (h === "raw.githubusercontent.com" && path.startsWith("/washingtonpost/")) return "Washington Post";
      return "GitHub dataset";
    }
    return h;
  }
  const pub = (u) => (u ? `<a class="cr" href="${esc(u)}" target="_blank" rel="noopener">${esc(pubName(u) || "source")}</a>` : "");
  function credit(urls, pre = "Source: ") {
    const seen = new Set(), out = [];
    for (const u of [].concat(urls || []).filter(Boolean)) {
      const n = pubName(u);
      if (!n || seen.has(n)) continue;
      seen.add(n); out.push(pub(u));
    }
    return out.length ? pre + out.join(", ") : "";
  }
  window.NKpub = Object.assign(pub, { pubName, credit });

  /* ---------------- AP-style dates ---------------- */
  const AP_MONTHS = ["Jan.", "Feb.", "March", "April", "May", "June", "July", "Aug.", "Sept.", "Oct.", "Nov.", "Dec."];
  function apDate(s, approx) {
    const m = String(s ?? "").match(/^(\d{4})(?:-(\d{1,2})(?:-(\d{1,2}))?)?/);
    if (!m) return String(s ?? "");
    let out = m[1];
    if (m[2] && AP_MONTHS[+m[2] - 1]) out = m[3] ? `${AP_MONTHS[+m[2] - 1]} ${+m[3]}, ${m[1]}` : `${AP_MONTHS[+m[2] - 1]} ${m[1]}`;
    return out + (approx ? " (month approximate)" : "");
  }
  window.NKapDate = apDate;

  /* ---------------- Pennsylvania keystone route shields ---------------- */
  const SHIELDED = new Set(["56", "366", "380", "780"]);
  function shield(ref) {
    const r = String(ref).trim().replace(/^(PA|SR)[\s-]*/i, "");
    if (!SHIELDED.has(r)) return "";
    const three = r.length >= 3;
    return `<svg class="ks" viewBox="0 0 26 24" width="26" height="24" role="img" aria-label="Pennsylvania Route ${r}"><path d="M2.5 1.5H23.5L21.8 5.2L24 7.4L19 22.5H7L2 7.4L4.2 5.2Z" fill="var(--surface)" stroke="var(--ink)" stroke-width="1.3" stroke-linejoin="round"/><text x="13" y="15.6" text-anchor="middle" font-family="Radio Canada, Arial, sans-serif" font-weight="700" font-size="${three ? 8.5 : 9.5}"${three ? ' style="font-stretch:85%"' : ""} fill="var(--ink)">${r}</text></svg>`;
  }
  window.NKshield = shield;
  const routes = (refs) => (refs || []).map((r) => shield(r) || `<span class="rt">${/^\d+$/.test(r) ? "Route " : ""}${esc(r)}</span>`).join("");
  const USPS = { Street: "St", Avenue: "Ave", Road: "Rd", Boulevard: "Blvd", Drive: "Dr", Lane: "Ln", Place: "Pl", Court: "Ct", Alley: "Aly" };
  const SUFFIX = /\b(Street|Avenue|Road|Boulevard|Drive|Lane|Place|Court|Alley)\b/g;
  function streetHead(n) {
    const m = String(n).match(/^(.*\S)\s+(Street|Avenue|Road|Boulevard|Drive|Lane|Place|Court|Alley)$/);
    return m ? `${esc(m[1])} <small>${USPS[m[2]]}</small>` : esc(n);
  }
  const shortAddr = (a) => String(a || "").split(",")[0].replace(SUFFIX, (w) => USPS[w]);
  const cap = (s) => String(s || "").replace(/^./, (c) => c.toUpperCase());
  const endStop = (s) => (/[.!?]$/.test(String(s).trim()) ? esc(String(s).trim()) : esc(String(s).trim()) + ".");

  /* ---------------- theme ---------------- */
  const root = document.documentElement;
  try { const t = localStorage.getItem("nk-theme"); if (t) root.dataset.theme = t; } catch (e) { /* storage unavailable */ }
  const darkMQ = matchMedia("(prefers-color-scheme: dark)");
  const isDarkNow = () => (root.dataset.theme ? root.dataset.theme === "dark" : darkMQ.matches);
  const themeBtn = $("#ttheme");
  function syncThemeBtn() {
    const d = isDarkNow();
    themeBtn.textContent = d ? "Light" : "Dark";
    themeBtn.setAttribute("aria-label", d ? "Switch to light theme" : "Switch to dark theme");
  }
  syncThemeBtn();
  darkMQ.addEventListener?.("change", () => { syncThemeBtn(); redrawCanvases(); });
  themeBtn.addEventListener("click", () => {
    root.dataset.theme = isDarkNow() ? "light" : "dark";
    try { localStorage.setItem("nk-theme", root.dataset.theme); } catch (e) { /* ignore */ }
    syncThemeBtn();
    if (map3d) rebuild3D();
    redrawCanvases();
  });
  function redrawCanvases() {
    hero?.redraw();
    drawTowns?.();
    if (map2d) { map2d.relief = null; map2d.dirty = true; }
  }

  /* ---------------- section bar: mark the section in view ---------------- */
  function scrollspy() {
    const bar = $(".secbar .links");
    const links = new Map($$(".secbar a[href^='#']").map((a) => [a.getAttribute("href").slice(1), a]));
    const io = new IntersectionObserver((ents) => {
      for (const e of ents) {
        if (!e.isIntersecting) continue;
        const a = links.get(e.target.id);
        if (!a) continue;
        links.forEach((x) => x.removeAttribute("aria-current"));
        a.setAttribute("aria-current", "true");
        if (a.offsetLeft < bar.scrollLeft || a.offsetLeft + a.offsetWidth > bar.scrollLeft + bar.clientWidth) bar.scrollLeft = a.offsetLeft - 24;
      }
    }, { rootMargin: "-45% 0px -50% 0px" });
    links.forEach((_, id) => { const el = document.getElementById(id); if (el) io.observe(el); });
  }
  scrollspy();

  /* rails stick only when they fit on screen */
  function stickyRails() {
    const fit = () => ["#story-rail", "#safety-depts"].forEach((s) => {
      const el = $(s);
      if (!el) return;
      el.classList.toggle("sticky", innerWidth >= 960 && el.offsetHeight < innerHeight - 80);
    });
    fit();
    let t;
    addEventListener("resize", () => { clearTimeout(t); t = setTimeout(fit, 150); });
    setTimeout(fit, 1500);
    refitRails = fit;
  }
  let refitRails = () => {};
  /* wide tables fade at the right edge while they overflow */
  function fadeWide() {
    $$(".dir-table-wrap").forEach((w) => {
      const upd = () => w.classList.toggle("fade", w.scrollWidth > w.clientWidth + 2 && w.scrollLeft + w.clientWidth < w.scrollWidth - 2);
      upd();
      if (!w.dataset.fade) {
        w.dataset.fade = 1;
        w.addEventListener("scroll", upd, { passive: true });
        const ro = new ResizeObserver(upd);
        ro.observe(w);
        const t = w.querySelector("table");
        if (t) ro.observe(t);
      }
    });
  }
  /* open every <details> for printing, then put them back */
  let printOpened = [];
  addEventListener("beforeprint", () => { printOpened = $$("details:not([open])"); printOpened.forEach((d) => { d.open = true; }); });
  addEventListener("afterprint", () => { printOpened.forEach((d) => { d.open = false; }); printOpened = []; });

  /* ---------------- lead art: a still drawing of the roads of 15068 ---------------- */
  let hero = null;
  function startHero(W) {
    const c = $("#hero-canvas"), ctx = c.getContext("2d");
    const lines = W.lines.filter((l) => l.rank <= 5).sort((a, b) => b.rank - a.rank);
    function draw() {
      const r = c.getBoundingClientRect();
      if (!r.width) return;
      const dpr = Math.min(2, devicePixelRatio || 1), w = r.width, h = r.height;
      c.width = Math.round(w * dpr); c.height = Math.round(h * dpr);
      const s = Math.max(w / 9000, h / 7000);
      const ox = w / 2 - DOWNTOWN[0] * s, oy = h * 0.5 - DOWNTOWN[1] * s;
      ctx.setTransform(1, 0, 0, 1, 0, 0);
      ctx.fillStyle = css("--map-bg"); ctx.fillRect(0, 0, c.width, c.height);
      ctx.setTransform(dpr * s, 0, 0, dpr * s, dpr * ox, dpr * oy);
      ctx.lineCap = ctx.lineJoin = "round";
      ctx.fillStyle = css("--map-land"); ctx.fill(W.zip);
      ctx.fillStyle = css("--river-soft"); ctx.fill(W.water);
      const route = css("--route"), minor = css("--muted");
      for (const l of lines) {
        const major = l.rank <= 2;
        ctx.strokeStyle = major ? route : minor;
        ctx.globalAlpha = major ? .9 : (l.rank >= 5 ? .22 : .42);
        ctx.lineWidth = (major ? 2.2 : l.rank >= 5 ? .6 : 1) / s;
        ctx.beginPath();
        ctx.moveTo(l.pts[0], l.pts[1]);
        for (let i = 2; i < l.pts.length; i += 2) ctx.lineTo(l.pts[i], l.pts[i + 1]);
        ctx.stroke();
      }
      ctx.globalAlpha = 1;
      ctx.lineWidth = 1.5 / s; ctx.strokeStyle = css("--boundary");
      ctx.setLineDash([6 / s, 4 / s]); ctx.stroke(W.zip); ctx.setLineDash([]);
    }
    draw();
    let rt;
    new ResizeObserver(() => { clearTimeout(rt); rt = setTimeout(draw, 120); }).observe(c);
    hero = { redraw: draw };
  }

  /* ---------------- data ---------------- */
  let W, meta, places = [], streets = [], history = {}, civic = {}, safety = {}, petsInfo = {}, map2d, map3d, drawTowns;
  const INC_COLORS = () => ({ violent: css("--inc-violent"), property: css("--inc-property"), police: css("--inc-police") });
  const PET_COLORS = () => ({ "pet-lost": css("--pet-lost"), "pet-found": css("--pet-found"), "pet-spotted": css("--pet-spotted") });
  const soft = (p) => p.catch((e) => { console.warn(e); return {}; });

  async function boot() {
    [meta, W] = await Promise.all([getJSON("meta.json"), loadWorld({ keepLines: true })]);
    renderMasthead();
    startHero(W);
    [places, streets, history, civic, safety, petsInfo] = await Promise.all([
      getJSON("places.json"), getJSON("streets.json"), soft(getJSON("history.json")), soft(getJSON("civic.json")),
      soft(getJSON("safety.json")), soft(getJSON("pets.json"))]);
    places.forEach((p, i) => { p.id = i; p.key = norm(p.n); });
    renderLedger(); initMap(); renderNews(); renderPets(); renderTowns(); renderSafety(); renderStory(); renderEat(); renderPeople(); renderDirectory(); renderSources();
    fadeWide(); stickyRails();
    document.fonts?.ready.then(() => redrawCanvases());
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

  /* ---------------- masthead + front ---------------- */
  function renderMasthead() {
    $("#u-built").textContent = `Map data built ${apDate(meta.generated)}`;
    $("#u-release").textContent = `Overture Maps release ${meta.sources[0].release}`;
    $("#hero-elev").textContent = `Allegheny River about ${meta.stats.elev_min_m} m · highest ground about ${meta.stats.elev_max_m} m`;
    $("#foot-line").innerHTML = `NK15068 · Map data built ${esc(apDate(meta.generated))} from Overture Maps release ${esc(meta.sources[0].release)} · Map data © OpenStreetMap contributors, Overture Maps Foundation · <a href="${ISSUES}" target="_blank" rel="noopener">Report a correction ›</a>`;
  }
  function renderLedger() {
    const s = meta.stats, d = civic.demographics || {};
    const pop = d.zcta_15068?.population;
    const share = Math.round(s.local_share * 100);
    const rows = [
      pop ? ["Residents", fmt(pop)] : null,
      ["Buildings", fmt(s.buildings)], ["Address points", fmt(s.addresses)], ["Named streets", fmt(s.streets)],
      ["Road, in kilometres", fmt(Math.round(s.road_km))], ["Businesses and places", fmt(s.places)],
      ["No chain brand (share)", share + "%"], ["Area, land and river, km²", String(s.area_km2)],
    ].filter(Boolean);
    $("#ledger-grid").innerHTML = rows.map(([k, v]) => `<div><dt>${esc(k)}</dt><dd>${esc(v)}</dd></div>`).join("");
    $("#ledger-note").innerHTML = (pop ? `Residents from the American Community Survey. ${credit(d.zcta_15068.source)}. ` : "") +
      `Other counts from Overture Maps release ${esc(meta.sources[0].release)}.`;
    $("#ledger-lede").innerHTML = `<p>ZIP 15068 holds ${fmt(s.buildings)} buildings, ${fmt(s.addresses)} address points and ${fmt(s.streets)} named streets, about ${fmt(Math.round(s.road_km))} kilometres of road in all. It covers the three cities along this stretch of the Allegheny and clips small edges of Upper Burrell, Plum and Allegheny Township.</p>
      <p>Of the ${fmt(s.places)} businesses and places listed, ${share}% carry no chain brand. <a class="act" href="#map">Open the map ›</a></p>`;
    const news = sortedNews().slice(0, 4);
    $("#latest").innerHTML = news.map((a) => `<li><p class="kicker">${esc(apDate(a.date))}</p><a href="#news">${esc(a.headline)}</a></li>`).join("");
    $("#latest-box").hidden = !news.length;
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

    // category filter
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
        .map((s) => `<button type="button" data-s="${esc(s.n)}"><i style="background:var(--muted)"></i><b>${esc(s.n)}${s.ref.map(shield).join("")}</b><small>Street · ${fmt(s.m)} m${s.t[0] ? " · " + esc(s.t.join(", ")) : ""}</small></button>`);
      res.innerHTML = ps.concat(ss).join("") || `<p class="none">Nothing named “${esc(q.value)}” in 15068.</p>`;
    });
    res.addEventListener("click", (e) => {
      const b = e.target.closest("button"); if (!b) return;
      if (b.dataset.p) focusPlace(places[+b.dataset.p]);
      else focusStreet(streets.find((s) => s.n === b.dataset.s));
      res.innerHTML = ""; q.value = "";
    });

    // layers popover
    const lb = $("#layers-btn"), pop = $("#layers-pop");
    const setPop = (open) => { pop.hidden = !open; lb.setAttribute("aria-expanded", String(open)); };
    lb.onclick = (e) => { e.stopPropagation(); setPop(pop.hidden); };
    document.addEventListener("click", (e) => { if (!pop.hidden && !pop.contains(e.target) && !lb.contains(e.target)) setPop(false); });
    document.addEventListener("keydown", (e) => {
      if (e.key !== "Escape") return;
      if (!pop.hidden) { setPop(false); lb.focus(); }
      if (map2d.pickMode) { map2d.pickMode = null; map2d.c.style.cursor = ""; showCard(null); }
    });

    $("#zin").onclick = () => map2d.zoomAt(1.6, map2d.w / 2, map2d.h / 2);
    $("#zout").onclick = () => map2d.zoomAt(1 / 1.6, map2d.w / 2, map2d.h / 2);
    $("#home").onclick = () => { setPop(false); set3D(false); const b = meta.bounds; map2d.fitView([b[0] + 300, b[1] + 300, b[2] - 300, b[3] - 300]); };
    $("#dt").onclick = () => { setPop(false); if (map3d && !$("#gl-host").hidden) map3d.flyTo(DOWNTOWN[0], DOWNTOWN[1]); else map2d.flyTo(DOWNTOWN[0], DOWNTOWN[1], 1.3); };
    const toggle = (id, key) => {
      const b = $(id);
      b.onclick = () => { map2d.layers[key] = !map2d.layers[key]; b.setAttribute("aria-pressed", String(map2d.layers[key])); map2d.dirty = true; };
    };
    toggle("#tbld", "buildings"); toggle("#trel", "relief");
    $("#t3d").onclick = () => set3D($("#gl-host").hidden);
    $("#tinc").onclick = () => setIncidents(!map2d.layers.incidents);
    $("#tcr").onclick = () => setCrashes(!map2d.layers.crashes);
    $("#tpet").onclick = () => setPetsLayer(!map2d.layers.pets);
  }

  async function set3D(on) {
    const gl = $("#gl-host"), b = $("#t3d");
    if (on && !window.THREE) { showCard({ msg: "3D needs the three.js library, which didn't load. Check your connection and reload the page." }); return; }
    gl.hidden = !on; b.setAttribute("aria-pressed", String(on));
    $("#map-canvas").hidden = on;
    syncLegend();
    ["#tbld", "#trel", ".zoom", "#scale"].forEach((s) => { $(s).hidden = on; });
    if (on && !map3d) {
      $("#map-loading").hidden = false; $("#map-loading").textContent = "Loading 3D terrain…";
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
    const L = map2d.layers;
    if (L.incidents || L.crashes || L.pets) {
      const list = [];
      if (L.incidents) list.push(...map2d.incidents.filter(map2d.incVisible).map((i) => Object.assign(Object.create(i), { g: i.c })));
      if (L.crashes) list.push(...map2d.crashes.map((c) => Object.assign(Object.create(c), { g: "crash" })));
      if (L.pets) list.push(...map2d.pets.filter((p) => typeof p.x === "number").map((p) => Object.assign(Object.create(p), { g: "pet-" + p.status })));
      map3d.setPlaces(list, { ...INC_COLORS(), crash: css("--ink"), ...PET_COLORS() });
    }
    else map3d.setPlaces(places.filter((p) => map2d.filter.has(p.g)), GROUP_COLORS);
  }
  function syncLegend() {
    const on = { inc: map2d.layers.incidents, cr: map2d.layers.crashes, pet: map2d.layers.pets };
    $("#inc-legend").hidden = !(on.inc || on.cr || on.pet);
    const in3d = !$("#gl-host").hidden;
    $$("#inc-legend [data-l]").forEach((el) => {
      el.hidden = !on[el.dataset.l] || (in3d && !!el.dataset.shape) || (!in3d && !!el.dataset["3d"]);
    });
  }
  function setLayer(key, btn, on, isSel) {
    map2d.layers[key] = on;
    $(btn).setAttribute("aria-pressed", String(on));
    syncLegend();
    map2d.hover = null; map2d.dirty = true;
    if (!on && map2d.sel && isSel(map2d.sel)) { map2d.sel = null; $("#card").hidden = true; }
    sync3DPins();
  }
  const setCrashes = (on) => setLayer("crashes", "#tcr", on, (p) => p.yr != null);
  const setIncidents = (on) => setLayer("incidents", "#tinc", on, (p) => p.d && p.k && p.yr == null);
  const setPetsLayer = (on) => setLayer("pets", "#tpet", on, (p) => !!p.status);
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

  function scrollToMap() { $("#explorer").scrollIntoView({ behavior: reduced ? "auto" : "smooth", block: "end" }); }
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

  /* ---------------- map card ---------------- */
  const PET_STATUS = { lost: "Lost", found: "Found", spotted: "Spotted" };
  function showCard(p) {
    const card = $("#card");
    if (!p) { card.hidden = true; return; }
    let top = "var(--ink)", html = "";
    if (p.msg) html = `<p class="msg">${esc(p.msg)}</p>`;
    else if (p.status) {
      top = `var(--pet-${esc(p.status)})`;
      html = `<p class="kicker"><span class="sw" style="background:${top}"></span>${esc(PET_STATUS[p.status] || "")} · ${esc(cap(p.animal))}</p>
        <h3>${p.name ? `“${esc(p.name)}”` : `${esc(PET_STATUS[p.status])} ${esc(p.animal || "pet")}`}</h3>
        <div class="lines">${p.desc ? `<p class="txt">${esc(p.desc)}</p>` : ""}
          ${p.near ? `<p><b>Last seen near</b> ${esc(p.near)}${p.town ? ", " + esc(p.town) : ""}</p>` : ""}
          <p>${esc(apDate(p.date))}${p.contact ? ` · <b>${esc(p.contact)}</b>` : ""}</p>
          ${p.url ? `<a href="${esc(p.url)}" target="_blank" rel="noopener">Listing on GitHub ›</a>` : ""}</div>
        <p class="meta">${p.prec === "street" ? "Pinned on the street named; the exact spot isn't known." : p.prec === "intersection" ? "Pinned at the intersection given." : "Pinned where the poster marked it."}</p>`;
    }
    else if (p.yr != null && p.col) {
      html = `<h3>${p.f ? "Fatal crash" : "Serious-injury crash"}</h3>
        <p class="plain"><span class="tri-key${p.f ? "" : " hollow"}"></span>${esc(p.col)}</p>
        <div class="lines"><p>${esc(apDate(p.mo ? `${p.yr}-${String(p.mo).padStart(2, "0")}` : String(p.yr)))} · ${esc(p.t)}</p>
          <p>${p.f ? `${p.f} killed` : ""}${p.f && p.s ? " · " : ""}${p.s ? `${p.s} seriously injured` : ""}</p>
          <p>${credit(safety.crashes?.source)}</p></div>
        <p class="meta">Location as recorded by the investigating police agency.</p>`;
    }
    else if (p.d && p.k && p.c) {
      const S = window.NKSafety;
      top = `var(--inc-${esc(p.c)})`;
      html = `<h3>${esc(S.TYPE[p.k] || p.k)}</h3>
        <p class="plain"><span class="inc-key${p.pi ? " pi" : ""}" style="background:${top}"></span>${esc(S.CAT[p.c] || "")}${p.pi ? " · police involved" : ""}</p>
        <div class="lines"><p>${esc(apDate(p.d))} · ${esc(p.t)}</p><p>${esc(p.l)}</p><p class="txt">${esc(p.s)}</p><p>${credit(p.src)}</p></div>
        <p class="meta">Location precision: ${esc(S.PREC[p.p] || p.p)}. Reported in the news; not a complete record.</p>`;
    }
    else if (p.street) {
      const s = p.street;
      html = `<p class="kicker">Street</p><h3>${streetHead(s.n)}${routes(s.ref)}</h3>
        <div class="lines"><p>${fmt(s.m)} m (${(s.m / 1609).toFixed(2)} mi) inside 15068${s.a ? ` · ${fmt(s.a)} addresses` : ""}</p>
        ${s.t.length ? `<p>Runs through ${esc(s.t.join(", "))}</p>` : ""}</div>`;
    } else {
      const col = GROUP_COLORS[p.g];
      top = col;
      html = `<p class="kicker"><span class="sw" style="background:${col}"></span>${esc(cap(p.c))} · ${esc(meta.groups[p.g])}</p><h3>${esc(p.n)}</h3>
        <div class="lines">
          ${p.a ? `<p>${esc(p.a)}</p>` : ""}
          ${p.ph ? `<p class="num">${esc(p.ph)}</p>` : ""}
          ${p.w ? `<a href="${esc(p.w)}" target="_blank" rel="noopener">Website</a>` : ""}
          <a href="https://www.google.com/maps/search/?api=1&query=${encodeURIComponent(p.n + " " + p.lat + "," + p.lon)}" target="_blank" rel="noopener">Directions ›</a>
          ${p.s ? `<a href="${esc(p.s)}" target="_blank" rel="noopener">${esc(/facebook\.com$/.test(pubName(p.s)) ? "Facebook page" : pubName(p.s))}</a>` : ""}
        </div>
        <p class="meta">${esc(p.t || "")}${p.t ? " · " : ""}${p.lat.toFixed(5)}, ${p.lon.toFixed(5)}${p.b ? " · chain: " + esc(p.b) : ""}</p>`;
    }
    card.style.setProperty("--card-top", top);
    card.innerHTML = `<button class="close" type="button" aria-label="Close">×</button>` + html;
    card.hidden = false;
    card.querySelector(".close").onclick = () => {
      card.hidden = true; map2d.sel = null; map2d.dirty = true;
      if (map2d.pickMode) { map2d.pickMode = null; map2d.c.style.cursor = ""; }
    };
  }

  /* ---------------- news river ---------------- */
  const sortedNews = () => [...(civic.news_2025_2026 || [])].sort((a, b) => String(b.date).localeCompare(String(a.date)));
  const newsTown = (a) => ["New Kensington", "Arnold", "Lower Burrell"].find((t) => (a.headline + " " + a.text).includes(t));
  function renderNews() {
    const n = sortedNews();
    if (!n.length) { $("#news-list").innerHTML = `<p class="empty">No news loaded.</p>`; return; }
    const kick = (a) => `<p class="kicker">${esc(apDate(a.date, a.date_note))}${newsTown(a) ? " · " + esc(newsTown(a)) : ""}</p>`;
    const [lead, ...rest] = n;
    const item = (a) => `<article>${kick(a)}<h3>${esc(a.headline)}</h3><p class="txt">${esc(a.text)}</p><p class="credit">${credit(a.source)}</p></article>`;
    $("#news-list").innerHTML = `
      <div class="stack"><article class="lead">${kick(lead)}<h3>${esc(lead.headline)}</h3><p class="txt">${esc(lead.text)}</p><p class="credit">${credit(lead.source)}</p></article>
        ${rest.slice(0, 3).map(item).join("")}</div>
      <div class="stack">${rest.slice(3, 8).map(item).join("")}</div>
      ${rest.length > 8 ? `<div><h3 class="lh">More headlines</h3><ul class="more-heads">${rest.slice(8).map((a) => `<li><time datetime="${esc(a.date)}">${esc(apDate(a.date, a.date_note))}</time><a href="${esc(a.source)}" target="_blank" rel="noopener">${esc(a.headline)}</a></li>`).join("")}</ul></div>` : ""}`;
  }

  /* ---------------- lost & found pets ---------------- */
  const LIMITS = window.NKPets?.LIMITS || { name: 40, desc: 500, near: 120, contact: 120 };
  const localToday = () => { const d = new Date(); return new Date(d - d.getTimezoneOffset() * 6e4).toISOString().slice(0, 10); };
  function nearestStreet(x, y) {
    let best = null, bd = 150 * 150;
    for (const l of W.lines) {
      if (!l.n) continue;
      for (let i = 0; i < l.pts.length; i += 2) {
        const d = (l.pts[i] - x) ** 2 + (l.pts[i + 1] - y) ** 2;
        if (d < bd) { bd = d; best = l.n; }
      }
    }
    return best;
  }
  function renderPets() {
    const items = petsInfo.items || [];
    $("#pets-res").innerHTML = items.map((r) => `<div class="entry"><p><b>${esc(String(r.name).replace(/\.$/, ""))}.</b> ${esc(r.what_to_use_it_for || "")}</p>
      <p class="meta">${[r.phone ? `<span class="num">${esc(r.phone)}</span>` : "", r.address ? esc(r.address) : "",
        r.url && r.url !== r.source ? `<a href="${esc(r.url)}" target="_blank" rel="noopener">Website</a>` : ""].filter(Boolean).join(" · ")}${r.phone || r.address || (r.url && r.url !== r.source) ? " · " : ""}${credit(r.source)}</p></div>`).join("")
      || `<p class="empty">Contact list not loaded.</p>`;
    $("#pets-tips").innerHTML = (petsInfo.tips || []).map((t) => `<li>${esc(t.tip)} <span class="credit">${credit(t.source)}</span></li>`).join("");
    if (!window.NKPets) { $("#pets-status").textContent = "The listings board didn't load."; return; }
    window.NKPets.init({ W, streets, ui: { onChange: drawPets } }).catch((e) => {
      console.warn(e);
      $("#pets-status").textContent = "The listings board couldn't load just now.";
    });
  }

  let placeBox = null, placeMode = null, picked = null;
  function buildPlaceBox(mode) {
    const P = window.NKPets;
    const box = document.createElement("div");
    box.className = "ad ad-place";
    if (mode === "db") {
      const today = localToday();
      box.innerHTML = `<h3>Place a free listing</h3>
        <p>Lost, found or spotted a pet in 15068? Post it here and it goes on the map for everyone who opens this page.</p>
        <button type="button" class="btn-line" id="pets-open" aria-expanded="false" aria-controls="pets-form">Write a listing</button>
        <form id="pets-form" hidden>
          <label>Lost, found or spotted?<select name="status" required><option value="lost">Lost</option><option value="found">Found</option><option value="spotted">Spotted</option></select></label>
          <label>Animal<select name="animal"><option value="dog">Dog</option><option value="cat">Cat</option><option value="other">Other</option></select></label>
          <label>Pet's name (if known)<input name="name" maxlength="${LIMITS.name}" autocomplete="off"></label>
          <label>Description<textarea name="desc" maxlength="${LIMITS.desc}" required placeholder="Breed, colour, size, collar or tags"></textarea></label>
          <label>Last seen near<input name="near" maxlength="${LIMITS.near}" required placeholder="Fifth Avenue & 9th Street" autocomplete="off"></label>
          <p><button type="button" class="linkbtn" id="pets-pick">Or pick the spot on the map</button> <span class="credit" id="pets-picked"></span></p>
          <label>Town<select name="town">${P.TOWNS.map((t) => `<option>${esc(t)}</option>`).join("")}</select></label>
          <label>Date<input type="date" name="date" required value="${today}" max="${today}"></label>
          <label>How to reach you (public)<input name="contact" maxlength="${LIMITS.contact}" required autocomplete="off"></label>
          <p class="fine">Everyone who can open this page sees the listing. Give a street and cross street rather than a house number; house numbers are removed.</p>
          <button type="submit" class="btn-line">Post the listing</button>
          <p class="form-msg" role="status"></p>
        </form>`;
      const form = box.querySelector("form"), openBtn = box.querySelector("#pets-open"), msg = box.querySelector(".form-msg");
      openBtn.onclick = () => { form.hidden = !form.hidden; openBtn.setAttribute("aria-expanded", String(!form.hidden)); if (!form.hidden) form.status.focus(); };
      box.querySelector("#pets-pick").onclick = () => {
        set3D(false); setPetsLayer(true); scrollToMap();
        showCard({ msg: "Click the map where the pet was last seen. Press Escape to cancel." });
        map2d.c.style.cursor = "crosshair";
        map2d.pickMode = (x, y) => {
          picked = { x: Math.round(x / 10) * 10, y: Math.round(y / 10) * 10 };
          const st = nearestStreet(x, y);
          if (st && !form.near.value.trim()) form.near.value = st;
          box.querySelector("#pets-picked").textContent = st ? `Spot set near ${st}.` : "Spot set.";
          showCard(null);
          $("#pets").scrollIntoView({ behavior: reduced ? "auto" : "smooth" });
        };
      };
      form.onsubmit = async (e) => {
        e.preventDefault();
        const f = new FormData(form), post = {};
        for (const k of ["status", "animal", "name", "desc", "near", "town", "date", "contact"]) post[k] = String(f.get(k) || "").trim().slice(0, LIMITS[k] || 40);
        post.near = P.cleanNear(post.near);
        if (picked) Object.assign(post, picked, { prec: "picked" });
        else {
          const g = P.geocodeNear(post.near, post.town);
          if (g) Object.assign(post, { x: Math.round(g.x), y: Math.round(g.y), prec: g.prec });
        }
        msg.textContent = "Posting…";
        try {
          await P.addPost(post);
          form.reset(); form.date.value = form.date.max = localToday(); picked = null;
          box.querySelector("#pets-picked").textContent = "";
          msg.textContent = typeof post.x === "number" ? "Posted. It's on the map." : "Posted. That street wasn't found on the map, so the listing has no pin.";
        } catch (err) {
          msg.textContent = err.message || "It didn't post. Try again in a minute.";
          if (P.board.readOnly) { form.querySelectorAll("input, select, textarea, button").forEach((el) => { el.disabled = true; }); }
        }
      };
    } else {
      box.innerHTML = `<h3>Place a free listing</h3>
        <p>Listings are posted through a short form on the NK15068 GitHub project, which needs a free GitHub account. Close the post when your pet is home and the listing comes down.</p>
        <p><a class="act" href="${esc(P.ISSUE_FORM)}" target="_blank" rel="noopener">Post it on GitHub ›</a></p>`;
    }
    return box;
  }
  function drawPets(posts) {
    const P = window.NKPets, B = P.board;
    map2d.setPets(posts);
    if (map2d.layers.pets) sync3DPins();
    const n = posts.length;
    $("#pets-status").textContent = B.error || (B.mode === "loading" ? "Loading listings…"
      : B.mode === "db" ? "Listings posted here are shared with everyone who opens this page. Mark yours reunited when your pet is home."
      : "Listings come from lost and found posts on the NK15068 GitHub project and stay up until they're closed.");
    const list = $("#pets-list");
    list.querySelectorAll(":scope > .ad:not(.ad-place)").forEach((n) => n.remove());
    const cards = posts.map((p, i) => `<article class="ad" data-status="${esc(p.status)}">
        ${p.photo ? `<img src="${esc(p.photo)}" alt="Photo of ${esc(p.name || "the " + (p.animal || "pet"))}" loading="lazy">` : ""}
        <p class="ad-st">${esc(PET_STATUS[p.status])} · ${esc(p.animal || "pet")}</p>
        ${p.name ? `<h3>“${esc(p.name)}”</h3>` : ""}
        ${p.desc ? `<p>${esc(p.desc)}</p>` : ""}
        ${p.near ? `<p><b>Last seen near</b> ${esc(p.near)}${p.town ? ", " + esc(p.town) : ""}</p>` : ""}
        <p class="ad-date">${esc(apDate(p.date))}</p>
        ${p.contact ? `<p class="ad-contact">${esc(p.contact)}</p>` : ""}
        <p class="ad-acts">${typeof p.x === "number" ? `<button type="button" class="linkbtn" data-pet="${i}">Map it</button>` : `<span class="muted">No pin: street not found</span>`}
          ${p.url ? `<a class="linkbtn" href="${esc(p.url)}" target="_blank" rel="noopener">Post on GitHub</a>` : ""}
          ${p.owner ? `<button type="button" class="linkbtn" data-reunite="${esc(p.id)}">Mark reunited</button>` : ""}</p>
      </article>`).join("") + (n || B.mode === "loading" ? "" : `<div class="ad empty-ad"><p>No open listings right now.</p></div>`);
    if (placeBox && placeBox.parentNode === list) placeBox.insertAdjacentHTML("beforebegin", cards);
    else list.insertAdjacentHTML("afterbegin", cards);
    if (B.mode !== "loading") {
      const want = B.mode === "db" && B.canPost ? "db" : "github";
      if (placeMode !== want) { placeBox?.remove(); placeBox = buildPlaceBox(want); placeMode = want; list.appendChild(placeBox); }
    }
    const line = $("#pets-line");
    line.hidden = !n;
    line.innerHTML = n ? `<a href="#pets">Lost and found pets: ${fmt(n)} open listing${n === 1 ? "" : "s"} ›</a>` : "";
  }
  $("#pets-list").addEventListener("click", async (e) => {
    const m = e.target.closest("[data-pet]");
    if (m) {
      const p = window.NKPets.board.posts[+m.dataset.pet];
      if (!p || typeof p.x !== "number") return;
      set3D(false); setPetsLayer(true); scrollToMap();
      map2d.flyTo(p.x, p.y, 2.2); map2d.select(p);
      return;
    }
    const r = e.target.closest("[data-reunite]");
    if (r) {
      r.disabled = true;
      try { await window.NKPets.markReunited(r.dataset.reunite); } catch (err) { r.disabled = false; $("#pets-status").textContent = err.message || "That didn't save. Try again in a minute."; }
    }
  });

  /* ---------------- towns ---------------- */
  function renderTowns() {
    const d = civic.demographics || {};
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
    const row = (k, v) => `<div><dt>${k}</dt><dd>${v}</dd></div>`;
    grid.innerHTML = meta.towns.filter((t) => t.core).sort((a, b) => order.indexOf(a.n) - order.indexOf(b.n)).map((t, idx) => {
      const i = info[t.n] || {}, dm = i.demo || {};
      return `<article class="town${idx === 0 ? " lead" : ""}">
        <canvas data-town="${esc(t.n)}" role="img" aria-label="Street map of ${esc(t.n)}"></canvas>
        <p class="caption">Street map of ${esc(t.n)}. State routes in orange.</p>
        <h3>${esc(t.n)}</h3>
        ${i.inc ? `<p class="inc">${esc(i.inc)}</p>` : ""}
        <p class="desc">${esc(i.text || "")}</p>
        <dl class="agate">
          ${dm.population_2020 ? row("Population (2020)", fmt(dm.population_2020)) : ""}
          ${dm.median_household_income ? row("Median household income", "$" + fmt(dm.median_household_income)) : ""}
          ${row("Buildings mapped", fmt(meta.stats.buildings_by_town[t.n] || 0))}
          ${row("Address points", fmt(meta.stats.addresses_by_town[t.n] || 0))}
          ${row("Places listed", fmt(byTown[t.n] || 0))}
        </dl>
        ${dm.source ? `<p class="credit">${credit(dm.source)}</p>` : ""}
      </article>`;
    }).join("");
    drawTowns = () => grid.querySelectorAll("canvas").forEach((c) => drawTown(c, W.towns.find((t) => t.n === c.dataset.town)));
    drawTowns();
    new ResizeObserver(() => drawTowns()).observe(grid);
  }
  function drawTown(c, t) {
    if (!t) return;
    const raw = W.base.towns.find((x) => x.n === t.n);
    let x0 = Infinity, y0 = Infinity, x1 = -Infinity, y1 = -Infinity;
    raw.r.forEach((r) => { const p = dec(r, W.q); for (let i = 0; i < p.length; i += 2) { x0 = Math.min(x0, p[i]); x1 = Math.max(x1, p[i]); y0 = Math.min(y0, p[i + 1]); y1 = Math.max(y1, p[i + 1]); } });
    const r = c.getBoundingClientRect(), dpr = Math.min(2, devicePixelRatio || 1);
    if (!r.width) return;
    c.width = r.width * dpr; c.height = r.height * dpr;
    const ctx = c.getContext("2d");
    const s = Math.min(r.width / (x1 - x0), r.height / (y1 - y0)) * 0.9;
    ctx.setTransform(dpr * s, 0, 0, dpr * s, dpr * (r.width / 2 - (x0 + x1) / 2 * s), dpr * (r.height / 2 - (y0 + y1) / 2 * s));
    ctx.fillStyle = css("--map-bg"); ctx.fillRect(x0 - 1e4, y0 - 1e4, 3e4, 3e4);
    ctx.fillStyle = css("--river-soft"); ctx.fill(W.water);
    ctx.save(); ctx.clip(t.p);
    ctx.fillStyle = css("--map-land"); ctx.fill(t.p);
    ctx.lineCap = ctx.lineJoin = "round";
    const route = css("--route"), minor = css("--ink-2");
    for (let k = 5; k >= 0; k--) {
      ctx.strokeStyle = k <= 2 ? route : minor;
      ctx.globalAlpha = k <= 2 ? .9 : .5;
      ctx.lineWidth = (k <= 2 ? 1.8 : k === 5 ? .5 : .9) / s;
      ctx.stroke(W.roads[k]);
    }
    ctx.restore();
    ctx.globalAlpha = 1; ctx.lineWidth = 1.5 / s; ctx.strokeStyle = css("--boundary");
    ctx.setLineDash([6 / s, 4 / s]); ctx.stroke(t.p); ctx.setLineDash([]);
  }

  /* ---------------- history ---------------- */
  function renderStory() {
    const tl = history.timeline || [];
    const f = history.facts || {};
    const pops = Object.entries(f.population_by_census || {}).map(([y, v]) => [+y, v]).sort((a, b) => a[0] - b[0]);
    if (pops.length) {
      const RH = 26, Wd = 320, X0 = 44, span = Wd - X0 - 56, max = Math.max(...pops.map((p) => p[1]));
      const bars = pops.map(([yr, v], i) => {
        const y = i * RH, w = v / max * span;
        return `<text x="0" y="${y + 17}" font-size="12" fill="var(--muted)" font-family="var(--f-sans)">${yr}</text>
          <rect x="${X0}" y="${y + 5}" width="${w.toFixed(1)}" height="15" fill="${v === max ? "var(--river-peak)" : "var(--river)"}"/>
          <text x="${(X0 + w + 6).toFixed(1)}" y="${y + 17}" font-size="12" font-weight="600" fill="var(--ink)" font-family="var(--f-sans)">${fmt(v)}</text>`;
      }).join("");
      const popSrc = tl.filter((e) => /^population/i.test(e.title)).map((e) => e.source);
      $("#pop-chart").innerHTML = `<svg viewBox="0 0 ${Wd} ${pops.length * RH}" width="100%" role="img" aria-label="New Kensington population by census year: ${pops.map(([y, v]) => `${y} ${fmt(v)}`).join(", ")}">${bars}</svg>
        <p class="credit">${esc(f.population_note || "")} ${credit(popSrc)}</p>`;
    }
    const item = (e) => `<div class="tl-item"><div class="yr">${esc(e.year)}</div><p><b>${endStop(e.title)}</b> ${esc(e.text)}${e.note ? ` <span class="tl-note">Note: ${esc(e.note)}</span>` : ""} <span class="credit">${credit(e.source)}</span></p></div>`;
    const sorted = [...tl].sort((a, b) => a.year - b.year);
    let open = false;
    const draw = () => {
      $("#timeline").innerHTML = (open ? sorted : sorted.filter((_, i) => i % Math.ceil(sorted.length / 14) === 0)).map(item).join("") || `<p class="empty">Timeline data not available.</p>`;
      $("#tl-more").textContent = open ? "Show fewer" : `Show all ${sorted.length} entries ›`;
      $("#tl-more").hidden = sorted.length <= 14;
    };
    draw();
    $("#tl-more").onclick = () => { open = !open; draw(); refitRails(); if (!open) $("#story").scrollIntoView({ behavior: reduced ? "auto" : "smooth" }); };
    const gloss = (title, list) => {
      if (!list.length) return "";
      return `<h3 class="sub-h">${title}</h3><div class="runin${list.length < 3 ? " few" : ""}">${list.map((l) => {
        const hit = matchPlace(l.name, l.address);
        return `<div class="entry"><p><b>${endStop(l.name)}</b> ${esc(l.text)}</p>
          <p class="meta">${l.address ? esc(l.address) + " · " : ""}${hit ? `<a href="#map" data-go="${hit.id}">Map it</a> · ` : ""}${credit(l.source)}</p></div>`;
      }).join("")}</div>`;
    };
    $("#landmarks").innerHTML = gloss("Neighborhoods", history.neighborhoods || []) + gloss("Landmarks and historic districts", history.landmarks || []);
  }

  /* ---------------- eat & drink + calendar ---------------- */
  const BUCKETS = [
    ["Restaurants and diners", /restaurant|diner|pizza|grill|italian|kitchen|sandwich|wing|burger|deli/i],
    ["Bars, breweries and clubs", /bar|pub|brew|tavern|club|lounge|distill|winery/i],
    ["Bakeries, cafés and sweets", /baker|caf|coffee|ice cream|sweet|donut|dessert|candy/i],
    ["Venues", /venue|hall|event|theat/i],
    ["Other", /.*/],
  ];
  function renderEat() {
    const list = civic.food_and_culture || [];
    $("#eat-deck").textContent = `${fmt(list.length)} restaurants, bars, bakeries and clubs with a published write-up. Select one to find it on the map.`;
    const groups = BUCKETS.map(([t]) => [t, []]);
    list.forEach((f) => groups[BUCKETS.findIndex(([, re]) => re.test(f.type || ""))][1].push(f));
    $("#eat-list").innerHTML = groups.filter(([, g]) => g.length).map(([t, g]) => `<h3 class="sub-h">${esc(t)}</h3><div class="bucket${g.length < 3 ? " few" : ""}">${g.map((f) => {
      const hit = matchPlace(f.name, f.address);
      return `<div class="dine"><div class="l1"><b>${esc(f.name)}</b>${f.address ? `<span class="lead-dots"></span><span class="addr">${esc(shortAddr(f.address))}</span>` : ""}</div>
        <p class="l2">${f.type ? `<i>${esc(cap(f.type.replace(/\//g, ", ")))}.</i> ` : ""}${esc(f.text)}</p>
        <p class="l3">${hit ? `<a href="#map" data-go="${hit.id}">Map it</a> · ` : ""}${credit(f.source)}</p></div>`;
    }).join("")}</div>`).join("") || `<p class="empty">No listings loaded.</p>`;
    $("#events").innerHTML = (history.events || []).map((e) => `<div class="event"><p class="when">${esc(e.when)}</p>
      <p><b>${endStop(e.name)}</b> ${esc(e.text)}</p>${e.where ? `<p class="where">${esc(e.where)}</p>` : ""}<p class="credit">${credit(e.source)}</p></div>`).join("") || `<p class="empty">No events loaded.</p>`;
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
    let tab = "places", limit = 100;
    $("#dir-tabs").innerHTML = tabs.map(([k, v], i) => `<button class="tab" type="button" role="tab" data-t="${k}" aria-selected="${i === 0}" aria-controls="dir-table">${esc(v)}</button>`).join("");
    const offices = [...(civic.government || []), ...(civic.parks_and_rec || []).map((p) => ({ ...p, role: p.text }))];
    const q = $("#dir-q");
    function draw() {
      const t = q.value.trim().toLowerCase();
      let rows, head;
      if (tab === "places") {
        head = "<tr><th>Name</th><th>Type</th><th>Town</th><th>Address</th><th>Phone</th></tr>";
        const f = places.filter((p) => !t || (p.n + " " + p.c + " " + (p.t || "") + " " + (p.a || "") + " " + meta.groups[p.g]).toLowerCase().includes(t));
        rows = [f.length, f.slice(0, limit).map((p) => `<tr data-go="${p.id}"><td><span class="dot" style="background:${GROUP_COLORS[p.g]}"></span>${esc(p.n)}<span class="sub">${esc(meta.groups[p.g])}</span></td><td>${esc(p.c)}</td><td>${esc(p.t || "")}</td><td>${esc(p.a || "")}</td><td class="num">${esc(p.ph || "")}</td></tr>`)];
      } else if (tab === "streets") {
        head = `<tr><th>Street</th><th>Town</th><th class="num">Length</th><th class="num">Addresses</th></tr>`;
        const f = streets.filter((s) => !t || (s.n + " " + s.t.join(" ") + " " + s.ref.join(" ")).toLowerCase().includes(t));
        rows = [f.length, f.slice(0, limit).map((s) => `<tr data-go="s:${esc(s.n)}"><td>${esc(s.n)}${routes(s.ref)}</td><td>${esc(s.t.join(", "))}</td><td class="num">${fmt(s.m)} m</td><td class="num">${s.a ? fmt(s.a) : "–"}</td></tr>`)];
      } else {
        head = "<tr><th>Office</th><th>What</th><th>Address</th><th>Phone</th></tr>";
        const f = offices.filter((o) => !t || JSON.stringify(o).toLowerCase().includes(t));
        rows = [f.length, f.slice(0, limit).map((o) => `<tr><td>${o.url || o.source ? `<a href="${esc(o.url || o.source)}" target="_blank" rel="noopener">${esc(o.name)}</a>` : esc(o.name)}</td><td>${esc(o.role || "")}</td><td>${esc(o.address || "")}</td><td class="num">${esc(o.phone || "")}</td></tr>`)];
      }
      $("#dir-table").innerHTML = `<thead>${head}</thead><tbody>${rows[1].join("") || `<tr><td colspan="5" class="empty">Nothing matches “${esc(q.value)}”.</td></tr>`}</tbody>`;
      $("#dir-count").textContent = `Showing ${fmt(Math.min(limit, rows[0]))} of ${fmt(rows[0])}`;
      $("#dir-more").hidden = rows[0] <= limit;
      $("#dir-more").textContent = `Show ${fmt(Math.min(100, rows[0] - limit))} more`;
    }
    $("#dir-tabs").addEventListener("click", (e) => {
      const b = e.target.closest(".tab"); if (!b) return;
      tab = b.dataset.t; limit = 100;
      $$(".tab", $("#dir-tabs")).forEach((x) => x.setAttribute("aria-selected", String(x === b)));
      draw();
    });
    q.addEventListener("input", () => { limit = 100; draw(); });
    $("#dir-more").onclick = () => { limit += 100; draw(); };
    draw();
  }

  /* ---------------- people / sources ---------------- */
  function renderPeople() {
    $("#people-list").innerHTML = (history.people || []).map((p) => `<div class="person"><b>${esc(p.name)}</b><p class="kf">${endStop(cap(p.known_for))}</p>
      ${p.connection ? `<p class="conn">${esc(p.connection)}</p>` : ""}<p class="credit">${credit(p.source)}</p></div>`).join("") || `<p class="empty">No people loaded.</p>`;
  }
  function renderSources() {
    const notes = [history._meta, civic._meta, petsInfo.compiled ? { compiled: petsInfo.compiled, method: petsInfo.method } : null].filter((m) => m && m.compiled);
    $("#src-list").innerHTML = meta.sources.map((s) => `<div><a href="${esc(s.url)}" target="_blank" rel="noopener">${esc(s.name)}</a> · ${esc(s.license)}</div>`).join("");
    $("#src-notes").innerHTML = notes.map((m) => `<p>Research compiled ${esc(apDate(m.compiled))}. ${esc(m.method || "")}</p>`).join("");
  }

  boot().catch((e) => {
    console.error(e);
    $("#map-loading").textContent = "The map data didn't load. Serve this folder over HTTP (for example: python -m http.server) and reload.";
  });
})();
