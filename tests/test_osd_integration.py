from __future__ import annotations

import json
import socket
import threading
from pathlib import Path

import spin_fm.osd_integration as osd_module
from spin_fm.osd_integration import SOCKET_NAME, WaylandOSDBridge


def _wayland_environment(runtime_dir: Path) -> dict[str, str]:
    return {
        "XDG_SESSION_TYPE": "wayland",
        "WAYLAND_DISPLAY": "wayland-test",
        "XDG_RUNTIME_DIR": str(runtime_dir),
        "HOME": str(runtime_dir),
    }


def _start_socket_server(
    socket_path: Path,
    expected_connections: int,
) -> tuple[threading.Thread, threading.Event, list[dict[str, object]]]:
    received: list[dict[str, object]] = []
    ready = threading.Event()

    def server() -> None:
        with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as listener:
            listener.bind(str(socket_path))
            listener.listen(expected_connections)
            listener.settimeout(1.5)
            ready.set()
            for _index in range(expected_connections):
                connection, _address = listener.accept()
                with connection:
                    data = b""
                    while not data.endswith(b"\n"):
                        chunk = connection.recv(4096)
                        if not chunk:
                            break
                        data += chunk
                received.append(json.loads(data.decode("utf-8")))

    thread = threading.Thread(target=server, daemon=True)
    thread.start()
    return thread, ready, received


def test_missing_osd_is_a_safe_noop(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr(osd_module.shutil, "which", lambda _name: None)
    bridge = WaylandOSDBridge(environ=_wayland_environment(tmp_path))

    assert bridge.available is False
    assert bridge.notify_media("Playing", "sample.ogg") is False
    assert bridge.notify_volume(72, False, "sample.ogg") is False


def test_regular_file_cannot_masquerade_as_osd_socket(
    tmp_path: Path, monkeypatch
) -> None:
    monkeypatch.setattr(osd_module.shutil, "which", lambda _name: None)
    (tmp_path / SOCKET_NAME).write_text("not a socket", encoding="utf-8")

    bridge = WaylandOSDBridge(environ=_wayland_environment(tmp_path))

    assert bridge.available is False
    assert bridge.connected is False
    assert bridge.notify_media("Playing", "sample.ogg") is False


def test_stale_osd_socket_does_not_enable_bridge(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr(osd_module.shutil, "which", lambda _name: None)
    socket_path = tmp_path / SOCKET_NAME
    with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as listener:
        listener.bind(str(socket_path))

    bridge = WaylandOSDBridge(environ=_wayland_environment(tmp_path))

    assert bridge.available is False
    assert bridge.notify_volume(50, False) is False


def test_daemon_launch_uses_current_cli_without_blocking(
    tmp_path: Path, monkeypatch
) -> None:
    monkeypatch.setattr(
        osd_module.shutil,
        "which",
        lambda _name: "/usr/bin/wayland-volume-osd",
    )
    launches: list[tuple[list[str], dict[str, object]]] = []

    def record_launch(arguments, **kwargs):
        launches.append((list(arguments), dict(kwargs)))
        return object()

    monkeypatch.setattr(osd_module.subprocess, "Popen", record_launch)
    bridge = WaylandOSDBridge(environ=_wayland_environment(tmp_path))

    assert bridge.notify_media("Playing", "sample.ogg") is False
    assert len(launches) == 1
    arguments, options = launches[0]
    assert arguments == [
        "/usr/bin/wayland-volume-osd",
        "--theme",
        "dark",
        "daemon",
    ]
    assert options == {
        "stdin": osd_module.subprocess.DEVNULL,
        "stdout": osd_module.subprocess.DEVNULL,
        "stderr": osd_module.subprocess.DEVNULL,
        "close_fds": True,
        "start_new_session": True,
    }


def test_daemon_launch_failure_never_escapes(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr(
        osd_module.shutil,
        "which",
        lambda _name: "/usr/bin/wayland-volume-osd",
    )

    def fail_launch(*_args, **_kwargs):
        raise OSError("simulated daemon launch failure")

    monkeypatch.setattr(osd_module.subprocess, "Popen", fail_launch)
    bridge = WaylandOSDBridge(environ=_wayland_environment(tmp_path))

    assert bridge.available is True
    assert bridge.notify_media("Playing", "sample.ogg") is False
    assert "simulated daemon launch failure" in bridge.last_error


def test_live_socket_receives_ping_and_media_payload(
    tmp_path: Path, monkeypatch
) -> None:
    monkeypatch.setattr(osd_module.shutil, "which", lambda _name: None)
    socket_path = tmp_path / SOCKET_NAME
    thread, ready, received = _start_socket_server(socket_path, 2)
    assert ready.wait(1)

    bridge = WaylandOSDBridge(environ=_wayland_environment(tmp_path))
    assert bridge.available is True
    assert bridge.notify_media(
        "Playing",
        "sample track.ogg",
        position_ms=25_000,
        duration_ms=100_000,
    )

    thread.join(timeout=2)
    assert not thread.is_alive()
    assert received == [
        {"type": "ping"},
        {
            "type": "show",
            "mode": "media",
            "title": "Playing",
            "detail": "sample track.ogg",
            "level": 25,
            "theme": "dark",
        },
    ]


def test_bridge_detects_live_socket_that_appears_later(
    tmp_path: Path, monkeypatch
) -> None:
    monkeypatch.setattr(osd_module.shutil, "which", lambda _name: None)
    bridge = WaylandOSDBridge(environ=_wayland_environment(tmp_path))
    assert bridge.available is False

    socket_path = tmp_path / SOCKET_NAME
    thread, ready, received = _start_socket_server(socket_path, 1)
    assert ready.wait(1)

    assert bridge.refresh_availability(force=True) is True
    thread.join(timeout=2)
    assert not thread.is_alive()
    assert received == [{"type": "ping"}]


def test_bridge_detects_command_that_appears_later(tmp_path: Path, monkeypatch) -> None:
    detected: dict[str, str | None] = {"path": None}
    monkeypatch.setattr(osd_module.shutil, "which", lambda _name: detected["path"])
    bridge = WaylandOSDBridge(environ=_wayland_environment(tmp_path))
    assert bridge.available is False

    detected["path"] = "/usr/bin/wayland-volume-osd"

    assert bridge.refresh_availability(force=True) is True
    assert bridge.command == "/usr/bin/wayland-volume-osd"

    detected["path"] = None
    assert bridge.refresh_availability(force=True) is False
    assert bridge.command is None


def test_command_lookup_uses_the_supplied_environment_path(
    tmp_path: Path, monkeypatch
) -> None:
    environment = _wayland_environment(tmp_path)
    environment["PATH"] = "/opt/wayland-osd/bin:/usr/bin"
    lookups: list[tuple[str, str | None]] = []

    def fake_which(name: str, *, path: str | None = None) -> str:
        lookups.append((name, path))
        return "/opt/wayland-osd/bin/wayland-volume-osd"

    monkeypatch.setattr(osd_module.shutil, "which", fake_which)
    bridge = WaylandOSDBridge(environ=environment)

    assert bridge.available is True
    assert lookups == [("wayland-volume-osd", "/opt/wayland-osd/bin:/usr/bin")]


def test_bridge_uses_osd_theme_and_sanitizes_volume_payload(
    tmp_path: Path, monkeypatch
) -> None:
    config = tmp_path / ".config" / "volume-osd" / "osd.conf"
    config.parent.mkdir(parents=True)
    config.write_text("theme=blue\n", encoding="utf-8")
    monkeypatch.setattr(osd_module.shutil, "which", lambda _name: None)

    bridge = WaylandOSDBridge(environ=_wayland_environment(tmp_path))
    assert bridge.theme == "blue"
    captured: list[dict[str, object]] = []
    bridge.available = True
    monkeypatch.setattr(
        bridge,
        "_notify",
        lambda payload: captured.append(payload) or True,
    )

    assert bridge.notify_volume(200, True, "line one\nline two") is True
    assert captured == [
        {
            "type": "show",
            "mode": "volume",
            "title": "Muted",
            "detail": "line one line two",
            "level": 0,
            "muted": True,
            "theme": "blue",
        }
    ]


def test_lookup_failure_disables_bridge_without_raising(
    tmp_path: Path, monkeypatch
) -> None:
    def fail_lookup(_name: str):
        raise OSError("broken PATH lookup")

    monkeypatch.setattr(osd_module.shutil, "which", fail_lookup)
    bridge = WaylandOSDBridge(environ=_wayland_environment(tmp_path))

    assert bridge.available is False
    assert bridge.command is None
    assert bridge.notify_media("Playing", "sample.ogg") is False


def test_installed_osd_is_not_started_outside_wayland_by_default(
    tmp_path: Path, monkeypatch
) -> None:
    monkeypatch.setattr(
        osd_module.shutil,
        "which",
        lambda _name: "/usr/bin/wayland-volume-osd",
    )
    environment = {
        "XDG_SESSION_TYPE": "x11",
        "XDG_RUNTIME_DIR": str(tmp_path),
        "HOME": str(tmp_path),
    }
    bridge = WaylandOSDBridge(environ=environment)

    assert bridge.available is False
    assert bridge.notify_volume(50, False) is False
