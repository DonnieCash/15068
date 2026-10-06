# Section manifest (`nk-gta4-manifest/1`)

One manifest describes one NK section: the NK components it uses, their target GTA IV model names, and every game-side value needed to write the IDE and WPL. Validate with `python -m nkgta4 manifest-check FILE`; `examples/synthetic/section.json` is a buildable synthetic example.

## Status blocks

| `status` | `value` | Also required | Build behaviour |
| --- | --- | --- | --- |
| `unknown` | absent | — | validation passes; **build refuses** any value it must write |
| `hypothesis` | required | `note` (source, and which gate will test it) | used; the build report records the status |
| `verified` | required | `evidence` (the test that showed it) | used |

## Fields

| Field | Meaning |
| --- | --- |
| `section_id` | Identifier (letters, digits, `_`); names `<section>.ide` and `<section>.wpl`. |
| `nk.release`, `nk.release_sha256` | The sealed NK release this section comes from. `audit_sha256` optional. |
| `nk.frame.units/axes/origin` | NK source frame, from the NK audit, as status blocks. |
| `target.game` | `"GTAIV"` only. `exe_version` (e.g. `1.0.7.0`) and optional `exe_sha256` from `snapshot`. |
| `target.frame.units/axes/handedness` | Game frame as status blocks (research: Z up, right-handed; metres assumed). |
| `nk_to_game` | Status block, `value` = 16 numbers, row-major affine 4x4, NK world → game world. Required (not `unknown`) to build. |
| `components[].nk` | `tile_id`, `component_id` (unique pair), `layer` (NK layer name, e.g. `road`, `bldg_res_cream`), `source` (path in the NK release), `source_sha256`. |
| `components[].render` | `obj` (path relative to the staging folder) and `sha256` of the OBJ exported from the NK component. |
| `components[].model` | `name` (unique model name; hashed into the WPL), `txd`, `draw_distance`. |
| `components[].wdd` | Status block: IDE WDD field. |
| `components[].ide_flags` | Status block: `[flag1, flag2]` for the IDE `objs` line. |
| `components[].placement` | Status block: `{"flags", "lod", "unknown_int", "unknown_float"}` for the WPL `inst` record. |
| `components[].lod_parent` | Status block: LOD parent model (no LOD for the first section). |
| `components[].materials[]` | `nk_material` plus a status block naming the target texture or shader. |
| `components[].collision` | `source`: `render` (collide with the render triangles) or `separate` (+ `obj`, `sha256`); `surface`: status block for the collision material index; `outcome`: status block for the in-game result. |

Positions come from the transform: each component's world bbox gives its instance origin (centre x, centre y, min z), and its geometry is written relative to that point. Rotation is identity. Collision and render share the same origin.
