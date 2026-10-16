# NK → GTA IV adapter

Goal: use the existing New Kensington (NK) city in GTA IV (PC 1.0.7.0), keeping the game's walking, driving and other gameplay. **This is not a working map mod.** It builds validated, deterministic intermediates for one NK section and stops where a Windows tool (OpenIV) has to compile them. NK stays canonical: this adapter reads exported NK components by hash and never edits NK data.

This directory sits in the NK15068 repo (`adapters/gtaiv/`) on its own branch, separate from the Spider-Man adapter. It is GPL-3.0-or-later (see LICENSE); the rest of the repository is not.

## What it does

| Command (`python -m nkgta4 …`) | Output | Status |
| --- | --- | --- |
| `obj-check`, `manifest-check` | validation reports | tested |
| `build-section MANIFEST STAGING OUT` | `<section>.ide`, binary `<section>.wpl`, local-frame OBJs, collision bound JSON, `build-report.json` (`game_ready: false`) | tested on synthetic data; formats from public readers, not yet loaded in game |
| `ofscan FILE` | structure-only summary of an OpenIV openFormats export (no numbers or names) | tested |
| `wpl-inspect FILE` | header counts and inst flag/lod/unknown value statistics of a vanilla WPL (no positions) | tested |
| `snapshot`, `check-restored` | game state with exe version, verified backups outside the game, rollback check | tested on a fake game folder |
| `oiv PLAN FILES OUT`, `verify-oiv` | OpenIV Package 2.2 (`target="IV"`, IMG3 add, text add) from compiled files you list | tested; install not tried |
| `hash NAME` | GTA IV model-name hashes | tested against standard vectors |

**Not implemented, by design:** WDR, WTD and WBN writers, and openFormats `.odr`/`.mesh`/`.obn`/`.opl` writers. Their exact formats are not publicly specified (docs/RESEARCH.md), so compilation is an explicit OpenIV step.

## Setup

Python 3.9+, standard library only.

```sh
cd adapters/gtaiv
python -m unittest discover -s tests -v
python -m nkgta4 build-section examples/synthetic/section.json examples/synthetic /tmp/nk-demo
```

CI: `.github/workflows/adapter-gtaiv.yml` runs the tests on Python 3.9 and 3.12 for changes in this directory.

## Docs

- `docs/RESEARCH.md`: sources (commit and licence), established facts, unknowns, toolchain answer.
- `docs/MANIFEST.md`: manifest fields and status rules.
- `LOCAL_HANDOFF.md`: exact local steps, inputs, gates and blockers.
- `docs/nk-source-audit.json`: the NK inventory audit (layer and metadata names only; inventory, not schemas).
- `TASK.md`: the brief.
