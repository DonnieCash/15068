"""Render a top-down PNG preview of a built volume — a quick "map" of the twin.

The PNG encoder is hand-rolled on top of :mod:`zlib`/:mod:`struct` so there is
no Pillow dependency.  Each pixel is coloured by the topmost non-air block in
its column, with a little height shading so the skyline reads.
"""

from __future__ import annotations

import struct
import zlib
from typing import Dict, Tuple

from .volume import Volume

RGB = Tuple[int, int, int]

# Colour lookup by block id.  Anything unknown falls back to a neutral grey.
BLOCK_COLORS: Dict[str, RGB] = {
    "minecraft:air": (135, 206, 235),          # sky (open ground shows terrain)
    "minecraft:grass_block": (96, 156, 76),
    "minecraft:moss_block": (74, 126, 56),
    "minecraft:water": (54, 108, 196),
    "minecraft:gravel": (130, 126, 120),
    "minecraft:dirt": (122, 86, 60),
    "minecraft:gray_concrete": (84, 88, 92),
    "minecraft:black_concrete": (32, 33, 35),
    "minecraft:light_gray_concrete": (160, 162, 162),
    "minecraft:smooth_stone": (160, 160, 160),
    "minecraft:green_concrete": (60, 110, 70),
    "minecraft:stone_bricks": (128, 128, 128),
    "minecraft:bricks": (150, 82, 64),
    "minecraft:white_concrete": (220, 222, 224),
    "minecraft:smooth_sandstone": (224, 210, 160),
    "minecraft:terracotta": (152, 94, 68),
    "minecraft:red_terracotta": (142, 60, 46),
    "minecraft:light_blue_stained_glass": (140, 190, 220),
    "minecraft:deepslate_tiles": (60, 62, 70),
    "minecraft:copper_block": (190, 110, 70),
    "minecraft:oak_log": (104, 78, 48),
    "minecraft:oak_leaves": (62, 110, 46),
    "minecraft:gold_block": (240, 206, 70),
    "minecraft:sea_lantern": (236, 240, 230),
    "minecraft:iron_block": (200, 200, 204),
}
DEFAULT_COLOR: RGB = (170, 170, 170)


def _top_color(vol: Volume, x: int, z: int,
               id_to_block) -> Tuple[RGB, int]:
    for y in range(vol.height - 1, -1, -1):
        idx = vol.get_index(x, y, z)
        if idx:
            block = id_to_block[idx]
            return BLOCK_COLORS.get(block, DEFAULT_COLOR), y
    return BLOCK_COLORS["minecraft:air"], 0


def render_topdown(vol: Volume) -> Tuple[bytearray, int, int]:
    """Return (rgb_pixels, width, height) for a top-down view (north up)."""
    id_to_block = {idx: block for block, idx in vol.palette.as_dict().items()}
    w, h = vol.width, vol.length
    pixels = bytearray(3 * w * h)
    for z in range(h):
        for x in range(w):
            (r, g, b), y = _top_color(vol, x, z, id_to_block)
            # subtle height shading: taller -> brighter
            shade = 0.75 + 0.25 * min(1.0, y / max(1, vol.height - 1))
            i = 3 * (z * w + x)
            pixels[i] = int(r * shade)
            pixels[i + 1] = int(g * shade)
            pixels[i + 2] = int(b * shade)
    return pixels, w, h


def _png_chunk(tag: bytes, data: bytes) -> bytes:
    return (struct.pack(">I", len(data)) + tag + data
            + struct.pack(">I", zlib.crc32(tag + data) & 0xFFFFFFFF))


def write_png(path: str, pixels: bytearray, width: int, height: int) -> None:
    """Write 8-bit RGB pixels (row-major, top row first) to a PNG file."""
    raw = bytearray()
    stride = width * 3
    for row in range(height):
        raw.append(0)  # filter type 0 (None)
        raw += pixels[row * stride:(row + 1) * stride]
    compressed = zlib.compress(bytes(raw), 9)

    ihdr = struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0)  # 8-bit RGB
    with open(path, "wb") as f:
        f.write(b"\x89PNG\r\n\x1a\n")
        f.write(_png_chunk(b"IHDR", ihdr))
        f.write(_png_chunk(b"IDAT", compressed))
        f.write(_png_chunk(b"IEND", b""))


def write_preview(path: str, vol: Volume, scale: int = 1) -> None:
    pixels, w, h = render_topdown(vol)
    if scale > 1:
        pixels, w, h = _upscale(pixels, w, h, scale)
    write_png(path, pixels, w, h)


def _upscale(pixels: bytearray, w: int, h: int, scale: int):
    nw, nh = w * scale, h * scale
    out = bytearray(3 * nw * nh)
    for z in range(nh):
        sz = z // scale
        for x in range(nw):
            sx = x // scale
            si = 3 * (sz * w + sx)
            di = 3 * (z * nw + x)
            out[di:di + 3] = pixels[si:si + 3]
    return out, nw, nh
