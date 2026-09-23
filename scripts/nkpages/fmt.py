"""Text helpers shared by every page: escaping, numbers, AP dates, outlet credits, phone links,
street names and the public() filter that research text must pass through before it reaches HTML."""
import datetime as _dt
import html
import re
import unicodedata
from urllib.parse import urlparse

# --------------------------------------------------------------------------- basics


def esc(s):
    return html.escape("" if s is None else str(s), quote=True)


def num(n, d=0):
    if n is None:
        return "–"
    if d:
        return f"{n:,.{d}f}"
    return f"{int(round(n)):,}"


def cap(s):
    s = str(s or "")
    return s[:1].upper() + s[1:]


def end_stop(s):
    s = str(s or "").strip()
    return s if re.search(r"[.!?]$", s) else s + "."


def slug(s):
    s = unicodedata.normalize("NFKD", str(s or "")).encode("ascii", "ignore").decode().lower()
    return re.sub(r"[^a-z0-9]+", "-", s).strip("-")


def words(html_text):
    """Visible word count of an HTML fragment (scripts, styles, templates and [hidden] removed)."""
    t = re.sub(r"<(script|style|template)\b.*?</\1>", " ", html_text, flags=re.S | re.I)
    t = re.sub(r"<[^>]+\bhidden\b[^>]*>.*?</[a-z0-9]+>", " ", t, flags=re.S | re.I)
    t = re.sub(r"<[^>]+>", " ", t)
    t = html.unescape(t)
    return len(re.findall(r"[A-Za-z0-9][\w'’.-]*", t))


# --------------------------------------------------------------------------- dates (AP style)

AP_MONTHS = ["Jan.", "Feb.", "March", "April", "May", "June", "July", "Aug.", "Sept.", "Oct.", "Nov.", "Dec."]
AP_DAYS = ["Mon.", "Tues.", "Wed.", "Thurs.", "Fri.", "Sat.", "Sun."]
DAYS = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]


def _d(d):
    if isinstance(d, _dt.datetime):
        return d.date()
    if isinstance(d, _dt.date):
        return d
    return _dt.date.fromisoformat(str(d)[:10])


def ap_date(s, approx=False):
    """'2026-09' -> 'Sept. 2026'; '2026-09-23' -> 'Sept. 23, 2026'; '2026' -> '2026'.
    approx=True -> 'About Sept. 2026' (never the internal '(month approximate)')."""
    m = re.match(r"^(\d{4})(?:-(\d{1,2})(?:-(\d{1,2}))?)?", str(s or ""))
    if not m:
        return str(s or "")
    y, mo, dd = m.group(1), m.group(2), m.group(3)
    if mo and 1 <= int(mo) <= 12:
        out = f"{AP_MONTHS[int(mo) - 1]} {int(dd)}, {y}" if dd else f"{AP_MONTHS[int(mo) - 1]} {y}"
    else:
        out = y
    return ("About " + out) if approx else out


def ap_day(d):
    """'Fri., Sept. 25'"""
    d = _d(d)
    return f"{AP_DAYS[d.weekday()]}, {AP_MONTHS[d.month - 1]} {d.day}"


def ap_long(d, year=True):
    """'Friday, Sept. 25, 2026'"""
    d = _d(d)
    s = f"{DAYS[d.weekday()]}, {AP_MONTHS[d.month - 1]} {d.day}"
    return s + f", {d.year}" if year else s


def ap_time(t):
    """datetime/time -> '9:15 a.m.', '5 p.m.', 'noon'."""
    h, mi = t.hour, t.minute
    if h == 12 and mi == 0:
        return "noon"
    suf = "a.m." if h < 12 else "p.m."
    h12 = h % 12 or 12
    return f"{h12}:{mi:02d} {suf}" if mi else f"{h12} {suf}"


# --------------------------------------------------------------------------- credits by outlet name

PUBS = {
    "wpxi.com": "WPXI", "cbsnews.com": "CBS News Pittsburgh", "post-gazette.com": "Pittsburgh Post-Gazette", "wesa.fm": "WESA",
    "spotlightpa.org": "Spotlight PA", "pittsburghmagazine.com": "Pittsburgh Magazine", "en.wikipedia.org": "Wikipedia",
    "britannica.com": "Britannica", "loc.gov": "Library of Congress", "hmdb.org": "Historical Marker Database",
    "parnassuspen.com": "Parnassus Pen", "crimewatch.net": "CrimeWatch", "policescorecard.org": "Police Scorecard",
    "census.gov": "Census Bureau", "censusreporter.org": "Census Reporter", "datausa.io": "Data USA",
    "cityofarnoldpa.org": "City of Arnold", "cityoflowerburrell.com": "City of Lower Burrell",
    "westmorelandcountypa.gov": "Westmoreland County", "engage.rideprt.org": "Pittsburgh Regional Transit",
    "newkensingtonpa.org": "City of New Kensington", "lowerburrellpolice.org": "Lower Burrell police",
    "newkenredevelopment.org": "New Kensington Redevelopment Authority", "peopleslibrary.org": "Peoples Library",
    "usps.com": "USPS", "tools.usps.com": "USPS", "nces.ed.gov": "National Center for Education Statistics",
    "myreadylink.com": "ReadyLink", "overturemaps.org": "Overture Maps",
    "animalprotectors.net": "Animal Protectors", "westmorelandhumanesociety.com": "Humane Society of Westmoreland County",
    "aspca.org": "ASPCA", "petcolove.org": "Petco Love", "findtobyinpa.org": "Find Toby in PA", "avets.com": "AVETS",
    "bluepearlvet.com": "BluePearl", "aaha.org": "AAHA", "pawboost.com": "PawBoost", "guidestar.org": "GuideStar",
    "mentalhealth.networkofcare.org": "Network of Care",
}
AGGREGATORS = {"citizenportal.ai", "hoodline.com"}


def host(u):
    try:
        return urlparse(u).hostname.lower().removeprefix("www.")
    except Exception:
        return ""


def pub_name(u):
    """Exact port of app.js pubName(): the outlet's name, else the bare hostname. Never invents a name."""
    try:
        p = urlparse(u)
    except Exception:
        return ""
    if not p.hostname:
        return ""
    h = p.hostname.lower().removeprefix("www.")
    path = (p.path or "").lower()
    if h == "triblive.com" and "/valley-news-dispatch/" in path:
        return "Valley News Dispatch (TribLive)"
    if h == "community.triblive.com":
        return "TribLive community news"
    if h == "archive.triblive.com":
        return "Tribune-Review archive"
    if h == "triblive.com" or h.endswith(".triblive.com"):
        return "TribLive"
    if h in PUBS:
        return PUBS[h]
    if h == "pa.gov" and path.startswith("/agencies/pda"):
        return "PA Dept. of Agriculture"
    if h.endswith(".crimewatchpa.com"):
        return "CrimeWatch"
    if h in ("github.com", "raw.githubusercontent.com"):
        if path.startswith("/jacobkap/"):
            return "FBI UCR via Jacob Kaplan"
        if path.startswith("/bencarneiro/ntsb"):
            return "PennDOT crash data"
        if h == "raw.githubusercontent.com" and path.startswith("/washingtonpost/"):
            return "Washington Post"
        return "GitHub dataset"
    return h


def pub(u):
    if not u:
        return ""
    return f'<a class="cr" href="{esc(u)}" target="_blank" rel="noopener">{esc(pub_name(u) or "source")}</a>'


def credit(urls, pre="Source: "):
    if isinstance(urls, str):
        urls = [urls]
    seen, out = set(), []
    for u in urls or []:
        if not u:
            continue
        n = pub_name(u)
        if not n or n in seen:
            continue
        seen.add(n)
        out.append(pub(u))
    return (pre + ", ".join(out)) if out else ""


def credit_line(urls, pre="Source: ", tag="p"):
    c = credit(urls, pre)
    return f'<{tag} class="credit">{c}</{tag}>' if c else ""


# --------------------------------------------------------------------------- phone numbers

_PHONE = re.compile(r"\(?\b(\d{3})\)?[-. ]?(\d{3})[-. ](\d{4})\b|\b911\b")


def tel(text):
    """'724-339-7533 or 724-339-7534' -> [('724-339-7533','tel:+17243397533'), ('724-339-7534', ...)];
    '911' -> [('911','tel:911')]."""
    out = []
    for m in _PHONE.finditer(str(text or "")):
        if m.group(0) == "911":
            out.append(("911", "tel:911"))
        else:
            a, b, c = m.group(1), m.group(2), m.group(3)
            out.append((f"{a}-{b}-{c}", f"tel:+1{a}{b}{c}"))
    return out


def tel_link(text, label=None, cls="tel", aria=None, keep=False):
    """One tap-to-call button for the first number in text. label may contain {n} for the number."""
    t = tel(text)
    if not t:
        return ""
    shown, href = t[0]
    lab = (label or "Call {n}").replace("{n}", shown)
    a = f' aria-label="{esc(aria)}"' if aria else ""
    k = " data-keep-above" if keep else ""
    return f'<a class="{cls}" href="{href}"{a}{k}>{esc(lab)}</a>'


def tel_links(text, first_label="Call {n}", more_prefix="or "):
    """Primary button for the first number, small 'or 724-…' links for the rest."""
    t = tel(text)
    if not t:
        return ""
    out = [f'<a class="tel" href="{t[0][1]}">{esc(first_label.replace("{n}", t[0][0]))}</a>']
    for shown, href in t[1:]:
        out.append(f'<span class="tel-alt">{more_prefix}<a href="{href}">{esc(shown)}</a></span>')
    return " ".join(out)


# --------------------------------------------------------------------------- streets

ORD = {"first": "1", "second": "2", "third": "3", "fourth": "4", "fifth": "5", "sixth": "6", "seventh": "7", "eighth": "8",
       "ninth": "9", "tenth": "10", "eleventh": "11", "twelfth": "12", "thirteenth": "13", "fourteenth": "14",
       "fifteenth": "15", "sixteenth": "16", "seventeenth": "17", "eighteenth": "18", "nineteenth": "19", "twentieth": "20"}
TYPES = {"street": "st", "st": "st", "avenue": "ave", "ave": "ave", "av": "ave", "road": "rd", "rd": "rd", "drive": "dr",
         "dr": "dr", "boulevard": "blvd", "blvd": "blvd", "lane": "ln", "ln": "ln", "court": "ct", "ct": "ct", "place": "pl",
         "pl": "pl", "way": "way", "alley": "aly", "aly": "aly", "terrace": "ter", "ter": "ter", "highway": "hwy",
         "hwy": "hwy", "pike": "pike", "circle": "cir", "cir": "cir"}


def street_key(name):
    """Exact port of pets.js streetKey(): {'core': '5', 'type': 'ave'} for 'Fifth Avenue' / '5th Ave'."""
    if not name:
        return None
    t = [w for w in re.split(r"\s+", re.sub(r"[.,#']", " ", str(name).lower())) if w]
    t = [ORD.get(w) or re.sub(r"^(\d+)(st|nd|rd|th)$", r"\1", w) for w in t]
    typ = None
    while t and t[-1] in TYPES:
        typ = typ or TYPES[t[-1]]
        t.pop()
    if len(t) > 1 and re.match(r"^(n|s|e|w|north|south|east|west)$", t[0]):
        t.pop(0)
    core = " ".join(t)
    return {"core": core, "type": typ} if core else None


USPS = {"Street": "St", "Avenue": "Ave", "Road": "Rd", "Boulevard": "Blvd", "Drive": "Dr", "Lane": "Ln", "Place": "Pl",
        "Court": "Ct", "Alley": "Aly"}
_SUFFIX = re.compile(r"\b(Street|Avenue|Road|Boulevard|Drive|Lane|Place|Court|Alley)\b")


def short_addr(a):
    """'956 Fifth Ave, New Kensington, PA 15068' -> '956 Fifth Ave'"""
    return _SUFFIX.sub(lambda m: USPS[m.group(1)], str(a or "").split(",")[0])


def street_head(n):
    m = re.match(r"^(.*\S)\s+(Street|Avenue|Road|Boulevard|Drive|Lane|Place|Court|Alley)$", str(n or ""))
    return f"{esc(m.group(1))} <small>{USPS[m.group(2)]}</small>" if m else esc(n)


SHIELDED = {"56", "366", "380", "780"}


def shield(ref):
    r = re.sub(r"^(PA|SR)[\s-]*", "", str(ref).strip(), flags=re.I)
    if r not in SHIELDED:
        return ""
    three = len(r) >= 3
    fs = "8.5" if three else "9.5"
    st = ' style="font-stretch:85%"' if three else ""
    return (f'<svg class="ks" viewBox="0 0 26 24" width="26" height="24" role="img" aria-label="Pennsylvania Route {r}">'
            f'<path d="M2.5 1.5H23.5L21.8 5.2L24 7.4L19 22.5H7L2 7.4L4.2 5.2Z" fill="var(--surface)" stroke="var(--ink)" '
            f'stroke-width="1.3" stroke-linejoin="round"/><text x="13" y="15.6" text-anchor="middle" '
            f'font-family="Radio Canada, Arial, sans-serif" font-weight="700" font-size="{fs}"{st} fill="var(--ink)">{r}</text></svg>')


def routes_html(refs):
    out = []
    for r in refs or []:
        s = shield(r)
        pre = "Route " if re.match(r"^\d+$", str(r)) else ""
        out.append(s or f'<span class="rt">{pre}{esc(r)}</span>')
    return "".join(out)


# --------------------------------------------------------------------------- public(): research text -> page text

_VERIFY_PAREN = re.compile(r"\s*\([^()]*\bverify\b[^()]*\)", re.I)
_DROP_SEG = re.compile(r"\bverify\b|\bvia search\b|search summar", re.I)


def public(text):
    """The only way research text reaches HTML: drops internal 'verify' notes and search-process remarks."""
    t = str(text or "")
    t = _VERIFY_PAREN.sub("", t)
    parts = re.split(r"(;\s*|\s+–\s+)", t)
    kept, i = [], 0
    while i < len(parts):
        seg = parts[i]
        sep = parts[i + 1] if i + 1 < len(parts) else ""
        if seg.strip() and not _DROP_SEG.search(seg):
            kept.append(seg + sep)
        i += 2
    t = "".join(kept)
    t = t.replace("the Wikipedia summary", "Wikipedia")
    t = re.sub(r"\s{2,}", " ", t)
    t = re.sub(r"\s+([,.;:)])", r"\1", t)
    t = re.sub(r"[;–\s]+$", "", t.strip())
    if t and str(text or "").strip().endswith(".") and not t.endswith((".", "!", "?")):
        t += "."
    return t


def is_aggregator_only(sources):
    if isinstance(sources, str):
        sources = [sources]
    hs = [host(u) for u in sources or [] if u]
    return bool(hs) and all(h in AGGREGATORS for h in hs)


# --------------------------------------------------------------------------- incident ids (identical to NKSafety.incIds)


def inc_ids(incidents):
    """'<d>-<slug(l)>' with -2, -3 … on collisions, in array order."""
    seen, out = {}, []
    for i in incidents:
        base = f"{i.get('d', '')}-{slug(i.get('l', ''))}"
        n = seen.get(base, 0) + 1
        seen[base] = n
        out.append(base if n == 1 else f"{base}-{n}")
    return out
