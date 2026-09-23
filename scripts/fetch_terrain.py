"""Download real elevation for ZIP 15068 from the AWS Open Data terrain tiles.

Terrarium-encoded PNG tiles (Mapzen / AWS "elevation-tiles-prod", public
domain + attribution) are fetched at zoom 13 (~14 m/pixel here), decoded
(height = R*256 + G + B/256 - 32768) and stitched into data/raw/terrain.json
as a lon/lat grid the site builder resamples.
"""
import io
import json
import math
import urllib.request
import zlib
from pathlib import Path

Z = 13
BBOX = (-79.8218, 40.4948, -79.6283, 40.6439)
URL = "https://s3.amazonaws.com/elevation-tiles-prod/terrarium/{z}/{x}/{y}.png"
OUT = Path(__file__).resolve().parent.parent / "data" / "raw" / "terrain.json"


def tile_xy(lon, lat, z):
    n = 2 ** z
    x = (lon + 180) / 360 * n
    r = math.radians(lat)
    y = (1 - math.log(math.tan(r) + 1 / math.cos(r)) / math.pi) / 2 * n
    return x, y


def decode_png_rgb(data):
    """Minimal PNG decoder for 8-bit RGB, non-interlaced (what terrarium uses)."""
    assert data[:8] == b"\x89PNG\r\n\x1a\n"
    pos, idat, w = 8, b"", 0
    while pos < len(data):
        ln = int.from_bytes(data[pos:pos + 4], "big")
        typ = data[pos + 4:pos + 8]
        body = data[pos + 8:pos + 8 + ln]
        if typ == b"IHDR":
            w, h = int.from_bytes(body[:4], "big"), int.from_bytes(body[4:8], "big")
            assert body[8] == 8 and body[9] == 2, "expected 8-bit RGB"
        elif typ == b"IDAT":
            idat += body
        pos += 12 + ln
    raw = zlib.decompress(idat)
    bpp, stride = 3, w * 3
    rows, prev = [], bytearray(stride)
    for r in range(h):
        f = raw[r * (stride + 1)]
        line = bytearray(raw[r * (stride + 1) + 1:(r + 1) * (stride + 1)])
        for i in range(stride):
            a = line[i - bpp] if i >= bpp else 0
            b = prev[i]
            c = prev[i - bpp] if i >= bpp else 0
            if f == 1:
                line[i] = (line[i] + a) & 255
            elif f == 2:
                line[i] = (line[i] + b) & 255
            elif f == 3:
                line[i] = (line[i] + (a + b) // 2) & 255
            elif f == 4:
                p = a + b - c
                pa, pb, pc = abs(p - a), abs(p - b), abs(p - c)
                pr = a if pa <= pb and pa <= pc else (b if pb <= pc else c)
                line[i] = (line[i] + pr) & 255
        rows.append(line)
        prev = line
    return w, h, rows


def main():
    x0, y0 = tile_xy(BBOX[0], BBOX[3], Z)
    x1, y1 = tile_xy(BBOX[2], BBOX[1], Z)
    tx0, ty0, tx1, ty1 = int(x0), int(y0), int(x1), int(y1)
    nx, ny = tx1 - tx0 + 1, ty1 - ty0 + 1
    grid = [[0.0] * (nx * 256) for _ in range(ny * 256)]
    for ty in range(ty0, ty1 + 1):
        for tx in range(tx0, tx1 + 1):
            url = URL.format(z=Z, x=tx, y=ty)
            with urllib.request.urlopen(url, timeout=60) as r:
                w, h, rows = decode_png_rgb(r.read())
            oy, ox = (ty - ty0) * 256, (tx - tx0) * 256
            for j, line in enumerate(rows):
                g = grid[oy + j]
                for i in range(256):
                    R, G, B = line[3 * i], line[3 * i + 1], line[3 * i + 2]
                    g[ox + i] = round(R * 256 + G + B / 256 - 32768, 1)
            print("tile", tx, ty, flush=True)
    OUT.write_text(json.dumps({"z": Z, "tx0": tx0, "ty0": ty0,
                               "w": nx * 256, "h": ny * 256, "grid": grid}))
    print("wrote", OUT)


if __name__ == "__main__":
    main()
