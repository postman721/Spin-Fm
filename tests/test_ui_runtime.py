from __future__ import annotations

import os
import threading
import time
from pathlib import Path

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

try:
    from spin_fm.main_window import MainWindow
    from spin_fm.qt_compat import (
        USING_PYQT6,
        QAction,
        QApplication,
        QMessageBox,
        Qt,
        QtCore,
    )
    from spin_fm.tabs import Tabs
    from spin_fm.workers import TaskManager
except ImportError:
    pytest.skip("PyQt5/PyQt6 is not installed", allow_module_level=True)


@pytest.fixture(scope="module")
def app():
    instance = QApplication.instance() or QApplication(["spin-fm-tests"])
    yield instance
    instance.processEvents()


def _drain_events(app, predicate, timeout: float = 3.0) -> None:
    deadline = time.monotonic() + timeout
    while predicate() and time.monotonic() < deadline:
        app.processEvents()
        time.sleep(0.01)
    assert not predicate()


def test_main_window_shares_storage_cache_and_releases_rejected_trash_task(
    app, monkeypatch
) -> None:
    monkeypatch.setattr(
        "spin_fm.disk_space.DiskSpaceInfo._run_lsblk",
        staticmethod(lambda: []),
    )
    window = MainWindow(startup_paths=[])
    try:
        assert window.mounted_devices_widget.disk_info is window.disk_info
        monkeypatch.setattr(
            QMessageBox,
            "question",
            staticmethod(lambda *_args, **_kwargs: QMessageBox.Yes),
        )
        monkeypatch.setattr(
            window.background_tasks, "submit", lambda *_args, **_kwargs: None
        )

        window.empty_trash()

        assert window._empty_trash_busy is False
        assert window.tabs._external_operation_busy is False
        assert window.activity_bar.isHidden()
    finally:
        window.disk_timer.stop()
        window.mounted_devices_widget.shutdown()
        window.tabs.shutdown()
        window.close()
        window.deleteLater()
        app.processEvents()


def test_open_with_uses_shared_settings_and_safe_launcher(
    app, monkeypatch, tmp_path: Path
) -> None:
    import spin_fm.launch as launch_module
    import spin_fm.tabs as tabs_module

    selected_file = tmp_path / "selected file.txt"
    selected_file.write_text("payload", encoding="utf-8")
    settings_values: dict[str, str] = {}
    launched: dict[str, object] = {}

    class FakeSettings:
        def __init__(self, organization: str, application: str) -> None:
            assert organization == "Spin"
            assert application == "Spin FM"

        def value(self, key: str, default=""):
            return settings_values.get(key, default)

        def setValue(self, key: str, value: str) -> None:  # noqa: N802 - Qt API
            settings_values[key] = value

    def fake_popen(arguments, **kwargs):
        launched["arguments"] = arguments
        launched["kwargs"] = kwargs
        return object()

    monkeypatch.setattr(tabs_module, "QSettings", FakeSettings)
    monkeypatch.setattr(
        tabs_module.QInputDialog,
        "getText",
        staticmethod(lambda *_args, **_kwargs: ("viewer --readonly", True)),
    )
    monkeypatch.setattr(launch_module.shutil, "which", lambda _name: "/usr/bin/viewer")
    monkeypatch.setattr(launch_module.subprocess, "Popen", fake_popen)

    widget = Tabs()
    try:
        monkeypatch.setattr(
            widget, "_path_from_index", lambda _index: str(selected_file)
        )
        widget.open_with([object()])
        assert launched["arguments"] == [
            "/usr/bin/viewer",
            "--readonly",
            str(selected_file),
        ]
        assert settings_values["open_with/last_program"] == "viewer --readonly"
    finally:
        widget.shutdown()
        widget.close()
        widget.deleteLater()
        app.processEvents()


def test_task_manager_rejects_work_beyond_configured_bound(app) -> None:
    manager = TaskManager(max_threads=1, max_tasks=1)
    release = threading.Event()

    first = manager.submit(lambda: release.wait(2))
    second = manager.submit(lambda: None)
    assert first is not None
    assert second is None
    assert manager.active_count == 1

    release.set()
    _drain_events(app, lambda: manager.is_busy)
    assert manager.shutdown(wait_msec=1000)


def test_parent_shortcut_is_ctrl_up(app) -> None:
    widget = Tabs()
    try:
        view = widget.currentView()
        shortcuts = {
            action.shortcut().toString()
            for action in view.actions()
            if not action.shortcut().isEmpty()
        }
        assert "Ctrl+Up" in shortcuts
        assert "Alt+Up" not in shortcuts
        assert "Return" in shortcuts
        assert "Enter" in shortcuts
        assert "Ctrl+Up" in widget.up_button.toolTip()
    finally:
        widget.shutdown()
        widget.close()
        widget.deleteLater()
        app.processEvents()


def test_ctrl_t_has_one_unambiguous_window_binding(app, monkeypatch) -> None:
    monkeypatch.setattr(
        "spin_fm.disk_space.DiskSpaceInfo._run_lsblk",
        staticmethod(lambda: []),
    )
    if USING_PYQT6:
        from PyQt6.QtCore import Qt as NativeQt
        from PyQt6.QtTest import QTest
    else:
        from PyQt5.QtCore import Qt as NativeQt
        from PyQt5.QtTest import QTest

    messages: list[str] = []

    def message_handler(_message_type, _context, message: str) -> None:
        messages.append(message)

    previous_handler = QtCore.qInstallMessageHandler(message_handler)
    window = MainWindow(startup_paths=[])
    try:
        window.show()
        view = window.tabs.currentView()
        view.setFocus()
        app.processEvents()

        ctrl_t_actions = [
            action
            for action in window.findChildren(QAction)
            if action.shortcut().toString() == "Ctrl+T"
        ]
        assert len(ctrl_t_actions) == 1
        assert all(
            action.shortcut().toString() != "Ctrl+T" for action in view.actions()
        )

        before = window.tabs.tab_widget.count()
        if USING_PYQT6:
            key_t = NativeQt.Key.Key_T
            control = NativeQt.KeyboardModifier.ControlModifier
        else:
            key_t = NativeQt.Key_T
            control = NativeQt.ControlModifier
        QTest.keyClick(view, key_t, control)
        app.processEvents()

        assert window.tabs.tab_widget.count() == before + 1
        assert not any(
            "Ambiguous shortcut overload: Ctrl+T" in message for message in messages
        )
    finally:
        window.disk_timer.stop()
        window.mounted_devices_widget.shutdown()
        window.tabs.shutdown()
        window.close()
        window.deleteLater()
        app.processEvents()
        QtCore.qInstallMessageHandler(previous_handler)


def test_play_pause_shortcut_is_window_wide(app, monkeypatch) -> None:
    monkeypatch.setattr(
        "spin_fm.disk_space.DiskSpaceInfo._run_lsblk",
        staticmethod(lambda: []),
    )
    window = MainWindow(startup_paths=[])
    triggered: list[bool] = []
    try:
        action = window.play_pause_action
        assert action.shortcut().toString() == "Alt+P"
        assert action.shortcutContext() == Qt.WindowShortcut
        assert "Alt+P" in window.audio_player.play_button.toolTip()

        action.triggered.connect(lambda: triggered.append(True))
        action.trigger()
        assert triggered == [True]
        assert window.statusBar().currentMessage() == "No audio track is loaded"
    finally:
        window.disk_timer.stop()
        window.mounted_devices_widget.shutdown()
        window.tabs.shutdown()
        window.close()
        window.deleteLater()
        app.processEvents()


def test_alt_p_key_event_toggles_playback_and_osd_across_focused_widgets(
    app, monkeypatch
) -> None:
    monkeypatch.setattr(
        "spin_fm.disk_space.DiskSpaceInfo._run_lsblk",
        staticmethod(lambda: []),
    )
    if USING_PYQT6:
        from PyQt6.QtTest import QTest
    else:
        from PyQt5.QtTest import QTest

    class FakePlayer:
        def __init__(self) -> None:
            self.pause_calls = 0
            self.play_calls = 0

        def pause(self) -> None:
            self.pause_calls += 1

        def play(self) -> None:
            self.play_calls += 1

        @staticmethod
        def position() -> int:
            return 12_000

    class RecordingOSD:
        available = True

        def __init__(self) -> None:
            self.media: list[tuple[str, str, int, int]] = []

        @staticmethod
        def refresh_availability() -> bool:
            return True

        def notify_media(
            self,
            heading: str,
            detail: str,
            *,
            position_ms: int,
            duration_ms: int,
        ) -> bool:
            self.media.append((heading, detail, position_ms, duration_ms))
            return True

    window = MainWindow(startup_paths=[])
    backend = FakePlayer()
    osd = RecordingOSD()
    player = window.audio_player
    player._player = backend
    player._osd = osd
    player._current_path = "/tmp/sample track.ogg"
    player._track_name = "sample track.ogg"
    player._duration = 60_000
    player._playback_requested = True

    try:
        window.show()
        view = window.tabs.currentView()
        view.setFocus()
        app.processEvents()

        QTest.keyClick(view, Qt.Key_P, Qt.AltModifier)
        app.processEvents()
        assert backend.pause_calls == 1
        assert player._playback_requested is False
        assert osd.media[-1] == (
            "Paused",
            "sample track.ogg",
            12_000,
            60_000,
        )

        window.tabs.address_bar.setFocus()
        app.processEvents()
        QTest.keyClick(window.tabs.address_bar, Qt.Key_P, Qt.AltModifier)
        app.processEvents()
        assert backend.play_calls == 1
        assert player._playback_requested is True
        assert osd.media[-1] == (
            "Playing",
            "sample track.ogg",
            12_000,
            60_000,
        )
    finally:
        player._player = None
        window.disk_timer.stop()
        window.mounted_devices_widget.shutdown()
        window.tabs.shutdown()
        window.close()
        window.deleteLater()
        app.processEvents()



def test_hidden_trash_path_primes_filesystem_model_when_not_indexed(
    app, monkeypatch, tmp_path: Path
) -> None:
    trash_files = tmp_path / ".local" / "share" / "Trash" / "files"
    trash_files.mkdir(parents=True)
    widget = Tabs()

    class Index:
        def __init__(self, valid: bool):
            self._valid = valid

        def isValid(self):
            return self._valid

    calls: list[str] = []
    try:
        monkeypatch.setattr(widget.fs_model, "index", lambda _path: Index(False))
        monkeypatch.setattr(
            widget.fs_model,
            "setRootPath",
            lambda path: calls.append(path) or Index(True),
        )

        index = widget._model_index_for_directory(str(trash_files))

        assert index.isValid()
        assert calls == [str(trash_files)]
    finally:
        widget.shutdown()
        widget.close()
        widget.deleteLater()
        app.processEvents()


def test_trash_toolbar_always_opens_trash(app, monkeypatch, tmp_path: Path) -> None:
    import spin_fm.tabs as tabs_module

    trash_files = tmp_path / "Trash" / "files"
    trash_files.mkdir(parents=True)
    widget = Tabs()
    navigated: list[str] = []
    try:
        monkeypatch.setattr(
            tabs_module, "ensure_trash_directories", lambda: str(trash_files)
        )
        monkeypatch.setattr(tabs_module, "mounted_trash_directories", lambda: ())
        monkeypatch.setattr(widget, "_navigateTo", navigated.append)
        monkeypatch.setattr(
            widget,
            "_confirm_delete",
            lambda _paths: pytest.fail("Trash toolbar must not delete selections"),
        )

        widget.trash_button.click()

        assert widget.trash_button.toolTip() == "Open Trash"
        assert navigated == [str(trash_files)]
    finally:
        widget.shutdown()
        widget.close()
        widget.deleteLater()
        app.processEvents()


def test_drop_is_confirmed_move_and_no_cancels(app, monkeypatch, tmp_path: Path) -> None:
    source = tmp_path / "source.txt"
    source.write_text("payload", encoding="utf-8")
    destination = tmp_path / "destination"
    destination.mkdir()
    widget = Tabs()
    try:
        monkeypatch.setattr(
            QMessageBox,
            "question",
            staticmethod(lambda *_args, **_kwargs: QMessageBox.No),
        )
        assert widget.dropFileOrFolder([str(source)], str(destination)) is False
        assert source.exists()
        assert not (destination / source.name).exists()

        calls: list[tuple[tuple, dict]] = []
        monkeypatch.setattr(
            widget,
            "_transfer_file_or_folder",
            lambda *args, **kwargs: calls.append((args, kwargs)) or True,
        )
        assert widget.dropFileOrFolder([str(source)], str(destination)) is True
        assert calls[0][0][2] == "cut"
        assert calls[0][1]["confirm_title"] == "Confirm Drop"
    finally:
        widget.shutdown()
        widget.close()
        widget.deleteLater()
        app.processEvents()



def test_confirmed_drop_moves_item_like_cut_paste(
    app, monkeypatch, tmp_path: Path
) -> None:
    source = tmp_path / "move-me.txt"
    source.write_text("payload", encoding="utf-8")
    destination = tmp_path / "folder"
    destination.mkdir()
    widget = Tabs()

    def run_now(function, *args, **kwargs):
        progress = kwargs.get("on_progress") if kwargs.get("with_progress") else None
        report = function(*args, progress_callback=progress)
        kwargs["on_result"](report)
        kwargs["on_finished"]()
        return object()

    try:
        monkeypatch.setattr(
            QMessageBox,
            "question",
            staticmethod(lambda *_args, **_kwargs: QMessageBox.Yes),
        )
        monkeypatch.setattr(widget.file_tasks, "submit", run_now)
        monkeypatch.setattr(widget, "refreshCurrentTab", lambda: None)

        assert widget.dropFileOrFolder([str(source)], str(destination)) is True
        assert not source.exists()
        assert (destination / source.name).read_text(encoding="utf-8") == "payload"
        assert widget.is_busy is False
    finally:
        widget.shutdown()
        widget.close()
        widget.deleteLater()
        app.processEvents()

def test_drop_same_name_requires_conflict_decision(
    app, monkeypatch, tmp_path: Path
) -> None:
    source_dir = tmp_path / "source"
    destination = tmp_path / "destination"
    source_dir.mkdir()
    destination.mkdir()
    source = source_dir / "same.txt"
    target = destination / source.name
    source.write_text("new", encoding="utf-8")
    target.write_text("old", encoding="utf-8")
    prompts: list[tuple[str, bool]] = []
    widget = Tabs()
    try:
        monkeypatch.setattr(
            QMessageBox,
            "question",
            staticmethod(lambda *_args, **_kwargs: QMessageBox.Yes),
        )
        monkeypatch.setattr(
            widget,
            "_prompt_overwrite",
            lambda path, is_dir: prompts.append((path, is_dir)) or "no",
        )

        assert widget.dropFileOrFolder([str(source)], str(destination)) is True
        assert prompts == [(str(target), False)]
        assert source.read_text(encoding="utf-8") == "new"
        assert target.read_text(encoding="utf-8") == "old"
    finally:
        widget.shutdown()
        widget.close()
        widget.deleteLater()
        app.processEvents()

def test_audio_activation_uses_embedded_player_signal(
    app, monkeypatch, tmp_path: Path
) -> None:
    audio_file = tmp_path / "sample track.OGG"
    audio_file.write_bytes(b"")
    widget = Tabs()
    requested: list[str] = []
    widget.audio_requested.connect(requested.append)
    try:
        monkeypatch.setattr(widget, "_path_from_index", lambda _index: str(audio_file))
        monkeypatch.setattr(
            widget,
            "_launch_default_application",
            lambda _path: pytest.fail("audio activation should stay inside Spin FM"),
        )

        widget.onFileActivated(object(), widget.currentView())

        assert requested == [str(audio_file)]
    finally:
        widget.shutdown()
        widget.close()
        widget.deleteLater()
        app.processEvents()


def test_single_click_is_selection_only_for_audio_and_other_files(
    app, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    from spin_fm.tabs import Tabs

    audio_file = tmp_path / "single-click.mp3"
    document = tmp_path / "document.txt"
    audio_file.write_bytes(b"")
    document.write_text("hello", encoding="utf-8")
    requested: list[str] = []
    widget = Tabs()
    widget.audio_requested.connect(requested.append)
    try:
        from spin_fm.qt_compat import QtCore

        index = QtCore.QModelIndex()
        view = widget.currentView()
        view.clicked.emit(index)
        assert requested == []

        monkeypatch.setattr(widget, "_path_from_index", lambda _index: str(audio_file))
        widget.onFileActivated(audio_file, widget.currentView())
        assert requested == [str(audio_file)]
    finally:
        widget.shutdown()
        widget.deleteLater()
        app.processEvents()


def test_view_signals_only_activate_on_double_click(
    app, monkeypatch: pytest.MonkeyPatch
) -> None:
    from spin_fm.qt_compat import QtCore
    from spin_fm.tabs import Tabs

    widget = Tabs()
    activated: list[object] = []
    view = widget.currentView()
    try:
        monkeypatch.setattr(
            widget,
            "onFileActivated",
            lambda index, _view=None: activated.append(index),
        )
        index = QtCore.QModelIndex()

        view.clicked.emit(index)
        assert activated == []

        view.doubleClicked.emit(index)
        assert activated == [index]
    finally:
        widget.shutdown()
        widget.close()
        widget.deleteLater()
        app.processEvents()


def test_folder_activation_navigates_in_the_originating_view(
    app, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    from spin_fm.tabs import Tabs

    folder = tmp_path / "opened folder"
    folder.mkdir()
    widget = Tabs()
    view = widget.currentView()
    navigated: list[tuple[str, object]] = []
    try:
        monkeypatch.setattr(widget, "_path_from_index", lambda _index: str(folder))
        monkeypatch.setattr(
            widget,
            "_navigateTo",
            lambda path, **kwargs: navigated.append((path, kwargs.get("view"))),
        )

        widget.onFileActivated(object(), view)

        assert navigated == [(str(folder), view)]
    finally:
        widget.shutdown()
        widget.close()
        widget.deleteLater()
        app.processEvents()


def test_non_audio_activation_uses_desktop_launcher(
    app, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    from spin_fm.tabs import Tabs

    document = tmp_path / "notes.txt"
    document.write_text("hello", encoding="utf-8")
    launched: list[str] = []
    widget = Tabs()
    try:
        monkeypatch.setattr(widget, "_launch_default_application", launched.append)
        widget._open_file_path(str(document))
        assert launched == [str(document)]
    finally:
        widget.shutdown()
        widget.deleteLater()
        app.processEvents()


def test_external_audio_open_bypasses_embedded_player(
    app, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    from spin_fm.tabs import Tabs

    audio_file = tmp_path / "sample.ogg"
    audio_file.write_bytes(b"")
    launched: list[str] = []
    requested: list[str] = []
    widget = Tabs()
    widget.audio_requested.connect(requested.append)
    try:
        monkeypatch.setattr(widget, "_launch_default_application", launched.append)
        widget._open_file_path(str(audio_file), externally=True)
        assert launched == [str(audio_file)]
        assert requested == []
    finally:
        widget.shutdown()
        widget.deleteLater()
        app.processEvents()


def test_audio_player_backend_is_lazy_and_released(app, tmp_path: Path) -> None:
    import wave

    from spin_fm.audio_player import AudioPlayerWidget

    audio_file = tmp_path / "silence.wav"
    with wave.open(str(audio_file), "wb") as output:
        output.setnchannels(1)
        output.setsampwidth(2)
        output.setframerate(8_000)
        output.writeframes(b"\x00\x00" * 800)

    player = AudioPlayerWidget()
    try:
        assert player._player is None
        started = player.play_file(str(audio_file))
        if not started:
            # Some minimal CI images provide PyQt5 itself but omit a shared
            # multimedia backend library. Spin FM must keep browsing usable and
            # report that condition so MainWindow can open the desktop player.
            assert "Qt Multimedia is unavailable" in player.backend_error
            assert player._player is None
            return

        assert player._player is not None
        assert player.current_path == str(audio_file)

        player.close_player()
        assert player._player is None
        assert player.current_path == ""
    finally:
        player.shutdown()
        player.close()
        player.deleteLater()
        app.processEvents()


def test_audio_seek_controls_support_rewind_forward_and_direct_seek(app) -> None:
    from spin_fm.audio_player import AudioPlayerWidget

    class FakePlayer:
        def __init__(self) -> None:
            self.position_value = 25_000

        def position(self) -> int:
            return self.position_value

        def setPosition(self, value: int) -> None:  # noqa: N802 - Qt API shape
            self.position_value = int(value)

        def isSeekable(self) -> bool:  # noqa: N802 - Qt API shape
            return True

        def stop(self) -> None:
            pass

    player = AudioPlayerWidget()
    fake = FakePlayer()
    try:
        player._player = fake
        player._current_path = "/tmp/sample.ogg"
        player._track_name = "sample.ogg"
        player._duration = 60_000
        player.seek_slider.setRange(0, 60_000)
        player._refresh_seek_controls()

        assert player.rewind_button.isEnabled()
        assert player.forward_button.isEnabled()

        player.rewind()
        assert fake.position_value == 15_000
        player.fast_forward()
        assert fake.position_value == 25_000

        player.seek_slider.setValue(48_000)
        assert fake.position_value == 48_000
        assert player.position_label.text() == "0:48"
    finally:
        player._player = None
        player.shutdown()
        player.close()
        player.deleteLater()
        app.processEvents()


def test_toggle_playback_notifies_osd_without_backend_state_signal(
    app, monkeypatch: pytest.MonkeyPatch
) -> None:
    from spin_fm.audio_player import AudioPlayerWidget

    class FakePlayer:
        def __init__(self) -> None:
            self.playing = True
            self.position_value = 12_000
            self.pause_calls = 0
            self.play_calls = 0

        def position(self) -> int:
            return self.position_value

        def setPosition(self, value: int) -> None:  # noqa: N802 - Qt API shape
            self.position_value = int(value)

        def pause(self) -> None:
            self.pause_calls += 1
            self.playing = False

        def play(self) -> None:
            self.play_calls += 1
            self.playing = True

    class RecordingOSD:
        available = True

        def __init__(self) -> None:
            self.media: list[tuple[str, str, int, int]] = []

        @staticmethod
        def refresh_availability() -> bool:
            return True

        def notify_media(
            self,
            heading: str,
            track: str,
            *,
            position_ms: int,
            duration_ms: int,
        ) -> bool:
            self.media.append((heading, track, position_ms, duration_ms))
            return True

    player = AudioPlayerWidget()
    backend = FakePlayer()
    osd = RecordingOSD()
    messages: list[str] = []
    player.status_message.connect(messages.append)
    try:
        player._player = backend
        player._osd = osd
        player._current_path = "/tmp/sample track.ogg"
        player._track_name = "sample track.ogg"
        player._duration = 60_000
        player._playback_requested = True

        assert player.toggle_playback() is True
        assert backend.pause_calls == 1
        assert player._playback_requested is False
        assert osd.media[-1] == (
            "Paused",
            "sample track.ogg",
            12_000,
            60_000,
        )
        assert player.state_label.text() == "Paused"
        assert messages[-1] == "Paused sample track.ogg"

        assert player.toggle_playback() is True
        assert backend.play_calls == 1
        assert player._playback_requested is True
        assert osd.media[-1] == (
            "Playing",
            "sample track.ogg",
            12_000,
            60_000,
        )
        assert player.state_label.text() == "Playing"
        assert messages[-1] == "Playing sample track.ogg"
    finally:
        player._player = None
        player.shutdown()
        player.close()
        player.deleteLater()
        app.processEvents()


def test_audio_player_ignores_unexpected_osd_adapter_failures(app) -> None:
    from spin_fm.audio_player import AudioPlayerWidget

    class RaisingOSD:
        available = True

        def notify_media(self, *_args, **_kwargs):
            raise RuntimeError("simulated media OSD failure")

        def notify_volume(self, *_args, **_kwargs):
            raise RuntimeError("simulated volume OSD failure")

    player = AudioPlayerWidget()
    try:
        player._osd = RaisingOSD()
        assert player.osd_available is True

        player._notify_osd_media("Playing", track="sample.ogg")
        player._notify_osd_volume()
    finally:
        player.shutdown()
        player.close()
        player.deleteLater()
        app.processEvents()


def test_audio_player_discards_stale_delayed_osd_events(app) -> None:
    from spin_fm.audio_player import AudioPlayerWidget

    class RecordingOSD:
        available = True

        @staticmethod
        def refresh_availability() -> bool:
            return True

        def __init__(self) -> None:
            self.media: list[tuple[str, str]] = []

        def notify_media(self, heading: str, track: str, **_kwargs: object) -> bool:
            self.media.append((heading, track))
            return True

        @staticmethod
        def notify_volume(*_args: object, **_kwargs: object) -> bool:
            return True

    player = AudioPlayerWidget()
    osd = RecordingOSD()
    try:
        player._osd = osd
        player._pending_osd_media = ("Seeking", "old.ogg", 1_000, 2_000)
        player._pending_seek_heading = "Rewind 10 seconds"
        for timer in (
            player._osd_retry_timer,
            player._seek_osd_timer,
            player._volume_osd_timer,
            player._volume_osd_retry_timer,
        ):
            timer.start(5_000)

        player.notify_external_open("/tmp/new track.ogg")

        assert player._pending_osd_media is None
        assert player._pending_seek_heading == "Seeking"
        assert not player._seek_osd_timer.isActive()
        assert not player._volume_osd_timer.isActive()
        assert not player._volume_osd_retry_timer.isActive()
        assert osd.media == [("Opening externally", "new track.ogg")]
    finally:
        player.shutdown()
        player.close()
        player.deleteLater()
        app.processEvents()


def test_file_view_uses_wrapped_non_elided_full_name_layout(app) -> None:
    from spin_fm.tabs import FullNameIconDelegate

    widget = Tabs()
    try:
        view = widget.currentView()
        assert view is not None
        assert view.wordWrap() is True
        assert view.uniformItemSizes() is False
        assert view.gridSize().isEmpty()
        assert view.textElideMode() == Qt.ElideNone
        assert isinstance(view.itemDelegate(), FullNameIconDelegate)

        from spin_fm.qt_compat import QStyleOptionViewItem, QtGui

        model = QtGui.QStandardItemModel(view)
        model.appendRow(QtGui.QStandardItem("Downloads"))
        model.appendRow(
            QtGui.QStandardItem(
                "a-very-long-folder-name-that-must-wrap-without-being-elided"
            )
        )
        view.setModel(model)
        option = QStyleOptionViewItem()
        option.font = view.font()
        option.decorationSize = view.iconSize()
        delegate = view.itemDelegate()
        short_size = delegate.sizeHint(option, model.index(0, 0))
        long_size = delegate.sizeHint(option, model.index(1, 0))
        assert long_size.height() > short_size.height()
        assert long_size.width() == short_size.width()
    finally:
        widget.shutdown()
        widget.close()
        widget.deleteLater()
        app.processEvents()


def test_trash_toolbar_can_open_mounted_trash(app, monkeypatch, tmp_path: Path) -> None:
    import spin_fm.tabs as tabs_module

    home = tmp_path / "home" / "Trash" / "files"
    usb = tmp_path / "media" / "USB" / ".Trash-1000" / "files"
    home.mkdir(parents=True)
    usb.mkdir(parents=True)
    widget = Tabs()
    navigated: list[str] = []
    try:
        monkeypatch.setattr(tabs_module, "ensure_trash_directories", lambda: str(home))
        monkeypatch.setattr(
            tabs_module, "mounted_trash_directories", lambda: (str(usb),)
        )
        monkeypatch.setattr(
            tabs_module, "trash_mount_point", lambda _path: str(usb.parents[1])
        )
        captured = []

        def choose(_parent, locations):
            captured.extend(locations)
            return str(usb)

        monkeypatch.setattr(tabs_module.TrashLocationDialog, "choose", choose)
        monkeypatch.setattr(widget, "_navigateTo", navigated.append)

        widget.trash_button.click()

        assert navigated == [str(usb)]
        assert [location.name for location in captured] == ["Home Trash", "USB Trash"]
        assert captured[1].path == str(usb)
        assert captured[1].detail == f"Mounted filesystem: {usb.parents[1]}"
        assert captured[1].removable is True
    finally:
        widget.shutdown()
        widget.close()
        widget.deleteLater()
        app.processEvents()


def test_trash_location_dialog_is_large_readable_and_unelided(app, tmp_path: Path) -> None:
    from spin_fm.dialogs import TrashLocation, TrashLocationDialog

    home = tmp_path / "home" / ".local" / "share" / "Trash" / "files"
    usb = (
        tmp_path
        / "media"
        / "A USB volume with a deliberately long readable name"
        / ".Trash-1000"
        / "files"
    )
    locations = (
        TrashLocation("Home Trash", str(home), "User profile"),
        TrashLocation(
            "A USB volume with a deliberately long readable name Trash",
            str(usb),
            f"Mounted filesystem: {usb.parents[2]}",
            True,
        ),
    )
    dialog = TrashLocationDialog(locations)
    try:
        assert TrashLocationDialog.MINIMUM_SIZE.width() == 720
        assert TrashLocationDialog.MINIMUM_SIZE.height() == 360
        assert TrashLocationDialog.INITIAL_SIZE.width() == 860
        assert TrashLocationDialog.INITIAL_SIZE.height() == 460
        assert dialog.width() >= dialog.minimumWidth()
        assert dialog.height() >= dialog.minimumHeight()
        assert dialog.location_table.wordWrap() is True
        assert dialog.location_table.alternatingRowColors() is False
        assert dialog.location_table.textElideMode() == Qt.ElideNone
        assert dialog.location_table.horizontalHeaderItem(0).text() == "Location"
        assert dialog.location_table.horizontalHeaderItem(1).text() == "Folder"
        assert dialog.location_table.item(1, 1).text() == str(usb)
        assert "Mounted filesystem:" in dialog.location_table.item(1, 0).text()
        dialog.location_table.selectRow(1)
        assert dialog.selected_path() == str(usb)
        assert dialog.open_button is not None
        assert dialog.open_button.text() == "Open Trash"
    finally:
        dialog.close()
        dialog.deleteLater()
        app.processEvents()


def test_trash_location_dialog_second_row_is_themed_before_selection(app) -> None:
    from spin_fm.dialogs import TrashLocation, TrashLocationDialog

    previous_stylesheet = app.styleSheet()
    dark_theme = (
        Path(__file__).resolve().parents[1]
        / "src"
        / "spin_fm"
        / "themes"
        / "dark.css"
    ).read_text(encoding="utf-8")
    app.setStyleSheet(dark_theme)

    dialog = TrashLocationDialog(
        (
            TrashLocation(
                "Home Trash",
                "/home/user/.local/share/Trash/files",
                "User profile",
            ),
            TrashLocation(
                "USB Trash",
                "/media/user/USB/.Trash-1000/files",
                "Mounted filesystem: /media/user/USB",
                True,
            ),
        )
    )
    try:
        dialog.show()
        app.processEvents()

        table = dialog.location_table
        assert table.currentRow() == 0
        second_row = table.visualItemRect(table.item(1, 1))
        sample_point = second_row.center()
        sample_point.setX(second_row.right() - 12)
        pixel = table.viewport().grab().toImage().pixelColor(sample_point)

        # The regression painted this unselected row #f7f7f7 under dark themes.
        assert max(pixel.red(), pixel.green(), pixel.blue()) < 160
    finally:
        dialog.close()
        dialog.deleteLater()
        app.setStyleSheet(previous_stylesheet)
        app.processEvents()


def test_devices_sidebar_reserves_space_for_mount_actions(app) -> None:
    from spin_fm.disk_space import DeviceInfo
    from spin_fm.mounted_devices_widget import MountedDevicesWidget

    widget = MountedDevicesWidget()
    widget._refresh_timer.stop()
    device = DeviceInfo(
        device_node="/dev/sdz1",
        mount_point="/media/user/A long mounted volume name",
        fs_type="ext4",
        label="A long mounted volume name",
        model="USB storage",
        size_bytes=32 * 1024**3,
    )
    try:
        widget.populate_table((device,))
        widget.resize(widget.MINIMUM_WIDTH, 480)
        widget.show()
        app.processEvents()

        button = widget.table_widget.cellWidget(0, 2)
        assert widget.minimumWidth() == widget.MINIMUM_WIDTH
        assert widget.maximumWidth() == widget.MAXIMUM_WIDTH
        assert widget.table_widget.columnWidth(2) == widget.ACTION_COLUMN_WIDTH
        assert button is not None
        assert button.width() >= widget.ACTION_BUTTON_WIDTH
        assert button.text() == "Unmount"
        assert widget.table_widget.horizontalHeaderItem(2).text() == "Action"
    finally:
        widget.shutdown()
        widget.close()
        widget.deleteLater()
        app.processEvents()


def test_first_run_icon_theme_prefers_adwaita(app, monkeypatch) -> None:
    from spin_fm.icon_theme_manager import IconThemeManager

    manager = IconThemeManager()
    monkeypatch.setattr(
        manager,
        "get_available_icon_themes",
        lambda refresh=False: ["Breeze", "hicolor", "Adwaita"],
    )
    assert manager.resolve_theme("") == "Adwaita"
    assert manager.resolve_theme("Breeze") == "Breeze"


def test_task_manager_releases_completed_payload_references(app) -> None:
    manager = TaskManager(max_threads=1, max_tasks=1)
    payload = bytearray(2 * 1024 * 1024)
    worker = manager.submit(lambda value: len(value), payload)
    assert worker is not None

    _drain_events(app, lambda: manager.is_busy)

    assert worker.function is None
    assert worker.args == ()
    assert worker.kwargs == {}
    assert manager.active_count == 0
    assert manager.shutdown(wait_msec=1000)
