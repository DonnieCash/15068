"""The lost & found pets pages: JS/Python parity of the issue parser, the snapshot, the board states and the
Call now card.

    python -m unittest tests.test_pages_pets
"""
import json
import re
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))

from pagebuild import FIX, ROOT, build, html_of, main_words, parse  # noqa: E402

from nkpages import pets as P  # noqa: E402

ISSUES = json.loads((FIX / "pet_issues.json").read_text(encoding="utf-8"))
NEAR_CASES = ["1025-1027 Leechburg Rd", "1012 Fifth Avenue & 11th Street", "Route 56 & 1012 5th Ave",
              "PA 366 near 12B Main St", "the 1000 block of Fifth Ave", " ,& 9th St & 5th Ave,, ", "SR 780 at 2400 Leechburg",
              "Fifth Ave\u2009& 9th St", "12–14 Freeport Road", ""]
HOUSE_CASES = ["found at 1012 Fifth Ave near the park", "Call 724-339-7388", "Route 56 Freeport Road",
               "Seen by 400 Main St\nand 12 N. Oak Lane", "2 Mile Run Road", "Answers to Biscuit"]


def node():
    return shutil.which("node")


def run_js(expr_js):
    """Load site/assets/pets.js in a bare vm context with window = {} and print JSON of expr_js."""
    code = ("const vm=require('vm'),fs=require('fs');const ctx={window:{}};vm.createContext(ctx);"
            f"vm.runInContext(fs.readFileSync({json.dumps(str(ROOT / 'site/assets/pets.js'))},'utf8'),ctx);"
            "const P=ctx.window.NKPets;const input=JSON.parse(fs.readFileSync(0,'utf8'));"
            f"process.stdout.write(JSON.stringify({expr_js}));")
    return code


class Parity(unittest.TestCase):
    def js(self, expr, data):
        if not node():
            self.skipTest("node is not installed")
        r = subprocess.run([node(), "-e", run_js(expr)], input=json.dumps(data), capture_output=True, text=True)
        self.assertEqual(r.returncode, 0, r.stderr)
        return json.loads(r.stdout)

    def test_pets_parity(self):
        """pets.js and nkpages.pets agree on parseIssue and cleanNear for the fixture issues."""
        js = self.js("input.map(i => P.parseIssue(i))", ISSUES)
        py = [P.parse_issue(i) for i in ISSUES]
        self.assertEqual(js, py)
        near = [re.search(r"### Last seen near\n+([^\n]*)", i.get("body") or "") for i in ISSUES]
        texts = [m.group(1) for m in near if m] + NEAR_CASES
        self.assertEqual(self.js("input.map(t => P.cleanNear(t))", texts), [P.clean_near(t) for t in texts])
        self.assertEqual(self.js("input.map(t => P.stripHouse(t))", HOUSE_CASES), [P.strip_house(t) for t in HOUSE_CASES])

    def test_sanitize_parity(self):
        posts = json.loads((FIX / "pets-board.json").read_text())["posts"]
        odd = [{"status": "lost", "x": 12.5, "y": -15, "prec": "bogus", "placeLabel": " ", "animal": "DOG", "town": "Plum",
                "date": "2026-09-20\n", "url": "https://github.com/DonnieCash/15068/issues/7/x"},
               {"status": ["lost"]}, None, {"status": "found", "x": 1e9, "y": 0, "desc": "at 1012 Fifth Ave"}]
        data = posts + odd
        self.assertEqual(self.js("input.map(p => P.sanitize(p, 'github'))", data), [P.sanitize(p, "github") for p in data])

    def test_street_key_parity(self):
        names = ["Fifth Avenue", "5th Ave", "N. 3rd St.", "Leechburg Rd", "East Tenth Street", "Route 56", "", "Seventh Street Road"]
        self.assertEqual(self.js("input.map(n => P.streetKey(n))", names), [P.street_key(n) for n in names])


class Parser(unittest.TestCase):
    def test_fixture_shape(self):
        posts = [P.parse_issue(i) for i in ISSUES]
        self.assertIsNone(posts[2], "a pull request is not a post")
        self.assertEqual(posts[0]["near"], "Fifth Avenue & 11th Street", "the house number 1012 must be stripped")
        self.assertEqual(posts[4]["near"], "Leechburg Rd", "a house-number range must be stripped")
        self.assertFalse(P.is_pet_issue(ISSUES[3]), "an issue without the form is not a listing")
        self.assertFalse(P.is_pet_issue(ISSUES[2]))


class Snapshot(unittest.TestCase):
    def test_snapshot_script_matches_fixture(self):
        """scripts/snapshot_pets.py writes 2 posts from the fixture, identical to tests/fixtures/pets-board.json."""
        with tempfile.TemporaryDirectory() as d:
            out = Path(d) / "board.json"
            r = subprocess.run([sys.executable, str(ROOT / "scripts/snapshot_pets.py"), "--issues", str(FIX / "pet_issues.json"),
                                "--fetched", "2026-09-23T13:15:00Z", "--out", str(out)], capture_output=True, text=True)
            self.assertEqual(r.returncode, 0, r.stderr)
            got = json.loads(out.read_text())
        self.assertEqual(got, json.loads((FIX / "pets-board.json").read_text()))
        posts = {p["id"]: p for p in got["posts"]}
        self.assertEqual(sorted(posts), ["gh-7", "gh-8"])
        dog, cat = posts["gh-7"], posts["gh-8"]
        self.assertNotIn("1012", json.dumps(dog))
        self.assertEqual(dog["prec"], "intersection")
        self.assertEqual(P.street_key(dog["placeLabel"].split(" & ")[0])["core"], "5")
        self.assertEqual(dog["placeLabel"], "5th Avenue & 11th Street")
        self.assertEqual((cat["prec"], cat["placeLabel"]), ("street", "Leechburg Road"))

    def test_snapshot_never_fails(self):
        with tempfile.TemporaryDirectory() as d:
            out = Path(d) / "board.json"
            r = subprocess.run([sys.executable, str(ROOT / "scripts/snapshot_pets.py"), "--issues", str(Path(d) / "missing.json"),
                                "--out", str(out)], capture_output=True, text=True)
            self.assertEqual(r.returncode, 0)
            self.assertFalse(out.exists())
            self.assertIn("warning", r.stderr)


def text_of(html):
    return " ".join(parse(html).main_text)


class Pages(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.default = build("default")
        cls.snap = build("snapshot")

    def page(self, out, route):
        p = out / route.lstrip("/") / "index.html"
        if not p.exists():
            self.skipTest(f"{route} not built")
        return p.read_text(encoding="utf-8")

    def test_default_build_has_no_listings(self):
        t = self.page(self.default, "/lost-pets/")
        self.assertNotIn("No open listings", t)
        self.assertNotIn("Nothing is posted", t)
        self.assertNotIn('class="listing"', t)
        self.assertNotIn("nk-pets-snapshot", t, "no snapshot marker, so pets.js never asks for a missing file")
        self.assertFalse(list(self.default.glob("lost-pets/gh-*")))
        self.assertFalse((self.default / "lost-pets/feed.xml").exists())
        self.assertIn("The board shows live listings when JavaScript is on", text_of(t))

    def test_snapshot_renders_both_posts(self):
        t = self.page(self.snap, "/lost-pets/")
        self.assertIn('id="gh-7"', t)
        self.assertIn('id="gh-8"', t)
        txt = text_of(t)
        self.assertNotIn("1012", txt)
        self.assertIn("Last seen near Fifth Avenue & 11th Street, New Kensington", txt)
        self.assertIn("Found near Leechburg Road, Lower Burrell (no cross street given)", txt)
        self.assertIn("The board: 2 open listings, newest Sept. 22.", txt)
        self.assertIn("Board checked 9:15 a.m.", txt)
        self.assertIn('href="../map/?pet=gh-7"', t)
        self.assertIn('href="../lost-pets/flyer/?pet=gh-7"', t)
        self.assertIn('<meta name="nk-pets-snapshot" content="2026-09-23T13:15:00Z">', t)
        self.assertIn('href="feed.xml"', t)

    def test_listing_pages(self):
        t = self.page(self.snap, "/lost-pets/gh-7/")
        p = parse(t)
        self.assertEqual(p.h1, ["Lost dog: Biscuit"])
        self.assertIn('<meta property="og:title" content="LOST DOG: Biscuit, near Fifth Avenue &amp; 11th Street, New Kensington">', t)
        self.assertIn('<meta name="robots" content="noindex">', t)
        self.assertIn("<title>Lost dog: Biscuit, near Fifth Avenue &amp; 11th Street · NK15068</title>", t)
        self.assertIn('href="../../map/?pet=gh-7"', t)
        self.assertIn("data-keep-above", t)
        cat = self.page(self.snap, "/lost-pets/gh-8/")
        self.assertEqual(parse(cat).h1, ["Found cat"])
        self.assertIn('href="tel:+17243394287"', cat, "the Lower Burrell listing shows Lower Burrell police")
        feed = (self.snap / "lost-pets/feed.xml").read_text()
        self.assertEqual(feed.count("<item>"), 2)
        self.assertIn("<link>https://nk15068.com/lost-pets/gh-7/</link>", feed)

    def test_snapshot_links_resolve(self):
        """Links inside the lost-pets pages resolve (the site-wide test covers the rest of the default build)."""
        for route in ("/lost-pets/", "/lost-pets/gh-7/", "/lost-pets/gh-8/"):
            t = self.page(self.snap, route)
            base = self.snap / route.lstrip("/")
            for u in parse(t[t.index("<main"):t.index("</main>")]).links:
                if re.match(r"^(https?:|mailto:|tel:|#|data:)", u) or not u:
                    continue
                u = u.split("#")[0].split("?")[0]
                if not u:
                    continue
                tgt = (base / u).resolve()
                if u.endswith("/") or tgt.is_dir():
                    tgt = tgt / "index.html"
                if "lost-pets" in tgt.as_posix() or tgt.suffix == ".xml":
                    self.assertTrue(tgt.exists(), f"{route} links to missing {u}")

    def test_call_now_card(self):
        for out in (self.default, self.snap):
            t = self.page(out, "/lost-pets/")
            m = re.search(r'<aside id="call-now".*?</aside>', t, re.S)
            self.assertTrue(m, "no Call now card")
            card = m.group(0)
            self.assertIn("data-keep-above", card)
            main = t[t.index("<main"):]
            self.assertLess(main.index('id="call-now"'), main.index('id="board"'), "Call now comes before the board")
            tels = re.findall(r'<a class="tel[^"]*" href="(tel:[^"]+)"', card)
            for n in ("tel:+17243397388", "tel:+17243397533", "tel:+17243399663", "tel:+17243394287", "tel:+17244685505",
                      "tel:+17246007300", "tel:+17248321073", "tel:+14123734200"):
                self.assertIn(n, tels)
            self.assertLess(tels.index("tel:+17243397388"), tels.index("tel:+17243397533"), "the shelter is first")
            self.assertRegex(card, r'data-town="Lower Burrell"><div class="cn-top"><b class="cn-name">Hoffman Kennels')
            self.assertIn("Call 724-339-7388", card)
            self.assertIn("If your pet is missing, call these today.", card)
            self.assertIn("Pennsylvania law says to call police, animal control or the dog warden", card)
            self.assertIn("State dog law office, weekdays 8 a.m.–4 p.m.", card)
            self.assertIn('class="picker" role="group" aria-label="Your town" hidden', card, "the picker needs JS")
            self.assertIn("Sources:", card)

    def test_page_copy(self):
        t = self.page(self.default, "/lost-pets/")
        txt = text_of(t)
        for s in ("Call these first. Then check the board and post your pet.", "I lost a pet", "I found a pet",
                  "If your pet is missing: the first 48 hours", "If you found a pet",
                  "Call Animal Protectors and your town’s police non-emergency line.",
                  "Also useful: licenses, microchips, cats and more ›", "It’s free and takes two minutes.",
                  "Contacts and tips from", "Checked Sept. 23, 2026"):
            self.assertIn(s, txt)
        self.assertIn('id="pets-tips"', t)
        self.assertIn('id="found-steps"', t)
        self.assertIn('<a class="seg" href="#lost"', t)
        self.assertGreaterEqual(main_words(t), 400)
        post = self.page(self.default, "/lost-pets/post/")
        for label in ("Lost, found or spotted?", "Animal", "Pet’s name (if known)", "Description", "Last seen near", "Town",
                      "Date", "How to reach you (public)", "Photo (for the flyer only)"):
            self.assertIn(label, text_of(post))
        self.assertIn("Nothing you type here leaves your phone until you choose where to post it.", text_of(post))
        self.assertNotIn("Email it to NK15068 instead", post, "only when contact_email is set")
        fl = self.page(self.default, "/lost-pets/flyer/")
        self.assertEqual(parse(fl).h1, ["Lost pet flyer"])
        self.assertIn("nk15068.com/lost-pets/", text_of(fl))

    def test_home_box_and_town_section_states(self):
        import datetime as dt
        from nkpages import data as ND
        from nkpages import routes as NR
        cfg = json.loads((ROOT / "data/site.json").read_text())
        home = NR.ROUTES[0]
        town = next(r for r in NR.ROUTES if r.path == "/towns/arnold/")
        D = ND.load(cfg, dt.date(2026, 9, 23))
        box = P.home_box(D, home)
        self.assertIn('id="pets-box"', box)
        self.assertIn("The board shows live listings when JavaScript is on.", box)
        self.assertNotIn("No open listings", box)
        D = ND.load(cfg, dt.date(2026, 9, 23), snapshot=True, board=FIX / "pets-board.json")
        box = P.home_box(D, home)
        self.assertEqual(box.count('class="listing-row"'), 2)
        self.assertIn("2 open", box)
        self.assertIn('href="lost-pets/#gh-8"', box)
        self.assertIn("Grey tabby, no collar, taken to Animal Protectors.", box)
        self.assertIn("Leechburg Road, Lower Burrell · Sept. 22", box)
        D["board"] = dict(D["board"], posts=D["board"]["posts"] * 3)
        D.pop("_pets_open", None)
        self.assertEqual(P.home_box(D, home).count('class="listing-row"'), 3, "at most 3 rows")
        D["board"] = {"fetched": "2026-09-23T13:15:00Z", "posts": []}
        D.pop("_pets_open", None)
        empty = P.home_box(D, home)
        self.assertIn("No open listings on the board right now (checked 9:15 a.m.).", empty)
        self.assertIn('href="tel:+17243397388"', empty)
        D = ND.load(cfg, dt.date(2026, 9, 23), snapshot=True, board=FIX / "pets-board.json")
        sec = P.town_section(D, town, "Lower Burrell")
        self.assertIn("Lost and found pets in Lower Burrell", sec)
        self.assertIn('data-pets-town="Lower Burrell"', sec)
        self.assertEqual(sec.count('class="listing-row"'), 1)
        self.assertIn('href="../../lost-pets/#board"', sec)
        self.assertEqual(P.town_section(D, town, "Arnold").count('class="listing-row"'), 0)

    def test_privacy(self):
        house = re.compile(r"\b(\d{2,5})\s+(?:[NSEW]\.?\s+)?(?:\d+(?:st|nd|rd|th)|[A-Z][a-z]+)\s+"
                           r"(?:Street|St|Avenue|Ave|Road|Rd|Drive|Dr|Boulevard|Blvd|Lane|Ln|Way|Court|Ct|Alley|Place|Pl)\b")
        for p in list(self.snap.glob("lost-pets/**/index.html")) + [self.snap / "lost-pets/feed.xml",
                                                                    self.snap / "data/pets-board.json"]:
            t = p.read_text(encoding="utf-8")
            for b in re.findall(r'<(?:article|li|div) class="listing\b.*?</(?:article|li|div)>', t, re.S) + [t]:
                if "listing" not in b[:40] and p.suffix == ".html":
                    continue
                for n in house.findall(re.sub(r"<[^>]+>", " ", b)):
                    self.assertEqual(int(n) % 100, 0, f"house number in {p}")
            self.assertNotIn("1012", t)
            self.assertNotIn("1025", t)


if __name__ == "__main__":
    unittest.main()
