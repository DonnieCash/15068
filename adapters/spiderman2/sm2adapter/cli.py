"""Command line: inventory | candidates | extract | package | unpack | compare. Game files are only read."""
import argparse
import collections
import hashlib
import json
import sys
from pathlib import Path

from . import candidates as cand
from . import dsar
from .dat1 import looks_like_dat1, parse_dat1
from .errors import FormatError
from .paths import require_outside, safe_join
from .stg import pack_stg, parse_stg
from .toc import load_toc, read_asset_header


def _atomic_write(path, write):
    """Write via a temp file so a failure leaves no partial output."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + '.tmp')
    try:
        with tmp.open('w') as f:
            write(f)
        tmp.replace(path)
    finally:
        tmp.unlink(missing_ok=True)


def _write_json(path, doc):
    _atomic_write(path, lambda f: f.write(json.dumps(doc, indent=2)))


def cmd_inventory(a):
    game = Path(a.game)
    out = require_outside(a.output, game)
    toc = load_toc(game)
    archives, errors = [], 0
    for name in toc.archive_names:
        path = safe_join(game, name)
        row = {'name': name, 'exists': path.is_file()}
        if row['exists']:
            row['bytes'] = path.stat().st_size
            try:
                with path.open('rb') as f:
                    if dsar.is_dsar(f):
                        row['compression_blocks'] = dict(collections.Counter(str(b.kind) for b in dsar.read_table(f)))
                    else:
                        row['compression'] = 'raw'
            except FormatError as e:
                row['error'] = str(e)
                errors += 1
        archives.append(row)
    doc = {'toc_sha256': toc.sha256, 'asset_entries': toc.count, 'spans': [list(s) for s in toc.spans],
           'span_report': toc.span_report(), 'section_tags': toc.section_tags, 'archives': archives}
    _write_json(out, doc)
    print('Assets:', toc.count, 'Archives:', len(archives), 'Missing:', sum(not r['exists'] for r in archives),
          'Errors:', errors)
    return 1 if errors else 0


def cmd_candidates(a):
    game = Path(a.game)
    out = require_outside(a.output, game)
    toc = load_toc(game)
    scan = cand.Scan(toc, cand.load_hashes(a.hashes), name_contains=a.name_contains,
                     include_unnamed=a.include_unnamed)

    def write(f):
        f.write('{"format": "sm2-candidates/1", "toc_sha256": "%s", "candidates": [' % toc.sha256)
        sep = '\n'
        for row in scan.rows():
            f.write(sep + json.dumps(row))
            sep = ',\n'
        f.write('\n], "stats": %s}\n' % json.dumps(scan.stats))

    _atomic_write(out, write)
    print(json.dumps(scan.stats))


def load_candidates(path):
    """Return (rows, toc_sha256 or None) from a candidates file or a bare list of rows."""
    try:
        doc = json.loads(Path(path).read_text())
    except ValueError as e:
        raise FormatError('candidates file is not valid JSON: %s' % e) from None
    rows = doc.get('candidates') if isinstance(doc, dict) else doc
    if not isinstance(rows, list):
        raise FormatError('candidates file has no candidate list')
    return [cand.validate_row(r) for r in rows], (doc.get('toc_sha256') if isinstance(doc, dict) else None)


def cmd_extract(a):
    game = Path(a.game)
    out = require_outside(a.output, game)
    rows, doc_sha = load_candidates(a.candidates)
    needle = a.name_contains.lower()
    rows = [r for r in rows if needle in (r.get('name') or '').lower()]
    if not rows:
        raise FormatError('no candidate matches %r' % a.name_contains)
    row = dict(min(rows, key=lambda r: (r['bytes'], r['index'])))
    path = safe_join(game, row['archive'])
    toc = load_toc(game)
    if doc_sha is not None and doc_sha != toc.sha256:
        raise FormatError('candidates were generated from a different TOC; regenerate them')
    cand.verify_against_toc(row, toc)
    with path.open('rb') as f:
        if dsar.is_dsar(f):
            blocks = dsar.read_table(f)
            payload = dsar.extract_range(f, row['offset'], row['bytes'], blocks=blocks)
            used = [{'offset': b.comp_offset, 'compressed': b.comp_size, 'uncompressed': b.raw_size}
                    for b in dsar.covering_blocks(blocks, row['offset'], row['bytes'])]
        else:
            payload, used = dsar.read_raw_range(f, row['offset'], row['bytes']), []
    header = read_asset_header(toc.headers, row['header_offset'])
    row.update(payload_sha256=hashlib.sha256(payload).hexdigest(), header_sha256=hashlib.sha256(header).hexdigest(),
               payload_is_dat1=looks_like_dat1(payload), blocks=used,
               status='raw extraction only; not converted or installable')
    out.mkdir(parents=True, exist_ok=True)
    (out / 'probe.payload.bin').write_bytes(payload)
    (out / 'probe.header.bin').write_bytes(header)
    _write_json(out / 'extraction.json', row)
    print(json.dumps(row, indent=2))


def cmd_package(a):
    probe = Path(a.probe)
    header = (probe / 'probe.header.bin').read_bytes()
    payload = (probe / 'probe.payload.bin').read_bytes()
    packed = pack_stg(header, payload)
    back = parse_stg(packed)
    if (back.header, back.payload) != (header, payload) or pack_stg(back.header, back.payload) != packed:
        raise FormatError('STG container round trip failed')
    out = Path(a.output)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_bytes(packed)
    print(json.dumps({'file': str(out), 'bytes': len(packed), 'sha256': hashlib.sha256(packed).hexdigest(),
                      'flags': back.flags, 'container_roundtrip': 'passed', 'geometry_roundtrip': 'not performed'},
                     indent=2))


def cmd_unpack(a):
    """Split an STG container, or a bare DAT1 blob, into probe.payload.bin / probe.header.bin."""
    data = Path(a.model).read_bytes()
    if looks_like_dat1(data):
        header, payload, kind = b'', data, 'bare DAT1 blob (no header)'
        parse_dat1(payload)
    else:
        stg = parse_stg(data)
        header, payload, kind = stg.header, stg.payload, 'STG flags=%d' % stg.flags
        if stg.texture_meta:
            print('note: texture meta (%d bytes) is not written' % len(stg.texture_meta), file=sys.stderr)
    out = Path(a.output)
    out.mkdir(parents=True, exist_ok=True)
    (out / 'probe.payload.bin').write_bytes(payload)
    (out / 'probe.header.bin').write_bytes(header)
    print(json.dumps({'input': kind, 'payload_bytes': len(payload), 'header_bytes': len(header),
                      'payload_sha256': hashlib.sha256(payload).hexdigest(),
                      'header_sha256': hashlib.sha256(header).hexdigest()}, indent=2))


def _probe_sections(probe):
    payload = (probe / 'probe.payload.bin').read_bytes()
    header = (probe / 'probe.header.bin').read_bytes()
    try:
        _, sections = parse_dat1(payload)
    except FormatError:
        sections = None
    return payload, header, sections


def cmd_compare(a):
    """Compare two probe directories (the output of `extract`). Exit 0 only if the
    payload and header are byte-identical; 3 if they differ (report on stdout)."""
    (pb, hb, sb), (pa, ha, sa) = _probe_sections(Path(a.before)), _probe_sections(Path(a.after))
    report = {'payload_identical': pb == pa, 'header_identical': hb == ha,
              'payload_bytes': [len(pb), len(pa)], 'header_bytes': [len(hb), len(ha)]}
    if sb is None or sa is None:
        report['sections'] = 'not comparable: %s is not a valid DAT1 blob' % ('before' if sb is None else 'after')
    else:
        def digest(v):
            return {'bytes': len(v), 'sha256': hashlib.sha256(v).hexdigest()}
        report['sections'] = {'0x%08x' % t: {'before': digest(sb[t]) if t in sb else None,
                                             'after': digest(sa[t]) if t in sa else None,
                                             'identical': t in sb and t in sa and sb[t] == sa[t]}
                              for t in sorted(set(sb) | set(sa))}
    identical = report['payload_identical'] and report['header_identical']
    report['verdict'] = 'identical' if identical else 'different'
    print(json.dumps(report, indent=2))
    return 0 if identical else 3


def build_parser():
    p = argparse.ArgumentParser(prog='sm2adapter', description=__doc__)
    sub = p.add_subparsers(dest='cmd', required=True)
    s = sub.add_parser('inventory', help='read the TOC and summarise archives')
    s.add_argument('game'); s.add_argument('output'); s.set_defaults(fn=cmd_inventory)
    s = sub.add_parser('candidates', help='resolve a hashes dictionary against the TOC')
    s.add_argument('game'); s.add_argument('hashes'); s.add_argument('output')
    s.add_argument('--name-contains', help='keep only names containing this text')
    s.add_argument('--include-unnamed', action='store_true',
                   help='also emit entries whose ID is not in the dictionary')
    s.set_defaults(fn=cmd_candidates)
    s = sub.add_parser('extract', help='extract the smallest matching asset (LZ4 or raw archives)')
    s.add_argument('game'); s.add_argument('candidates'); s.add_argument('output')
    s.add_argument('--name-contains', required=True); s.set_defaults(fn=cmd_extract)
    s = sub.add_parser('package', help='wrap an extracted payload/header as an STG container')
    s.add_argument('probe'); s.add_argument('output'); s.set_defaults(fn=cmd_package)
    s = sub.add_parser('unpack', help='split an STG (or bare DAT1) model file into probe files')
    s.add_argument('model'); s.add_argument('output'); s.set_defaults(fn=cmd_unpack)
    s = sub.add_parser('compare', help='compare two extracted probe directories byte for byte')
    s.add_argument('before'); s.add_argument('after'); s.set_defaults(fn=cmd_compare)
    return p


def main(argv=None):
    a = build_parser().parse_args(argv)
    try:
        return a.fn(a) or 0
    except (FormatError, OSError) as e:
        print('error: %s' % e, file=sys.stderr)
        return 1
