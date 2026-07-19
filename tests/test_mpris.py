from __future__ import annotations

import os
import shutil
import subprocess
import sys
import textwrap
from pathlib import Path

import pytest

try:
    from spin_fm.mpris import (
        MPRISService,
        clamp_volume,
        local_path_from_uri,
        metadata_for_track,
        track_id_for_path,
    )
    from spin_fm.qt_compat import QtCore
except ImportError:
    pytest.skip("PyQt5/PyQt6 is not installed", allow_module_level=True)

ROOT = Path(__file__).resolve().parents[1]


def test_mpris_helpers_are_stable_and_safe(tmp_path: Path) -> None:
    track = tmp_path / "A track with spaces.ogg"
    track.write_bytes(b"")

    assert clamp_volume(-1) == 0.0
    assert clamp_volume(0.4) == 0.4
    assert clamp_volume(8) == 1.0
    assert clamp_volume(float("nan")) == 0.0

    track_id = track_id_for_path(track)
    assert track_id.startswith("/net/techtimejourney/SpinFM/track/")
    assert track_id == track_id_for_path(track)

    metadata = metadata_for_track(str(track), 12_345)
    assert metadata["mpris:trackid"] == track_id
    assert metadata["mpris:length"] == 12_345_000
    assert metadata["xesam:title"] == track.name
    assert metadata["xesam:url"] == track.as_uri()

    assert local_path_from_uri(track.as_uri()) == str(track.resolve())
    assert local_path_from_uri(str(track)) == str(track.resolve())
    assert local_path_from_uri("https://example.invalid/track.ogg") is None
    assert local_path_from_uri("file://remote-host/tmp/track.ogg") is None


def test_mpris_registration_failure_is_non_fatal(monkeypatch) -> None:
    import spin_fm.mpris as mpris_module

    class FakePlayer(QtCore.QObject):
        def current_position(self) -> int:
            return 0

    player = FakePlayer()
    monkeypatch.setattr(mpris_module, "QtDBus", None)
    service = MPRISService(player, player)
    try:
        service.set_track("/tmp/test.ogg", 1_000)
        service.set_playback_status("Playing", force=True)
        service.set_seekable(True)
        service.set_volume(0.5)
        assert service.available is False
        assert service.playback_status == "Playing"
        assert service.has_track is True
    finally:
        service.shutdown()


def test_real_session_bus_exposes_mpris_and_emits_activity(tmp_path: Path) -> None:
    required = ("dbus-run-session", "busctl", "dbus-monitor")
    if any(shutil.which(command) is None for command in required):
        pytest.skip("D-Bus command-line tools are unavailable")

    probe = tmp_path / "probe.py"
    probe.write_text(
        textwrap.dedent(
            f"""
            import sys
            sys.path.insert(0, {str(ROOT / 'src')!r})
            from spin_fm.mpris import MPRISService
            from spin_fm.qt_compat import QtCore

            class Player(QtCore.QObject):
                def __init__(self):
                    super().__init__()
                    self.position = 12000
                    self.playing = True
                    self.service = None

                def current_position(self):
                    return self.position

                def play(self):
                    self.playing = True
                    self.service.set_playback_status('Playing', force=True)

                def pause(self):
                    self.playing = False
                    self.service.set_playback_status('Paused', force=True)

                def toggle_playback(self):
                    self.playing = not self.playing
                    self.service.set_playback_status(
                        'Playing' if self.playing else 'Paused', force=True
                    )
                    print('TOGGLED', self.playing, flush=True)
                    return True

                def stop(self):
                    self.playing = False
                    self.service.set_playback_status('Stopped', force=True)

                def seek_relative(self, value):
                    self.position += value
                    self.service.emit_seeked(self.position)

                def set_position(self, value):
                    self.position = value
                    self.service.emit_seeked(value)

                def set_volume_fraction(self, value):
                    self.service.set_volume(value)

                def play_file(self, _path):
                    return True

                def window(self):
                    return None

            app = QtCore.QCoreApplication(sys.argv)
            player = Player()
            service = MPRISService(player, player)
            player.service = service
            service.set_track('/tmp/Example Track.ogg', 123456)
            service.set_seekable(True)
            service.set_volume(.72)
            service.set_playback_status('Playing', force=True)
            print('SERVICE', service.service_name, service.available, flush=True)
            QtCore.QTimer.singleShot(15000, app.quit)
            app.exec()
            service.shutdown()
            """
        ),
        encoding="utf-8",
    )

    runtime_dir = tmp_path / "runtime"
    runtime_dir.mkdir(mode=0o700)
    shell = tmp_path / "probe.sh"
    shell.write_text(
        textwrap.dedent(
            f"""
            set -eu
            export XDG_RUNTIME_DIR={str(runtime_dir)!r}
            export QT_QPA_PLATFORM=offscreen
            export PYTHONDONTWRITEBYTECODE=1
            {sys.executable!r} -B {str(probe)!r} >probe.log 2>probe.err &
            pid=$!
            trap 'kill "$pid" 2>/dev/null || true' EXIT
            i=0
            while ! grep -q '^SERVICE ' probe.log 2>/dev/null; do
                i=$((i+1)); [ "$i" -lt 80 ] || {{ cat probe.err >&2; exit 1; }}
                sleep .05
            done
            service=$(awk '/^SERVICE /{{print $2}}' probe.log)
            busctl --user introspect "$service" /org/mpris/MediaPlayer2 >introspect.txt
            busctl --user get-property "$service" /org/mpris/MediaPlayer2 \
                org.mpris.MediaPlayer2.Player PlaybackStatus >status.txt
            busctl --user get-property "$service" /org/mpris/MediaPlayer2 \
                org.mpris.MediaPlayer2.Player Metadata >metadata.txt
            dbus-monitor --session \
                "type='signal',interface='org.freedesktop.DBus.Properties',member='PropertiesChanged'" \
                >monitor.txt 2>/dev/null &
            monitor=$!
            sleep .2
            busctl --user call "$service" /org/mpris/MediaPlayer2 \
                org.mpris.MediaPlayer2.Player PlayPause
            sleep .4
            kill "$monitor" 2>/dev/null || true
            wait "$monitor" 2>/dev/null || true
            grep -q 'org.mpris.MediaPlayer2.Player' introspect.txt
            grep -q 'PlayPause' introspect.txt
            grep -q 'Seeked' introspect.txt
            grep -q 's "Playing"' status.txt
            grep -q 'mpris:length.*x 123456000' metadata.txt
            grep -q 'mpris:trackid.*o "/net/techtimejourney/SpinFM/track/' metadata.txt
            grep -q 'PropertiesChanged' monitor.txt
            grep -q 'PlaybackStatus' monitor.txt
            grep -q 'Paused' monitor.txt
            ! grep -Eq 'variant[[:space:]]+variant' monitor.txt
            grep -q 'TOGGLED False' probe.log
            kill "$pid" 2>/dev/null || true
            wait "$pid" 2>/dev/null || true
            """
        ),
        encoding="utf-8",
    )

    environment = dict(os.environ)
    environment.pop("DBUS_SESSION_BUS_ADDRESS", None)
    result = subprocess.run(
        ["dbus-run-session", "--", "sh", str(shell)],
        cwd=tmp_path,
        env=environment,
        check=False,
        capture_output=True,
        text=True,
        timeout=30,
    )
    assert result.returncode == 0, result.stdout + result.stderr
