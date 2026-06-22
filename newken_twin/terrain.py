"""Terrain height model: the river valley New Kensington actually sits in.

New Kensington rises steeply from the east bank of the Allegheny.  We model
that by computing, for every block column, its distance to the river and
raising the ground inland, then adding a few octaves of value noise for gentle
hills.  Everything is integer block heights, computed with a fast two-pass
Chebyshev distance transform — no third-party libraries.
"""

from __future__ import annotations

import math
from array import array
from typing import Iterable, Set, Tuple

Cell = Tuple[int, int]

WATER_Y = 6           # river surface level
RIVERBED_DROP = 3     # how far below the surface the bed sits
BANK_HEIGHT = 1       # land just above the water at the shoreline
INLAND_SLOPE = 0.05   # blocks of rise per block of distance from water
MAX_RISE = 22         # cap on how high the valley walls climb
HILL_AMPLITUDE = 6    # extra relief from noise


class Heightmap:
    """Per-column ground surface height and a water mask."""

    def __init__(self, width: int, length: int):
        self.width = width
        self.length = length
        self.surface = array("h", bytes(2 * width * length))  # signed short
        self.is_water = bytearray(width * length)
        self._noise_seed = 1469  # deterministic

    def _i(self, x: int, z: int) -> int:
        return z * self.width + x

    def height(self, x: int, z: int) -> int:
        if 0 <= x < self.width and 0 <= z < self.length:
            return self.surface[self._i(x, z)]
        return WATER_Y

    def water(self, x: int, z: int) -> bool:
        if 0 <= x < self.width and 0 <= z < self.length:
            return bool(self.is_water[self._i(x, z)])
        return False

    def max_height(self) -> int:
        return max(self.surface) if len(self.surface) else WATER_Y

    # -- construction ------------------------------------------------------
    def build(self, water_cells: Iterable[Cell]) -> None:
        w, l = self.width, self.length
        dist = self._chebyshev_distance(set(water_cells))
        for z in range(l):
            base = z * w
            for x in range(w):
                i = base + x
                d = dist[i]
                if d == 0:
                    # river channel: carve a bed, mark water
                    self.surface[i] = WATER_Y - RIVERBED_DROP
                    self.is_water[i] = 1
                    continue
                rise = min(MAX_RISE, d * INLAND_SLOPE)
                hill = self._hills(x, z)
                h = WATER_Y + BANK_HEIGHT + rise + hill
                self.surface[i] = int(round(h))

    def _hills(self, x: int, z: int) -> float:
        # two octaves of smooth value noise
        n = (self._value_noise(x / 70.0, z / 70.0) * HILL_AMPLITUDE
             + self._value_noise(x / 23.0, z / 23.0) * (HILL_AMPLITUDE * 0.4))
        return n

    def _value_noise(self, fx: float, fz: float) -> float:
        x0, z0 = math.floor(fx), math.floor(fz)
        tx, tz = fx - x0, fz - z0
        v00 = self._lattice(x0, z0)
        v10 = self._lattice(x0 + 1, z0)
        v01 = self._lattice(x0, z0 + 1)
        v11 = self._lattice(x0 + 1, z0 + 1)
        sx = tx * tx * (3 - 2 * tx)
        sz = tz * tz * (3 - 2 * tz)
        a = v00 + sx * (v10 - v00)
        b = v01 + sx * (v11 - v01)
        return a + sz * (b - a)

    def _lattice(self, x: int, z: int) -> float:
        h = (x * 374761393 + z * 668265263 + self._noise_seed * 982451653)
        h = (h ^ (h >> 13)) * 1274126177
        h ^= (h >> 16)
        return (h & 0xFFFF) / 0xFFFF  # 0..1

    def _chebyshev_distance(self, sources: Set[Cell]) -> array:
        """Two-pass Chebyshev (chessboard) distance transform."""
        w, l = self.width, self.length
        INF = w + l + 10
        dist = array("i", [INF]) * (w * l)
        for (x, z) in sources:
            if 0 <= x < w and 0 <= z < l:
                dist[z * w + x] = 0
        # forward pass
        for z in range(l):
            base = z * w
            up = base - w
            for x in range(w):
                i = base + x
                d = dist[i]
                if x > 0 and dist[i - 1] + 1 < d:
                    d = dist[i - 1] + 1
                if z > 0:
                    if dist[up + x] + 1 < d:
                        d = dist[up + x] + 1
                    if x > 0 and dist[up + x - 1] + 1 < d:
                        d = dist[up + x - 1] + 1
                    if x < w - 1 and dist[up + x + 1] + 1 < d:
                        d = dist[up + x + 1] + 1
                dist[i] = d
        # backward pass
        for z in range(l - 1, -1, -1):
            base = z * w
            dn = base + w
            for x in range(w - 1, -1, -1):
                i = base + x
                d = dist[i]
                if x < w - 1 and dist[i + 1] + 1 < d:
                    d = dist[i + 1] + 1
                if z < l - 1:
                    if dist[dn + x] + 1 < d:
                        d = dist[dn + x] + 1
                    if x < w - 1 and dist[dn + x + 1] + 1 < d:
                        d = dist[dn + x + 1] + 1
                    if x > 0 and dist[dn + x - 1] + 1 < d:
                        d = dist[dn + x - 1] + 1
                dist[i] = d
        return dist
