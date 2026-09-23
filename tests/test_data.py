"""Sanity checks for the NK15068 pipeline and the shipped site data.

    python -m unittest discover -s tests
"""
import json
import struct
import sys
import unittest
import zlib
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))
DATA = ROOT / "site" / "data"


def dec(arr, q):
    out, x, y = [], 0, 0
    for i in range(0, len(arr), 2):
        x += arr[i]
        y += arr[i + 1]
        out.append((x / q, y / q))
    return out


class Encoding(unittest.TestCase):
    def test_roundtrip_within_quantum(self):
        import build_data as b
        pts = [(-79.7647, 40.5695), (-79.7640, 40.5701), (-79.7612, 40.5713)]
        back = dec(b.enc(pts), b.Q)
        for (lon, lat), (x, y) in zip(pts, back):
            ex, ey = b.proj(lon, lat)
            self.assertLess(abs(ex - x), 0.2)
            self.assertLess(abs(ey - y), 0.2)

    def test_projection_inverse(self):
        import build_data as b
        lon, lat = b.unproj(*b.proj(-79.73, 40.58))
        self.assertAlmostEqual(lon, -79.73, places=9)
        self.assertAlmostEqual(lat, 40.58, places=9)

    def test_grouping(self):
        import build_data as b
        tx = lambda *h: {"taxonomy": {"hierarchy": list(h)}}
        self.assertEqual(b.group_of(tx("food_and_drink", "restaurant")), "eat")
        self.assertEqual(b.group_of(tx("cultural_and_historic", "place_of_worship")), "faith")
        self.assertEqual(b.group_of(tx("cultural_and_historic", "historic_site")), "culture")
        self.assertIsNone(b.group_of({}))


@unittest.skipUnless((DATA / "meta.json").exists(), "site data not built")
class SiteData(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.meta = json.loads((DATA / "meta.json").read_text())

    def test_core_towns_present(self):
        names = {t["n"] for t in self.meta["towns"] if t["core"]}
        self.assertEqual(names, {"New Kensington", "Arnold", "Lower Burrell"})

    def test_counts_plausible(self):
        s = self.meta["stats"]
        self.assertGreater(s["buildings"], 10000)
        self.assertGreater(s["places"], 500)
        self.assertGreater(s["streets"], 300)
        self.assertTrue(200 <= s["elev_min_m"] <= 240, "Allegheny pool is ~221 m")

    def test_places_inside_bounds_and_grouped(self):
        places = json.loads((DATA / "places.json").read_text())
        x0, y0, x1, y1 = self.meta["bounds"]
        for p in places:
            self.assertIn(p["g"], self.meta["groups"])
            self.assertTrue(x0 <= p["x"] <= x1 and y0 <= p["y"] <= y1, p["n"])
            if "ph" in p:
                self.assertRegex(p["ph"], r"^\d{3}-\d{3}-\d{4}$")

    def test_terrain_png(self):
        t = self.meta["terrain"]
        raw = (DATA / "terrain.png").read_bytes()
        self.assertEqual(raw[:8], b"\x89PNG\r\n\x1a\n")
        w, h = struct.unpack(">II", raw[16:24])
        self.assertEqual((w, h), (t["w"], t["h"]))
        idat = raw[raw.index(b"IDAT") + 4:raw.index(b"IEND") - 8]
        rows = zlib.decompress(idat)
        for j in (0, h // 2, h - 1):
            line = rows[j * (w * 3 + 1) + 1:(j + 1) * (w * 3 + 1)]
            for i in range(0, w, 50):
                d = line[i * 3] * 256 + line[i * 3 + 1]
                self.assertTrue(1900 <= d <= 5200, d)

    def test_buildings_arrays_align(self):
        b = json.loads((DATA / "buildings.json").read_text())
        self.assertEqual(len(b["h"]), len(b["p"]))
        self.assertEqual(len(b["k"]), len(b["p"]))

    def test_research_has_sources(self):
        for name in ("history.json", "civic.json"):
            d = json.loads((DATA / name).read_text())
            for key, items in d.items():
                if isinstance(items, list):
                    for it in items:
                        self.assertTrue(it.get("source") or it.get("url"), f"{name}:{key}:{it}")


@unittest.skipUnless((DATA / "safety.json").exists(), "safety data not built")
class SafetyData(unittest.TestCase):
    """Privacy + integrity rules for the crime/policing layer."""

    @classmethod
    def setUpClass(cls):
        cls.s = json.loads((DATA / "safety.json").read_text())
        cls.meta = json.loads((DATA / "meta.json").read_text())

    def test_incidents_are_sourced_located_and_coarse(self):
        import re
        x0, y0, x1, y1 = self.meta["bounds"]
        house = re.compile(r"\b(\d{2,5})\s+(?:[NSEW]\.?\s+)?(?:\d+(?:st|nd|rd|th)|[A-Z][a-z]+)\s+"
                           r"(?:Street|St|Avenue|Ave|Road|Rd|Drive|Dr|Boulevard|Blvd|Lane|Ln|Way|Court|Ct|Alley|Place|Pl)\b")
        for i in self.s["incidents"]:
            self.assertTrue(i["src"].startswith("http"), i)
            self.assertIn(i["c"], {"violent", "property", "police"})
            self.assertIn(i["p"], {"block", "intersection", "place", "street"})
            self.assertNotIn(i["k"], {"sexual_assault", "rape", "sex_offense"})
            self.assertTrue(x0 <= i["x"] <= x1 and y0 <= i["y"] <= y1, i["l"])
            self.assertRegex(i["d"], r"^20\d\d-\d\d(-\d\d)?$")
            m = re.match(r"^(\d+) block of ", i["l"])
            if m:
                self.assertEqual(int(m.group(1)) % 100, 0, i["l"])
            else:
                self.assertFalse(re.match(r"^\d+\s", i["l"]), f"exact address leaked: {i['l']}")
            for n in house.findall(i["s"]):
                self.assertEqual(int(n) % 100, 0, f"house number in summary: {i['s']}")

    def test_no_titles_or_raw_coordinates_ship(self):
        for i in self.s["incidents"]:
            self.assertNotIn("st", i, "article titles can carry details the summary omits")
        for w in self.s["policing"].get("wapo_fatal_shootings_in_area", []):
            self.assertNotIn("lat", w)
            self.assertNotIn("lon", w)

    def test_coordinates_not_overly_precise(self):
        for i in self.s["incidents"] + self.s["crashes"]["points"]:
            for k in ("lat", "lon"):
                self.assertLessEqual(len(str(i[k]).split(".")[-1]), 5, i)

    def test_street_only_policy_respected(self):
        curated = json.loads((ROOT / "data" / "research" / "crime" / "incidents.json").read_text())["incidents"]
        street_only = {(c["date"], c["municipality"], c["type"]) for c in curated if c.get("label_policy") == "use_street_only"}
        for i in self.s["incidents"]:
            if (i["d"], i["t"], i["k"]) in street_only:
                self.assertIn(i["p"], {"block", "street"}, f"{i['d']} {i['l']} exposes a place or cross street")

    def test_fbi_counts_sane(self):
        for ag in self.s["fbi"].get("agencies", []):
            for y in ag["years"]:
                for k in ("violent", "property", "murder", "robbery", "agg_assault", "burglary", "larceny", "mvt"):
                    v = y.get(k)
                    if v is not None:
                        self.assertGreaterEqual(v, 0, (ag["agency"], y["year"], k))
                parts = [y.get(k) for k in ("burglary", "larceny", "mvt")]
                if y.get("property") is not None and all(p is not None for p in parts):
                    self.assertLessEqual(sum(parts), y["property"] + 2, (ag["agency"], y["year"]))
                self.assertTrue(y.get("sources"), (ag["agency"], y["year"]))


@unittest.skipUnless((DATA / "pets.json").exists(), "pets data not built")
class PetsData(unittest.TestCase):
    """The lost & found pets contacts are sourced, and the GitHub issue form matches what pets.js parses."""

    @classmethod
    def setUpClass(cls):
        cls.p = json.loads((DATA / "pets.json").read_text())

    def test_contacts_sourced_and_well_formed(self):
        import re
        self.assertTrue(self.p["items"])
        for it in self.p["items"]:
            self.assertTrue(it.get("source", "").startswith("https://"), it["name"])
            self.assertTrue(it.get("name") and it.get("what_to_use_it_for"), it)
            if it.get("phone"):
                for num in re.findall(r"[\d-]{7,}", it["phone"]):
                    self.assertRegex(num, r"^\d{3}-\d{3}-\d{4}$", it["name"])
        for t in self.p.get("tips", []):
            self.assertTrue(t.get("source", "").startswith("https://"), t)

    def test_issue_form_matches_parser(self):
        form = (ROOT / ".github" / "ISSUE_TEMPLATE" / "lost-found-pet.yml").read_text()
        parser = (ROOT / "site" / "assets" / "pets.js").read_text()
        # each label pets.js reads with field("...") must start a label in the issue form
        for label in ("Lost, found or spotted", "Animal", "Pet's name", "Description", "Last seen near", "Town", "Date", "How to reach you"):
            self.assertIn(f'field("{label}")', parser)
            self.assertRegex(form, r"label: " + label.replace("?", r"\?"), label)


if __name__ == "__main__":
    unittest.main()
