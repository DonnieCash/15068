"""The lost & found pets pages: /lost-pets/, /lost-pets/post/, /lost-pets/flyer/, and (deploy builds with
--snapshot only) one /lost-pets/gh-N/ page per open listing plus lost-pets/feed.xml.

Every contact, phone number and tip comes from data/research/pets.json and keeps its source credit; the checklist
and finder steps are the spec's copy, each tied to the pets.json tip that backs it (an item whose tip is gone is
left out rather than printed unsourced).
"""
import re

from . import fmt
from . import pets as P
from .data import updated
from .fmt import esc
from .routes import dynamic
from .shell import page_html, rel, site_url

# --------------------------------------------------------------------------- research items


def item(D, kind=None, name=None):
    """The first pets.json item of that kind whose name matches the regex (None if the data no longer has it)."""
    for it in D["pets"]["items"]:
        if (kind is None or it.get("kind") == kind) and (name is None or re.search(name, it.get("name", ""))):
            return it
    return None


def tip(D, pattern):
    return next((t for t in D["pets"].get("tips", []) if re.search(pattern, t.get("tip", ""), re.I)), None)


def board_url(D, kind):
    """PawBoost / Petco Love Lost / Find Toby links from the online_board items."""
    it = item(D, "online_board", kind)
    return it["url"] if it else ""


AP_SUFFIX = {"Street": "St.", "Avenue": "Ave.", "Boulevard": "Blvd.", "Road": "Road", "Drive": "Drive"}


def ap_addr(a):
    """'730 Church Street, New Kensington, PA 15068' -> '730 Church St., New Kensington' (AP style; a suite stays,
    the state and ZIP go)."""
    parts = [s.strip() for s in str(a or "").split(",") if s.strip()]
    if not parts:
        return ""
    street = re.sub(r"\b(Street|Avenue|Boulevard)\b", lambda m: AP_SUFFIX[m.group(1)], parts[0])
    rest = [s for s in parts[1:] if not re.fullmatch(r"[A-Z]{2}\s*\d{5}(-\d{4})?", s)]
    return ", ".join([street] + rest)


def plain_name(it):
    """'Hoffman Kennels (contracted animal control officer)' -> 'Hoffman Kennels'."""
    return re.sub(r"\s*\([^)]*\)", "", it["name"]).strip()


def link(url, text, ext=True):
    t = ' target="_blank" rel="noopener"' if ext and url.startswith("http") else ""
    return f'<a href="{esc(url)}"{t}>{text}</a>'


# --------------------------------------------------------------------------- Call now card


def cn_row(key, name, desc, buttons, town=None, extra=""):
    t = f' data-town="{esc(town)}"' if town else ""
    return (f'<li class="cn-row" data-k="{key}"{t}><div class="cn-top"><b class="cn-name">{name}</b>'
            f'<span class="cn-btns">{buttons}</span></div><p class="cn-desc">{desc}{extra}</p></li>')


def call_rows(D, R, mini_town=None):
    """[(key, html, source)] in lost-mode order. mini_town: only that town's police (the listing pages)."""
    rows = []
    sh = P.shelter(D)
    rows.append(("shelter", cn_row("shelter", esc(sh["name"]), f"The shelter in town, {esc(ap_addr(sh['address']))}",
                                   P.tel_btn(sh["phone"])), sh["source"]))
    pol = P.police(D)
    for t in P.TOWNS:
        it = pol.get(t)
        if not it or (mini_town and t != mini_town):
            continue
        nums = fmt.tel(it["phone"])
        alt = "".join(f' <span class="tel-alt">or <a href="{h}">{esc(s)}</a></span>' for s, h in nums[1:])
        rows.append(("police", cn_row("police", f"{esc(t)} police", "Non-emergency, for a missing or loose pet",
                                      P.tel_btn(it["phone"]), t, alt), it["source"]))
    hk = item(D, None, r"^Hoffman")
    if hk and hk.get("phone") and not mini_town:
        rows.append(("aco", cn_row("aco", esc(plain_name(hk)), "The city&rsquo;s animal control officer, weekdays",
                                   P.tel_btn(hk["phone"]), "Lower Burrell"), hk["source"]))
    county = pol.get("county")
    if county:
        rows.append(("county", cn_row("county", "After hours", "Westmoreland County non-emergency line",
                                      P.tel_btn(county["phone"])), county["source"]))
    if mini_town:
        return rows
    ward, reg = item(D, "dog_warden"), item(D, None, r"Region 4")
    if ward and reg and reg.get("phone"):
        btns = (f'<a class="tel cn-find" href="{esc(ward["url"])}" target="_blank" rel="noopener">Find yours ›</a>'
                + P.tel_btn(reg["phone"]))
        rows.append(("warden", cn_row("warden", "Dog warden", "Find the Westmoreland County warden on the state&rsquo;s map",
                                      btns, None, '<span class="small">State dog law office, weekdays 8 a.m.–4 p.m.</span>'),
                     [ward["source"], reg["source"]]))
    vet = item(D, "vet_er", r"^AVETS")
    if vet and vet.get("phone"):
        rows.append(("vet", cn_row("vet", "Injured pet", "AVETS emergency vet, open 24 hours, Monroeville",
                                   P.tel_btn(vet["phone"])), vet["source"]))
    return rows


def call_now(D, R):
    rows = call_rows(D, R)
    law = tip(D, r"^Found a dog")
    srcs = []
    for _, _, s in rows:
        srcs += s if isinstance(s, list) else [s]
    if law:
        srcs.append(law["source"])
    towns = "".join(f'<button type="button" aria-pressed="false" data-town="{esc(t)}">{esc(t)}</button>' for t in P.TOWNS)
    found_cap = ("Found a dog? Pennsylvania law says to call police, animal control or the dog warden, so the dog goes "
                 "to a licensed stray-hold kennel.") if law else "Found a dog? Call your town&rsquo;s police first."
    return (f'<aside id="call-now" class="box callnow" data-keep-above aria-labelledby="call-now-h">'
            f'<h2 class="lh" id="call-now-h">Call now</h2>'
            f'<p class="cn-cap" data-for="lost">If your pet is missing, call these today.</p>'
            f'<p class="cn-cap" data-for="found" hidden>{found_cap}</p>'
            f'<div class="picker" role="group" aria-label="Your town" hidden>{towns}</div>'
            f'<ul class="cn-rows">{"".join(h for _, h, _ in rows)}</ul>'
            f'{P.credit_line(srcs, "Sources: ")}</aside>'), srcs


def mini_call(D, R, town):
    """The short Call now block on a listing page: the shelter, that town's police and the after-hours line."""
    rows = call_rows(D, R, mini_town=town if town in P.TOWNS else "New Kensington")
    srcs = []
    for _, _, s in rows:
        srcs += s if isinstance(s, list) else [s]
    return (f'<aside class="box callnow mini" data-keep-above aria-labelledby="cn-mini-h">'
            f'<h2 class="lh" id="cn-mini-h">Call now</h2><ul class="cn-rows">{"".join(h for _, h, _ in rows)}</ul>'
            f'{P.credit_line(srcs, "Sources: ")}</aside>')


# --------------------------------------------------------------------------- checklists


def lost_steps(D, R):
    post = rel(R, "/lost-pets/post/")
    petco, paw = board_url(D, r"^Petco"), board_url(D, r"^PawBoost")
    groups = [
        ("Today", [
            ("call", "Call Animal Protectors and your town&rsquo;s police non-emergency line.", r"call local shelters"),
            ("chip", "Tell your microchip company your pet is missing, and check that your contact details are current.",
             r"microchip company"),
            ("walk", "Walk the neighborhood, knock on doors, and look under decks, sheds, porches and thick shrubs.",
             r"knock on doors"),
            ("post", f'{link(post, "Post your pet here", False)}, on {link(petco, "Petco Love Lost")} and on '
                     f'{link(paw, "PawBoost")}.', r"Petco Love Lost"),
            ("flyer", f'{link(post, "Make a flyer", False)} and put it up at vet offices, groomers, pet stores, grocery '
                      "and convenience stores, gas stations and laundromats.", r"flyers"),
        ]),
        ("Within 48 hours", [
            ("visit", "Go to Animal Protectors in person. Pennsylvania holds a stray dog at least 48 hours before it can "
                      "be adopted or change owners, so that&rsquo;s your window to reclaim it.", r"at least 48 hours")]),
        ("Every day", [("again", "Call the shelters and animal control again. Don&rsquo;t call only once.",
                        r"instead of calling only once")]),
        ("Afterward", [("license", "Keep your dog licensed. A current tag lets a warden or shelter find you quickly.",
                        r"Keep your dog licensed")]),
    ]
    out, srcs, n = [], [], 0
    for when, items in groups:
        lis = []
        for key, text, pat in items:
            t = tip(D, pat)
            if not t:
                continue
            srcs.append(t["source"])
            lis.append(f'<li><label><input type="checkbox" data-check="{key}"><span>{text}</span></label></li>')
        if not lis:
            continue
        first = not out
        attrs = ' id="pets-tips"' if first else f' start="{n + 1}"'
        out.append(f'<h3 class="ck-when">{when}</h3><ol class="checklist"{attrs}>{"".join(lis)}</ol>')
        n += len(lis)
    return "".join(out), srcs


def found_steps(D, R):
    post = rel(R, "/lost-pets/post/")
    law, petco_tip = tip(D, r"^Found a dog"), tip(D, r"Petco Love Lost")
    chip, rescue, sh, vet = item(D, "microchip_lookup"), item(D, "rescue"), P.shelter(D), item(D, "vet_er", r"^AVETS")
    petco, paw = board_url(D, r"^Petco"), board_url(D, r"^PawBoost")
    steps, srcs = [], []
    if law:
        steps.append("Found a dog: call the police non-emergency line, animal control or the dog warden. Pennsylvania law "
                     "says a found dog goes to a licensed stray-hold kennel, where it&rsquo;s held at least 48 hours so "
                     "the owner can reclaim it.")
        srcs.append(law["source"])
    if chip:
        steps.append("Ask a vet or the shelter to scan it for a microchip, then look the number up on the "
                     f'{link(chip["url"], "AAHA lookup ›")}')
        srcs.append(chip["source"])
    if petco_tip:
        steps.append(f'{link(post, "Post it here", False)} and on {link(petco, "Petco Love Lost")} and '
                     f'{link(paw, "PawBoost")}.')
        srcs.append(petco_tip["source"])
    if rescue:
        steps.append(f'Found a cat: call Animal Protectors, or contact {link(rescue["url"], esc(plain_name(rescue)) + " ›")}')
        srcs += [sh["source"], rescue["source"]]
    if vet and vet.get("phone"):
        steps.append(f'Injured? AVETS in Monroeville is open 24 hours: {P.tel_btn(vet["phone"], "{n}")}.')
        srcs.append(vet["source"])
    lis = "".join(f"<li>{s}</li>" for s in steps)
    return f'<ol class="steps" id="found-steps">{lis}</ol>', srcs


ALSO = [("humane_society", "County humane society"), ("license", "Dog licenses"), ("microchip_lookup", "Microchips"),
        ("rescue", "Cats"), ("vet_er", "Another 24-hour emergency vet"), ("online_board", "Free lost and found boards")]


def also_useful(D, used):
    groups = []
    for kind, label in ALSO:
        its = [it for it in D["pets"]["items"] if it.get("kind") == kind and it["name"] not in used]
        if not its:
            continue
        rows = []
        for it in its:
            bits = []
            if it.get("address"):
                bits.append(esc(ap_addr(it["address"])))
            if it.get("url"):
                bits.append(link(it["url"], "Website ›"))
            bits.append(P.credit([it["source"]]))
            rows.append(f'<div class="au-item"><p><b>{esc(fmt.public(it["name"]))}.</b> '
                        f'{esc(fmt.public(it.get("what_to_use_it_for", "")))}</p>'
                        f'<p class="au-meta">{P.tel_btn(it["phone"]) if it.get("phone") else ""}'
                        f'<span>{" · ".join(b for b in bits if b)}</span></p></div>')
        groups.append(f'<h3 class="ck-when">{label}</h3>{"".join(rows)}')
    return ('<details class="also" id="also"><summary>Also useful: licenses, microchips, cats and more ›</summary>'
            f'<div class="also-body">{"".join(groups)}</div></details>')


# --------------------------------------------------------------------------- the board


def status_text(D, state, fetched, R):
    sh = P.shelter(D)
    when = P.checked(fetched, D["today"]) if fetched else ""
    if state == "listed":
        return (f"Listings posted by neighbors through the NK15068 form. Checked {fmt.end_stop(when)} "
                "A post comes down when its owner closes it.")
    if state == "empty":
        return (f"No open listings on this board right now (checked {when}). It only covers posts made here, so also "
                f'check {link(board_url(D, "^PawBoost"), "PawBoost")} and {link(board_url(D, "^Petco"), "Petco Love Lost")}, '
                f"and call the shelter, {P.tel_btn(sh['phone'], '{n}', 'tel-inline')}.")
    return ('The board shows live listings when JavaScript is on. '
            f'{link(P.issues_url(D), "See the posts on GitHub ›")}')


def summary(D, state, posts, fetched):
    if state == "listed":
        n = len(posts)
        newest = max((p.get("date") or p.get("created") or "")[:10] for p in posts)
        return (f'<a href="#board">The board: {n} open listing{"s" if n != 1 else ""}, newest '
                f'{esc(P.short_date(newest, D["today"]))}. <span class="bs-go">See the listings ›</span></a>')
    if state == "empty":
        return (f'<a href="#board">The board: no open listings right now (checked {P.checked(fetched, D["today"])}). '
                '<span class="bs-go">See the board ›</span></a>')
    return '<a href="#board">The board: lost and found posts from neighbors in 15068. <span class="bs-go">See the board ›</span></a>'


def post_box(D, R):
    return ('<div class="listing listing-post" id="pets-post"><h3>Post a lost or found pet</h3>'
            '<p>It&rsquo;s free and takes two minutes.</p>'
            f'<p><a class="act" href="{rel(R, "/lost-pets/post/")}">Post your pet ›</a></p>'
            f'<p class="fine">No GitHub account? Post free on {link(board_url(D, "^PawBoost"), "PawBoost ›")} or '
            f'{link(board_url(D, "^Petco"), "Petco Love Lost ›")}</p></div>')


def corner_row():
    return ('<div class="corner" id="pets-corner" hidden>'
            '<label class="corner-l" for="pets-near">Your corner</label>'
            '<div class="corner-row"><input id="pets-near" type="text" placeholder="Like Fifth &amp; 9th" '
            'autocomplete="off" maxlength="120" enterkeyhint="go">'
            '<button type="button" id="pets-sort">Sort by distance</button></div>'
            '<div class="corner-row2"><button type="button" class="linkbtn" id="pets-loc">Use my location</button>'
            '<label class="remember"><input type="checkbox" id="pets-remember"> Remember on this phone</label></div>'
            '<div class="consent" id="pets-consent" hidden><p>Your location is used on this device to find your nearest '
            'street. It isn&rsquo;t sent anywhere.</p><p><button type="button" class="btn-line inline" id="pets-consent-go">'
            'Continue</button> <button type="button" class="btn-line inline" id="pets-consent-no">Cancel</button></p></div>'
            '<p class="corner-msg" id="pets-corner-msg" role="status"></p></div>')


# --------------------------------------------------------------------------- /lost-pets/


def lost_pets(D, R):
    state, posts, fetched = P.board_state(D)
    snap = D.get("board") is not None
    card, cn_srcs = call_now(D, R)
    lost_html, lost_srcs = lost_steps(D, R)
    found_html, found_srcs = found_steps(D, R)
    used = {it["name"] for it in D["pets"]["items"] if it.get("kind") in ("shelter", "police", "dog_warden")}
    used |= {it["name"] for it in (item(D, None, r"^Hoffman"), item(D, None, r"Region 4"), item(D, "vet_er", r"^AVETS")) if it}
    compiled = D["dates"]["pets"]
    when = f' · Board checked {P.checked(fetched, D["today"])}' if fetched else ""
    cards = "".join(P.card_html(p, R, D["today"]) for p in posts)
    count = f"{len(posts)} open" if state == "listed" else ""
    empty = ('<div class="listing listing-empty"><p>Nothing is posted on this board right now.</p></div>'
             if state == "empty" else "")
    rss = ('<p class="rss"><a href="feed.xml">Follow new listings (RSS) ›</a></p>' if snap else "")
    all_srcs = cn_srcs + lost_srcs + found_srcs
    body = f"""<div class="page lp">
<div class="lp-head">
<h1>{esc(R.h1)}</h1>
<p class="dateline">Contacts checked {fmt.ap_date(compiled)}<span id="board-checked">{esc(when)}</span></p>
<p class="deck">Call these first. Then check the board and post your pet.</p>
<nav class="lp-toggles" aria-label="What happened"><a class="seg" href="#lost" data-mode="lost">I lost a pet</a><a class="seg" href="#found" data-mode="found">I found a pet</a></nav>
<p class="board-sum" id="board-sum" data-state="{state}">{summary(D, state, posts, fetched)}</p>
</div>
{card}
<div class="lp-main">
<section class="board-sec" id="board" aria-labelledby="board-h" data-state="{state}"{f' data-fetched="{esc(fetched)}"' if fetched else ""}{P.data_attrs(D)} data-pawboost="{esc(board_url(D, "^PawBoost"))}" data-petco="{esc(board_url(D, "^Petco"))}">
<h2 class="lh board-h" id="board-h"><span>The board</span><span class="board-count" id="board-count">{count}</span></h2>
<p id="pets-status" role="status">{status_text(D, state, fetched, R)}</p>
{corner_row()}
<div class="board" id="pets-list">{cards}{empty}{post_box(D, R)}</div>
{rss}
</section>
<section class="sec" id="lost" aria-labelledby="lost-h"><h2 id="lost-h">If your pet is missing: the first 48 hours</h2>
{lost_html}
{P.credit_line(lost_srcs, "Sources: ")}
</section>
<section class="sec" id="found" aria-labelledby="found-h"><h2 id="found-h">If you found a pet</h2>
{found_html}
{P.credit_line(found_srcs, "Sources: ")}
</section>
{also_useful(D, used)}
<p class="credit lp-sources">{P.credit(all_srcs, "Contacts and tips from ", "and")} · Checked {fmt.ap_date(compiled)}</p>
</div>
</div>"""
    head = ('<link rel="alternate" type="application/rss+xml" title="NK15068 lost and found pets" href="feed.xml">'
            if snap else "")
    return {"body": body, "head": head}


# --------------------------------------------------------------------------- /lost-pets/post/


def lost_pets_post(D, R):
    repo = D["cfg"].get("repo") or P.REPO
    email = (D["cfg"].get("contact_email") or "").strip()
    petco, paw = board_url(D, r"^Petco"), board_url(D, r"^PawBoost")
    opt = lambda vals: "".join(f"<option>{esc(v)}</option>" for v in vals)  # noqa: E731
    L = P.LIMITS
    mail = (f'<a class="btn-line inline" id="post-mail" href="mailto:{esc(email)}">Email it to NK15068 instead ›</a>'
            if email else "")
    body = f"""<div class="page post-page">
<h1>{esc(R.h1)}</h1>
<p class="deck">Fill this in once. We&rsquo;ll open GitHub&rsquo;s form with it already typed, make you a flyer, and point you to two free boards that don&rsquo;t need an account.</p>
<div class="post-grid">
<form class="petform" id="post-form" action="https://github.com/{esc(repo)}/issues/new" method="get" target="_blank" data-email="{esc(email)}">
<input type="hidden" name="template" value="lost-found-pet.yml">
<label>Lost, found or spotted?<select name="status" id="f-status" required>{opt(["Lost", "Found", "Spotted"])}</select></label>
<label>Animal<select name="animal" id="f-animal" required>{opt(["Dog", "Cat", "Other"])}</select></label>
<label>Pet&rsquo;s name (if known)<input name="name" id="f-name" maxlength="{L["name"]}" autocomplete="off"></label>
<label>Description<textarea name="description" id="f-desc" maxlength="{L["desc"]}" required placeholder="Breed, color, size, collar or tags"></textarea></label>
<label>Last seen near<input name="near" id="f-near" maxlength="{L["near"]}" required autocomplete="off" aria-describedby="f-near-help"><span class="help" id="f-near-help">A street and cross street, like Fifth Avenue &amp; 9th Street. House numbers are removed.</span></label>
<label>Town<select name="town" id="f-town" required>{opt(P.TOWNS)}</select></label>
<label>Date<input type="date" name="date" id="f-date" required></label>
<label>How to reach you (public)<input name="contact" id="f-contact" maxlength="{L["contact"]}" required autocomplete="off" aria-describedby="f-contact-help"><span class="help" id="f-contact-help">A phone number or email you&rsquo;re OK posting publicly.</span></label>
<label>Photo (for the flyer only)<input type="file" id="f-photo" accept="image/*"></label>
<p class="post-btns"><button type="submit" class="btn-line inline primary" id="post-gh">Continue on GitHub ›</button>
<button type="button" class="btn-line inline" id="post-flyer" hidden>Make a flyer</button>
<button type="button" class="btn-line inline" id="post-share" hidden>Share</button>
{mail}</p>
<p class="form-msg" id="post-msg" role="status"></p>
</form>
<div class="post-notes">
<p>GitHub needs a free account. No account? Post the same details free on {link(paw, "PawBoost ›")} or {link(petco, "Petco Love Lost ›")}.</p>
<p>Nothing you type here leaves your phone until you choose where to post it.</p>
<p>When you submit on GitHub, your listing shows on the board within a few minutes.</p>
<p><a class="go" href="{rel(R, "/lost-pets/")}">Back to the board and who to call ›</a></p>
</div>
</div>
</div>"""
    return {"body": body, "crumbs": [("Lost pets", "/lost-pets/"), ("Post a pet", None)]}


# --------------------------------------------------------------------------- /lost-pets/flyer/


def flyer(D, R):
    sh = P.shelter(D)
    host = re.sub(r"^https?://", "", site_url(D))
    body = f"""<div class="page flyer-page">
<p class="fl-tools"><button type="button" class="btn-line inline" id="fl-print" hidden>Print</button> <a class="btn-line inline" id="fl-back" href="{rel(R, "/lost-pets/")}">Back</a></p>
<article class="flyer" id="flyer" data-status="lost">
<h1 id="fl-h">{esc(R.h1)}</h1>
<p class="fl-note" id="fl-note">This page turns a listing on the board, or the details you type on the <a href="{rel(R, "/lost-pets/post/")}">Post a pet</a> page, into a flyer you can print. It needs JavaScript to fill in the pet&rsquo;s details.</p>
<p class="fl-q" id="fl-q"></p>
<img class="fl-photo" id="fl-photo" alt="" hidden>
<p class="fl-desc" id="fl-desc"></p>
<p class="fl-seen" id="fl-seen"></p>
<p class="fl-contact" id="fl-contact"></p>
<ul class="fl-tabs" id="fl-tabs" aria-hidden="true"></ul>
<p class="fl-foot">More lost &amp; found pets: {esc(host)}/lost-pets/ · {esc(P.short_name(sh))} {P.tel_btn(sh["phone"], "{n}", "tel-inline")}</p>
</article>
</div>"""
    return {"body": body, "crumbs": [("Lost pets", "/lost-pets/"), ("Flyer", None)]}


# --------------------------------------------------------------------------- /lost-pets/gh-N/ (deploy only)


def og_title(p):
    h = f"{P.STATUS[p['status']].upper()} {P.animal_word(p).upper()}"
    h += f": {p['name']}" if p.get("name") else ""
    w = P.where(p)
    return f"{h}, near {w}" if w else h


VERB = {"lost": ("last seen", "owner"), "found": ("found", "finder"), "spotted": ("seen", "person who saw it")}


def listing_route(D, p):
    h1 = P.headline(p)
    title = h1 + (f", near {p['near']}" if p.get("near") else "") + " · NK15068"
    verb, who = VERB[p["status"]]
    d = p.get("date") or (p.get("created") or "")[:10]
    desc = (f"{P.STATUS[p['status']]} {P.animal_word(p)}" + (f" in {p['town']}" if p.get("town") else " in 15068")
            + (f", {verb} {P.short_date(d, D['today'])}" if d else "") + f". How to reach the {who} and who to call.")
    return dynamic(P.post_path(p), "lost-pets-listing", title, desc, h1, index="N", scripts=("pubs", "pets", "app"),
                   dates=("pets",), nav="lost-pets")


def listing(D, R, p):
    posted = (p.get("created") or "")[:10]
    fetched = D["board"].get("fetched")
    line = " · ".join(x for x in ((f"Posted {fmt.ap_date(posted)}" if posted else ""),
                                  (f"Board checked {P.checked(fetched, D['today'])}" if fetched else "")) if x)
    card = P.card_html(p, R, D["today"], name=False).replace('class="listing"', 'class="listing listing-one"', 1)
    body = f"""<div class="page listing-page">
<h1>{esc(R.h1)}</h1>
{f'<p class="dateline">{esc(line)}</p>' if line else ""}
<div class="lpg">
{card}
{mini_call(D, R, p.get("town"))}
</div>
<p><a class="go" href="{rel(R, "/lost-pets/")}#board">All listings ›</a> <a class="go" href="{rel(R, "/lost-pets/")}">Who to call and what to do ›</a></p>
</div>"""
    res = {"body": body, "crumbs": [("Lost pets", "/lost-pets/"), (R.h1, None)], "og_title": og_title(p),
           "updated": updated(D, ("pets",))}
    if p.get("photo"):
        res["og_image"] = p["photo"]
    return res


def feed_xml(D, posts):
    su = site_url(D)
    items = []
    for p in posts:
        u = su + P.post_path(p)
        body = " ".join(x for x in (p.get("desc"), P.near_line(p) + "." if P.near_line(p) else "",
                                    f"Contact: {p['contact']}." if p.get("contact") else "") if x)
        pub = ""
        if p.get("created"):
            t = P.eastern(p["created"])
            pub = f"<pubDate>{t.strftime('%a, %d %b %Y %H:%M:%S %z')}</pubDate>"
        items.append(f"<item><title>{esc(og_title(p))}</title><link>{esc(u)}</link>"
                     f'<guid isPermaLink="true">{esc(u)}</guid>{pub}<description>{esc(body)}</description></item>')
    built = ""
    if D["board"].get("fetched"):
        built = f"<lastBuildDate>{P.eastern(D['board']['fetched']).strftime('%a, %d %b %Y %H:%M:%S %z')}</lastBuildDate>"
    return ('<?xml version="1.0" encoding="UTF-8"?>\n<rss version="2.0"><channel>'
            f"<title>NK15068 lost and found pets</title><link>{esc(su)}/lost-pets/</link>"
            "<description>Open lost and found pet listings for New Kensington, Arnold and Lower Burrell (ZIP 15068).</description>"
            f"<language>en-us</language>{built}{''.join(items)}</channel></rss>\n")


def extra_files(D):
    """Deploy builds only: a page per open listing and the listings feed."""
    if D.get("board") is None:
        return {}
    posts = [p for p in P.open_posts(D) if re.fullmatch(r"gh-\d+", p.get("id", ""))]
    files = {}
    for p in posts:
        R = listing_route(D, p)
        files[R.file] = page_html(D, R, listing(D, R, p))
    files["lost-pets/feed.xml"] = feed_xml(D, posts)
    return files
