"""Build site/data/safety.json: crime statistics, policing, and mapped incidents.

    python scripts/build_safety.py

Inputs (all hand-verified research, every item sourced):
    data/research/crime/fbi.json        FBI UCR annual counts per police department
    data/research/crime/policing.json   agencies, activity stats, notable interactions
    data/research/crime/incidents.json  news-reported incidents with a mappable location
    data/research/crime/crashes.json    police-reported crash summaries (optional)

Incidents are geocoded against the Overture/NAD address points and street
centerlines already pulled into data/raw/. Locations are deliberately coarsened
the way police blotters do it: a house number becomes the median point of its
hundred-block, and the displayed text never carries the exact address.
"""
from __future__ import annotations

import json
import os
import re
import statistics
from collections import Counter, defaultdict
from pathlib import Path

from shapely import prepared
from shapely.geometry import LineString, MultiLineString, Point, shape
from shapely.ops import linemerge, nearest_points, unary_union

import build_data as bd

ROOT = bd.ROOT
CRIME = Path(os.environ.get("NK_CRIME_DIR", ROOT / "data" / "research" / "crime"))
OUT = bd.OUT

# incident type -> map category (three hues max: see nk.css --inc-*)
CATEGORY = {
    "homicide": "violent", "shooting": "violent", "stabbing": "violent",
    "robbery": "violent", "assault": "violent", "weapons": "violent", "standoff": "violent",
    "burglary": "property", "theft": "property", "vehicle_theft": "property",
    "arson": "property", "vandalism": "property", "fraud": "property",
    "police_shooting": "police", "use_of_force": "police", "pursuit": "police",
    "drugs": "police", "crash": "police", "fire": "police", "other": "police",
}
EXCLUDED_TYPES = {"sexual_assault", "rape", "sex_offense"}

# Named places that the incident reports use but Overture doesn't carry, resolved
# from the reports themselves (e.g. the DA's CrimeWatch posts put Valley Royal
# Court at Fourth Avenue and Hileman Drive, across from City Hall).
GAZETTEER = {
    "valleyroyalcourt": {"street": "Fourth Avenue", "cross_street": "Hileman Drive"},
    "hillcrestshoppingcenter": {"addr_contains": "hillcrest shopping ctr", "label": "Hillcrest Shopping Center"},
}

ORDINALS = {
    "first": "1st", "second": "2nd", "third": "3rd", "fourth": "4th", "fifth": "5th",
    "sixth": "6th", "seventh": "7th", "eighth": "8th", "ninth": "9th", "tenth": "10th",
    "eleventh": "11th", "twelfth": "12th", "thirteenth": "13th", "fourteenth": "14th",
    "fifteenth": "15th", "sixteenth": "16th", "seventeenth": "17th", "eighteenth": "18th",
    "nineteenth": "19th", "twentieth": "20th",
}
TYPES = {
    "street": "st", "st": "st", "avenue": "ave", "ave": "ave", "av": "ave",
    "road": "rd", "rd": "rd", "drive": "dr", "dr": "dr", "boulevard": "blvd", "blvd": "blvd",
    "lane": "ln", "ln": "ln", "court": "ct", "ct": "ct", "place": "pl", "pl": "pl",
    "way": "way", "alley": "aly", "aly": "aly", "terrace": "ter", "ter": "ter",
    "highway": "hwy", "hwy": "hwy", "pike": "pike", "circle": "cir", "cir": "cir",
    "extension": "ext", "ext": "ext", "bypass": "byp",
}
DIRS = {"north": "n", "south": "s", "east": "e", "west": "w", "n": "n", "s": "s", "e": "e", "w": "w"}


def street_key(name: str | None):
    """-> (core, type) e.g. 'Fifth Avenue' -> ('5th', 'ave'); None if empty."""
    if not name:
        return None
    s = re.sub(r"[.,#']", " ", name.lower())
    s = re.sub(r"\b(route|rt|sr|pa|state route)\s*(\d+)", r"route\2", s)
    toks = [ORDINALS.get(t, t) for t in s.split()]
    toks = [re.sub(r"^(\d+)(st|nd|rd|th)$", r"\1th", t) for t in toks]  # 1st/2nd -> 1th: one canonical form
    typ = None
    while toks and toks[-1] in TYPES:
        typ = typ or TYPES[toks[-1]]
        toks.pop()
    toks = [DIRS.get(t, t) for t in toks]
    if toks and toks[0] in ("n", "s", "e", "w") and len(toks) > 1:
        toks = toks[1:]
    core = " ".join(toks).strip()
    return (core, typ) if core else None


def pretty_street(name: str) -> str:
    t = re.sub(r"\s+", " ", name).strip().title().replace("'S", "'s")
    return re.sub(r"(\d)(St|Nd|Rd|Th)\b", lambda m: m.group(1) + m.group(2).lower(), t)


def load_geo():
    zcta = shape(json.loads((bd.RAW / "zcta15068.geojson").read_text())["geometry"])
    clip = prepared.prep(zcta.buffer(bd.MARGIN_DEG))
    towns = {}
    for f in bd.load("division_area"):
        p = f["properties"]
        if p.get("subtype") == "locality" and p.get("class") == "land" and bd.pname(p) in bd.CORE_TOWNS:
            towns[bd.pname(p)] = shape(f["geometry"])
    tprep = {n: prepared.prep(g) for n, g in towns.items()}

    def town_at(lon, lat):
        pt = Point(lon, lat)
        for n, g in tprep.items():
            if g.contains(pt):
                return n
        return None

    addrs = defaultdict(list)          # (core,type) -> [(num, lon, lat, town, raw street)]
    for f in bd.load("address"):
        pr = f["properties"]
        lon, lat = f["geometry"]["coordinates"][:2]
        if not clip.contains(Point(lon, lat)):
            continue
        k = street_key(pr.get("street"))
        m = re.match(r"\d+", str(pr.get("number") or ""))
        if not k or not m:
            continue
        addrs[k].append((int(m.group()), lon, lat, town_at(lon, lat), pr.get("street")))

    roads = defaultdict(list)          # (core,type) -> [(LineString lon/lat, raw name)]
    for f in bd.load("segment"):
        p = f["properties"]
        if p.get("subtype") != "road":
            continue
        n = bd.pname(p)
        k = street_key(n)
        if not k:
            continue
        g = shape(f["geometry"])
        if not clip.intersects(g):
            continue
        roads[k].append((g, n))
    return towns, town_at, addrs, roads


def candidates(index, key):
    """Exact (core,type) first, then every other type sharing the core."""
    if not key:
        return []
    exact = [key] if key in index else []
    return exact + [k for k in index if k[0] == key[0] and k != key]


def merge_lines(geoms):
    """Union + linemerge that tolerates a single LineString or mixed collections."""
    u = unary_union(list(geoms))
    if u.geom_type == "LineString":
        return u
    parts = [g for g in getattr(u, "geoms", []) if g.geom_type == "LineString"]
    if not parts:
        return u
    return linemerge(parts) if len(parts) > 1 else parts[0]


class Geocoder:
    """Places incidents on street centerlines — never on a house or parcel.

    Every non-place result is a point on the road centerline: a hundred-block is
    the stretch of centerline beside that block's address points; an intersection
    is where two centerlines meet; "street only" is the point on the street
    nearest an anchor (a reported place or coordinates), else its midpoint.
    Labels come from the segment actually used, so a New Kensington block never
    borrows a same-named street across the river.
    """

    def __init__(self, towns, town_at, addrs, roads, places):
        self.towns, self.town_at, self.addrs, self.roads, self.places = towns, town_at, addrs, roads, places

    def _in_town(self, town):
        tgeom = self.towns.get(town)
        tp = prepared.prep(tgeom.buffer(0.0015)) if tgeom is not None else None
        return (lambda lon, lat: tp.contains(Point(lon, lat))) if tp else (lambda lon, lat: True)

    def _segments(self, k, town):
        tgeom = self.towns.get(town)
        buf = tgeom.buffer(0.0015) if tgeom is not None else None
        return [(g, n) for g, n in self.roads.get(k, []) if buf is None or g.intersects(buf)]

    def _line_near(self, k, town, pt, any_type=False):
        """(merged line component nearest pt, name of the nearest segment).

        With any_type, every road sharing the street's core name is considered, so
        a block whose addresses say "7th Street Road" can sit on the segment that
        Overture calls "7th Street" — whichever centerline is actually beside it."""
        keys = candidates(self.roads, k) if any_type else [k]
        segs = [s for kk in keys for s in self._segments(kk, town)]
        if not segs:
            return None, None
        g, name = min(segs, key=lambda s: s[0].distance(pt))
        merged = merge_lines(s[0] for s in segs)
        comps = [merged] if merged.geom_type == "LineString" else list(getattr(merged, "geoms", []))
        comp = min(comps, key=lambda c: c.distance(pt)) if comps else g
        return comp, name

    def place_anchor(self, name, town):
        """Coordinates for a named place (places directory or gazetteer), or None."""
        if not name:
            return None
        in_town = self._in_town(town)
        pn = re.sub(r"[^a-z]", "", name.lower())
        gz = next((v for k, v in GAZETTEER.items() if k in pn), None)
        if gz and gz.get("addr_contains"):
            hits = [p for p in self.places if gz["addr_contains"] in (p.get("a") or "").lower() and in_town(p["lon"], p["lat"])]
            if hits:
                return Point(statistics.median(p["lon"] for p in hits), statistics.median(p["lat"] for p in hits))
        if gz and gz.get("street"):
            x = self.intersection(street_key(gz["street"]), street_key(gz["cross_street"]), town)
            if x:
                return x[0]
        stop = {"the", "of", "and", "new", "kensington", "arnold", "lower", "burrell", "pa", "inc", "llc", "at", "on"}
        toks = lambda t: {w for w in re.findall(r"[a-z0-9]+", t.lower().replace("'s", "")) if w not in stop and len(w) > 1}
        nk = re.sub(r"[^a-z0-9]", "", name.lower())
        qt = toks(name)
        best = None
        for p in self.places:
            pk = re.sub(r"[^a-z0-9]", "", p["n"].lower())
            prefix = len(nk) >= 5 and (pk == nk or pk.startswith(nk) or (len(pk) >= 6 and nk.startswith(pk)))
            subset = len(qt) >= 2 and qt <= toks(p["n"])
            if (prefix or subset) and in_town(p["lon"], p["lat"]):
                if best is None or (p.get("t") == town and best.get("t") != town):
                    best = p
        return Point(best["lon"], best["lat"]) if best else None

    def block(self, key, num, town):
        """Centerline point for a hundred-block, from matching address points or
        by interpolating between neighbouring numbers on the same street."""
        in_town = self._in_town(town)
        block = int(num) // 100 * 100
        for k in candidates(self.addrs, key):
            pts = [a for a in self.addrs[k] if in_town(a[1], a[2])]
            same = [a for a in pts if block <= a[0] < block + 100]
            if not same:
                continue
            mid = Point(statistics.mean(a[1] for a in same), statistics.mean(a[2] for a in same))
            line, name = self._line_near(k, town, mid, any_type=True)
            if line is None or line.distance(mid) > 0.0005:      # centerline must be beside the block (~40 m)
                continue
            span = same
            if len(same) < 2:
                # one address in the block: widen to its numbered neighbours so the pin marks the block, not the house
                pts_sorted = sorted(pts, key=lambda a: a[0])
                lo = [a for a in pts_sorted if a[0] < block][-1:]
                hi = [a for a in pts_sorted if a[0] >= block + 100][:1]
                span = lo + same + hi
            proj = sorted(line.project(Point(a[1], a[2])) for a in span)
            p = line.interpolate((proj[0] + proj[-1]) / 2)
            raw = Counter(a[4] for a in same).most_common(1)[0][0]
            return p, f"{block} block of {pretty_street(raw or name)}"
        # no address points in that block: interpolate along the street between
        # the nearest lower and higher house numbers (never borrow a neighbour block)
        for k in candidates(self.addrs, key):
            pts = sorted((a for a in self.addrs[k] if in_town(a[1], a[2])), key=lambda a: a[0])
            lo = [a for a in pts if a[0] < block]
            hi = [a for a in pts if a[0] >= block + 100]
            if not lo or not hi or hi[0][0] - lo[-1][0] > 600:
                continue
            a0, a1 = lo[-1], hi[0]
            mid = Point((a0[1] + a1[1]) / 2, (a0[2] + a1[2]) / 2)
            line, name = self._line_near(k, town, mid, any_type=True)
            if line is None or line.distance(mid) > 0.0005:
                continue
            d0, d1 = line.project(Point(a0[1], a0[2])), line.project(Point(a1[1], a1[2]))
            t = (block + 50 - a0[0]) / max(1, a1[0] - a0[0])
            p = line.interpolate(d0 + (d1 - d0) * t)
            return p, f"{block} block of {pretty_street(name or a0[4])}"
        return None

    def intersection(self, key, xkey, town):
        """Where two named centerlines meet (tolerates "Wildlife Lodge Rd" vs "Wildlife Rd")."""
        if not key or not xkey:
            return None
        in_town = self._in_town(town)

        def variants(k):
            exact = [c for c in candidates(self.roads, k)]
            head = k[0].split()[0]
            return exact + [c for c in self.roads if c not in exact and c[0].split()[0] == head]

        best = None
        for k1 in variants(key):
            for k2 in variants(xkey):
                if k1 == k2:
                    continue
                s1, s2 = self._segments(k1, town), self._segments(k2, town)
                if not s1 or not s2:
                    continue
                a = unary_union([g for g, _ in s1])
                b = unary_union([g for g, _ in s2])
                d = a.distance(b)
                if d > 0.0004:            # ~40 m
                    continue
                if d == 0:
                    hit = a.intersection(b)
                    pts = [g.centroid for g in getattr(hit, "geoms", [hit]) if not g.is_empty]
                else:
                    p1, p2 = nearest_points(a, b)
                    pts = [p1]            # stay on the first street's centerline
                pts = [p for p in pts if in_town(p.x, p.y)]
                if pts and (best is None or d < best[0]):
                    best = (d, pts[0], k1, k2)
        if not best:
            return None
        _, p, k1, k2 = best
        n1 = min(self._segments(k1, town), key=lambda s: s[0].distance(p))[1]
        n2 = min(self._segments(k2, town), key=lambda s: s[0].distance(p))[1]
        return p, f"{pretty_street(n1)} & {pretty_street(n2)}"

    def street(self, key, town, anchor=None, coarse=0.0):
        """A point on the named street: nearest the anchor if given, else the midpoint.
        coarse (in degrees along the line) snaps the anchor's position to bins so a
        withheld place isn't pinpointed."""
        for k in candidates(self.roads, key):
            segs = self._segments(k, town)
            tgeom = self.towns.get(town)
            if tgeom is not None:
                segs = [s for s in segs if s[0].intersects(tgeom)]
            if not segs:
                continue
            if anchor is not None:
                line, name = self._line_near(k, town, anchor)
                if line.distance(anchor) > 0.006:      # anchor isn't on this street (~500 m)
                    anchor = None
                else:
                    d = line.project(anchor)
                    if coarse:
                        d = min(line.length, (int(d / coarse) + 0.5) * coarse)
                    return line.interpolate(d), pretty_street(name)
            u = unary_union([g for g, _ in segs])
            if tgeom is not None:
                u = u.intersection(tgeom)
            if u.is_empty:
                continue
            merged = merge_lines([u]) if u.geom_type != "LineString" else u
            m = merged if merged.geom_type == "LineString" else max(getattr(merged, "geoms", [merged]), key=lambda g: g.length)
            p = m.interpolate(0.5, normalized=True)
            name = min(segs, key=lambda s: s[0].distance(p))[1]
            return p, pretty_street(name)
        return None

    def geocode(self, inc):
        """-> (lon, lat, precision, label) or None. Honors the incident's label_policy."""
        town = inc["municipality"]
        policy = inc.get("label_policy") or "use_place_name"
        key = street_key(inc.get("street"))
        xkey = street_key(inc.get("cross_street"))
        pname = inc.get("place_name")
        anchor = Point(inc["lon"], inc["lat"]) if inc.get("lat") is not None and inc.get("lon") is not None else None
        coarse = 0.0
        if anchor is None and inc.get("anchor"):
            # a withheld place, stored only as a ~100 m anchor: bin it along the street too
            anchor, coarse = Point(*inc["anchor"]), 0.0015
        if anchor is None and pname:
            anchor = self.place_anchor(pname, town)
            if policy == "use_street_only":
                coarse = 0.0015          # withheld place: ~150 m bins along the street, never the doorstep
        gz = next((v for k, v in GAZETTEER.items() if k in re.sub(r"[^a-z]", "", (pname or "").lower())), None)

        if policy == "use_street_only":
            # the reviewer ruled that neither a place name nor a cross street may be shown
            xkey, pname = None, None
        elif gz and gz.get("street") and not xkey:
            key = key or street_key(gz["street"])
            xkey = street_key(gz["cross_street"])

        coords_only = inc.get("lat") is not None and not inc.get("number")
        if key and inc.get("number") and not coords_only:
            r = self.block(key, inc["number"], town)
            if r:
                return r[0].x, r[0].y, "block", r[1]
        if key and xkey:
            r = self.intersection(key, xkey, town)
            if r:
                return r[0].x, r[0].y, "intersection", r[1]
        if pname and policy == "use_place_name":
            if gz and gz.get("label") and anchor is not None:
                return anchor.x, anchor.y, "place", gz["label"]
            k = street_key(pname)
            if k in self.roads:                                  # e.g. "New Kensington Bridge"
                r = self.street(k, town)
                if r:
                    return r[0].x, r[0].y, "place", r[1]
            if anchor is not None:
                return anchor.x, anchor.y, "place", pname.split(" (")[0].split(" / ")[0]
        if key:
            r = self.street(key, town, anchor, coarse)
            if r:
                return r[0].x, r[0].y, "street", r[1]
        return None


SUFFIX = r"(?:Street|St|Avenue|Ave|Av|Road|Rd|Drive|Dr|Boulevard|Blvd|Lane|Ln|Way|Court|Ct|Alley|Aly|Place|Pl|Terrace|Ter|Circle|Cir|Pike|Highway|Hwy)\b"
HOUSE_RE = re.compile(r"(?<![\d/.,])\b(\d{2,5})(?:\s+\d/\d)?(\s+(?:block of\s+)?)(?=(?:[NSEW]\.?\s+|(?:North|South|East|West)\s+)?(?:\d+(?:st|nd|rd|th)|[A-Z][a-z]+)(?:\s+[A-Z][a-z]+)?\s+" + SUFFIX + ")")


def scrub(text: str) -> str:
    """Replace exact house numbers ('1024 Fifth Ave') with hundred-blocks.

    Only a number followed by a street name *and* a street suffix counts, so
    years and counts ("in 2024 Police said", "27 bricks") are left alone.
    """
    def rep(m):
        n = int(m.group(1))
        before = m.string[max(0, m.start() - 4):m.start()].lower()
        lead = "" if before.endswith("the ") else "the "
        return f"{lead}unit block of " if n < 100 else f"{lead}{n // 100 * 100} block of "
    out = HOUSE_RE.sub(rep, text).replace("block of block of", "block of")
    return re.sub(r"\bthe the\b", "the", out)


def load_json(name, default):
    p = CRIME / name
    return json.loads(p.read_text()) if p.exists() else default


def main():
    fbi = load_json("fbi.json", {"agencies": []})
    policing = load_json("policing.json", {})
    incidents = load_json("incidents.json", {"incidents": []})
    crashes = load_json("crashes.json", {})
    places = json.loads((OUT / "places.json").read_text())

    towns, town_at, addrs, roads = load_geo()
    geo = Geocoder(towns, town_at, addrs, roads, places)
    print(f"address index: {sum(len(v) for v in addrs.values())} points on {len(addrs)} streets")

    # fill each agency-year's missing population from the nearest year that has one
    for ag in fbi.get("agencies", []):
        yrs = sorted(ag.get("years", []), key=lambda y: y["year"])
        known = [(y["year"], y["population"]) for y in yrs if y.get("population")]
        for y in yrs:
            if not y.get("population") and known:
                near = min(known, key=lambda k: abs(k[0] - y["year"]))
                y["population"] = near[1]
                y["population_estimated_from"] = near[0]
        ag["years"] = yrs

    out_inc, unplaced = [], []
    for inc in incidents.get("incidents", []):
        if inc.get("type") in EXCLUDED_TYPES:
            continue
        inc = dict(inc)
        g = geo.geocode(inc)
        if not g:
            unplaced.append(inc)
            continue
        lon, lat, prec, label = g
        x, y = bd.proj(lon, lat)
        out_inc.append({
            "d": inc["date"], "k": inc["type"], "c": CATEGORY.get(inc["type"], "police"),
            "t": inc["municipality"], "x": round(x, 1), "y": round(y, 1),
            "lat": round(lat, 5), "lon": round(lon, 5),
            "p": prec, "l": label, "s": scrub(inc["summary"]),
            "pi": bool(inc.get("police_involved")),
            "src": inc["source"],
            "n": inc.get("n_sources", 1), "cf": inc.get("confidence", ""),
        })
    # guard: no published non-place point may sit on (or next to) an address point
    tree = [(a[1], a[2]) for pts in addrs.values() for a in pts]
    kx, ky = bd.KX, bd.KY
    for r in out_inc:
        if r["p"] == "place":
            continue
        dmin = min(((lon - r["lon"]) * kx) ** 2 + ((lat - r["lat"]) * ky) ** 2 for lon, lat in tree) ** 0.5
        if dmin < 6:
            raise SystemExit(f"privacy guard: incident '{r['l']}' ({r['d']}) is {dmin:.1f} m from an address point")
    out_inc.sort(key=lambda r: r["d"], reverse=True)
    print(f"incidents placed {len(out_inc)}, unplaced {len(unplaced)}")
    for u in unplaced:
        print("  unplaced:", u["date"], u["municipality"], "|", u.get("location_text"))

    # police-reported serious crashes: keep those inside the three cities
    pts, stats = [], defaultdict(lambda: {"crashes": 0, "fatal": 0, "serious": 0})
    # learn PennDOT municipality code -> town from the crashes that have coordinates
    votes = defaultdict(Counter)
    for c in crashes.get("points", []):
        if c.get("lat") is not None and c.get("muni"):
            votes[c["muni"]][town_at(c["lon"], c["lat"])] += 1
    code_town = {m: v.most_common(1)[0][0] for m, v in votes.items()
                 if v.most_common(1)[0][0] and v.most_common(1)[0][1] >= 0.8 * sum(v.values()) and sum(v.values()) >= 5}
    print(f"PennDOT codes -> towns: {code_town}")
    unmapped = 0
    for c in crashes.get("points", []):
        has_xy = c.get("lat") is not None
        t = code_town.get(c.get("muni")) or (town_at(c["lon"], c["lat"]) if has_xy else None)
        if not t:
            continue
        if has_xy:
            x, y = bd.proj(c["lon"], c["lat"])
            pts.append({"yr": c["year"], "mo": c.get("month"), "t": t, "x": round(x, 1), "y": round(y, 1),
                        "lat": c["lat"], "lon": c["lon"], "f": c["fatal"], "s": c["serious"], "col": c["collision"]})
        else:
            unmapped += 1
        st = stats[(t, c["year"])]
        st["crashes"] += 1
        st["fatal"] += c["fatal"]
        st["serious"] += c["serious"]
    crash_doc = {"source": crashes.get("source"), "notes": crashes.get("notes", ""), "points": pts, "unmapped": unmapped,
                 "stats": [{"t": t, "year": y, **v} for (t, y), v in sorted(stats.items())]}
    print(f"crashes in the three cities: {len(pts)}")

    policing = dict(policing)
    policing["wapo_fatal_shootings_in_area"] = [
        {k: v for k, v in w.items() if k not in ("lat", "lon")} for w in policing.get("wapo_fatal_shootings_in_area", [])]
    doc = {
        "fbi": fbi,
        "policing": policing,
        "crashes": crash_doc,
        "incidents": out_inc,
        "unplaced": len(unplaced),
        "precision_counts": {p: sum(1 for r in out_inc if r["p"] == p) for p in ("block", "intersection", "place", "street")},
    }
    bd.dump("safety.json", doc)


if __name__ == "__main__":
    main()
