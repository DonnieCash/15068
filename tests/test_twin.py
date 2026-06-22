"""Test suite for newken_twin (standard-library unittest, no deps)."""

import io
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from newken_twin import nbt, raster
from newken_twin.blocks import AIR, Palette, material
from newken_twin.builder import GROUND_Y, CityBuilder
from newken_twin.data import load_default_city
from newken_twin.geo import BBox, LatLon, Projection, bbox_around, haversine_m
from newken_twin.model import Building, City, Road, city_from_dict
from newken_twin.preview import render_topdown, write_png
from newken_twin.schematic import (DEFAULT_DATA_VERSION, build_block_data,
                                    decode_varints, encode_varint,
                                    schematic_nbt, write_schematic)
from newken_twin.volume import Volume


class TestGeo(unittest.TestCase):
    def test_projection_corners(self):
        box = BBox(south=40.0, west=-80.0, north=40.02, east=-79.98)
        proj = Projection(box, meters_per_block=1.0)
        # NW corner -> (0, 0)
        x, z = proj.to_block(LatLon(box.north, box.west))
        self.assertAlmostEqual(x, 0.0, places=6)
        self.assertAlmostEqual(z, 0.0, places=6)
        # SE corner -> (width, height)
        x, z = proj.to_block(LatLon(box.south, box.east))
        self.assertAlmostEqual(x, proj.width_m, places=3)
        self.assertAlmostEqual(z, proj.height_m, places=3)

    def test_projection_orientation(self):
        box = BBox(40.0, -80.0, 40.02, -79.98)
        proj = Projection(box)
        c = box.center
        # moving north decreases z; moving east increases x
        north = proj.to_block(LatLon(c.lat + 0.001, c.lon))
        south = proj.to_block(LatLon(c.lat - 0.001, c.lon))
        self.assertLess(north[1], south[1])
        east = proj.to_block(LatLon(c.lat, c.lon + 0.001))
        west = proj.to_block(LatLon(c.lat, c.lon - 0.001))
        self.assertGreater(east[0], west[0])

    def test_haversine_known_distance(self):
        # ~1 degree of latitude is ~111 km.
        d = haversine_m(LatLon(40.0, -80.0), LatLon(41.0, -80.0))
        self.assertTrue(110_000 < d < 112_000)

    def test_bbox_around(self):
        c = LatLon(40.5695, -79.7647)
        box = bbox_around(c, 500, 500)
        self.assertTrue(box.contains(c))
        proj = Projection(box)
        self.assertAlmostEqual(proj.width_m, 1000, delta=5)
        self.assertAlmostEqual(proj.height_m, 1000, delta=5)


class TestRaster(unittest.TestCase):
    def test_square_fill_area(self):
        cells = set(raster.polygon_cells(
            [(0, 0), (10, 0), (10, 10), (0, 10)]))
        # Cells whose centre lies inside [0,10]x[0,10]: a 10x10 block
        # (centres 0.5..9.5 on each axis).
        self.assertEqual(len(cells), 10 * 10)
        self.assertIn((5, 5), cells)
        self.assertIn((0, 0), cells)
        self.assertIn((9, 9), cells)
        self.assertNotIn((10, 10), cells)  # centre 10.5 is outside

    def test_triangle_excludes_outside(self):
        cells = set(raster.polygon_cells([(0, 0), (10, 0), (0, 10)]))
        self.assertIn((1, 1), cells)
        self.assertNotIn((9, 9), cells)  # outside the hypotenuse

    def test_thick_line_width(self):
        cells = set(raster.thick_line((0, 5), (10, 5), width=3))
        # A horizontal band three cells tall.
        self.assertIn((5, 4), cells)
        self.assertIn((5, 5), cells)
        self.assertIn((5, 6), cells)
        self.assertNotIn((5, 8), cells)

    def test_disk_radius(self):
        cells = set(raster.disk_cells(0, 0, 2))
        self.assertIn((0, 0), cells)
        self.assertIn((2, 0), cells)
        self.assertNotIn((2, 2), cells)  # distance ~2.83 > 2

    def test_clamp(self):
        cells = list(raster.clamp_cells(
            [(-1, 0), (0, 0), (5, 5), (5, 6)], width=5, length=5))
        self.assertEqual(cells, [(0, 0)])


class TestNBT(unittest.TestCase):
    def test_roundtrip_types(self):
        root = {
            "b": nbt.Byte(7),
            "s": nbt.Short(-1000),
            "i": nbt.Int(123456),
            "l": nbt.Long(9_000_000_000),
            "f": nbt.Float(1.5),
            "d": nbt.Double(2.5),
            "str": nbt.String("héllo"),
            "arr": nbt.ByteArray(b"\x01\x02\x03"),
            "ints": nbt.IntArray([1, 2, 3]),
            "list": nbt.List(nbt.TAG_INT, [nbt.Int(1), nbt.Int(2)]),
            "nested": {"x": nbt.Int(5)},
        }
        raw = nbt.write_nbt("Root", root)
        name, parsed = nbt.read_nbt(raw)
        self.assertEqual(name, "Root")
        self.assertEqual(parsed["b"], 7)
        self.assertEqual(parsed["s"], -1000)
        self.assertEqual(parsed["i"], 123456)
        self.assertEqual(parsed["l"], 9_000_000_000)
        self.assertAlmostEqual(parsed["f"], 1.5, places=5)
        self.assertAlmostEqual(parsed["d"], 2.5, places=9)
        self.assertEqual(parsed["str"], "héllo")
        self.assertEqual(parsed["arr"], b"\x01\x02\x03")
        self.assertEqual(parsed["ints"], [1, 2, 3])
        self.assertEqual(parsed["list"], [1, 2])
        self.assertEqual(parsed["nested"]["x"], 5)

    def test_file_roundtrip_gzip(self):
        import tempfile
        root = {"v": nbt.Int(42)}
        with tempfile.NamedTemporaryFile(suffix=".nbt", delete=False) as tf:
            path = tf.name
        try:
            nbt.write_nbt_file(path, "T", root, gzipped=True)
            with open(path, "rb") as f:
                self.assertEqual(f.read(2), b"\x1f\x8b")  # gzip magic
            name, parsed = nbt.read_nbt_file(path)
            self.assertEqual(name, "T")
            self.assertEqual(parsed["v"], 42)
        finally:
            os.unlink(path)


class TestPaletteBlocks(unittest.TestCase):
    def test_air_is_zero(self):
        pal = Palette()
        self.assertEqual(pal.id_of(AIR), 0)

    def test_stable_indices(self):
        pal = Palette()
        a = pal.id_of("minecraft:stone")
        b = pal.id_of("minecraft:dirt")
        self.assertEqual(pal.id_of("minecraft:stone"), a)
        self.assertNotEqual(a, b)
        self.assertEqual(len(pal), 3)  # air + stone + dirt

    def test_material_lookup(self):
        self.assertEqual(material("water"), "minecraft:water")
        with self.assertRaises(KeyError):
            material("does_not_exist")


class TestVolume(unittest.TestCase):
    def test_set_get_and_bounds(self):
        pal = Palette()
        vol = Volume(4, 5, 6, pal)
        vol.set(1, 2, 3, "minecraft:stone")
        self.assertNotEqual(vol.get_index(1, 2, 3), 0)
        self.assertEqual(vol.get_index(0, 0, 0), 0)
        # out-of-bounds writes are ignored, reads return air
        vol.set(99, 99, 99, "minecraft:stone")
        self.assertEqual(vol.get_index(99, 99, 99), 0)

    def test_index_formula_matches_sponge(self):
        pal = Palette()
        vol = Volume(3, 2, 4, pal)
        # index = (y*Length + z)*Width + x
        self.assertEqual(vol._index(0, 0, 0), 0)
        self.assertEqual(vol._index(2, 0, 0), 2)
        self.assertEqual(vol._index(0, 0, 1), 3)         # z step = Width
        self.assertEqual(vol._index(0, 1, 0), 3 * 4)     # y step = Width*Length

    def test_fill_column(self):
        vol = Volume(2, 10, 2, Palette())
        vol.fill_column(0, 0, 2, 5, "minecraft:stone")
        self.assertEqual(vol.get_index(0, 1, 0), 0)
        self.assertNotEqual(vol.get_index(0, 2, 0), 0)
        self.assertNotEqual(vol.get_index(0, 5, 0), 0)
        self.assertEqual(vol.get_index(0, 6, 0), 0)


class TestVarint(unittest.TestCase):
    def test_known_varints(self):
        self.assertEqual(encode_varint(0), b"\x00")
        self.assertEqual(encode_varint(127), b"\x7f")
        self.assertEqual(encode_varint(128), b"\x80\x01")
        self.assertEqual(encode_varint(300), b"\xac\x02")

    def test_roundtrip_stream(self):
        values = [0, 1, 127, 128, 255, 300, 16384, 70000]
        data = b"".join(encode_varint(v) for v in values)
        self.assertEqual(decode_varints(data), values)

    def test_negative_rejected(self):
        with self.assertRaises(ValueError):
            encode_varint(-1)


class TestSchematic(unittest.TestCase):
    def _small_volume(self):
        pal = Palette()
        vol = Volume(3, 3, 3, pal)
        vol.set(0, 0, 0, "minecraft:stone")
        vol.set(2, 2, 2, "minecraft:dirt")
        return vol

    def test_block_data_length(self):
        vol = self._small_volume()
        data = build_block_data(vol)
        # Each index here is < 128, so one byte per cell.
        self.assertEqual(len(decode_varints(data)),
                         vol.width * vol.height * vol.length)

    def test_block_data_ordering(self):
        vol = self._small_volume()
        indices = decode_varints(build_block_data(vol))
        self.assertEqual(indices[vol._index(0, 0, 0)],
                         vol.palette.id_of("minecraft:stone"))
        self.assertEqual(indices[vol._index(2, 2, 2)],
                         vol.palette.id_of("minecraft:dirt"))

    def test_schematic_nbt_structure(self):
        vol = self._small_volume()
        root = schematic_nbt(vol)
        self.assertEqual(root["Version"].value, 2)
        self.assertEqual(root["DataVersion"].value, DEFAULT_DATA_VERSION)
        self.assertEqual(root["Width"].value, 3)
        self.assertEqual(root["Height"].value, 3)
        self.assertEqual(root["Length"].value, 3)
        self.assertIn("minecraft:air", root["Palette"])
        self.assertEqual(root["Palette"]["minecraft:air"].value, 0)

    def test_write_and_reparse(self):
        import tempfile
        vol = self._small_volume()
        with tempfile.NamedTemporaryFile(suffix=".schem", delete=False) as tf:
            path = tf.name
        try:
            write_schematic(path, vol, name="Test City")
            name, root = nbt.read_nbt_file(path)
            self.assertEqual(name, "Schematic")
            self.assertEqual(root["Width"], 3)
            self.assertEqual(root["Height"], 3)
            self.assertEqual(root["Length"], 3)
            self.assertEqual(root["Version"], 2)
            self.assertEqual(root["Metadata"]["Name"], "Test City")
            # BlockData round-trips to the right number of cells.
            self.assertEqual(len(decode_varints(root["BlockData"])), 27)
            self.assertEqual(root["Palette"]["minecraft:air"], 0)
        finally:
            os.unlink(path)


class TestModel(unittest.TestCase):
    def test_building_height(self):
        b = Building(geometry=[], levels=5)
        self.assertEqual(b.height_blocks, 16)  # 5 * 3.2

    def test_road_width_default_by_class(self):
        self.assertEqual(Road(geometry=[], klass="primary").width_blocks, 12)
        self.assertEqual(Road(geometry=[], klass="residential").width_blocks, 7)
        self.assertEqual(Road(geometry=[], width_m=20).width_blocks, 20)

    def test_city_from_dict(self):
        doc = {
            "name": "T", "center": [40.0, -80.0],
            "features": [
                {"kind": "building", "geometry": [[-80, 40], [-79.99, 40]],
                 "levels": 3},
                {"kind": "road", "geometry": [[-80, 40], [-79.99, 40]],
                 "class": "primary"},
                {"kind": "water", "geometry": [[-80, 40], [-79.99, 40]]},
                {"kind": "landmark", "geometry": [-80, 40], "height": 20},
            ],
        }
        city = city_from_dict(doc)
        self.assertEqual(len(city.buildings), 1)
        self.assertEqual(len(city.roads), 1)
        self.assertEqual(len(city.areas), 1)
        self.assertEqual(len(city.points), 1)

    def test_unknown_kind_raises(self):
        with self.assertRaises(ValueError):
            city_from_dict({"center": [0, 0],
                            "features": [{"kind": "alien", "geometry": []}]})


class TestDataset(unittest.TestCase):
    def test_bundled_dataset_loads(self):
        city = load_default_city()
        self.assertGreater(len(city.buildings), 50)
        self.assertGreaterEqual(len(city.roads), 10)
        self.assertTrue(any(a.kind == "water" for a in city.areas))
        names = {p.name for p in city.points}
        self.assertIn("Mount Saint Peter Church", names)

    def test_center_is_new_kensington(self):
        city = load_default_city()
        self.assertAlmostEqual(city.center.lat, 40.5695, places=3)
        self.assertAlmostEqual(city.center.lon, -79.7647, places=3)


class TestBuilderIntegration(unittest.TestCase):
    def test_build_small_region_produces_structures(self):
        # A tiny synthetic city keeps the test fast.
        doc = {
            "name": "Tiny", "center": [40.5, -79.76],
            "features": [
                {"kind": "road", "class": "primary",
                 "geometry": [[-79.7605, 40.5], [-79.7595, 40.5]]},
                {"kind": "building", "levels": 4,
                 "geometry": [[-79.7602, 40.5003], [-79.7599, 40.5003],
                              [-79.7599, 40.5006], [-79.7602, 40.5006]]},
                {"kind": "landmark", "height": 18, "geometry": [-79.7600, 40.4997]},
            ],
        }
        city = city_from_dict(doc)
        result = CityBuilder(city, meters_per_block=1.0).build()
        vol = result.volume
        self.assertGreater(vol.width, 5)
        self.assertGreater(vol.length, 5)
        # ground layer exists everywhere
        self.assertNotEqual(vol.get_index(0, 0, 0), 0)             # bedrock
        self.assertNotEqual(vol.get_index(1, GROUND_Y, 1), 0)     # grass
        # something was built above ground level (a wall or landmark)
        above = sum(1 for y in range(GROUND_Y + 1, vol.height)
                    for z in range(vol.length) for x in range(vol.width)
                    if vol.get_index(x, y, z))
        self.assertGreater(above, 0)

    def test_full_bundled_build_runs(self):
        city = load_default_city()
        # Shrink with a coarse scale so the full-city build is quick.
        result = CityBuilder(city, meters_per_block=3.0).build()
        vol = result.volume
        self.assertGreater(vol.non_air_count(), 1000)
        # schematic block data has one entry per cell
        data = build_block_data(vol)
        self.assertEqual(len(decode_varints(data)),
                         vol.width * vol.height * vol.length)


class TestPreview(unittest.TestCase):
    def test_render_and_png_signature(self):
        import tempfile
        pal = Palette()
        vol = Volume(4, 6, 4, pal)
        for x in range(4):
            for z in range(4):
                vol.set(x, GROUND_Y, z, "minecraft:grass_block")
        pixels, w, h = render_topdown(vol)
        self.assertEqual((w, h), (4, 4))
        self.assertEqual(len(pixels), 3 * 4 * 4)
        with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as tf:
            path = tf.name
        try:
            write_png(path, pixels, w, h)
            with open(path, "rb") as f:
                self.assertEqual(f.read(8), b"\x89PNG\r\n\x1a\n")
        finally:
            os.unlink(path)


if __name__ == "__main__":
    unittest.main(verbosity=2)
