"""GTA IV model-name hash (Jenkins one-at-a-time, lowercased, '\\' -> '/').

Behaviour documented by RageLib's Hasher (GTA4Unity @ c107e46,
Assets/Scripts/RageLib/Common/Hasher.cs): an optional leading '"' starts a
quoted name that ends at the next '"'; results below 2 are bumped by 2.
This is an independent re-implementation, checked against the standard
one-at-a-time test vectors (docs/RESEARCH.md).
"""

M = 0xFFFFFFFF


def one_at_a_time(data):
    h = 0
    for b in data:
        h = (h + b) & M
        h = (h + (h << 10)) & M
        h ^= h >> 6
    h = (h + (h << 3)) & M
    h ^= h >> 11
    h = (h + (h << 15)) & M
    return h


def gta_hash(name):
    if not isinstance(name, str) or not name:
        raise ValueError('name must be a non-empty string')
    s = name.lower()
    if s.startswith('"'):
        end = s.find('"', 1)
        s = s[1:] if end < 0 else s[1:end]
    h = one_at_a_time(s.replace('\\', '/').encode('latin-1'))
    return h + 2 if h < 2 else h
