# Public references

- https://github.com/Tkachov/Overstrike — examined commit 9f906ca09ea5ce4b84528410171c235bc4b0bfe6; TOC_I29, DAT1 section tables, DSAR and STG wrapper formats.
- https://github.com/Tkachov/ALERT — examined commit bc90ed9b53fbcaa3b7acf94b36f00e77eab0dacb; native model converter trial failed for the local MSM2 probe.
- https://github.com/okangel12345/InsomniacToolbox — GUI delegates model export to external Windows tools.
- https://reshax.com/files/file/89-spider-man-2-model-exportimport-tools-pc/ — id-daemon converter release; separate download, not bundled.

Local inspection results are reported in README without distributing the inspected files. Tools are research prototypes based on the public format implementations above, released under GPL-3.0-or-later.

Format layouts were re-read from Tkachov/Overstrike at commit 9f906ca09ea5ce4b84528410171c235bc4b0bfe6 (DAT1/TOC.cs, DAT1/DAT1.cs, DAT1/DSAR.cs, DAT1/Sections/TOC/*, OverstrikeShared/STG/STG.cs) during the first cloud task. The Python here re-implements those layouts; no Overstrike code or binaries are bundled.
