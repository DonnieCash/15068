"""MSM2 `toc` file (Overstrike's TOC_I29 class, with the I30 asset-header layout).

Record layouts were re-checked against Tkachov/Overstrike commit 9f906ca (see
docs/PROVENANCE.md). They have not been checked against a real MSM2 `toc` by
this code; see docs/STATUS.md.
"""
import hashlib
import struct
from dataclasses import dataclass

from .dat1 import parse_dat1
from .errors import FormatError, UnsupportedError
from .limits import DEFAULT_LIMITS
from .paths import safe_join

TOC_MAGIC = 0x34e89035
TAG_IDS = 0x506d7b8a        # uint64 asset IDs, sorted within each span
TAG_META = 0x65bcf461       # (size, archive_index, offset, header_offset)
TAG_SPANS = 0xede8ada9      # (first asset index, count)
TAG_ARCHIVES = 0x398abff0   # 66-byte records, 40-byte NUL-padded name first
TAG_HEADERS = 0x654bded9    # asset header blobs

ARCHIVE_RECORD = 66
ARCHIVE_NAME_LEN = 40
_ID = struct.Struct('<Q')
_META = struct.Struct('<IIIi')
_SPAN = struct.Struct('<II')


@dataclass(frozen=True)
class Asset:
    index: int
    asset_id: int
    size: int           # bytes of the (uncompressed) asset inside its archive
    archive_index: int
    offset: int         # offset in the archive's uncompressed address space
    header_offset: int  # negative (-1 in practice): the asset has no header


class Toc:
    """Validated, lazily decoded TOC. Entry tables stay as memoryviews."""

    def __init__(self, sha256, ids, meta, spans, archive_names, headers, section_tags):
        self.sha256 = sha256
        self._ids = ids
        self._meta = meta
        self.spans = spans
        self.archive_names = archive_names
        self.headers = headers
        self.section_tags = section_tags
        self.count = len(ids) // _ID.size

    def asset(self, index):
        if not 0 <= index < self.count:
            raise IndexError(index)
        (asset_id,) = _ID.unpack_from(self._ids, index * _ID.size)
        size, arch, off, head = _META.unpack_from(self._meta, index * _META.size)
        return Asset(index, asset_id, size, arch, off, head)

    def span_of(self, index):
        """Index of the first span containing entry `index`, or None."""
        for i, (start, n) in enumerate(self.spans):
            if start <= index < start + n:
                return i
        return None

    def header(self, asset):
        return read_asset_header(self.headers, asset.header_offset)

    def span_report(self):
        """Counts of departures from the layout Overstrike's lookups assume
        (IDs sorted inside each span, each ID once per span, spans partitioning
        the entries). Informational: nothing here is rejected."""
        cov = bytearray(self.count)
        unsorted = dup = 0
        for start, n in self.spans:
            if n == 0:
                continue
            vals = struct.unpack_from('<%dQ' % n, self._ids, start * _ID.size)
            if any(a > b for a, b in zip(vals, vals[1:])):
                unsorted += 1
            dup += n - len(set(vals))
            for i in range(start, start + n):
                if cov[i] < 255:
                    cov[i] += 1
        return {'spans': len(self.spans), 'unsorted_spans': unsorted, 'duplicate_ids_in_span': dup,
                'entries_in_several_spans': sum(1 for c in cov if c > 1),
                'entries_in_no_span': cov.count(0)}


def read_asset_header(section, head, limits=DEFAULT_LIMITS):
    """Slice one asset header out of the headers section (b'' when head < 0).

    Layout (I30): u32 magic, u8 unknown, u8 pair count, u16 extra size, then
    8 bytes per pair and `extra` bytes.
    """
    if head < 0:
        return b''
    if head + 8 > len(section):
        raise FormatError('asset header offset out of bounds')
    _, pairs, extra = struct.unpack_from('<BBH', section, head + 4)
    n = 8 + pairs * 8 + extra
    if n > limits.max_header_bytes or head + n > len(section):
        raise FormatError('truncated asset header')
    return bytes(section[head:head + n])


def parse_toc(data, limits=DEFAULT_LIMITS):
    if len(data) > limits.max_toc_bytes:
        raise FormatError('TOC larger than limit')
    if len(data) < 8:
        raise FormatError('TOC truncated')
    magic, length = struct.unpack_from('<II', data)
    if magic != TOC_MAGIC:
        raise FormatError('bad TOC magic 0x%08x' % magic)
    if length != len(data) - 8:
        raise FormatError('TOC length field disagrees with file size')
    _, sec = parse_dat1(memoryview(data)[8:], limits)
    for tag in (TAG_IDS, TAG_META, TAG_SPANS, TAG_ARCHIVES, TAG_HEADERS):
        if tag not in sec:
            raise FormatError('TOC missing section 0x%08x' % tag)
    ids, meta, spans_raw, raw = sec[TAG_IDS], sec[TAG_META], sec[TAG_SPANS], sec[TAG_ARCHIVES]
    headers = sec[TAG_HEADERS]
    if len(ids) % _ID.size or len(meta) % _META.size or len(spans_raw) % _SPAN.size:
        raise FormatError('TOC table size is not a multiple of its record size')
    count = len(ids) // _ID.size
    if len(meta) // _META.size != count:
        raise FormatError('asset ID/metadata count mismatch')
    if len(raw) % ARCHIVE_RECORD:
        raise FormatError('unexpected archive record size')
    if len(raw) // ARCHIVE_RECORD > limits.max_archives:
        raise FormatError('too many archives')
    names = []
    for i in range(0, len(raw), ARCHIVE_RECORD):
        try:
            names.append(bytes(raw[i:i + ARCHIVE_NAME_LEN]).split(b'\0')[0].decode('ascii'))
        except UnicodeDecodeError:
            raise FormatError('non-ASCII archive name') from None
    if any('sargasso' in n for n in names):
        # Overstrike tells Rift Apart's 36-byte asset headers apart this way.
        raise UnsupportedError('Ratchet & Clank: Rift Apart TOC (I29 asset headers) is not supported')
    spans = list(_SPAN.iter_unpack(spans_raw))
    total = 0
    for start, n in spans:
        if start + n > count:
            raise FormatError('span exceeds asset array')
        total += n
    if total > limits.max_span_entries:
        raise FormatError('span entries exceed limit')
    seen = set()
    for i, (_size, arch, _off, head) in enumerate(_META.iter_unpack(meta)):
        if arch >= len(names):
            raise FormatError('entry %d: bad archive index %d' % (i, arch))
        if head >= len(headers):
            raise FormatError('entry %d: header offset out of bounds' % i)
        if head >= 0 and head not in seen:
            seen.add(head)
            read_asset_header(headers, head, limits)
    return Toc(hashlib.sha256(data).hexdigest(), ids, meta, spans, names, headers,
               ['0x%08x' % t for t in sec])


def load_toc(game, limits=DEFAULT_LIMITS):
    path = safe_join(game, 'toc')
    if path.stat().st_size > limits.max_toc_bytes:
        raise FormatError('TOC larger than limit')
    return parse_toc(path.read_bytes(), limits)
