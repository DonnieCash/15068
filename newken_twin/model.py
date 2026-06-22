"""Feature model for the digital twin and a loader for the bundled / external
GeoJSON-style dataset.

The on-disk format is a small JSON document::

    {
      "name": "...",
      "center": [lat, lon],
      "features": [
        {"kind": "building", "geometry": [[lon, lat], ...],
         "levels": 3, "material": "wall_brick", "name": "..."},
        {"kind": "road", "geometry": [[lon, lat], ...],
         "class": "primary", "width_m": 12, "name": "..."},
        {"kind": "water"|"park", "geometry": [[lon, lat], ...]},
        {"kind": "landmark"|"tree", "geometry": [lon, lat], ...}
      ]
    }

Coordinates are ``[lon, lat]`` pairs (GeoJSON order) so the data interoperates
with real OpenStreetMap exports.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import List, Optional

from .geo import BBox, LatLon

# Approximate metres added per building storey.
METERS_PER_LEVEL = 3.2

# Default carriageway widths (metres) by OSM-style highway class.
ROAD_WIDTHS = {
    "motorway": 16.0,
    "trunk": 14.0,
    "primary": 12.0,
    "secondary": 10.0,
    "tertiary": 8.0,
    "residential": 7.0,
    "service": 5.0,
    "footway": 2.0,
    "bridge": 14.0,
}


@dataclass
class Building:
    geometry: List[LatLon]
    levels: int = 2
    material: Optional[str] = None
    roof: Optional[str] = None
    name: str = ""

    @property
    def height_blocks(self) -> int:
        return max(3, int(round(self.levels * METERS_PER_LEVEL)))


@dataclass
class Road:
    geometry: List[LatLon]
    klass: str = "residential"
    width_m: Optional[float] = None
    name: str = ""
    bridge: bool = False

    @property
    def width_blocks(self) -> int:
        w = self.width_m if self.width_m is not None else ROAD_WIDTHS.get(
            self.klass, 7.0)
        return max(1, int(round(w)))


@dataclass
class Area:
    """A filled polygon: water, park, plaza, etc."""
    geometry: List[LatLon]
    kind: str = "park"
    name: str = ""


@dataclass
class Point:
    """A landmark or a tree."""
    location: LatLon
    kind: str = "landmark"
    name: str = ""
    height: int = 0  # for landmarks; 0 -> use a default


@dataclass
class City:
    name: str
    center: LatLon
    buildings: List[Building] = field(default_factory=list)
    roads: List[Road] = field(default_factory=list)
    areas: List[Area] = field(default_factory=list)
    points: List[Point] = field(default_factory=list)

    def bounding_box(self) -> BBox:
        lats: List[float] = [self.center.lat]
        lons: List[float] = [self.center.lon]

        def add(p: LatLon) -> None:
            lats.append(p.lat)
            lons.append(p.lon)

        for b in self.buildings:
            for p in b.geometry:
                add(p)
        for r in self.roads:
            for p in r.geometry:
                add(p)
        for a in self.areas:
            for p in a.geometry:
                add(p)
        for pt in self.points:
            add(pt.location)
        return BBox(south=min(lats), west=min(lons),
                    north=max(lats), east=max(lons))


def _to_latlon_list(coords) -> List[LatLon]:
    return [LatLon(lat=c[1], lon=c[0]) for c in coords]


def load_city(path: str) -> City:
    with open(path, "r", encoding="utf-8") as f:
        doc = json.load(f)
    return city_from_dict(doc)


def city_from_dict(doc: dict) -> City:
    center = LatLon(doc["center"][0], doc["center"][1])
    city = City(name=doc.get("name", "Unnamed"), center=center)
    for feat in doc.get("features", []):
        kind = feat["kind"]
        geom = feat["geometry"]
        if kind == "building":
            city.buildings.append(Building(
                geometry=_to_latlon_list(geom),
                levels=int(feat.get("levels", 2)),
                material=feat.get("material"),
                roof=feat.get("roof"),
                name=feat.get("name", ""),
            ))
        elif kind == "road":
            city.roads.append(Road(
                geometry=_to_latlon_list(geom),
                klass=feat.get("class", "residential"),
                width_m=feat.get("width_m"),
                name=feat.get("name", ""),
                bridge=bool(feat.get("bridge", False)),
            ))
        elif kind in ("water", "park", "plaza"):
            city.areas.append(Area(
                geometry=_to_latlon_list(geom),
                kind=kind,
                name=feat.get("name", ""),
            ))
        elif kind in ("landmark", "tree"):
            city.points.append(Point(
                location=LatLon(geom[1], geom[0]),
                kind=kind,
                name=feat.get("name", ""),
                height=int(feat.get("height", 0)),
            ))
        else:
            raise ValueError(f"Unknown feature kind: {kind!r}")
    return city
