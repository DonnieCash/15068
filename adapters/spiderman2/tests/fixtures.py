"""Builders for synthetic TOC / DSAR / STG data. Nothing here is game content."""
import struct
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))  # run from any directory

from sm2adapter import toc as T  # noqa: E402

try:
    import lz4.block
except ImportError:  # tests needing it are skipped
    lz4 = None


def dat1(sections, size_override=None, unknowns=0):
    """sections: list of (tag, bytes). Returns a DAT1 blob. `unknowns` adds that
    many 8-byte unknown records after the section table, as real files may."""
    table = 16 + 12 * len(sections) + 8 * unknowns
    body, entries, off = b'', [], table
    for tag, data in sections:
        entries.append(struct.pack('<III', tag, off, len(data)))
        body += data + bytes((-len(data)) % 4)
        off += len(data) + (-len(data)) % 4
    total = table + len(body)
    head = struct.pack('<IIIHH', 0x44415431, 0, total if size_override is None else size_override,
                       len(sections), unknowns)
    return head + b''.join(entries) + bytes(8 * unknowns) + body


def model_payload(tag=0x1234, n=40):
    return dat1([(tag, bytes(range(n % 256)) or b'\0')])


def asset_header(pairs=1, extra=4):
    return struct.pack('<I', 7) + struct.pack('<BBH', 0, pairs, extra) + bytes(pairs * 8 + extra)


def toc_bytes(assets, spans, archives, headers=b'\0' * 16, *, extra_sections=(), length_delta=0):
    """assets: [(asset_id, size, archive_index, offset, header_offset)]."""
    ids = b''.join(struct.pack('<Q', a[0]) for a in assets)
    meta = b''.join(struct.pack('<IIIi', a[1], a[2], a[3], a[4]) for a in assets)
    sp = b''.join(struct.pack('<II', *s) for s in spans)
    arch = b''.join(n.encode().ljust(T.ARCHIVE_NAME_LEN, b'\0') + bytes(T.ARCHIVE_RECORD - T.ARCHIVE_NAME_LEN)
                    for n in archives)
    blob = dat1([(T.TAG_IDS, ids), (T.TAG_META, meta), (T.TAG_SPANS, sp), (T.TAG_ARCHIVES, arch),
                 (T.TAG_HEADERS, headers)] + list(extra_sections))
    return struct.pack('<II', T.TOC_MAGIC, len(blob) + length_delta) + blob


def dsar_bytes(raw_chunks, kind=3):
    """One DSAR block per chunk: kind 3 LZ4-compresses it; any other kind stores it as given."""
    table_end = 32 + 32 * len(raw_chunks)
    table, data, raw_off = b'', b'', 0
    for chunk in raw_chunks:
        comp = lz4.block.compress(chunk, store_size=False) if kind == 3 else chunk
        table += struct.pack('<QQIIB', raw_off, table_end + len(data), len(chunk), len(comp), kind) + bytes(7)
        data += comp
        raw_off += len(chunk)
    head = b'DSAR' + bytes(8) + struct.pack('<I', table_end) + bytes(16)
    return head + table + data


def make_game(root, *, hydrant=None, other=None):
    """Write a synthetic game dir. Layout:
    asset 0: hydrant model, asset 1: other model (same raw archive, 2 blocks),
    asset 2: duplicate of asset 0's ID (different offset), asset 3: unspanned.
    Spans: (0,2) and (1,2) -> entry 1 is in two spans."""
    root = Path(root)
    hydrant = hydrant or model_payload(0x1111, 60)
    other = other or model_payload(0x2222, 120)
    raw = hydrant + other + hydrant
    half = len(raw) // 2
    (root / 'archives').mkdir(parents=True, exist_ok=True)
    (root / 'archives' / 'a.dsar').write_bytes(dsar_bytes([raw[:half], raw[half:]]))
    hdr = asset_header()
    assets = [
        (0xAAAA0000000000AA, len(hydrant), 0, 0, 0),
        (0xBBBB0000000000BB, len(other), 0, len(hydrant), -1),
        (0xAAAA0000000000AA, len(hydrant), 0, len(hydrant) + len(other), 0),
        (0xCCCC0000000000CC, 8, 0, 0, -1),
    ]
    (root / 'toc').write_bytes(toc_bytes(assets, [(0, 2), (1, 2)], ['archives\\a.dsar'], headers=hdr))
    return {'hydrant': hydrant, 'other': other, 'header': hdr}
