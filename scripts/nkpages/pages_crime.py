"""Crime pages: /crime/ (hub), /crime/<town>/ (department reports), /crime/blotter/ and /crashes/.

Every number is computed from site/data/safety.json at build time (sentences.py holds the wording rules);
research text passes through fmt.public(); incidents are hundred-block only and never name private people.
"""
import re
from urllib.parse import quote_plus

from . import charts, fmt
from . import sentences as S
from .data import CORE_TOWNS, SLUG_TOWNS, TOWN_SLUGS, updated
from .fmt import esc
from .shell import rel, site_url

FBI_URL = S.FBI_SOURCE
CAT = {"violent": "Violent", "property": "Property", "police": "Police and other"}
TYPE = {
    "homicide": "Homicide", "shooting": "Shooting", "stabbing": "Stabbing", "robbery": "Robbery", "assault": "Assault",
    "burglary": "Burglary", "theft": "Theft", "vehicle_theft": "Vehicle theft", "arson": "Arson", "fire": "Fire",
    "drugs": "Drug case", "weapons": "Weapons", "pursuit": "Police pursuit", "standoff": "Standoff",
    "police_shooting": "Police shooting", "use_of_force": "Use of force", "crash": "Crash", "vandalism": "Vandalism",
    "fraud": "Fraud", "other": "Other",
}
COLLISION = {"Angle": "angle crashes", "Hit fixed object": "crashes into a fixed object",
             "Hit pedestrian": "crashes that hit a pedestrian", "Rear-end": "rear-end crashes", "Head-on": "head-on crashes",
             "Non-collision": "non-collision crashes", "Sideswipe (opposite direction)": "opposite-direction sideswipes",
             "Sideswipe (same direction)": "same-direction sideswipes", "Other": "other crashes"}


# --------------------------------------------------------------------------- small pieces


def sec(sid, title, body, cls=""):
    c = f"sec {cls}".strip()
    return (f'<section class="{c}" id="{sid}" aria-labelledby="{sid}-h"><h2 id="{sid}-h">{title}</h2>'
            f"{body}</section>")


def dateline(D, R, lead):
    return f'<p class="dateline">{lead} · Updated {fmt.ap_date(updated(D, R.dates))}</p>'


def fbi_years(D):
    ys = [y["year"] for a in D["safety"]["fbi"]["agencies"] for y in a["years"]]
    return min(ys), max(y["year"] for a in D["safety"]["fbi"]["agencies"] for y in S.series(a))


def fbi_credit(extra=""):
    return f'<p class="credit">{fmt.credit(FBI_URL)}{extra}</p>'


def sources_line(urls):
    return f'<p class="credit sources">{fmt.credit(urls, "Sources: ")}.</p>'


def dataset(D, R, name, desc, years, based_on, keywords):
    u = site_url(D)
    return {"@context": "https://schema.org", "@type": "Dataset", "name": name, "description": desc,
            "url": u + R.path, "temporalCoverage": f"{years[0]}/{years[1]}",
            "spatialCoverage": {"@type": "Place", "name": "New Kensington, Arnold and Lower Burrell, Pennsylvania (ZIP 15068)"},
            "isAccessibleForFree": True, "isBasedOn": based_on, "keywords": keywords,
            "creator": {"@type": "Organization", "name": "NK15068", "url": u + "/"}}


def fbi_dataset(D, R, name, who):
    y0, y1 = fbi_years(D)
    return dataset(D, R, f"{name}, {y0}–{y1}",
                   f"Offenses, clearances, arrests and staffing that {who} reported to the FBI's Uniform Crime Reporting "
                   "program, with rates per 1,000 residents, from the per-agency files compiled by Jacob Kaplan "
                   "(crimedatatool_helper).",
                   (y0, y1), [FBI_URL], ["crime", "FBI UCR", "police", "Westmoreland County", "15068"])


def ap_addr(a):
    """'601 Drey St, Arnold, PA 15068' -> '601 Drey St.'"""
    s = fmt.short_addr(a)
    return re.sub(r"\b(St|Ave|Blvd|Rd|Dr|Ln|Pl|Ct)$", r"\1.", s)


# --------------------------------------------------------------------------- incidents (blotter entries)


def inc_list(D):
    """[(incident, id)] newest first (ids from fmt.inc_ids in safety.json order)."""
    inc = D["safety"].get("incidents") or []
    pairs = list(zip(inc, fmt.inc_ids(inc)))
    return sorted(pairs, key=lambda p: str(p[0].get("d")), reverse=True)


def inc_streets(i):
    """The street names in an incident's location label: '1100 block of 5th Avenue' -> ['5th Avenue'],
    '4th Avenue & Hileman Drive' -> both, a named place -> []."""
    l = str(i.get("l") or "")
    p = i.get("p")
    if p == "place":
        return []
    if p == "block":
        l = re.sub(r"^\d+\s+block\s+of\s+", "", l, flags=re.I)
    return [s.strip() for s in l.split("&") if s.strip()]


def street_attrs(i):
    keys = [fmt.street_key(s) for s in inc_streets(i)]
    keys = [k for k in keys if k]
    return "|".join(k["core"] for k in keys), "|".join(k["type"] or "" for k in keys)


def entry(D, R, i, iid, xref=""):
    st, sty = street_attrs(i)
    pi = " pi" if i.get("pi") else ""
    c = i.get("c") or "police"
    approx = " · approximate location" if i.get("p") == "street" else ""
    return (f'<article class="entry" id="inc-{esc(iid)}" data-id="{esc(iid)}" data-c="{esc(c)}" data-t="{esc(i.get("t"))}" '
            f'data-yr="{esc(str(i.get("d"))[:4])}" data-st="{esc(st)}" data-sty="{esc(sty)}" '
            f'data-mx="{round(i.get("x") or 0)}" data-my="{round(i.get("y") or 0)}">'
            f'<p class="bl"><b class="lead-in">{esc(i.get("t"))}.</b> <span class="inc-key k{pi}" '
            f'style="background:var(--inc-{esc(c)})"></span><b class="what">{esc(TYPE.get(i.get("k"), fmt.cap(i.get("k"))))}.</b> '
            f'{esc(fmt.public(i.get("s")))}</p>'
            f'<p class="meta"><time datetime="{esc(i.get("d"))}">{esc(fmt.ap_date(i.get("d")))}</time> · {esc(i.get("l"))}'
            f'{approx} · <a href="{rel(R, "/map/")}?inc={esc(iid)}">Map it</a> · {fmt.credit(i.get("src"))}</p>{xref}</article>')


def xref_html(D, R, iid, town, kind):
    if not town:
        return ""
    href = rel(R, f"/crime/{TOWN_SLUGS[town]}/") + "#police"
    what = "police shootings" if kind == "police_shooting" else "police actions"
    return f'<p class="xref"><a href="{href}">Also listed under {what} on the {esc(town)} crime page ›</a></p>'


# --------------------------------------------------------------------------- shared blocks


def numbers_line(D, R):
    """Emergency 911 plus each department's non-emergency line (a data-keep-above block)."""
    nums = S.police_numbers(D)
    btns = "".join(f'<a class="tel stack" href="{fmt.tel(nums[t]["primary"])[0][1]}">{esc(t)}'
                   f'<span class="small">{esc(nums[t]["primary"])}</span></a>' for t in CORE_TOWNS if t in nums)
    srcs = [nums[t]["source"] for t in CORE_TOWNS if t in nums]
    return ('<div class="numline top-rail" data-keep-above><div class="nl-911"><span class="nl-l">Emergency</span>'
            '<a class="tel primary" href="tel:911">911</a></div>'
            f'<div class="nl-ne"><span class="nl-l">Non-emergency</span><div class="three">{btns}</div></div>'
            f'{fmt.credit_line(srcs)}</div>')


def contact_box(D, R, town):
    pol = S.police(D, town) or {}
    nums = S.police_numbers(D).get(town)
    head = [f"<b>{esc(pol.get('name') or town + ' Police Department')}</b>"]
    if pol.get("address"):
        head.append(esc(ap_addr(pol["address"])))
    if pol.get("chief"):
        head.append(f"Chief {esc(pol['chief'])}")
    rows = []
    srcs = []
    if nums:
        alt = "".join(f', also <a href="{fmt.tel(a)[0][1]}">{esc(a)}</a>' for a in nums["alt"])
        rows.append(f'<div class="c-row">{fmt.tel_link(nums["primary"])}<span class="c-what">Non-emergency{alt}</span></div>')
        srcs.append(nums["source"])
    rows.append('<div class="c-row"><a class="tel primary" href="tel:911">911</a><span class="c-what">Emergency</span></div>')
    srcs += [u for u in pol.get("sources") or [] if fmt.host(u) not in ("facebook.com", "m.facebook.com")][:1]
    return (f'<div class="contact box top-rail" data-keep-above><p class="c-name">{" · ".join(head)}</p>{"".join(rows)}'
            f'{fmt.credit_line(srcs)}</div>')


def method_html(D, short=False):
    """'About these numbers': what the counts are, rates, gaps, partial years, mapping precision, what's left out."""
    s = D["safety"]
    fbi, pol = s["fbi"], s.get("policing") or {}
    pc = s.get("precision_counts") or {}
    oris = [f"{esc(a['municipality'])} {esc(a['ori'])}" for a in fbi["agencies"] if a.get("ori")]
    out = [
        "<p><b>Crime counts</b> come from the FBI's Uniform Crime Reporting program: the offenses each city's police "
        "department reported to the FBI, year by year, as compiled per department by Jacob Kaplan. "
        + (f"The FBI identifies the departments by these codes: {S.join_and(oris)}.</p>" if oris else "</p>"),
        "<p><b>Violent crime</b> is murder and manslaughter, rape, robbery and aggravated assault. <b>Property crime</b> "
        "is burglary, larceny-theft and motor vehicle theft. Arson is listed on its own.</p>",
        "<p><b>Rates</b> are per 1,000 residents, using the population the FBI published for that department and year. "
        f"{S.SMALL_NOTE}</p>",
    ]
    if fbi.get("gaps"):
        out.append(f"<p><b>Gaps:</b> {esc(fmt.public(fbi['gaps']))}</p>")
    out.append("<p><b>Partial years.</b> In some years a department reported fewer than 12 months. Those years are "
               "marked † and drawn as hollow dots, and comparisons with them use monthly averages rather than totals.</p>")
    out.append(
        "<p><b>Cleared</b> means the FBI counts the case as closed, usually by an arrest. <b>Arrests</b> include people "
        "who don't live in the city.</p>")
    if not short:
        out.append(
            f"<p><b>Mapped incidents</b> are ones local news reported with a street location, checked against the original "
            f"report. They are a sample, not a complete record. Locations are rounded to the hundred-block "
            f"({fmt.num(pc.get('block', 0))}), an intersection ({fmt.num(pc.get('intersection', 0))}) or a named place "
            f"({fmt.num(pc.get('place', 0))}); {fmt.num(pc.get('street', 0))} are placed on the street only and marked "
            f"approximate.{(' ' + fmt.num(s['unplaced']) + ' reported incidents could not be placed and are left off.') if s.get('unplaced') else ''}</p>")
    out.append(
        "<p><b>Left out on purpose:</b> names of suspects, victims and line officers (public officials such as chiefs "
        "and mayors may be named); exact house numbers; anything identifying a juvenile. Individual sexual-offense "
        "incidents are never mapped or listed; the FBI totals include them. An arrest or charge is not a conviction. "
        "The linked source articles are the original news reports and may name people; this site does not.</p>")
    if pol.get("notes"):
        out.append(f"<p><b>Policing notes:</b> {esc(fmt.public(pol['notes']))}</p>")
    return "".join(out)


def small_note(D, towns):
    return f'<p class="fine">{S.SMALL_NOTE}</p>' if any(S.small_numbers(D, t) for t in towns) else ""


# --------------------------------------------------------------------------- tables (ports of safety.js)


def box_score(D, R):
    fbi, pol = D["safety"]["fbi"], D["safety"].get("policing") or {}
    rows = []
    for t in CORE_TOWNS:
        ag = S.agency(D, t)
        a, _ = S.latest_pair(ag)
        py, _ = S.latest_pair(ag, "property")
        offy = [y for y in (ag or {}).get("years") or [] if y.get("officers") is not None and y.get("population")]
        p = S.police(D, t) or {}

        def sub(y, k):
            mark = f", only {S.months(y)} of 12 months †" if S.partial(y) else ""
            return f"{fmt.num(y[k])} in {y['year']}{mark}"

        cell = lambda b, s: f"<td><b>{b}</b><small>{s}</small></td>"
        name = f'<a href="{rel(R, "/crime/" + TOWN_SLUGS[t] + "/")}">{esc(t)}</a>'
        tds = (cell(S.f1(S.rate(a, "violent")), sub(a, "violent")) if a else '<td><small>No FBI figures</small></td>')
        tds += (cell(S.f1(S.rate(py, "property")), sub(py, "property")) if py else '<td><small>No FBI figures</small></td>')
        if offy:
            o = offy[-1]
            tds += cell(S.f1(o["officers"] / o["population"] * 1000), f"{fmt.num(o['officers'])} sworn, {o['year']}")
        else:
            tds += cell("–", "not reported")
        rows.append(f'<tr><th scope="row">{name}<small>{esc((ag or {}).get("agency") or p.get("name") or "")}</small></th>{tds}</tr>')
    links = S.join_and(f'<a href="{rel(R, "/crime/" + TOWN_SLUGS[t] + "/")}#officers">{esc(t)}</a>' for t in CORE_TOWNS)
    return ('<div class="dir-table-wrap"><table class="box-score"><thead><tr><th scope="col">Department</th>'
            '<th scope="col">Violent</th><th scope="col">Property</th><th scope="col">Officers*</th></tr></thead>'
            f'<tbody>{"".join(rows)}</tbody></table></div>'
            '<p class="credit">Rates are per 1,000 residents; under each is the count and the year. † Partial year. '
            f'* Sworn officers per 1,000 residents, as counted by the FBI. Each department page sets that next to the '
            f'department\'s own count: {links}. {fmt.credit(FBI_URL)}.</p>')


def _n(v):
    return "–" if v is None else fmt.num(v)


def fbi_table(D, town):
    ag = S.agency(D, town)
    rows = sorted((ag or {}).get("years") or [], key=lambda y: -y["year"])
    body = []
    for y in rows:
        rv, rp = S.rate(y, "violent"), S.rate(y, "property")
        src = fmt.pub((y.get("sources") or [None])[0])
        note = f'<span class="sub">{esc(fmt.public(y["note"]))}</span>' if y.get("note") else ""
        body.append(
            f'<tr><td class="num">{y["year"]}</td><td class="num">{_n(y.get("months_reported"))}</td>'
            f'<td class="num">{_n(y.get("population"))}{"*" if y.get("population_estimated_from") else ""}</td>'
            f'<td class="num">{_n(y.get("violent"))}</td><td class="num">{"–" if rv is None else S.f1(rv)}</td>'
            f'<td class="num">{_n(y.get("property"))}</td><td class="num">{"–" if rp is None else S.f1(rp)}</td>'
            f'<td class="num">{_n((y.get("arrests") or {}).get("total"))}</td><td class="num">{_n(y.get("officers"))}</td>'
            f'<td>{src}{note}</td></tr>')
    return ('<div class="dir-table-wrap"><table class="dir"><thead><tr><th class="num">Year</th><th class="num">Months</th>'
            '<th class="num">Population</th><th class="num">Violent</th><th class="num">per 1,000</th>'
            '<th class="num">Property</th><th class="num">per 1,000</th><th class="num">Arrests</th>'
            '<th class="num">Officers</th><th>Source</th></tr></thead><tbody>' + "".join(body) + '</tbody></table></div>'
            '<p class="table-note">Months is the number of months that year the department reported to the FBI. '
            '* Population carried over from the nearest year that reported one.</p>')


def offense_table(D, town):
    y = S.offense_year(S.agency(D, town))
    if not y:
        return ""
    head = f"{y['year']}{'†' if S.partial(y) else ''}"
    rows = [f'<tr><td>{l}</td><td class="num">{_n(y.get(k))}</td></tr>' for k, l in S.OFFENSES]
    rows.insert(4, f'<tr class="tot"><td>Violent crimes, total</td><td class="num">{_n(y.get("violent"))}</td></tr>')
    rows.insert(8, f'<tr class="tot"><td>Property crimes, total</td><td class="num">{_n(y.get("property"))}</td></tr>')
    note = f"† Partial year: {S.months(y)} of 12 months reported. " if S.partial(y) else ""
    return ('<div class="dir-table-wrap narrow"><table class="dir"><thead><tr><th>Offense</th>'
            f'<th class="num">{head}</th></tr></thead><tbody>{"".join(rows)}</tbody></table></div>'
            f'<p class="table-note">{note}{fmt.credit(FBI_URL)}</p>')


def police_work(D, town):
    ag = S.agency(D, town)
    ys = [y for y in (ag or {}).get("years") or []
          if y.get("arrests") or y.get("cleared_violent") is not None or y.get("officers_assaulted") is not None]
    ys = sorted(ys, key=lambda y: -y["year"])

    def pct(c, n, floor):
        if c is None or not n:
            return "–"
        if c == 0 and n >= floor:
            return "–*"
        return f"{round(c / n * 100)}%"

    rows = [f'<tr><td class="num">{y["year"]}{"†" if S.partial(y) else ""}</td>'
            f'<td class="num">{_n((y.get("arrests") or {}).get("total"))}</td>'
            f'<td class="num">{_n((y.get("arrests") or {}).get("drugs"))}</td>'
            f'<td class="num">{_n((y.get("arrests") or {}).get("dui"))}</td>'
            f'<td class="num">{_n((y.get("arrests") or {}).get("violent"))}</td>'
            f'<td class="num">{pct(y.get("cleared_violent"), y.get("violent"), 10)}</td>'
            f'<td class="num">{pct(y.get("cleared_property"), y.get("property"), 20)}</td>'
            f'<td class="num">{_n(y.get("officers_assaulted"))}</td></tr>' for y in ys]
    if not rows:
        return '<p class="empty">No police-work figures reported.</p>'
    return ('<div class="dir-table-wrap"><table class="dir"><thead><tr><th class="num">Year</th><th class="num">Arrests</th>'
            '<th class="num">Drug</th><th class="num">DUI</th><th class="num">Violent-crime arrests</th>'
            '<th class="num">Violent crimes cleared</th><th class="num">Property crimes cleared</th>'
            '<th class="num">Officers assaulted</th></tr></thead><tbody>' + "".join(rows) + '</tbody></table></div>'
            '<p class="table-note">"Cleared" means the FBI counts the case as closed, usually by an arrest. Arrests include '
            "people who don't live in the city. A dash means the department didn't report that figure. † Partial year. "
            "* Zero clearances reported against 10 or more violent or 20 or more property crimes, which almost certainly "
            f"means clearances weren't reported. {fmt.credit(FBI_URL)}</p>")


def stats_table(D, town):
    rows = [s for s in D["safety"]["policing"].get("stats") or [] if str(s.get("agency", "")).startswith(town)]
    if not rows:
        return ""

    def value(s):
        u = s.get("unit") or ""
        if re.search(r"percent", u, re.I):
            return f"{fmt.num(s['value'])}%"
        if "USD" in u:
            return f"${fmt.num(s['value'])}"
        return fmt.num(s["value"])

    body = []
    for s in sorted(rows, key=lambda s: -(s.get("year") or 0)):
        note = f'<span class="sub">{esc(fmt.public(s["note"]))}</span>' if s.get("note") else ""
        body.append(f'<tr><td>{esc(S.pretty(s["metric"]))}{note}</td><td class="num">{s.get("year") or "–"}</td>'
                    f'<td class="num">{value(s)}</td><td>{fmt.pub(s.get("source"))}</td></tr>')
    return ('<h3 class="gh">Other published figures</h3><div class="dir-table-wrap"><table class="dir"><thead><tr>'
            '<th>Measure</th><th class="num">Year</th><th class="num">Value</th><th>Source</th></tr></thead>'
            f'<tbody>{"".join(body)}</tbody></table></div>')


# --------------------------------------------------------------------------- /crime/


def crime_hub(D, R):
    y0, y1 = fbi_years(D)
    safety = D["safety"]
    rows = {r["town"]: r for r in S.home_crime_rows(D)}
    answers = "".join(
        f'<div class="ans" data-town="{esc(t)}"><p>{S.short_answer(D, t)} '
        f'<a class="go" href="{rel(R, "/crime/" + TOWN_SLUGS[t] + "/")}">Full report ›</a></p></div>' for t in CORE_TOWNS)
    short = (f'<div class="answers" id="answers">{answers}</div>{small_note(D, CORE_TOWNS)}{fbi_credit()}')
    vf = S.violent_finding(D)
    pf, pnote = S.property_finding(D)
    violent = (f'<p class="finding">{esc(vf)}</p><p class="chatter">Violent crimes per 1,000 residents, as each department '
               'reported them to the FBI. Every panel uses the same scale.</p>'
               f'<div class="multiples">{charts.svg_panels(safety["fbi"], "violent", "--inc-violent", "Violent crimes")}</div>'
               f'{fbi_credit(" · Hollow dots are partial-year reports")}')
    prop = (f'<p class="finding">{esc(pf)}</p><p class="chatter">Property crimes per 1,000 residents. Every panel uses '
            'the same scale.</p>'
            f'<div class="multiples">{charts.svg_panels(safety["fbi"], "property", "--inc-property", "Property crimes")}</div>'
            f'<p class="fine">{esc(pnote)}</p>{fbi_credit(" · Hollow dots are partial-year reports")}')
    latest = inc_list(D)
    blot = ('<div class="blotter">' + "".join(entry(D, R, i, iid) for i, iid in latest[:5]) + "</div>"
            f'<p><a class="go" href="{rel(R, "/crime/blotter/")}">All {fmt.num(len(latest))} incidents in the police '
            'blotter ›</a></p>')
    cy0, cy1 = S.crash_years(D)
    crash = (f'<p>{esc(S.crash_lead(D)[0])}</p>'
             f'<p><a class="go" href="{rel(R, "/crashes/")}">Serious and fatal crashes, {cy0}–{cy1} ›</a></p>')
    depts = "".join(
        f'<li><a class="go" href="{rel(R, "/crime/" + TOWN_SLUGS[t] + "/")}">{esc(t)} ›</a>'
        f'<span class="dl-row"><b>{rows[t]["word"]}.</b> Violent crime: {rows[t]["text"]}.</span></li>'
        for t in CORE_TOWNS if t in rows)
    srcs = [FBI_URL, safety["crashes"].get("source")] + [i.get("src") for i, _ in latest]
    body = (
        '<div class="page crime-hub">'
        f"<h1>{esc(R.h1)}</h1>{dateline(D, R, f'FBI figures through {y1}')}"
        f'<div class="top-grid">{numbers_line(D, R)}'
        + sec("short", "The short answer", short, "top-main") + "</div>"
        + sec("side", "The latest year, side by side", box_score(D, R))
        + "<!--AD:mid-->"
        + sec("violent", f"Violent crime since {y0}", violent)
        + sec("property", f"Property crime since {y0}", prop)
        + sec("latest", "Latest in the police blotter", blot)
        + sec("crashes", "Serious crashes", crash)
        + sec("depts", "Department reports", f'<ul class="dept-links">{depts}</ul>')
        + f'<details class="about-data" id="about"><summary>About these numbers</summary>{method_html(D)}</details>'
        + "<!--AD:end-->"
        + sources_line(srcs)
        + "</div>")
    ld = fbi_dataset(D, R, "Crime reported by New Kensington, Arnold and Lower Burrell police",
                     "the New Kensington, Arnold and Lower Burrell police departments")
    return {"body": body, "jsonld": [ld]}


# --------------------------------------------------------------------------- /crime/<town>/


def interactions_html(D, R, town):
    items = S.merged_interactions(D, town)
    out = []
    for it, inc, iid in items:
        srcs = [it.get("source")] + ([inc.get("src")] if inc else [])
        where = f" · {esc(fmt.public(it['location_text']))}" if it.get("location_text") else ""
        mapit = f' · <a href="{rel(R, "/map/")}?inc={esc(iid)}">Map it</a>' if iid else ""
        out.append(f'<article class="entry"><p class="bl"><b class="what">{esc(fmt.end_stop(S.pretty(it.get("kind"))))}</b> '
                   f'{esc(fmt.public(it.get("summary")))}</p>'
                   f'<p class="meta"><time datetime="{esc(it.get("date"))}">{esc(fmt.ap_date(it.get("date")))}</time>'
                   f'{where}{mapit} · {fmt.credit(srcs)}</p></article>')
    wapo, wurl = S.wapo_sentence(D, town)
    intro = ("<p class=\"chatter\">Shootings, use of force, lawsuits, staffing, policy changes and programs reported in "
             "the news, newest first. Where the same event is also on the police blotter, it is shown once here with "
             "both sources.</p>")
    lst = f'<div class="blotter">{"".join(out)}</div>' if out else '<p class="empty">None reported in our sources.</p>'
    return (intro + lst + f'<p class="wapo">{esc(wapo)} {fmt.credit(wurl)}</p>' + stats_table(D, town))


def crime_dept(D, R):
    town = SLUG_TOWNS[R.arg]
    safety = D["safety"]
    y0, y1 = fbi_years(D)
    ag = S.agency(D, town)
    one = (town,)
    lead = f'<p class="lead">{S.short_answer(D, town)}</p>{small_note(D, one)}{fbi_credit()}'
    violent = (f'<p class="finding">{esc(S.record_high_low(D, town))}</p>'
               f'<div class="multiples one">{charts.svg_panels(safety["fbi"], "violent", "--inc-violent", "Violent crimes", towns=one)}</div>'
               f'<p>{S.gaps_sentence(D, town)}</p>'
               f'{fbi_credit(" · A hollow dot is a partial-year report")}')
    prop = (f'<p class="finding">{S.property_dept(D, town)}</p>'
            f'<div class="multiples one">{charts.svg_panels(safety["fbi"], "property", "--inc-property", "Property crimes", towns=one)}</div>'
            f'<p>{esc(S.record_high_low(D, town, "property", "property crime rate"))}</p>'
            f'{fbi_credit(" · A hollow dot is a partial-year report")}')
    oy = S.offense_year(ag)
    reported = f'<p>{S.offense_sentence(D, town)}</p>{offense_table(D, town)}'
    solved = (f'<p>{S.clearance(D, town)}</p><p class="fine">“Cleared” means the FBI counts the case as closed, '
              'usually by an arrest.</p>' + fbi_credit())
    arrests = (f'<p>{S.arrests_sentence(D, town)} Arrests include people who don\'t live in the city.</p>'
               f'<div class="multiples one">{charts.svg_panels(safety["fbi"], lambda y: (y.get("arrests") or {}).get("total"), "--inc-police", "Arrests", towns=one)}</div>'
               + fbi_credit())
    otext, osrc = S.officers(D, town)
    officers = f"<p>{otext}</p>" + fmt.credit_line(osrc)
    merged = S.merged_incident_ids(D)
    mine = [(i, iid) for i, iid in inc_list(D) if i.get("t") == town]
    shown = [(i, iid) for i, iid in mine if iid not in merged][:10]
    q = quote_plus(town)
    incs = ('<p class="chatter">Incidents local news reported with a street location, newest first. They are a sample, '
            'not every police call.</p>'
            f'<div class="blotter">{"".join(entry(D, R, i, iid) for i, iid in shown)}</div>'
            f'<p><a class="go" href="{rel(R, "/crime/blotter/")}?town={q}">All {fmt.num(len(mine))} in {esc(town)} on the '
            'police blotter ›</a></p>')
    crash = (f'<p>{esc(S.crash_town_sentence(D, town))}</p>{fmt.credit_line(safety["crashes"].get("source"))}'
             f'<p><a class="go" href="{rel(R, "/crashes/")}">Serious and fatal crashes ›</a></p>')
    srcs = ([FBI_URL] + [it.get("source") for it, _, _ in S.merged_interactions(D, town)]
            + [i.get("src") for i, _ in mine] + [safety["crashes"].get("source")])
    body = (
        f'<div class="page crime-dept">'
        f"<h1>{esc(R.h1)}</h1>{dateline(D, R, f'FBI figures through {y1}')}"
        f'<div class="top-grid">{contact_box(D, R, town)}<div class="top-main">{lead}</div></div>'
        + sec("violent", f"Violent crime since {y0}", violent)
        + sec("property", "Property crime", prop)
        + "<!--AD:mid-->"
        + (sec("reported", f"What was reported in {oy['year']}", reported) if oy else "")
        + sec("solved", "How many were solved", solved)
        + sec("arrests", "Arrests", arrests)
        + sec("officers", "Officers", officers)
        + sec("police", "Police shootings, lawsuits and policy changes", interactions_html(D, R, town))
        + sec("incidents", "Incidents reported in the news", incs)
        + sec("crashes", f"Serious crashes in {esc(town)}", crash)
        + f'<details class="tableview" id="years"><summary>Every year as a table</summary>{fbi_table(D, town)}</details>'
        + f'<details class="tableview" id="work"><summary>Police work, by the FBI\'s count</summary>{police_work(D, town)}</details>'
        + "<!--AD:end-->"
        + sec("how", "How these numbers are made", method_html(D), "about-data")
        + sources_line(srcs)
        + "</div>")
    ld = fbi_dataset(D, R, f"Crime reported by the {(ag or {}).get('agency') or town + ' Police Department'}",
                     f"the {town} Police Department")
    return {"body": body, "crumbs": [("Crime", "/crime/"), (town, None)], "jsonld": [ld]}


# --------------------------------------------------------------------------- /crime/blotter/


def blotter(D, R):
    safety = D["safety"]
    pairs = inc_list(D)
    merged = S.merged_incident_ids(D)
    kinds = {iid: i.get("k") for i, iid in pairs}
    counts = {k: sum(1 for i, _ in pairs if i.get("c") == k) for k in CAT}
    years = sorted({str(i.get("d"))[:4] for i, _ in pairs}, reverse=True)
    chips = (f'<button type="button" data-c="*" aria-pressed="true">All <span class="n">{fmt.num(len(pairs))}</span></button>'
             + "".join(f'<button type="button" data-c="{k}" aria-pressed="false"><span class="inc-key" '
                       f'style="background:var(--inc-{k})"></span>{v} <span class="n">{fmt.num(counts[k])}</span></button>'
                       for k, v in CAT.items()))
    towns = "".join(f"<option>{esc(t)}</option>" for t in CORE_TOWNS)
    yopts = "".join(f"<option>{y}</option>" for y in years)
    filters = (
        '<div class="inc-filters" id="inc-filters" role="group" aria-label="Filter incidents" hidden>'
        f'<div class="picker cats">{chips}</div>'
        '<div class="frow"><label class="fl">Town<select id="inc-town"><option value="">All towns</option>'
        f'{towns}</select></label><label class="fl">Year<select id="inc-year"><option value="">All years</option>{yopts}'
        '</select></label><label class="fl st">Street<input id="inc-street" type="search" placeholder="A street, like Leishman" '
        'autocomplete="off" spellcheck="false"></label></div>'
        '<label class="near"><input type="checkbox" id="inc-near" disabled> Include incidents within a block (400 ft)</label>'
        "</div>")
    groups = []
    for y in years:
        es = "".join(entry(D, R, i, iid, xref_html(D, R, iid, merged.get(iid), kinds[iid]))
                     for i, iid in pairs if str(i.get("d"))[:4] == y)
        groups.append(f'<section class="inc-yr" data-yr="{y}" aria-labelledby="y{y}-h"><h2 class="yr-h" id="y{y}-h">{y}</h2>'
                      f'<div class="blotter">{es}</div></section>')
    n = len(pairs)
    last = pairs[0][0].get("d") if pairs else None
    first_year = min((int(str(i.get("d"))[:4]) for i, _ in pairs), default=None)
    per_town = S.join_and(f"{fmt.num(sum(1 for i, _ in pairs if i.get('t') == t))} in {t}" for t in CORE_TOWNS)
    note = ('<p class="note"><b>About this list.</b> These are incidents local news reported with a street location since '
            f'{first_year}: {per_town}. They are a sample, not every police call. No suspects, victims or line officers are '
            'named, and locations are rounded to the hundred-block, an intersection or a named place, or placed on the '
            'street only. An arrest or charge is not a conviction.</p>')
    block = (
        f'<div id="inc-block">{filters}'
        f'<p class="count" id="inc-count" role="status">{fmt.num(n)} incidents with a mappable location</p>'
        f'<p class="inc-map-p"><a class="go" id="inc-map" href="{rel(R, "/map/")}?layer=incidents">Show these on the map ›</a></p>'
        '<p class="empty" id="inc-none" hidden>No incidents match these filters.</p>'
        f'<div id="inc-list">{"".join(groups)}</div></div>')
    srcs = [i.get("src") for i, _ in pairs]
    body = (f'<div class="page blotter-page"><h1>{esc(R.h1)}</h1>'
            f'{dateline(D, R, "Newest incident " + fmt.ap_date(last) if last else "Police blotter")}{note}'
            f"{block}{sources_line(srcs)}</div>")
    return {"body": body, "crumbs": [("Crime", "/crime/"), ("Police blotter", None)]}


# --------------------------------------------------------------------------- /crashes/


def crashes(D, R):
    cr = D["safety"]["crashes"]
    y0, y1 = S.crash_years(D)
    src = cr.get("source")
    lead = f'<p class="lead">{esc(" ".join(S.crash_lead(D)))}</p>{fmt.credit_line(src)}'
    st = cr.get("stats") or []
    years = list(range(y0, y1 + 1))
    by = {(r["t"], r["year"]): r for r in st}
    tot = {t: S.crash_totals(D, t) for t in CORE_TOWNS}
    last5 = {t: S.crash_totals(D, t, y1 - 4) for t in CORE_TOWNS}
    totals = ('<div class="dir-table-wrap"><table class="dir"><thead><tr><th>Town</th>'
              f'<th class="num">Crashes {y0}–{y1}</th><th class="num">Killed</th><th class="num">Seriously injured</th>'
              f'<th class="num">Crashes {y1 - 4}–{y1}</th></tr></thead><tbody>'
              + "".join(f'<tr><td>{esc(t)}</td><td class="num">{fmt.num(tot[t]["crashes"])}</td>'
                        f'<td class="num">{fmt.num(tot[t]["fatal"])}</td><td class="num">{fmt.num(tot[t]["serious"])}</td>'
                        f'<td class="num">{fmt.num(last5[t]["crashes"])}</td></tr>' for t in CORE_TOWNS)
              + "</tbody></table></div>")
    every = ('<div class="dir-table-wrap"><table class="dir"><thead><tr><th class="num">Year</th>'
             + "".join(f'<th class="num">{esc(t)}</th>' for t in CORE_TOWNS) + "</tr></thead><tbody>"
             + "".join(f'<tr><td class="num">{y}</td>' + "".join(
                 f'<td class="num">{by[(t, y)]["crashes"]} ({by[(t, y)]["fatal"]} killed)</td>' if (t, y) in by
                 else '<td class="num">0</td>' for t in CORE_TOWNS) + "</tr>" for y in reversed(years))
             + "</tbody></table></div>")
    worst = max(years, key=lambda y: (sum(by[(t, y)]["crashes"] for t in CORE_TOWNS if (t, y) in by), -y))
    worst_n = sum(by[(t, worst)]["crashes"] for t in CORE_TOWNS if (t, worst) in by)
    by_town = (f'<p class="chatter">Police-reported crashes that killed or seriously injured someone, {y0}–{y1}. '
               'Every panel uses the same scale.</p>'
               f'<div class="multiples">{charts.svg_panels(charts.crash_series(cr), "crashes", "--ink-2", "Crashes", count=True)}</div>'
               f'{fmt.credit_line(src)}'
               f'<p>The worst year in the record was {worst}, with {fmt.num(worst_n)} such crashes across the three cities.</p>'
               f'<div class="gap">{totals}</div>'
               f'<details class="tableview"><summary>Every year as a table</summary>{every}</details>')
    pts = cr.get("points") or []
    snapped = S.snap_crashes(D)
    matched = sum(1 for _, r in snapped if r)
    roads = S.crash_roads(D)[:8]
    road_rows = "".join(
        f'<tr><td>{fmt.street_head(r["road"])}</td><td>{esc(S.join_and(r["towns"]))}</td>'
        f'<td class="num">{fmt.num(r["n"])}</td><td class="num">{fmt.num(r["killed"])}</td></tr>' for r in roads)
    roads_html = (
        f'<p>To count crashes by road, each of the {fmt.num(len(pts))} crashes with a mapped location is matched to the '
        'nearest named road in the map data, if one is within 100 feet (30 m). These road counts use only the mapped '
        f'crashes; the totals above come from PennDOT\'s yearly counts, which also include {fmt.num(cr.get("unmapped") or 0)} '
        'crashes with no recorded location.</p>'
        '<div class="dir-table-wrap"><table class="dir"><thead><tr><th>Road</th><th>Where</th><th class="num">Crashes</th>'
        f'<th class="num">Killed</th></tr></thead><tbody>{road_rows}</tbody></table></div>'
        f'<p>Of the {fmt.num(len(pts))} crashes with a mapped location, {fmt.num(matched)} were matched to a named road; '
        f'{fmt.num(len(pts) - matched)} couldn\'t be matched to a named road within 100 feet.</p>'
        + fmt.credit_line(src))
    types = S.crash_types(D)
    top = types[:5]
    rest = types[5:]
    phr = [f"{COLLISION.get(c, c.lower() + ' crashes')} ({fmt.num(n)})" for c, n, _, _ in top]
    kind_s = f"The most common were {S.join_and(phr)}."
    if rest:
        kind_s += (f" The other {fmt.num(sum(r[1] for r in rest))} were "
                   f"{S.join_and(COLLISION.get(c, c.lower() + ' crashes') for c, *_ in rest)}.")
    deadliest = max(types, key=lambda r: (r[2], r[1]))
    kind_s += f" {fmt.cap(COLLISION.get(deadliest[0], deadliest[0].lower() + ' crashes'))} killed the most people, {fmt.num(deadliest[2])}."
    per = [r for r in types if r[1] >= 5]
    if per:
        worst_rate = max(per, key=lambda r: r[2] / r[1])
        if worst_rate[0] != deadliest[0]:
            kind_s += (f" For their number, {COLLISION.get(worst_rate[0], worst_rate[0].lower() + ' crashes')} were the "
                       f"deadliest: {fmt.num(worst_rate[2])} people died in {fmt.num(worst_rate[1])} of them.")
    ped = next((r for r in types if r[0] == "Hit pedestrian"), None)
    if ped:
        kind_s += (f" {S.lead_num(ped[1])} of the mapped crashes hit a pedestrian; those crashes killed "
                   f"{fmt.num(ped[2])} {S.plural(ped[2], 'person', 'people')}.")
    type_rows = "".join(f'<tr><td>{esc(c)}</td><td class="num">{fmt.num(n)}</td><td class="num">{fmt.num(k)}</td>'
                        f'<td class="num">{fmt.num(s)}</td></tr>' for c, n, k, s in types)
    kinds = (f"<p>{esc(kind_s)}</p>"
             '<div class="dir-table-wrap"><table class="dir"><thead><tr><th>Collision type</th><th class="num">Crashes</th>'
             f'<th class="num">Killed</th><th class="num">Seriously injured</th></tr></thead><tbody>{type_rows}</tbody>'
             f'</table></div><p class="table-note">Mapped crashes only, by the collision type police recorded. '
             f'{fmt.credit(src)}</p>')
    l5 = S.crash_totals(D, since_year=y1 - 4)
    p5 = {k: sum(r[k] for r in st if y1 - 9 <= r["year"] <= y1 - 5) for k in ("crashes", "fatal")}
    split = S.join_and(f"{fmt.num(last5[t]['crashes'])} in {t}" for t in
                       sorted(CORE_TOWNS, key=lambda t: (-last5[t]["crashes"], CORE_TOWNS.index(t))))
    recent = (f"<p>From {y1 - 4} through {y1} there were {fmt.num(l5['crashes'])} such crashes, which killed "
              f"{fmt.num(l5['fatal'])} {S.plural(l5['fatal'], 'person', 'people')}: {split}. "
              f"In the five years before, {y1 - 9} through {y1 - 5}, there were {fmt.num(p5['crashes'])}, which killed "
              f"{fmt.num(p5['fatal'])}.</p>" + fmt.credit_line(src))
    about = (f"<p>{esc(fmt.public(cr.get('notes')))}</p>"
             "<p>Only crashes that killed someone or left someone with a suspected serious injury are here; crashes with "
             "minor injuries or damage only are not. Each crash is counted in the city where PennDOT's records place it. "
             f"{fmt.num(cr.get('unmapped') or 0)} of the {fmt.num(sum(r['crashes'] for r in st))} crashes have no recorded "
             "location, so they are in the totals but not on the map or in the road and collision counts.</p>"
             f'{fmt.credit_line(src)}'
             f'<p><a class="go" href="{rel(R, "/map/")}?layer=crashes">See them on the map ›</a></p>')
    body = (
        '<div class="page crashes-page">'
        f"<h1>{esc(R.h1)}</h1>{dateline(D, R, f'PennDOT records, {y0}–{y1}')}{lead}"
        + sec("by-town", "By town and year", by_town)
        + sec("roads", "Roads with the most serious crashes", roads_html)
        + "<!--AD:mid-->"
        + sec("kinds", "What kind of crashes", kinds)
        + sec("recent", "The last five years", recent)
        + sec("about", "What this data does and doesn't include", about)
        + "<!--AD:end-->"
        + sources_line([src])
        + "</div>")
    ld = dataset(D, R, f"Serious and fatal crashes in New Kensington, Arnold and Lower Burrell, {y0}–{y1}",
                 "Police-reported crashes that killed or seriously injured someone in the three cities of ZIP 15068, by "
                 "town, year, road and collision type, from PennDOT crash records (the bencarneiro/ntsb mirror).",
                 (y0, y1), [src], ["traffic crashes", "PennDOT", "road safety", "15068"])
    return {"body": body, "crumbs": [("Crime", "/crime/"), ("Serious crashes", None)], "jsonld": [ld]}
