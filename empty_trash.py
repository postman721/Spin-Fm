#!/usr/bin/env python3
"""Helpers for clearing the user's local freedesktop Trash."""

import os
import shutil
import sys

sys.dont_write_bytecode = True


def _remove_entry(path: str) -> None:
    """Delete a single filesystem entry.

    scandir/listdir callers hand us one entry at a time so this stays memory
    efficient even for large trash folders.
    """
    if os.path.isdir(path) and not os.path.islink(path):
        shutil.rmtree(path)
    else:
        os.unlink(path)


def empty_trash() -> None:
    """Empty both Trash/files and Trash/info.

    Removing only the payload files leaves stale .trashinfo metadata behind, so
    both directories are cleaned together.
    """
    trash_root = os.path.expanduser("~/.local/share/Trash")
    trash_dirs = [
        os.path.join(trash_root, "files"),
        os.path.join(trash_root, "info"),
    ]

    found_any = False
    failures = []

    for directory in trash_dirs:
        if not os.path.isdir(directory):
            continue

        found_any = True
        with os.scandir(directory) as entries:
            for entry in entries:
                try:
                    _remove_entry(entry.path)
                except Exception as exc:
                    failures.append(f"{entry.path}: {exc}")

    if failures:
        raise RuntimeError("\n".join(failures))

    if found_any:
        print("Trash emptied successfully.")
    else:
        print("Trash directory not found.")
