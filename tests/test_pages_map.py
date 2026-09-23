"""The map pages: data/search.json, /directory/, /map/, /map/3d/ and /search/ (and the search matcher in search.js)."""
import json
import re
import shutil
import subprocess
import sys
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
        self.assertEqual(PM.town_label({"a": "357 Freeport St, New Kensingtn", "t": "New Kensington"}), "New Kensington")
        self.assertEqual(PM.town_label({"a": "3020 Leechburg Rd, Lower-Burrell", "t": "New Kensington"}), "Lower Burrell")
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
for (const q of ["arnold police", "fifth ave", "lost dog", "pizza", "trash", "zzz", "5th & 9th"]) {
  const m = X.match(q, d, {});
  const G = m.groups;
  out[q] = { call: G.call.map((r) => [r.n, r.ph[0]]), pages: G.pages.map((r) => r.u), streets: G.streets.map((s) => s.n),
             places: G.places.map((p) => p.n), corner: G.corner.length, gap: m.gap, total: m.total };
}
out.dedupe = X.dedupe(rd("places.json")).length;
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

    def test_directory_rule_matches_python(self):
        places = json.loads((ROOT / "site/data/places.json").read_text())
        self.assertEqual(self.m["dedupe"], len(PM.dedupe(places)))


if __name__ == "__main__":
    unittest.main()
