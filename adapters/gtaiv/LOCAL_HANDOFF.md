# Local handoff: one NK section in GTA IV (walk and drive)

**Code:** commit `2db348eb52c79d1d2c50f9ab96a418704f0086a0` on branch `claude/nk-gtaiv-adapter`, directory `adapters/gtaiv/`. This file was added in the commit after it. The tests (28, standard library only, Python 3.9+) run in CI for this directory.

**Rules:** no `nkgta4` command writes inside the game folder; each refuses an output path there. The game changes only in step G5, through OpenIV, after G0–G4 pass and you approve. Report structure and statistics back, never game assets or NK geometry.

## Required local inputs

| Name | What | Check |
| --- | --- | --- |
| `GAME` | GTA IV install (contains `GTAIV.exe`, `common/`, `pc/`) | `snapshot` reports file version `1.0.7.0`; the package is third-party-modified, so record its sha256 |
| OpenIV | Windows tool; mandatory for compiling WDR/WTD/WBN and installing `.oiv` | must run on the Mac (Wine/CrossOver) or a Windows VM: **unverified** |
| NK release | sealed NKDrive release (390 tiles) and its audit | release sha256 |
| Blender (or similar) | to export one NK section's components as OBJ, unchanged (no remodelling) | — |
| `ART` | work folder outside `GAME` | — |

## Setup

```sh
git fetch origin claude/nk-gtaiv-adapter && git checkout 2db348eb52c79d1d2c50f9ab96a418704f0086a0
cd adapters/gtaiv
python3 -m unittest discover -s tests          # expect: Ran 28 tests ... OK
python3 -m nkgta4 build-section examples/synthetic/section.json examples/synthetic $ART/demo   # dry run, game_ready false
```

## Gates

| Gate | Do | Expect / report |
| --- | --- | --- |
| **G0** baseline | `python3 -m nkgta4 snapshot "$GAME" $ART/before.json --backup-dir $ART/backup` | `exe_file_version: 1.0.7.0`, sha256s of `gta.dat` and `images.txt`, backup paths. Keep `before.json` and `backup/`. |
| **G1** grammar samples | In OpenIV, export one small vanilla static object's WDR → openFormats (`.odr` + `.mesh`), its WBN → `.obn`, and one WPL → `.opl`, all into `$ART/samples`. Run `python3 -m nkgta4 ofscan <file>` on each. | Paste the `ofscan` outputs (structure only). They give the exact grammar for a future `.mesh`/`.obn` writer. If OpenIV does not run, stop here: this is blocker 1. |
| **G2** vanilla values | From the same object: copy its IDE `objs` line (flags and WDD only), and run `python3 -m nkgta4 wpl-inspect <exported .wpl>`. Note how `common/data/images.txt` and `common/data/gta.dat` list existing map IMGs and IDEs (the form of one line, not the contents). | Fill the manifest's `ide_flags`, `wdd` and `placement` as `hypothesis` with a note naming the source object. Record the registration line form for G4. |
| **G3** build | Pick one NK section (a few road and building components). Export each component to OBJ unchanged, in `$ART/staging`. Choose an empty test area in Liberty City, write `nk_to_game` as a translation to it (`hypothesis`). Write `$ART/section.json` (copy `examples/synthetic/section.json`; `python3 -m nkgta4 hash NAME` gives model hashes). Run `python3 -m nkgta4 manifest-check $ART/section.json`, then `python3 -m nkgta4 build-section $ART/section.json $ART/staging $ART/out --game "$GAME"`. | `build-report.json` with `game_ready: false`; per component, collision `open_edges` and `max_quantization_error` (under 0.01). Building the same inputs twice gives identical hashes. |
| **G4** compile and package | In OpenIV: import `out/models/<name>.obj` → `<name>.wdr` (openFormats or 3ds Max/GIMS IV), create `<txd>.wtd`, and build each `<name>.wbn` matching `out/collision/<name>.bound.json` (same vertices and triangles). Copy `examples/synthetic/install-plan.example.json` to `$ART/plan.json`; list every compiled file with its sha256, `out/<section>.wpl`, `out/<section>.ide`, and registration lines in the **exact form** seen in G2, each with a `note`. Then `python3 -m nkgta4 oiv $ART/plan.json $ART $ART/nk-section.oiv --game "$GAME"` and `python3 -m nkgta4 verify-oiv $ART/nk-section.oiv`. | `verify-oiv` exits 0 with `unreferenced: []`. Then `python3 -m nkgta4 snapshot "$GAME" $ART/before-install.json --plan $ART/plan.json --backup-dir $ART/backup-plan`: it backs up the exact files the package edits and records that the files it adds are absent. |
| **G5** install (approval) | Game closed. Install `nk-section.oiv` with the OpenIV Package Installer. Launch the game. | The game reaches gameplay without a crash; the section is visible at the test area. |
| **G6** collision | Walk onto the road and building, drive a car across the road, collide with the building walls. | Player and car do not fall through; walls block. Record the result as `collision.outcome` evidence. |
| **G7** rollback | Restore every file from `$ART/backup-plan` to the same path under `GAME`, and delete the files the package added (the new `.img` and `.ide`). Then `python3 -m nkgta4 check-restored "$GAME" $ART/before-install.json`. | `restored: true` (exit 0), including the added files being gone. Exit 3 lists what still differs. |

## Report back

Report the G0 output, the G1 `ofscan` outputs, the G2 `wpl-inspect` output and the registration line forms, the G3 build report, `verify-oiv`, what happened in G5–G6, and the G7 `check-restored` result.

## Later gates (not part of this milestone)

- **NPC traffic:** path nodes for the NK roads (unresearched).
- **LOD and streaming:** `lod` links, LOD models, multiple IMGs, city-scale streaming.
- **Textures and materials:** mapping NK materials to WTD textures and shaders.
- **More of NK:** more sections, then whole tiles.

## Unresolved blockers

1. **OpenIV on the Mac** is unverified, and no public tool writes WDR/WTD/WBN, so without OpenIV (or 3ds Max + GIMS IV on Windows) nothing becomes game-ready.
2. **The collision compile step:** the bound JSON holds what the game stores, but turning it into a WBN depends on the `.obn` grammar (G1) or manual work in OpenIV/3ds Max. The per-polygon surface type is unknown.
3. **Unknown field semantics:** IDE flags, WDD, WPL `flags`/`lod`/unknowns. They are copied from vanilla (G2), not understood.
4. **Registration:** sources disagree on the `images.txt` second column; the `gta.dat` lines needed for a new IDE are unconfirmed. Copy the local pattern and test (G4–G5).
5. **Units and axes:** Z-up, right-handed and metres come from one reimplementation (GTA4Unity) and are untested in game.
6. **Third-party game package:** the local GTA IV build is modified; static inspection does not establish what it changes.
7. **NK export:** this adapter consumes OBJ; the NK release's own geometry format and frame come from the NK audit and must be exported unchanged.
