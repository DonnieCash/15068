# Local handoff: first reversible NK section in Spider-Man 2

**Code:** commit `b8845642f32b25499ad3851a00b5836cd3882fbd` on branch `claude/compassionate-newton-dg8yd3` ([PR #2](https://github.com/DonnieCash/15068/pull/2)), directory `adapters/spiderman2/`. This file was added in the commit after it.

**Rules:** the game must not be running. Every command below only reads the game directory and writes under `$ART`; the commands refuse output paths inside the game. The single step that changes the game is the Overstrike install in step 7, and it should run only after gates G1–G3 pass and you approve it.

## Inputs (local only, never committed)

| Name | What | Check |
| --- | --- | --- |
| `GAME` | Spider-Man 2 install folder (has `toc`, `Spider-Man2.exe`) | v1.526.0.0: `toc` SHA-1 `6829bc78e277997d21483975545e0a27f7c0191a` |
| `HASHES` | asset-name dictionary used for the earlier probe | text `<hex id> <name>` or JSON (README) |
| Converter | the Windows model exporter/importer that works under native .NET 4.8 | exported the 60-vertex / 98-triangle model |
| Overstrike | mod manager (`net7.0-windows`, WPF), for step 7 only | runs on the Mac: **unverified** |
| `NK` | NK release (390 tiles, building/road/sidewalk/bridge geometry, placement, lanes) and `NK-CITY-SOURCE-AUDIT.json` | step 5 only |
| `ART` | an empty work folder outside `GAME`, e.g. `~/nk-sm2-artifacts` | — |

## Setup

```sh
git fetch origin claude/compassionate-newton-dg8yd3 && git checkout b8845642f32b25499ad3851a00b5836cd3882fbd
cd adapters/spiderman2
python3 -m venv .venv && . .venv/bin/activate && pip install -r requirements.txt
python -m unittest discover -s tests          # expect: Ran 70 tests ... OK
```

## Steps, gates and expected output

| # | Command | Expect |
| --- | --- | --- |
| 1 | `python -m sm2adapter snapshot "$GAME" $ART/before.json --backup-dir $ART/backup` | prints `toc_sha1` = the v1.526 hash above, `toc_bak: false` (true if Overstrike was used before), and a `toc_backup` path. Keep `before.json` and the backup. |
| 2 | `python -m sm2adapter inventory "$GAME" $ART/inventory.json` | `Assets: 1423352 Archives: 225 Missing: 0 Errors: 0`. Any `error:` line is the first thing to report. |
| 3 | `python -m sm2adapter candidates "$GAME" "$HASHES" $ART/candidates.json --name-contains hydrant` then `python -m sm2adapter extract "$GAME" $ART/candidates.json $ART/probe --name-contains hydrant` and `python -m sm2adapter package $ART/probe $ART/probe/probe.model` | `extraction.json` with `payload_is_dat1: true` and the same `payload_sha256` as the earlier probe. |
| 3b | `python -m sm2adapter sections $ART/probe/probe.payload.bin` | section list; record whether `0xEFD92E68` (Model Physics Data) and `0x5CBA9DE9` (Model Col Vert) are present (RESEARCH.md §3). |
| 4 | Converter: export `$ART/probe/probe.model`, re-import it **unchanged** to `$ART/reimport/unchanged.model`. Then `python -m sm2adapter unpack $ART/reimport/unchanged.model $ART/probe_after` and `python -m sm2adapter compare $ART/probe $ART/probe_after` | **G1:** `verdict: identical` (exit 0). If `different`, report which sections differ. Do not continue until each difference is explained. |
| 5 | Copy `examples/section-manifest.example.json` to `$ART/section.json`. Fill `target.toc_sha1` (step 1), the component's `target.span`/`asset_id` (from `extraction.json`), `geometry.file` = `models/unchanged.model` and its `sha256` (`shasum -a 256`), the NK fields from the audit, and leave every unproven convention as `"status": "unknown"`. Put the model at `$ART/staging/models/unchanged.model`. Run `python -m sm2adapter manifest-check $ART/section.json --game "$GAME"` | **G2:** exit 0, `in_toc` lists the target entry. |
| 6 | `python -m sm2adapter stage $ART/section.json $ART/staging $ART/nk-section.stage --game "$GAME"` then `python -m sm2adapter verify-stage $ART/nk-section.stage --game "$GAME"` | **G3:** `nk-section.stage` and `nk-section.stage.plan.json`; verify exits 0. Building the stage twice gives the same `stage_sha256`. |
| 7 | **Install (changes the game; needs approval).** In Overstrike's folder: `Overstrike.exe create-profile NK "<GAME>"`, copy the `.stage` into `Mods Library`, `Overstrike.exe add-mod nk-section.stage`, `Overstrike.exe enable-mod NK "Mods Library\nk-section.stage"`, `Overstrike.exe install-mods NK`. These argument forms are read from Overstrike's `App.xaml.cs` and untested; the GUI does the same. | exit 0; `GAME/toc.BAK` now exists and `GAME/d/mods/mod0` was added. Launch, go to the prop's known location: it should look unchanged (unchanged reimport) and the game must load. |
| 8 | **Rollback.** `Overstrike.exe uninstall-mods NK`, then `python -m sm2adapter check-restored "$GAME" $ART/before.json` | **G4:** `restored: true` (exit 0); notes about `toc.BAK` and `d/mods` are expected. If not restored: copy `$ART/backup/toc.<sha1>` over `GAME/toc` and run `check-restored` again. |
| 9 | Repeat 4–8 with a **visibly modified** prop (same asset) | Tests H1 (placement kept) and H5 (collision follows the old shape). Record results as `evidence` in the manifest. |

## Report back

Report the step 2 output line, `extraction.json`, the step 3b section list, the `compare` report, both plan/verify outputs, the `check-restored` report, and what the game showed in steps 7 and 9.

## Unresolved blockers

1. **Collision:** no public tool writes MSM2 Havok physics (`0xEFD92E68`). Replaced models keep their old collision (RESEARCH.md §3).
2. **Placement and streaming:** the `.zone`/`.level` layouts (instances, transforms, district streaming) are not publicly decoded, so adding or moving NK geometry is not possible yet. Only in-place replacement is (H1, H2, H6).
3. **Coordinate conventions:** NK→game axes, units, handedness and model scale are `unknown` (H3, H4). Nothing in the code assumes them.
4. **Unchanged reimport (G1)** has not been run.
5. **Overstrike on the Mac:** it needs the .NET 7 Windows desktop runtime under Wine/GPTK, which is unverified. Without it there is no tested install path, and this adapter deliberately never writes into the game itself.
6. **NK source audit** was not attached to the cloud session; the manifest's NK frame fields must be filled from it locally.
7. **Hashes file format** is assumed (README); adapt `load_hashes` if step 3 fails to parse it.
