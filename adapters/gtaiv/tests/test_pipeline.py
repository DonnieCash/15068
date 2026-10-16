import contextlib
import copy
import hashlib
import io
import json
import shutil
import struct
import subprocess
import sys
import tempfile
import unittest
import zipfile
from pathlib import Path

import helpers
from nkgta4 import gamestate, manifest, ofscan, oiv, section, wpl
from nkgta4.cli import main
from nkgta4.errors import FormatError, UnsupportedError
from nkgta4.jenkins import gta_hash

EX = helpers.EXAMPLES


def example():
    return json.loads((EX / 'section.json').read_text())


def run(*args):
    out, err = io.StringIO(), io.StringIO()
    with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
        code = main([str(a) for a in args])
    return code, out.getvalue(), err.getvalue()


class ManifestTests(unittest.TestCase):
    def test_example_valid(self):
        self.assertEqual(manifest.validate(example())['components'], 2)

    def bad(self, edit, exc=FormatError):
        doc = example()
        edit(doc)
        with self.assertRaises(exc):
            manifest.validate(doc)

    def test_rejects(self):
        c = lambda d: d['components'][0]
        cases = {
            'unknown with value': lambda d: c(d)['lod_parent'].update(value='x'),
            'hypothesis without note': lambda d: c(d)['wdd'].pop('note'),
            'verified without evidence': lambda d: c(d)['ide_flags'].update(status='verified'),
            'non-affine': lambda d: d['nk_to_game'].update(value=[1] * 16),
            'duplicate component': lambda d: d['components'].append(copy.deepcopy(c(d))),
            'duplicate model': lambda d: d['components'][1]['model'].update(name='NK_DEMO_ROAD_0001'),
            'section id': lambda d: d.update(section_id='has space'),
            'placement field': lambda d: c(d)['placement']['value'].update(lod=1.5),
            'flags pair': lambda d: c(d)['ide_flags'].update(value=[0]),
            'separate collision without obj': lambda d: c(d)['collision'].update(source='separate'),
            'escaping path': lambda d: c(d)['render'].update(obj='../x.obj'),
            'release hash': lambda d: d['nk'].update(release_sha256='abc'),
        }
        for name, edit in cases.items():
            with self.subTest(name):
                self.bad(edit)
        self.bad(lambda d: d['target'].update(game='GTAV'), UnsupportedError)


class SectionTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.out = Path(self.tmp.name) / 'out'

    def test_build_outputs_and_determinism(self):
        report = section.build(example(), EX, self.out)
        self.assertFalse(report['game_ready'])
        self.assertEqual(sorted(report['files']), sorted([
            'models/nk_demo_road_0001.obj', 'models/nk_demo_bldg_0001.obj', 'collision/nk_demo_road_0001.bound.json',
            'collision/nk_demo_bldg_0001.bound.json', 'nk_demo.ide', 'nk_demo.wpl']))
        insts = wpl.unpack((self.out / 'nk_demo.wpl').read_bytes())
        self.assertEqual([i['hash'] for i in insts], [gta_hash('nk_demo_road_0001'), gta_hash('nk_demo_bldg_0001')])
        self.assertEqual(insts[1]['position'], (35.0, 6.0, 0.0))          # bbox centre x/y, min z
        bound = json.loads((self.out / 'collision/nk_demo_bldg_0001.bound.json').read_text())
        self.assertEqual(bound['stats']['open_edges'], 0)
        self.assertEqual(bound['bbox_min'], [-5.0, -6.0, 0.0])
        ide = (self.out / 'nk_demo.ide').read_text().splitlines()
        self.assertEqual((ide[0], ide[-1], len(ide)), ('objs', 'end', 4))
        first = {p: (self.out / p).read_bytes() for p in report['files']}
        section.build(example(), EX, self.out)
        self.assertEqual({p: (self.out / p).read_bytes() for p in report['files']}, first)

    def test_transform_applies(self):
        doc = example()
        doc['nk_to_game']['value'] = [1, 0, 0, 100, 0, 1, 0, -50, 0, 0, 1, 5, 0, 0, 0, 1]
        section.build(doc, EX, self.out)
        insts = wpl.unpack((self.out / 'nk_demo.wpl').read_bytes())
        self.assertEqual(insts[1]['position'], (135.0, -44.0, 5.0))

    def test_refuses_unknowns_and_bad_inputs(self):
        for edit in (lambda d: d.update(nk_to_game={'status': 'unknown'}),
                     lambda d: d['components'][0].update(ide_flags={'status': 'unknown'}),
                     lambda d: d['components'][0].update(placement={'status': 'unknown'}),
                     lambda d: d['components'][0].update(wdd={'status': 'unknown'})):
            doc = example()
            edit(doc)
            with self.assertRaises(UnsupportedError):
                section.build(doc, EX, self.out)
        doc = example()
        doc['components'][0]['render']['sha256'] = '1' * 64
        with self.assertRaisesRegex(FormatError, 'sha256'):
            section.build(doc, EX, self.out)

    def test_separate_collision(self):
        staging = Path(self.tmp.name) / 'staging'
        shutil.copytree(EX, staging)
        (staging / 'col.obj').write_text(helpers.BOX)
        doc = example()
        doc['components'][1]['collision'].update(source='separate', obj='col.obj',
                                                 sha256=hashlib.sha256(helpers.BOX.encode()).hexdigest())
        section.build(doc, staging, self.out)
        bound = json.loads((self.out / 'collision/nk_demo_bldg_0001.bound.json').read_text())
        self.assertEqual(bound['stats']['vertices'], 8)
        # 1 m box at the world origin, seen from the building's instance origin (35, 6, 0)
        self.assertEqual((bound['bbox_min'], bound['bbox_max']), ([-35.0, -6.0, 0.0], [-34.0, -5.0, 1.0]))


def make_plan(root):
    files = {'compiled/nk_demo_road_0001.wdr': b'compiled elsewhere', 'out/nk_demo.wpl': b'wpl bytes',
             'out/nk_demo.ide': b'objs\nend\n'}
    for rel, data in files.items():
        (root / rel).parent.mkdir(parents=True, exist_ok=True)
        (root / rel).write_bytes(data)
    plan = json.loads((EX / 'install-plan.example.json').read_text())
    for f in plan['archive_files'] + plan['loose_files']:
        f['sha256'] = hashlib.sha256(files[f['file']]).hexdigest()
    plan['text_edits'][0]['add'] = 'pc/data/maps/nk/nk_demo 1'
    return plan


class OivTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.plan = make_plan(self.root)

    def test_example_template_is_not_buildable(self):
        with self.assertRaises(FormatError):
            oiv.validate(json.loads((EX / 'install-plan.example.json').read_text()))

    def test_build_and_verify(self):
        out = self.root / 'pkg' / 'nk.oiv'
        info = oiv.build(self.plan, self.root, out)
        self.assertEqual(info['files'], 3)
        with zipfile.ZipFile(out) as z:
            self.assertEqual(sorted(z.namelist()), ['assembly.xml', 'content/nk_demo.ide', 'content/nk_demo.wpl',
                                                    'content/nk_demo_road_0001.wdr'])
            xml = z.read('assembly.xml').decode()
        self.assertIn('<package version="2.2" id="{6B1C2D3E-4F50-4A61-8B72-93A4B5C6D7E8}" target="IV">', xml)
        self.assertIn('<archive path="pc\\data\\maps\\nk\\nk_demo.img" createIfNotExist="True" type="IMG3">', xml)
        self.assertIn('<add>pc/data/maps/nk/nk_demo 1</add>', xml)
        first = out.read_bytes()
        oiv.build(self.plan, self.root, out)
        self.assertEqual(out.read_bytes(), first)
        code, report, _ = run('verify-oiv', out)
        self.assertEqual((code, json.loads(report)['unreferenced']), (0, []))

    def test_rejects(self):
        cases = {
            'abs target': lambda p: p['loose_files'][0].update(target='C:\\x.ide'),
            'dotdot': lambda p: p['loose_files'][0].update(target='..\\x.ide'),
            'slash target': lambda p: p['loose_files'][0].update(target='pc/x.ide'),
            'guid': lambda p: p.update(guid='nope'),
            'name with path': lambda p: p['archive_files'][0].update(name='a\\b.wdr'),
            'bad ext': lambda p: p['archive_files'][0].update(name='x.exe'),
            'no note': lambda p: p['text_edits'][0].pop('note'),
            'multi-line add': lambda p: p['text_edits'][0].update(add='a\nb'),
            'not img': lambda p: p['archive'].update(path='pc\\x.rpf'),
            'create flag': lambda p: p['archive'].update(create_if_missing='yes'),
            'nothing': lambda p: p.update(archive_files=[], loose_files=[]),
        }
        for name, edit in cases.items():
            plan = copy.deepcopy(self.plan)
            edit(plan)
            with self.subTest(name), self.assertRaises(FormatError):
                oiv.validate(plan)
        self.plan['archive_files'][0]['sha256'] = '2' * 64
        with self.assertRaisesRegex(FormatError, 'sha256'):
            oiv.build(self.plan, self.root, self.root / 'x.oiv')

    def test_verify_rejects(self):
        for name, entries in (('no assembly', [('content/a', b'')]),
                              ('wrong target', [('assembly.xml', b'<package version="2.2" target="Five"/>')]),
                              ('missing file', [('assembly.xml', b'<package version="2.2" target="IV"><metadata/><colors/>'
                                                                 b'<content><add source="a.wdr">a.wdr</add></content></package>')])):
            p = self.root / ('%s.oiv' % name.replace(' ', '_'))
            with zipfile.ZipFile(p, 'w') as z:
                for n, d in entries:
                    z.writestr(n, d)
            with self.subTest(name):
                self.assertEqual(run('verify-oiv', p)[0], 1)


class OfscanTests(unittest.TestCase):
    def test_structure_only(self):
        text = 'Version 110 12\nBound\n{\n\tType BoundGeometry\n\tCentroid 1.5 -2 3e2\n\tVerts 2\n\t{\n\t\t1 2 3\n\t\t4 5 6\n\t}\n}\n'
        out = ofscan.scan(text)
        self.assertEqual(out, ['Version n n', 'Bound', '{', '  Type s', '  Centroid n n n', '  Verts n', '  {',
                               '    n n n   x2', '  }', '}'])
        self.assertNotIn('1.5', '\n'.join(out))

    def test_unbalanced(self):
        for text in ('a\n{\n', '}\n', 'a {\n}\n}\n'):
            with self.subTest(text), self.assertRaises(FormatError):
                ofscan.scan(text)


def fake_game(root):
    exe = b'MZ' + bytes(100) + b'\xbd\x04\xef\xfe' + struct.pack('<IIIII', 0x10000, 0x10000, 7 << 16, 0, 0) + bytes(50)
    (root / 'common' / 'data').mkdir(parents=True)
    (root / 'pc' / 'data' / 'maps' / 'manhat').mkdir(parents=True)
    (root / 'GTAIV.exe').write_bytes(exe)
    (root / 'common' / 'data' / 'gta.dat').write_text('IDE pc:/data/maps/manhat/manhat01.ide\n')
    (root / 'common' / 'data' / 'images.txt').write_text('pc/data/maps/manhat/manhat01 1\n')
    (root / 'pc' / 'data' / 'maps' / 'manhat' / 'manhat01.img').write_bytes(b'img')


class SnapshotTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.game = self.root / 'game'
        fake_game(self.game)
        self.planfile = self.root / 'plan.json'
        self.planfile.write_text(json.dumps(make_plan(self.root)))

    def test_version_and_backup_rollback_cycle(self):
        code, out, err = run('snapshot', self.game, self.root / 'before.json', '--plan', self.planfile,
                             '--backup-dir', self.root / 'backup')
        self.assertEqual(code, 0, err)
        info = json.loads(out)
        self.assertEqual(info['exe_file_version'], '1.0.7.0')
        self.assertEqual(len(info['backup']), 2)                        # gta.dat, images.txt (+ no existing targets)
        # simulate an OpenIV install: new IMG + IDE and an extra images.txt line
        (self.game / 'pc/data/maps/nk').mkdir()
        (self.game / 'pc/data/maps/nk/nk_demo.img').write_bytes(b'new')
        with open(self.game / 'common/data/images.txt', 'a') as f:
            f.write('pc/data/maps/nk/nk_demo 1\n')
        code, out, _ = run('check-restored', self.game, self.root / 'before.json')
        self.assertEqual(code, 3)
        self.assertTrue(json.loads(out)['blocking'])
        # rollback: restore backed-up text, remove added files
        shutil.copyfile(self.root / 'backup/common/data/images.txt', self.game / 'common/data/images.txt')
        shutil.rmtree(self.game / 'pc/data/maps/nk')
        code, out, _ = run('check-restored', self.game, self.root / 'before.json')
        self.assertEqual((code, json.loads(out)['restored']), (0, True))

    def test_never_writes_into_game(self):
        before = sorted(p.as_posix() for p in self.game.rglob('*'))
        self.assertEqual(run('snapshot', self.game, self.game / 's.json')[0], 1)
        self.assertEqual(run('snapshot', self.game, self.root / 's.json', '--backup-dir', self.game / 'bk')[0], 1)
        self.assertEqual(run('build-section', EX / 'section.json', EX, self.game / 'out', '--game', self.game)[0], 1)
        self.assertEqual(run('oiv', self.planfile, self.root, self.game / 'x.oiv', '--game', self.game)[0], 1)
        self.assertEqual(sorted(p.as_posix() for p in self.game.rglob('*')), before)

    def test_pe_version_missing(self):
        self.assertIsNone(gamestate.pe_file_version(b'MZ' + bytes(64)))
        (self.game / 'GTAIV.exe').unlink()
        self.assertEqual(run('snapshot', self.game, self.root / 's.json')[0], 1)


class CliTests(unittest.TestCase):
    def test_python_dash_m(self):
        with tempfile.TemporaryDirectory() as d:
            p = subprocess.run([sys.executable, '-m', 'nkgta4', 'build-section', str(EX / 'section.json'), str(EX), d],
                               cwd=str(helpers.ROOT), capture_output=True, text=True)
            self.assertEqual(p.returncode, 0, p.stderr)
            self.assertFalse(json.loads(p.stdout)['game_ready'])
        code, out, _ = run('hash', 'NK_A')
        self.assertEqual(json.loads(out)['NK_A'], '0x%08x' % gta_hash('nk_a'))
        code, out, _ = run('obj-check', EX / 'building.obj')
        self.assertEqual((code, json.loads(out)['triangles']), (0, 12))
        self.assertEqual(run('manifest-check', EX / 'building.obj')[0], 1)


if __name__ == '__main__':
    unittest.main()
