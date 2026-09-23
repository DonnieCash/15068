/* NK15068 — shell: helpers every page uses (window.NKS), theme, More menu, dates, badges, share.
   Page modules register themselves as NKS.pages[<data-page>] = () => {…}; 99-boot.js runs the one for this page.
   All page text is already in the HTML; JS only refreshes live parts. */
(function () {
  "use strict";
  const doc = document.documentElement;
  const $ = (s, r = document) => r.querySelector(s);
  const $$ = (s, r = document) => [...r.querySelectorAll(s)];
  const esc = (s) => String(s ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
  const fmt = (n) => Number(n).toLocaleString("en-US");
  const ROOT = doc.dataset.root || "";

  /* ---------------- storage, every call guarded ---------------- */
  const store = (area) => ({
    get(k) { try { return area().getItem(k); } catch (e) { return null; } },
    set(k, v) { try { area().setItem(k, v); return true; } catch (e) { return false; } },
    del(k) { try { area().removeItem(k); } catch (e) { /* ignore */ } },
    keys() { try { const a = area(), out = []; for (let i = 0; i < a.length; i++) out.push(a.key(i)); return out; } catch (e) { return []; } },
  });
  const local = store(() => localStorage), session = store(() => sessionStorage);
  const getJSONKey = (k, d) => { try { const v = JSON.parse(local.get(k)); return v ?? d; } catch (e) { return d; } };

  /* ---------------- credits by outlet name (same table as nkpages/fmt.py, from pubs.js) ---------------- */
  const PUBS = window.NK_PUBS || {};
  function pubName(u) {
    let url;
    try { url = new URL(u); } catch (e) { return ""; }
    const h = url.hostname.replace(/^www\./, ""), path = url.pathname.toLowerCase();
    if (h === "triblive.com" && path.includes("/valley-news-dispatch/")) return "Valley News Dispatch (TribLive)";
    if (h === "community.triblive.com") return "TribLive community news";
    if (h === "archive.triblive.com") return "Tribune-Review archive";
    if (h === "triblive.com" || h.endsWith(".triblive.com")) return "TribLive";
    if (PUBS[h]) return PUBS[h];
    if (h === "pa.gov" && path.startsWith("/agencies/pda")) return "PA Dept. of Agriculture";
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

  /* ---------------- AP-style dates (same rules as nkpages/fmt.py) ---------------- */
  const AP_MONTHS = ["Jan.", "Feb.", "March", "April", "May", "June", "July", "Aug.", "Sept.", "Oct.", "Nov.", "Dec."];
  const AP_DAYS = ["Sun.", "Mon.", "Tues.", "Wed.", "Thurs.", "Fri.", "Sat."];
  const DAYS = ["Sunday", "Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday"];
  function apDate(s, approx) {
    const m = String(s ?? "").match(/^(\d{4})(?:-(\d{1,2})(?:-(\d{1,2}))?)?/);
    if (!m) return String(s ?? "");
    let out = m[1];
    if (m[2] && AP_MONTHS[+m[2] - 1]) out = m[3] ? `${AP_MONTHS[+m[2] - 1]} ${+m[3]}, ${m[1]}` : `${AP_MONTHS[+m[2] - 1]} ${m[1]}`;
    return approx ? "About " + out : out;
  }
  /* a local calendar date from 'YYYY-MM-DD' (never parsed as UTC) */
  const day = (iso) => { const [y, m, d] = String(iso).slice(0, 10).split("-").map(Number); return new Date(y, m - 1, d); };
  const isoDay = (d) => `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}-${String(d.getDate()).padStart(2, "0")}`;
  const apDay = (iso) => { const d = day(iso); return `${AP_DAYS[d.getDay()]}, ${AP_MONTHS[d.getMonth()]} ${d.getDate()}`; };
  const apLong = (iso, year = true) => { const d = day(iso); return `${DAYS[d.getDay()]}, ${AP_MONTHS[d.getMonth()]} ${d.getDate()}` + (year ? `, ${d.getFullYear()}` : ""); };
  function apTime(d) {
    const h = d.getHours(), mi = d.getMinutes();
    if (h === 12 && mi === 0) return "noon";
    const suf = h < 12 ? "a.m." : "p.m.", h12 = h % 12 || 12;
    return mi ? `${h12}:${String(mi).padStart(2, "0")} ${suf}` : `${h12} ${suf}`;
  }
  const today = () => { const n = new Date(); return new Date(n.getFullYear(), n.getMonth(), n.getDate()); };
  const daysFrom = (iso) => Math.round((day(iso) - today()) / 864e5);
  /* "Today", "Tomorrow", "This Friday" (within 6 days), "" otherwise */
  function relDay(iso) {
    const n = daysFrom(iso);
    if (n === 0) return "Today";
    if (n === 1) return "Tomorrow";
    if (n > 1 && n < 7) return "This " + DAYS[day(iso).getDay()];
    return "";
  }
  /* "today", "yesterday", "3 days ago", "2 weeks ago" */
  function ago(iso) {
    const n = -daysFrom(iso);
    if (n <= 0) return "today";
    if (n === 1) return "yesterday";
    if (n < 14) return `${n} days ago`;
    if (n < 60) return `${Math.round(n / 7)} weeks ago`;
    return `${Math.round(n / 30)} months ago`;
  }
  /* relabel [data-rel-day] (text = relDay) and [data-ago] (text = "(3 days ago)" style when data-paren) */
  function relabel(root = document) {
    $$("[data-rel-day]", root).forEach((el) => { el.textContent = relDay(el.dataset.relDay); });
    $$("[data-ago]", root).forEach((el) => { const t = ago(el.dataset.ago); el.textContent = el.hasAttribute("data-paren") ? `(${t})` : t; });
  }

  /* ---------------- streets, routes, small text helpers ---------------- */
  const SHIELDED = new Set(["56", "366", "380", "780"]);
  function shield(ref) {
    const r = String(ref).trim().replace(/^(PA|SR)[\s-]*/i, "");
    if (!SHIELDED.has(r)) return "";
    const three = r.length >= 3;
    return `<svg class="ks" viewBox="0 0 26 24" width="26" height="24" role="img" aria-label="Pennsylvania Route ${r}"><path d="M2.5 1.5H23.5L21.8 5.2L24 7.4L19 22.5H7L2 7.4L4.2 5.2Z" fill="var(--surface)" stroke="var(--ink)" stroke-width="1.3" stroke-linejoin="round"/><text x="13" y="15.6" text-anchor="middle" font-family="Radio Canada, Arial, sans-serif" font-weight="700" font-size="${three ? 8.5 : 9.5}"${three ? ' style="font-stretch:85%"' : ""} fill="var(--ink)">${r}</text></svg>`;
  }
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
  const slug = (s) => String(s || "").toLowerCase().normalize("NFKD").replace(/[^a-z0-9]+/g, "-").replace(/^-|-$/g, "");
  /* tel links: "724-339-7533 or 724-339-7534" -> [["724-339-7533", "tel:+17243397533"], …] */
  function tels(text) {
    const out = [], re = /\(?\b(\d{3})\)?[-. ]?(\d{3})[-. ](\d{4})\b|\b911\b/g;
    let m;
    while ((m = re.exec(String(text || "")))) out.push(m[0] === "911" ? ["911", "tel:911"] : [`${m[1]}-${m[2]}-${m[3]}`, `tel:+1${m[1]}${m[2]}${m[3]}`]);
    return out;
  }
  const telLink = (text, label = "Call {n}", cls = "tel") => {
    const t = tels(text)[0];
    return t ? `<a class="${cls}" href="${t[1]}">${esc(label.replace("{n}", t[0]))}</a>` : "";
  };

  /* ---------------- URL state (replaceState only: one Back always leaves the page) ---------------- */
  const qs = () => new URLSearchParams(location.search);
  function setQS(obj) {
    const p = qs();
    for (const [k, v] of Object.entries(obj)) {
      if (v == null || v === "" || v === false) p.delete(k); else p.set(k, v);
    }
    const s = p.toString().replace(/%2C/g, ",").replace(/%7E/g, "~");
    try { history.replaceState(history.state, "", location.pathname + (s ? "?" + s : "") + location.hash); } catch (e) { /* file:// or sandbox */ }
  }

  /* ---------------- theme ---------------- */
  const darkMQ = matchMedia("(prefers-color-scheme: dark)");
  const isDark = () => (doc.dataset.theme ? doc.dataset.theme === "dark" : darkMQ.matches);
  const themeHooks = [];
  function syncTheme() {
    const d = isDark();
    $$("[data-theme-toggle]").forEach((b) => {
      const long = !b.classList.contains("theme-btn");
      b.textContent = d ? (long ? "Light theme" : "Light") : (long ? "Dark theme" : "Dark");
      b.setAttribute("aria-label", d ? "Switch to light theme" : "Switch to dark theme");
    });
    /* themed pictures: <picture class="themed"><source media="(prefers-color-scheme: dark)" …> follow the chosen theme */
    $$("picture.themed source").forEach((s) => {
      if (!s.dataset.media) s.dataset.media = s.getAttribute("media") || "";
      if (!/prefers-color-scheme:\s*dark/.test(s.dataset.media)) return;
      s.setAttribute("media", doc.dataset.theme ? (d ? "all" : "not all") : s.dataset.media);
    });
  }
  function setTheme(t) {
    doc.dataset.theme = t;
    local.set("nk-theme", t);
    syncTheme();
    themeHooks.forEach((f) => { try { f(isDark()); } catch (e) { console.error(e); } });
  }
  document.addEventListener("click", (e) => {
    const b = e.target.closest("[data-theme-toggle]");
    if (b) setTheme(isDark() ? "light" : "dark");
  });
  darkMQ.addEventListener?.("change", () => { syncTheme(); themeHooks.forEach((f) => { try { f(isDark()); } catch (e) { console.error(e); } }); });

  /* ---------------- More menu: works without JS; with JS closes on Escape, outside click and navigation ---------------- */
  function wireMore() {
    const d = $("details.more");
    if (!d) return;
    document.addEventListener("keydown", (e) => { if (e.key === "Escape" && d.open) { d.open = false; d.querySelector("summary").focus(); } });
    document.addEventListener("click", (e) => { if (d.open && !d.contains(e.target)) d.open = false; });
    d.addEventListener("click", (e) => { if (e.target.closest("a")) d.open = false; });
    addEventListener("pageshow", () => { d.open = false; });
  }

  /* ---------------- wide tables fade at the right edge while they overflow ---------------- */
  function fadeWide(root = document) {
    $$(".dir-table-wrap", root).forEach((w) => {
      const upd = () => w.classList.toggle("fade", w.scrollWidth > w.clientWidth + 2 && w.scrollLeft + w.clientWidth < w.scrollWidth - 2);
      upd();
      if (w.dataset.fade) return;
      w.dataset.fade = 1;
      w.addEventListener("scroll", upd, { passive: true });
      if (window.ResizeObserver) {
        const ro = new ResizeObserver(upd);
        ro.observe(w);
        const t = w.querySelector("table");
        if (t) ro.observe(t);
      }
    });
  }

  /* ---------------- print: open every <details>, then put them back ---------------- */
  let printOpened = [];
  addEventListener("beforeprint", () => { printOpened = $$("details:not([open])"); printOpened.forEach((d) => { d.open = true; }); });
  addEventListener("afterprint", () => { printOpened.forEach((d) => { d.open = false; }); printOpened = []; });

  /* ---------------- my town, last visit, lost-pets badge ---------------- */
  const TOWNS = ["New Kensington", "Arnold", "Lower Burrell"];
  const town = () => { const t = local.get("nk-town"); return TOWNS.includes(t) ? t : null; };
  function setTown(t) {
    if (t && !TOWNS.includes(t)) return;
    if (t) local.set("nk-town", t); else local.del("nk-town");
    document.dispatchEvent(new CustomEvent("nk-town", { detail: t }));
  }
  /* order a list so my town comes first (never hides anything) */
  const townFirst = (list, key = (x) => x) => { const t = town(); return t ? [...list].sort((a, b) => (key(b) === t) - (key(a) === t)) : list; };
  /* the previous visit's start, fixed for this browser session */
  const prevVisit = (() => {
    let prev = session.get("nk-visit-prev");
    if (prev === null) {
      prev = local.get("nk-last-visit") || "";
      session.set("nk-visit-prev", prev);
      local.set("nk-last-visit", new Date().toISOString());
    }
    return prev || null;
  })();
  function setBadge(n) {
    const a = $('.secbar a[data-nav="lost-pets"]');
    if (!a) return;
    a.querySelector(".badge")?.remove();
    if (n > 0) {
      a.insertAdjacentHTML("beforeend", `<span class="badge" aria-hidden="true">${n > 9 ? "9+" : n}</span>`);
      a.setAttribute("aria-label", `Lost pets, ${n} new listing${n === 1 ? "" : "s"} since your last visit`);
    } else a.removeAttribute("aria-label");
  }

  /* ---------------- share and copy ---------------- */
  async function copy(text) {
    try { await navigator.clipboard.writeText(text); return true; } catch (e) { /* fall through */ }
    try {
      const t = Object.assign(document.createElement("textarea"), { value: text });
      t.setAttribute("readonly", ""); t.style.position = "fixed"; t.style.opacity = "0";
      document.body.appendChild(t); t.select();
      const ok = document.execCommand("copy"); t.remove(); return ok;
    } catch (e) { return false; }
  }
  /* resolves "shared" | "copied" | "failed" (a cancelled share sheet counts as shared) */
  async function share({ title, text, url }) {
    if (navigator.share) {
      try { await navigator.share({ title, text, url }); return "shared"; } catch (e) { if (e && e.name === "AbortError") return "shared"; }
    }
    return (await copy([text, url].filter(Boolean).join(" "))) ? "copied" : "failed";
  }
  /* absolute URL of a site path, for sharing */
  const abs = (path) => new URL(ROOT + String(path).replace(/^\//, ""), location.href).href;

  const NKS = window.NKS = {
    $, $$, esc, fmt, ROOT, url: (p) => ROOT + String(p).replace(/^\//, ""),
    local, session, getJSONKey,
    pubName, pub, credit, apDate, apDay, apLong, apTime, day, isoDay, today, daysFrom, relDay, ago, relabel,
    shield, routes, streetHead, shortAddr, cap, endStop, slug, tels, telLink,
    qs, setQS, isDark, onTheme: (f) => themeHooks.push(f), syncTheme, fadeWide,
    TOWNS, town, setTown, townFirst, prevVisit, setBadge, copy, share, abs,
    pages: {},
  };
  /* names older modules read */
  window.NKpub = Object.assign(pub, { pubName, credit });
  window.NKapDate = apDate;
  window.NKshield = shield;

  syncTheme();
  wireMore();
  relabel();
  fadeWide();
  void NKS;
})();
