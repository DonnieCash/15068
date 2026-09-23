# NK15068

**New Kensington · Arnold · Lower Burrell.** A local guide and map of ZIP 15068,
built entirely from open data and published reporting: lost and found pets,
the phone numbers people need, what's coming up, plain answers on crime and
crashes, the three towns' history, and a map drawn from every building, road,
address point and business listing in the ZIP.

The site is static. `scripts/build_pages.py` writes every page as plain HTML
from the data files (Python standard library only), so the text is readable
without JavaScript and each topic has its own address. JavaScript only
refreshes the live parts: the lost-pets board, relative dates, filters and the
map. The site draws its own map from the scraped data, so it needs no tile
server or API key.

| What | How much (built 2026-09-23) |
| --- | --- |
| Buildings (footprints, 29k with real heights) | 19,242 inside the ZIP |
| Address points | 16,051 |
| Roads | 510 km, 790 named streets |
| Places & businesses | 1,256 (about 90% with no chain brand) |
| Terrain | 30 m grid, Allegheny about 220 m, ridges about 430 m |
| History | 61 dated timeline entries, 18 landmarks, 9 neighborhoods, 21 people |
| Civic / culture / news | 21 offices, 32 local spots, 10 parks, 23 news items (2025–26) |
| Lost & found pets | 18 sourced contacts and 6 tips, plus a live board |
| Crime & policing | FBI UCR counts, arrests, clearances and staffing for the 3 police departments (2000–2024); 43 mapped incidents (2018–26); 150 fatal/serious crashes (PennDOT, 2005–2024) |

## Pages

| Address | What it is |
| --- | --- |
| `/` | This week: the lost-pets box, the next three dates, numbers to keep, the crime answer, latest news |
| `/lost-pets/` | Who to call first, the board, the first-48-hours checklist; `post/` and `flyer/` |
| `/numbers/` | Every police, city hall, library, school and animal number, tap to call, prints on one sheet |
| `/calendar/` | Fridays on Fifth, council nights, deadlines and yearly events, sorted by next date |
| `/crime/`, `/crime/<town>/` | Is crime going up? Plain answers from each department's FBI reports |
| `/crime/blotter/` | News-reported incidents, on the block, filterable by town, year and street |
| `/crashes/` | PennDOT's fatal and serious crashes by town, year and road |
| `/towns/`, `/towns/<town>/` | Each city's hall, police, parks, neighborhoods, history and figures |
| `/news/`, `/history/`, `/history/people/`, `/eat/` | Credited news briefs, the history, notable people, where to eat |
| `/map/`, `/map/3d/` | The map explorer (search, layers, deep links) and the 3D view |
| `/poster/` | Every road in 15068 as a free poster, including a "your street" version |
| `/directory/`, `/search/` | Places and streets A to Z; site search |
| `/whats-new/`, `/about/`, `/privacy/`, `/contact/`, `/sources/` | Changelog, about, privacy, contact and sources |

Credits name the outlet ("Source: WPXI") and dates are AP style. Light and
dark themes, keyboard and touch support, reduced-motion aware, print styles.

## Build and run locally

```bash
python scripts/build_pages.py            # regenerate site/ after any change to data, research or templates
python scripts/build_pages.py --check    # exit 1 if the committed site/ is out of date (CI runs this)
python -m unittest discover -s tests
cd site && python -m http.server 8000    # open http://localhost:8000
```

Generated files (every `index.html`, `404.html`, `assets/app.js`,
`assets/nk.css`, `assets/pubs.js`, the SVG map art, `data/search.json`,
`sitemap.xml`, …) are listed in `site/data/build.json`. Edit the templates in
`scripts/nkpages/`, the styles in `site/assets/css/` and the scripts in
`site/assets/js/`, never the generated files. `tests/ui_check.mjs` runs the
browser checks by hand (see its header).

### Configuration: `data/site.json`

| Field | Meaning |
| --- | --- |
| `site_url`, `base_path` | Canonical URLs, sitemap and the 404 page's root-relative links |
| `owner_name` | Who runs the site, shown on About. Required before ads can be turned on |
| `contact_email` | Optional; shown on Contact and the post-a-pet page only when set |
| `adsense_client`, `adsense_slots` | Ads switch (see below). Empty means no ad code anywhere |
| `repo` | GitHub repo for the pets board, issue forms and corrections |
| `privacy_effective` | The privacy policy's effective date |

## Deploy

`.github/workflows/pages.yml` runs the tests, snapshots the open lost-pet
issues (`scripts/snapshot_pets.py`), rebuilds with `--snapshot` and publishes
`site/` to GitHub Pages. It runs on every push to `main`, whenever an issue
changes, and daily at 09:15 UTC so "This week" rolls forward. The snapshot,
the per-listing pages and the listings feed are built at deploy only and never
committed.

One-time setup:

- *Settings → Pages → Source: GitHub Actions.*
- Set the custom domain in *Settings → Pages* (the deploy action ignores `CNAME` files).
- Create the `pet-listing` and `correction` labels (the issue forms apply them).
- For the monthly refresh PRs: *Settings → Actions → General → Allow GitHub Actions to create and approve pull requests.*
- Submit `https://nk15068.com/sitemap.xml` in Google Search Console.

`.github/workflows/refresh.yml` re-pulls the data on the 3rd of each month,
rebuilds, records a What's new entry (`build_pages.py --log`) and opens a pull
request for review. It never merges on its own.

### Ads (off)

Ads are off until `adsense_client` is set (and the build refuses to turn them
on while `owner_name` is empty). When on, the AdSense script and at most two
server-rendered slots appear only on the nine long-form pages (`/crime/`, the
three department pages, `/crashes/`, the three town pages and `/history/`),
always after the emergency and contact blocks and at least 250 words in. Never
on the front page, the pets pages, the numbers, calendar, map or trust pages.

In the AdSense dashboard keep Auto ads, anchor ads and vignettes off, and turn
on the EEA/UK consent message. Resubmit for review only after the pages are
deployed and indexed and What's new shows at least three real data updates
spread over three to four weeks.

### Lost & found pets board

- **On GitHub Pages** the board lists open issues made with the
  [lost or found pet form](.github/ISSUE_TEMPLATE/lost-found-pet.yml). The
  deploy snapshot puts them in the HTML; the page asks GitHub's API only when
  the snapshot is missing or more than a day old. Posting means filling in that
  form (the site's post page fills it in for you), and closing the issue takes
  the listing down.
- **In the Claude artifact preview** it uses the artifact's shared `db`: each
  viewer can write only their own document (`pets/<their id>`), everyone can
  read all of them, and owners can mark a post reunited.

Locations are a street and cross street, placed on the site's own road data.
House numbers are stripped. A post that names only a street highlights the
street instead of showing a precise-looking dot.

## Rebuild the data

```bash
pip install -r requirements.txt
python scripts/fetch_overture.py   # Overture Maps GeoParquet from public S3 → data/raw/
python scripts/fetch_terrain.py    # AWS Terrain Tiles (z13) → data/raw/terrain.json
python scripts/build_data.py       # clip to 15068, project, compress → site/data/
python scripts/fetch_crime.py      # FBI UCR per-department CSVs + PennDOT serious crashes → data/research/crime/
python scripts/build_safety.py     # geocode incidents + stats → site/data/safety.json
python scripts/build_pages.py --log  # regenerate pages and record a What's new entry
python -m unittest discover -s tests
```

The curated research lives in `data/research/*.json`. Edit it by hand, then run
`python scripts/build_pages.py` (it syncs the research into `site/data/`).

### Crime & policing data: rules

- **FBI statistics** come from each department's own Uniform Crime Reporting
  submissions (Return A offenses and clearances, arson, LEOKA staffing and
  assaults on officers, arrests), read from Jacob Kaplan's per-agency files in
  [crimedatatool_helper](https://github.com/jacobkap/crimedatatool_helper).
  Years a department didn't report stay blank; nothing is interpolated.
  Partial years are compared as monthly averages.
- **Incidents** are a news-reported sample, each checked for evidence
  consistency and privacy before publishing.
- **Location precision:** locations are geocoded against the ZIP's address
  points and street centerlines. A hundred-block becomes the stretch of road
  beside that block, an intersection is where two centerlines meet, and
  "street only" is flagged as approximate. The build refuses to publish a
  point within 6 m of any address point. Exact house numbers, article
  headlines and raw coordinates never ship, and the tests enforce all of this.
- **Crashes:** PennDOT's fatal and suspected-serious-injury crash records
  (via the [bencarneiro/ntsb](https://github.com/bencarneiro/ntsb) mirror),
  assigned to a town by its boundary polygon.
- **Privacy:** no names of suspects, victims or line officers. Individual
  sexual-offense incidents and anything identifying a juvenile are never
  published; FBI aggregate totals include sexual offenses.

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
- History, civic, news and pets entries each cite their own source.

The earlier Minecraft digital-twin experiment lives on the
`claude/minecraft-new-kensington-twin-jnri2p` branch.
