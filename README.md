# New Kensington Digital Twin (Minecraft)

A full pipeline that turns the real-world geography of **New Kensington,
Pennsylvania (ZIP 15068)** into a Minecraft **digital twin** — a block-for-block
voxel model of the downtown core that you can paste into any world with
WorldEdit / FAWE.

It is written in **pure Python (standard library only)** — no `pip install`
needed to build the twin — and ships with:

- a representative dataset of New Kensington's avenue/street grid, the Allegheny
  River, the Tarentum Bridge, Memorial Park and named landmarks, anchored to
  real latitude/longitude;
- a **live OpenStreetMap importer** for an exact-footprint twin when you have
  network access;
- a **WorldEdit-compatible Sponge `.schem`** exporter;
- a **top-down PNG map** renderer so you can preview the twin without launching
  the game.

![Top-down preview of the New Kensington twin](build/new_kensington_preview.png)

*Top-down preview: the Allegheny River (blue), the rotated avenue/street grid,
Fifth Avenue (the dark spine), the Tarentum Bridge (grey), and varied
rooftops across downtown.*

---

## Quick start

No dependencies required (Python 3.9+):

```bash
# Build the bundled twin -> schematic + preview image
python -m newken_twin build \
    --out build/new_kensington.schem \
    --preview build/new_kensington_preview.png

# Inspect a dataset without building
python -m newken_twin info
```

Then in Minecraft (Java Edition, with WorldEdit or FastAsyncWorldEdit):

```
//schem load new_kensington
//paste
```

### Build an *exact* twin from live OpenStreetMap

When you have internet access, pull real building footprints and the real
street network straight from OpenStreetMap's Overpass API:

```bash
python -m newken_twin build --osm --lat 40.5695 --lon -79.7647 --radius 700
```

If Overpass is unreachable, the tool prints a warning and falls back to the
bundled dataset, so a build always succeeds.

---

## How it works

```
features (bundled JSON or live OSM)
        │   model.py        load + typed feature model
        ▼
   projection             geo.py     lat/lon → local metres → block grid
        ▼
   rasterisation          raster.py  scanline polygon fill, thick polylines, disks
        ▼
   voxel volume           volume.py  dense 3D array of palette indices
        │   builder.py     terrain → water/parks → roads → bridges → buildings → trees → landmarks
        ▼
   export                 schematic.py  Sponge Schematic v2 (.schem)  +  preview.py  top-down PNG
```

| Module | Responsibility |
| --- | --- |
| `geo.py` | Local equirectangular projection; lat/lon ↔ block coordinates. |
| `model.py` | Feature model (`Building`, `Road`, `Area`, `Point`, `City`) and JSON loader. |
| `raster.py` | 2D rasterisation: polygon fill, thick polylines, disks. |
| `volume.py` | Dense voxel grid in Sponge index order. |
| `blocks.py` | Material → block-id palette. |
| `builder.py` | Assembles the layered voxel city. |
| `schematic.py` | Writes Sponge Schematic v2; varint block data. |
| `nbt.py` | Minimal dependency-free NBT reader/writer. |
| `preview.py` | Hand-rolled PNG encoder for top-down maps. |
| `osm.py` | Live OpenStreetMap (Overpass) importer. |
| `data/` | Bundled `new_kensington.json` dataset + loader. |

### Coordinate convention

One block = one metre by default (`--scale` changes this). `+X` is east, `+Z`
is south, and the north-west corner of the area maps to `(0, 0)` — matching the
Sponge schematic layout `index = x + z·Width + y·Width·Length`.

---

## The dataset

`newken_twin/data/new_kensington.json` is a GeoJSON-style document
(`[lon, lat]` coordinate order) using the same schema the OSM importer emits, so
the two are interchangeable. Regenerate it with:

```bash
python scripts/generate_dataset.py
```

> **Note on fidelity.** This sandbox has no access to OpenStreetMap, so the
> bundled dataset is a *representative* parametric model of New Kensington's
> downtown — its real numbered-avenue/street grid, the Allegheny River, the
> Tarentum Bridge, Memorial Park and several real landmarks, all anchored to the
> city's true coordinates. For a block-exact reproduction of every footprint,
> run with `--osm` (or drop a real OSM export in via `--dataset`).

---

## Customising the look

`newken_twin/blocks.py` maps **material groups** (e.g. `road`, `wall_brick`,
`roof_civic`, `water`) to concrete Minecraft block IDs. Edit one table to
re-skin the whole city. `builder.py` controls heights, setbacks, window
banding, bridge piers and landmark beacons.

---

## Tests

```bash
python -m unittest discover -s tests -v
```

The suite covers the projection maths, rasterisation, the NBT round-trip, the
varint encoder, schematic structure, the bundled dataset, a full end-to-end
build and the PNG encoder.

---

## CLI reference

```
python -m newken_twin build [options]
  --dataset PATH        use a custom GeoJSON-style dataset
  --osm                 fetch live OpenStreetMap data (needs network)
  --lat / --lon         centre for --osm (default: downtown New Kensington)
  --radius M            half-extent in metres for --osm (default 650)
  --out PATH            output .schem (default build/new_kensington.schem)
  --preview PATH        output PNG ('' to skip)
  --preview-scale N     integer upscaling for the preview
  --scale M             metres per block (>1 shrinks the model)
  --data-version N      Minecraft DataVersion to embed (default 3465 = 1.20.1)

python -m newken_twin info [--dataset PATH | --osm ...]
```

## License

MIT — see [LICENSE](LICENSE).
