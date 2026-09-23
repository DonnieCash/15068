"""Pull every Overture Maps feature inside ZIP 15068's bounding box.

Reads GeoParquet straight from the public Overture S3 bucket (anonymous),
uses row-group bbox statistics to skip the rest of the planet, and writes
one GeoJSON per feature type into data/raw/.
"""
import json
import os
import sys
from pathlib import Path

import pyarrow.compute as pc
import pyarrow.dataset as ds
import pyarrow.fs as fs
from shapely import wkb

RELEASE = os.environ.get("OVERTURE_RELEASE", "2026-08-19.0")
BBOX = (-79.8218, 40.4948, -79.6283, 40.6439)  # ZCTA 15068 bounds
OUT = Path(__file__).resolve().parent.parent / "data" / "raw"

TYPES = {
    "place": "places",
    "building": "buildings",
    "segment": "transportation",
    "address": "addresses",
    "division_area": "divisions",
    "land_use": "base",
    "water": "base",
    "infrastructure": "base",
    "land": "base",
}


def s3():
    proxy = os.environ.get("HTTPS_PROXY") or os.environ.get("https_proxy")
    kw = dict(anonymous=True, region="us-west-2")
    if proxy:
        kw["proxy_options"] = proxy
    return fs.S3FileSystem(**kw)


def jsonable(v):
    if isinstance(v, (bytes, bytearray)):
        return None
    if isinstance(v, dict):
        return {k: jsonable(x) for k, x in v.items() if x is not None}
    if isinstance(v, list):
        return [jsonable(x) for x in v]
    return v


def fetch(kind, theme, filesystem):
    path = f"overturemaps-us-west-2/release/{RELEASE}/theme={theme}/type={kind}/"
    dset = ds.dataset(path, filesystem=filesystem, format="parquet")
    xmin, ymin, xmax, ymax = BBOX
    f = lambda k: ds.field("bbox", k)
    flt = ((f("xmin") < xmax) & (f("xmax") > xmin) &
           (f("ymin") < ymax) & (f("ymax") > ymin))
    table = dset.to_table(filter=flt)
    feats = []
    for row in table.to_pylist():
        geom = wkb.loads(row.pop("geometry"))
        row.pop("bbox", None)
        feats.append({"type": "Feature", "id": row.get("id"),
                      "geometry": geom.__geo_interface__,
                      "properties": jsonable(row)})
    out = OUT / f"{kind}.geojson"
    out.write_text(json.dumps({"type": "FeatureCollection", "features": feats}))
    print(f"{kind}: {len(feats)} features -> {out}", flush=True)


if __name__ == "__main__":
    OUT.mkdir(parents=True, exist_ok=True)
    f = s3()
    kinds = sys.argv[1:] or list(TYPES)
    for k in kinds:
        fetch(k, TYPES[k], f)
