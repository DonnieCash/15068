"""Turns a :class:`~newken_twin.model.City` into a detailed voxel city.

Layers, in build order (later overwrites earlier):
  terrain (valley + hills) -> river & ponds -> riverbanks -> parks ->
  road network + sidewalks + markings -> bridges -> buildings (foundations,
  facades, floors, windows, doors, roofs) -> street furniture (lamps, trees,
  benches, cars) -> modelled landmarks (church, city hall, monuments).
"""

from __future__ import annotations

import random
from collections import deque
from dataclasses import dataclass
from typing import Dict, List, Optional, Set, Tuple

from . import raster
from .blocks import (CAR_COLORS, TREE_SPECIES, WALL_CYCLE, Palette,
                     door_state, log, material, slab, stairs)
from .geo import BBox, LatLon, Projection
from .model import Area, Building, City, Point, Road
from .terrain import WATER_Y, Heightmap
from .volume import Volume

FLOOR_H = 4               # blocks per storey
TOP_MARGIN = 10
DEFAULT_LANDMARK_H = 28
MAJOR_CLASSES = {"motorway", "trunk", "primary"}
SECONDARY_CLASSES = {"secondary", "tertiary"}

Cell = Tuple[int, int]

# Use -> (wall material group, roof style)
USE_STYLE = {
    "commercial": ("wall_brick", "flat"),
    "civic": ("wall_andesite", "flat"),
    "industrial": ("wall_industrial", "flat"),
    "residential": ("wall_brick", "hip"),
}


@dataclass
class BuildResult:
    volume: Volume
    projection: Projection
    city: City
    heightmap: Heightmap


class CityBuilder:
    def __init__(self, city: City, meters_per_block: float = 1.0,
                 bbox: Optional[BBox] = None, pad_m: float = 40.0,
                 detail: bool = True):
        self.city = city
        box = bbox if bbox is not None else city.bounding_box()
        if pad_m and bbox is None:
            box = _pad_bbox(box, pad_m)
        self.projection = Projection(box, meters_per_block)
        self.palette = Palette()
        self.detail = detail
        self.rng = random.Random(20150)  # ZIP-coded determinism :)
        self.heightmap: Optional[Heightmap] = None

    # -- public ------------------------------------------------------------
    def build(self) -> BuildResult:
        W, L = self.projection.width_blocks, self.projection.height_blocks

        # 1. terrain heightmap (needs the river footprint first)
        hm = Heightmap(W, L)
        water_cells = self._collect_water_cells(W, L)
        hm.build(water_cells)
        self.heightmap = hm

        tallest = self._tallest_structure()
        height = hm.max_height() + tallest + TOP_MARGIN
        vol = Volume(W, height, L, self.palette)

        self._lay_terrain(vol, hm)
        for area in self.city.areas:
            if area.kind in ("park", "plaza", "pond", "riverwalk"):
                self._lay_area(vol, hm, area)

        road_cells = self._lay_roads(vol, hm)
        for road in self.city.roads:
            if road.bridge:
                self._lay_bridge(vol, hm, road)

        for b in self.city.buildings:
            self._lay_building(vol, hm, b)

        if self.detail:
            self._street_furniture(vol, hm, road_cells)

        for pt in self.city.points:
            if pt.kind == "tree":
                self._plant_tree(vol, hm, pt.location, pt.species)
        for pt in self.city.points:
            if pt.kind == "landmark":
                self._lay_landmark(vol, hm, pt)

        return BuildResult(vol, self.projection, self.city, hm)

    # -- geometry helpers --------------------------------------------------
    def _project(self, pts: List[LatLon]) -> List[Tuple[float, float]]:
        return [self.projection.to_block(p) for p in pts]

    def _collect_water_cells(self, W: int, L: int) -> Set[Cell]:
        cells: Set[Cell] = set()
        for area in self.city.areas:
            if area.kind in ("water", "pond"):
                cells.update(raster.clamp_cells(
                    raster.polygon_cells(self._project(area.geometry)), W, L))
        return cells

    def _tallest_structure(self) -> int:
        tallest = DEFAULT_LANDMARK_H
        for b in self.city.buildings:
            tallest = max(tallest, b.height_blocks + 12)
        for p in self.city.points:
            if p.kind == "landmark":
                tallest = max(tallest, (p.height or DEFAULT_LANDMARK_H) + 10)
        return tallest

    # -- terrain -----------------------------------------------------------
    def _lay_terrain(self, vol: Volume, hm: Heightmap) -> None:
        W, L = vol.width, vol.length
        data = vol.data
        stride = vol.stride_y
        pal = self.palette
        bedrock = pal.id_of(material("bedrock"))
        stone = pal.id_of(material("stone"))
        dirt = pal.id_of(material("subsoil"))
        grass = pal.id_of(material("terrain"))
        water = pal.id_of(material("water"))
        riverbed = pal.id_of(material("riverbed"))
        sand = pal.id_of(material("riverbank"))

        vol.fill_layer(0, material("bedrock"))  # contiguous, fast

        surface = hm.surface
        is_water = hm.is_water
        for z in range(L):
            zb = z * W
            for x in range(W):
                i = zb + x
                col0 = i  # (z*W + x) is the y=0 index
                h = surface[i]
                if is_water[i]:
                    # stone up to bed-1, gravel bed, water to surface level
                    for y in range(1, h):
                        data[col0 + y * stride] = stone
                    data[col0 + h * stride] = riverbed
                    for y in range(h + 1, WATER_Y + 1):
                        data[col0 + y * stride] = water
                    continue
                for y in range(1, h - 1):
                    data[col0 + y * stride] = stone
                if h - 1 >= 1:
                    data[col0 + (h - 1) * stride] = dirt
                # shoreline sand where land barely rises above the water
                top = sand if (h <= WATER_Y + 1 and self._near_water(hm, x, z)) else grass
                data[col0 + h * stride] = top

    def _near_water(self, hm: Heightmap, x: int, z: int) -> bool:
        return (hm.water(x + 1, z) or hm.water(x - 1, z)
                or hm.water(x, z + 1) or hm.water(x, z - 1))

    # -- areas (parks, plazas, ponds) -------------------------------------
    def _lay_area(self, vol: Volume, hm: Heightmap, area: Area) -> None:
        cells = list(raster.clamp_cells(
            raster.polygon_cells(self._project(area.geometry)),
            vol.width, vol.length))
        if area.kind == "park":
            moss = material("park")
            for (x, z) in cells:
                vol.set(x, hm.height(x, z), z, moss)
            self._scatter_flowers(vol, hm, cells)
            self._park_trees(vol, hm, cells)
        elif area.kind == "plaza":
            for (x, z) in cells:
                vol.set(x, hm.height(x, z), z, material("plaza"))
        elif area.kind == "riverwalk":
            for (x, z) in cells:
                vol.set(x, hm.height(x, z), z, material("sidewalk"))
        elif area.kind == "pond":
            for (x, z) in cells:
                h = hm.height(x, z)
                vol.set(x, h, z, material("water"))
                vol.set(x, h - 1, z, material("riverbed"))

    def _scatter_flowers(self, vol, hm, cells):
        flowers = [material("flower_red"), material("flower_yellow"),
                   material("flower_blue"), material("grass_tuft")]
        for (x, z) in cells:
            if self.rng.random() < 0.06:
                vol.set(x, hm.height(x, z) + 1, z, self.rng.choice(flowers))

    def _park_trees(self, vol, hm, cells):
        for (x, z) in cells:
            if self.rng.random() < 0.012:
                self._plant_tree(vol, hm, None, None, at=(x, z))

    # -- roads -------------------------------------------------------------
    def _lay_roads(self, vol: Volume, hm: Heightmap) -> Set[Cell]:
        road_cells: Set[Cell] = set()
        center_cells: Set[Cell] = set()
        major_cells: Set[Cell] = set()
        W, L = vol.width, vol.length

        for road in self.city.roads:
            if road.bridge:
                continue
            pts = self._project(road.geometry)
            major = road.klass in MAJOR_CLASSES
            mat = material("road_major" if major else "road")
            cells = list(raster.clamp_cells(
                raster.polyline_cells(pts, road.width_blocks), W, L))
            for (x, z) in cells:
                if not hm.water(x, z):
                    vol.set(x, hm.height(x, z), z, mat)
                    road_cells.add((x, z))
            # centre line
            for (x, z) in raster.clamp_cells(raster.polyline_cells(pts, 1), W, L):
                center_cells.add((x, z))
            if major:
                major_cells.update(cells)

        # sidewalks: a 2-cell apron around roads, on bare ground only
        self._lay_sidewalks(vol, hm, road_cells)

        # paint centre lines on major roads last so they sit on top
        line = material("road_line")
        for (x, z) in center_cells:
            if (x, z) in major_cells and not hm.water(x, z):
                vol.set(x, hm.height(x, z), z, line)
        return road_cells

    def _lay_sidewalks(self, vol, hm, road_cells: Set[Cell]) -> None:
        sidewalk = material("sidewalk")
        pal = self.palette
        grass_idx = pal.id_of(material("terrain"))
        moss_idx = pal.id_of(material("park"))
        sand_idx = pal.id_of(material("riverbank"))
        convertible = {grass_idx, moss_idx, sand_idx}
        apron: Set[Cell] = set()
        for (x, z) in road_cells:
            for dx in (-2, -1, 0, 1, 2):
                for dz in (-2, -1, 0, 1, 2):
                    c = (x + dx, z + dz)
                    if c not in road_cells:
                        apron.add(c)
        for (x, z) in apron:
            if hm.water(x, z):
                continue
            h = hm.height(x, z)
            if vol.get_index(x, h, z) in convertible:
                vol.set(x, h, z, sidewalk)

    # -- bridges -----------------------------------------------------------
    def _lay_bridge(self, vol: Volume, hm: Heightmap, road: Road) -> None:
        deck_y = WATER_Y + 8
        deck = material("bridge_deck")
        truss = material("bridge_truss")
        tower = material("bridge_tower")
        cable = material("bridge_cable")
        pts = self._project(road.geometry)
        deck_cells = list(raster.clamp_cells(
            raster.polyline_cells(pts, road.width_blocks), vol.width, vol.length))
        deck_set = set(deck_cells)
        for (x, z) in deck_cells:
            vol.set(x, deck_y, z, deck)
            # piers down to the bed
            if (x + z) % 9 == 0:
                bottom = WATER_Y - 3
                for y in range(bottom, deck_y):
                    vol.set(x, y, z, tower)
        # side trusses / railings + suspension cables
        for (x, z) in deck_cells:
            edge = any((x + dx, z + dz) not in deck_set
                       for dx, dz in ((1, 0), (-1, 0), (0, 1), (0, -1)))
            if edge:
                vol.set(x, deck_y + 1, z, truss)
                if (x + z) % 4 == 0:
                    for y in range(deck_y + 2, deck_y + 6):
                        vol.set(x, y, z, cable)
        # towers at the two ends
        for end in (deck_cells[0], deck_cells[-1]):
            ex, ez = end
            for y in range(deck_y, deck_y + 12):
                for dx, dz in ((0, 0), (1, 0), (0, 1), (1, 1)):
                    vol.set(ex + dx, y, ez + dz, tower)

    # -- buildings ---------------------------------------------------------
    def _lay_building(self, vol: Volume, hm: Heightmap, b: Building) -> None:
        verts = self._project(b.geometry)
        interior = list(raster.clamp_cells(
            raster.polygon_cells(verts), vol.width, vol.length))
        if not interior:
            return
        interior_set = set(interior)

        # platform: sit the building on the highest ground it covers
        base_y = max(hm.height(x, z) for (x, z) in interior)
        height = b.height_blocks
        wall_top = base_y + height

        wall_group, roof_style = USE_STYLE.get(b.use, USE_STYLE["residential"])
        if b.material:
            wall_group = b.material
        else:
            wall_group = WALL_CYCLE[abs(_poly_hash(verts)) % len(WALL_CYCLE)] \
                if b.use == "residential" else wall_group
        wall_mat = material(wall_group)
        pillar_mat = material("pillar") if b.use in ("civic", "commercial") \
            else material("wall_stone")
        found_mat = material("foundation")
        floor_mat = material("floor_slab")

        # foundation: fill each column from its ground up to the platform
        for (x, z) in interior:
            g = hm.height(x, z)
            for y in range(g, base_y + 1):
                vol.set(x, y, z, found_mat)

        # interior floor slabs (visible through windows)
        n_floors = max(1, height // FLOOR_H)
        for k in range(1, n_floors):
            fy = base_y + k * FLOOR_H
            for (x, z) in interior:
                vol.set(x, fy, z, slab(floor_mat, "bottom"))

        # walls along each edge, with window banding and a glassy ground floor
        edge_cells = self._edge_cells(verts, interior_set, vol)
        window = material("window")
        store = material("storefront")
        commercial_ground = b.use in ("commercial", "civic")
        for (x, z) in edge_cells:
            for y in range(base_y + 1, wall_top):
                row = (y - base_y - 1)
                floor_row = row % FLOOR_H
                ground_floor = row < FLOOR_H
                if ground_floor and commercial_ground and floor_row in (1, 2):
                    vol.set(x, y, z, store)
                elif (not ground_floor) and floor_row in (1, 2) and ((x + z) % 2 == 0):
                    vol.set(x, y, z, window)
                else:
                    vol.set(x, y, z, wall_mat)

        # corner pillars at the polygon vertices
        for (vx, vz) in verts:
            x, z = int(round(vx)), int(round(vz))
            for y in range(base_y + 1, wall_top + 1):
                vol.set(x, y, z, pillar_mat)

        # a front door on a deterministic edge cell
        self._place_door(vol, edge_cells, interior_set, base_y,
                         material("door_civic") if b.use == "civic"
                         else material("door"))

        # roof
        if roof_style == "hip":
            self._hip_roof(vol, interior, interior_set, wall_top)
        else:
            self._flat_roof(vol, interior, edge_cells, wall_top, wall_mat, b.use)

    def _edge_cells(self, verts, interior_set, vol) -> List[Cell]:
        out: List[Cell] = []
        seen: Set[Cell] = set()
        n = len(verts)
        for i in range(n):
            for c in raster.thick_line(verts[i], verts[(i + 1) % n], 1):
                if c in seen:
                    continue
                seen.add(c)
                x, z = c
                if 0 <= x < vol.width and 0 <= z < vol.length:
                    out.append(c)
        return out

    def _place_door(self, vol, edge_cells, interior_set, base_y, door_block):
        if not edge_cells:
            return
        # pick the southern-most edge cell (largest z) as the street front
        fx, fz = max(edge_cells, key=lambda c: (c[1], c[0]))
        vol.set(fx, base_y + 1, fz, door_state(door_block, "north", "lower"))
        vol.set(fx, base_y + 2, fz, door_state(door_block, "north", "upper"))

    def _flat_roof(self, vol, interior, edge_cells, wall_top, wall_mat, use):
        roof = material("roof_civic") if use == "civic" else material("roof_flat")
        for (x, z) in interior:
            vol.set(x, wall_top, z, roof)
        # parapet
        for (x, z) in edge_cells:
            vol.set(x, wall_top + 1, z, material("roof_parapet"))
        # rooftop HVAC units + a vent or two
        hvac = material("hvac")
        for (x, z) in interior:
            if (x * 7 + z * 3) % 23 == 0:
                vol.set(x, wall_top + 1, z, hvac)

    def _hip_roof(self, vol, interior, interior_set, wall_top):
        body = "minecraft:dark_oak_planks"
        stair = material("roof_house")     # dark_oak_stairs
        top_slab = material("roof_house_top")
        dist = _inset_distance(interior_set)
        cap = max(2, min(8, (max(dist.values()) if dist else 2)))
        # ceiling over the top floor
        for (x, z) in interior:
            vol.set(x, wall_top, z, slab(material("floor_slab"), "top"))
        for (x, z) in interior:
            d = min(dist[(x, z)], cap)
            rh = wall_top + d
            # downhill neighbour = smallest distance around us
            facing = _downhill_facing((x, z), dist)
            if facing is None:
                vol.set(x, rh, z, top_slab)         # ridge / peak
            else:
                vol.set(x, rh, z, stairs(stair, facing))
            # close the step face below so there are no holes on slopes
            if d > 0:
                vol.set(x, rh - 1, z, body)

    # -- street furniture --------------------------------------------------
    def _street_furniture(self, vol, hm, road_cells: Set[Cell]):
        self._street_lamps(vol, hm, road_cells)
        self._cars(vol, hm, road_cells)

    def _street_lamps(self, vol, hm, road_cells: Set[Cell]):
        post = material("lamp_post")
        lamp = material("lamp_light")
        placed = 0
        # lamps on sidewalk cells next to roads, spaced out
        candidates = sorted(road_cells)
        for (x, z) in candidates:
            if (x % 11 == 0) and (z % 11 == 0):
                # step just outside the road
                for dx, dz in ((2, 0), (-2, 0), (0, 2), (0, -2)):
                    cx, cz = x + dx, z + dz
                    if (cx, cz) in road_cells or hm.water(cx, cz):
                        continue
                    h = hm.height(cx, cz)
                    for y in range(h + 1, h + 4):
                        vol.set(cx, y, cz, post)
                    vol.set(cx, h + 4, cz, lamp)
                    placed += 1
                    break
        return placed

    def _cars(self, vol, hm, road_cells: Set[Cell]):
        for (x, z) in road_cells:
            if self.rng.random() < 0.004:
                color = self.rng.choice(CAR_COLORS)
                h = hm.height(x, z)
                vol.set(x, h + 1, z, color)
                # a 2-long body
                vol.set(x, h + 1, z + 1 if (x + z) % 2 else z, color)

    # -- vegetation --------------------------------------------------------
    def _plant_tree(self, vol, hm, location, species, at: Optional[Cell] = None):
        if at is not None:
            x, z = at
        else:
            x, z = self.projection.to_block_int(location)
        if hm.water(x, z):
            return
        log_id, leaf_id = self._species(species)
        g = hm.height(x, z)
        trunk_h = self.rng.randint(4, 6)
        for y in range(g + 1, g + 1 + trunk_h):
            vol.set(x, y, z, log(log_id, "y"))
        crown = g + trunk_h
        for (cx, cz) in raster.disk_cells(x, z, 2):
            vol.set(cx, crown, cz, leaf_id)
            vol.set(cx, crown + 1, cz, leaf_id)
        for (cx, cz) in raster.disk_cells(x, z, 1):
            vol.set(cx, crown + 2, cz, leaf_id)
        vol.set(x, crown + 2, z, leaf_id)

    def _species(self, species: Optional[str]):
        if species:
            for lg, lv in TREE_SPECIES:
                if species in lg:
                    return lg, lv
        return self.rng.choice(TREE_SPECIES)

    # -- landmarks ---------------------------------------------------------
    def _lay_landmark(self, vol: Volume, hm: Heightmap, pt: Point) -> None:
        x, z = self.projection.to_block_int(pt.location)
        g = hm.height(x, z)
        h = pt.height or DEFAULT_LANDMARK_H
        fp = max(8, pt.footprint)
        if pt.structure == "church":
            self._build_church(vol, x, z, g, h, fp)
        elif pt.structure == "cityhall":
            self._build_cityhall(vol, x, z, g, h, fp)
        elif pt.structure == "monument":
            self._build_monument(vol, x, z, g, h)
        else:
            self._build_tower(vol, x, z, g, h, fp)

    def _box(self, vol, x0, z0, x1, z1, y0, y1, block, hollow=False):
        for x in range(x0, x1 + 1):
            for z in range(z0, z1 + 1):
                edge = x in (x0, x1) or z in (z0, z1)
                for y in range(y0, y1 + 1):
                    if hollow and not edge and y not in (y0, y1):
                        continue
                    vol.set(x, y, z, block)

    def _build_tower(self, vol, x, z, g, h, fp):
        gold = material("landmark")
        beacon = material("marker")
        r = fp // 2
        self._box(vol, x - r, z - r, x + r, z + r, g + 1, g + h, gold, hollow=True)
        for y in range(g + h + 1, g + h + 4):
            vol.set(x, y, z, beacon)

    def _build_church(self, vol, x, z, g, h, fp):
        stone = material("wall_stone")
        roof = material("roof_church")
        glass = material("window")
        spire = material("spire")
        cross = material("cross")
        r = fp // 2
        nave_top = g + max(10, h - 14)
        # nave walls
        self._box(vol, x - r, z - r, x + r, z + r, g + 1, nave_top, stone, hollow=True)
        # arched stained-glass windows along the long walls
        for zz in range(z - r + 1, z + r, 3):
            vol.set(x - r, nave_top - 3, zz, glass)
            vol.set(x - r, nave_top - 2, zz, glass)
            vol.set(x + r, nave_top - 3, zz, glass)
            vol.set(x + r, nave_top - 2, zz, glass)
        # gabled roof over the nave
        for d in range(0, r + 1):
            ry = nave_top + d
            for zz in range(z - r, z + r + 1):
                vol.set(x - r + d, ry, zz, roof)
                vol.set(x + r - d, ry, zz, roof)
        # bell tower at the front
        tr = max(2, r // 2)
        tx, tz = x, z - r
        tower_top = g + h
        self._box(vol, tx - tr, tz - tr, tx + tr, tz + tr, g + 1, tower_top,
                  stone, hollow=True)
        # spire
        for d in range(0, tr + 2):
            sy = tower_top + d
            s = tr - d
            if s < 0:
                vol.set(tx, sy, tz, spire)
            else:
                self._box(vol, tx - s, tz - s, tx + s, tz + s, sy, sy, spire)
        # cross on top
        vol.set(tx, tower_top + tr + 3, tz, cross)
        vol.set(tx, tower_top + tr + 4, tz, cross)

    def _build_cityhall(self, vol, x, z, g, h, fp):
        wall = material("wall_quartz")
        pillar = material("pillar")
        dome = material("dome")
        roof = material("roof_civic")
        r = fp // 2
        body_top = g + max(8, h - 8)
        self._box(vol, x - r, z - r, x + r, z + r, g + 1, body_top, wall, hollow=True)
        # flat cornice
        for xx in range(x - r, x + r + 1):
            for zz in range(z - r, z + r + 1):
                vol.set(xx, body_top, zz, roof)
        # front portico columns
        for cx in range(x - r, x + r + 1, 2):
            for y in range(g + 1, body_top):
                vol.set(cx, y, z + r + 1, log(pillar, "y"))
            vol.set(cx, body_top, z + r + 1, roof)
        # central dome
        for d in range(0, max(3, r // 2)):
            dy = body_top + d
            s = max(0, (r // 2) - d)
            self._box(vol, x - s, z - s, x + s, z + s, dy, dy, dome)
        vol.set(x, body_top + max(3, r // 2) + 1, z, material("cross"))

    def _build_monument(self, vol, x, z, g, h):
        stone = material("wall_stone")
        for y in range(g + 1, g + h):
            s = 1 if y < g + h - 3 else 0
            self._box(vol, x - s, z - s, x + s, z + s, y, y, stone)
        vol.set(x, g + h, z, material("marker"))


# --- module helpers -------------------------------------------------------

def _inset_distance(interior: Set[Cell]) -> Dict[Cell, int]:
    """Chebyshev distance of every interior cell to the footprint boundary."""
    dist: Dict[Cell, int] = {}
    dq: deque = deque()
    for (x, z) in interior:
        boundary = any((x + dx, z + dz) not in interior
                       for dx in (-1, 0, 1) for dz in (-1, 0, 1)
                       if (dx, dz) != (0, 0))
        if boundary:
            dist[(x, z)] = 0
            dq.append((x, z))
    while dq:
        x, z = dq.popleft()
        d = dist[(x, z)]
        for dx, dz in ((1, 0), (-1, 0), (0, 1), (0, -1),
                       (1, 1), (1, -1), (-1, 1), (-1, -1)):
            c = (x + dx, z + dz)
            if c in interior and c not in dist:
                dist[c] = d + 1
                dq.append(c)
    return dist


_FACE = {(0, -1): "north", (0, 1): "south", (1, 0): "east", (-1, 0): "west"}


def _downhill_facing(cell: Cell, dist: Dict[Cell, int]) -> Optional[str]:
    x, z = cell
    here = dist.get(cell, 0)
    best = None
    best_d = here
    for (dx, dz), face in _FACE.items():
        nd = dist.get((x + dx, z + dz))
        if nd is not None and nd < best_d:
            best_d = nd
            best = face
    return best


def _pad_bbox(box: BBox, pad_m: float) -> BBox:
    from .geo import meters_per_degree
    m_lat, m_lon = meters_per_degree(box.center.lat)
    dlat = pad_m / m_lat
    dlon = pad_m / m_lon
    return BBox(south=box.south - dlat, west=box.west - dlon,
                north=box.north + dlat, east=box.east + dlon)


def _poly_hash(pts: List[Tuple[float, float]]) -> int:
    acc = 0
    for (x, z) in pts:
        acc = acc * 31 + int(x * 7.0) + int(z * 13.0)
    return acc
