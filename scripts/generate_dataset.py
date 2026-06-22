#!/usr/bin/env python3
"""Generate the bundled New Kensington, PA dataset.

Without live OpenStreetMap access we build a *representative* model of the
city's downtown core, anchored to real-world coordinates and tagged in the same
GeoJSON-style schema the OSM importer emits.  The result is a believable
gridded river town: the numbered-avenue / numbered-street grid, the Allegheny
River, the Tarentum Bridge, Memorial Park and several real landmarks.

Run from the repo root:

    python scripts/generate_dataset.py

It writes ``newken_twin/data/new_kensington.json``.
"""

from __future__ import annotations

import json
import math
import os
from typing import List

# --- real-world anchor ----------------------------------------------------
# Downtown New Kensington, Westmoreland County, Pennsylvania.
CENTER_LAT = 40.5695
CENTER_LON = -79.7647

# Avenue bearing (degrees clockwise from north).  The grid is rotated so the
# avenues run parallel to the Allegheny River (which flows roughly NW->SE).
AVENUE_BEARING = 132.0

AVENUE_SPACING_M = 82.0     # distance between consecutive avenues
STREET_SPACING_M = 108.0    # distance between consecutive cross-streets
N_AVENUES = 8               # Fourth Ave .. Eleventh Ave
N_STREETS = 13              # numbered cross-streets
SETBACK_M = 9.0             # building setback from the block edge

AVENUE_NAMES = ["Fourth Avenue", "Fifth Avenue", "Sixth Avenue",
                "Seventh Avenue", "Eighth Avenue", "Ninth Avenue",
                "Tenth Avenue", "Eleventh Avenue"]

OUT_PATH = os.path.join(os.path.dirname(__file__), "..",
                        "newken_twin", "data", "new_kensington.json")


def meters_per_degree(lat_deg: float):
    lat = math.radians(lat_deg)
    m_lat = 111_132.92 - 559.82 * math.cos(2 * lat) + 1.175 * math.cos(4 * lat)
    m_lon = 111_412.84 * math.cos(lat) - 93.5 * math.cos(3 * lat)
    return m_lat, m_lon


_M_LAT, _M_LON = meters_per_degree(CENTER_LAT)
_ALPHA = math.radians(AVENUE_BEARING)


def uv_to_lonlat(u: float, v: float) -> List[float]:
    """Map local grid metres (u along avenues, v across) to [lon, lat]."""
    east_m = u * math.sin(_ALPHA) + v * math.cos(_ALPHA)
    north_m = u * math.cos(_ALPHA) - v * math.sin(_ALPHA)
    lon = CENTER_LON + east_m / _M_LON
    lat = CENTER_LAT + north_m / _M_LAT
    return [round(lon, 7), round(lat, 7)]


def rect(u0: float, u1: float, v0: float, v1: float) -> List[List[float]]:
    return [uv_to_lonlat(u0, v0), uv_to_lonlat(u1, v0),
            uv_to_lonlat(u1, v1), uv_to_lonlat(u0, v1)]


def build() -> dict:
    features: List[dict] = []

    u_min = -(N_STREETS - 1) * STREET_SPACING_M / 2.0
    u_max = +(N_STREETS - 1) * STREET_SPACING_M / 2.0
    v0 = 0.0  # Fourth Avenue baseline (nearest the river)

    avenue_v = [v0 + i * AVENUE_SPACING_M for i in range(N_AVENUES)]
    street_u = [u_min + j * STREET_SPACING_M for j in range(N_STREETS)]

    # --- Allegheny River (a wide band on the SW side of the grid) ----------
    river_outer = -210.0
    river_inner = -25.0
    features.append({
        "kind": "water",
        "name": "Allegheny River",
        "geometry": rect(u_min - 260, u_max + 260, river_outer, river_inner),
    })

    # --- avenues (run along +u) -------------------------------------------
    for i, v in enumerate(avenue_v):
        name = AVENUE_NAMES[i] if i < len(AVENUE_NAMES) else f"Avenue {i}"
        # Fifth Avenue (i == 1) is the commercial spine -> primary road.
        klass = "primary" if i == 1 else ("secondary" if i in (0, 3) else "residential")
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

            # Downtown core: low avenue index + central streets -> taller.
            core = (i <= 2) and (abs(j - (N_STREETS - 1) / 2) <= 3)
            # Fifth Avenue frontage (avenue index 1) is the commercial spine.
            commercial = core or i == 1
            if i == 0:
                use = "industrial"          # riverfront blocks
            elif commercial:
                use = "commercial"
            else:
                use = "residential"
            if (i + j) % 17 == 0:
                use = "civic"

            if core:
                levels = 3 + ((i + j) % 4)         # 3..6 storeys
            elif use == "industrial":
                levels = 2 + ((i + j) % 2)
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

    # --- Tarentum Bridge across the Allegheny -----------------------------
    bridge_u = street_u[3]
    features.append({
        "kind": "road",
        "name": "Tarentum Bridge",
        "class": "primary",
        "bridge": True,
        "width_m": 14,
        "geometry": [uv_to_lonlat(bridge_u, avenue_v[1]),
                     uv_to_lonlat(bridge_u, river_outer - 40)],
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

    # --- riverwalk along the Allegheny ------------------------------------
    features.append({
        "kind": "riverwalk", "name": "Allegheny Riverwalk",
        "geometry": rect(u_min - 20, u_max + 20, river_inner, river_inner + 8),
    })

    # --- street trees down Fifth Avenue verge -----------------------------
    for k in range(12):
        tu = u_min + 40 + k * 90
        features.append({"kind": "tree", "species": "oak",
                         "geometry": uv_to_lonlat(tu, avenue_v[1] + 14)})

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
        "description": ("Representative digital-twin model of the downtown "
                        "core, anchored to real coordinates. Replace with a "
                        "live OSM export for an exact footprint twin."),
        "center": [CENTER_LAT, CENTER_LON],
        "source": "procedural (newken_twin scripts/generate_dataset.py)",
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
