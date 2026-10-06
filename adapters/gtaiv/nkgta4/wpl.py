"""Binary GTA IV WPL placement: header + `inst` records only.

Layout from GTA4Unity @ c107e46 (Assets/Scripts/IVUnity/IPL/IPL.cs ReadHeader,
IPL/Items/Ipl_INST.cs), a reader whose authors derived it from the game:
17 int32 header fields (version [observed 3], inst, unused, grge, cars, cull,
3 unused, strbig, lcul, zone, 4 unused, blok) followed by `inst` records of
position (3 float), stored rotation quaternion (4 float), model-name hash
(uint32), flags (int32), lod index (int32), unknown (int32), unknown (float).
Only `inst` is written; every other count is 0. Not yet confirmed by loading
a written file in the game (LOCAL_HANDOFF.md gate G5).
"""
import math
import struct

from .errors import FormatError
from .jenkins import gta_hash

HEADER = struct.Struct('<17i')
INST = struct.Struct('<3f4fIiiif')
VERSION = 3


def stored_quaternion_z(yaw_degrees):
    """Stored quaternion for a rotation of `yaw_degrees` about +Z.

    GTA4Unity (RageCoordinates.cs, citing OpenRage entity.cpp:200) says RAGE
    stores quaternions with x, y, z negated relative to the mathematical
    rotation. Hypothesis until checked in game.
    """
    h = math.radians(yaw_degrees) / 2
    return (0.0, 0.0, -math.sin(h), math.cos(h))


def pack(instances):
    """instances: dicts with model, position, rotation (stored xyzw), flags, lod, unknown_int, unknown_float."""
    if not instances:
        raise FormatError('no instances to place')
    body = b''
    for i, inst in enumerate(instances):
        try:
            pos, rot = inst['position'], inst['rotation']
            vals = (*pos, *rot)
            if len(pos) != 3 or len(rot) != 4 or not all(math.isfinite(v) for v in vals):
                raise FormatError('instance %d: position/rotation must be 3/4 finite numbers' % i)
            norm = math.sqrt(sum(r * r for r in rot))
            if abs(norm - 1) > 1e-4:
                raise FormatError('instance %d: rotation is not a unit quaternion' % i)
            for k in ('flags', 'lod', 'unknown_int'):
                if isinstance(inst[k], bool) or not isinstance(inst[k], int):
                    raise FormatError('instance %d: %s must be an explicit integer' % (i, k))
            body += INST.pack(*pos, *rot, gta_hash(inst['model']), inst['flags'], inst['lod'],
                              inst['unknown_int'], float(inst['unknown_float']))
        except KeyError as e:
            raise FormatError('instance %d: missing %s' % (i, e)) from None
        except struct.error as e:
            raise FormatError('instance %d: %s' % (i, e)) from None
    header = [0] * 17
    header[0], header[1] = VERSION, len(instances)
    return HEADER.pack(*header) + body


def unpack(data):
    if len(data) < HEADER.size:
        raise FormatError('WPL truncated')
    h = HEADER.unpack_from(data)
    if h[0] != VERSION:
        raise FormatError('unexpected WPL version %d' % h[0])
    if any(h[2:]):
        raise FormatError('only inst-only WPLs are supported')
    n = h[1]
    if n < 0 or len(data) != HEADER.size + n * INST.size:
        raise FormatError('WPL size does not match its inst count')
    out = []
    for i in range(n):
        v = INST.unpack_from(data, HEADER.size + i * INST.size)
        out.append({'position': v[0:3], 'rotation': v[3:7], 'hash': v[7], 'flags': v[8], 'lod': v[9],
                    'unknown_int': v[10], 'unknown_float': v[11]})
    return out


HEADER_NAMES = ('version', 'inst', 'unused1', 'grge', 'cars', 'cull', 'unused2', 'unused3', 'unused4',
                'strbig', 'lcul', 'zone', 'unused5', 'unused6', 'unused7', 'unused8', 'blok')


def inspect(data):
    """Header counts and value statistics of the `inst` records of any WPL.

    For copying flags/lod/unknown values from vanilla files: reports only
    distinct values and counts, never positions, rotations or model hashes.
    Assumes `inst` records follow the header, as in GTA4Unity's reader.
    """
    if len(data) < HEADER.size:
        raise FormatError('WPL truncated')
    h = dict(zip(HEADER_NAMES, HEADER.unpack_from(data)))
    n = h['inst']
    if n < 0 or len(data) < HEADER.size + n * INST.size:
        raise FormatError('WPL shorter than its inst count')
    stats = {k: {} for k in ('flags', 'lod_is_minus_one', 'unknown_int', 'unknown_float')}
    for i in range(n):
        v = INST.unpack_from(data, HEADER.size + i * INST.size)
        for k, x in (('flags', v[8]), ('lod_is_minus_one', v[9] == -1), ('unknown_int', v[10]),
                     ('unknown_float', round(v[11], 4))):
            stats[k][str(x)] = stats[k].get(str(x), 0) + 1
    return {'header': h, 'inst_value_counts': stats}
