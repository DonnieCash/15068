# NK15068

**New Kensington · Arnold · Lower Burrell.** A website and map of ZIP 15068,
built entirely from open data. It includes every building, road, address point
and business listing in the ZIP, draped over real terrain, alongside a sourced
history, civic directory, local picks and recent news.

The site is static HTML/JS in `site/`, with no framework and no build step. It
draws its own map from the scraped data, so it needs no tile server or API key.

| What | How much (built 2026-09-23) |
| --- | --- |
| Buildings (footprints, 29k with real heights) | 19,242 inside the ZIP |
| Address points | 16,051 |
| Roads | 510 km, 790 named streets |
| Places & businesses | 1,256 (≈90% independent) |
| Terrain | 30 m grid, Allegheny ≈ 220 m → ridges ≈ 430 m |
| History | 61 dated timeline entries, 18 landmarks, 9 neighborhoods, 21 people |
| Civic / culture / news | 21 offices, 32 local spots, 10 parks, 23 news items (2025–26) |

## What's on the page

- **Hero:** the ZIP's real road network draws itself outward from downtown New Ken.
- **By the numbers:** counts computed from the data, not estimated.
- **Map explorer:** pan, zoom and pinch; search 1,256 places and 790 streets;
  filter by category; toggle buildings and terrain relief; tap any pin for its
  address, phone, website and directions.
  - **3D mode:** real elevation (1.5× vertical exaggeration) with every
    building extruded to its height. It slowly orbits downtown until you
    grab it.
- **Three towns:** a street map and stats for each city.
- **Story:** a population chart and timeline from 1769 to 2026, plus
  neighborhoods and landmarks.
- **Eat & Drink**, **Events**, **Directory** (places, streets, public offices),
  **People** and **News**. Every researched entry links to its source.
- Light and dark themes, keyboard and touch support, reduced-motion aware.

## Run it locally

```bash
cd site && python -m http.server 8000   # open http://localhost:8000
```

## Deploy

`.github/workflows/pages.yml` runs the tests and publishes `site/` to GitHub
Pages on every push to `main`. Enable it once under *Settings → Pages →
Source: GitHub Actions*.

## Rebuild the data

```bash
pip install -r requirements.txt
python scripts/fetch_overture.py   # Overture Maps GeoParquet from public S3 → data/raw/
python scripts/fetch_terrain.py    # AWS Terrain Tiles (z13) → data/raw/terrain.json
python scripts/build_data.py       # clip to 15068, project, compress → site/data/
python -m unittest discover -s tests
```

- `fetch_overture.py` reads only the parquet row groups whose bounding box
  touches 15068, so a full refresh takes about 90 seconds. Set
  `OVERTURE_RELEASE` to pull a newer release.
- The curated research lives in `data/research/*.json`. Edit it by hand and
  re-run `build_data.py`.

### Data format

Geometry is projected to a local metre grid centred on the ZIP (x east,
y south), quantised to 0.25 m and delta-encoded. `meta.json` holds the
projection, bounds, terrain grid spec, stats and attributions. `terrain.bin`
is little-endian uint16 elevation in decimetres.

## Sources & licenses

- [Overture Maps Foundation](https://overturemaps.org): places, buildings,
  transportation, addresses, divisions, base layers. CDLA-Permissive-2.0 /
  ODbL (OpenStreetMap-derived).
- © [OpenStreetMap contributors](https://www.openstreetmap.org/copyright), ODbL.
- US Census TIGER/Line ZCTA5 boundary for 15068 (public domain).
- [Terrain Tiles on AWS](https://registry.opendata.aws/terrain-tiles/)
  (USGS 3DEP / SRTM).
- History, civic and news entries each cite their own source. These were
  compiled from search results on 2026-09-23, so verify anything important.

The earlier Minecraft digital-twin experiment lives on the
`claude/minecraft-new-kensington-twin-jnri2p` branch.
