# Working rules

Read README.md, TASK.md, docs/RESEARCH.md and LOCAL_HANDOFF.md. NK inputs are canonical and stay unchanged; the Spider-Man adapter (other branch) is separate and must not be modified from here.

Never install a mod, edit the game, or run game files during cloud work. Do not download or run opaque packages, converters or installers. Never commit or upload proprietary game assets, extracted geometry, executables, credentials or NK datasets; use synthetic fixtures.

Unknown fields, units, axes, limits and transforms stay `unknown` until primary documentation or a local test supports them. Do not write a format whose grammar is not established, and do not write converters that merely rename files. Keep parsers and writers independently testable; record upstream commits and licences; do not copy incompatible source.

Do not conflate source triangles with GTA collision serialisation, working meshes with working traffic, or menu rendering with gameplay.

Run `python -m unittest discover -s tests -v`. No merge, deployment, spending or messaging is authorised by these instructions.
