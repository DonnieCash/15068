"""Read-only snapshot of the GTA IV install, for version gating, backup and rollback checks.

Records: GTAIV.exe sha256 and the file version from its VS_FIXEDFILEINFO
block; sha256 of common/data/gta.dat and common/data/images.txt; every .img
and .ide under pc/data/maps (path and size); and the state of any paths named
by an install plan. Nothing in the game folder is written. `backup` copies the
text files the plan edits (and any existing target files) to a folder outside
the game and verifies each copy.
"""
import hashlib
import os
import shutil
import struct
from pathlib import Path

from .errors import FormatError

TEXT_FILES = ('common/data/gta.dat', 'common/data/images.txt')
_FIXED = b'\xbd\x04\xef\xfe'


def _resolve(game, rel):
    root = Path(game).resolve()
    p = (root / rel.replace('\\', '/')).resolve()
    if not p.is_relative_to(root):
        raise FormatError('path escapes the game folder: %s' % rel)
    return p


def outside(path, game):
    out = Path(os.path.abspath(path)).resolve()
    root = Path(game).resolve()
    if out == root or out.is_relative_to(root):
        raise FormatError('output must be outside the game folder')
    return out


def sha256_file(path):
    h = hashlib.sha256()
    with open(path, 'rb') as f:
        for chunk in iter(lambda: f.read(1 << 20), b''):
            h.update(chunk)
    return h.hexdigest()


def pe_file_version(data):
    """File version 'a.b.c.d' from the first VS_FIXEDFILEINFO, or None."""
    i = data.find(_FIXED)
    if i < 0 or i + 16 > len(data):
        return None
    ms, ls = struct.unpack_from('<II', data, i + 8)
    return '%d.%d.%d.%d' % (ms >> 16, ms & 0xFFFF, ls >> 16, ls & 0xFFFF)


def plan_targets(plan):
    return [plan['archive']['path']] + [f['target'] for f in plan['loose_files']] + [t['path'] for t in plan['text_edits']]


def snapshot(game, targets=()):
    game = Path(game)
    exe = _resolve(game, 'GTAIV.exe')
    if not exe.is_file():
        raise FormatError('GTAIV.exe not found in %s' % game)
    data = exe.read_bytes()
    snap = {'format': 'nk-gta4-snapshot/1',
            'exe': {'sha256': hashlib.sha256(data).hexdigest(), 'file_version': pe_file_version(data)},
            'text': {}, 'maps': [], 'plan_targets': {}}
    for rel in TEXT_FILES:
        p = _resolve(game, rel)
        snap['text'][rel] = sha256_file(p) if p.is_file() else None
    maps = _resolve(game, 'pc/data/maps')
    if maps.is_dir():
        snap['maps'] = sorted([[p.relative_to(game.resolve()).as_posix(), p.stat().st_size]
                               for p in maps.rglob('*') if p.is_file() and p.suffix.lower() in ('.img', '.ide')])
    for rel in targets:
        p = _resolve(game, rel)
        snap['plan_targets'][rel] = sha256_file(p) if p.is_file() else None
    return snap


def backup(game, snap, backup_dir):
    """Copy every existing text file and plan target recorded in `snap` to backup_dir; verify copies."""
    out = outside(backup_dir, game)
    copied, done = [], set()
    for rel, digest in list(snap['text'].items()) + list(snap['plan_targets'].items()):
        key = rel.replace('\\', '/').lower()
        if digest is None or key in done:
            continue
        done.add(key)
        dst = out / rel.replace('\\', '/')
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(_resolve(game, rel), dst)
        if sha256_file(dst) != digest:
            raise FormatError('backup of %s does not match the game file' % rel)
        copied.append(str(dst))
    return copied


def compare(before, after):
    blocking, notes = [], []
    if before['exe'] != after['exe']:
        blocking.append('GTAIV.exe differs')
    for rel in before['text']:
        if before['text'][rel] != after['text'].get(rel):
            blocking.append('%s differs' % rel)
    if before['maps'] != after['maps']:
        blocking.append('pc/data/maps .img/.ide files differ')
    for rel, digest in before.get('plan_targets', {}).items():
        if after.get('plan_targets', {}).get(rel, digest) != digest:
            blocking.append('%s differs' % rel)
    return blocking, notes
