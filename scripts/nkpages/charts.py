"""Static SVG charts, rendered at build time.

svg_panels() is a port of the old safety.js panels(): the same geometry and the same data-pts/data-y0/data-y1/
data-vmax/data-label attributes, so NKSafety.wirePanels() adds the hover and keyboard readout unchanged.
pop_chart() is a port of the old renderStory() population bars.
"""
import json
import math

from .data import CORE_TOWNS
from .fmt import esc

W, H, L, R, T, B = 320, 172, 34, 34, 12, 24


def jsnum(v):
    """Number -> text the way JavaScript's String(n) writes it (34, 86.5, 102.83333333333333)."""
    if isinstance(v, bool):
        return "true" if v else "false"
    if isinstance(v, int):
        return str(v)
    if float(v).is_integer():
        return str(int(v))
    return repr(float(v))


def jsfmt(v, d=0):
    """Number(v).toLocaleString('en-US', {min/max fraction digits: d})"""
    return f"{v:,.{d}f}"


def fixed1(v):
    """Number.prototype.toFixed(1)"""
    return f"{v:.1f}"


def val(y, key):
    if callable(key):
        return key(y)
    return y.get(key)


def agency_for(fbi, town):
    return next((a for a in fbi.get("agencies") or []
                 if a.get("municipality") == town or town in (a.get("agency") or "")), None)


def nice_max(v):
    p = math.pow(10, math.floor(math.log10(v or 1)))
    for m in (1, 1.5, 2, 2.5, 3, 4, 5, 6, 8, 10):
        if m * p >= v:
            return m * p
    return 10 * p


def _point(y, key, count):
    v = val(y, key)
    pt = {"year": y["year"], "v": v if count else v / y["population"] * 1000, "n": v,
          "est": bool(y.get("population_estimated_from"))}
    if "months_reported" in y:
        pt["m"] = y["months_reported"]
    pt["c"] = 1 if count else 0
    return pt


def svg_panels(fbi, key, color_var, label, count=False, towns=CORE_TOWNS):
    """Small-multiple trend panels on one shared scale, one per town. key: a year field or a function of the year."""
    series = []
    for t in towns:
        ag = agency_for(fbi, t)
        pts = [_point(y, key, count) for y in (ag or {}).get("years") or []
               if val(y, key) is not None and (count or y.get("population"))]
        series.append((t, pts))
    allp = [p for _, pts in series for p in pts]
    if not allp:
        return f'<p class="empty">No {esc(label.lower())} figures available.</p>'
    y0, y1 = min(p["year"] for p in allp), max(p["year"] for p in allp)
    vmax = nice_max(max(p["v"] for p in allp) * 1.08)

    def x(yr):
        return L + (0.5 if y1 == y0 else (yr - y0) / (y1 - y0)) * (W - L - R)

    def y(v):
        return T + (1 - v / vmax) * (H - T - B)

    ticks = [0, vmax / 2, vmax]
    xt = [y0, math.floor((y0 + y1) / 2 + 0.5), y1] if y1 - y0 > 12 else [y0, y1]
    d = 0 if count else 1
    out = []
    for t, pts in series:
        runs = []
        for i, p in enumerate(pts):
            if not i or p["year"] != pts[i - 1]["year"] + 1:
                runs.append([])
            runs[-1].append(p)
        paths = "".join(
            f'<path d="{" ".join(("L" if i else "M") + fixed1(x(p["year"])) + " " + fixed1(y(p["v"])) for i, p in enumerate(r))}" '
            f'fill="none" stroke="var({color_var})" stroke-width="2" stroke-linejoin="round" stroke-linecap="round"/>'
            if len(r) > 1 else
            f'<circle cx="{jsnum(x(r[0]["year"]))}" cy="{jsnum(y(r[0]["v"]))}" r="3" fill="var({color_var})"/>'
            for r in runs)
        part = "".join(
            f'<circle cx="{jsnum(x(p["year"]))}" cy="{jsnum(y(p["v"]))}" r="4" fill="var(--ground)" stroke="var({color_var})" '
            f'stroke-width="2"><title>{p["year"]}: {p["m"]} of 12 months reported</title></circle>'
            for i, p in enumerate(pts) if p.get("m") and p["m"] < 12 and i < len(pts) - 1)
        last = pts[-1] if pts else None
        lp = bool(last and last.get("m") and last["m"] < 12)
        end = ""
        if last:
            fill = "var(--ground)" if lp else f"var({color_var})"
            stroke = f"var({color_var})" if lp else "var(--ground)"
            end = (f'<circle cx="{jsnum(x(last["year"]))}" cy="{jsnum(y(last["v"]))}" r="4" fill="{fill}" stroke="{stroke}" '
                   f'stroke-width="2"/>'
                   f'<text x="{jsnum(x(last["year"]) + 7)}" y="{jsnum(y(last["v"]) + 4)}" font-size="12" fill="var(--ink)" '
                   f'font-family="var(--f-sans)" font-weight="600">{jsfmt(last["v"], d)}{"†" if lp else ""}</text>')
        aria = f'{esc(label)}{"" if count else " per 1,000 residents"} in {esc(t)}, {y0}–{y1}'
        if last:
            aria += f'; latest {last["year"]}: {jsfmt(last["v"], d)}'
            if last.get("m") and last["m"] < 12:
                aria += f' (only {last["m"]} of 12 months reported)'
        grid = "".join(
            f'<line x1="{L}" x2="{W - R}" y1="{jsnum(y(tk))}" y2="{jsnum(y(tk))}" stroke="var(--grid)" stroke-width="1"/>'
            f'<text x="{L - 6}" y="{jsnum(y(tk) + 4)}" text-anchor="end" font-size="11" fill="var(--muted)" '
            f'font-family="var(--f-sans)">{jsfmt(tk, 1 if tk < 10 and tk % 1 else 0)}</text>' for tk in ticks)
        xs = "".join(
            f'<text x="{jsnum(x(tk))}" y="{H - 6}" text-anchor="middle" font-size="11" fill="var(--muted)" '
            f'font-family="var(--f-sans)">{tk}</text>' for tk in xt)
        body = (paths + part + end) if pts else (
            f'<text x="{jsnum((L + W - R) / 2)}" y="{jsnum(H / 2)}" text-anchor="middle" font-size="12" '
            f'fill="var(--muted)">no data</text>')
        data = esc(json.dumps(pts, separators=(",", ":"), ensure_ascii=False))
        out.append(
            f'<div class="panel-chart" data-pts="{data}" data-y0="{y0}" data-y1="{y1}" data-vmax="{jsnum(vmax)}" '
            f'data-label="{esc(label)}"><h4><i style="background:var({color_var})"></i>{esc(t)}</h4>'
            f'<svg viewBox="0 0 {W} {H}" role="img" tabindex="0" aria-label="{aria}">{grid}{xs}{body}'
            f'<line class="xh" y1="{T}" y2="{H - B}" stroke="var(--muted)" stroke-width="1" visibility="hidden"/>'
            f'</svg><div class="tip" hidden></div></div>')
    return "".join(out)


def crash_series(crashes, towns=CORE_TOWNS):
    """crashes.stats -> an fbi-shaped dict with one row per year (years with no serious crash are real zeros)."""
    st = crashes.get("stats") or []
    if not st:
        return {"agencies": []}
    y0, y1 = min(r["year"] for r in st), max(r["year"] for r in st)
    by = {(r["t"], r["year"]): r for r in st}
    return {"agencies": [{"municipality": t, "years": [{"year": y, "crashes": by[(t, y)]["crashes"] if (t, y) in by else 0}
                                                      for y in range(y0, y1 + 1)]} for t in towns]}


def pop_chart(facts, label="New Kensington population by census year"):
    """Horizontal bars of facts.population_by_census (port of the old renderStory chart). SVG only: the caller adds
    the fixed gap copy and the credit (never facts.population_note)."""
    pops = sorted((int(y), v) for y, v in (facts.get("population_by_census") or {}).items())
    if not pops:
        return ""
    RH, Wd, X0 = 26, 320, 44
    span = Wd - X0 - 56
    mx = max(v for _, v in pops)
    bars = []
    for i, (yr, v) in enumerate(pops):
        top, w = i * RH, v / mx * span
        bars.append(
            f'<text x="0" y="{top + 17}" font-size="12" fill="var(--muted)" font-family="var(--f-sans)">{yr}</text>'
            f'<rect x="{X0}" y="{top + 5}" width="{fixed1(w)}" height="15" fill="{"var(--river-peak)" if v == mx else "var(--river)"}"/>'
            f'<text x="{fixed1(X0 + w + 6)}" y="{top + 17}" font-size="12" font-weight="600" fill="var(--ink)" '
            f'font-family="var(--f-sans)">{jsfmt(v)}</text>')
    aria = f'{esc(label)}: ' + ", ".join(f"{y} {jsfmt(v)}" for y, v in pops)
    return (f'<svg class="pop-chart" viewBox="0 0 {Wd} {len(pops) * RH}" width="100%" role="img" aria-label="{aria}">'
            + "".join(bars) + "</svg>")
