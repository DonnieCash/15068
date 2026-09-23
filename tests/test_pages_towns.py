"""The towns builder's pages and files: /towns/*, /news/, /history/*, /eat/, /poster/, /whats-new/, the trust pages,
404, the map art (nkpages.mapsvg) and the changelog (nkpages.changelog).

Run with the other page tests: NK_KEEP_GOING=1 python -m unittest tests.test_pages tests.test_pages_towns
"""
import contextlib
import copy
import datetime as dt
import io
import json
import re
import sys
import tempfile
import unittest
import xml.etree.ElementTree as ET
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))

from pagebuild import ROOT, TODAY, build, html_of, main_words  # noqa: E402
from test_pages import GENERATED  # noqa: E402

from nkpages import changelog, mapsvg  # noqa: E402
from nkpages import data as ND  # noqa: E402
from nkpages import pages_towns as T  # noqa: E402
from nkpages import routes as NR  # noqa: E402

needs_site = unittest.skipUnless(GENERATED, "site/ has not been generated yet (run scripts/build_pages.py)")
TOWNS = {"New Kensington": "new-kensington", "Arnold": "arnold", "Lower Burrell": "lower-burrell"}
ART = ["img/15068-locator.svg", "img/15068-locator-dark.svg", "poster/15068-roads.svg", "poster/15068-roads-dark.svg"] + \
      [f"img/town-{s}{d}.svg" for s in TOWNS.values() for d in ("", "-dark")]
MAROON = ("#8a1c2b", "#5c1621", "#e8848f", "#f1dcdf", "#3a1c20")
# every storage key the site uses (contracts.md); /privacy/ must list them all
KEYS = ["nk-theme", "nk-town", "nk-corner", "nk-last-visit", "nk-seen-pets", "nk-seen-news", "nk-checklist",
        "nk-visit-prev", "nk-flyer-draft"]
FLOORS = {"/towns/new-kensington/": 400, "/towns/arnold/": 400, "/towns/lower-burrell/": 400, "/history/": 400,
          "/towns/": 300, "/news/": 300, "/eat/": 300, "/about/": 300, "/privacy/": 300, "/sources/": 300,
          "/history/people/": 300}
SPEC_GLANCE = {
    "New Kensington": "New Kensington had 12,170 residents in the 2020 census, down from a peak of 25,146 in 1950, and a "
                      "median household income of $49,063. It grew from the June 10, 1891, land sale, became a borough "
                      "in 1892 and a city in 1934. The map data holds 5,990 buildings, 6,222 address points and 565 "
                      "listed places in the city.",
    "Arnold": "Arnold had 4,772 residents in the 2020 census and a median household income of $48,119. It became a "
              "borough in 1896 and a city in 1939. The map data holds 2,365 buildings, 2,444 address points and 123 "
              "listed places in the city.",
    "Lower Burrell": "Lower Burrell had 11,758 residents in the 2020 census, and its median household income, $84,602, "
                     "is the highest of the three cities. It was split off from Burrell Township in 1879 and became a "
                     "city in 1959. The map data holds 5,857 buildings, 5,527 address points and 435 listed places in "
                     "the city.",
}


def load_D(today=TODAY):
    cfg = json.loads((ROOT / "data" / "site.json").read_text())
    D = ND.load(cfg, dt.date.fromisoformat(today))
    D["routes"] = NR.resolve(D)
    return D


def route(D, path):
    return next(r for r in D["routes"] if r.path == path)


def unescape(s):
    return __import__("html").unescape(s)


class Glance(unittest.TestCase):
    """town_glance() is computed from civic, history and meta, never typed in."""

    @classmethod
    def setUpClass(cls):
        cls.D = load_D()

    def test_spec_sentences_for_this_data(self):
        dm = {t: T.demo(self.D, t) for t in TOWNS}
        if dm["Arnold"].get("population_2020") != 4772 or self.D["meta"]["stats"]["buildings"] != 19242:
            self.skipTest("the data changed since the spec's sentences were written")
        for t, want in SPEC_GLANCE.items():
            self.assertEqual(unescape(T.town_glance(self.D, t)), want, t)

    def test_follows_the_data(self):
        D = copy.deepcopy(self.D)
        D["civic"]["demographics"]["arnold_city"]["median_household_income"] = 99999
        D["civic"]["demographics"]["arnold_city"]["population_2020"] = 5001
        D["meta"]["stats"]["buildings_by_town"]["Arnold"] = 2400
        a = unescape(T.town_glance(D, "Arnold"))
        self.assertIn("Arnold had 5,001 residents", a)
        self.assertIn("its median household income, $99,999, is the highest of the three cities", a)
        self.assertIn("2,400 buildings", a)
        lb = unescape(T.town_glance(D, "Lower Burrell"))
        self.assertIn("and a median household income of $84,602", lb)
        self.assertNotIn("highest", lb)

    def test_no_peak_when_2020_is_the_peak(self):
        D = copy.deepcopy(self.D)
        D["history"]["facts"]["population_by_census"]["2020"] = 30000
        self.assertNotIn("peak", T.town_glance(D, "New Kensington"))

    def test_incorporation_from_the_timeline(self):
        D = copy.deepcopy(self.D)
        for e in D["history"]["timeline"]:
            if e["title"] == "Arnold becomes a city":
                e["year"] = 1940
        self.assertIn("a city in 1940", T.town_glance(D, "Arnold"))

    def test_council_next_date(self):
        n, wd, d = T.next_meeting("2nd Tuesday", dt.date(2026, 9, 23))
        self.assertEqual((n, wd, d), (2, "Tuesday", dt.date(2026, 10, 13)))
        self.assertEqual(T.next_meeting("2nd Tuesday", dt.date(2026, 10, 13))[2], dt.date(2026, 10, 13))
        self.assertEqual(T.next_meeting("2nd Tuesday", dt.date(2026, 12, 9))[2], dt.date(2027, 1, 12))

    def test_census_gap_copy(self):
        if set(self.D["history"]["facts"]["population_by_census"]) != {"1930", "1940", "1950", "1960", "2000", "2010", "2020"}:
            self.skipTest("census years changed")
        self.assertEqual(T.census_gaps(self.D), "1900–1920 and 1970–1990")


class TownBodies(unittest.TestCase):
    """The page functions' output, before the shell places ads."""

    @classmethod
    def setUpClass(cls):
        cls.D = load_D()

    def test_keep_above_card_before_any_ad_marker(self):
        for t, s in TOWNS.items():
            body = T.town(self.D, route(self.D, f"/towns/{s}/"))["body"]
            with self.subTest(town=t):
                k = body.index("data-keep-above")
                self.assertLess(k, body.index("<!--AD:mid-->"))
                self.assertLess(k, body.index("<!--AD:end-->"))
                self.assertNotIn("data-keep-above", body[body.index("<!--AD:mid-->"):])
                card = body[k:body.index("</section>", k)]
                self.assertIn('href="tel:911"', card)
                self.assertIn(f"Make {t} my town", card)

    def test_history_markers(self):
        body = T.history(self.D, route(self.D, "/history/"))["body"]
        mid, end = body.index("<!--AD:mid-->"), body.index("<!--AD:end-->")
        self.assertLess(body.index('id="1891-1945"'), mid)
        self.assertLess(mid, body.index('id="1946-1999"'))
        self.assertLess(body.index('id="landmarks"'), end)

    def test_news_ids(self):
        items = T.news_items(self.D)
        ids = [n["id"] for n in items]
        self.assertEqual(len(ids), len(set(ids)))
        self.assertTrue(all(re.match(r"^n-[a-z0-9-]+$", i) for i in ids))
        self.assertFalse([n for n in items if T.fmt.is_aggregator_only(n.get("source"))])


@needs_site
class Built(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.out = build("default")
        cls.D = load_D()

    def page(self, path):
        return html_of(self.out, path)

    def test_word_floors(self):
        for path, floor in FLOORS.items():
            with self.subTest(route=path):
                self.assertGreaterEqual(main_words(self.page(path)), floor)

    def test_town_pages(self):
        for t, s in TOWNS.items():
            h = self.page(f"/towns/{s}/")
            with self.subTest(town=t):
                self.assertIn(T.town_glance(self.D, t), h)
                for sid in ("call-city", "glance", "parks", "safety", "crashes", "places", "whats-here", "history",
                            "news", "pets-" + s):
                    self.assertIn(f'id="{sid}"', h)
                self.assertIn(f"img/town-{s}.svg", h)
                self.assertIn(f"img/town-{s}-dark.svg", h)
                self.assertIn(f'data-pets-town="{t}"', h)
                self.assertIn("directory/?town=", h)
        a = self.page("/towns/arnold/")
        self.assertIn("Council</b> meets the second Tuesday of the month at 7 p.m. Next expected: Tuesday, Oct. 13.", a)
        self.assertIn("Council</b> meeting nights aren&rsquo;t in our data yet.", self.page("/towns/lower-burrell/"))

    def test_hub(self):
        h = self.page("/towns/")
        self.assertIn('id="towns-grid"', h)
        self.assertIn('id="ledger-grid"', h)
        self.assertEqual(h.count('class="tw-card"'), 3)
        self.assertIn("img/15068-locator.svg", h)

    def test_art_files(self):
        for rel in ART:
            p = self.out / rel
            with self.subTest(file=rel):
                self.assertTrue(p.exists())
                txt = p.read_text(encoding="utf-8")
                root = ET.fromstring(txt)
                self.assertEqual(root.tag, "{http://www.w3.org/2000/svg}svg")
                self.assertFalse(any(m in txt.lower() for m in MAROON), "maroon is chrome only")
                self.assertTrue(mapsvg.size_ok(txt))
                self.assertRegex(txt, r' d="M-?\d+ -?\d+l-?\d+')  # whole metres, relative l commands
        size = len((self.out / "poster/15068-roads.svg").read_bytes())
        self.assertTrue(150_000 < size < 420_000, size)
        poster = (self.out / "poster/15068-roads.svg").read_text()
        for s in ("NEW KENSINGTON · ARNOLD · LOWER BURRELL", "ZIP 15068 · 40.", "Map data © OpenStreetMap contributors, "
                  "Overture Maps Foundation · nk15068.com", ">ARNOLD<", ">LOWER BURRELL<", ">NEW KENSINGTON<"):
            self.assertIn(s, poster)

    def test_privacy_lists_every_key(self):
        h = self.page("/privacy/")
        for k in KEYS:
            self.assertIn(f"<code>{k}</code>", h, k)
        self.assertIn("This site shows no ads and sets no advertising cookies.", h)
        self.assertIn("Your coordinates are never sent to us or anyone else", h)
        self.assertIn('id="forget"', h)
        self.assertIn("Effective Sept. 23, 2026", h)

    def test_scripts_use_only_listed_keys(self):
        """Every nk-* key a script reads or writes in storage is one /privacy/ lists."""
        rx = re.compile(r'(?:\.(?:get|set|getItem|setItem|del|removeItem)|getJSONKey)\(\s*["\'](nk-[a-z-]+)["\']')
        used = set()
        for f in ("assets/app.js", "assets/pets.js", "assets/nkmap.js", "assets/safety.js", "assets/search.js"):
            p = self.out / f
            if p.exists():
                used |= set(rx.findall(p.read_text(encoding="utf-8")))
        self.assertEqual(sorted(used - set(KEYS)), [], "storage keys missing from /privacy/")

    def test_feed(self):
        root = ET.fromstring((self.out / "whats-new/feed.xml").read_text(encoding="utf-8"))
        self.assertEqual(root.tag, "rss")
        self.assertEqual(root.get("version"), "2.0")
        self.assertIsNotNone(root.find("channel/title"))
        self.assertIn('href="feed.xml"', self.page("/whats-new/"))

    def test_news(self):
        h = self.page("/news/")
        ids = re.findall(r'<article class="brief" id="(n-[^"]+)"', h)
        self.assertEqual(len(ids), len(T.news_items(self.D)))
        self.assertEqual(len(ids), len(set(ids)))
        for host in ("citizenportal.ai", "hoodline.com"):
            self.assertNotIn(host, h)
        older = [n for n in T.news_items(self.D) if T.months_between(n["date"], self.D["today"]) > 12]
        if older:
            self.assertIn(f"({len(older)})</summary>", h)
        tags = re.findall(r'<span class="new-tag"([^>]*)>', h)
        self.assertTrue(tags and all("hidden" in a for a in tags))  # "New to you" shows only with JS

    def test_history(self):
        h = self.page("/history/")
        self.assertEqual(h.count('class="tl-item"'), len(self.D["history"]["timeline"]))
        for a in ("#1769-1890", "#1891-1945", "#1946-1999", "#2000-today"):
            self.assertIn(f'href="{a}"', h)
        self.assertIn("aren&rsquo;t in our data yet.", h)
        self.assertNotIn("could not be retrieved", h)
        self.assertIn("history/people/", h.replace("../", ""))

    def test_people_and_eat(self):
        p = self.page("/history/people/")
        self.assertEqual(p.count('class="person"'), len(self.D["history"]["people"]))
        e = self.page("/eat/")
        self.assertEqual(e.count('class="dine"'), len(self.D["civic"]["food_and_culture"]))
        self.assertIn(f"{len(self.D['civic']['food_and_culture'])} restaurants, bars, bakeries and clubs", e)
        self.assertNotIn("Business listings can go stale", e)

    def test_trust_pages(self):
        a = self.page("/about/")
        self.assertIn("published by the GitHub account DonnieCash.", a)
        self.assertIn("Nothing here is paid placement.", a)
        c = self.page("/contact/")
        self.assertIn("https://github.com/DonnieCash/15068/issues", c)
        self.assertIn("template=correction.yml", c)
        self.assertNotIn("mailto:", c)  # no address until contact_email is set
        s = self.page("/sources/")
        self.assertIn('id="src-list"', s)
        self.assertIn("Outlets cited", s)
        nf = (self.out / "404.html").read_text()
        self.assertIn('<base href="/">', nf)
        self.assertIn('action="search/"', nf)
        self.assertIn('href="lost-pets/"', nf)

    def test_poster_page(self):
        h = self.page("/poster/")
        for s in ("Download the poster (SVG, prints at any size)", "Save a PNG (3600 × 4800)", "Your street poster",
                  "Make my poster", "The 3D version ›", 'href="15068-roads.svg"'):
            self.assertIn(s, h)


@needs_site
class WithAds(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.out = build("ads")

    def test_owner_and_ad_copy(self):
        self.assertIn("published by Test Owner.", html_of(self.out, "/about/"))
        p = html_of(self.out, "/privacy/")
        self.assertIn("Third-party vendors, including Google, use cookies", p)
        self.assertIn("Visitors in the EEA and UK are asked for consent first.", p)

    def test_town_slots_after_the_card(self):
        for s in TOWNS.values():
            t = html_of(self.out, f"/towns/{s}/")
            main = t[t.index("<main"):t.index("</main>")]
            first = main.find('class="adslot"')
            with self.subTest(town=s):
                self.assertGreater(first, main.index('id="call-city"'))
                self.assertNotIn("data-keep-above", main[first:])


class Changelog(unittest.TestCase):
    """--log on temporary copies (never the real data/ files)."""

    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        (self.tmp / "data").mkdir()
        self.D = load_D()
        self.D["root"] = self.tmp

    def test_first_entry_then_nothing(self):
        with contextlib.redirect_stdout(io.StringIO()):
            items = changelog.log(self.D, dt.date(2026, 9, 23))
            again = changelog.log(self.D, dt.date(2026, 9, 24))
        ents = json.loads((self.tmp / "data/changelog.json").read_text())
        self.assertEqual(ents[0]["date"], "2026-09-23")
        self.assertTrue(items[0].startswith("First edition on its own pages: "))
        if self.D["meta"]["stats"]["places"] == 1256 and len(self.D["safety"]["incidents"]) == 43:
            self.assertEqual(changelog.line(ents[0]),
                             "First edition on its own pages: 1,256 places, 790 streets and 19,242 buildings from "
                             "Overture Maps release 2026-08-19.0 · FBI figures through 2024 for all three departments "
                             "· 43 mapped incidents, newest July 2026 · 20 news briefs, newest Sept. 2026.")
        self.assertEqual(again, [])
        self.assertEqual(len(json.loads((self.tmp / "data/changelog.json").read_text())), 1)

    def test_diff_sentences(self):
        prev = changelog.digest(self.D)
        cur = copy.deepcopy(prev)
        cur["fbi"] = {t: y + 1 for t, y in prev["fbi"].items()}
        cur["news"]["n-a-new-brief"] = "2026-10"
        cur["incidents"]["2026-09-100-block-of-x"] = "2026-09"
        cur["release"] = "2026-10-01.0"
        items = changelog.diff(prev, cur)
        y = max(prev["fbi"].values()) + 1
        self.assertIn(f"FBI figures for {y} added", items)
        self.assertIn("1 new news brief, newest Oct. 2026", items)
        self.assertIn("1 new police blotter entry, newest Sept. 2026", items)
        self.assertTrue(any(i.startswith("Map data updated to Overture Maps release 2026-10-01.0") for i in items))
        self.assertEqual(changelog.diff(prev, copy.deepcopy(prev)), [])

    def test_append_merges_same_day(self):
        p = self.tmp / "data/changelog.json"
        changelog.append(dt.date(2026, 10, 1), ["a"], p)
        changelog.append(dt.date(2026, 10, 1), ["b", "a"], p)
        changelog.append(dt.date(2026, 10, 2), ["c"], p)
        self.assertEqual(json.loads(p.read_text()), [{"date": "2026-10-02", "items": ["c"]},
                                                     {"date": "2026-10-01", "items": ["a", "b"]}])

    def test_feed_and_page_with_entries(self):
        self.D["changelog"] = [{"date": "2026-10-03", "items": ["2 new news briefs, newest Oct. 2026"]},
                               {"date": "2026-01-02", "items": ["FBI figures for 2025 added"]}]
        root = ET.fromstring(changelog.feed_xml(self.D))
        self.assertEqual(len(root.findall("channel/item")), 2)
        self.assertEqual(root.find("channel/item/link").text, "https://nk15068.com/whats-new/#d-2026-10-03")
        D = dict(self.D, today=dt.date(2026, 10, 5))
        body = T.whats_new(D, route(self.D, "/whats-new/"))["body"]
        self.assertIn('id="d-2026-10-03"', body)
        self.assertIn("Older updates (1)", body)
        self.assertNotIn("Nothing has been logged here yet", body)
        D["changelog"] = []
        self.assertIn("Nothing has been logged here yet", T.whats_new(D, route(self.D, "/whats-new/"))["body"])


if __name__ == "__main__":
    unittest.main()
