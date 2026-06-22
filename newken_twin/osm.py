"""Build a :class:`City` from live OpenStreetMap data via the Overpass API.

This is the path to an *exact* twin: real building footprints, the real street
network, the river and parks.  It only needs the Python standard library.

Network access is required.  In sandboxes where Overpass is unreachable the
bundled dataset (:func:`newken_twin.data.load_default_city`) is used instead;
this module raises :class:`OverpassError` rather than failing silently.
"""

from __future__ import annotations

import json
import urllib.error
import urllib.parse
import urllib.request
from typing import List, Optional

from .geo import BBox, LatLon
from .model import City, city_from_dict

OVERPASS_URL = "https://overpass-api.de/api/interpreter"


class OverpassError(RuntimeError):
    pass


def _build_query(bbox: BBox) -> str:
    s, w, n, e = bbox.south, bbox.west, bbox.north, bbox.east
    box = f"{s},{w},{n},{e}"
    return f"""
    [out:json][timeout:60];
    (
      way["building"]({box});
      way["highway"]({box});
      way["waterway"="riverbank"]({box});
      way["natural"="water"]({box});
      relation["natural"="water"]({box});
      way["leisure"="park"]({box});
    );
    out geom;
    """.strip()


def fetch_raw(bbox: BBox, url: str = OVERPASS_URL, timeout: int = 90) -> dict:
    query = _build_query(bbox)
    data = urllib.parse.urlencode({"data": query}).encode("utf-8")
    req = urllib.request.Request(url, data=data,
                                 headers={"User-Agent": "newken_twin/1.0"})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except (urllib.error.URLError, urllib.error.HTTPError, TimeoutError) as exc:
        raise OverpassError(f"Overpass request failed: {exc}") from exc


def _levels_from_tags(tags: dict) -> int:
    for key in ("building:levels", "levels"):
        if key in tags:
            try:
                return max(1, int(float(tags[key])))
            except ValueError:
                pass
    if "height" in tags:
        try:
            return max(1, int(float(tags["height"]) / 3.2))
        except ValueError:
            pass
    return 2


def overpass_to_dict(raw: dict, name: str, center: LatLon) -> dict:
    features: List[dict] = []
    for el in raw.get("elements", []):
        geom = el.get("geometry")
        tags = el.get("tags", {})
        if not geom:
            continue
        coords = [[g["lon"], g["lat"]] for g in geom]
        if "building" in tags:
            features.append({
                "kind": "building",
                "geometry": coords,
                "levels": _levels_from_tags(tags),
                "name": tags.get("name", ""),
            })
        elif "highway" in tags:
            features.append({
                "kind": "road",
                "geometry": coords,
                "class": tags["highway"],
                "name": tags.get("name", ""),
                "bridge": tags.get("bridge") in ("yes", "viaduct"),
            })
        elif tags.get("natural") == "water" or tags.get("waterway") == "riverbank":
            features.append({"kind": "water", "geometry": coords,
                             "name": tags.get("name", "")})
        elif tags.get("leisure") == "park":
            features.append({"kind": "park", "geometry": coords,
                             "name": tags.get("name", "")})
    return {"name": name, "center": [center.lat, center.lon],
            "features": features}


def fetch_city(bbox: BBox, name: str = "New Kensington, PA",
               center: Optional[LatLon] = None,
               url: str = OVERPASS_URL) -> City:
    raw = fetch_raw(bbox, url=url)
    doc = overpass_to_dict(raw, name, center or bbox.center)
    return city_from_dict(doc)
