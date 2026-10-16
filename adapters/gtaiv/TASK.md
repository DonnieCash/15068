# Claude: first GTA IV milestone

Build portable tooling for converting existing NK city data into a GTA IV test map. Do not rebuild NK. Do not modify or discard the Spider-Man PR.

If working in DonnieCash/15068, inspect repository instructions and use a separate branch with adapters/gtaiv/. This starter has no executable conversion code yet.

1. Inspect primary tool source/documentation for GTA IV 1.0.7.0 map workflows: IDE object definitions, WPL/OPL placement, WDR/ODR meshes, WBN/OBN collision, textures, LOD linkage and loading registration. Confirm schemas and dependencies; flag fields that cannot be established. Distinguish GTA IV from GTA V and older GTA formats.
2. Determine the smallest usable mesh-plus-collision import pipeline. Identify whether OpenIV and 3ds Max/GIMS are mandatory, and whether a documented native Python/Blender path exists. Do not assume the Mac can run Windows tools.
3. Implement only formats justified by the evidence. Use synthetic one-road/one-building fixtures with deterministic output, bounds checks and tests. Where binary compilation needs an external tool, emit validated intermediate data plus an explicit unimplemented compilation step; never claim it is game-ready.
4. Define an NK component manifest containing source release hash, tile/component IDs, source geometry hash, source coordinate frame, separately evidenced target transform, target assets, materials, collision and LOD relationships. Use supplied source-audit.json for inventory only; it does not establish full schemas or transforms.
5. Prepare a reversible local single-section plan: baseline/backup, game version validation, outside-game generation, inspection, approved install, walking/driving collision test, rollback verification. Keep NPC traffic and full-city streaming as later explicit gates.
6. Deliver LOCAL_HANDOFF.md with code commit, tests, exact commands, required local inputs and unresolved blockers. Add narrowly scoped CI for implemented code. Do not merge or deploy. Do not run game assets in cloud or request that proprietary inputs be uploaded.

The Mac operator handles game launch and local asset validation. First objective is one existing NK section that loads and supports walking/driving, not a speculative whole-city converter.
