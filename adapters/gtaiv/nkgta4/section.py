"""Build validated, deterministic intermediates for one NK section.

Outputs (all under `out_dir`, which must be outside the game):
  <section>.ide                 IDE `objs` section, one line per component
  <section>.wpl                 binary WPL with one `inst` per component
  models/<name>.obj             render geometry in the model's local frame
  collision/<name>.bound.json   phBoundGeometry-shaped collision intermediate
  build-report.json             hashes, transforms, and the external steps still required

Local frame: each component's world-space vertices (after `nk_to_game`) are
re-centred on (bbox centre x, bbox centre y, bbox min z); that point becomes the
instance position and the rotation is identity. This is an adapter
convention, not a game requirement.
"""
import hashlib
import json
from pathlib import Path

from . import ide, wpl
from .collision import build_bound
from .errors import FormatError
from .manifest import known, rel_path
from .objmesh import parse_obj, write_obj

EXTERNAL_STEPS = [
    'compile models/<name>.obj to <name>.wdr (OpenIV openFormats import or 3ds Max + GIMS IV/OFIO); no native writer exists here',
    'build <txd>.wtd textures for the materials (OpenIV texture editor); none are generated here',
    'compile collision/<name>.bound.json to a WBN (openFormats .obn grammar unknown until gate G1 sample)',
    'package with `oiv` from compiled files + exact registration lines copied from the local game (gate G4)',
]


def _sha(data):
    return hashlib.sha256(data).hexdigest()


def _read_checked(root, rel, expected, where):
    p = Path(root) / rel_path(rel, where)
    data = p.read_bytes()
    if _sha(data) != expected:
        raise FormatError('%s: sha256 of %s does not match the manifest' % (where, rel))
    return data.decode('utf-8')


def _apply(m, v):
    x, y, z = v
    return (m[0] * x + m[1] * y + m[2] * z + m[3],
            m[4] * x + m[5] * y + m[6] * z + m[7],
            m[8] * x + m[9] * y + m[10] * z + m[11])


def build(doc, staging_root, out_dir):
    matrix = known(doc['nk_to_game'], 'nk_to_game')
    out = Path(out_dir)
    (out / 'models').mkdir(parents=True, exist_ok=True)
    (out / 'collision').mkdir(parents=True, exist_ok=True)
    ide_lines, instances, report_components, files = [], [], [], {}

    def emit(rel, data):
        (out / rel).write_bytes(data)
        files[rel] = _sha(data)

    for i, c in enumerate(doc['components']):
        w = 'components[%d]' % i
        name = c['model']['name']
        render = parse_obj(_read_checked(staging_root, c['render']['obj'], c['render']['sha256'], w + '.render'))
        world = [_apply(matrix, v) for v in render.vertices]
        lo = [min(v[k] for v in world) for k in range(3)]
        hi = [max(v[k] for v in world) for k in range(3)]
        origin = ((lo[0] + hi[0]) / 2, (lo[1] + hi[1]) / 2, lo[2])
        to_local = lambda vs: [tuple(round(v[k] - origin[k], 6) for k in range(3)) for v in vs]
        render.vertices = to_local(world)

        col = c['collision']
        if col['source'] == 'render':
            col_vertices, col_triangles = render.vertices, render.triangles
        else:
            cm = parse_obj(_read_checked(staging_root, col['obj'], col['sha256'], w + '.collision'))
            col_vertices, col_triangles = to_local([_apply(matrix, v) for v in cm.vertices]), cm.triangles
        bound = build_bound(col_vertices, col_triangles)
        bound['surface'] = col['surface']

        flags = known(c['ide_flags'], w + '.ide_flags')
        bmin, bmax, sphere = ide.bounds_of(render.vertices)
        ide_lines.append(ide.objs_line(name, c['model']['txd'], c['model']['draw_distance'], flags[0], flags[1],
                                       bmin, bmax, sphere, known(c['wdd'], w + '.wdd')))
        place = known(c['placement'], w + '.placement')
        instances.append(dict(place, model=name, position=origin, rotation=(0.0, 0.0, 0.0, 1.0)))

        emit('models/%s.obj' % name, write_obj(render).encode())
        emit('collision/%s.bound.json' % name, (json.dumps(bound, indent=1, sort_keys=True) + '\n').encode())
        report_components.append({
            'tile_id': c['nk']['tile_id'], 'component_id': c['nk']['component_id'], 'model': name,
            'model_hash': '0x%08x' % wpl.gta_hash(name), 'instance_position': [round(x, 6) for x in origin],
            'render': {'vertices': len(render.vertices), 'triangles': len(render.triangles)},
            'collision': dict(bound['stats'], max_quantization_error=bound['max_quantization_error'],
                              surface=col['surface']['status'], outcome=col['outcome']['status']),
            'lod_parent': c['lod_parent']['status'],
        })

    section = doc['section_id']
    emit('%s.ide' % section, ide.objs_section(ide_lines).encode())
    emit('%s.wpl' % section, wpl.pack(instances))
    report = {
        'format': 'nk-gta4-build-report/1', 'section_id': section, 'game_ready': False,
        'nk_release_sha256': doc['nk']['release_sha256'],
        'nk_to_game': {'status': doc['nk_to_game']['status'], 'matrix': matrix},
        'components': report_components, 'files': files, 'external_steps': EXTERNAL_STEPS,
    }
    (out / 'build-report.json').write_text(json.dumps(report, indent=2, sort_keys=True) + '\n')
    return report
