#!/usr/bin/env python3
"""Compile project Python sources in memory without creating bytecode caches."""

from __future__ import annotations

import argparse
import sys
import tokenize
from pathlib import Path

# Keep direct invocations cache-free; Make and Debian additionally start Python
# with ``-B`` and PYTHONDONTWRITEBYTECODE=1.
sys.dont_write_bytecode = True

EXCLUDED_DIRECTORIES = frozenset(
    {
        ".git",
        ".hg",
        ".mypy_cache",
        ".nox",
        ".pytest_cache",
        ".svn",
        ".tox",
        ".venv",
        "__pycache__",
        "venv",
    }
)


def iter_python_files(root: Path):
    for path in sorted(root.rglob("*.py"), key=lambda item: item.as_posix()):
        parts = path.relative_to(root).parts
        if EXCLUDED_DIRECTORIES.intersection(parts) or any(
            part.endswith("_cache") for part in parts
        ):
            continue
        if path.is_file():
            yield path


def check_syntax(root: Path) -> list[str]:
    errors: list[str] = []
    for path in iter_python_files(root):
        try:
            with tokenize.open(path) as source_file:
                source = source_file.read()
            compile(source, str(path), "exec", dont_inherit=True)
        except (OSError, SyntaxError, UnicodeError) as exc:
            errors.append(f"{path}: {exc}")
    return errors


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "root",
        nargs="?",
        type=Path,
        default=Path(__file__).resolve().parents[1],
    )
    args = parser.parse_args(argv)
    root = args.root.resolve()
    errors = check_syntax(root)
    if errors:
        print("\n".join(errors), file=sys.stderr)
        return 1
    count = sum(1 for _ in iter_python_files(root))
    print(f"Syntax OK: {count} Python files checked without writing bytecode")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
