"""Write a :class:`Volume` as a Sponge Schematic v2 ``.schem`` file.

Spec: https://github.com/SpongePowered/Schematic-Specification (version 2).
The file is gzip-compressed NBT whose root compound is named ``Schematic`` and
contains ``Width``/``Height``/``Length`` shorts, a ``Palette`` compound and a
varint-encoded ``BlockData`` byte array indexed by
``x + z * Width + y * Width * Length``.
"""

from __future__ import annotations

from array import array
from typing import List

from . import nbt
from .volume import Volume

# Minecraft world data version stored in the schematic.  3465 == 1.20.1, a
# widely supported release; WorldEdit/FAWE accept schematics across versions.
DEFAULT_DATA_VERSION = 3465
SPONGE_VERSION = 2


def encode_varint(value: int) -> bytes:
    """Unsigned LEB128 varint, as used for Sponge BlockData entries."""
    if value < 0:
        raise ValueError("Palette indices are non-negative")
    out = bytearray()
    while True:
        byte = value & 0x7F
        value >>= 7
        if value:
            out.append(byte | 0x80)
        else:
            out.append(byte)
            return bytes(out)


def decode_varints(data: bytes) -> List[int]:
    """Decode a stream of unsigned varints (used in tests)."""
    out: List[int] = []
    value = 0
    shift = 0
    for byte in data:
        value |= (byte & 0x7F) << shift
        if byte & 0x80:
            shift += 7
        else:
            out.append(value)
            value = 0
            shift = 0
    return out


def build_block_data(vol: Volume) -> bytes:
    # vol.data is already laid out as (y * Length + z) * Width + x.
    data = vol.data
    if not len(data):
        return b""
    # Fast path: when every palette index fits in 7 bits, its varint encoding
    # is the single byte equal to the value itself.  Our material palette is
    # well under 128 entries, so this is the common case.
    if max(data) < 0x80:
        return array("B", data).tobytes()
    out = bytearray()
    for idx in data:
        out += encode_varint(idx)
    return bytes(out)


def schematic_nbt(vol: Volume, name: str = "New Kensington Digital Twin",
                  data_version: int = DEFAULT_DATA_VERSION,
                  author: str = "newken_twin") -> dict:
    if vol.width > 0xFFFF or vol.height > 0xFFFF or vol.length > 0xFFFF:
        raise ValueError("Schematic dimensions exceed unsigned-short range")

    palette_dict = vol.palette.as_dict()
    palette_nbt = {block: nbt.Int(idx) for block, idx in palette_dict.items()}

    metadata = {
        "Name": nbt.String(name),
        "Author": nbt.String(author),
        "WEOffsetX": nbt.Int(0),
        "WEOffsetY": nbt.Int(0),
        "WEOffsetZ": nbt.Int(0),
    }

    root = {
        "Version": nbt.Int(SPONGE_VERSION),
        "DataVersion": nbt.Int(data_version),
        "Metadata": metadata,
        "Width": nbt.Short(vol.width),
        "Height": nbt.Short(vol.height),
        "Length": nbt.Short(vol.length),
        "Offset": nbt.IntArray([0, 0, 0]),
        "PaletteMax": nbt.Int(len(palette_dict)),
        "Palette": palette_nbt,
        "BlockData": nbt.ByteArray(build_block_data(vol)),
    }
    return root


def write_schematic(path: str, vol: Volume, **kwargs) -> None:
    root = schematic_nbt(vol, **kwargs)
    nbt.write_nbt_file(path, "Schematic", root, gzipped=True)
