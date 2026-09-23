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
| Crime & policing | FBI UCR counts, arrests, clearances and staffing for the 3 police departments (2000–2024); 43 mapped incidents (2018–26): 41 verified news incidents from 2022–26 plus 2 fatal police shootings; 146 police-reported fatal/serious crashes (PennDOT, 2005–2024) |

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
- **Safety:**
  - Crime rates per 1,000 residents from the FBI's Uniform Crime Reporting
    data, shown as small-multiple trends per town. Partial-year reports are
    flagged.
  - Arrests, clearance rates, assaults on officers and police staffing.
  - Police departments and notable police interactions.
  - A filterable list of news-reported incidents that doubles as a map
    layer (**INC** button).
  - PennDOT's police-reported fatal and serious-injury crashes, shown as a
    chart and as a map layer (**CRASH** button).
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
python scripts/fetch_crime.py      # FBI UCR per-department CSVs + PennDOT serious crashes → data/research/crime/
python scripts/build_safety.py     # geocode incidents + stats → site/data/safety.json
python -m unittest discover -s tests
```

### Crime & policing data: rules

- **FBI statistics** come from each department's own Uniform Crime Reporting
  submissions (Return A offenses and clearances, arson, LEOKA staffing and
  assaults on officers, arrests). They are read directly from Jacob Kaplan's
  per-agency files in
  [crimedatatool_helper](https://github.com/jacobkap/crimedatatool_helper).
  Years a department didn't report stay blank; nothing is interpolated.
- **Incidents** are a news-reported sample. Each one was gathered by
  independent search sweeps, then checked by two separate review lenses
  (evidence consistency, privacy/framing), and any disputes went to an
  arbiter.
- **Location precision:** locations are geocoded against the ZIP's address
  points and street centerlines. Every point except a named public place sits
  on the street centerline:
  - a hundred-block becomes the stretch of road beside that block;
  - an intersection is where the two centerlines meet;
  - "street only" is flagged on the map as approximate.

  The build refuses to publish a point within 6 m of any address point.
  Exact house numbers, article headlines and raw coordinates never ship, and
  the tests enforce all of this.
- **Crashes:** PennDOT's fatal and suspected-serious-injury crash records
  (via the [bencarneiro/ntsb](https://github.com/bencarneiro/ntsb) mirror).
  Spot-checked against PennDOT's full statewide crash files, and assigned to
  a town by its boundary polygon.
- **Privacy:** no names of suspects, victims or line officers. Individual
  sexual-offense incidents and anything identifying a juvenile are never
  published; FBI aggregate totals include sexual offenses.

- `fetch_overture.py` reads only the parquet row groups whose bounding box
  touches 15068, so a full refresh takes about 90 seconds. Set
  `OVERTURE_RELEASE` to pull a newer release.
- The curated research lives in `data/research/*.json`. Edit it by hand and
  re-run `build_data.py`.

### Data format

Geometry is projected to a local metre grid centred on the ZIP (x east,
y south), quantised to 0.25 m and delta-encoded. `meta.json` holds the
projection, bounds, terrain grid spec, stats and attributions. `terrain.png`
is an RGB heightmap: elevation in decimetres = R×256 + G.

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
