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
# with the town's street names: text -> what strip_house must leave (the JS port must agree character for character)
HOUSE_STREETS = {
    "Got out of our yard at 412 Leishman": "Got out of our yard at Leishman",
    "Seen at 1605 Victoria near the school": "Seen at Victoria near the school",
    "house 1507 on Kenneth": "house on Kenneth",
    "at 412 Garvers Ferry Road": "at Garvers Ferry Road",
    "1450 Old Greensburg Road": "Old Greensburg Road",
    "88 Pleasant Valley Rd": "Pleasant Valley Rd",
    "near 3210 Logans Ferry Rd": "near Logans Ferry Rd",
    "1025-1027 Leechburg Rd": "Leechburg Rd",
    "12–14 Freeport Road": "Freeport Road",
    "at 1012 11th Street": "at 11th Street",
    "Biscuit (412 Leishman)": "Biscuit (Leishman)",
    "#412 Leishman": "Leishman",
    "12B Main St": "Main St",
    "1605 victoria": "victoria",
    "PA 366 at 1200 Leechburg Rd": "PA 366 at Leechburg Rd",
    "Seen by 400 Main St\nand 12 N. Oak Lane": "Seen by Main St\nand N. Oak Lane",
    # never damaged: counts, ages, routes, ordinals, hundred-blocks, phone numbers, times and dates
    "Lost 2 dogs on Freeport Rd": "Lost 2 dogs on Freeport Rd",
    "3 years old": "3 years old",
    "Route 56": "Route 56",
    "Route 56 Freeport Road": "Route 56 Freeport Road",
    "5th Ave": "5th Ave",
    "11th Street": "11th Street",
    "the 100 block of Freeport Rd": "the 100 block of Freeport Rd",
    "Has 2 white paws": "Has 2 white paws",
    "Weighs 15 lbs, 3 years old, 11th St kid": "Weighs 15 lbs, 3 years old, 11th St kid",
    "Text 724 339 7388 Mary": "Text 724 339 7388 Mary",
    "(724) 339-7388 Kenneth": "(724) 339-7388 Kenneth",
    "724.339.7388 Victoria": "724.339.7388 Victoria",
    "Call 724-339-7388": "Call 724-339-7388",
    "at 7:30 on Leishman": "at 7:30 on Leishman",
    "since 9/20 on Kenneth": "since 9/20 on Kenneth",
    "2 Mile Run Road": "2 Mile Run Road",
}
DAYS = ["2026-09-20", "2026-09-31", "2026-02-30", "2024-02-29", "2026-02-29", "0000-01-01", "0001-01-01", "2026-13-01",
        "2026-00-10", "2026-09-20\n", " 2026-09-20", "9999-12-31", "2026-9-20", "", None, 20260920]
TIMES = ["2026-09-21T14:00:00Z", "2026-09-23T13:15:00.000Z", "2026-02-30T10:00:00Z", "2026-09-22T24:00:00Z",
         "2026-09-22T10:60:00Z", "2026-09-22T10:00Z", "0000-01-01T00:00:00Z", "2026-09-22T10:00:00.5Z", "2026-09-22", None]
# fixture issues (and posts below) whose free text carries these house numbers; none may be published
HOUSE_NUMBERS = ("1605", "3210", "1450", "1012", "1025", "412", "1507", "4120")


def node():
    return shutil.which("node")


def town_data():
    """The street list and road-line names the board uses, for both ports: (keys, JS setIndex() input)."""
    from nkpages import data as ND
    D = {"meta": ND.read_json(ND.SITE / "data/meta.json"), "roads": ND.read_json(ND.SITE / "data/roads.json")}
    lines = ND.lines(D)
    streets = ND.read_json(ND.SITE / "data/streets.json", [])
    return P.street_keys(streets, P.build_index(lines)), {
        "lines": [{"n": ln["n"], "pts": [0, 0]} for ln in lines if ln.get("n")], "streets": streets}


def has_house(text):
    """Any of HOUSE_NUMBERS standing alone in text (not inside a longer number such as a phone number)."""
    return [n for n in HOUSE_NUMBERS if re.search(rf"(?<![\d-]){n}(?![\d-])", text)]


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

    def test_house_numbers_before_street_names(self):
        """Both ports strip a house number when the words after it name a real street, with or without a street
        type ("412 Leishman", "1507 on Kenneth", "88 Pleasant Valley Rd"), and keep counts, routes and ordinals."""
        keys, idx = town_data()
        cases = list(HOUSE_STREETS)
        py = [P.strip_house(t, keys) for t in cases]
        self.assertEqual(dict(zip(cases, py)), HOUSE_STREETS)
        js = self.js("(P.setIndex(input.idx), input.cases.map(t => P.stripHouse(t)))", {"idx": idx, "cases": cases})
        self.assertEqual(js, py)

    def test_sanitize_strips_every_free_text_field(self):
        """name, desc and contact all go through strip_house, in both ports, and the result carries no house number."""
        keys, idx = town_data()
        posts = [{"id": "gh-20", "status": "lost", "name": "Biscuit of 412 Leishman", "near": "Fifth Ave & 11th St",
                  "desc": "Got out at 1507 on Kenneth. Also seen at 88 Pleasant Valley Rd and 1605 Victoria near the school.",
                  "contact": "Call 724-339-7388 or stop by 1450 Old Greensburg Road", "date": "2026-09-20"},
                 {"id": "gh-21", "status": "found", "name": "Tag: 3210 Logans Ferry Rd", "desc": "at 412 Garvers Ferry Road",
                  "contact": "near 4120 Leishman", "date": "2026-09-31", "created": "2026-02-30T10:00:00Z"}]
        py = [P.sanitize(p, "github", keys=keys) for p in posts]
        js = self.js("(P.setIndex(input.idx), input.posts.map(p => P.sanitize(p, 'github')))", {"idx": idx, "posts": posts})
        self.assertEqual(js, py)
        self.assertEqual(py[0]["name"], "Biscuit of Leishman")
        self.assertEqual(py[1]["name"], "Tag: Logans Ferry Rd")
        self.assertIn("724-339-7388", py[0]["contact"], "phone numbers stay")
        for p in py:
            for k in ("name", "desc", "contact"):
                self.assertEqual(has_house(p[k]), [], f"{p['id']} {k}: {p[k]!r}")
        self.assertEqual((py[1]["date"], py[1]["created"]), ("", ""), "impossible dates are dropped")

    def test_real_dates(self):
        """Only real calendar days survive sanitize (2026-09-31, 2026-02-30 and 0000-01-01 are dropped), in both ports."""
        self.assertEqual(self.js("input.map(d => P.realDay(d))", DAYS), [P.real_day(d) for d in DAYS])
        self.assertEqual(self.js("input.map(t => P.realTime(t))", TIMES), [P.real_time(t) for t in TIMES])
        self.assertEqual([d for d in DAYS if P.real_day(d)], ["2026-09-20", "2024-02-29", "0001-01-01", "9999-12-31"])
        posts = [{"status": "lost", "date": d} for d in DAYS] + [{"status": "lost", "created": t} for t in TIMES]
        self.assertEqual(self.js("input.map(p => P.sanitize(p, 'github'))", posts), [P.sanitize(p, "github") for p in posts])
        for d in ("2026-09-31", "2026-02-30", "0000-01-01"):
            self.assertEqual(P.sanitize({"status": "lost", "date": d}, "github")["date"], "")
        today = __import__("datetime").date(2026, 9, 23)
        self.assertEqual(P.short_date("2026-09-31", today), "")
        self.assertEqual(P.date_line({"status": "lost", "date": "2026-02-30"}, today), "")
        self.assertEqual(P.checked("2026-02-30T10:00:00Z", today), "")

    def test_street_key_parity(self):
        names = ["Fifth Avenue", "5th Ave", "N. 3rd St.", "Leechburg Rd", "East Tenth Street", "Route 56", "", "Seventh Street Road"]
        self.assertEqual(self.js("input.map(n => P.streetKey(n))", names), [P.street_key(n) for n in names])


class Network(unittest.TestCase):
    """pets.js gives up on a stalled request after 8 s, and init() sets the geocoding index before any network wait."""

    def run_node(self, body):
        if not node():
            self.skipTest("node is not installed")
        code = ("const vm=require('vm'),fs=require('fs');const asked=[];const waits=[];let signals=[];"
                "const fast=(f,ms)=>{waits.push(ms);return setTimeout(f,Math.min(ms,30));};"
                "const hang=(url,opts={})=>{asked.push(url);if(opts.signal)signals.push(opts.signal);"
                "return new Promise((ok,no)=>{if(opts.signal)opts.signal.addEventListener('abort',()=>no(new Error('aborted')));});};"
                "const make=(fetch,extra={})=>{const ctx={window:{...extra},fetch,setTimeout:fast,clearTimeout,AbortController,console};"
                "vm.createContext(ctx);"
                f"vm.runInContext(fs.readFileSync({json.dumps(str(ROOT / 'site/assets/pets.js'))},'utf8'),ctx);"
                "return ctx.window.NKPets;};"
                "const lines=[{n:'Fifth Avenue',pts:[0,0,100,0]},{n:'11th Street',pts:[50,-50,50,50]}];"
                "const done=(o)=>process.stdout.write(JSON.stringify(o));" + body)
        r = subprocess.run([node(), "-e", code], capture_output=True, text=True, timeout=30)
        self.assertEqual(r.returncode, 0, r.stderr)
        return json.loads(r.stdout)

    def test_stalled_github_gives_up(self):
        r = self.run_node(
            "const P=make(hang);const t=Date.now();"
            "const p=P.init({lines,streets:[{n:'Leishman Avenue',x:0,y:0,t:[]}]});"
            "const idx=P.board.idx?P.board.idx.size:0;"  # synchronously, before any network wait
            "const g=P.geocodeNear('Fifth Avenue & 11th Street','New Kensington');"
            "p.then(()=>done({idx,g,state:P.board.state,ms:Date.now()-t,asked,waits,aborted:signals.map(s=>s.aborted)}));")
        self.assertEqual(r["idx"], 2)
        self.assertEqual(r["g"]["prec"], "intersection", "geocoding works before the board answers")
        self.assertEqual(r["state"], "unknown", "a stalled API with no snapshot is 'unknown', never empty or loading")
        self.assertTrue(any("api.github.com" in u for u in r["asked"]))
        self.assertIn(8000, r["waits"])
        self.assertTrue(r["aborted"] and all(r["aborted"]), "the stalled requests are aborted")

    def test_stalled_github_falls_back_to_stale_snapshot(self):
        board = json.loads((FIX / "pets-board.json").read_text())
        board["fetched"] = "2026-01-01T00:00:00Z"
        r = self.run_node(
            f"const snap={json.dumps(board)};"
            "const f=(url,opts={})=>/pets-board/.test(url)?Promise.resolve({ok:true,status:200,json:()=>Promise.resolve(snap)}):hang(url,opts);"
            "const P=make(f);P.loadBoard().then(()=>done({state:P.board.state,n:P.board.posts.length,asked}));")
        self.assertEqual((r["state"], r["n"]), ("stale", 2))

    def test_ensure_index_does_not_wait_for_the_board(self):
        r = self.run_node(
            "const f=(url,opts={})=>/streets\\.json/.test(url)?Promise.resolve({ok:true,status:200,json:()=>Promise.resolve([])}):hang(url,opts);"
            "const P=make(f,{NK:{loadLines:()=>Promise.resolve(lines)}});"
            "P.ensureIndex().then((idx)=>done({size:idx.size,state:P.board.state,asked}));")
        self.assertEqual(r["size"], 2)
        self.assertEqual(r["state"], "loading", "ensureIndex never starts or awaits the board")
        self.assertFalse([u for u in r["asked"] if "github" in u or "pets-board" in u])


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
        self.assertEqual(has_house(json.dumps(got)), [], "no house number in the snapshot")
        self.assertEqual(dog["desc"], "Small brown and white beagle mix, red collar, very friendly. "
                                      "Got out of our yard at Victoria near the school.")
        self.assertEqual(cat["name"], "Smokey (Logans Ferry Rd)")
        self.assertEqual(cat["contact"], "Animal Protectors, 724-339-7388, or stop by Old Greensburg Road")
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
        self.assertEqual(parse(cat).h1, ["Found cat: Smokey (Logans Ferry Rd)"], "the house number is gone from the name")
        self.assertIn('<meta property="og:title" content="FOUND CAT: Smokey (Logans Ferry Rd), near Leechburg Road, '
                      'Lower Burrell">', cat)
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
        for t in P.TOWNS:
            sec = P.town_section(D, town, t)
            self.assertNotIn("tel:", sec, "the town section sits below ads, so it carries no phone number")
            self.assertIn('<a class="act" href="../../lost-pets/">What to do first ›</a>', sec)

    def test_town_pages_pets_section(self):
        """On the built town pages the pets section has no tap-to-call button (every pets contact comes before ads)."""
        for slug in ("new-kensington", "arnold", "lower-burrell"):
            for out in (self.default, self.snap):
                t = self.page(out, f"/towns/{slug}/")
                m = re.search(rf'<section class="sec pets-town" id="pets-{slug}".*?</section>', t, re.S)
                self.assertTrue(m, slug)
                self.assertNotIn("tel:", m.group(0))
                self.assertIn("What to do first ›", m.group(0))

    def test_long_words_wrap(self):
        """A pasted URL can't push a listing card, a compact row or the flyer sideways: the grids get a shrinkable
        column and the free text wraps anywhere (checked in a browser at 390 px too)."""
        css = (ROOT / "site/assets/css/30-pets.css").read_text()
        rule = lambda sel: re.search(rf"(?m)^{re.escape(sel)} \{{([^}}]*)\}}", css).group(1)  # noqa: E731
        self.assertIn("grid-template-columns: minmax(0, 1fr)", rule(".listing"))
        self.assertIn("grid-template-columns: minmax(0, 1fr)", rule(".flyer"))
        self.assertIn("grid-template-columns: minmax(0, 1fr)", rule(".lpg"))
        self.assertIn("overflow-wrap: anywhere", rule(".listing h3, .listing-desc, .listing-near"))
        self.assertIn("overflow-wrap: anywhere", rule(".fl-q, .fl-desc, .fl-seen"))
        self.assertIn("overflow-wrap: anywhere", rule(".listing-row a"))

    def test_no_house_numbers_published(self):
        """The fixture issues put house numbers in a name, a description and a contact; none reaches a gh-N page
        (title, h1, og:title, card), the feed, the board, the snapshot file or the rows on the home and town pages."""
        raw = json.dumps(ISSUES)
        for n in ("1605", "3210", "1450"):
            self.assertIn(n, raw, "the fixture must carry the house numbers this test looks for")
        files = list(self.snap.glob("lost-pets/**/index.html")) + [self.snap / "lost-pets/feed.xml", self.snap / "data/pets-board.json",
                                                                   self.snap / "index.html", self.snap / "towns/lower-burrell/index.html",
                                                                   self.snap / "towns/new-kensington/index.html"]
        self.assertTrue((self.snap / "lost-pets/gh-7/index.html").exists() and (self.snap / "lost-pets/gh-8/index.html").exists())
        for f in files:
            t = f.read_text(encoding="utf-8")
            if f.suffix == ".html":
                head = t[:t.index("</head>")]
                t = " ".join(re.findall(r"<title>.*?</title>|<meta [^>]*>", head)) + t[t.index("<main"):t.index("</main>")]
            self.assertEqual(has_house(t), [], f"house number in {f.relative_to(self.snap)}")
        cat = self.page(self.snap, "/lost-pets/gh-8/")
        self.assertIn("<title>Found cat: Smokey (Logans Ferry Rd), near Leechburg Road · NK15068</title>", cat)
        self.assertIn("or stop by Old Greensburg Road", cat)
        self.assertIn("Got out of our yard at Victoria near the school.", self.page(self.snap, "/lost-pets/gh-7/"))

    def test_bad_snapshot_never_fails_the_build(self):
        """A snapshot post with an impossible date, or house numbers the old stripping missed, still builds: the date
        is dropped and the numbers are stripped when the build re-sanitizes the board."""
        board = json.loads((FIX / "pets-board.json").read_text())
        bad = [dict(board["posts"][1], id="gh-31", date="2026-09-31", name="Rex of 412 Leishman",
                    desc="Got out of our yard at 412 Leishman. Seen at 1605 Victoria near the school, house 1507 on Kenneth.",
                    contact="Owner at 88 Pleasant Valley Rd, 724-339-7388", url="https://github.com/DonnieCash/15068/issues/31"),
               dict(board["posts"][0], id="gh-32", date="2026-02-30", created="2026-02-30T10:00:00Z", name="Tag: 3210 Logans Ferry Rd",
                    contact="at 412 Garvers Ferry Road or 1450 Old Greensburg Road", url="https://github.com/DonnieCash/15068/issues/32"),
               dict(board["posts"][0], id="gh-33", date="0000-01-01", created="0000-01-01T00:00:00Z", name="",
                    url="https://github.com/DonnieCash/15068/issues/33")]
        with tempfile.TemporaryDirectory() as d:
            src = Path(d) / "board.json"
            src.write_text(json.dumps({"fetched": board["fetched"], "posts": board["posts"] + bad}))
            out = Path(d) / "out"
            r = subprocess.run([sys.executable, str(ROOT / "scripts/build_pages.py"), "--today", "2026-09-23", "--out", str(out),
                                "--snapshot", "--board", str(src)], capture_output=True, text=True)
            self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
            for pid in ("gh-31", "gh-32", "gh-33"):
                t = (out / f"lost-pets/{pid}/index.html").read_text(encoding="utf-8")
                main = t[t.index("<main"):t.index("</main>")]
                if pid == "gh-31":  # a bad date falls back to the (real) posting date
                    self.assertIn('<p class="listing-date">Lost Mon., Sept. 21 ', main)
                else:
                    self.assertNotIn('class="listing-date"', main, f"{pid} shows no date")
                    self.assertNotIn("Posted", main)
                self.assertEqual(has_house(t[:t.index("</head>")] + main), [], pid)
            feed = (out / "lost-pets/feed.xml").read_text()
            self.assertEqual(feed.count("<item>"), 5)
            self.assertEqual(has_house(feed), [])
            self.assertIn("Rex of Leishman", feed)
            lp = (out / "lost-pets/index.html").read_text(encoding="utf-8")
            self.assertEqual(has_house(lp[lp.index("<main"):lp.index("</main>")]), [])

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
