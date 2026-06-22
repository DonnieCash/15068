"""Minecraft block identifiers and the material palette used by the twin.

Block names are modern (flattened) namespaced IDs, e.g. ``minecraft:stone``.
The :class:`Palette` assigns each distinct block state an index; the schematic
stores those indices as a varint array.
"""

from __future__ import annotations

from typing import Dict, List

AIR = "minecraft:air"

# Material groups -> the block used to render them.  Kept readable so the
# look of the city can be tuned in one place.
MATERIALS = {
    # Ground / terrain
    "terrain": "minecraft:grass_block",
    "dirt": "minecraft:dirt",
    "bedrock": "minecraft:bedrock",
    "water": "minecraft:water",
    "riverbed": "minecraft:gravel",
    "sand": "minecraft:sand",

    # Transport network
    "road": "minecraft:gray_concrete",
    "road_major": "minecraft:black_concrete",
    "sidewalk": "minecraft:light_gray_concrete",
    "rail": "minecraft:iron_block",
    "bridge_deck": "minecraft:smooth_stone",
    "bridge_truss": "minecraft:green_concrete",

    # Open space
    "park": "minecraft:moss_block",
    "tree_trunk": "minecraft:oak_log",
    "tree_leaves": "minecraft:oak_leaves",
    "plaza": "minecraft:stone_bricks",

    # Buildings (walls keyed by a small rotating palette for variety)
    "wall_brick": "minecraft:bricks",
    "wall_concrete": "minecraft:white_concrete",
    "wall_stone": "minecraft:stone_bricks",
    "wall_sandstone": "minecraft:smooth_sandstone",
    "wall_terracotta": "minecraft:terracotta",
    "window": "minecraft:light_blue_stained_glass",
    "roof_flat": "minecraft:deepslate_tiles",
    "roof_civic": "minecraft:copper_block",
    "roof_church": "minecraft:red_terracotta",
    "landmark": "minecraft:gold_block",
    "marker": "minecraft:sea_lantern",
}

# Rotating wall materials give blocks a varied skyline instead of one texture.
WALL_CYCLE: List[str] = [
    "wall_brick", "wall_concrete", "wall_stone",
    "wall_terracotta", "wall_sandstone",
]


def material(name: str) -> str:
    """Resolve a material group name to a concrete block id."""
    try:
        return MATERIALS[name]
    except KeyError as exc:  # pragma: no cover - defensive
        raise KeyError(f"Unknown material group: {name!r}") from exc


class Palette:
    """Maps block-state strings to stable integer indices (air is always 0)."""

    def __init__(self) -> None:
        self._index: Dict[str, int] = {}
        self.id_of(AIR)  # guarantee air == 0

    def id_of(self, block: str) -> int:
        idx = self._index.get(block)
        if idx is None:
            idx = len(self._index)
            self._index[block] = idx
        return idx

    def as_dict(self) -> Dict[str, int]:
        return dict(self._index)

    def __len__(self) -> int:
        return len(self._index)
