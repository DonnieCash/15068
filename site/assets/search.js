/* NK15068 — search (window.NKSearch), shared by /search/ and the map's search panel.
   load(root) fetches data/search.json (pages, phone numbers, events, news, streets with incidents, synonyms) plus
   places.json and streets.json. match(q, data, opts) is pure: it returns the result groups in the order /search/ shows
   them — call, pages, corner, streets, places, events, news, pets — and each caller draws its own rows. */
(function () {
  "use strict";
  const TOWNS = ["New Kensington", "Arnold", "Lower Burrell"];
  /* town words in a query, longest first (a town word orders results; it never hides a phone number) */
  const TOWN_WORDS = [["new kensington", "New Kensington"], ["new ken", "New Kensington"], ["newken", "New Kensington"],
    ["lower burrell", "Lower Burrell"], ["arnold", "Arnold"]];
  const STOP = new Set(["the", "a", "an", "of", "in", "on", "for", "to", "near", "is", "my", "me", "where", "what", "how",
    "and", "at", "find", "show", "whats", "s"]);
  const CALL_WORDS = new Set(["call", "phone", "phones", "number", "numbers", "tel", "telephone", "contact"]);
  const PET_WORDS = /\b(lost|found|missing|stray|loose|runaway)\b/;
  const ANIMAL_WORDS = /\b(dog|dogs|cat|cats|pet|pets|puppy|kitten)\b/;
  const ORD = { first: "1", second: "2", third: "3", fourth: "4", fifth: "5", sixth: "6", seventh: "7", eighth: "8", ninth: "9",
    tenth: "10", eleventh: "11", twelfth: "12", thirteenth: "13", fourteenth: "14", fifteenth: "15", sixteenth: "16",
    seventeenth: "17", eighteenth: "18", nineteenth: "19", twentieth: "20" };
  const TYPES = { street: "st", avenue: "ave", av: "ave", road: "rd", drive: "dr", boulevard: "blvd", lane: "ln", court: "ct",
    place: "pl", alley: "aly", terrace: "ter", highway: "hwy", circle: "cir" };

  /* a word typed or read from a URL is looked up only among a table's own keys ("constructor" is not an ordinal) */
  const own = (o, k) => Object.prototype.hasOwnProperty.call(o, k);
  /* a route number with its prefix ("Route 366", "PA 366", "SR-780", "US Route 22", "Rt. 56") is one word, "rt366" */
  const ROUTE = /\b(?:(?:state|us|pa)\s+)?(?:route|rte|rt|sr|pa|us)\s*(\d{1,3})\b/g;
  /* lower case, no accents or apostrophes, "&" kept as a word, ordinals as numbers ("Fifth" and "5th" -> "5"),
     street types short ("Avenue" -> "ave"), route numbers as "rt366" */
  function norm(s) {
    return String(s ?? "").toLowerCase().normalize("NFKD").replace(/[\u0300-\u036f]/g, "").replace(/[’']/g, "")
      .replace(/&/g, " & ").replace(/[^a-z0-9&]+/g, " ").trim()
      .split(/\s+/).map((w) => (own(ORD, w) && ORD[w]) || (own(TYPES, w) && TYPES[w]) || w.replace(/^(\d+)(st|nd|rd|th)$/, "$1"))
      .join(" ").replace(ROUTE, "rt$1");
  }
  /* a word (or phrase) at the start of a word in h; numbers and route numbers match whole words only */
  function has(h, w) {
    if (!w) return true;
    if (/^(rt)?\d+$/.test(w) || w.length === 1) return (" " + h + " ").includes(" " + w + " ");
    if ((" " + h).includes(" " + w)) return true;
    const stem = w.length > 4 ? w.replace(/(es|s)$/, "") : w;
    return stem !== w && (" " + h).includes(" " + stem);
  }

  /* ---------------- street names (identical to pets.js / nkpages.fmt.street_key) ---------------- */
  const KTYPES = { street: "st", st: "st", avenue: "ave", ave: "ave", av: "ave", road: "rd", rd: "rd", drive: "dr", dr: "dr", boulevard: "blvd", blvd: "blvd",
    lane: "ln", ln: "ln", court: "ct", ct: "ct", place: "pl", pl: "pl", way: "way", alley: "aly", aly: "aly", terrace: "ter", ter: "ter", highway: "hwy", hwy: "hwy", pike: "pike", circle: "cir", cir: "cir" };
  function streetKey(name) {
    if (!name) return null;
    let t = String(name).toLowerCase().replace(/[.,#']/g, " ").split(/\s+/).filter(Boolean);
    t = t.map((w) => (own(ORD, w) && ORD[w]) || w.replace(/^(\d+)(st|nd|rd|th)$/, "$1"));
    let type = null;
    while (t.length && own(KTYPES, t[t.length - 1])) { type = type || KTYPES[t[t.length - 1]]; t.pop(); }
    if (t.length > 1 && /^(n|s|e|w|north|south|east|west)$/.test(t[0])) t.shift();
    const core = t.join(" ");
    return core ? { core, type } : null;
  }

  /* ---------------- places: the directory's de-duplication key, and only true repeats merged here ---------------- */
  const normName = (s) => String(s || "").toLowerCase().replace(/\b(new kensington|lower burrell|arnold|the|pa)\b/g, "").replace(/[^a-z0-9]/g, "");
  function dedupeKey(p) {
    const d = String(p.ph || "").replace(/\D/g, "");
    return d ? `${d}|${normName(p.n)}` : `${normName(p.n)}|${Math.floor(p.x / 50)},${Math.floor(p.y / 50)}`;
  }
  /* the directory's rule: one row per key, the highest q */
  function dedupe(places) {
    const best = new Map();
    for (const p of places) { const k = dedupeKey(p); const b = best.get(k); if (!b || (p.q || 0) > (b.q || 0)) best.set(k, p); }
    const keep = new Set(best.values());
    return places.filter((p) => keep.has(p));
  }
  /* search keeps branches that share a head-office phone: only the same key at the same address (or within 50 m)
     counts as a repeat */
  function repeats(places) {
    const seen = new Map(), out = [];
    const addr = (p) => norm(String(p.a || "").split(",")[0]);
    for (const p of [...places].sort((a, b) => (b.q || 0) - (a.q || 0))) {
      const k = dedupeKey(p), list = seen.get(k) || [];
      if (list.some((o) => (addr(o) && addr(o) === addr(p)) || Math.hypot(o.x - p.x, o.y - p.y) < 50)) continue;
      list.push(p); seen.set(k, list); out.push(p);
    }
    const keep = new Set(out);
    return places.filter((p) => keep.has(p));
  }
  function townLabel(p) {
    const parts = String(p.a || "").split(",").map((s) => s.trim());
    if (parts.length >= 2) {
      const low = parts[1].toLowerCase().replace(/-/g, " ");
      const fixed = { "new kensington": "New Kensington", "new kensingtn": "New Kensington", "new kinsington": "New Kensington",
        "lower burrell": "Lower Burrell", arnold: "Arnold" }[low];
      if (fixed) return fixed;
    }
    return p.t || "";
  }
  /* the same slug as nkpages.fmt.slug (accents dropped, not turned into dashes) */
  const placeSlug = (s) => String(s || "").normalize("NFKD").replace(/[^\x00-\x7f]/g, "").toLowerCase().replace(/[^a-z0-9]+/g, "-").replace(/^-+|-+$/g, "");
  const placeParam = (p) => `${placeSlug(p.n)}~${Math.round(p.x)},${Math.round(p.y)}`;
  /* a place's website or social link as the data gives it: an http(s) URL as it is, a bare host name ("www.example.com",
     "example.com/menu") with https:// in front, anything else (a handle like "EdwardJones", an address cut off with
     "...") no link at all */
  function webURL(v) {
    const s = String(v ?? "").trim();
    if (!s || /\s|(\.\.\.|\u2026)$/.test(s)) return "";
    if (/^https?:\/\/[^/?#:]+\.[^/?#:]+/i.test(s)) return s;
    if (/^([a-z0-9](?:[a-z0-9-]*[a-z0-9])?\.)+[a-z]{2,}(:\d+)?([/?#]|$)/i.test(s)) return "https://" + s;
    return "";
  }

  /* ---------------- data ---------------- */
  let loading = null;
  function load(root) {
    if (!loading) {
      const r = root ?? ((typeof document !== "undefined" && document.documentElement.dataset.root) || "");
      const get = (n) => (window.NK && window.NK.getJSON ? window.NK.getJSON(n)
        : fetch(r + "data/" + n).then((x) => { if (!x.ok) throw new Error(n + " " + x.status); return x.json(); }));
      loading = Promise.all([get("search.json"), get("places.json"), get("streets.json"), get("meta.json")])
        .then(([s, places, streets, meta]) => prepare({ ...s, places, streets, groups: meta.groups || {} }));
      loading.catch(() => { loading = null; });
    }
    return loading;
  }
  /* the haystacks, built once */
  function prepare(d) {
    const groups = d.groups || {};
    const incBy = new Map((d.streets_inc || []).map((s) => [s.s, s]));
    d.places = repeats(d.places || []);
    d.places.forEach((p, i) => {
      if (p.id == null) p.id = i;
      p._town = townLabel(p);
      p._h = norm([p.n, p.c, p.a, p._town, groups[p.g]].join(" "));
      p._name = norm(p.n);
    });
    const seen = new Set();
    d.streets = (d.streets || []).filter((s) => !seen.has(s.n) && seen.add(s.n));
    /* a street's route numbers match as typed ("366") and with a prefix ("Route 366", "PA 366") */
    const refs = (s) => (s.ref || []).flatMap((r) => (/^\d+$/.test(r) ? [r, "route " + r] : [r]));
    d.streets.forEach((s) => { s._h = norm([s.n, ...refs(s)].join(" ")); s._k = streetKey(s.n); s._inc = incBy.get(s.n) || null; });
    (d.numbers || []).forEach((r) => { r._h = norm([r.n, r.t, r.k].join(" ")); });
    (d.pages || []).forEach((r) => { r._h = norm([r.t, r.k, r.u.replace(/[/-]/g, " ")].join(" ")); });
    (d.events || []).forEach((r) => { r._h = norm(r.n); }); // not the label: its times ("5–9 p.m.") match stray words
    (d.news || []).forEach((r) => { r._h = norm([r.h, r.o].join(" ")); });
    d.syns = Object.entries(d.syn || {}).map(([canon, list]) => {
      const cw = norm(canon).split(" ");
      const members = [canon, ...list].map(norm).sort((a, b) => b.length - a.length);
      return { canon: norm(canon), members, words: cw };
    });
    d.ready = true;
    return d;
  }

  /* ---------------- the query ---------------- */
  function parse(q, d) {
    const raw = norm(q);
    let t = " " + raw + " ";
    const towns = [];
    for (const [w, T] of TOWN_WORDS) {
      if (t.includes(" " + w + " ")) { if (!towns.includes(T)) towns.push(T); t = t.split(" " + w + " ").join(" "); }
    }
    const text = t.trim();
    const concepts = [];
    for (const g of d.syns || []) {
      const hit = g.members.find((m) => t.includes(" " + m + " "));
      if (!hit) continue;
      /* a one-word synonym that is part of the canonical name ("city" for "city hall") only counts when typed */
      const members = g.members.filter((m) => m === hit || m.includes(" ") || !g.words.includes(m) || m === g.canon);
      concepts.push({ canon: g.canon, hit, members, words: g.words });
      t = t.split(" " + hit + " ").join(" ");
    }
    const words = t.split(/\s+/).filter(Boolean);
    const call = words.some((w) => CALL_WORDS.has(w));
    const tokens = words.filter((w) => !STOP.has(w) && !CALL_WORDS.has(w) && w !== "&");
    const petIntent = concepts.some((c) => c.canon === "lost pet") || (PET_WORDS.test(raw) && ANIMAL_WORDS.test(raw));
    const trash = concepts.some((c) => c.canon === "trash");
    const m = raw.match(/^(.+?)\s+(?:&|and|at)\s+(.+)$/);
    const corner = m && m[1].trim() && m[2].trim() && !/^(&|and|at)$/.test(m[2].trim()) ? String(q).trim() : null;
    return { q: String(q || "").trim(), raw, text, towns, concepts, tokens, call, petIntent, trash, corner };
  }
  const conceptIn = (h, c) => c.members.some((m) => has(h, m)) || c.words.every((w) => has(h, w));
  /* every token and every concept is found in the haystack; town words count too when asked (withTowns) */
  function hits(h, P, withTowns) {
    if (!P.tokens.every((w) => has(h, w))) return false;
    if (!P.concepts.every((c) => conceptIn(h, c))) return false;
    if (withTowns && !P.towns.every((t) => has(h, norm(t)))) return false;
    return true;
  }
  const empty = (P) => !P.tokens.length && !P.concepts.length && !P.towns.length && !P.call;
  const byTown = (list, key, towns) => {
    if (!towns.length) return list;
    return [...list].sort((a, b) => (towns.includes(key(b)) ? 1 : 0) - (towns.includes(key(a)) ? 1 : 0));
  };

  /* opts: {town: my town, pets: board posts, spot: {x, y} to measure places from} */
  function match(q, d, opts = {}) {
    const P = parse(q, d);
    const G = { call: [], pages: [], corner: [], streets: [], places: [], events: [], news: [], pets: [] };
    const out = { q: P.q, parsed: P, gap: false, groups: G, total: 0 };
    if (!P.raw || empty(P)) return out;
    const bare = !P.tokens.length && !P.concepts.length; // only town words (and maybe "phone")

    /* 1. call: every phone-number row whose words match; a town word puts that town first */
    let call = (d.numbers || []).filter((r) => (bare ? (P.towns.length ? P.towns.includes(r.t) : P.call) : hits(r._h, P, false)));
    /* rows that name what was typed (or its canonical word) come before rows found through a synonym */
    const score = (r) => P.concepts.reduce((n, c) => n + (has(r._h, c.hit) ? 2 : 0) + (has(r._h, c.canon) ? 1 : 0), 0);
    call = call.map((r, i) => [r, score(r), i]).sort((a, b) => b[1] - a[1] || a[2] - b[2]).map((x) => x[0]);
    call = byTown(call, (r) => r.t, P.towns.length ? P.towns : opts.town ? [opts.town] : []);
    if (P.trash) {
      call = call.filter((r) => /city hall/i.test(r.n));
      out.gap = true;
    }
    G.call = call;

    /* 2. pages: a lost-pet question pins the lost and found page first */
    let pages = (d.pages || []).filter((r) => (bare ? P.towns.some((t) => has(r._h, norm(t))) : hits(r._h, P, false)));
    pages = byTown(pages, (r) => (P.towns.find((t) => has(r._h, norm(t))) || ""), P.towns);
    if (P.petIntent) {
      const lp = (d.pages || []).find((r) => r.u === "lost-pets/");
      if (lp) pages = [lp, ...pages.filter((r) => r !== lp)];
    }
    G.pages = pages;

    /* 3. a corner: two parts joined by &, "and" or "at", each naming a street in 15068 */
    if (P.corner) {
      const parts = P.raw.split(/\s+(?:&|and|at)\s+/).slice(0, 2).map((x) => streetKey(x));
      const known = (k) => k && (d.streets || []).some((st) => st._k && st._k.core === k.core);
      if (parts.length === 2 && parts.every(known)) G.corner = [{ text: P.corner }];
    }

    /* 4. streets: the same street key (Fifth Ave = 5th Avenue), then names that start with the words */
    if (P.tokens.length && !P.concepts.length) {
      const text = P.tokens.join(" ");
      const k = streetKey(text);
      const exact = [], keyed = [], named = [];
      for (const s of d.streets || []) {
        if (s._h === text) exact.push(s);
        else if (k && s._k && s._k.core === k.core && (!k.type || !s._k.type || k.type === s._k.type)) keyed.push(s);
        else if (P.tokens.every((w) => has(s._h, w))) named.push(s);
      }
      const big = (a, b) => (b.a || 0) - (a.a || 0) || b.m - a.m;
      let streets = [...exact, ...keyed.sort(big), ...named.sort(big)];
      streets = byTown(streets, (s) => ((s.t || []).find((t) => P.towns.includes(t)) || ""), P.towns);
      G.streets = streets;
    }

    /* 5. places: every word matches the name, type, address or town; my town first, then the best-kept listings */
    if (!bare || P.towns.length) {
      const mine = opts.town;
      let places = (d.places || []).filter((p) => hits(p._h, P, true));
      if (opts.spot) places.forEach((p) => { p._d = Math.hypot(p.x - opts.spot.x, p.y - opts.spot.y); });
      /* a name that is (or starts with) what was typed comes first; then my town, then the best-kept listings */
      const phrase = P.text;
      const tier = (p) => (!phrase ? 2 : p._name === phrase ? 0 : p._name.startsWith(phrase + " ") ? 1 : 2);
      places.sort((a, b) => tier(a) - tier(b) || (mine ? (b._town === mine) - (a._town === mine) : 0) || (b.q || 0) - (a.q || 0) || a.n.localeCompare(b.n));
      G.places = places;
    }

    /* 6-7. what's on and news */
    if (!bare) {
      G.events = (d.events || []).filter((r) => hits(r._h, P, true));
      G.news = (d.news || []).filter((r) => hits(r._h, P, true));
    } else {
      G.events = (d.events || []).filter((r) => P.towns.some((t) => has(r._h, norm(t))));
      G.news = (d.news || []).filter((r) => P.towns.some((t) => has(r._h, norm(t))));
    }

    /* 8. lost and found listings from the board */
    const STATUS = { lost: "lost missing", found: "found", spotted: "spotted seen" };
    const animal = (P.raw.match(/\b(dog|cat)s?\b/) || [])[1];
    G.pets = (opts.pets || []).filter((p) => {
      const h = norm([STATUS[p.status] || "", p.animal, p.animal === "dog" || p.animal === "cat" ? "pet" : "pet animal",
        p.name, p.desc, p.near, p.town].join(" "));
      /* "lost dog": every dog on the board (a found or spotted dog may be the one), in the town asked about */
      if (P.petIntent && !P.tokens.length) return (!animal || p.animal === animal) && (!P.towns.length || P.towns.includes(p.town));
      return hits(h, { ...P, concepts: P.concepts.filter((c) => c.canon !== "lost pet") }, true);
    });

    out.total = Object.values(G).reduce((n, g) => n + g.length, 0);
    return out;
  }

  window.NKSearch = { load, prepare, match, parse, norm, streetKey, dedupe, dedupeKey, townLabel, placeParam, placeSlug, webURL, TOWNS };
})();
