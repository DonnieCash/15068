"""Geographic helpers for projecting real-world coordinates onto a Minecraft
block grid.

We use a local equirectangular ("plate carree") projection centred on the
city.  Over an area a couple of kilometres across this introduces negligible
distortion while keeping the maths trivial and dependency-free.  One Minecraft
block represents ``meters_per_block`` metres on the ground (default: 1 m).

Block coordinate convention (matches Minecraft / Sponge schematics):
  * +X points east
  * +Z points south
  * origin (0, 0) is the north-west corner of the area being generated
"""

from __future__ import annotations

import math
from dataclasses import dataclass

EARTH_RADIUS_M = 6_378_137.0  # WGS-84 equatorial radius


@dataclass(frozen=True)
class LatLon:
    lat: float
    lon: float


@dataclass(frozen=True)
class BBox:
    """A geographic bounding box (degrees)."""
    south: float
    west: float
    north: float
    east: float

    def contains(self, p: LatLon) -> bool:
        return (self.south <= p.lat <= self.north
                and self.west <= p.lon <= self.east)

    @property
    def center(self) -> LatLon:
        return LatLon((self.south + self.north) / 2.0,
                      (self.west + self.east) / 2.0)


def meters_per_degree(lat_deg: float) -> tuple[float, float]:
    """Return (metres per degree latitude, metres per degree longitude) at the
    given latitude."""
    lat = math.radians(lat_deg)
    m_per_deg_lat = (111_132.92 - 559.82 * math.cos(2 * lat)
                     + 1.175 * math.cos(4 * lat))
    m_per_deg_lon = (111_412.84 * math.cos(lat)
                     - 93.5 * math.cos(3 * lat))
    return m_per_deg_lat, m_per_deg_lon


class Projection:
    """Projects lat/lon to integer block coordinates within a bounding box."""

    def __init__(self, bbox: BBox, meters_per_block: float = 1.0):
        if meters_per_block <= 0:
            raise ValueError("meters_per_block must be positive")
        self.bbox = bbox
        self.meters_per_block = meters_per_block
        center = bbox.center
        self.m_per_deg_lat, self.m_per_deg_lon = meters_per_degree(center.lat)

        # Ground span of the bbox in metres.
        self.width_m = (bbox.east - bbox.west) * self.m_per_deg_lon
        self.height_m = (bbox.north - bbox.south) * self.m_per_deg_lat

        self.width_blocks = max(1, int(round(self.width_m / meters_per_block)))
        self.height_blocks = max(1, int(round(self.height_m / meters_per_block)))

    def to_block(self, p: LatLon) -> tuple[float, float]:
        """Project to (x, z) block coordinates (floats; not yet rounded)."""
        east_m = (p.lon - self.bbox.west) * self.m_per_deg_lon
        # North is +lat, but +Z points south, so invert latitude offset.
        south_m = (self.bbox.north - p.lat) * self.m_per_deg_lat
        return east_m / self.meters_per_block, south_m / self.meters_per_block

    def to_block_int(self, p: LatLon) -> tuple[int, int]:
        x, z = self.to_block(p)
        return int(round(x)), int(round(z))


def haversine_m(a: LatLon, b: LatLon) -> float:
    """Great-circle distance between two points in metres."""
    r = EARTH_RADIUS_M
    phi1, phi2 = math.radians(a.lat), math.radians(b.lat)
    dphi = math.radians(b.lat - a.lat)
    dlam = math.radians(b.lon - a.lon)
    h = (math.sin(dphi / 2) ** 2
         + math.cos(phi1) * math.cos(phi2) * math.sin(dlam / 2) ** 2)
    return 2 * r * math.asin(min(1.0, math.sqrt(h)))


def bbox_around(center: LatLon, half_width_m: float, half_height_m: float) -> BBox:
    """Build a bbox extending the given half-extents (metres) from a centre."""
    m_per_deg_lat, m_per_deg_lon = meters_per_degree(center.lat)
    dlat = half_height_m / m_per_deg_lat
    dlon = half_width_m / m_per_deg_lon
    return BBox(south=center.lat - dlat, west=center.lon - dlon,
                north=center.lat + dlat, east=center.lon + dlon)
