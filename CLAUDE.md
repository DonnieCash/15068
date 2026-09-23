# CLAUDE.md

## What this is
NK15068: a static website + self-drawn map of ZIP 15068 (New Kensington,
Arnold, Lower Burrell, PA), built from open data.

## Layout
- `site/` — the deployable site. **Pages are generated and committed**: every `index.html`, `404.html`,
  `assets/app.js`, `assets/nk.css`, `assets/pubs.js`, SVG map art, `data/search.json`, robots/sitemap/manifest
  (the full list is `site/data/build.json`). Never hand-edit a generated file.
  - `assets/css/*.css` — style sources, concatenated into `assets/nk.css` (tokens: light on `:root`, dark via media
    query + `[data-theme]`; Newsreader + Radio Canada; `--f-display/--f-body/--f-mono` stay literal font stacks
    because the canvas reads them).
  - `assets/js/*.js` — the shell (`window.NKS`) and one module per group of pages (`NKS.pages[<data-page>]`),
    concatenated into `assets/app.js`.
  - `assets/nkmap.js` — data loading/decoding + 2D canvas map (`window.NK`).
  - `assets/nk3d.js` — three.js (r128 from cdnjs, global `THREE`), only on `/map/3d/`.
  - `assets/safety.js` — chart wiring and the blotter filters (`window.NKSafety`).
  - `assets/pets.js` — lost & found board (deploy snapshot, else GitHub issues; artifact `db` in previews) + street geocoder.
  - `assets/search.js` — search shared by `/search/` and the map panel.
- `scripts/build_pages.py` + `scripts/nkpages/` — the page generator (stdlib only; must not import build_data or
  build_safety): `routes.py` (every page), `shell.py` (head, masthead, bar, footer, ad slots), `fmt.py` (escaping,
  AP dates, credits, tel links, `public()`), one `pages_*.py` per group of pages, plus sentences, charts, calendar,
  pets, mapsvg, search, changelog.
- `scripts/snapshot_pets.py` — CI only: open pet issues → `site/data/pets-board.json` (gitignored).
- `scripts/` pipeline — `fetch_overture.py`, `fetch_terrain.py`, `build_data.py`, `fetch_crime.py`
  (FBI UCR → research/crime/fbi.json), `build_safety.py` (geocodes incidents to hundred-blocks → site/data/safety.json).
- `data/site.json` — site config (URL, owner, contact, ads switch). `data/changelog.json` + `data/build_digest.json` — What's new.
- `data/research/` — hand-curated, sourced JSON (history.json, civic.json, pets.json, crime/).
- `data/raw/` — gitignored raw pulls (except the ZCTA boundary).

## Commands
```bash
python scripts/build_pages.py           # after any change to research, data, templates, css or js
python scripts/build_pages.py --check   # CI: committed site/ must match a fresh build
python scripts/build_pages.py --log     # after a data refresh: record a What's new entry, then rebuild
python -m unittest discover -s tests
cd site && python -m http.server 8000
node tests/ui_check.mjs                 # browser checks, by hand (see the file header)
```

## Conventions
- Every researched fact carries a `source` URL; never add unsourced claims. Research text reaches HTML only
  through `fmt.public()`; internal notes (`_meta`, `note`, "verify" remarks) are never printed.
- Crime/police data: never publish names of private people or line officers,
  exact house numbers, individual sexual-offense incidents (FBI totals may
  include them), or juvenile-identifying details.
  Incidents are rounded to the hundred-block (tests enforce it).
- Keep the site dependency-free apart from three.js (only `/map/3d/`) + Google Fonts. The one exception is the
  AdSense script, and only once `adsense_client` is set in `data/site.json`.
- Ads: only on the nine ad-eligible routes in `routes.py` (`ads="C"`), server-rendered, after every
  `data-keep-above` block and at least 250 words in. Never on the front page, pets, numbers, calendar, map or trust pages.
- Design: no eyebrow labels over headings (datelines go under the H1); credit outlets by name; AP dates;
  no arrows except ›; maroon (`--press`/`--bar`) is page chrome only, never in charts or map layers.
- Links between pages are relative to page depth (`shell.rel`); JS fetches through `NKS.url()`.
- Pets board: never store or show house numbers; issue-form labels must match `field("…")` in pets.js (tested).
  The board snapshot and `/lost-pets/gh-N/` pages are built at deploy only and never committed.
- World coords: metres, x east / y south, origin in `build_data.py` (LON0/LAT0).
- Network note for cloud sessions: Overture's S3 bucket, raw.githubusercontent.com
  and the AWS terrain bucket are reachable; Overpass/Wikipedia/census.gov are not.
