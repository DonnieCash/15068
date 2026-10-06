# GTA IV map pipeline: what public sources establish

Target: GTA IV PC 1.0.7.0 (x86). The goal is one existing NK section that loads with working collision, so the player can walk and drive on it with normal gameplay. Everything below was read in a cloud session on 2026-10-06 from public repositories cloned read-only. The GTAMods wiki, GTAForums, gtagarage and dev-c.com were **blocked by the session's network policy**, so their content appears only as search-result summaries and is marked as such. No game files or tools were run.

"Established" means a public source implements or specifies it. It does not mean a test in the game confirmed it.

| Source | Commit | Licence | Used for |
| --- | --- | --- | --- |
| [OpenIV-Team/OpenIV-PackageFormat](https://github.com/OpenIV-Team/OpenIV-PackageFormat) | `6f9d25a` | — (spec) | `.oiv` package format 2.2 (official) |
| [OpenIV-Team/OpenIV-openFormats](https://github.com/OpenIV-Team/OpenIV-openFormats) | `9295837` | — | **empty** (title only): no official openFormats grammar is published |
| [Infinity-Loops/GTA4Unity](https://github.com/Infinity-Loops/GTA4Unity) | `c107e46` | GPL-3.0 | IDE, binary WPL, collision bounds, hash, axes, images.txt (readers; its comments say layouts were derived from the game executable) |
| [renan-hath/GTAIV-MapMover](https://github.com/renan-hath/GTAIV-MapMover) | `7890880` | none stated (read, not copied) | OpenIV round trip WPL↔OPL, WBN↔OBN; OPL/OBN coordinate tokens |
| [spicybung/BlenDR](https://github.com/spicybung/BlenDR) | `9bc686d` | GPL-3.0 | Blender add-on: IV `.odr`/`.mesh` import/export (WIP); WIP WDR/WDD readers; no bounds or placement |
| [svenar-nl/OpenFormatObjConverter](https://github.com/svenar-nl/OpenFormatObjConverter) | `61bf8e8` | MIT | ODR/mesh structure as exported by OpenIV ("ODR version 110 12 (GTA 4)") |
| [z87/rpf-archive-rs](https://github.com/z87/rpf-archive-rs) | `b79ac7f` | public domain | claims IMG3 read/write (magic `0xA94E2A52`) |

All code in `nkgta4/` is an independent re-implementation of documented facts; nothing was copied.

## Established

| Topic | Fact | Reference |
| --- | --- | --- |
| Install packaging | OIV 2.2 is a zip with `assembly.xml` (`<package version="2.2" target="IV">`, required `metadata`, `colors`, `content`) and `content/`. Commands: `add`/`delete` files, `<archive type="IMG3">` (also RPF2/RPF3 for IV) with `createIfNotExist`, and `<text>` line edits (`add`, `insert`, `replace`, `delete`). | PackageFormat `specification/versions/2.2.md` |
| Item definitions | IDE `objs` lines hold: model, txd, draw distance, flag1, flag2, bbox min (3), bbox max (3), bounding sphere (4), WDD name. | GTA4Unity `IVUnity/IDE/Items/Item_OBJS.cs` |
| Placement | Binary WPL: 17 int32 header (version 3, inst, grge, cars, cull, strbig, lcul, zone, blok counts and unused fields), then 48-byte `inst` records: position (3 f), rotation quaternion (4 f), model hash (u32), flags, lod, unknown int, unknown float. | GTA4Unity `IVUnity/IPL/IPL.cs`, `IPL/Items/Ipl_INST.cs` |
| Model hash | Jenkins one-at-a-time over the lowercased name, `\` → `/`, results < 2 bumped by 2. | GTA4Unity `RageLib/Common/Hasher.cs` |
| Axes | RAGE world is right-handed, Z up; stored quaternions have x, y, z negated relative to the mathematical rotation. | GTA4Unity `IVUnity/RageCoordinates.cs` (cites OpenRage `entity.cpp:200`) |
| Collision | Bound types: Sphere 0, Capsule 1, Box 3, Geometry 4, CurvedGeometry 5, Grid 6, Ribbon 7, BVH 10, Surface 11, Composite 12. Geometry bounds store int16 vertices decoded as `q * unquantize + center`, and 32-byte polygons (normal, area, 4 × u16 vertex, 4 × u16 neighbour). Composite bounds hold child bounds plus matrices. | GTA4Unity `RageLib/Collision/*.cs` |
| Loading | The game reads `common/data/gta.dat` and `common/data/images.txt`; map WPLs are found in IMGs, and `inst.lod` links instances inside one WPL. | GTA4Unity `IVUnity/GTADatLoader.cs`, `ImagesListReader.cs` |
| Round trip | OpenIV exports WPL → OPL and WBN → OBN (text) and imports them back; OPL instance lines begin with `x,y,z`; OBN carries `Centroid x y z` and `VertexOffset x y z` lines. | MapMover `README.md`, `GTAIV_Map_Mover.py` |
| Meshes | OpenIV `.odr` text for GTA IV is "Version 110 12" with a `shadinggroup`/`Shaders` block and a `lodgroup` naming `.mesh` files per LOD; `.mesh` files hold `Idx` and `Verts` blocks with `x y z / nx ny nz / … / u v` lines. | OpenFormatObjConverter; BlenDR `import_iv_mesh_odr.py` |

## Not established (kept as explicit unknowns)

- **openFormats grammar.** The official repository is empty. The exact `.odr`/`.mesh`/`.obn`/`.opl` syntax OpenIV accepts on import is known only from partial readers, so this adapter writes **no** openFormats files. `ofscan` lets the operator export a real file and report only its structure (gate G1).
- **Binary resources.** WDR (drawable), WTD (textures) and WBN (bounds) are relocated RAGE resources, and no public writer was found. Producing them needs OpenIV import, or 3ds Max with GIMS IV/OFIO.
- **IDE semantics.** The meaning of `flag1`/`flag2` and the WDD value for static map objects.
- **WPL semantics.** `flags`, `lod` sentinel, and the two unknown fields of `inst`.
- **Collision details.** The per-polygon surface (material) index, the neighbour sentinel, how a triangle fills the 4-index polygon slot, and phBound margin, CG and volume fields.
- **`images.txt` second column.** Sources disagree: the GTAMods search summary says a 0/1 flag for whether WPL/XPL are expected; GTA4Unity reads a load priority. The registration line must be copied from the local file's existing pattern and tested.
- **`gta.dat` lines** needed for a new IDE (search summary only).
- **Units.** Metres are assumed by GTA4Unity (1 game unit = 1 Unity metre), which is plausible but untested here.

## Toolchain answer

- **OpenIV is mandatory** for this milestone. It is the only documented path from openFormats text to WDR/WBN/WPL and into IMG archives (`.oiv` install). It is a Windows application, and running it on the Mac (Wine/CrossOver/VM) is unverified.
- **3ds Max + GIMS IV or OFIO** is an alternative authoring path, not required. It is also Windows-only, and its documentation pages were blocked here.
- **No native Python/Blender path** produces game-ready GTA IV map files. BlenDR exports ODR/mesh only (WIP) and has no bounds or placement. This adapter therefore emits validated intermediates (local-frame OBJ, collision bound JSON, IDE text, binary WPL) and leaves compilation as an explicit external step.

## GTA IV is not GTA V or the 3D-era games

IV uses IDE + **binary WPL** (V uses YTYP/YMAP; III/VC/SA use text or binary IPL with COL collision). IV models are WDR/WDD/WFT and textures WTD (V uses YDR/YDD/YFT/YTD). IV bounds are WBN/WBD with **bound-type numbers that differ from V** for values ≥ 8 (GTA4Unity `BoundType.cs`). IV archives are IMG3 and RPF2/RPF3 (V uses RPF7). Tools for GTA V (CodeWalker, Sollumz) and for the RenderWare-era games (DragonFF, COL editors) do not apply.

## Gameplay beyond collision

Walking and driving need collision and placement only. **NPC traffic** needs path nodes (not researched). **Streaming and LOD** at city scale need `lod` linkage and multiple IMGs. Both stay later gates; see LOCAL_HANDOFF.md.
