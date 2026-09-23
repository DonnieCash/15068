/* NK15068 — lost & found pets board (window.NKPets).
   Backends, chosen at run time:
   - inside the Claude artifact viewer: a shared `db` store (each viewer writes only
     their own document, everyone reads all of them);
   - anywhere else (GitHub Pages): open GitHub issues made with the "Lost or found pet"
     issue form. The deploy writes them to data/pets-board.json (scripts/snapshot_pets.py);
     that snapshot is trusted while it is at most 26 hours old, and only otherwise does the
     page ask GitHub's public API. If the API fails and there is no snapshot, the board says
     it doesn't know (state "unknown"); it never claims the board is empty.
   Locations are street + cross street, placed from the site's own road data.
   scripts/nkpages/pets.py holds exact Python ports of cleanNear, stripHouse, sanitize,
   parseIssue, streetKey, buildIndex and geocodeNear (tests/test_pages_pets.py compares them).
   This file must load with no DOM (the parity test runs it in a bare vm with window = {}). */
(function () {
  "use strict";
  const doc = typeof document !== "undefined" ? document : null;
  const esc = (s) => String(s ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
  const REPO = "DonnieCash/15068";
  const ISSUE_FORM = `https://github.com/${REPO}/issues/new?template=lost-found-pet.yml`;
  const ISSUES = `https://github.com/${REPO}/issues`;
  const TOWNS = ["New Kensington", "Arnold", "Lower Burrell"];
  const MAX_PER_VIEWER = 20;
  const LIMITS = { name: 40, desc: 500, near: 120, contact: 120, town: 40, animal: 20 };
  const FRESH_MS = 26 * 36e5; // a snapshot this new is trusted without asking GitHub
  const STATUS = { lost: "Lost", found: "Found", spotted: "Spotted" };
  const VERB = { lost: "Last seen near", found: "Found near", spotted: "Seen near" };
  const FORM_MARK = "### Lost, found or spotted?";
  const NKS = () => window.NKS || null;
  const root = () => (doc && doc.documentElement.dataset.root) || "";

  /* house numbers never ship: drop standalone numbers and ranges ("1025", "1025-1027", "12B"),
     keep ordinals ("9th") and route numbers ("Route 56", "PA 366", "SR 780") */
  function cleanNear(t) {
    return String(t || "")
      .replace(/\b(route|rte|pa|sr|us|i)[\s-]*(\d{1,4})\b/gi, (m, a, n) => a + "\u2009" + n) // protect route numbers
      .replace(/\b(\d{0,3}00)\s+block\b/gi, "\u2009$1\u2009block") // hundred-blocks are coarse enough to keep
      .replace(/(^|[^\w\u2009])\d{1,5}[a-z]?(?:\s*[-–]\s*\d{1,5}[a-z]?)?(?![\w\u2009])(?!\s*(?:st|nd|rd|th)\b)/gi, "$1")
      .replace(/\u2009/g, " ")
      .replace(/\s{2,}/g, " ").replace(/^[\s,&]+|[\s,]+$/g, "").trim();
  }
  /* in free text (description, contact) only a number right before a street name is a house number:
     "found at 1012 Fifth Ave" -> "found at Fifth Ave"; phone numbers, ordinals and routes stay */
  function stripHouse(t) {
    return String(t || "")
      .replace(/\b(route|rte|pa|sr|us|i)[\s-]*(\d{1,4})\b/gi, (m, a, n) => a + "\u2009" + n)
      .replace(/(^|[^\w\u2009-])\d{1,5}[a-z]?(?:\s*[-–]\s*\d{1,5}[a-z]?)?(?=\s+(?:[nsew]\.?\s+)?(?:\d+(?:st|nd|rd|th)|[a-z]+)\s+(?:street|st|avenue|ave|av|road|rd|drive|dr|boulevard|blvd|lane|ln|way|court|ct|alley|aly|place|pl|terrace|ter|highway|hwy|pike|circle|cir)\b)/gi, "$1")
      .replace(/\u2009/g, " ")
      .replace(/ {2,}/g, " ").trim();
  }
  const clip = (v, k) => String(v ?? "").trim().slice(0, LIMITS[k] || 40);
  const GH_IMG = /^https:\/\/(user-images\.githubusercontent\.com|github\.com\/user-attachments)\//;
  const GH_ISSUE = new RegExp(`^https://github\\.com/${REPO.replace("/", "\\/")}/issues/\\d+$`);
  /* posts in the shared store (and the snapshot) are untrusted: rebuild each one from an allow-list */
  function sanitize(p, source) {
    if (!p || typeof p !== "object" || typeof p.status !== "string" || !/^(lost|found|spotted)$/.test(p.status)) return null;
    const out = {
      id: clip(p.id, "name"), status: p.status,
      animal: typeof p.animal === "string" && /^(dog|cat|other)$/i.test(p.animal) ? p.animal.toLowerCase() : "other",
      name: clip(p.name, "name"), desc: stripHouse(clip(p.desc, "desc")), near: cleanNear(clip(p.near, "near")),
      town: TOWNS.includes(p.town) ? p.town : "", date: typeof p.date === "string" && /^\d{4}-\d{2}-\d{2}$/.test(p.date) ? p.date : "",
      contact: stripHouse(clip(p.contact, "contact")),
      created: typeof p.created === "string" && /^\d{4}-\d{2}-\d{2}T[\d:.]+Z$/.test(p.created) ? p.created : "", source,
    };
    if (Number.isFinite(p.x) && Number.isFinite(p.y) && Math.abs(p.x) < 2e4 && Math.abs(p.y) < 2e4) {
      out.x = Math.round(p.x / 10) * 10; out.y = Math.round(p.y / 10) * 10;
      out.prec = typeof p.prec === "string" && /^(intersection|street|picked)$/.test(p.prec) ? p.prec : "picked";
      if (typeof p.placeLabel === "string" && p.placeLabel.trim()) out.placeLabel = clip(p.placeLabel, "near");
    }
    if (source === "github") {
      if (GH_ISSUE.test(p.url || "")) out.url = p.url;
      if (GH_IMG.test(p.photo || "")) out.photo = p.photo;
    }
    return out;
  }

  /* ---------------- street matching (nkpages/fmt.py street_key is the Python port) ---------------- */
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

  /* src: the map's world (W.lines) or {lines}: [{n, pts: flat x,y array}] */
  function buildIndex(src) {
    const idx = new Map();
    for (const l of (src && src.lines) || []) {
      if (!l.n) continue;
      const k = streetKey(l.n);
      if (!k) continue;
      if (!idx.has(k.core)) idx.set(k.core, []);
      idx.get(k.core).push({ type: k.type, pts: l.pts, n: l.n });
    }
    return idx;
  }

  /* "Fifth Avenue & 9th Street" -> {x, y, prec, label} using the road lines */
  function geocodeNear(text, idx, streets, town) {
    const parts = String(text || "").split(/\s*(?:&|\band\b|\bat\b|\/|@|,|\bnear\b)\s*/i).map((s) => s.trim()).filter(Boolean);
    const lines = (name) => {
      const k = streetKey(name);
      if (!k) return [];
      const all = (idx && idx.get(k.core)) || [];
      const typed = all.filter((l) => !k.type || !l.type || l.type === k.type);
      return typed.length ? typed : all;
    };
    if (parts.length >= 2) {
      const A = lines(parts[0]), B = lines(parts[1]);
      let best = null;
      for (const a of A) for (const b of B) {
        for (let i = 0; i < a.pts.length; i += 2) for (let j = 0; j < b.pts.length; j += 2) {
          const d = (a.pts[i] - b.pts[j]) ** 2 + (a.pts[i + 1] - b.pts[j + 1]) ** 2;
          if (!best || d < best.d) best = { d, x: (a.pts[i] + b.pts[j]) / 2, y: (a.pts[i + 1] + b.pts[j + 1]) / 2, na: a.n, nb: b.n };
        }
      }
      if (best && best.d < 80 * 80) return { x: best.x, y: best.y, prec: "intersection", label: `${best.na} & ${best.nb}` };
    }
    // single street: its label point in the right town
    const k = streetKey(parts[0]);
    if (k) {
      const cands = (streets || []).filter((s) => { const sk = streetKey(s.n); return sk && sk.core === k.core && (!k.type || !sk.type || sk.type === k.type); });
      const inTown = cands.find((s) => (s.t || []).includes(town)) || cands[0];
      if (inTown) return { x: inTown.x, y: inTown.y, prec: "street", label: inTown.n };
    }
    return null;
  }

  /* ---------------- GitHub issue-form parsing ---------------- */
  const isPetIssue = (i) => !!i && !i.pull_request && String(i.body || "").includes(FORM_MARK);
  function parseIssue(issue) {
    const body = String(issue.body || "");
    const field = (label) => {
      const m = body.match(new RegExp(`###\\s*${label}[^\\n]*\\n+([\\s\\S]*?)(?=\\n###|$)`, "i"));
      const v = m ? m[1].trim() : "";
      return v === "_No response_" ? "" : v;
    };
    const titleStatus = (String(issue.title || "").match(/^\s*\[(lost|found|spotted)\]/i) || [])[1];
    const status = (field("Lost, found or spotted") || titleStatus || "").toLowerCase();
    if (!/^(lost|found|spotted)$/.test(status)) return null;
    const img = (body.match(/!\[[^\]]*\]\((https:\/\/[^)\s]+)\)/) || body.match(/<img[^>]+src="(https:\/\/[^"]+)"/) || [])[1] || "";
    return sanitize({
      id: "gh-" + issue.number, url: issue.html_url, status,
      animal: (field("Animal") || "Other").toLowerCase(), name: field("Pet's name"), desc: field("Description").replace(/!\[[^\]]*\]\([^)]*\)|<img[^>]*>/g, "").trim(),
      near: field("Last seen near"), town: field("Town"), date: field("Date") || String(issue.created_at).slice(0, 10), contact: field("How to reach you"),
      photo: img,
      created: issue.created_at,
    }, "github");
  }

  /* ---------------- board ---------------- */
  /* state: loading | listed | empty | unknown | stale; known: the list is a real answer (listed, empty or stale) */
  const board = {
    posts: [], mode: "loading", state: "loading", fetched: null, stale: false, known: false,
    uid: null, mine: null, db: null, idx: null, streets: [], ui: null, error: "", canPost: false, readOnly: false,
    snapIds: new Set(), listeners: new Set(),
  };
  let started = null;

  async function useCap(name) {
    try { return window.claude && typeof window.claude.use === "function" ? await window.claude.use(name) : null; } catch (e) { return null; }
  }

  function place(p) {
    if (typeof p.x === "number" && typeof p.y === "number") return p;
    const g = p.near && board.idx ? geocodeNear(p.near, board.idx, board.streets, p.town) : null;
    return g ? { ...p, x: g.x, y: g.y, prec: g.prec, placeLabel: g.label } : p;
  }

  const sortKey = (p) => String(p.date || p.created);
  function notify() {
    if (board.ui && typeof board.ui.onChange === "function") { try { board.ui.onChange(board.posts); } catch (e) { console.error(e); } }
    for (const f of board.listeners) { try { f(board.posts, board); } catch (e) { console.error(e); } }
    badge();
  }
  function publish(list, state) {
    board.posts = list.map(place).sort((a, b) => sortKey(b).localeCompare(sortKey(a)));
    board.state = state || (board.posts.length ? "listed" : "empty");
    board.known = board.state !== "unknown" && board.state !== "loading";
    notify();
  }
  function unknown(msg) {
    board.state = "unknown"; board.known = false;
    board.error = msg || "The board didn't load just now, so we can't tell you what's posted.";
    notify();
  }

  async function githubPosts() {
    const r = await fetch(`https://api.github.com/repos/${REPO}/issues?state=open&per_page=100`, { headers: { Accept: "application/vnd.github+json" } });
    if (!r.ok) throw new Error("GitHub answered " + r.status);
    const issues = await r.json();
    if (!Array.isArray(issues)) throw new Error("GitHub answered with no list");
    return issues.filter(isPetIssue).map(parseIssue).filter(Boolean);
  }

  /* the live API; `snap` is a stale snapshot to fall back on */
  async function startGithub(snap) {
    board.mode = "github";
    try {
      const posts = await githubPosts();
      board.fetched = new Date().toISOString(); board.stale = false; board.error = "";
      publish(posts);
    } catch (e) {
      if (snap && snap.posts.length) {
        board.fetched = snap.fetched; board.stale = true; board.error = "";
        publish(snap.posts, "stale");
      } else unknown(); // never publish([]): an API failure is not an empty board
    }
  }

  /* data/pets-board.json from the deploy; trusted while it is at most 26 hours old. Deploy builds mark their
     pages with <meta name="nk-pets-snapshot">; without it there is no file to ask for (and no 404 to log). */
  async function startSnapshot() {
    board.mode = "github";
    let snap = null;
    if (doc && !doc.querySelector('meta[name="nk-pets-snapshot"]')) return startGithub(null);
    try {
      const r = await fetch(root() + "data/pets-board.json", { cache: "no-cache" });
      if (r.ok) {
        const j = await r.json();
        const t = Date.parse(j && j.fetched);
        if (j && Array.isArray(j.posts) && Number.isFinite(t)) {
          snap = { fetched: j.fetched, age: Date.now() - t, posts: j.posts.map((p) => sanitize(p, "github")).filter(Boolean) };
          snap.posts.forEach((p) => board.snapIds.add(p.id));
        }
      }
    } catch (e) { snap = null; }
    if (snap && snap.age <= FRESH_MS) {
      board.fetched = snap.fetched; board.stale = false;
      return publish(snap.posts);
    }
    return startGithub(snap);
  }

  async function startDb(db, user) {
    board.mode = "db";
    board.db = db;
    try { board.uid = user ? await user.id() : null; } catch (e) { board.uid = null; }
    board.canPost = typeof board.uid === "string" && board.uid.length > 0;
    db.collection("pets").onSnapshot((snap) => {
      const all = [];
      board.mine = null;
      for (const d of snap.docs) {
        const body = d.data() || {};
        if (d.id === board.uid) board.mine = body;
        for (const p of Array.isArray(body.posts) ? body.posts.slice(0, MAX_PER_VIEWER * 2) : []) {
          const clean = sanitize(p, "board");
          if (clean) all.push({ ...clean, owner: d.id === board.uid });
        }
      }
      board.fetched = new Date().toISOString();
      publish(all);
    }, () => { board.error = "The shared board is unavailable right now."; board.canPost = false; if (!board.known) unknown(board.error); else notify(); });
  }

  /* read the viewer's own document fresh before every write, so a stale snapshot (another tab,
     a dropped subscription) can never overwrite posts that are already stored */
  async function ownPosts() {
    const snap = await board.db.doc("pets/" + board.uid).get();
    const body = snap && snap.exists ? (typeof snap.data === "function" ? snap.data() : snap.data) || {} : {};
    return Array.isArray(body.posts) ? body.posts : [];
  }
  function writeError(e) {
    const code = e && e.code;
    if (code === "invalid_argument" || code === "not_granted" || code === "revoked" || code === "capability_disabled" || code === "capability_removed" || code === "transform_error") {
      board.readOnly = true; board.canPost = false;
      return new Error("You can read the board, but this page won't take posts from you. Post on GitHub instead.");
    }
    if (code === "quota_exceeded") return new Error("The board is full right now. Post on GitHub instead.");
    if (code === "resource_exhausted") return new Error("Too many changes at once. Wait a minute and try again.");
    return new Error("It didn't save. Try again in a minute.");
  }
  async function addPost(post) {
    if (board.mode !== "db" || !board.canPost) throw new Error("Posting isn't available here.");
    try {
      const kept = (await ownPosts()).filter((p) => p && (p.status !== "reunited" || Date.now() - Date.parse(p.created) < 30 * 864e5));
      if (kept.filter((p) => p.status !== "reunited").length >= MAX_PER_VIEWER) throw Object.assign(new Error(`You have ${MAX_PER_VIEWER} listings up. Mark one reunited first.`), { mine: true });
      const clean = sanitize({ ...post, id: "p" + Date.now().toString(36), created: new Date().toISOString() }, "board");
      if (!clean) throw Object.assign(new Error("Pick lost, found or spotted."), { mine: true });
      delete clean.source;
      await board.db.doc("pets/" + board.uid).set({ posts: [...kept, clean] });
    } catch (e) { throw e.mine ? e : writeError(e); }
  }

  async function markReunited(id) {
    if (board.mode !== "db" || !board.canPost) return;
    try {
      const posts = (await ownPosts()).map((p) => (p && p.id === id ? { ...p, status: "reunited" } : p));
      await board.db.doc("pets/" + board.uid).set({ posts });
    } catch (e) { throw writeError(e); }
  }

  /* the backend starts once per page, whichever of loadBoard/init comes first */
  function start() {
    if (!started) {
      started = (async () => {
        const db = await useCap("db");
        if (db) return startDb(db, await useCap("user"));
        return startSnapshot();
      })().catch((e) => { console.warn(e); unknown(); });
    }
    return started;
  }
  function listen(ui) {
    if (!ui) return;
    if (typeof ui === "function") board.listeners.add(ui);
    else if (typeof ui.onChange === "function") board.listeners.add(ui.onChange);
  }

  /* pages with a map (or street lines): W may be null when `lines` is given */
  async function init({ W = null, lines = null, streets = null, ui = null } = {}) {
    const idx = buildIndex(lines ? { lines } : W);
    if (idx.size) board.idx = idx;
    if (Array.isArray(streets)) board.streets = streets;
    if (ui) board.ui = ui;
    if (ui && typeof ui.onChange === "function") { try { ui.onChange(board.posts); } catch (e) { console.error(e); } }
    if (started) {
      if (board.idx && board.posts.length) board.posts = board.posts.map(place);
      notify();
      return started;
    }
    return start();
  }
  /* pages without a map: listings only, no geocoding */
  function loadBoard({ ui = null } = {}) {
    listen(ui);
    return start();
  }

  /* ---------------- street lines, loaded lazily (never on the home page) ---------------- */
  const dataCache = {};
  function getData(name) {
    if (!dataCache[name]) dataCache[name] = fetch(root() + "data/" + name).then((r) => { if (!r.ok) throw new Error(name + " " + r.status); return r.json(); });
    return dataCache[name];
  }
  function dec(arr, q) {
    const out = new Float32Array(arr.length);
    let x = 0, y = 0;
    for (let i = 0; i < arr.length; i += 2) { x += arr[i]; y += arr[i + 1]; out[i] = x / q; out[i + 1] = y / q; }
    return out;
  }
  let linesP = null;
  function loadLines() {
    if (!linesP) {
      const NK = window.NK;
      const own = () => Promise.all([getData("meta.json"), getData("roads.json")]).then(([meta, roads]) =>
        roads.r.map(([rank, ni, , c]) => ({ n: ni >= 0 ? roads.names[ni] : null, rank, pts: (NK && NK.dec ? NK.dec : dec)(c, meta.q) })));
      linesP = (NK && typeof NK.loadLines === "function" ? Promise.resolve().then(() => NK.loadLines()).catch(own) : own())
        .catch((e) => { linesP = null; throw e; });
    }
    return linesP;
  }
  let idxP = null;
  function ensureIndex() {
    if (board.idx && board.idx.size) return Promise.resolve(board.idx);
    if (!idxP) {
      idxP = Promise.all([loadLines(), getData("streets.json")])
        .then(([lines, streets]) => { init({ W: null, lines, streets }); return board.idx; })
        .catch((e) => { idxP = null; throw e; });
    }
    return idxP;
  }
  const loadMeta = () => getData("meta.json");

  /* the two nearest distinct named streets within 150 m of (x, y): "5th Avenue & 9th Street" */
  function segDist(px, py, ax, ay, bx, by) {
    const dx = bx - ax, dy = by - ay, L = dx * dx + dy * dy;
    const t = L ? Math.max(0, Math.min(1, ((px - ax) * dx + (py - ay) * dy) / L)) : 0;
    const qx = ax + t * dx, qy = ay + t * dy;
    return { d: Math.hypot(px - qx, py - qy), x: qx, y: qy };
  }
  function nearestPoint(pts, px, py) {
    let best = null;
    for (let i = 0; i + 3 < pts.length; i += 2) {
      const s = segDist(px, py, pts[i], pts[i + 1], pts[i + 2], pts[i + 3]);
      if (!best || s.d < best.d) best = s;
    }
    if (!best && pts.length >= 2) best = { d: Math.hypot(px - pts[0], py - pts[1]), x: pts[0], y: pts[1] };
    return best;
  }
  function nearestStreets(x, y, max = 150) {
    const byName = new Map();
    for (const list of (board.idx || new Map()).values()) for (const l of list) {
      const s = nearestPoint(l.pts, x, y);
      if (s && s.d <= max && (!byName.has(l.n) || s.d < byName.get(l.n))) byName.set(l.n, s.d);
    }
    return [...byName.entries()].sort((a, b) => a[1] - b[1]).slice(0, 2).map((e) => e[0]);
  }

  /* ---------------- distance and compass words ---------------- */
  const DIRS = ["east", "northeast", "north", "northwest", "west", "southwest", "south", "southeast"];
  /* {m, mi, dir} from the spot pt to the post; a street-only post is measured to the nearest point of its street */
  function distanceFrom(post, pt) {
    if (!post || !pt || typeof post.x !== "number" || typeof pt.x !== "number") return null;
    let tx = post.x, ty = post.y;
    if (post.prec === "street" && post.placeLabel && board.idx) {
      const k = streetKey(post.placeLabel);
      let best = null;
      for (const l of (k && board.idx.get(k.core)) || []) {
        if (l.n !== post.placeLabel) continue;
        const s = nearestPoint(l.pts, pt.x, pt.y);
        if (s && (!best || s.d < best.d)) best = s;
      }
      if (best) { tx = best.x; ty = best.y; }
    }
    const dx = tx - pt.x, dy = ty - pt.y, m = Math.hypot(dx, dy);
    const a = Math.atan2(-dy, dx) * 180 / Math.PI;
    return { m, mi: m / 1609.344, dir: DIRS[((Math.round(a / 45) % 8) + 8) % 8] };
  }
  const USPS = { Street: "St", Avenue: "Ave", Road: "Rd", Boulevard: "Blvd", Drive: "Dr", Lane: "Ln", Place: "Pl", Court: "Ct", Alley: "Aly" };
  const shortStreet = (s) => String(s || "").replace(/\b(Street|Avenue|Road|Boulevard|Drive|Lane|Place|Court|Alley)\b/g, (w) => USPS[w]);
  /* "About 0.2 mi north of 5th Ave & 9th St" / "About 300 ft west of …" */
  function distText(d, label) {
    if (!d) return "";
    const of = label ? ` of ${shortStreet(label)}` : "";
    if (d.m < 15) return label ? `Right by ${shortStreet(label)}` : "Right here";
    if (d.mi < 0.1) return `About ${Math.max(50, Math.round(d.m * 3.28084 / 50) * 50)} ft ${d.dir}${of}`;
    return `About ${d.mi.toFixed(1)} mi ${d.dir}${of}`;
  }

  /* ---------------- badge: posts newer than the last time this device saw the board ---------------- */
  function newSince(iso) {
    const t = iso ? Date.parse(iso) : Date.now() - 7 * 864e5;
    if (!Number.isFinite(t) || !board.known) return 0;
    return board.posts.filter((p) => p.created && Date.parse(p.created) > t).length;
  }
  function badge() {
    const S = NKS();
    if (!S || !S.setBadge) return;
    try { S.setBadge(board.known ? newSince(S.local.get("nk-seen-pets")) : 0); } catch (e) { /* ignore */ }
  }
  /* call when the listings have been seen (the #board region scrolled into view) */
  function markSeen() {
    const S = NKS();
    if (!S || !board.known) return;
    const newest = board.posts.map((p) => p.created).filter(Boolean).sort().pop();
    S.local.set("nk-seen-pets", newest || board.fetched || new Date().toISOString());
    badge();
  }

  /* ---------------- words shared by the page, the rows, the flyer and share text ---------------- */
  const animalWord = (p) => (p.animal === "dog" || p.animal === "cat" ? p.animal : "pet");
  const where = (p) => [p.near, p.town].filter(Boolean).join(", ");
  function nearLine(p) {
    const w = where(p);
    if (!w) return "";
    return `${VERB[p.status] || "Last seen near"} ${w}${p.prec === "street" ? " (no cross street given)" : ""}`;
  }
  const headline = (p) => `${STATUS[p.status]} ${animalWord(p)}${p.name ? ": " + p.name : ""}`;
  const dayOf = (p) => p.date || String(p.created || "").slice(0, 10);
  function shortDate(iso) {
    const S = NKS();
    if (!iso || !S) return iso || "";
    const s = S.apDate(String(iso).slice(0, 10));
    return s.replace(new RegExp(", " + new Date().getFullYear() + "$"), "");
  }
  /* "9:15 a.m." today, else "Sept. 22, 9:15 a.m." */
  function checkedText(iso) {
    const S = NKS(), d = new Date(iso);
    if (!S || !iso || isNaN(d)) return "";
    return S.isoDay(d) === S.isoDay(new Date()) ? S.apTime(d) : `${shortDate(S.isoDay(d))}, ${S.apTime(d)}`;
  }
  function cut(s, n = 80) {
    s = String(s || "").trim();
    if (s.length <= n) return s;
    let c = s.slice(0, n + 1);
    const i = c.lastIndexOf(" ");
    c = i > Math.floor(n / 2) ? c.slice(0, i) : s.slice(0, n);
    return c.replace(/[ ,;:.–-]+$/, "") + "…";
  }
  const PHONE = /\(?\b(\d{3})\)?[-. ]?(\d{3})[-. ](\d{4})\b|\b911\b/;
  const EMAIL = /[\w.+-]+@[\w-]+(?:\.[\w-]+)+/;
  function contactHTML(p) {
    const c = p.contact || "";
    if (!c) return "";
    if (p.url && /^comment (?:on|below|here)[\w .]*$/i.test(c)) return `<a href="${esc(p.url)}" target="_blank" rel="noopener">${esc(c)}</a>`;
    const re = new RegExp(PHONE.source + "|" + EMAIL.source, "g");
    let out = "", pos = 0, m;
    while ((m = re.exec(c))) {
      out += esc(c.slice(pos, m.index));
      const s = m[0];
      if (s.includes("@")) out += `<a href="mailto:${esc(s)}">${esc(s)}</a>`;
      else if (s === "911") out += `<a class="tel" href="tel:911">911</a>`;
      else out += `<a class="tel" href="tel:+1${m[1]}${m[2]}${m[3]}">${m[1]}-${m[2]}-${m[3]}</a>`;
      pos = m.index + s.length;
    }
    return out + esc(c.slice(pos));
  }
  function shareText(p) {
    const h = `${STATUS[p.status].toUpperCase()} ${animalWord(p).toUpperCase()}${p.name ? ": " + p.name : ""}.`;
    const d = dayOf(p), w = where(p);
    const seen = w ? `${VERB[p.status]} ${w}${d ? ", " + shortDate(d) : ""}.` : "";
    const desc = p.desc ? (/[.!?]$/.test(p.desc.trim()) ? p.desc.trim() : p.desc.trim() + ".") : "";
    return [h, desc, seen].filter(Boolean).join(" ");
  }
  /* the listing's own page when the deploy built one, else its card on the board */
  function shareUrl(p) {
    const S = NKS();
    const path = board.snapIds.has(p.id) && /^gh-\d+$/.test(p.id) ? `lost-pets/${p.id}/` : `lost-pets/#${p.id}`;
    return S ? S.abs(path) : path;
  }
  function sharePost(p) {
    const S = NKS();
    return S ? S.share({ title: headline(p), text: shareText(p), url: shareUrl(p) }) : Promise.resolve("failed");
  }

  /* ---------------- posting: GitHub's form, pre-filled; e-mail when the site has an address ---------------- */
  const cap = (s) => String(s || "").replace(/^./, (c) => c.toUpperCase());
  function issueTitle(d) {
    const t = `[${STATUS[d.status] || "Lost"}] ${cap(d.animal || "dog")}${d.name ? ": " + d.name : ""}${d.near ? ", " + cleanNear(d.near) : ""}`;
    if (t.length <= 80) return t;
    const c = t.slice(0, 80), i = c.lastIndexOf(" ");
    return (i > 40 ? c.slice(0, i) : c).replace(/[ ,;:&-]+$/, "");
  }
  function issueUrl(d) {
    const q = (k, v) => (v ? `&${k}=${encodeURIComponent(v)}` : "");
    return ISSUE_FORM + "&title=" + encodeURIComponent(issueTitle(d)) + q("name", clip(d.name, "name")) + q("description", clip(d.desc, "desc"))
      + q("near", cleanNear(clip(d.near, "near"))) + q("date", d.date) + q("contact", clip(d.contact, "contact"))
      + q("status", STATUS[d.status]) + q("animal", cap(d.animal)) + q("town", TOWNS.includes(d.town) ? d.town : "");
  }
  function draftText(d) {
    return [["Lost, found or spotted?", STATUS[d.status]], ["Animal", cap(d.animal)], ["Pet's name (if known)", d.name], ["Description", d.desc],
      ["Last seen near", cleanNear(d.near)], ["Town", d.town], ["Date", d.date], ["How to reach you (public)", d.contact]]
      .map(([k, v]) => `${k} ${v || "(none)"}`).join("\n");
  }
  function mailtoUrl(d, email) {
    return `mailto:${email}?subject=${encodeURIComponent(issueTitle(d))}&body=${encodeURIComponent(draftText(d) + "\n\nPlease post this on the NK15068 lost and found board.")}`;
  }

  /* ---------------- markup (nkpages/pets.py row_html / card_html make the same) ---------------- */
  function rowHTML(p) {
    const S = NKS(), href = (S ? S.url("lost-pets/") : "lost-pets/") + "#" + p.id;
    const tail = [where(p), shortDate(dayOf(p))].filter(Boolean).join(" · ");
    return `<li class="listing-row" data-status="${esc(p.status)}" data-id="${esc(p.id)}"><a href="${esc(href)}">`
      + `<span class="listing-st">${STATUS[p.status]} ${animalWord(p)}</span> `
      + `<span class="listing-desc">${p.name ? `<b>${esc(p.name)}.</b> ` : ""}${esc(cut(p.desc))}</span>`
      + (tail ? ` <span class="listing-where">${esc(tail)}</span>` : "") + "</a></li>";
  }
  function dateLine(p) {
    const S = NKS(), d = dayOf(p);
    if (!d || !S) return "";
    const ago = S.daysFrom(d) <= 0 ? ` <span data-ago="${d}" data-paren>(${S.ago(d)})</span>` : "";
    return `${STATUS[p.status]} ${S.apDay(d)}${ago}`;
  }
  /* opts: {dist: text for the distance line, share: false to leave out Share, name: false to leave out the name} */
  function cardHTML(p, opts = {}) {
    const S = NKS(), u = (x) => (S ? S.url(x) : x), id = esc(p.id);
    const alt = p.name ? `Photo of ${p.name}` : `Photo of the ${animalWord(p)}`;
    const acts = [];
    if (typeof p.x === "number" || p.near) acts.push(`<a href="${esc(u("map/"))}?pet=${id}">Map it</a>`);
    if (opts.share !== false) acts.push(`<button type="button" class="linkbtn" data-share="${id}">Share</button>`);
    acts.push(`<a href="${esc(u("lost-pets/flyer/"))}?pet=${id}">Flyer</a>`);
    if (p.url) acts.push(`<a href="${esc(p.url)}" target="_blank" rel="noopener">See this post ›</a>`);
    if (p.owner) acts.push(`<button type="button" class="linkbtn" data-reunite="${id}">Mark reunited</button>`);
    const near = nearLine(p), dl = dateLine(p);
    return `<article class="listing" id="${id}" data-status="${esc(p.status)}" data-id="${id}">`
      + (p.photo ? `<img src="${esc(p.photo)}" alt="${esc(alt)}" loading="lazy">` : "")
      + `<p class="listing-st">${STATUS[p.status]} · ${animalWord(p)}</p>`
      + (p.name && opts.name !== false ? `<h3>“${esc(p.name)}”</h3>` : "")
      + (p.desc ? `<p class="listing-desc">${esc(p.desc)}</p>` : "")
      + (near ? `<p class="listing-near">${esc(near)}</p>` : "")
      + `<p class="listing-dist"${opts.dist ? "" : " hidden"}>${esc(opts.dist || "")}</p>`
      + (dl ? `<p class="listing-date">${dl}</p>` : "")
      + (p.contact ? `<p class="listing-contact">${contactHTML(p)}</p>` : "")
      + `<p class="listing-acts">${acts.join("")}</p></article>`;
  }
  const telA = (ph, label) => (ph ? `<a class="tel" href="tel:+1${String(ph).replace(/\D/g, "").slice(-10)}">${esc(label || ph)}</a>` : "");

  /* the home page box (#pets-box): the server rendered the build's state; this keeps it live */
  const subscribed = new WeakSet();
  function renderHomeBox(el) {
    if (!el) return;
    if (!subscribed.has(el)) { subscribed.add(el); board.listeners.add(() => renderHomeBox(el)); start(); }
    const st = board.state, body = el.querySelector(".pb-body"), count = el.querySelector(".pb-count");
    if (!body) return;
    const S = NKS(), lp = S ? S.url("lost-pets/") : "lost-pets/", post = S ? S.url("lost-pets/post/") : "lost-pets/post/";
    const shName = el.dataset.shelterName || "Animal Protectors", shTel = el.dataset.shelterTel || "";
    const issues = el.dataset.issues || ISSUES;
    const acts = `<p class="pb-acts"><a class="act" href="${esc(lp)}#board">${board.posts.length > 3 ? `See all ${board.posts.length} on the board ›` : "See the board ›"}</a><a class="act" href="${esc(lp)}">Lost a pet? What to do now ›</a></p>`;
    let html;
    if (st === "loading") {
      if (el.dataset.state !== "nosnap") return; // keep the deploy's listings until the live answer comes
      html = `<p class="pb-msg">Checking the board…</p>` + acts;
    } else if (st === "listed" || st === "stale") {
      html = (st === "stale" ? `<p class="pb-msg">The live board didn't answer. These are the listings as of ${esc(checkedText(board.fetched).replace(/\.$/, ""))}.</p>` : "")
        + `<ul class="petrows">${board.posts.slice(0, 3).map(rowHTML).join("")}</ul>` + acts;
    } else if (st === "empty") {
      html = `<p class="pb-msg">No open listings on the board right now (checked ${esc(checkedText(board.fetched))}).</p>`
        + `<p class="pb-msg">Lost a pet? Call ${esc(shName)}, ${telA(shTel)}, then post it here.</p>`
        + `<p class="pb-acts"><a class="act" href="${esc(lp)}#found">Found a dog? Who to call ›</a><a class="act" href="${esc(post)}">Post a free listing ›</a></p>`;
    } else {
      html = `<p class="pb-msg">The board didn't load just now, so we can't tell you what's posted.</p>`
        + `<p class="pb-msg"><a href="${esc(issues)}" target="_blank" rel="noopener">See the posts on GitHub ›</a></p>`
        + `<p class="pb-msg">Lost a pet? Call ${esc(shName)}, ${telA(shTel)}</p>`;
    }
    body.innerHTML = html;
    el.dataset.state = st;
    if (count) count.textContent = st === "listed" || st === "stale" ? `${board.posts.length} open` : "";
    if (S) S.relabel(el);
  }

  /* a town page's [data-pets-town] host: that town's live listings */
  function renderTownList(el, town) {
    if (!el) return;
    town = town || el.dataset.petsTown;
    if (!subscribed.has(el)) { subscribed.add(el); board.listeners.add(() => renderTownList(el, town)); start(); }
    const st = board.state;
    if (st === "loading") return;
    const S = NKS(), mine = board.posts.filter((p) => p.town === town);
    const when = checkedText(board.fetched);
    let html;
    if (st === "listed" || st === "stale") {
      html = mine.length
        ? `<p class="pb-msg">${mine.length} open listing${mine.length === 1 ? "" : "s"} in ${esc(town)} (${st === "stale" ? "as of" : "checked"} ${esc(when)}).</p><ul class="petrows">${mine.map(rowHTML).join("")}</ul>`
        : `<p class="pb-msg">None of the board's open listings are in ${esc(town)} right now (checked ${esc(when)}).</p>`;
    } else if (st === "empty") {
      html = `<p class="pb-msg">No open listings on the board right now (checked ${esc(when)}).</p>`;
    } else {
      html = `<p class="pb-msg">The board didn't load just now. <a href="${esc(ISSUES)}" target="_blank" rel="noopener">See the posts on GitHub ›</a></p>`;
    }
    el.innerHTML = html;
    if (S) S.relabel(el);
  }

  window.NKPets = {
    init, loadBoard, addPost, markReunited, board, ISSUE_FORM, ISSUES, TOWNS, LIMITS, STATUS,
    geocodeNear: (t, town) => geocodeNear(t, board.idx, board.streets, town),
    parseIssue, isPetIssue, cleanNear, stripHouse, sanitize, streetKey, buildIndex,
    startSnapshot, startGithub, ensureIndex, loadLines, loadMeta, nearestStreets, shortStreet,
    distanceFrom, distText, newSince, markSeen, issueTitle, issueUrl, mailtoUrl, draftText,
    headline, nearLine, where, animalWord, shortDate, checkedText, shareText, shareUrl, sharePost,
    rowHTML, cardHTML, contactHTML, renderHomeBox, renderTownList,
  };
})();
