"""A dense 3D voxel volume holding palette indices.

Storage order matches the Sponge Schematic spec so writing is a straight copy::

    index = (y * Length + z) * Width + x

Memory use is ``Width * Length * Height * 2`` bytes (unsigned-short indices),
which comfortably handles a city-core sized region.
"""

from __future__ import annotations

from array import array

from .blocks import Palette


class Volume:
    def __init__(self, width: int, height: int, length: int, palette: Palette):
        if width <= 0 or height <= 0 or length <= 0:
            raise ValueError("Volume dimensions must be positive")
        self.width = width    # X
        self.height = height  # Y
        self.length = length  # Z
        self.palette = palette
        # 'H' = unsigned short (0..65535) palette index; 0 == air.
        self.data = array("H", bytes(2 * width * height * length))

    def _index(self, x: int, y: int, z: int) -> int:
        return (y * self.length + z) * self.width + x

    def in_bounds(self, x: int, y: int, z: int) -> bool:
        return (0 <= x < self.width and 0 <= y < self.height
                and 0 <= z < self.length)

    def set(self, x: int, y: int, z: int, block: str) -> None:
        if not self.in_bounds(x, y, z):
            return
        self.data[self._index(x, y, z)] = self.palette.id_of(block)

    def set_index(self, x: int, y: int, z: int, idx: int) -> None:
        if not self.in_bounds(x, y, z):
            return
        self.data[self._index(x, y, z)] = idx

    def get_index(self, x: int, y: int, z: int) -> int:
        if not self.in_bounds(x, y, z):
            return 0
        return self.data[self._index(x, y, z)]

    def fill_column(self, x: int, z: int, y0: int, y1: int, block: str) -> None:
        """Fill the inclusive vertical span [y0, y1] at column (x, z)."""
        if not (0 <= x < self.width and 0 <= z < self.length):
            return
        idx = self.palette.id_of(block)
        lo = max(0, min(y0, y1))
        hi = min(self.height - 1, max(y0, y1))
        for y in range(lo, hi + 1):
            self.data[self._index(x, y, z)] = idx

    def non_air_count(self) -> int:
        return sum(1 for v in self.data if v)
