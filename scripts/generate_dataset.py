#!/usr/bin/env python3
"""Generate the bundled New Kensington, PA dataset.

The street grid is anchored to **real geography**: the Allegheny River course,
the grid's orientation and the city's east-bank offset are all derived from the
authoritative US Census TIGER/Line ZCTA boundary for ZIP 15068 (see
``newken_twin/data/nk_real_geo.json``).  Building footprints within that real
frame are modelled procedurally (block-exact footprints require live OSM, which
the OSM importer fetches when network is available).

Run from the repo root:

    python scripts/generate_dataset.py

It writes ``newken_twin/data/new_kensington.json``.
"""

from __future__ import annotations

import json
import math
import os
from typing import List

HERE = os.path.dirname(__file__)
REAL_GEO_PATH = os.path.join(HERE, "..", "newken_twin", "data", "nk_real_geo.json")
OUT_PATH = os.path.join(HERE, "..", "newken_twin", "data", "new_kensington.json")

with open(os.path.normpath(REAL_GEO_PATH), encoding="utf-8") as _f:
    REAL = json.load(_f)

# Real Allegheny River centreline (lon/lat) from the Census ZCTA boundary.
RIVER_POLY: List[List[float]] = REAL["river_polyline_lonlat"]
# Real grid orientation: avenues run parallel to the river.
AVENUE_BEARING = REAL["river_bearing_deg"]        # ~352 deg (nearly N-S here)
DOWNTOWN_LAT, DOWNTOWN_LON = REAL["downtown"]      # [lat, lon]

RIVER_WIDTH_M = 200.0       # rendered width of the Allegheny
RIVER_TO_FIRST_M = 185.0    # First Avenue's offset inland from the centreline
AVENUE_SPACING_M = 82.0     # distance between consecutive avenues
STREET_SPACING_M = 108.0    # distance between consecutive cross-streets
N_AVENUES = 9               # First Avenue .. Ninth Avenue (river -> inland)
N_STREETS = 13              # numbered cross-streets
SETBACK_M = 9.0             # building setback from the block edge

AVENUE_NAMES = ["First Avenue", "Second Avenue", "Third Avenue",
                "Fourth Avenue", "Fifth Avenue", "Sixth Avenue",
                "Seventh Avenue", "Eighth Avenue", "Ninth Avenue"]
COMMERCIAL_AVE = 4          # Fifth Avenue is the historic commercial spine


def meters_per_degree(lat_deg: float):
    lat = math.radians(lat_deg)
    m_lat = 111_132.92 - 559.82 * math.cos(2 * lat) + 1.175 * math.cos(4 * lat)
    m_lon = 111_412.84 * math.cos(lat) - 93.5 * math.cos(3 * lat)
    return m_lat, m_lon


_M_LAT, _M_LON = meters_per_degree(DOWNTOWN_LAT)
_ALPHA = math.radians(AVENUE_BEARING)
_SIN, _COS = math.sin(_ALPHA), math.cos(_ALPHA)

# Anchor the local frame at the river-centreline point nearest downtown.
_ANCHOR = min(RIVER_POLY, key=lambda p: ((p[0] - DOWNTOWN_LON) * _M_LON) ** 2
              + ((p[1] - DOWNTOWN_LAT) * _M_LAT) ** 2)
_ANCHOR_LON, _ANCHOR_LAT = _ANCHOR


def uv_to_lonlat(u: float, v: float) -> List[float]:
    """Local metres (u along the river/avenues, +v inland toward the east
    bank) -> [lon, lat], anchored on the real river centreline."""
    east_m = u * _SIN + v * _COS
    north_m = u * _COS - v * _SIN
    return [round(_ANCHOR_LON + east_m / _M_LON, 7),
            round(_ANCHOR_LAT + north_m / _M_LAT, 7)]


def rect(u0: float, u1: float, v0: float, v1: float) -> List[List[float]]:
    return [uv_to_lonlat(u0, v0), uv_to_lonlat(u1, v0),
            uv_to_lonlat(u1, v1), uv_to_lonlat(u0, v1)]


def _river_polygon(width_m: float) -> List[List[float]]:
    """Buffer the real river centreline by +/- width/2 along the cross axis."""
    half = width_m / 2.0
    # cross-axis (v) unit vector in (east, north): (cos a, -sin a)
    de_lon = (_COS * half) / _M_LON
    de_lat = (-_SIN * half) / _M_LAT
    west = [[round(lon - de_lon, 7), round(lat - de_lat, 7)]
            for lon, lat in RIVER_POLY]
    east = [[round(lon + de_lon, 7), round(lat + de_lat, 7)]
            for lon, lat in RIVER_POLY]
    return west + list(reversed(east))


def build() -> dict:
    features: List[dict] = []

    u_min = -(N_STREETS - 1) * STREET_SPACING_M / 2.0
    u_max = +(N_STREETS - 1) * STREET_SPACING_M / 2.0

    # Avenues march inland (+v) from the real river centreline.
    avenue_v = [RIVER_TO_FIRST_M + i * AVENUE_SPACING_M for i in range(N_AVENUES)]
    street_u = [u_min + j * STREET_SPACING_M for j in range(N_STREETS)]

    # --- the real Allegheny River (Census-derived centreline, buffered) ---
    features.append({
        "kind": "water",
        "name": "Allegheny River",
        "geometry": _river_polygon(RIVER_WIDTH_M),
    })

    # --- avenues (run along +u, parallel to the river) --------------------
    for i, v in enumerate(avenue_v):
        name = AVENUE_NAMES[i] if i < len(AVENUE_NAMES) else f"Avenue {i}"
        if i == COMMERCIAL_AVE:
            klass = "primary"               # Fifth Avenue, the commercial spine
        elif i in (COMMERCIAL_AVE - 1, COMMERCIAL_AVE + 1):
            klass = "secondary"
        else:
            klass = "residential"
        features.append({
            "kind": "road",
            "name": name,
            "class": klass,
            "geometry": [uv_to_lonlat(u_min - 30, v), uv_to_lonlat(u_max + 30, v)],
        })

    # --- numbered cross-streets (run along +v) ----------------------------
    for j, u in enumerate(street_u):
        name = f"{_ordinal(j + 2)} Street"
        klass = "secondary" if j % 4 == 0 else "residential"
        features.append({
            "kind": "road",
            "name": name,
            "class": klass,
            "geometry": [uv_to_lonlat(u, avenue_v[0] - 40),
                         uv_to_lonlat(u, avenue_v[-1] + 40)],
        })

    # --- buildings: fill each block, taller toward the commercial core -----
    for i in range(N_AVENUES - 1):
        for j in range(N_STREETS - 1):
            bu0 = street_u[j] + SETBACK_M
            bu1 = street_u[j + 1] - SETBACK_M
            bv0 = avenue_v[i] + SETBACK_M
            bv1 = avenue_v[i + 1] - SETBACK_M
            if bu1 - bu0 < 12 or bv1 - bv0 < 12:
                continue

            # Downtown core: around the commercial spine + central streets.
            core = (abs(i - COMMERCIAL_AVE) <= 1) and (abs(j - (N_STREETS - 1) / 2) <= 3)
            commercial = core or i == COMMERCIAL_AVE
            if i <= 1:
                use = "industrial"          # riverfront blocks
            elif commercial:
                use = "commercial"
            else:
                use = "residential"
            if (i + j) % 17 == 0:
                use = "civic"

            if core:
                levels = 3 + ((i + j) % 4)         # 3..6 storeys
            else:
                levels = 2 + ((i + j) % 2)         # 2..3 storeys

            mat = _wall_for(i, j) if use == "residential" else None

            # Split larger blocks into two structures for a finer grain.
            if (bu1 - bu0) > 70:
                mid = (bu0 + bu1) / 2.0
                features.append(_building(bu0, mid - 4, bv0, bv1, levels, mat, use))
                features.append(_building(mid + 4, bu1, bv0, bv1,
                                          max(2, levels - 1), mat, use))
            else:
                features.append(_building(bu0, bu1, bv0, bv1, levels, mat, use))

    # --- Constitution Boulevard: a primary arterial along the valley ------
    features.append({
        "kind": "road", "name": "Constitution Boulevard", "class": "primary",
        "width_m": 14,
        "geometry": [uv_to_lonlat(street_u[1], avenue_v[2] + 20),
                     uv_to_lonlat(street_u[-2], avenue_v[2] + 20)],
    })

    # --- Tarentum Bridge across the real Allegheny ------------------------
    bridge_u = street_u[6]
    features.append({
        "kind": "road",
        "name": "Tarentum Bridge",
        "class": "primary",
        "bridge": True,
        "width_m": 14,
        "geometry": [uv_to_lonlat(bridge_u, avenue_v[0]),
                     uv_to_lonlat(bridge_u, -(RIVER_WIDTH_M / 2 + 60))],
    })

    # --- Memorial Park + pond + war monument ------------------------------
    pu0 = street_u[-3]
    features.append({
        "kind": "park",
        "name": "Memorial Park",
        "geometry": rect(pu0, pu0 + 150, avenue_v[4] + 10, avenue_v[6] - 10),
    })
    features.append({
        "kind": "pond", "name": "Memorial Park Pond",
        "geometry": rect(pu0 + 95, pu0 + 135, avenue_v[5] - 15, avenue_v[5] + 25),
    })
    features.append({
        "kind": "landmark", "name": "Veterans Memorial", "structure": "monument",
        "height": 16, "geometry": uv_to_lonlat(pu0 + 40, avenue_v[5] + 5),
    })
    # park trees of mixed species
    species = ["oak", "birch", "spruce", "dark_oak"]
    for k in range(10):
        tu = pu0 + 18 + (k % 5) * 28
        tv = avenue_v[4] + 22 + (k // 5) * 64
        features.append({"kind": "tree", "species": species[k % 4],
                         "geometry": uv_to_lonlat(tu, tv)})

    # --- riverwalk between the east bank and First Avenue -----------------
    walk_v = RIVER_WIDTH_M / 2 + 18
    features.append({
        "kind": "riverwalk", "name": "Allegheny Riverwalk",
        "geometry": rect(u_min - 20, u_max + 20, walk_v, walk_v + 8),
    })

    # --- street trees down Fifth Avenue verge -----------------------------
    for k in range(12):
        tu = u_min + 40 + k * 90
        features.append({"kind": "tree", "species": "oak",
                         "geometry": uv_to_lonlat(tu, avenue_v[COMMERCIAL_AVE] + 14)})

    # --- modelled landmarks (approximate positions within the core) -------
    landmarks = [
        ("Mount Saint Peter Church", street_u[2], avenue_v[5] + 30, 40, "church", 22),
        ("New Kensington City Hall", street_u[6], avenue_v[1] + 22, 30, "cityhall", 24),
        ("Citizens General Hospital", street_u[10], avenue_v[3] + 30, 34, "tower", 28),
        ("PNC Bank Building", street_u[5] + 10, avenue_v[1] - 12, 30, "tower", 16),
    ]
    for name, u, v, h, structure, fp in landmarks:
        features.append({
            "kind": "landmark", "name": name, "height": h,
            "structure": structure, "footprint": fp,
            "geometry": uv_to_lonlat(u, v),
        })

    return {
        "name": "New Kensington, Pennsylvania",
        "description": ("Digital-twin model anchored to real geography: the "
                        "Allegheny River course, grid orientation and east-bank "
                        "offset come from the US Census ZCTA boundary for 15068. "
                        "Building footprints are modelled; use the OSM importer "
                        "for block-exact footprints."),
        "center": [DOWNTOWN_LAT, DOWNTOWN_LON],
        "source": ("procedural grid on real Census geometry "
                   "(scripts/generate_dataset.py + data/nk_real_geo.json)"),
        "features": features,
    }


def _building(u0, u1, v0, v1, levels, material, use) -> dict:
    feat = {
        "kind": "building",
        "geometry": rect(u0, u1, v0, v1),
        "levels": levels,
        "use": use,
    }
    if material:
        feat["material"] = material
    return feat


_WALLS = ["wall_brick", "wall_concrete", "wall_stone",
          "wall_terracotta", "wall_sandstone"]


def _wall_for(i: int, j: int) -> str:
    return _WALLS[(i * 3 + j) % len(_WALLS)]


def _ordinal(n: int) -> str:
    if 10 <= n % 100 <= 20:
        suffix = "th"
    else:
        suffix = {1: "st", 2: "nd", 3: "rd"}.get(n % 10, "th")
    return f"{n}{suffix}"


def main() -> None:
    doc = build()
    out = os.path.normpath(OUT_PATH)
    with open(out, "w", encoding="utf-8") as f:
        json.dump(doc, f, indent=1)
    counts = {}
    for feat in doc["features"]:
        counts[feat["kind"]] = counts.get(feat["kind"], 0) + 1
    print(f"Wrote {out}")
    print(f"Features: {counts} (total {len(doc['features'])})")


if __name__ == "__main__":
    main()
