import io
import struct
import tempfile
import unittest
from pathlib import Path

import fixtures as F
from sm2adapter import dat1, dsar, stg, toc as T
from sm2adapter.errors import FormatError, UnsafePathError, UnsupportedError
from sm2adapter.limits import Limits
from sm2adapter.paths import require_outside, safe_join

needs_lz4 = unittest.skipIf(F.lz4 is None, 'lz4 not installed')


class Dat1Tests(unittest.TestCase):
    def test_valid(self):
        _, s = dat1.parse_dat1(F.dat1([(1, b'abcd'), (2, b'')]))
        self.assertEqual(bytes(s[1]), b'abcd')
        self.assertEqual(len(s[2]), 0)

    def test_unknowns_area_is_skipped(self):
        _, s = dat1.parse_dat1(F.dat1([(1, b'abcd')], unknowns=3))
        self.assertEqual(bytes(s[1]), b'abcd')

    def test_malformed(self):
        good = F.dat1([(1, b'abcd')])
        in_unknowns = bytearray(F.dat1([(1, b'abcd')], unknowns=2))
        struct.pack_into('<I', in_unknowns, 16 + 4, 16 + 12 + 8)   # offset points into the unknowns
        cases = {
            'truncated': good[:8],
            'magic': b'XXXX' + good[4:],
            'size': F.dat1([(1, b'abcd')], size_override=len(good) + 4),
            'duplicate tag': F.dat1([(1, b'ab'), (1, b'cd')]),
            'section oob': good[:16] + struct.pack('<III', 1, 28, 999) + good[28:],
            'section in table': good[:16] + struct.pack('<III', 1, 4, 4) + good[28:],
            'section in unknowns': bytes(in_unknowns),
            'unknowns past end': good[:14] + struct.pack('<H', 5000) + good[16:],
            'too many': good[:12] + struct.pack('<H', 60000) + good[14:],
        }
        for name, blob in cases.items():
            with self.subTest(name), self.assertRaises(FormatError):
                dat1.parse_dat1(blob)

    def test_section_limit(self):
        with self.assertRaises(FormatError):
            dat1.parse_dat1(F.dat1([(i, b'') for i in range(5)]), Limits(max_sections=4))

    def test_looks_like_dat1(self):
        self.assertTrue(dat1.looks_like_dat1(F.model_payload()))
        self.assertFalse(dat1.looks_like_dat1(bytes(20)))
        self.assertFalse(dat1.looks_like_dat1(F.dat1([(1, b'x')], size_override=9999)))
        self.assertFalse(dat1.looks_like_dat1(b'DAT1'))


class TocTests(unittest.TestCase):
    ASSETS = [(1, 8, 0, 0, -1), (2, 8, 0, 8, 0)]

    def toc(self, **kw):
        a = kw.pop('assets', self.ASSETS)
        return F.toc_bytes(a, kw.pop('spans', [(0, 2)]), kw.pop('archives', ['a.dsar']),
                           kw.pop('headers', F.asset_header()), **kw)

    def test_valid(self):
        t = T.parse_toc(self.toc())
        self.assertEqual((t.count, t.spans, t.archive_names), (2, [(0, 2)], ['a.dsar']))
        self.assertEqual(t.asset(1).offset, 8)
        self.assertEqual(t.header(t.asset(0)), b'')
        self.assertEqual(len(t.header(t.asset(1))), 8 + 8 + 4)
        self.assertEqual(t.span_of(1), 0)
        self.assertIsNone(t.span_of(5))
        self.assertIn('0x506d7b8a', t.section_tags)

    def test_meta_field_order(self):
        # (size, archive_index, offset, header_offset), as in Overstrike's SizeEntriesSection_I29
        t = T.parse_toc(self.toc(assets=[(0x1122334455667788, 111, 1, 222, -1)], spans=[(0, 1)],
                                 archives=['x.dsar', 'y.dsar']))
        self.assertEqual(t.asset(0), T.Asset(0, 0x1122334455667788, 111, 1, 222, -1))

    def test_any_negative_header_offset_means_no_header(self):
        t = T.parse_toc(self.toc(assets=[(1, 8, 0, 0, -5)], spans=[(0, 1)]))
        self.assertEqual(t.header(t.asset(0)), b'')

    def test_malformed(self):
        good = self.toc()
        cases = {
            'short': good[:4],
            'magic': b'\0\0\0\0' + good[4:],
            'length': self.toc(length_delta=1),
            'span past array': self.toc(spans=[(1, 5)]),
            'archive index': self.toc(assets=[(1, 8, 9, 0, -1)]),
            'header offset': self.toc(assets=[(1, 8, 0, 0, 9999)]),
            'truncated header': self.toc(headers=struct.pack('<IBBH', 0, 0, 200, 0)),
            'non-ascii name': self.toc(archives=['\u00e9.dsar']),
            'duplicate section': self.toc(extra_sections=[(T.TAG_IDS, b'')]),
        }
        for name, blob in cases.items():
            with self.subTest(name), self.assertRaises(FormatError):
                T.parse_toc(blob)

    def test_missing_section(self):
        blob = F.dat1([(T.TAG_IDS, b'')])
        with self.assertRaises(FormatError):
            T.parse_toc(struct.pack('<II', T.TOC_MAGIC, len(blob)) + blob)

    def test_ragged_tables(self):
        blob = F.dat1([(T.TAG_IDS, bytes(7)), (T.TAG_META, b''), (T.TAG_SPANS, b''),
                       (T.TAG_ARCHIVES, b''), (T.TAG_HEADERS, b'')])
        with self.assertRaises(FormatError):
            T.parse_toc(struct.pack('<II', T.TOC_MAGIC, len(blob)) + blob)

    def test_limits(self):
        with self.assertRaises(FormatError):
            T.parse_toc(self.toc(), Limits(max_toc_bytes=16))
        with self.assertRaises(FormatError):
            T.parse_toc(self.toc(), Limits(max_archives=0))
        with self.assertRaises(FormatError):
            T.parse_toc(self.toc(spans=[(0, 2), (0, 2)]), Limits(max_span_entries=3))

    def test_rift_apart_layout_is_refused(self):
        with self.assertRaises(UnsupportedError):
            T.parse_toc(self.toc(archives=['sargasso_a.dsar']))

    def test_span_report(self):
        assets = [(1, 8, 0, 0, -1), (2, 8, 0, 0, -1), (2, 8, 0, 0, -1), (1, 8, 0, 0, -1), (9, 8, 0, 0, -1)]
        r = T.parse_toc(self.toc(assets=assets, spans=[(0, 2), (1, 2), (3, 1)])).span_report()
        # entries 1,2 share an ID; span (1,2) repeats ID 2; entry 4 is in no span; entry 1 is in two spans
        self.assertEqual(r, {'spans': 3, 'unsorted_spans': 0, 'duplicate_ids_in_span': 1,
                             'entries_in_several_spans': 1, 'entries_in_no_span': 1})
        r = T.parse_toc(self.toc(assets=assets, spans=[(0, 4)])).span_report()
        self.assertEqual((r['unsorted_spans'], r['duplicate_ids_in_span']), (1, 2))


@needs_lz4
class DsarTests(unittest.TestCase):
    def table(self, blob, **lim):
        return dsar.read_table(io.BytesIO(blob), Limits(**lim) if lim else dsar.DEFAULT_LIMITS)

    def extract(self, blob, start, n, **lim):
        return dsar.extract_range(io.BytesIO(blob), start, n, Limits(**lim) if lim else dsar.DEFAULT_LIMITS)

    def test_extract_across_blocks(self):
        raw = bytes(range(256)) * 4
        blob = F.dsar_bytes([raw[:300], raw[300:]])
        self.assertEqual(self.extract(blob, 250, 100), raw[250:350])
        self.assertEqual(self.extract(blob, 0, len(raw)), raw)
        self.assertEqual(self.extract(blob, 5, 0), b'')

    def test_blocks_are_sorted_and_empty_ones_dropped(self):
        blob = bytearray(F.dsar_bytes([b'a' * 50, b'b' * 50, b'c' * 50]))
        struct.pack_into('<Q', blob, 32, 100)          # first table entry now holds the last raw range
        struct.pack_into('<Q', blob, 32 + 64, 0)
        self.assertEqual(self.extract(bytes(blob), 0, 150), b'c' * 50 + b'b' * 50 + b'a' * 50)
        struct.pack_into('<I', blob, 32 + 16, 0)       # raw_size 0 -> block ignored
        self.assertEqual([b.raw_size for b in self.table(bytes(blob))], [50, 50])

    def test_malformed_tables(self):
        good = F.dsar_bytes([b'a' * 100])
        def patch(off, fmt, val):
            b = bytearray(good); struct.pack_into(fmt, b, off, val); return bytes(b)
        cases = {
            'magic': b'XXXX' + good[4:],
            'short': good[:10],
            'table end past file': patch(12, '<I', 10 ** 6),
            'table end unaligned': patch(12, '<I', 70),
            'block past eof': patch(32 + 20, '<I', 10 ** 6),   # comp_size
            'block into table': patch(32 + 8, '<Q', 0),        # comp_offset
        }
        for name, blob in cases.items():
            with self.subTest(name), self.assertRaises(FormatError):
                self.table(blob)

    def test_table_limits_and_inventory_of_undecodable_kinds(self):
        with self.assertRaises(FormatError):
            self.table(F.dsar_bytes([b'a', b'b']), max_dsar_blocks=1)
        # a table of blocks we cannot decode still reads (inventory must not depend on decoder limits)
        blob = bytearray(F.dsar_bytes([b'x' * 100], kind=2))
        struct.pack_into('<I', blob, 32 + 16, 100 * 1024 * 1024)
        self.assertEqual(self.table(bytes(blob))[0].kind, 2)

    def test_extraction_limits(self):
        blob = F.dsar_bytes([b'\0' * 100000])
        with self.assertRaises(FormatError):
            self.extract(blob, 0, 100000, max_block_bytes=1000)
        with self.assertRaises(FormatError):
            self.extract(blob, 0, 1000, max_ratio=2)
        with self.assertRaises(FormatError):
            self.extract(blob, 0, 50000, max_asset_bytes=100)
        zero = bytearray(blob); struct.pack_into('<I', zero, 32 + 20, 0)
        with self.assertRaises(FormatError):
            self.extract(bytes(zero) + b'', 0, 10)

    def test_overlap_gap_and_short(self):
        blob = bytearray(F.dsar_bytes([b'a' * 100, b'b' * 100]))
        struct.pack_into('<Q', blob, 32 + 32, 50)           # second block starts at raw 50
        with self.assertRaises(FormatError):
            self.table(bytes(blob))
        blob = bytearray(F.dsar_bytes([b'a' * 100, b'b' * 100]))
        struct.pack_into('<Q', blob, 32 + 32, 150)          # gap 100..150
        with self.assertRaises(FormatError):
            self.extract(bytes(blob), 90, 70)
        with self.assertRaises(FormatError):                  # before any block
            self.extract(bytes(blob), 100, 10)
        with self.assertRaises(FormatError):                  # past the end
            self.extract(F.dsar_bytes([b'a' * 100]), 50, 100)

    def test_unsupported_kinds(self):
        with self.assertRaisesRegex(UnsupportedError, 'GDeflate'):
            self.extract(F.dsar_bytes([b'a' * 10], kind=2), 0, 10)
        with self.assertRaises(UnsupportedError):
            self.extract(F.dsar_bytes([b'a' * 10], kind=0), 0, 10)

    def test_corrupt_lz4(self):
        blob = bytearray(F.dsar_bytes([bytes(range(200))]))
        struct.pack_into('<I', blob, 32 + 16, 210)          # table claims 210 raw bytes, stream holds 200
        with self.assertRaises(FormatError):
            self.extract(bytes(blob), 0, 210)
        blob = bytearray(F.dsar_bytes([b'abcabcabc' * 30]))
        n = struct.unpack_from('<I', blob, 32 + 20)[0]
        struct.pack_into('<I', blob, 32 + 20, n - 3)         # stream cut short
        with self.assertRaises(FormatError):
            self.extract(bytes(blob), 0, 270)

    def test_raw_archive(self):
        f = io.BytesIO(b'0123456789')
        self.assertFalse(dsar.is_dsar(f))
        self.assertEqual(dsar.read_raw_range(f, 2, 4), b'2345')
        for start, n in ((8, 4), (-1, 2), (0, -1)):
            with self.subTest((start, n)), self.assertRaises(FormatError):
                dsar.read_raw_range(f, start, n)
        with self.assertRaises(FormatError):
            dsar.read_raw_range(f, 0, 5, Limits(max_asset_bytes=4))


class StgTests(unittest.TestCase):
    def test_layout_follows_overstrike(self):
        payload, header, meta = F.model_payload(), bytes(range(24)), b'meta5'
        packed = stg.pack_stg(header, payload, meta)
        self.assertEqual(struct.unpack_from('<IIII', packed), (0x475453, 3, 24, 5))
        self.assertEqual(packed[16:40], header)
        self.assertEqual(packed[40:48], bytes(8))             # header padded to a 16-byte file offset
        self.assertEqual(packed[48:53], meta)
        self.assertEqual(packed[53:64], bytes(11))
        self.assertEqual(packed[64:], payload)

    def test_roundtrip_and_derived_flags(self):
        payload = F.model_payload()
        for header, meta, flags in ((bytes(range(24)), b'', 1), (b'', b'', 0), (b'', b'm', 2), (bytes(16), b'm', 3)):
            with self.subTest(flags):
                packed = stg.pack_stg(header, payload, meta)
                self.assertEqual(stg.parse_stg(packed), stg.Stg(flags, header, meta, payload))
                self.assertEqual(len(packed) % 16, len(payload) % 16)

    def test_pack_rejects_bad_payload(self):
        bad_section = bytearray(F.model_payload()); struct.pack_into('<I', bad_section, 16 + 8, 10 ** 6)
        for bad in (b'', bytes(16), F.dat1([(1, b'x')], size_override=999), bytes(bad_section)):
            with self.subTest(bad[:4]), self.assertRaises(FormatError):
                stg.pack_stg(b'', bad)
        with self.assertRaises(FormatError):
            stg.pack_stg(bytes(100), F.model_payload(), limits=Limits(max_header_bytes=10))

    def test_parse_malformed(self):
        good = stg.pack_stg(bytes(5), F.model_payload())
        bad_pad = bytearray(good); bad_pad[16 + 5] = 1
        cases = {'short': good[:6], 'magic': b'XXXX' + good[4:],
                 'header oob': good[:8] + struct.pack('<I', 10 ** 6) + good[12:],
                 'padding': bytes(bad_pad), 'payload': good[:-4], 'no payload': good[:32],
                 'meta flag without meta': good[:4] + struct.pack('<I', 3) + good[8:],
                 'header flag without header': stg.pack_stg(b'', F.model_payload())[:4] + struct.pack('<I', 1)
                                               + stg.pack_stg(b'', F.model_payload())[8:]}
        for name, blob in cases.items():
            with self.subTest(name), self.assertRaises(FormatError):
                stg.parse_stg(blob)

    def test_parse_unsupported(self):
        good = stg.pack_stg(bytes(5), F.model_payload())
        with self.assertRaisesRegex(UnsupportedError, 'version'):
            stg.parse_stg(good[:3] + b'\x01' + good[4:])
        with self.assertRaisesRegex(UnsupportedError, 'flags'):
            stg.parse_stg(good[:4] + struct.pack('<I', 5) + good[8:])


class PathTests(unittest.TestCase):
    def test_safe_join(self):
        with tempfile.TemporaryDirectory() as d:
            self.assertEqual(safe_join(d, 'a\\b.dsar'), Path(d).resolve() / 'a' / 'b.dsar')
            for bad in ('', '..\\x', 'a/../../x', '/etc/passwd', 'C:\\x', 'a\0b', '.'):
                with self.subTest(bad), self.assertRaises(UnsafePathError):
                    safe_join(d, bad)

    def test_symlink_escape(self):
        with tempfile.TemporaryDirectory() as d, tempfile.TemporaryDirectory() as o:
            (Path(d) / 'link').symlink_to(o)
            with self.assertRaises(UnsafePathError):
                safe_join(d, 'link/file')

    def test_require_outside(self):
        with tempfile.TemporaryDirectory() as d:
            for bad in (d, Path(d) / 'sub', Path(d) / 'sub' / '..' / 'x.json'):
                with self.subTest(bad), self.assertRaises(UnsafePathError):
                    require_outside(bad, d)
            with tempfile.TemporaryDirectory() as o:
                require_outside(o, d)
                require_outside(Path(d).parent / 'elsewhere.json', d)


if __name__ == '__main__':
    unittest.main()
