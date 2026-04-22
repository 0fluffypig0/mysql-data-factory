"""
Runtime path resolution.

Returns the user-visible application root:
- Frozen (PyInstaller): directory containing the .exe — writable, editable by the user.
- Development: repo root (src/ parent).
"""

from __future__ import annotations

import sys
from pathlib import Path


def get_app_root() -> Path:
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parents[2]
