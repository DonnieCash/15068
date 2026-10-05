"""Overstrike STG model container (version 0). Container only: no geometry conversion.

Layout (OverstrikeShared/STG/STG.cs): u32 magic 'STG' | version << 24, u32
flags, u32 header size, u32 texture-meta size, the header, zero padding to a
16-byte file offset, the texture meta, zero padding, then the raw asset
payload (a DAT1 blob for models). Overstrike's installers apply the header
only when INSTALL_HEADER is set and the texture meta only when
INSTALL_TEXTURE_META is set, so the flags are derived from what is present.
"""
import struct
from dataclasses import dataclass

from .dat1 import parse_dat1
from .errors import FormatError, UnsupportedError
from .limits import DEFAULT_LIMITS

STG_MAGIC = 0x475453
FLAG_INSTALL_HEADER = 1
FLAG_INSTALL_TEXTURE_META = 2
_KNOWN_FLAGS = FLAG_INSTALL_HEADER | FLAG_INSTALL_TEXTURE_META
_HEAD = struct.Struct('<IIII')


@dataclass(frozen=True)
class Stg:
    flags: int
    header: bytes
    texture_meta: bytes
    payload: bytes


def _align16(n):
    return (n + 15) // 16 * 16


def check_payload(payload, limits=DEFAULT_LIMITS):
    """The payload must be one well-formed DAT1 blob whose size field is its length."""
    try:
        parse_dat1(payload, limits)
    except FormatError as e:
        raise FormatError('payload is not a valid DAT1 blob: %s' % e) from None


def pack_stg(header, payload, texture_meta=b'', limits=DEFAULT_LIMITS):
    """Wrap header + payload (+ optional texture meta). Validates before packing."""
    header, payload, meta = bytes(header), bytes(payload), bytes(texture_meta)
    if len(header) > limits.max_header_bytes or len(meta) > limits.max_texture_meta_bytes:
        raise FormatError('header or texture meta too large')
    check_payload(payload, limits)
    flags = (FLAG_INSTALL_HEADER if header else 0) | (FLAG_INSTALL_TEXTURE_META if meta else 0)
    out = bytearray(_HEAD.pack(STG_MAGIC, flags, len(header), len(meta)))
    for part in (header, meta):
        out += part
        out += bytes(_align16(len(out)) - len(out))
    return bytes(out) + payload


def parse_stg(data, limits=DEFAULT_LIMITS):
    """Parse an STG into an `Stg`. Rejects unknown versions/flags, truncation,
    non-zero padding, a flag set for an empty part, and an invalid payload."""
    data = bytes(data)
    if len(data) < _HEAD.size:
        raise FormatError('STG truncated')
    word, flags, nh, nm = _HEAD.unpack_from(data)
    if word & 0xFFFFFF != STG_MAGIC:
        raise FormatError('bad STG magic')
    if word >> 24:
        raise UnsupportedError('unsupported STG version %d' % (word >> 24))
    if flags & ~_KNOWN_FLAGS:
        raise UnsupportedError('unsupported STG flags 0x%x' % flags)
    if nh > limits.max_header_bytes or nm > limits.max_texture_meta_bytes:
        raise FormatError('STG header or texture meta too large')
    if (flags & FLAG_INSTALL_HEADER and not nh) or (flags & FLAG_INSTALL_TEXTURE_META and not nm):
        raise FormatError('STG flag set for an empty part')
    pos, parts = _HEAD.size, []
    for n in (nh, nm):
        end = pos + n
        nxt = _align16(end)
        if nxt > len(data):
            raise FormatError('STG truncated')
        if any(data[end:nxt]):
            raise FormatError('non-zero STG padding')
        parts.append(data[pos:end])
        pos = nxt
    payload = data[pos:]
    check_payload(payload, limits)
    return Stg(flags, parts[0], parts[1], payload)
