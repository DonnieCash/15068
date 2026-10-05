import contextlib
import copy
import hashlib
import io
import json
import shutil
import tempfile
import unittest
import zipfile
from pathlib import Path

import fixtures as F
from sm2adapter import manifest as M
from sm2adapter import stage as S
from sm2adapter import gamestate as G
from sm2adapter import stg
from sm2adapter.cli import main
from sm2adapter.errors import FormatError, UnsupportedError
from sm2adapter.toc import load_toc

ROOT = Path(__file__).resolve().parents[1]
EXAMPLE = ROOT / 'examples' / 'section-manifest.example.json'
HYD, OTH = 0xAAAA0000000000AA, 0xBBBB0000000000BB


def example():
    return json.loads(EXAMPLE.read_text())


class ManifestTests(unittest.TestCase):
    def test_example_is_valid(self):
        s = M.validate(example())
        self.assertEqual((s['nk_to_game'], s['components'][0]['transform']), ('unknown', 'unknown'))

    def bad(self, edit, exc=FormatError):
        doc = example()
        edit(doc)
        with self.assertRaises(exc):
            M.validate(doc)

    def test_statuses_must_be_explicit_and_justified(self):
        c = lambda d: d['components'][0]
        cases = {
            'unknown with a value': lambda d: d['nk_to_game'].update(matrix=[1] * 16),
            'hypothesis without note': lambda d: d['nk_to_game'].update(status='hypothesis', matrix=[0] * 16),
            'verified without evidence': lambda d: d['nk_to_game'].update(status='verified', matrix=[0] * 16, note='x'),
            'matrix too short': lambda d: d['nk_to_game'].update(status='hypothesis', matrix=[0] * 9, note='x'),
            'matrix not finite': lambda d: d['nk_to_game'].update(status='hypothesis', matrix=[float('nan')] * 16, note='x'),
            'bad status word': lambda d: d['target']['frame']['axes'].update(status='guessed'),
            'frame value missing': lambda d: d['nk']['frame']['axes'].update(status='verified', evidence='e'),
            'material verified, no evidence': lambda d: c(d)['materials'][0].update(status='verified', target_material='m'),
            'collision hypothesis, no note': lambda d: c(d)['collision'].pop('note'),
            'collision bad strategy': lambda d: c(d)['collision'].update(strategy='convex'),
        }
        for name, edit in cases.items():
            with self.subTest(name):
                self.bad(edit)

    def test_structure(self):
        c = lambda d: d['components'][0]
        cases = {
            'format': lambda d: d.update(format='other'),
            'no components': lambda d: d.update(components=[]),
            'duplicate nk component': lambda d: d['components'].append(copy.deepcopy(c(d))),
            'duplicate target': lambda d: d['components'].append(dict(copy.deepcopy(c(d)), nk=dict(c(d)['nk'], component_id='b2'))),
            'span range': lambda d: c(d)['target'].update(span=256),
            'span bool': lambda d: c(d)['target'].update(span=True),
            'asset id': lambda d: c(d)['target'].update(asset_id='xyz'),
            'kind': lambda d: c(d)['nk'].update(kind='castle'),
            'absolute geometry': lambda d: c(d)['geometry'].update(file='/tmp/x.model'),
            'escaping geometry': lambda d: c(d)['geometry'].update(file='../x.model'),
            'windows geometry': lambda d: c(d)['geometry'].update(file='models\\x.model'),
            'bad sha': lambda d: c(d)['geometry'].update(sha256='ABC'),
            'negative count': lambda d: c(d)['geometry'].update(vertices=-1),
            'toc sha1': lambda d: d['target'].update(toc_sha1='123'),
            'generated collision without file': lambda d: c(d)['collision'].update(strategy='generated'),
        }
        for name, edit in cases.items():
            with self.subTest(name):
                self.bad(edit)

    def test_unsupported(self):
        c = lambda d: d['components'][0]
        self.bad(lambda d: d['target'].update(game='MSMR'), UnsupportedError)
        self.bad(lambda d: c(d)['target'].update(mode='add-instance'), UnsupportedError)
        self.bad(lambda d: c(d)['geometry'].update(header_policy='replace'), UnsupportedError)

    def test_geometry_is_optional_and_hypotheses_are_allowed(self):
        doc = example()
        doc['components'][0]['geometry'] = None
        doc['nk_to_game'] = {'status': 'hypothesis', 'matrix': [1, 0, 0, 0, 0, 1, 0, 0, 0, 0, 1, 0, 0, 0, 0, 1],
                             'note': 'identity, to be checked with a calibration prop'}
        self.assertFalse(M.validate(doc)['components'][0]['has_geometry'])


class GameFixture(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.game = self.root / 'game'
        self.game.mkdir()
        self.data = F.make_game(self.game)
        self.toc = load_toc(self.game)
        self.staging = self.root / 'staging'
        (self.staging / 'models').mkdir(parents=True)
        self.model = F.model_payload(0x7777, 64)
        (self.staging / 'models' / 'b1.model').write_bytes(self.model)
        self.doc = example()
        self.doc['target']['toc_sha1'] = self.toc.sha1.upper()
        c = self.doc['components'][0]
        c['target'].update(span=0, asset_id='0x%016X' % HYD)
        c['geometry'].update(file='models/b1.model', sha256=hashlib.sha256(self.model).hexdigest())
        (self.root / 'manifest.json').write_text(json.dumps(self.doc))

    def run_cli(self, *args):
        out, err = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            code = main([str(a) for a in args])
        return code, out.getvalue(), err.getvalue()


class StageTests(GameFixture):
    def test_check_against_toc(self):
        found = M.check_against_toc(self.doc, self.toc)
        self.assertEqual((found[0]['index'], found[0]['archive']), (0, 'archives\\a.dsar'))
        bad = copy.deepcopy(self.doc)
        bad['target']['toc_sha1'] = '0' * 40
        with self.assertRaisesRegex(FormatError, 'toc sha1'):
            M.check_against_toc(bad, self.toc)
        bad = copy.deepcopy(self.doc)
        bad['components'][0]['target']['asset_id'] = '0x%016X' % 0x1234
        with self.assertRaisesRegex(FormatError, 'not in the TOC'):
            M.check_against_toc(bad, self.toc)
        bad['components'][0]['target'].update(span=1, asset_id='0x%016X' % HYD)   # HYD is also in span 1
        self.assertEqual(M.check_against_toc(bad, self.toc)[0]['index'], 2)

    def test_build_verify_and_determinism(self):
        out = self.root / 'out' / 'nk.stage'
        plan = S.build(self.doc, self.staging, self.toc, out, manifest_sha256='0' * 64)
        first = out.read_bytes()
        self.assertEqual(plan['stage_sha256'], hashlib.sha256(first).hexdigest())
        self.assertEqual(plan['preconditions']['toc_sha1'], self.toc.sha1)
        self.assertEqual(plan['assets'][0]['entry'], '0/%016X' % HYD)
        self.assertEqual(json.loads((out.parent / 'nk.stage.plan.json').read_text())['format'], 'nk-sm2-stage-plan/1')
        with zipfile.ZipFile(out) as z:
            self.assertEqual(z.namelist(), ['info.json', '0/%016X' % HYD])
            self.assertEqual(z.read('0/%016X' % HYD), self.model)              # bare DAT1: header untouched
            info = json.loads(z.read('info.json'))
        self.assertEqual((info['game'], info['format_version']), ('MSM2', 2))
        summary = S.verify(out, self.toc)
        self.assertEqual(summary['assets'][0]['stg_flags'], None)
        S.build(self.doc, self.staging, self.toc, out, manifest_sha256='0' * 64)
        self.assertEqual(out.read_bytes(), first)                               # reproducible bytes

    def test_build_refusals(self):
        out = self.root / 'o.stage'
        doc = copy.deepcopy(self.doc)
        doc['components'][0]['collision'] = {'strategy': 'generated', 'file': 'c.bin', 'sha256': '0' * 64,
                                             'status': 'hypothesis', 'note': 'n'}
        with self.assertRaises(UnsupportedError):
            S.build(doc, self.staging, self.toc, out)
        doc = copy.deepcopy(self.doc)
        doc['components'][0]['geometry']['sha256'] = '1' * 64
        with self.assertRaisesRegex(FormatError, 'sha256'):
            S.build(doc, self.staging, self.toc, out)
        doc = copy.deepcopy(self.doc)
        doc['components'][0]['geometry'] = None
        with self.assertRaisesRegex(FormatError, 'no component'):
            S.build(doc, self.staging, self.toc, out)
        self.assertFalse(out.exists())

    def test_stg_inputs(self):
        with_header = stg.pack_stg(b'h' * 8, self.model)
        (self.staging / 'models' / 'b1.model').write_bytes(with_header)
        self.doc['components'][0]['geometry']['sha256'] = hashlib.sha256(with_header).hexdigest()
        with self.assertRaises(UnsupportedError):
            S.build(self.doc, self.staging, self.toc, self.root / 'o.stage')
        plain = stg.pack_stg(b'', self.model)
        (self.staging / 'models' / 'b1.model').write_bytes(plain)
        self.doc['components'][0]['geometry']['sha256'] = hashlib.sha256(plain).hexdigest()
        S.build(self.doc, self.staging, self.toc, self.root / 'o.stage')
        with zipfile.ZipFile(self.root / 'o.stage') as z:
            self.assertEqual(z.read('0/%016X' % HYD), self.model)

    def write_zip(self, entries):
        p = self.root / 'bad.stage'
        with zipfile.ZipFile(p, 'w') as z:
            for name, data in entries:
                z.writestr(name, data)
        return p

    def test_verify_refusals(self):
        info = json.dumps({'game': 'MSM2', 'format_version': 2})
        good = ('0/%016X' % HYD, self.model)
        cases = {
            'no info': [good],
            'wrong game': [('info.json', json.dumps({'game': 'RCRA', 'format_version': 2})), good],
            'v1': [('info.json', json.dumps({'game': 'MSM2'})), good],
            'traversal': [('info.json', info), ('../0/%016X' % HYD, self.model)],
            'lowercase id': [('info.json', info), ('0/%016x' % HYD, self.model)],
            'span 300': [('info.json', info), ('300/%016X' % HYD, self.model)],
            'not dat1': [('info.json', info), ('0/%016X' % HYD, b'x' * 40)],
            'empty': [('info.json', info)],
        }
        for name, entries in cases.items():
            with self.subTest(name), self.assertRaises(FormatError):
                S.verify(self.write_zip(entries))
        with self.assertRaisesRegex(FormatError, 'not in the TOC'):
            S.verify(self.write_zip([('info.json', info), ('0/%016X' % 0x99, self.model)]), self.toc)
        (self.root / 'junk.stage').write_bytes(b'not a zip')
        with self.assertRaises(FormatError):
            S.verify(self.root / 'junk.stage')

    def test_cli_stage_and_verify(self):
        code, out, err = self.run_cli('stage', self.root / 'manifest.json', self.staging, self.root / 'o' / 'nk.stage',
                                      '--game', self.game)
        self.assertEqual(code, 0, err)
        self.assertEqual(json.loads(out)['assets'][0]['tile_id'], 'tile-000')
        code, out, _ = self.run_cli('verify-stage', self.root / 'o' / 'nk.stage', '--game', self.game)
        self.assertEqual((code, json.loads(out)['nk_adapter']['section_id']), (0, 'example-section-01'))
        code, _, err = self.run_cli('stage', self.root / 'manifest.json', self.staging, self.game / 'nk.stage',
                                    '--game', self.game)
        self.assertEqual(code, 1)
        self.assertIn('outside the game directory', err)
        code, out, _ = self.run_cli('manifest-check', self.root / 'manifest.json', '--game', self.game)
        self.assertEqual((code, json.loads(out)['in_toc'][0]['index']), (0, 0))

    def test_cli_sections(self):
        model = F.dat1([(0xEFD92E68, b'hk'), (0x12345678, b'??')])
        (self.root / 'm.model').write_bytes(stg.pack_stg(b'', model))
        code, out, _ = self.run_cli('sections', self.root / 'm.model')
        names = {r['tag']: r['name'] for r in json.loads(out)['sections']}
        self.assertEqual((code, names['0x12345678']), (0, None))
        self.assertIn('Physics', names['0xEFD92E68'])
        (self.root / 'x.bin').write_bytes(b'nope' * 10)
        self.assertEqual(self.run_cli('sections', self.root / 'x.bin')[0], 1)


class SnapshotTests(GameFixture):
    def install_like_overstrike(self):
        """Simulate what Overstrike does on install: toc -> toc.BAK, new mods archive, rewritten toc."""
        shutil.copyfile(self.game / 'toc', self.game / 'toc.BAK')
        (self.game / 'd' / 'mods').mkdir(parents=True)
        (self.game / 'd' / 'mods' / 'mod0').write_bytes(self.model)
        (self.game / 'toc').write_bytes(F.toc_bytes(
            [(HYD, len(self.model), 1, 0, -1)], [(0, 1)], ['archives\\a.dsar', 'd\\mods\\mod0']))

    def test_backup_install_rollback_cycle(self):
        r = self.root
        code, out, err = self.run_cli('snapshot', self.game, r / 'before.json', '--backup-dir', r / 'backup')
        self.assertEqual(code, 0, err)
        backup = Path(json.loads(out)['toc_backup'])
        self.assertEqual(backup.read_bytes(), (self.game / 'toc').read_bytes())
        self.install_like_overstrike()
        code, out, _ = self.run_cli('check-restored', self.game, r / 'before.json')
        self.assertEqual(code, 3)
        self.assertFalse(json.loads(out)['restored'])
        shutil.copyfile(self.game / 'toc.BAK', self.game / 'toc')                   # Overstrike's uninstall
        code, out, _ = self.run_cli('check-restored', self.game, r / 'before.json')
        rep = json.loads(out)
        self.assertEqual((code, rep['restored']), (0, True))
        self.assertTrue(any('toc.BAK' in n for n in rep['notes']))
        self.assertTrue(any('d/mods' in n for n in rep['notes']))

    def test_snapshot_never_writes_into_game(self):
        before = sorted(p.relative_to(self.game).as_posix() for p in self.game.rglob('*'))
        self.assertEqual(self.run_cli('snapshot', self.game, self.game / 'snap.json')[0], 1)
        self.assertEqual(self.run_cli('snapshot', self.game, self.root / 's.json', '--backup-dir', self.game / 'bk')[0], 1)
        self.assertEqual(sorted(p.relative_to(self.game).as_posix() for p in self.game.rglob('*')), before)

    def test_compare_flags_archive_changes(self):
        a = G.snapshot(self.game)
        b = copy.deepcopy(a)
        b['archives'][0]['bytes'] += 1
        self.assertEqual(G.compare(a, b)[0], ['archive list or sizes differ'])


if __name__ == '__main__':
    unittest.main()
