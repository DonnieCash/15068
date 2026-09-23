"""The map pages: data/search.json, /directory/, /map/, /map/3d/ and /search/ (and the search matcher in search.js)."""
import functools
import http.server
import json
import os
import re
import shutil
import subprocess
import sys
import threading
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))

from pagebuild import ROOT, build, html_of, parse  # noqa: E402
from test_pages import needs_site  # noqa: E402

from nkpages import fmt  # noqa: E402
from nkpages import pages_map as PM  # noqa: E402

SYN = {"pharmacy": ["drugstore", "drug store", "pharmacies"], "grocery": ["supermarket", "groceries", "food store"],
       "police": ["cops", "non-emergency", "nonemergency"],
       "city hall": ["borough building", "municipal building", "council", "mayor", "city"],
       "trash": ["garbage", "refuse", "recycling", "pothole", "potholes", "public works", "snow", "plow"],
       "lost pet": ["lost dog", "lost cat", "found dog", "found cat", "stray", "missing dog", "missing cat", "warden",
                    "dog catcher", "animal control"]}
KEPT_IDS = ["explorer", "map-canvas", "gl-host", "map-loading", "q", "results", "chips", "layers-btn", "layers-pop", "tbld",
            "trel", "tinc", "tcr", "tpet", "dt", "home", "zin", "zout", "card", "inc-legend", "scale", "t3d"]


def known_phones():
    known = set()
    for f in ("data/research/civic.json", "data/research/pets.json", "site/data/places.json", "site/data/safety.json"):
        known |= {re.sub(r"\D", "", m) for m in re.findall(r"\(?\d{3}\)?[-. ]?\d{3}[-. ]\d{4}", (ROOT / f).read_text())}
    return known


@needs_site
class SearchJSON(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.out = build("default")
        cls.s = json.loads((cls.out / "data/search.json").read_text(encoding="utf-8"))

    def test_shape(self):
        s = self.s
        self.assertEqual(set(s), {"built", "pages", "numbers", "events", "news", "streets_inc", "syn"})
        self.assertEqual(s["built"], "2026-09-23")
        self.assertEqual(s["syn"], SYN)
        for p in s["pages"]:
            self.assertEqual(set(p), {"t", "u", "k"})
        for n in s["numbers"]:
            self.assertEqual(set(n), {"n", "t", "ph", "u", "k"})
            self.assertRegex(n["u"], r"^numbers/#(new-kensington|arnold|lower-burrell|county)$")
        for e in s["events"]:
            self.assertEqual(set(e), {"n", "next", "label", "u"})
        for n in s["news"]:
            self.assertLessEqual({"h", "d", "u", "o"}, set(n))
            self.assertLessEqual(set(n), {"h", "d", "u", "o", "about"})
        for r in s["streets_inc"]:
            self.assertEqual(set(r), {"s", "n", "u"})

    def test_pages_are_the_indexable_routes(self):
        from nkpages import routes as NR
        want = sorted(r.path.lstrip("/") for r in NR.ROUTES if r.index == "I")
        self.assertEqual(sorted(p["u"] for p in self.s["pages"]), want)
        lp = next(p for p in self.s["pages"] if p["u"] == "lost-pets/")
        self.assertEqual(lp["t"], "Lost or found a pet")

    def test_numbers_come_from_the_data(self):
        known = known_phones()
        rows = self.s["numbers"]
        self.assertGreaterEqual(len(rows), 20)
        for r in rows:
            for ph in r["ph"]:
                self.assertRegex(ph, r"^\d{3}-\d{3}-\d{4}$")
                self.assertIn(ph.replace("-", ""), known, r["n"])
        arnold = next(r for r in rows if r["n"] == "Arnold police, non-emergency")
        self.assertEqual(arnold["ph"][0], "724-339-9663")
        self.assertEqual(sum(1 for r in rows if r["n"].endswith("City Hall")), 3)

    def test_links_resolve(self):
        cal, news = html_of(self.out, "/calendar/"), html_of(self.out, "/news/")
        for e in self.s["events"]:
            self.assertIn(f'id="{e["u"].split("#")[1]}"', cal, e["n"])
        for n in self.s["news"]:
            self.assertIn(f'id="{n["u"].split("#")[1]}"', news, n["h"])
        fri = next(e for e in self.s["events"] if e["n"] == "Fridays on Fifth")
        self.assertEqual(fri["next"], "2026-09-25")

    def test_streets_with_incidents(self):
        names = {s["n"] for s in json.loads((ROOT / "site/data/streets.json").read_text())}
        by = {r["s"]: r for r in self.s["streets_inc"]}
        self.assertEqual(by["Leishman Avenue"]["n"], 6)
        self.assertEqual(by["Leishman Avenue"]["u"], "crime/blotter/?street=Leishman+Avenue")
        for r in self.s["streets_inc"]:
            self.assertIn(r["s"], names)
            self.assertGreater(r["n"], 0)

    def test_no_aggregator_news(self):
        self.assertFalse([n for n in self.s["news"] if n["o"] in ("citizenportal.ai", "hoodline.com")])


@needs_site
class Directory(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.out = build("default")
        cls.html = html_of(cls.out, "/directory/")
        cls.places = json.loads((ROOT / "site/data/places.json").read_text())
        cls.rows = re.findall(r"<tr><td class=\"dn\">.*?</tr>", cls.html, re.S)

    def test_first_100_static(self):
        self.assertEqual(len(self.rows), 100)
        self.assertIn('id="dir-tabs"', self.html)
        for i in ("dir-q", "dir-count", "dir-table", "dir-more", "dir-town"):
            self.assertIn(f'id="{i}"', self.html)

    def test_no_duplicates(self):
        """No two static rows share the de-duplication key (phone digits + name, or name + 50 m cell)."""
        by_href = {}
        for p in self.places:
            by_href.setdefault(f"?place={fmt.slug(p['n'])}~{round(p['x'])},{round(p['y'])}", p)
        keys = []
        for r in self.rows:
            href = re.search(r'href="\.\./map/(\?place=[^"]+)"', r).group(1)
            keys.append(PM.dedupe_key(by_href[href.replace("&amp;", "&")]))
        self.assertEqual(len(keys), len(set(keys)))

    def test_dedupe_rule(self):
        kept = PM.dedupe(self.places)
        keys = [PM.dedupe_key(p) for p in kept]
        self.assertEqual(len(keys), len(set(keys)))
        for p in self.places:  # every dropped row lost to a kept one with the same key and at least its q
            if p in kept:
                continue
            other = next(k for k in kept if PM.dedupe_key(k) == PM.dedupe_key(p))
            self.assertGreaterEqual(other.get("q", 0), p.get("q", 0))
        names = [re.sub(r"<[^>]+>", "", re.search(r'<td class="dn">(.*?)<span class="sub"', r).group(1)) for r in self.rows]
        low = [__import__("html").unescape(n).lower() for n in names]
        self.assertEqual(low, sorted(low), "A to Z")

    def test_rows_link_to_the_map_and_call(self):
        for r in self.rows:
            self.assertRegex(r, r'href="\.\./map/\?place=[a-z0-9-]+~-?\d+,-?\d+"')
            for href in re.findall(r'href="(tel:[^"]*)"', r):
                self.assertRegex(href, r"^tel:\+1\d{10}$")

    def test_town_labels(self):
        # the municipality from the town boundaries, never the mailing city ("New Kensington" covers much of the ZIP)
        self.assertEqual(PM.town_label({"a": "357 Freeport St, New Kensingtn", "t": "New Kensington"}), "New Kensington")
        self.assertEqual(PM.town_label({"a": "3020 Leechburg Rd, New Kensington", "t": "Lower Burrell"}), "Lower Burrell")
        self.assertEqual(PM.town_label({"a": "5 River Rd, Oakmont", "t": "Plum"}), "Plum")
        self.assertEqual(PM.town_label({"t": "Arnold"}), "Arnold")


@needs_site
class MapPages(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.out = build("default")
        cls.map = html_of(cls.out, "/map/")
        cls.map3d = html_of(cls.out, "/map/3d/")
        cls.search = html_of(cls.out, "/search/")

    def test_map_ids(self):
        for i in KEPT_IDS:
            self.assertEqual(len(re.findall(rf'\bid="{i}"', self.map)), 1, i)
        self.assertIn('<a id="t3d" href="3d/">3D view ›</a>', self.map)

    def test_map_page_parts(self):
        p = parse(self.map)
        self.assertEqual(p.h1, ["Map of ZIP 15068"])
        self.assertNotIn('class="site-foot"', self.map)
        self.assertNotIn("utility", self.map.split("<main")[0].split('class="masthead')[1][:200])
        self.assertIn("Drawing the map…", self.map)
        self.assertNotIn("Loading map data", self.map)
        self.assertIn('placeholder="A business, street or corner, like 5th &amp; 9th"', self.map)
        order = [re.search(rf'id="{i}"', self.map).start() for i in ("tpet", "tinc", "tcr", "tbld", "trel", "dt", "home", "t3d")]
        self.assertEqual(order, sorted(order), "layers order")
        self.assertNotIn("map-credit", self.map)
        self.assertIn('class="attrib"', self.map)
        data = json.loads(re.search(r'<script type="application/json" id="map-data">(.*?)</script>', self.map).group(1))
        self.assertEqual(data["police"]["Arnold"]["ph"], "724-339-9663")

    def test_noscript_fallback(self):
        ns = re.search(r"<noscript>(.*?)</noscript>", self.map, re.S).group(1)
        self.assertIn("../poster/15068-roads.svg", ns)
        self.assertIn('href="../directory/"', ns)
        self.assertIn('href="../numbers/"', ns)
        text = re.sub(r"<[^>]+>", " ", re.search(r'<p class="nojs-t">(.*?)</p>', ns, re.S).group(1))
        self.assertTrue(text.strip().startswith("Every street, building and storefront in ZIP 15068, drawn from open data"))
        self.assertGreaterEqual(len(re.findall(r"[A-Za-z0-9][\w'’.-]*", text)), 55)
        ns3 = re.search(r"<noscript>(.*?)</noscript>", self.map3d, re.S).group(1)
        self.assertIn("../../poster/15068-roads.svg", ns3)

    def test_three_only_on_3d(self):
        self.assertIn("cdnjs.cloudflare.com/ajax/libs/three.js/r128/three.min.js", self.map3d)
        for p in self.out.rglob("*.html"):
            if p.is_symlink() or p == self.out / "map/3d/index.html":
                continue
            self.assertNotIn("three.min.js", p.read_text(encoding="utf-8"), p)

    def test_3d_copy(self):
        for s in ("15068 in 3D", "Made for looking, not finding. To find a place, ", "use the flat map ›", "Downtown New Kensington",
                  "Lower Burrell hills", "Whole ZIP", "Town labels", "Save as image", "Poster mode",
                  "Back to the flat map ›", "New Kensington · Arnold · Lower Burrell"):
            self.assertIn(s, self.map3d)

    def test_search_shell(self):
        self.assertIn('<form class="sitesearch s-form" id="sq"', self.search)
        self.assertIn('id="sresults"', self.search)
        ns = re.sub(r"<[^>]+>", "", re.search(r"<noscript>(.*?)</noscript>", self.search, re.S).group(1))
        self.assertEqual(ns, "Search needs JavaScript. Try Phone numbers, Lost pets, or Places and streets A to Z.")
        self.assertIn('name="robots" content="noindex"', self.search)


NODE_MATCH = r"""
const fs = require("fs"), vm = require("vm");
const [src, dir] = process.argv.slice(1);
const ctx = { window: {}, console };
vm.createContext(ctx);
vm.runInContext(fs.readFileSync(src, "utf8"), ctx);
const X = ctx.window.NKSearch, rd = (f) => JSON.parse(fs.readFileSync(dir + "/" + f, "utf8"));
const d = X.prepare({ ...rd("search.json"), places: rd("places.json"), streets: rd("streets.json"), groups: rd("meta.json").groups });
const out = {};
for (const q of ["arnold police", "fifth ave", "lost dog", "pizza", "trash", "zzz", "5th & 9th", "Route 366", "PA 366", "SR 780",
                 "route 780", "Route 56", "PA-56", "Rt. 56", "366", "constructor"]) {
  const m = X.match(q, d, {});
  const G = m.groups;
  out[q] = { call: G.call.map((r) => [r.n, r.ph[0]]), pages: G.pages.map((r) => r.u), streets: G.streets.map((s) => s.n),
             places: G.places.map((p) => p.n), corner: G.corner.length, gap: m.gap, total: m.total };
}
out.dedupe = X.dedupe(rd("places.json")).length;
out.norm = ["Route 366", "PA 366", "SR-780", "US Route 22", "Rt. 56", "State Route 780", "New Kensington, PA 15068", "constructor"].map(X.norm);
out.key = X.streetKey("constructor");
out.web = ["dashdesign.net", "www.cuttingedgehairsalons.com", "example.com/menu?x=1", "EdwardJones",
           "local.dmv.org/pennsylvania/westmoreland-county/new-kensington/1600...", "https://www.facebook.com/x", "http://www.cbc_lbc.org/",
           "javascript:alert(1)", "", null].map(X.webURL);
out.webAll = rd("places.json").flatMap((p) => [p.w, p.s].filter(Boolean).map((v) => [v, X.webURL(v)]));
process.stdout.write(JSON.stringify(out));
"""


@needs_site
@unittest.skipUnless(shutil.which("node"), "node is not installed")
class SearchMatch(unittest.TestCase):
    """search.js match() on the built data: the spec's search checks, without a browser."""

    @classmethod
    def setUpClass(cls):
        out = build("default")
        r = subprocess.run(["node", "-e", NODE_MATCH, str(ROOT / "site/assets/search.js"), str(out / "data")],
                           capture_output=True, text=True)
        if r.returncode:
            raise RuntimeError(r.stderr)
        cls.m = json.loads(r.stdout)

    def test_call_first_with_town(self):
        self.assertEqual(self.m["arnold police"]["call"][0], ["Arnold police, non-emergency", "724-339-9663"])

    def test_street_key(self):
        self.assertIn("5th Avenue", self.m["fifth ave"]["streets"])
        self.assertIn("Fifth Avenue", self.m["fifth ave"]["streets"])

    def test_lost_pet_intent(self):
        self.assertEqual(self.m["lost dog"]["pages"][0], "lost-pets/")

    def test_places(self):
        self.assertEqual(len(self.m["pizza"]["places"]), 24)
        self.assertIn("P & M Pizza", self.m["pizza"]["places"][:10])

    def test_trash(self):
        t = self.m["trash"]
        self.assertTrue(t["gap"])
        self.assertEqual(sorted(n for n, _ in t["call"]), ["Arnold City Hall", "Lower Burrell City Hall", "New Kensington City Hall"])

    def test_empty_and_corner(self):
        self.assertEqual(self.m["zzz"]["total"], 0)
        self.assertEqual(self.m["5th & 9th"]["corner"], 1)

    def test_route_numbers(self):
        """"Route 366", "PA 366", "SR 780" name the streets that carry the route; places whose address gives it match."""
        r366 = {"Tarentum Bridge", "Tarentum Bridge Road", "Stevenson Boulevard", "Freeport Street", "Greensburg Road"}
        for q in ("Route 366", "PA 366", "366"):
            self.assertEqual(set(self.m[q]["streets"]), r366, q)
        for q in ("SR 780", "route 780"):
            self.assertEqual(set(self.m[q]["streets"]), {"7th Street Road", "7th Street", "Powers Drive"}, q)
        for q in ("Route 56", "PA-56", "Rt. 56"):
            self.assertIn("Leechburg Road", self.m[q]["streets"], q)
            self.assertIn("Stevenson Boulevard", self.m[q]["streets"], q)
            self.assertLessEqual({"Ace Hardware", "Avis Car Rental"}, set(self.m[q]["places"]), q)
        self.assertEqual(self.m["norm"], ["rt366", "rt366", "rt780", "rt22", "rt56", "rt780", "new kensington pa 15068", "constructor"])

    def test_prototype_words(self):
        self.assertEqual(self.m["constructor"]["total"], 0)
        self.assertEqual(self.m["key"], {"core": "constructor", "type": None})

    def test_web_links(self):
        self.assertEqual(self.m["web"], ["https://dashdesign.net", "https://www.cuttingedgehairsalons.com", "https://example.com/menu?x=1",
                                         "", "", "https://www.facebook.com/x", "http://www.cbc_lbc.org/", "", "", ""])
        pairs = self.m["webAll"]
        for v, u in pairs:  # every website or social value is a full http(s) link or none at all
            self.assertTrue(u == "" or re.match(r"^https?://[^/\s]+\.[^/\s]+", u), (v, u))
        fixed = [u for v, u in pairs if not re.match(r"^https?://", v) and u]
        self.assertGreaterEqual(len(fixed), 16)
        self.assertTrue(all(u.startswith("https://") for u in fixed))
        self.assertIn(("EdwardJones", ""), [tuple(x) for x in pairs])

    def test_directory_rule_matches_python(self):
        places = json.loads((ROOT / "site/data/places.json").read_text())
        self.assertEqual(self.m["dedupe"], len(PM.dedupe(places)))


NODE_BROWSER = r"""
const [base, issuesFile, placePaths] = process.argv.slice(1);
const { chromium } = require(process.env.PLAYWRIGHT);
const fs = require("fs"), path = require("path");
const out = { errors: [] };
const wait = (p, ms) => p.waitForTimeout(ms);
(async () => {
  const b = await chromium.launch(process.env.NK_CHROMIUM ? { executablePath: process.env.NK_CHROMIUM } : {});
  async function context(w, h, { gh = "ok", geo = null } = {}) {
    const phone = w < 700;
    const ctx = await b.newContext({ viewport: { width: w, height: h }, hasTouch: phone, isMobile: phone,
      ...(geo ? { geolocation: geo, permissions: ["geolocation"] } : {}) });
    const F = process.env.NK_FONTS;
    if (F) {
      await ctx.route(/fonts\.googleapis\.com/, (r) => r.fulfill({ contentType: "text/css", path: path.join(F, "local.css") }));
      await ctx.route(/fonts\.gstatic\.com\/local\//, (r) => r.fulfill({ contentType: "font/woff2", path: path.join(F, r.request().url().split("/").pop()) }));
    } else await ctx.route(/fonts\.(googleapis|gstatic)\.com/, (r) => r.abort());
    await ctx.route(/cdnjs\.cloudflare\.com/, (r) => (process.env.NK_THREE ? r.fulfill({ path: process.env.NK_THREE, contentType: "text/javascript" }) : r.abort()));
    /* "hang": the GitHub API never answers */
    await ctx.route(/api\.github\.com/, (r) => { if (gh !== "hang") r.fulfill({ contentType: "application/json", body: fs.readFileSync(issuesFile, "utf8") }); });
    return ctx;
  }
  async function open(ctx, url) {
    const p = await ctx.newPage();
    p.on("pageerror", (e) => out.errors.push(url + ": " + e.message));
    p.on("console", (m) => { if (m.type() === "error" && !/Failed to load resource|net::ERR/.test(m.text())) out.errors.push(url + ": " + m.text()); });
    await p.goto(base + url, { waitUntil: "load" });
    if (/^\/map\/(\?|$)/.test(url)) await p.waitForFunction(() => window.NKdebug && window.NKdebug.view, null, { timeout: 15000 });
    return p;
  }
  const until = (p, f, arg) => p.waitForFunction(f, arg, { timeout: 6000 }).then((h) => h.jsonValue()).catch(() => null);

  /* 1. Use my location after a zoom tap: nothing in ?at= while the view is on the spot; Copy link names the corner */
  for (const [w, h] of [[390, 844], [1280, 800]]) {
    const ctx = await context(w, h, { geo: { latitude: 40.56912, longitude: -79.76234 } });
    const p = await open(ctx, "/map/?at=-3000,0,1.5&place=nowhere");
    await wait(p, 1200);
    const r = out["located" + w] = {};
    await p.click("#zin"); await wait(p, 900);
    r.zoomed = p.url();
    await p.click("#q"); await p.click('[data-k="loc"]'); await p.click("#loc-go");
    r.card = await until(p, () => { const t = document.querySelector("#card").innerText; return /Your location/.test(t) && t; });
    await wait(p, 1500);
    r.located = p.url();
    await p.click("#zin"); await wait(p, 900);
    r.zoomedOnSpot = p.url();
    r.copied = await p.evaluate(async () => {
      let t = null;
      NKS.copy = async (x) => { t = x; return true; };
      document.querySelector("#card [data-copy]").click();
      await new Promise((ok) => setTimeout(ok, 50));
      return t;
    });
    const box = await p.locator("#map-canvas").boundingBox();
    for (let i = 0; i < 4; i++) {
      await p.mouse.move(box.x + box.width - 20, box.y + 200); await p.mouse.down();
      await p.mouse.move(box.x + 20, box.y + 200, { steps: 5 }); await p.mouse.up();
    }
    await wait(p, 900);
    r.away = p.url();
    await ctx.close();
  }

  /* 2. a board that never answers: ?near= and the search panel still work */
  {
    const ctx = await context(1280, 800, { gh: "hang" });
    let p = await open(ctx, "/map/?near=5th+%26+9th");
    out.hungNear = await until(p, () => { const c = document.querySelector("#card"); return !c.hidden && c.innerText; });
    await p.fill("#q", "pizza");
    out.hungSearch = await until(p, () => /Pizza/.test(document.querySelector("#results").innerText) && document.querySelector("#results").innerText);
    p = await open(ctx, "/map/?pet=gh-7");
    await wait(p, 300);
    await p.fill("#q", "pizza");
    out.hungSearchPet = await until(p, () => /Pizza/.test(document.querySelector("#results").innerText) && document.querySelector("#results").innerText);
    await ctx.close();
  }

  /* 3-7 at 1280 */
  {
    const ctx = await context(1280, 800);
    let p = await open(ctx, "/map/?layer=incidents&street=Fifth+Avenue");
    await wait(p, 2000);
    out.filter = await p.evaluate(async () => {
      const s = await (await fetch(NKS.url("data/safety.json"))).json();
      const v = NKdebug.view(), c = document.querySelector("#map-canvas").getBoundingClientRect(), card = document.querySelector("#card");
      const inc = s.incidents.filter((i) => /\b(5th|fifth)\s+av/i.test(i.l || ""));
      return { n: inc.length, card: card.hidden ? "" : card.innerText, note: document.querySelector(".lg-filter")?.innerText || "", hl: NKdebug.highlight,
        onScreen: inc.map((i) => { const x = (i.x - v.x) * v.s + c.width / 2, y = (i.y - v.y) * v.s + c.height / 2; return x >= 0 && y >= 0 && x <= c.width && y <= c.height; }) };
    });
    await p.click("#inc-all");
    out.filter.hlAfter = await p.evaluate(() => NKdebug.highlight);

    out.links = [];
    for (const u of JSON.parse(placePaths)) {
      p = await open(ctx, u);
      await wait(p, 900);
      out.links.push(await p.evaluate(() => [document.querySelector("#card h3")?.textContent,
        [...document.querySelectorAll("#card a[target=_blank]")].map((a) => [a.textContent, a.getAttribute("href")])]));
    }

    p = await open(ctx, "/map/?layer=incidents&c=constructor");
    await wait(p, 1500);
    out.protoLegend = await p.evaluate(() => document.querySelector("#inc-legend").innerText);
    p = await open(ctx, "/map/?cat=constructor");
    await wait(p, 800);
    out.protoCat = await p.evaluate(() => [...document.querySelectorAll("#chips .chip[aria-pressed=true]")].map((c) => c.dataset.g));
    p = await open(ctx, "/directory/?g=constructor");
    await wait(p, 800);
    out.protoDir = await p.evaluate(() => document.querySelector("#dir-count").textContent);

    p = await open(ctx, "/search/?q=PA+366");
    out.searchPA = await until(p, () => document.querySelector("[data-group=streets]")?.innerText);
    await ctx.close();
  }

  /* 7. the three town names at the whole-ZIP view */
  for (const [w, h] of [[1280, 800], [390, 844]]) {
    const ctx = await context(w, h);
    const p = await open(ctx, "/map/");
    await wait(p, 1200);
    await p.click("#layers-btn"); await p.click("#home"); await wait(p, 600);
    out["towns" + w] = await p.evaluate(() => NKdebug.towns);
    await ctx.close();
  }
  if (process.env.NK_THREE) for (const [w, h] of [[1280, 800], [390, 844]]) {
    const ctx = await context(w, h);
    const p = await open(ctx, "/map/3d/");
    await p.waitForSelector("#p3-ctl:not([hidden])", { timeout: 20000 });
    await p.click('[data-go="zip"]'); await wait(p, 2200);
    out["towns3d" + w] = await p.evaluate(() => {
      const vis = [...document.querySelectorAll("#p3-labels span")].filter((s) => getComputedStyle(s).visibility === "visible")
        .map((s) => ({ t: s.dataset.town, r: s.getBoundingClientRect() }));
      const hit = (a, c) => a.left < c.right && a.right > c.left && a.top < c.bottom && a.bottom > c.top;
      return { names: vis.map((x) => x.t), overlap: vis.some((a, i) => vis.slice(i + 1).some((c) => hit(a.r, c.r))),
        inside: vis.every((x) => x.r.left >= 0 && x.r.right <= innerWidth) };
    });
    await ctx.close();
  }
  await b.close();
  process.stdout.write(JSON.stringify(out));
})().catch((e) => { console.error(e); process.exit(1); });
"""
PLAYWRIGHT = Path(os.environ.get("PLAYWRIGHT") or "/opt/node22/lib/node_modules/playwright")
CHROMIUM = Path("/opt/pw-browsers/chromium")


class _Quiet(http.server.SimpleHTTPRequestHandler):
    def log_message(self, *args):
        pass


@needs_site
@unittest.skipUnless(shutil.which("node") and PLAYWRIGHT.exists(), "Playwright is not installed")
class MapBrowser(unittest.TestCase):
    """/map/ in Chromium: Use my location stays out of the URL, a board that never answers freezes nothing, the blotter's
    street filter, website links, URL values that name Object properties, and the town names at the whole-ZIP view.
    Set NK_THREE (a local three.min.js) to check the 3D labels too, NK_FONTS (ui_check.mjs's font folder) for real fonts."""

    @classmethod
    def setUpClass(cls):
        out = build("default")
        places = json.loads((out / "data/places.json").read_text(encoding="utf-8"))
        want = ("Cutting Edge Hair Salon", "Ak Valley Auto Glass", "Michael J Derouin",
                "Pennsylvania Department of Transportation Drivers License Center")
        paths = [f"/map/?place={fmt.slug(p['n'])}~{round(p['x'])},{round(p['y'])}"
                 for p in (next(p for p in places if p["n"] == n) for n in want)]
        srv = http.server.ThreadingHTTPServer(("127.0.0.1", 0), functools.partial(_Quiet, directory=str(out)))
        threading.Thread(target=srv.serve_forever, daemon=True).start()
        env = {**os.environ, "PLAYWRIGHT": str(PLAYWRIGHT)}
        if CHROMIUM.exists():
            env["NK_CHROMIUM"] = str(CHROMIUM)
        try:
            r = subprocess.run(["node", "-e", NODE_BROWSER, f"http://127.0.0.1:{srv.server_address[1]}",
                                str(ROOT / "tests/fixtures/pet_issues.json"), json.dumps(paths)],
                               capture_output=True, text=True, env=env, timeout=600)
        finally:
            srv.shutdown()
            srv.server_close()
        if r.returncode:
            raise RuntimeError(r.stderr)
        cls.r = json.loads(r.stdout)

    def test_my_location_never_in_the_url(self):
        for w in (390, 1280):
            r = self.r[f"located{w}"]
            self.assertIn("Your location", r["card"] or "", w)
            self.assertIn("at=", r["zoomed"], w)  # a zoom tap writes the view...
            for k in ("located", "zoomedOnSpot"):  # ...but never while it is centred on the located spot
                self.assertNotIn("at=", r[k], (w, k))
                self.assertNotIn("place=", r[k], (w, k))
            self.assertRegex(r["copied"] or "", r"/map/\?near=[A-Za-z+%0-9]+$", w)
            self.assertIn("at=", r["away"], w)  # panned away by hand: the view is written again

    def test_board_that_never_answers(self):
        self.assertIn("Near 5th Ave & 9th St", self.r["hungNear"] or "")
        self.assertIn("P & M Pizza", self.r["hungSearch"] or "")
        self.assertIn("P & M Pizza", self.r["hungSearchPet"] or "")

    def test_blotter_street_filter(self):
        f = self.r["filter"]
        self.assertEqual(f["n"], 2)
        self.assertEqual(f["onScreen"], [True, True], "the view stays on the incidents")
        self.assertEqual(f["card"], "", "no street card")
        self.assertIn("Showing Fifth Avenue", f["note"])
        self.assertEqual(f["hl"], "5th Avenue")
        self.assertIsNone(f["hlAfter"])

    def test_card_links(self):
        by = {n: links for n, links in self.r["links"]}
        self.assertEqual(len(by), 4)
        for n, links in by.items():
            for text, href in links:
                self.assertTrue(text.strip(), (n, href))
                self.assertRegex(href, r"^https?://[^/]+\.[^/]+", n)
        self.assertIn(["Website", "https://www.cuttingedgehairsalons.com"], by["Cutting Edge Hair Salon"])
        self.assertIn(["Website", "https://dashdesign.net"], by["Ak Valley Auto Glass"])
        self.assertNotIn("Website", [t for t, _ in by["Pennsylvania Department of Transportation Drivers License Center"]])

    def test_object_property_names_in_urls(self):
        self.assertNotRegex(self.r["protoLegend"], r"native code|function|Showing")
        self.assertEqual(self.r["protoCat"], ["*"])
        self.assertTrue(self.r["protoDir"].startswith("Showing 100 of"), self.r["protoDir"])

    def test_route_search_page(self):
        self.assertIn("Tarentum Bridge", self.r["searchPA"] or "")

    def test_town_names_at_whole_zip(self):
        for w in (1280, 390):
            self.assertEqual(sorted(self.r[f"towns{w}"]), ["Arnold", "Lower Burrell", "New Kensington"], w)
        if "towns3d1280" not in self.r:
            self.skipTest("set NK_THREE to check the 3D labels")
        for w in (1280, 390):
            t = self.r[f"towns3d{w}"]
            self.assertEqual(sorted(t["names"]), ["Arnold", "Lower Burrell", "New Kensington"], w)
            self.assertFalse(t["overlap"], w)
            self.assertTrue(t["inside"], w)

    def test_no_console_errors(self):
        self.assertEqual(self.r["errors"], [])


if __name__ == "__main__":
    unittest.main()
