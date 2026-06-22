"""A small, dependency-free NBT (Named Binary Tag) reader/writer.

This implements just enough of Mojang's NBT format to write (and read back,
for round-trip testing) a Sponge Schematic v2 file.  Everything here is pure
standard library so the digital-twin generator has no runtime dependencies.

NBT reference: https://minecraft.wiki/w/NBT_format
All numeric values are big-endian; strings are length-prefixed UTF-8.
"""

from __future__ import annotations

import gzip
import struct
from dataclasses import dataclass
from typing import BinaryIO, Dict, List as PyList, Union

# Tag type IDs
TAG_END = 0
TAG_BYTE = 1
TAG_SHORT = 2
TAG_INT = 3
TAG_LONG = 4
TAG_FLOAT = 5
TAG_DOUBLE = 6
TAG_BYTE_ARRAY = 7
TAG_STRING = 8
TAG_LIST = 9
TAG_COMPOUND = 10
TAG_INT_ARRAY = 11
TAG_LONG_ARRAY = 12


# --- Typed tag wrappers ---------------------------------------------------
# Python ints don't carry width information, so we wrap values to record the
# exact NBT type the writer should emit.

@dataclass
class Byte:
    value: int


@dataclass
class Short:
    value: int


@dataclass
class Int:
    value: int


@dataclass
class Long:
    value: int


@dataclass
class Float:
    value: float


@dataclass
class Double:
    value: float


@dataclass
class String:
    value: str


@dataclass
class ByteArray:
    # Stored as signed bytes per NBT, but we accept a bytes/bytearray payload.
    value: bytes


@dataclass
class IntArray:
    value: PyList[int]


@dataclass
class LongArray:
    value: PyList[int]


@dataclass
class List:
    item_type: int          # tag id of the contained elements
    items: PyList["Tag"]


# A Compound is just a dict of name -> Tag.
Compound = dict

Tag = Union[
    Byte, Short, Int, Long, Float, Double, String,
    ByteArray, IntArray, LongArray, List, Compound,
]


def _tag_id(tag: Tag) -> int:
    if isinstance(tag, Byte):
        return TAG_BYTE
    if isinstance(tag, Short):
        return TAG_SHORT
    if isinstance(tag, Int):
        return TAG_INT
    if isinstance(tag, Long):
        return TAG_LONG
    if isinstance(tag, Float):
        return TAG_FLOAT
    if isinstance(tag, Double):
        return TAG_DOUBLE
    if isinstance(tag, ByteArray):
        return TAG_BYTE_ARRAY
    if isinstance(tag, String):
        return TAG_STRING
    if isinstance(tag, List):
        return TAG_LIST
    if isinstance(tag, dict):
        return TAG_COMPOUND
    if isinstance(tag, IntArray):
        return TAG_INT_ARRAY
    if isinstance(tag, LongArray):
        return TAG_LONG_ARRAY
    raise TypeError(f"Unsupported tag type: {type(tag)!r}")


# --- Writing --------------------------------------------------------------

def _write_string(f: BinaryIO, s: str) -> None:
    data = s.encode("utf-8")
    if len(data) > 0xFFFF:
        raise ValueError("NBT string too long")
    f.write(struct.pack(">H", len(data)))
    f.write(data)


def _write_payload(f: BinaryIO, tag: Tag) -> None:
    if isinstance(tag, Byte):
        f.write(struct.pack(">b", _clamp(tag.value, -128, 127)))
    elif isinstance(tag, Short):
        f.write(struct.pack(">h", tag.value))
    elif isinstance(tag, Int):
        f.write(struct.pack(">i", tag.value))
    elif isinstance(tag, Long):
        f.write(struct.pack(">q", tag.value))
    elif isinstance(tag, Float):
        f.write(struct.pack(">f", tag.value))
    elif isinstance(tag, Double):
        f.write(struct.pack(">d", tag.value))
    elif isinstance(tag, ByteArray):
        f.write(struct.pack(">i", len(tag.value)))
        f.write(bytes(tag.value))
    elif isinstance(tag, String):
        _write_string(f, tag.value)
    elif isinstance(tag, List):
        f.write(struct.pack(">b", tag.item_type))
        f.write(struct.pack(">i", len(tag.items)))
        for item in tag.items:
            if _tag_id(item) != tag.item_type:
                raise TypeError("Heterogeneous NBT list")
            _write_payload(f, item)
    elif isinstance(tag, dict):
        for name, child in tag.items():
            f.write(struct.pack(">b", _tag_id(child)))
            _write_string(f, name)
            _write_payload(f, child)
        f.write(struct.pack(">b", TAG_END))
    elif isinstance(tag, IntArray):
        f.write(struct.pack(">i", len(tag.value)))
        for v in tag.value:
            f.write(struct.pack(">i", v))
    elif isinstance(tag, LongArray):
        f.write(struct.pack(">i", len(tag.value)))
        for v in tag.value:
            f.write(struct.pack(">q", v))
    else:
        raise TypeError(f"Unsupported tag type: {type(tag)!r}")


def _clamp(v: int, lo: int, hi: int) -> int:
    return max(lo, min(hi, v))


def write_nbt(root_name: str, root: Compound) -> bytes:
    """Serialise a compound as an uncompressed NBT byte string."""
    import io
    buf = io.BytesIO()
    buf.write(struct.pack(">b", TAG_COMPOUND))
    _write_string(buf, root_name)
    _write_payload(buf, root)
    return buf.getvalue()


def write_nbt_file(path: str, root_name: str, root: Compound,
                   gzipped: bool = True) -> None:
    raw = write_nbt(root_name, root)
    if gzipped:
        with gzip.open(path, "wb", compresslevel=6) as f:
            f.write(raw)
    else:
        with open(path, "wb") as f:
            f.write(raw)


# --- Reading (used by tests for round-trip validation) --------------------

class _Reader:
    def __init__(self, data: bytes):
        self.data = data
        self.pos = 0

    def read(self, n: int) -> bytes:
        chunk = self.data[self.pos:self.pos + n]
        if len(chunk) != n:
            raise EOFError("Unexpected end of NBT data")
        self.pos += n
        return chunk

    def _str(self) -> str:
        (length,) = struct.unpack(">H", self.read(2))
        return self.read(length).decode("utf-8")

    def _payload(self, tag_id: int):
        if tag_id == TAG_BYTE:
            return struct.unpack(">b", self.read(1))[0]
        if tag_id == TAG_SHORT:
            return struct.unpack(">h", self.read(2))[0]
        if tag_id == TAG_INT:
            return struct.unpack(">i", self.read(4))[0]
        if tag_id == TAG_LONG:
            return struct.unpack(">q", self.read(8))[0]
        if tag_id == TAG_FLOAT:
            return struct.unpack(">f", self.read(4))[0]
        if tag_id == TAG_DOUBLE:
            return struct.unpack(">d", self.read(8))[0]
        if tag_id == TAG_BYTE_ARRAY:
            (n,) = struct.unpack(">i", self.read(4))
            return self.read(n)
        if tag_id == TAG_STRING:
            return self._str()
        if tag_id == TAG_LIST:
            (item_type,) = struct.unpack(">b", self.read(1))
            (n,) = struct.unpack(">i", self.read(4))
            return [self._payload(item_type) for _ in range(n)]
        if tag_id == TAG_COMPOUND:
            out: Dict[str, object] = {}
            while True:
                (child_id,) = struct.unpack(">b", self.read(1))
                if child_id == TAG_END:
                    break
                name = self._str()
                out[name] = self._payload(child_id)
            return out
        if tag_id == TAG_INT_ARRAY:
            (n,) = struct.unpack(">i", self.read(4))
            return list(struct.unpack(">" + "i" * n, self.read(4 * n)))
        if tag_id == TAG_LONG_ARRAY:
            (n,) = struct.unpack(">i", self.read(4))
            return list(struct.unpack(">" + "q" * n, self.read(8 * n)))
        raise ValueError(f"Unknown tag id {tag_id}")

    def root(self):
        (tag_id,) = struct.unpack(">b", self.read(1))
        if tag_id != TAG_COMPOUND:
            raise ValueError("NBT root is not a compound")
        name = self._str()
        return name, self._payload(TAG_COMPOUND)


def read_nbt(data: bytes):
    """Parse uncompressed NBT, returning (root_name, plain_python_dict)."""
    return _Reader(data).root()


def read_nbt_file(path: str):
    with open(path, "rb") as f:
        head = f.read(2)
        f.seek(0)
        raw = gzip.decompress(f.read()) if head[:1] == b"\x1f" else f.read()
    return read_nbt(raw)
