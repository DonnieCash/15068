"""Map art drawn from roads.json and base.json: the ZIP locator (plus one per town) and the road poster.

- locator(D, town=None, dark=False): ZIP outline, water, roads up to rank 3, the three core towns outlined with
  dashed boundary lines and their names in caps at 14 px. With a town, that town is filled and the rest dimmed.
- poster(D, dark=False): every road rank, state routes (rank <= 2) in the route orange, the river, the dashed ZIP
  line, the three town names, the title, subtitle and attribution drawn in. 3:4 portrait (3600 x 4800 units).

Paths are written with relative l commands in whole metres. An <img> can't read CSS variables, so every colour is
the literal hex of the light or dark design token; maroon (the page chrome colour) never appears in map art.
"""
import math
import re
from urllib.parse import urlparse

from .data import CORE_TOWNS, TOWN_SLUGS, bbox, dec, lines, town_at, town_polys
from .fmt import esc

# literal token values (00-base.css): light / dark
PALETTE = {
    False: {"land": "#e4e7e2", "water": "#9fc2e2", "stream": "#86b0d8", "boundary": "#3b3d40", "route": "#c0561c",
            "road": "#8d949a", "label": "#1c232a", "halo": "#ffffff", "muted": "#66696c", "fill": "#cdd5c8",
            "dim": "#ffffff", "paper": "#fbfaf6", "ink": "#191a1b", "focus": "#0b63c4", "town": "#3b3d40"},
    True: {"land": "#0f1419", "water": "#123150", "stream": "#1d4a78", "boundary": "#9b9994", "route": "#ee8f45",
           "road": "#5d6975", "label": "#d5dce2", "halo": "#0b0f13", "muted": "#9b9994", "fill": "#26303a",
           "dim": "#17181a", "paper": "#0b0f13", "ink": "#e8e6e1", "focus": "#7db7ff", "town": "#c4c2bd"},
}
CHROME = ("#8a1c2b", "#5c1621", "#e8848f", "#f1dcdf", "#3a1c20")  # maroon family: never in map art
FONT_SERIF = "Newsreader, Georgia, 'Times New Roman', serif"
FONT_SANS = "'Radio Canada', 'Helvetica Neue', Arial, sans-serif"

LOC_W = 400            # locator intrinsic width in CSS px (town names are 14 px at this size)
LOC_PAD = 260          # metres of margin around the ZIP
POSTER_W, POSTER_H = 3600, 4800
POSTER_MAP = (150, 140, 3300, 3560)   # x, y, w, h of the map box in poster units
ATTRIB = "Map data © OpenStreetMap contributors, Overture Maps Foundation"


# --------------------------------------------------------------------------- path encoding


def _nums(v):
    """'12 -3 4' written compactly: '12-3 4' (a minus sign separates numbers on its own)."""
    out = []
    for i, n in enumerate(v):
        s = str(n)
        if i and not s.startswith("-"):
            out.append(" ")
        out.append(s)
    return "".join(out)


def simplify(pts, tol):
    """Douglas-Peucker in metres (tol <= 0 returns the points unchanged)."""
    if tol <= 0 or len(pts) < 3:
        return list(pts)
    keep = [False] * len(pts)
    keep[0] = keep[-1] = True
    stack = [(0, len(pts) - 1)]
    while stack:
        a, b = stack.pop()
        ax, ay = pts[a]
        bx, by = pts[b]
        dx, dy = bx - ax, by - ay
        L = math.hypot(dx, dy)
        best, idx = -1.0, -1
        for i in range(a + 1, b):
            px, py = pts[i]
            # distance to the chord (to the end point itself when a closed ring's ends coincide)
            d = abs(dy * (px - ax) - dx * (py - ay)) / L if L > 1e-6 else math.hypot(px - ax, py - ay)
            if d > best:
                best, idx = d, i
        if best > tol:
            keep[idx] = True
            stack += [(a, idx), (idx, b)]
    return [p for p, k in zip(pts, keep) if k]


class PathD:
    """Builds one SVG path 'd' from many lines or rings: whole metres, relative moves and relative l commands."""

    def __init__(self):
        self.parts = []
        self.cur = None

    def add(self, pts, close=False, tol=0):
        q = []
        for x, y in simplify(pts, tol):
            p = (round(x), round(y))
            if not q or p != q[-1]:
                q.append(p)
        if close and len(q) > 2 and q[-1] == q[0]:
            q.pop()
        if len(q) < 2:
            return
        x0, y0 = q[0]
        self.parts.append(f"M{x0} {y0}" if self.cur is None else "m" + _nums([x0 - self.cur[0], y0 - self.cur[1]]))
        d = []
        for (ax, ay), (bx, by) in zip(q, q[1:]):
            d += [bx - ax, by - ay]
        self.parts.append("l" + _nums(d))
        if close:
            self.parts.append("z")
            self.cur = (x0, y0)
        else:
            self.cur = q[-1]

    def __str__(self):
        return "".join(self.parts)

    def __bool__(self):
        return bool(self.parts)


def _path(rings_or_lines, close, tol=0):
    p = PathD()
    for r in rings_or_lines:
        p.add(r, close, tol)
    return str(p)


# --------------------------------------------------------------------------- geometry from the data


def zip_rings(D):
    q = D["meta"]["q"]
    return [dec(r, q) for r in D["base"]["zip"]]


def water_rings(D):
    q = D["meta"]["q"]
    return [dec(r, q) for r in D["base"]["water"]]


def streams(D, min_w=1):
    q = D["meta"]["q"]
    return [dec(s["c"], q) for s in D["base"]["streams"] if s["w"] >= min_w]


def centroid(ring):
    """Area-weighted centroid of one ring (metres)."""
    A = cx = cy = 0.0
    for i in range(len(ring)):
        x0, y0 = ring[i]
        x1, y1 = ring[(i + 1) % len(ring)]
        c = x0 * y1 - x1 * y0
        A += c
        cx += (x0 + x1) * c
        cy += (y0 + y1) * c
    if not A:
        xs, ys = zip(*ring)
        return sum(xs) / len(xs), sum(ys) / len(ys)
    A /= 2
    return cx / (6 * A), cy / (6 * A)


def lonlat(D, x, y):
    m = D["meta"]
    return m["origin"][0] + x / m["kx"], m["origin"][1] - y / m["ky"]


def coord_text(D, x, y):
    """'40.57° N, 79.75° W'"""
    lon, lat = lonlat(D, x, y)
    return f"{abs(lat):.2f}° {'N' if lat >= 0 else 'S'}, {abs(lon):.2f}° {'W' if lon < 0 else 'E'}"


def subtitle(D):
    """'ZIP 15068 · 40.57° N, 79.75° W' — the coordinates of the centre of New Kensington, the ZIP's namesake."""
    ring = max(town_polys(D)["New Kensington"], key=len)
    return "ZIP 15068 · " + coord_text(D, *centroid(ring))


def site_host(D):
    return (urlparse(D["cfg"].get("site_url") or "").hostname or "nk15068.com").removeprefix("www.")


# town-name anchors for the locator (metres). The data's label points for New Kensington and Arnold sit 1.6 km apart,
# closer than the names are long at 14 px, so each name is placed beside its own town, away from the others.
def _label_spots(D):
    polys = town_polys(D)
    out = {}
    for t in CORE_TOWNS:
        rings = polys.get(t) or []
        if not rings:
            continue
        x0, y0, x1, y1 = bbox(rings)
        out[t] = (x0, y0, x1, y1, *centroid(max(rings, key=len)))
    return out


# --------------------------------------------------------------------------- SVG pieces


def _text(x, y, s, size, color, halo, anchor="middle", weight=700, spacing=0.06, family=FONT_SANS, extra=""):
    ls = f' letter-spacing="{round(size * spacing, 1)}"' if spacing else ""
    h = (f' stroke="{halo}" stroke-width="{round(size * .24, 1)}" stroke-linejoin="round" paint-order="stroke"'
         if halo else "")
    return (f'<text x="{round(x)}" y="{round(y)}" font-family="{family}" font-size="{round(size, 1)}" '
            f'font-weight="{weight}" text-anchor="{anchor}"{ls} fill="{color}"{h}{extra}>{esc(s)}</text>')


def _roads_by_rank(D, max_rank=7, tol=0):
    by = {}
    for l in lines(D):
        if l["rank"] <= max_rank:
            by.setdefault(l["rank"], []).append(l["pts"])
    return {r: _path(v, False, tol) for r, v in sorted(by.items())}


# --------------------------------------------------------------------------- locator


def locator(D, town=None, dark=False):
    """The ZIP locator SVG (a whole document). town: a core town name to fill, dimming the rest."""
    c = PALETTE[bool(dark)]
    zr = zip_rings(D)
    x0, y0, x1, y1 = bbox(zr)
    vx, vy = math.floor(x0 - LOC_PAD), math.floor(y0 - LOC_PAD)
    vw, vh = math.ceil(x1 - x0 + 2 * LOC_PAD), math.ceil(y1 - y0 + 2 * LOC_PAD)
    k = vw / LOC_W                       # metres per CSS px at the intrinsic size
    H = round(vh / k)
    zp = _path(zr, True)
    polys = town_polys(D)
    tol = 0.35 * k
    out = [f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="{vx} {vy} {vw} {vh}" width="{LOC_W}" height="{H}" '
           f'role="img" aria-labelledby="t">']
    title = (f"{town} within ZIP 15068" if town else "ZIP 15068: New Kensington, Arnold and Lower Burrell") + \
        ". Dashed lines are city limits."
    out.append(f'<title id="t">{esc(title)}</title>')
    out.append(f'<defs><clipPath id="z"><path d="{zp}"/></clipPath>')
    if town:
        out.append(f'<clipPath id="tc"><path d="{_path(polys[town], True)}"/></clipPath>')
    out.append("</defs>")
    out.append(f'<path d="{zp}" fill="{c["land"]}"/>')
    if town:
        out.append(f'<path d="{_path(polys[town], True)}" fill="{c["fill"]}"/>')
    # the river runs along the ZIP line, so water is drawn unclipped
    out.append(f'<path d="{_path(water_rings(D), True, tol)}" fill="{c["water"]}"/>')
    out.append(f'<g clip-path="url(#z)">')
    out.append(f'<path d="{_path(streams(D, 2), False, tol)}" fill="none" stroke="{c["stream"]}" '
               f'stroke-width="{round(1.1 * k)}" stroke-linecap="round" stroke-linejoin="round"/>')
    roads = _roads_by_rank(D, 3, tol)

    def road_layer(dim):
        g = [f'<g fill="none" stroke-linecap="round" stroke-linejoin="round"{" opacity=" + chr(34) + ".45" + chr(34) if dim else ""}>']
        for r in (3, 2, 1, 0):
            if r in roads:
                col = c["route"] if r <= 2 else c["road"]
                w = {0: 2.4, 1: 2.2, 2: 1.8, 3: 1.0}[r] * k
                g.append(f'<path d="{roads[r]}" stroke="{col}" stroke-width="{round(w)}"/>')
        g.append("</g>")
        return "".join(g)

    if town:
        # every road dimmed, then the chosen town's roads at full strength
        out.append(road_layer(True))
        out.append(f'<g clip-path="url(#tc)">{road_layer(False)}</g>')
    else:
        out.append(road_layer(False))
    out.append("</g>")
    # city limits: dashed for all three, solid for the chosen town
    dash = f'stroke-dasharray="{round(5 * k)} {round(3.5 * k)}"'
    for t in CORE_TOWNS:
        if t == town or t not in polys:
            continue
        out.append(f'<path d="{_path(polys[t], True, tol)}" fill="none" stroke="{c["boundary"]}" '
                   f'stroke-width="{round(1.3 * k)}" {dash}/>')
    if town:
        out.append(f'<path d="{_path(polys[town], True)}" fill="none" stroke="{c["boundary"]}" stroke-width="{round(2 * k)}"/>')
    out.append(f'<path d="{zp}" fill="none" stroke="{c["boundary"]}" stroke-width="{round(1.6 * k)}" '
               f'stroke-opacity=".7"/>')
    # names in caps at 14 px
    fs = 14 * k
    for t, (x, y, anchor) in _locator_labels(D, fs).items():
        col = c["label"] if (not town or t == town) else c["muted"]
        out.append(_text(x, y, t.upper(), fs, col, c["halo"], anchor=anchor))
    out.append("</svg>")
    return "".join(out) + "\n"


def _locator_labels(D, fs):
    """{town: (x, y, anchor)}: Lower Burrell over the middle of its hills, New Kensington just below its centre,
    Arnold above its own (small) area so the three names never touch."""
    spots = _label_spots(D)
    out = {}
    if "Lower Burrell" in spots:
        bx0, by0, bx1, by1, cx, cy = spots["Lower Burrell"]
        out["Lower Burrell"] = (cx + fs, cy - fs * 0.3, "middle")
    if "New Kensington" in spots:
        bx0, by0, bx1, by1, cx, cy = spots["New Kensington"]
        out["New Kensington"] = (cx, cy + fs * 0.9, "middle")
    if "Arnold" in spots:
        bx0, by0, bx1, by1, cx, cy = spots["Arnold"]
        out["Arnold"] = (bx0 + fs * 0.4, by0 - fs * 0.45, "start")
    return out


# --------------------------------------------------------------------------- poster


POSTER_WIDTHS = {0: 7, 1: 6.2, 2: 5.2, 3: 3.8, 4: 2.8, 5: 2.1, 6: 1.3, 7: 1.1}  # poster units (px at 3600 wide)
TITLE = "NEW KENSINGTON · ARNOLD · LOWER BURRELL"


def poster_frame(D):
    """(viewBox tuple in metres, metres per poster unit) for the whole-ZIP poster map."""
    zr = zip_rings(D)
    x0, y0, x1, y1 = bbox(zr)
    _, _, mw, mh = POSTER_MAP
    pad = 200
    w, h = x1 - x0 + 2 * pad, y1 - y0 + 2 * pad
    k = max(w / mw, h / mh)
    vw, vh = mw * k, mh * k
    cx, cy = (x0 + x1) / 2, (y0 + y1) / 2
    return (math.floor(cx - vw / 2), math.floor(cy - vh / 2), math.ceil(vw), math.ceil(vh)), k


def nice_len(m):
    """The largest of 1-2-5 x 10^n metres not above m."""
    e = 10 ** math.floor(math.log10(max(m, 1)))
    return max(f * e for f in (1, 2, 5) if f * e <= m)


def scale_bar(k, cx, y, color, max_units=520):
    """A metric scale bar centred on cx (poster units; k metres per unit)."""
    m = nice_len(max_units * k)
    L = m / k
    x0 = cx - L / 2
    lab = f"{m // 1000:g} km" if m >= 1000 else f"{m:g} m"
    half = f"{m / 2000:g}" if m >= 1000 else f"{m / 2:g}"
    t = lambda x, s, anchor: (f'<text x="{round(x)}" y="{round(y + 62)}" font-family="{FONT_SANS}" font-size="36" '
                              f'text-anchor="{anchor}" fill="{color}">{s}</text>')
    return (f'<g id="scale" data-m="{m}">'
            f'<rect x="{round(x0)}" y="{y}" width="{round(L / 2)}" height="14" fill="{color}"/>'
            f'<rect x="{round(x0 + L / 2)}" y="{y}" width="{round(L / 2)}" height="14" fill="none" stroke="{color}" stroke-width="3"/>'
            + t(x0, "0", "middle") + t(x0 + L / 2, half, "middle") + t(x0 + L, lab, "middle") + "</g>")


def poster(D, dark=False):
    """The 15068 road poster (a whole SVG document, 3:4)."""
    c = PALETTE[bool(dark)]
    (vx, vy, vw, vh), k = poster_frame(D)
    mx, my, mw, mh = POSTER_MAP
    zr = zip_rings(D)
    zp = _path(zr, True)
    roads = _roads_by_rank(D, 7, 0)
    out = [f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {POSTER_W} {POSTER_H}" width="{POSTER_W // 4}" '
           f'height="{POSTER_H // 4}" role="img" aria-labelledby="pt" data-focus="{c["focus"]}" data-k="{round(k, 4)}" '
           f'data-paper="{c["paper"]}" data-ink="{c["ink"]}">',
           '<title id="pt">Every road in ZIP 15068: New Kensington, Arnold and Lower Burrell, Pa.</title>',
           f'<rect width="{POSTER_W}" height="{POSTER_H}" fill="{c["paper"]}"/>',
           f'<svg id="map" x="{mx}" y="{my}" width="{mw}" height="{mh}" viewBox="{vx} {vy} {vw} {vh}" '
           f'preserveAspectRatio="xMidYMid meet">',
           f'<defs><clipPath id="zc"><path d="{zp}"/></clipPath></defs>',
           f'<path d="{_path(water_rings(D), True)}" fill="{c["water"]}"/>',
           '<g clip-path="url(#zc)">',
           f'<path d="{_path(streams(D, 1), False, 1.5)}" fill="none" stroke="{c["stream"]}" data-w="1.3" '
           f'stroke-width="{round(1.3 * k, 1)}" stroke-linecap="round" stroke-linejoin="round"/>',
           '<g id="roads" fill="none" stroke-linecap="round" stroke-linejoin="round">']
    for r in sorted(roads, reverse=True):
        col = c["route"] if r <= 2 else c["ink"]
        op = ' stroke-opacity=".55"' if r >= 6 else ""
        w = POSTER_WIDTHS[r]
        out.append(f'<path class="r{r}" d="{roads[r]}" stroke="{col}" data-w="{w}" stroke-width="{round(w * k, 1)}"{op}/>')
    out.append("</g></g>")
    out.append(f'<path id="zipline" d="{zp}" fill="none" stroke="{c["boundary"]}" data-w="3" data-dash="16 10" '
               f'stroke-width="{round(3 * k, 1)}" stroke-dasharray="{round(16 * k)} {round(10 * k)}"/>')
    out.append('<g id="towns">')
    fs = 64 * k
    spots = _label_spots(D)
    taken = []
    for t in ("Arnold", "Lower Burrell", "New Kensington"):
        if t not in spots:
            continue
        x, y, anchor = _poster_label(D, spots, t, fs, taken)
        w = len(t) * fs * 0.78
        taken.append((x - w / 2 - fs, y - fs * 1.4, x + w / 2 + fs, y + fs * 0.6))
        out.append(_text(x, y, t.upper(), fs, c["ink"], c["paper"], anchor=anchor, spacing=0.14, family=FONT_SANS,
                         extra=' data-fs="64"'))
    out.append("</g></svg>")
    # title block under the map
    rule = my + mh + 110
    out.append(f'<rect x="{mx}" y="{rule}" width="{mw}" height="6" fill="{c["ink"]}"/>')
    out.append(_text(POSTER_W / 2, rule + 230, TITLE, 118, c["ink"], None, weight=700, spacing=0.05,
                     family=FONT_SERIF, extra=' id="title"'))
    out.append(_text(POSTER_W / 2, rule + 370, subtitle(D), 64, c["ink"], None, weight=400, spacing=0.12,
                     family=FONT_SANS, extra=' id="subtitle"'))
    out.append(scale_bar(k, POSTER_W / 2, rule + 470, c["ink"]))
    out.append(_text(POSTER_W / 2, POSTER_H - 130, f"{ATTRIB} · {site_host(D)}", 40, c["muted"], None, weight=400,
                     spacing=0.02, family=FONT_SANS, extra=' id="attrib"'))
    out.append("</svg>")
    return "".join(out) + "\n"


def _poster_label(D, spots, t, fs, taken=()):
    """Where a town's name goes on the poster. Arnold's streets fill its small area, so its name sits just above
    it; the other two go on the spot inside the town, clear of the other names, that covers the fewest road
    vertices (ties go to the spot nearer the town's centre)."""
    bx0, by0, bx1, by1, cx, cy = spots[t]
    if t == "Arnold":
        return (bx0 + bx1) / 2 - fs * 0.6, by0 - fs * 0.6, "middle"
    w, h = len(t) * fs * 0.78, fs * 1.1
    pts = [p for p in _road_samples(D) if bx0 - w <= p[0] <= bx1 + w and by0 - h <= p[1] <= by1 + h]
    step = max(50, round(fs / 3))
    best = None
    y = by0 + h
    while y <= by1 - h / 2:
        x = bx0 + w / 2
        while x <= bx1 - w / 2:
            box = (x - w / 2, y - h, x + w / 2, y + h * 0.25)
            corners = [(box[0], box[1]), (box[2], box[1]), (box[0], box[3]), (box[2], box[3]), (x, y - h / 2)]
            if all(town_at(D, px, py) == t for px, py in corners) and not any(_overlap(box, o) for o in taken):
                n = sum(1 for px, py in pts if box[0] <= px <= box[2] and box[1] <= py <= box[3])
                score = n + math.hypot(x - cx, y - cy) / 150
                if best is None or score < best[0]:
                    best = (score, x, y)
            x += step
        y += step
    if best is None:
        return cx, cy, "middle"
    return best[1], best[2], "middle"


def _road_samples(D, step=40):
    """Points every `step` metres along every road (so a straight grid street counts as much as a winding one)."""
    if "_road_samples" not in D:
        out = []
        for l in lines(D):
            if l["rank"] > 6:
                continue
            p = l["pts"]
            for (ax, ay), (bx, by) in zip(p, p[1:]):
                n = max(1, int(math.hypot(bx - ax, by - ay) // step))
                out += [(ax + (bx - ax) * i / n, ay + (by - ay) * i / n) for i in range(n)]
            out.append(p[-1])
        D["_road_samples"] = out
    return D["_road_samples"]


def _overlap(a, b):
    return not (a[2] < b[0] or b[2] < a[0] or a[3] < b[1] or b[3] < a[1])


# --------------------------------------------------------------------------- files


def extra_files(D):
    out = {
        "img/15068-locator.svg": locator(D),
        "img/15068-locator-dark.svg": locator(D, dark=True),
        "poster/15068-roads.svg": poster(D),
        "poster/15068-roads-dark.svg": poster(D, dark=True),
    }
    for t in CORE_TOWNS:
        s = TOWN_SLUGS[t]
        out[f"img/town-{s}.svg"] = locator(D, t)
        out[f"img/town-{s}-dark.svg"] = locator(D, t, dark=True)
    for k, v in out.items():
        low = v.lower()
        assert not any(h in low for h in CHROME), f"{k}: chrome colour in map art"
    return out


def size_ok(svg):
    """True when an SVG string has no NaN/None coordinates (a cheap sanity check for tests)."""
    return not re.search(r"nan|None|inf", svg)
