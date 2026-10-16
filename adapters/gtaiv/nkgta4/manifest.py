"""Section manifest (`nk-gta4-manifest/1`): one NK section -> GTA IV map files.

NK stays canonical: the manifest references NK sources by release hash, tile
and component ID, relative path and SHA-256, and never contains geometry.
Every game-side value is a status block:

    {"status": "unknown"}                                   nothing asserted
    {"status": "hypothesis", "value": ..., "note": "..."}   proposed, with the test that will check it
    {"status": "verified",   "value": ..., "evidence": "..."} shown by a test that was run

Validation accepts `unknown`; building refuses any `unknown` value it would
have to write into a file. See docs/MANIFEST.md.
"""
import json
import math
import re
from pathlib import Path, PurePosixPath

from .errors import FormatError, UnsupportedError
from .ide import NAME

FORMAT = 'nk-gta4-manifest/1'
STATUSES = ('unknown', 'hypothesis', 'verified')
_SHA = re.compile(r'^[0-9a-f]{64}$')


def req(obj, key, where, types):
    if not isinstance(obj, dict) or key not in obj:
        raise FormatError('%s: missing "%s"' % (where, key))
    v = obj[key]
    if isinstance(v, bool) or not isinstance(v, types):
        raise FormatError('%s.%s has the wrong type' % (where, key))
    return v


def text(obj, key, where):
    v = req(obj, key, where, str)
    if not v.strip():
        raise FormatError('%s.%s is empty' % (where, key))
    return v


def sha(obj, key, where, optional=False):
    v = obj.get(key) if isinstance(obj, dict) else None
    if v is None and optional:
        return None
    if not isinstance(v, str) or not _SHA.match(v):
        raise FormatError('%s.%s must be a lowercase sha256' % (where, key))
    return v


def rel_path(v, where):
    if not isinstance(v, str) or not v or '\\' in v or '\0' in v:
        raise FormatError('%s must be a relative POSIX path' % where)
    p = PurePosixPath(v)
    if p.is_absolute() or (len(v) > 1 and v[1] == ':') or '..' in p.parts:
        raise FormatError('%s must stay inside its root' % where)
    return v


def status(obj, where, check=None):
    """Validate a status block; returns (status, value)."""
    s = req(obj, 'status', where, str)
    if s not in STATUSES:
        raise FormatError('%s.status must be one of %s' % (where, ', '.join(STATUSES)))
    v = obj.get('value')
    if s == 'unknown':
        if v is not None:
            raise FormatError('%s: status "unknown" must not carry a value' % where)
        return s, None
    if v is None:
        raise FormatError('%s: status "%s" needs a value' % (where, s))
    if check:
        check(v, where + '.value')
    text(obj, 'evidence' if s == 'verified' else 'note', where)
    return s, v


def known(block, where):
    """Value of a status block that a build needs; refuses unknown."""
    if block['status'] == 'unknown':
        raise UnsupportedError('%s is unknown; record a hypothesis (with a note) or a verified value first' % where)
    return block['value']


def _is_text(v, w):
    if not isinstance(v, str) or not v.strip():
        raise FormatError('%s must be text' % w)


def _matrix(v, w):
    if (not isinstance(v, list) or len(v) != 16
            or not all(isinstance(x, (int, float)) and not isinstance(x, bool) and math.isfinite(x) for x in v)):
        raise FormatError('%s must be 16 finite numbers (row-major 4x4)' % w)
    if v[12:16] != [0, 0, 0, 1]:
        raise FormatError('%s must be affine (last row 0 0 0 1)' % w)


def _int_pair(v, w):
    if not isinstance(v, list) or len(v) != 2 or any(isinstance(x, bool) or not isinstance(x, int) for x in v):
        raise FormatError('%s must be two integers' % w)


def _placement(v, w):
    if not isinstance(v, dict):
        raise FormatError('%s must be an object' % w)
    for k in ('flags', 'lod', 'unknown_int'):
        if isinstance(v.get(k), bool) or not isinstance(v.get(k), int):
            raise FormatError('%s.%s must be an integer' % (w, k))
    uf = v.get('unknown_float')
    if isinstance(uf, bool) or not isinstance(uf, (int, float)) or not math.isfinite(uf):
        raise FormatError('%s.unknown_float must be a number' % w)


def _int(v, w):
    if isinstance(v, bool) or not isinstance(v, int):
        raise FormatError('%s must be an integer' % w)


def validate(doc):
    if not isinstance(doc, dict) or doc.get('format') != FORMAT:
        raise FormatError('manifest "format" must be %r' % FORMAT)
    section = text(doc, 'section_id', 'manifest')
    if not NAME.match(section):
        raise FormatError('section_id must be 1-63 letters, digits or _ (it names output files)')
    nk = req(doc, 'nk', 'manifest', dict)
    text(nk, 'release', 'nk')
    sha(nk, 'release_sha256', 'nk')
    sha(nk, 'audit_sha256', 'nk', optional=True)
    for k in ('units', 'axes', 'origin'):
        status(req(req(nk, 'frame', 'nk', dict), k, 'nk.frame', dict), 'nk.frame.' + k, _is_text)
    tgt = req(doc, 'target', 'manifest', dict)
    if text(tgt, 'game', 'target') != 'GTAIV':
        raise UnsupportedError('only target.game "GTAIV" is supported (not GTA V or older games)')
    text(tgt, 'exe_version', 'target')
    sha(tgt, 'exe_sha256', 'target', optional=True)
    for k in ('units', 'axes', 'handedness'):
        status(req(req(tgt, 'frame', 'target', dict), k, 'target.frame', dict), 'target.frame.' + k, _is_text)
    status(req(doc, 'nk_to_game', 'manifest', dict), 'nk_to_game', _matrix)

    comps = req(doc, 'components', 'manifest', list)
    if not comps:
        raise FormatError('manifest has no components')
    seen, names = set(), set()
    for i, c in enumerate(comps):
        w = 'components[%d]' % i
        cnk = req(c, 'nk', w, dict)
        key = (text(cnk, 'tile_id', w + '.nk'), text(cnk, 'component_id', w + '.nk'))
        if key in seen:
            raise FormatError('%s: NK component %s/%s listed twice' % (w, *key))
        seen.add(key)
        text(cnk, 'layer', w + '.nk')
        rel_path(text(cnk, 'source', w + '.nk'), w + '.nk.source')
        sha(cnk, 'source_sha256', w + '.nk')
        render = req(c, 'render', w, dict)
        rel_path(text(render, 'obj', w + '.render'), w + '.render.obj')
        sha(render, 'sha256', w + '.render')
        model = req(c, 'model', w, dict)
        name = text(model, 'name', w + '.model')
        if not NAME.match(name) or name.lower() in names:
            raise FormatError('%s.model.name must be a unique 1-63 character identifier' % w)
        names.add(name.lower())
        if not NAME.match(text(model, 'txd', w + '.model')):
            raise FormatError('%s.model.txd must be an identifier' % w)
        dd = req(model, 'draw_distance', w + '.model', (int, float))
        if not math.isfinite(dd) or dd <= 0:
            raise FormatError('%s.model.draw_distance must be > 0' % w)
        status(req(c, 'wdd', w, dict), w + '.wdd', _is_text)
        status(req(c, 'ide_flags', w, dict), w + '.ide_flags', _int_pair)
        status(req(c, 'placement', w, dict), w + '.placement', _placement)
        status(req(c, 'lod_parent', w, dict), w + '.lod_parent', _is_text)
        for j, m in enumerate(req(c, 'materials', w, list)):
            mw = '%s.materials[%d]' % (w, j)
            text(m, 'nk_material', mw)
            status(m, mw, _is_text)
        col = req(c, 'collision', w, dict)
        src = text(col, 'source', w + '.collision')
        if src not in ('render', 'separate'):
            raise FormatError('%s.collision.source must be "render" or "separate"' % w)
        if src == 'separate':
            rel_path(text(col, 'obj', w + '.collision'), w + '.collision.obj')
            sha(col, 'sha256', w + '.collision')
        status(req(col, 'surface', w + '.collision', dict), w + '.collision.surface', _int)
        status(req(col, 'outcome', w + '.collision', dict), w + '.collision.outcome', _is_text)
    return {'section_id': section, 'components': len(comps), 'nk_to_game': doc['nk_to_game']['status']}


def load(path):
    try:
        doc = json.loads(Path(path).read_text(encoding='utf-8'))
    except ValueError as e:
        raise FormatError('manifest is not valid JSON: %s' % e) from None
    return doc, validate(doc)
