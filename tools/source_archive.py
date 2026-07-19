#!/usr/bin/env python3
"""Build, clean, and verify cache-free Spin FM source trees and archives.

Spin FM intentionally has no Python-index packaging layer. This helper creates
its supported source ZIP directly from the working tree, excludes local caches,
virtual environments, and generated build output even when the checkout is
dirty, and validates the completed archive before publishing it atomically.
"""

from __future__ import annotations

import argparse
import ast
import os
import shutil
import stat
import sys
import tempfile
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from pathlib import Path, PurePosixPath
from zipfile import ZIP_DEFLATED, BadZipFile, ZipFile, ZipInfo

# Keep this maintenance tool cache-free even when it is invoked without ``-B``.
# The supported Make and Debian paths also set PYTHONDONTWRITEBYTECODE before
# Python starts, which protects imports that happen before this module executes.
sys.dont_write_bytecode = True

CACHE_DIR_NAMES = frozenset(
    {
        "__pycache__",
        ".hypothesis",
        ".mypy_cache",
        ".nox",
        ".pyright",
        ".pytest_cache",
        ".pytype",
        ".tox",
        "htmlcov",
    }
)
CACHE_DIR_SUFFIXES = ("_cache",)
CACHE_FILE_NAMES = frozenset({".coverage", "coverage.xml"})
CACHE_FILE_PREFIXES = (".coverage.",)
CACHE_FILE_SUFFIXES = (".pyc", ".pyo")
VCS_DIR_NAMES = frozenset({".git", ".hg", ".svn"})
# Local environments are never archived or deleted wholesale. Their bytecode
# caches are still traversed and removed so a checkout can be genuinely
# cache-free at every depth.
PRESERVED_LOCAL_DIR_NAMES = frozenset({".venv", "venv"})
GENERATED_DIR_NAMES = frozenset({".eggs", "build", "dist", "pip-wheel-metadata"})
GENERATED_DIR_SUFFIXES = (".dist-info", ".egg-info")
FORBIDDEN_PYPI_FILES = frozenset(
    {"MANIFEST.in", "pyproject.toml", "setup.cfg", "setup.py"}
)
LEGACY_RELATIVE_PATHS = frozenset(
    {
        "src/spin_fm/__main__.py",
        "src/spin_fm/empty_trash.py",
        "ruff.toml",
    }
)
TRANSIENT_FILE_SUFFIXES = (".bak", ".orig", ".rej", ".swp")
GENERATED_DEBIAN_DIRS = frozenset(
    {
        "debian/.debhelper",
        "debian/spin-fm",
        "debian/tmp",
    }
)
GENERATED_FILE_SUFFIXES = (
    ".build",
    ".buildinfo",
    ".changes",
    ".deb",
    ".dsc",
    ".egg",
    ".whl",
)
RELEASE_ARCHIVE_SUFFIXES = (
    ".tar",
    ".tar.bz2",
    ".tar.gz",
    ".tar.xz",
    ".tbz2",
    ".tgz",
    ".txz",
    ".zip",
)
LICENSE_ID = "GPL-2.0-or-later"
LICENSE_MARKERS = {
    "LICENSE": f"SPDX-License-Identifier: {LICENSE_ID}",
    "README.md": f"Spin FM is {LICENSE_ID}",
    "debian/copyright": f"License: {LICENSE_ID}",
    "data/metainfo/net.techtimejourney.SpinFM.metainfo.xml": (
        f"<project_license>{LICENSE_ID}</project_license>"
    ),
}


def _is_cache_directory_name(name: str) -> bool:
    return name in CACHE_DIR_NAMES or name.endswith(CACHE_DIR_SUFFIXES)


def _is_cache_file_name(name: str) -> bool:
    return (
        name in CACHE_FILE_NAMES
        or name.startswith(CACHE_FILE_PREFIXES)
        or name.endswith(CACHE_FILE_SUFFIXES)
        or name.endswith("$py.class")
    )


def is_cache_artifact(relative_path: PurePosixPath) -> bool:
    """Return whether a project-relative path is a Python/tool cache."""
    return bool(
        any(_is_cache_directory_name(part) for part in relative_path.parts)
        or _is_cache_file_name(relative_path.name)
    )


def _is_release_archive_name(name: str) -> bool:
    lowered = name.lower()
    return lowered.startswith(
        ("spin-fm-", "spin-fm_", "spin_fm-", "spin_fm_")
    ) and lowered.endswith(RELEASE_ARCHIVE_SUFFIXES)


def _is_generated_directory_name(name: str) -> bool:
    return name in GENERATED_DIR_NAMES or name.endswith(GENERATED_DIR_SUFFIXES)


def _is_under(relative_path: PurePosixPath, parent: str) -> bool:
    parent_path = PurePosixPath(parent)
    return relative_path == parent_path or parent_path in relative_path.parents


def _is_legacy_artifact(relative_path: PurePosixPath) -> bool:
    """Return whether a path belongs to a retired or transient workflow."""
    name = relative_path.name
    return bool(
        relative_path.as_posix() in LEGACY_RELATIVE_PATHS
        or name in FORBIDDEN_PYPI_FILES
        or name.endswith(TRANSIENT_FILE_SUFFIXES)
        or name.endswith("~")
    )


def _is_generated_artifact(relative_path: PurePosixPath) -> bool:
    parts = relative_path.parts
    if VCS_DIR_NAMES.intersection(parts):
        return True
    if PRESERVED_LOCAL_DIR_NAMES.intersection(parts):
        return True
    if any(_is_generated_directory_name(part) for part in parts):
        return True
    if any(_is_under(relative_path, path) for path in GENERATED_DEBIAN_DIRS):
        return True

    name = relative_path.name
    if name == "files" and relative_path.parent == PurePosixPath("debian"):
        return True
    if name.endswith(".substvars") or ".debhelper" in name:
        return True
    return name.endswith(GENERATED_FILE_SUFFIXES) or _is_release_archive_name(name)


def is_excluded_artifact(relative_path: PurePosixPath) -> bool:
    """Return whether a path must not appear in a source release."""
    return bool(
        is_cache_artifact(relative_path)
        or _is_generated_artifact(relative_path)
        or _is_legacy_artifact(relative_path)
    )


def _version_from_source(root: Path) -> str:
    version_file = root / "src" / "spin_fm" / "__init__.py"
    try:
        tree = ast.parse(version_file.read_text(encoding="utf-8"), version_file.name)
    except (OSError, SyntaxError) as exc:
        raise RuntimeError(f"could not read the release version: {exc}") from exc

    for node in tree.body:
        if not isinstance(node, ast.Assign):
            continue
        if not any(
            isinstance(target, ast.Name) and target.id == "__version__"
            for target in node.targets
        ):
            continue
        if isinstance(node.value, ast.Constant) and isinstance(node.value.value, str):
            version = node.value.value.strip()
            if version:
                return version
    raise RuntimeError(f"__version__ was not found in {version_file}")


def _validate_project_layout(root: Path) -> None:
    missing = [
        str(path)
        for path in (
            root / "LICENSE",
            root / "main.py",
            root / "src" / "spin_fm" / "__init__.py",
        )
        if not path.is_file()
    ]
    if missing:
        raise RuntimeError(f"not a Spin FM source tree; missing: {', '.join(missing)}")

    forbidden: list[str] = []
    for current_root, directories, files in os.walk(root, topdown=True):
        current = Path(current_root)
        retained_directories: list[str] = []
        for directory in directories:
            if directory in VCS_DIR_NAMES or directory in PRESERVED_LOCAL_DIR_NAMES:
                continue
            relative = PurePosixPath((current / directory).relative_to(root).as_posix())
            if is_cache_artifact(relative) or _is_generated_artifact(relative):
                continue
            retained_directories.append(directory)
        directories[:] = retained_directories

        for file_name in files:
            relative = PurePosixPath((current / file_name).relative_to(root).as_posix())
            if _is_legacy_artifact(relative):
                forbidden.append(relative.as_posix())

    forbidden.sort()
    if forbidden:
        raise RuntimeError(
            "legacy or Python-index packaging files are not permitted: "
            + ", ".join(forbidden[:12])
        )

    inconsistent_license_files: list[str] = []
    for relative_name, marker in LICENSE_MARKERS.items():
        path = root / relative_name
        try:
            content = path.read_text(encoding="utf-8")
        except OSError:
            inconsistent_license_files.append(relative_name)
            continue
        if marker not in content or "GPL-2.0-only" in content:
            inconsistent_license_files.append(relative_name)
    if inconsistent_license_files:
        raise RuntimeError(
            f"license metadata must consistently use {LICENSE_ID}: "
            + ", ".join(inconsistent_license_files)
        )


def _release_datetime(root: Path) -> datetime:
    raw_epoch = os.environ.get("SOURCE_DATE_EPOCH", "").strip()
    if raw_epoch:
        try:
            return datetime.fromtimestamp(int(raw_epoch), tz=timezone.utc)
        except (OverflowError, ValueError) as exc:
            raise RuntimeError("SOURCE_DATE_EPOCH must be a valid integer") from exc

    changelog = root / "debian" / "changelog"
    try:
        lines = changelog.read_text(encoding="utf-8").splitlines()
    except OSError:
        lines = []
    for line in lines:
        if not line.startswith(" -- ") or "  " not in line:
            continue
        try:
            parsed = parsedate_to_datetime(line.rsplit("  ", 1)[1])
        except (TypeError, ValueError):
            continue
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=timezone.utc)
        return parsed.astimezone(timezone.utc)

    # A stable, ZIP-compatible fallback rather than the wall clock keeps output
    # reproducible even in a source tree without Debian metadata.
    return datetime(1980, 1, 1, tzinfo=timezone.utc)


def _zip_datetime(value: datetime) -> tuple[int, int, int, int, int, int]:
    value = value.astimezone(timezone.utc)
    year = min(2107, max(1980, value.year))
    # ZIP stores seconds in two-second increments.
    second = value.second - (value.second % 2)
    return (year, value.month, value.day, value.hour, value.minute, second)


def _iter_source_entries(
    root: Path,
    *,
    excluded_paths: frozenset[Path] = frozenset(),
):
    """Yield source entries in stable order while pruning ignored subtrees."""
    excluded_resolved: set[Path] = set()
    for path in excluded_paths:
        try:
            excluded_resolved.add(path.resolve())
        except OSError:
            excluded_resolved.add(path.absolute())

    for current_root, directories, files in os.walk(root, topdown=True):
        current = Path(current_root)
        directories.sort()
        files.sort()

        retained_directories: list[str] = []
        for directory in directories:
            path = current / directory
            relative = PurePosixPath(path.relative_to(root).as_posix())
            if is_excluded_artifact(relative):
                continue
            if path.is_symlink():
                yield path, relative
                continue
            retained_directories.append(directory)
        directories[:] = retained_directories

        for file_name in files:
            path = current / file_name
            try:
                path_resolved = path.resolve()
            except OSError:
                path_resolved = path.absolute()
            if path_resolved in excluded_resolved:
                continue

            relative = PurePosixPath(path.relative_to(root).as_posix())
            if _is_legacy_artifact(relative):
                raise RuntimeError(
                    "legacy or Python-index packaging files are not permitted: "
                    + relative.as_posix()
                )
            if is_excluded_artifact(relative):
                continue
            yield path, relative


def _write_entry(
    archive: ZipFile,
    path: Path,
    archive_name: PurePosixPath,
    timestamp: tuple[int, int, int, int, int, int],
) -> None:
    info = ZipInfo(archive_name.as_posix(), date_time=timestamp)
    info.create_system = 3
    info.compress_type = ZIP_DEFLATED

    file_stat = path.lstat()
    if stat.S_ISLNK(file_stat.st_mode):
        data = os.readlink(path).encode("utf-8")
        mode = stat.S_IFLNK | 0o777
    elif stat.S_ISREG(file_stat.st_mode):
        data = path.read_bytes()
        # Git only tracks the executable bit. Normalize all other permission
        # bits so archives remain reproducible across different checkout
        # umasks, shared repositories, and build users.
        permissions = 0o755 if file_stat.st_mode & 0o111 else 0o644
        mode = stat.S_IFREG | permissions
    else:
        raise RuntimeError(f"unsupported source entry type: {path}")

    info.external_attr = mode << 16
    archive.writestr(info, data, compress_type=ZIP_DEFLATED, compresslevel=9)


def verify_archive(archive_path: Path) -> tuple[int, int]:
    """Validate an archive and return ``(member_count, uncompressed_bytes)``."""
    try:
        with ZipFile(archive_path) as archive:
            bad_crc = archive.testzip()
            if bad_crc:
                raise RuntimeError(f"archive CRC check failed for {bad_crc}")

            names = archive.namelist()
            if not all(names):
                raise RuntimeError("archive contains an empty member name")
            if names != sorted(names):
                raise RuntimeError("archive members are not in canonical order")
            if len(names) != len(set(names)):
                raise RuntimeError("archive contains duplicate member names")
            if not names:
                raise RuntimeError("archive is empty")

            member_paths = [PurePosixPath(name) for name in names if name]
            unsafe = [
                name
                for name, member_path in zip(names, member_paths, strict=False)
                if member_path.is_absolute() or ".." in member_path.parts
            ]
            if unsafe:
                raise RuntimeError(
                    "archive contains unsafe member paths: " + ", ".join(unsafe[:8])
                )

            roots = {member_path.parts[0] for member_path in member_paths}
            if len(roots) != 1:
                raise RuntimeError("archive must have exactly one top-level directory")
            root_name = next(iter(roots))

            project_paths = [
                PurePosixPath(*member_path.parts[1:]) for member_path in member_paths
            ]
            bad_cache = [
                name
                for name, project_path in zip(names, project_paths, strict=False)
                if is_cache_artifact(project_path)
            ]
            if bad_cache:
                raise RuntimeError(
                    "archive contains cache artifacts: " + ", ".join(bad_cache[:8])
                )

            bad_generated = [
                name
                for name, project_path in zip(names, project_paths, strict=False)
                if _is_generated_artifact(project_path)
            ]
            if bad_generated:
                raise RuntimeError(
                    "archive contains generated/local artifacts: "
                    + ", ".join(bad_generated[:8])
                )

            bad_pypi = [
                name
                for name, project_path in zip(names, project_paths, strict=False)
                if project_path.name in FORBIDDEN_PYPI_FILES
            ]
            if bad_pypi:
                raise RuntimeError(
                    "archive contains Python-index packaging metadata: "
                    + ", ".join(bad_pypi)
                )

            bad_legacy = [
                name
                for name, project_path in zip(names, project_paths, strict=False)
                if _is_legacy_artifact(project_path)
            ]
            if bad_legacy:
                raise RuntimeError(
                    "archive contains legacy/transient artifacts: "
                    + ", ".join(bad_legacy[:8])
                )

            required = {
                f"{root_name}/LICENSE",
                f"{root_name}/main.py",
                f"{root_name}/src/spin_fm/__init__.py",
            }
            missing = sorted(required.difference(names))
            if missing:
                raise RuntimeError(
                    "archive is missing required application files: "
                    + ", ".join(missing)
                )

            bad_modes: list[str] = []
            for member in archive.infolist():
                mode = member.external_attr >> 16
                permissions = stat.S_IMODE(mode)
                if stat.S_ISREG(mode):
                    if permissions not in {0o644, 0o755}:
                        bad_modes.append(f"{member.filename} ({permissions:o})")
                elif stat.S_ISLNK(mode):
                    if permissions != 0o777:
                        bad_modes.append(f"{member.filename} ({permissions:o})")
                else:
                    bad_modes.append(f"{member.filename} (unsupported type)")
            if bad_modes:
                raise RuntimeError(
                    "archive contains non-canonical Unix permissions: "
                    + ", ".join(bad_modes[:8])
                )

            total_size = sum(member.file_size for member in archive.infolist())
            return len(names), total_size
    except (BadZipFile, OSError) as exc:
        raise RuntimeError(f"could not verify {archive_path}: {exc}") from exc


def build_archive(root: Path, output: Path) -> tuple[int, int]:
    """Build a deterministic, cache-free source ZIP and verify it."""
    root = root.resolve()
    output = output.resolve()
    _validate_project_layout(root)
    version = _version_from_source(root)
    prefix = PurePosixPath(f"spin-fm-{version}")
    timestamp = _zip_datetime(_release_datetime(root))

    output.parent.mkdir(parents=True, exist_ok=True)
    temporary_path: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(
            dir=output.parent,
            prefix=f".{output.name}.",
            suffix=".tmp",
            delete=False,
        ) as temporary:
            temporary_path = Path(temporary.name)

        with ZipFile(
            temporary_path, "w", compression=ZIP_DEFLATED, compresslevel=9
        ) as archive:
            excluded_paths = frozenset({output, temporary_path})
            entries = sorted(
                _iter_source_entries(root, excluded_paths=excluded_paths),
                key=lambda item: item[1].as_posix(),
            )
            for path, relative in entries:
                _write_entry(archive, path, prefix / relative, timestamp)

        counts = verify_archive(temporary_path)
        # NamedTemporaryFile is private by default. Publish source releases with
        # ordinary read permissions so they behave like normal distribution
        # artifacts after the atomic replacement.
        temporary_path.chmod(0o644)
        os.replace(temporary_path, output)
        temporary_path = None
        return counts
    finally:
        if temporary_path is not None:
            temporary_path.unlink(missing_ok=True)


def _remove_directory(path: Path) -> None:
    if path.is_symlink():
        path.unlink(missing_ok=True)
    else:
        shutil.rmtree(path, ignore_errors=False)


def _is_cleanable_generated_file(name: str) -> bool:
    if (
        _is_cache_file_name(name)
        or name in FORBIDDEN_PYPI_FILES
        or name.endswith((".egg", ".whl") + TRANSIENT_FILE_SUFFIXES)
        or name.endswith("~")
    ):
        return True
    lowered = name.lower()
    return lowered.startswith(
        ("spin-fm-", "spin-fm_", "spin_fm-", "spin_fm_")
    ) and lowered.endswith(RELEASE_ARCHIVE_SUFFIXES)


def clean_tree(root: Path) -> list[Path]:
    """Remove project caches and obsolete build artifacts recursively.

    Local virtual environments are preserved, but caches inside them are
    removed. VCS internals are left untouched. Both are excluded from every
    source archive.
    """
    root = root.resolve()
    removed: list[Path] = []

    for current_root, directories, files in os.walk(root, topdown=True):
        current = Path(current_root)
        current_relative = current.relative_to(root)
        inside_preserved_local_directory = bool(
            PRESERVED_LOCAL_DIR_NAMES.intersection(current_relative.parts)
        )
        retained_directories: list[str] = []
        for directory in directories:
            if directory in VCS_DIR_NAMES:
                continue
            target = current / directory
            relative = PurePosixPath(target.relative_to(root).as_posix())
            if _is_cache_directory_name(directory):
                _remove_directory(target)
                removed.append(target)
                continue
            if (
                not inside_preserved_local_directory
                and directory not in PRESERVED_LOCAL_DIR_NAMES
                and (
                    _is_generated_directory_name(directory)
                    or any(_is_under(relative, path) for path in GENERATED_DEBIAN_DIRS)
                )
            ):
                _remove_directory(target)
                removed.append(target)
                continue
            retained_directories.append(directory)
        directories[:] = retained_directories

        for file_name in files:
            target = current / file_name
            if _is_cache_file_name(file_name):
                target.unlink(missing_ok=True)
                removed.append(target)
                continue
            if inside_preserved_local_directory:
                continue
            relative = PurePosixPath(target.relative_to(root).as_posix())
            is_generated_debian_file = (
                bool(
                    file_name == "files" and relative.parent == PurePosixPath("debian")
                )
                or file_name.endswith(".substvars")
                or ".debhelper" in file_name
            )
            if not (
                _is_cleanable_generated_file(file_name)
                or relative.as_posix() in LEGACY_RELATIVE_PATHS
                or is_generated_debian_file
                or file_name.endswith(GENERATED_FILE_SUFFIXES)
            ):
                continue
            target.unlink(missing_ok=True)
            removed.append(target)

    return removed


def find_cache_artifacts(root: Path) -> list[Path]:
    """Return cache artifacts at every checkout depth outside VCS internals."""
    root = root.resolve()
    found: list[Path] = []

    for current_root, directories, files in os.walk(root, topdown=True):
        current = Path(current_root)
        retained_directories: list[str] = []
        for directory in directories:
            if directory in VCS_DIR_NAMES:
                continue
            target = current / directory
            if _is_cache_directory_name(directory):
                found.append(target)
                continue
            retained_directories.append(directory)
        directories[:] = retained_directories

        found.extend(current / name for name in files if _is_cache_file_name(name))

    return sorted(found)


def assert_cache_free(root: Path) -> None:
    caches = find_cache_artifacts(root)
    if not caches:
        return
    preview = ", ".join(str(path.relative_to(root)) for path in caches[:12])
    extra = "" if len(caches) <= 12 else f" (+{len(caches) - 12} more)"
    raise RuntimeError(f"source tree contains cache artifacts: {preview}{extra}")


def find_release_artifacts(root: Path) -> list[Path]:
    """Return generated, cache, packaging, and legacy release blockers.

    VCS metadata and local virtual environments are intentionally outside the
    project-controlled release surface. They are preserved locally and always
    excluded from source archives.
    """
    root = root.resolve()
    found: list[Path] = []

    for current_root, directories, files in os.walk(root, topdown=True):
        current = Path(current_root)
        retained_directories: list[str] = []
        for directory in directories:
            if directory in VCS_DIR_NAMES or directory in PRESERVED_LOCAL_DIR_NAMES:
                continue
            target = current / directory
            relative = PurePosixPath(target.relative_to(root).as_posix())
            if is_cache_artifact(relative) or _is_generated_artifact(relative):
                found.append(target)
                continue
            retained_directories.append(directory)
        directories[:] = retained_directories

        for file_name in files:
            target = current / file_name
            relative = PurePosixPath(target.relative_to(root).as_posix())
            if is_excluded_artifact(relative):
                found.append(target)

    return sorted(set(found))


def assert_release_clean(root: Path) -> None:
    """Fail unless the project-controlled source tree is release-ready."""
    blockers = sorted(set(find_cache_artifacts(root) + find_release_artifacts(root)))
    if not blockers:
        return
    preview = ", ".join(str(path.relative_to(root)) for path in blockers[:12])
    extra = "" if len(blockers) <= 12 else f" (+{len(blockers) - 12} more)"
    raise RuntimeError(f"source tree contains release artifacts: {preview}{extra}")


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--root",
        type=Path,
        default=Path(__file__).resolve().parents[1],
        help="source tree root (default: repository root)",
    )
    parser.add_argument("--output", type=Path, help="output ZIP path")
    parser.add_argument(
        "--clean",
        action="store_true",
        help="remove caches/obsolete build output before creating the archive",
    )
    action = parser.add_mutually_exclusive_group()
    action.add_argument(
        "--clean-only",
        action="store_true",
        help="remove caches/obsolete build output and exit",
    )
    action.add_argument(
        "--check-clean",
        action="store_true",
        help="fail when the project tree contains cache artifacts",
    )
    action.add_argument(
        "--check-release",
        action="store_true",
        help="fail on caches, generated output, packaging metadata, or legacy files",
    )
    action.add_argument("--verify", type=Path, help="verify an existing source ZIP")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    try:
        if args.verify is not None:
            members, total_size = verify_archive(args.verify.resolve())
            print(
                f"Verified {args.verify}: {members} members, "
                f"{total_size} uncompressed bytes"
            )
            return 0

        root = args.root.resolve()
        if args.clean or args.clean_only:
            removed = clean_tree(root)
            print(f"Removed {len(removed)} cache/build artifact(s) from {root}")
        if args.clean_only:
            return 0
        _validate_project_layout(root)
        if args.check_clean:
            assert_cache_free(root)
            print(f"Cache-free source tree: {root}")
            return 0
        if args.check_release:
            assert_release_clean(root)
            print(f"Release-clean source tree: {root}")
            return 0

        version = _version_from_source(root)
        output = (
            args.output.resolve()
            if args.output is not None
            else root.parent / f"spin-fm-{version}-source.zip"
        )
        members, total_size = build_archive(root, output)
        print(f"Created {output}: {members} members, {total_size} uncompressed bytes")
        return 0
    except RuntimeError as exc:
        print(f"source_archive.py: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
