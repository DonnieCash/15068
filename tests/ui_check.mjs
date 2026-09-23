// Browser checks for the generated site (spec step 12). Run by hand, not in CI:
//
//   python scripts/build_pages.py --out /tmp/nk-a --today 2026-09-23
//   python scripts/build_pages.py --out /tmp/nk-b --today 2026-09-23 --config tests/fixtures/site-ads.json
//   (cd /tmp/nk-a && python -m http.server 8765 &) ; (cd /tmp/nk-b && python -m http.server 8766 &)
//   node tests/ui_check.mjs
//
// Env: NK_BASE (default http://localhost:8765), NK_ADS_BASE (default http://localhost:8766, "" skips the ads checks),
// NK_FONTS (a folder with local.css + the woff2 files, served in place of Google Fonts), NK_THREE (a local
// three.min.js), NK_ONLY (comma-separated check numbers), PLAYWRIGHT (path to the playwright package).
import { createRequire } from "module";
import fs from "fs";
import path from "path";
import { fileURLToPath } from "url";

const require = createRequire(import.meta.url);
const { chromium } = require(process.env.PLAYWRIGHT || "/opt/node22/lib/node_modules/playwright");
const HERE = path.dirname(fileURLToPath(import.meta.url));
const BASE = (process.env.NK_BASE || "http://localhost:8765").replace(/\/$/, "");
const ADS = process.env.NK_ADS_BASE === "" ? "" : (process.env.NK_ADS_BASE || "http://localhost:8766").replace(/\/$/, "");
const ONLY = new Set((process.env.NK_ONLY || "").split(",").filter(Boolean).map(Number));
const ISSUES = fs.readFileSync(path.join(HERE, "fixtures", "pet_issues.json"), "utf8");
const P = { viewport: { width: 390, height: 844 }, hasTouch: true, isMobile: true, deviceScaleFactor: 2 };
const D = { viewport: { width: 1280, height: 800 } };
const W360 = { viewport: { width: 360, height: 740 }, hasTouch: true, isMobile: true };
const C_ROUTES = ["/crime/", "/crime/new-kensington/", "/crime/arnold/", "/crime/lower-burrell/", "/crashes/",
  "/towns/new-kensington/", "/towns/arnold/", "/towns/lower-burrell/", "/history/"];
const WORDS = { 400: ["/crime/new-kensington/", "/crime/arnold/", "/crime/lower-burrell/", "/crashes/", "/towns/new-kensington/",
  "/towns/arnold/", "/towns/lower-burrell/", "/history/", "/lost-pets/"],
  300: ["/crime/", "/numbers/", "/calendar/", "/news/", "/eat/", "/towns/", "/about/", "/privacy/", "/sources/", "/history/people/"],
  200: ["/"] };

const results = [];
const ok = (n, msg) => results.push({ n, pass: true, msg });
const fail = (n, msg) => results.push({ n, pass: false, msg });
const want = (n) => !ONLY.size || ONLY.has(n);
const check = (n, cond, msg) => (cond ? ok(n, msg) : fail(n, msg));

const browser = await chromium.launch(fs.existsSync("/opt/pw-browsers/chromium") ? { executablePath: "/opt/pw-browsers/chromium" } : {});

async function context(opts = {}, { gh = "ok", js = true, scheme = "light" } = {}) {
  const ctx = await browser.newContext({ ...opts, javaScriptEnabled: js, colorScheme: scheme });
  if (process.env.NK_FONTS) {
    await ctx.route(/fonts\.googleapis\.com/, (r) => r.fulfill({ contentType: "text/css", path: path.join(process.env.NK_FONTS, "local.css") }));
    await ctx.route(/fonts\.gstatic\.com\/local\//, (r) => r.fulfill({ contentType: "font/woff2", path: path.join(process.env.NK_FONTS, r.request().url().split("/").pop()) }));
  } else {
    await ctx.route(/fonts\.(googleapis|gstatic)\.com/, (r) => r.abort());
  }
  await ctx.route(/cdnjs\.cloudflare\.com.*three\.min\.js/, (r) => (process.env.NK_THREE ? r.fulfill({ path: process.env.NK_THREE, contentType: "text/javascript" }) : r.continue()));
  await ctx.route(/api\.github\.com/, (r) => (gh === "fail" ? r.fulfill({ status: 403, contentType: "application/json", body: "{}" })
    : r.fulfill({ contentType: "application/json", body: ISSUES })));
  await ctx.route(/googlesyndication|doubleclick|adservice/, (r) => r.abort());
  return ctx;
}

async function page(ctx, url, { errors } = {}) {
  const p = await ctx.newPage();
  if (errors) {
    p.on("pageerror", (e) => errors.push(`${url}: ${e.message}`));
    p.on("console", (m) => { if (m.type() === "error" && !/net::ERR_FAILED|Failed to load resource/.test(m.text())) errors.push(`${url}: ${m.text()}`); });
  }
  await p.goto(url, { waitUntil: "load" });
  await p.waitForTimeout(400);
  return p;
}

const build = JSON.parse(await (await fetch(`${BASE}/data/build.json`)).text());
const ROUTES = build.files.filter((f) => f.endsWith("index.html") || f === "404.html")
  .map((f) => (f === "404.html" ? "/404.html" : "/" + f.replace(/index\.html$/, "")));
const INDEXABLE = (await (await fetch(`${BASE}/sitemap.xml`)).text()).match(/<loc>[^<]+<\/loc>/g).map((l) => new URL(l.slice(5, -6)).pathname);

// 1 — home layout budgets
if (want(1)) {
  const ctx = await context(P);
  const p = await page(ctx, `${BASE}/`);
  await p.waitForTimeout(600);
  const m = await p.evaluate(() => {
    const b = (s) => { const e = document.querySelector(s); return e ? e.getBoundingClientRect().bottom + scrollY : null; };
    return { main: b("main"), pets: b("#pets-box"), cal: b(".cal-row, .cal li, .cal > *") };
  });
  check(1, m.main !== null && m.main <= 2200, `home P main bottom ${m.main} <= 2200`);
  check(1, m.pets !== null && m.pets <= 420, `home P #pets-box bottom ${m.pets} <= 420`);
  check(1, m.cal !== null && m.cal <= 844, `home P first calendar row bottom ${m.cal} <= 844`);
  await ctx.close();
  const cd = await context(D);
  const q = await page(cd, `${BASE}/`);
  const d = await q.evaluate(() => ({
    tels: [...document.querySelectorAll(".nums a.tel")].map((a) => a.getBoundingClientRect().bottom),
    pets: document.querySelector("#pets-box")?.getBoundingClientRect().bottom ?? null,
  }));
  check(1, d.tels.length >= 6 && d.tels.every((b) => b <= 800), `home D ${d.tels.length} .nums tel buttons, max bottom ${Math.max(...d.tels)} <= 800`);
  check(1, d.pets !== null && d.pets <= 380, `home D #pets-box bottom ${d.pets} <= 380`);
  await cd.close();
}

// 2 — the section bar fits at every width
if (want(2)) {
  for (const w of [360, 375, 390, 720, 960, 1280]) {
    const ctx = await context({ viewport: { width: w, height: 800 } });
    const p = await page(ctx, `${BASE}/crime/`);
    const r = await p.evaluate(() => {
      const more = document.querySelector(".secbar details.more > summary").getBoundingClientRect();
      const bar = document.querySelector(".secbar").getBoundingClientRect();
      const links = [...document.querySelectorAll(".secbar .links a")].filter((a) => a.offsetParent);
      const bad = links.filter((a) => { const b = a.getBoundingClientRect(); return b.right > more.left + 0.5 || b.left < bar.left - 0.5; }).map((a) => a.textContent);
      return { bad, sw: document.documentElement.scrollWidth, iw: innerWidth };
    });
    check(2, r.bad.length === 0 && r.sw <= r.iw, `bar at ${w}: clipped ${JSON.stringify(r.bad)}, scrollWidth ${r.sw} <= ${r.iw}`);
    await ctx.close();
  }
}

// 3 — one tap from anywhere to Lost pets, with 3 numbers above the fold
if (want(3)) {
  const ctx = await context(P);
  const bad = [];
  for (const r of ROUTES) {
    const p = await page(ctx, BASE + r);
    const a = p.locator('.secbar a[data-nav="lost-pets"]');
    if (!(await a.isVisible())) { bad.push(`${r}: link hidden`); await p.close(); continue; }
    await a.click();
    await p.waitForLoadState("load");
    if (!new URL(p.url()).pathname.endsWith("/lost-pets/")) bad.push(`${r}: landed on ${p.url()}`);
    await p.close();
  }
  check(3, bad.length === 0, `Lost pets reachable in one tap from ${ROUTES.length} routes ${bad.join("; ")}`);
  const p = await page(ctx, `${BASE}/lost-pets/`);
  const n = await p.evaluate(() => [...document.querySelectorAll("#call-now a.tel")].filter((a) => a.offsetParent && a.getBoundingClientRect().bottom <= 844).length);
  check(3, n >= 3, `/lost-pets/ P: ${n} Call now numbers above 844`);
  await ctx.close();
}

// 4 — tap targets
if (want(4)) {
  const ctx = await context(P);
  const bad = [];
  for (const r of ["/", "/numbers/", "/lost-pets/", "/crime/", "/crime/new-kensington/", "/crime/arnold/", "/crime/lower-burrell/",
    "/towns/new-kensington/", "/towns/arnold/", "/towns/lower-burrell/"]) {
    const p = await page(ctx, BASE + r);
    const small = await p.evaluate(() => [...document.querySelectorAll("a.tel")].filter((a) => a.offsetParent)
      .map((a) => [a.textContent.trim(), a.getBoundingClientRect().height]).filter(([, h]) => h < 44));
    if (small.length) bad.push(`${r}: ${JSON.stringify(small.slice(0, 3))}`);
    await p.close();
  }
  check(4, bad.length === 0, `a.tel heights >= 44 ${bad.join("; ")}`);
  await ctx.close();
}

// 5 — content without JavaScript
if (want(5)) {
  const ctx = await context(P, { js: false });
  const bad = [];
  for (const r of INDEXABLE) {
    const p = await page(ctx, BASE + r);
    const t = await p.evaluate(() => document.querySelector("main").innerText);
    const words = (t.match(/[A-Za-z0-9][\w'’.-]*/g) || []).length;
    const floor = Number(Object.keys(WORDS).find((k) => WORDS[k].includes(r)) || 0);
    if (words < floor) bad.push(`${r}: ${words} < ${floor} words`);
    if (/\bLoading\b/.test(t)) bad.push(`${r}: says Loading`);
    await p.close();
  }
  check(5, bad.length === 0, `no-JS word floors on ${INDEXABLE.length} pages ${bad.join("; ")}`);
  await ctx.close();
}

// 6 — ads: none by default; with ads on, only on C pages, below the fold and below every keep-above block
if (want(6)) {
  const ctx = await context(D);
  const hits = [];
  ctx.on("request", (q) => { if (/googlesyndication/.test(q.url())) hits.push(q.url()); });
  let slots = 0;
  for (const r of ROUTES) { const p = await page(ctx, BASE + r); slots += await p.locator(".adslot").count(); await p.close(); }
  check(6, slots === 0 && hits.length === 0, `ads off: ${slots} slots, ${hits.length} ad requests`);
  await ctx.close();
  if (ADS) {
    for (const opts of [P, D]) {
      const c2 = await context(opts);
      const bad = [];
      for (const r of ROUTES) {
        const p = await page(c2, ADS + r);
        const m = await p.evaluate(() => {
          const s = [...document.querySelectorAll(".adslot")].map((e) => e.getBoundingClientRect().top + scrollY);
          const k = [...document.querySelectorAll("[data-keep-above]")].map((e) => e.getBoundingClientRect().bottom + scrollY);
          return { s, k, h: innerHeight };
        });
        if (!C_ROUTES.includes(r)) { if (m.s.length) bad.push(`${r}: slot on a non-ad page`); }
        else {
          if (m.s.some((t) => t < m.h)) bad.push(`${r}: slot in the first viewport`);
          if (m.s.length && m.k.some((b) => b > Math.min(...m.s))) bad.push(`${r}: keep-above block below a slot`);
        }
        await p.close();
      }
      check(6, bad.length === 0, `ads on at ${opts.viewport.width}px ${bad.join("; ")}`);
      await c2.close();
    }
  }
}

// 7 — old one-page hashes land on their new pages
if (want(7)) {
  const ctx = await context(P);
  const map = { map: "/map/", news: "/news/", pets: "/lost-pets/", towns: "/towns/", safety: "/crime/", story: "/history/", eat: "/eat/",
    people: "/history/people/", directory: "/directory/", sources: "/sources/" };
  const bad = [];
  for (const [h, dest] of Object.entries(map)) {
    const p = await ctx.newPage();
    await p.goto(`${BASE}/#${h}`);
    await p.waitForURL((u) => u.pathname.endsWith(dest), { timeout: 5000 }).catch(() => {});
    const n = await p.evaluate(() => [...document.querySelectorAll("h1")].filter((e) => e.offsetParent || getComputedStyle(e).position === "absolute").length);
    if (!new URL(p.url()).pathname.endsWith(dest) || n !== 1) bad.push(`#${h} -> ${p.url()} (${n} h1)`);
    await p.close();
  }
  check(7, bad.length === 0, `legacy hashes ${bad.join("; ")}`);
  await ctx.close();
}

// 8 — the map page never scrolls and the view stays near the ZIP
if (want(8)) {
  for (const opts of [P, D]) {
    const ctx = await context(opts);
    const p = await page(ctx, `${BASE}/map/`);
    await p.waitForFunction(() => window.NKdebug && window.NKdebug.view, null, { timeout: 15000 }).catch(() => {});
    const sh = await p.evaluate(() => document.scrollingElement.scrollHeight - innerHeight);
    check(8, sh <= 1, `/map/ ${opts.viewport.width}px scrollHeight - innerHeight = ${sh}`);
    const box = await p.locator("#map-canvas").boundingBox();
    const cx = box.x + box.width / 2, cy = box.y + box.height / 2;
    for (let i = 0; i < 3; i++) {
      await p.mouse.move(cx, cy + 150); await p.mouse.down(); await p.mouse.move(cx, cy - 150, { steps: 6 }); await p.mouse.up();
    }
    check(8, (await p.evaluate(() => scrollY)) === 0, `/map/ ${opts.viewport.width}px swipes leave scrollY at 0`);
    for (let i = 0; i < 20; i++) {
      await p.mouse.move(cx - 150, cy); await p.mouse.down(); await p.mouse.move(cx + 250, cy, { steps: 4 }); await p.mouse.up();
    }
    const v = await p.evaluate(async () => ({ v: window.NKdebug?.view?.(), b: (await (await fetch(NKS.url("data/meta.json"))).json()).bounds }));
    check(8, v.v && v.v.x >= v.b[0] - 1001, `/map/ ${opts.viewport.width}px after 20 flings west x=${v.v && Math.round(v.v.x)} >= ${v.b[0] - 1000}`);
    await ctx.close();
  }
}

// 9 — Map it on a lost dog lands on its pin with the streets around it labelled; Back returns
if (want(9)) {
  const ctx = await context(P);
  const p = await page(ctx, `${BASE}/lost-pets/`);
  await p.waitForSelector('#pets-list a[href*="map/?pet=gh-7"]', { timeout: 8000 }).catch(() => {});
  const a = p.locator('#pets-list a[href*="map/?pet=gh-7"]').first();
  if (await a.count()) {
    await a.click();
    await p.waitForURL(/\/map\/\?pet=gh-7/);
    await p.waitForFunction(() => window.NKdebug && (window.NKdebug.labels || []).length > 0, null, { timeout: 15000 }).catch(() => {});
    const r = await p.evaluate(() => ({
      pressed: document.querySelector("#tpet")?.getAttribute("aria-pressed"), scale: document.querySelector("#scale")?.textContent,
      labels: window.NKdebug?.labels || [], pin: window.NKdebug?.pin?.("gh-7"), card: document.querySelector("#card")?.getBoundingClientRect().toJSON(),
    }));
    check(9, r.pressed === "true", `#tpet aria-pressed=${r.pressed}`);
    check(9, /100\s*m/.test(r.scale || ""), `#scale reads ${JSON.stringify(r.scale)}`);
    check(9, r.labels.includes("5th Avenue") && r.labels.includes("11th Street"), `labels ${JSON.stringify(r.labels)}`);
    const inCard = r.pin && r.card && r.pin.x >= r.card.left && r.pin.x <= r.card.right && r.pin.y >= r.card.top && r.pin.y <= r.card.bottom;
    check(9, r.pin && !inCard, `pin ${JSON.stringify(r.pin)} not under the card`);
    await p.goBack();
    await p.waitForTimeout(500);
    check(9, new URL(p.url()).pathname.endsWith("/lost-pets/"), `Back returns to ${p.url()}`);
  } else fail(9, "no Map it link for gh-7 on /lost-pets/");
  await ctx.close();
}

// 10 — a street-only post highlights its street instead of a dot
if (want(10)) {
  const ctx = await context(P);
  const p = await page(ctx, `${BASE}/map/?pet=gh-8`);
  await p.waitForFunction(() => window.NKdebug && window.NKdebug.highlight, null, { timeout: 15000 }).catch(() => {});
  const r = await p.evaluate(() => ({ dots: window.NKdebug?.petDots?.("gh-8"), hl: window.NKdebug?.highlight, card: document.querySelector("#card")?.innerText || "" }));
  check(10, r.dots === 0, `gh-8 pet dots ${r.dots}`);
  check(10, r.hl === "Leechburg Road", `highlight ${r.hl}`);
  check(10, r.card.includes("No cross street was given"), "card says no cross street");
  await ctx.close();
}

// 11 — search
if (want(11)) {
  const ctx = await context(P);
  const s = async (q) => { const p = await page(ctx, `${BASE}/search/?q=${encodeURIComponent(q)}`); await p.waitForTimeout(700); return p; };
  let p = await s("arnold police");
  check(11, (await p.locator("#sresults a[href^='tel:']").first().getAttribute("href").catch(() => null)) === "tel:+17243399663", "arnold police -> first a Call row for 724-339-9663");
  p = await s("fifth ave");
  const t = await p.locator("#sresults").innerText();
  check(11, /5th Avenue/.test(t) && /Fifth Avenue/.test(t), "fifth ave -> 5th Avenue and Fifth Avenue");
  p = await s("lost dog");
  check(11, /lost-pets\/$/.test((await p.locator("#sresults .pages a, #sresults [data-group=pages] a").first().getAttribute("href").catch(() => "")) || ""), "lost dog -> Lost pets page first");
  p = await s("pizza");
  const pz = await p.locator("#sresults").innerText();
  check(11, /Show all 24/.test(pz) && /P & M Pizza/.test(pz), "pizza -> Show all 24 incl. P & M Pizza");
  p = await s("trash");
  const tr = await p.locator("#sresults").innerText();
  check(11, (tr.match(/City Hall|city hall/g) || []).length >= 3 && /public-works|public works/i.test(tr), "trash -> 3 city halls + gap line");
  p = await s("zzz");
  check(11, /Nothing found for/.test(await p.locator("#sresults").innerText()), "zzz -> empty copy");
  await ctx.close();
}

// 12 — a street's page on the map
if (want(12)) {
  const ctx = await context(D);
  const p = await page(ctx, `${BASE}/map/?street=Leishman+Avenue`);
  await p.waitForFunction(() => window.NKdebug && window.NKdebug.highlight, null, { timeout: 15000 }).catch(() => {});
  await p.waitForTimeout(800);
  const r = await p.evaluate(() => ({ hl: window.NKdebug?.highlight, card: document.querySelector("#card")?.innerText || "" }));
  check(12, r.hl === "Leishman Avenue", `highlight ${r.hl}`);
  check(12, /6 news-reported incidents/.test(r.card) && /3 in Arnold, 3 in New Kensington/.test(r.card), "Near card: 6 incidents, 3 + 3");
  await ctx.close();
}

// 13 — blotter street filter
if (want(13)) {
  const ctx = await context(P);
  const p = await page(ctx, `${BASE}/crime/blotter/?street=Leishman`);
  await p.waitForTimeout(600);
  const n = await p.evaluate(() => [...document.querySelectorAll("#inc-list .entry")].filter((e) => e.offsetParent).length);
  check(13, n === 6, `blotter ?street=Leishman shows ${n} entries`);
  await ctx.close();
}

// 14 — when GitHub is unreachable and there is no snapshot, never claim the board is empty
if (want(14)) {
  const ctx = await context(P, { gh: "fail" });
  const home = await page(ctx, `${BASE}/`);
  await home.waitForTimeout(1500);
  const h = await home.locator("#pets-box").innerText();
  const lp = await page(ctx, `${BASE}/lost-pets/`);
  await lp.waitForTimeout(1500);
  const s = await lp.locator("#pets-status").innerText();
  check(14, /didn.t load/.test(h) && !/No open listings/.test(h), "home pets box shows the unknown state");
  check(14, /didn.t load/.test(s) && !/No open listings/.test(s), "/lost-pets/ status shows the unknown state");
  await ctx.close();
}

// 15 — dark theme
if (want(15)) {
  const ctx = await context(P, { scheme: "dark" });
  const bad = [];
  for (const r of ["/", "/lost-pets/", "/crime/"]) {
    const p = await page(ctx, BASE + r);
    const bg = await p.evaluate(() => getComputedStyle(document.body).backgroundColor);
    if (bg === "rgb(255, 255, 255)") bad.push(`${r} background ${bg}`);
    if (r === "/") {
      const src = await p.evaluate(() => [...document.querySelectorAll("picture.themed img")].map((i) => i.currentSrc));
      if (!src.length || !src.every((s) => s.endsWith("-dark.svg"))) bad.push(`locator ${JSON.stringify(src)}`);
    }
    await p.close();
  }
  check(15, bad.length === 0, `dark theme ${bad.join("; ")}`);
  await ctx.close();
}

// 16, 17, 19 — every route: three.js only on 3D, no sideways scroll at 360, no console errors at P and D
if (want(16) || want(17) || want(19)) {
  const errors = [], three = [], wide = [];
  for (const opts of [P, D, W360]) {
    const ctx = await context(opts);
    ctx.on("request", (q) => { if (/three(\.min)?\.js/.test(q.url())) three.push(q.frame().url()); });
    for (const r of ROUTES) {
      const p = await page(ctx, BASE + r, { errors: opts === W360 ? null : errors });
      if (opts === W360 && (await p.evaluate(() => document.documentElement.scrollWidth > innerWidth))) wide.push(r);
      await p.close();
    }
    await ctx.close();
  }
  if (want(16)) check(16, three.every((u) => new URL(u).pathname.endsWith("/map/3d/")) && three.length > 0, `three.js requested from ${[...new Set(three.map((u) => new URL(u).pathname))].join(", ")}`);
  if (want(17)) check(17, wide.length === 0, `no sideways scroll at 360 ${wide.join(", ")}`);
  if (want(19)) check(19, errors.length === 0, `console errors: ${errors.slice(0, 8).join(" | ")}`);
}

// 18 — the phone numbers print on at most two Letter pages
if (want(18)) {
  const ctx = await context(D);
  const p = await page(ctx, `${BASE}/numbers/`);
  const pdf = await p.pdf({ format: "Letter" });
  const pages = (pdf.toString("latin1").match(/\/Type\s*\/Page[^s]/g) || []).length;
  check(18, pages >= 1 && pages <= 2, `/numbers/ prints on ${pages} Letter pages`);
  await ctx.close();
}

// 20 — "I found a pet" puts the police first
if (want(20)) {
  const ctx = await context(P);
  const p = await page(ctx, `${BASE}/lost-pets/`);
  await p.click('a.seg[href="#found"]');
  await p.waitForTimeout(300);
  const r = await p.evaluate(() => ({
    found: !!document.querySelector("#found")?.offsetParent, lost: !!document.querySelector("#lost")?.offsetParent,
    first: [...document.querySelectorAll("#call-now [data-row], #call-now li, #call-now .row")].find((e) => e.offsetParent)?.innerText || "",
  }));
  check(20, r.found && !r.lost, `found steps visible (${r.found}), lost hidden (${!r.lost})`);
  check(20, /police/i.test(r.first), `first Call now row: ${JSON.stringify(r.first.slice(0, 60))}`);
  await ctx.close();
}

await browser.close();
const failed = results.filter((r) => !r.pass);
for (const r of results) console.log(`${r.pass ? "ok  " : "FAIL"} #${r.n} ${r.msg}`);
console.log(`\n${results.length - failed.length}/${results.length} passed`);
process.exit(failed.length ? 1 : 0);
