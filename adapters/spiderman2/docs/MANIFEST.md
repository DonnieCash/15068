# Adapter manifest (`nk-sm2-manifest/1`)

One manifest describes one **section**: a set of NK components and the MSM2 assets they replace. NK stays canonical: the manifest references NK files by relative path and SHA-256 and never contains NK geometry or game data. Validate with `python -m sm2adapter manifest-check FILE [--game GAME]`. A synthetic example is in `examples/section-manifest.example.json`.

## Status blocks: no silent conventions

Each coordinate convention, transform, material mapping and collision outcome is a status block:

| `status` | Value field | Also required |
| --- | --- | --- |
| `unknown` | must be `null` | — |
| `hypothesis` | required | `note`: why, and which test will check it |
| `verified` | required | `evidence`: the test or observation that showed it |

The validator rejects a value under `unknown`, and a value without its note or evidence. The adapter applies no transforms yet: the only supported mode replaces existing assets in place, where placement is expected to stay the game's own (hypothesis H1 in RESEARCH.md).

## Fields

| Field | Meaning |
| --- | --- |
| `format` | `"nk-sm2-manifest/1"` |
| `section_id` | Name of this import section (free text, unique per experiment). |
| `nk.release` | NK release identifier, as stated by the NK source audit. |
| `nk.audit_sha256` | Optional SHA-256 of the NK source-audit JSON this manifest was written against. |
| `nk.frame.units / axes / origin` | Status blocks describing the NK release's coordinate frame, copied from the audit rather than assumed. |
| `target.game` | `"MSM2"` (others are refused). |
| `target.game_version`, `target.toc_sha1`, `target.toc_sha256` | Build the section was prepared for. `toc_sha1` uses Overstrike's hash (v1.526.0.0 = `6829BC78…0191A`); `stage` refuses a game whose `toc` differs. |
| `target.frame.units / axes / handedness` | Status blocks for the game's world frame. |
| `nk_to_game` | Status block with `matrix`: 16 numbers, row-major 4x4, NK world → game world. |
| `components[].nk` | `tile_id`, `component_id` (unique pair), `kind` (`building`, `road`, `sidewalk`, `bridge`, `lane`, `terrain`, `prop`, `other`), `source` (path relative to the NK release root), `source_sha256`. |
| `components[].target` | `mode` (`replace-model` only; `add-instance` and `replace-zone` are refused until the zone layout is known), `span` (0–255), `asset_id` (hex). Each (span, asset) may be used once per manifest. |
| `components[].geometry` | Optional. The converted model to install: `file` (relative to the staging root), `sha256`, `vertices`, `triangles`, `header_policy` (`keep-original` only). A bare DAT1 `.model` or an STG with flags 0 is accepted. |
| `components[].transform` | Status block with `matrix`: component local → game world, for future modes. |
| `components[].materials[]` | `nk_material` plus a status block whose value is `target_material` (an existing game material path or asset ID). |
| `components[].collision` | `strategy`: `keep-original` (the model's existing Havok data stays: collision follows the old shape), `none`, or `generated` (needs `file` + `sha256`; refused by `stage` until a writer exists). `status` and `note`/`evidence` as above, describing the in-game outcome. |

## Checks against a game

`manifest-check --game` and `stage` also require the game's `toc` SHA-1 (and SHA-256 if given) to match, and every (span, asset ID) to exist in that TOC. Generated outputs are read only from the staging root (no absolute paths or `..`), and their SHA-256 must match the manifest.
