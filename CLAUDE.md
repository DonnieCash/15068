# CLAUDE.md

Guidance for working in this repo.

## What this is
`newken_twin` — a **pure standard-library** Python tool that builds a Minecraft
digital twin of New Kensington, PA, and exports a WorldEdit-compatible Sponge
`.schem` plus a top-down PNG preview. No third-party runtime dependencies.

## Common commands
```bash
# Run the test suite
python -m unittest discover -s tests

# Build the bundled twin (schematic + preview)
python -m newken_twin build --out build/new_kensington.schem \
    --preview build/new_kensington_preview.png

# Inspect a dataset
python -m newken_twin info

# Regenerate the bundled dataset
python scripts/generate_dataset.py
```

## Architecture
Pipeline: `model` (load features) → `geo` (project lat/lon to blocks) →
`raster` (2D fill) → `volume` (3D voxels) → `builder` (assemble city) →
`schematic` / `preview` (export). See README "How it works".

## Conventions
- Keep it dependency-free (stdlib only). `osm.py` uses `urllib` for live OSM.
- Material → block mappings live in `blocks.py`; tweak there to re-skin.
- Voxel/schematic index order is Sponge: `index = x + z·Width + y·Width·Length`.
- Add tests in `tests/test_twin.py` for any new behaviour.
