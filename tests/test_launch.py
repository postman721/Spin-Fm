from __future__ import annotations

from pathlib import Path

import pytest

import spin_fm.launch as launch


def test_resolve_command_preserves_quoted_arguments(monkeypatch) -> None:
    monkeypatch.setattr(
        launch.shutil,
        "which",
        lambda name: "/usr/bin/viewer" if name == "viewer" else None,
    )
    assert launch.resolve_command('viewer --title "My File"') == [
        "/usr/bin/viewer",
        "--title",
        "My File",
    ]


def test_resolve_command_rejects_missing_program(monkeypatch) -> None:
    monkeypatch.setattr(launch.shutil, "which", lambda _name: None)
    with pytest.raises(FileNotFoundError, match="Program not found"):
        launch.resolve_command("missing-program")


def test_launch_paths_uses_argument_array_without_shell(
    monkeypatch, tmp_path: Path
) -> None:
    source = tmp_path / "name with spaces.txt"
    source.write_text("payload", encoding="utf-8")
    captured: dict[str, object] = {}

    class DummyProcess:
        pass

    def fake_popen(arguments, **kwargs):
        captured["arguments"] = arguments
        captured["kwargs"] = kwargs
        return DummyProcess()

    monkeypatch.setattr(launch.shutil, "which", lambda _name: "/usr/bin/viewer")
    monkeypatch.setattr(launch.subprocess, "Popen", fake_popen)

    process = launch.launch_paths("viewer --readonly", [str(source)])
    assert isinstance(process, DummyProcess)
    assert captured["arguments"] == ["/usr/bin/viewer", "--readonly", str(source)]
    assert captured["kwargs"]["start_new_session"] is True
    assert "shell" not in captured["kwargs"]
