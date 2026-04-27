"""Internal hex-color validation shared by composition schemas + overlays.

Lives in its own module so that schemas.py and overlays.py can both import it
without creating a circular dependency. Not part of the public API.
"""

from __future__ import annotations

import re

_HEX_COLOR_RE = re.compile(r"^#(?:[0-9a-fA-F]{6}|[0-9a-fA-F]{8})$")


def _validate_hex_color(v: str) -> str:
    if not _HEX_COLOR_RE.match(v):
        raise ValueError(f"Invalid hex color: {v!r} (expected #RRGGBB or #RRGGBBAA)")
    return v.upper()
