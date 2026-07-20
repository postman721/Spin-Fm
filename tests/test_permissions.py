from __future__ import annotations

import os
import runpy
import shutil
import stat
import subprocess
import sys
from pathlib import Path, PurePosixPath
from zipfile import ZipFile

ROOT = Path(__file__).resolve().parents[1]
PERMISSIONS = runpy.run_path(
    str(ROOT / "tools" / "normalize_permissions.py"),
    run_name="spin_fm_normalize_permissions",
)
SOURCE_ARCHIVE = runpy.run_path(
    str(ROOT / "tools" / "source_archive.py"),
    run_name="spin_fm_source_archive_permissions",
)

EXPECTED_EXECUTABLES = {
    PurePosixPath("bin/spin-fm"),
    PurePosixPath("debian/rules"),
    PurePosixPath("debian/tests/smoke"),
    PurePosixPath("main.py"),
    PurePosixPath("tools/check_syntax.py"),
    PurePosixPath("tools/normalize_permissions.py"),
    PurePosixPath("tools/source_archive.py"),
}


def _copy_release_tree(destination: Path) -> None:
    shutil.copytree(
        ROOT,
        destination,
        ignore=shutil.ignore_patterns(
            ".git",
            "__pycache__",
            ".pytest_cache",
            "*.pyc",
            "*.pyo",
            "build",
            "dist",
            "debian/.debhelper",
            "debian/spin-fm",
            "debian/tmp",
            "*.deb",
            "*.buildinfo",
            "*.changes",
            "spin-fm-*-source.zip",
        ),
    )


def test_executable_manifest_is_small_audited_and_complete() -> None:
    loaded = set(PERMISSIONS["load_executable_paths"](ROOT))
    assert loaded == EXPECTED_EXECUTABLES
    assert SOURCE_ARCHIVE["CANONICAL_EXECUTABLE_PATHS"] == frozenset(
        EXPECTED_EXECUTABLES
    )
    for relative in EXPECTED_EXECUTABLES:
        path = ROOT / relative
        assert path.is_file()
        assert stat.S_IMODE(path.stat().st_mode) == 0o755


def test_permission_repair_works_after_github_style_mode_loss(tmp_path: Path) -> None:
    source_root = tmp_path / "mode-stripped"
    _copy_release_tree(source_root)
    for relative in EXPECTED_EXECUTABLES:
        os.chmod(source_root / relative, 0o644)

    errors = PERMISSIONS["permission_errors"](source_root)
    assert len(errors) == len(EXPECTED_EXECUTABLES)

    result = subprocess.run(
        [
            sys.executable,
            "-B",
            source_root / "tools" / "normalize_permissions.py",
            "--fix",
            "--root",
            source_root,
        ],
        check=True,
        capture_output=True,
        text=True,
        timeout=20,
        env={**os.environ, "PYTHONDONTWRITEBYTECODE": "1"},
    )
    assert "Restored executable permissions" in result.stdout
    assert not PERMISSIONS["permission_errors"](source_root)
    for relative in EXPECTED_EXECUTABLES:
        assert stat.S_IMODE((source_root / relative).stat().st_mode) == 0o755


def test_source_zip_restores_modes_without_chmod_on_checkout(tmp_path: Path) -> None:
    source_root = tmp_path / "mode-stripped"
    _copy_release_tree(source_root)
    for relative in EXPECTED_EXECUTABLES:
        os.chmod(source_root / relative, 0o644)

    output = tmp_path / "source.zip"
    SOURCE_ARCHIVE["build_archive"](source_root, output)

    with ZipFile(output) as archive:
        members = {
            PurePosixPath(member.filename).relative_to("spin-fm-2.6.21"): stat.S_IMODE(
                member.external_attr >> 16
            )
            for member in archive.infolist()
        }
    for relative in EXPECTED_EXECUTABLES:
        assert members[relative] == 0o755
    assert members[PurePosixPath("README.md")] == 0o644


def test_make_permissions_target_is_interpreter_driven() -> None:
    makefile = (ROOT / "Makefile").read_text(encoding="utf-8")
    assert ".PHONY: all permissions check tests deb" in makefile
    assert (
        "permissions:\n\t@$(PYTHON) -B tools/normalize_permissions.py --fix" in makefile
    )
    assert "check: permissions" in makefile
    assert "tests: permissions" in makefile
    assert "deb: permissions" in makefile


def test_debian_docs_only_reference_shipped_files() -> None:
    docs = (ROOT / "debian" / "docs").read_text(encoding="utf-8").splitlines()
    assert docs == ["README.md", "CHANGELOG.md"]
    assert all((ROOT / relative).is_file() for relative in docs)
