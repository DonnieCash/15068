# NK Drive → Spider-Man 2 adapter research

Portable tools for investigating a New Kensington world adapter for Marvel's Spider-Man 2 PC. This repository contains research tooling, not a working city mod.

NK Drive remains the canonical geography and source dataset. This game adapter must own coordinate transforms, asset mapping, collision conversion, packaging, and version checks without changing canonical geography to fit the game.

This directory lives in the NK15068 repo (`adapters/spiderman2/`) but is isolated: it imports nothing from the site pipeline, reads no NK datasets, and the site build, CI and root tests do not touch it. Licensed GPL-3.0-or-later (see LICENSE); the rest of the repository is not.

## Verified checkpoint

Results below come from the local Mac sessions and the user's reports; none were reproduced in the cloud session that wrote this code.

- The game reached its rendered setup/menu on an M2 Max Mac Studio through GPTK/Wine. Sustained traversal is not verified.
- Native Python read the local game's TOC: 1,423,352 entries and 225 archive references.
- A small fire-hydrant sign model was extracted with LZ4; payload size and DAT1 bounds were checked.
- STG container packaging preserved header and payload bytes. This is not a geometry round-trip.
- ALERT's Python converter rejected this model, and the supplied Windows converter exited with Mono FailFast under Wine Mono.
- **Reported by the user after that:** native .NET 4.8 fixed the exporter. One model exported successfully and passed structural validation (60 vertices, 98 triangles, valid indices, finite coordinates) and was converted to a local OBJ. The earlier .NET 4.8 install question is therefore settled for the exporter.
- **Still untested:** reimport of that model, even unchanged. No changed geometry, world placement, collision, or mod installation has been demonstrated, and the exported geometry has not been checked against the game.

## Setup

Python 3.9+ (tested on 3.9, 3.11 and 3.13; CI runs 3.9 and 3.12). Only `lz4` is needed, and only to decode LZ4 blocks.

```sh
python3 -m venv .venv && . .venv/bin/activate
pip install -r requirements.txt
python -m unittest discover -s tests -v     # synthetic fixtures only; no game files needed
```

CI: `.github/workflows/adapter-spiderman2.yml` runs these tests on every PR touching this directory. The tests also run from elsewhere: `python -m unittest discover -s adapters/spiderman2/tests` from the repository root.

## Layout

- `sm2adapter/` — reusable parsers: `dat1.py` (section container), `toc.py`, `dsar.py` (block archives, LZ4 only; raw archives too), `stg.py` (container pack/parse), `candidates.py` (hashes dictionary → candidates), `paths.py` (containment), `limits.py` (parse bounds), `cli.py`.
- `sm2adapter/manifest.py`, `stage.py`, `gamestate.py`, `sections.py` — the NK → MSM2 manifest, Overstrike stage-v2 builder/verifier, read-only game snapshots for rollback checks, and known section names.
- `docs/RESEARCH.md` (what public sources say about placement, collision and streaming), `docs/MANIFEST.md` (manifest fields), `examples/` (synthetic manifest), `LOCAL_HANDOFF.md` (the local run sheet).
- `tools/` — thin wrappers with the original prototype names, plus `generate_candidates.py`.
- `tests/` — synthetic valid and malformed TOC / DSAR / STG fixtures (`tests/fixtures.py` builds them).

## Local-only game inputs

Supply your own game installation outside this repository. Never commit game archives, extracted models, converter executables, Wine prefixes, credentials, or proprietary assets. The game directory is only ever read; every command refuses to write its output inside it.

```sh
mkdir -p artifacts
python -m sm2adapter inventory  /path/to/game artifacts/inventory.json
python -m sm2adapter candidates /path/to/game /path/to/hashes.txt artifacts/candidates.json --name-contains hydrant
python -m sm2adapter extract    /path/to/game artifacts/candidates.json artifacts/probe --name-contains hydrant
python -m sm2adapter package    artifacts/probe artifacts/probe/probe.model
python -m sm2adapter unpack     reimported.model artifacts/probe_after   # split an STG (or bare DAT1) file
python -m sm2adapter compare    artifacts/probe artifacts/probe_after    # unchanged-reimport check, below
python -m sm2adapter sections   artifacts/probe/probe.payload.bin        # section tags, with known names
python -m sm2adapter snapshot   /path/to/game artifacts/before.json --backup-dir artifacts/backup
python -m sm2adapter manifest-check section.json --game /path/to/game
python -m sm2adapter stage      section.json artifacts/staging artifacts/nk-section.stage --game /path/to/game
python -m sm2adapter verify-stage artifacts/nk-section.stage --game /path/to/game
python -m sm2adapter check-restored /path/to/game artifacts/before.json  # after uninstalling the mod
```

The full single-section workflow, with gates and expected outputs, is in `LOCAL_HANDOFF.md`.

Failures print `error: ...` and exit 1 (`compare` and `check-restored` use 3 for "differs"); outputs are written through a temporary file (or after every check passes), so a failed run leaves no partial result. `inventory` is the exception by design: a bad archive is recorded in the JSON (`error`) and the exit status is 1 once the whole report is written. `compare` exits 0 only for a byte-identical payload and header, 3 for any difference.

### Hashes dictionary

Supplied by you (not bundled); the real file's format is unknown to this code, so adapt `load_hashes` if yours differs. Accepted: text lines `<hex id> <name>` (`#` comments); JSON `{"<id>": "<name>"}`; JSON `[{"id": ..., "name": ...}]`. IDs are 64-bit; strings are hex, JSON numbers decimal. Conflicting names for one ID (including duplicate JSON keys) are an error.

### Candidate JSON

`{"format": "sm2-candidates/1", "toc_sha256", "candidates": [...], "stats": {...}}`, one row per line. Every `(span, asset ID)` occurrence is its own row, ordered by span then entry index: the same ID in several spans, the same ID at several entries, and one entry reachable through several spans are all kept. `stats` counts what a consumer might otherwise collapse: `duplicate_id_rows` (rows beyond the first per ID), `duplicate_span_id_rows` (the same ID twice in one span, which Overstrike's binary-search lookups assume never happens), `entries_in_several_spans`, `unspanned_entries`. Entries outside every span get `span: null`. Entries whose ID is not in the dictionary are omitted unless `--include-unnamed`. Rows carry `asset_id, name, index, span, archive, archive_index, offset, bytes, header_offset`.

`extract` accepts this file or a bare list of rows, picks the smallest row (then lowest index) whose name contains `--name-contains`, and refuses a row that no longer matches the TOC (or a file whose `toc_sha256` differs). It reads LZ4 DSAR blocks and raw archives; GDeflate blocks and import assets are not supported and fail with a clear error.

### Unchanged-reimport check

The next gate is an *unchanged* export → reimport cycle. Keep the `extract` output as the "before" directory. Take the model file the converter produces from the unchanged export, `unpack` it into a second directory (nothing is installed into the game), then run `compare`. Byte-identical is the strong result. Same DAT1 sections with different bytes means the converter re-encodes the data; `compare` lists which sections differ, and that needs judgment, not a pass. Neither outcome says anything about modified geometry, collision or placement, which remain separate gates.

### Parser bounds

`sm2adapter/limits.py` caps TOC size, section/archive/block counts, summed span entries, per-block uncompressed size (16 MiB), per-asset bytes, per-block compression ratio (applied when a block is decoded), and header sizes. TOC archive names and candidate `archive` values must stay inside the game directory (no absolute paths, drive letters, `..`, NUL, or symlink escapes). Overlapping DSAR blocks, coverage gaps, short or oversized decompression, unsupported compression kinds, duplicate DAT1 tags and out-of-range spans/archive indexes/header offsets all fail with `FormatError`.

## Cloud work

Start with docs/CLOUD_TASK.md. Cloud agents can build synthetic fixtures, harden parsing, and investigate public format implementations without game files. Installation and gameplay validation require a separately configured machine with the game. Linux cloud credits alone do not imply Windows GUI or GPU access.

## License and provenance

Scripts use formats documented in Tkachov/Overstrike, GPL-3.0-or-later. See LICENSE and docs/PROVENANCE.md. This software license grants no rights to game content or external NK datasets.
