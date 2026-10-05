"""Names of known DAT1 section tags, for reports only (no parsing depends on them).

Names come from Ripped Apart (chaoticgd/ripped_apart @ 64ea4d6, libra/lump_types.h,
MIT); entries marked "+ALERT" also carry the same name in Tkachov/ALERT @ bc90ed9.
Ripped Apart targets Rift Apart; MSM2 sharing these tags is plausible (same
engine family) but each one is only confirmed once seen in a real MSM2 asset.
"""
import struct

from .dat1 import DAT1_MAGIC, parse_dat1
from .stg import parse_stg
from .errors import FormatError

KNOWN = {
    # .model
    0x283D0383: 'Model Built', 0x3250BB80: 'Model Material', 0x06EB7EFC: 'Model Look',
    0x0859863D: 'Model Index', 0x78D9CBDE: 'Model Subset', 0xA98BE69B: 'Model Std Vert',
    0xEFD92E68: 'Model Physics Data (+ALERT, Havok)', 0x5CBA9DE9: 'Model Col Vert',
    0x15DF9D3B: 'Model Joint', 0xDCA379A2: 'Model Skin Data', 0xC61B1FF5: 'Model Skin Batch',
    0x4CCEA4AD: 'Model Look Group', 0x811902D7: 'Model Look Built', 0x9F614FAB: 'Model Locator',
    0xBCE86B01: 'Model Render Overrides', 0x00823787: 'Model Texture Overrides',
    # .zone
    0x06ABCAB2: 'Zone Scene Objects', 0x6987F172: 'Zone Model Insts', 0xC6A5905E: 'Zone Model Names',
    0x70682CB8: 'Zone Actors', 0xDC625B3D: 'Zone Actor Names (+ALERT)', 0x0CF58A6E: 'Zone Actor Groups',
    0x30DADA09: 'Zone Asset References', 0xE4158AC3: 'Zone Material Overrides (+ALERT)',
    0xBDAB2B0D: 'Zone Volumes', 0x97FF6EB5: 'Zone Lights', 0x657512BB: 'Zone Decal Geometry',
    0xDC311FC3: 'Zone Impostors', 0xCB8D34F9: 'Zone Impostors Atlas', 0xB6A0B72A: 'Zone Atmosphere Name',
    # .level
    0x2BA33702: 'Level Zone Names', 0x4E023760: 'Level Zones Built', 0x4130D903: 'Level Region Names',
    0x396F9418: 'Level Regions Built', 0x2236C47A: 'Level Link Names', 0x7CA7267D: 'Level Built',
    # .actor
    0x32FAC8E0: 'Actor Built', 0x364A6C7C: 'Actor Object Built', 0x3AB204B9: 'Actor Asset Refs',
    # toc
    0x506D7B8A: 'Archive TOC Asset IDs', 0x65BCF461: 'Archive TOC Asset Metadata',
    0xEDE8ADA9: 'Archive TOC Header', 0x398ABFF0: 'Archive TOC File Metadata',
    0x654BDED9: 'Archive TOC Asset Header Data',
}


def describe(data):
    """List (tag, name, size) for a DAT1 blob or an STG wrapping one."""
    if bytes(data[:4]) != struct.pack('<I', DAT1_MAGIC):
        try:
            data = parse_stg(data).payload
        except FormatError:
            raise FormatError('not a DAT1 blob or STG container') from None
    typ, sections = parse_dat1(data)
    return typ, [('0x%08X' % t, KNOWN.get(t), len(v)) for t, v in sorted(sections.items())]
