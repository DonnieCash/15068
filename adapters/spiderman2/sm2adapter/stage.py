"""Build and verify Overstrike `.stage` (format_version 2) mods for MSM2.

Format, from Overstrike @ 9f906ca (Detectors/StageModDetector.cs,
Installers/StageInstaller.cs): a zip holding `info.json` (`game` = "MSM2",
`format_version` = 2, optional `name`/`author`) and one entry per asset named
`<span>/<16 hex digit asset id>`. An entry that is an STG container installs
its header/texture meta only when the STG flags say so; any other bytes are
installed as the asset with the TOC header left untouched. Overstrike appends
the bytes to a new archive `d/mods/modN` and repoints the TOC entry; it keeps
the original `toc` as `toc.BAK` and restores it on uninstall.

This module only writes the zip (outside the game directory). Installing it is
a separate, manual step done with Overstrike on the game machine.
"""
import hashlib
import io
import json
import re
import struct
import zipfile
from pathlib import Path

from .candidates import parse_id
from .dat1 import DAT1_MAGIC, parse_dat1
from .errors import FormatError, UnsupportedError
from .limits import DEFAULT_LIMITS
from .manifest import check_against_toc
from .paths import safe_join
from .stg import parse_stg

ENTRY = re.compile(r'^([0-9]{1,3})/([0-9A-F]{16})$')
_EPOCH = (1980, 1, 1, 0, 0, 0)


def _is_dat1(data):
    return len(data) >= 4 and struct.unpack_from('<I', data)[0] == DAT1_MAGIC


def payload_for(path, expected_sha256, limits=DEFAULT_LIMITS):
    """Read a converted model file and return the bare DAT1 bytes to install.

    Accepts a bare DAT1 blob or an STG without an installable header (header
    policy keep-original). The file's sha256 must match the manifest.
    """
    data = Path(path).read_bytes()
    if hashlib.sha256(data).hexdigest() != expected_sha256:
        raise FormatError('%s: sha256 does not match the manifest' % path)
    if not _is_dat1(data):
        stg = parse_stg(data, limits)
        if stg.flags:
            raise UnsupportedError('%s: STG asks to install a header/texture meta; '
                                   'header policy keep-original forbids it' % path)
        data = stg.payload
    parse_dat1(data, limits)
    return data


def build(doc, staging_root, toc, out_path, *, name=None, author='NK adapter', manifest_sha256=None):
    """Write a deterministic stage-v2 zip for every component that has geometry.

    Returns the plan dict (also written next to the zip as <out>.plan.json).
    """
    located = check_against_toc(doc, toc)
    entries, plan_assets = [], []
    for loc in located:
        c = doc['components'][loc['component']]
        if c.get('geometry') is None:
            continue
        if c['collision']['strategy'] == 'generated':
            raise UnsupportedError('components[%d]: no verified collision writer exists yet; '
                                   'use strategy "keep-original" or "none" (docs/RESEARCH.md)' % loc['component'])
        src = safe_join(staging_root, c['geometry']['file'])
        data = payload_for(src, c['geometry']['sha256'])
        span, asset_id = c['target']['span'], parse_id(c['target']['asset_id'])
        entries.append(('%d/%016X' % (span, asset_id), data))
        plan_assets.append(dict(loc, entry='%d/%016X' % (span, asset_id),
                                tile_id=c['nk']['tile_id'], component_id=c['nk']['component_id'],
                                payload_bytes=len(data), payload_sha256=hashlib.sha256(data).hexdigest(),
                                collision=c['collision']['strategy']))
    if not entries:
        raise FormatError('no component has geometry to stage')
    info = {'game': 'MSM2', 'format_version': 2, 'name': name or 'NK section %s' % doc['section_id'],
            'author': author,
            'nk_adapter': {'section_id': doc['section_id'], 'toc_sha1': toc.sha1,
                           'manifest_sha256': manifest_sha256}}
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, 'w', zipfile.ZIP_DEFLATED) as z:
        for arcname, data in [('info.json', json.dumps(info, indent=2, sort_keys=True).encode())] + sorted(entries):
            zi = zipfile.ZipInfo(arcname, date_time=_EPOCH)
            zi.compress_type = zipfile.ZIP_DEFLATED
            zi.external_attr = 0o644 << 16
            z.writestr(zi, data)
    blob = buf.getvalue()
    plan = {
        'format': 'nk-sm2-stage-plan/1', 'stage_sha256': hashlib.sha256(blob).hexdigest(),
        'section_id': doc['section_id'], 'game_version': doc['target']['game_version'],
        'preconditions': {'toc_sha1': toc.sha1, 'toc_sha256': toc.sha256},
        'assets': plan_assets,
        'not_covered': ['world placement (assets are replaced in place, not moved)',
                        'collision matching the new geometry (keep-original keeps the old Havok data)',
                        'streaming/LOD behaviour of the replaced assets'],
    }
    out = Path(out_path)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_bytes(blob)
    out.with_name(out.name + '.plan.json').write_text(json.dumps(plan, indent=2))
    return plan


def verify(path, toc=None, limits=DEFAULT_LIMITS):
    """Check a stage zip without extracting it to disk. Returns a summary."""
    try:
        z = zipfile.ZipFile(path)
    except zipfile.BadZipFile as e:
        raise FormatError('not a zip: %s' % e) from None
    with z:
        names = z.namelist()
        if len(names) != len(set(names)):
            raise FormatError('duplicate zip entries')
        if 'info.json' not in names:
            raise FormatError('stage has no info.json')
        total, assets = 0, []
        for zi in z.infolist():
            if zi.file_size > limits.max_asset_bytes:
                raise FormatError('%s: entry too large' % zi.filename)
            total += zi.file_size
            if total > 4 * limits.max_asset_bytes:
                raise FormatError('stage too large')
        try:
            info = json.loads(z.read('info.json'))
        except ValueError:
            raise FormatError('info.json is not valid JSON') from None
        if info.get('game') != 'MSM2' or info.get('format_version') != 2:
            raise FormatError('info.json must declare game "MSM2" and format_version 2')
        for n in names:
            if n == 'info.json':
                continue
            m = ENTRY.match(n)
            if not m or int(m.group(1)) > 255:
                raise FormatError('unexpected stage entry %r' % n)
            data = z.read(n)
            if len(data) != z.getinfo(n).file_size:
                raise FormatError('%s: size mismatch' % n)
            if _is_dat1(data):
                parse_dat1(data, limits)
                flags = None
            else:
                flags = parse_stg(data, limits).flags
            span, asset_id = int(m.group(1)), int(m.group(2), 16)
            if toc is not None and toc.find(span, asset_id) is None:
                raise FormatError('%s is not in the TOC' % n)
            assets.append({'entry': n, 'bytes': len(data), 'stg_flags': flags,
                           'sha256': hashlib.sha256(data).hexdigest()})
    if not assets:
        raise FormatError('stage has no assets')
    return {'name': info.get('name'), 'assets': assets, 'nk_adapter': info.get('nk_adapter')}
