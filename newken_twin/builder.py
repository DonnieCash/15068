"""Turns a :class:`~newken_twin.model.City` into a voxel :class:`Volume`.

The build is layered: terrain first, then water/parks, the road network,
bridges, building shells, street trees and finally landmarks.  Later layers
overwrite earlier ones, mirroring how a real site is built up.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import List, Optional, Tuple

from . import raster
from .blocks import WALL_CYCLE, Palette, material
from .geo import BBox, LatLon, Projection
from .model import Area, Building, City, Point, Road
from .volume import Volume

GROUND_Y = 4          # grass surface; bedrock/dirt fill below
TOP_MARGIN = 8        # head-room above the tallest structure
DEFAULT_LANDMARK_H = 28

MAJOR_CLASSES = {"motorway", "trunk", "primary"}

# Roofs used when a building doesn't specify one, for a varied skyline.
DEFAULT_ROOFS = ["roof_flat", "roof_church", "roof_civic", "wall_terracotta"]


@dataclass
class BuildResult:
    volume: Volume
    projection: Projection
    city: City
    ground_y: int


class CityBuilder:
    def __init__(self, city: City, meters_per_block: float = 1.0,
                 bbox: Optional[BBox] = None, pad_m: float = 30.0):
        self.city = city
        box = bbox if bbox is not None else city.bounding_box()
        if pad_m and bbox is None:
            box = _pad_bbox(box, pad_m)
        self.projection = Projection(box, meters_per_block)
        self.palette = Palette()

    # -- public ------------------------------------------------------------
    def build(self) -> BuildResult:
        tallest = self._tallest_structure()
        height = GROUND_Y + tallest + TOP_MARGIN
        vol = Volume(self.projection.width_blocks, height,
                     self.projection.height_blocks, self.palette)
        self._lay_terrain(vol)
        for area in self.city.areas:
            self._lay_area(vol, area)
        for road in self.city.roads:
            if not road.bridge:
                self._lay_road(vol, road)
        for road in self.city.roads:
            if road.bridge:
                self._lay_bridge(vol, road)
        for building in self.city.buildings:
            self._lay_building(vol, building)
        for pt in self.city.points:
            if pt.kind == "tree":
                self._plant_tree(vol, pt)
        for pt in self.city.points:
            if pt.kind == "landmark":
                self._lay_landmark(vol, pt)
        return BuildResult(vol, self.projection, self.city, GROUND_Y)

    # -- helpers -----------------------------------------------------------
    def _project(self, pts: List[LatLon]) -> List[Tuple[float, float]]:
        return [self.projection.to_block(p) for p in pts]

    def _tallest_structure(self) -> int:
        tallest = DEFAULT_LANDMARK_H
        for b in self.city.buildings:
            tallest = max(tallest, b.height_blocks)
        for p in self.city.points:
            if p.kind == "landmark":
                tallest = max(tallest, p.height or DEFAULT_LANDMARK_H)
        return tallest

    def _lay_terrain(self, vol: Volume) -> None:
        bedrock = material("bedrock")
        dirt = material("dirt")
        grass = material("terrain")
        for z in range(vol.length):
            for x in range(vol.width):
                vol.set(x, 0, z, bedrock)
                for y in range(1, GROUND_Y):
                    vol.set(x, y, z, dirt)
                vol.set(x, GROUND_Y, z, grass)

    def _lay_area(self, vol: Volume, area: Area) -> None:
        cells = raster.clamp_cells(
            raster.polygon_cells(self._project(area.geometry)),
            vol.width, vol.length)
        if area.kind == "water":
            water = material("water")
            bed = material("riverbed")
            for (x, z) in cells:
                vol.set(x, GROUND_Y - 1, z, bed)
                vol.set(x, GROUND_Y, z, water)
        elif area.kind == "park":
            moss = material("park")
            for (x, z) in cells:
                vol.set(x, GROUND_Y, z, moss)
        elif area.kind == "plaza":
            plaza = material("plaza")
            for (x, z) in cells:
                vol.set(x, GROUND_Y, z, plaza)

    def _lay_road(self, vol: Volume, road: Road) -> None:
        mat = material("road_major" if road.klass in MAJOR_CLASSES else "road")
        pts = self._project(road.geometry)
        cells = raster.clamp_cells(
            raster.polyline_cells(pts, road.width_blocks),
            vol.width, vol.length)
        for (x, z) in cells:
            vol.set(x, GROUND_Y, z, mat)

    def _lay_bridge(self, vol: Volume, road: Road) -> None:
        deck_y = GROUND_Y + 6
        deck = material("bridge_deck")
        truss = material("bridge_truss")
        pts = self._project(road.geometry)
        deck_cells = list(raster.clamp_cells(
            raster.polyline_cells(pts, road.width_blocks),
            vol.width, vol.length))
        deck_set = set(deck_cells)
        pier = material("bridge_truss")
        for (x, z) in deck_cells:
            # sparse piers down to the water/ground
            if (x + z) % 7 == 0:
                vol.fill_column(x, z, GROUND_Y, deck_y - 1, pier)
            vol.set(x, deck_y, z, deck)
        # railings along the edges of the deck
        for (x, z) in deck_cells:
            neighbours = [(x + 1, z), (x - 1, z), (x, z + 1), (x, z - 1)]
            if any(n not in deck_set for n in neighbours):
                vol.set(x, deck_y + 1, z, truss)

    def _lay_building(self, vol: Volume, b: Building) -> None:
        pts = self._project(b.geometry)
        base = GROUND_Y + 1
        h = b.height_blocks
        top = base + h

        phash = abs(_poly_hash(pts))
        wall_mat = material(b.material) if b.material else material(
            WALL_CYCLE[phash % len(WALL_CYCLE)])
        window_mat = material("window")
        roof_choice = b.roof or DEFAULT_ROOFS[phash % len(DEFAULT_ROOFS)]
        roof_mat = material(roof_choice)
        found_mat = material("wall_stone")

        interior = list(raster.clamp_cells(
            raster.polygon_cells(pts), vol.width, vol.length))
        outline = list(raster.clamp_cells(
            raster.polygon_outline(pts, width=1), vol.width, vol.length))
        outline_set = set(outline)

        # foundation + ground floor slab
        for (x, z) in interior:
            vol.set(x, GROUND_Y, z, found_mat)

        # walls with a simple window banding
        for (x, z) in outline:
            for y in range(base, top):
                row = y - base
                is_window = (row % 4 in (1, 2) and row > 0 and (x + z) % 2 == 0)
                vol.set(x, y, z, window_mat if is_window else wall_mat)

        # roof slab (covers the whole footprint)
        roof_y = top
        for (x, z) in interior:
            vol.set(x, roof_y, z, roof_mat)
        for (x, z) in outline:
            vol.set(x, roof_y, z, roof_mat)
        # parapet for flat-roofed blocks
        if roof_choice == "roof_flat":
            for (x, z) in outline_set:
                vol.set(x, roof_y + 1, z, wall_mat)

    def _plant_tree(self, vol: Volume, pt: Point) -> None:
        x, z = self.projection.to_block_int(pt.location)
        trunk = material("tree_trunk")
        leaves = material("tree_leaves")
        trunk_h = 4
        for y in range(GROUND_Y + 1, GROUND_Y + 1 + trunk_h):
            vol.set(x, y, z, trunk)
        crown_y = GROUND_Y + trunk_h
        for (cx, cz) in raster.disk_cells(x, z, 2):
            vol.set(cx, crown_y, cz, leaves)
        for (cx, cz) in raster.disk_cells(x, z, 1):
            vol.set(cx, crown_y + 1, cz, leaves)

    def _lay_landmark(self, vol: Volume, pt: Point) -> None:
        x, z = self.projection.to_block_int(pt.location)
        h = pt.height or DEFAULT_LANDMARK_H
        gold = material("landmark")
        beacon = material("marker")
        for (cx, cz) in raster.disk_cells(x, z, 2):
            vol.fill_column(cx, cz, GROUND_Y + 1, GROUND_Y + h, gold)
        # a beacon of light on top
        vol.fill_column(x, z, GROUND_Y + h + 1, GROUND_Y + h + 3, beacon)


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
