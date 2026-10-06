"""GTA IV IDE `objs` lines (text).

Field order from GTA4Unity @ c107e46 (Assets/Scripts/IVUnity/IDE/Items/Item_OBJS.cs):
model name, texture dictionary, draw distance, flag1, flag2, bbox min xyz,
bbox max xyz, bounding sphere centre xyz + radius, WDD name. The meaning of
the two flag fields is not established, so they are required inputs (copy
them from a comparable vanilla object), never defaults.
"""
import math
import re

from .errors import FormatError

NAME = re.compile(r'^[A-Za-z0-9_]{1,63}$')


def _name(v, what):
    if not isinstance(v, str) or not NAME.match(v):
        raise FormatError('%s must be 1-63 letters, digits or _' % what)
    return v


def bounds_of(vertices):
    lo = [min(v[i] for v in vertices) for i in range(3)]
    hi = [max(v[i] for v in vertices) for i in range(3)]
    c = [(lo[i] + hi[i]) / 2 for i in range(3)]
    r = max(math.dist(c, v) for v in vertices)
    return lo, hi, c + [r]


def objs_line(model, txd, draw_distance, flag1, flag2, bbox_min, bbox_max, sphere, wdd):
    _name(model, 'model name')
    _name(txd, 'texture dictionary')
    if not isinstance(wdd, str) or not wdd or ',' in wdd:
        raise FormatError('wdd name must be given explicitly')
    for v in (flag1, flag2):
        if isinstance(v, bool) or not isinstance(v, int):
            raise FormatError('flags must be integers')
    nums = [draw_distance, *bbox_min, *bbox_max, *sphere]
    if len(nums) != 11 or not all(isinstance(x, (int, float)) and math.isfinite(x) for x in nums):
        raise FormatError('draw distance, bounds and sphere must be finite numbers')
    if draw_distance <= 0 or sphere[3] < 0 or any(bbox_min[i] > bbox_max[i] for i in range(3)):
        raise FormatError('inconsistent draw distance or bounds')
    fields = [model, txd, f(draw_distance), str(flag1), str(flag2)] + [f(x) for x in (*bbox_min, *bbox_max, *sphere)] + [wdd]
    return ', '.join(fields)


def f(x):
    s = ('%.6f' % x).rstrip('0').rstrip('.')
    return '0' if s in ('', '-0') else s


def objs_section(lines):
    return 'objs\n' + ''.join(l + '\n' for l in lines) + 'end\n'


def parse_objs_line(line):
    parts = [p.strip() for p in line.split(',')]
    if len(parts) != 16:
        raise FormatError('objs line needs 16 fields, got %d' % len(parts))
    try:
        nums = [float(x) for x in parts[5:15]]
        return {'model': parts[0], 'txd': parts[1], 'draw_distance': float(parts[2]),
                'flag1': int(parts[3]), 'flag2': int(parts[4]),
                'bbox_min': nums[0:3], 'bbox_max': nums[3:6], 'sphere': nums[6:10], 'wdd': parts[15]}
    except ValueError:
        raise FormatError('objs line has a non-numeric field') from None
