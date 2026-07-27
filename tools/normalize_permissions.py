#!/usr/bin/env python3
"""Repair or verify Spin FM executable modes after archive downloads.

GitHub's zipped workflow artifacts intentionally normalize regular files to
0644. This helper restores only the small, audited set of source files that must
be executable. It is itself invoked through ``python3`` and therefore works even
when its own executable bit was lost during upload/download.
"""

from __future__ import annotations

import argparse
import os
import stat
import sys
from pathlib import Path, PurePosixPath

sys.dont_write_bytecode = True

MANIFEST_RELATIVE_PATH = Path("tools/executable_paths.txt")


def load_executable_paths(root: Path) -> tuple[PurePosixPath, ...]:
    """Load and validate the canonical executable-path manifest."""
    manifest = root / MANIFEST_RELATIVE_PATH
    try:
        lines = manifest.read_text(encoding="utf-8").splitlines()
    except OSError as exc:
        raise RuntimeError(f"could not read {manifest}: {exc}") from exc

    paths: list[PurePosixPath] = []
    for line_number, raw_line in enumerate(lines, start=1):
        value = raw_line.split("#", 1)[0].strip()
        if not value:
            continue
        path = PurePosixPath(value)
        if path.is_absolute() or ".." in path.parts or path.as_posix() != value:
            raise RuntimeError(
                f"invalid executable path at {manifest}:{line_number}: {value!r}"
            )
        paths.append(path)

    if not paths or len(paths) != len(set(paths)):
        raise RuntimeError(f"{manifest} is empty or contains duplicate paths")
    return tuple(sorted(paths, key=lambda item: item.as_posix()))


def permission_errors(root: Path) -> list[str]:
    """Return missing/non-executable manifest entries."""
    errors: list[str] = []
    for relative in load_executable_paths(root):
        path = root / relative
        try:
            mode = path.lstat().st_mode
        except OSError as exc:
            errors.append(f"{relative}: {exc}")
            continue
        if not stat.S_ISREG(mode):
            errors.append(f"{relative}: not a regular file")
            continue
        if stat.S_IMODE(mode) != 0o755:
            errors.append(f"{relative}: mode {stat.S_IMODE(mode):04o}, expected 0755")
    return errors


def normalize_permissions(root: Path) -> tuple[PurePosixPath, ...]:
    """Set every manifest entry to mode 0755 and return the repaired paths."""
    repaired: list[PurePosixPath] = []
    for relative in load_executable_paths(root):
        path = root / relative
        try:
            mode = path.lstat().st_mode
        except OSError as exc:
            raise RuntimeError(f"could not inspect {relative}: {exc}") from exc
        if not stat.S_ISREG(mode):
            raise RuntimeError(f"refusing to chmod non-regular path: {relative}")
        if stat.S_IMODE(mode) == 0o755:
            continue
        try:
            os.chmod(path, 0o755, follow_symlinks=False)
        except OSError as exc:
            raise RuntimeError(
                f"could not restore executable permission on {relative}: {exc}"
            ) from exc
        repaired.append(relative)
    return tuple(repaired)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--fix", action="store_true", help="restore canonical modes")
    group.add_argument("--check", action="store_true", help="verify canonical modes")
    parser.add_argument(
        "--root",
        type=Path,
        default=Path(__file__).resolve().parents[1],
        help="source-tree root",
    )
    args = parser.parse_args(argv)
    root = args.root.resolve()

    try:
        if args.fix:
            repaired = normalize_permissions(root)
            errors = permission_errors(root)
            if errors:
                raise RuntimeError("; ".join(errors))
            if repaired:
                print("Restored executable permissions: " + ", ".join(map(str, repaired)))
            else:
                print("Executable permissions already canonical.")
            return 0

        errors = permission_errors(root)
        if errors:
            print("Executable permission check failed:", file=sys.stderr)
            print("\n".join(f"  {item}" for item in errors), file=sys.stderr)
            return 1
        print("Executable permissions are canonical.")
        return 0
    except RuntimeError as exc:
        print(f"normalize_permissions.py: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
