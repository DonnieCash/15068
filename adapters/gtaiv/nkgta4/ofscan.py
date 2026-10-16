"""Structure-only summary of an openFormats text file (.obn, .odr, .mesh, .opl, .ide).

The grammar of these files is not publicly specified (docs/RESEARCH.md). The
operator exports a real file with OpenIV and runs this scanner; its report
keeps keywords, brace nesting and per-line token shapes, but replaces every
number with `n` and every other value with `s`, so no coordinates, names or
textures leave the machine. Repeated identical lines are collapsed with a count.
"""
import re

from .errors import FormatError

KEYWORD = re.compile(r'^[A-Za-z_][A-Za-z0-9_]*$')
NUMBER = re.compile(r'^[-+]?(\d+\.?\d*|\.\d+)([eE][-+]?\d+)?$')
MAX_BYTES = 256 * 1024 * 1024


def _shape(tokens):
    out = []
    for i, t in enumerate(tokens):
        if t in ('{', '}', '/', ',', ';'):
            out.append(t)
        elif NUMBER.match(t):
            out.append('n')
        elif i == 0 and KEYWORD.match(t):
            out.append(t)
        else:
            out.append('s')
    return ' '.join(out)


def scan(text):
    if len(text) > MAX_BYTES:
        raise FormatError('file too large to scan')
    rows, depth, prev = [], 0, None
    for raw in text.splitlines():
        line = raw.strip()
        if not line:
            continue
        tokens = re.findall(r'[{}/,;]|[^\s{}/,;]+', line)
        if line.startswith('}'):
            depth -= 1
        if depth < 0:
            raise FormatError('unbalanced braces')
        shape = '  ' * depth + _shape(tokens)
        if prev is not None and rows[-1][0] == shape:
            rows[-1][1] += 1
        else:
            rows.append([shape, 1])
        prev = shape
        depth += tokens.count('{') - tokens.count('}') + (1 if line.startswith('}') else 0)
        if depth < 0:
            raise FormatError('unbalanced braces')
    if depth != 0:
        raise FormatError('unbalanced braces at end of file')
    return [s if n == 1 else '%s   x%d' % (s, n) for s, n in rows]
