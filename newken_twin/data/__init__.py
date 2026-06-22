"""Bundled datasets for the digital twin."""

from __future__ import annotations

import os

from ..model import City, load_city

_DATA_DIR = os.path.dirname(__file__)
DEFAULT_DATASET = os.path.join(_DATA_DIR, "new_kensington.json")


def load_default_city() -> City:
    """Load the bundled New Kensington, PA dataset."""
    return load_city(DEFAULT_DATASET)
