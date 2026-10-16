# MSM2 static world, collision and streaming: public research

Goal: run Spider-Man 2 on the existing NK city geometry while keeping the game's traversal and gameplay. This page records what public source code and documentation say about the three things that requires (placing static geometry, giving it collision, and streaming it), and keeps verified facts apart from hypotheses.

Everything below was read in the cloud session on 2026-10-05 from public repositories, cloned read-only. No game files were available there, so **nothing on this page was checked against MSM2 data**. "Verified" means "stated by source code that implements it", not "observed in the game".

| Source | Commit | Licence |
| --- | --- | --- |
| [Tkachov/Overstrike](https://github.com/Tkachov/Overstrike) (mod manager) | `9f906ca` | GPL-3.0 |
| [Tkachov/ALERT](https://github.com/Tkachov/ALERT) (format research) | `bc90ed9` | GPL-3.0 |
| [ALERT wiki](https://github.com/Tkachov/ALERT/wiki) | `35dc8d6` | — |
| [chaoticgd/ripped_apart](https://github.com/chaoticgd/ripped_apart) (Rift Apart tools) | `64ea4d6` | MIT |
| [okangel12345/InsomniacToolbox](https://github.com/okangel12345/InsomniacToolbox) | `8f91bcc` | GPL-3.0 |

## 1. Installing changed assets: verified, with a working tool

| Fact | Reference |
| --- | --- |
| Overstrike recognises an MSM2 `.stage` mod: a zip whose `info.json` says `"game": "MSM2"`, with entries named `<span>/<16-hex asset id>`; `"format_version": 2` selects the v2 installer. | Overstrike `Detectors/StageModDetector.cs:64-79` |
| The v2 installer unwraps an STG entry (header and texture meta applied only when its flags say so) or installs other bytes as-is, leaving the TOC header alone. | `Installers/StageInstaller.cs:190-262` |
| Installed bytes go into a new archive `d/mods/modN`; the TOC entry for (span, asset ID) is repointed to it. Original archives are not written. | `StageInstaller.cs:194-200`, `Installers/InstallerBase.cs:109-127` |
| Before installing, Overstrike copies `toc` to `toc.BAK` (once) and always rebuilds from `toc.BAK`; uninstall copies `toc.BAK` back over `toc`. | `MetaInstallers/MetaInstaller_I29.cs:20-34, 131-141` |
| Overstrike has a command line: `install-mods <profile>`, `uninstall-mods <profile>`, `add-mod`, `enable-mod`. | `Overstrike/App.xaml.cs:128-137` |
| The stock v1.526.0.0 `toc` has SHA-1 `6829BC78E277997D21483975545E0A27F7C0191A` (same as v2.629.0.0). | `Games/GameMSM2.cs:52` |

Consequence: **replacing an existing asset** (same span and ID, new bytes) has a documented, reversible install path. This adapter's `stage` command writes exactly that format, outside the game directory.

## 2. Model geometry: verified tools, with limits

| Fact | Reference |
| --- | --- |
| ALERT's `gltf_to_model.py` / `ascii_to_model.py` (and ID-Daemon's closed `spiderman_pc_mi.exe`, which they imitate) **inject** vertices, faces, weights and optionally materials into an *existing* `.model`; they do not author a model from scratch. | ALERT wiki `Scripts.md:19-63`; `gltf_to_model.py:21-30` |
| The importer touches index, vertex, UV, look, mesh, skin, built and material sections only. | `gltf_to_model.py:21-30` |
| When injecting, it sets five LOD-distance floats in "Model Built" to 4096.0 ("similarly to how daemon's mi.exe does"). | `gltf_to_model.py:261-271` |
| Vertex positions are stored as int16 and decoded with a 1/4096 factor in ALERT's reader for the Rift Apart era; "Model Built" also carries a per-model position scale and offset. | `dat1lib/types/sections/model/geo.py:146-160`, `unknowns.py:89-106` |
| ALERT targets MSMR/MM/RCRA and says MSM2 "most likely would work … though some minor changes could be required". The user reports one MSM2 model exported through the Windows converter under native .NET 4.8 (60 vertices, 98 triangles); reimport is untested. | ALERT `README.md:5-14` |

## 3. Collision: the Havok blob is not regenerated (verified); how to replace it is unknown

| Fact | Reference |
| --- | --- |
| Models carry a section `0xEFD92E68` "Model Physics Data", holding a Havok tagfile-like structure (big-endian sizes, 4-byte names). ALERT parses only its container, not the shapes. | ALERT `model/havok.py:11-81`; Ripped Apart `libra/lump_types.h:11` |
| The geometry importers above do not read or write that section, so an injected model keeps its **original** collision. | `gltf_to_model.py:21-30` (section list) |
| Ripped Apart also names `0x5CBA9DE9` "Model Col Vert". Its role in MSM2 is unknown. | `lump_types.h:21` |

No public tool found here writes Havok physics data for these games. This is the main blocker for "use NK geometry with game collision": with `keep-original`, Spider-Man would collide with the *old* shape.

## 4. Static-world placement and streaming: largely unresearched in public

| Fact | Reference |
| --- | --- |
| The ALERT wiki lists `.level` ("only one level" in SO/MSMR/MM/RCRA), `.zone` ("describes hexagon (?) tiles that worlds consist of. Probably lists actors…") and `.actor` as **"Not researched enough"**. | ALERT wiki `Assets.md:33-35` |
| Section names (Ripped Apart, Rift Apart): `0x6987F172` Zone Model Insts, `0xC6A5905E` Zone Model Names, `0x06ABCAB2` Zone Scene Objects, `0x70682CB8` Zone Actors, `0xBDAB2B0D` Zone Volumes, `0x2BA33702` Level Zone Names, `0x4E023760` Level Zones Built, `0x4130D903` Level Region Names. | `lump_types.h:26-50` |
| ALERT notes ID-Daemon's code treats `0x6987F172` as a "number of instances" and `0xC6A5905E` as a "number of models"; both sections are arrays of uint32. ALERT marks `0x06ABCAB2` "matrixes?" and leaves it as raw bytes. | ALERT `zone/autogen.py:1378-1415, 1887`, `:191-199` |
| Zone and level layouts (instance transforms, bounds, streaming radii) are not decoded by any source examined. | — |

## Hypotheses (each needs a local test; none is assumed by the code)

| ID | Hypothesis | Test that would settle it |
| --- | --- | --- |
| H1 | A replaced static model renders at its original world placement, because placement lives in the zone, not the model. | Single-section workflow (LOCAL_HANDOFF.md): unchanged reimport, then a visibly modified prop, observed in game at its known spot. |
| H2 | MSM2 zone instance placement lives in `0x06ABCAB2` (Zone Scene Objects) and is indexed by `0x6987F172`/`0xC6A5905E`. | Compare `sections` output for several `.zone` assets; correlate entry counts; diff a zone whose instance count is known. |
| H3 | Static models use the per-model "Model Built" scale/offset, so building-sized meshes fit int16 positions. | Read the 60-vertex export's bounds versus its raw int16 range; repeat on a large building model. |
| H4 | The game's world axes match the converter's export axes for static props. | Export a prop with a known asymmetric shape and orientation in the world; record the matrix as `hypothesis`, then `verified` with that evidence. |
| H5 | `keep-original` collision makes the player collide with the old shape (invisible walls or falling through). | In-game test after H1, with a prop whose shape changes. |
| H6 | The "district" streaming unit is the `.zone` (the wiki's "tiles that worlds consist of"), grouped by `.level` regions. | List `.zone`/`.level` assets via `candidates --name-contains .zone`; count Level Zone Names entries. |

## What this means for NK

- **Feasible now (pending H1):** swap the geometry of existing static models for NK geometry, one model at a time, through Overstrike with `toc.BAK` rollback. Collision stays the original's.
- **Blocked:** adding or moving instances (needs the zone layout, H2), matching collision (needs a Havok writer), changing district streaming (H6). Replacing the whole city depends on all three.
- **Not an option here:** rebuilding NK or moving to another engine. The manifest keeps NK as the source and records every game-side convention with an explicit status.
