"""Adapter manifest: links NK tile/component IDs to MSM2 target assets.

NK stays canonical: the manifest only *references* NK sources (by relative
path and hash) and records how each component maps into the game. Every
convention that is not proven is carried as an explicit status instead of a
guessed value:

    "unknown"     nothing is asserted (value must be null)
    "hypothesis"  a value is proposed for testing, with a note saying why
    "verified"    a value is asserted, with evidence naming the test that showed it

See docs/MANIFEST.md for the field reference and examples/ for a synthetic file.
"""
import json
import math
import re
from pathlib import Path, PurePosixPath

from .candidates import parse_id
from .errors import FormatError, UnsupportedError

FORMAT = 'nk-sm2-manifest/1'
STATUSES = ('unknown', 'hypothesis', 'verified')
KINDS = ('building', 'road', 'sidewalk', 'bridge', 'lane', 'terrain', 'prop', 'other')
MODES = ('replace-model',)            # the only mode with a known install path (see docs/RESEARCH.md)
FUTURE_MODES = ('add-instance', 'replace-zone')
COLLISION = ('keep-original', 'generated', 'none')
HEADER_POLICIES = ('keep-original',)
_SHA256 = re.compile(r'^[0-9a-f]{64}$')
_SHA1 = re.compile(r'^[0-9a-fA-F]{40}$')


def _req(obj, key, where, types):
    if not isinstance(obj, dict) or key not in obj:
        raise FormatError('%s: missing "%s"' % (where, key))
    v = obj[key]
    if isinstance(v, bool) or not isinstance(v, types):
        raise FormatError('%s.%s has the wrong type' % (where, key))
    return v


def _text(obj, key, where, optional=False):
    if optional and (not isinstance(obj, dict) or obj.get(key) is None):
        return None
    v = _req(obj, key, where, str)
    if not v.strip():
        raise FormatError('%s.%s is empty' % (where, key))
    return v


def rel_path(value, where):
    """A portable path relative to some root: no absolute paths, drive letters, '..' or backslashes."""
    if not isinstance(value, str) or not value or '\\' in value or '\0' in value:
        raise FormatError('%s must be a relative POSIX path' % where)
    p = PurePosixPath(value)
    if p.is_absolute() or (len(value) > 1 and value[1] == ':') or '..' in p.parts:
        raise FormatError('%s must stay inside its root: %r' % (where, value))
    return value


def _sha256(obj, key, where, optional=False):
    v = obj.get(key) if isinstance(obj, dict) else None
    if v is None and optional:
        return None
    if not isinstance(v, str) or not _SHA256.match(v):
        raise FormatError('%s.%s must be a lowercase sha256 hex digest' % (where, key))
    return v


def _status_block(obj, where, value_key, check_value):
    """Validate {"status", value_key, "evidence"/"note"} blocks."""
    status = _req(obj, 'status', where, str)
    if status not in STATUSES:
        raise FormatError('%s.status must be one of %s' % (where, ', '.join(STATUSES)))
    value = obj.get(value_key)
    if status == 'unknown':
        if value is not None:
            raise FormatError('%s: status "unknown" must not carry a %s' % (where, value_key))
        return status
    if value is None:
        raise FormatError('%s: status "%s" needs a %s' % (where, status, value_key))
    check_value(value, '%s.%s' % (where, value_key))
    need = 'evidence' if status == 'verified' else 'note'
    _text(obj, need, where)
    return status


def _matrix(value, where):
    if (not isinstance(value, list) or len(value) != 16
            or not all(isinstance(x, (int, float)) and not isinstance(x, bool) and math.isfinite(x) for x in value)):
        raise FormatError('%s must be 16 finite numbers (row-major 4x4)' % where)


def _any_text(value, where):
    if not isinstance(value, str) or not value.strip():
        raise FormatError('%s must be non-empty text' % where)


def validate(doc):
    """Validate a manifest dict; return a summary dict. Raises FormatError/UnsupportedError."""
    if not isinstance(doc, dict) or doc.get('format') != FORMAT:
        raise FormatError('manifest "format" must be %r' % FORMAT)
    _text(doc, 'section_id', 'manifest')

    nk = _req(doc, 'nk', 'manifest', dict)
    _text(nk, 'release', 'nk')
    _sha256(nk, 'audit_sha256', 'nk', optional=True)
    frame = _req(nk, 'frame', 'nk', dict)
    for key in ('units', 'axes', 'origin'):
        _status_block(_req(frame, key, 'nk.frame', dict), 'nk.frame.' + key, 'value', _any_text)

    target = _req(doc, 'target', 'manifest', dict)
    if _text(target, 'game', 'target') != 'MSM2':
        raise UnsupportedError('only target.game "MSM2" is supported')
    _text(target, 'game_version', 'target')
    if not _SHA1.match(_text(target, 'toc_sha1', 'target')):
        raise FormatError('target.toc_sha1 must be 40 hex digits')
    _sha256(target, 'toc_sha256', 'target', optional=True)
    game_frame = _req(target, 'frame', 'target', dict)
    for key in ('units', 'axes', 'handedness'):
        _status_block(_req(game_frame, key, 'target.frame', dict), 'target.frame.' + key, 'value', _any_text)

    world = _status_block(_req(doc, 'nk_to_game', 'manifest', dict), 'nk_to_game', 'matrix', _matrix)

    comps = _req(doc, 'components', 'manifest', list)
    if not comps:
        raise FormatError('manifest has no components')
    seen_nk, seen_target, summary = set(), {}, []
    for i, c in enumerate(comps):
        where = 'components[%d]' % i
        cnk = _req(c, 'nk', where, dict)
        key = (_text(cnk, 'tile_id', where + '.nk'), _text(cnk, 'component_id', where + '.nk'))
        if key in seen_nk:
            raise FormatError('%s: NK component %s/%s listed twice' % (where, key[0], key[1]))
        seen_nk.add(key)
        if _text(cnk, 'kind', where + '.nk') not in KINDS:
            raise FormatError('%s.nk.kind must be one of %s' % (where, ', '.join(KINDS)))
        rel_path(_text(cnk, 'source', where + '.nk'), where + '.nk.source')
        _sha256(cnk, 'source_sha256', where + '.nk')

        tgt = _req(c, 'target', where, dict)
        mode = _text(tgt, 'mode', where + '.target')
        if mode in FUTURE_MODES:
            raise UnsupportedError('%s: mode %r has no known install path yet (docs/RESEARCH.md)' % (where, mode))
        if mode not in MODES:
            raise FormatError('%s.target.mode must be one of %s' % (where, ', '.join(MODES)))
        span = _req(tgt, 'span', where + '.target', int)
        if not 0 <= span <= 255:
            raise FormatError('%s.target.span must be 0..255' % where)
        asset_id = parse_id(_text(tgt, 'asset_id', where + '.target'))
        if (span, asset_id) in seen_target:
            raise FormatError('%s: target %d/%016X is already used by components[%d]'
                              % (where, span, asset_id, seen_target[(span, asset_id)]))
        seen_target[(span, asset_id)] = i

        geo = c.get('geometry')
        if geo is not None:
            rel_path(_text(geo, 'file', where + '.geometry'), where + '.geometry.file')
            _sha256(geo, 'sha256', where + '.geometry')
            for k in ('vertices', 'triangles'):
                if _req(geo, k, where + '.geometry', int) < 0:
                    raise FormatError('%s.geometry.%s must be >= 0' % (where, k))
            if _text(geo, 'header_policy', where + '.geometry') not in HEADER_POLICIES:
                raise UnsupportedError('%s.geometry.header_policy: only "keep-original" is supported' % where)

        _status_block(_req(c, 'transform', where, dict), where + '.transform', 'matrix', _matrix)

        for j, m in enumerate(_req(c, 'materials', where, list)):
            mw = '%s.materials[%d]' % (where, j)
            _text(m, 'nk_material', mw)
            _status_block(m, mw, 'target_material', _any_text)

        col = _req(c, 'collision', where, dict)
        strategy = _text(col, 'strategy', where + '.collision')
        if strategy not in COLLISION:
            raise FormatError('%s.collision.strategy must be one of %s' % (where, ', '.join(COLLISION)))
        if strategy == 'generated':
            rel_path(_text(col, 'file', where + '.collision'), where + '.collision.file')
            _sha256(col, 'sha256', where + '.collision')
        status = _req(col, 'status', where + '.collision', str)
        if status not in STATUSES:
            raise FormatError('%s.collision.status must be one of %s' % (where, ', '.join(STATUSES)))
        if status != 'unknown':
            _text(col, 'evidence' if status == 'verified' else 'note', where + '.collision')

        summary.append({'tile_id': key[0], 'component_id': key[1], 'span': span,
                        'asset_id': '0x%016x' % asset_id, 'mode': mode, 'has_geometry': geo is not None,
                        'transform': c['transform']['status'], 'collision': '%s/%s' % (strategy, col['status'])})
    return {'section_id': doc['section_id'], 'components': summary, 'nk_to_game': world,
            'toc_sha1': target['toc_sha1'].lower()}


def load(path):
    try:
        doc = json.loads(Path(path).read_text(encoding='utf-8'))
    except ValueError as e:
        raise FormatError('manifest is not valid JSON: %s' % e) from None
    return doc, validate(doc)


def check_against_toc(doc, toc):
    """Refuse a manifest written for another game build or naming assets the TOC lacks."""
    if doc['target']['toc_sha1'].lower() != toc.sha1:
        raise FormatError('manifest targets toc sha1 %s, this game has %s' % (doc['target']['toc_sha1'], toc.sha1))
    want256 = doc['target'].get('toc_sha256')
    if want256 and want256 != toc.sha256:
        raise FormatError('manifest toc_sha256 does not match this game')
    found = []
    for i, c in enumerate(doc['components']):
        span, asset_id = c['target']['span'], parse_id(c['target']['asset_id'])
        index = toc.find(span, asset_id)
        if index is None:
            raise FormatError('components[%d]: %d/%016X is not in the TOC' % (i, span, asset_id))
        a = toc.asset(index)
        found.append({'component': i, 'index': index, 'archive': toc.archive_names[a.archive_index],
                      'offset': a.offset, 'bytes': a.size, 'header_offset': a.header_offset})
    return found
