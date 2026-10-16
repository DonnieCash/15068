class FormatError(ValueError):
    """Input is malformed, out of bounds or over a configured limit."""


class UnsupportedError(FormatError):
    """Well-formed input that needs a feature this adapter does not implement."""
