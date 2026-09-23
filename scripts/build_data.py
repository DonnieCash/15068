"""Turn the raw Overture + terrain pulls into compact web data for the site.

    python scripts/fetch_overture.py      # -> data/raw/*.geojson
    python scripts/fetch_terrain.py       # -> data/raw/terrain.json
    python scripts/build_data.py          # -> site/data/*

Everything is clipped to ZIP 15068 (plus a small margin), projected to a local
metre grid centred on the ZIP, quantised, and delta-encoded so the whole
region — every building, road, stream and business — ships as a few MB of
JSON the browser can draw directly. No tile server is involved.
"""
from __future__ import annotations

import datetime as _dt
import json
import math
import re
import struct
from collections import Counter, defaultdict
from pathlib import Path

from shapely import prepared
from shapely.geometry import (LineString, MultiLineString, MultiPolygon, Point,
                              Polygon, shape)
from shapely.ops import unary_union

ROOT = Path(__file__).resolve().parent.parent
RAW = ROOT / "data" / "raw"
OUT = ROOT / "site" / "data"

LON0, LAT0 = -79.7250, 40.5690          # projection origin (centre of 15068)
KX = math.cos(math.radians(LAT0)) * 111320.0
KY = 110574.0
Q = 4                                   # quantisation: 1 unit = 0.25 m
MARGIN_DEG = 0.004                      # ~400 m margin around the ZIP
TERRAIN_CELL = 30                       # metres per terrain sample

# The three municipalities that make up the 15068 ZIP code.
CORE_TOWNS = ("New Kensington", "Arnold", "Lower Burrell")


# --------------------------------------------------------------------------- #
# projection + encoding
# --------------------------------------------------------------------------- #
def proj(lon, lat):
    return (lon - LON0) * KX, (LAT0 - lat) * KY


def unproj(x, y):
    return x / KX + LON0, LAT0 - y / KY


def enc(coords):
    """Quantise + delta-encode a coordinate sequence to a flat int list."""
    out, px, py = [], 0, 0
    for lon, lat in coords:
        x, y = proj(lon, lat)
        qx, qy = round(x * Q), round(y * Q)
        if out and qx == px and qy == py:
            continue
        out.append(qx - px)
        out.append(qy - py)
        px, py = qx, qy
    return out


def rings(geom):
    """Outer + inner rings of any polygonal geometry."""
    if geom.is_empty:
        return []
    polys = [geom] if isinstance(geom, Polygon) else [
        g for g in getattr(geom, "geoms", []) if isinstance(g, Polygon)]
    rs = []
    for p in polys:
        rs.append(list(p.exterior.coords))
        rs.extend(list(i.coords) for i in p.interiors)
    return rs


def lines(geom):
    if geom.is_empty:
        return []
    if isinstance(geom, LineString):
        return [list(geom.coords)]
    return [list(g.coords) for g in getattr(geom, "geoms", [])
            if isinstance(g, LineString)]


def load(name):
    return json.loads((RAW / f"{name}.geojson").read_text())["features"]


def pname(props):
    n = props.get("names") or {}
    return n.get("primary")


def dump(name, obj):
    OUT.mkdir(parents=True, exist_ok=True)
    txt = json.dumps(obj, separators=(",", ":"), ensure_ascii=False)
    (OUT / name).write_text(txt)
    print(f"  {name}: {len(txt) / 1e6:.2f} MB")


# --------------------------------------------------------------------------- #
# place categorisation
# --------------------------------------------------------------------------- #
GROUPS = {
    "eat": "Eat & Drink", "shop": "Shops", "health": "Health",
    "faith": "Faith", "learn": "Schools & Learning", "play": "Parks & Play",
    "civic": "Civic & Safety", "culture": "Arts & History",
    "auto": "Auto & Travel", "services": "Services", "stay": "Lodging",
}


def group_of(props):
    h = (props.get("taxonomy") or {}).get("hierarchy") or []
    top = h[0] if h else None
    sub = h[1] if len(h) > 1 else None
    if top == "food_and_drink":
        return "eat"
    if top == "shopping":
        return "eat" if sub == "food_and_beverage_store" and "bakery" in h else "shop"
    if top == "health_care":
        return "health"
    if top == "cultural_and_historic":
        return "faith" if sub in ("place_of_worship", "religious_organization") else "culture"
    if top == "arts_and_entertainment":
        return "culture"
    if top == "education":
        return "learn"
    if top == "sports_and_recreation":
        return "play"
    if top == "community_and_government":
        return "civic"
    if top == "travel_and_transportation":
        return "auto"
    if top in ("services_and_business", "lifestyle_services"):
        return "services"
    if top == "lodging":
        return "stay"
    return None


def pretty(cat):
    return (cat or "").replace("_", " ").strip().capitalize()


# --------------------------------------------------------------------------- #
# build
# --------------------------------------------------------------------------- #
def main():
    zcta = shape(json.loads((RAW / "zcta15068.geojson").read_text())["geometry"])
    clip = zcta.buffer(MARGIN_DEG)
    clip_p = prepared.prep(clip)
    zcta_p = prepared.prep(zcta)
    minx, miny, maxx, maxy = clip.bounds
    stats = {}

    # ---- municipalities ------------------------------------------------- #
    print("divisions")
    towns = []
    for f in load("division_area"):
        p = f["properties"]
        if p.get("subtype") not in ("locality", "neighborhood") or p.get("class") != "land":
            continue
        g = shape(f["geometry"])
        if not g.intersects(clip):
            continue
        area_in = g.intersection(zcta).area / zcta.area
        towns.append({"name": pname(p), "geom": g, "core": pname(p) in CORE_TOWNS,
                      "share": area_in})
    towns.sort(key=lambda t: (not t["core"], -t["share"]))
    town_prep = [(t["name"], prepared.prep(t["geom"])) for t in towns]

    def town_at(lon, lat):
        pt = Point(lon, lat)
        for n, tp in town_prep:
            if tp.contains(pt):
                return n
        return None

    # ---- base layers ---------------------------------------------------- #
    print("base")
    base = {"zip": [enc(r) for r in rings(zcta.simplify(0.00005))],
            "towns": [], "water": [], "streams": [], "green": [], "use": [],
            "rail": [], "bridges": [], "labels": []}
    for t in towns:
        g = t["geom"].intersection(clip).simplify(0.00003)
        base["towns"].append({"n": t["name"], "core": t["core"],
                              "r": [enc(r) for r in rings(g)]})
        c = t["geom"].intersection(zcta)
        if t["core"] and not c.is_empty:
            lp = c.representative_point()
            x, y = proj(lp.x, lp.y)
            base["labels"].append({"n": t["name"], "k": "town", "x": round(x), "y": round(y)})

    for f in load("water"):
        p = f["properties"]
        g = shape(f["geometry"])
        if not clip_p.intersects(g):
            continue
        g = g.intersection(clip)
        if p.get("class") == "swimming_pool":
            continue
        if g.geom_type in ("Polygon", "MultiPolygon"):
            base["water"].extend(enc(r) for r in rings(g.simplify(0.00001)))
        else:
            w = 3 if p.get("subtype") == "river" else (2 if p.get("subtype") == "canal" else 1)
            for ln in lines(g.simplify(0.00001)):
                base["streams"].append({"n": pname(p), "w": w, "c": enc(ln)})

    use_kind = {"park": "park", "recreation": "park", "golf": "golf",
                "cemetery": "cemetery", "education": "school",
                "developed": "industrial", "managed": "park",
                "agriculture": "farm", "horticulture": "farm",
                "religious": "cemetery"}
    for f in load("land_use"):
        p = f["properties"]
        g = shape(f["geometry"])
        if g.geom_type not in ("Polygon", "MultiPolygon") or not clip_p.intersects(g):
            continue
        k = use_kind.get(p.get("subtype"))
        if not k or p.get("class") in ("bunker", "tee", "green", "rough", "lateral_water_hazard"):
            continue
        if p.get("subtype") == "developed" and p.get("class") in ("retail", "commercial"):
            k = "retail"
        g = g.intersection(clip).simplify(0.00002)
        base["use"].append({"k": k, "n": pname(p), "r": [enc(r) for r in rings(g)]})
        if pname(p) and g.area > 2e-6:
            lp = g.representative_point()
            x, y = proj(lp.x, lp.y)
            base["labels"].append({"n": pname(p), "k": k, "x": round(x), "y": round(y)})

    for f in load("land"):
        p = f["properties"]
        g = shape(f["geometry"])
        if p.get("subtype") not in ("forest", "shrub", "grass", "wetland"):
            continue
        if g.geom_type not in ("Polygon", "MultiPolygon") or not clip_p.intersects(g):
            continue
        g = g.intersection(clip).simplify(0.00003)
        base["green"].extend(enc(r) for r in rings(g))

    for f in load("infrastructure"):
        p = f["properties"]
        if p.get("subtype") != "bridge":
            continue
        g = shape(f["geometry"])
        if not clip_p.intersects(g):
            continue
        if g.geom_type == "Polygon":
            base["bridges"].extend(enc(r) for r in rings(g))

    # ---- roads ---------------------------------------------------------- #
    print("roads")
    road_rank = {"motorway": 0, "trunk": 1, "primary": 1, "secondary": 2,
                 "tertiary": 3, "residential": 4, "unclassified": 4,
                 "living_street": 4, "service": 5, "track": 6,
                 "footway": 7, "path": 7, "steps": 7, "cycleway": 7,
                 "pedestrian": 7, "bridleway": 7, "unknown": 5}
    names, name_ix = [], {}
    roads = []
    street_len = defaultdict(float)
    street_towns = defaultdict(Counter)
    street_pts = defaultdict(list)
    street_rank = {}
    refs = defaultdict(set)
    for f in load("segment"):
        p = f["properties"]
        g = shape(f["geometry"])
        if not clip_p.intersects(g):
            continue
        g = g.intersection(clip)
        if g.is_empty:
            continue
        n = pname(p)
        if p.get("subtype") == "rail":
            for ln in lines(g):
                base["rail"].append(enc(ln))
            continue
        rank = road_rank.get(p.get("class"), 5)
        ni = -1
        if n:
            if n not in name_ix:
                name_ix[n] = len(names)
                names.append(n)
            ni = name_ix[n]
        for r in p.get("routes") or []:
            if r.get("ref") and n:
                refs[n].add(r["ref"])
        brg = 1 if (p.get("road_flags") and any("is_bridge" in (fl.get("values") or [])
                                                   for fl in p["road_flags"])) else 0
        for ln in lines(g):
            roads.append([rank, ni, brg, enc(ln)])
        if n and rank <= 5 and zcta_p.intersects(g):
            gz = g.intersection(zcta)
            m = sum(LineString([proj(*c) for c in ln]).length for ln in lines(gz) if len(ln) > 1)
            street_len[n] += m
            mid = gz.interpolate(0.5, normalized=True) if gz.geom_type == "LineString" else gz.representative_point()
            street_towns[n][town_at(mid.x, mid.y)] += m
            street_pts[n].append((mid.x, mid.y, m))
            street_rank[n] = min(street_rank.get(n, 9), rank)
    roads.sort(key=lambda r: -r[0])
    dump("roads.json", {"names": names, "r": roads})
    stats["road_km"] = round(sum(street_len.values()) / 1000, 1)

    # ---- buildings ------------------------------------------------------ #
    print("buildings")
    bclass = {"residential": 1, "house": 1, "detached": 1, "apartments": 1,
              "semidetached_house": 1, "terrace": 1, "commercial": 2,
              "retail": 2, "office": 2, "industrial": 3, "warehouse": 3,
              "school": 4, "university": 4, "college": 4, "church": 5,
              "religious": 5, "chapel": 5, "civic": 6, "public": 6,
              "government": 6, "post_office": 6, "hospital": 7,
              "garage": 8, "shed": 8, "roof": 8, "carport": 8}
    B = {"h": [], "k": [], "est": [], "p": [], "n": {}}
    heights = []
    town_bcount = Counter()
    for f in load("building"):
        p = f["properties"]
        g = shape(f["geometry"])
        if p.get("is_underground"):
            continue
        c = g.centroid
        if not clip_p.contains(c):
            continue
        k = bclass.get(p.get("class") or p.get("subtype") or "", 0)
        h = p.get("height")
        est = 0
        if not h:
            est = 1
            h = {1: 7.5, 2: 7, 3: 9, 4: 10, 5: 12, 6: 9, 7: 14, 8: 3}.get(k, 6)
            if p.get("num_floors"):
                h = p["num_floors"] * 3.3
        h = max(2.5, min(float(h), 80))
        ring = rings(g)
        if not ring:
            continue
        coords = ring[0][:-1]
        e = enc(coords)
        if len(e) < 6:
            continue
        i = len(B["h"])
        B["h"].append(round(h, 1))
        B["k"].append(k)
        B["est"].append(est)
        B["p"].append(e)
        if pname(p):
            B["n"][i] = pname(p)
        if zcta_p.contains(c):
            town_bcount[town_at(c.x, c.y)] += 1
            if not est:
                heights.append(h)
    dump("buildings.json", B)
    stats["buildings"] = sum(town_bcount.values())
    stats["buildings_by_town"] = dict(town_bcount.most_common())
    stats["tallest_m"] = round(max(heights), 1) if heights else None

    # ---- addresses ------------------------------------------------------ #
    print("addresses")
    addr_count = Counter()
    addr_town = Counter()
    for f in load("address"):
        lon, lat = f["geometry"]["coordinates"][:2]
        if not zcta_p.contains(Point(lon, lat)):
            continue
        st = f["properties"].get("street")
        if st:
            addr_count[st] += 1
        addr_town[town_at(lon, lat)] += 1
    stats["addresses"] = sum(addr_town.values())
    stats["addresses_by_town"] = dict(addr_town.most_common())

    # ---- streets directory --------------------------------------------- #
    def norm(s):
        s = s.lower()
        for a, b in (("avenue", "ave"), ("street", "st"), ("road", "rd"),
                     ("drive", "dr"), ("boulevard", "blvd"), ("lane", "ln")):
            s = re.sub(rf"\b{a}\b", b, s)
        return re.sub(r"[^a-z0-9]", "", s)

    addr_norm = Counter()
    for k, v in addr_count.items():
        addr_norm[norm(k)] += v
    streets = []
    for n, m in street_len.items():
        if m < 25:
            continue
        pts = street_pts[n]
        tot = sum(w for *_, w in pts) or 1
        cx = sum(x * w for x, _, w in pts) / tot
        cy = sum(y * w for _, y, w in pts) / tot
        best = min(pts, key=lambda q: (q[0] - cx) ** 2 + (q[1] - cy) ** 2)
        x, y = proj(best[0], best[1])
        streets.append({"n": n, "m": round(m), "r": street_rank.get(n, 5),
                        "t": [t for t, _ in street_towns[n].most_common() if t][:3],
                        "a": addr_norm.get(norm(n), 0),
                        "ref": sorted(refs.get(n, [])),
                        "x": round(x), "y": round(y)})
    streets.sort(key=lambda s: s["n"])
    dump("streets.json", streets)
    stats["streets"] = len(streets)

    # ---- places --------------------------------------------------------- #
    print("places")
    places, seen = [], {}
    cat_count = Counter()
    for f in load("place"):
        p = f["properties"]
        lon, lat = f["geometry"]["coordinates"][:2]
        n = pname(p)
        if not n or (p.get("confidence") or 0) < 0.5:
            continue
        if not zcta_p.contains(Point(lon, lat)):
            continue
        grp = group_of(p)
        if not grp:
            continue
        x, y = proj(lon, lat)
        key = re.sub(r"[^a-z0-9]", "", n.lower())
        dup = seen.get(key)
        if dup is not None and math.hypot(places[dup]["x"] - x, places[dup]["y"] - y) < 60:
            continue
        a = (p.get("addresses") or [{}])[0]
        addr = ", ".join(v for v in (a.get("freeform"), a.get("locality")) if v)
        cat = (p.get("categories") or {}).get("primary")
        rec = {"n": n, "g": grp, "c": pretty(cat), "x": round(x, 1), "y": round(y, 1),
               "lat": round(lat, 6), "lon": round(lon, 6),
               "t": town_at(lon, lat), "q": round(p.get("confidence") or 0, 2)}
        if addr:
            rec["a"] = addr
        if p.get("phones"):
            digits = re.sub(r"\D", "", p["phones"][0])[-10:]
            if len(digits) == 10:
                rec["ph"] = f"{digits[:3]}-{digits[3:6]}-{digits[6:]}"
        if p.get("websites"):
            rec["w"] = p["websites"][0]
        if p.get("socials"):
            rec["s"] = p["socials"][0]
        brand = ((p.get("brand") or {}).get("names") or {}).get("primary")
        if brand:
            rec["b"] = brand
        seen[key] = len(places)
        places.append(rec)
        cat_count[grp] += 1
    places.sort(key=lambda r: r["n"].lower())
    dump("places.json", places)
    stats["places"] = len(places)
    stats["places_by_group"] = {GROUPS[k]: v for k, v in cat_count.most_common()}
    stats["local_share"] = round(sum(1 for r in places if "b" not in r) / max(1, len(places)), 3)

    # ---- terrain -------------------------------------------------------- #
    print("terrain")
    T = json.loads((RAW / "terrain.json").read_text())
    grid, z, tx0, ty0 = T["grid"], T["z"], T["tx0"], T["ty0"]
    n2 = 2 ** z
    x0, y0 = proj(minx, maxy)
    x1, y1 = proj(maxx, miny)
    W = int((x1 - x0) / TERRAIN_CELL) + 1
    H = int((y1 - y0) / TERRAIN_CELL) + 1

    def sample(lon, lat):
        px = ((lon + 180) / 360 * n2 - tx0) * 256 - 0.5
        r = math.radians(lat)
        py = ((1 - math.log(math.tan(r) + 1 / math.cos(r)) / math.pi) / 2 * n2 - ty0) * 256 - 0.5
        i, j = int(px), int(py)
        fx, fy = px - i, py - j
        vals = []
        for dj, di, w in ((0, 0, (1 - fx) * (1 - fy)), (0, 1, fx * (1 - fy)),
                          (1, 0, (1 - fx) * fy), (1, 1, fx * fy)):
            v = grid[j + dj][i + di]
            if 190 < v < 520:
                vals.append((v, w))
        if not vals:
            return None
        sw = sum(w for _, w in vals) or 1
        return sum(v * w for v, w in vals) / sw

    hm = []
    for j in range(H):
        for i in range(W):
            lon, lat = unproj(x0 + i * TERRAIN_CELL, y0 + j * TERRAIN_CELL)
            hm.append(sample(lon, lat))
    # fill any holes from neighbours
    for _ in range(4):
        for idx, v in enumerate(hm):
            if v is None:
                nb = [hm[k] for k in (idx - 1, idx + 1, idx - W, idx + W)
                      if 0 <= k < len(hm) and hm[k] is not None]
                hm[idx] = sum(nb) / len(nb) if nb else None
    hm = [v if v is not None else 230.0 for v in hm]
    (OUT / "terrain.bin").write_bytes(struct.pack(f"<{len(hm)}H", *[round(v * 10) for v in hm]))
    print(f"  terrain.bin: {W}x{H}")
    stats["elev_min_m"] = round(min(hm))
    stats["elev_max_m"] = round(max(hm))

    stats["area_km2"] = round(zcta.area * KX * KY / 1e6, 1)
    meta = {
        "generated": _dt.date.today().isoformat(),
        "origin": [LON0, LAT0], "kx": KX, "ky": KY, "q": Q,
        "bounds": [round(x0), round(y0), round(x1), round(y1)],
        "terrain": {"w": W, "h": H, "cell": TERRAIN_CELL, "x0": round(x0, 2), "y0": round(y0, 2)},
        "groups": GROUPS,
        "towns": [{"n": t["name"], "core": t["core"],
                   "share": round(t["share"], 3)} for t in towns if t["share"] > 0.001],
        "stats": stats,
        "sources": [
            {"name": "Overture Maps Foundation — places, buildings, transportation, addresses, divisions, base",
             "license": "CDLA-Permissive-2.0 / ODbL (OpenStreetMap-derived layers)",
             "url": "https://overturemaps.org", "release": "2026-08-19.0"},
            {"name": "OpenStreetMap contributors", "license": "ODbL",
             "url": "https://www.openstreetmap.org/copyright"},
            {"name": "US Census TIGER/Line ZCTA5 (ZIP 15068 boundary)",
             "license": "Public domain", "url": "https://www.census.gov/geographies/mapping-files.html"},
            {"name": "Terrain Tiles on AWS (Mapzen terrarium; USGS 3DEP / SRTM)",
             "license": "Public domain / attribution", "url": "https://registry.opendata.aws/terrain-tiles/"},
        ],
    }
    dump("base.json", base)
    dump("meta.json", meta)
    # curated research (history, civic, food, news) ships as-is
    for f in sorted((ROOT / "data" / "research").glob("*.json")):
        dump(f.name, json.loads(f.read_text()))
    print(json.dumps(stats, indent=1))


if __name__ == "__main__":
    main()
