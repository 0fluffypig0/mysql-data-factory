#!/usr/bin/env python3
"""Deprecated shim. Use scripts/build_offline_env.py instead."""

from __future__ import annotations

import runpy
from pathlib import Path


SCRIPT_PATH = Path(__file__).resolve().with_name("build_offline_env.py")


if __name__ == "__main__":
    print("[DEPRECATED] Use scripts/build_offline_env.py instead.")
    runpy.run_path(str(SCRIPT_PATH), run_name="__main__")
