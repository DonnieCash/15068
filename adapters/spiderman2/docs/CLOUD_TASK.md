> **Status (see STATUS.md):** items 1–3 are done on synthetic data. Items 4–6 are open. The user reports the Windows exporter now works under native .NET 4.8 (one model exported and structurally validated); reimport is untested, so item 6's unchanged-round-trip gate is the next step.

# First cloud task

Goal: make the existing read-only extraction and model-container prototype reproducible, well-tested and ready for a real geometry round-trip. Do not promise or attempt whole-city replacement yet.

1. Inspect the three tools and public upstream format references. Add synthetic TOC, DSAR/LZ4 and STG fixtures. Validate length/bounds, duplicate tags, span identity, archive path containment and compression limits. Test failure behavior explicitly.
2. Add a CLI that resolves a supplied hashes dictionary against TOC entries and emits candidate JSON. Preserve every (span, asset ID) occurrence; do not silently collapse duplicate IDs into one entry. Do not fetch or bundle proprietary inputs.
3. Refactor parsing into reusable modules with streaming or bounded memory where practical. Inventory works, but the prototype is not a hardened hostile-input parser.
4. Investigate native model conversion from publicly documented formats. The known Windows exporter uses CLR v2 metadata and Windows API references, and failed on Wine Mono. ALERT did not recognize this MSM2 model. Do not pretend an older game's converter supports it without tests.
5. Design an optional converter runner with explicit runtime selection, timeout, separate work directory, retained logs and output validation. Do not install runtimes or run opaque binaries automatically.
6. Specify a reversible single-prop replacement experiment. Require verified unchanged geometry round-trip before modified geometry; keep collision and placement as separate gates.

Deliver code, synthetic tests, concise findings and remaining blockers. No cloud game execution required for this first task. User will later provide local validation results.

NK sample boundary: use a synthetic metre-scale road/intersection fixture until an authorized NK source snapshot is provided. Record source IDs, source hashes, coordinates/units, origin, target asset/span and target game version in adapter manifests. Do not guess the actual game's axis convention.
