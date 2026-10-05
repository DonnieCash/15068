#!/usr/bin/env python3
"""Compatibility wrapper: python tools/inspect_toc.py GAME OUTPUT.json"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from sm2adapter.cli import main
sys.exit(main(['inventory'] + sys.argv[1:]))
