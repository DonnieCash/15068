"""What's new: a digest of the data, the differences between two digests as plain sentences, the changelog file,
and the RSS feed at whats-new/feed.xml.

    digest(D)            -> dict summarising the data the site is built from
    diff(prev, cur)      -> [item, …]  (prev None -> the first-edition entry)
    append(date, items)  -> prepends {"date", "items"} to data/changelog.json (newest first)
    log(D, today)        -> diff against data/build_digest.json, append, rewrite the digest (build_pages.py --log)
    entries(D)           -> [{"date", "items"}] newest first
    extra_files(D)       -> {"whats-new/feed.xml": RSS 2.0}

Entries are honest: only a real change in the data writes one.
"""
import datetime as dt
import json
from email.utils import format_datetime
from pathlib import Path
from xml.sax.saxutils import escape as xesc

from . import fmt
from . import sentences as S
from .data import CORE_TOWNS, ROOT

CHANGELOG = ROOT / "data" / "changelog.json"
DIGEST = ROOT / "data" / "build_digest.json"
COUNTS = [  # (digest key, noun, plural) for research lists that only grow or shrink
    ("timeline", "history entry", "history entries"),
    ("people", "notable person", "notable people"),
    ("landmarks", "landmark", "landmarks"),
    ("eat", "place to eat and drink", "places to eat and drink"),
    ("events", "yearly event", "yearly events"),
    ("parks", "park", "parks"),
]


def _read(path, default=None):
    p = Path(path)
    if not p.exists():
        return default
    return json.loads(p.read_text(encoding="utf-8"))


def _write(path, obj):
    Path(path).write_text(json.dumps(obj, indent=1, ensure_ascii=False, sort_keys=True) + "\n", encoding="utf-8")


# --------------------------------------------------------------------------- digest


def digest(D):
    from .pages_towns import news_items  # late import: pages_towns imports this module
    m, s = D["meta"], D["safety"]
    st = m["stats"]
    fbi = {}
    for t in CORE_TOWNS:
        a, _ = S.latest_pair(S.agency(D, t))
        if a is not None:
            fbi[t] = a["year"]
    inc = s.get("incidents") or []
    ids = fmt.inc_ids(inc)
    news = news_items(D)
    h, c = D["history"], D["civic"]
    return {
        "release": (m.get("sources") or [{}])[0].get("release", ""),
        "places": st["places"], "streets": st["streets"], "buildings": st["buildings"],
        "fbi": fbi,
        "incidents": {i: str(x.get("d")) for i, x in zip(ids, inc) if x.get("x") is not None and x.get("y") is not None},
        "news": {n["id"]: str(n.get("date")) for n in news},
        "crash_last": max((r["year"] for r in s["crashes"]["stats"]), default=None),
        "timeline": len(h.get("timeline") or []), "people": len(h.get("people") or []),
        "landmarks": len(h.get("landmarks") or []), "events": len(h.get("events") or []),
        "eat": len(c.get("food_and_culture") or []), "parks": len(c.get("parks_and_rec") or []),
    }


# --------------------------------------------------------------------------- diff -> sentences


def _n(n, one, many):
    return f"{fmt.num(n)} {one if n == 1 else many}"


def _fbi_items(prev, cur):
    """'FBI figures for 2025 added' (all three) or '… added for Arnold and Lower Burrell'."""
    by_year = {}
    for t, y in (cur or {}).items():
        if y and (prev or {}).get(t) != y and (not (prev or {}).get(t) or y > prev[t]):
            by_year.setdefault(y, []).append(t)
    out = []
    for y, towns in sorted(by_year.items()):
        if len(towns) == len(CORE_TOWNS):
            out.append(f"FBI figures for {y} added")
        else:
            out.append(f"FBI figures for {y} added for {S.join_and(towns)}")
    return out


def _fbi_through(fbi):
    years = sorted(set(fbi.values()))
    if not years:
        return ""
    if len(years) == 1 and len(fbi) == len(CORE_TOWNS):
        return f"FBI figures through {years[0]} for all three departments"
    return "FBI figures through " + S.join_and([f"{y} for {S.join_and([t for t in CORE_TOWNS if fbi.get(t) == y])}"
                                                for y in sorted(years, reverse=True)])


def first_edition(cur):
    items = [f"First edition on its own pages: {fmt.num(cur['places'])} places, {fmt.num(cur['streets'])} streets and "
             f"{fmt.num(cur['buildings'])} buildings from Overture Maps release {cur['release']}"]
    if cur.get("fbi"):
        items.append(_fbi_through(cur["fbi"]))
    if cur.get("incidents"):
        items.append(f"{fmt.num(len(cur['incidents']))} mapped incidents, newest "
                     f"{fmt.ap_date(max(cur['incidents'].values()))}")
    if cur.get("news"):
        items.append(f"{_n(len(cur['news']), 'news brief', 'news briefs')}, newest {fmt.ap_date(max(cur['news'].values()))}")
    return items


def diff(prev, cur):
    """Plain-language items for what changed from digest prev to digest cur ([] when nothing did)."""
    if not prev:
        return first_edition(cur)
    out = []
    if cur.get("release") != prev.get("release"):
        out.append(f"Map data updated to Overture Maps release {cur['release']}: {fmt.num(cur['places'])} places, "
                   f"{fmt.num(cur['streets'])} streets and {fmt.num(cur['buildings'])} buildings")
    out += _fbi_items(prev.get("fbi"), cur.get("fbi"))
    for key, one, many, label in (("incidents", "police blotter entry", "police blotter entries", "blotter"),
                                  ("news", "news brief", "news briefs", "news")):
        a, b = prev.get(key) or {}, cur.get(key) or {}
        new = [i for i in b if i not in a]
        gone = [i for i in a if i not in b]
        if new:
            out.append(f"{_n(len(new), 'new ' + one, 'new ' + many)}, newest {fmt.ap_date(max(b[i] for i in new))}")
        if gone:
            out.append(f"{_n(len(gone), one, many)} removed")
    if cur.get("crash_last") and prev.get("crash_last") and cur["crash_last"] > prev["crash_last"]:
        out.append(f"PennDOT crash figures for {cur['crash_last']} added")
    for key, one, many in COUNTS:
        a, b = prev.get(key), cur.get(key)
        if a is None or b is None or a == b:
            continue
        out.append(f"{_n(b - a, 'new ' + one, 'new ' + many)}" if b > a else f"{_n(a - b, one, many)} removed")
    return out


# --------------------------------------------------------------------------- the changelog file


def append(date, items, path=CHANGELOG):
    """Prepend an entry for `date` (merging into an entry already dated that day). Returns the new list."""
    ents = _read(path, []) or []
    iso = date.isoformat() if hasattr(date, "isoformat") else str(date)
    items = [i for i in items if i]
    if not items:
        return ents
    if ents and ents[0].get("date") == iso:
        ents[0]["items"] = ents[0].get("items", []) + [i for i in items if i not in ents[0].get("items", [])]
    else:
        ents.insert(0, {"date": iso, "items": items})
    Path(path).write_text(json.dumps(ents, indent=1, ensure_ascii=False) + "\n", encoding="utf-8")
    return ents


def log(D, today):
    """Record what changed since the last --log run, then store the new digest. Returns the items written."""
    root = Path(D.get("root") or ROOT)
    dpath, cpath = root / "data" / "build_digest.json", root / "data" / "changelog.json"
    prev = _read(dpath)
    cur = digest(D)
    items = diff(prev, cur)
    if items:
        D["changelog"] = append(today, items, cpath)
        print(f"What's new, {today}: " + " · ".join(items))
    else:
        print("What's new: no data changes to log")
    _write(dpath, cur)
    return items


def entries(D):
    """Changelog entries, newest first, each {"date": ISO, "items": [str]} (malformed rows skipped)."""
    out = []
    for e in D.get("changelog") or []:
        try:
            d = dt.date.fromisoformat(str(e.get("date"))[:10]).isoformat()
        except ValueError:
            continue
        items = [str(i) for i in e.get("items") or [] if str(i).strip()]
        if items:
            out.append({"date": d, "items": items})
    return sorted(out, key=lambda e: e["date"], reverse=True)


def line(e):
    """'First edition … · FBI figures through 2024 … · 20 news briefs, newest Sept. 2026.'"""
    return fmt.end_stop(" · ".join(e["items"]))


# --------------------------------------------------------------------------- RSS


def feed_xml(D):
    u = D["cfg"]["site_url"].rstrip("/")
    ents = entries(D)
    page = u + "/whats-new/"
    items = []
    for e in ents[:50]:
        d = dt.date.fromisoformat(e["date"])
        when = format_datetime(dt.datetime(d.year, d.month, d.day, 12, 0, tzinfo=dt.timezone.utc))
        title = f"{fmt.ap_date(e['date'])}: {e['items'][0]}"
        link = f"{page}#d-{e['date']}"
        items.append(f"<item><title>{xesc(title)}</title><link>{xesc(link)}</link>"
                     f'<guid isPermaLink="true">{xesc(link)}</guid><pubDate>{when}</pubDate>'
                     f"<description>{xesc(line(e))}</description></item>")
    last = ""
    if ents:
        d = dt.date.fromisoformat(ents[0]["date"])
        last = f"<lastBuildDate>{format_datetime(dt.datetime(d.year, d.month, d.day, 12, 0, tzinfo=dt.timezone.utc))}</lastBuildDate>"
    return ('<?xml version="1.0" encoding="UTF-8"?>\n'
            '<rss version="2.0" xmlns:atom="http://www.w3.org/2005/Atom"><channel>'
            "<title>What&apos;s new on NK15068</title>"
            f"<link>{xesc(page)}</link>"
            f'<atom:link href="{xesc(page)}feed.xml" rel="self" type="application/rss+xml"/>'
            "<description>Every data update to NK15068, newest first: news briefs, police blotter entries, FBI years "
            "and map releases for New Kensington, Arnold and Lower Burrell, Pa.</description>"
            f"<language>en-us</language>{last}" + "".join(items) + "</channel></rss>\n")


def extra_files(D):
    return {"whats-new/feed.xml": feed_xml(D)}
