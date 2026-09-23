# NK15068

**New Kensington · Arnold · Lower Burrell.** A website and map of ZIP 15068,
built entirely from open data. It includes every building, road, address point
and business listing in the ZIP, draped over real terrain, alongside sourced
news, crime data, history, a civic directory, local picks and a lost & found
pets board.

The site is static HTML/JS in `site/`, with no framework and no build step. It
draws its own map from the scraped data, so it needs no tile server or API key.

| What | How much (built 2026-09-23) |
| --- | --- |
| Buildings (footprints, 29k with real heights) | 19,242 inside the ZIP |
| Address points | 16,051 |
| Roads | 510 km, 790 named streets |
| Places & businesses | 1,256 (about 90% with no chain brand) |
| Terrain | 30 m grid, Allegheny about 220 m, ridges about 430 m |
| History | 61 dated timeline entries, 18 landmarks, 9 neighborhoods, 21 people |
| Civic / culture / news | 21 offices, 32 local spots, 10 parks, 23 news items (2025–26) |
| Lost & found pets | 18 sourced contacts (dog warden, shelters, police non-emergency lines, emergency vets, licensing, online boards) and 6 tips, plus a live board |
| Crime & policing | FBI UCR counts, arrests, clearances and staffing for the 3 police departments (2000–2024); 43 mapped incidents (2018–26): 41 verified news incidents from 2022–26 plus 2 fatal police shootings; 146 police-reported fatal/serious crashes (PennDOT, 2005–2024) |

## What's on the page

The page is laid out like a small regional daily: a utility strip, a
left-aligned nameplate with an "ear", and a sticky maroon section bar. Type is
Newsreader (headlines and text) and Radio Canada (tables, credits, map UI), and
each section uses its own grid rather than one repeated card template.

- **Front:** a still drawing of the ZIP's roads (state routes in orange), the
  lead, and a rail with "15068 by the count", the latest headlines and a count
  of open lost-pet listings.
- **Map explorer:** pan, zoom and pinch; search 1,256 places and 790 streets
  (state routes 56, 366, 380 and 780 get keystone shields); filter by category.
  A **Layers** menu toggles buildings, terrain relief, 3D, crime incidents,
  serious crashes and lost pets, and jumps to downtown or the whole ZIP.
  - **3D mode:** real elevation (1.5× vertical exaggeration) with every
    building extruded to its height.
- **News:** a three-column river of credited summaries, newest first.
- **Lost & found pets:** classified-style listings pinned on the map, a
  "place a free listing" box, and who to call in 15068 (see below).
- **Towns:** a street map, incorporation dates and figures for each city.
- **Crime & safety:**
  - A box score of the latest FBI rates per department, then small-multiple
    trends for violent crime, property crime and arrests. Partial-year
    reports are flagged.
  - Clearances, assaults on officers, staffing and a rail on each department.
  - Police shootings, lawsuits and policy changes, and a filterable **police
    blotter** of news-reported incidents that doubles as a map layer.
  - PennDOT's police-reported fatal and serious-injury crashes.
- **History:** a chronology from 1769 to 2026, a population chart, and
  neighborhoods and landmarks.
- **Eat & drink** (grouped like a dining guide), a **community calendar**,
  **People**, a **business directory** (places, streets, public offices), and
  **Sources**. Credits name the outlet ("Source: WPXI") and dates are AP style.
- Light and dark themes, keyboard and touch support, reduced-motion aware,
  and a print stylesheet.

### Lost & found pets board

The board picks its backend at run time:

- **On GitHub Pages** it lists open issues made with the
  [lost or found pet form](.github/ISSUE_TEMPLATE/lost-found-pet.yml),
  read through GitHub's public API. Posting a listing means filling in that
  form, and closing the issue takes it down.
- **In the Claude artifact preview** it uses the artifact's shared `db`: each
  viewer can write only their own document (`pets/<their id>`), everyone can
  read all of them, and owners can mark a post reunited.

Locations are a street and cross street, placed on the site's own road data.
House numbers are stripped, and a spot picked on the map is rounded to 10 m.

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
- History, civic, news and pets entries each cite their own source. These were
  compiled from search results on 2026-09-23, so verify anything important.

The earlier Minecraft digital-twin experiment lives on the
`claude/minecraft-new-kensington-twin-jnri2p` branch.
