"""Loads every input the pages are built from into one dict, D.

D keys: cfg, today (date), meta, places, streets, roads, base, safety, civic, history, pets, board (None
unless --snapshot), changelog, dates (see DATES), root (repo Path), site (site dir Path).
"""
import json
import math
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SITE = ROOT / "site"
RESEARCH = ROOT / "data" / "research"
CORE_TOWNS = ("New Kensington", "Arnold", "Lower Burrell")
TOWN_SLUGS = {"New Kensington": "new-kensington", "Arnold": "arnold", "Lower Burrell": "lower-burrell"}
SLUG_TOWNS = {v: k for k, v in TOWN_SLUGS.items()}
# research files synced into site/data/ (as public_copy(), with build_data.dump's serializer)
SYNCED = ("civic", "history", "pets")


def read_json(p, default=None):
    p = Path(p)
    if not p.exists():
        return default
    return json.loads(p.read_text(encoding="utf-8"))


def dumps(obj):
    """The same bytes build_data.dump writes."""
    return json.dumps(obj, separators=(",", ":"), ensure_ascii=False)


# research fields that are working notes, never published; and fields public() must not touch
PRIVATE_KEYS = {"method", "note", "notes", "date_note", "population_note", "coverage"}
RAW_KEYS = {"source", "url", "date", "dates", "deadline", "year", "phone", "compiled", "zip"}


def public_copy(obj, key=None):
    """The research JSON as published under site/data/: working notes dropped and every text field passed through
    fmt.public(), the same filter the pages use."""
    from .fmt import public
    if isinstance(obj, dict):  # "_meta" is published as "about": just the compile date and the ZIP
        return {("about" if k == "_meta" else k): public_copy(v, k) for k, v in obj.items() if k not in PRIVATE_KEYS}
    if isinstance(obj, list):
        return [public_copy(v, key) for v in obj]
    if isinstance(obj, str) and key not in RAW_KEYS:
        return public(obj)
    return obj


def load(cfg, today, snapshot=False, site=SITE, board=None):
    data = site / "data"
    D = {"cfg": cfg, "today": today, "root": ROOT, "site": site}
    D["meta"] = read_json(data / "meta.json")
    for k in ("places", "streets", "roads", "base", "safety"):
        D[k] = read_json(data / f"{k}.json")
    for k in SYNCED:
        D[k] = read_json(RESEARCH / f"{k}.json")
    D["board"] = read_json(Path(board) if board else data / "pets-board.json") if snapshot else None
    D["changelog"] = read_json(ROOT / "data" / "changelog.json", []) or []
    D["dates"] = DATES(D)
    return D


def DATES(D):
    """The data date behind each kind of page ("Updated …"); never depends on --today."""
    meta = D["meta"]["generated"]
    return {
        "meta": meta,
        "civic": D["civic"]["_meta"]["compiled"],
        "history": D["history"]["_meta"]["compiled"],
        "pets": D["pets"]["compiled"],
        "safety": D["safety"].get("generated") or meta,
        "changelog": (D["changelog"][0]["date"] if D["changelog"] else meta),
    }


def updated(D, keys):
    """Newest of the named data dates (ISO strings compare correctly)."""
    ds = [D["dates"][k] for k in keys if D["dates"].get(k)]
    return max(ds) if ds else D["dates"]["meta"]


# --------------------------------------------------------------------------- geometry


def dec(arr, q):
    """Delta/quantised int list -> [(x, y), ...] in metres (same as nkmap.js dec)."""
    out, x, y = [], 0, 0
    for i in range(0, len(arr) - 1, 2):
        x += arr[i]
        y += arr[i + 1]
        out.append((x / q, y / q))
    return out


def lines(D):
    """roads.json -> [{n, rank, bridge, pts}] (cached on D)."""
    if "_lines" not in D:
        q, R = D["meta"]["q"], D["roads"]
        D["_lines"] = [{"n": R["names"][ni] if ni >= 0 else None, "rank": rank, "bridge": bool(brg), "pts": dec(c, q)}
                       for rank, ni, brg, c in R["r"]]
    return D["_lines"]


def proj(D, lon, lat):
    m = D["meta"]
    return (lon - m["origin"][0]) * m["kx"], (m["origin"][1] - lat) * m["ky"]


def town_polys(D):
    """{town name: [ring, ...]} for every town in base.json (rings as [(x, y)])."""
    if "_towns" not in D:
        q = D["meta"]["q"]
        D["_towns"] = {t["n"]: [dec(r, q) for r in t["r"]] for t in D["base"]["towns"]}
    return D["_towns"]


def in_ring(x, y, ring):
    inside, j = False, len(ring) - 1
    for i in range(len(ring)):
        xi, yi = ring[i]
        xj, yj = ring[j]
        if (yi > y) != (yj > y) and x < (xj - xi) * (y - yi) / ((yj - yi) or 1e-12) + xi:
            inside = not inside
        j = i
    return inside


def town_at(D, x, y):
    """Name of the town polygon containing (x, y), core towns first; None outside all of them."""
    polys = town_polys(D)
    for name in list(CORE_TOWNS) + [n for n in polys if n not in CORE_TOWNS]:
        rings = polys.get(name) or []
        # even-odd over all rings handles holes
        if sum(in_ring(x, y, r) for r in rings) % 2:
            return name
    return None


def seg_dist(px, py, ax, ay, bx, by):
    dx, dy = bx - ax, by - ay
    L = dx * dx + dy * dy
    t = 0 if L == 0 else max(0, min(1, ((px - ax) * dx + (py - ay) * dy) / L))
    return math.hypot(px - (ax + t * dx), py - (ay + t * dy))


def line_dist(px, py, pts):
    return min((seg_dist(px, py, *pts[i], *pts[i + 1]) for i in range(len(pts) - 1)), default=float("inf"))


def bbox(pts_list):
    xs = [p[0] for pts in pts_list for p in pts]
    ys = [p[1] for pts in pts_list for p in pts]
    return min(xs), min(ys), max(xs), max(ys)
