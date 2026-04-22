#!/usr/bin/env python3
"""
MySQL Data Factory 3.0.2 - GUI Application Entry Point

Usage:
    python scripts/ui_app.py              # launch GUI
    python scripts/ui_app.py --selftest   # print runtime paths and exit
                                          # (verifies frozen/dev path resolution)
"""

import sys
from pathlib import Path

if not getattr(sys, "frozen", False):
    PROJECT_ROOT = Path(__file__).resolve().parents[1]
    if str(PROJECT_ROOT) not in sys.path:
        sys.path.insert(0, str(PROJECT_ROOT))


def _selftest() -> int:
    from src import __version__
    from src.utils.runtime_paths import get_app_root
    from src.config.app_config import AppPaths, PROJECT_ROOT

    root = get_app_root()
    paths = AppPaths()
    env_file = root / ".env"
    env_example = root / ".env.example"

    print(f"MySQL Data Factory {__version__} - selftest")
    print(f"  frozen        : {getattr(sys, 'frozen', False)}")
    print(f"  sys.executable: {sys.executable}")
    print(f"  app_root      : {root}")
    print(f"  PROJECT_ROOT  : {PROJECT_ROOT}")
    print(f"  .env exists   : {env_file.exists()}")
    print(f"  .env.example  : {env_example.exists()}")
    print(f"  reports_dir   : {paths.reports_dir}")
    print(f"  metadata_cache: {paths.metadata_cache_dir}")
    ok = PROJECT_ROOT == root and (env_file.exists() or env_example.exists())
    print(f"  result        : {'OK' if ok else 'FAIL'}")
    return 0 if ok else 1


def main():
    if "--selftest" in sys.argv:
        sys.exit(_selftest())
    from src.ui.main_window import run_gui
    run_gui()


if __name__ == "__main__":
    main()

