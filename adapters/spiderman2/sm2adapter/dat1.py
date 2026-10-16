"""DAT1 section container (format reference: Tkachov/Overstrike, DAT1/DAT1.cs).

Layout: 16-byte header `<IIIHH` (magic, type, total size, section count,
"unknowns" count), the section table (12 bytes per section: tag, offset,
size), `unknowns * 8` unknown bytes, a strings block, then the sections.
"""
import struct

from .errors import FormatError
from .limits import DEFAULT_LIMITS

DAT1_MAGIC = 0x44415431  # 'DAT1' little-endian read as uint32
_HEAD = struct.Struct('<IIIHH')
_ENTRY = struct.Struct('<III')


def parse_dat1(buf, limits=DEFAULT_LIMITS, *, require_exact_size=True):
    """Return (type_field, {tag: memoryview}) for a DAT1 blob.

    Rejects short buffers, wrong magic, a size field that disagrees with the
    buffer, section tables or sections that leave the buffer (or start inside
    the header, unknowns or strings area), and duplicate tags.
    """
    buf = memoryview(buf)
    if len(buf) < _HEAD.size:
        raise FormatError('DAT1 header truncated')
    magic, typ, size, count, unknowns = _HEAD.unpack_from(buf)
    if magic != DAT1_MAGIC:
        raise FormatError('bad DAT1 magic 0x%08x' % magic)
    if require_exact_size and size != len(buf):
        raise FormatError('DAT1 size field %d != buffer length %d' % (size, len(buf)))
    if size > len(buf) or size < _HEAD.size:
        raise FormatError('DAT1 size field out of range')
    if count > limits.max_sections:
        raise FormatError('too many DAT1 sections: %d' % count)
    table_end = _HEAD.size + count * _ENTRY.size
    header_end = table_end + unknowns * 8
    if header_end > size:
        raise FormatError('DAT1 section table out of bounds')
    sections = {}
    for i in range(count):
        tag, off, n = _ENTRY.unpack_from(buf, _HEAD.size + i * _ENTRY.size)
        if tag in sections:
            raise FormatError('duplicate DAT1 section tag 0x%08x' % tag)
        if off < header_end or off + n > size:
            raise FormatError('DAT1 section 0x%08x out of bounds' % tag)
        sections[tag] = buf[off:off + n]
    return typ, sections


def looks_like_dat1(data):
    """Cheap check: DAT1 magic and a size field equal to the data length."""
    return (len(data) >= _HEAD.size and struct.unpack_from('<I', data)[0] == DAT1_MAGIC
            and struct.unpack_from('<I', data, 8)[0] == len(data))
