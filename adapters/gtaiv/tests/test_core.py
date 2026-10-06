import math
import struct
import unittest

import helpers
from nkgta4 import ide, wpl
from nkgta4.collision import build_bound, dequantize
from nkgta4.errors import FormatError
from nkgta4.jenkins import gta_hash, one_at_a_time
from nkgta4.objmesh import parse_obj, write_obj


class HashTests(unittest.TestCase):
    def test_standard_vectors(self):
        self.assertEqual(one_at_a_time(b'a'), 0xCA2E9442)
        self.assertEqual(one_at_a_time(b'The quick brown fox jumps over the lazy dog'), 0x519E91F5)

    def test_gta_rules(self):
        self.assertEqual(gta_hash('NK_Demo'), gta_hash('nk_demo'))
        self.assertEqual(gta_hash('a\\b'), gta_hash('a/b'))
        self.assertEqual(gta_hash('"abc"def'), gta_hash('abc'))
        self.assertEqual(gta_hash('a'), 0xCA2E9442)
        with self.assertRaises(ValueError):
            gta_hash('')


class ObjTests(unittest.TestCase):
    def test_parse_and_roundtrip(self):
        m = parse_obj('# c\nv 0 0 0\nv 1 0 0\nv 1 1 0\nv 0 1 0\nvt 0 0\nusemtl a\nf 1/1/1 2/1 3 -1\n')
        self.assertEqual(m.triangles, [(0, 1, 2), (0, 2, 3)])
        self.assertEqual(m.materials, ['a', 'a'])
        again = parse_obj(write_obj(m))
        self.assertEqual((again.vertices, again.triangles, again.materials), (m.vertices, m.triangles, m.materials))
        self.assertEqual(write_obj(m), write_obj(again))

    def test_rejects(self):
        for text in ('v 0 0\nf 1 1 1', 'v 0 0 0\nv 1 0 0\nv 0 1 0\nf 1 2 4', 'v 0 0 0\nl 1 2',
                     'v nan 0 0\nv 1 0 0\nv 0 1 0\nf 1 2 3', 'v 0 0 0\nv 1 0 0\nf 1 2', 'v 0 0 0\n',
                     'v 0 0 0\nv 1 0 0\nv 0 1 0\nf 1 x 3'):
            with self.subTest(text), self.assertRaises(FormatError):
                parse_obj(text)


class CollisionTests(unittest.TestCase):
    def box(self):
        m = parse_obj(helpers.BOX)
        return m.vertices, m.triangles

    def test_closed_box(self):
        b = build_bound(*self.box())
        self.assertEqual(b['stats'], {'vertices': 8, 'polygons': 12, 'open_edges': 0, 'non_manifold_edges': 0})
        self.assertTrue(all(None not in p['neighbors'] for p in b['polygons']))
        self.assertEqual(b['center'], [0.5, 0.5, 0.5])
        self.assertLess(b['max_quantization_error'], 1e-4)
        for got, want in zip(dequantize(b), self.box()[0]):
            self.assertLess(math.dist(got, want), 1e-4)
        for p in b['polygons']:
            self.assertAlmostEqual(math.hypot(*p['normal']), 1.0, places=5)
            self.assertAlmostEqual(p['area'], 0.5, places=6)
        self.assertIn('per-polygon collision material (surface type) index', b['unresolved'])

    def test_neighbors_and_flat(self):
        b = build_bound([(0, 0, 0), (1, 0, 0), (1, 1, 0), (0, 1, 0)], [(0, 1, 2), (0, 2, 3)])
        self.assertEqual(b['polygons'][0]['neighbors'], [None, None, 1])
        self.assertEqual(b['polygons'][1]['neighbors'], [0, None, None])
        self.assertEqual(b['stats']['open_edges'], 4)
        self.assertEqual(b['vertices_quantized'][0][2], 0)          # zero-height axis does not divide by zero

    def test_rejects(self):
        v, t = self.box()
        cases = {'degenerate': (v, [(0, 1, 1)]), 'collinear': ([(0, 0, 0), (1, 0, 0), (2, 0, 0)], [(0, 1, 2)]),
                 'index': (v, [(0, 1, 99)]), 'empty': ([], [])}
        for name, (vv, tt) in cases.items():
            with self.subTest(name), self.assertRaises(FormatError):
                build_bound(vv, tt)
        with self.assertRaisesRegex(FormatError, 'quantisation'):
            build_bound([(0, 0, 0), (3.0e6, 0, 0), (1234.567, 1, 0)], [(0, 1, 2)], max_error=1.0)
        with self.assertRaisesRegex(FormatError, 'uint16'):
            build_bound([(i, 0, 0) for i in range(65537)], [(0, 1, 2)])


class IdeTests(unittest.TestCase):
    def test_line_roundtrip(self):
        lo, hi, sphere = ide.bounds_of([(-1, -2, 0), (1, 2, 10.5)])
        line = ide.objs_line('nk_a', 'nk_txd', 300, 0, 2, lo, hi, sphere, 'null')
        self.assertEqual(line.count(','), 15)
        back = ide.parse_objs_line(line)
        self.assertEqual((back['model'], back['flag2'], back['bbox_max'], back['wdd']), ('nk_a', 2, [1, 2, 10.5], 'null'))
        self.assertAlmostEqual(back['sphere'][3], math.dist((0, 0, 5.25), (1, 2, 10.5)), places=5)
        self.assertEqual(ide.objs_section([line]), 'objs\n%s\nend\n' % line)

    def test_rejects(self):
        ok = dict(model='nk_a', txd='t', draw_distance=1, flag1=0, flag2=0, bbox_min=[0, 0, 0], bbox_max=[1, 1, 1],
                  sphere=[0, 0, 0, 1], wdd='null')
        for k, v in (('model', 'has space'), ('txd', ''), ('flag1', True), ('flag2', 1.5), ('draw_distance', 0),
                     ('bbox_min', [2, 0, 0]), ('sphere', [0, 0, 0, float('inf')]), ('wdd', '')):
            with self.subTest(k), self.assertRaises(FormatError):
                ide.objs_line(**dict(ok, **{k: v}))
        with self.assertRaises(FormatError):
            ide.parse_objs_line('a, b, c')


class WplTests(unittest.TestCase):
    INST = {'model': 'nk_a', 'position': (1.0, 2.0, 3.0), 'rotation': (0.0, 0.0, 0.0, 1.0),
            'flags': 0, 'lod': -1, 'unknown_int': 0, 'unknown_float': 0.0}

    def test_layout_and_roundtrip(self):
        data = wpl.pack([self.INST, dict(self.INST, model='nk_b', rotation=wpl.stored_quaternion_z(90))])
        self.assertEqual(len(data), 17 * 4 + 2 * 48)
        self.assertEqual(struct.unpack_from('<17i', data)[:3], (3, 2, 0))
        back = wpl.unpack(data)
        self.assertEqual(back[0]['hash'], gta_hash('nk_a'))
        self.assertEqual((back[0]['position'], back[0]['lod']), ((1.0, 2.0, 3.0), -1))
        self.assertAlmostEqual(back[1]['rotation'][2], -math.sqrt(0.5), places=6)   # stored with negated xyz

    def test_rejects(self):
        for k, v in (('rotation', (0, 0, 0, 2)), ('position', (0, 0)), ('flags', True), ('lod', 1.0)):
            with self.subTest(k), self.assertRaises(FormatError):
                wpl.pack([dict(self.INST, **{k: v})])
        with self.assertRaises(FormatError):
            wpl.pack([{k: v for k, v in self.INST.items() if k != 'unknown_float'}])
        with self.assertRaises(FormatError):
            wpl.pack([])
        good = wpl.pack([self.INST])
        for name, blob in (('version', struct.pack('<i', 4) + good[4:]), ('size', good[:-4]), ('short', good[:10]),
                           ('cars', good[:16] + struct.pack('<i', 1) + good[20:])):
            with self.subTest(name), self.assertRaises(FormatError):
                wpl.unpack(blob)


if __name__ == '__main__':
    unittest.main()
