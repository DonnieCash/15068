"""DSAR block archives, plus raw (non-DSAR) archives. Only LZ4 blocks are decoded.

Format reference: Tkachov/Overstrike, DAT1/DSAR.cs. A 32-byte header
(`DSAR`, version, block count, end of block table at offset 12, original
size, padding) precedes the block table; entries are 32 bytes:
`<QQIIB` + 7 bytes = raw_offset, compressed_offset, raw_size, compressed_size,
kind. Kind 2 is GDeflate, kind 3 is LZ4. Archives without the magic hold the
asset bytes directly at the TOC offset.
"""
import os
import struct
from dataclasses import dataclass

from .errors import FormatError, UnsupportedError
from .limits import DEFAULT_LIMITS

DSAR_MAGIC = b'DSAR'
HEADER_SIZE = 32
ENTRY_SIZE = 32
KIND_GDEFLATE = 2
KIND_LZ4 = 3
_ENTRY = struct.Struct('<QQIIB')


@dataclass(frozen=True)
class Block:
    raw_offset: int
    comp_offset: int
    raw_size: int
    comp_size: int
    kind: int


def _size(f):
    f.seek(0, os.SEEK_END)
    return f.tell()


def is_dsar(f):
    f.seek(0)
    return f.read(4) == DSAR_MAGIC


def read_table(f, limits=DEFAULT_LIMITS):
    """Return the blocks sorted by raw_offset, without empty blocks.

    Structural checks only (bounds, count, overlap); per-block size and ratio
    limits apply when a block is decompressed, so a full inventory does not
    reject kinds this module cannot decode.
    """
    size = _size(f)
    f.seek(0)
    head = f.read(HEADER_SIZE)
    if len(head) < HEADER_SIZE or head[:4] != DSAR_MAGIC:
        raise FormatError('expected DSAR')
    table_end = struct.unpack_from('<I', head, 12)[0]
    if not HEADER_SIZE <= table_end <= size or (table_end - HEADER_SIZE) % ENTRY_SIZE:
        raise FormatError('bad DSAR table')
    if (table_end - HEADER_SIZE) // ENTRY_SIZE > limits.max_dsar_blocks:
        raise FormatError('too many DSAR blocks')
    raw = f.read(table_end - HEADER_SIZE)
    if len(raw) != table_end - HEADER_SIZE:
        raise FormatError('DSAR table truncated')
    blocks = []
    for pos in range(0, len(raw), ENTRY_SIZE):
        b = Block(*_ENTRY.unpack_from(raw, pos))
        if b.comp_offset < table_end or b.comp_offset + b.comp_size > size:
            raise FormatError('invalid block bounds')
        if b.raw_size:
            blocks.append(b)
    blocks.sort(key=lambda b: b.raw_offset)
    for a, b in zip(blocks, blocks[1:]):
        if a.raw_offset + a.raw_size > b.raw_offset:
            raise FormatError('overlapping DSAR blocks')
    return blocks


def extract_range(f, start, nbytes, limits=DEFAULT_LIMITS, blocks=None):
    """Return `nbytes` uncompressed bytes beginning at raw offset `start`.

    Fails (never returns short data) on gaps, unsupported compression, bad
    decompression sizes, block size/ratio over the limits, or when `nbytes`
    exceeds the asset limit.
    """
    if nbytes < 0 or start < 0 or nbytes > limits.max_asset_bytes:
        raise FormatError('invalid or oversized asset range')
    if blocks is None:
        blocks = read_table(f, limits)
    end = start + nbytes
    out = bytearray()
    cursor = start
    for b in blocks:
        if b.raw_offset >= end:
            break
        if b.raw_offset + b.raw_size <= start:
            continue
        if b.raw_offset > cursor:
            raise FormatError('gap in DSAR coverage')
        plain = _decode(f, b, limits)
        lo = max(start - b.raw_offset, 0)
        hi = min(end - b.raw_offset, b.raw_size)
        out += plain[lo:hi]
        cursor = b.raw_offset + hi
    if len(out) != nbytes:
        raise FormatError('incomplete asset: got %d of %d bytes' % (len(out), nbytes))
    return bytes(out)


def read_raw_range(f, start, nbytes, limits=DEFAULT_LIMITS):
    """Bytes `[start, start+nbytes)` of a raw (non-DSAR) archive."""
    if nbytes < 0 or start < 0 or nbytes > limits.max_asset_bytes:
        raise FormatError('invalid or oversized asset range')
    if start + nbytes > _size(f):
        raise FormatError('asset range outside archive')
    f.seek(start)
    data = f.read(nbytes)
    if len(data) != nbytes:
        raise FormatError('archive truncated')
    return data


def covering_blocks(blocks, start, nbytes):
    end = start + nbytes
    return [b for b in blocks if b.raw_offset < end and b.raw_offset + b.raw_size > start]


def _decode(f, b, limits):
    if b.kind == KIND_GDEFLATE:
        raise UnsupportedError('GDeflate blocks (kind 2) are not supported')
    if b.kind != KIND_LZ4:
        raise UnsupportedError('unknown DSAR compression kind %d' % b.kind)
    if b.raw_size > limits.max_block_bytes:
        raise FormatError('block exceeds uncompressed size limit')
    if b.comp_size == 0 or b.raw_size > b.comp_size * limits.max_ratio:
        raise FormatError('block exceeds compression ratio limit')
    f.seek(b.comp_offset)
    comp = f.read(b.comp_size)
    if len(comp) != b.comp_size:
        raise FormatError('block data truncated')
    return _lz4(comp, b.raw_size)


def _lz4(comp, raw_size):
    try:
        import lz4.block
    except ImportError:
        raise UnsupportedError('the lz4 package is required (pip install -r requirements.txt)') from None
    try:
        plain = lz4.block.decompress(comp, uncompressed_size=raw_size)
    except Exception as e:
        raise FormatError('LZ4 decompression failed: %s' % e) from None
    if len(plain) != raw_size:
        raise FormatError('decompression size mismatch')
    return plain
