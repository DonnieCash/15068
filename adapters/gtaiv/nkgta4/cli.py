"""nkgta4 command line. Nothing here writes inside the game folder.

  hash NAME...                           GTA IV model-name hashes
  obj-check FILE                         validate an NK component OBJ
  manifest-check MANIFEST                validate a section manifest
  build-section MANIFEST STAGING OUT     IDE + WPL + local OBJs + collision intermediates
  ofscan FILE                            structure-only summary of an OpenIV openFormats file
  snapshot GAME OUT [--plan] [--backup-dir]   read-only state (+ verified backup outside the game)
  check-restored GAME SNAPSHOT           compare after rollback (exit 3 if not restored)
  oiv PLAN FILES OUT                     OpenIV Package 2.2 from an install plan
  verify-oiv FILE                        check a built .oiv
"""
import argparse
import json
import sys
import zipfile
import xml.etree.ElementTree as ET
from pathlib import Path

from . import gamestate, manifest, oiv, ofscan, section
from .errors import FormatError
from .jenkins import gta_hash
from .objmesh import parse_obj


def _game_guard(path, game):
    if game:
        gamestate.outside(path, game)


def cmd_hash(a):
    print(json.dumps({n: '0x%08x' % gta_hash(n) for n in a.names}, indent=2))


def cmd_obj_check(a):
    m = parse_obj(Path(a.file).read_text(encoding='utf-8'))
    lo, hi = m.bounds()
    print(json.dumps({'vertices': len(m.vertices), 'triangles': len(m.triangles),
                      'materials': sorted({x for x in m.materials if x}), 'bbox_min': lo, 'bbox_max': hi}, indent=2))


def cmd_manifest_check(a):
    print(json.dumps(manifest.load(a.manifest)[1], indent=2))


def cmd_build_section(a):
    _game_guard(a.out, a.game)
    doc, _ = manifest.load(a.manifest)
    report = section.build(doc, a.staging, a.out)
    print(json.dumps({'section_id': report['section_id'], 'game_ready': report['game_ready'],
                      'files': report['files'], 'external_steps': report['external_steps']}, indent=2))


def cmd_ofscan(a):
    print('\n'.join(ofscan.scan(Path(a.file).read_text(encoding='utf-8', errors='replace'))))


def cmd_snapshot(a):
    out = gamestate.outside(a.output, a.game)
    targets = gamestate.plan_targets(oiv.load_plan(a.plan)) if a.plan else ()
    snap = gamestate.snapshot(a.game, targets)
    if a.backup_dir:
        snap['backup'] = gamestate.backup(a.game, snap, a.backup_dir)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(snap, indent=2) + '\n')
    print(json.dumps({'exe_file_version': snap['exe']['file_version'], 'exe_sha256': snap['exe']['sha256'],
                      'text': snap['text'], 'maps_files': len(snap['maps']),
                      'backup': snap.get('backup')}, indent=2))


def cmd_check_restored(a):
    try:
        before = json.loads(Path(a.snapshot).read_text())
    except ValueError as e:
        raise FormatError('snapshot is not valid JSON: %s' % e) from None
    after = gamestate.snapshot(a.game, list(before.get('plan_targets') or {}))
    blocking, notes = gamestate.compare(before, after)
    print(json.dumps({'restored': not blocking, 'blocking': blocking, 'notes': notes}, indent=2))
    return 0 if not blocking else 3


def cmd_oiv(a):
    _game_guard(a.output, a.game)
    print(json.dumps(oiv.build(oiv.load_plan(a.plan), a.files, a.output), indent=2))


def cmd_verify_oiv(a):
    try:
        z = zipfile.ZipFile(a.file)
    except zipfile.BadZipFile as e:
        raise FormatError('not a zip: %s' % e) from None
    with z:
        names = set(z.namelist())
        if 'assembly.xml' not in names:
            raise FormatError('package has no assembly.xml')
        try:
            root = ET.fromstring(z.read('assembly.xml'))
        except ET.ParseError as e:
            raise FormatError('assembly.xml is not valid XML: %s' % e) from None
        if root.tag != 'package' or root.get('version') != '2.2' or root.get('target') != 'IV':
            raise FormatError('assembly.xml must be <package version="2.2" target="IV">')
        for node in ('metadata', 'colors', 'content'):
            if root.find(node) is None:
                raise FormatError('assembly.xml lacks <%s>' % node)
        sources = [e.get('source') for e in root.iter('add') if e.get('source')]
        missing = [s for s in sources if 'content/' + s not in names]
        if missing:
            raise FormatError('package lacks content files: %s' % ', '.join(missing))
        extra = sorted(n for n in names if n != 'assembly.xml' and n[len('content/'):] not in sources)
        archives = [(e.get('path'), e.get('type')) for e in root.iter('archive')]
        texts = [(e.get('path'), [x.text for x in e.findall('add')]) for e in root.iter('text')]
    print(json.dumps({'files': sorted(sources), 'unreferenced': extra, 'archives': archives, 'text_edits': texts}, indent=2))
    return 0 if not extra else 3


def build_parser():
    p = argparse.ArgumentParser(prog='nkgta4', description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = p.add_subparsers(dest='cmd', required=True)
    s = sub.add_parser('hash'); s.add_argument('names', nargs='+'); s.set_defaults(fn=cmd_hash)
    s = sub.add_parser('obj-check'); s.add_argument('file'); s.set_defaults(fn=cmd_obj_check)
    s = sub.add_parser('manifest-check'); s.add_argument('manifest'); s.set_defaults(fn=cmd_manifest_check)
    s = sub.add_parser('build-section'); s.add_argument('manifest'); s.add_argument('staging'); s.add_argument('out')
    s.add_argument('--game', help='refuse an output folder inside this game folder'); s.set_defaults(fn=cmd_build_section)
    s = sub.add_parser('ofscan'); s.add_argument('file'); s.set_defaults(fn=cmd_ofscan)
    s = sub.add_parser('snapshot'); s.add_argument('game'); s.add_argument('output')
    s.add_argument('--plan'); s.add_argument('--backup-dir'); s.set_defaults(fn=cmd_snapshot)
    s = sub.add_parser('check-restored'); s.add_argument('game'); s.add_argument('snapshot'); s.set_defaults(fn=cmd_check_restored)
    s = sub.add_parser('oiv'); s.add_argument('plan'); s.add_argument('files'); s.add_argument('output')
    s.add_argument('--game', help='refuse an output inside this game folder'); s.set_defaults(fn=cmd_oiv)
    s = sub.add_parser('verify-oiv'); s.add_argument('file'); s.set_defaults(fn=cmd_verify_oiv)
    return p


def main(argv=None):
    a = build_parser().parse_args(argv)
    try:
        return a.fn(a) or 0
    except (FormatError, OSError, UnicodeDecodeError) as e:
        print('error: %s' % e, file=sys.stderr)
        return 1
