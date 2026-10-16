#!/usr/bin/env python3
"""python tools/generate_candidates.py GAME HASHES OUTPUT.json [--name-contains X] [--include-unnamed]"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from sm2adapter.cli import main
sys.exit(main(['candidates'] + sys.argv[1:]))
