"""The front page (/), the phone numbers (/numbers/) and the calendar (/calendar/).

Every number is computed from the data at build time: the calendar from nkpages.calendar, the crime lead from
nkpages.sentences, the pets box from nkpages.pets, phone numbers from civic.json, pets.json and places.json.
Research text passes through fmt.public(); every row credits its outlet by name.

Other builders call: numbers_rows(D) (search.json). News anchors come from pages_towns.news_items().
"""
import datetime as dt
import json
import re

from . import calendar as C
from . import fmt
from . import pets as P
from . import sentences as S
from .data import CORE_TOWNS, TOWN_SLUGS, updated
from .fmt import esc
from .shell import rel, site_url

OVERTURE = "https://overturemaps.org"
GAP_LINE = "Trash, recycling, potholes and snow: we don't have public-works numbers yet. Call your city hall."


# --------------------------------------------------------------------------- credits and small pieces


def outlet(u):
    return fmt.pub_name(u)


def credit(urls, pre="Source: "):
    """fmt.credit() with the civic and pets outlets named."""
    seen, out = set(), []
    for u in ([urls] if isinstance(urls, str) else urls or []):
        n = outlet(u) if u else ""
        if not n or n in seen:
            continue
        seen.add(n)
        out.append(f'<a class="cr" href="{esc(u)}" target="_blank" rel="noopener">{esc(n)}</a>')
    return (pre + ", ".join(out)) if out else ""


def credit_line(urls, pre="Source: ", cls="credit"):
    c = credit(urls, pre)
    return f'<p class="{cls}">{c}</p>' if c else ""


def tel_a(shown, cls="tel", label=None, attrs=""):
    t = fmt.tel(shown)
    if not t:
        return ""
    return f'<a class="{cls}" href="{t[0][1]}"{attrs}>{label if label is not None else esc(t[0][0])}</a>'


def phones(text):
    return [shown for shown, _ in fmt.tel(text)]


def city_of(address):
    """'2674 Monroeville Blvd, Monroeville, PA 15146' -> 'Monroeville'; '2 North Main Street, Suite 110, Greensburg,
    PA 15601' -> 'Greensburg' (the part before the state and ZIP)."""
    parts = [p.strip() for p in str(address or "").split(",")]
    i = next((i for i, p in enumerate(parts) if re.match(r"^[A-Z]{2}\s+\d{5}", p)), None)
    return parts[i - 1] if i and i >= 2 else ""


def news_id(n):
    """The /news/ anchor of a news brief: the id pages_towns gave it, else 'n-' + the headline's slug."""
    return n.get("id") or "n-" + fmt.slug(n.get("headline"))


def news_items(D):
    """News briefs newest first, without the aggregator-only ones, from pages_towns.news_items() (which owns the
    /news/ ids) when that module is there."""
    try:
        from . import pages_towns
        return pages_towns.news_items(D)
    except (ImportError, AttributeError):
        items = [n for n in D["civic"].get("news_2025_2026") or [] if not fmt.is_aggregator_only(n.get("source"))]
        return sorted(items, key=lambda n: str(n.get("date")), reverse=True)


# --------------------------------------------------------------------------- the phone numbers


def _gov(D, pat):
    return next((g for g in D["civic"].get("government") or [] if re.search(pat, g.get("name", ""), re.I)), None)


def _pet(D, pat, kind=None):
    return next((i for i in D["pets"].get("items") or []
                 if re.search(pat, i.get("name", ""), re.I) and (kind is None or i.get("kind") == kind)), None)


def _place(D, pat):
    return next((p for p in D["places"] or [] if re.search(pat, p.get("n", ""), re.I) and p.get("ph")), None)


DAY_AP = {"m": "Mon.", "mon": "Mon.", "tu": "Tues.", "tue": "Tues.", "tues": "Tues.", "w": "Wed.", "wed": "Wed.",
          "th": "Thurs.", "thu": "Thurs.", "thurs": "Thurs.", "f": "Fri.", "fri": "Fri.", "sa": "Sat.", "sat": "Sat.",
          "su": "Sun.", "sun": "Sun."}


def ap_hours(s):
    """'M–F 8:30–4:30, Sat 9:30–1' -> 'Mon.–Fri. 8:30 a.m.–4:30 p.m., Sat. 9:30 a.m.–1 p.m.' (office hours: 7-11 are
    morning, 12 and 1-6 afternoon). None when the text isn't in that shape."""
    out = []
    for seg in str(s or "").split(","):
        m = re.match(r"^\s*([A-Za-z]+)(?:\s*[–-]\s*([A-Za-z]+))?\s+(\d{1,2})(?::(\d\d))?\s*[–-]\s*(\d{1,2})(?::(\d\d))?\s*$", seg)
        if not m:
            return None
        d1, d2 = DAY_AP.get(m.group(1).lower()), DAY_AP.get((m.group(2) or "").lower())
        if not d1 or (m.group(2) and not d2):
            return None
        t = []
        for h, mi in ((m.group(3), m.group(4)), (m.group(5), m.group(6))):
            h = int(h)
            t.append(fmt.ap_time(dt.time(h if 7 <= h <= 12 else h + 12 if h <= 6 else h, int(mi or 0))))
        out.append(f"{d1}{'–' + d2 if d2 else ''} {t[0]}–{t[1]}")
    return ", ".join(out) or None


def _row(sec, label, full, *, ph=(), a="", note="", w=None, wl=None, source=None, k="", note_html=None):
    return {"sec": sec, "label": label, "n": full, "ph": list(ph), "a": a, "note": note, "note_html": note_html,
            "w": w, "wl": wl, "source": source, "k": k}


def _police(D, town, sec):
    nums = S.police_numbers(D).get(town)
    item = _pet(D, "^" + re.escape(town), "police")
    if not nums:
        return None
    return _row(sec, "Police non-emergency", f"{town} police, non-emergency", ph=[nums["primary"], *nums["alt"]],
                a=C.ap_addr(item.get("address")) if item else "", source=nums["source"], k="police cops non-emergency stray loose dog lost pet")


def _office(D, pat, sec, label, full, k, note="", web_label=None):
    g = _gov(D, pat)
    if not g:
        return None
    a = C.ap_addr(g.get("address"))
    return _row(sec, label, full, ph=phones(g.get("phone")), a=a, note=note, source=g.get("url"),
                w=g.get("url") if web_label else None, wl=web_label, k=k)


def _pets_row(D, pat, sec, label, full, k, note="", kind=None):
    it = _pet(D, pat, kind)
    if not it or not it.get("phone"):
        return None
    a = C.ap_addr(it.get("address")) if re.match(r"^\d", str(it.get("address") or "")) else ""
    city = city_of(it.get("address"))
    a = ", ".join(x for x in (a, city) if x)
    return _row(sec, label, full, ph=phones(it["phone"])[:1], a=a, note=note, source=it.get("source"), k=k)


def _grades(role):
    m = re.search(r"grades?\s+\d+\s*[–-]\s*\d+", str(role or ""), re.I)
    return fmt.cap(m.group(0).replace("-", "–")) if m else ""


def _all_rows(D):
    """Every row on /numbers/, in page order, with the page-only fields (label, address, note, website)."""
    if "_numbers" in D:
        return D["_numbers"]
    rows = []
    add = lambda r: r and rows.append(r)
    hall_k = "city hall mayor council municipal building borough building trash garbage recycling pothole potholes snow"
    for town in CORE_TOWNS:
        sec = TOWN_SLUGS[town]
        pat = rf"^City of {re.escape(town)} – City Hall"
        g = _gov(D, pat)
        wl = ("Contact page ›" if g and "contact" in str(g.get("url")).lower() else "City website ›")
        add(_office(D, pat, sec, "City hall", f"{town} City Hall", hall_k, web_label=wl))
        add(_police(D, town, sec))
        if town == "New Kensington":
            add(_office(D, r"^Peoples Library – New Kensington", sec, "Peoples Library", "Peoples Library, New Kensington",
                        "library books"))
            add(_office(D, r"Parks & Recreation", sec, "Parks and recreation (Memorial Park)",
                        "New Kensington parks and recreation (Memorial Park)", "parks recreation memorial park pool"))
            po = _gov(D, r"Post Office")
            hours = ap_hours((re.search(r"\(([^()]*)\)", po.get("role", "")) or [None, ""])[1]) if po else None
            add(_office(D, r"Post Office", sec, "Post office", "New Kensington post office", "post office mail usps",
                        note=hours or ""))
            add(_office(D, r"^Redevelopment Authority", sec, "Redevelopment Authority",
                        "Redevelopment Authority of the City of New Kensington", "redevelopment downtown",
                        web_label="Website ›"))
            hs = _gov(D, r"^Valley Junior/Senior High")
            dist = _gov(D, r"^New Kensington-Arnold School District")
            note = ", ".join(x for x in (_grades(hs and hs.get("role")), dist and dist["name"]) if x)
            add(_office(D, r"^Valley Junior/Senior High", sec, "Valley Junior/Senior High School",
                        "Valley Junior/Senior High School", "school high school valley nkasd", note=note))
        c = (g or {}).get("council")
        if c and C.parse_rule(c.get("rule")):
            nxt = C.next_rule(D, D["today"], town)
            words = C.rule_words(c["rule"])
            note = f"{fmt.cap(words)} of the month" + (f", {c['time']}" if c.get("time") else "")
            nh = esc(note)
            if nxt:
                note += f" · Next expected: {fmt.ap_long(nxt, year=False)}"
                nh += f' · <a href="{{cal}}#{esc(slug_of_rule(D, town))}">Next expected: {esc(fmt.ap_long(nxt, year=False))}</a>'
            add(_row(sec, "Council", f"{town} City Council meetings", note=note, note_html=nh, source=c.get("source"),
                     k="council meeting city council"))
        if town == "Lower Burrell":
            add(_pets_row(D, r"^Hoffman Kennels", sec, "Animal control (Hoffman Kennels)",
                          "Lower Burrell animal control (Hoffman Kennels)", "animal control dog catcher stray loose dog",
                          note="The city's animal control officer, weekdays"))
            add(_office(D, r"^Burrell School District", sec, "Burrell School District", "Burrell School District",
                        "school district burrell"))
            lib = _gov(D, r"^Peoples Library – Lower Burrell")
            if lib:
                add(_row(sec, "Peoples Library, Lower Burrell branch", "Peoples Library, Lower Burrell branch",
                         a=C.ap_addr(lib.get("address")), ph=phones(lib.get("phone")), w=lib.get("url"), wl="website ›",
                         source=lib.get("url"), k="library books"))
    sec = "county"
    add(_pets_row(D, r"County Public Safety", sec, "County non-emergency line",
                  "Westmoreland County non-emergency line",
                  "police non-emergency after hours county 911 center dispatch",
                  note="Westmoreland County's 911 center. Call after hours when you can't reach local police.",
                  kind="police"))
    add(_pets_row(D, r"^Animal Protectors", sec, "Animal Protectors", "Animal Protectors of Allegheny Valley",
                  "animal shelter lost pet found pet dog cat", note="The animal shelter in town", kind="shelter"))
    add(_pets_row(D, r"^Humane Society", sec, "Humane Society of Westmoreland County",
                  "Humane Society of Westmoreland County", "humane society animal shelter lost pet"))
    add(_pets_row(D, r"Treasurer, dog licenses", sec, "Dog licenses (County Treasurer)",
                  "Dog licenses (Westmoreland County Treasurer)", "dog license tag treasurer"))
    add(_pets_row(D, r"Region 4 office", sec, "State dog law office", "State dog law office (PA Dept. of Agriculture)",
                  "dog warden dog law state", note="PA Dept. of Agriculture, weekdays 8 a.m.–4 p.m."))
    add(_pets_row(D, r"^AVETS", sec, "AVETS emergency vet", "AVETS emergency vet",
                  "emergency vet veterinarian injured pet animal hospital", note="Open 24 hours"))
    add(_pets_row(D, r"^BluePearl", sec, "BluePearl Pittsburgh North", "BluePearl Pet Hospital Pittsburgh North",
                  "emergency vet veterinarian injured pet animal hospital",
                  note="24-hour emergency vet in Pittsburgh's North Hills"))
    y = _place(D, r"^Valley Points Family YMCA$")
    if y:
        name = re.sub(r"\bYmca\b", "YMCA", y["n"])
        add(_row(sec, name, name, ph=phones(y["ph"]), a=", ".join(x for x in (C.ap_addr(y.get("a")), y.get("t")) if x),
                 w=y.get("w"), wl="Website ›", source=OVERTURE, k="ymca gym pool fitness swim"))
    D["_numbers"] = rows
    return rows


def slug_of_rule(D, town):
    return next((i["id"] for i in C.occurrences(D, D["today"]) if i["kind"] == "rule" and i.get("town") == town), "")


SECTIONS = [(TOWN_SLUGS[t], t, t) for t in CORE_TOWNS] + [("county", "County and animals", "County")]


def numbers_rows(D):
    """Every row on /numbers/ for search.json: [{n, t (town or "County"), ph, u, k, source, a, w}]."""
    town = {s: t for s, _, t in SECTIONS}
    return [{"n": r["n"], "t": town[r["sec"]], "ph": r["ph"], "u": f"numbers/#{r['sec']}", "k": r["k"],
             "source": r["source"], "a": r["a"], "w": r["w"]} for r in _all_rows(D)]


# --------------------------------------------------------------------------- /numbers/


def _nrow(R, r):
    if r["ph"]:
        calls = tel_a(r["ph"][0]) + "".join(
            f'<span class="tel-alt">or {tel_a(p, cls="alt")}</span>' for p in r["ph"][1:])
    elif r["label"] != "Council":
        calls = (f'<span class="nr-none">No public number listed'
                 + (f' · <a href="{esc(r["w"])}" target="_blank" rel="noopener">{esc(r["wl"])}</a>' if r.get("w") else "")
                 + "</span>")
    else:
        calls = ""
    note = (r["note_html"] or esc(r["note"])).replace("{cal}", rel(R, "/calendar/"))
    web = (f'<a href="{esc(r["w"])}" target="_blank" rel="noopener">{esc(r["wl"])}</a> · '
           if r.get("w") and r["ph"] else "")
    t = (f'<b class="nr-n">{esc(r["label"])}</b>'
         + (f'<span class="nr-a">{esc(r["a"])}</span>' if r["a"] else "")
         + (f'<span class="nr-note">{note}</span>' if note else ""))
    return (f'<li class="nrow"><div class="nr-t">{t}</div>'
            + (f'<div class="nr-c">{calls}</div>' if calls else "")
            + f'<p class="nr-x">{web}{credit(r["source"])}</p></li>')


def numbers(D, R):
    rows = _all_rows(D)
    cards = []
    for sid, title, town in SECTIONS:
        mine = [r for r in rows if r["sec"] == sid]
        if not mine:
            continue
        dt_attr = f' data-town="{esc(town)}"' if town in CORE_TOWNS else ""
        cards.append(f'<section class="ncard" id="{sid}"{dt_attr} aria-labelledby="{sid}-h">'
                     f'<h2 id="{sid}-h">{esc(title)}</h2><ul class="nrows">'
                     + "".join(_nrow(R, r) for r in mine) + "</ul></section>")
    picker = "".join(f'<button type="button" data-town="{esc(t)}" aria-pressed="false">{esc(t or "All")}</button>'
                     for t in ("",) + CORE_TOWNS)
    body = (f'<div class="page numbers-page">'
            f'<h1>{esc(R.h1)}</h1>'
            f'<p class="dateline">Checked {fmt.ap_date(updated(D, R.dates))}</p>'
            '<p class="deck">Tap a number to call.</p>'
            '<div class="nine11" data-keep-above><p class="n9-t">Emergency? Call 911</p>'
            '<a class="tel primary" href="tel:911">Call 911</a></div>'
            '<div class="ntools" id="ntools" hidden><p class="nt-l" id="nt-l">Put your town first</p>'
            f'<div class="picker" role="group" aria-labelledby="nt-l">{picker}</div>'
            '<button type="button" class="linkbtn" id="n-remember" hidden>Remember my town</button></div>'
            f'<div class="ncards" id="ncards">{"".join(cards)}</div>'
            f'<p class="gapline">{esc(GAP_LINE)}</p>'
            '<p class="n-print"><button type="button" class="btn-line inline" id="n-print" hidden>Print this list</button></p>'
            '</div>')
    return {"body": body}


# --------------------------------------------------------------------------- calendar rows (home and /calendar/)


def _date_col(it, today):
    d = dt.date.fromisoformat(it["date"])
    return (f'<p class="cal-d"><time datetime="{it["date"]}">{fmt.ap_day(d)}</time>'
            f'<span class="cal-rel" data-rel-day="{it["date"]}">{C.rel_day(d, today)}</span></p>')


def _meta(it):
    first = it.get("what") or it.get("time")
    return " · ".join(esc(x) for x in (first, it.get("where")) if x)


def _exp(it):
    return ' <span class="exp">(expected)</span>' if it["kind"] == "rule" else ""


def home_row(it, R, today, anchor=None):
    """One compact row on the front page: date column, title linking to calendar/#id, time and where.
    `anchor` overrides the link target when /calendar/ doesn't list this occurrence (see _week)."""
    return (f'<li class="cal-row" data-date="{it["date"]}" data-id="{esc(it["id"])}">{_date_col(it, today)}'
            f'<div class="cal-t"><a href="{rel(R, "/calendar/")}#{esc(anchor or it["id"])}">{esc(it["title"])}</a>{_exp(it)}'
            f'<span class="cal-m">{_meta(it)}</span></div></li>')


def cal_item(it, R, today):
    ics = C.ics_data(it)
    btn = (f'<p class="cal-acts"><button type="button" class="linkbtn" data-ics="{esc(json.dumps(ics, ensure_ascii=False))}" '
           f'hidden>Add to calendar</button></p>') if ics else ""
    body = (f'<h3>{esc(it["title"])}{_exp(it)}</h3>'
            + (f'<p class="cal-m">{_meta(it)}</p>' if _meta(it) else "")
            + (f'<p class="cal-x">{esc(it["text"])}</p>' if it.get("text") else "")
            + credit_line(it.get("source")) + btn)
    if it["date"]:
        return (f'<article class="cal-item" id="{esc(it["id"])}" data-date="{it["date"]}" data-kind="{it["kind"]}">'
                f'{_date_col(it, today)}<div class="cal-b">{body}</div></article>')
    return (f'<article class="cal-item yearly" id="{esc(it["id"])}" data-kind="when">'
            f'<p class="cal-when">{esc(it["when"])}</p><div class="cal-b">{body}</div></article>')


def groups(items, today):
    """[(id, title, [items])] for /calendar/: Next 7 days, Later this month, Coming up, Every year (empty ones out)."""
    week_end = today + dt.timedelta(days=6)
    reach = today + dt.timedelta(days=C.WINDOW)
    g = {"next-7-days": [], "later-this-month": [], "coming-up": [], "every-year": []}
    seen_explicit = set()
    for it in items:
        if not it["date"]:
            g["every-year"].append(it)
            continue
        d = dt.date.fromisoformat(it["date"])
        if d <= week_end:
            g["next-7-days"].append(it)
        elif (d.year, d.month) == (today.year, today.month):
            g["later-this-month"].append(it)
        elif d <= reach or (it["kind"] == "explicit" and it["title"] not in seen_explicit):
            g["coming-up"].append(it)
        else:
            continue
        if it["kind"] == "explicit":
            seen_explicit.add(it["title"])
    titles = {"next-7-days": "Next 7 days", "later-this-month": "Later this month", "coming-up": "Coming up",
              "every-year": "Every year"}
    return [(k, titles[k], v) for k, v in g.items() if v]


def _meetings(D, R, today):
    """The Public meetings group: each rule we have, then the towns whose meeting nights aren't in the data."""
    have, srcs, lines = [], [], []
    for g in D["civic"].get("government") or []:
        c = g.get("council") or {}
        town = C.town_in(g.get("name"))
        if not town or not C.parse_rule(c.get("rule")) or not re.search(r"City Hall", g.get("name", "")):
            continue
        have.append(town)
        nxt = C.next_rule(D, today, town)
        s = esc(fmt.end_stop(f"{town} City Council meets the {C.rule_words(c['rule'])} of each month"
                             + (f" at {c['time']}" if c.get("time") else "")))
        if nxt:
            s += (f' The next expected meeting is <a href="#{esc(slug_of_rule(D, town))}">'
                  f'{esc(fmt.ap_long(nxt, year=False))}</a>.')
        lines.append(f'<p class="cal-x">{s}</p>' + credit_line(c.get("source") or g.get("url")))
    missing = [t for t in CORE_TOWNS if t not in have]
    if missing:
        links = []
        for t in missing:
            g = _gov(D, rf"^City of {re.escape(t)} – City Hall")
            if g and g.get("url"):
                m = re.match(r"^(https?://[^/]+)", g["url"])
                links.append(f'<a href="{esc(m.group(1) + "/")}" target="_blank" rel="noopener">City of {esc(t)} ›</a>')
        lines.append(f'<p class="cal-x">{esc(S.join_and(missing))} council nights aren&rsquo;t in our data yet. '
                     + " · ".join(links) + "</p>")
    return "".join(lines)


def calendar(D, R):
    today = D["today"]
    items = C.occurrences(D, today)
    su = site_url(D)
    secs, ld = [], []
    for gid, title, its in groups(items, today):
        secs.append(f'<section class="sec cal-group" id="{gid}" aria-labelledby="{gid}-h"><h2 id="{gid}-h">{title}</h2>'
                    + "".join(cal_item(i, R, today) for i in its) + "</section>")
        ld += [C.event_jsonld(i, f"{su}{R.path}#{i['id']}") for i in its if i["kind"] in ("explicit", "deadline")]
    secs.append('<section class="sec cal-group" id="public-meetings" aria-labelledby="public-meetings-h">'
                f'<h2 id="public-meetings-h">Public meetings</h2>{_meetings(D, R, today)}</section>')
    body = (f'<div class="page calendar-page"><h1>{esc(R.h1)}</h1>'
            f'<p class="dateline">As of {fmt.ap_long(today)}. Dates marked expected follow a regular schedule; '
            f'check before you go.</p>{"".join(secs)}</div>')
    return {"body": body, "jsonld": ld}


# --------------------------------------------------------------------------- the front page


def _week(D, R, items):
    today = D["today"]
    rows = C.dated(items)
    first, spare = rows[:3], rows[3:9]
    # spare rows can lie past the calendar page's reach: link those to the event's first listed date there
    shown = [i for _, _, its in groups(items, today) for i in its]
    ids = {i["id"] for i in shown}
    by_title = {}
    for i in shown:
        by_title.setdefault(i["title"], i["id"])
    target = lambda i: i["id"] if i["id"] in ids else by_title.get(i["title"], "")
    lis = "".join(home_row(i, R, today) for i in first) or \
        '<li class="cal-none">Nothing dated on the calendar right now.</li>'
    return ('<section class="week" id="week" aria-labelledby="week-h">'
            '<h1 id="week-h">This week in 15068</h1>'
            f'<p class="dateline">As of {fmt.ap_long(today, year=False)}</p>'
            f'<ol class="cal" id="cal-rows">{lis}</ol>'
            + (f'<template id="cal-more">{"".join(home_row(i, R, today, target(i)) for i in spare)}</template>'
               if spare else "")
            + f'<p class="go-line"><a class="go" href="{rel(R, "/calendar/")}">Full calendar ›</a></p></section>')


def _nums(D, R):
    pol = S.police_numbers(D)
    county = _pet(D, r"County Public Safety", "police")
    sh = P.shelter(D)
    btns = "".join(f'<a class="tel stack" href="{fmt.tel(pol[t]["primary"])[0][1]}" data-town="{esc(t)}">'
                   f'{esc(t)}<span class="small">{esc(pol[t]["primary"])}</span></a>' for t in CORE_TOWNS if t in pol)
    rows = [f'<div class="nk-row nk-911"><span class="nk-l">Emergency</span><a class="tel primary" href="tel:911">911</a></div>',
            f'<p class="nk-l">Police, non-emergency</p><div class="three" id="nums-police">{btns}</div>']
    srcs = [pol[t]["source"] for t in CORE_TOWNS if t in pol]
    if county and county.get("phone"):
        rows.append(f'<div class="nk-row"><span class="nk-l">After hours · County non-emergency line</span>'
                    f'{tel_a(phones(county["phone"])[0])}</div>')
        srcs.append(county.get("source"))
    if sh and sh.get("phone"):
        rows.append(f'<div class="nk-row"><span class="nk-l">Animal shelter · {esc(P.short_name(sh))}, '
                    f'{esc(C.ap_addr(sh.get("address")))}</span>{tel_a(phones(sh["phone"])[0])}</div>')
        srcs.append(sh.get("source"))
    return ('<section class="nums" id="nums" aria-labelledby="nums-h" data-keep-above>'
            '<h2 class="lh" id="nums-h">Numbers to keep</h2>' + "".join(rows)
            + f'<p class="go-line"><a class="go" href="{rel(R, "/numbers/")}">City halls, library, schools and more numbers ›</a></p>'
            + credit_line(srcs, "Sources: ") + "</section>")


def locator_size(D):
    """(width, height) for the locator <img>: from mapsvg's viewBox when that module is there, else the ZIP's bounds."""
    if "_loc_size" in D:
        return D["_loc_size"]
    w = h = None
    try:
        from . import mapsvg
        m = re.search(r'viewBox="\s*[-\d.]+\s+[-\d.]+\s+([\d.]+)\s+([\d.]+)"', mapsvg.locator(D))
        if m:
            w, h = float(m.group(1)), float(m.group(2))
    except Exception:
        w = h = None
    if not w:
        b = D["meta"]["bounds"]
        w, h = b[2] - b[0], b[3] - b[1]
    D["_loc_size"] = (600, max(1, round(600 * h / w)))
    return D["_loc_size"]


def _locator(D, R):
    w, h = locator_size(D)
    img = rel(R, "/img/15068-locator.svg")
    dark = rel(R, "/img/15068-locator-dark.svg")
    return ('<section class="locbox" id="where" aria-labelledby="where-h">'
            '<h2 class="lh" id="where-h">Where the three cities are</h2>'
            f'<a class="loc-img" href="{rel(R, "/towns/")}"><picture class="themed">'
            f'<source media="(prefers-color-scheme: dark)" srcset="{dark}">'
            f'<img src="{img}" width="{w}" height="{h}" alt="Map of ZIP 15068 with the city limits of New Kensington, '
            'Arnold and Lower Burrell"></picture></a>'
            f'<p class="loc-links"><a href="{rel(R, "/towns/")}">The three towns ›</a> · '
            f'<a href="{rel(R, "/map/")}">Open the map ›</a> · <a href="{rel(R, "/poster/")}">Get the poster ›</a></p>'
            '</section>')


def _crime(D, R):
    rows = S.home_crime_rows(D)
    if not rows:
        return ""
    last = max(r["year"] for r in rows)
    lis = "".join(f'<li><a class="bs-t" href="{rel(R, "/crime/" + r["slug"] + "/")}">{esc(r["town"])}</a>'
                  f'<span class="sep"> · </span><b class="bs-w">{esc(r["word"])}</b><span class="sep"> · </span>'
                  f'<span class="bs-x">{r["text"]}</span></li>' for r in rows)
    return ('<section class="home-sec crime-lead" id="crime-lead" aria-labelledby="crime-lead-h">'
            f'<h2 class="hl" id="crime-lead-h">{esc(S.home_crime_headline(rows))}</h2>'
            f'<p class="dateline">What each police department reported to the FBI, through {last}</p>'
            f'<ul class="lead-bs">{lis}</ul>'
            + fmt.credit_line(S.FBI_SOURCE)
            + f'<p class="go-line"><a class="go" href="{rel(R, "/crime/")}">Is crime going up? The full answer ›</a></p>'
            '</section>')


def _latest(D, R):
    items = news_items(D)
    if not items:
        return ""
    lis = "".join(f'<li><a class="hd-h" href="{rel(R, "/news/")}#{esc(news_id(n))}">{esc(fmt.public(n["headline"]))}</a>'
                  f'<p class="hd-m"><time datetime="{esc(n["date"])}">{esc(fmt.ap_date(n["date"], bool(n.get("date_note"))))}'
                  f'</time> · {credit(n.get("source"), "")}</p></li>' for n in items[:3])
    return ('<section class="home-sec" id="latest" aria-labelledby="latest-h"><h2 class="lh" id="latest-h">Latest</h2>'
            f'<ol class="heads">{lis}</ol>'
            f'<p class="go-line"><a class="go" href="{rel(R, "/news/")}">All {len(items)} news briefs ›</a></p></section>')


INSIDE = [("/crime/", "Crime and safety"), ("/crime/blotter/", "Police blotter"), ("/crashes/", "Serious crashes"),
          ("/towns/", "The three towns"), ("/history/", "History"), ("/history/people/", "Notable people"),
          ("/eat/", "Eat and drink"), ("/map/", "Map"), ("/poster/", "Map poster"),
          ("/directory/", "Places and streets A to Z")]


def _inside(R):
    lis = "".join(f'<li><a href="{rel(R, p)}">{esc(t)}</a></li>' for p, t in INSIDE)
    return (f'<nav class="home-sec inside" id="inside" aria-labelledby="inside-h"><h2 class="lh" id="inside-h">Inside</h2>'
            f'<ul>{lis}</ul></nav>')


def _changes(D):
    """Changelog dates for the since-your-last-visit line: [{date, n}] newest first."""
    entries = None
    try:
        from . import changelog
        if hasattr(changelog, "entries"):
            entries = changelog.entries(D)
    except Exception:
        entries = None
    if entries is None:
        entries = D.get("changelog") or []
    out = [{"date": str(e.get("date"))[:10], "n": len(e.get("items") or [])} for e in entries if e.get("date")]
    return fmt.json_script(out[:30])


def _search(R):
    return (f'<form class="sitesearch home-search m-only" role="search" action="{rel(R, "/search/")}" method="get">'
            '<label for="hs">Search 15068</label><span class="sf-row">'
            '<input id="hs" name="q" type="search" placeholder="Street, business, number or topic" autocomplete="off">'
            '<button type="submit">Search</button></span></form>')


def home(D, R):
    items = C.occurrences(D, D["today"])
    body = ('<div class="page home">'
            '<p class="since" id="since" role="status" hidden></p>'
            '<div class="home-grid">'
            + P.home_box(D, R)
            + _search(R)
            + _week(D, R, items)
            + f'<aside class="home-rail" aria-label="Numbers to keep and where the cities are">{_nums(D, R)}{_locator(D, R)}</aside>'
            + _crime(D, R) + _latest(D, R) + _inside(R)
            + '</div>'
            f'<script type="application/json" id="changes">{_changes(D)}</script>'
            '</div>')
    return {"body": body}
