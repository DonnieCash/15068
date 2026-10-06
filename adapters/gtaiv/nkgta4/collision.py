"""Collision intermediate shaped like GTA IV's phBoundGeometry. NOT a WBN/OBN file.

What the game stores for a geometry bound (GTA4Unity @ c107e46,
RageLib/Collision/PhBoundGeometry.cs, PhBound.cs; layouts derived by that
project from the game executable): vertices as int16 triples decoded as
`q * unquantize_factor + center` per axis; 32-byte polygons holding a normal,
an area, four vertex indices (uint16) and four neighbour indices (uint16);
plus bounding box, centroid and radius in the phBound base.

This module computes those quantities from source triangles and checks them
(index range, degenerate faces, quantisation error, uint16 limits). It does
not serialise a resource: the binary WBN is a relocated RAGE resource and the
openFormats .obn text grammar is not publicly specified, so compilation is an
explicit external step (docs/RESEARCH.md). Things the game needs that are not
established here are listed in `unresolved`.
"""
import math

from .errors import FormatError

INT16_MAX = 32767
MAX_INDEX = 0xFFFF  # vertex and polygon indices are uint16


def _sub(a, b):
    return (a[0] - b[0], a[1] - b[1], a[2] - b[2])


def _cross(a, b):
    return (a[1] * b[2] - a[2] * b[1], a[2] * b[0] - a[0] * b[2], a[0] * b[1] - a[1] * b[0])


def _len(a):
    return math.sqrt(a[0] * a[0] + a[1] * a[1] + a[2] * a[2])


def build_bound(vertices, triangles, *, min_area=1e-6, max_error=0.01):
    """Return a dict describing one geometry bound in the same (model-local) frame as `vertices`.

    `max_error` (metres, as a hypothesis about units) is the largest allowed
    distance between a source vertex and its quantised position.
    """
    if not vertices or not triangles:
        raise FormatError('collision needs vertices and triangles')
    if len(vertices) > MAX_INDEX + 1:
        raise FormatError('%d vertices exceed the uint16 index range of one bound' % len(vertices))
    if len(triangles) > MAX_INDEX:
        raise FormatError('%d polygons exceed the uint16 range of one bound' % len(triangles))
    lo = [min(v[i] for v in vertices) for i in range(3)]
    hi = [max(v[i] for v in vertices) for i in range(3)]
    center = tuple((lo[i] + hi[i]) / 2 for i in range(3))
    half = [(hi[i] - lo[i]) / 2 for i in range(3)]
    factor = tuple(h / INT16_MAX if h > 0 else 1.0 / INT16_MAX for h in half)

    quantized, worst = [], 0.0
    for v in vertices:
        q = tuple(int(round((v[i] - center[i]) / factor[i])) for i in range(3))
        if any(abs(c) > INT16_MAX for c in q):
            raise FormatError('vertex outside the int16 quantisation range')
        back = tuple(q[i] * factor[i] + center[i] for i in range(3))
        worst = max(worst, _len(_sub(back, v)))
        quantized.append(q)
    if worst > max_error:
        raise FormatError('quantisation error %.6f exceeds %.6f; split the bound' % (worst, max_error))

    polygons, edges = [], {}
    for n, (a, b, c) in enumerate(triangles):
        for i in (a, b, c):
            if not 0 <= i < len(vertices):
                raise FormatError('triangle %d: index %d out of range' % (n, i))
        if len({a, b, c}) < 3:
            raise FormatError('triangle %d repeats a vertex' % n)
        cr = _cross(_sub(vertices[b], vertices[a]), _sub(vertices[c], vertices[a]))
        area = _len(cr) / 2
        if area < min_area:
            raise FormatError('triangle %d is degenerate (area %.3g)' % (n, area))
        normal = tuple(x / (2 * area) for x in cr)
        polygons.append({'vertices': [a, b, c], 'normal': [round(x, 6) for x in normal], 'area': round(area, 6)})
        for e, (p, q) in enumerate(((a, b), (b, c), (c, a))):
            edges.setdefault((min(p, q), max(p, q)), []).append((n, e))

    non_manifold = 0
    for users in edges.values():
        if len(users) == 2:
            (p1, e1), (p2, e2) = users
            polygons[p1].setdefault('neighbors', [None, None, None])[e1] = p2
            polygons[p2].setdefault('neighbors', [None, None, None])[e2] = p1
        elif len(users) > 2:
            non_manifold += 1
    for p in polygons:
        p.setdefault('neighbors', [None, None, None])

    centroid = tuple(sum(v[i] for v in vertices) / len(vertices) for i in range(3))
    radius = max(_len(_sub(v, centroid)) for v in vertices)
    r6 = lambda t: [round(x, 6) for x in t]
    return {
        'format': 'nk-gta4-bound-geometry/1',
        'bound_type': 'Geometry (GTA IV type 4)',
        'bbox_min': r6(lo), 'bbox_max': r6(hi), 'center': r6(center),
        'unquantize_factor': [round(f, 9) for f in factor],
        'centroid': r6(centroid), 'radius_around_centroid': round(radius, 6),
        'max_quantization_error': round(worst, 9),
        'vertices_quantized': [list(q) for q in quantized],
        'polygons': polygons,
        'stats': {'vertices': len(vertices), 'polygons': len(polygons),
                  'open_edges': sum(1 for u in edges.values() if len(u) == 1),
                  'non_manifold_edges': non_manifold},
        'unresolved': [
            'per-polygon collision material (surface type) index',
            'neighbour sentinel value and edge order expected by the game',
            'triangle encoding in the 4-index polygon slot (fourth index)',
            'margin, CG offset and volume distribution fields of phBound',
            'binary resource container (WBN) or openFormats .obn text grammar',
        ],
    }


def dequantize(bound):
    f, c = bound['unquantize_factor'], bound['center']
    return [tuple(q[i] * f[i] + c[i] for i in range(3)) for q in bound['vertices_quantized']]
