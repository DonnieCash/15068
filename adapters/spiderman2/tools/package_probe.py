#!/usr/bin/env python3
"""Compatibility wrapper: python tools/package_probe.py PROBE_DIR OUTPUT.model"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from sm2adapter.cli import main
sys.exit(main(['package'] + sys.argv[1:]))
