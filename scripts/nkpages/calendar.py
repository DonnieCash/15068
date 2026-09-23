"""What's coming up in 15068: every dated or yearly item the research data gives, as one sorted list.

Four kinds of item, each from a research field (spec section 3, /calendar/, and section 7 step 1):
- explicit  history.events[*].dates   dates the organizers announced (Fridays on Fifth)
- rule      civic.government[*].council  a regular schedule ("2nd Tuesday", 7 p.m.), always marked expected
- deadline  civic.news_2025_2026[*].deadline  the last day to comment (title = the news headline, what = "Last day for
            comments")
- when      history.events[*].when for events without dates: yearly events, sorted by typical month

Once an explicit event's last date has passed it becomes a `when` item with "{year} dates not announced yet."
Only explicit and deadline items get .ics files and Event JSON-LD (never a date derived from a rule).
"""
import datetime as dt
import re

from . import fmt
from .data import CORE_TOWNS

RULE_DAYS = 185        # how far ahead a schedule rule is expanded (home keeps 3 rows + 6 spare in a template)
WINDOW = 90            # the calendar page's "Coming up" reach
WEEKDAYS = ["monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday"]
ORDINALS = {"1st": 1, "first": 1, "2nd": 2, "second": 2, "3rd": 3, "third": 3, "4th": 4, "fourth": 4,
            "5th": 5, "fifth": 5, "last": -1}
ORD_WORD = {1: "first", 2: "second", 3: "third", 4: "fourth", 5: "fifth", -1: "last"}
MONTHS = ["january", "february", "march", "april", "may", "june", "july", "august", "september", "october",
          "november", "december"]
SEASONS = {"winter": 1, "spring": 4, "summer": 6, "fall": 10, "autumn": 10}


# --------------------------------------------------------------------------- dates and times


def nth_weekday(y, m, n, wd):
    """The nth weekday `wd` (0 = Monday) of month m in year y; n = -1 is the last one. None if there is no such day
    (a 5th Tuesday in a month with four)."""
    if n == -1:
        last = (dt.date(y + (m == 12), m % 12 + 1, 1) - dt.timedelta(days=1))
        return last - dt.timedelta(days=(last.weekday() - wd) % 7)
    first = dt.date(y, m, 1)
    d = first + dt.timedelta(days=(wd - first.weekday()) % 7 + 7 * (n - 1))
    return d if d.month == m else None


def parse_rule(rule):
    """'2nd Tuesday' -> (2, 1); None when the rule isn't a monthly nth-weekday rule."""
    m = re.match(r"^\s*(\w+)\s+(\w+?)s?\s*$", str(rule or "").lower())
    if not m or m.group(1) not in ORDINALS or m.group(2) not in WEEKDAYS:
        return None
    return ORDINALS[m.group(1)], WEEKDAYS.index(m.group(2))


def rule_words(rule):
    """'2nd Tuesday' -> 'second Tuesday'"""
    p = parse_rule(rule)
    return f"{ORD_WORD[p[0]]} {WEEKDAYS[p[1]].capitalize()}" if p else str(rule or "")


def rule_dates(rule, start, end):
    p = parse_rule(rule)
    if not p:
        return []
    out, y, m = [], start.year, start.month
    while dt.date(y, m, 1) <= end:
        d = nth_weekday(y, m, *p)
        if d and start <= d <= end:
            out.append(d)
        y, m = (y + 1, 1) if m == 12 else (y, m + 1)
    return out


_CLOCK = re.compile(r"(noon)|(\d{1,2})(?::(\d{2}))?\s*([ap])?\.?\s*m?\.?", re.I)


def _clock(part):
    """'5' -> (5, 0, None); '4:30 p.m.' -> (16, 30, 'p'); 'noon' -> (12, 0, 'p')"""
    m = _CLOCK.search(part or "")
    if not m:
        return None
    if m.group(1):
        return 12, 0, "p"
    return int(m.group(2)), int(m.group(3) or 0), (m.group(4) or "").lower() or None


def _h24(h, suf):
    return h % 12 + (12 if suf == "p" else 0)


def parse_time(s):
    """'5–9 p.m.' -> ((17, 0), (21, 0)); '7 p.m.' -> ((19, 0), None); '' -> (None, None).
    A start without a.m./p.m. takes the end's, unless that would put it after the end."""
    s = str(s or "").strip()
    if not s:
        return None, None
    parts = re.split(r"\s*(?:–|-|—|\bto\b)\s*", s, maxsplit=1)
    a = _clock(parts[0])
    b = _clock(parts[1]) if len(parts) > 1 else None
    if not a:
        return None, None
    if b is None:
        return ((_h24(a[0], a[2] or "p"), a[1]), None)
    end = (_h24(b[0], b[2] or "p"), b[1])
    suf = a[2] or b[2] or "p"
    start = (_h24(a[0], suf), a[1])
    if not a[2] and start > end:
        start = (_h24(a[0], "a"), a[1])
    return start, end


def rel_day(d, today):
    """Python twin of NKS.relDay: 'Today', 'Tomorrow', 'This Friday' (2-6 days out), else ''."""
    n = (d - today).days
    if n == 0:
        return "Today"
    if n == 1:
        return "Tomorrow"
    if 1 < n < 7:
        return "This " + fmt.DAYS[d.weekday()]
    return ""


def month_of(when):
    """Typical month (1-12) of a free-text `when`: the first month named, else the season ('Summer' is June);
    13 when neither is there."""
    t = str(when or "").lower()
    hits = [(t.find(m), i + 1) for i, m in enumerate(MONTHS) if re.search(rf"\b{m}\b", t)]
    hits += [(t.find(m[:3] + "."), i + 1) for i, m in enumerate(MONTHS) if re.search(rf"\b{m[:3]}\.", t)]
    if hits:
        return min(hits)[1]
    for s, mo in SEASONS.items():
        if re.search(rf"\b{s}\b", t):
            return mo
    return 13


# --------------------------------------------------------------------------- where things are


def ap_addr(a):
    """AP street address: '1829 Fifth Ave, Arnold, PA 15068' -> '1829 Fifth Ave.'; Road, Drive and the rest are
    spelled out ('1021 Puckety Church Rd' -> '1021 Puckety Church Road'). Only Ave., Blvd. and St. are abbreviated."""
    s = str(a or "").split(",")[0].strip()
    if not re.match(r"^\d", s):
        return s
    full = {"Rd": "Road", "Dr": "Drive", "Ln": "Lane", "Ct": "Court", "Pl": "Place", "Ter": "Terrace", "Aly": "Alley"}
    s = re.sub(r"\b(Rd|Dr|Ln|Ct|Pl|Ter|Aly)\.?$", lambda m: full[m.group(1)], s)
    s = re.sub(r"\b(Avenue|Ave)\.?$", "Ave.", s)
    s = re.sub(r"\b(Boulevard|Blvd)\.?$", "Blvd.", s)
    s = re.sub(r"\b(Street|St)\.?$", "St.", s)
    return s


def town_in(text):
    return next((t for t in CORE_TOWNS if t in str(text or "")), None)


# --------------------------------------------------------------------------- the items


def _first_sentence(t):
    m = re.match(r"^(.+?[.!?])\s+[A-Z]", t)
    return m.group(1) if m else t


def _explicit(e, today):
    """[item] for each announced date still ahead; [] when every date has passed (see _when)."""
    days = sorted(dt.date.fromisoformat(d) for d in e.get("dates") or [])
    ahead = [d for d in days if d >= today]
    text = fmt.public(e.get("text"))
    out = []
    for i, d in enumerate(ahead):
        t = e.get("time") or ""
        out.append({
            "date": d.isoformat(), "time": t, "title": e["name"], "where": fmt.public(e.get("where")),
            "text": text if i == 0 else _first_sentence(text), "source": e.get("source"), "kind": "explicit",
            "label": ", ".join(x for x in (fmt.ap_day(d), t) if x), "sort": 0,
        })
    return out


def _when(e):
    """A yearly event known only by its `when` text. An explicit event whose dates are all past lands here too,
    with '{next year} dates not announced yet.'"""
    text = fmt.public(e.get("text"))
    days = sorted(e.get("dates") or [])
    if days:
        nxt = int(days[-1][:4]) + 1
        text = fmt.end_stop(text) + f" {nxt} dates not announced yet." if text else f"{nxt} dates not announced yet."
    when = fmt.public(e.get("when"))
    return {"date": None, "time": e.get("time") or "", "title": e["name"], "where": fmt.public(e.get("where")),
            "text": text, "source": e.get("source"), "kind": "when", "label": when, "when": when,
            "month": month_of(e.get("when"))}


def _rules(g, today):
    c = g.get("council") or {}
    town = town_in(g.get("name")) or town_in(g.get("address"))
    if not c.get("rule") or not town:
        return []
    end = today + dt.timedelta(days=RULE_DAYS)
    place = str(g.get("name", "")).split(" – ")[-1].strip()
    where = ", ".join(x for x in (place, ap_addr(g.get("address"))) if x)
    t = c.get("time") or ""
    text = (fmt.end_stop(f"{town} City Council meets the {rule_words(c['rule'])} of each month" + (f" at {t}" if t else ""))
            + " This date follows that schedule, so check the city's website before you go.")
    return [{"date": d.isoformat(), "time": t, "title": f"{town} City Council", "where": where, "text": text,
             "source": c.get("source") or g.get("url"), "kind": "rule", "town": town, "rule": c["rule"],
             "label": ", ".join(x for x in (fmt.ap_day(d), t) if x) + " (expected)", "sort": 2}
            for d in rule_dates(c["rule"], today, end)]


def _deadlines(n, today):
    if not n.get("deadline") or fmt.is_aggregator_only(n.get("source")):
        return []
    d = dt.date.fromisoformat(n["deadline"])
    if d < today:
        return []
    h = fmt.host(n.get("source"))  # comments go in through the source page, credited on /calendar/
    return [{"date": d.isoformat(), "time": "", "title": fmt.public(n["headline"]), "what": "Last day for comments",
             "where": "Online" if h else "", "text": fmt.public(n.get("text")), "source": n.get("source"),
             "kind": "deadline", "label": "Comments due " + fmt.ap_day(d), "sort": 1,
             "slug": f"comments-due-{d.isoformat()}"}]


def occurrences(D, today):
    """Every item, dated ones first by date (then explicit, deadline, rule), then yearly ones by typical month
    starting from this month. Each item: {date (ISO or None), time, title, where, text, source, kind, id, label}."""
    today = today if isinstance(today, dt.date) else dt.date.fromisoformat(str(today))
    dated, yearly = [], []
    for e in D["history"].get("events") or []:
        if e.get("dates"):
            got = _explicit(e, today)
            if got:
                dated += got
            else:
                yearly.append(_when(e))
        elif e.get("when"):
            yearly.append(_when(e))
    for g in D["civic"].get("government") or []:
        dated += _rules(g, today)
    for n in D["civic"].get("news_2025_2026") or []:
        dated += _deadlines(n, today)
    dated.sort(key=lambda i: (i["date"], i["sort"], i["title"]))
    yearly.sort(key=lambda i: ((i["month"] - today.month) % 12 if i["month"] <= 12 else 12, i["month"]))
    seen, out = {}, []
    for it in dated + yearly:
        base = it.get("slug") or fmt.slug(it["title"])[:60].strip("-") or "item"
        iid = base if base not in seen else f"{base}-{it['date'] or seen[base] + 1}"
        seen[base] = seen.get(base, 0) + 1
        it = {k: v for k, v in it.items() if k not in ("sort", "slug")}
        it["id"] = iid
        out.append(it)
    return out


def dated(items):
    return [i for i in items if i["date"]]


def next_rule(D, today, town):
    """The next expected council date for a town (a date) or None."""
    return next((dt.date.fromisoformat(i["date"]) for i in occurrences(D, today)
                 if i["kind"] == "rule" and i.get("town") == town), None)


# --------------------------------------------------------------------------- .ics data and JSON-LD


def ics_data(it):
    """What the device needs to build an .ics file: floating local times for timed items, an all-day date otherwise.
    None for rule and yearly items."""
    if it["kind"] not in ("explicit", "deadline") or not it["date"]:
        return None
    d = dt.date.fromisoformat(it["date"])
    start, end = parse_time(it.get("time")) if it["kind"] == "explicit" else (None, None)
    t = f"{it['what']}: {it['title']}" if it.get("what") else it["title"]
    out = {"t": t, "w": it.get("where") or "", "x": it.get("text") or "", "id": it["id"]}
    if start:
        s = dt.datetime(d.year, d.month, d.day, *start)
        e = dt.datetime(d.year, d.month, d.day, *end) if end else s + dt.timedelta(hours=1)
        out["s"], out["e"] = s.strftime("%Y%m%dT%H%M%S"), e.strftime("%Y%m%dT%H%M%S")
    else:
        out["d"] = d.strftime("%Y%m%d")
        out["e"] = (d + dt.timedelta(days=1)).strftime("%Y%m%d")
    return out


def _eastern_offset(d):
    """'-04:00' or '-05:00' for a date in America/New_York."""
    try:
        from zoneinfo import ZoneInfo
        off = dt.datetime(d.year, d.month, d.day, 12, tzinfo=ZoneInfo("America/New_York")).utcoffset()
    except Exception:
        mar = nth_weekday(d.year, 3, 2, 6)
        nov = nth_weekday(d.year, 11, 1, 6)
        off = dt.timedelta(hours=-4 if mar <= d < nov else -5)
    h = int(off.total_seconds() // 3600)
    return f"{'-' if h < 0 else '+'}{abs(h):02d}:00"


def event_jsonld(it, url):
    """schema.org Event for an explicit or deadline item (never a rule date)."""
    d = dt.date.fromisoformat(it["date"])
    name = f"{it['what']}: {it['title']}" if it.get("what") else it["title"]
    ev = {"@context": "https://schema.org", "@type": "Event", "name": name, "url": url,
          "description": it.get("text") or it["title"], "eventStatus": "https://schema.org/EventScheduled"}
    start, end = parse_time(it.get("time")) if it["kind"] == "explicit" else (None, None)
    if start:
        off = _eastern_offset(d)
        ev["startDate"] = f"{d.isoformat()}T{start[0]:02d}:{start[1]:02d}:00{off}"
        if end:
            ev["endDate"] = f"{d.isoformat()}T{end[0]:02d}:{end[1]:02d}:00{off}"
    else:
        ev["startDate"] = d.isoformat()
    if it["kind"] == "deadline":
        ev["eventAttendanceMode"] = "https://schema.org/OnlineEventAttendanceMode"
        ev["location"] = {"@type": "VirtualLocation", "url": it.get("source")}
    else:
        ev["eventAttendanceMode"] = "https://schema.org/OfflineEventAttendanceMode"
        addr = {"@type": "PostalAddress", "addressRegion": "PA", "postalCode": "15068", "addressCountry": "US"}
        t = town_in(it.get("where"))
        if t:
            addr["addressLocality"] = t
        ev["location"] = {"@type": "Place", "name": it.get("where") or "ZIP 15068", "address": addr}
    return ev
