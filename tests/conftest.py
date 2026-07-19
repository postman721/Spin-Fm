"""Keep ordinary pytest runs from writing bytecode into the source tree."""

from __future__ import annotations

import sys
from pathlib import Path

# ``--assert=plain`` prevents pytest's assertion-rewrite bytecode. This hook runs
# before project/test modules are collected, disables normal import bytecode, and
# removes the one cache entry Python may have created while importing conftest.
sys.dont_write_bytecode = True
_cached_file = globals().get("__cached__")
if isinstance(_cached_file, str):
    cached_path = Path(_cached_file)
    try:
        cached_path.unlink()
    except OSError:
        pass
    try:
        cached_path.parent.rmdir()
    except OSError:
        pass
del _cached_file
