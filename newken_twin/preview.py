"""Render a top-down PNG preview of a built volume — a quick "map" of the twin.

The PNG encoder is hand-rolled on top of :mod:`zlib`/:mod:`struct` so there is
no Pillow dependency.  Each pixel is coloured by the topmost non-air block in
its column, with a little height shading so the skyline reads.
"""

from __future__ import annotations

import struct
import zlib
from typing import Dict, Tuple

from .blocks import base_id
from .volume import Volume

RGB = Tuple[int, int, int]

# Colour lookup by *base* block id (block states are stripped first).  Anything
# unknown falls back to a neutral grey.
BLOCK_COLORS: Dict[str, RGB] = {
    "minecraft:air": (135, 206, 235),          # sky (open ground shows terrain)
    "minecraft:grass_block": (96, 156, 76),
    "minecraft:moss_block": (74, 126, 56),
    "minecraft:short_grass": (96, 156, 76),
    "minecraft:water": (54, 108, 196),
    "minecraft:gravel": (130, 126, 120),
    "minecraft:dirt": (122, 86, 60),
    "minecraft:dirt_path": (150, 124, 80),
    "minecraft:sand": (222, 210, 158),
    "minecraft:gray_concrete": (84, 88, 92),
    "minecraft:black_concrete": (32, 33, 35),
    "minecraft:light_gray_concrete": (160, 162, 162),
    "minecraft:yellow_concrete": (224, 196, 60),
    "minecraft:white_concrete": (220, 222, 224),
    "minecraft:red_concrete": (160, 56, 50),
    "minecraft:blue_concrete": (50, 76, 160),
    "minecraft:lime_concrete": (94, 168, 64),
    "minecraft:orange_concrete": (210, 120, 40),
    "minecraft:smooth_stone": (160, 160, 160),
    "minecraft:stone": (130, 130, 130),
    "minecraft:green_concrete": (60, 110, 70),
    "minecraft:stone_bricks": (128, 128, 128),
    "minecraft:polished_andesite": (148, 150, 148),
    "minecraft:polished_deepslate": (70, 70, 76),
    "minecraft:bricks": (150, 82, 64),
    "minecraft:smooth_sandstone": (224, 210, 160),
    "minecraft:terracotta": (152, 94, 68),
    "minecraft:light_gray_terracotta": (150, 122, 112),
    "minecraft:red_terracotta": (142, 60, 46),
    "minecraft:quartz_block": (232, 228, 220),
    "minecraft:quartz_pillar": (232, 228, 220),
    "minecraft:light_blue_stained_glass": (140, 190, 220),
    "minecraft:light_blue_stained_glass_pane": (140, 190, 220),
    "minecraft:glass": (200, 224, 230),
    "minecraft:deepslate_tiles": (60, 62, 70),
    "minecraft:deepslate_tile_stairs": (60, 62, 70),
    "minecraft:deepslate_tile_slab": (60, 62, 70),
    "minecraft:copper_block": (190, 110, 70),
    "minecraft:waxed_oxidized_copper": (84, 160, 132),
    "minecraft:dark_oak_planks": (66, 44, 24),
    "minecraft:dark_oak_stairs": (66, 44, 24),
    "minecraft:dark_oak_slab": (66, 44, 24),
    "minecraft:dark_prismarine": (40, 78, 66),
    "minecraft:oak_log": (104, 78, 48),
    "minecraft:birch_log": (200, 196, 180),
    "minecraft:spruce_log": (74, 56, 34),
    "minecraft:dark_oak_log": (52, 38, 22),
    "minecraft:oak_leaves": (62, 120, 46),
    "minecraft:birch_leaves": (110, 156, 70),
    "minecraft:spruce_leaves": (50, 90, 56),
    "minecraft:dark_oak_leaves": (46, 96, 40),
    "minecraft:gold_block": (240, 206, 70),
    "minecraft:sea_lantern": (236, 240, 230),
    "minecraft:lantern": (240, 196, 120),
    "minecraft:iron_block": (200, 200, 204),
    "minecraft:iron_bars": (140, 142, 146),
    "minecraft:cobblestone_wall": (120, 120, 120),
    "minecraft:oak_fence": (140, 110, 66),
    "minecraft:poppy": (190, 50, 40),
    "minecraft:dandelion": (220, 200, 60),
    "minecraft:cornflower": (90, 110, 200),
    "minecraft:cauldron": (70, 72, 76),
}
DEFAULT_COLOR: RGB = (170, 170, 170)


def _color_for(block: str) -> RGB:
    return BLOCK_COLORS.get(base_id(block), DEFAULT_COLOR)


def _highest_occupied_layer(vol: Volume) -> int:
    plane = vol.stride_y
    data = vol.data
    for y in range(vol.height - 1, -1, -1):
        if any(data[y * plane:(y + 1) * plane]):
            return y
    return 0


def render_topdown(vol: Volume) -> Tuple[bytearray, int, int]:
    """Return (rgb_pixels, width, height) for a top-down view (north up)."""
    id_to_block = {idx: block for block, idx in vol.palette.as_dict().items()}
    # Precompute a colour table indexed by palette id (with shading folded in
    # per pixel later); here we just resolve base colours once.
    color_of = {idx: _color_for(block) for idx, block in id_to_block.items()}
    w, h = vol.width, vol.length
    data = vol.data
    stride = vol.stride_y
    top = _highest_occupied_layer(vol)
    sky = BLOCK_COLORS["minecraft:air"]
    pixels = bytearray(3 * w * h)
    for z in range(h):
        zw = z * w
        for x in range(w):
            col0 = zw + x
            r = g = b = -1
            yy = top
            base = col0 + top * stride
            while yy >= 0:
                idx = data[base]
                if idx:
                    (r, g, b) = color_of[idx]
                    break
                base -= stride
                yy -= 1
            i = 3 * col0
            if r < 0:
                pixels[i] = sky[0]
                pixels[i + 1] = sky[1]
                pixels[i + 2] = sky[2]
            else:
                shade = 0.82 + 0.20 * (min(1.0, (yy - 4) / 42.0) if yy > 4 else 0.0)
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
