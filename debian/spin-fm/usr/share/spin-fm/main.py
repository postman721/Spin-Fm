#!/usr/bin/env python3
"""Spin FM launcher for source checkouts and direct system installations."""

from __future__ import annotations

import sys
from pathlib import Path

# The supported launch paths run directly from application-private source.
# Disable bytecode writes before importing any project module so source trees
# and system installations stay free of ``__pycache__`` directories.
sys.dont_write_bytecode = True

APP_ROOT = Path(__file__).resolve().parent

# Source checkouts keep the application under ``src/spin_fm``. A direct system
# install keeps that same ``src`` tree beside this launcher.
SOURCE_ROOT = APP_ROOT / "src"
if not (SOURCE_ROOT / "spin_fm").is_dir():
    print(
        f"Spin FM application files were not found below {SOURCE_ROOT}",
        file=sys.stderr,
    )
    raise SystemExit(2)

source_path = str(SOURCE_ROOT)
if source_path not in sys.path:
    sys.path.insert(0, source_path)

from spin_fm.app import main  # noqa: E402

if __name__ == "__main__":
    raise SystemExit(main())
