#!/usr/bin/env python3
"""
MySQL Data Factory 3.0.2 — PyInstaller build helper (Windows, --onedir).

Runs PyInstaller against mysql_factory.spec and stages user-editable files
(.env.example) next to the resulting executable so the distribution folder
is immediately usable.

Usage:
    python scripts/build_exe.py            # clean build
    python scripts/build_exe.py --keep     # reuse previous build/ cache
"""

from __future__ import annotations

import argparse
import shutil
import subprocess
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SPEC_FILE = PROJECT_ROOT / "mysql_factory.spec"
DIST_DIR = PROJECT_ROOT / "dist" / "mysql_factory"
BUILD_DIR = PROJECT_ROOT / "build"


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Build mysql-data-factory GUI as a Windows --onedir PyInstaller bundle."
    )
    parser.add_argument(
        "--keep",
        action="store_true",
        help="Reuse build/ and dist/ caches (faster rebuild).",
    )
    args = parser.parse_args()

    if not SPEC_FILE.exists():
        print(f"[FAIL] spec file not found: {SPEC_FILE}")
        return 1

    if not args.keep:
        for d in (BUILD_DIR, PROJECT_ROOT / "dist"):
            if d.exists():
                print(f"[clean] {d}")
                shutil.rmtree(d)

    cmd = [sys.executable, "-m", "PyInstaller", "--noconfirm", str(SPEC_FILE)]
    print(f"[run] {' '.join(cmd)}")
    result = subprocess.run(cmd, cwd=str(PROJECT_ROOT))
    if result.returncode != 0:
        print(f"[FAIL] PyInstaller exited with code {result.returncode}")
        return result.returncode

    # Stage user-editable files next to the exe.
    exe_path = DIST_DIR / "mysql_factory.exe"
    if not exe_path.exists():
        print(f"[FAIL] expected exe not found: {exe_path}")
        return 1

    env_example_src = PROJECT_ROOT / ".env.example"
    env_example_dst = DIST_DIR / ".env.example"
    if env_example_src.exists():
        shutil.copy2(env_example_src, env_example_dst)
        print(f"[stage] {env_example_dst.name}")

    size_mb = sum(p.stat().st_size for p in DIST_DIR.rglob("*") if p.is_file()) / (1024 * 1024)
    print()
    print("=" * 60)
    print(f"  Build OK — {DIST_DIR}")
    print(f"  Total size: {size_mb:.1f} MB")
    print()
    print("  Try it:")
    print(f"    cd {DIST_DIR}")
    print(f"    copy .env.example .env   # edit DB creds")
    print(f"    mysql_factory.exe")
    print("=" * 60)
    return 0


if __name__ == "__main__":
    sys.exit(main())
