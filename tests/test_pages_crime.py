"""Crime pages: /crime/, the three department pages, /crime/blotter/ and /crashes/, plus the sentence rules they use.

Numbers are asserted against values computed from site/data/safety.json; the exact section-6 copy is asserted only
while the data is the one the spec was written against (latest FBI year 2024; crash stats summing to 150).
"""
import datetime
import html
import json
import re
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))

from pagebuild import ROOT, build, html_of, main_words  # noqa: E402

from nkpages import data as ND  # noqa: E402
from nkpages import fmt  # noqa: E402
from nkpages import sentences as S  # noqa: E402

DEPTS = ["/crime/new-kensington/", "/crime/arnold/", "/crime/lower-burrell/"]
CRIME_PAGES = ["/crime/"] + DEPTS + ["/crime/blotter/", "/crashes/"]

SHORT = {
    "New Kensington": "New Kensington police reported 54 violent crimes to the FBI in 2024, or 4.6 per 1,000 residents, "
                      "up from 40 (3.4 per 1,000) in 2023. That is the city's highest rate since 2019 (5.3). Property "
                      "crime rose to 24.0 per 1,000 from 21.2, still lower than any year from 2001 through 2019. Police "
                      "cleared 32 of the 54 violent crimes.",
    "Arnold": "Arnold police reported 39 violent crimes in the 9 months of 2024 they sent to the FBI, about 4.3 a month, "
              "up from about 2.2 a month in 2022 (22 in 10 months). Arnold sent no figures for 2023. The 2024 count "
              "works out to 8.4 per 1,000 residents, the city's highest rate since 2018 (9.7), and with three months "
              "missing the full-year number can only be higher. Police cleared 8 of the 39.",
    "Lower Burrell": "Lower Burrell police reported 10 violent crimes to the FBI in 2024, or 0.9 per 1,000 residents, down "
                     "from 17 in the 11 months of 2023 it reported (about 1.5 a month). That is the lowest rate since 2018 "
                     "(0.8). Property crime fell to 2.3 per 1,000, the lowest in the department's FBI record, which goes "
                     "back to 2000. Police cleared all 10 violent crimes.",
}
HEADLINE = "Violent crime rose in New Kensington and Arnold in 2024 and fell in Lower Burrell"
ROWS = [("New Kensington", "Up", "54 in 2024 (4.6 per 1,000), from 40 in 2023 (3.4)"),
        ("Arnold", "Up", "39 in 9 months of 2024 (about 4.3 a month), from 22 in 10 months of 2022 (about 2.2 a month)"),
        ("Lower Burrell", "Down", "10 in 2024 (0.9 per 1,000), from 17 in 11 months of 2023 (about 1.5 a month)")]


def flat(page):
    t = re.sub(r"<(script|style|template)\b.*?</\1>", " ", page, flags=re.S)
    t = html.unescape(re.sub(r"<[^>]+>", "", t))
    return re.sub(r"\s+", " ", t)


def load_D():
    cfg = json.loads((ROOT / "data/site.json").read_text())
    return ND.load(cfg, datetime.date(2026, 9, 23))


class Sentences(unittest.TestCase):
    """The comparison rules in spec 1c, on made-up agencies."""

    def ag(self, years):
        return {"agency": "Test Police Department", "municipality": "Test", "years": years}

    def y(self, year, violent, months=12, pop=10000, **kw):
        return {"year": year, "violent": violent, "months_reported": months, "population": pop, **kw}

    def test_about_the_same_band(self):
        a, b = self.y(2024, 54), self.y(2023, 50)
        self.assertEqual(S.direction(a, b), "same")  # +8%
        self.assertEqual(S.direction(self.y(2024, 56), b), "up")  # +12%
        self.assertEqual(S.direction(self.y(2024, 44), b), "down")  # -12%

    def test_partial_years_compare_monthly_averages(self):
        # 30 in 6 months (5 a month) against 48 in 12 (4 a month) is up, though the count fell
        self.assertEqual(S.direction(self.y(2024, 30, months=6), self.y(2023, 48)), "up")
        self.assertEqual(S.direction(self.y(2024, 24, months=6), self.y(2023, 48)), "same")

    def test_highest_and_lowest_since(self):
        ag = self.ag([self.y(2018, 60), self.y(2019, 30), self.y(2020, 40), self.y(2021, 50)])
        last = ag["years"][-1]
        self.assertEqual(S.since(ag, "violent", last, True)[0]["year"], 2018)
        self.assertEqual(S.since(ag, "violent", last, False)[0]["year"], 2020)
        top = self.ag([self.y(2019, 30), self.y(2020, 40), self.y(2021, 50)])
        self.assertIsNone(S.since(top, "violent", top["years"][-1], True))

    def test_small_number_note_and_words(self):
        self.assertIn("a few incidents can move a rate a lot", S.SMALL_NOTE)
        self.assertEqual(S.spell(16), "sixteen")
        self.assertEqual(S.lead_num(44), "Forty-four")
        self.assertEqual(S.join_and(["a", "b", "c"]), "a, b and c")


class CrimeData(unittest.TestCase):
    """Cross-builder functions, against the committed data."""

    @classmethod
    def setUpClass(cls):
        cls.D = load_D()

    def test_home_rows_shape(self):
        rows = S.home_crime_rows(self.D)
        self.assertEqual([r["town"] for r in rows], list(ND.CORE_TOWNS))
        for r in rows:
            self.assertIn(r["word"], ("Up", "Down", "About the same"))
            self.assertEqual(r["slug"], ND.TOWN_SLUGS[r["town"]])
            self.assertTrue(r["text"])
        self.assertTrue(S.home_crime_headline(rows).startswith("Violent crime "))

    def test_police_numbers_come_from_pets_json(self):
        nums = S.police_numbers(self.D)
        items = [i for i in self.D["pets"]["items"] if i.get("kind") == "police"]
        for t in ND.CORE_TOWNS:
            it = next(i for i in items if i["name"].startswith(t))
            self.assertEqual([nums[t]["primary"]] + nums[t]["alt"], [s for s, _ in fmt.tel(it["phone"])])
            self.assertEqual(nums[t]["source"], it["source"])

    def test_incident_counts(self):
        inc = self.D["safety"]["incidents"]
        for t in ND.CORE_TOWNS:
            mine = [i for i in inc if i["t"] == t]
            self.assertEqual(S.incident_counts(self.D, t), {"n": len(mine), "first_year": min(int(i["d"][:4]) for i in mine)})

    def test_crash_town_sentence(self):
        for t in ND.CORE_TOWNS:
            tot = S.crash_totals(self.D, t)
            s = S.crash_town_sentence(self.D, t)
            self.assertIn(f"PennDOT recorded {tot['crashes']} crash", s)
            self.assertIn(t, s)
        if S.crash_totals(self.D, "Arnold") == {"crashes": 7, "fatal": 0, "serious": 8}:
            self.assertEqual(S.crash_town_sentence(self.D, "Arnold"),
                             "PennDOT recorded 7 crashes in Arnold from 2005 through 2024 that seriously injured someone, "
                             "8 people in all. None killed anyone.")

    def test_crash_snapping(self):
        pts = self.D["safety"]["crashes"]["points"]
        snapped = S.snap_crashes(self.D)
        self.assertEqual(len(snapped), len(pts))
        roads = S.crash_roads(self.D)
        self.assertEqual(sum(r["n"] for r in roads), sum(1 for _, r in snapped if r))
        self.assertEqual(roads, sorted(roads, key=lambda r: (-r["n"], -r["killed"], r["road"])))


class SafetyJSParity(unittest.TestCase):
    """site/assets/safety.js incIds and streetKey agree with nkpages.fmt (skipped without node)."""

    def test_ids_and_street_keys(self):
        import shutil
        import subprocess
        node = shutil.which("node")
        if not node:
            self.skipTest("node is not installed")
        inc = json.loads((ROOT / "site/data/safety.json").read_text())["incidents"]
        extra = [{"d": "2026-01", "l": "Café Renée Drive"}, {"d": "2026-01", "l": "Café Renée Drive"}, {"l": "  "}]
        names = ["Fifth Avenue", "5th Ave", "N. Leishman Ave.", "Seventh Street Road", "Freeport Rd", "Cherry Alley",
                 "East 9th St", "Route 56", "", "Terrace"]
        js = ("const vm=require('vm');const fs=require('fs');const ctx={window:{},console};vm.createContext(ctx);"
              "vm.runInContext(fs.readFileSync(process.argv[1],'utf8'),ctx);const S=ctx.window.NKSafety;"
              "const inp=JSON.parse(fs.readFileSync(0,'utf8'));"
              "process.stdout.write(JSON.stringify({ids:S.incIds(inp.inc),keys:inp.names.map(S.streetKey)}));")
        r = subprocess.run([node, "-e", js, str(ROOT / "site/assets/safety.js")], input=json.dumps({"inc": inc + extra, "names": names}),
                           capture_output=True, text=True, timeout=60)
        self.assertEqual(r.returncode, 0, r.stderr)
        got = json.loads(r.stdout)
        self.assertEqual(got["ids"], fmt.inc_ids(inc + extra))
        self.assertEqual(got["keys"], [fmt.street_key(n) for n in names])
        for k in ("CAT", "TYPE", "PREC", "monthName", "wirePanels", "enhanceCharts", "enhanceBlotter", "incIds"):
            self.assertIn(k, (ROOT / "site/assets/safety.js").read_text())


class CrimePages(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.out = build("default")
        cls.D = load_D()
        cls.pages = {}
        for p in CRIME_PAGES:
            f = cls.out / (p.lstrip("/") + "index.html")
            if f.exists():
                cls.pages[p] = f.read_text(encoding="utf-8")

    def page(self, p):
        if p not in self.pages:
            self.skipTest(f"{p} not built")
        return self.pages[p]

    def test_all_built(self):
        self.assertEqual(sorted(self.pages), sorted(CRIME_PAGES))

    def test_crime_copy(self):
        last = max(y["year"] for a in self.D["safety"]["fbi"]["agencies"] for y in S.series(a))
        if last != 2024:
            self.skipTest("the section-6 copy was written for FBI figures through 2024")
        hub = flat(self.page("/crime/"))
        for t, s in SHORT.items():
            self.assertEqual(S.short_answer(self.D, t), html.escape(s, quote=False))
            self.assertIn(s, hub, t)
        rows = S.home_crime_rows(self.D)
        self.assertEqual([(r["town"], r["word"], html.unescape(r["text"])) for r in rows], ROWS)
        self.assertEqual(S.home_crime_headline(rows), HEADLINE)
        for (t, w, text), dept in zip(ROWS, DEPTS):
            self.assertIn(SHORT[t], flat(self.page(dept)))
        home = self.out / "index.html"
        if home.exists():
            h = flat(home.read_text(encoding="utf-8"))
            self.assertIn(HEADLINE, h)
            for t, w, text in ROWS:
                self.assertRegex(h, re.escape(t) + r"\W+" + re.escape(w) + r"\W+" + re.escape(text))

    def test_crash_copy(self):
        st = self.D["safety"]["crashes"]["stats"]
        if sum(r["crashes"] for r in st) != 150:
            self.skipTest("the crash copy was written for 150 crashes")
        t = flat(self.page("/crashes/"))
        for s in ("150 crashes", "73 in Lower Burrell, 70 in New Kensington and 7 in Arnold",
                  "killed 38 people and seriously injured 145", "Leechburg Road (16)",
                  "From 2020 through 2024 there were 44 such crashes, which killed 7 people.",
                  "Sixteen of the mapped crashes hit a pedestrian; those crashes killed 3 people."):
            self.assertIn(s, t)
        # the road analysis uses the mapped points; the totals come from crashes.stats (G1)
        pts = self.D["safety"]["crashes"]["points"]
        matched = sum(1 for _, r in S.snap_crashes(self.D) if r)
        self.assertIn(f"Of the {len(pts)} crashes with a mapped location, {matched} were matched to a named road; "
                      f"{len(pts) - matched} couldn't be matched to a named road within 100 feet.", t)
        for r in S.crash_roads(self.D)[:8]:
            self.assertIn(r["road"].rsplit(" ", 1)[0], t)

    def test_crash_totals_from_stats(self):
        st = self.D["safety"]["crashes"]["stats"]
        t = flat(self.page("/crashes/"))
        self.assertIn(f"PennDOT recorded {fmt.num(sum(r['crashes'] for r in st))} crashes", t)
        self.assertIn(f"They killed {fmt.num(sum(r['fatal'] for r in st))} people", t)

    def test_blotter_ids(self):
        b = self.page("/crime/blotter/")
        ids = re.findall(r'<article class="entry" id="inc-([^"]+)" data-id="([^"]+)"', b)
        self.assertTrue(ids)
        self.assertTrue(all(a == c for a, c in ids))
        got = [a for a, _ in ids]
        self.assertEqual(len(got), len(set(got)), "duplicate incident ids")
        inc = self.D["safety"]["incidents"]
        self.assertEqual(sorted(got), sorted(fmt.inc_ids(inc)))
        self.assertEqual(len(got), len(inc))
        # every entry has the attributes the filters read
        for attrs in re.findall(r'<article class="entry"([^>]*)>', b):
            for k in ("data-c", "data-t", "data-yr", "data-st", "data-mx", "data-my"):
                self.assertIn(k + "=", attrs)
        # no collapsing, no "show more"
        self.assertNotIn("inc-more", b)
        self.assertNotRegex(flat(b), r"(?i)show (\d+ )?more")

    def test_blotter_leishman(self):
        b = self.page("/crime/blotter/")
        sts = re.findall(r'<article class="entry"[^>]*data-st="([^"]*)"', b)
        hits = [s for s in sts if "leishman" in s.split("|")]
        inc = self.D["safety"]["incidents"]
        want = [i for i in inc if re.search(r"\bLeishman\b", i["l"])]
        self.assertEqual(len(hits), len(want))
        if len(inc) == 43:
            self.assertEqual(len(hits), 6)
            towns = re.findall(r'<article class="entry"[^>]*data-t="([^"]*)"[^>]*data-st="(?:[^"]*\|)?leishman(?:\|[^"]*)?"', b)
            self.assertEqual(sorted(towns), ["Arnold"] * 3 + ["New Kensington"] * 3)

    def test_blotter_markup(self):
        b = self.page("/crime/blotter/")
        for needle in ('id="inc-filters"', 'id="inc-town"', 'id="inc-year"', 'id="inc-street"',
                       'placeholder="A street, like Leishman"', "Include incidents within a block (400 ft)",
                       'id="inc-count"', 'id="inc-map"', 'id="inc-list"', "Show these on the map ›",
                       "incidents with a mappable location"):
            self.assertIn(needle, b)
        years = sorted({i["d"][:4] for i in self.D["safety"]["incidents"]}, reverse=True)
        self.assertEqual(re.findall(r'<h2 class="yr-h"[^>]*>(\d{4})</h2>', b), years)
        merged = S.merged_incident_ids(self.D)
        for iid, town in merged.items():
            block = re.search(rf'<article class="entry" id="inc-{re.escape(iid)}".*?</article>', b, re.S).group(0)
            self.assertIn(f"on the {town} crime page ›", block)

    def test_keep_above(self):
        for p in ["/crime/"] + DEPTS:
            t = self.page(p)
            main = t[t.index("<main"):t.index("</main>")]
            m = re.search(r"<div [^>]*data-keep-above[^>]*>.*?</div>\s*(?:<p class=\"credit\">.*?</p>)?</div>", main, re.S)
            self.assertTrue(m, p)
            self.assertIn('href="tel:911"', m.group(0), p)
            self.assertRegex(m.group(0), r'href="tel:\+1\d{10}"')
            # the keep-above block comes before the first section heading
            self.assertLess(main.index("data-keep-above"), main.index("<h2"))
        for p in DEPTS:
            town = ND.SLUG_TOWNS[p.split("/")[2]]
            nums = S.police_numbers(self.D)[town]
            t = self.page(p)
            for n in [nums["primary"]] + nums["alt"]:
                self.assertIn(f'href="{fmt.tel(n)[0][1]}"', t)
            pol = S.police(self.D, town)
            if pol.get("chief"):
                self.assertIn(f"Chief {pol['chief']}", flat(t))
            else:
                self.assertNotIn("Chief ", flat(t)[:2000])

    def test_dataset_jsonld(self):
        for p in ["/crime/"] + DEPTS + ["/crashes/"]:
            t = self.page(p)
            lds = [json.loads(m) for m in re.findall(r'<script type="application/ld\+json">(.*?)</script>', t, re.S)]
            ds = [o for o in lds if o.get("@type") == "Dataset"]
            self.assertEqual(len(ds), 1, p)
            d = ds[0]
            self.assertTrue(d["isAccessibleForFree"])
            self.assertRegex(d["temporalCoverage"], r"^\d{4}/\d{4}$")
            self.assertTrue(d["name"] and d["description"])
            src = " ".join(d["isBasedOn"])
            self.assertIn("bencarneiro/ntsb" if p == "/crashes/" else "jacobkap/crimedatatool_helper", src)
        self.assertFalse([m for m in re.findall(r'"@type":"Dataset"', self.page("/crime/blotter/"))])

    def test_ad_markers_and_words(self):
        # word floors (the site-wide test covers them too), measured without JS
        floors = {"/crime/": 300, "/crashes/": 400, **{p: 400 for p in DEPTS}}
        for p, n in floors.items():
            self.assertGreaterEqual(main_words(self.page(p)), n, p)
        self.assertGreater(main_words(self.page("/crime/blotter/")), 1000)

    def test_ad_slots_placed(self):
        out = build("ads")
        for p in ["/crime/"] + DEPTS + ["/crashes/"]:
            t = html_of(out, p)
            self.assertEqual(t.count('class="adslot"'), 2, p)
        self.assertEqual(html_of(out, "/crime/blotter/").count("adslot"), 0)

    def test_no_officers_oct31_claim(self):
        for p in DEPTS:
            self.assertNotIn("Oct. 31", flat(self.page(p)))

    def test_interactions_merged_once(self):
        """An interaction and an incident with the same (date, municipality, kind) appear once on the department
        page, crediting both sources."""
        for it, inc, iid in S.merged_interactions(self.D):
            if not inc:
                continue
            p = f"/crime/{ND.TOWN_SLUGS[it['municipality']]}/"
            t = self.page(p)
            police = t[t.index('id="police"'):t.index('id="incidents"')]
            self.assertIn(fmt.pub_name(inc["src"]), flat(police))
            self.assertIn(fmt.pub_name(it["source"]), flat(police))
            incs = t[t.index('id="incidents"'):t.index('id="crashes"')]
            self.assertNotIn(f'id="inc-{iid}"', incs)

    def test_privacy(self):
        """No house numbers in incident text (hundred-blocks only), no sexual-offense incidents, no private names."""
        house = re.compile(r"\b(\d{2,5})\s+(?:[NSEW]\.?\s+)?(?:\d+(?:st|nd|rd|th)|[A-Z][a-z]+)\s+"
                           r"(?:Street|St|Avenue|Ave|Road|Rd|Drive|Dr|Boulevard|Blvd|Lane|Ln|Way|Court|Ct|Alley|Place|Pl)\b")
        for p in CRIME_PAGES:
            for block in re.findall(r'<article class="entry".*?</article>', self.page(p), re.S):
                for n in house.findall(re.sub(r"<[^>]+>", " ", block)):
                    self.assertEqual(int(n) % 100, 0, p)
        b = self.page("/crime/blotter/")
        self.assertNotRegex(b, r'data-(?:k|c)="(?:sexual_assault|rape|sex_offense)"')

    def test_no_internal_text(self):
        for p in CRIME_PAGES:
            t = flat(self.page(p))
            self.assertNotRegex(t, r"(?i)\bverify\b|crimedatatool|not re-confirmed|month approximate")
            self.assertNotIn(self.D["safety"]["fbi"]["method"][:60], t)


if __name__ == "__main__":
    unittest.main()
