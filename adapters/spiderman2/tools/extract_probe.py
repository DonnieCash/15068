#!/usr/bin/env python3
"""Compatibility wrapper: python tools/extract_probe.py GAME CANDIDATES.json OUTDIR [NAME_FRAGMENT]
NAME_FRAGMENT defaults to 'hydrant' (the original probe's choice)."""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from sm2adapter.cli import main
args = sys.argv[1:]
name = args[3] if len(args) > 3 else 'hydrant'
sys.exit(main(['extract'] + args[:3] + ['--name-contains', name]))
