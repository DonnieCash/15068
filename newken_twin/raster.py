"""2D rasterisation primitives operating on integer block cells.

These are deliberately simple and dependency-free.  Each generator yields
``(x, z)`` integer cells, which the builder then extrudes vertically.
"""

from __future__ import annotations

import math
from typing import Iterable, Iterator, List, Tuple

Cell = Tuple[int, int]
Pt = Tuple[float, float]


def polygon_cells(points: List[Pt]) -> Iterator[Cell]:
    """Yield integer cells whose centre lies inside the polygon.

    Uses an even-odd scanline fill.  ``points`` is a list of (x, z) floats; the
    polygon is implicitly closed.
    """
    if len(points) < 3:
        return
    zs = [p[1] for p in points]
    z_min = int(round(min(zs)))
    z_max = int(round(max(zs)))
    n = len(points)
    for z in range(z_min, z_max + 1):
        zc = z + 0.5  # sample at the cell centre
        xs: List[float] = []
        for i in range(n):
            x1, z1 = points[i]
            x2, z2 = points[(i + 1) % n]
            # Does edge straddle the scanline?
            if (z1 <= zc < z2) or (z2 <= zc < z1):
                t = (zc - z1) / (z2 - z1)
                xs.append(x1 + t * (x2 - x1))
        xs.sort()
        for k in range(0, len(xs) - 1, 2):
            # Include cells whose centre (x + 0.5) lies within the span, the
            # same centre-sampling convention used for the Z scanline.
            x_start = math.ceil(xs[k] - 0.5)
            x_end = math.floor(xs[k + 1] - 0.5)
            for x in range(x_start, x_end + 1):
                yield (x, z)


def polygon_outline(points: List[Pt], width: int = 1) -> Iterator[Cell]:
    """Yield cells along the polygon's perimeter (closed)."""
    n = len(points)
    for i in range(n):
        yield from thick_line(points[i], points[(i + 1) % n], width)


def _bresenham(x0: int, z0: int, x1: int, z1: int) -> Iterator[Cell]:
    dx = abs(x1 - x0)
    dz = abs(z1 - z0)
    sx = 1 if x0 < x1 else -1
    sz = 1 if z0 < z1 else -1
    err = dx - dz
    while True:
        yield (x0, z0)
        if x0 == x1 and z0 == z1:
            break
        e2 = 2 * err
        if e2 > -dz:
            err -= dz
            x0 += sx
        if e2 < dx:
            err += dx
            z0 += sz


def disk_cells(cx: int, cz: int, radius: float) -> Iterator[Cell]:
    """Yield cells within ``radius`` blocks of (cx, cz)."""
    r = int(round(radius))
    r2 = radius * radius
    for dz in range(-r, r + 1):
        for dx in range(-r, r + 1):
            if dx * dx + dz * dz <= r2:
                yield (cx + dx, cz + dz)


def thick_line(p0: Pt, p1: Pt, width: int) -> Iterator[Cell]:
    """Yield cells for a line of the given pixel width using stamped disks."""
    radius = max(0.0, (width - 1) / 2.0)
    x0, z0 = int(round(p0[0])), int(round(p0[1]))
    x1, z1 = int(round(p1[0])), int(round(p1[1]))
    seen = set()
    for (cx, cz) in _bresenham(x0, z0, x1, z1):
        if width <= 1:
            if (cx, cz) not in seen:
                seen.add((cx, cz))
                yield (cx, cz)
        else:
            for cell in disk_cells(cx, cz, radius):
                if cell not in seen:
                    seen.add(cell)
                    yield cell


def polyline_cells(points: List[Pt], width: int) -> Iterator[Cell]:
    """Yield cells for a multi-segment line of constant width."""
    seen = set()
    for i in range(len(points) - 1):
        for cell in thick_line(points[i], points[i + 1], width):
            if cell not in seen:
                seen.add(cell)
                yield cell


def clamp_cells(cells: Iterable[Cell], width: int, length: int) -> Iterator[Cell]:
    """Drop cells outside the [0,width) x [0,length) grid."""
    for (x, z) in cells:
        if 0 <= x < width and 0 <= z < length:
            yield (x, z)
