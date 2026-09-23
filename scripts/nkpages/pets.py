"""Lost & found pets: exact ports of site/assets/pets.js (cleanNear, stripHouse, sanitize, parseIssue, streetKey,
buildIndex, geocodeNear), the snapshot posts, and the board markup other pages embed.

Cross-builder API (see contracts.md):
    home_box(D, R)            the complete <section id="pets-box"> for the home page
    town_section(D, R, town)  the "Lost and found pets in {town}" section for a town page
    row_html(post, R, today)  one compact row linking to lost-pets/#gh-N
    open_posts(D)             sanitized, geocoded snapshot posts, newest first ([] without --snapshot)

JavaScript and Python must agree character for character on parse_issue and clean_near (tests/test_pages_pets.py
runs both on tests/fixtures/pet_issues.json), so the regular expressions below spell out JavaScript's semantics:
ASCII \\w, \\b and \\d, JavaScript's \\s set, $ only at the very end, and String.prototype.slice in UTF-16 units.
"""
import datetime as dt
import math
import re

from . import data as ND
from . import fmt
from .fmt import esc
from .shell import rel

REPO = "DonnieCash/15068"
TOWNS = ("New Kensington", "Arnold", "Lower Burrell")
LIMITS = {"name": 40, "desc": 500, "near": 120, "contact": 120, "town": 40, "animal": 20}
STATUS = {"lost": "Lost", "found": "Found", "spotted": "Spotted"}
VERB = {"lost": "Last seen near", "found": "Found near", "spotted": "Seen near"}
FORM_MARK = "### Lost, found or spotted?"

# --------------------------------------------------------------------------- JavaScript semantics

JS_WS = "\t\n\v\f\r \u00a0\u1680\u2000-\u200a\u2028\u2029\u202f\u205f\u3000\ufeff"  # the \s class, inside [...]
S = f"[{JS_WS}]"
AI = re.A | re.I


def js_str(v):
    """String(v ?? "") for the values issues and posts carry."""
    if v is None:
        return ""
    if isinstance(v, bool):
        return "true" if v else "false"
    if isinstance(v, float) and v.is_integer() and abs(v) < 1e21:
        return str(int(v))
    return str(v)


def js_trim(s):
    return re.sub(f"^{S}+|{S}+\\Z", "", s)


def js_slice(s, n):
    """s.slice(0, n) counted in UTF-16 code units, as JavaScript does."""
    b = s.encode("utf-16-le", "surrogatepass")
    return s if len(b) <= 2 * n else b[:2 * n].decode("utf-16-le", "surrogatepass")


def js_round(x):
    return int(math.floor(x + 0.5))


def clip(v, k):
    return js_slice(js_trim(js_str(v)), LIMITS.get(k) or 40)


# --------------------------------------------------------------------------- house numbers never ship

_ROUTE = re.compile(rf"\b(route|rte|pa|sr|us|i)[{JS_WS}-]*(\d{{1,4}})\b", AI)
_BLOCK = re.compile(rf"\b(\d{{0,3}}00){S}+block\b", AI)
_NUM = re.compile(rf"(^|[^\w\u2009])\d{{1,5}}[a-z]?(?:{S}*[-–]{S}*\d{{1,5}}[a-z]?)?(?![\w\u2009])"
                  rf"(?!{S}*(?:st|nd|rd|th)\b)", AI)
_HOUSE = re.compile(rf"(^|[^\w\u2009-])\d{{1,5}}[a-z]?(?:{S}*[-–]{S}*\d{{1,5}}[a-z]?)?"
                    rf"(?={S}+(?:[nsew]\.?{S}+)?(?:\d+(?:st|nd|rd|th)|[a-z]+){S}+"
                    r"(?:street|st|avenue|ave|av|road|rd|drive|dr|boulevard|blvd|lane|ln|way|court|ct|alley|aly|"
                    r"place|pl|terrace|ter|highway|hwy|pike|circle|cir)\b)", AI)


def _protect_routes(t):
    return _ROUTE.sub(lambda m: m.group(1) + "\u2009" + m.group(2), t)


def clean_near(t):
    """Port of cleanNear(): drop standalone numbers and ranges ("1025", "1025-1027", "12B"), keep ordinals ("9th"),
    route numbers ("Route 56", "PA 366") and hundred-blocks ("1000 block")."""
    t = _protect_routes(js_str(t))
    t = _BLOCK.sub(lambda m: "\u2009" + m.group(1) + "\u2009block", t)
    t = _NUM.sub(lambda m: m.group(1), t)
    t = t.replace("\u2009", " ")
    t = re.sub(f"{S}{{2,}}", " ", t)
    t = re.sub(f"^[{JS_WS},&]+|[{JS_WS},]+\\Z", "", t)
    return js_trim(t)


def strip_house(t):
    """Port of stripHouse(): remove a house number that comes right before a street name in free text
    ("found at 1012 Fifth Ave" -> "found at Fifth Ave"); phone numbers, ordinals and routes are kept."""
    t = _protect_routes(js_str(t))
    t = _HOUSE.sub(lambda m: m.group(1), t)
    t = t.replace("\u2009", " ")
    t = re.sub(" {2,}", " ", t)
    return js_trim(t)


# --------------------------------------------------------------------------- sanitize / parseIssue

_ISO_DAY = re.compile(r"[0-9]{4}-[0-9]{2}-[0-9]{2}")
_ISO_TIME = re.compile(r"[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9:.]+Z")
_GH_IMG = re.compile(r"https://(user-images\.githubusercontent\.com|github\.com/user-attachments)/")


def _num(v):
    return isinstance(v, (int, float)) and not isinstance(v, bool) and math.isfinite(v)


def sanitize(p, source, repo=REPO):
    """Port of sanitize(): rebuild a post from an allow-list (posts are untrusted)."""
    if not isinstance(p, dict) or not re.fullmatch(r"lost|found|spotted", js_str(p.get("status"))):
        return None
    animal = p.get("animal")
    out = {
        "id": clip(p.get("id"), "name"), "status": p["status"],
        "animal": animal.lower() if isinstance(animal, str) and re.fullmatch(r"dog|cat|other", animal, AI) else "other",
        "name": clip(p.get("name"), "name"), "desc": strip_house(clip(p.get("desc"), "desc")),
        "near": clean_near(clip(p.get("near"), "near")),
        "town": p["town"] if p.get("town") in TOWNS else "",
        "date": p["date"] if isinstance(p.get("date"), str) and _ISO_DAY.fullmatch(p["date"]) else "",
        "contact": strip_house(clip(p.get("contact"), "contact")),
        "created": p["created"] if isinstance(p.get("created"), str) and _ISO_TIME.fullmatch(p["created"]) else "",
        "source": source,
    }
    x, y = p.get("x"), p.get("y")
    if _num(x) and _num(y) and abs(x) < 2e4 and abs(y) < 2e4:
        out["x"], out["y"] = js_round(x / 10) * 10, js_round(y / 10) * 10
        prec = p.get("prec")
        out["prec"] = prec if isinstance(prec, str) and re.fullmatch(r"intersection|street|picked", prec) else "picked"
        lab = p.get("placeLabel")
        if isinstance(lab, str) and js_trim(lab):
            out["placeLabel"] = clip(lab, "near")
    if source == "github":
        if re.fullmatch(rf"https://github\.com/{re.escape(repo)}/issues/[0-9]+", js_str(p.get("url"))):
            out["url"] = p["url"]
        if _GH_IMG.match(js_str(p.get("photo"))):
            out["photo"] = p["photo"]
    return out


def _field(body, label):
    m = re.search(rf"###{S}*{label}[^\n]*\n+([\s\S]*?)(?=\n###|\Z)", body, AI)
    v = js_trim(m.group(1)) if m else ""
    return "" if v == "_No response_" else v


def is_pet_issue(issue):
    """An open issue made with the lost-found-pet form (pull requests and free-form issues are skipped)."""
    return isinstance(issue, dict) and not issue.get("pull_request") and FORM_MARK in js_str(issue.get("body"))


def parse_issue(issue, repo=REPO):
    """Port of parseIssue(): a GitHub issue made with the lost-found-pet form -> a sanitized post, or None."""
    body = js_str(issue.get("body")) or ""
    field = lambda label: _field(body, label)  # noqa: E731
    ts = re.match(rf"{S}*\[(lost|found|spotted)\]", js_str(issue.get("title")), AI)
    status = (field("Lost, found or spotted") or (ts.group(1) if ts else "") or "").lower()
    if not re.fullmatch(r"lost|found|spotted", status):
        return None
    im = (re.search(rf"!\[[^\]]*\]\((https://[^){JS_WS}]+)\)", body) or re.search(r'<img[^>]+src="(https://[^"]+)"', body))
    return sanitize({
        "id": "gh-" + js_str(issue.get("number")), "url": issue.get("html_url"), "status": status,
        "animal": (field("Animal") or "Other").lower(), "name": field("Pet's name"),
        "desc": js_trim(re.sub(r"!\[[^\]]*\]\([^)]*\)|<img[^>]*>", "", field("Description"))),
        "near": field("Last seen near"), "town": field("Town"),
        "date": field("Date") or js_str(issue.get("created_at"))[:10], "contact": field("How to reach you"),
        "photo": im.group(1) if im else "",
        "created": issue.get("created_at"),
    }, "github", repo)


# --------------------------------------------------------------------------- street matching and geocoding

street_key = fmt.street_key


def _flat(pts):
    if pts and isinstance(pts[0], (tuple, list)):
        return [c for p in pts for c in p]
    return list(pts)


def build_index(lines):
    """Port of buildIndex(): {core: [{type, pts (flat x,y list), n}]} in road order."""
    idx = {}
    for ln in lines or []:
        if not ln.get("n"):
            continue
        k = street_key(ln["n"])
        if not k:
            continue
        idx.setdefault(k["core"], []).append({"type": k["type"], "pts": _flat(ln["pts"]), "n": ln["n"]})
    return idx


_SPLIT = re.compile(rf"{S}*(?:&|\band\b|\bat\b|/|@|,|\bnear\b){S}*", AI)


def geocode_near(text, idx, streets, town):
    """Port of geocodeNear(): "Fifth Avenue & 9th Street" -> {x, y, prec, label} from the road lines."""
    parts = [s for s in (js_trim(s) for s in _SPLIT.split(js_str(text or ""))) if s]

    def lines_for(name):
        k = street_key(name)
        if not k:
            return []
        every = idx.get(k["core"]) or []
        typed = [ln for ln in every if not k["type"] or not ln["type"] or ln["type"] == k["type"]]
        return typed or every

    if len(parts) >= 2:
        best = None
        for a in lines_for(parts[0]):
            for b in lines_for(parts[1]):
                ap, bp = a["pts"], b["pts"]
                for i in range(0, len(ap) - 1, 2):
                    for j in range(0, len(bp) - 1, 2):
                        d = (ap[i] - bp[j]) ** 2 + (ap[i + 1] - bp[j + 1]) ** 2
                        if best is None or d < best[0]:
                            best = (d, (ap[i] + bp[j]) / 2, (ap[i + 1] + bp[j + 1]) / 2, a["n"], b["n"])
        if best and best[0] < 80 * 80:
            return {"x": best[1], "y": best[2], "prec": "intersection", "label": f"{best[3]} & {best[4]}"}
    k = street_key(parts[0]) if parts else None
    if k:
        cands = []
        for s in streets or []:
            sk = street_key(s.get("n"))
            if sk and sk["core"] == k["core"] and (not k["type"] or not sk["type"] or sk["type"] == k["type"]):
                cands.append(s)
        hit = next((s for s in cands if town in (s.get("t") or [])), None) or (cands[0] if cands else None)
        if hit:
            return {"x": hit["x"], "y": hit["y"], "prec": "street", "label": hit["n"]}
    return None


def place(p, idx, streets):
    """Port of place(): give a post coordinates from its "near" text when it has none."""
    if _num(p.get("x")) and _num(p.get("y")):
        return p
    g = geocode_near(p["near"], idx, streets, p.get("town")) if p.get("near") else None
    return {**p, "x": g["x"], "y": g["y"], "prec": g["prec"], "placeLabel": g["label"]} if g else p


def index(D):
    if "_pets_idx" not in D:
        D["_pets_idx"] = build_index(ND.lines(D))
    return D["_pets_idx"]


def newest_first(posts):
    """publish()'s order: date (else created), newest first, stable."""
    return sorted(posts, key=lambda p: js_str(p.get("date") or p.get("created")), reverse=True)


def snapshot_posts(issues, idx, streets, repo=REPO):
    """What scripts/snapshot_pets.py writes: form issues -> parsed, sanitized, geocoded posts (open ones only)."""
    out = []
    for i in issues or []:
        if not is_pet_issue(i) or i.get("state", "open") != "open":
            continue
        p = parse_issue(i, repo)
        if p:
            out.append(sanitize(place(p, idx, streets), "github", repo))
    return newest_first(out)


def open_posts(D):
    """The snapshot's open posts, sanitized and geocoded, newest first; [] when the build has no snapshot."""
    if D.get("board") is None:
        return []
    if "_pets_open" not in D:
        repo = D["cfg"].get("repo") or REPO
        posts = []
        for p in (D["board"].get("posts") or []):
            s = sanitize(p, "github", repo)
            if s and "x" not in s:
                s = sanitize(place(s, index(D), D["streets"]), "github", repo)
            if s:
                posts.append(s)
        D["_pets_open"] = newest_first(posts)
    return D["_pets_open"]


# --------------------------------------------------------------------------- times and words


def eastern(iso):
    """UTC ISO timestamp -> aware datetime in America/New_York (manual US DST rule if tzdata is missing)."""
    t = dt.datetime.fromisoformat(str(iso).replace("Z", "+00:00"))
    if t.tzinfo is None:
        t = t.replace(tzinfo=dt.timezone.utc)
    try:
        from zoneinfo import ZoneInfo
        return t.astimezone(ZoneInfo("America/New_York"))
    except Exception:
        y = t.year
        mar = dt.datetime(y, 3, 8 + (6 - dt.date(y, 3, 8).weekday()) % 7, 7, tzinfo=dt.timezone.utc)
        nov = dt.datetime(y, 11, 1 + (6 - dt.date(y, 11, 1).weekday()) % 7, 6, tzinfo=dt.timezone.utc)
        off = -4 if mar <= t < nov else -5
        return t.astimezone(dt.timezone(dt.timedelta(hours=off)))


def checked(iso, today):
    """'9:15 a.m.' when the board was read today, else 'Sept. 22, 9:15 a.m.'."""
    if not iso:
        return ""
    t = eastern(iso)
    tm = fmt.ap_time(t)
    return tm if t.date() == today else f"{short_date(t.date().isoformat(), today)}, {tm}"


def short_date(iso, today):
    """'Sept. 22' in the current year, 'Sept. 22, 2025' otherwise."""
    if not iso:
        return ""
    d = dt.date.fromisoformat(iso[:10])
    s = fmt.ap_date(d.isoformat())
    return s.removesuffix(f", {d.year}") if d.year == today.year else s


def animal_word(p):
    return p.get("animal") if p.get("animal") in ("dog", "cat") else "pet"


def cut(s, n=80):
    """Cut at n characters on a word boundary, with an ellipsis."""
    s = str(s or "").strip()
    if len(s) <= n:
        return s
    c = s[:n + 1]
    i = c.rfind(" ")
    c = c[:i] if i > n // 2 else s[:n]
    return c.rstrip(" ,;:.–-") + "…"


def where(p):
    return ", ".join(x for x in (p.get("near"), p.get("town")) if x)


def near_line(p):
    """'Last seen near Fifth Avenue & 11th Street, New Kensington' ('Found near …' for a found pet), and
    '(no cross street given)' after a post placed on a street only."""
    w = where(p)
    if not w:
        return ""
    return f"{VERB.get(p['status'], 'Last seen near')} {w}" + (" (no cross street given)" if p.get("prec") == "street" else "")


def headline(p):
    """'Lost dog: Biscuit' / 'Found cat'."""
    h = f"{STATUS[p['status']]} {animal_word(p)}"
    return f"{h}: {p['name']}" if p.get("name") else h


def post_path(p):
    return f"/lost-pets/{p['id']}/"


_EMAIL = re.compile(r"[\w.+-]+@[\w-]+(?:\.[\w-]+)+", re.A)
_PHONE = re.compile(r"\(?\b(\d{3})\)?[-. ]?(\d{3})[-. ](\d{4})\b|\b911\b", re.A)


def contact_html(p):
    """The public contact with phone numbers as tap-to-call links and e-mail addresses as mailto links."""
    c = p.get("contact") or ""
    if not c:
        return ""
    if p.get("url") and re.fullmatch(r"comment (?:on|below|here)[\w .]*", c, AI):
        return f'<a href="{esc(p["url"])}" target="_blank" rel="noopener">{esc(c)}</a>'
    out, pos = [], 0
    pat = re.compile(_PHONE.pattern + "|" + _EMAIL.pattern, re.A)
    for m in pat.finditer(c):
        out.append(esc(c[pos:m.start()]))
        s = m.group(0)
        if "@" in s:
            out.append(f'<a href="mailto:{esc(s)}">{esc(s)}</a>')
        else:
            shown, href = fmt.tel(s)[0]
            out.append(f'<a class="tel" href="{href}">{esc(shown)}</a>')
        pos = m.end()
    out.append(esc(c[pos:]))
    return "".join(out)


# --------------------------------------------------------------------------- markup shared with pets.js


def row_html(post, R, today=None):
    """One compact row (home, town pages, search) linking to lost-pets/#gh-N. pets.js rowHTML() makes the same."""
    today = today or dt.date.today()
    p = post
    desc = cut(p.get("desc"))
    name = f'<b>{esc(p["name"])}.</b> ' if p.get("name") else ""
    tail = " · ".join(x for x in (where(p), short_date(p.get("date") or p.get("created"), today)) if x)
    return (f'<li class="listing-row" data-status="{esc(p["status"])}" data-id="{esc(p["id"])}">'
            f'<a href="{rel(R, "/lost-pets/")}#{esc(p["id"])}">'
            f'<span class="listing-st">{STATUS[p["status"]]} {animal_word(p)}</span> '
            f'<span class="listing-desc">{name}{esc(desc)}</span>'
            + (f' <span class="listing-where">{esc(tail)}</span>' if tail else "") + '</a></li>')


def date_line(p, today):
    d = p.get("date") or (p.get("created") or "")[:10]
    if not d:
        return ""
    ago = ""
    n = (today - dt.date.fromisoformat(d)).days
    if n >= 0:
        ago = ("today" if n == 0 else "yesterday" if n == 1 else f"{n} days ago" if n < 14 else
               f"{js_round(n / 7)} weeks ago" if n < 60 else f"{js_round(n / 30)} months ago")
        ago = f' <span data-ago="{d}" data-paren>({ago})</span>'
    return f'{STATUS[p["status"]]} {fmt.ap_day(d)}{ago}'


def card_html(p, R, today, share=True, name=True):
    """The full listing card on /lost-pets/ (pets.js cardHTML() makes the same markup). name=False leaves the
    name out (the listing page's H1 already has it)."""
    pid = esc(p["id"])
    alt = f'Photo of {p["name"]}' if p.get("name") else f'Photo of the {animal_word(p)}'
    acts = []
    if _num(p.get("x")) or p.get("near"):
        acts.append(f'<a href="{rel(R, "/map/")}?pet={pid}">Map it</a>')
    if share:
        acts.append(f'<button type="button" class="linkbtn" data-share="{pid}" hidden>Share</button>')
    acts.append(f'<a href="{rel(R, "/lost-pets/flyer/")}?pet={pid}">Flyer</a>')
    if p.get("url"):
        acts.append(f'<a href="{esc(p["url"])}" target="_blank" rel="noopener">See this post ›</a>')
    near = near_line(p)
    dl = date_line(p, today)
    return (f'<article class="listing" id="{pid}" data-status="{esc(p["status"])}" data-id="{pid}">'
            + (f'<img src="{esc(p["photo"])}" alt="{esc(alt)}" loading="lazy">' if p.get("photo") else "")
            + f'<p class="listing-st">{STATUS[p["status"]]} · {animal_word(p)}</p>'
            + (f'<h3>“{esc(p["name"])}”</h3>' if p.get("name") and name else "")
            + (f'<p class="listing-desc">{esc(p["desc"])}</p>' if p.get("desc") else "")
            + (f'<p class="listing-near">{esc(near)}</p>' if near else "")
            + '<p class="listing-dist" hidden></p>'
            + (f'<p class="listing-date">{dl}</p>' if dl else "")
            + (f'<p class="listing-contact">{contact_html(p)}</p>' if p.get("contact") else "")
            + f'<p class="listing-acts">{"".join(acts)}</p></article>')


# --------------------------------------------------------------------------- research contacts (pets.json)


def shelter(D):
    return next(i for i in D["pets"]["items"] if i.get("kind") == "shelter")


def police(D):
    """{town: item} for the three departments' non-emergency lines, and "county" for the county line."""
    out = {}
    for it in D["pets"]["items"]:
        if it.get("kind") != "police":
            continue
        t = next((t for t in TOWNS if it["name"].startswith(t)), None)
        out[t or "county"] = it
    return out


def outlet(u):
    return fmt.pub_name(u)


def credit(urls, pre="Source: ", joiner=", "):
    """fmt.credit() with the pets outlets named; `joiner` 'and' gives 'A, B and C'."""
    seen, out = set(), []
    for u in ([urls] if isinstance(urls, str) else urls or []):
        n = outlet(u) if u else ""
        if not n or n in seen:
            continue
        seen.add(n)
        out.append(f'<a class="cr" href="{esc(u)}" target="_blank" rel="noopener">{esc(n)}</a>')
    if not out:
        return ""
    body = ", ".join(out) if joiner == ", " or len(out) < 2 else ", ".join(out[:-1]) + " and " + out[-1]
    return pre + body


def credit_line(urls, pre="Source: "):
    c = credit(urls, pre)
    return f'<p class="credit">{c}</p>' if c else ""


def issues_url(D):
    return f"https://github.com/{D['cfg'].get('repo') or REPO}/issues"


def tel_btn(phone, label="Call {n}", cls="tel"):
    return fmt.tel_link(phone, label, cls)


# --------------------------------------------------------------------------- home box and town section


def board_state(D):
    """(state, posts, fetched): state is 'nosnap' | 'listed' | 'empty'."""
    if D.get("board") is None:
        return "nosnap", [], None
    posts = open_posts(D)
    return ("listed" if posts else "empty"), posts, D["board"].get("fetched")


def home_box(D, R):
    """The home page's pets box, in the state the build knows; pets.js renderHomeBox() refreshes it live."""
    state, posts, fetched = board_state(D)
    sh = shelter(D)
    lp = rel(R, "/lost-pets/")
    count = f'<span class="pb-count">{len(posts)} open</span>' if state == "listed" else '<span class="pb-count"></span>'
    head = f'<h2 class="lh" id="pets-box-h"><span>Lost &amp; found pets</span>{count}</h2>'
    if state == "listed":
        rows = "".join(row_html(p, R, D["today"]) for p in posts[:3])
        more = (f'<a class="act" href="{lp}#board">See all {len(posts)} on the board ›</a>' if len(posts) > 3 else
                f'<a class="act" href="{lp}#board">See the board ›</a>')
        body = (f'<ul class="petrows">{rows}</ul>'
                f'<p class="pb-acts">{more}<a class="act" href="{lp}">Lost a pet? What to do now ›</a></p>')
    elif state == "empty":
        body = (f'<p class="pb-msg">No open listings on the board right now (checked {checked(fetched, D["today"])}).</p>'
                f'<p class="pb-msg">Lost a pet? Call {esc(short_name(sh))}, {tel_btn(sh["phone"], "{n}")}, then post it here.</p>'
                f'<p class="pb-acts"><a class="act" href="{lp}#found">Found a dog? Who to call ›</a>'
                f'<a class="act" href="{rel(R, "/lost-pets/post/")}">Post a free listing ›</a></p>')
    else:
        body = (f'<p class="pb-msg">The board shows live listings when JavaScript is on. '
                f'<a href="{esc(issues_url(D))}" target="_blank" rel="noopener">See the posts on GitHub ›</a></p>'
                f'<p class="pb-acts"><a class="act" href="{lp}#board">See the board ›</a>'
                f'<a class="act" href="{lp}">Lost a pet? What to do now ›</a></p>')
    return (f'<section id="pets-box" class="pets-box" aria-labelledby="pets-box-h" data-state="{state}"'
            + (f' data-fetched="{esc(fetched)}"' if fetched else "") + data_attrs(D)
            + f'>{head}<div class="pb-body">{body}</div></section>')


def town_section(D, R, town):
    """'Lost and found pets in {town}' for a town page: static text, the snapshot's rows for that town, and an
    empty [data-pets-town] host that pets.js renderTownList() fills with live posts."""
    state, posts, fetched = board_state(D)
    mine = [p for p in posts if p.get("town") == town]
    lp = rel(R, "/lost-pets/")
    sid = "pets-" + fmt.slug(town)
    rows = "".join(row_html(p, R, D["today"]) for p in mine)
    if state == "listed" and mine:
        note = f'<p class="pb-msg">{len(mine)} open listing{"s" if len(mine) != 1 else ""} in {esc(town)} (checked {checked(fetched, D["today"])}).</p>'
    elif state in ("listed", "empty"):
        note = f'<p class="pb-msg">None of the board&rsquo;s open listings are in {esc(town)} right now (checked {checked(fetched, D["today"])}).</p>'
    else:
        note = ""
    sh = shelter(D)
    return (f'<section class="sec pets-town" id="{sid}" aria-labelledby="{sid}-h">'
            f'<h2 id="{sid}-h">Lost and found pets in {esc(town)}</h2>'
            f'<p class="pt-lead">Open listings for {esc(town)} are on the <a href="{lp}#board">lost and found board ›</a></p>'
            f'<div class="pt-live" data-pets-town="{esc(town)}"{data_attrs(D)}>{note}'
            + (f'<ul class="petrows">{rows}</ul>' if rows else "") + '</div>'
            f'<p class="pt-call">Lost or found a pet? Call {esc(short_name(sh))} {tel_btn(sh["phone"])} '
            f'<a class="act" href="{lp}">What to do first ›</a></p>'
            + credit_line([sh["source"]])
            + '</section>')


def data_attrs(D):
    """What pets.js needs to write the live states' copy (all from pets.json and the site config)."""
    sh = shelter(D)
    return (f' data-shelter-name="{esc(short_name(sh))}" data-shelter-tel="{esc(fmt.tel(sh["phone"])[0][0])}"'
            f' data-issues="{esc(issues_url(D))}"')


def short_name(item):
    """'Animal Protectors of Allegheny Valley' -> 'Animal Protectors'."""
    return re.sub(r"\s+of\s+.*$", "", item["name"]) if item.get("kind") == "shelter" else item["name"]
