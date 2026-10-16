"""Read-only snapshots of the game directory, for backup and rollback checks.

A snapshot records the `toc` (size, SHA-1, SHA-256), whether `toc.BAK`
exists (Overstrike's backup), the files under `d/mods` (Overstrike's install
target) and the size of every archive the TOC names. Nothing in the game
directory is written; `--backup-dir` copies `toc` to a directory outside it.
"""
import hashlib
import shutil
from pathlib import Path

from .errors import FormatError
from .paths import require_outside, safe_join
from .toc import load_toc


def _digests(path):
    h1, h256, n = hashlib.sha1(), hashlib.sha256(), 0
    with open(path, 'rb') as f:
        for chunk in iter(lambda: f.read(1 << 20), b''):
            h1.update(chunk)
            h256.update(chunk)
            n += len(chunk)
    return {'bytes': n, 'sha1': h1.hexdigest(), 'sha256': h256.hexdigest()}


def snapshot(game):
    game = Path(game)
    toc = load_toc(game)
    bak = safe_join(game, 'toc.BAK')
    mods = safe_join(game, 'd/mods')
    archives = []
    for name in toc.archive_names:
        p = safe_join(game, name)
        archives.append({'name': name, 'bytes': p.stat().st_size if p.is_file() else None})
    return {
        'format': 'nk-sm2-snapshot/1',
        'toc': _digests(safe_join(game, 'toc')),
        'toc_bak': _digests(bak) if bak.is_file() else None,
        'mods': sorted([{'name': p.relative_to(mods).as_posix(), 'bytes': p.stat().st_size}
                        for p in mods.rglob('*') if p.is_file()], key=lambda r: r['name']) if mods.is_dir() else None,
        'archives': archives,
    }


def backup_toc(game, backup_dir):
    """Copy `toc` to <backup_dir>/toc.<sha1> (outside the game) and verify the copy."""
    src = safe_join(game, 'toc')
    out_dir = require_outside(backup_dir, game)
    out_dir.mkdir(parents=True, exist_ok=True)
    want = _digests(src)
    dst = out_dir / ('toc.' + want['sha1'])
    shutil.copyfile(src, dst)
    if _digests(dst) != want:
        dst.unlink()
        raise FormatError('backup copy does not match the source toc')
    return str(dst), want


def compare(before, after):
    """Differences between two snapshots: (blocking, notes)."""
    blocking, notes = [], []
    if before['toc'] != after['toc']:
        blocking.append('toc differs (sha1 %s -> %s)' % (before['toc']['sha1'], after['toc']['sha1']))
    if before['archives'] != after['archives']:
        blocking.append('archive list or sizes differ')
    if before['toc_bak'] != after['toc_bak']:
        notes.append('toc.BAK changed (%s -> %s)' % (
            before['toc_bak'] and before['toc_bak']['sha1'], after['toc_bak'] and after['toc_bak']['sha1']))
    if before['mods'] != after['mods']:
        notes.append('d/mods contents differ (Overstrike leaves mod archives; the restored toc no longer references them)')
    return blocking, notes
