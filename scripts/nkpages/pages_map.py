"""The map pages: /map/ (the searchable 2D map), /map/3d/, /directory/ (places and streets A to Z) and /search/.

The map and 3D pages are app shells: the canvas is drawn by site/assets/nkmap.js and nk3d.js, wired by
site/assets/js/60-map.js. Their HTML holds every label, the loading figure and a no-JavaScript fallback. The directory's
first 100 de-duplicated places are static; /search/ is a form whose results come from data/search.json (search.py).
"""
import json
import math
import re

from . import fmt
from . import mapsvg
from . import sentences as S
from .data import CORE_TOWNS
from .fmt import esc
from .shell import correction_url, rel

# the same colours as GROUP_COLORS in site/assets/nkmap.js (place-type dots)
GROUP_COLORS = {"eat": "#e0743a", "shop": "#c9a227", "health": "#d4455b", "faith": "#8b6fc6", "learn": "#3c8dbc",
                "play": "#3f9a5b", "civic": "#5c7cfa", "culture": "#b0508f", "auto": "#7a8a99", "services": "#8c7b6b",
                "stay": "#1aa39a"}
DIR_STATIC = 100
POSTER = ("/poster/15068-roads.svg", "/poster/15068-roads-dark.svg")
LOCATOR = ("/img/15068-locator.svg", "/img/15068-locator-dark.svg")
ATTRIB = "Map data © OpenStreetMap contributors · Overture Maps · US Census · AWS Terrain Tiles"


# --------------------------------------------------------------------------- shared pieces


def picture(R, art, alt, w, h, cls="", lazy=True):
    c = f' class="{cls}"' if cls else ""
    load = ' loading="lazy"' if lazy else ""
    return (f'<picture class="themed"><source media="(prefers-color-scheme: dark)" srcset="{rel(R, art[1])}">'
            f'<img{c} src="{rel(R, art[0])}" width="{w}" height="{h}" alt="{esc(alt)}"{load} decoding="async"></picture>')


def locator_size(D):
    if "_locsize" not in D:
        m = re.search(r'width="(\d+)" height="(\d+)"', mapsvg.locator(D)[:400])
        D["_locsize"] = (int(m.group(1)), int(m.group(2))) if m else (400, 400)
    return D["_locsize"]


def loading_figure(D, R, caption):
    w, h = locator_size(D)
    return (f'<figure class="loading" id="map-loading">'
            + picture(R, LOCATOR, "Outline of ZIP 15068 with New Kensington, Arnold and Lower Burrell", w, h, lazy=False)
            + f'<figcaption>{esc(caption)}</figcaption></figure>')


def nojs(D, R, lead):
    """The fallback over the map when JavaScript is off: the page's name, a short intro, the text-only pages and
    the poster."""
    return ('<noscript><div class="nojs"><div class="nojs-in">'
            f'<p class="nojs-h" aria-hidden="true">{esc(R.h1)}</p><p class="nojs-t">{lead}</p>'
            f'<p class="nojs-links"><a class="go" href="{rel(R, "/directory/")}">Places and streets A to Z ›</a> '
            f'<a class="go" href="{rel(R, "/numbers/")}">Phone numbers ›</a> '
            f'<a class="go" href="{rel(R, "/poster/")}">The map poster ›</a></p>'
            + picture(R, POSTER, "Poster of every road in ZIP 15068, with New Kensington, Arnold and Lower Burrell "
                      "labeled", mapsvg.POSTER_W // 4, mapsvg.POSTER_H // 4, "nojs-poster")
            + "</div></div></noscript>")


def intro(D):
    st = D["meta"]["stats"]
    return (f"Every street, building and storefront in ZIP 15068, drawn from open data: {fmt.num(st['places'])} places, "
            f"{fmt.num(st['streets'])} named streets and {fmt.num(st['buildings'])} buildings in New Kensington, "
            "Arnold and Lower Burrell. The map is drawn in your browser, so it needs JavaScript. Without it, here "
            "are the poster of every road, the full list of places and streets, and the phone numbers for the three "
            "cities.")


# --------------------------------------------------------------------------- /map/


LAYERS = [("tpet", "Lost and found pets", "false"), ("tinc", "Crime and police incidents", "false"),
          ("tcr", "Serious and fatal crashes", "false"), ("tbld", "Buildings", "true"), ("trel", "Terrain relief", "true")]

LEGEND = (
    '<div class="panel map-legend" id="inc-legend" hidden>'
    '<div data-l="pet"><span class="pet-key" style="background:var(--pet-lost)">L</span>Lost pet</div>'
    '<div data-l="pet"><span class="pet-key found">F</span>Found pet</div>'
    '<div data-l="pet"><span class="pet-key" style="background:var(--pet-spotted)">S</span>Spotted</div>'
    '<div data-l="inc"><span class="inc-key" style="background:var(--inc-violent)"></span>Violent</div>'
    '<div data-l="inc"><span class="inc-key" style="background:var(--inc-property)"></span>Property</div>'
    '<div data-l="inc"><span class="inc-key" style="background:var(--inc-police)"></span>Police and other</div>'
    '<div data-l="inc"><span class="inc-key pi" style="background:var(--muted)"></span>Police involved</div>'
    '<div data-l="inc"><span class="ring-key"></span>Street only (approximate)</div>'
    '<small data-l="inc">News-reported, placed at a block, intersection, place or street</small>'
    '<div data-l="cr"><span class="tri-key"></span>Fatal crash</div>'
    '<div data-l="cr"><span class="tri-key hollow"></span>Serious-injury crash</div>'
    "</div>")


def map_data(D):
    """Numbers the map's cards need, computed here so the page never guesses: each town's police line."""
    pol = {t: {"ph": v["primary"], "alt": v["alt"]} for t, v in S.police_numbers(D).items()}
    return json.dumps({"police": pol}, ensure_ascii=False, separators=(",", ":")).replace("</", "<\\/")


def map_page(D, R):
    layers = "".join(f'<button type="button" id="{i}" aria-pressed="{p}">{esc(t)}</button>' for i, t, p in LAYERS)
    body = (
        '<div class="explorer" id="explorer">'
        '<canvas class="stage" id="map-canvas" aria-label="Map of ZIP 15068. Drag to pan, scroll or pinch to zoom; '
        'arrow keys also work."></canvas>'
        '<div class="gl" id="gl-host" hidden></div>'
        + loading_figure(D, R, "Drawing the map…") +
        '<div class="panel search-panel" id="search-panel">'
        f'<h1 id="map-h">{esc(R.h1)}</h1>'
        '<div class="sp-row"><input id="q" type="search" placeholder="A business, street or corner, like 5th &amp; 9th" '
        'autocomplete="off" spellcheck="false" enterkeyhint="search" aria-label="Search the map" aria-controls="results">'
        '<button type="button" class="filter-btn" id="filter-btn" aria-expanded="false" aria-controls="chips">Filter</button>'
        '</div>'
        '<div class="results" id="results" aria-label="Search results"></div>'
        '<div class="chips" id="chips" role="group" aria-label="Show one type of place"></div>'
        '</div>'
        '<div class="layers">'
        '<button type="button" class="panel layers-btn" id="layers-btn" aria-expanded="false" aria-controls="layers-pop">'
        'Layers</button>'
        '<div class="panel layers-pop" id="layers-pop" role="group" aria-label="Map layers" hidden>'
        f'{layers}<hr><p class="lp-h">Go to</p>'
        '<button type="button" id="dt">Downtown New Kensington</button>'
        '<button type="button" id="home">Whole ZIP</button>'
        '<hr><a id="t3d" href="3d/">3D view ›</a></div></div>'
        '<div class="panel zoom" role="group" aria-label="Zoom">'
        '<button type="button" id="zin" aria-label="Zoom in">+</button>'
        '<button type="button" id="zout" aria-label="Zoom out">−</button></div>'
        '<div class="panel card" id="card" hidden aria-live="polite"></div>'
        + LEGEND +
        '<div class="scale" id="scale"></div>'
        f'<p class="attrib">{esc(ATTRIB)}</p>'
        + nojs(D, R, esc(intro(D))) +
        f'<script type="application/json" id="map-data">{map_data(D)}</script>'
        '</div>')
    return {"body": body}


# --------------------------------------------------------------------------- /map/3d/


def map3d(D, R):
    lead = esc(intro(D)).replace("The map is drawn", "The 3D view is drawn", 1)
    body = (
        '<div class="explorer explorer3d" id="explorer">'
        '<div class="gl" id="gl-host"></div>'
        '<div class="p3-labels" id="p3-labels" aria-hidden="true"></div>'
        + loading_figure(D, R, "Drawing the hills and buildings…") +
        '<div class="panel p3-head" id="p3-head">'
        f'<h1>{esc(R.h1)}</h1>'
        f'<p class="p3-deck">Made for looking, not finding. To find a place, <a href="{rel(R, "/map/")}">use the flat map ›</a></p>'
        '</div>'
        '<div class="panel p3-ctl" id="p3-ctl" role="group" aria-label="3D view controls" hidden>'
        '<div class="p3-row"><button type="button" data-go="downtown">Downtown New Kensington</button>'
        '<button type="button" data-go="hills">Lower Burrell hills</button>'
        '<button type="button" data-go="zip">Whole ZIP</button></div>'
        '<div class="p3-row"><button type="button" id="p3-town" aria-pressed="true">Town labels</button>'
        '<button type="button" id="p3-save">Save as image</button>'
        '<button type="button" id="p3-poster" aria-pressed="false">Poster mode</button></div>'
        f'<p class="p3-back"><a href="{rel(R, "/map/")}">Back to the flat map ›</a></p>'
        '<p class="p3-msg" id="p3-msg" role="status"></p></div>'
        '<div class="p3-title" id="p3-title" hidden><p class="p3-t1">NK15068</p>'
        '<p class="p3-t2">New Kensington · Arnold · Lower Burrell</p></div>'
        '<button type="button" class="panel p3-exit" id="p3-exit" hidden>Exit poster mode</button>'
        f'<p class="attrib">{esc(ATTRIB)}</p>'
        + nojs(D, R, lead) +
        '</div>')
    return {"body": body}


# --------------------------------------------------------------------------- places: de-duplication, town labels


_NORM_DROP = re.compile(r"\b(new kensington|lower burrell|arnold|the|pa)\b")


def norm(s):
    """The old app.js norm(): lower case, town names and 'the'/'pa' dropped, letters and digits only."""
    return re.sub(r"[^a-z0-9]", "", _NORM_DROP.sub("", str(s or "").lower()))


def dedupe_key(p):
    """Digits of the phone + norm(name), or norm(name) + a 50 m grid cell when there is no phone."""
    digits = re.sub(r"\D", "", p.get("ph") or "")
    if digits:
        return f"{digits}|{norm(p['n'])}"
    return f"{norm(p['n'])}|{math.floor(p['x'] / 50)},{math.floor(p['y'] / 50)}"


def dedupe(places):
    """One row per key, keeping the highest q (the first on a tie), in the original order."""
    best = {}
    for p in places:
        k = dedupe_key(p)
        if k not in best or p.get("q", 0) > best[k].get("q", 0):
            best[k] = p
    keep = {id(p) for p in best.values()}
    return [p for p in places if id(p) in keep]


def town_label(p):
    """The address's city when it is one of the three (misspellings fixed), otherwise the map's town."""
    parts = [x.strip() for x in str(p.get("a") or "").split(",")]
    if len(parts) >= 2:
        low = parts[1].lower().replace("-", " ")
        fixed = {"new kensington": "New Kensington", "new kensingtn": "New Kensington",
                 "new kinsington": "New Kensington", "lower burrell": "Lower Burrell", "arnold": "Arnold"}.get(low)
        if fixed:
            return fixed
    return p.get("t") or ""


def a_to_z(places):
    return sorted(places, key=lambda p: (p["n"].lower(), -p.get("q", 0)))


def place_href(R, p):
    return rel(R, "/map/") + f"?place={fmt.slug(p['n'])}~{round(p['x'])},{round(p['y'])}"


def phone_cell(ph):
    t = fmt.tel(ph)
    if not t:
        return esc(ph or "")
    return f'<a class="dtel" href="{t[0][1]}">{esc(t[0][0])}</a>'


def place_row(D, R, p):
    g = D["meta"]["groups"].get(p["g"], "")
    return (f'<tr><td class="dn"><a href="{esc(place_href(R, p))}"><span class="dot" '
            f'style="background:{GROUP_COLORS.get(p["g"], "#7a8a99")}"></span>{esc(p["n"])}</a>'
            f'<span class="sub">{esc(g)}</span></td><td class="dc">{esc(p.get("c") or "")}</td>'
            f'<td class="dt">{esc(town_label(p))}</td><td class="da">{esc(p.get("a") or "")}</td>'
            f'<td class="dp">{phone_cell(p.get("ph"))}</td></tr>')


# --------------------------------------------------------------------------- /directory/


def town_options(places):
    labels = {town_label(p) for p in places if town_label(p)}
    others = sorted(labels - set(CORE_TOWNS))
    return [t for t in CORE_TOWNS if t in labels] + others


def directory(D, R):
    rows = a_to_z(dedupe(D["places"]))
    n, ns = len(rows), len({s["n"] for s in D["streets"]})
    release = D["meta"]["sources"][0].get("release", "")
    towns = "".join(f'<option value="{esc(t)}">{esc(t)}</option>' for t in town_options(rows))
    groups = "".join(f'<option value="{esc(k)}">{esc(v)}</option>' for k, v in D["meta"]["groups"].items())
    body = (
        f'<h1>{esc(R.h1)}</h1>'
        f'<p class="dateline">From Overture Maps release {esc(release)}</p>'
        f'<p class="deck">{fmt.num(n)} places and {fmt.num(ns)} named streets in ZIP 15068, as the open map data lists '
        'them. Each name opens it on the map.</p>'
        '<div class="dir-tools" id="dir-tools" hidden>'
        '<div class="tabs" id="dir-tabs" role="tablist" aria-label="Directory lists">'
        f'<button class="tab" type="button" role="tab" data-t="places" aria-selected="true" aria-controls="dir-table">'
        f'Places ({fmt.num(n)})</button>'
        f'<button class="tab" type="button" role="tab" data-t="streets" aria-selected="false" aria-controls="dir-table">'
        f'Streets ({fmt.num(ns)})</button></div>'
        '<div class="dir-controls">'
        '<input id="dir-q" type="search" placeholder="Filter by name, street or type" autocomplete="off" '
        'spellcheck="false" aria-label="Filter the list">'
        f'<select id="dir-town" aria-label="Town"><option value="">All towns</option>{towns}</select>'
        f'<select id="dir-g" aria-label="Type of place"><option value="">All types</option>{groups}</select>'
        '</div></div>'
        f'<p class="dir-count" id="dir-count" role="status">The first {DIR_STATIC} of {fmt.num(n)} places, A to Z.</p>'
        '<div class="dir-table-wrap"><table class="dir dirlist" id="dir-table">'
        '<thead><tr><th>Name</th><th>Type</th><th>Town</th><th>Address</th><th>Phone</th></tr></thead><tbody>'
        + "".join(place_row(D, R, p) for p in rows[:DIR_STATIC]) +
        '</tbody></table></div>'
        '<button class="btn-line" type="button" id="dir-more" hidden>Show 100 more</button>'
        f'<p class="fine">Places from Overture Maps and OpenStreetMap contributors. Something wrong? '
        f'<a href="{esc(correction_url(D))}">Report a correction ›</a></p>')
    return {"body": f'<div class="page dir-page">{body}</div>', "crumbs": [("Places and streets A to Z", None)]}


# --------------------------------------------------------------------------- /search/


def search_page(D, R):
    from .pages_home import GAP_LINE
    body = (
        f'<h1>{esc(R.h1)}</h1>'
        '<form class="sitesearch s-form" id="sq" role="search" action="./" method="get">'
        '<label for="sq-q">Places, streets, phone numbers, events and lost pets</label>'
        '<span class="sf-row"><input id="sq-q" name="q" type="search" placeholder="Street, business, number or topic" '
        'autocomplete="off" spellcheck="false" enterkeyhint="search"><button type="submit">Search</button></span></form>'
        '<div class="sresults" id="sresults" aria-live="polite"></div>'
        f'<p class="s-gap" id="s-gap" hidden>{esc(GAP_LINE)}</p>'
        '<noscript><p class="s-nojs">Search needs JavaScript. Try '
        f'<a href="{rel(R, "/numbers/")}">Phone numbers</a>, <a href="{rel(R, "/lost-pets/")}">Lost pets</a>, or '
        f'<a href="{rel(R, "/directory/")}">Places and streets A to Z</a>.</p></noscript>')
    return {"body": f'<div class="page search-page">{body}</div>', "crumbs": [("Search", None)]}
