# CLAUDE.md

## What this is
NK15068: a static website + self-drawn map of ZIP 15068 (New Kensington,
Arnold, Lower Burrell, PA), built from open data.

## Layout
- `site/` — the deployable site (index.html, assets/, data/). No build step.
  - `assets/nkmap.js` — data loading/decoding + 2D canvas map (`window.NK`).
  - `assets/nk3d.js` — three.js (r128 from cdnjs, global `THREE`) terrain + buildings.
  - `assets/app.js` — page sections, search, directory, wiring.
  - `assets/nk.css` — tokens (light on `:root`, dark via media query + `[data-theme]`).
- `scripts/` — `fetch_overture.py`, `fetch_terrain.py`, `build_data.py`.
- `data/research/` — hand-curated, sourced JSON (history.json, civic.json).
- `data/raw/` — gitignored raw pulls (except the ZCTA boundary).

## Commands
```bash
python -m unittest discover -s tests
python scripts/build_data.py            # after changing research JSON or the pipeline
cd site && python -m http.server 8000
```

## Conventions
- Every researched fact carries a `source` URL; never add unsourced claims.
- Keep the site dependency-free apart from three.js + Google Fonts.
- World coords: metres, x east / y south, origin in `build_data.py` (LON0/LAT0).
- Network note for cloud sessions: Overture's S3 bucket, raw.githubusercontent.com
  and the AWS terrain bucket are reachable; Overpass/Wikipedia/census.gov are not.
