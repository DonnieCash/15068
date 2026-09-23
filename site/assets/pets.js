/* NK15068 — lost & found pets board.
   Two backends, chosen at run time:
   - inside the Claude artifact viewer: a shared `db` store (each viewer writes only
     their own document, everyone reads all of them);
   - anywhere else (GitHub Pages): open GitHub issues made with the
     "Lost or found pet" issue form, read through GitHub's public API.
   Locations are street + cross street, placed on the map from the site's own road data. */
(function () {
  "use strict";
  const $ = (s, r = document) => r.querySelector(s);
  const esc = (s) => String(s ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
  const REPO = "DonnieCash/15068";
  const ISSUE_FORM = `https://github.com/${REPO}/issues/new?template=lost-found-pet.yml`;
  const TOWNS = ["New Kensington", "Arnold", "Lower Burrell"];
  const MAX_PER_VIEWER = 20;
  const LIMITS = { name: 40, desc: 500, near: 120, contact: 120, town: 40, animal: 20 };

  /* house numbers never ship: drop standalone numbers and ranges ("1025", "1025-1027", "12B"),
     keep ordinals ("9th") and route numbers ("Route 56", "PA 366", "SR 780") */
  function cleanNear(t) {
    return String(t || "")
      .replace(/\b(route|rte|pa|sr|us|i)[\s-]*(\d{1,4})\b/gi, (m, a, n) => a + "\u2009" + n) // protect route numbers
      .replace(/\b(\d{0,3}00)\s+block\b/gi, "\u2009$1\u2009block") // hundred-blocks are coarse enough to keep
      .replace(/(^|[^\w\u2009])\d{1,5}[a-z]?(?:\s*[-\u2013]\s*\d{1,5}[a-z]?)?(?![\w\u2009])(?!\s*(?:st|nd|rd|th)\b)/gi, "$1")
      .replace(/\u2009/g, " ")
      .replace(/\s{2,}/g, " ").replace(/^[\s,&]+|[\s,]+$/g, "").trim();
  }
  const clip = (v, k) => String(v ?? "").trim().slice(0, LIMITS[k] || 40);
  const GH_IMG = /^https:\/\/(user-images\.githubusercontent\.com|github\.com\/user-attachments)\//;
  const GH_ISSUE = new RegExp(`^https://github\\.com/${REPO.replace("/", "\\/")}/issues/\\d+$`);
  /* posts in the shared store are untrusted: rebuild each one from an allow-list */
  function sanitize(p, source) {
    if (!p || typeof p !== "object" || !/^(lost|found|spotted)$/.test(p.status)) return null;
    const out = {
      id: clip(p.id, "name"), status: p.status, animal: /^(dog|cat|other)$/i.test(p.animal) ? p.animal.toLowerCase() : "other",
      name: clip(p.name, "name"), desc: clip(p.desc, "desc"), near: cleanNear(clip(p.near, "near")),
      town: TOWNS.includes(p.town) ? p.town : "", date: /^\d{4}-\d{2}-\d{2}$/.test(p.date) ? p.date : "",
      contact: clip(p.contact, "contact"), created: /^\d{4}-\d{2}-\d{2}T[\d:.]+Z$/.test(p.created) ? p.created : "", source,
    };
    if (Number.isFinite(p.x) && Number.isFinite(p.y) && Math.abs(p.x) < 2e4 && Math.abs(p.y) < 2e4) {
      out.x = Math.round(p.x / 10) * 10; out.y = Math.round(p.y / 10) * 10;
      out.prec = /^(intersection|street|picked)$/.test(p.prec) ? p.prec : "picked";
    }
    if (source === "github") {
      if (GH_ISSUE.test(p.url || "")) out.url = p.url;
      if (GH_IMG.test(p.photo || "")) out.photo = p.photo;
    }
    return out;
  }

  /* ---------------- street matching (mirrors scripts/build_safety.py street_key) ---------------- */
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

  function buildIndex(W) {
    const idx = new Map();
    for (const l of W.lines || []) {
      if (!l.n) continue;
      const k = streetKey(l.n);
      if (!k) continue;
      if (!idx.has(k.core)) idx.set(k.core, []);
      idx.get(k.core).push({ type: k.type, pts: l.pts, n: l.n });
    }
    return idx;
  }

  /* "Fifth Avenue & 9th Street" -> {x, y, prec, label} using the map's road lines */
  function geocodeNear(text, idx, streets, town) {
    const parts = String(text || "").split(/\s*(?:&|\band\b|\bat\b|\/|@|,|\bnear\b)\s*/i).map((s) => s.trim()).filter(Boolean);
    const lines = (name) => {
      const k = streetKey(name);
      if (!k) return [];
      const all = idx.get(k.core) || [];
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
      const cands = streets.filter((s) => { const sk = streetKey(s.n); return sk && sk.core === k.core && (!k.type || !sk.type || sk.type === k.type); });
      const inTown = cands.find((s) => (s.t || []).includes(town)) || cands[0];
      if (inTown) return { x: inTown.x, y: inTown.y, prec: "street", label: inTown.n };
    }
    return null;
  }

  /* ---------------- GitHub issue-form parsing ---------------- */
  function parseIssue(issue) {
    const body = issue.body || "";
    const field = (label) => {
      const m = body.match(new RegExp(`###\\s*${label}[^\\n]*\\n+([\\s\\S]*?)(?=\\n###|$)`, "i"));
      const v = m ? m[1].trim() : "";
      return v === "_No response_" ? "" : v;
    };
    const titleStatus = (issue.title.match(/^\s*\[(lost|found|spotted)\]/i) || [])[1];
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
  const board = { posts: [], mode: "loading", uid: null, mine: null, db: null, idx: null, streets: [], ui: null, error: "", canPost: false, readOnly: false };

  async function useCap(name) {
    try { return window.claude && typeof window.claude.use === "function" ? await window.claude.use(name) : null; } catch (e) { return null; }
  }

  function place(p) {
    if (typeof p.x === "number" && typeof p.y === "number") return p;
    const g = p.near ? geocodeNear(p.near, board.idx, board.streets, p.town) : null;
    return g ? { ...p, x: g.x, y: g.y, prec: g.prec, placeLabel: g.label } : p;
  }

  function publish(list) {
    board.posts = list.map(place).sort((a, b) => String(b.date || b.created).localeCompare(String(a.date || a.created)));
    board.ui?.onChange(board.posts);
  }

  async function startGithub() {
    board.mode = "github";
    try {
      const r = await fetch(`https://api.github.com/repos/${REPO}/issues?state=open&per_page=100`, { headers: { Accept: "application/vnd.github+json" } });
      if (!r.ok) throw new Error("GitHub answered " + r.status);
      const issues = await r.json();
      publish(issues.filter((i) => !i.pull_request).map(parseIssue).filter(Boolean));
    } catch (e) {
      board.error = "The board couldn't reach GitHub just now. Reload later, or post through one of the groups below.";
      publish([]);
    }
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
      publish(all);
    }, () => { board.error = "The shared board is unavailable right now."; board.canPost = false; board.ui?.onChange(board.posts); });
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

  async function init({ W, streets, ui }) {
    board.idx = buildIndex(W);
    board.streets = streets;
    board.ui = ui;
    ui.onChange([]);
    const db = await useCap("db");
    if (db) {
      const user = await useCap("user");
      return startDb(db, user);
    }
    return startGithub();
  }

  window.NKPets = { init, addPost, markReunited, geocodeNear: (t, town) => geocodeNear(t, board.idx, board.streets, town), parseIssue, cleanNear, sanitize, board, ISSUE_FORM, TOWNS, LIMITS };
})();
