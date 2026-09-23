"""data/search.json: what /search/ and the map's search panel look through besides places and streets.

    {"built": ISO, "pages": [{t, u, k}], "numbers": [{n, t, ph, u, k}], "events": [{n, next, label, u}],
     "news": [{h, d, u, o}], "streets_inc": [{s, n, u}], "syn": {canonical: [synonyms]}}

Pages come from the route table, numbers from pages_home.numbers_rows() (every row on /numbers/), events from
calendar.occurrences(), news from pages_towns.news_items(), and the street counts from the news-reported incidents.
A news brief whose month is approximate also carries "about": true so its date reads "About Sept. 2026".
"""
import json
from urllib.parse import quote_plus

from . import calendar as C
from . import fmt
from .data import CORE_TOWNS

# the synonyms the query parser folds together (spec section 3, /search/)
SYN = {
    "pharmacy": ["drugstore", "drug store", "pharmacies"],
    "grocery": ["supermarket", "groceries", "food store"],
    "police": ["cops", "non-emergency", "nonemergency"],
    "city hall": ["borough building", "municipal building", "council", "mayor", "city"],
    "trash": ["garbage", "refuse", "recycling", "pothole", "potholes", "public works", "snow", "plow"],
    "lost pet": ["lost dog", "lost cat", "found dog", "found cat", "stray", "missing dog", "missing cat", "warden",
                 "dog catcher", "animal control"],
}

# indexable pages: the name a search result shows, and the words it answers to
PAGES = {
    "/": ("Front page", "home front page this week news pets calendar numbers crime"),
    "/lost-pets/": ("Lost or found a pet",
                    "lost found stray missing dog cat pet warden dog catcher animal control shelter lost pet found pet "
                    "flyer microchip reunite"),
    "/numbers/": ("Phone numbers", "phone numbers call contact city hall police non-emergency library school post "
                  "office animal shelter vet ymca county"),
    "/calendar/": ("Calendar", "calendar events coming up this week council meeting fridays on fifth parade festival "
                   "dates"),
    "/crime/": ("Crime and safety", "crime safety police fbi violent property rate going up statistics"),
    "/crime/new-kensington/": ("New Kensington police and crime",
                               "new kensington crime police department fbi violent property arrests officers"),
    "/crime/arnold/": ("Arnold police and crime", "arnold crime police department fbi violent property arrests officers"),
    "/crime/lower-burrell/": ("Lower Burrell police and crime",
                              "lower burrell crime police department fbi violent property arrests officers"),
    "/crime/blotter/": ("Police blotter", "police blotter incidents news shooting robbery arrest crime map"),
    "/crashes/": ("Serious crashes", "crashes crash traffic accidents fatal killed injured roads penndot"),
    "/towns/": ("The three towns", "towns cities new kensington arnold lower burrell population zip"),
    "/towns/new-kensington/": ("New Kensington", "new kensington city hall parks neighborhoods population"),
    "/towns/arnold/": ("Arnold", "arnold city hall parks neighborhoods population council"),
    "/towns/lower-burrell/": ("Lower Burrell", "lower burrell city hall parks neighborhoods population"),
    "/news/": ("News", "news local news briefs stories"),
    "/history/": ("History", "history timeline parnassus alcoa aluminum past census population landmarks"),
    "/history/people/": ("Notable people", "notable people famous born raised celebrities athletes"),
    "/eat/": ("Eat and drink", "eat drink restaurants bars food dinner lunch breakfast pizza bakery cafe coffee club"),
    "/map/": ("Map", "map street map places directions"),
    "/poster/": ("Map poster", "poster print map t-shirt download svg"),
    "/whats-new/": ("What's new", "whats new updates changes changelog"),
    "/about/": ("About NK15068", "about who runs how its made"),
    "/privacy/": ("Privacy policy", "privacy cookies ads location storage"),
    "/contact/": ("Contact and corrections", "contact email correction report mistake"),
    "/sources/": ("Sources and licenses", "sources licenses data outlets"),
}


def _routes(D):
    if D.get("routes"):
        return D["routes"]
    from . import routes as NR
    return NR.resolve(D)


def pages(D):
    out = []
    for R in _routes(D):
        if R.index != "I":
            continue
        t, k = PAGES.get(R.path) or (R.title.removesuffix(" · NK15068"), "")
        out.append({"t": t, "u": R.path.lstrip("/"), "k": k})
    return out


def numbers(D):
    from .pages_home import numbers_rows
    return [{"n": r["n"], "t": r["t"], "ph": r["ph"], "u": r["u"], "k": r["k"]} for r in numbers_rows(D)]


def events(D):
    """The next date of each calendar item (yearly ones by their 'when' text), in calendar order."""
    seen, out = set(), []
    for it in C.occurrences(D, D["today"]):
        if it["title"] in seen:
            continue
        seen.add(it["title"])
        out.append({"n": it["title"], "next": it["date"], "label": it["label"], "u": f"calendar/#{it['id']}"})
    return out


def _first_source(n):
    s = n.get("source")
    if isinstance(s, (list, tuple)):
        s = next((u for u in s if u), "")
    return s or ""


def news(D):
    from .pages_towns import news_items
    out = []
    for n in news_items(D):
        row = {"h": fmt.public(n.get("headline")), "d": str(n.get("date") or "")[:7], "u": f"news/#{n['id']}",
               "o": fmt.pub_name(_first_source(n))}
        if n.get("approx"):
            row["about"] = True
        out.append(row)
    return out


def inc_streets(i):
    from .pages_crime import inc_streets as streets
    return streets(i)


def streets_inc(D):
    """Streets that news-reported incidents name, with how many name each: the incident's location names the street
    (same street key, as the blotter's street filter matches) in a town the street runs through."""
    keyed = []
    for i in D["safety"].get("incidents") or []:
        ks = [fmt.street_key(s) for s in inc_streets(i)]
        keyed.append((i.get("t"), [k for k in ks if k]))
    out, seen = [], set()
    for s in D["streets"]:
        if s["n"] in seen:
            continue
        seen.add(s["n"])
        k = fmt.street_key(s["n"])
        if not k:
            continue
        towns = s.get("t") or []
        n = sum(1 for t, ks in keyed if t in towns and any(
            x["core"] == k["core"] and (not x["type"] or not k["type"] or x["type"] == k["type"]) for x in ks))
        if not n:
            continue
        core = [t for t in towns if t in CORE_TOWNS]
        u = "crime/blotter/?street=" + quote_plus(s["n"])
        if len(core) == 1:
            u += "&town=" + quote_plus(core[0])
        out.append({"s": s["n"], "n": n, "u": u})
    return sorted(out, key=lambda r: (-r["n"], r["s"]))


def search_json(D):
    return {"built": D["today"].isoformat(), "pages": pages(D), "numbers": numbers(D), "events": events(D),
            "news": news(D), "streets_inc": streets_inc(D), "syn": SYN}


def extra_files(D):
    return {"data/search.json": json.dumps(search_json(D), ensure_ascii=False, separators=(",", ":"))}
