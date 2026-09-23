"""FBI UCR statistics and PennDOT serious crashes for 15068, straight from source.

    python scripts/fetch_crime.py        # -> data/research/crime/fbi.json + crashes.json

Crashes: PennDOT's fatal and suspected-serious-injury ("KSI") crash records with
coordinates, 2005-2024, as mirrored in github.com/bencarneiro/ntsb (the data behind
roadway.report; its crash numbers match PennDOT's full statewide CRASH files).

Reads Jacob Kaplan's per-agency CSVs (github.com/jacobkap/crimedatatool_helper,
the backend of crimedatatool.com), which are built from the FBI's Uniform Crime
Reporting master files: Return A offenses + clearances, arson, LEOKA (police
employees and assaults on officers) and arrests. Years a department did not
report are left null — nothing is interpolated.
"""
from __future__ import annotations

import csv
import io
import json
import urllib.request
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "data" / "research" / "crime" / "fbi.json"
RAW = "https://raw.githubusercontent.com/jacobkap/crimedatatool_helper/master/data"
REPO = "https://github.com/jacobkap/crimedatatool_helper/blob/master/data"
FIRST_YEAR = 2000

AGENCIES = [
    ("New Kensington", "New_Kensington"),
    ("Arnold", "Arnold"),
    ("Lower Burrell", "Lower_Burrell"),
]

DRUGS = ("marijuana", "opium_and_cocaine_and_derivatives_including_heroin", "synthetic_narcotics", "other_drug")

ARREST_GROUPS = {
    "violent": ["murder_and_nonnegligent_manslaughter", "rape", "robbery", "aggravated_assault"],
    "property": ["burglary", "theft", "motor_vehicle_theft", "arson"],
    "drugs": ["drug_total_drug"],
    "dui": ["dui"],
    "other_assault": ["other_assault"],
    "public_order": ["disorderly_conduct", "drunkenness", "liquor_laws", "vandalism", "weapons_carrying_possessing_etc"],
}


def fetch(kind: str, slug: str) -> list[dict]:
    url = f"{RAW}/{kind}/Pennsylvania_{slug}_Police_Department.csv"
    with urllib.request.urlopen(url, timeout=60) as r:
        return list(csv.DictReader(io.StringIO(r.read().decode("utf-8"))))


def num(v):
    if v in (None, "", "NA"):
        return None
    try:
        return int(float(v))
    except ValueError:
        return None


def by_year(rows):
    return {int(r["year"][:4]): r for r in rows}


def build_agency(town: str, slug: str) -> dict:
    off = by_year(fetch("offenses", slug))
    ars = by_year(fetch("arson", slug))
    leo = by_year(fetch("leoka", slug))
    arr = by_year(fetch("arrests", slug))
    months = Counter()
    for r in fetch("offenses_monthly", slug):
        if r.get("card_actual_type") not in ("", "NA", None):
            months[int(r["year"][:4])] += 1
    ori = next((r.get("ORI") for r in off.values() if r.get("ORI")), None)
    src = lambda kind: f"{REPO}/{kind}/Pennsylvania_{slug}_Police_Department.csv"

    years = []
    last = max(off) if off else FIRST_YEAR
    for y in range(FIRST_YEAR, last + 1):
        o, a, l, r = off.get(y, {}), ars.get(y, {}), leo.get(y, {}), arr.get(y, {})
        reported = months.get(y, 0)
        rec = {"year": y, "population": num(o.get("population")) or num(l.get("population")) or num(r.get("population")),
               "months_reported": reported, "sources": []}
        if reported and num(o.get("actual_index_violent")) is not None:
            rec.update({
                "violent": num(o.get("actual_index_violent")),
                "murder": num(o.get("actual_murder")),
                "rape": num(o.get("actual_rape_total")),
                "robbery": num(o.get("actual_robbery_total")),
                "agg_assault": num(o.get("actual_assault_aggravated")),
                "property": num(o.get("actual_index_property")),
                "burglary": num(o.get("actual_burglary_total")),
                "larceny": num(o.get("actual_theft_total")),
                "mvt": num(o.get("actual_motor_vehicle_theft_total")),
                "simple_assault": num(o.get("actual_assault_simple")),
                "cleared_violent": num(o.get("total_cleared_index_violent")),
                "cleared_property": num(o.get("total_cleared_index_property")),
            })
            rec["sources"].append(src("offenses"))
            if num(a.get("actual_grand_total")) is not None:
                rec["arson"] = num(a.get("actual_grand_total"))
                rec["sources"].append(src("arson"))
        if num(l.get("total_employees_total")):
            rec["officers"] = num(l.get("total_employees_officers"))
            rec["civilians"] = num(l.get("total_employees_civilians"))
            inj, noinj = num(l.get("assaults_with_injury_total")), num(l.get("assaults_no_injury_total"))
            if inj is not None or noinj is not None:
                rec["officers_assaulted"] = (inj or 0) + (noinj or 0)
            rec["sources"].append(src("leoka"))
        total = num(r.get("all_arrests_total_total_arrests"))
        if total:
            rec["arrests"] = {"total": total, "adult": num(r.get("all_arrests_total_total_adult")),
                              "juvenile": num(r.get("all_arrests_total_total_juvenile"))}
            for g, keys in ARREST_GROUPS.items():
                vals = [num(r.get(f"{k}_total_arrests")) for k in keys]
                rec["arrests"][g] = sum(v for v in vals if v is not None) if any(v is not None for v in vals) else None
            # drug arrests: the per-drug possession/sale columns are the detail the FBI
            # actually records; the rolled-up totals are sometimes 0 or inflated (e.g. 560)
            per = [num(r.get(f"drug_{a}_{d}_total_arrests")) for a in ("possess", "sale") for d in DRUGS]
            dt = rec["arrests"]["drugs"]
            if any(v is not None for v in per):
                ps = sum(v for v in per if v is not None)
                rec["arrests"]["drugs"] = ps
                if dt is not None and dt != ps:
                    rec["arrests"]["drugs_note"] = f"sum of possession + sale by drug ({ps}); the FBI roll-up column says {dt}"
            if rec["arrests"]["drugs"] == 0 and total >= 100:
                rec["arrests"]["drugs"] = None
                rec["arrests"]["drugs_note"] = f"reported as 0 alongside {total} total arrests; category likely unreported"
            # internal consistency: male + female should add up to the total
            mf = [num(r.get("all_arrests_total_total_male")), num(r.get("all_arrests_total_total_female"))]
            if all(v is not None for v in mf) and sum(mf) and abs(sum(mf) - total) > max(10, 0.1 * total):
                rec["arrests"]["note"] = f"FBI total ({total}) disagrees with its male + female breakdown ({sum(mf)})"
                rec["arrests"]["total"] = None
            rec["sources"].append(src("arrests"))
        if 0 < reported < 12:
            rec["note"] = f"Only {reported} of 12 months reported to the FBI; counts are partial."
        if rec["sources"]:
            years.append(rec)
    return {"agency": f"{town} Police Department", "municipality": town, "ori": ori, "years": years}


CRASH_URL = "https://raw.githubusercontent.com/bencarneiro/ntsb/master/pennsylvania/crash_{y}.csv"
CRASH_REPO = "https://github.com/bencarneiro/ntsb/tree/master/pennsylvania"
BBOX = (-79.8218, 40.4948, -79.6283, 40.6439)   # ZCTA 15068
# PennDOT municipality codes seen in and around 15068 (Westmoreland = county 64). The
# code -> town mapping is learned from the crashes' own coordinates in build_safety.
MUNI_HINT = {"64301", "64305", "64306"}
COLLISION = {"0": "Non-collision", "1": "Rear-end", "2": "Head-on", "3": "Backing", "4": "Angle",
             "5": "Sideswipe (same direction)", "6": "Sideswipe (opposite direction)", "7": "Hit fixed object",
             "8": "Hit pedestrian", "9": "Other"}


def fetch_crashes(first=2005, last=2024):
    """Fatal + serious-injury crashes inside the ZIP's bounding box (towns assigned later)."""
    pts = []
    for y in range(first, last + 1):
        try:
            with urllib.request.urlopen(CRASH_URL.format(y=y), timeout=120) as r:
                rows = csv.DictReader(io.StringIO(r.read().decode("utf-8")))
                for x in rows:
                    if x.get("COUNTY", "").strip() != "64":
                        continue
                    muni = (x.get("MUNICIPALITY") or "").strip()
                    try:
                        lat, lon = float(x["DEC_LATITUDE"]), float(x["DEC_LONGITUDE"])
                    except (TypeError, ValueError):
                        lat = lon = None
                    in_box = lat is not None and BBOX[0] <= lon <= BBOX[2] and BBOX[1] <= lat <= BBOX[3]
                    if not in_box and muni not in MUNI_HINT:
                        continue
                    fatal, serious = num(x.get("FATAL_COUNT")) or 0, num(x.get("SUSP_SERIOUS_INJ_COUNT")) or 0
                    if not (fatal or serious):
                        continue
                    pts.append({"year": y, "month": num(x.get("CRASH_MONTH")), "muni": muni,
                                "lat": round(lat, 5) if in_box else None, "lon": round(lon, 5) if in_box else None,
                                "fatal": fatal, "serious": serious,
                                "collision": COLLISION.get(str(num(x.get("COLLISION_TYPE"))), "Other")})
        except Exception as exc:  # a missing year shouldn't sink the build
            print(f"  crashes {y}: {exc}")
    return pts


def main():
    crashes = fetch_crashes()
    (OUT.parent / "crashes.json").write_text(json.dumps({
        "source": CRASH_REPO,
        "notes": ("PennDOT fatal and suspected-serious-injury crashes (police-reported), 2005-2024, "
                  "from the bencarneiro/ntsb mirror of PennDOT crash data; spot-checked against PennDOT's "
                  "full statewide CRASH files for 2012-2016."),
        "points": crashes}, indent=1))
    print(f"crashes in bbox: {len(crashes)}")
    agencies = [build_agency(t, s) for t, s in AGENCIES]
    doc = {
        "agencies": agencies,
        "method": ("Counts are the FBI Uniform Crime Reporting figures each department submitted "
                   "(Return A offenses and clearances, arson, police employee/LEOKA and arrest files), "
                   "compiled per agency by Jacob Kaplan's crimedatatool and read directly from its GitHub data. "
                   "Spot-checked against the FBI's published Crime in the United States Table 8 for Pennsylvania."),
        "gaps": "",
        "source": "https://github.com/jacobkap/crimedatatool_helper",
    }
    missing = []
    for ag in agencies:
        have = {y["year"] for y in ag["years"] if y.get("violent") is not None}
        last = max((y["year"] for y in ag["years"]), default=FIRST_YEAR)
        gone = [y for y in range(FIRST_YEAR, last + 1) if y not in have]
        if gone:
            missing.append(f"{ag['municipality']}: no offense counts for {', '.join(map(str, gone))}")
    doc["gaps"] = ("; ".join(missing) + ". 2021 is missing for most Pennsylvania agencies because of the FBI's switch "
                   "to incident-based reporting (NIBRS).") if missing else ""
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(doc, indent=1))
    for ag in agencies:
        ys = [y["year"] for y in ag["years"] if y.get("violent") is not None]
        print(f"{ag['agency']} ({ag['ori']}): offense years {ys[0] if ys else '-'}–{ys[-1] if ys else '-'}, {len(ys)} years")
    print("gaps:", doc["gaps"])


if __name__ == "__main__":
    main()
