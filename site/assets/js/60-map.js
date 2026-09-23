/* NK15068 — the map pages: /map/ (the 2D map: search panel, layers, cards, deep links, near-me), /map/3d/,
   /directory/ (places and streets A to Z) and /search/.
   The HTML holds every label; this file draws the map (nkmap.js), fills cards and results, and keeps the view in the URL
   with NKS.setQS (replaceState, so one Back always leaves the page). Coordinates from "Use my location" are never
   stored or sent: only the street label is kept, and only when "Remember on this phone" is ticked. */
(function () {
  "use strict";
  const S = window.NKS;
  if (!S) return;
  const { $, $$, esc, fmt } = S;
  const isPhone = () => matchMedia("(max-width: 719px)").matches;
  const DOWNTOWN = [-3350, -40];
  const TOWN_NAME = { Allegheny: "Allegheny Township" };
  const townName = (t) => TOWN_NAME[t] || t;
  const plural = (n, one, many) => (n === 1 ? one : many || one + "s");
  const HALF_MILE = 804.672;
  /* "300 ft" under 0.1 mi (rounded to 50), else "0.4 mi" */
  const dist = (m) => { const mi = m / 1609.344; return mi < 0.1 ? `${Math.max(50, Math.round(m * 3.28084 / 50) * 50)} ft` : `${mi.toFixed(1)} mi`; };
  const readJSON = (sel) => { try { return JSON.parse($(sel)?.textContent || "null"); } catch (e) { return null; } };
  const wait = (ms) => new Promise((r) => setTimeout(r, ms));
  const flash = (btn, text) => { const was = btn.textContent; btn.textContent = text; setTimeout(() => { btn.textContent = was; }, 1800); };

  /* ---------------- places: the directory's de-duplication, town labels, map links (same rules as pages_map.py) ---------------- */
  const normName = (s) => String(s || "").toLowerCase().replace(/\b(new kensington|lower burrell|arnold|the|pa)\b/g, "").replace(/[^a-z0-9]/g, "");
  function dedupeKey(p) {
    const d = String(p.ph || "").replace(/\D/g, "");
    return d ? `${d}|${normName(p.n)}` : `${normName(p.n)}|${Math.floor(p.x / 50)},${Math.floor(p.y / 50)}`;
  }
  function dedupe(places) {
    const best = new Map();
    for (const p of places) { const k = dedupeKey(p), b = best.get(k); if (!b || (p.q || 0) > (b.q || 0)) best.set(k, p); }
    const keep = new Set(best.values());
    return places.filter((p) => keep.has(p));
  }
  const FIX_CITY = { "new kensington": "New Kensington", "new kensingtn": "New Kensington", "new kinsington": "New Kensington",
    "lower burrell": "Lower Burrell", arnold: "Arnold" };
  function townLabel(p) {
    const parts = String(p.a || "").split(",").map((s) => s.trim());
    return (parts.length >= 2 && FIX_CITY[parts[1].toLowerCase().replace(/-/g, " ")]) || p.t || "";
  }
  const slug = (s) => String(s || "").normalize("NFKD").replace(/[^\x00-\x7f]/g, "").toLowerCase().replace(/[^a-z0-9]+/g, "-").replace(/^-+|-+$/g, "");
  const placeParam = (p) => `${slug(p.n)}~${Math.round(p.x)},${Math.round(p.y)}`;
  const mapURL = (k, v) => `${S.url("map/")}?${k}=${encodeURIComponent(v).replace(/%2C/g, ",").replace(/%7E/g, "~").replace(/%20/g, "+")}`;
  const aToZ = (a, b) => { const x = a.n.toLowerCase(), y = b.n.toLowerCase(); return x < y ? -1 : x > y ? 1 : (b.q || 0) - (a.q || 0); };
  function social(u) {
    const h = S.pubName(u);
    return /facebook\.com$/.test(h) ? "Facebook page" : /instagram\.com$/.test(h) ? "Instagram" : h;
  }

  /* ---------------- street keys and incident locations (as the blotter matches them) ---------------- */
  const streetKey = (n) => (window.NKSafety && window.NKSafety.streetKey ? window.NKSafety.streetKey(n)
    : window.NKSearch ? window.NKSearch.streetKey(n) : window.NKPets ? window.NKPets.streetKey(n) : null);
  const typeOk = (a, b) => !a || !b || a === b;
  function incStreets(i) {
    if (i.p === "place") return [];
    let l = String(i.l || "");
    if (i.p === "block") l = l.replace(/^\d+\s+block\s+of\s+/i, "");
    return l.split("&").map((s) => s.trim()).filter(Boolean);
  }
  const incNames = (i, k) => incStreets(i).some((n) => { const x = streetKey(n); return x && x.core === k.core && typeOk(k.type, x.type); });

  /* ======================================================================== /map/ */
  S.pages.map = () => mapPage().catch((e) => { console.warn(e); });

  async function mapPage() {
    const NK = window.NK, ex = $("#explorer"), canvas = $("#map-canvas"), loading = $("#map-loading"), card = $("#card");
    if (!NK || !ex || !canvas || !card) return;
    const cap = loading && loading.querySelector("figcaption");
    const Q = S.qs();
    let meta, W, places, streets;
    try {
      [meta, W, places, streets] = await Promise.all([NK.getJSON("meta.json"), NK.loadWorld({ keepLines: true }),
        NK.getJSON("places.json"), NK.getJSON("streets.json")]);
    } catch (e) {
      console.warn(e);
      if (cap) cap.textContent = "The map data didn't load just now. Check your connection and reload the page.";
      return;
    }
    places.forEach((p, i) => { p.id = i; });
    const police = (readJSON("#map-data") || {}).police || {};
    const map = new NK.Map2D(canvas, W, {
      initial: [-5200, -1700, -1400, 1700], scaleEl: $("#scale"), hold: true,
      onSelect: (p) => pick(p),
      onView: (v) => S.setQS({ at: `${Math.round(v.x)},${Math.round(v.y)},${+v.s.toFixed(3)}` }),
    });
    map.hold = true;
    map.setData(places, streets);
    NK.getTerrain(meta).then((T) => { map.terrain = T; map.dirty = true; }).catch((e) => console.warn(e));
    NK.loadBuildings(W).then((b) => { map.bld = b; map.dirty = true; }).catch((e) => console.warn(e));
    const L = map.layers;
    let settled = false, arriving = true, atSet = false;
    window.NKdebug = {
      get labels() { return settled ? map.drawnLabels.slice() : []; },
      get highlight() { return map.hl ? map.hl.name : null; },
      petDots: (id) => map.petDrawn.get(id) || 0,
      pin(id) {
        const p = map.pets.find((x) => x.id === id), pin = p && map.petPin(p);
        if (!pin) return null;
        const r = canvas.getBoundingClientRect();
        return { x: r.left + pin.x, y: r.top + pin.y };
      },
      view: () => map.view(),
    };

    /* ---------- where things go: on phone a selected point sits at 35% of the height, above the sheet ---------- */
    /* on a wide screen the card covers the left column, so things are centred in what's left */
    const offY = () => (isPhone() ? 0.15 * map.h : 0);
    const offX = () => (!isPhone() && map.w >= 900 ? 200 : 0);
    function go(x, y, s) {
      if (arriving && atSet) return;
      if (arriving) map.setView(x - offX() / s, y + offY() / s, s);
      else map.flyTo(x, y, s, { offsetX: offX(), offsetY: offY() });
    }
    const inset = () => (isPhone() ? { top: 64, bottom: 160 } : { top: 40, bottom: 30, left: map.w >= 900 ? 410 : 0, right: 70 });
    function fitBox(b) { if (!(arriving && atSet)) map.fitView(b, inset(), 3); }
    function fitPoints(pts, pad = 250) {
      if (!pts.length) return;
      let x0 = Infinity, y0 = Infinity, x1 = -Infinity, y1 = -Infinity;
      pts.forEach((p) => { x0 = Math.min(x0, p.x); x1 = Math.max(x1, p.x); y0 = Math.min(y0, p.y); y1 = Math.max(y1, p.y); });
      fitBox([x0 - pad, y0 - pad, x1 + pad, y1 + pad]);
    }

    /* ---------- the selection lives in the URL: one of place, street, near, pet, inc ---------- */
    const SEL = ["place", "street", "near", "pet", "inc"];
    function setSel(k, v) {
      const o = {};
      SEL.forEach((x) => { o[x] = null; });
      if (k) { o[k] = v; o.at = null; } // the selection sets the view; a later pan writes ?at= again
      S.setQS(o);
    }
    function clearMarks() { map.focus = null; map.here = null; map.highlightStreet(null); }

    /* ---------- lazy data: crime incidents and crashes ---------- */
    let safety = null, safetyP = null;
    function loadSafety() {
      if (!safetyP) {
        safetyP = NK.getJSON("safety.json").then((s) => {
          const inc = s.incidents || [];
          const ids = window.NKSafety ? window.NKSafety.incIds(inc) : inc.map((i, k) => String(k));
          inc.forEach((i, k) => { i.id = ids[k]; });
          map.setIncidents(inc);
          map.setCrashes((s.crashes && s.crashes.points) || []);
          safety = s;
          return s;
        });
        safetyP.catch(() => { safetyP = null; });
      }
      return safetyP;
    }

    /* ---------- the pets board ---------- */
    const P = window.NKPets;
    let petsDefault = !Q.has("layer");
    const boardP = P ? P.init({ W, streets, ui: { onChange: onPets } }).catch((e) => console.warn(e)) : Promise.resolve();
    function onPets(posts) {
      map.setPets(posts);
      if (petsDefault && P.board.known && posts.length) { petsDefault = false; setLayer("pets", true); }
    }

    /* ---------- layers ---------- */
    const lb = $("#layers-btn"), pop = $("#layers-pop");
    const setPop = (open) => { if (!pop || !lb) return; pop.hidden = !open; lb.setAttribute("aria-expanded", String(open)); };
    if (lb) lb.addEventListener("click", (e) => { e.stopPropagation(); setPop(pop.hidden); });
    document.addEventListener("click", (e) => { if (pop && !pop.hidden && !pop.contains(e.target) && !lb.contains(e.target)) setPop(false); });
    const LAYER_BTN = { pets: "#tpet", incidents: "#tinc", crashes: "#tcr", buildings: "#tbld", relief: "#trel" };
    const OVERLAYS = ["pets", "incidents", "crashes"];
    function syncLegend() {
      const on = { pet: L.pets, inc: L.incidents, cr: L.crashes };
      const lg = $("#inc-legend");
      if (!lg) return;
      lg.hidden = !(on.pet || on.inc || on.cr);
      $$("[data-l]", lg).forEach((el) => { el.hidden = !on[el.dataset.l]; });
    }
    async function setLayer(key, on, { write = false } = {}) {
      if ((key === "incidents" || key === "crashes") && on) {
        try { await loadSafety(); } catch (e) { console.warn(e); showMsg("The crime and crash data didn't load just now. Try again in a minute."); return; }
      }
      L[key] = on;
      const b = $(LAYER_BTN[key]);
      if (b) b.setAttribute("aria-pressed", String(on));
      map.hover = null; map.dirty = true;
      syncLegend();
      if (!on && map.sel && ((key === "pets" && map.sel.status) || (key === "crashes" && map.sel.yr != null) || (key === "incidents" && map.sel.k && map.sel.d))) closeCard();
      if (write) S.setQS({ layer: OVERLAYS.filter((k) => L[k]).join(",") || "none" });
    }
    Object.entries(LAYER_BTN).forEach(([key, sel]) => {
      const b = $(sel);
      if (b) b.addEventListener("click", () => { if (key === "pets") petsDefault = false; setLayer(key, !L[key], { write: OVERLAYS.includes(key) }); });
    });
    const zoomBy = (f) => { map.touched = true; map.zoomAt(f, map.w / 2, map.h / 2); };
    $("#zin")?.addEventListener("click", () => zoomBy(1.6));
    $("#zout")?.addEventListener("click", () => zoomBy(1 / 1.6));
    $("#home")?.addEventListener("click", () => { setPop(false); map.touched = true; const b = meta.bounds; map.fitView([b[0] + 300, b[1] + 300, b[2] - 300, b[3] - 300]); });
    $("#dt")?.addEventListener("click", () => { setPop(false); map.touched = true; map.flyTo(DOWNTOWN[0], DOWNTOWN[1], 1.3); });

    /* ---------- incident filters from the blotter's "Show these on the map" link ---------- */
    const layerParam = Q.has("layer") ? Q.get("layer").split(",") : [];
    const withInc = layerParam.includes("incidents");
    const F = { t: withInc ? Q.get("town") || "" : "", y: withInc ? Q.get("year") || "" : "", st: withInc ? (Q.get("street") || "").slice(0, 60) : "", c: withInc ? Q.get("c") || "" : "" };
    function incFilter() {
      const k = F.st ? streetKey(F.st) : null;
      return (i) => (!F.c || i.c === F.c) && (!F.t || i.t === F.t) && (!F.y || String(i.d).slice(0, 4) === F.y) && (!F.st || (k && incNames(i, k)));
    }
    const filtered = () => !!(F.c || F.t || F.y || F.st);
    function showFilterNote() {
      const lg = $("#inc-legend");
      if (!lg || !filtered()) return;
      const CAT = (window.NKSafety && window.NKSafety.CAT) || {};
      const what = [F.c && CAT[F.c], F.t, F.y, F.st].filter(Boolean).join(" · ");
      lg.insertAdjacentHTML("beforeend", `<p class="lg-filter" data-l="inc">Showing ${esc(what)} <button type="button" class="linkbtn" id="inc-all">Show all</button></p>`);
      $("#inc-all").addEventListener("click", () => {
        F.c = F.t = F.y = F.st = "";
        map.incVisible = () => true; map.dirty = true;
        $(".lg-filter", lg)?.remove();
        S.setQS({ town: null, year: null, street: null, c: null });
      });
    }

    /* ---------- category chips; on phone they open from the Filter button ---------- */
    const chips = $("#chips"), fb = $("#filter-btn");
    if (chips) {
      const counts = {};
      places.forEach((p) => { counts[p.g] = (counts[p.g] || 0) + 1; });
      chips.innerHTML = `<button class="chip" type="button" data-g="*" aria-pressed="true">All ${fmt(places.length)}</button>` +
        Object.entries(meta.groups).filter(([k]) => counts[k]).map(([k, v]) =>
          `<button class="chip" type="button" data-g="${k}" aria-pressed="false"><i style="background:${NK.GROUP_COLORS[k]}"></i>${esc(v)}</button>`).join("");
      const setCat = (g, write) => {
        if (g !== "*" && !meta.groups[g]) g = "*";
        $$(".chip", chips).forEach((x) => x.setAttribute("aria-pressed", String(x.dataset.g === g)));
        map.filter = new Set(g === "*" ? Object.keys(NK.GROUP_COLORS) : [g]);
        map.dirty = true;
        if (write) S.setQS({ cat: g === "*" ? null : g });
      };
      chips.addEventListener("click", (e) => { const b = e.target.closest(".chip"); if (b) setCat(b.dataset.g, true); });
      if (Q.get("cat")) setCat(Q.get("cat"), false);
      if (fb) fb.addEventListener("click", () => {
        const open = !chips.hasAttribute("data-open");
        chips.toggleAttribute("data-open", open);
        fb.setAttribute("aria-expanded", String(open));
      });
    }

    /* ---------- the card: a panel on desktop, a bottom sheet with a 140 px peek on phone ---------- */
    let cardKind = null;
    /* phone: zoom and scale sit above the sheet; desktop: the card stops short of the search panel */
    const panel = $("#search-panel");
    function syncSheet() {
      const phone = isPhone();
      ex.style.setProperty("--sheet", !card.hidden && phone ? card.offsetHeight + "px" : "0px");
      if (phone || !panel) { card.style.maxHeight = ""; return; }
      const r = $("#results"), ph = panel.offsetHeight - (r && !r.hidden ? r.offsetHeight : 0);
      card.style.maxHeight = Math.max(160, ex.clientHeight - panel.offsetTop - ph - 26) + "px";
    }
    if (window.ResizeObserver && chips) new ResizeObserver(syncSheet).observe(chips);
    if (window.ResizeObserver) new ResizeObserver(syncSheet).observe(card);
    addEventListener("resize", syncSheet);
    function setSheet(state) {
      card.dataset.sheet = state;
      const g = $(".sheet-grip", card);
      if (g) { g.setAttribute("aria-expanded", String(state === "full")); g.setAttribute("aria-label", state === "full" ? "Show less" : "Show more"); }
      syncSheet();
    }
    function showCard(html, { top = "var(--ink)", kind = "msg" } = {}) {
      cardKind = kind;
      card.dataset.kind = kind;
      card.style.setProperty("--card-top", top);
      card.innerHTML = `<button class="sheet-grip" type="button" aria-expanded="false" aria-label="Show more"><span></span></button>`
        + `<button class="close" type="button" aria-label="Close">×</button><div class="card-in">${html}</div>`;
      card.hidden = false;
      card.scrollTop = 0;
      setSheet("peek");
      S.relabel(card);
    }
    const showMsg = (text, extra = "") => showCard(`<p class="msg">${esc(text)}</p>${extra}`);
    function closeCard() {
      card.hidden = true; cardKind = null;
      map.sel = null; clearMarks(); map.dirty = true;
      setSel(null);
      syncSheet();
    }
    card.addEventListener("click", async (e) => {
      if (e.target.closest(".close")) { closeCard(); return; }
      if (e.target.closest(".sheet-grip")) { setSheet(card.dataset.sheet === "full" ? "peek" : "full"); return; }
      const cp = e.target.closest("[data-copy]");
      if (cp) { const ok = await S.copy(location.href); flash(cp, ok ? "Link copied" : "Couldn't copy"); return; }
      const inc = e.target.closest("[data-inc]");
      if (inc) { const i = safety && safety.incidents.find((x) => x.id === inc.dataset.inc); if (i) focusIncident(i); return; }
      const pl = e.target.closest("[data-place]");
      if (pl) { const p = places[+pl.dataset.place]; if (p) focusPlace(p); }
    });
    /* keyboard focus inside a peeking sheet opens it, so nothing focused is out of sight */
    card.addEventListener("focusin", (e) => {
      if (isPhone() && card.dataset.sheet === "peek" && !e.target.closest(".sheet-grip, .close")) setSheet("full");
    });
    card.addEventListener("change", (e) => {
      const r = e.target.closest("[data-remember]");
      if (!r) return;
      if (r.checked) S.local.set("nk-corner", r.dataset.remember); else S.local.del("nk-corner");
    });
    /* drag the grip: up opens the sheet, down closes it a step at a time */
    let drag = null;
    card.addEventListener("pointerdown", (e) => { if (e.target.closest(".sheet-grip") && isPhone()) drag = { y: e.clientY }; });
    addEventListener("pointerup", (e) => {
      if (!drag) return;
      const dy = e.clientY - drag.y;
      drag = null;
      if (dy < -30) setSheet("full");
      else if (dy > 40) { if (card.dataset.sheet === "full") setSheet("peek"); else closeCard(); }
    });
    const copyBtn = () => `<button type="button" class="cbtn" data-copy>Copy link</button>`;

    /* ---------- cards ---------- */
    function placeCard(p) {
      const col = NK.GROUP_COLORS[p.g] || "var(--ink)";
      const acts = [];
      if (p.ph && S.tels(p.ph).length) acts.push(S.telLink(p.ph, "Call {n}"));
      acts.push(`<a class="cbtn" href="https://www.google.com/maps/search/?api=1&query=${encodeURIComponent(p.n + " " + p.lat + "," + p.lon)}" target="_blank" rel="noopener">Directions</a>`);
      if (p.w) acts.push(`<a class="cbtn" href="${esc(p.w)}" target="_blank" rel="noopener">Website</a>`);
      acts.push(copyBtn());
      const more = [townLabel(p), p.s ? `<a href="${esc(p.s)}" target="_blank" rel="noopener">${esc(social(p.s))}</a>` : ""].filter(Boolean);
      showCard(`<p class="kicker"><span class="sw" style="background:${col}"></span>${esc(S.cap(p.c || ""))}${meta.groups[p.g] ? " · " + esc(meta.groups[p.g]) : ""}</p>
        <h3>${esc(p.n)}</h3>${p.a ? `<p class="c-addr">${esc(p.a)}</p>` : ""}
        <p class="c-acts">${acts.join("")}</p>${more.length ? `<p class="meta">${more.join(" · ")}</p>` : ""}`, { top: col, kind: "place" });
    }
    const PREC = { intersection: "Pinned at the cross streets given.", picked: "Pinned where the poster marked it.", street: "" };
    function petCard(p) {
      const st = P.STATUS[p.status] || "Lost", aw = P.animalWord(p), top = `var(--pet-${p.status})`;
      const street = p.prec === "street" || typeof p.x !== "number";
      const where = street
        ? (p.placeLabel || p.near ? `Somewhere on ${p.placeLabel || p.near}${p.town ? ", " + p.town : ""}. No cross street was given.` : "")
        : P.nearLine(p);
      const d = p.date || String(p.created || "").slice(0, 10);
      const acts = [`<a class="cbtn" href="${esc(S.url("lost-pets/flyer/"))}?pet=${esc(p.id)}">Flyer</a>`];
      if (p.url) acts.push(`<a class="cbtn" href="${esc(p.url)}" target="_blank" rel="noopener">See this post ›</a>`);
      acts.push(`<a class="cbtn" href="${esc(S.url("lost-pets/"))}#${esc(p.id)}">On the board</a>`, copyBtn());
      showCard(`<p class="kicker"><span class="sw" style="background:${top}"></span>${esc(st)} · ${esc(aw)}</p>
        <h3>${p.name ? `“${esc(p.name)}”` : esc(`${st} ${aw}`)}</h3>
        ${where ? `<p class="c-where">${esc(where)}</p>` : ""}<p class="c-acts">${acts.join("")}</p>
        ${p.desc ? `<p class="txt">${esc(p.desc)}</p>` : ""}
        ${d ? `<p class="c-line">${esc(st)} ${esc(S.apDay(d))} <span data-ago="${esc(d)}" data-paren></span></p>` : ""}
        ${p.contact ? `<p class="c-line">${P.contactHTML(p)}</p>` : ""}
        ${!street && PREC[p.prec] ? `<p class="meta">${PREC[p.prec]}</p>` : ""}`, { top, kind: "pet" });
    }
    function incidentCard(p) {
      const Sf = window.NKSafety || { TYPE: {}, CAT: {}, PREC: {} }, top = `var(--inc-${esc(p.c)})`;
      const blot = `${S.url("crime/blotter/")}#inc-${encodeURIComponent(p.id || "")}`;
      showCard(`<p class="kicker"><span class="sw" style="background:${top}"></span>${esc(Sf.CAT[p.c] || "")}${p.pi ? " · police involved" : ""}</p>
        <h3>${esc(Sf.TYPE[p.k] || S.cap(p.k))}</h3>
        <p class="c-where">${esc(S.apDate(p.d))} · ${esc(p.l)}, ${esc(p.t)}</p>
        <p class="c-acts"><a class="cbtn" href="${esc(blot)}">On the police blotter</a>${copyBtn()}</p>
        <p class="txt">${esc(p.s)}</p><p class="credit">${S.credit(p.src)}</p>
        <p class="meta">Location precision: ${esc(Sf.PREC[p.p] || p.p)}. Reported in the news; not a complete record.</p>`, { top, kind: "inc" });
    }
    function crashCard(p) {
      const when = S.apDate(p.mo ? `${p.yr}-${String(p.mo).padStart(2, "0")}` : String(p.yr));
      const hurt = [p.f ? `${p.f} killed` : "", p.s ? `${p.s} seriously injured` : ""].filter(Boolean).join(" · ");
      showCard(`<p class="kicker"><span class="tri-key${p.f ? "" : " hollow"}"></span>${esc(p.col || "Crash")}</p>
        <h3>${p.f ? "Fatal crash" : "Serious-injury crash"}</h3>
        <p class="c-where">${esc(when)} · ${esc(p.t)}</p>${hurt ? `<p class="c-line">${esc(hurt)}</p>` : ""}
        <p class="c-acts"><a class="cbtn" href="${esc(S.url("crashes/"))}">Serious crashes</a></p>
        <p class="credit">${S.credit(safety && safety.crashes && safety.crashes.source)}</p>
        <p class="meta">Location as recorded by the investigating police agency.</p>`, { kind: "crash" });
    }

    /* ---------- "Near this street" and "Near this corner" (spec section 5), measured on this device ---------- */
    const polTel = (t) => { const r = police[t]; return r ? `${esc(t)} ${S.telLink(r.ph, "{n}", "tel-inline")}` : ""; };
    function policeLine(towns) {
      const core = towns.filter((t) => police[t]);
      if (!core.length) return "";
      return `<p class="near-l"><b>Police</b> ${core.length === 1 ? `${polTel(core[0])} (non-emergency)` : `${core.map(polTel).join(" or ")}, depending on the block`}</p>`;
    }
    const nearestTo = (dFn, test) => {
      let best = null, bd = Infinity;
      for (const p of places) { if (!test(p)) continue; const d = dFn(p); if (d < bd) { bd = d; best = p; } }
      return best ? { p: best, d: bd } : null;
    };
    function nearbyHTML(dFn) {
      /* the spec's tests (grocer|supermarket, pharmac|drug, the play group), narrowed to real parks and away from drug treatment */
      const kinds = [["Grocery", (p) => /grocer|supermarket/i.test(p.c || "")],
        ["Pharmacy", (p) => /pharmac|drug/i.test(p.c || "") && !/treatment/i.test(p.c || "")],
        ["Park", (p) => p.g === "play" && /park|field|playground/i.test(p.c || "")]];
      const rows = kinds.map(([label, test]) => {
        const hit = nearestTo(dFn, test);
        if (!hit) return "";
        const call = hit.p.ph && S.tels(hit.p.ph).length ? S.telLink(hit.p.ph, "Call") : "";
        return `<li><span class="nb-k">${label}</span><span class="nb-p"><button type="button" class="linkbtn" data-place="${hit.p.id}">${esc(hit.p.n)}</button>, ${dist(hit.d)}</span>${call}</li>`;
      }).join("");
      return rows ? `<p class="near-h">Nearest grocery, pharmacy and park</p><ul class="near-list">${rows}</ul>` : "";
    }
    const incRow = (i) => `<li><button type="button" class="linkbtn" data-inc="${esc(i.id)}">${esc(S.apDate(i.d))} · ${esc(((window.NKSafety || {}).TYPE || {})[i.k] || S.cap(i.k))} · ${esc(i.l)}</button></li>`;
    const split = (list) => {
      const c = {};
      list.forEach((i) => { c[i.t] = (c[i.t] || 0) + 1; });
      return Object.entries(c).sort((a, b) => b[1] - a[1] || a[0].localeCompare(b[0])).map(([t, n]) => `${n} in ${t}`).join(", ");
    };
    const newest = (list) => [...list].sort((a, b) => String(b.d).localeCompare(String(a.d)));
    const firstYear = (list) => Math.min(...list.map((i) => +String(i.d).slice(0, 4)));
    function crashYears() {
      const ys = ((safety && safety.crashes && safety.crashes.stats) || []).map((r) => r.year);
      return ys.length ? [Math.min(...ys), Math.max(...ys)] : null;
    }
    function crashLine(list) {
      if (!safety) return "";
      if (!list.length) { const y = crashYears(); return `<p class="near-l">Serious crashes within 100 ft: none${y ? ` from ${y[0]} through ${y[1]}` : ""}.</p>`; }
      const ys = [...new Set(list.map((c) => c.yr))].sort();
      return `<p class="near-l">Serious crashes within 100 ft: ${list.length} (${ys.join(", ")}).</p>`;
    }
    function petsLine(dFn) {
      if (!P || !P.board.known) return "";
      const n = P.board.posts.filter((p) => typeof p.x === "number" && dFn(p) <= HALF_MILE).length;
      return `<p class="near-l">Open lost and found posts within ½ mile: ${n}.</p>`;
    }
    const rememberBox = (label) => `<label class="remember"><input type="checkbox" data-remember="${esc(label)}"${S.local.get("nk-corner") === label ? " checked" : ""}> Remember on this phone</label>`;

    async function streetCard(s) {
      const lines = W.lines.filter((l) => l.n === s.n);
      const dFn = (p) => Math.min(...lines.map((l) => NK.lineDist(p.x, p.y, l.pts)));
      try { await loadSafety(); } catch (e) { console.warn(e); }
      const mi = s.m / 1609.344;
      const towns = (s.t || []).map(townName);
      const head = [`${fmt(s.m)} m (${mi < 1 ? mi.toFixed(2) : mi.toFixed(1)} mi) in 15068`, s.a ? `${fmt(s.a)} addresses` : "",
        towns.length ? `Runs through ${towns.join(", ")}` : ""].filter(Boolean).join(" · ");
      let incHTML = "";
      if (safety) {
        const k = streetKey(s.n);
        const all = safety.incidents || [];
        const on = [], near = [];
        all.forEach((i) => {
          const d = dFn(i);
          if ((k && incNames(i, k) && (s.t || []).includes(i.t)) || d <= 30) on.push(i);
          else if (d <= 120) near.push(i);
        });
        if (on.length) {
          const u = `${S.url("crime/blotter/")}?street=${encodeURIComponent(s.n).replace(/%20/g, "+")}`;
          incHTML = `<p class="near-l"><b>${on.length} news-reported ${plural(on.length, "incident")} on ${esc(s.n)}</b> since ${firstYear(on)} (${esc(split(on))}).</p>
            <ul class="near-list">${newest(on).slice(0, 3).map(incRow).join("")}</ul><p><a class="go" href="${esc(u)}">See all on the police blotter ›</a></p>`;
        } else {
          incHTML = `<p class="near-l">No news-reported incidents on ${esc(s.n)}${all.length ? ` since ${firstYear(all)}` : ""}.</p>`;
        }
        if (near.length) incHTML += `<p class="near-l">${near.length} more within a block (400 ft).</p>`;
        incHTML += crashLine(((safety.crashes && safety.crashes.points) || []).filter((c) => dFn(c) <= 30));
      }
      showCard(`<p class="kicker"><span class="sw" style="background:var(--map-focus)"></span>Street</p>
        <h3>${S.streetHead(s.n)}${S.routes(s.ref)}</h3><p class="c-where">${esc(head)}</p>
        <p class="c-acts">${copyBtn()}</p>
        <div class="near">${incHTML}${petsLine(dFn)}${nearbyHTML(dFn)}${policeLine(s.t || [])}</div>`, { top: "var(--map-focus)", kind: "street" });
    }
    function townOf(x, y) {
      const ctx = map.ctx;
      ctx.save(); ctx.setTransform(1, 0, 0, 1, 0, 0);
      const t = (W.towns || []).filter((t) => t.core).find((t) => ctx.isPointInPath(t.p, x, y)) || (W.towns || []).find((t) => ctx.isPointInPath(t.p, x, y));
      ctx.restore();
      return t ? t.n : null;
    }
    async function cornerCard(spot) {
      const dFn = (p) => Math.hypot(p.x - spot.x, p.y - spot.y);
      try { await loadSafety(); } catch (e) { console.warn(e); }
      const town = townOf(spot.x, spot.y);
      let incHTML = "";
      if (safety) {
        const on = (safety.incidents || []).filter((i) => dFn(i) <= 120);
        incHTML = on.length
          ? `<p class="near-l"><b>${on.length} news-reported ${plural(on.length, "incident")} within a block (400 ft)</b> since ${firstYear(on)} (${esc(split(on))}).</p><ul class="near-list">${newest(on).slice(0, 3).map(incRow).join("")}</ul>`
          : `<p class="near-l">No news-reported incidents within a block (400 ft).</p>`;
        incHTML += crashLine(((safety.crashes && safety.crashes.points) || []).filter((c) => dFn(c) <= 30));
      }
      const label = spot.label ? `Near ${P ? P.shortStreet(spot.label) : spot.label}` : "This spot";
      showCard(`<p class="kicker"><span class="sw" style="background:var(--here)"></span>${spot.located ? "Your location" : "Corner"}</p>
        <h3>${esc(label)}</h3>${town ? `<p class="c-where">In ${esc(townName(town))}</p>` : ""}
        <p class="c-acts">${copyBtn()}</p>
        <div class="near">${incHTML}${petsLine(dFn)}${nearbyHTML(dFn)}${policeLine(town ? [town] : [])}</div>
        ${rememberBox(spot.text || label)}`, { top: "var(--here)", kind: "near" });
    }

    /* ---------- focusing things ---------- */
    function focusPlace(p, { write = true } = {}) {
      if (!p) return;
      clearMarks();
      if (!map.filter.has(p.g)) $("#chips .chip[data-g='*']")?.click();
      go(p.x, p.y, 2.6);
      map.sel = p; map.dirty = true;
      placeCard(p);
      if (write) setSel("place", placeParam(p));
    }
    async function focusStreet(s, { write = true } = {}) {
      if (!s) return;
      clearMarks();
      map.sel = null;
      map.highlightStreet(s.n);
      if (!(arriving && atSet)) map.fitStreet(s.n, inset());
      if (write) setSel("street", s.n);
      await streetCard(s);
    }
    async function focusCorner(spot, { write = true, zoom = 1.6 } = {}) {
      clearMarks();
      map.sel = null;
      map.here = { x: spot.x, y: spot.y }; map.focus = { x: spot.x, y: spot.y };
      go(spot.x, spot.y, zoom);
      if (write) setSel("near", spot.text || spot.label);
      await cornerCard(spot);
    }
    function focusPet(p, { write = true } = {}) {
      clearMarks();
      if (!L.pets) setLayer("pets", true);
      petsDefault = false;
      if ((p.prec === "street" || typeof p.x !== "number") && (p.placeLabel || p.near)) {
        map.sel = null;
        map.highlightStreet(p.placeLabel || p.near, p.town || null);
        if (!(arriving && atSet)) { if (!map.fitStreet(null, inset()) && typeof p.x === "number") go(p.x, p.y, 0.6); }
      } else if (typeof p.x === "number") {
        map.focus = { x: p.x, y: p.y };
        go(p.x, p.y, 1.25);
        map.sel = p;
      }
      map.dirty = true;
      petCard(p);
      if (write) setSel("pet", p.id);
    }
    async function focusIncident(i, { write = true } = {}) {
      clearMarks();
      await setLayer("incidents", true);
      if (!map.incVisible(i)) { map.incVisible = () => true; $(".lg-filter")?.remove(); }
      map.focus = { x: i.x, y: i.y };
      go(i.x, i.y, 1.25);
      map.sel = i; map.dirty = true;
      incidentCard(i);
      if (write) setSel("inc", i.id);
    }
    /* a tap on the map */
    function pick(p) {
      if (!p) { if (cardKind && cardKind !== "street" && cardKind !== "near") closeCard(); return; }
      clearMarks();
      if (p.status) { focusPetTap(p); return; }
      if (p.yr != null) { crashCard(p); setSel(null); return; }
      if (p.k && p.d) { incidentCard(p); setSel("inc", p.id); return; }
      placeCard(p); setSel("place", placeParam(p));
    }
    function focusPetTap(p) { map.sel = p; petCard(p); setSel("pet", p.id); }

    /* ---------- deep links ---------- */
    function findPlace(v) {
      const m = String(v).match(/^(.*?)(?:~(-?\d+(?:\.\d+)?),(-?\d+(?:\.\d+)?))?$/);
      const sl = slug(m[1]), hasXY = m[2] != null, x = +m[2], y = +m[3];
      const same = places.filter((p) => slug(p.n) === sl);
      const nearest = (list) => {
        let best = null, bd = Infinity;
        list.forEach((p) => { const d = Math.hypot(p.x - x, p.y - y); if (d < bd) { bd = d; best = p; } });
        return { p: best, d: bd };
      };
      if (hasXY) {
        let n = nearest(same);
        if (n.p && n.d <= 200) return { p: n.p };
        n = nearest(places);
        if (n.p && n.d <= 30) return { p: n.p };
        return { x, y };
      }
      return same.length ? { p: [...same].sort((a, b) => (b.q || 0) - (a.q || 0))[0] } : {};
    }
    function findStreet(name) {
      const n = String(name || "").trim().toLowerCase();
      if (!n) return null;
      const exact = streets.find((s) => s.n.toLowerCase() === n);
      if (exact) return exact;
      const k = streetKey(name);
      const keyed = k ? streets.filter((s) => { const x = streetKey(s.n); return x && x.core === k.core && typeOk(k.type, x.type); }) : [];
      return keyed.sort((a, b) => (b.a || 0) - (a.a || 0) || b.m - a.m)[0] || streets.find((s) => s.n.toLowerCase().startsWith(n)) || null;
    }
    async function geocode(text) {
      if (!P) return null;
      await boardP;
      return P.geocodeNear(P.cleanNear(text), S.town() || "New Kensington");
    }
    async function arrive() {
      if (Q.has("at")) {
        const [x, y, s] = Q.get("at").split(",").map(Number);
        if ([x, y, s].every(Number.isFinite) && s > 0) { map.setView(x, y, s); atSet = true; }
      }
      const want = layerParam.filter((k) => OVERLAYS.includes(k));
      for (const k of want) await setLayer(k, true);
      if (want.includes("incidents")) {
        map.incVisible = incFilter();
        showFilterNote();
        const vis = (safety ? safety.incidents : []).filter(map.incVisible);
        if (filtered() && !vis.length) showMsg("No incidents match those filters.");
        else if (!Q.has("inc")) fitPoints(vis.length ? vis : safety ? safety.incidents : []);
      } else if (want.includes("crashes")) fitPoints((safety && safety.crashes.points) || []);
      if (Q.get("place")) {
        const f = findPlace(Q.get("place"));
        if (f.p) focusPlace(f.p, { write: false });
        else if (Number.isFinite(f.x)) { go(f.x, f.y, 2); showMsg("That place isn't in the current map data."); }
        else showMsg("That place isn't in the current map data.");
      } else if (Q.get("street")) {
        const s = findStreet(Q.get("street"));
        if (s) await focusStreet(s, { write: false });
        else if (!want.includes("incidents")) showMsg(`We couldn't find a street called “${Q.get("street")}” in 15068.`);
      } else if (Q.get("near")) {
        const g = await geocode(Q.get("near"));
        if (g) await focusCorner({ x: g.x, y: g.y, label: g.label, text: Q.get("near") }, { write: false });
        else showMsg("We couldn't find that corner. Try two street names, like 5th Avenue & 9th Street.");
      } else if (Q.get("pet")) {
        await boardP;
        const id = Q.get("pet"), p = P && P.board.posts.find((x) => x.id === id);
        if (p) focusPet(p, { write: false });
        else if (P && P.board.state === "unknown") showMsg("The lost and found board didn't load just now, so that listing can't be shown.", `<p><a class="go" href="${esc(S.url("lost-pets/"))}">Lost and found pets ›</a></p>`);
        else showMsg("That listing isn't open on the board now. Its owner may have closed it.", `<p><a class="go" href="${esc(S.url("lost-pets/"))}#board">See the board ›</a></p>`);
      } else if (Q.get("inc")) {
        try { await loadSafety(); } catch (e) { console.warn(e); }
        const i = safety && safety.incidents.find((x) => x.id === Q.get("inc"));
        if (i) await focusIncident(i, { write: false });
        else showMsg("That incident isn't in the current data.", `<p><a class="go" href="${esc(S.url("crime/blotter/"))}">The police blotter ›</a></p>`);
      }
    }
    const release = () => { map.hold = false; map.dirty = true; if (loading) loading.hidden = true; };
    const done = arrive().catch((e) => console.warn(e));
    await Promise.race([done, wait(4000)]);
    release();
    await done;
    arriving = false;
    map.drawnLabels = []; map.dirty = true;
    settled = true;

    /* ---------- the search panel (NKSearch) ---------- */
    const q = $("#q"), res = $("#results");
    if (!q || !res) return;
    let sdata = null, spot = null, rows = [], showAll = false;
    const saved = S.local.get("nk-corner");
    const loadSearch = () => (window.NKSearch ? window.NKSearch.load() : Promise.reject(new Error("search.js")));
    if (saved) geocode(saved).then((g) => { if (g) spot = { x: g.x, y: g.y, label: g.label }; }).catch(() => {});
    function hideResults() { res.innerHTML = ""; res.hidden = true; }
    function locRow() {
      return `<div class="res res-loc"><button type="button" class="res-go" data-k="loc"><i class="loc-i"></i><b>Use my location</b><small>Find what's near you</small></button></div>`
        + (saved ? `<div class="res"><button type="button" class="res-go" data-k="saved"><i class="loc-i"></i><b>Near ${esc(P ? P.shortStreet(saved) : saved)}</b><small>Your saved corner</small></button></div>` : "");
    }
    function rowHTML(r) {
      if (r.kind === "msg") return `<p class="none">${esc(r.text)}</p>`;
      if (r.kind === "call") {
        const ph = r.x.ph[0];
        return `<div class="res res-call"><a class="res-go" href="${esc(S.url(r.x.u))}"><i class="call-i"></i><b>${esc(r.x.n)}</b><small>${esc(r.x.t)} · phone number</small></a>${ph ? S.telLink(ph, "Call", "tel res-tel") : ""}</div>`;
      }
      const call = r.ph && S.tels(r.ph).length ? S.telLink(r.ph, "Call", "tel res-tel") : "";
      const icon = r.col ? `<i style="background:${r.col}"></i>` : `<i class="loc-i"></i>`;
      return `<div class="res"><button type="button" class="res-go" data-k="${esc(r.k)}">${icon}<b>${r.name}</b><small>${esc(r.sub)}</small></button>${call}</div>`;
    }
    function drawResults() {
      const t = q.value.trim();
      if (!t) { res.innerHTML = locRow(); res.hidden = false; return; }
      if (!sdata) { res.innerHTML = `<p class="none">Searching…</p>`; res.hidden = false; return; }
      const m = window.NKSearch.match(t, sdata, { town: S.town(), pets: P ? P.board.posts : [], spot });
      rows = [];
      const G = m.groups;
      if (G.corner.length && P) {
        const g = P.geocodeNear(P.cleanNear(t), S.town() || "New Kensington");
        rows.push(g ? { k: "c", name: esc(`Near ${P.shortStreet(g.label)}`), sub: "Corner · what's near it", col: "", g }
          : { kind: "msg", text: "We couldn't find that corner. Try two street names, like 5th Avenue & 9th Street." });
      }
      G.streets.slice(0, 8).forEach((s) => rows.push({ k: "s:" + s.n, name: esc(s.n) + S.routes(s.ref),
        sub: ["Street", fmt(s.m) + " m", (s.t || []).map(townName).join(", ")].filter(Boolean).join(" · "), col: "var(--map-focus)" }));
      G.places.forEach((p) => rows.push({ k: "p:" + p.id, name: esc(p.n), ph: p.ph, col: NK.GROUP_COLORS[p.g],
        sub: [S.cap(p.c || ""), S.shortAddr(p.a) || townLabel(p), spot && p._d != null ? dist(p._d) : ""].filter(Boolean).join(" · ") }));
      G.call.slice(0, 6).forEach((r) => rows.push({ kind: "call", x: r }));
      G.pets.forEach((p) => rows.push({ k: "pet:" + p.id, name: esc(P.headline(p)), col: `var(--pet-${p.status})`, sub: P.where(p) || "Lost and found board" }));
      if (!rows.length) { res.innerHTML = `<p class="none">Nothing found for “${esc(t)}”. Try a business, a street (“5th Ave”) or a corner (“5th & 9th”).</p>`; res.hidden = false; return; }
      const n = rows.length, lim = showAll ? n : 50;
      res.innerHTML = rows.slice(0, lim).map(rowHTML).join("") + (n > lim ? `<button type="button" class="res-all" data-k="all">Show all ${fmt(n)}</button>` : "");
      res.hidden = false;
    }
    function open(k) {
      if (k === "all") { showAll = true; drawResults(); return; }
      if (k === "loc") { askLocation(); return; }
      q.blur();
      if (k === "saved") { geocode(saved).then((g) => g && focusCorner({ x: g.x, y: g.y, label: g.label, text: saved })); hideResults(); return; }
      if (k === "c") { const r = rows.find((x) => x.k === "c"); if (r) focusCorner({ x: r.g.x, y: r.g.y, label: r.g.label, text: q.value.trim() }); }
      else if (k.startsWith("s:")) focusStreet(streets.find((s) => s.n === k.slice(2)));
      else if (k.startsWith("p:")) focusPlace(places[+k.slice(2)]);
      else if (k.startsWith("pet:")) { const p = P.board.posts.find((x) => x.id === k.slice(4)); if (p) focusPet(p); }
      hideResults();
      if (isPhone() && chips) { chips.removeAttribute("data-open"); fb?.setAttribute("aria-expanded", "false"); }
    }
    let timer = 0;
    q.addEventListener("focus", () => { if (!sdata) loadSearch().then((d) => { sdata = d; drawResults(); }).catch((e) => console.warn(e)); drawResults(); });
    q.addEventListener("input", () => { showAll = false; clearTimeout(timer); timer = setTimeout(drawResults, 120); });
    q.addEventListener("keydown", (e) => {
      if (e.key === "Escape") { hideResults(); q.blur(); }
      if (e.key !== "Enter") return;
      e.preventDefault();
      clearTimeout(timer); drawResults();
      const first = res.querySelector("[data-k]:not([data-k='loc']):not([data-k='saved']):not([data-k='all'])") || res.querySelector("a.res-go");
      if (first && first.dataset.k) open(first.dataset.k); else if (first) location.href = first.href;
    });
    res.addEventListener("click", (e) => { const b = e.target.closest("button[data-k]"); if (b) open(b.dataset.k); });
    document.addEventListener("click", (e) => { if (!res.hidden && !e.composedPath().includes(res) && e.target !== q) hideResults(); });
    document.addEventListener("keydown", (e) => {
      if (e.key !== "Escape") return;
      if (pop && !pop.hidden) { setPop(false); lb.focus(); }
    });

    /* ---------- Use my location: the consent sentence first; only the street label is ever kept ---------- */
    function askLocation() {
      if (!navigator.geolocation) { res.innerHTML = `<p class="none">This browser can't share a location. Type a corner instead.</p>`; return; }
      res.innerHTML = `<div class="consent"><p>Your location is used on this device to find your nearest street. It isn't sent anywhere.</p>
        <p><button type="button" class="btn-line inline" id="loc-go">Continue</button> <button type="button" class="btn-line inline" id="loc-no">Cancel</button></p></div>`;
      $("#loc-no").addEventListener("click", hideResults);
      $("#loc-go").addEventListener("click", () => {
        res.innerHTML = `<p class="none">Finding your nearest street…</p>`;
        navigator.geolocation.getCurrentPosition(async (pos) => {
          const x = (pos.coords.longitude - meta.origin[0]) * meta.kx, y = (meta.origin[1] - pos.coords.latitude) * meta.ky;
          const [x0, y0, x1, y1] = meta.bounds;
          if (x < x0 || x > x1 || y < y0 || y > y1) { res.innerHTML = `<p class="none">You look to be outside 15068. Type a corner instead.</p>`; return; }
          await boardP;
          const names = P ? P.nearestStreets(x, y, 150) : [];
          if (!names.length) { res.innerHTML = `<p class="none">We couldn't find a street near you. Type a corner instead.</p>`; return; }
          hideResults();
          const label = names.join(" & ");
          focusCorner({ x, y, label, text: "Near " + names.map(P.shortStreet).join(" & "), located: true }, { write: false });
        }, () => { res.innerHTML = `<p class="none">Your location isn't available. Type a corner instead.</p>`; },
        { enableHighAccuracy: false, timeout: 10000, maximumAge: 300000 });
      });
    }
  }

  /* ======================================================================== /map/3d/ */
  S.pages.map3d = () => map3dPage().catch((e) => { console.warn(e); });

  const VIEWS = {
    downtown: { x: -3350, y: -40, dist: 1500, pitch: 0.55, yaw: -0.6 },
    hills: { x: 900, y: -1500, dist: 4200, pitch: 0.3, yaw: 2.3 },
    zip: { x: -400, y: 0, dist: 16500, pitch: 0.95, yaw: -0.35 },
  };
  async function map3dPage() {
    const NK = window.NK, ex = $("#explorer"), host = $("#gl-host"), loading = $("#map-loading");
    if (!NK || !ex || !host) return;
    const cap = loading && loading.querySelector("figcaption");
    const fail = (t) => { if (cap) cap.textContent = t; if (loading) loading.hidden = false; };
    if (!window.THREE || !NK.Map3D) { fail("The 3D view needs the three.js library, which didn't load. Check your connection and reload, or use the flat map."); return; }
    let W, meta, T, bld;
    try {
      [meta, W] = await Promise.all([NK.getJSON("meta.json"), NK.loadWorld()]);
      [T, bld] = await Promise.all([NK.getTerrain(meta), NK.loadBuildings(W)]);
    } catch (e) { console.warn(e); fail("The 3D data didn't load just now. Reload the page to try again."); return; }
    const labelsEl = $("#p3-labels"), ctl = $("#p3-ctl"), msg = $("#p3-msg");
    const towns = W.base.labels.filter((l) => l.k === "town" && (meta.towns || []).some((t) => t.n === l.n && t.core));
    if (labelsEl) labelsEl.innerHTML = towns.map((l) => `<span data-town="${esc(l.n)}">${esc(l.n.toUpperCase())}</span>`).join("");
    const spans = labelsEl ? $$("span", labelsEl) : [];
    let labelsOn = true, m3 = null;
    function placeLabels(m) {
      if (!labelsOn || !labelsEl) return;
      towns.forEach((l, i) => {
        const p = m.project(l.x, l.y, 90), el = spans[i];
        const vis = p.visible && p.x > -80 && p.y > -20 && p.x < host.clientWidth + 80 && p.y < host.clientHeight + 20;
        el.style.visibility = vis ? "visible" : "hidden";
        if (vis) el.style.transform = `translate(${p.x.toFixed(1)}px, ${p.y.toFixed(1)}px) translate(-50%, -50%)`;
      });
    }
    async function build() {
      if (m3) { m3.stopped = true; try { m3.renderer.dispose(); } catch (e) { /* ignore */ } host.innerHTML = ""; }
      try { m3 = new NK.Map3D(host, W, { onFrame: placeLabels }); } catch (e) {
        console.warn(e);
        fail("This browser can't draw the 3D view (WebGL is turned off or unavailable). The flat map works everywhere.");
        return false;
      }
      await m3.build(T, bld);
      return true;
    }
    if (!(await build())) return;
    if (loading) loading.hidden = true;
    if (ctl) ctl.hidden = false;
    S.onTheme(async () => {
      const v = m3 ? { x: m3.target.x, y: m3.target.z, dist: m3.dist, pitch: m3.pitch, yaw: m3.yaw } : null;
      if (await build() && v) { m3.target.set(v.x, m3.target.y, v.y); m3.dist = v.dist; m3.pitch = v.pitch; m3.yaw = v.yaw; m3.auto = false; }
    });
    ex.addEventListener("click", (e) => {
      const b = e.target.closest("[data-go]");
      if (b && m3 && VIEWS[b.dataset.go]) m3.goTo(VIEWS[b.dataset.go]);
    });
    const tl = $("#p3-town");
    tl?.addEventListener("click", () => {
      labelsOn = !labelsOn;
      tl.setAttribute("aria-pressed", String(labelsOn));
      if (labelsEl) labelsEl.hidden = !labelsOn;
    });
    /* poster mode: the controls step aside for a title block and the credit line */
    const pb = $("#p3-poster"), exitB = $("#p3-exit"), title = $("#p3-title"), head = $("#p3-head");
    function poster(on) {
      ex.toggleAttribute("data-poster", on);
      pb?.setAttribute("aria-pressed", String(on));
      if (title) title.hidden = !on;
      if (exitB) exitB.hidden = !on;
      if (ctl) ctl.hidden = on;
      if (head) head.hidden = on;
      (on ? exitB : pb)?.focus();
    }
    pb?.addEventListener("click", () => poster(true));
    exitB?.addEventListener("click", () => poster(false));
    document.addEventListener("keydown", (e) => { if (e.key === "Escape" && ex.hasAttribute("data-poster")) poster(false); });
    /* save as image: the WebGL frame at 2x, with the town labels, the title in poster mode and the credit line drawn on */
    $("#p3-save")?.addEventListener("click", async (e) => {
      const btn = e.currentTarget;
      btn.disabled = true;
      try {
        const url = m3.snapshot(2);
        const img = await new Promise((ok, no) => { const i = new Image(); i.onload = () => ok(i); i.onerror = no; i.src = url; });
        const c = document.createElement("canvas");
        c.width = img.width; c.height = img.height;
        const ctx = c.getContext("2d"), k = img.width / host.clientWidth;
        ctx.drawImage(img, 0, 0);
        const ink = NK.css("--map-label") || "#1c232a", halo = NK.css("--map-halo") || "rgba(255,255,255,.9)";
        const text = (t, x, y, font, align = "center") => {
          ctx.font = font; ctx.textAlign = align; ctx.textBaseline = "middle"; ctx.lineJoin = "round";
          ctx.lineWidth = 4 * k; ctx.strokeStyle = halo; ctx.strokeText(t, x, y); ctx.fillStyle = ink; ctx.fillText(t, x, y);
        };
        if (labelsOn) towns.forEach((l) => { const p = m3.project(l.x, l.y, 90); if (p.visible) text(l.n.toUpperCase(), p.x * k, p.y * k, `800 ${15 * k}px ${NK.css("--f-display")}`); });
        if (ex.hasAttribute("data-poster")) {
          text("NK15068", c.width / 2, c.height - 96 * k, `800 ${40 * k}px ${NK.css("--f-display")}`);
          text("New Kensington · Arnold · Lower Burrell", c.width / 2, c.height - 58 * k, `600 ${17 * k}px ${NK.css("--f-body")}`);
        }
        text("Map data © OpenStreetMap contributors · Overture Maps · US Census · AWS Terrain Tiles", c.width - 12 * k, c.height - 14 * k, `400 ${11 * k}px ${NK.css("--f-body")}`, "right");
        const blob = await new Promise((ok) => c.toBlob(ok, "image/png"));
        const a = Object.assign(document.createElement("a"), { href: URL.createObjectURL(blob), download: "15068-3d.png" });
        document.body.appendChild(a); a.click(); a.remove();
        setTimeout(() => URL.revokeObjectURL(a.href), 4000);
        if (msg) msg.textContent = `Saved a ${fmt(c.width)} × ${fmt(c.height)} image.`;
      } catch (err) {
        console.warn(err);
        if (msg) msg.textContent = "The image couldn't be made in this browser.";
      }
      btn.disabled = false;
    });
  }

  /* ======================================================================== /directory/ */
  S.pages.directory = () => directoryPage().catch((e) => { console.warn(e); });

  async function directoryPage() {
    const NK = window.NK, tools = $("#dir-tools"), table = $("#dir-table"), count = $("#dir-count"), more = $("#dir-more");
    if (!NK || !table || !tools) return;
    let places, streets, meta;
    try { [places, streets, meta] = await Promise.all([NK.getJSON("places.json"), NK.getJSON("streets.json"), NK.getJSON("meta.json")]); }
    catch (e) { console.warn(e); return; } // the first 100 rows are already on the page
    const rows = dedupe(places).sort(aToZ);
    const seen = new Set();
    const sts = streets.filter((s) => !seen.has(s.n) && seen.add(s.n)).sort(aToZ);
    const inp = $("#dir-q"), selT = $("#dir-town"), selG = $("#dir-g"), tabs = $("#dir-tabs");
    const Q = S.qs();
    const st = { tab: Q.get("tab") === "streets" ? "streets" : "places", q: (Q.get("q") || "").slice(0, 80), town: Q.get("town") || "", g: Q.get("g") || "", limit: 100 };
    if (st.town && selT && ![...selT.options].some((o) => o.value === st.town)) selT.insertAdjacentHTML("beforeend", `<option value="${esc(st.town)}">${esc(st.town)}</option>`);
    if (st.g && !meta.groups[st.g]) st.g = "";
    tools.hidden = false;
    if (inp) inp.value = st.q;
    if (selT) selT.value = st.town;
    if (selG) selG.value = st.g;
    const hay = (p) => (p._h || (p._h = [p.n, p.c, townLabel(p), p.a, meta.groups[p.g]].join(" ").toLowerCase()));
    const telCell = (ph) => { const t = S.tels(ph)[0]; return t ? `<a class="dtel" href="${t[1]}">${esc(t[0])}</a>` : esc(ph || ""); };
    const placeRow = (p) => `<tr><td class="dn"><a href="${esc(mapURL("place", placeParam(p)))}"><span class="dot" style="background:${NK.GROUP_COLORS[p.g] || "#7a8a99"}"></span>${esc(p.n)}</a><span class="sub">${esc(meta.groups[p.g] || "")}</span></td><td class="dc">${esc(p.c || "")}</td><td class="dt">${esc(townLabel(p))}</td><td class="da">${esc(p.a || "")}</td><td class="dp">${telCell(p.ph)}</td></tr>`;
    const streetRow = (s) => `<tr><td class="dn"><a href="${esc(mapURL("street", s.n))}">${esc(s.n)}</a>${S.routes(s.ref)}</td><td class="dt">${esc((s.t || []).map(townName).join(", "))}</td><td class="num dl">${fmt(s.m)} m</td><td class="num dd${s.a ? "" : " none"}">${s.a ? `${fmt(s.a)}<span class="ph-u"> ${plural(s.a, "address", "addresses")}</span>` : "–"}</td></tr>`;
    function draw() {
      const t = st.q.trim().toLowerCase();
      let list, head, noun;
      if (st.tab === "places") {
        list = rows.filter((p) => (!t || hay(p).includes(t)) && (!st.town || townLabel(p) === st.town) && (!st.g || p.g === st.g));
        head = "<tr><th>Name</th><th>Type</th><th>Town</th><th>Address</th><th>Phone</th></tr>";
        noun = "place";
      } else {
        list = sts.filter((s) => (!t || (s.n + " " + (s.t || []).join(" ") + " " + (s.ref || []).join(" ")).toLowerCase().includes(t)) && (!st.town || (s.t || []).includes(st.town) || (s.t || []).map(townName).includes(st.town)));
        head = `<tr><th>Street</th><th>Town</th><th class="num">Length</th><th class="num">Addresses</th></tr>`;
        noun = "street";
      }
      table.classList.toggle("streets", st.tab === "streets");
      const shown = list.slice(0, st.limit);
      table.innerHTML = `<thead>${head}</thead><tbody>${shown.map(st.tab === "places" ? placeRow : streetRow).join("")
        || `<tr><td colspan="5" class="empty">Nothing matches${st.q ? ` “${esc(st.q)}”` : ""}${st.town ? ` in ${esc(st.town)}` : ""}.</td></tr>`}</tbody>`;
      if (count) count.textContent = list.length > shown.length
        ? `Showing ${fmt(shown.length)} of ${fmt(list.length)} ${noun}s, A to Z.`
        : `${fmt(list.length)} ${plural(list.length, noun)}${list.length > 1 ? ", A to Z" : ""}.`;
      if (more) { more.hidden = list.length <= st.limit; more.textContent = `Show ${fmt(Math.min(100, list.length - st.limit))} more`; }
      if (selG) selG.hidden = st.tab !== "places";
      $$(".tab", tabs).forEach((b) => b.setAttribute("aria-selected", String(b.dataset.t === st.tab)));
      S.setQS({ q: st.q.trim(), town: st.town, tab: st.tab === "streets" ? "streets" : null, g: st.tab === "places" ? st.g : null });
      S.fadeWide();
    }
    tabs?.addEventListener("click", (e) => { const b = e.target.closest(".tab"); if (b) { st.tab = b.dataset.t; st.limit = 100; draw(); } });
    let timer = 0;
    inp?.addEventListener("input", () => { clearTimeout(timer); timer = setTimeout(() => { st.q = inp.value.slice(0, 80); st.limit = 100; draw(); }, 120); });
    selT?.addEventListener("change", () => { st.town = selT.value; st.limit = 100; draw(); });
    selG?.addEventListener("change", () => { st.g = selG.value; st.limit = 100; draw(); });
    more?.addEventListener("click", () => { st.limit += 100; draw(); });
    draw();
  }

  /* ======================================================================== /search/ */
  S.pages.search = () => searchPage().catch((e) => { console.warn(e); });

  const TITLES = { call: "Call", pages: "Pages", corner: "Corner", streets: "Streets", places: "Places", events: "What's on", news: "News", pets: "Lost & found listings" };
  async function searchPage() {
    const X = window.NKSearch, form = $("#sq"), input = $("#sq-q"), out = $("#sresults");
    if (!X || !form || !input || !out) return;
    const gapText = $("#s-gap") ? $("#s-gap").textContent : "";
    input.value = S.qs().get("q") || "";
    let data = null, posts = [], openPlaces = false;
    const P = window.NKPets;
    if (P) P.loadBoard({ ui: { onChange: (ps) => { posts = P.board.state === "listed" || P.board.state === "stale" ? ps : []; if (data && input.value.trim()) render(); } } });
    const today = S.isoDay(new Date());
    const hint = () => `<p class="s-hint">Try ${["police", "lost dog", "city hall", "pizza", "5th Ave"].map((w) => `<a href="?q=${encodeURIComponent(w)}">${esc(w)}</a>`).join(", ")}, or a corner like <a href="?q=${encodeURIComponent("5th & 9th")}">5th &amp; 9th</a>.</p>`;
    const group = (k, inner, extra = "") => `<section class="sgroup" data-group="${k}" aria-labelledby="sg-${k}"><h2 class="lh" id="sg-${k}">${TITLES[k]}</h2>${inner}${extra}</section>`;
    const li = (main, sub, tail = "") => `<li class="srow"><div class="sr-t">${main}${sub ? `<small>${sub}</small>` : ""}</div>${tail}</li>`;
    function render() {
      const q = input.value.trim();
      if (!q) { out.innerHTML = hint(); return; }
      const m = X.match(q, data, { town: S.town(), pets: posts });
      const G = m.groups, html = [];
      if (G.call.length || m.gap) {
        const rows = G.call.slice(0, 6).map((r) => {
          const [first, ...alt] = r.ph;
          const tail = first ? `<div class="sr-c">${S.telLink(first, "Call {n}")}${alt.map((p) => `<span class="tel-alt">or ${S.telLink(p, "{n}", "alt")}</span>`).join("")}</div>`
            : `<div class="sr-c"><a class="go" href="${esc(S.url(r.u))}">Details ›</a></div>`;
          return li(`<a href="${esc(S.url(r.u))}">${esc(r.n)}</a>`, esc(r.t), tail);
        }).join("");
        html.push(group("call", `<ul class="slist">${rows}</ul>`, (m.gap && gapText ? `<p class="s-gapline">${esc(gapText)}</p>` : "")
          + `<p><a class="go" href="${esc(S.url("numbers/"))}">All phone numbers ›</a></p>`));
      }
      if (G.pages.length) html.push(group("pages", `<ul class="slist">${G.pages.slice(0, 6).map((r) => li(`<a href="${esc(S.url(r.u))}">${esc(r.t)}</a>`, "")).join("")}</ul>`));
      if (G.corner.length) html.push(group("corner", `<p><a class="go" href="${esc(mapURL("near", G.corner[0].text))}">Find “${esc(G.corner[0].text)}” on the map ›</a></p>`));
      if (G.streets.length) html.push(group("streets", `<ul class="slist">${G.streets.slice(0, 8).map((s) => li(
        `<a href="${esc(mapURL("street", s.n))}">${esc(s.n)}</a>${S.routes(s.ref)}`,
        esc([(s.t || []).map(townName).join(", "), `${fmt(s.m)} m`].filter(Boolean).join(" · ")),
        s._inc ? `<div class="sr-c"><a class="go" href="${esc(S.url(s._inc.u))}">${s._inc.n} news-reported ${plural(s._inc.n, "incident")} on this street ›</a></div>` : "")).join("")}</ul>`));
      if (G.places.length) {
        const n = G.places.length, show = openPlaces ? G.places : G.places.slice(0, 10);
        html.push(group("places", `<ul class="slist">${show.map((p) => li(`<a href="${esc(mapURL("place", placeParam(p)))}">${esc(p.n)}</a>`,
          esc([S.cap(p.c || ""), p._town, S.shortAddr(p.a)].filter(Boolean).join(" · ")),
          p.ph && S.tels(p.ph).length ? `<div class="sr-c">${S.telLink(p.ph, "Call {n}")}</div>` : "")).join("")}</ul>`,
          n > show.length ? `<button type="button" class="btn-line inline" id="s-all">Show all ${fmt(n)}</button>` : ""));
      }
      const events = G.events.filter((e) => !e.next || e.next >= today);
      if (events.length) html.push(group("events", `<ul class="slist">${events.slice(0, 6).map((e) => li(`<a href="${esc(S.url(e.u))}">${esc(e.n)}</a>`, esc(e.label))).join("")}</ul>`));
      if (G.news.length) html.push(group("news", `<ul class="slist">${G.news.slice(0, 6).map((r) => li(`<a href="${esc(S.url(r.u))}">${esc(r.h)}</a>`, esc(`${S.apDate(r.d, r.about)} · ${r.o}`))).join("")}</ul>`));
      if (G.pets.length && P) html.push(group("pets", `<ul class="petrows">${G.pets.slice(0, 6).map(P.rowHTML).join("")}</ul>`));
      out.innerHTML = html.join("") || `<p class="s-empty">Nothing found for “${esc(q)}”. Try a business, a street (“5th Ave”), a corner (“5th & 9th”) or a topic like “police”, “lost dog” or “city hall”.</p>`;
      S.relabel(out);
    }
    out.addEventListener("click", (e) => { if (e.target.closest("#s-all")) { openPlaces = true; render(); } });
    form.addEventListener("submit", (e) => { e.preventDefault(); openPlaces = false; S.setQS({ q: input.value.trim() }); render(); });
    let timer = 0;
    input.addEventListener("input", () => { clearTimeout(timer); timer = setTimeout(() => { openPlaces = false; S.setQS({ q: input.value.trim() }); if (data) render(); }, 200); });
    out.innerHTML = input.value.trim() ? `<p class="s-hint">Searching…</p>` : hint();
    try { data = await X.load(); } catch (e) {
      console.warn(e);
      out.innerHTML = `<p class="s-empty">Search didn't load just now. Try <a href="${esc(S.url("numbers/"))}">Phone numbers</a>, <a href="${esc(S.url("lost-pets/"))}">Lost pets</a> or <a href="${esc(S.url("directory/"))}">Places and streets A to Z</a>.</p>`;
      return;
    }
    render();
  }
})();
