from __future__ import annotations

import time
from pathlib import Path

import pytest

try:
    from spin_fm.disk_space import DiskSpaceInfo
    from spin_fm.file_info_extension import install
    from spin_fm.main_window import MainWindow
    from spin_fm.qt_compat import QApplication, Qt

    try:
        from PyQt6.QtTest import QTest
    except ImportError:
        from PyQt5.QtTest import QTest
except ImportError:
    pytest.skip("PyQt5/PyQt6 is not installed", allow_module_level=True)


@pytest.fixture(scope="module")
def app():
    instance = QApplication.instance() or QApplication(["spin-fm-file-info-tests"])
    yield instance
    instance.processEvents()


def _process_until(app, predicate, timeout: float = 5.0) -> None:
    deadline = time.monotonic() + timeout
    while not predicate() and time.monotonic() < deadline:
        app.processEvents()
        time.sleep(0.01)
    assert predicate()


def _click_index(app, view, index) -> None:
    view.scrollTo(index)
    _process_until(
        app,
        lambda: view.visualRect(index).isValid()
        and not view.visualRect(index).isEmpty(),
    )
    QTest.mouseClick(
        view.viewport(), Qt.LeftButton, pos=view.visualRect(index).center()
    )
    app.processEvents()


def _shutdown_window(app, window, integration) -> None:
    integration.shutdown()
    window.mounted_devices_widget.shutdown()
    window.tabs.shutdown()
    window.background_tasks.shutdown(wait_msec=6_000)
    window.close()
    window.deleteLater()
    app.processEvents()


def test_clicked_signal_populates_location_size_and_status(
    app, monkeypatch, tmp_path: Path
) -> None:
    monkeypatch.setattr(DiskSpaceInfo, "_run_lsblk", staticmethod(lambda: []))
    selected = tmp_path / "selected file.txt"
    selected.write_text("hello", encoding="utf-8")

    window = MainWindow(startup_paths=[])
    window.disk_timer.stop()
    integration = install(window)
    assert integration is not None
    window.resize(1_000, 700)
    window.show()

    try:
        window.tabs._navigateTo(str(tmp_path))
        app.processEvents()
        view = window.tabs.currentView()
        index = window.tabs.fs_model.index(str(selected))
        _process_until(app, index.isValid)

        assert not integration.event_filter_installed
        assert integration.direct_signal_integration_active
        assert integration.connected_view_count == 1
        assert integration._status_label is not None
        assert integration._status_label.objectName() == "fileInfoStatusLabel"

        serial_before = integration._serial
        view.clicked.emit(index)
        _process_until(
            app,
            lambda: "File type:" in integration._status_label.full_text
            and "Name: selected file.txt" in integration._status_label.full_text,
        )

        assert integration._serial == serial_before + 1
        assert window.tabs.address_bar.text() == str(selected.resolve())
        status = integration._status_label.full_text
        assert "Size:" in status
        assert "Size:" in integration._status_label.text()
        assert "Last modified:" in status
        assert "File type:" in status

        window.show_status("Copying selected files…", 0)
        app.processEvents()
        assert window.status_bar.currentMessage() == "Copying selected files…"
        assert not integration._status_label.isVisible()
        window.status_bar.clearMessage()
        app.processEvents()
        assert integration._status_label.isVisible()
        assert "Size:" in integration._status_label.text()
    finally:
        _shutdown_window(app, window, integration)


def test_real_mouse_click_uses_the_bound_qt_signal(
    app, monkeypatch, tmp_path: Path
) -> None:
    monkeypatch.setattr(DiskSpaceInfo, "_run_lsblk", staticmethod(lambda: []))
    selected = tmp_path / "drag-source.bin"
    selected.write_bytes(b"x" * 2048)

    window = MainWindow(startup_paths=[])
    window.disk_timer.stop()
    integration = install(window)
    assert integration is not None
    window.resize(1_000, 700)
    window.show()

    try:
        window.tabs._navigateTo(str(tmp_path))
        app.processEvents()
        view = window.tabs.currentView()
        index = window.tabs.fs_model.index(str(selected))
        _process_until(app, index.isValid)
        view.scrollTo(index)
        _process_until(
            app,
            lambda: view.visualRect(index).isValid()
            and not view.visualRect(index).isEmpty(),
        )

        serial_before = integration._serial
        _click_index(app, view, index)
        _process_until(
            app,
            lambda: "File type:" in integration._status_label.full_text
            and "Name: drag-source.bin" in integration._status_label.full_text,
        )

        assert integration._serial == serial_before + 1
        assert window.tabs.address_bar.text() == str(selected.resolve())
        assert "Size: 0.002 MiB Name: drag-source.bin" in (
            integration._status_label.full_text
        )
        assert "KiB" not in integration._status_label.full_text
        assert "bytes" not in integration._status_label.full_text
        assert "Path:" not in integration._status_label.full_text
    finally:
        _shutdown_window(app, window, integration)


def test_future_tab_is_bound_once_and_reports_size(
    app, monkeypatch, tmp_path: Path
) -> None:
    monkeypatch.setattr(DiskSpaceInfo, "_run_lsblk", staticmethod(lambda: []))
    first_folder = tmp_path / "first"
    second_folder = tmp_path / "second"
    first_folder.mkdir()
    second_folder.mkdir()
    selected = second_folder / "payload.bin"
    selected.write_bytes(b"x" * 4096)

    window = MainWindow(startup_paths=[])
    window.disk_timer.stop()
    integration = install(window)
    assert integration is not None
    window.resize(1_000, 700)
    window.show()

    try:
        window.tabs._navigateTo(str(first_folder))
        tab_index = window.tabs.createNewTab(str(second_folder))
        app.processEvents()

        view = window.tabs.tab_widget.widget(tab_index)
        index = window.tabs.fs_model.index(str(selected))
        _process_until(app, index.isValid)

        assert not integration.event_filter_installed
        assert integration.direct_signal_integration_active
        assert integration.connected_view_count == 2
        assert hasattr(integration, "_view_slots")

        serial_before = integration._serial
        view.clicked.emit(index)
        _process_until(
            app,
            lambda: "File type:" in integration._status_label.full_text
            and "Name: payload.bin" in integration._status_label.full_text,
        )

        assert integration._serial == serial_before + 1
        status = integration._status_label.full_text
        assert "Size: 0.004 MiB Name: payload.bin" in status
        assert "KiB" not in status
        assert "bytes" not in status
        assert "Path:" not in status
        assert window.tabs.address_bar.text() == str(selected.resolve())
    finally:
        _shutdown_window(app, window, integration)


def test_folder_click_reports_recursive_size(app, monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setattr(DiskSpaceInfo, "_run_lsblk", staticmethod(lambda: []))
    selected = tmp_path / "selected-folder"
    nested = selected / "nested"
    nested.mkdir(parents=True)
    (selected / "one.bin").write_bytes(b"1" * 1024)
    (nested / "two.bin").write_bytes(b"2" * 2048)

    window = MainWindow(startup_paths=[])
    window.disk_timer.stop()
    integration = install(window)
    assert integration is not None
    window.resize(1_000, 700)
    window.show()

    try:
        window.tabs._navigateTo(str(tmp_path))
        app.processEvents()
        view = window.tabs.currentView()
        index = window.tabs.fs_model.index(str(selected))
        _process_until(app, index.isValid)

        view.clicked.emit(index)
        _process_until(
            app,
            lambda: "Folder size:" in integration._status_label.full_text,
        )

        status = integration._status_label.full_text
        assert "Folder size: 0.003 MiB Name: selected-folder" in status
        assert "KiB" not in status
        assert "bytes" not in status
        assert "Path:" not in status
        assert "Contents: 3 items (2 files, 1 folder)" in status
        assert "Folder size:" in integration._status_label.text()
        assert window.tabs.address_bar.text() == str(selected.resolve())
    finally:
        _shutdown_window(app, window, integration)
