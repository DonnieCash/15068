"""Containment checks for names read from archives and for output locations."""
import os
from pathlib import Path

from .errors import UnsafePathError


def safe_join(root, name):
    """Resolve an archive-relative `name` under `root`.

    TOC names use backslashes. Absolute paths, drive letters, NUL bytes, `..`
    components and symlinks that resolve outside `root` are rejected. The
    result need not exist.
    """
    root = Path(root).resolve()
    if not isinstance(name, str) or not name:
        raise UnsafePathError('empty archive path')
    if '\0' in name:
        raise UnsafePathError('NUL in archive path')
    rel = name.replace('\\', '/')
    if rel.startswith('/') or (len(rel) > 1 and rel[1] == ':'):
        raise UnsafePathError('absolute archive path: %r' % name)
    parts = [p for p in rel.split('/') if p not in ('', '.')]
    if not parts or '..' in parts:
        raise UnsafePathError('unsafe archive path: %r' % name)
    path = (root / Path(*parts)).resolve()
    if not path.is_relative_to(root):
        raise UnsafePathError('archive path escapes game directory: %r' % name)
    return path


def require_outside(output, game):
    """Refuse to write inside (or onto) the game directory."""
    out = Path(os.path.abspath(output)).resolve()
    game = Path(game).resolve()
    if out == game or out.is_relative_to(game) or game.is_relative_to(out):
        raise UnsafePathError('output must be outside the game directory')
    return out
