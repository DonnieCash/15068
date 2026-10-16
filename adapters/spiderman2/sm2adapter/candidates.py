"""Resolve a hashes dictionary against TOC entries into extraction candidates.

Every (span, asset ID) occurrence is kept: one row per (span, entry index), so
the same ID in several spans, the same ID at several entries, and an entry
reachable from several spans each produce rows. Nothing is deduplicated.
"""
import json
import re
from pathlib import Path

from .errors import FormatError

_HEX = re.compile(r'^(?:0x)?[0-9a-fA-F]{1,16}$')
_INT_FIELDS = ('index', 'archive_index', 'offset', 'bytes', 'header_offset')


def parse_id(value):
    """'0x1f' / '1F' (hex text) or a JSON integer (decimal) -> int in [0, 2**64)."""
    if isinstance(value, int) and not isinstance(value, bool):
        n = value
    elif isinstance(value, str) and _HEX.match(value.strip()):
        n = int(value.strip(), 16)
    else:
        raise FormatError('bad asset ID: %r' % (value,))
    if not 0 <= n < 1 << 64:
        raise FormatError('asset ID out of 64-bit range: %r' % (value,))
    return n


class _Pairs(list):
    """JSON object as (key, value) pairs, so duplicate keys stay visible."""


def load_hashes(path):
    """Return {asset_id: name}.

    Accepts text lines `<hex id> <name>` (`#` comments), JSON `{"<id>": "<name>"}`,
    or JSON `[{"id": ..., "name": ...}]`. Conflicting names for one ID are an error.
    """
    raw = Path(path).read_text(encoding='utf-8')
    pairs = []
    if raw.lstrip()[:1] in ('{', '['):
        try:
            doc = json.loads(raw, object_pairs_hook=_Pairs)
        except ValueError as e:
            raise FormatError('hashes JSON invalid: %s' % e) from None
        if isinstance(doc, _Pairs):
            pairs = [(parse_id(k), v) for k, v in doc]
        elif isinstance(doc, list):
            for r in doc:
                r = dict(r) if isinstance(r, _Pairs) else None
                if r is None or 'id' not in r or 'name' not in r:
                    raise FormatError('hashes list entries need "id" and "name"')
                pairs.append((parse_id(r['id']), r['name']))
        else:
            raise FormatError('hashes JSON must be an object or list')
    else:
        for n, line in enumerate(raw.splitlines(), 1):
            line = line.strip()
            if not line or line.startswith('#'):
                continue
            parts = line.split(None, 1)
            if len(parts) != 2:
                raise FormatError('hashes line %d: expected "<id> <name>"' % n)
            pairs.append((parse_id(parts[0]), parts[1].strip()))
    out = {}
    for asset_id, name in pairs:
        if not isinstance(name, str) or not name:
            raise FormatError('empty or non-string name for 0x%016x' % asset_id)
        if out.setdefault(asset_id, name) != name:
            raise FormatError('conflicting names for 0x%016x' % asset_id)
    return out


class Scan:
    """Iterate candidate rows with `rows()`; read `stats` once it is exhausted.

    Rows come ordered by span, then entry index; entries outside every span
    follow with span=None. Entries whose ID is not in `hashes` are skipped
    unless `include_unnamed`.
    """

    def __init__(self, toc, hashes, *, name_contains=None, include_unnamed=False):
        self.toc = toc
        self.hashes = hashes
        self.needle = name_contains.lower() if name_contains else None
        self.include_unnamed = include_unnamed
        self._stats = None

    @property
    def stats(self):
        if self._stats is None:
            raise RuntimeError('stats are available after rows() is exhausted')
        return self._stats

    def _row(self, span, index):
        a = self.toc.asset(index)
        name = self.hashes.get(a.asset_id)
        if name is None and not self.include_unnamed:
            return None
        if self.needle and (name is None or self.needle not in name.lower()):
            return None
        return {'asset_id': '0x%016x' % a.asset_id, 'name': name, 'index': index, 'span': span,
                'archive': self.toc.archive_names[a.archive_index], 'archive_index': a.archive_index,
                'offset': a.offset, 'bytes': a.size, 'header_offset': a.header_offset}

    def rows(self):
        toc = self.toc
        cov = bytearray(toc.count)
        ids, pairs, n_rows = set(), set(), 0
        order = [(s, i) for s, (start, n) in enumerate(toc.spans) for i in range(start, start + n)]
        for span, index in order:
            if cov[index] < 255:
                cov[index] += 1
            row = self._row(span, index)
            if row:
                n_rows += 1
                ids.add(row['asset_id'])
                pairs.add((span, row['asset_id']))
                yield row
        for index in range(toc.count):
            if not cov[index]:
                row = self._row(None, index)
                if row:
                    n_rows += 1
                    ids.add(row['asset_id'])
                    pairs.add((None, row['asset_id']))
                    yield row
        self._stats = {
            'toc_entries': toc.count, 'spans': len(toc.spans), 'rows': n_rows,
            'distinct_ids': len(ids), 'duplicate_id_rows': n_rows - len(ids),
            'duplicate_span_id_rows': n_rows - len(pairs),
            'entries_in_several_spans': sum(1 for c in cov if c > 1),
            'unspanned_entries': cov.count(0)}


def build_candidates(toc, hashes, *, name_contains=None, include_unnamed=False):
    """Convenience wrapper returning (rows, stats) for small result sets."""
    scan = Scan(toc, hashes, name_contains=name_contains, include_unnamed=include_unnamed)
    rows = list(scan.rows())
    return rows, scan.stats


def validate_row(row):
    """Type-check one candidate row read from a JSON file; returns it."""
    if not isinstance(row, dict):
        raise FormatError('candidate row must be an object')
    for k in _INT_FIELDS:
        v = row.get(k)
        if isinstance(v, bool) or not isinstance(v, int):
            raise FormatError('candidate field %r must be an integer' % k)
    if row['index'] < 0 or row['offset'] < 0 or row['bytes'] < 0 or row['archive_index'] < 0:
        raise FormatError('candidate has a negative index, offset or size')
    if not isinstance(row.get('archive'), str):
        raise FormatError('candidate field "archive" must be a string')
    if row.get('name') is not None and not isinstance(row['name'], str):
        raise FormatError('candidate field "name" must be a string or null')
    parse_id(row.get('asset_id'))
    return row


def verify_against_toc(row, toc):
    """Refuse a candidate that no longer matches the TOC (stale candidates file)."""
    if row['index'] >= toc.count:
        raise FormatError('candidate index %d is outside the TOC' % row['index'])
    a = toc.asset(row['index'])
    same = (parse_id(row['asset_id']), row['bytes'], row['archive_index'], row['offset'],
            row['header_offset']) == (a.asset_id, a.size, a.archive_index, a.offset, a.header_offset)
    if not same or row['archive'] != toc.archive_names[a.archive_index]:
        raise FormatError('candidate does not match the TOC; regenerate it with the candidates command')
