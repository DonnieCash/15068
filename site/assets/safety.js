/* NK15068 — crime and safety helpers (window.NKSafety).
   The crime pages are built as static HTML by scripts/nkpages/pages_crime.py; this file adds the chart readouts
   (wirePanels), the police-blotter filters (enhanceBlotter) and the labels the map uses for incidents.
   Loaded before app.js, so NKS (the shell) is only used inside functions called after load. */
(function () {
  "use strict";
  const TOWNS = ["New Kensington", "Arnold", "Lower Burrell"];
  const CAT = { violent: "Violent", property: "Property", police: "Police and other" };
  const TYPE = {
    homicide: "Homicide", shooting: "Shooting", stabbing: "Stabbing", robbery: "Robbery", assault: "Assault",
    burglary: "Burglary", theft: "Theft", vehicle_theft: "Vehicle theft", arson: "Arson", fire: "Fire",
    drugs: "Drug case", weapons: "Weapons", pursuit: "Police pursuit", standoff: "Standoff",
    police_shooting: "Police shooting", use_of_force: "Use of force", crash: "Crash", vandalism: "Vandalism",
    fraud: "Fraud", other: "Other",
  };
  const OFFENSES = [["murder", "Murder & manslaughter"], ["rape", "Rape"], ["robbery", "Robbery"], ["agg_assault", "Aggravated assault"],
    ["burglary", "Burglary"], ["larceny", "Larceny-theft"], ["mvt", "Motor vehicle theft"], ["arson", "Arson"]];
  const PREC = { block: "hundred-block", intersection: "intersection", place: "named place", street: "street only (approximate)" };
  const NEAR_M = 120; // "within a block (400 ft)"

  const fmt = (n, d = 0) => Number(n).toLocaleString("en-US", { minimumFractionDigits: d, maximumFractionDigits: d });
  const apDate = (d) => (window.NKS ? window.NKS.apDate(d) : window.NKapDate ? window.NKapDate(d) : String(d ?? ""));
  const monthName = (d) => apDate(d);

  function agencyFor(fbi, town) {
    return (fbi.agencies || []).find((a) => a.municipality === town || (a.agency || "").includes(town));
  }
  const val = (y, k) => (typeof k === "function" ? k(y) : y?.[k]);
  const rate = (y, k) => { const v = val(y, k); return v != null && y.population ? v / y.population * 1000 : null; };
  function niceMax(v) {
    const p = Math.pow(10, Math.floor(Math.log10(v || 1)));
    for (const m of [1, 1.5, 2, 2.5, 3, 4, 5, 6, 8, 10]) if (m * p >= v) return m * p;
    return 10 * p;
  }

  /* ---------- chart readouts: hover, touch and arrow keys on the static SVG panels ---------- */
  function wirePanels(root) {
    (root || document).querySelectorAll(".panel-chart").forEach((pc) => {
      if (pc.dataset.wired) return;
      let pts;
      try { pts = JSON.parse(pc.dataset.pts || "[]"); } catch (e) { return; }
      if (!pts.length) return;
      pc.dataset.wired = "1";
      const svg = pc.querySelector("svg"), tip = pc.querySelector(".tip"), xh = svg && svg.querySelector(".xh");
      if (!svg || !tip || !xh) return;
      const y0 = +pc.dataset.y0, y1 = +pc.dataset.y1, vmax = +pc.dataset.vmax;
      const W = 320, H = 172, L = 34, R = 34, T = 12, B = 24;
      const x = (yr) => L + (y1 === y0 ? 0.5 : (yr - y0) / (y1 - y0)) * (W - L - R);
      const y = (v) => T + (1 - v / vmax) * (H - T - B);
      let idx = pts.length - 1;
      const show = (i) => {
        idx = Math.max(0, Math.min(pts.length - 1, i));
        const p = pts[idx], k = svg.getBoundingClientRect().width / W;
        xh.setAttribute("x1", x(p.year)); xh.setAttribute("x2", x(p.year)); xh.setAttribute("visibility", "visible");
        tip.hidden = false;
        tip.style.left = Math.max(60, Math.min(svg.getBoundingClientRect().width - 60, x(p.year) * k)) + "px";
        tip.style.top = (y(p.v) * k + 22) + "px";
        tip.textContent = "";
        const b = document.createElement("b");
        b.textContent = p.c ? `${fmt(p.n)} ${pc.dataset.label.toLowerCase()}` : fmt(p.v, 1) + " per 1,000";
        const s = document.createElement("span");
        s.textContent = p.c ? String(p.year) : `${p.year} · ${fmt(p.n)} total${p.m && p.m < 12 ? ` · ${p.m} of 12 months` : ""}${p.est ? " · population estimated" : ""}`;
        tip.append(b, s);
      };
      const hide = () => { tip.hidden = true; xh.setAttribute("visibility", "hidden"); };
      svg.addEventListener("pointermove", (e) => {
        const r = svg.getBoundingClientRect(), yr = y0 + ((e.clientX - r.left) / r.width * W - L) / (W - L - R) * (y1 - y0);
        let best = 0;
        pts.forEach((p, i) => { if (Math.abs(p.year - yr) < Math.abs(pts[best].year - yr)) best = i; });
        show(best);
      });
      svg.addEventListener("pointerleave", hide);
      svg.addEventListener("focus", () => show(idx));
      svg.addEventListener("blur", hide);
      svg.addEventListener("keydown", (e) => {
        if (e.key === "ArrowLeft") { show(idx - 1); e.preventDefault(); }
        if (e.key === "ArrowRight") { show(idx + 1); e.preventDefault(); }
        if (e.key === "Escape") hide();
      });
    });
  }
  function enhanceCharts(root) { wirePanels(root || document); }

  /* ---------- incident ids: identical to nkpages.fmt.inc_ids / fmt.slug ---------- */
  const slug = (s) => String(s ?? "").normalize("NFKD").replace(/[^\x00-\x7f]/g, "").toLowerCase()
    .replace(/[^a-z0-9]+/g, "-").replace(/^-+|-+$/g, "");
  function incIds(list) {
    const seen = new Map();
    return (list || []).map((i) => {
      const base = `${i.d ?? ""}-${slug(i.l ?? "")}`;
      const n = (seen.get(base) || 0) + 1;
      seen.set(base, n);
      return n === 1 ? base : `${base}-${n}`;
    });
  }

  /* ---------- street names: identical to pets.js / nkpages.fmt.street_key ---------- */
  const ORD = { first: "1", second: "2", third: "3", fourth: "4", fifth: "5", sixth: "6", seventh: "7", eighth: "8", ninth: "9", tenth: "10",
    eleventh: "11", twelfth: "12", thirteenth: "13", fourteenth: "14", fifteenth: "15", sixteenth: "16", seventeenth: "17", eighteenth: "18", nineteenth: "19", twentieth: "20" };
  const TYPES = { street: "st", st: "st", avenue: "ave", ave: "ave", av: "ave", road: "rd", rd: "rd", drive: "dr", dr: "dr", boulevard: "blvd", blvd: "blvd",
    lane: "ln", ln: "ln", court: "ct", ct: "ct", place: "pl", pl: "pl", way: "way", alley: "aly", aly: "aly", terrace: "ter", ter: "ter", highway: "hwy", hwy: "hwy", pike: "pike", circle: "cir", cir: "cir" };
  function streetKey(name) {
    if (!name) return null;
    let t = String(name).toLowerCase().replace(/[.,#']/g, " ").split(/\s+/).filter(Boolean);
    t = t.map((w) => ORD[w] || w.replace(/^(\d+)(st|nd|rd|th)$/, "$1"));
    let type = null;
    while (t.length && TYPES[t[t.length - 1]]) { type = type || TYPES[t[t.length - 1]]; t.pop(); }
    if (t.length > 1 && /^(n|s|e|w|north|south|east|west)$/.test(t[0])) t.shift();
    const core = t.join(" ");
    return core ? { core, type } : null;
  }
  /* an entry's streets from data-st / data-sty ("5|hileman", "ave|dr") */
  function entryStreets(el) {
    const cores = (el.dataset.st || "").split("|"), types = (el.dataset.sty || "").split("|");
    return cores.map((core, i) => ({ core, type: types[i] || null })).filter((s) => s.core);
  }
  const typeOk = (a, b) => !a || !b || a === b;
  const onStreet = (el, k) => entryStreets(el).some((s) => s.core === k.core && typeOk(k.type, s.type));

  /* ---------- road lines, loaded once when "within a block" is first ticked ---------- */
  let linesP = null;
  function decode(arr, q) {
    if (window.NK && typeof window.NK.dec === "function") return window.NK.dec(arr, q);
    const out = new Float32Array(arr.length);
    let x = 0, y = 0;
    for (let i = 0; i < arr.length; i += 2) { x += arr[i]; y += arr[i + 1]; out[i] = x / q; out[i + 1] = y / q; }
    return out;
  }
  function loadLines() {
    if (!linesP) {
      const get = (n) => fetch(window.NKS.url("data/" + n)).then((r) => { if (!r.ok) throw new Error(n + " " + r.status); return r.json(); });
      linesP = Promise.all([get("meta.json"), get("roads.json")]).then(([meta, roads]) =>
        roads.r.filter((r) => r[1] >= 0).map(([rank, ni, , c]) => ({ n: roads.names[ni], rank, pts: decode(c, meta.q) })));
      linesP.catch(() => { linesP = null; });
    }
    return linesP;
  }
  function segDist(px, py, ax, ay, bx, by) {
    const dx = bx - ax, dy = by - ay, L = dx * dx + dy * dy;
    const t = L ? Math.max(0, Math.min(1, ((px - ax) * dx + (py - ay) * dy) / L)) : 0;
    return Math.hypot(px - (ax + t * dx), py - (ay + t * dy));
  }
  function lineDist(px, py, pts) {
    let best = Infinity;
    for (let i = 0; i + 3 < pts.length; i += 2) best = Math.min(best, segDist(px, py, pts[i], pts[i + 1], pts[i + 2], pts[i + 3]));
    return best;
  }

  /* ---------- the police blotter: filters, street search, "within a block", URL state, map link ---------- */
  function enhanceBlotter(host) {
    const NKS = window.NKS;
    if (!host || !NKS) return;
    const $ = (s) => host.querySelector(s);
    const bar = $("#inc-filters"), list = $("#inc-list"), count = $("#inc-count"), none = $("#inc-none"), mapA = $("#inc-map");
    const selT = $("#inc-town"), selY = $("#inc-year"), inp = $("#inc-street"), near = $("#inc-near");
    if (!bar || !list) return;
    bar.hidden = false;
    const entries = [...list.querySelectorAll("article.entry")];
    const years = [...list.querySelectorAll(".inc-yr")];
    const mapBase = mapA ? mapA.getAttribute("href").split("?")[0] : "";
    const q = NKS.qs();
    const state = {
      c: CAT[q.get("c")] ? q.get("c") : "*",
      t: TOWNS.includes(q.get("town")) ? q.get("town") : "",
      y: /^\d{4}$/.test(q.get("year") || "") ? q.get("year") : "",
      st: (q.get("street") || "").slice(0, 60),
      near: false,
    };
    if (state.y && selY && ![...selY.options].some((o) => o.value === state.y || o.text === state.y)) state.y = "";
    if (selT) selT.value = state.t;
    if (selY) selY.value = state.y;
    if (inp) inp.value = state.st;
    let lines = null, nearIds = new Set(), nearFor = "";

    const chips = [...bar.querySelectorAll("[data-c]")];
    const syncChips = () => chips.forEach((b) => b.setAttribute("aria-pressed", String(b.dataset.c === state.c)));

    function computeNear(k) {
      nearIds = new Set();
      nearFor = k ? k.core + "|" + (k.type || "") : "";
      if (!k || !lines) return;
      const segs = lines.filter((l) => { const lk = streetKey(l.n); return lk && lk.core === k.core && typeOk(k.type, lk.type); });
      if (!segs.length) return;
      entries.forEach((el) => {
        if (onStreet(el, k)) return;
        const x = +el.dataset.mx, y = +el.dataset.my;
        if (segs.some((l) => lineDist(x, y, l.pts) <= NEAR_M)) nearIds.add(el.dataset.id);
      });
    }

    function draw() {
      const k = state.st ? streetKey(state.st) : null;
      if (near) near.disabled = !k;
      const useNear = state.near && k && lines;
      if (useNear && nearFor !== k.core + "|" + (k.type || "")) computeNear(k);
      let n = 0, extra = 0;
      entries.forEach((el) => {
        let ok = (state.c === "*" || el.dataset.c === state.c) && (!state.t || el.dataset.t === state.t)
          && (!state.y || el.dataset.yr === state.y);
        let isNear = false;
        if (ok && state.st) {
          if (!k) ok = false;
          else if (!onStreet(el, k)) { isNear = !!(useNear && nearIds.has(el.dataset.id)); ok = isNear; }
        }
        el.hidden = !ok;
        el.classList.toggle("near", isNear);
        if (ok) { n++; if (isNear) extra++; }
      });
      years.forEach((s) => { s.hidden = !s.querySelector("article.entry:not([hidden])"); });
      if (none) none.hidden = n > 0;
      if (count) {
        count.textContent = `${fmt(n)} incident${n === 1 ? "" : "s"} with a mappable location`
          + (extra ? `, ${fmt(extra)} of them within a block of the street` : "");
      }
      const params = { layer: "incidents", town: state.t, year: state.y, street: state.st.trim(), c: state.c === "*" ? "" : state.c };
      if (mapA) {
        const p = new URLSearchParams();
        Object.entries(params).forEach(([key, v]) => { if (v) p.set(key, v); });
        mapA.setAttribute("href", mapBase + "?" + p.toString().replace(/%2C/g, ","));
      }
      NKS.setQS({ town: state.t, year: state.y, street: state.st.trim(), c: state.c === "*" ? "" : state.c });
      syncChips();
    }

    bar.addEventListener("click", (e) => {
      const b = e.target.closest("[data-c]");
      if (!b) return;
      state.c = b.dataset.c;
      draw();
    });
    if (selT) selT.addEventListener("change", () => { state.t = selT.value; draw(); });
    if (selY) selY.addEventListener("change", () => { state.y = selY.value; draw(); });
    let timer = 0;
    if (inp) {
      inp.addEventListener("input", () => { clearTimeout(timer); timer = setTimeout(() => { state.st = inp.value.slice(0, 60); draw(); }, 150); });
      inp.addEventListener("keydown", (e) => { if (e.key === "Enter") { e.preventDefault(); clearTimeout(timer); state.st = inp.value.slice(0, 60); draw(); } });
    }
    if (near) {
      near.addEventListener("change", async () => {
        state.near = near.checked;
        if (state.near && !lines) {
          if (count) count.textContent = "Measuring distances to the street…";
          try { lines = await loadLines(); } catch (e) {
            console.warn(e);
            near.checked = false; state.near = false;
            draw();
            if (count) count.textContent += ". The street map didn't load, so nearby incidents can't be added right now.";
            return;
          }
        }
        draw();
      });
    }
    draw();
  }

  window.NKSafety = {
    TOWNS, CAT, TYPE, OFFENSES, PREC, monthName, niceMax, agencyFor, rate,
    wirePanels, enhanceCharts, enhanceBlotter, incIds, streetKey, loadLines,
  };
})();
