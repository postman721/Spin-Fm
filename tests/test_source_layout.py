from __future__ import annotations

import ast
import os
import re
import runpy
import shutil
import stat
import subprocess
import sys
from pathlib import Path, PurePosixPath
from types import SimpleNamespace
from zipfile import ZIP_DEFLATED, ZipFile

import pytest

ROOT = Path(__file__).resolve().parents[1]
_SOURCE_ARCHIVE = runpy.run_path(
    str(ROOT / "tools" / "source_archive.py"),
    run_name="spin_fm_source_archive",
)
CACHE_DIRECTORY_NAMES = {
    "__pycache__",
    ".hypothesis",
    ".mypy_cache",
    ".nox",
    ".pyright",
    ".pytest_cache",
    ".pytype",
    ".ruff_cache",
    ".tox",
    "htmlcov",
}
LOCAL_GENERATED_DIRECTORY_NAMES = {
    ".eggs",
    ".venv",
    "build",
    "dist",
    "pip-wheel-metadata",
    "venv",
}
CACHE_DIRECTORY_SUFFIXES = ("_cache",)
CACHE_SUFFIXES = (".pyc", ".pyo")
GENERATED_DIRECTORY_SUFFIXES = (".dist-info", ".egg-info")
GENERATED_FILE_SUFFIXES = (".egg", ".whl")
PYPI_METADATA = {"MANIFEST.in", "pyproject.toml", "setup.cfg", "setup.py"}
LEGACY_RELATIVE_PATHS = {
    "ruff.toml",
    "src/spin_fm/__main__.py",
    "src/spin_fm/empty_trash.py",
}
TRANSIENT_SUFFIXES = (".bak", ".orig", ".rej", ".swp")


def _copy_source_tree(destination: Path) -> None:
    shutil.copytree(
        ROOT,
        destination,
        ignore=shutil.ignore_patterns(
            *CACHE_DIRECTORY_NAMES,
            *LOCAL_GENERATED_DIRECTORY_NAMES,
            "*.pyc",
            "*.pyo",
            "*$py.class",
            "*.egg",
            "*.egg-info",
            "*.dist-info",
            "*.whl",
            "*.orig",
            "*.rej",
            "*.bak",
            "*~",
            "spin-fm-*-source.zip",
            "spin_fm-*.tar*",
        ),
    )


def _is_excluded_member(name: str) -> bool:
    path = PurePosixPath(name)
    return bool(
        any(
            part in CACHE_DIRECTORY_NAMES or part.endswith(CACHE_DIRECTORY_SUFFIXES)
            for part in path.parts
        )
        or LOCAL_GENERATED_DIRECTORY_NAMES.intersection(path.parts)
        or any(part.endswith(GENERATED_DIRECTORY_SUFFIXES) for part in path.parts)
        or path.name in {".coverage", "coverage.xml"}
        or path.name.startswith(".coverage.")
        or path.name.endswith(CACHE_SUFFIXES)
        or path.name.endswith("$py.class")
        or path.name.endswith(GENERATED_FILE_SUFFIXES)
        or path.name in PYPI_METADATA
        or any(
            path.as_posix().endswith(relative_path)
            for relative_path in LEGACY_RELATIVE_PATHS
        )
        or path.name.endswith(TRANSIENT_SUFFIXES)
        or path.name.endswith("~")
        or "/debian/tmp/" in f"/{path.as_posix()}/"
        or "/debian/spin-fm/" in f"/{path.as_posix()}/"
        or path.name.startswith(("spin_fm-", "spin-fm-"))
        and path.name.endswith((".tar", ".tar.gz", ".tar.xz", ".zip"))
    )


def _cache_paths(root: Path) -> list[Path]:
    return [
        path
        for path in root.rglob("*")
        if path.name in CACHE_DIRECTORY_NAMES
        or path.name.endswith(CACHE_DIRECTORY_SUFFIXES)
        or path.name in {".coverage", "coverage.xml"}
        or path.name.startswith(".coverage.")
        or path.name.endswith(CACHE_SUFFIXES)
        or path.name.endswith("$py.class")
    ]


def _subprocess_environment() -> dict[str, str]:
    environment = dict(os.environ)
    environment.pop("PYTHONPYCACHEPREFIX", None)
    environment.pop("PYTHONDONTWRITEBYTECODE", None)
    return environment


def test_pypi_build_metadata_and_module_packaging_entry_are_absent() -> None:
    for relative_path in PYPI_METADATA:
        assert not (ROOT / relative_path).exists()

    assert not (ROOT / "src" / "spin_fm" / "__main__.py").exists()
    assert not (ROOT / "src" / "spin_fm" / "empty_trash.py").exists()
    assert (ROOT / "pytest.ini").is_file()
    assert not (ROOT / "ruff.toml").exists()
    assert (ROOT / "Makefile").is_file()
    assert (ROOT / "tools" / "source_archive.py").is_file()

    metainfo = (
        ROOT / "data" / "metainfo" / "net.techtimejourney.SpinFM.metainfo.xml"
    ).read_text(encoding="utf-8")
    assert '<release version="2.6.22" date="2026-07-20">' in metainfo

    desktop = (
        ROOT / "data" / "applications" / "net.techtimejourney.SpinFM.desktop"
    ).read_text(encoding="utf-8")
    assert "\nTryExec=spin-fm\n" in desktop
    assert "\nExec=spin-fm %U\n" in desktop


def test_license_metadata_is_gpl_2_or_later_everywhere() -> None:
    license_text = (ROOT / "LICENSE").read_text(encoding="utf-8")
    readme = (ROOT / "README.md").read_text(encoding="utf-8")
    copyright_text = (ROOT / "debian" / "copyright").read_text(encoding="utf-8")
    metainfo = (
        ROOT / "data" / "metainfo" / "net.techtimejourney.SpinFM.metainfo.xml"
    ).read_text(encoding="utf-8")
    manpage = (ROOT / "data" / "man" / "spin-fm.1").read_text(encoding="utf-8")

    assert "SPDX-License-Identifier: GPL-2.0-or-later" in license_text
    assert "either version 2 of the License" in license_text
    assert "or (at your option) any later" in license_text
    assert "Spin FM is GPL-2.0-or-later" in readme
    assert "License: GPL-2.0-or-later" in copyright_text
    assert "<project_license>GPL-2.0-or-later</project_license>" in metainfo
    assert "GNU General Public License version 2 or later." in manpage

    combined = "\n".join((readme, copyright_text, metainfo, manpage))
    assert "GPL-2.0-only" not in combined


def test_alt_p_shortcut_and_direct_osd_wiring_are_present() -> None:
    main_window_path = ROOT / "src" / "spin_fm" / "main_window.py"
    main_window = main_window_path.read_text(encoding="utf-8")
    assert 'self.play_pause_action.setShortcut("Alt+P")' in main_window
    assert "self.play_pause_action.setShortcutContext(Qt.WindowShortcut)" in main_window
    assert (
        "self.play_pause_action.triggered.connect(self.toggle_audio_playback)"
        in main_window
    )
    assert "application.installEventFilter(self)" in main_window
    assert "QEvent.ShortcutOverride" in main_window
    assert "QEvent.KeyPress" in main_window

    audio_player_path = ROOT / "src" / "spin_fm" / "audio_player.py"
    module = ast.parse(
        audio_player_path.read_text(encoding="utf-8"),
        filename=str(audio_player_path),
    )
    methods = {
        node.name: node
        for node in ast.walk(module)
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
    }
    toggle = methods["toggle_playback"]
    commit = methods["_commit_playback_request"]
    toggle_calls = {
        call.func.attr
        for call in ast.walk(toggle)
        if isinstance(call, ast.Call) and isinstance(call.func, ast.Attribute)
    }
    commit_calls = {
        call.func.attr
        for call in ast.walk(commit)
        if isinstance(call, ast.Call) and isinstance(call.func, ast.Attribute)
    }
    assert {"pause", "play"}.issubset(toggle_calls)
    assert {
        "_cancel_pending_osd_notifications",
        "_notify_osd_media",
        "_set_state_text",
        "_update_play_icon",
        "set_playback_status",
    }.issubset(commit_calls)
    assert {"Playing", "Paused"}.issubset(
        {
            node.value
            for node in ast.walk(commit)
            if isinstance(node, ast.Constant) and isinstance(node.value, str)
        }
    )


def test_audio_shortcut_matcher_executes_without_qt_runtime() -> None:
    main_window_path = ROOT / "src" / "spin_fm" / "main_window.py"
    module = ast.parse(
        main_window_path.read_text(encoding="utf-8"),
        filename=str(main_window_path),
    )
    window_class = next(
        node
        for node in module.body
        if isinstance(node, ast.ClassDef) and node.name == "MainWindow"
    )
    matcher = next(
        node
        for node in window_class.body
        if isinstance(node, ast.FunctionDef) and node.name == "_audio_shortcut_command"
    )
    matcher.decorator_list = []
    standalone = ast.Module(body=[matcher], type_ignores=[])
    ast.fix_missing_locations(standalone)

    class FakeQt:
        AltModifier = 1
        ControlModifier = 2
        ShiftModifier = 4
        MetaModifier = 8
        Key_P = 80
        Key_M = 77

    class FakeQEvent:
        ShortcutOverride = 1
        KeyPress = 2

    namespace: dict[str, object] = {"Qt": FakeQt, "QEvent": FakeQEvent}
    exec(compile(standalone, str(main_window_path), "exec"), namespace)
    match = namespace["_audio_shortcut_command"]

    class Event:
        def __init__(self, event_type: int, key: int, modifiers: int) -> None:
            self._type = event_type
            self._key = key
            self._modifiers = modifiers

        def type(self) -> int:
            return self._type

        def key(self) -> int:
            return self._key

        def modifiers(self) -> int:
            return self._modifiers

    assert match(Event(FakeQEvent.KeyPress, FakeQt.Key_P, FakeQt.AltModifier)) == (
        "play_pause"
    )
    assert (
        match(Event(FakeQEvent.ShortcutOverride, FakeQt.Key_M, FakeQt.AltModifier))
        == "mute"
    )
    assert (
        match(
            Event(
                FakeQEvent.KeyPress,
                FakeQt.Key_P,
                FakeQt.AltModifier | FakeQt.ControlModifier,
            )
        )
        is None
    )


def test_toggle_playback_logic_executes_without_qt_runtime() -> None:
    """Exercise the exact shared button/Alt+P state path without a Qt runtime."""
    audio_player_path = ROOT / "src" / "spin_fm" / "audio_player.py"
    module = ast.parse(
        audio_player_path.read_text(encoding="utf-8"),
        filename=str(audio_player_path),
    )
    player_class = next(
        node
        for node in module.body
        if isinstance(node, ast.ClassDef) and node.name == "AudioPlayerWidget"
    )
    method_names = {"play", "pause", "toggle_playback", "_commit_playback_request"}
    selected = [
        node
        for node in player_class.body
        if isinstance(node, ast.FunctionDef) and node.name in method_names
    ]
    standalone = ast.Module(body=selected, type_ignores=[])
    ast.fix_missing_locations(standalone)
    namespace: dict[str, object] = {}
    exec(compile(standalone, str(audio_player_path), "exec"), namespace)

    class FakeBackend:
        def __init__(self, owner) -> None:
            self.owner = owner

        def pause(self) -> None:
            self.owner.pause_calls += 1

        def play(self) -> None:
            self.owner.play_calls += 1

        def setPosition(self, value: int) -> None:  # noqa: N802 - Qt API shape
            self.owner._position = int(value)

    class FakeMpris:
        def __init__(self) -> None:
            self.statuses: list[tuple[str, bool]] = []
            self.seeked: list[int] = []

        def set_playback_status(self, status: str, *, force: bool = False) -> None:
            self.statuses.append((status, force))

        def emit_seeked(self, position: int) -> None:
            self.seeked.append(position)

    class FakeWidget:
        play = namespace["play"]
        pause = namespace["pause"]
        toggle_playback = namespace["toggle_playback"]
        _commit_playback_request = namespace["_commit_playback_request"]

        def __init__(self) -> None:
            self._current_path = "/tmp/sample.ogg"
            self._track_name = "sample.ogg"
            self._duration = 60_000
            self._position = 12_000
            self._playback_requested = True
            self._player = FakeBackend(self)
            self._mpris = FakeMpris()
            self.status_message = SimpleNamespace(messages=[], emit=self._emit)
            self.states: list[str] = []
            self.icons: list[bool] = []
            self.osd: list[str] = []
            self.cancel_count = 0
            self.pause_calls = 0
            self.play_calls = 0

        def _emit(self, message: str) -> None:
            self.status_message.messages.append(message)

        def _is_playing(self) -> bool:
            return self._playback_requested

        def current_position(self) -> int:
            return self._position

        def _cancel_pending_osd_notifications(self) -> None:
            self.cancel_count += 1

        def _set_state_text(self, text: str) -> None:
            self.states.append(text)

        def _update_play_icon(self, *, playing: bool) -> None:
            self.icons.append(playing)

        def _notify_osd_media(self, heading: str) -> None:
            self.osd.append(heading)

    widget = FakeWidget()
    assert widget.toggle_playback() is True
    assert widget.pause_calls == 1
    assert widget._playback_requested is False
    assert widget.osd[-1] == "Paused"
    assert widget._mpris.statuses[-1] == ("Paused", True)
    assert widget.states[-1] == "Paused"
    assert widget.icons[-1] is False
    assert widget.status_message.messages[-1] == "Paused sample.ogg"

    # No backend state signal is emitted. The accepted state still makes the
    # second invocation play rather than pausing twice.
    assert widget.toggle_playback() is True
    assert widget.play_calls == 1
    assert widget._playback_requested is True
    assert widget.osd[-1] == "Playing"
    assert widget._mpris.statuses[-1] == ("Playing", True)
    assert widget.states[-1] == "Playing"
    assert widget.icons[-1] is True
    assert widget.status_message.messages[-1] == "Playing sample.ogg"
    assert widget.cancel_count == 2


def test_source_launcher_reports_the_release_version() -> None:
    result = subprocess.run(
        [sys.executable, "main.py", "--version"],
        cwd=ROOT,
        check=True,
        capture_output=True,
        text=True,
        timeout=10,
        env=_subprocess_environment(),
    )
    assert result.stdout.strip() == "Spin FM 2.6.22"
    assert result.stderr == ""


def test_direct_install_layout_uses_the_same_sources(tmp_path: Path) -> None:
    install_root = tmp_path / "spin-fm"
    install_root.mkdir()
    shutil.copy2(ROOT / "main.py", install_root / "main.py")
    shutil.copytree(
        ROOT / "src",
        install_root / "src",
        ignore=shutil.ignore_patterns("__pycache__", "*.pyc", "*.pyo"),
    )

    result = subprocess.run(
        [sys.executable, install_root / "main.py", "--version"],
        check=True,
        capture_output=True,
        text=True,
        timeout=10,
        env=_subprocess_environment(),
    )
    assert result.stdout.strip() == "Spin FM 2.6.22"


def test_supported_launchers_do_not_write_bytecode(tmp_path: Path) -> None:
    install_root = tmp_path / "spin-fm"
    install_root.mkdir()
    shutil.copy2(ROOT / "main.py", install_root / "main.py")
    shutil.copytree(
        ROOT / "src",
        install_root / "src",
        ignore=shutil.ignore_patterns("__pycache__", "*.pyc", "*.pyo"),
    )

    environment = _subprocess_environment()
    for command, cwd in (
        ([sys.executable, install_root / "main.py", "--version"], tmp_path),
        ([ROOT / "bin" / "spin-fm", "--version"], ROOT),
    ):
        subprocess.run(
            command,
            cwd=cwd,
            check=True,
            capture_output=True,
            text=True,
            timeout=10,
            env=environment,
        )

    assert not _cache_paths(install_root)


def test_debian_rules_do_not_invoke_python_package_builders() -> None:
    control = (ROOT / "debian" / "control").read_text(encoding="utf-8")
    rules = (ROOT / "debian" / "rules").read_text(encoding="utf-8")
    packaging_text = f"{control}\n{rules}".lower()
    assert "Priority:" not in control
    for forbidden in (
        "pybuild",
        "setuptools",
        "pep 517",
        "python3 -m build",
        "dh-sequence-python3",
        "python3-all",
        "${python3:depends}",
    ):
        assert forbidden not in packaging_text

    # The repository Makefile is for development/release automation. Debian
    # must not auto-run it as an upstream build or install system.
    assert "override_dh_auto_configure:" in rules
    assert "override_dh_auto_build:" in rules
    assert "override_dh_auto_install:" in rules
    assert "execute_after_dh_install:" in rules
    assert "ruff" not in control.lower()
    assert "override_dh_auto_test:\n\t@:" in rules


def test_cache_exclusion_is_declared_for_every_distribution_path() -> None:
    gitignore = (ROOT / ".gitignore").read_text(encoding="utf-8")
    attributes = (ROOT / ".gitattributes").read_text(encoding="utf-8")
    source_options = (ROOT / "debian/source/options").read_text(encoding="utf-8")
    rules = (ROOT / "debian/rules").read_text(encoding="utf-8")
    smoke = (ROOT / "debian/tests/smoke").read_text(encoding="utf-8")
    makefile = (ROOT / "Makefile").read_text(encoding="utf-8")
    pytest_config = (ROOT / "pytest.ini").read_text(encoding="utf-8")
    launcher = (ROOT / "bin/spin-fm").read_text(encoding="utf-8")

    for marker in (
        "__pycache__/",
        "*.pyc",
        "*.pyo",
        "*$py.class",
        ".*_cache/",
        ".pyright/",
        ".pytype/",
        ".venv/",
        "build/",
        "dist/",
        "*.egg-info/",
        "*.dist-info/",
        "*.whl",
    ):
        assert marker in gitignore, f"missing {marker!r} from .gitignore"
    for marker in (
        "__pycache__",
        "*.pyc",
        "*.pyo",
        "*$py.class",
        ".*_cache",
        ".pyright",
        ".pytype",
        ".venv",
        "build",
        "dist",
        "*.egg-info",
        "*.dist-info",
        "*.whl",
        "debian/tmp",
        "debian/files",
        "*.deb",
        "*.dsc",
    ):
        assert marker in attributes, f"missing {marker!r} from .gitattributes"
        assert marker in source_options, (
            f"missing {marker!r} from debian/source/options"
        )

    assert "PYTHONDONTWRITEBYTECODE=1" in rules
    assert "override_dh_auto_test:\n\t@:" in rules
    assert "-X__pycache__" in rules
    assert "-X.pyc" in rules
    assert "-X.pyo" in rules
    assert "-X.egg-info" in rules
    assert "--clean-only" in rules
    assert "PYTHONDONTWRITEBYTECODE := 1" in makefile
    assert ".NOTPARALLEL:" in makefile
    assert "--check-clean" in makefile
    assert "--check-release" in makefile
    assert "-m pytest" in makefile
    assert ".PHONY: all permissions check tests deb" in makefile
    assert "dpkg-buildpackage" in makefile
    assert "dpkg-checkbuilddeps" in makefile
    for retired in ("deb-binary:", "deb-source:", "deb-release:", "lint:"):
        assert retired not in makefile
    assert "-p no:cacheprovider" in pytest_config
    assert "--assert=plain" in pytest_config
    assert (ROOT / "tests" / "conftest.py").is_file()
    assert "PYTHONDONTWRITEBYTECODE=1" in launcher
    assert "python3 -B" in launcher
    assert "PYTHONDONTWRITEBYTECODE=1" in smoke
    assert smoke.count("python3 -B") == 3
    assert "__pycache__" in smoke
    assert "dh_missing --fail-missing" in rules


def test_source_archive_is_deterministic_and_excludes_dirty_tree_artifacts(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    source_root = tmp_path / "spin-fm-source"
    _copy_source_tree(source_root)

    artifacts = {
        "bytecode": source_root / "src" / "spin_fm" / "__pycache__" / "module.pyc",
        "optimized_bytecode": source_root / "tests" / "helper.pyo",
        "jython_bytecode": source_root / "tests" / "helper$py.class",
        "pytest": source_root / ".pytest_cache" / "v" / "cache" / "nodeids",
        "tool_cache": source_root / ".tool_cache" / "content",
        "mypy": source_root / "tests" / ".mypy_cache" / "cache.json",
        "pyright": source_root / "tests" / ".pyright" / "state.json",
        "pytype": source_root / ".pytype" / "state.json",
        "coverage": source_root / ".coverage.worker",
        "coverage_xml": source_root / "coverage.xml",
        "htmlcov": source_root / "htmlcov" / "index.html",
        "build": source_root / "build" / "output.bin",
        "wheel": source_root / "dist" / "spin_fm-2.6.22-py3-none-any.whl",
        "egg_info": source_root / "src" / "spin_fm.egg-info" / "PKG-INFO",
        "dist_info": source_root / "src" / "spin_fm.dist-info" / "METADATA",
        "sdist": source_root / "spin_fm-2.6.22.tar.gz",
        "debian": source_root / "debian" / "tmp" / "generated-file",
        "venv": source_root / ".venv" / "lib" / "python" / "cached.pyc",
        "venv_plain": source_root / "venv" / "lib" / "cached.pyc",
    }
    for name, artifact_path in artifacts.items():
        artifact_path.parent.mkdir(parents=True, exist_ok=True)
        artifact_path.write_bytes(name.encode("utf-8"))

    archive_one = tmp_path / "one.zip"
    archive_two = tmp_path / "two.zip"
    monkeypatch.setenv("SOURCE_DATE_EPOCH", "1784163047")

    build_archive = _SOURCE_ARCHIVE["build_archive"]
    verify_archive = _SOURCE_ARCHIVE["verify_archive"]
    assert_cache_free = _SOURCE_ARCHIVE["assert_cache_free"]
    clean_tree = _SOURCE_ARCHIVE["clean_tree"]

    build_archive(source_root, archive_one)
    build_archive(source_root, archive_two)

    assert archive_one.read_bytes() == archive_two.read_bytes()
    assert stat.S_IMODE(archive_one.stat().st_mode) == 0o644
    assert all(artifact_path.exists() for artifact_path in artifacts.values()), (
        "building without --clean must not mutate the checkout"
    )

    with ZipFile(archive_one) as archive:
        names = archive.namelist()
        assert names
        assert all(name.startswith("spin-fm-2.6.22/") for name in names)
        assert not [name for name in names if _is_excluded_member(name)]
        assert not {PurePosixPath(name).name for name in names}.intersection(
            PYPI_METADATA
        )
        member_modes = {
            PurePosixPath(member.filename)
            .relative_to("spin-fm-2.6.22")
            .as_posix(): stat.S_IMODE(member.external_attr >> 16)
            for member in archive.infolist()
        }
        assert member_modes["LICENSE"] == 0o644
        assert member_modes["bin/spin-fm"] == 0o755
        assert member_modes["main.py"] == 0o755
        assert set(member_modes.values()) <= {0o644, 0o755, 0o777}
        assert archive.testzip() is None

    members, total_size = verify_archive(archive_one)
    assert members > 0
    assert total_size > 0

    with pytest.raises(RuntimeError, match="cache artifacts"):
        assert_cache_free(source_root)

    clean_tree(source_root)
    assert not [
        artifact_path for artifact_path in artifacts.values() if artifact_path.exists()
    ]
    assert (source_root / ".venv").is_dir()
    assert (source_root / "venv").is_dir()
    assert_cache_free(source_root)

    for forbidden_path in (
        source_root / "setup.py",
        source_root / "src" / "nested" / "pyproject.toml",
    ):
        forbidden_path.parent.mkdir(parents=True, exist_ok=True)
        forbidden_path.write_text("raise SystemExit\n", encoding="utf-8")
        with pytest.raises(RuntimeError, match="not permitted|packaging metadata"):
            build_archive(source_root, tmp_path / "forbidden.zip")
        forbidden_path.unlink()


def test_source_archive_requires_complete_distribution_policy(tmp_path: Path) -> None:
    source_root = tmp_path / "spin-fm-source"
    _copy_source_tree(source_root)
    build_archive = _SOURCE_ARCHIVE["build_archive"]

    attributes = source_root / ".gitattributes"
    original = attributes.read_text(encoding="utf-8")
    attributes.unlink()
    with pytest.raises(RuntimeError, match=r"missing: .*\.gitattributes"):
        build_archive(source_root, tmp_path / "missing-policy.zip")

    attributes.write_text(
        original.replace("*.dsc export-ignore\n", ""),
        encoding="utf-8",
    )
    with pytest.raises(
        RuntimeError, match=r"incomplete distribution exclusion policy.*\*\.dsc"
    ):
        build_archive(source_root, tmp_path / "incomplete-policy.zip")


def test_final_cleanup_removes_legacy_and_transient_files(tmp_path: Path) -> None:
    source_root = tmp_path / "spin-fm-source"
    _copy_source_tree(source_root)
    legacy_paths = (
        source_root / "src" / "spin_fm" / "__main__.py",
        source_root / "src" / "spin_fm" / "empty_trash.py",
        source_root / "src" / "spin_fm" / "audio_player.py.orig",
        source_root / "tests" / "failed-change.rej",
        source_root / "README.md.bak",
        source_root / "debian" / "tmp" / "staged",
        source_root / "debian" / "spin-fm" / "usr" / "bin" / "spin-fm",
        source_root / "debian" / "files",
        source_root / "spin-fm-2.6.5-source.zip",
    )
    for path in legacy_paths:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("obsolete\n", encoding="utf-8")

    _SOURCE_ARCHIVE["clean_tree"](source_root)

    assert not [path for path in legacy_paths if path.exists()]
    _SOURCE_ARCHIVE["assert_release_clean"](source_root)


def test_release_gate_rejects_pypi_and_legacy_files(tmp_path: Path) -> None:
    source_root = tmp_path / "spin-fm-source"
    _copy_source_tree(source_root)

    blockers = (
        source_root / "src" / "spin_fm" / "__main__.py",
        source_root / "src" / "spin_fm" / "empty_trash.py",
        source_root / "nested" / "setup.py",
        source_root / "README.md.orig",
    )
    for blocker in blockers:
        blocker.parent.mkdir(parents=True, exist_ok=True)
        blocker.write_text("obsolete\n", encoding="utf-8")

    with pytest.raises(RuntimeError, match="release artifacts"):
        _SOURCE_ARCHIVE["assert_release_clean"](source_root)
    with pytest.raises(RuntimeError, match="legacy|packaging"):
        _SOURCE_ARCHIVE["build_archive"](source_root, tmp_path / "blocked.zip")


def test_cache_gate_reaches_nested_local_environments(tmp_path: Path) -> None:
    source_root = tmp_path / "spin-fm-source"
    _copy_source_tree(source_root)
    cached = source_root / ".venv" / "lib" / "python" / "pkg" / "__pycache__"
    cached.mkdir(parents=True)
    (cached / "module.pyc").write_bytes(b"cached")

    with pytest.raises(RuntimeError, match="cache artifacts"):
        _SOURCE_ARCHIVE["assert_cache_free"](source_root)
    with pytest.raises(RuntimeError, match="release artifacts"):
        _SOURCE_ARCHIVE["assert_release_clean"](source_root)

    _SOURCE_ARCHIVE["clean_tree"](source_root)
    assert (source_root / ".venv").is_dir()
    assert not cached.exists()
    _SOURCE_ARCHIVE["assert_cache_free"](source_root)


def test_plain_pytest_subset_does_not_generate_bytecode(tmp_path: Path) -> None:
    source_root = tmp_path / "spin-fm-source"
    _copy_source_tree(source_root)
    environment = _subprocess_environment()

    subprocess.run(
        [
            sys.executable,
            "-m",
            "pytest",
            "-q",
            "tests/test_audio.py",
            "tests/test_cli.py",
        ],
        cwd=source_root,
        env=environment,
        check=True,
        capture_output=True,
        text=True,
        timeout=60,
    )

    assert not _cache_paths(source_root)


def test_cache_symlink_cleanup_never_follows_the_target(tmp_path: Path) -> None:
    source_root = tmp_path / "source"
    linked_parent = source_root / "nested"
    linked_parent.mkdir(parents=True)
    protected_directory = tmp_path / "protected-cache-target"
    protected_directory.mkdir()
    protected_file = protected_directory / "keep.txt"
    protected_file.write_text("keep", encoding="utf-8")

    linked_cache = linked_parent / "__pycache__"
    linked_cache.symlink_to(protected_directory, target_is_directory=True)
    _SOURCE_ARCHIVE["clean_tree"](source_root)

    assert not linked_cache.exists()
    assert protected_file.read_text(encoding="utf-8") == "keep"


def test_source_archive_can_be_written_inside_the_source_tree(tmp_path: Path) -> None:
    source_root = tmp_path / "spin-fm-source"
    _copy_source_tree(source_root)
    output = source_root / "release" / "spin-fm-2.6.22-source.zip"
    output.parent.mkdir()

    _SOURCE_ARCHIVE["build_archive"](source_root, output)

    assert stat.S_IMODE(output.stat().st_mode) == 0o644
    with ZipFile(output) as archive:
        names = archive.namelist()
        assert not any(name.endswith(".tmp") for name in names)
        assert not any(name.endswith("source.zip") for name in names)


@pytest.mark.parametrize(
    "bad_member",
    (
        "spin-fm-2.6.22/src/spin_fm/__pycache__/module.pyc",
        "spin-fm-2.6.22/dist/spin_fm-2.6.22-py3-none-any.whl",
        "spin-fm-2.6.22/examples/nested/setup.py",
        "spin-fm-2.6.22/src/spin_fm/__main__.py",
        "spin-fm-2.6.22/src/spin_fm/empty_trash.py",
        "spin-fm-2.6.22/README.md.orig",
    ),
)
def test_archive_verifier_rejects_excluded_members(
    tmp_path: Path,
    bad_member: str,
) -> None:
    archive_path = tmp_path / "bad.zip"
    members = {
        "spin-fm-2.6.22/main.py": b"pass\n",
        "spin-fm-2.6.22/src/spin_fm/__init__.py": b'__version__ = "2.6.22"\n',
        bad_member: b"generated",
    }
    with ZipFile(archive_path, "w", compression=ZIP_DEFLATED) as archive:
        for name in sorted(members):
            archive.writestr(name, members[name])

    with pytest.raises(RuntimeError, match="archive contains"):
        _SOURCE_ARCHIVE["verify_archive"](archive_path)


def test_full_name_layout_and_native_lwm_themes_are_shipped() -> None:
    tabs = (ROOT / "src" / "spin_fm" / "tabs.py").read_text(encoding="utf-8")
    player = (ROOT / "src" / "spin_fm" / "audio_player.py").read_text(
        encoding="utf-8"
    )
    theme_manager = (ROOT / "src" / "spin_fm" / "theme_manager.py").read_text(
        encoding="utf-8"
    )

    assert "class FullNameIconDelegate" in tabs
    assert '("setUniformItemSizes", False)' in tabs
    assert '("setGridSize", QSize())' in tabs
    assert "view.setTextElideMode(Qt.ElideNone)" in tabs
    assert "Qt.ElideMiddle" not in tabs
    assert "elidedText" not in player
    assert "self.track_label.setText(self._track_name)" in player
    assert "self.path_label.setText(self._current_path)" in player

    theme_dir = ROOT / "src" / "spin_fm" / "themes"
    for name in ("lwm_dark.css", "lwm_graphite.css"):
        text = (theme_dir / name).read_text(encoding="utf-8")
        assert "SPDX-License-Identifier: GPL-2.0-or-later" in text
        assert "QFrame#audioPlayer" in text
        assert "QLabel#audioMprisBadge" in text
    assert not list(theme_dir.glob("*.qss"))
    assert 'path.suffix == ".css"' in theme_manager


def test_top_level_and_debian_changelogs_cover_the_same_release_highlights() -> None:
    changelog = (ROOT / "CHANGELOG.md").read_text(encoding="utf-8")
    debian = (ROOT / "debian" / "changelog").read_text(encoding="utf-8")

    markdown_entries: dict[str, list[str]] = {}
    current_version = ""
    for line in changelog.splitlines():
        heading = re.match(r"^## ([^ ]+) — ", line)
        if heading:
            current_version = heading.group(1)
            markdown_entries[current_version] = []
        elif current_version and line.startswith("- "):
            markdown_entries[current_version].append(" ".join(line[2:].split()))

    debian_entries: dict[str, list[str]] = {}
    current_version = ""
    current_bullet: list[str] = []

    def flush_bullet() -> None:
        if current_version and current_bullet:
            debian_entries[current_version].append(" ".join(current_bullet))
            current_bullet.clear()

    for line in debian.splitlines():
        heading = re.match(r"^spin-fm \(([^)]+)\)", line)
        if heading:
            flush_bullet()
            current_version = heading.group(1)
            assert current_version not in debian_entries
            debian_entries[current_version] = []
        elif line.startswith("  * "):
            flush_bullet()
            current_bullet.append(" ".join(line[4:].split()))
        elif current_bullet and line.startswith("    "):
            current_bullet.append(" ".join(line.strip().split()))
        elif line.startswith(" -- "):
            flush_bullet()
    flush_bullet()

    assert list(markdown_entries) == list(debian_entries)
    assert markdown_entries == debian_entries


def test_production_dialog_sidebar_icon_and_legacy_cleanup_are_explicit() -> None:
    dialogs = (ROOT / "src" / "spin_fm" / "dialogs.py").read_text(
        encoding="utf-8"
    )
    sidebar = (ROOT / "src" / "spin_fm" / "mounted_devices_widget.py").read_text(
        encoding="utf-8"
    )
    main_window = (ROOT / "src" / "spin_fm" / "main_window.py").read_text(
        encoding="utf-8"
    )
    icon_manager = (ROOT / "src" / "spin_fm" / "icon_theme_manager.py").read_text(
        encoding="utf-8"
    )
    combined_python = "\n".join(
        path.read_text(encoding="utf-8")
        for path in (ROOT / "src" / "spin_fm").glob("*.py")
    )

    assert "class TrashLocationDialog(QDialog)" in dialogs
    assert "MINIMUM_SIZE = QSize(720, 360)" in dialogs
    assert "INITIAL_SIZE = QSize(860, 460)" in dialogs
    assert "table.setTextElideMode(Qt.ElideNone)" in dialogs
    assert 'table.setHorizontalHeaderLabels(["Location", "Folder"])' in dialogs
    assert "ACTION_COLUMN_WIDTH = 124" in sidebar
    assert "ACTION_BUTTON_WIDTH = 104" in sidebar
    assert "def ensure_action_column_visible" in sidebar
    assert "self.sidebar_action.toggled.connect(self.set_devices_sidebar_visible)" in main_window
    assert 'DEFAULT_THEME = "Adwaita"' in icon_manager

    for retired in (
        "def addNewTab(",
        "def update_devices(",
        "def get_all_usb_devices_with_mount_points(",
        "def default_icon_theme(",
        "def _seek_relative(",
        "def _current_position(",
        "def onFileClicked(",
        "def confirmDelete(",
        "def cutFileOrFolder(",
        "def copyFileOrFolder(",
        "def pasteFileOrFolder(",
    ):
        assert retired not in combined_python



def test_trash_and_drop_production_wiring_is_explicit() -> None:
    tabs = (ROOT / "src" / "spin_fm" / "tabs.py").read_text(encoding="utf-8")
    file_ops = (ROOT / "src" / "spin_fm" / "file_ops.py").read_text(
        encoding="utf-8"
    )
    readme = (ROOT / "README.md").read_text(encoding="utf-8")
    control = (ROOT / "debian" / "control").read_text(encoding="utf-8")

    assert "self.trash_button.clicked.connect(self.goTrash)" in tabs
    assert "trashOrGoTrash" not in tabs
    assert '"Delete Permanently"' in tabs
    assert '"cut",' in tabs
    assert "move=self._drop_is_move(event)" not in tabs
    assert "event.setDropAction(copy_action)" in tabs
    assert '[gio, "trash", "--empty"]' in file_ops
    assert "python3-pyqt5.qtmultimedia" in readme
    assert "python3-pyqt5` supplies the Qt Widgets and Qt D-Bus bindings" in readme
    binary_stanza = control.split("Package: spin-fm", 1)[1]
    package_fields = binary_stanza.split("Description:", 1)[0]
    depends = package_fields.split("Depends:", 1)[1]
    assert "libglib2.0-bin" in depends

    if "Recommends:" in package_fields:
        recommends = package_fields.split("Recommends:", 1)[1]
        assert "libglib2.0-bin" not in recommends
