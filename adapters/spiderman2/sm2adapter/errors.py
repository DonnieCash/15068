"""Exception types. Every parse failure is a FormatError so callers can tell
malformed input apart from programming errors."""


class FormatError(ValueError):
    """Input is malformed, truncated, out of bounds or over a configured limit."""


class UnsupportedError(FormatError):
    """Input is well formed but uses a feature this adapter does not implement."""


class UnsafePathError(FormatError):
    """A name taken from untrusted data would escape its root directory."""
