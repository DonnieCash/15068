"""Bounds applied while parsing untrusted archives. All values are overridable."""
from dataclasses import dataclass


@dataclass(frozen=True)
class Limits:
    max_toc_bytes: int = 512 * 1024 * 1024
    max_sections: int = 256
    max_archives: int = 4096
    max_span_entries: int = 64 * 1024 * 1024     # sum of span counts (spans may overlap)
    max_dsar_blocks: int = 4 * 1024 * 1024
    max_block_bytes: int = 16 * 1024 * 1024      # uncompressed size of one block we decompress
    max_asset_bytes: int = 1024 * 1024 * 1024    # bytes extracted for one asset
    max_ratio: int = 1024                        # uncompressed / compressed, per block we decompress
    max_header_bytes: int = 64 * 1024
    max_texture_meta_bytes: int = 1024 * 1024


DEFAULT_LIMITS = Limits()
