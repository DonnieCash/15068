"""newken_twin — a Minecraft digital twin generator for New Kensington, PA.

Pipeline: real-world geographic features (bundled or live OpenStreetMap) are
projected onto a block grid, rasterised into a 3D voxel volume, and exported as
a WorldEdit-compatible Sponge ``.schem`` plus a top-down PNG preview.
"""

from __future__ import annotations

from .builder import BuildResult, CityBuilder
from .geo import BBox, LatLon
from .model import City, load_city
from .schematic import write_schematic
from .volume import Volume

__version__ = "1.1.0"

__all__ = [
    "BuildResult",
    "CityBuilder",
    "BBox",
    "LatLon",
    "City",
    "load_city",
    "write_schematic",
    "Volume",
    "__version__",
]
