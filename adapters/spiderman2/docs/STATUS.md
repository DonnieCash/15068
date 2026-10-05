# Status

## Milestone 2 — CI, research, manifest, single-section tooling (done, synthetic data only)

- CI: `.github/workflows/adapter-spiderman2.yml` runs the adapter tests on Python 3.9 and 3.12 for PRs touching `adapters/spiderman2/`. 70 tests; also run locally on 3.9, 3.11 and 3.13.
- Research: `docs/RESEARCH.md` covers placement, collision and streaming, with verified source references, hypotheses H1–H6, and blockers.
- Manifest: `docs/MANIFEST.md`, `sm2adapter/manifest.py`, `examples/section-manifest.example.json`. Unknown conventions must be written as `unknown`; values need a note (hypothesis) or evidence (verified).
- Workflow: `stage` builds an Overstrike stage-v2 zip outside the game, gated on the `toc` SHA-1; `verify-stage`; `snapshot` (with a verified `toc` backup outside the game) and `check-restored` confirm rollback. `sections` lists model/zone sections with known names.
- Not received: the NK source audit (`NK-CITY-SOURCE-AUDIT.json`) is on the Mac and was not attached to the cloud session, so `nk.frame` statuses in the example are placeholders.

## Milestone 1 — parsers, fixtures, candidates CLI (done, synthetic data only)

Verified by `python -m unittest discover -s tests -v` (55 tests at the time, Python 3.11, lz4 4.x):

- Reusable parsers replace the three prototypes: DAT1, TOC, DSAR (LZ4 and raw archives), STG pack/parse.
- Malformed-input tests for each format: truncation, bad magic/length fields, duplicate section tags, sections inside the DAT1 header area, out-of-bounds sections/spans/archive indexes/header offsets, ragged tables, DSAR table and block bounds, overlapping blocks, coverage gaps, unsupported compression (GDeflate named), corrupt LZ4 streams, block-size / ratio / asset-size limits, STG version/flags/padding/truncation.
- Path safety: absolute, drive-letter, `..`, NUL and symlink-escaping names rejected for TOC archive names and candidate rows; output inside the game directory refused by every command; failed runs leave no partial output.
- `candidates` CLI resolves a hashes dictionary and keeps every (span, asset ID) occurrence, with stats that expose duplicate IDs, repeats inside one span, and multi-span entries.
- Added for the next gate: `unpack` (STG or bare DAT1 → probe files) and `compare` (byte-for-byte plus per-section report).

## Checked against upstream (Tkachov/Overstrike @ 9f906ca, read in the cloud session)

Matches what the prototypes assumed: TOC asset metadata `(size, archive index, offset, header offset)`; 66-byte archive records with a 40-byte name; spans `(first asset index, count)`; the MSM2 ("I30") asset-header layout; DSAR 32-byte block entries `(raw offset, compressed offset, raw size, compressed size, kind)`; compression kind 3 = LZ4.

Differences from the prototypes, all deliberate:

- DSAR kind 2 is GDeflate (reported as unsupported); archives without the DSAR magic are raw files and are now readable.
- DAT1 has an "unknowns" area and strings block before the first section; section offsets are checked against it.
- STG: the first word is `'STG' | version << 24`, the second is a flags word. Overstrike's installers apply a header only with `INSTALL_HEADER` and texture meta only with `INSTALL_TEXTURE_META`. The prototype hard-coded `flags=1`, which for an asset with no header (`header_offset` = -1) would have produced a file asking for an empty header to be installed. Flags are now derived from what is present, and such a combination is rejected on parse.
- A TOC whose archive names contain `sargasso` (Rift Apart's 36-byte asset headers) is refused rather than mis-parsed.
- Upstream finds assets by binary search inside a span, so a real span has sorted IDs and each ID once. `inventory` reports departures (`span_report`) without rejecting them.

## Not verified / limits

- All tests use synthetic bytes built by `tests/fixtures.py`. This code has **not** been run against the real `toc` or archives. Stricter validation than the prototypes (overlapping DSAR blocks, every header offset checked, ratio limit 1024, 16 MiB blocks, DAT1 section bounds, STG padding) could reject real data. If so, that is a finding to report, not a parser bug to silence; limits are in `sm2adapter/limits.py`.
- The hashes dictionary format is a guess (see README).
- `python-lz4` accepts an LZ4 match with offset 0 without error, so decompression-size checks, not the library, catch truncation. Extracted payloads are unvalidated until DAT1 bounds are checked (`extraction.json` records `payload_is_dat1`; STG packing enforces it).
- Reported by the user, not reproduced here: native .NET 4.8 fixed the Windows exporter; one model exported with 60 vertices and 98 triangles (valid indices, finite coordinates) and was converted to a local OBJ. This code has not seen that file.
- Untested: reimport of that model (even unchanged), modified geometry, collision, placement, mod installation, whole-city replacement. Item 5 of docs/CLOUD_TASK.md (converter runner) is not started; item 6 (reversible single-prop experiment) is specified in LOCAL_HANDOFF.md but not run; native conversion (item 4) is researched only. No runtime was installed or run in the cloud.
- No NK dataset, coordinate transform or axis convention is included; the synthetic-fixture boundary in CLOUD_TASK.md still applies.

## Next local validation step

See `LOCAL_HANDOFF.md`: the exact commands, inputs, gates and expected outputs for the unchanged-reimport check and the first reversible single-section import.
