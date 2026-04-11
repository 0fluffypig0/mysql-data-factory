#!/usr/bin/env python3
"""
MySQL Data Factory 3.00 - GUI Application Entry Point

Usage:
    python scripts/ui_app.py
"""

import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))


def main():
    from src.ui.main_window import run_gui
    run_gui()


if __name__ == "__main__":
    main()

