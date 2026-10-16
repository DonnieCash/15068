"""OpenIV Package (.oiv, format 2.2) for GTA IV, from an explicit install plan.

Spec: OpenIV-Team/OpenIV-PackageFormat @ 6f9d25a, specification/versions/2.2.md.
A zip holding assembly.xml (package version="2.2", target="IV", metadata,
colors, content) and a content/ folder. Content commands used here: <add>
(loose files), <archive type="IMG3"> wrapping <add> (files inside an IMG),
and <text><add> (append a line to a text file).

This module never invents registration lines or compiled files: every file
must be listed in the plan with its sha256, and every text line must carry a
note saying where its exact form was copied from.
"""
import hashlib
import io
import json
import re
import zipfile
from pathlib import Path, PureWindowsPath
from xml.sax.saxutils import escape

from .errors import FormatError
from .manifest import rel_path, req, sha, text

FORMAT = 'nk-gta4-install/1'
GUID = re.compile(r'^\{[0-9A-Fa-f]{8}-[0-9A-Fa-f]{4}-[0-9A-Fa-f]{4}-[0-9A-Fa-f]{4}-[0-9A-Fa-f]{12}\}$')
ARCHIVE_EXT = ('.wdr', '.wdd', '.wft', '.wtd', '.wbn', '.wbd', '.wpl')
LOOSE_EXT = ('.ide', '.img')
_EPOCH = (1980, 1, 1, 0, 0, 0)


def game_path(v, where):
    """A path inside the game folder, Windows style, no drive letter or '..'."""
    if not isinstance(v, str) or not v or '/' in v or '\0' in v:
        raise FormatError('%s must be a relative Windows path (backslashes)' % where)
    p = PureWindowsPath(v)
    if p.drive or p.root or '..' in p.parts:
        raise FormatError('%s must stay inside the game folder' % where)
    return v


def validate(plan):
    if not isinstance(plan, dict) or plan.get('format') != FORMAT:
        raise FormatError('install plan "format" must be %r' % FORMAT)
    pkg = req(plan, 'package', 'plan', dict)
    for k in ('name', 'author', 'description'):
        text(pkg, k, 'package')
    for k in ('major', 'minor'):
        if req(pkg, k, 'package', int) < 0:
            raise FormatError('package.%s must be >= 0' % k)
    if not GUID.match(text(plan, 'guid', 'plan')):
        raise FormatError('plan.guid must look like {XXXXXXXX-XXXX-XXXX-XXXX-XXXXXXXXXXXX}')
    arc = req(plan, 'archive', 'plan', dict)
    if not game_path(text(arc, 'path', 'archive'), 'archive.path').lower().endswith('.img'):
        raise FormatError('archive.path must name an .img')
    if not isinstance(arc.get('create_if_missing'), bool):
        raise FormatError('archive.create_if_missing must be true or false')
    names = set()
    for i, f in enumerate(req(plan, 'archive_files', 'plan', list)):
        w = 'archive_files[%d]' % i
        rel_path(text(f, 'file', w), w + '.file')
        sha(f, 'sha256', w)
        n = text(f, 'name', w)
        if '\\' in n or '/' in n or not n.lower().endswith(ARCHIVE_EXT) or n.lower() in names:
            raise FormatError('%s.name must be a unique bare file name ending in %s' % (w, ', '.join(ARCHIVE_EXT)))
        names.add(n.lower())
    for i, f in enumerate(req(plan, 'loose_files', 'plan', list)):
        w = 'loose_files[%d]' % i
        rel_path(text(f, 'file', w), w + '.file')
        sha(f, 'sha256', w)
        if not game_path(text(f, 'target', w), w + '.target').lower().endswith(LOOSE_EXT):
            raise FormatError('%s.target must end in %s' % (w, ', '.join(LOOSE_EXT)))
    for i, t in enumerate(req(plan, 'text_edits', 'plan', list)):
        w = 'text_edits[%d]' % i
        game_path(text(t, 'path', w), w + '.path')
        line = text(t, 'add', w)
        if '\n' in line or '\r' in line:
            raise FormatError('%s.add must be one line' % w)
        text(t, 'note', w)
    if not plan['archive_files'] and not plan['loose_files']:
        raise FormatError('install plan installs nothing')
    return plan


def _assembly(plan):
    p = plan['package']
    e = lambda s: escape(s, {'"': '&quot;'})
    out = ['<?xml version="1.0" encoding="UTF-8"?>',
           '<package version="2.2" id="%s" target="IV">' % plan['guid'],
           '\t<metadata>', '\t\t<name>%s</name>' % e(p['name']),
           '\t\t<version>', '\t\t\t<major>%d</major>' % p['major'], '\t\t\t<minor>%d</minor>' % p['minor'],
           '\t\t\t<tag>TEST</tag>', '\t\t</version>',
           '\t\t<author>', '\t\t\t<displayName>%s</displayName>' % e(p['author']), '\t\t</author>',
           '\t\t<description><![CDATA[%s]]></description>' % p['description'].replace(']]>', ']] >'),
           '\t</metadata>',
           '\t<colors>', '\t\t<headerBackground useBlackTextColor="False">$FF23366A</headerBackground>',
           '\t\t<iconBackground>$FF3B5998</iconBackground>', '\t</colors>', '\t<content>']
    for f in plan['loose_files']:
        out.append('\t\t<add source="%s">%s</add>' % (e(Path(f['file']).name), e(f['target'])))
    arc = plan['archive']
    if plan['archive_files']:
        out.append('\t\t<archive path="%s" createIfNotExist="%s" type="IMG3">'
                   % (e(arc['path']), 'True' if arc['create_if_missing'] else 'False'))
        for f in plan['archive_files']:
            out.append('\t\t\t<add source="%s">%s</add>' % (e(f['name']), e(f['name'])))
        out.append('\t\t</archive>')
    by_path = {}
    for t in plan['text_edits']:
        by_path.setdefault(t['path'], []).append(t['add'])
    for path, lines in by_path.items():
        out.append('\t\t<text path="%s" createIfNotExist="False">' % e(path))
        out += ['\t\t\t<add>%s</add>' % e(l) for l in lines]
        out.append('\t\t</text>')
    out += ['\t</content>', '</package>']
    return '\n'.join(out) + '\n'


def build(plan, files_root, out_path):
    validate(plan)
    payload, seen = [], set()
    for f in plan['archive_files'] + plan['loose_files']:
        data = (Path(files_root) / f['file']).read_bytes()
        if hashlib.sha256(data).hexdigest() != f['sha256']:
            raise FormatError('%s: sha256 does not match the install plan' % f['file'])
        arcname = 'content/' + (f.get('name') or Path(f['file']).name)
        if arcname.lower() in seen:
            raise FormatError('two files would share %s in the package' % arcname)
        seen.add(arcname.lower())
        payload.append((arcname, data))
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, 'w', zipfile.ZIP_DEFLATED) as z:
        for arcname, data in [('assembly.xml', _assembly(plan).encode('utf-8'))] + sorted(payload):
            zi = zipfile.ZipInfo(arcname, date_time=_EPOCH)
            zi.compress_type = zipfile.ZIP_DEFLATED
            z.writestr(zi, data)
    blob = buf.getvalue()
    out = Path(out_path)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_bytes(blob)
    return {'package': str(out), 'sha256': hashlib.sha256(blob).hexdigest(), 'files': len(payload),
            'text_edits': len(plan['text_edits'])}


def load_plan(path):
    try:
        return validate(json.loads(Path(path).read_text(encoding='utf-8')))
    except ValueError as e:
        if isinstance(e, FormatError):
            raise
        raise FormatError('install plan is not valid JSON: %s' % e) from None
