#!/usr/bin/env python3
"""Spin FM's standard source and installed launcher."""

from __future__ import annotations

import sys
from pathlib import Path

# Avoid writing bytecode beside a source checkout or read-only installation.
sys.dont_write_bytecode = True

APP_ROOT = Path(__file__).resolve().parent
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

from spin_fm.app import main as application_main  # noqa: E402
from spin_fm.file_info_extension import install as install_file_info  # noqa: E402


def run(argv: list[str] | None = None) -> int:
    """Run Spin FM with the independent file-information module attached."""
    arguments = list(sys.argv[1:] if argv is None else argv)
    return int(application_main(arguments, window_setup=install_file_info))


if __name__ == "__main__":
    raise SystemExit(run())
