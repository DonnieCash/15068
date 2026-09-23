"""Town and reference pages: /towns/, /towns/<town>/, /news/, /history/, /history/people/, /eat/, /poster/,
/whats-new/, /about/, /privacy/, /contact/, /sources/ and /404.html.

Every number is computed from the data at build time; every piece of research text passes through fmt.public()
and keeps its outlet credit. Other builders import town_glance(D, town) and news_items(D) from here.
"""
import calendar as _cal
import datetime as dt
import re
from collections import Counter
from urllib.parse import quote, urlencode

from . import changelog, charts, fmt, mapsvg
from . import pages_map as PM
from . import pets as P
from . import sentences as S
from .data import CORE_TOWNS, SLUG_TOWNS, TOWN_SLUGS, updated
from .fmt import esc, public
from .shell import correction_url, issues_url, rel

# --------------------------------------------------------------------------- small pieces


def sec(sid, title, body, cls="", attrs=""):
    c = f"sec {cls}".strip()
    return (f'<section class="{c}" id="{sid}" aria-labelledby="{sid}-h"{attrs}><h2 id="{sid}-h">{title}</h2>'
            f"{body}</section>")


def dateline(text):
    return f'<p class="dateline">{text}</p>'


def updated_line(D, R):
    return dateline(f"Updated {fmt.ap_date(updated(D, R.dates))}")


def sources_line(urls, pre="Sources: "):
    c = P.credit(urls, pre)
    return f'<p class="credit sources">{c}.</p>' if c else ""


def credit_line(urls, pre="Source: "):
    return P.credit_line(urls, pre)


def pub_text(s):
    """Research text for an HTML text node: filtered through public(), then escaped."""
    return esc(public(s))


_PHONE = re.compile(r"\(?\b(\d{3})\)?[-. ]?(\d{3})[-. ](\d{4})\b")


def tel_text(s):
    """public() + escape, with every phone number in the text made a tap-to-call link."""
    t, out, pos = public(s), [], 0
    for m in _PHONE.finditer(t):
        out.append(esc(t[pos:m.start()]))
        a, b, c = m.groups()
        out.append(f'<a class="tel-inline" href="tel:+1{a}{b}{c}">{a}-{b}-{c}</a>')
        pos = m.end()
    out.append(esc(t[pos:]))
    return "".join(out)


def ap_addr(a):
    """'1829 Fifth Ave, Arnold, PA 15068' -> '1829 Fifth Ave.'"""
    s = fmt.short_addr(a)
    return re.sub(r"\b(St|Ave|Blvd|Rd|Dr|Ln|Pl|Ct)$", r"\1.", s)


def short_place(a):
    """'1500 Stevenson Blvd, New Kensington, PA 15068' -> '1500 Stevenson Blvd., New Kensington'; 'Arnold, PA 15068' -> 'Arnold'."""
    parts = [x.strip() for x in public(a).split(",") if x.strip() and not re.match(r"^(PA|Pa\.)?\s*\d{5}$|^PA$", x.strip())]
    if parts and re.match(r"^\d", parts[0]):
        parts[0] = ap_addr(parts[0])
    return ", ".join(parts)


def ext(url, label, cls="act"):
    return f'<a class="{cls}" href="{esc(url)}" target="_blank" rel="noopener">{label}</a>'


def picture(R, light, dark, alt, w, h, cls=""):
    c = f' class="{cls}"' if cls else ""
    return (f'<picture class="themed"><source media="(prefers-color-scheme: dark)" srcset="{rel(R, dark)}">'
            f'<img{c} src="{rel(R, light)}" width="{w}" height="{h}" alt="{esc(alt)}" loading="lazy" decoding="async">'
            "</picture>")


def locator_size(D):
    m = re.search(r'width="(\d+)" height="(\d+)"', mapsvg.locator(D)[:400])
    return int(m.group(1)), int(m.group(2))


def join_and(items):
    return S.join_and(items)


def plural(n, one, many=None):
    return one if n == 1 else (many or one + "s")


def map_place(R, p):
    return rel(R, "/map/") + f"?place={fmt.slug(p['n'])}~{round(p['x'])},{round(p['y'])}"


def dir_link(R, **q):
    return rel(R, "/directory/") + "?" + urlencode(q, quote_via=quote)


# --------------------------------------------------------------------------- matching research to places and towns

_NORM_DROP = re.compile(r"\b(new kensington|lower burrell|arnold|the|pa)\b")


def _norm(s):
    return re.sub(r"[^a-z0-9]", "", _NORM_DROP.sub("", str(s or "").lower()))


def match_place(D, name, address=None, exact=False):
    """Port of the old app.js matchPlace(): the places.json row a research entry refers to, or None.
    exact=True accepts only a same-name place (neighborhood names prefix-match unrelated businesses)."""
    if "_pkeys" not in D:
        D["_pkeys"] = [(p, _norm(p["n"])) for p in D["places"]]
    k = _norm(re.split(r" [–-] ", str(name))[0])
    if len(k) < 4:
        return None
    hits = [p for p, pk in D["_pkeys"]
            if pk and (pk == k or (not exact and len(k) >= 6 and (pk.startswith(k) or (k.startswith(pk) and len(pk) >= 6))))]
    if not hits:
        return None
    if address:
        m = re.match(r"^\d+", address)
        if m:
            by = next((p for p in hits if (p.get("a") or "").startswith(m.group(0) + " ")), None)
            if by:
                return by
    return sorted(hits, key=lambda p: -p.get("q", 0))[0]


# names that count as a mention of a town (history also counts Parnassus for New Kensington, spec 1c)
HISTORY_NAMES = {"New Kensington": ("New Kensington", "Parnassus"), "Arnold": ("Arnold",),
                 "Lower Burrell": ("Lower Burrell", "Burrell Township")}
NEWS_NAMES = {"New Kensington": ("New Kensington", "Parnassus"), "Arnold": ("Arnold",), "Lower Burrell": ("Lower Burrell",)}


def mentions(text, town, names=HISTORY_NAMES):
    return any(re.search(rf"\b{re.escape(n)}\b", text or "") for n in names[town])


def towns_in(text, names=HISTORY_NAMES):
    return [t for t in CORE_TOWNS if mentions(text, t, names)]


def first_town(text, names=NEWS_NAMES):
    """The core town named earliest in the text (the old newsTown())."""
    best = None
    for t in CORE_TOWNS:
        for n in names[t]:
            m = re.search(rf"\b{re.escape(n)}\b", text or "")
            if m and (best is None or m.start() < best[0]):
                best = (m.start(), t)
    return best[1] if best else None


def addr_city(a):
    """Town named in a places.json address, with the known misspellings fixed ('' when none)."""
    parts = [p.strip() for p in str(a or "").split(",")]
    if len(parts) < 2:
        return ""
    c = parts[1]
    low = c.lower().replace("-", " ")
    if low in ("new kensington", "new kensingtn", "new kinsington"):
        return "New Kensington"
    if low == "lower burrell":
        return "Lower Burrell"
    if low == "arnold":
        return "Arnold"
    return c


def other_name(t):
    return {"Allegheny": "Allegheny Township"}.get(t, t)


# --------------------------------------------------------------------------- per-town data


def demo(D, town):
    return (D["civic"].get("demographics") or {}).get(fmt.slug(town).replace("-", "_") + "_city") or {}


def gov(D, pattern):
    rx = re.compile(pattern)
    return next((g for g in D["civic"].get("government") or [] if rx.search(g.get("name", ""))), None)


def city_hall(D, town):
    return gov(D, rf"^City of {re.escape(town)}\b.*City Hall")


def library(D, town):
    for g in D["civic"].get("government") or []:
        if "Library" in g.get("name", "") and (town in g.get("name", "") or f", {town}," in g.get("address", "")):
            return g
    return None


def places_in(D, town):
    """The town's places as the directory lists them (duplicates merged), so every count matches its link."""
    return [p for p in PM.dedupe(D["places"]) if PM.town_label(p) == town]


def streets_in(D, town):
    return [s for s in D["streets"] if town in (s.get("t") or [])]


def timeline(D):
    return sorted(D["history"].get("timeline") or [], key=lambda e: int(str(e["year"])[:4]))


def _entry_text(e):
    return " ".join(str(e.get(k) or "") for k in ("title", "text", "name", "address"))


def town_timeline(D, town):
    return [e for e in timeline(D) if mentions(_entry_text(e), town)]


def _year_of(D, test):
    e = next((e for e in timeline(D) if test(e)), None)
    return (int(str(e["year"])[:4]), e) if e else (None, None)


def incorporation(D, town):
    """{'borough': (year, entry), 'city': …, 'split': (year, entry, parent)} from the timeline."""
    t = re.escape(town)
    out = {}
    y, e = _year_of(D, lambda e: re.search(rf"\b{t} was incorporated as a borough", e.get("text", ""))
                    or re.search(rf"^{t} becomes a borough", e.get("title", "")))
    if y:
        out["borough"] = (y, e)
    y, e = _year_of(D, lambda e: re.search(rf"\b{t} was incorporated as a (third-class )?city", e.get("text", ""))
                    or re.search(rf"^{t} becomes a city", e.get("title", "")))
    if y:
        out["city"] = (y, e)
    for e in timeline(D):
        m = re.search(rf"^([A-Z][\w ]*? Township) was divided into .*\b{t}\b", e.get("text", ""))
        if m:
            out["split"] = (int(str(e["year"])[:4]), e, m.group(1))
            break
    return out


_MONTHS = {m: i for i, m in enumerate(_cal.month_name) if m}


def founding_sale(D, town):
    """'June 10, 1891' for New Kensington (history.facts describe New Kensington), else None."""
    if town != "New Kensington":
        return None
    f = str((D["history"].get("facts") or {}).get("founded") or "")
    m = re.search(r"land sale, (\w+) (\d{1,2}), (\d{4})", f)
    if not m or m.group(1) not in _MONTHS:
        return None
    return fmt.ap_date(f"{m.group(3)}-{_MONTHS[m.group(1)]:02d}-{int(m.group(2)):02d}")


def pop_peak(D, town):
    """(value, year) of New Kensington's census peak when it differs from 2020, else None."""
    if town != "New Kensington":
        return None
    pops = {int(y): v for y, v in ((D["history"].get("facts") or {}).get("population_by_census") or {}).items()}
    if not pops:
        return None
    y = max(pops, key=lambda k: pops[k])
    return (pops[y], y) if y != max(pops) else None


def town_glance(D, town):
    """The 'At a glance' paragraph (spec section 6), computed from civic, history and meta. HTML-safe text."""
    dm = demo(D, town)
    pop, inc = dm.get("population_2020"), dm.get("median_household_income")
    out = []
    if pop:
        s = f"{town} had {fmt.num(pop)} residents in the 2020 census"
        peak = pop_peak(D, town)
        if peak:
            s += f", down from a peak of {fmt.num(peak[0])} in {peak[1]}"
        if inc:
            incs = {t: demo(D, t).get("median_household_income") for t in CORE_TOWNS}
            top = max((v for v in incs.values() if v), default=None)
            highest = inc == top and sum(1 for v in incs.values() if v == top) == 1
            if highest:
                s += f", and its median household income, ${fmt.num(inc)}, is the highest of the three cities"
            else:
                s += f"{',' if peak else ''} and a median household income of ${fmt.num(inc)}"
        out.append(s + ".")
    clauses = []
    sale = founding_sale(D, town)
    if sale:
        clauses.append(f"grew from the {sale}, land sale")
    inc_ = incorporation(D, town)
    if "split" in inc_:
        clauses.append(f"was split off from {inc_['split'][2]} in {inc_['split'][0]}")
    if "borough" in inc_:
        clauses.append(f"became a borough in {inc_['borough'][0]}")
    if "city" in inc_:
        clauses.append(("a city" if "borough" in inc_ else "became a city") + f" in {inc_['city'][0]}")
    if clauses:
        out.append("It " + join_and(clauses) + ".")
    st = D["meta"]["stats"]
    out.append(f"The map data holds {fmt.num(st['buildings_by_town'].get(town, 0))} buildings, "
               f"{fmt.num(st['addresses_by_town'].get(town, 0))} address points and "
               f"{fmt.num(len(places_in(D, town)))} listed places in the city.")
    return esc(" ".join(out))


def glance_sources(D, town):
    dm = demo(D, town)
    srcs = [dm.get("source")]
    inc_ = incorporation(D, town)
    srcs += [v[1].get("source") for v in inc_.values()]
    if founding_sale(D, town):
        e = next((e for e in timeline(D) if re.search(r"land sale", e.get("title", ""), re.I)), None)
        if e:
            srcs.insert(1, e.get("source"))
    if pop_peak(D, town):
        e = next((e for e in timeline(D) if re.search(r"peak", e.get("title", ""), re.I)), None)
        if e:
            srcs.append(e.get("source"))
    return [s for s in srcs if s]


def zip_edge_note(D):
    """New Kensington only: how many places outside the city line carry a New Kensington address."""
    c = Counter(p.get("t") for p in D["places"]
                if addr_city(p.get("a")) == "New Kensington" and p.get("t") and p.get("t") != "New Kensington")
    n = sum(c.values())
    if not n:
        return ""
    parts = [f"{fmt.num(v)} in {esc(other_name(t))}" for t, v in sorted(c.items(), key=lambda kv: (-kv[1], kv[0]))]
    return (f"A New Kensington mailing address doesn&rsquo;t always mean the city. In the map data, {fmt.num(n)} places "
            f"outside the city line give New Kensington as their town: {join_and(parts)}. The counts on this page "
            "follow the city line.")


def share_of_zip(D, town):
    return next((t.get("share") for t in D["meta"].get("towns") or [] if t["n"] == town), None)


# --------------------------------------------------------------------------- council (Arnold's rule in civic.json)

ORD_WORDS = {1: "first", 2: "second", 3: "third", 4: "fourth"}
WEEKDAYS = {d: i for i, d in enumerate(_cal.day_name)}


def nth_weekday(y, m, n, wd):
    first = dt.date(y, m, 1)
    d = first + dt.timedelta(days=(wd - first.weekday()) % 7 + 7 * (n - 1))
    return d if d.month == m else None


def next_meeting(rule, today):
    """'2nd Tuesday' -> (n, weekday name, next date on or after today)."""
    m = re.match(r"(\d)(?:st|nd|rd|th)\s+(\w+day)", str(rule or ""), re.I)
    if not m:
        return None
    n, wdn = int(m.group(1)), m.group(2).capitalize()
    if wdn not in WEEKDAYS:
        return None
    y, mo = today.year, today.month
    for _ in range(14):
        d = nth_weekday(y, mo, n, WEEKDAYS[wdn])
        if d and d >= today:
            return n, wdn, d
        mo += 1
        if mo > 12:
            y, mo = y + 1, 1
    return None


# --------------------------------------------------------------------------- news


def news_items(D):
    """Public news briefs, newest first: aggregator-only items dropped, each with an 'id' ('n-<slug>') and 'town'.
    /news/ anchors, the home page's Latest and search.json all use these ids."""
    items = [n for n in D["civic"].get("news_2025_2026") or [] if not fmt.is_aggregator_only(n.get("source"))]
    items = sorted(items, key=lambda n: str(n.get("date") or ""), reverse=True)
    seen, out = Counter(), []
    for n in items:
        base = "n-" + fmt.slug(n.get("headline"))
        seen[base] += 1
        out.append({**n, "id": base if seen[base] == 1 else f"{base}-{seen[base]}",
                    "town": first_town(f"{n.get('headline', '')} {n.get('text', '')}"),
                    "towns": towns_in(f"{n.get('headline', '')} {n.get('text', '')}", NEWS_NAMES),
                    "approx": bool(n.get("date_note"))})
    return out


def news_date(n):
    return fmt.ap_date(n.get("date"), approx=n.get("approx", bool(n.get("date_note"))))


def months_between(a, b):
    """Whole months from the month of ISO date a to the month of date b."""
    ay, am = int(str(a)[:4]), int(str(a)[5:7] or 1)
    return (b.year - ay) * 12 + (b.month - am)


# --------------------------------------------------------------------------- the town pages


def call_card(D, R, town):
    ch, lib = city_hall(D, town), library(D, town)
    pol = S.police_numbers(D).get(town)
    rows, srcs = [], []
    if ch:
        tel = fmt.tel_link(ch.get("phone"), "Call {n}")
        web = ext(ch["url"], "City website ›") if ch.get("url") else ""
        rows.append(f'<div class="cc-row"><p class="cc-what"><b>City hall</b> · {esc(ap_addr(ch.get("address")))}</p>'
                    f'<p class="cc-btns">{tel} {web}</p></div>')
        srcs.append(ch.get("url"))
    if pol:
        alt = "".join(f' <span class="tel-alt">or <a href="{fmt.tel(a)[0][1]}">{esc(a)}</a></span>' for a in pol["alt"])
        rows.append(f'<div class="cc-row"><p class="cc-what"><b>Police</b> · Non-emergency, or 911 for an emergency</p>'
                    f'<p class="cc-btns">{fmt.tel_link(pol["primary"])} '
                    f'<a class="tel primary" href="tel:911" aria-label="Call 911, emergency">911</a>{alt}</p></div>')
        srcs.append(pol.get("source"))
    council = (ch or {}).get("council")
    nm = next_meeting(council.get("rule"), D["today"]) if council else None
    if nm:
        n, wdn, d = nm
        rows.append(f'<p class="cc-note"><b>Council</b> meets the {ORD_WORDS.get(n, str(n))} {wdn} of the month'
                    f'{" at " + esc(council.get("time")) if council.get("time") else ""}'
                    f'{"" if str(council.get("time") or "").endswith(".") else "."} Next expected: '
                    f'{fmt.ap_long(d, year=False)}.</p>')
        srcs.append(council.get("source"))
    else:
        link = f' {ext(ch["url"], "See the city&rsquo;s website ›")}' if ch and ch.get("url") else ""
        rows.append(f'<p class="cc-note"><b>Council</b> meeting nights aren&rsquo;t in our data yet.{link}</p>')
    if lib:
        name = re.sub(r"\s+–\s+.*$", "", lib["name"])
        branch = " branch" if "Branch" in lib["name"] else ""
        label = f"{esc(name)}{', ' + esc(town) + branch if branch else ''}, {esc(ap_addr(lib.get('address')))}"
        if fmt.tel(lib.get("phone")):
            btn = fmt.tel_link(lib["phone"])
        else:
            btn = ('<span class="cc-none">No public number listed'
                   + (" · " + ext(lib["url"], "website ›") if lib.get("url") else "") + "</span>")
        rows.append(f'<div class="cc-row"><p class="cc-what"><b>Library</b> · {label}</p><p class="cc-btns">{btn}</p></div>')
        srcs.append(lib.get("url"))
    rows.append('<p class="cc-note">Trash, recycling and potholes: call city hall. We don&rsquo;t have those '
                "schedules yet.</p>")
    rows.append(f'<p class="cc-mine"><button type="button" class="btn-line inline" data-my-town="{esc(town)}" '
                f'aria-pressed="false" hidden>Make {esc(town)} my town</button></p>'
                f'<p class="fine cc-mine-note" role="status" hidden></p>')
    return (f'<section class="callcity box" id="call-city" aria-labelledby="call-city-h" data-keep-above>'
            f'<h2 class="lh" id="call-city-h">Call the city</h2>{"".join(rows)}{credit_line(srcs, "Sources: ")}</section>')


def locator_figure(D, R, town=None):
    w, h = locator_size(D)
    if town:
        s = TOWN_SLUGS[town]
        pic = picture(R, f"/img/town-{s}.svg", f"/img/town-{s}-dark.svg", f"Map of ZIP 15068 with {town} shaded", w, h)
        cap = f"{esc(town)} within ZIP 15068. Dashed lines are city limits."
    else:
        pic = picture(R, "/img/15068-locator.svg", "/img/15068-locator-dark.svg",
                      "Map of ZIP 15068 showing New Kensington, Arnold and Lower Burrell", w, h)
        cap = ("New Kensington, Arnold and Lower Burrell within ZIP 15068. Dashed lines are city limits; "
               "state routes are orange.")
    return f'<figure class="locator">{pic}<figcaption class="caption">{cap}</figcaption></figure>'


def glance_table(D, town):
    dm, st = demo(D, town), D["meta"]["stats"]
    rows = []
    if dm.get("population_2020"):
        rows.append(("Residents (2020 census)", fmt.num(dm["population_2020"])))
    if dm.get("median_household_income"):
        rows.append(("Median household income", "$" + fmt.num(dm["median_household_income"])))
    sh = share_of_zip(D, town)
    if sh:
        rows.append(("Share of ZIP 15068&rsquo;s area", f"{round(sh * 100)}%"))
    rows += [("Buildings mapped", fmt.num(st["buildings_by_town"].get(town, 0))),
             ("Address points", fmt.num(st["addresses_by_town"].get(town, 0))),
             ("Places listed", fmt.num(len(places_in(D, town)))),
             ("Named streets", fmt.num(len(streets_in(D, town))))]
    return '<dl class="agate">' + "".join(f"<div><dt>{k}</dt><dd>{v}</dd></div>" for k, v in rows) + "</dl>"


def parks_html(D, R, town):
    parks = [p for p in D["civic"].get("parks_and_rec") or [] if town in (p.get("address") or "")]
    if not parks:
        return f'<p>No parks for {esc(town)} are in our research yet.</p>'
    items = []
    for p in parks:
        hit = match_place(D, p["name"], p.get("address"))
        meta = [esc(short_place(p.get("address")))]
        if hit:
            meta.append(f'<a href="{map_place(R, hit)}">Map it</a>')
        meta.append(P.credit(p.get("source")))
        name = re.sub(rf"\s*\({re.escape(town)}\)$", "", p["name"])
        items.append(f'<div class="entry"><p><b>{esc(fmt.end_stop(public(name)))}</b> {tel_text(p.get("text"))}</p>'
                     f'<p class="meta">{" · ".join(m for m in meta if m)}</p></div>')
    return f'<div class="runin{" few" if len(items) < 3 else ""}">{"".join(items)}</div>'


def neighborhoods_for(D, town):
    out = []
    for n in D["history"].get("neighborhoods") or []:
        name = n.get("name", "")
        if name in CORE_TOWNS:
            owner = name
        else:
            owner = first_town(n.get("text"), HISTORY_NAMES) or "New Kensington"  # the research's home city
        if owner == town:
            out.append(n)
    return out


def landmark_towns(D, l):
    a = l.get("address") or ""
    ts = towns_in(a)
    return ts or towns_in(f"{l.get('name', '')} {l.get('text', '')}")


def entry_html(D, R, e, name_key="name", exact=False):
    hit = match_place(D, e.get(name_key), e.get("address"), exact)
    meta = []
    if e.get("address"):
        meta.append(esc(public(e["address"])))
    if hit:
        meta.append(f'<a href="{map_place(R, hit)}">Map it</a>')
    meta.append(P.credit(e.get("source")))
    return (f'<div class="entry"><p><b>{esc(fmt.end_stop(public(e.get(name_key))))}</b> {pub_text(e.get("text"))}</p>'
            f'<p class="meta">{" · ".join(m for m in meta if m)}</p></div>')


def runin(items):
    return f'<div class="runin{" few" if len(items) < 3 else ""}">{"".join(items)}</div>' if items else ""


GROUP_WORDS = {  # group -> (plural, singular)
    "services": ("services", "service"), "shop": ("shops", "shop"),
    "eat": ("places to eat and drink", "place to eat and drink"), "health": ("health care", "health care"),
    "auto": ("auto and travel", "auto and travel"), "civic": ("civic and safety", "civic and safety"),
    "faith": ("places of worship", "place of worship"), "learn": ("schools and learning", "schools and learning"),
    "play": ("parks and play", "parks and play"), "culture": ("arts and history", "arts and history"),
    "stay": ("places to stay", "place to stay"),
}


def whats_here(D, R, town):
    ps = places_in(D, town)
    c = Counter(p["g"] for p in ps)
    parts = []
    for g, n in sorted(c.items(), key=lambda kv: (-kv[1], kv[0])):
        pl, one = GROUP_WORDS.get(g, (D["meta"]["groups"].get(g, g).lower(),) * 2)
        parts.append(f'<a href="{esc(dir_link(R, town=town, g=g))}">{fmt.num(n)} {pl if n != 1 else one}</a>')
    st = D["meta"]["stats"]
    body = (f"<p>The map data lists {fmt.num(len(ps))} places in {esc(town)}: {join_and(parts)}. "
            f"Its {fmt.num(len(streets_in(D, town)))} named streets, {fmt.num(st['buildings_by_town'].get(town, 0))} "
            f"buildings and {fmt.num(st['addresses_by_town'].get(town, 0))} address points are on the map too.</p>"
            f'<p class="links"><a class="go" href="{esc(dir_link(R, town=town))}">All {fmt.num(len(ps))} places in '
            f'{esc(town)}, A to Z ›</a> <a class="go" href="{esc(dir_link(R, tab="streets", town=town))}">'
            f'Streets in {esc(town)} ›</a></p>'
            f'<p class="credit">Source: {mapsvg_credit(D)}</p>')
    return body


def mapsvg_credit(D):
    s = D["meta"]["sources"][0]
    return f'<a class="cr" href="{esc(s["url"])}" target="_blank" rel="noopener">Overture Maps</a> release {esc(s.get("release", ""))}'


def tl_item(D, R, e, tag="h3", towns=True):
    note = public(e.get("note")) if e.get("note") else ""
    dt_ = f' data-towns="{esc("|".join(towns_in(_entry_text(e))))}"' if towns else ""
    return (f'<article class="tl-item"{dt_}><p class="yr">{esc(e.get("year"))}</p><div class="tl-body">'
            f'<{tag} class="tl-h">{esc(fmt.end_stop(public(e.get("title"))))}</{tag}>'
            f'<p class="tl-t">{pub_text(e.get("text"))}</p>'
            + (f'<p class="tl-note">Note: {esc(note)}</p>' if note else "")
            + credit_line([e.get("source")]) + "</div></article>")


def town_news(D, R, town, n=3):
    items = [x for x in news_items(D) if town in x["towns"]][:n]
    if not items:
        return f"<p>No recent news briefs mention {esc(town)} yet.</p>"
    lis = "".join(f'<li><a href="{rel(R, "/news/")}#{x["id"]}">{esc(public(x["headline"]))}</a>'
                  f'<span class="hl-meta">{esc(news_date(x))} · {esc(P.outlet(_first(x.get("source"))))}</span></li>'
                  for x in items)
    return f'<ul class="heads">{lis}</ul><p><a class="go" href="{rel(R, "/news/")}">All news ›</a></p>'


def _first(src):
    return src[0] if isinstance(src, list) else src


def _srcs(x):
    s = x.get("source") if isinstance(x, dict) else x
    return [u for u in (s if isinstance(s, list) else [s]) if u]


def town(D, R):
    t = SLUG_TOWNS[R.arg]
    s = R.arg
    srcs = []
    # top: the call card and locator (rail on desktop), at a glance and parks (main column)
    glance = (f"<p>{town_glance(D, t)}</p>" + credit_line(glance_sources(D, t), "Sources: ")
              + glance_table(D, t)
              + (f'<p class="edge-note">{zip_edge_note(D)}</p>' if t == "New Kensington" and zip_edge_note(D) else ""))
    srcs += glance_sources(D, t)
    parks = parks_html(D, R, t)
    srcs += [p.get("source") for p in D["civic"].get("parks_and_rec") or [] if t in (p.get("address") or "")]
    top = (f'<div class="tw-top"><div class="tw-rail">{call_card(D, R, t)}{locator_figure(D, R, t)}</div>'
           f'<div class="tw-main">{sec("glance", "At a glance", glance)}{sec("parks", "Parks", parks)}</div></div>')

    # safety and crashes
    ic = S.incident_counts(D, t)
    blot = rel(R, "/crime/blotter/") + "?" + urlencode({"town": t}, quote_via=quote)
    safety = (f"<p>{S.short_answer(D, t)}</p>"
              + (f"<p>{fmt.num(ic['n'])} news-reported {plural(ic['n'], 'incident')} in {esc(t)} "
                 f"{'is' if ic['n'] == 1 else 'are'} on the police blotter, the earliest from {ic['first_year']}.</p>"
                 if ic["n"] else f"<p>No news-reported incidents in {esc(t)} are on the police blotter yet.</p>")
              + f'<p class="links"><a class="go" href="{rel(R, f"/crime/{s}/")}">{esc(t)} crime, in full ›</a> '
              f'<a class="go" href="{esc(blot)}">{esc(t)} on the police blotter ›</a></p>'
              + credit_line([S.FBI_SOURCE]))
    srcs.append(S.FBI_SOURCE)
    cr_src = D["safety"]["crashes"].get("source")
    crashes = (f"<p>{S.crash_town_sentence(D, t)}</p>"
               f'<p class="links"><a class="go" href="{rel(R, "/crashes/")}">Serious and fatal crashes ›</a></p>'
               + credit_line([cr_src]))
    srcs.append(cr_src)

    # neighborhoods and landmarks
    hoods = neighborhoods_for(D, t)
    lms = [l for l in D["history"].get("landmarks") or [] if t in landmark_towns(D, l)]
    nl = ""
    own = [n for n in hoods if n.get("name") == t]
    hoods = [n for n in hoods if n.get("name") != t]
    for n in own:
        nl += f'<p>{pub_text(n.get("text"))}</p>{credit_line([n.get("source")])}'
    if hoods:
        nl += f'<h3 class="sub-h">Neighborhoods</h3>{runin([entry_html(D, R, n, exact=True) for n in hoods])}'
    if lms:
        first, rest = lms[:5], lms[5:]
        nl += f'<h3 class="sub-h">Landmarks</h3>{runin([entry_html(D, R, l) for l in first])}'
        if rest:
            nl += (f'<details class="more-list"><summary>All {len(lms)} landmarks</summary>'
                   f'{runin([entry_html(D, R, l) for l in rest])}</details>')
    if not nl:
        nl = f"<p>No neighborhoods or landmarks for {esc(t)} are in our research yet.</p>"
    srcs += [x.get("source") for x in own + hoods + lms]

    # history
    tl = town_timeline(D, t)
    hist = ""
    if tl:
        first, rest = tl[:6], tl[6:]
        hist = f'<div class="chron">{"".join(tl_item(D, R, e, towns=False) for e in first)}</div>'
        if rest:
            hist += (f'<details class="more-list"><summary>{len(rest)} more from {esc(t)}&rsquo;s history</summary>'
                     f'<div class="chron">{"".join(tl_item(D, R, e, towns=False) for e in rest)}</div></details>')
        hist += f'<p class="links"><a class="go" href="{rel(R, "/history/")}">A history of 15068 ›</a></p>'
        srcs += [e.get("source") for e in tl]
    else:
        hist = f'<p>No dated events for {esc(t)} are in our research yet. <a class="go" href="{rel(R, "/history/")}">A history of 15068 ›</a></p>'

    news = town_news(D, R, t)
    srcs += [_first(x.get("source")) for x in news_items(D) if t in x["towns"]][:3]

    body = (
        f'<h1>{esc(R.h1)}</h1>{updated_line(D, R)}{top}'
        "<!--AD:mid-->"
        + sec("safety", "Safety", safety)
        + sec("crashes", "Serious crashes", crashes)
        + sec("places", "Neighborhoods and landmarks", nl)
        + sec("whats-here", "What&rsquo;s here", whats_here(D, R, t))
        + sec("history", "History", hist)
        + sec("news", "In the news", news)
        + P.town_section(D, R, t)
        + "<!--AD:end-->"
        + sources_line(srcs + [D["meta"]["sources"][0]["url"]])
    )
    return {"body": f'<div class="page town-page">{body}</div>', "crumbs": [("Towns", "/towns/"), (t, None)]}


# --------------------------------------------------------------------------- /towns/

TOWN_DESC = {
    "New Kensington": ("The river-flat street grid, laid out for the 1891 land sale and the first aluminum works. "
                       "Downtown sits along Fifth Avenue.", r"land sale|Aluminum works"),
    "Arnold": ("The smaller city just upriver, sharing New Kensington&rsquo;s school district and its Alcoa-era mill "
               "history.", r"^Arnold$"),
    "Lower Burrell": ("Hilltop suburbs and ravines above the valley, split from old Burrell Township in 1879.",
                      r"^Lower Burrell$|Lower and Upper Burrell split"),
}


def desc_sources(D, t):
    rx = re.compile(TOWN_DESC[t][1])
    srcs = [e.get("source") for e in timeline(D) if rx.search(e.get("title", ""))]
    srcs += [n.get("source") for n in D["history"].get("neighborhoods") or [] if rx.search(n.get("name", ""))]
    return [s for s in srcs if s]


def inc_line(D, t):
    i = incorporation(D, t)
    parts = []
    if "split" in i:
        parts.append(f"Township {i['split'][0]}")
    if "borough" in i:
        parts.append(f"Borough {i['borough'][0]}")
    if "city" in i:
        parts.append(("city" if parts else "City") + f" {i['city'][0]}")
    return " · ".join(parts)


def ledger(D):
    s, d = D["meta"]["stats"], (D["civic"].get("demographics") or {}).get("zcta_15068") or {}
    rows = []
    if d.get("population"):
        rows.append(("Residents (ACS estimate)", fmt.num(d["population"])))
    rows += [("Buildings", fmt.num(s["buildings"])), ("Address points", fmt.num(s["addresses"])),
             ("Named streets", fmt.num(s["streets"])), ("Road, in kilometres", fmt.num(round(s["road_km"]))),
             ("Businesses and places", fmt.num(s["places"])), ("No chain brand (share)", f"{round(s['local_share'] * 100)}%"),
             ("Area, land and river, km²", f"{s['area_km2']:g}")]
    note = []
    if d.get("population"):
        note.append(f"Residents from the American Community Survey. {P.credit(d.get('source'))}.")
    note.append(f"Other counts from {mapsvg_credit(D)}.")
    return (f'<dl class="facts" id="ledger-grid">' + "".join(f"<div><dt>{k}</dt><dd>{v}</dd></div>" for k, v in rows)
            + f'</dl><p class="fine" id="ledger-note">{" ".join(note)}</p>')


def edges_note(D):
    towns = D["meta"].get("towns") or []
    core = sum(t["share"] for t in towns if t["n"] in CORE_TOWNS)
    others = sorted((t for t in towns if t["n"] not in CORE_TOWNS), key=lambda t: -t["share"])
    big = [t for t in others if round(t["share"] * 100) >= 1]
    small = [t for t in others if round(t["share"] * 100) < 1]
    bb = D["meta"]["stats"]["buildings_by_town"]
    edge_b = sum(v for k, v in bb.items() if k not in CORE_TOWNS)
    parts = [f"{esc(other_name(t['n']))} ({round(t['share'] * 100)}%)" for t in big]
    tail = f", plus slivers of {join_and([esc(other_name(t['n'])) for t in small])}" if small else ""
    return (f"<p>ZIP 15068 is bigger than the three cities. By area, {round(core * 100)}% of it is New Kensington, "
            f"Arnold and Lower Burrell; the rest is edges of {join_and(parts)}{tail}. Those edges hold "
            f"{fmt.num(edge_b)} of the ZIP&rsquo;s {fmt.num(D['meta']['stats']['buildings'])} buildings. The map covers "
            "the whole ZIP; the town pages cover the three cities.</p>")


def towns_hub(D, R):
    rows = {r["town"]: r for r in S.home_crime_rows(D)}
    pols = S.police_numbers(D)
    cards, srcs = [], []
    for t in CORE_TOWNS:
        dm = demo(D, t)
        ch = city_hall(D, t)
        s = TOWN_SLUGS[t]
        agate = []
        if dm.get("population_2020"):
            agate.append(("Population (2020)", fmt.num(dm["population_2020"])))
        if dm.get("median_household_income"):
            agate.append(("Median household income", "$" + fmt.num(dm["median_household_income"])))
        agate += [("Buildings mapped", fmt.num(D["meta"]["stats"]["buildings_by_town"].get(t, 0))),
                  ("Places listed", fmt.num(len(places_in(D, t))))]
        cr = rows.get(t)
        crime = (f'<p class="tw-crime"><b>Violent crime: {esc(cr["word"])}</b> · {cr["text"]}. '
                 f'<a href="{rel(R, f"/crime/{s}/")}">Crime in {esc(t)} ›</a></p>') if cr else ""
        tels = []
        if ch and fmt.tel(ch.get("phone")):
            tels.append(f'<a class="tel stack" href="{fmt.tel(ch["phone"])[0][1]}">City hall'
                        f'<span class="small">{fmt.tel(ch["phone"])[0][0]}</span></a>')
        if pols.get(t):
            tels.append(f'<a class="tel stack" href="{fmt.tel(pols[t]["primary"])[0][1]}">Police'
                        f'<span class="small">{pols[t]["primary"]} (non-emergency)</span></a>')
        desc_src = desc_sources(D, t)
        cards.append(
            f'<article class="tw-card" data-town="{esc(t)}">'
            f'<h2 class="tw-name"><a href="{rel(R, f"/towns/{s}/")}">{esc(t)}</a></h2>'
            + (f'<p class="tw-inc">{esc(inc_line(D, t))}</p>' if inc_line(D, t) else "")
            + f'<p class="tw-desc">{TOWN_DESC[t][0]}</p>'
            + '<dl class="agate">' + "".join(f"<div><dt>{k}</dt><dd>{v}</dd></div>" for k, v in agate) + "</dl>"
            + crime
            + (f'<div class="tw-tels">{"".join(tels)}</div>' if tels else "")
            + credit_line([dm.get("source")] + desc_src + ([ch.get("url")] if ch else []), "Sources: ")
            + f'<p><a class="go" href="{rel(R, f"/towns/{s}/")}">All about {esc(t)} ›</a></p></article>')
        srcs += [dm.get("source")] + desc_src
    body = (f'<h1>{esc(R.h1)}</h1>'
            '<p class="deck">New Kensington holds the river-flat street grid, Arnold sits just upriver, and Lower Burrell '
            "covers the hills above. The ZIP also clips edges of Upper Burrell, Plum and Allegheny Township.</p>"
            f'<div class="hub-top">{locator_figure(D, R)}<div class="hub-grid" id="towns-grid">{"".join(cards)}</div></div>'
            + sec("ledger", "15068 by the count", f'<div class="ledger-cols"><div>{ledger(D)}</div>{edges_note(D)}</div>')
            + sources_line(srcs + [S.FBI_SOURCE, D["meta"]["sources"][0]["url"]]))
    return {"body": f'<div class="page towns-hub">{body}</div>', "crumbs": [("Towns", None)]}


# --------------------------------------------------------------------------- /news/


def town_chips(label, what):
    btns = '<button type="button" data-town="" aria-pressed="true">All</button>' + "".join(
        f'<button type="button" data-town="{esc(t)}" aria-pressed="false">{esc(t)}</button>' for t in CORE_TOWNS)
    return (f'<div class="chips-row" data-chips="{what}" hidden><div class="picker" role="group" aria-label="{esc(label)}">'
            f'{btns}</div><p class="chip-count" role="status"></p></div>')


def brief(R, n):
    where = f" · {esc(n['town'])}" if n.get("town") else ""
    return (f'<article class="brief" id="{esc(n["id"])}" data-towns="{esc("|".join(n["towns"]))}">'
            f'<h2 class="brief-h">{esc(public(n["headline"]))}</h2>'
            f'<p class="dateline"><span class="new-tag" hidden>New to you · </span>{esc(news_date(n))}{where}</p>'
            f'<p class="brief-t">{pub_text(n.get("text"))}</p>{credit_line(_srcs(n))}</article>')


def news(D, R):
    items = news_items(D)
    today = D["today"]
    recent = [n for n in items if months_between(n["date"], today) <= 12]
    older = [n for n in items if months_between(n["date"], today) > 12]
    body = [f'<h1>{esc(R.h1)}</h1>',
            '<p class="deck">Short summaries of other outlets&rsquo; reporting, newest first. Each links to the original.</p>',
            town_chips("Show briefs about", "news"),
            f'<div id="news-list" class="briefs">{"".join(brief(R, n) for n in recent)}']
    if older:
        ys = sorted({str(n["date"])[:4] for n in older})
        span = ys[0] if len(ys) == 1 else f"{ys[0]}–{ys[-1]}"
        body.append(f'<details class="earlier" id="earlier"><summary>Earlier: {span} ({len(older)})</summary>'
                    f'{"".join(brief(R, n) for n in older)}</details>')
    body.append("</div>")
    body.append(f'<p class="empty" id="news-none" hidden>No briefs mention that town yet.</p>')
    body.append(f'<p class="fine">Briefs are summaries in our own words; follow each source link for the full story. '
                f'Something wrong? <a href="{esc(correction_url(D))}">Report a correction ›</a></p>')
    return {"body": f'<div class="page news-page">{"".join(body)}</div>', "crumbs": [("News", None)]}


# --------------------------------------------------------------------------- /history/

ERAS = [(None, 1890, "{first}–1890"), (1891, 1945, "1891–1945"), (1946, 1999, "1946–1999"), (2000, None, "2000–today")]


def eras(D):
    tl = timeline(D)
    first = int(str(tl[0]["year"])[:4]) if tl else 1769
    out = []
    for lo, hi, label in ERAS:
        lab = label.format(first=first)
        items = [e for e in tl if (lo is None or int(str(e["year"])[:4]) >= lo) and (hi is None or int(str(e["year"])[:4]) <= hi)]
        out.append((lab.replace("–", "-"), lab, items))
    return out


def census_gaps(D):
    """'1900–1920 and 1970–1990': census decades from the first after the borough began through the latest
    count that aren't in population_by_census."""
    pops = {int(y) for y in ((D["history"].get("facts") or {}).get("population_by_census") or {})}
    if not pops:
        return ""
    b = incorporation(D, "New Kensington").get("borough")
    start = ((b[0] // 10) + 1) * 10 if b else min(pops)
    missing = [y for y in range(start, max(pops) + 1, 10) if y not in pops]
    runs = []
    for y in missing:
        if runs and y == runs[-1][1] + 10:
            runs[-1][1] = y
        else:
            runs.append([y, y])
    return join_and([f"{a}–{b}" if a != b else str(a) for a, b in runs])


def population_html(D):
    f = D["history"].get("facts") or {}
    chart = charts.pop_chart(f)
    gaps = census_gaps(D)
    nb = f.get("neighbor_populations_2020") or {}
    pop_src = [e.get("source") for e in timeline(D) if re.match(r"^population", e.get("title", ""), re.I)]
    out = f'<div class="pop-chart">{chart}</div>' if chart else ""
    txt = []
    if gaps:
        txt.append(f"Census counts for {gaps} aren&rsquo;t in our data yet.")
    if nb.get("Arnold") and nb.get("Lower Burrell"):
        txt.append(f"In 2020 Arnold had {fmt.num(nb['Arnold'])} residents and Lower Burrell {fmt.num(nb['Lower Burrell'])}.")
    out += f"<p>{' '.join(txt)}</p>" + credit_line(pop_src)
    return out


def history(D, R):
    ers = eras(D)
    tl = timeline(D)
    jumps = " · ".join(f'<a href="#{a}">{esc(l)}</a>' for a, l, items in ers if items)
    parts = [f'<h1>{esc(R.h1)}</h1>',
             dateline(f"Research compiled {fmt.ap_date(D['history']['_meta']['compiled'])}"),
             f'<p class="deck">From the Parnassus land tract and Fort Crawford to the first aluminum works, the 1950 census '
             f"peak and the Fifth Avenue revival: {fmt.num(len(tl))} dated events, each linked to where it was reported.</p>",
             f'<nav class="era-jump" aria-label="Eras"><span class="lh-inline">Jump to</span> {jumps}</nav>',
             town_chips("Show events about", "history")]
    for a, label, items in ers:
        if not items:
            continue
        parts.append(f'<section class="sec era" id="{a}" aria-labelledby="{a}-h"><h2 id="{a}-h">{esc(label)}</h2>'
                     f'<div class="chron">{"".join(tl_item(D, R, e) for e in items)}</div></section>')
        if label == "1891–1945":
            parts.append("<!--AD:mid-->")
    parts.append('<p class="empty" id="tl-none" hidden>No events mention that town.</p>')
    parts.append(sec("population", "New Kensington population, by census", population_html(D)))
    hoods = [entry_html(D, R, n, exact=True) for n in D["history"].get("neighborhoods") or []]
    lms = [entry_html(D, R, l) for l in D["history"].get("landmarks") or []]
    parts.append(sec("neighborhoods", "Neighborhoods", runin(hoods)))
    parts.append(sec("landmarks", "Landmarks and historic districts", runin(lms)))
    parts.append(f'<p class="links"><a class="go" href="{rel(R, "/history/people/")}">Notable people from 15068 ›</a></p>')
    parts.append("<!--AD:end-->")
    srcs = [e.get("source") for e in tl] + [x.get("source") for k in ("neighborhoods", "landmarks")
                                              for x in D["history"].get(k) or []]
    parts.append(sources_line(srcs))
    return {"body": f'<div class="page history-page">{"".join(parts)}</div>', "crumbs": [("History", None)]}


# --------------------------------------------------------------------------- /history/people/


def people(D, R):
    ps = D["history"].get("people") or []
    items = []
    for p in ps:
        items.append(f'<div class="person"><h2 class="p-name">{esc(public(p.get("name")))}</h2>'
                     f'<p class="kf">{esc(fmt.end_stop(fmt.cap(public(p.get("known_for")))))}</p>'
                     + (f'<p class="conn">{esc(fmt.end_stop(public(p["connection"])))}</p>' if p.get("connection") else "")
                     + credit_line([p.get("source")]) + "</div>")
    body = (f'<h1>{esc(R.h1)}</h1>'
            + dateline(f"Research compiled {fmt.ap_date(D['history']['_meta']['compiled'])}")
            + f'<p class="deck">{fmt.num(len(ps))} people born, raised or remembered in the three cities, from the '
            "inventor of Kevlar to NFL players. Each entry links to where it was reported.</p>"
            + f'<div class="people" id="people-list">{"".join(items)}</div>'
            + f'<p class="links"><a class="go" href="{rel(R, "/history/")}">A history of 15068 ›</a> '
            f'<a class="go" href="{esc(correction_url(D))}">Know someone we missed? Tell us ›</a></p>')
    return {"body": f'<div class="page people-page">{body}</div>',
            "crumbs": [("History", "/history/"), ("Notable people", None)]}


# --------------------------------------------------------------------------- /eat/

BUCKETS = [
    ("Restaurants and diners", r"restaurant|diner|pizza|grill|italian|kitchen|sandwich|wing|burger|deli"),
    ("Bars, breweries and clubs", r"bar|pub|brew|tavern|club|lounge|distill|winery"),
    ("Bakeries, cafés and sweets", r"baker|caf|coffee|ice cream|sweet|donut|dessert|candy"),
    ("Venues", r"venue|hall|event|theat"),
    ("Other", r".*"),
]


def eat(D, R):
    # like the news briefs, entries sourced only to an aggregator wait for a primary source
    lst = [f for f in D["civic"].get("food_and_culture") or [] if not fmt.is_aggregator_only(f.get("source"))]
    groups = [(t, []) for t, _ in BUCKETS]
    for f in lst:
        i = next(i for i, (_, rx) in enumerate(BUCKETS) if re.search(rx, f.get("type") or "", re.I))
        groups[i][1].append(f)
    secs = []
    for title, g in groups:
        if not g:
            continue
        rows = []
        for f in g:
            hit = match_place(D, f["name"], f.get("address"))
            addr = f'<span class="addr">{esc(fmt.short_addr(public(f["address"])))}</span>' if f.get("address") else ""
            typ = f'<i>{esc(fmt.end_stop(fmt.cap(public(f["type"]).replace("/", ", "))))}</i> ' if f.get("type") else ""
            acts = []
            if hit and fmt.tel(hit.get("ph")):
                acts.append(fmt.tel_link(hit["ph"], "Call {n}"))
            town_ = addr_city(f.get("address"))
            links = [esc(town_)] if town_ in CORE_TOWNS else []
            if hit:
                links.append(f'<a href="{map_place(R, hit)}">Map it</a>')
            links.append(P.credit(f.get("source")))
            rows.append(f'<div class="dine"><div class="l1"><b>{esc(public(f["name"]))}</b>{addr}</div>'
                        f'<p class="l2">{typ}{pub_text(f.get("text"))}</p>'
                        f'<p class="l3">{"".join(acts)}<span>{" · ".join(l for l in links if l)}</span></p></div>')
        sid = fmt.slug(title)
        secs.append(sec(sid, esc(title), f'<div class="bucket{" few" if len(rows) < 3 else ""}">{"".join(rows)}</div>',
                        "eat-sec"))
    body = (f'<h1>{esc(R.h1)}</h1>'
            f'<p class="deck">{fmt.num(len(lst))} restaurants, bars, bakeries and clubs with a published write-up.</p>'
            + "".join(secs)
            + f'<p class="links"><a class="go" href="{rel(R, "/calendar/")}">Festivals and Fridays on Fifth: the calendar ›</a> '
            f'<a class="go" href="{esc(dir_link(R, g="eat"))}">Every place to eat and drink in the map data, A to Z ›</a></p>'
            + sources_line([f.get("source") for f in lst]))
    return {"body": f'<div class="page eat-page">{body}</div>', "crumbs": [("Eat & drink", None)]}


# --------------------------------------------------------------------------- /poster/


def poster(D, R):
    st = D["meta"]["stats"]
    rel_ = D["meta"]["sources"][0].get("release", "")
    km = fmt.num(round(st["road_km"]))
    w, h = mapsvg.POSTER_W // 4, mapsvg.POSTER_H // 4
    pic = picture(R, "/poster/15068-roads.svg", "/poster/15068-roads-dark.svg",
                  "Poster: every road in ZIP 15068, with New Kensington, Arnold and Lower Burrell labeled", w, h,
                  "poster-img")
    body = (
        f'<h1>{esc(R.h1)}</h1>'
        f'<p class="deck">Every road in ZIP 15068, drawn from {km} km of open road data. Print it, frame it, put it '
        "on a T-shirt. Just keep the credit line on it.</p>"
        f'<div class="poster-grid"><figure class="poster-fig" id="poster-fig">{pic}</figure>'
        '<div class="poster-side">'
        '<p class="poster-btns"><a class="btn-line" id="poster-svg" href="15068-roads.svg" download="15068-roads.svg">'
        "Download the poster (SVG, prints at any size)</a>"
        '<button type="button" class="btn-line" id="poster-png" data-src="15068-roads.svg" hidden>Save a PNG (3600 × 4800)</button>'
        '<a class="go" href="15068-roads-dark.svg" download="15068-roads-dark.svg">The dark version (SVG) ›</a></p>'
        '<p class="fine" id="poster-msg" role="status"></p>'
        + sec("mine", "Your street poster",
              '<p>Type a street in 15068. We&rsquo;ll crop the poster to it, draw your street in blue and put its name '
              "in the title. It&rsquo;s made on your device; nothing is sent anywhere.</p>"
              '<form class="sitesearch street-form" id="street-form" hidden><label for="street-q">Street</label>'
              '<span class="sf-row"><input id="street-q" name="street" type="search" list="street-list" '
              'placeholder="Like Leishman Avenue" autocomplete="off"><button type="submit">Make my poster</button></span>'
              '<datalist id="street-list"></datalist></form>'
              '<noscript><p class="fine">The street poster is made in your browser, so it needs JavaScript.</p></noscript>'
              '<p class="fine" id="street-msg" role="status"></p><p class="fine street-alt" id="street-alt" hidden></p>'
              '<div id="street-out" hidden><figure class="poster-fig" id="street-fig"></figure>'
              '<p class="poster-btns"><a class="btn-line" id="street-svg" href="#" download>Download it (SVG)</a>'
              '<button type="button" class="btn-line" id="street-png">Save it as a PNG (3600 × 4800)</button></p></div>',
              "mine")
        + f'<p class="links"><a class="go" href="{rel(R, "/map/3d/")}">The 3D version ›</a> '
        f'<a class="go" href="{rel(R, "/map/")}">The searchable map ›</a></p>'
        + sec("how", "How it&rsquo;s drawn",
              f"<p>{km} km of road and {fmt.num(st['streets'])} named streets from Overture Maps release {esc(rel_)}, "
              "clipped to the Census Bureau&rsquo;s boundary for ZIP 15068. State routes are orange, the dashed line is "
              "the ZIP boundary, and the river and creeks come from the same open data. Every line is rounded to the "
              "nearest metre, and the coordinates under the title are the centre of New Kensington.</p>"
              f'<p class="credit">Map data © {ext("https://www.openstreetmap.org/copyright", "OpenStreetMap contributors", "cr")}, '
              f'{ext(D["meta"]["sources"][0]["url"], "Overture Maps Foundation", "cr")}.</p>')
        + "</div></div>")
    return {"body": f'<div class="page poster-page">{body}</div>', "crumbs": [("Map poster", None)]}


# --------------------------------------------------------------------------- /whats-new/


def whats_new(D, R):
    ents = changelog.entries(D)
    today = D["today"]
    feed = '<p class="links"><a class="go" href="feed.xml">Follow updates (RSS) ›</a></p>'
    intro = ('<p class="deck">Every change to the data behind NK15068, newest first: news briefs, police blotter '
             "entries, FBI years and map releases.</p>")

    def entry(e):
        return (f'<article class="wn-entry" id="d-{esc(e["date"])}"><h2 class="wn-date">'
                f'<time datetime="{esc(e["date"])}">{fmt.ap_date(e["date"])}</time></h2>'
                f'<p class="wn-items">{esc(changelog.line(e))}</p></article>')
    if not ents:
        list_html = ('<p class="wn-none">Nothing has been logged here yet. Each time the site&rsquo;s data changes, '
                     "an entry appears here with the date and what changed: new news briefs, police blotter entries, "
                     "FBI figures or a new map release. Follow the feed to hear about the first one.</p>")
    else:
        recent = [e for e in ents if (today - dt.date.fromisoformat(e["date"])).days <= 183]
        older = [e for e in ents if e not in recent]
        list_html = f'<div class="wn-list">{"".join(entry(e) for e in recent)}</div>'
        if older:
            list_html += (f'<details class="more-list"><summary>Older updates ({len(older)})</summary>'
                          f'<div class="wn-list">{"".join(entry(e) for e in older)}</div></details>')
    body = (f'<h1>{esc(R.h1)}</h1>{intro}{list_html}{feed}'
            f'<p class="fine">Spotted something that changed and isn&rsquo;t here? '
            f'<a href="{esc(correction_url(D))}">Report a correction ›</a></p>')
    head = f'<link rel="alternate" type="application/rss+xml" title="What&rsquo;s new on NK15068" href="feed.xml">'
    return {"body": f'<div class="page wn-page">{body}</div>', "crumbs": [("What’s new", None)], "head": head}


# --------------------------------------------------------------------------- /about/


def refresh_live(D):
    return (D["root"] / ".github" / "workflows" / "refresh.yml").exists()


def owner(D):
    n = (D["cfg"].get("owner_name") or "").strip()
    return esc(n) if n else "the GitHub account DonnieCash"


def about(D, R):
    st = D["meta"]["stats"]
    kept = ("<p>Map data and crime figures are refreshed monthly; each change is listed on "
            f'<a href="{rel(R, "/whats-new/")}">What&rsquo;s new</a>. The lost and found board updates within minutes '
            "of a post.</p>") if refresh_live(D) else (
        f'<p>Each change to the data is listed on <a href="{rel(R, "/whats-new/")}">What&rsquo;s new</a>. The lost and '
        "found board updates within minutes of a post.</p>")
    ads = ("<p>The site shows no ads.</p>" if not (D["cfg"].get("adsense_client") or "").strip() else
           "<p>Some pages carry up to two clearly labeled Google ads, placed below the phone numbers and never on the "
           "lost-pets, phone-number, calendar or front pages. Ads don&rsquo;t choose or change what we publish.</p>")
    whats = [
        ("/lost-pets/", "Lost and found pets", "who to call first, a free board for neighbors&rsquo; posts and a flyer maker"),
        ("/numbers/", "Phone numbers", "city halls, police non-emergency lines, the library, schools and animal help"),
        ("/calendar/", "Calendar", "Fridays on Fifth, council nights, deadlines and yearly events"),
        ("/crime/", "Crime", "each police department&rsquo;s FBI figures in plain words, the police blotter and serious crashes"),
        ("/map/", "Map", f"{fmt.num(st['places'])} places and {fmt.num(st['streets'])} streets on a map drawn from open data"),
        ("/towns/", "The three towns", "city halls, parks, neighborhoods and figures for each city"),
        ("/news/", "News", "short summaries of other outlets&rsquo; reporting, each linked to the original"),
        ("/history/", "History", f"{fmt.num(len(D['history'].get('timeline') or []))} dated events, neighborhoods, landmarks and notable people"),
    ]
    whats_html = "<ul class=\"about-list\">" + "".join(
        f'<li><a href="{rel(R, p)}">{t}</a>: {d}.</li>' for p, t, d in whats) + "</ul>"
    body = (
        f'<h1>{esc(R.h1)}</h1>'
        f'<p class="lede-p">NK15068 is an independent guide to ZIP 15068 (New Kensington, Arnold and Lower Burrell, Pa.), '
        f"published by {owner(D)}. It draws its own map from open data, computes crime and crash figures from the "
        "FBI&rsquo;s and PennDOT&rsquo;s public files, and links every news summary, phone number and historical fact "
        "to where it was published. Nothing here is paid placement.</p>"
        + ads
        + sec("whats-here", "What&rsquo;s on the site", whats_html)
        + sec("made", "How it&rsquo;s made",
              "<p>The map comes from Overture Maps and OpenStreetMap, clipped to the Census boundary for 15068. The "
              "history, civic, news and lost-pet entries were compiled from published reporting and official pages in "
              f"{_month_year(D['civic']['_meta']['compiled'])}. Some linked pages couldn&rsquo;t be opened while this was compiled; for "
              "those, the facts come from a search engine&rsquo;s summary of the page rather than the page itself. Every "
              "entry links to its source, so you can check it, and corrections are welcome.</p>"
              f'<p>Every source is listed with its license on <a href="{rel(R, "/sources/")}">Sources</a>.</p>')
        + sec("kept", "How it&rsquo;s kept up to date", kept)
        + sec("corrections", "Corrections",
              "<p>If something is wrong, tell us with a link to a better source and we&rsquo;ll fix it and note the "
              "change on What&rsquo;s new.</p>"
              f'<p class="links"><a class="go" href="{esc(correction_url(D))}">Report a correction ›</a> '
              f'<a class="go" href="{rel(R, "/contact/")}">Other ways to reach us ›</a></p>')
        + sec("data", "What&rsquo;s in the data", ledger(D)))
    return {"body": f'<div class="page about-page">{body}</div>', "crumbs": [("About", None)]}


def _month_year(iso):
    d = dt.date.fromisoformat(str(iso)[:10])
    return f"{_cal.month_name[d.month]} {d.year}"


# --------------------------------------------------------------------------- /privacy/

LOCAL_KEYS = [
    ("nk-theme", "your light or dark theme choice, when you pick one"),
    ("nk-town", "your town, when you choose &ldquo;Make … my town&rdquo; or pick one on Phone numbers or Lost pets, "
                "so that town comes first"),
    ("nk-corner", "the corner or street you typed on the lost-pets board or the map, only if you tap Remember"),
    ("nk-last-visit", "when you last opened the site, for the &ldquo;since your last visit&rdquo; line and the new-listing badge"),
    ("nk-seen-pets", "when you last looked at the lost and found board, so new listings can be marked"),
    ("nk-seen-news", "which news briefs you&rsquo;ve seen, so new ones can be marked &ldquo;New to you&rdquo;"),
    ("nk-checklist", "which steps you ticked on the lost-pet checklist"),
]
SESSION_KEYS = [
    ("nk-visit-prev", "the time of your previous visit, kept only until you close the tab"),
    ("nk-flyer-draft", "a lost-pet flyer you&rsquo;re making, including its photo, until you close the tab"),
]
STORAGE_KEYS = [k for k, _ in LOCAL_KEYS + SESSION_KEYS]


def privacy(D, R):
    cfg = D["cfg"]
    ads = bool((cfg.get("adsense_client") or "").strip())
    keys = "".join(f"<li><code>{k}</code>: {d}.</li>" for k, d in LOCAL_KEYS)
    skeys = "".join(f"<li><code>{k}</code>: {d}.</li>" for k, d in SESSION_KEYS)
    stored = (f"<p>The site keeps a few small settings in your browser&rsquo;s local storage:</p><ul class=\"keys\">{keys}</ul>"
              f"<p>And, until you close the tab, in session storage:</p><ul class=\"keys\">{skeys}</ul>"
              "<p>All of it stays in your browser; none of it is sent to us. There are no accounts, and the site "
              "sets no cookies of its own.</p>")
    location = ("<p>If you tap Use my location, your browser asks first. The page turns your position into the nearest "
                "street using map data already on your phone. Your coordinates are never sent to us or anyone else, and "
                "we keep only the street name, and only if you tap Remember.</p>"
                "<p>Use my location appears only on the lost-pets board and the map, and before your browser asks, the "
                "page says what it will do with your location.</p>")
    posts = ("<p>Lost and found posts are public GitHub issues, written by the people who post them. Anyone can read "
             "them, on GitHub and on this site. To take yours down, close the issue on GitHub; it drops off the board "
             "at the next update. Only share contact details you&rsquo;re comfortable posting publicly. The form "
             "removes house numbers from the &ldquo;last seen near&rdquo; line.</p>")
    hosts = [
        "<b>Google Fonts</b> (fonts.googleapis.com and fonts.gstatic.com) on every page, for the typefaces.",
        "<b>cdnjs.cloudflare.com</b> only on the 3D map page, for the three.js graphics library.",
        "<b>api.github.com</b> only when the lost and found board&rsquo;s copy on this site is missing or more than a "
        "day old, to read the open posts.",
        "<b>GitHub</b> for pet photos attached to posts, and when you choose to post or open a listing there.",
        "<b>Google Maps</b> only when you tap Directions on the map.",
        "<b>GitHub Pages</b>, which hosts the site and, like any web host, keeps server logs of requests.",
    ]
    if ads:
        hosts.append("<b>Google&rsquo;s ad servers</b> (googlesyndication.com and related Google domains) on the "
                     "few pages that carry ads.")
    other = ("<p>When a page opens, your browser also asks these other sites for files, so they see your IP address and browser details "
             "the way any website does:</p><ul class=\"hosts\">" + "".join(f"<li>{h}</li>" for h in hosts) + "</ul>")
    if ads:
        adtext = ("<p>Third-party vendors, including Google, use cookies to serve ads based on your prior visits to "
                  "this website or other websites. Google&rsquo;s use of advertising cookies enables it and its "
                  "partners to serve ads based on your visits to this site and/or other sites on the internet. You can "
                  "opt out of personalized advertising in Google&rsquo;s "
                  f'{ext("https://adssettings.google.com", "Ads Settings", "")} (https://adssettings.google.com), or opt '
                  "out of some third-party vendors&rsquo; cookies at "
                  f'{ext("https://www.aboutads.info", "www.aboutads.info", "")}.</p>'
                  "<p>Visitors in the EEA and UK are asked for consent first.</p>"
                  "<p>Ads appear only on the crime, crash, town and history pages, never on the lost-pets, phone-number, "
                  "calendar or front pages.</p>")
    else:
        adtext = "<p>This site shows no ads and sets no advertising cookies.</p>"
    forget = ("<p>To clear every setting this site has stored on this device, tap the button. It removes each "
              "<code>nk-</code> item from local and session storage.</p>"
              '<p><button type="button" class="btn-line inline" id="forget" hidden>Forget my settings</button></p>'
              '<p class="fine" id="forget-msg" role="status"></p>'
              "<p class=\"fine\">You can also clear them in your browser&rsquo;s settings by deleting this site&rsquo;s data.</p>")
    contact = (f"<p>Questions about this policy? {ext(issues_url(D), 'Open a GitHub issue ›', '')}"
               + (f' or email <a href="mailto:{esc(cfg["contact_email"])}">{esc(cfg["contact_email"])}</a>.'
                  if (cfg.get("contact_email") or "").strip() else "") + "</p>")
    eff = cfg.get("privacy_effective") or D["dates"]["meta"]
    body = (f'<h1>{esc(R.h1)}</h1>' + dateline(f"Effective {fmt.ap_date(eff)}")
            + '<p class="deck">What NK15068 keeps on your device, what your browser sends where, and how ads and cookies '
            "work here.</p>"
            + sec("stored", "What this site stores on your device", stored)
            + sec("location", "Your location", location)
            + sec("posts", "Lost and found posts", posts)
            + sec("hosts", "Other sites your browser contacts", other)
            + sec("ads", "Ads and cookies", adtext)
            + sec("forget", "Forget my settings", forget)
            + sec("questions", "Questions", contact))
    return {"body": f'<div class="page privacy-page">{body}</div>', "crumbs": [("Privacy", None)]}


# --------------------------------------------------------------------------- /contact/


def contact(D, R):
    cfg = D["cfg"]
    iu = issues_url(D)
    email = (cfg.get("contact_email") or "").strip()
    body = (
        f'<h1>{esc(R.h1)}</h1>'
        f'<p class="lede-p">The quickest way to reach NK15068 is a GitHub issue: {ext(iu, esc(iu), "")} (GitHub needs a '
        "free account).</p>"
        + (f'<p class="lede-p">Email: <a href="mailto:{esc(email)}">{esc(email)}</a></p>' if email else "")
        + sec("fix", "Report a correction",
              "<p>Tell us the page, what&rsquo;s wrong and, if you can, a link to a source for the fix. We&rsquo;ll "
              "correct it and note the change on What&rsquo;s new. Please don&rsquo;t include private people&rsquo;s "
              "names or house numbers.</p>"
              f'<p><a class="btn-line inline" href="{esc(correction_url(D))}">Report a correction ›</a></p>')
        + sec("pets", "Lost or found a pet?",
              f'<p>Post it on the <a href="{rel(R, "/lost-pets/")}">lost and found board</a>; it&rsquo;s free, and the '
              "page lists who to call first. We can&rsquo;t take pet reports by message.</p>")
        + sec("urgent", "Emergencies and city services",
              f'<p>For an emergency, call <a class="tel-inline" href="tel:911">911</a>. NK15068 isn&rsquo;t run by the '
              "cities or their police departments and can&rsquo;t pass messages to them. Their numbers are on "
              f'<a href="{rel(R, "/numbers/")}">Phone numbers</a>.</p>'))
    return {"body": f'<div class="page contact-page">{body}</div>', "crumbs": [("Contact", None)]}


# --------------------------------------------------------------------------- /sources/

SOURCE_KEYS = ("source", "source_alt", "sources", "src", "url")


def _walk_urls(obj, out, skip_meta=True):
    if isinstance(obj, dict):
        if obj.get("headline") and fmt.is_aggregator_only(obj.get("source")):
            return  # hidden news briefs aren't cited anywhere on the site
        for k, v in obj.items():
            if skip_meta and k == "_meta":
                continue
            if k in SOURCE_KEYS:
                for u in (v if isinstance(v, list) else [v]):
                    if isinstance(u, str) and u.startswith("http"):
                        out.append(u)
            else:
                _walk_urls(v, out, skip_meta)
    elif isinstance(obj, list):
        for v in obj:
            _walk_urls(v, out, skip_meta)


def outlets(D):
    """[(outlet name, pages cited)] across all research and safety sources (distinct URLs), most cited first."""
    urls = []
    for k in ("civic", "history", "pets", "safety"):
        _walk_urls(D[k], urls)
    c = Counter(P.outlet(u) for u in set(urls) if P.outlet(u))
    return sorted(c.items(), key=lambda kv: (-kv[1], kv[0].lower()))


def sources(D, R):
    m, s = D["meta"], D["safety"]
    lic = "".join(
        f'<li>{ext(x["url"], esc(x["name"]), "")} · {esc(x.get("license", ""))}'
        + (f' · release {esc(x["release"])}' if x.get("release") else "") + "</li>" for x in m.get("sources") or [])
    mapdata = (f'<ul class="src-list" id="src-list">{lic}</ul>'
               f"<p>The map data was built {fmt.ap_date(m['generated'])}: {fmt.num(m['stats']['places'])} places, "
               f"{fmt.num(m['stats']['streets'])} named streets, {fmt.num(m['stats']['buildings'])} buildings and "
               f"{fmt.num(m['stats']['addresses'])} address points. Map data © OpenStreetMap contributors, Overture Maps "
               "Foundation.</p>")
    civ, his, pts = D["civic"], D["history"], D["pets"]
    n_news = len(news_items(D))
    research = (
        "<ul class=\"src-list\">"
        f"<li><b>News briefs, city offices, parks and places to eat:</b> compiled {fmt.ap_date(civ['_meta']['compiled'])}. "
        f"{fmt.num(n_news)} news briefs, {fmt.num(len(civ.get('government') or []))} public offices, "
        f"{fmt.num(len(civ.get('parks_and_rec') or []))} parks and {fmt.num(len(civ.get('food_and_culture') or []))} "
        "places to eat and drink.</li>"
        f"<li><b>History:</b> compiled {fmt.ap_date(his['_meta']['compiled'])}. {fmt.num(len(his.get('timeline') or []))} "
        f"dated events, {fmt.num(len(his.get('neighborhoods') or []))} neighborhoods, "
        f"{fmt.num(len(his.get('landmarks') or []))} landmarks, {fmt.num(len(his.get('events') or []))} yearly events and "
        f"{fmt.num(len(his.get('people') or []))} notable people.</li>"
        f"<li><b>Lost and found pet contacts and tips:</b> checked {fmt.ap_date(pts['compiled'])}. "
        f"{fmt.num(len(pts.get('items') or []))} contacts and {fmt.num(len(pts.get('tips') or []))} tips.</li></ul>"
        "<p>Each entry links to where it was published.</p>")
    fbi = s["fbi"]
    years = sorted({y["year"] for a in fbi["agencies"] for y in a["years"]})
    cst = s["crashes"]["stats"]
    cy = sorted({r["year"] for r in cst})
    wapo = (s.get("policing") or {}).get("wapo_fatal_shootings_in_area") or []
    inc = s.get("incidents") or []
    inc_outlets = Counter(P.outlet(i.get("src")) for i in inc if i.get("src"))
    datasets = (
        "<ul class=\"src-list\">"
        f"<li>{ext(fbi['source'], 'FBI Uniform Crime Reporting figures', '')}, {years[0]}–{years[-1]}, for each "
        "department, as compiled by Jacob Kaplan (crimedatatool_helper): offenses, clearances, arrests and staffing.</li>"
        f"<li>{ext(s['crashes']['source'], 'PennDOT crash records', '')}, {cy[0]}–{cy[-1]}: crashes that killed or "
        f"seriously injured someone, {fmt.num(sum(r['crashes'] for r in cst))} in the three cities.</li>"
        + (f"<li>{ext(wapo[0]['source'], 'The Washington Post&rsquo;s database of fatal police shootings', '')}: "
           f"{fmt.num(len(wapo))} in the three cities.</li>" if wapo else "")
        + f"<li>The police blotter: {fmt.num(len(inc))} incidents from {fmt.num(len(inc_outlets))} news outlets, "
        "each placed on its block, a corner, a named place or just the street, and linked to the report.</li></ul>")
    outs = outlets(D)
    out_html = ('<ul class="outlets">' + "".join(f"<li><b>{esc(n)}</b> {fmt.num(c)}</li>" for n, c in outs) + "</ul>")
    body = (f'<h1>{esc(R.h1)}</h1>'
            + '<p class="deck">Every dataset and outlet NK15068 draws on, with licenses and the dates the research was '
            "compiled.</p>"
            + sec("map-data", "Map data and licenses", mapdata)
            + sec("research", "Research", research)
            + sec("datasets", "Crime, crash and police data", datasets)
            + sec("outlets", "Outlets cited",
                  f"<p>{fmt.num(len(outs))} outlets, agencies and websites, with how many of their pages and articles we "
                  f"cite:</p>{out_html}")
            + f'<p class="fine">See something that needs a better source? <a href="{esc(correction_url(D))}">Report a correction ›</a></p>')
    return {"body": f'<div class="page sources-page">{body}</div>', "crumbs": [("Sources", None)]}


# --------------------------------------------------------------------------- /404.html


def not_found(D, R):
    links = [("/lost-pets/", "Lost pets"), ("/numbers/", "Phone numbers"), ("/calendar/", "Calendar"),
             ("/crime/", "Crime"), ("/map/", "Map"), ("/", "Front page")]
    lis = "".join(f'<li><a class="go" href="{rel(R, p)}">{t} ›</a></li>' for p, t in links)
    form = (f'<form class="sitesearch nf-search" role="search" action="{rel(R, "/search/")}" method="get">'
            '<label for="nfq">Search 15068</label><span class="sf-row">'
            '<input id="nfq" name="q" type="search" placeholder="Street, business, number or topic" autocomplete="off">'
            '<button type="submit">Search</button></span></form>')
    body = (f'<h1>{esc(R.h1)}</h1>'
            '<p class="deck">NK15068 recently moved its sections onto their own pages. Try one of these, or search below.</p>'
            f'<ul class="nf-links">{lis}</ul>{form}')
    return {"body": f'<div class="page nf-page">{body}</div>'}
