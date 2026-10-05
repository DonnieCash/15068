import contextlib
import io
import json
import struct
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

import fixtures as F
from sm2adapter import candidates as C
from sm2adapter import stg
from sm2adapter.cli import main
from sm2adapter.errors import FormatError
from sm2adapter.toc import load_toc, parse_toc

ROOT = Path(__file__).resolve().parents[1]
HYD, OTH = 0xAAAA0000000000AA, 0xBBBB0000000000BB
HYD_S = '0x%016x' % HYD


class HashesTests(unittest.TestCase):
    def load(self, text, suffix='.txt'):
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / ('h' + suffix)
            p.write_text(text)
            return C.load_hashes(p)

    def test_formats(self):
        want = {HYD: 'props/hydrant_a', OTH: 'props/other'}
        self.assertEqual(self.load('# c\naaaa0000000000aa props/hydrant_a\n0xBBBB0000000000BB props/other\n'), want)
        self.assertEqual(self.load(json.dumps({'AAAA0000000000AA': 'props/hydrant_a',
                                               '0xbbbb0000000000bb': 'props/other'}), '.json'), want)
        self.assertEqual(self.load(json.dumps([{'id': HYD, 'name': 'props/hydrant_a'},      # JSON numbers are decimal
                                               {'id': 'bbbb0000000000bb', 'name': 'props/other'}]), '.json'), want)
        self.assertEqual(self.load(''), {})
        self.assertEqual(self.load('aa name with spaces'), {0xaa: 'name with spaces'})

    def test_bad(self):
        for text in ('zzzz name', 'aa', '1ffffffffffffffff name', 'aa one\naa two', '{"aa": ""}', '{"aa": 5}',
                     '[1]', '{bad', '{"aa": "x", "AA": "y"}', '{"aa": "x", "0xaa": "y"}', '"str"[', '[{"id": 1}]'):
            with self.subTest(text), self.assertRaises(FormatError):
                self.load(text, '.json' if text[:1] in '{["' else '.txt')
        self.assertEqual(self.load('aa same\naa same'), {0xaa: 'same'})

    def test_json_duplicate_keys_are_not_collapsed(self):
        with self.assertRaises(FormatError):
            self.load('{"aa": "one", "aa": "two"}', '.json')


class CandidateTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.game = Path(self.tmp.name) / 'game'
        self.game.mkdir()
        F.make_game(self.game)
        self.toc = load_toc(self.game)
        self.hashes = {HYD: 'props/fire_hydrant', OTH: 'props/other'}

    def test_every_span_occurrence_is_kept(self):
        rows, stats = C.build_candidates(self.toc, self.hashes)
        # spans (0,2) and (1,2): entries 0,1 then 1,2 -> entry 1 appears twice; entry 3 is unspanned and unnamed
        self.assertEqual([(r['span'], r['index']) for r in rows], [(0, 0), (0, 1), (1, 1), (1, 2)])
        self.assertEqual([r['asset_id'] for r in rows].count(HYD_S), 2)      # same ID, distinct entries and spans
        self.assertEqual(stats['rows'], 4)
        self.assertEqual(stats['distinct_ids'], 2)
        self.assertEqual(stats['duplicate_id_rows'], 2)
        self.assertEqual(stats['duplicate_span_id_rows'], 0)
        self.assertEqual((stats['entries_in_several_spans'], stats['unspanned_entries']), (1, 1))
        self.assertNotEqual(rows[0]['offset'], rows[3]['offset'])

    def test_same_id_twice_in_one_span_is_kept_and_counted(self):
        toc = parse_toc(F.toc_bytes([(HYD, 8, 0, 0, -1), (HYD, 8, 0, 16, -1), (OTH, 8, 0, 32, -1)],
                                    [(0, 3)], ['a.dsar']))
        rows, stats = C.build_candidates(toc, self.hashes)
        self.assertEqual([(r['span'], r['index'], r['offset']) for r in rows], [(0, 0, 0), (0, 1, 16), (0, 2, 32)])
        self.assertEqual((stats['duplicate_span_id_rows'], stats['duplicate_id_rows']), (1, 1))

    def test_filters_and_unnamed(self):
        rows, _ = C.build_candidates(self.toc, self.hashes, name_contains='HYDRANT')
        self.assertEqual({r['index'] for r in rows}, {0, 2})
        rows, stats = C.build_candidates(self.toc, self.hashes, include_unnamed=True)
        self.assertEqual((rows[-1]['span'], rows[-1]['index'], rows[-1]['name']), (None, 3, None))
        self.assertEqual(stats['unspanned_entries'], 1)
        rows, _ = C.build_candidates(self.toc, {}, name_contains='x', include_unnamed=True)
        self.assertEqual(rows, [])

    def test_stats_need_exhausted_scan(self):
        scan = C.Scan(self.toc, self.hashes)
        with self.assertRaises(RuntimeError):
            scan.stats
        list(scan.rows())
        self.assertEqual(scan.stats['rows'], 4)

    def test_row_validation(self):
        rows, _ = C.build_candidates(self.toc, self.hashes)
        good = rows[0]
        C.validate_row(dict(good))
        C.verify_against_toc(good, self.toc)
        for key, value in (('bytes', '88'), ('offset', -1), ('index', True), ('archive', 5), ('name', 3),
                           ('asset_id', 'xyz'), ('header_offset', None)):
            with self.subTest(key), self.assertRaises(FormatError):
                C.validate_row(dict(good, **{key: value}))
        with self.assertRaises(FormatError):
            C.validate_row([1])
        for key, value in (('offset', 7), ('bytes', 9), ('index', 1), ('archive', 'other.dsar'), ('index', 99)):
            with self.subTest(key), self.assertRaises(FormatError):
                C.verify_against_toc(dict(good, **{key: value}), self.toc)


class CliTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.game = self.root / 'game'
        self.game.mkdir()
        self.data = F.make_game(self.game)
        (self.root / 'hashes.txt').write_text('aaaa0000000000aa props/fire_hydrant\nbbbb0000000000bb props/other\n')

    def run_cli(self, *args):
        out, err = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            code = main([str(a) for a in args])
        return code, out.getvalue(), err.getvalue()

    def candidates(self, *extra):
        code, _, err = self.run_cli('candidates', self.game, self.root / 'hashes.txt', self.root / 'cand.json', *extra)
        self.assertEqual(code, 0, err)
        return json.loads((self.root / 'cand.json').read_text())

    def test_full_pipeline(self):
        r = self.root
        code, out, _ = self.run_cli('inventory', self.game, r / 'inv.json')
        self.assertEqual(code, 0)
        self.assertIn('Assets: 4 Archives: 1 Missing: 0 Errors: 0', out)
        inv = json.loads((r / 'inv.json').read_text())
        self.assertEqual((inv['asset_entries'], inv['archives'][0]['exists'], inv['archives'][0]['compression_blocks']),
                         (4, True, {'3': 2}))
        self.assertEqual(inv['span_report']['entries_in_several_spans'], 1)
        doc = self.candidates()
        self.assertEqual(len(doc['candidates']), 4)
        self.assertEqual(doc['stats']['rows'], 4)
        self.assertEqual(doc['format'], 'sm2-candidates/1')
        self.assertEqual(self.run_cli('extract', self.game, r / 'cand.json', r / 'out', '--name-contains', 'hydrant')[0], 0)
        self.assertEqual((r / 'out' / 'probe.payload.bin').read_bytes(), self.data['hydrant'])
        self.assertEqual((r / 'out' / 'probe.header.bin').read_bytes(), self.data['header'])
        info = json.loads((r / 'out' / 'extraction.json').read_text())
        self.assertTrue(info['payload_is_dat1'])
        self.assertEqual(info['index'], 0)                    # smallest bytes, then lowest index
        code, out, _ = self.run_cli('package', r / 'out', r / 'out' / 'p.model')
        self.assertEqual(code, 0)
        self.assertEqual(json.loads(out)['flags'], 1)
        parsed = stg.parse_stg((r / 'out' / 'p.model').read_bytes())
        self.assertEqual((parsed.header, parsed.payload), (self.data['header'], self.data['hydrant']))

    def test_headerless_asset_packages_without_install_header_flag(self):
        self.candidates()
        r = self.root
        self.assertEqual(self.run_cli('extract', self.game, r / 'cand.json', r / 'o', '--name-contains', 'other')[0], 0)
        self.assertEqual((r / 'o' / 'probe.header.bin').read_bytes(), b'')
        code, out, _ = self.run_cli('package', r / 'o', r / 'o' / 'p.model')
        self.assertEqual((code, json.loads(out)['flags']), (0, 0))

    def test_extract_reads_bare_list_and_later_occurrence(self):
        rows = self.candidates()['candidates']
        (self.root / 'list.json').write_text(json.dumps(rows[1:]))   # entry 1 (other) and the later hydrant entry
        code, _, err = self.run_cli('extract', self.game, self.root / 'list.json', self.root / 'o', '--name-contains', 'hyd')
        self.assertEqual(code, 0, err)
        self.assertEqual((self.root / 'o' / 'probe.payload.bin').read_bytes(), self.data['hydrant'])

    def test_raw_archive_extraction(self):
        payload = F.model_payload(0x3333, 80)
        (self.game / 'archives' / 'raw.bin').write_bytes(b'\xee' * 16 + payload + b'\xee' * 7)
        (self.game / 'toc').write_bytes(F.toc_bytes([(HYD, len(payload), 0, 16, -1)], [(0, 1)], ['archives\\raw.bin']))
        self.assertEqual(self.run_cli('inventory', self.game, self.root / 'inv.json')[0], 0)
        self.assertEqual(json.loads((self.root / 'inv.json').read_text())['archives'][0]['compression'], 'raw')
        self.candidates()
        code, _, err = self.run_cli('extract', self.game, self.root / 'cand.json', self.root / 'o', '--name-contains', 'hydrant')
        self.assertEqual(code, 0, err)
        self.assertEqual((self.root / 'o' / 'probe.payload.bin').read_bytes(), payload)
        (self.game / 'archives' / 'raw.bin').write_bytes(b'\xee' * 20)           # shorter than the asset range
        self.assertEqual(self.run_cli('extract', self.game, self.root / 'cand.json', self.root / 'o2', '--name-contains', 'hydrant')[0], 1)
        self.assertFalse((self.root / 'o2').exists())

    def test_failures_exit_nonzero_and_write_nothing(self):
        r = self.root
        self.assertEqual(self.run_cli('inventory', r / 'nope', r / 'x.json')[0], 1)
        self.assertEqual(self.run_cli('extract', self.game, r / 'missing.json', r / 'o', '--name-contains', 'a')[0], 1)
        (r / 'garbage.json').write_text('{not json')
        code, _, err = self.run_cli('extract', self.game, r / 'garbage.json', r / 'o', '--name-contains', 'a')
        self.assertEqual(code, 1)
        self.assertIn('not valid JSON', err)
        self.candidates()
        self.assertEqual(self.run_cli('extract', self.game, r / 'cand.json', r / 'o', '--name-contains', 'zzz')[0], 1)
        self.assertEqual(self.run_cli('extract', self.game, r / 'cand.json', self.game / 'inside', '--name-contains', 'hydrant')[0], 1)
        self.assertFalse((self.game / 'inside').exists())
        # corrupt archive -> extraction fails, no partial output
        (self.game / 'archives' / 'a.dsar').write_bytes(b'DSAR' + bytes(40))
        self.assertEqual(self.run_cli('extract', self.game, r / 'cand.json', r / 'o2', '--name-contains', 'hydrant')[0], 1)
        self.assertFalse((r / 'o2').exists())

    def test_outputs_inside_game_dir_are_refused(self):
        for cmd in (('inventory', self.game, self.game / 'inv.json'),
                    ('candidates', self.game, self.root / 'hashes.txt', self.game / 'c.json')):
            with self.subTest(cmd[0]):
                code, _, err = self.run_cli(*cmd)
                self.assertEqual(code, 1)
                self.assertIn('outside the game directory', err)
        self.assertEqual(sorted(p.name for p in self.game.iterdir()), ['archives', 'toc'])

    def test_no_temp_file_left_after_failure(self):
        (self.root / 'bad.txt').write_text('not a hash line\n')
        code, _, _ = self.run_cli('candidates', self.game, self.root / 'bad.txt', self.root / 'c.json')
        self.assertEqual(code, 1)
        self.assertEqual(sorted(p.name for p in self.root.iterdir() if p.name.startswith('c.json')), [])

    def test_stale_candidates_are_refused(self):
        r = self.root
        doc = self.candidates()
        for name, edit in (('offset', lambda d: d['candidates'][0].update(offset=d['candidates'][0]['offset'] + 1)),
                           ('sha', lambda d: d.update(toc_sha256='0' * 64)),
                           ('archive', lambda d: d['candidates'][0].update(archive='archives\\b.dsar'))):
            with self.subTest(name):
                bad = json.loads(json.dumps(doc))
                edit(bad)
                (r / 'stale.json').write_text(json.dumps(bad))
                code, _, err = self.run_cli('extract', self.game, r / 'stale.json', r / 'o', '--name-contains', 'hydrant')
                self.assertEqual(code, 1)
                self.assertIn('regenerate', err)
                self.assertFalse((r / 'o').exists())

    def test_unsafe_archive_name_in_candidates(self):
        doc = self.candidates()
        doc['candidates'][0]['archive'] = '..\\..\\etc\\passwd'
        (self.root / 'evil.json').write_text(json.dumps(doc))
        code, _, err = self.run_cli('extract', self.game, self.root / 'evil.json', self.root / 'o', '--name-contains', 'hydrant')
        self.assertEqual(code, 1)
        self.assertIn('unsafe archive path', err)

    def test_toc_with_unsafe_archive_name(self):
        (self.game / 'toc').write_bytes(F.toc_bytes([(1, 8, 0, 0, -1)], [(0, 1)], ['..\\evil.dsar']))
        code, _, err = self.run_cli('inventory', self.game, self.root / 'x.json')
        self.assertEqual(code, 1)
        self.assertIn('unsafe archive path', err)

    def test_inventory_reports_bad_archive_but_finishes(self):
        (self.game / 'archives' / 'a.dsar').write_bytes(b'DSAR' + bytes(40))
        code, out, _ = self.run_cli('inventory', self.game, self.root / 'inv.json')
        self.assertEqual(code, 1)
        self.assertIn('Errors: 1', out)
        self.assertIn('error', json.loads((self.root / 'inv.json').read_text())['archives'][0])

    def test_inventory_counts_missing_archives(self):
        (self.game / 'archives' / 'a.dsar').unlink()
        code, out, _ = self.run_cli('inventory', self.game, self.root / 'inv.json')
        self.assertEqual(code, 0)
        self.assertIn('Missing: 1', out)

    def test_python_dash_m_and_wrapper_scripts(self):
        r = self.root
        env_cwd = dict(cwd=str(ROOT), capture_output=True, text=True)
        p = subprocess.run([sys.executable, '-m', 'sm2adapter', 'candidates', str(self.game),
                            str(r / 'hashes.txt'), str(r / 'c.json')], **env_cwd)
        self.assertEqual(p.returncode, 0, p.stderr)
        self.assertEqual(json.loads(p.stdout)['rows'], 4)
        p = subprocess.run([sys.executable, str(ROOT / 'tools/generate_candidates.py'), str(self.game),
                            str(r / 'hashes.txt'), str(r / 'c2.json'), '--name-contains', 'other'], **env_cwd)
        self.assertEqual((p.returncode, json.loads(p.stdout)['rows']), (0, 2))
        p = subprocess.run([sys.executable, str(ROOT / 'tools/inspect_toc.py'), str(self.game), str(r / 'i.json')], **env_cwd)
        self.assertEqual(p.returncode, 0, p.stderr)
        p = subprocess.run([sys.executable, str(ROOT / 'tools/extract_probe.py'), str(self.game), str(r / 'c.json'),
                            str(r / 'probe')], **env_cwd)            # name fragment defaults to 'hydrant'
        self.assertEqual(p.returncode, 0, p.stderr)
        p = subprocess.run([sys.executable, str(ROOT / 'tools/package_probe.py'), str(r / 'probe'), str(r / 'ok.model')], **env_cwd)
        self.assertEqual(p.returncode, 0, p.stderr)
        self.assertEqual(stg.parse_stg((r / 'ok.model').read_bytes()).payload, self.data['hydrant'])

    def probe_dir(self, name, payload, header=b'hdr'):
        d = self.root / name
        d.mkdir()
        (d / 'probe.payload.bin').write_bytes(payload)
        (d / 'probe.header.bin').write_bytes(header)
        return d

    def test_unpack_roundtrips_package_and_accepts_bare_dat1(self):
        r = self.root
        self.candidates()
        self.run_cli('extract', self.game, r / 'cand.json', r / 'before', '--name-contains', 'hydrant')
        self.run_cli('package', r / 'before', r / 'before.model')
        code, out, _ = self.run_cli('unpack', r / 'before.model', r / 'after')
        self.assertEqual(code, 0)
        self.assertEqual(json.loads(out)['input'], 'STG flags=1')
        self.assertEqual(self.run_cli('compare', r / 'before', r / 'after')[0], 0)      # unchanged cycle is identical
        (r / 'bare.dat1').write_bytes(self.data['hydrant'])
        code, out, _ = self.run_cli('unpack', r / 'bare.dat1', r / 'bare')
        self.assertEqual((code, json.loads(out)['header_bytes']), (0, 0))
        self.assertEqual(self.run_cli('compare', r / 'before', r / 'bare')[0], 3)       # header differs: reported
        (r / 'junk.bin').write_bytes(bytes(64))
        code, _, err = self.run_cli('unpack', r / 'junk.bin', r / 'junk')
        self.assertEqual(code, 1)
        self.assertFalse((r / 'junk').exists())

    def test_compare(self):
        a = self.probe_dir('a', F.dat1([(1, b'aaaa'), (2, b'bbbb')]))
        same = self.probe_dir('same', F.dat1([(1, b'aaaa'), (2, b'bbbb')]))
        code, out, _ = self.run_cli('compare', a, same)
        self.assertEqual(code, 0)
        self.assertEqual(json.loads(out)['verdict'], 'identical')
        changed = self.probe_dir('changed', F.dat1([(1, b'aaaa'), (2, b'bbbX'), (3, b'new!')]), header=b'other')
        code, out, _ = self.run_cli('compare', a, changed)
        rep = json.loads(out)
        self.assertEqual((code, rep['verdict'], rep['header_identical']), (3, 'different', False))
        self.assertEqual({t: v['identical'] for t, v in rep['sections'].items()},
                         {'0x00000001': True, '0x00000002': False, '0x00000003': False})
        self.assertIsNone(rep['sections']['0x00000003']['before'])
        junk = self.probe_dir('junk', bytes(40))
        code, out, _ = self.run_cli('compare', a, junk)
        self.assertEqual(code, 3)
        self.assertIn('not comparable', json.loads(out)['sections'])
        self.assertEqual(self.run_cli('compare', a, self.root / 'missing')[0], 1)

    def test_package_container_wrapper_matches_original_prototype_layout(self):
        r = self.root / 'probe'
        r.mkdir()
        payload = struct.pack('<IIIHH', 0x44415431, 0, 16, 0, 0)
        (r / 'probe.header.bin').write_bytes(bytes(range(24)))
        (r / 'probe.payload.bin').write_bytes(payload)
        subprocess.run([sys.executable, str(ROOT / 'tools/package_probe.py'), str(r), str(r / 'ok.model')],
                       check=True, capture_output=True)
        b = (r / 'ok.model').read_bytes()
        self.assertEqual(struct.unpack_from('<IIII', b), (0x475453, 1, 24, 0))
        self.assertEqual((b[16:40], b[40:48], b[48:]), (bytes(range(24)), bytes(8), payload))
        (r / 'probe.payload.bin').write_bytes(bytes(16))
        bad = subprocess.run([sys.executable, str(ROOT / 'tools/package_probe.py'), str(r), str(r / 'bad.model')],
                             capture_output=True)
        self.assertNotEqual(bad.returncode, 0)
        self.assertFalse((r / 'bad.model').exists())


if __name__ == '__main__':
    unittest.main()
