# Agent instructions

Read README.md, docs/STATUS.md and docs/CLOUD_TASK.md first. Work only in adapters/spiderman2/ (the parent repo has its own CLAUDE.md for the site); NK source datasets are authoritative and remain independent.

Never claim menu rendering proves gameplay, raw extraction proves conversion, or container packing proves a model round-trip. Record actual commands, outputs, and limits.

Do not commit or upload proprietary game files, extracted assets, executable converters, Wine prefixes, local user paths, secrets, or NK source datasets. Use synthetic fixtures in tests. Do not obtain leaked engine source.

Default all game access to read-only. Do not implement or run in-place archive edits without version/hash preconditions, verified backups, and tested rollback. No changes to a running game.

Do not assume Win32 APIs or Windows .NET work on Linux/macOS. Keep native parsing independent from optional external converter execution. Fail on unsupported formats or incomplete outputs; zero exit status alone is insufficient.

Run python -m unittest discover -s tests -v. Update the status documentation after material findings. No autonomous deployment, cloud compute purchase, or remote publication is authorized by this file.
