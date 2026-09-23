"""Plain-language crime and crash sentences, computed from site/data/safety.json and the research JSON.

Comparison rules (spec 1c):
- compare the latest reported year with the previous reported year;
- if either has fewer than 12 months reported, compare monthly averages (count / months) and say so;
- within +-10% is "about the same", otherwise up or down; raw counts are always printed;
- "highest since Y (r)" names the most recent earlier year with a rate at least as high, else "the highest in the
  department's FBI record, which goes back to <first year>"; "lowest" works the same way;
- counts under 20 get the small-numbers note.

Other builders call: home_crime_rows, home_crime_headline, short_answer, crash_town_sentence, police_numbers,
incident_counts. Everything returned is HTML-safe text (no tags) unless a function says otherwise.
"""
import html
import re
import statistics
from collections import Counter, defaultdict

from . import fmt
from .data import CORE_TOWNS, TOWN_SLUGS, line_dist, lines

SAME_BAND = 0.10
SMALL = 20
SMALL_NOTE = "Small towns swing from year to year; a few incidents can move a rate a lot."
FBI_SOURCE = "https://github.com/jacobkap/crimedatatool_helper"
SNAP_M = 30  # crash points count toward a road when within 30 m (100 ft) of it

_WORDS = ("zero one two three four five six seven eight nine ten eleven twelve thirteen fourteen fifteen sixteen "
          "seventeen eighteen nineteen").split()
_TENS = "twenty thirty forty fifty sixty seventy eighty ninety".split()


# --------------------------------------------------------------------------- small helpers


def spell(n):
    """0-99 in words ('three', 'forty-four'); larger numbers as figures."""
    n = int(n)
    if 0 <= n < 20:
        return _WORDS[n]
    if n < 100:
        t, u = divmod(n, 10)
        return _TENS[t - 2] + (f"-{_WORDS[u]}" if u else "")
    return fmt.num(n)


def ap_num(n):
    """AP style in running text: one through nine spelled out, 10 and up as figures."""
    return spell(n) if 0 <= int(n) < 10 else fmt.num(n)


def lead_num(n):
    """A number that starts a sentence is spelled out."""
    return fmt.cap(spell(n))


def join_and(items):
    items = [str(i) for i in items]
    if len(items) <= 1:
        return "".join(items)
    return ", ".join(items[:-1]) + " and " + items[-1]


def plural(n, one, many=None):
    return one if n == 1 else (many or one + "s")


def f1(x):
    return f"{x:,.1f}"


def text(s):
    """Escape for an HTML text node (apostrophes and quotes stay as typed)."""
    return html.escape(s, quote=False)


# --------------------------------------------------------------------------- FBI series


def agency(D, town):
    for a in D["safety"]["fbi"]["agencies"]:
        if a.get("municipality") == town or town in (a.get("agency") or ""):
            return a
    return None


def val(y, key):
    if callable(key):
        return key(y)
    if key == "arrests":
        return (y.get("arrests") or {}).get("total")
    return y.get(key)


def months(y):
    return y.get("months_reported") or 0


def partial(y):
    return 0 < months(y) < 12


def rate(y, key):
    v = val(y, key)
    return v / y["population"] * 1000 if v is not None and y.get("population") else None


def monthly(y, key):
    return val(y, key) / months(y)


def pace(y, key):
    """Best full-year estimate of the rate: a partial year is scaled up to 12 months."""
    r = rate(y, key)
    return r * 12 / months(y) if r is not None and partial(y) else r


def series(ag, key="violent", need_months=True):
    """Years with a figure for key (and population), oldest first."""
    out = []
    for y in (ag or {}).get("years") or []:
        if val(y, key) is None or not y.get("population"):
            continue
        if need_months and months(y) <= 0:
            continue
        out.append(y)
    return sorted(out, key=lambda y: y["year"])


def latest_pair(ag, key="violent"):
    ys = series(ag, key)
    if not ys:
        return None, None
    return ys[-1], (ys[-2] if len(ys) > 1 else None)


def direction(a, b, key="violent"):
    """'up' | 'down' | 'same' for latest year a against previous year b (monthly averages when either is partial)."""
    if b is None:
        return "same"
    if partial(a) or partial(b):
        va, vb = monthly(a, key), monthly(b, key)
    else:
        va, vb = rate(a, key), rate(b, key)
    if not vb:
        return "same" if not va else "up"
    ch = (va - vb) / vb
    if abs(ch) <= SAME_BAND:
        return "same"
    return "up" if ch > 0 else "down"


def since(ag, key, y, higher=True):
    """The most recent earlier year whose rate was at least as high (higher=True) or at least as low as y's.
    Earlier partial years are judged at their full-year pace. Returns (year dict, rate shown) or None."""
    cur = rate(y, key)
    for e in reversed([e for e in series(ag, key) if e["year"] < y["year"]]):
        p = pace(e, key)
        if (higher and p >= cur) or (not higher and p <= cur):
            return e, p
    return None


def rate_label(e, key, p):
    """'5.3' for a full year; the pace for a partial one, labelled."""
    if partial(e):
        return f"{f1(p)} at the pace of its {months(e)} reported months"
    return f1(p)


def first_year(ag, key="violent"):
    ys = series(ag, key)
    return ys[0]["year"] if ys else None


def missing_between(ag, a, b):
    """Years strictly between b and a with no figures sent (a zero-month year or no row at all)."""
    if a is None or b is None:
        return []
    have = {y["year"] for y in series(ag, "violent")}
    return [yr for yr in range(b["year"] + 1, a["year"]) if yr not in have]


def record_first(ag):
    """First year of the department's FBI record (any row), for 'sent no figures' lists."""
    ys = [y["year"] for y in (ag or {}).get("years") or []]
    return min(ys) if ys else None


def gap_years(D, ag):
    """Every year from the start of the FBI data through the department's latest with no offense figures."""
    starts = [record_first(a) for a in D["safety"]["fbi"]["agencies"] if record_first(a)]
    have = {y["year"] for y in series(ag, "violent")}
    last = max(have) if have else None
    if not starts or last is None:
        return []
    return [yr for yr in range(min(starts), last + 1) if yr not in have]


def partial_years(ag):
    return [y for y in series(ag, "violent") if partial(y)]


def police(D, town):
    return next((a for a in D["safety"]["policing"].get("agencies") or [] if a.get("municipality") == town), None)


# --------------------------------------------------------------------------- the short answer (spec section 6)


def _crimes(n):
    return f"{fmt.num(n)} violent {plural(n, 'crime')}"


def _since_sentence(ag, key, a, word):
    """'That is the city's highest rate since 2019 (5.3).' / 'That is the lowest rate since 2018 (0.8).'"""
    if word == "up":
        s = since(ag, key, a, True)
        if s:
            return f"That is the city's highest rate since {s[0]['year']} ({rate_label(s[0], key, s[1])})."
        return f"That is the highest rate in the department's FBI record, which goes back to {first_year(ag, key)}."
    if word == "down":
        s = since(ag, key, a, False)
        if s:
            return f"That is the lowest rate since {s[0]['year']} ({rate_label(s[0], key, s[1])})."
        return f"That is the lowest rate in the department's FBI record, which goes back to {first_year(ag, key)}."
    return ""


def property_clause(ag):
    """'Property crime rose to 24.0 per 1,000 from 21.2, still lower than any year from 2001 through 2019.'
    Only for a full latest year (a partial year's rate is understated); '' otherwise."""
    a, b = latest_pair(ag, "property")
    if a is None or partial(a):
        return ""
    word = direction(a, b, "property")
    r = f1(rate(a, "property"))
    frm = f" from {f1(rate(b, 'property'))}" if b is not None and not partial(b) else ""
    if word == "same":
        return f"Property crime held about steady at {r} per 1,000{frm}."
    verb = "rose" if word == "up" else "fell"
    ys = series(ag, "property")
    first = ys[0]["year"]
    cur = rate(a, "property")
    s = since(ag, "property", a, word == "up")
    if s is None:
        q = f"the {'highest' if word == 'up' else 'lowest'} in the department's FBI record, which goes back to {first}"
    else:
        early = [pace(e, "property") for e in ys if e["year"] <= s[0]["year"]]
        beyond = all(p > cur for p in early) if word == "up" else all(p < cur for p in early)
        if beyond and s[0]["year"] - first >= 4:
            q = f"still {'lower' if word == 'up' else 'higher'} than any year from {first} through {s[0]['year']}"
        else:
            q = f"the {'highest' if word == 'up' else 'lowest'} since {s[0]['year']} ({rate_label(s[0], 'property', s[1])})"
    return f"Property crime {verb} to {r} per 1,000{frm}, {q}."


def clearance_short(a, long):
    """'Police cleared 32 of the 54 violent crimes.' (long) / 'Police cleared 8 of the 39.'"""
    c, n = a.get("cleared_violent"), a.get("violent")
    if c is None or not n or (c == 0 and n >= 10):
        return ""
    if c >= n:
        return f"Police cleared all {fmt.num(n)} violent {plural(n, 'crime')}." if long else f"Police cleared all {fmt.num(n)}."
    return f"Police cleared {fmt.num(c)} of the {_crimes(n)}." if long else f"Police cleared {fmt.num(c)} of the {fmt.num(n)}."


def short_answer(D, town):
    """The department paragraph for the /crime/ short answers, the department page lead and the town pages."""
    ag = agency(D, town)
    a, b = latest_pair(ag)
    if a is None:
        return f"{town} police have not sent violent-crime figures to the FBI."
    word = direction(a, b)
    n, Y = a["violent"], a["year"]
    miss = missing_between(ag, a, b)
    gap = f"{town} sent no figures for {join_and(miss)}." if miss else ""
    out = []
    if partial(a):
        m = months(a)
        s = (f"{town} police reported {_crimes(n)} in the {m} months of {Y} they sent to the FBI, "
             f"about {f1(monthly(a, 'violent'))} a month")
        if b is not None:
            prev = (f"({fmt.num(b['violent'])} in {months(b)} months)" if partial(b)
                    else f"({fmt.num(b['violent'])} for the full year)")
            if word == "same":
                s += f", about the same as the {f1(monthly(b, 'violent'))} a month in {b['year']} {prev}"
            else:
                s += f", {word} from about {f1(monthly(b, 'violent'))} a month in {b['year']} {prev}"
        out.append(s + ".")
        out.append(gap)
        t = f"The {Y} count works out to {f1(rate(a, 'violent'))} per 1,000 residents"
        if word == "up":
            hs = since(ag, "violent", a, True)
            t += (f", the city's highest rate since {hs[0]['year']} ({rate_label(hs[0], 'violent', hs[1])})" if hs
                  else f", the highest in the department's FBI record, which goes back to {first_year(ag)}")
        k = 12 - m
        t += f", and with {spell(k)} {plural(k, 'month')} missing the full-year number can only be higher."
        out.append(t)
        out.append(clearance_short(a, long=False))
    else:
        s = f"{town} police reported {_crimes(n)} to the FBI in {Y}, or {f1(rate(a, 'violent'))} per 1,000 residents"
        if b is not None and partial(b):  # compare like with like: a partial year is only comparable per month
            s += f" and about {f1(monthly(a, 'violent'))} a month"
        if b is not None:
            if partial(b):
                prev = (f"{fmt.num(b['violent'])} in the {months(b)} months of {b['year']} it reported "
                        f"(about {f1(monthly(b, 'violent'))} a month)")
            else:
                prev = f"{fmt.num(b['violent'])} ({f1(rate(b, 'violent'))} per 1,000) in {b['year']}"
            s += f", about the same as the {prev}" if word == "same" else f", {word} from {prev}"
        out.append(s + ".")
        out.append(gap)
        out.append(_since_sentence(ag, "violent", a, word))
        prop = property_clause(ag)
        out.append(prop)
        out.append(clearance_short(a, long=bool(prop)))
    return text(" ".join(p for p in out if p))


def small_numbers(D, town):
    """True when the latest violent or property count shown for the town is under 20."""
    ag = agency(D, town)
    a, b = latest_pair(ag)
    counts = [y.get("violent") for y in (a, b) if y]
    pa, _ = latest_pair(ag, "property")
    if pa:
        counts.append(pa.get("property"))
    return any(c is not None and c < SMALL for c in counts)


# --------------------------------------------------------------------------- home crime lead


def _row_text(a, b):
    if partial(a):
        cur = f"{fmt.num(a['violent'])} in {months(a)} months of {a['year']} (about {f1(monthly(a, 'violent'))} a month)"
    elif b is not None and partial(b):
        cur = f"{fmt.num(a['violent'])} in {a['year']} (about {f1(monthly(a, 'violent'))} a month)"
    else:
        cur = f"{fmt.num(a['violent'])} in {a['year']} ({f1(rate(a, 'violent'))} per 1,000)"
    if b is None:
        return cur
    if partial(b):
        prev = f"{fmt.num(b['violent'])} in {months(b)} months of {b['year']} (about {f1(monthly(b, 'violent'))} a month)"
    else:
        per = "" if not partial(a) else " per 1,000"
        prev = f"{fmt.num(b['violent'])} in {b['year']} ({f1(rate(b, 'violent'))}{per})"
    return f"{cur}, from {prev}"


WORD = {"up": "Up", "down": "Down", "same": "About the same"}


def home_crime_rows(D):
    """[{town, slug, word ('Up'|'Down'|'About the same'), text, year}] in NK, Arnold, LB order."""
    rows = []
    for t in CORE_TOWNS:
        a, b = latest_pair(agency(D, t))
        if a is None:
            continue
        rows.append({"town": t, "slug": TOWN_SLUGS[t], "word": WORD[direction(a, b)], "text": text(_row_text(a, b)),
                     "year": a["year"]})
    return rows


def home_crime_headline(rows):
    """'Violent crime rose in New Kensington and Arnold in 2024 and fell in Lower Burrell'"""
    if not rows:
        return "Violent crime in the three cities"
    verbs = {"Up": "rose", "Down": "fell", "About the same": "held about steady"}
    groups = []
    for r in rows:
        g = next((g for g in groups if g[0] == r["word"]), None)
        if g:
            g[1].append(r["town"])
        else:
            groups.append((r["word"], [r["town"]]))
    years = {r.get("year") for r in rows}
    when = f" in {years.pop()}" if len(years) == 1 else " in each department's latest report"
    parts = []
    for i, (w, towns) in enumerate(groups):
        where = "all three cities" if len(towns) == 3 else join_and(towns)
        parts.append(f"{verbs[w]} in {where}" + (when if i == 0 else ""))
    return "Violent crime " + join_and(parts)


# --------------------------------------------------------------------------- chart findings (hub)


def violent_finding(D):
    """'Arnold's rate has swung the most, from 1.6 per 1,000 in 2016 to 13.9 in 2017.'"""
    best = None
    for t in CORE_TOWNS:
        ys = series(agency(D, t))
        if not ys:
            continue
        hi = max(ys, key=lambda y: rate(y, "violent"))
        full = [y for y in ys if not partial(y)] or ys
        lo = min(full, key=lambda y: rate(y, "violent"))
        span = rate(hi, "violent") - rate(lo, "violent")
        if best is None or span > best[0]:
            best = (span, t, hi, lo)
    if best is None:
        return ""
    _, t, hi, lo = best
    a, b = sorted((hi, lo), key=lambda y: y["year"])
    return (f"{t}'s rate has swung the most, from {f1(rate(a, 'violent'))} per 1,000 in {a['year']} "
            f"to {f1(rate(b, 'violent'))} in {b['year']}.")


def property_finding(D, lo=2001, hi=2009):
    """Each department's latest property rate (at its full-year pace) against the median of its 2001-2009 rates.
    Returns (sentence, detail) where detail explains the comparison with the numbers."""
    cats, detail = [], []
    for t in CORE_TOWNS:
        ag = agency(D, t)
        a, _ = latest_pair(ag, "property")
        base = [rate(y, "property") for y in series(ag, "property") if lo <= y["year"] <= hi and not partial(y)]
        if a is None or not base:
            continue
        med = statistics.median(base)
        cur = pace(a, "property")
        ratio = cur / med
        cat = "well" if ratio < 0.75 else "below" if ratio < 0.9 else "same" if ratio <= 1.1 else "above"
        cats.append((t, cat, a))
        pace_note = f", at the pace of its {months(a)} reported months" if partial(a) else ""
        detail.append(f"{t} {f1(cur)} in {a['year']}{pace_note}, against {f1(med)}")
    if not cats:
        return "", ""
    full = {"well": "well below its 2000s level", "below": "below its 2000s level", "same": "about the same as in the 2000s",
            "above": "above its 2000s level"}
    short = {"well": "well below it", "below": "below it", "same": "about the same", "above": "above it"}
    groups = []
    for t, c, a in cats:
        g = next((g for g in groups if g[0] == c), None)
        if g:
            g[1].append(t)
        else:
            groups.append((c, [t]))
    if len(groups) == 1 and len(cats) == 3:
        s = f"Property crime in all three cities is {full[groups[0][0]]}"
    else:
        parts = [f"{(full if i == 0 else short)[c]} in {join_and(ts)}" for i, (c, ts) in enumerate(groups)]
        s = "Property crime is " + join_and(parts)
    part = [(t, a) for t, _, a in cats if partial(a)]
    if part:
        s += "".join(f", going by the {months(a)} months of {a['year']} {t} reported" for t, a in part[:1])
    note = ("The 2000s level is the median of each department's 2001–2009 rates per 1,000 residents: "
            + "; ".join(detail) + ".")
    return s + ".", note


# --------------------------------------------------------------------------- department-page sentences


def record_high_low(D, town, key="violent", noun="rate"):
    """'Arnold's highest rate in the record was 13.9 per 1,000 in 2017; its lowest was 1.6 in 2016.'"""
    ys = series(agency(D, town), key)
    if not ys:
        return ""
    hi = max(ys, key=lambda y: rate(y, key))
    full = [y for y in ys if not partial(y)] or ys
    lo = min(full, key=lambda y: rate(y, key))
    # partial years are left out of the low (their rates undercount), so say so when there were any
    lowest = "its lowest full-year rate was" if len(full) < len(ys) else "its lowest was"
    return (f"{town}'s highest {noun} in the record was {f1(rate(hi, key))} per 1,000 in {hi['year']}; "
            f"{lowest} {f1(rate(lo, key))} in {lo['year']}.")


def gaps_sentence(D, town):
    """'Arnold sent no offense figures for 2003, 2019, 2021 and 2023. 2021 is missing for most Pennsylvania
    departments because the FBI switched to incident-based reporting that year. 2022 covers 10 months and 2024 covers 9.'"""
    ag = agency(D, town)
    miss = gap_years(D, ag)
    out = []
    if miss:
        out.append(f"{town} sent no offense figures for {join_and(miss)}.")
        if 2021 in miss:
            out.append("2021 is missing for most Pennsylvania departments because the FBI switched to "
                       "incident-based reporting that year.")
    parts = partial_years(ag)
    if parts:
        bits = [f"{y['year']} covers {months(y)}" + (" months" if i == 0 else "") for i, y in enumerate(parts)]
        out.append(fmt.cap(join_and(bits)) + ".")
    return text(" ".join(out))


def property_dept(D, town):
    """The department page's property sentence (handles a partial latest year)."""
    ag = agency(D, town)
    a, b = latest_pair(ag, "property")
    if a is None:
        return ""
    if not partial(a):
        return text(property_clause(ag))
    word = direction(a, b, "property")
    s = (f"In the {months(a)} months of {a['year']} it reported, {town} had {fmt.num(a['property'])} property "
         f"{plural(a['property'], 'crime')}, about {f1(monthly(a, 'property'))} a month")
    if b is not None:
        prev = (f"({fmt.num(b['property'])} in {months(b)} months)" if partial(b)
                else f"({fmt.num(b['property'])} for the full year)")
        if word == "same":
            s += f", about the same as the {f1(monthly(b, 'property'))} a month in {b['year']} {prev}"
        else:
            s += f", {word} from about {f1(monthly(b, 'property'))} a month in {b['year']} {prev}"
    return text(s + ".")


OFFENSES = [("murder", "Murder & manslaughter"), ("rape", "Rape"), ("robbery", "Robbery"),
            ("agg_assault", "Aggravated assault"), ("burglary", "Burglary"), ("larceny", "Larceny-theft"),
            ("mvt", "Motor vehicle theft"), ("arson", "Arson")]
VIOLENT_PARTS = [("murder", "Murders and manslaughters"), ("robbery", "Robberies"),
                 ("agg_assault", "Aggravated assaults")]
PROPERTY_PARTS = [("burglary", "Burglaries"), ("larceny", "Larceny-thefts"), ("mvt", "Motor vehicle thefts")]


def offense_year(ag):
    ys = [y for y in series(ag) if any(y.get(k) is not None for k, _ in OFFENSES)]
    return ys[-1] if ys else None


def offense_sentence(D, town):
    """'Aggravated assaults were 34 of the 39 violent crimes.' plus the largest property offense."""
    y = offense_year(agency(D, town))
    if not y:
        return ""
    out = []
    n = y.get("violent") or 0
    parts = [(y.get(k) or 0, l) for k, l in VIOLENT_PARTS]
    top = max(parts)
    if n and top[0]:
        out.append(f"All {fmt.num(n)} violent crimes were {top[1].lower()}." if top[0] == n and n > 1
                   else f"{top[1]} were {fmt.num(top[0])} of the {_crimes(n)}.")
    p = y.get("property") or 0
    pparts = [(y.get(k) or 0, l) for k, l in PROPERTY_PARTS]
    ptop = max(pparts)
    if p and ptop[0]:
        out.append(f"{ptop[1]} made up {fmt.num(ptop[0])} of the {fmt.num(p)} property {plural(p, 'crime')}.")
    if y.get("murder"):
        out.append(f"The department reported {spell(y['murder']) if y['murder'] < 10 else fmt.num(y['murder'])} "
                   f"{plural(y['murder'], 'murder or manslaughter', 'murders or manslaughters')}.")
    if partial(y):
        out.append(f"These figures cover {months(y)} months of {y['year']}.")
    return text(" ".join(out))


def _clear_ok(c, n, floor):
    return c is not None and n and not (c == 0 and n >= floor)


def _odd_zero(e):
    """'violent', 'property', 'both' or '' when a zero clearance count sits next to many reported crimes."""
    v = e.get("cleared_violent") == 0 and (e.get("violent") or 0) >= 10
    p = e.get("cleared_property") == 0 and (e.get("property") or 0) >= 20
    return "both" if v and p else "violent" if v else "property" if p else ""


def clearance(D, town):
    """'Arnold police cleared 8 of the 39 violent crimes they reported in 2024 and 2 of the 72 property crimes.'
    A zero clearance count against many reported crimes means clearances weren't sent, not that none were solved."""
    ag = agency(D, town)
    ys = [y for y in series(ag) if y.get("cleared_violent") is not None]
    if not ys:
        return ""
    y = ys[-1]
    out = []
    cv, n, cp, p = y.get("cleared_violent"), y.get("violent"), y.get("cleared_property"), y.get("property")
    if _clear_ok(cv, n, 10):
        what = f"all {_crimes(n)}" if cv >= n else f"{fmt.num(cv)} of the {_crimes(n)}"
        s = f"{town} police cleared {what} they reported in {y['year']}"
        if _clear_ok(cp, p, 20):
            s += f" and {'all' if cp >= p else fmt.num(cp) + ' of the'} {fmt.num(p)} property {plural(p, 'crime')}"
        out.append(s + ".")
    recent = ys[-5:]
    if len(recent) >= 3 and not any(_odd_zero(e) for e in recent):
        cv5, n5 = sum(e["cleared_violent"] for e in recent), sum(e["violent"] for e in recent)
        s = (f"Over its last {spell(len(recent))} reporting years ({join_and(e['year'] for e in recent)}), the "
             f"department cleared {round(cv5 / n5 * 100)}% of the violent crimes it reported")
        pr = [e for e in recent if e.get("cleared_property") is not None and e.get("property")]
        if len(pr) == len(recent):
            s += f" and {round(sum(e['cleared_property'] for e in pr) / sum(e['property'] for e in pr) * 100)}% of property crimes"
        out.append(s + ".")
    both = [e for e in series(ag) if _odd_zero(e) == "both"]
    prop = [e for e in series(ag) if _odd_zero(e) == "property"]
    viol = [e for e in series(ag) if _odd_zero(e) == "violent"]
    bits = []
    if both:
        bits.append(f"no clearances at all for {join_and(e['year'] for e in both)}, when the department reported "
                    f"{join_and(fmt.num(e['violent']) for e in both)} violent crimes")
    if viol:
        bits.append(f"no violent-crime clearances for {join_and(e['year'] for e in viol)}")
    if prop:
        bits.append(f"no property-crime clearances for {join_and(e['year'] for e in prop)}, against "
                    f"{join_and(fmt.num(e['property']) for e in prop)} property crimes")
    if bits:
        out.append("The FBI files show " + (", and ".join(bits) if len(bits) < 3 else join_and(bits)) + ". That almost certainly means clearances weren't "
                   "reported those years, not that none were solved.")
    return text(" ".join(out))


def arrests_sentence(D, town):
    """'Arnold's most recent arrest figures sent to the FBI are for 2020: 504 arrests, 62 of them for drugs.'"""
    ag = agency(D, town)
    ys = series(ag, "arrests", need_months=False)
    if not ys:
        return f"{town} police have not sent arrest figures to the FBI."
    y = ys[-1]
    ar = y["arrests"]
    s = f"{town}'s most recent arrest figures sent to the FBI are for {y['year']}: {fmt.num(ar['total'])} arrests"
    bits = []
    if ar.get("drugs") and not (ar["drugs"] == 0 and ar["total"] >= 100):
        bits.append(f"{fmt.num(ar['drugs'])} of them for drugs")
    if ar.get("dui"):
        bits.append(f"{fmt.num(ar['dui'])} for driving under the influence")
    if bits:
        s += ", " + join_and(bits)
    s += f". That is {f1(rate(y, 'arrests'))} arrests per 1,000 residents."
    offense_last = latest_pair(ag)[0]
    if offense_last and offense_last["year"] > y["year"]:
        s += f" The department has sent offense figures since then but no arrest counts."
    return text(s)


def officers(D, town):
    """FBI staffing count next to the department's published count, with a plain explanation (no Oct. 31 claim).
    Returns (text, source urls)."""
    ag = agency(D, town)
    fy = [y for y in (ag or {}).get("years") or [] if y.get("officers") is not None]
    pol = police(D, town) or {}
    out, srcs = [], [FBI_SOURCE]
    fbi_n = None
    if fy:
        y = fy[-1]
        fbi_n = y["officers"]
        out.append(f"The FBI's {y['year']} staffing file lists {fmt.num(fbi_n)} sworn officers for the {ag['agency']}.")
        if y.get("population"):
            out.append(f"That is {f1(fbi_n / y['population'] * 1000)} officers per 1,000 residents.")
    stats = [s for s in D["safety"]["policing"].get("stats") or [] if str(s.get("agency", "")).startswith(town)]
    auth = next((s for s in stats if s.get("metric") == "sworn_officers_authorized"), None)
    part = next((s for s in stats if s.get("metric") == "part_time_officers"), None)
    if pol.get("officers") is not None:
        n = pol["officers"]
        if part and part.get("year") == pol.get("officers_year"):
            what = f"{ap_num(n)} full-time and {ap_num(part['value'])} part-time officers"
            srcs.append(part["source"])
        else:
            what = f"{ap_num(n)} full-time {plural(n, 'officer')}"
        tail = ""
        if auth and auth.get("year") == pol.get("officers_year"):
            tail = f", of {ap_num(auth['value'])} authorized"
            srcs.append(auth["source"])
        out.append(f"Other published counts put the department at {what} in {pol.get('officers_year')}{tail}.")
        if len(srcs) == 1:  # no staffing figure with its own source: credit the department's page
            srcs += [u for u in pol.get("sources") or [] if fmt.host(u) not in ("facebook.com", "m.facebook.com")][:1]
        out.append("The two counts agree." if fbi_n == n and not part
                   else "The two counts come from different sources and dates.")
    staffing = [i for i in D["safety"]["policing"].get("interactions") or []
                if i.get("municipality") == town and i.get("kind") == "staffing"]
    if staffing:
        out.append("Staffing and leadership changes reported in the news are listed under police shootings, lawsuits "
                   "and policy changes below.")
    return text(" ".join(out)), srcs


# --------------------------------------------------------------------------- police numbers and incidents


def police_numbers(D):
    """{town: {"primary": "724-339-7533", "alt": ["724-339-7534"], "source": url}} from the pets.json police items."""
    out = {}
    for it in D["pets"].get("items") or []:
        if it.get("kind") != "police":
            continue
        town = next((t for t in CORE_TOWNS if str(it.get("name", "")).startswith(t)), None)
        if not town or town in out:
            continue
        nums = [shown for shown, _ in fmt.tel(it.get("phone"))]
        if nums:
            out[town] = {"primary": nums[0], "alt": nums[1:], "source": it.get("source")}
    return out


def incident_counts(D, town):
    """{"n": news-reported incidents in town, "first_year": earliest year}"""
    inc = [i for i in D["safety"].get("incidents") or [] if i.get("t") == town]
    return {"n": len(inc), "first_year": min((int(str(i["d"])[:4]) for i in inc), default=None)}


# --------------------------------------------------------------------------- crashes


def crash_years(D):
    st = D["safety"]["crashes"]["stats"]
    ys = [r["year"] for r in st]
    return min(ys), max(ys)


def crash_totals(D, town=None, since_year=None):
    st = [r for r in D["safety"]["crashes"]["stats"] if (town is None or r["t"] == town)
          and (since_year is None or r["year"] >= since_year)]
    return {k: sum(r[k] for r in st) for k in ("crashes", "fatal", "serious")}


def crash_town_sentence(D, town):
    return text(_crash_town_sentence(D, town))


def _crash_town_sentence(D, town):
    """'PennDOT recorded 7 crashes in Arnold from 2005 through 2024 that seriously injured someone, 8 people in all.
    None killed anyone.'"""
    y0, y1 = crash_years(D)
    t = crash_totals(D, town)
    n = t["crashes"]
    if not n:
        return f"PennDOT recorded no crashes in {town} from {y0} through {y1} that killed or seriously injured someone."
    if not t["fatal"]:
        if n == 1:
            return (f"PennDOT recorded 1 crash in {town} from {y0} through {y1} that seriously injured someone. "
                    "No one was killed.")
        return (f"PennDOT recorded {fmt.num(n)} crashes in {town} from {y0} through {y1} that seriously injured "
                f"someone, {fmt.num(t['serious'])} {plural(t['serious'], 'person', 'people')} in all. "
                "None killed anyone.")
    return (f"PennDOT recorded {fmt.num(n)} {plural(n, 'crash', 'crashes')} in {town} from {y0} through {y1} that "
            f"killed or seriously injured someone. They killed {fmt.num(t['fatal'])} "
            f"{plural(t['fatal'], 'person', 'people')} and seriously injured {fmt.num(t['serious'])}.")


def snap_crashes(D):
    """Each mapped crash point matched to the nearest named road within 30 m (cached on D).
    Returns [(point, road name or None)]."""
    if "_snapped" not in D:
        named = [l for l in lines(D) if l["n"]]
        out = []
        for p in D["safety"]["crashes"]["points"]:
            best, bd = None, float("inf")
            for l in named:
                d = line_dist(p["x"], p["y"], l["pts"])
                if d < bd:
                    best, bd = l["n"], d
            out.append((p, best if bd <= SNAP_M else None))
        D["_snapped"] = out
    return D["_snapped"]


def crash_roads(D):
    """[{"road", "n", "killed", "towns": [..]}] sorted by crashes, then people killed, then name."""
    agg = defaultdict(lambda: {"n": 0, "killed": 0, "towns": Counter()})
    for p, road in snap_crashes(D):
        if road:
            a = agg[road]
            a["n"] += 1
            a["killed"] += p.get("f") or 0
            a["towns"][p["t"]] += 1
    rows = [{"road": r, "n": a["n"], "killed": a["killed"], "towns": [t for t, _ in a["towns"].most_common()]}
            for r, a in agg.items()]
    return sorted(rows, key=lambda r: (-r["n"], -r["killed"], r["road"]))


def crash_lead(D):
    """The /crashes/ lead (spec section 6), as a list of sentences."""
    y0, y1 = crash_years(D)
    tot = crash_totals(D)
    by = sorted(((crash_totals(D, t)["crashes"], t) for t in CORE_TOWNS), key=lambda x: (-x[0], CORE_TOWNS.index(x[1])))
    out = [f"PennDOT recorded {fmt.num(tot['crashes'])} crashes from {y0} through {y1} that killed or seriously injured "
           f"someone in the three cities: {join_and(f'{fmt.num(n)} in {t}' for n, t in by)}.",
           f"They killed {fmt.num(tot['fatal'])} people and seriously injured {fmt.num(tot['serious'])}."]
    last = crash_totals(D, since_year=y1 - 4)
    out.append(f"From {y1 - 4} through {y1} there were {fmt.num(last['crashes'])} such crashes, which killed "
               f"{fmt.num(last['fatal'])} {plural(last['fatal'], 'person', 'people')}.")
    pts = D["safety"]["crashes"]["points"]
    roads = crash_roads(D)
    if roads:
        top = roads[:3]
        named = [f"{r['road']} ({fmt.num(r['n'])})" for r in top]
        s = f"Of the {fmt.num(len(pts))} crashes with a mapped location, the most were on {join_and(named)}"
        most = max(r["killed"] for r in roads)
        deadly = [r for r in roads if r["killed"] == most]
        if most and len(deadly) == 1 and deadly[0] is top[-1]:
            s += f", where {fmt.num(most)} people died, more than on any other road."
        elif most and len(deadly) == 1:
            s += f". The deadliest road was {deadly[0]['road']}, where {fmt.num(most)} people died."
        else:
            s += "."
        out.append(s)
    ped = [p for p in pts if p.get("col") == "Hit pedestrian"]
    if ped:
        k = sum(p.get("f") or 0 for p in ped)
        out.append(f"{lead_num(len(ped))} of the mapped crashes hit a pedestrian; those crashes killed "
                   f"{fmt.num(k)} {plural(k, 'person', 'people')}.")
    return out


def crash_types(D):
    """[(collision type, crashes, killed, seriously injured)] from the mapped points, most common first."""
    agg = defaultdict(lambda: [0, 0, 0])
    for p in D["safety"]["crashes"]["points"]:
        a = agg[p.get("col") or "Other"]
        a[0] += 1
        a[1] += p.get("f") or 0
        a[2] += p.get("s") or 0
    return sorted(((c, *v) for c, v in agg.items()), key=lambda r: (-r[1], r[0]))


# --------------------------------------------------------------------------- police interactions


LABELS = {
    "sworn_officers_authorized": "Authorized full-time officers", "part_time_officers": "Part-time officers",
    "starting_salary_patrol_officer": "Starting patrol salary", "body_camera_funding": "Body-camera funding from DA forfeiture",
    "pct_arrests_low_level_nonviolent": "Arrests for low-level, nonviolent offenses (2013–2023)",
    "people_killed_by_police": "People killed by police (2013–2023)",
    "fatal_police_shootings_wapo": "Fatal police shootings (Washington Post, 2015–2024)",
    "police_shooting": "Police shooting", "officer_killed": "Officer killed in the line of duty",
    "misconduct_charge": "Officer charged", "death_in_custody": "Death in custody", "use_of_force": "Use of force",
    "body_cameras": "Body cameras", "regionalization": "Regionalization talks", "community_program": "Community program",
    "staffing": "Staffing", "lawsuit": "Lawsuit", "complaint": "Complaint", "policy": "Policy",
}


def pretty(m):
    return LABELS.get(m) or fmt.cap(str(m).replace("_", " "))


def merged_interactions(D, town=None):
    """Interactions (newest first) with the matching incident attached: same (date, municipality, kind) = one item.
    Returns [(interaction, incident or None, incident id or None)]."""
    inc = D["safety"].get("incidents") or []
    ids = fmt.inc_ids(inc)
    key = {(i.get("d"), i.get("t"), i.get("k")): (i, iid) for i, iid in zip(inc, ids)}
    out = []
    for it in sorted(D["safety"]["policing"].get("interactions") or [], key=lambda i: str(i.get("date")), reverse=True):
        if town and it.get("municipality") != town:
            continue
        hit = key.get((it.get("date"), it.get("municipality"), it.get("kind")))
        out.append((it, hit[0] if hit else None, hit[1] if hit else None))
    return out


def merged_incident_ids(D):
    """{incident id: municipality} for incidents shown with a police interaction on a department page."""
    out = {}
    for it, i, iid in merged_interactions(D):
        if iid:
            out[iid] = it.get("municipality")
    return out


def wapo_sentence(D, town):
    """One sentence on the Washington Post fatal police shootings database for the city. Returns (text, url)."""
    pol = D["safety"]["policing"]
    rows = [w for w in pol.get("wapo_fatal_shootings_in_area") or [] if w.get("city") == town]
    stat = next((s for s in pol.get("stats") or [] if s.get("metric") == "fatal_police_shootings_wapo"), None)
    m = re.search(r"(\d{4})\D+(\d{4})", str((stat or {}).get("unit", "")))
    span = f" from {m.group(1)} through {m.group(2)}" if m else ""
    url = (rows[0].get("source") if rows else None) or (stat or {}).get("source")
    if not rows:
        return f"The Washington Post's database of fatal police shootings lists none in {town}{span}.", url
    dates = join_and(fmt.ap_date(w["date"]) for w in sorted(rows, key=lambda w: w["date"]))
    n = len(rows)
    return (f"The Washington Post's database of fatal police shootings lists {spell(n)} in {town}{span}: "
            f"on {dates}." if n > 1 else
            f"The Washington Post's database of fatal police shootings lists one in {town}{span}, on {dates}."), url
