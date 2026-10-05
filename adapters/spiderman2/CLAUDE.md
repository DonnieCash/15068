# Claude handoff

Follow AGENTS.md, then read README.md and docs/CLOUD_TASK.md.

Milestones 1 (parsers, fixtures, candidates CLI) and 2 (CI, research, manifest, stage/rollback tooling) are done; see docs/STATUS.md, docs/RESEARCH.md and LOCAL_HANDOFF.md. Codex runs local game tests; cloud work stays on portable code and research.

Run `python3 -m unittest discover -s tests -v` before and after changes. The repository intentionally contains no game assets, Wine prefixes, or NK datasets. Cloud work can proceed on synthetic data; an actual model import and gameplay test still require the local game installation.
