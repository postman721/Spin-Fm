from __future__ import annotations

import os
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

from spin_fm import file_info_extension as extension

ROOT = Path(__file__).resolve().parents[1]


class _AddressBar:
    def __init__(self) -> None:
        self.text = ""

    def setText(self, value: str) -> None:  # noqa: N802 - Qt-shaped test double
        self.text = value


class _Index:
    def __init__(self, row: int = 0) -> None:
        self._row = row

    def isValid(self) -> bool:  # noqa: N802 - Qt-shaped test double
        return True

    def row(self) -> int:
        return self._row

    def parent(self):
        return None


class _Model:
    def __init__(self, path: Path) -> None:
        self.path = str(path)

    def index(self, row: int, column: int, parent):
        del row, column, parent
        return _Index()

    def filePath(self, index) -> str:  # noqa: N802 - Qt-shaped test double
        del index
        return self.path


class _View:
    def __init__(self, path: Path) -> None:
        self._model = _Model(path)

    def model(self):
        return self._model


class _Signal:
    def __init__(self) -> None:
        self.slots = []

    def connect(self, slot) -> None:
        self.slots.append(slot)

    def disconnect(self, slot) -> None:
        self.slots.remove(slot)

    def emit(self, *args) -> None:
        for slot in tuple(self.slots):
            slot(*args)


class _BindableView(_View):
    def __init__(self, path: Path) -> None:
        super().__init__(path)
        self.clicked = _Signal()
        self.destroyed = _Signal()


def test_inspect_path_formats_size_time_and_mime(tmp_path: Path, monkeypatch) -> None:
    sample = tmp_path / "sample.bin"
    sample.write_bytes(b"x" * 1536)
    os.utime(sample, (1_700_000_000, 1_700_000_000))
    monkeypatch.setattr(
        extension,
        "_python_magic_mime",
        lambda _path: "application/x-spin-test; charset=binary",
    )

    details = extension.inspect_path(sample)
    message = extension.format_file_details(details)

    assert details.path == str(sample.resolve())
    assert details.size_bytes == 1536
    assert details.mime_type == "application/x-spin-test; charset=binary"
    assert "0.001 MiB (1.50 KiB, 1,536 bytes)" in message
    assert "Last modified:" in message
    assert "File type: application/x-spin-test; charset=binary" in message


def test_inspect_directory_reports_recursive_content_size(tmp_path: Path) -> None:
    folder = tmp_path / "folder"
    nested = folder / "nested"
    nested.mkdir(parents=True)
    (folder / "one.bin").write_bytes(b"1" * 5)
    (nested / "two.bin").write_bytes(b"2" * 7)

    details = extension.inspect_path(folder)
    message = extension.format_file_details(details)

    assert details.is_directory
    assert details.size_bytes == 12
    assert details.file_count == 2
    assert details.folder_count == 1
    assert details.skipped_items == 0
    assert details.mime_type == "inode/directory"
    assert "Folder size:" in message
    assert "12 bytes" in message
    assert "Contents: 3 items (2 files, 1 folder)" in message


def test_cancelled_directory_scan_stops_before_work(tmp_path: Path) -> None:
    folder = tmp_path / "folder"
    folder.mkdir()
    cancel_event = extension.threading.Event()
    cancel_event.set()

    with pytest.raises(extension._InspectionCancelled):
        extension.inspect_path(folder, cancel_event)


def test_detect_mime_handles_directories_without_content_probe(tmp_path: Path) -> None:
    assert extension.detect_mime_type(str(tmp_path), tmp_path.stat().st_mode) == (
        "inode/directory"
    )


def test_detect_mime_uses_extension_before_file_command(
    tmp_path: Path, monkeypatch
) -> None:
    sample = tmp_path / "track.ogg"
    sample.write_bytes(b"not a real stream")
    monkeypatch.setattr(extension, "_python_magic_mime", lambda _path: "")
    monkeypatch.setattr(
        extension,
        "_file_command_mime",
        lambda _path: (_ for _ in ()).throw(AssertionError("unexpected file(1) call")),
    )
    assert extension.detect_mime_type(str(sample), sample.stat().st_mode) == "audio/ogg"


def test_broken_python_magic_cannot_suppress_file_size(
    tmp_path: Path, monkeypatch
) -> None:
    sample = tmp_path / "selected.txt"
    sample.write_bytes(b"Spin FM")

    def broken_magic(_path: str) -> str:
        raise RuntimeError("libmagic database is unavailable")

    monkeypatch.setattr(extension, "_python_magic_mime", broken_magic)
    details = extension.inspect_path(sample)
    message = extension.format_file_details(details)

    assert details.size_bytes == 7
    assert details.mime_type == "text/plain"
    assert message.startswith("Size:")
    assert "7 bytes" in message


def test_python_magic_official_class_api_preserves_encoding(
    tmp_path: Path, monkeypatch
) -> None:
    sample = tmp_path / "content-without-extension"
    sample.write_bytes(b"Spin FM\n")
    calls: list[tuple[bool, bool]] = []
    closed: list[bool] = []

    class MagicDetector:
        def __init__(self, *, mime: bool, mime_encoding: bool = False) -> None:
            calls.append((mime, mime_encoding))

        def from_file(self, path) -> bytes:
            assert path == str(sample)
            return b"text/plain; charset=us-ascii"

        def close(self) -> None:
            closed.append(True)

    monkeypatch.setitem(sys.modules, "magic", SimpleNamespace(Magic=MagicDetector))

    assert extension._python_magic_mime(str(sample)) == ("text/plain; charset=us-ascii")
    assert calls == [(True, True)]
    assert closed == [True]


def test_python_magic_module_api_is_supported(tmp_path: Path, monkeypatch) -> None:
    sample = tmp_path / "document"
    sample.write_bytes(b"%PDF-1.7\n")
    calls: list[tuple[object, bool]] = []

    def from_file(path, mime=True):
        calls.append((path, mime))
        return "application/pdf"

    monkeypatch.setitem(sys.modules, "magic", SimpleNamespace(from_file=from_file))

    assert extension._python_magic_mime(str(sample)) == "application/pdf"
    assert calls == [(str(sample), True)]


def test_python_magic_structured_and_legacy_apis_are_supported(
    tmp_path: Path, monkeypatch
) -> None:
    sample = tmp_path / "track"
    sample.write_bytes(b"OggS")

    structured = SimpleNamespace(
        detect_from_filename=lambda _path: SimpleNamespace(
            mime_type="audio/ogg", encoding="binary"
        )
    )
    monkeypatch.setitem(sys.modules, "magic", structured)
    assert extension._python_magic_mime(str(sample)) == ("audio/ogg; charset=binary")

    class Cookie:
        loaded = False
        closed = False

        def load(self) -> None:
            self.loaded = True

        def file(self, _path) -> str:
            assert self.loaded
            return "audio/ogg; charset=binary"

        def close(self) -> None:
            self.closed = True

    cookie = Cookie()
    legacy = SimpleNamespace(MAGIC_MIME=0x410, open=lambda _flags: cookie)
    monkeypatch.setitem(sys.modules, "magic", legacy)
    assert extension._python_magic_mime(str(sample)) == ("audio/ogg; charset=binary")
    assert cookie.closed


def test_installed_python_magic_detects_content(tmp_path: Path) -> None:
    pytest.importorskip("magic")
    sample = tmp_path / "content-without-extension"
    sample.write_bytes(b"Spin FM python3-magic integration\n")

    detected = extension._python_magic_mime(str(sample))

    assert detected.startswith("text/plain"), detected


def test_parent_directory_keeps_root_stable(tmp_path: Path) -> None:
    nested = tmp_path / "one" / "two"
    assert extension.parent_directory(nested) == str(nested.parent.resolve())
    assert extension.parent_directory(os.sep) == os.path.abspath(os.sep)


def test_click_handler_updates_location_and_queues_latest_request(
    tmp_path: Path,
) -> None:
    sample = tmp_path / "selected.txt"
    sample.write_text("hello", encoding="utf-8")
    view = _View(sample)
    address_bar = _AddressBar()
    tabs = SimpleNamespace(address_bar=address_bar, currentView=lambda: view)

    integration = extension.FileInfoExtension.__new__(extension.FileInfoExtension)
    integration.window = SimpleNamespace()
    integration.tabs = tabs
    integration._shutting_down = False
    integration._serial = 0
    integration._latest_path = ""
    integration._latest_view_id = 0
    integration._pending_request = None
    integration._active_request = None
    integration.filepath = ""
    integration.info = None
    integration.basic = ""
    messages: list[str] = []
    integration._show_status = lambda message, timeout=0: messages.append(message)
    integration._start_pending_request = lambda: None

    integration.on_treeview2_clicked(_Index(), view)

    resolved = str(sample.resolve())
    assert integration.filepath == resolved
    assert integration.basic == sample.name
    assert address_bar.text == resolved
    assert integration._pending_request.path == resolved
    assert integration._pending_request.view_id == id(view)
    assert not integration._pending_request.cancel_event.is_set()
    assert messages == [f"Reading file information for {sample.name}…"]


def test_direct_view_binding_calls_click_handler_once(tmp_path: Path) -> None:
    sample = tmp_path / "selected.txt"
    sample.write_text("hello", encoding="utf-8")
    view = _BindableView(sample)

    integration = extension.FileInfoExtension.__new__(extension.FileInfoExtension)
    integration._shutting_down = False
    integration._view_slots = {}
    received = []
    integration.on_treeview2_clicked = lambda index, bound_view: received.append(
        (index, bound_view)
    )

    assert integration._bind_view(view)
    assert not integration._bind_view(view)
    assert integration.connected_view_count == 1

    index = _Index()
    view.clicked.emit(index)

    assert received == [(index, view)]
    assert len(view.clicked.slots) == 1


def test_show_status_updates_normal_status_widget() -> None:
    class Label:
        def __init__(self) -> None:
            self.full_text = ""
            self.visible = False

        def set_full_text(self, value: str) -> None:
            self.full_text = value

        def show(self) -> None:
            self.visible = True

    class StatusBar:
        def __init__(self) -> None:
            self.clear_count = 0

        def clearMessage(self) -> None:  # noqa: N802 - Qt-shaped test double
            self.clear_count += 1

    displayed = []
    status_bar = StatusBar()
    integration = extension.FileInfoExtension.__new__(extension.FileInfoExtension)
    integration._status_label = Label()
    integration.window = SimpleNamespace(
        status_bar=status_bar,
        show_status=lambda message, timeout=0: displayed.append((message, timeout)),
    )

    integration._show_status("Size: 42 bytes")

    assert integration._status_label.full_text == "Size: 42 bytes"
    assert integration._status_label.visible
    assert status_bar.clear_count == 1
    assert displayed == []


def test_legacy_changed_callback_delegates_to_existing_navigation(
    tmp_path: Path,
) -> None:
    child = tmp_path / "child"
    child.mkdir()

    class Tabs:
        def __init__(self) -> None:
            self.path = str(child)

        def currentPath(self) -> str:  # noqa: N802 - Qt-shaped test double
            return self.path

        def _navigateTo(self, path: str) -> None:
            self.path = path

    integration = extension.FileInfoExtension.__new__(extension.FileInfoExtension)
    integration.tabs = Tabs()
    statuses: list[str] = []
    integration._show_status = lambda message, timeout=0: statuses.append(message)

    assert integration.changed(False) == str(tmp_path.resolve())
    assert statuses == [str(tmp_path.resolve())]
    assert integration.changed(True) is None


def test_packaging_routes_through_main_bootstrap() -> None:
    launcher = (ROOT / "bin" / "spin-fm").read_text(encoding="utf-8")
    main_source = (ROOT / "main.py").read_text(encoding="utf-8")
    app_source = (ROOT / "src" / "spin_fm" / "app.py").read_text(encoding="utf-8")
    install_manifest = (ROOT / "debian" / "install").read_text(encoding="utf-8")
    control = (ROOT / "debian" / "control").read_text(encoding="utf-8")
    extension_source = (ROOT / "src" / "spin_fm" / "file_info_extension.py").read_text(
        encoding="utf-8"
    )

    assert "../main.py" in launcher
    assert "/usr/share/spin-fm/main.py" in launcher
    assert "extension_main.py" not in launcher
    assert "window_setup=install_file_info" in main_source
    assert "window_setup(window)" in app_source
    assert "main.py usr/share/spin-fm" in install_manifest
    assert "extension_main.py" not in install_manifest
    assert "python3-magic" in control
    assert "clicked_signal.connect(clicked)" in extension_source
    assert "installEventFilter" not in extension_source
    assert "fileInfoStatusLabel" in extension_source
    assert "status_bar.insertWidget(0, label, 1)" in extension_source
    assert "Folder size:" in extension_source
    assert "install_main_window_extension" not in extension_source
    assert "_view_slots" in extension_source
