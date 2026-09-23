"""The front page, /numbers/ and /calendar/: the calendar rules, the front-page caps, the research additions the calendar
reads, the phone-number anchors and tap-to-call coverage, and the word floors.

Run with the rest: NK_KEEP_GOING=1 python3 -m unittest tests.test_pages tests.test_pages_home
"""
import datetime as dt
import html
import json
import re
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))

from pagebuild import ROOT, build, html_of, main_words, parse  # noqa: E402

from nkpages import calendar as C  # noqa: E402
from nkpages import data as ND  # noqa: E402
from nkpages import fmt  # noqa: E402
from nkpages import pages_home as H  # noqa: E402

TODAY = dt.date(2026, 9, 23)


def load_D(today=TODAY):
    cfg = json.loads((ROOT / "data/site.json").read_text())
    return ND.load(cfg, today)


def flat(page):
    t = re.sub(r"<(script|style|template)\b.*?</\1>", " ", page, flags=re.S)
    t = html.unescape(re.sub(r"<[^>]+>", " ", t))
    return re.sub(r"\s+", " ", t)


def main_of(page):
    return page[page.index("<main"):page.index("</main>")]


def outside_template(page):
    return re.sub(r"<template\b.*?</template>", " ", page, flags=re.S)


class ResearchAdditions(unittest.TestCase):
    """The dated fields the calendar reads exist and each item keeps its source."""

    @classmethod
    def setUpClass(cls):
        cls.history = json.loads((ROOT / "data/research/history.json").read_text())
        cls.civic = json.loads((ROOT / "data/research/civic.json").read_text())

    def test_research_additions(self):
        fof = next(e for e in self.history["events"] if e["name"] == "Fridays on Fifth")
        self.assertTrue(fof.get("dates"))
        for d in fof["dates"]:
            dt.date.fromisoformat(d)
        self.assertTrue(fof.get("time"))
        self.assertTrue(fof.get("source", "").startswith("https://"))
        arnold = next(g for g in self.civic["government"] if g["name"].startswith("City of Arnold"))
        self.assertEqual(C.parse_rule(arnold["council"]["rule"]), (2, 1))
        self.assertTrue(arnold["council"].get("source", "").startswith("https://"))
        prt = next(n for n in self.civic["news_2025_2026"] if n["headline"].startswith("PRT proposes"))
        dt.date.fromisoformat(prt["deadline"])
        self.assertTrue(prt.get("source", "").startswith("https://"))


class Calendar(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.D = load_D()
        cls.items = C.occurrences(cls.D, TODAY)

    def test_nth_weekday(self):
        self.assertEqual(C.nth_weekday(2026, 10, 2, 1), dt.date(2026, 10, 13))
        self.assertEqual(C.nth_weekday(2026, 9, 4, 4), dt.date(2026, 9, 25))
        self.assertEqual(C.nth_weekday(2026, 9, -1, 4), dt.date(2026, 9, 25))
        self.assertEqual(C.nth_weekday(2026, 12, -1, 6), dt.date(2026, 12, 27))
        self.assertIsNone(C.nth_weekday(2026, 2, 5, 1))
        self.assertEqual(C.parse_rule("2nd Tuesday"), (2, 1))
        self.assertIsNone(C.parse_rule("second Tuesday after the primary"))

    def test_calendar(self):
        first = self.items[:3]
        self.assertEqual([i["date"] for i in first], ["2026-09-25", "2026-09-30", "2026-10-13"])
        self.assertEqual([fmt.ap_day(i["date"]) for i in first], ["Fri., Sept. 25", "Wed., Sept. 30", "Tues., Oct. 13"])
        self.assertEqual([i["kind"] for i in first], ["explicit", "deadline", "rule"])
        self.assertEqual(first[0]["title"], "Fridays on Fifth")
        self.assertIn("PRT", first[1]["title"])
        self.assertIn("comments", first[1]["what"] + " " + first[1]["label"])
        self.assertEqual(first[2]["title"], "Arnold City Council")
        self.assertIn("(expected)", first[2]["label"])
        for i in self.items:
            self.assertTrue(i["source"], i["title"])
            for k in ("date", "time", "title", "where", "text", "source", "kind", "id", "label"):
                self.assertIn(k, i)
        dated = [i["date"] for i in self.items if i["date"]]
        self.assertEqual(dated, sorted(dated))
        self.assertTrue(all(i["date"] is None for i in self.items[len(dated):]), "yearly items come last")
        ids = [i["id"] for i in self.items]
        self.assertEqual(len(ids), len(set(ids)))

    def test_yearly_order_and_rollover(self):
        yearly = [i for i in self.items if i["kind"] == "when"]
        self.assertEqual(yearly[0]["title"], "City of New Kensington Christmas Parade")  # December is next after Sept.
        self.assertEqual(C.month_of("Summer"), 6)
        self.assertEqual(C.month_of("Summer (June)"), 6)
        self.assertEqual(C.month_of("Mid-March (the weekend before St. Patrick's Day), 11 a.m."), 3)
        after = C.occurrences(load_D(dt.date(2026, 10, 24)), dt.date(2026, 10, 24))
        fof = [i for i in after if i["title"] == "Fridays on Fifth"]
        self.assertEqual(len(fof), 1)
        self.assertEqual(fof[0]["kind"], "when")
        self.assertIn("2027 dates not announced yet.", fof[0]["text"])

    def test_ics_and_jsonld_only_for_listed_dates(self):
        for i in self.items:
            ics = C.ics_data(i)
            if i["kind"] in ("explicit", "deadline"):
                self.assertTrue(ics)
            else:
                self.assertIsNone(ics, i["id"])
        fof = C.ics_data(self.items[0])
        self.assertEqual((fof["s"], fof["e"]), ("20260925T170000", "20260925T210000"))  # floating local time
        prt = C.ics_data(self.items[1])
        self.assertEqual((prt["d"], prt["e"]), ("20260930", "20261001"))  # all-day
        ev = C.event_jsonld(self.items[0], "https://nk15068.com/calendar/#fridays-on-fifth")
        self.assertEqual(ev["startDate"], "2026-09-25T17:00:00-04:00")

    def test_times_and_addresses(self):
        self.assertEqual(C.parse_time("5–9 p.m."), ((17, 0), (21, 0)))
        self.assertEqual(C.parse_time("7 p.m."), ((19, 0), None))
        self.assertEqual(C.parse_time("11 a.m.–1 p.m."), ((11, 0), (13, 0)))
        self.assertEqual(C.ap_addr("1829 Fifth Ave, Arnold, PA 15068"), "1829 Fifth Ave.")
        self.assertEqual(C.ap_addr("1021 Puckety Church Rd, Lower Burrell, PA 15068"), "1021 Puckety Church Road")
        self.assertEqual(H.ap_hours("M–F 8:30–4:30, Sat 9:30–1"), "Mon.–Fri. 8:30 a.m.–4:30 p.m., Sat. 9:30 a.m.–1 p.m.")


class HomePages(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.out = build("default")
        cls.D = load_D()
        cls.home = html_of(cls.out, "/")
        cls.numbers = html_of(cls.out, "/numbers/")
        cls.cal = html_of(cls.out, "/calendar/")

    def test_front_caps(self):
        for out in (self.out, build("snapshot")):
            t = html_of(out, "/")
            box = re.search(r'<section id="pets-box".*?</section>', t, re.S).group(0)
            self.assertLessEqual(box.count('class="listing-row"'), 3)
            self.assertLessEqual(outside_template(t).count('class="cal-row"'), 3)
            latest = re.search(r'<section class="home-sec" id="latest".*?</section>', t, re.S).group(0)
            self.assertLessEqual(latest.count("<li"), 3)
        tpl = re.search(r'<template id="cal-more">(.*?)</template>', self.home, re.S)
        self.assertTrue(tpl)
        self.assertLessEqual(tpl.group(1).count('class="cal-row"'), 6)
        snap = html_of(build("snapshot"), "/")
        self.assertIn('class="listing-row"', snap, "the snapshot build lists posts in the pets box")

    def test_home_order_and_rows(self):
        m = main_of(self.home)
        order = [m.index(s) for s in ('id="pets-box"', 'class="sitesearch home-search', "<h1", 'id="nums"',
                                      'id="crime-lead"', 'id="latest"', 'id="inside"')]
        self.assertEqual(order, sorted(order))
        rows = re.findall(r'<li class="cal-row".*?</li>', outside_template(m), re.S)
        text = [flat(r) for r in rows]
        self.assertIn("Fri., Sept. 25", text[0])
        self.assertIn("This Friday", text[0])
        self.assertIn("Fridays on Fifth", text[0])
        self.assertIn("5–9 p.m. · Fifth Avenue between Ninth and 11th streets, New Kensington", text[0])
        self.assertIn("Wed., Sept. 30", text[1])
        self.assertRegex(text[1], r"PRT .*comments")
        self.assertIn("Tues., Oct. 13", text[2])
        self.assertIn("Arnold City Council (expected)", text[2])
        self.assertIn("As of Wednesday, Sept. 23", flat(m))
        self.assertIn('href="calendar/#fridays-on-fifth"', rows[0])

    def test_home_numbers_module(self):
        nums = re.search(r'<section class="nums".*?</section>', self.home, re.S).group(0)
        self.assertIn("data-keep-above", nums)
        tels = re.findall(r'<a class="tel[^"]*" href="(tel:[^"]+)"', nums)
        self.assertEqual(tels, ["tel:911", "tel:+17243397533", "tel:+17243399663", "tel:+17243394287",
                                "tel:+17246007300", "tel:+17243397388"])
        self.assertEqual(nums.count('class="tel primary"'), 1)
        for s in ("Numbers to keep", "Emergency", "Police, non-emergency", "After hours · County non-emergency line",
                  "Animal shelter · Animal Protectors, 730 Church St.", "City halls, library, schools and more numbers ›"):
            self.assertIn(s, flat(nums))
        self.assertIn('href="numbers/"', nums)

    def test_home_locator_latest_changes(self):
        m = main_of(self.home)
        self.assertRegex(m, r'<picture class="themed"><source media="\(prefers-color-scheme: dark\)" '
                            r'srcset="img/15068-locator-dark.svg"><img src="img/15068-locator.svg"')
        latest = re.search(r'<section class="home-sec" id="latest".*?</section>', m, re.S).group(0)
        ids = re.findall(r'href="news/#(n-[^"]+)"', latest)
        self.assertEqual(len(ids), 3)
        want = [H.news_id(n) for n in H.news_items(self.D)[:3]]
        self.assertEqual(ids, want)
        news = self.out / "news" / "index.html"
        if news.exists():  # the towns builder's page: every Latest anchor must land on an item there
            t = news.read_text(encoding="utf-8")
            for i in ids:
                self.assertIn(f'id="{i}"', t)
        self.assertIn(f"All {len(H.news_items(self.D))} news briefs ›", flat(m))
        ch = re.search(r'<script type="application/json" id="changes">(.*?)</script>', self.home, re.S)
        self.assertIsInstance(json.loads(ch.group(1)), list)
        for u in ("crime/new-kensington/", "crime/arnold/", "crime/lower-burrell/"):
            self.assertIn(f'href="{u}"', m)

    def test_home_loads_no_map_data(self):
        srcs = re.findall(r'<script src="([^"]+)"', self.home)
        self.assertEqual([s.rsplit("/", 1)[-1] for s in srcs], ["pubs.js", "pets.js", "app.js"])
        for f in ("roads.json", "streets.json", "places.json", "base.json", "safety.json", "meta.json"):
            self.assertNotIn(f, main_of(self.home))

    def test_numbers_anchors_and_tels(self):
        for a in ("new-kensington", "arnold", "lower-burrell", "county"):
            self.assertIn(f'id="{a}"', self.numbers)
        self.assertIn("data-keep-above", re.search(r'<div class="nine11".*?</div>', self.numbers, re.S).group(0))
        self.assertIn('href="tel:911"', self.numbers)
        hrefs = set(re.findall(r'href="(tel:[^"]+)"', self.numbers))
        rows = H.numbers_rows(self.D)
        self.assertGreaterEqual(len(rows), 20)
        for r in rows:
            with self.subTest(row=r["n"]):
                self.assertTrue(r["source"], "every row credits a source")
                self.assertIn(r["t"], ("New Kensington", "Arnold", "Lower Burrell", "County"))
                self.assertRegex(r["u"], r"^numbers/#(new-kensington|arnold|lower-burrell|county)$")
                for ph in r["ph"]:
                    self.assertIn(fmt.tel(ph)[0][1], hrefs)
        by_n = {r["n"]: r for r in rows}
        self.assertEqual(by_n["Arnold police, non-emergency"]["ph"], ["724-339-9663", "724-339-9078"])
        self.assertEqual(by_n["New Kensington City Hall"]["ph"], ["724-337-4523"])
        self.assertIn("Mon.–Fri. 8:30 a.m.–4:30 p.m., Sat. 9:30 a.m.–1 p.m.", flat(self.numbers))
        self.assertIn("Next expected: Tuesday, Oct. 13", flat(self.numbers))
        self.assertIn("No public number listed", flat(self.numbers))
        self.assertIn(H.GAP_LINE, flat(self.numbers).replace("’", "'"))
        for s in ("Emergency? Call 911", "Tap a number to call.", "Remember my town", "Print this list"):
            self.assertIn(s, self.numbers)
        # every row credits an outlet by name
        self.assertEqual(self.numbers.count('<li class="nrow">'), len(rows))
        self.assertEqual(len(re.findall(r'<li class="nrow">.*?Source: <a class="cr"', self.numbers, re.S)), len(rows))

    def test_calendar_page(self):
        m = main_of(self.cal)
        heads = re.findall(r'<h2 id="[^"]+">(.*?)</h2>', m)
        self.assertEqual(heads, ["Next 7 days", "Later this month", "Coming up", "Every year", "Public meetings"])
        self.assertIn("As of Wednesday, Sept. 23, 2026. Dates marked expected follow a regular schedule; check before you go.",
                      flat(m))
        items = C.occurrences(self.D, TODAY)
        listed = [i for i in items if i["kind"] in ("explicit", "deadline") and f'id="{i["id"]}"' in m]
        self.assertEqual(m.count("data-ics="), len(listed))
        for a in re.findall(r'<article class="cal-item[^"]*" id="[^"]+"[^>]*data-kind="rule".*?</article>', m, re.S):
            self.assertNotIn("data-ics", a)
            self.assertIn("(expected)", flat(a))
        lds = [json.loads(x) for x in re.findall(r'<script type="application/ld\+json">(.*?)</script>', self.cal)]
        events = [x for x in lds if x.get("@type") == "Event"]
        self.assertEqual(len(events), len(listed))
        self.assertIn('id="fridays-on-fifth"', m)
        self.assertIn("aren’t in our data yet", html.unescape(m))
        self.assertEqual(len(re.findall(r"p\.m\.\.", flat(m))), 0)

    def test_word_floors(self):
        self.assertGreaterEqual(main_words(self.home), 200)
        self.assertGreaterEqual(main_words(self.numbers), 300)
        self.assertGreaterEqual(main_words(self.cal), 300)

    def test_one_h1(self):
        self.assertEqual(parse(self.home).h1, ["This week in 15068"])
        self.assertEqual(len(parse(self.numbers).h1), 1)
        self.assertEqual(parse(self.cal).h1, ["Coming up in 15068"])


if __name__ == "__main__":
    unittest.main()
