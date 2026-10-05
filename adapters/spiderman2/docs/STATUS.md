# Status

## Milestone 1 — parsers, fixtures, candidates CLI (done, synthetic data only)

Verified by `python -m unittest discover -s tests -v` (55 tests, Python 3.11, lz4 4.x):

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
- Untested: reimport of that model (even unchanged), modified geometry, collision, placement, mod installation, whole-city replacement. Items 4–6 of docs/CLOUD_TASK.md (native conversion, converter runner, reversible single-prop experiment) are not started. No runtime was installed or run in the cloud.
- No NK dataset, coordinate transform or axis convention is included; the synthetic-fixture boundary in CLOUD_TASK.md still applies.
- The adapter tests are not wired into the repository's CI (the root workflows run only `tests/`); doing so needs `pip install -r adapters/spiderman2/requirements.txt`.

## Next local validation step

Unchanged-reimport check, using the real game and the model you already exported (nothing is installed into the game):

```sh
python -m sm2adapter inventory  /path/to/game artifacts/inventory.json      # expect Assets: 1423352 Archives: 225, Errors: 0
python -m sm2adapter candidates /path/to/game /path/to/hashes.txt artifacts/candidates.json --name-contains hydrant
python -m sm2adapter extract    /path/to/game artifacts/candidates.json artifacts/probe --name-contains hydrant
# reimport the UNCHANGED export with the converter to a new model file outside the game directory, then:
python -m sm2adapter unpack     /path/to/reimported.model artifacts/probe_after
python -m sm2adapter compare    artifacts/probe artifacts/probe_after
```

First confirm `extraction.json` `payload_sha256` equals the earlier probe's. Report any `error:` line verbatim; it names the failed check. Then report the `compare` verdict and, if different, which sections differ. Only an identical or fully explained result opens the modified-geometry gate.
