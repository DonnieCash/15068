"""Sanity checks for the NK15068 pipeline and the shipped site data.

    python -m unittest discover -s tests
"""
import json
import struct
import sys
import unittest
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

    def test_terrain_size(self):
        t = self.meta["terrain"]
        raw = (DATA / "terrain.bin").read_bytes()
        self.assertEqual(len(raw), t["w"] * t["h"] * 2)
        vals = struct.unpack(f"<{t['w'] * t['h']}H", raw)
        self.assertTrue(all(1900 <= v <= 5200 for v in vals))

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


if __name__ == "__main__":
    unittest.main()
