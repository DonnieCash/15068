"""Minecraft block identifiers, the material palette, and block-state helpers.

Block names are modern (flattened) namespaced IDs.  The :class:`Palette`
assigns each distinct *block state string* an index; the Sponge schematic stores
those indices as a varint array.  Because palette keys are full block-state
strings (e.g. ``minecraft:oak_stairs[facing=east,half=bottom]``) we can place
stairs, slabs, panes, logs, doors and more — not just full cubes.
"""

from __future__ import annotations

from typing import Dict, List

AIR = "minecraft:air"

# Material groups -> the block used to render them.  Tune the whole city's look
# from this one table.
MATERIALS = {
    # Terrain / nature
    "terrain": "minecraft:grass_block",
    "subsoil": "minecraft:dirt",
    "stone": "minecraft:stone",
    "bedrock": "minecraft:bedrock",
    "water": "minecraft:water",
    "riverbed": "minecraft:gravel",
    "riverbank": "minecraft:sand",
    "beach": "minecraft:sand",
    "path": "minecraft:dirt_path",

    # Transport
    "road": "minecraft:gray_concrete",
    "road_major": "minecraft:black_concrete",
    "road_line": "minecraft:yellow_concrete",
    "crosswalk": "minecraft:white_concrete",
    "sidewalk": "minecraft:light_gray_concrete",
    "curb": "minecraft:smooth_stone",
    "rail": "minecraft:iron_block",
    "bridge_deck": "minecraft:smooth_stone",
    "bridge_truss": "minecraft:green_concrete",
    "bridge_cable": "minecraft:iron_bars",
    "bridge_tower": "minecraft:stone_bricks",

    # Open space
    "park": "minecraft:moss_block",
    "plaza": "minecraft:stone_bricks",
    "tree_trunk": "minecraft:oak_log",
    "tree_leaves": "minecraft:oak_leaves",

    # Building fabric
    "wall_brick": "minecraft:bricks",
    "wall_concrete": "minecraft:white_concrete",
    "wall_stone": "minecraft:stone_bricks",
    "wall_sandstone": "minecraft:smooth_sandstone",
    "wall_terracotta": "minecraft:terracotta",
    "wall_andesite": "minecraft:polished_andesite",
    "wall_quartz": "minecraft:quartz_block",
    "wall_industrial": "minecraft:light_gray_terracotta",
    "foundation": "minecraft:stone_bricks",
    "floor_slab": "minecraft:smooth_stone_slab",
    "pillar": "minecraft:quartz_pillar",

    "window": "minecraft:light_blue_stained_glass",
    "window_pane": "minecraft:light_blue_stained_glass_pane",
    "storefront": "minecraft:glass",
    "door": "minecraft:oak_door",
    "door_civic": "minecraft:dark_oak_door",

    # Roofs
    "roof_flat": "minecraft:deepslate_tiles",
    "roof_parapet": "minecraft:polished_deepslate",
    "roof_civic": "minecraft:copper_block",
    "roof_house": "minecraft:dark_oak_stairs",
    "roof_house_top": "minecraft:dark_oak_slab",
    "roof_church": "minecraft:deepslate_tile_stairs",
    "roof_church_top": "minecraft:deepslate_tile_slab",
    "hvac": "minecraft:iron_block",
    "vent": "minecraft:cauldron",

    # Landmarks / detail
    "landmark": "minecraft:gold_block",
    "marker": "minecraft:sea_lantern",
    "spire": "minecraft:dark_prismarine",
    "cross": "minecraft:gold_block",
    "dome": "minecraft:waxed_oxidized_copper",
    "lamp_post": "minecraft:cobblestone_wall",
    "lamp_light": "minecraft:lantern",
    "bench": "minecraft:oak_stairs",
    "fence": "minecraft:oak_fence",

    # Flowers (scattered in parks / verges)
    "flower_red": "minecraft:poppy",
    "flower_yellow": "minecraft:dandelion",
    "flower_blue": "minecraft:cornflower",
    "grass_tuft": "minecraft:short_grass",
}

# Rotating wall materials give a varied skyline for unspecified buildings.
WALL_CYCLE: List[str] = [
    "wall_brick", "wall_concrete", "wall_stone",
    "wall_terracotta", "wall_sandstone", "wall_andesite",
]

# Car body colours.
CAR_COLORS: List[str] = [
    "minecraft:red_concrete", "minecraft:blue_concrete",
    "minecraft:white_concrete", "minecraft:black_concrete",
    "minecraft:lime_concrete", "minecraft:light_gray_concrete",
    "minecraft:orange_concrete",
]

# Deciduous tree species -> (log, leaves).
TREE_SPECIES = [
    ("minecraft:oak_log", "minecraft:oak_leaves"),
    ("minecraft:birch_log", "minecraft:birch_leaves"),
    ("minecraft:spruce_log", "minecraft:spruce_leaves"),
    ("minecraft:dark_oak_log", "minecraft:dark_oak_leaves"),
]


def material(name: str) -> str:
    """Resolve a material group name to a concrete block id."""
    try:
        return MATERIALS[name]
    except KeyError as exc:  # pragma: no cover - defensive
        raise KeyError(f"Unknown material group: {name!r}") from exc


# --- block-state helpers --------------------------------------------------

def with_states(block: str, **states) -> str:
    """Attach block-state properties: ``with_states(stair, facing='east')``."""
    if not states:
        return block
    body = ",".join(f"{k}={_fmt(v)}" for k, v in sorted(states.items()))
    return f"{block}[{body}]"


def _fmt(v) -> str:
    if isinstance(v, bool):
        return "true" if v else "false"
    return str(v)


def stairs(block: str, facing: str, half: str = "bottom") -> str:
    return with_states(block, facing=facing, half=half)


def slab(block: str, kind: str = "bottom") -> str:
    return with_states(block, type=kind)


def log(block: str, axis: str = "y") -> str:
    return with_states(block, axis=axis)


def door_state(block: str, facing: str, half: str, hinge: str = "left",
               is_open: bool = False) -> str:
    return with_states(block, facing=facing, half=half, hinge=hinge,
                       open=is_open)


def base_id(block: str) -> str:
    """Strip any ``[...]`` block-state suffix, returning the bare block id."""
    i = block.find("[")
    return block if i < 0 else block[:i]


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
