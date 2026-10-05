# Claude handoff

Follow AGENTS.md, then read README.md and docs/CLOUD_TASK.md.

Milestone 1 (parsers, fixtures, candidates CLI) is done; see docs/STATUS.md for results and the next gate.

Run `python3 -m unittest discover -s tests -v` before and after changes. The repository intentionally contains no game assets, Wine prefixes, or NK datasets. Cloud work can proceed on synthetic data; an actual model import and gameplay test still require the local game installation.
