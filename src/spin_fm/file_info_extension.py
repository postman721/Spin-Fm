"""Selected-file and folder information integration for Spin FM.

The original Spin FM click handler mixed navigation, global state, filesystem
inspection, and UI updates in the main window. This module keeps the feature
independent while integrating it through each real file view's
``clicked(QModelIndex)`` signal:

* a single click copies the selected path into the location bar;
* file size, recursive folder size, modification time, and MIME information are
  shown in the status bar;
* expensive MIME and directory scans run in one bounded background worker;
* a newer click cancels an older directory scan and retains only the latest
  pending request;
* current and future tabs are bound once, without a fragile application-wide
  mouse event filter;
* the legacy ``changed(current)`` parent-navigation callback remains available;
* ``main.py`` attaches the module through :func:`install` after creating the
  application window.

The module deliberately has no Qt import at module-import time. This preserves
fast ``--help``/``--version`` handling and lets the metadata helpers be tested on
systems where Qt is not installed.
"""

from __future__ import annotations

import logging
import mimetypes
import os
import shutil
import stat
import subprocess
import threading
import time
import weakref
from dataclasses import dataclass
from typing import Any, Callable

logger = logging.getLogger(__name__)

_DISABLED_VALUES = frozenset({"0", "false", "no", "off"})
_FILE_COMMAND_TIMEOUT_SECONDS = 1.5
_STATUS_TIMEOUT_MSEC = 0


@dataclass(frozen=True, slots=True)
class FileDetails:
    """A compact, immutable result returned by the inspection worker."""

    path: str
    stat_result: os.stat_result
    mime_type: str
    content_size_bytes: int | None = None
    file_count: int = 0
    folder_count: int = 0
    skipped_items: int = 0

    @property
    def size_bytes(self) -> int:
        if self.content_size_bytes is not None:
            return int(self.content_size_bytes)
        return int(self.stat_result.st_size)

    @property
    def is_directory(self) -> bool:
        return stat.S_ISDIR(self.stat_result.st_mode)

    @property
    def modified_time(self) -> float:
        return float(self.stat_result.st_mtime)


@dataclass(frozen=True, slots=True)
class _InspectionRequest:
    serial: int
    path: str
    view_id: int
    cancel_event: threading.Event


class _InspectionCancelled(RuntimeError):
    """Raised internally when a newer click supersedes a folder scan."""


def _magic_text(value: Any) -> str:
    """Return a clean text value from one python-magic result field."""
    if value is None:
        return ""
    if isinstance(value, bytes):
        return value.decode("utf-8", errors="replace").strip()
    if isinstance(value, str):
        return value.strip()
    return ""


def _combine_magic_fields(mime_type: Any, encoding: Any = None) -> str:
    """Combine MIME and encoding fields returned by structured magic APIs."""
    mime_text = _magic_text(mime_type)
    encoding_text = _magic_text(encoding)
    if not mime_text:
        return ""
    if not encoding_text or "charset=" in mime_text.lower():
        return mime_text
    return f"{mime_text}; charset={encoding_text}"


def _normalize_magic_result(result: Any) -> str:
    """Normalize strings and structured results from python-magic variants."""
    direct = _magic_text(result)
    if direct:
        return direct

    if isinstance(result, dict):
        return _combine_magic_fields(
            result.get("mime_type") or result.get("mime"),
            result.get("encoding") or result.get("mime_encoding"),
        )

    mime_type = getattr(result, "mime_type", None)
    if mime_type is None:
        mime_type = getattr(result, "mime", None)
    encoding = getattr(result, "encoding", None)
    if encoding is None:
        encoding = getattr(result, "mime_encoding", None)
    structured = _combine_magic_fields(mime_type, encoding)
    if structured:
        return structured

    # Some alternative bindings return ``(mime_type, encoding, description)``.
    if isinstance(result, (tuple, list)) and result:
        return _combine_magic_fields(
            result[0],
            result[1] if len(result) > 1 else None,
        )
    return ""


def _magic_file_method(detector: Any) -> Any | None:
    """Return a filename detector method from a python-magic object."""
    for name in ("from_file", "file", "id_filename"):
        method = getattr(detector, name, None)
        if callable(method):
            return method
    return None


def _call_magic_file(method: Any, path: str) -> str:
    """Call one bound detector method, including old bytes-path bindings."""
    try:
        return _normalize_magic_result(method(path))
    except (TypeError, UnicodeError):
        return _normalize_magic_result(method(os.fsencode(path)))


def _close_magic_detector(detector: Any) -> None:
    close = getattr(detector, "close", None)
    if callable(close):
        try:
            close()
        except Exception:
            logger.debug("Unable to close python-magic detector", exc_info=True)


def _python_magic_mime(path: str) -> str:
    """Return MIME information through supported python-magic APIs.

    Debian's ``python3-magic`` currently exposes the upstream ``Magic`` class
    and module-level ``from_file`` helper.  Other distributions still ship the
    legacy cookie API or a structured ``detect_from_filename`` function.  The
    adapter deliberately tries each API without assuming that another package
    named ``magic`` implements the same surface.
    """
    try:
        import magic  # type: ignore[import-not-found]
    except (ImportError, OSError):
        return ""

    # Preferred upstream class API. Requesting both fields preserves the old
    # ``MAGIC_MIME`` behaviour (for example ``text/plain; charset=us-ascii``).
    magic_class = getattr(magic, "Magic", None)
    if callable(magic_class):
        constructors: list[tuple[tuple[Any, ...], dict[str, Any]]] = [
            ((), {"mime": True, "mime_encoding": True}),
            ((), {"mime": True}),
        ]
        mime_type_flag = getattr(magic, "MAGIC_MIME_TYPE", None)
        mime_encoding_flag = getattr(magic, "MAGIC_MIME_ENCODING", None)
        if isinstance(mime_type_flag, int):
            flags = mime_type_flag
            if isinstance(mime_encoding_flag, int):
                flags |= mime_encoding_flag
            constructors.extend(
                [
                    ((), {"flags": flags}),
                    ((flags,), {}),
                ]
            )

        for args, kwargs in constructors:
            detector = None
            try:
                detector = magic_class(*args, **kwargs)
                method = _magic_file_method(detector)
                if method is None:
                    continue
                result = _call_magic_file(method, path)
                if result:
                    return result
            except Exception:
                logger.debug(
                    "python-magic class API failed for %s",
                    path,
                    exc_info=True,
                )
            finally:
                if detector is not None:
                    _close_magic_detector(detector)

    # Official module-level API used by python-magic 0.4.x.
    from_file = getattr(magic, "from_file", None)
    if callable(from_file):
        for positional, keyword in (
            ((path,), {"mime": True}),
            ((path, True), {}),
            ((os.fsencode(path),), {"mime": True}),
            ((os.fsencode(path), True), {}),
        ):
            try:
                result = _normalize_magic_result(from_file(*positional, **keyword))
                if result:
                    return result
            except Exception:
                logger.debug(
                    "python-magic module API failed for %s",
                    path,
                    exc_info=True,
                )

    # ``file-magic`` and a few distro bindings return a structured result.
    detect = getattr(magic, "detect_from_filename", None)
    if callable(detect):
        for candidate in (path, os.fsencode(path)):
            try:
                result = _normalize_magic_result(detect(candidate))
                if result:
                    return result
            except Exception:
                logger.debug(
                    "python-magic structured API failed for %s",
                    path,
                    exc_info=True,
                )

    # Legacy libmagic cookie API used by the original Spin FM implementation.
    opener = getattr(magic, "open", None)
    if not callable(opener):
        return ""

    flags: list[int] = []
    combined_flag = getattr(magic, "MAGIC_MIME", None)
    if isinstance(combined_flag, int):
        flags.append(combined_flag)
    mime_type_flag = getattr(magic, "MAGIC_MIME_TYPE", None)
    mime_encoding_flag = getattr(magic, "MAGIC_MIME_ENCODING", None)
    if isinstance(mime_type_flag, int):
        value = mime_type_flag
        if isinstance(mime_encoding_flag, int):
            value |= mime_encoding_flag
        if value not in flags:
            flags.append(value)

    for flag in flags:
        detector = None
        try:
            detector = opener(flag)
            load = getattr(detector, "load", None)
            if callable(load):
                try:
                    load()
                except TypeError:
                    load(None)
            method = _magic_file_method(detector)
            if method is None:
                continue
            result = _call_magic_file(method, path)
            if result:
                return result
        except Exception:
            logger.debug(
                "python-magic legacy API failed for %s",
                path,
                exc_info=True,
            )
        finally:
            if detector is not None:
                _close_magic_detector(detector)
    return ""


def _file_command_mime(path: str) -> str:
    """Return a MIME description using ``file(1)`` without invoking a shell."""
    command = shutil.which("file")
    if not command:
        return ""
    try:
        completed = subprocess.run(
            [command, "--brief", "--mime", "--", path],
            check=False,
            capture_output=True,
            text=True,
            timeout=_FILE_COMMAND_TIMEOUT_SECONDS,
        )
    except (OSError, subprocess.SubprocessError):
        return ""
    if completed.returncode != 0:
        return ""
    return completed.stdout.strip()


def detect_mime_type(path: str, mode: int | None = None) -> str:
    """Detect a readable MIME type with bounded, dependency-tolerant fallbacks."""
    if mode is None:
        try:
            mode = os.lstat(path).st_mode
        except OSError:
            mode = 0

    if stat.S_ISDIR(mode):
        return "inode/directory"
    if stat.S_ISLNK(mode) and not os.path.exists(path):
        return "inode/symlink"
    if stat.S_ISFIFO(mode):
        return "inode/fifo"
    if stat.S_ISSOCK(mode):
        return "inode/socket"
    if stat.S_ISCHR(mode):
        return "inode/chardevice"
    if stat.S_ISBLK(mode):
        return "inode/blockdevice"

    try:
        detected = _python_magic_mime(path)
    except Exception:
        # MIME integration must never suppress the independently available
        # size and timestamp fields. A broken or conflicting ``magic`` module
        # therefore falls through to the bounded detectors below.
        logger.debug("python-magic failed for %s", path, exc_info=True)
        detected = ""
    if detected:
        return detected

    guessed, encoding = mimetypes.guess_type(path, strict=False)
    if guessed:
        return f"{guessed}; encoding={encoding}" if encoding else guessed

    detected = _file_command_mime(path)
    return detected or "application/octet-stream"


def _raise_if_cancelled(cancel_event: threading.Event | None) -> None:
    if cancel_event is not None and cancel_event.is_set():
        raise _InspectionCancelled("file information request was superseded")


def _directory_content_size(
    path: str,
    root_info: os.stat_result,
    cancel_event: threading.Event | None,
) -> tuple[int, int, int, int]:
    """Return recursive apparent size and counts without following symlinks.

    Scans stay on the selected directory's filesystem. This avoids accidentally
    traversing another mounted disk through a mount point inside the directory.
    Directory inode identities are retained so bind-mount or filesystem loops
    cannot recurse forever. Permission failures and skipped mount points are
    counted and reported as a partial result instead of failing the whole click.
    """
    total_size = 0
    file_count = 0
    folder_count = 0
    skipped_items = 0
    root_device = int(root_info.st_dev)
    seen_directories: set[tuple[int, int]] = {
        (int(root_info.st_dev), int(root_info.st_ino))
    }
    pending_directories = [path]

    while pending_directories:
        _raise_if_cancelled(cancel_event)
        directory = pending_directories.pop()
        try:
            entries = os.scandir(directory)
        except OSError:
            skipped_items += 1
            continue

        try:
            with entries:
                for entry in entries:
                    _raise_if_cancelled(cancel_event)
                    try:
                        entry_info = entry.stat(follow_symlinks=False)
                    except OSError:
                        skipped_items += 1
                        continue

                    if stat.S_ISDIR(entry_info.st_mode):
                        folder_count += 1
                        identity = (int(entry_info.st_dev), int(entry_info.st_ino))
                        if int(entry_info.st_dev) != root_device:
                            skipped_items += 1
                            continue
                        if identity in seen_directories:
                            skipped_items += 1
                            continue
                        seen_directories.add(identity)
                        pending_directories.append(entry.path)
                        continue

                    file_count += 1
                    total_size += max(0, int(entry_info.st_size))
        except OSError:
            skipped_items += 1

    return total_size, file_count, folder_count, skipped_items


def inspect_path(
    path: str | os.PathLike[str],
    cancel_event: threading.Event | None = None,
) -> FileDetails:
    """Collect size, timestamp, and MIME metadata for a selected path.

    ``os.stat`` preserves the old handler's symlink-following behaviour. A broken
    symlink falls back to ``os.lstat`` so it can still be described. Directories
    receive a cancellable, memory-bounded recursive apparent-size scan; symlinked
    children are counted but never followed.
    """
    normalized = os.path.abspath(os.path.expanduser(os.fspath(path)))
    _raise_if_cancelled(cancel_event)
    try:
        info = os.stat(normalized)
    except FileNotFoundError:
        info = os.lstat(normalized)
    mime_type = detect_mime_type(normalized, info.st_mode)

    if not stat.S_ISDIR(info.st_mode):
        return FileDetails(normalized, info, mime_type)

    size_bytes, file_count, folder_count, skipped_items = _directory_content_size(
        normalized,
        info,
        cancel_event,
    )
    return FileDetails(
        normalized,
        info,
        mime_type,
        content_size_bytes=size_bytes,
        file_count=file_count,
        folder_count=folder_count,
        skipped_items=skipped_items,
    )


def format_file_details(details: FileDetails) -> str:
    """Format metadata so the most useful fields remain visible first."""
    size_mib = details.size_bytes / (1024 * 1024)
#    size_kib = details.size_bytes / 1024
    modified = time.strftime(
        "%a %b %d %H:%M:%S %Y",
        time.localtime(details.modified_time),
    )
    display_name = os.path.basename(details.path.rstrip(os.sep)) or details.path
    if details.is_directory:
        item_count = details.file_count + details.folder_count
        item_label = "item" if item_count == 1 else "items"
        file_label = "file" if details.file_count == 1 else "files"
        folder_label = "folder" if details.folder_count == 1 else "folders"
        partial = (
            f"; partial result, {details.skipped_items} item(s) skipped"
            if details.skipped_items
            else ""
        )
        return (
            f"Folder size: {size_mib:.3f} MiB "
#            f"({size_kib:.2f} KiB, {details.size_bytes:,} bytes)  "
            f"Name: {display_name}  Contents: {item_count} {item_label} "
            f"({details.file_count} {file_label}, "
            f"{details.folder_count} {folder_label}{partial})  "
            f"File type: {details.mime_type}  Last modified: {modified}  "
#            f"Path: {details.path}"
        )
    return (
        f"Size: {size_mib:.3f} MiB "
#        f"({size_kib:.2f} KiB, {details.size_bytes:,} bytes)  "
        f"Name: {display_name}  "
        f"File type: {details.mime_type}  Last modified: {modified}  "
#        f"Path: {details.path}"
    )


def parent_directory(path: str | os.PathLike[str]) -> str:
    """Return a normalized parent, keeping filesystem roots stable."""
    current = os.path.abspath(os.path.expanduser(os.fspath(path)))
    parent = os.path.dirname(current.rstrip(os.sep)) or current
    return parent if parent else current


class FileInfoExtension:
    """Attach file information to every current and future file view."""

    ATTRIBUTE_NAME = "_spin_fm_file_info_extension"

    def __init__(self, main_window: Any) -> None:
        from .qt_compat import QApplication, QLabel, QSizePolicy, Qt, QTimer
        from .workers import TaskManager

        self.window = main_window
        self.tabs = main_window.tabs
        self._timer = QTimer
        self._tasks = TaskManager(main_window, max_threads=1, max_tasks=1)
        self._serial = 0
        self._latest_path = ""
        self._latest_view_id = 0
        self._pending_request: _InspectionRequest | None = None
        self._active_request: _InspectionRequest | None = None
        self._shutting_down = False
        self._application = QApplication.instance()
        self._view_slots: dict[
            int,
            tuple[Callable[[], Any | None], Any, Any],
        ] = {}

        self.filepath = ""
        self.info: os.stat_result | None = None
        self.basic = ""
        self._status_label = self._create_status_label(QLabel, QSizePolicy, Qt)

        self.tabs.tab_widget.currentChanged.connect(self._on_current_tab_changed)
        self._bind_all_views()
        self._timer.singleShot(0, self._bind_all_views)

        if self._application is not None:
            self._application.aboutToQuit.connect(self.shutdown)

    def _create_status_label(
        self, label_class: Any, size_policy: Any, qt: Any
    ) -> Any | None:
        """Create a persistent, elided metadata field in the real status bar.

        ``QStatusBar.showMessage`` was being populated correctly, but the storage
        label had stretch factor 1 and could consume the complete visible width.
        The extension therefore owns a permanent left-hand label and reinserts
        the storage label without stretch. Core window code remains unchanged.
        """
        status_bar = getattr(self.window, "status_bar", None)
        if status_bar is None:
            try:
                status_bar = self.window.statusBar()
            except Exception:
                return None
        if status_bar is None:
            return None

        elide_mode = getattr(qt, "ElideRight", getattr(qt, "ElideMiddle", None))

        class ElidingStatusLabel(label_class):
            def __init__(self, parent: Any) -> None:
                super().__init__(parent)
                self.full_text = ""

            def set_full_text(self, text: str) -> None:
                self.full_text = str(text)
                self.setToolTip(self.full_text)
                self._refresh_text()

            def _refresh_text(self) -> None:
                width = max(0, int(self.width()) - 8)
                try:
                    rendered = (
                        self.fontMetrics().elidedText(
                            self.full_text,
                            elide_mode,
                            width,
                        )
                        if width and elide_mode is not None
                        else self.full_text
                    )
                except Exception:
                    rendered = self.full_text
                self.setText(rendered)

            def resizeEvent(self, event: Any) -> None:  # noqa: N802 - Qt API name
                self._refresh_text()
                super().resizeEvent(event)

        label = ElidingStatusLabel(status_bar)
        label.setObjectName("fileInfoStatusLabel")
        label.setMinimumWidth(140)
        try:
            label.setAccessibleName("Selected file information")
        except Exception:
            pass
        try:
            ignored = getattr(size_policy, "Ignored", None)
            preferred = getattr(size_policy, "Preferred", None)
            if ignored is None or preferred is None:
                ignored = size_policy.Policy.Ignored
                preferred = size_policy.Policy.Preferred
            label.setSizePolicy(ignored, preferred)
        except Exception:
            pass

        disk_label = getattr(self.window, "disk_label", None)
        if disk_label is not None:
            try:
                status_bar.removeWidget(disk_label)
            except Exception:
                pass
        # Use a normal status widget rather than a permanent one. Qt then
        # hides the metadata automatically while copy/move/device progress is
        # shown through QStatusBar.showMessage(), and restores it afterwards.
        try:
            status_bar.insertWidget(0, label, 1)
        except Exception:
            try:
                status_bar.addWidget(label, 1)
            except Exception:
                label.deleteLater()
                return None
        if disk_label is not None:
            try:
                status_bar.addPermanentWidget(disk_label, 0)
                disk_label.show()
            except Exception:
                pass
        return label

    @property
    def event_filter_installed(self) -> bool:
        """Compatibility property: the fragile global event filter was removed."""
        return False

    @property
    def direct_signal_integration_active(self) -> bool:
        self._discard_dead_views()
        return not self._shutting_down and bool(self._view_slots)

    @property
    def connected_view_count(self) -> int:
        """Return the number of live file views bound to ``clicked``."""
        self._discard_dead_views()
        return len(self._view_slots)

    def _discard_dead_views(self) -> None:
        dead = [
            view_id
            for view_id, (
                view_reference,
                _clicked,
                _destroyed,
            ) in self._view_slots.items()
            if view_reference() is None
        ]
        for view_id in dead:
            self._view_slots.pop(view_id, None)

    def _bind_all_views(self) -> None:
        """Bind every tab page once, including tabs created after startup."""
        if self._shutting_down:
            return
        self._discard_dead_views()
        try:
            tab_widget = self.tabs.tab_widget
            count = int(tab_widget.count())
        except (AttributeError, RuntimeError):
            return
        for index in range(count):
            try:
                view = tab_widget.widget(index)
            except RuntimeError:
                continue
            self._bind_view(view)

    def _bind_view(self, view: Any) -> bool:
        """Connect one actual file view's click signal exactly once."""
        if self._shutting_down or view is None:
            return False
        view_id = id(view)
        existing = self._view_slots.get(view_id)
        if existing is not None and existing[0]() is view:
            return False

        clicked_signal = getattr(view, "clicked", None)
        if clicked_signal is None or not callable(
            getattr(clicked_signal, "connect", None)
        ):
            return False

        try:
            view_reference = weakref.ref(view)
        except TypeError:
            # Some older PyQt/SIP wrappers cannot be weak-referenced. Keep the
            # view only until tab destruction or extension shutdown rather than
            # silently disabling file information on those systems.
            def strong_reference(current: Any = view) -> Any:
                return current

            view_reference = strong_reference

        def clicked(index: Any, reference=view_reference) -> None:
            bound_view = reference()
            if bound_view is not None and not self._shutting_down:
                self.on_treeview2_clicked(index, bound_view)

        def destroyed(*_args: Any, bound_id: int = view_id) -> None:
            self._view_slots.pop(bound_id, None)

        try:
            clicked_signal.connect(clicked)
            destroyed_signal = getattr(view, "destroyed", None)
            if destroyed_signal is not None and callable(
                getattr(destroyed_signal, "connect", None)
            ):
                destroyed_signal.connect(destroyed)
        except (AttributeError, RuntimeError, TypeError):
            logger.exception("Unable to connect selected-file information to a tab")
            try:
                clicked_signal.disconnect(clicked)
            except Exception:
                pass
            return False

        self._view_slots[view_id] = (view_reference, clicked, destroyed)
        return True

    def _disconnect_all_views(self) -> None:
        records = list(self._view_slots.values())
        self._view_slots.clear()
        for view_reference, clicked, destroyed in records:
            view = view_reference()
            if view is None:
                continue
            try:
                view.clicked.disconnect(clicked)
            except Exception:
                pass
            try:
                view.destroyed.disconnect(destroyed)
            except Exception:
                pass

    def _on_current_tab_changed(self, _index: int) -> None:
        if self._shutting_down:
            return
        if self._active_request is not None:
            self._active_request.cancel_event.set()
        if self._pending_request is not None:
            self._pending_request.cancel_event.set()
        self._serial += 1
        self._latest_path = ""
        self._latest_view_id = 0
        self._pending_request = None
        if self._status_label is not None:
            try:
                self._status_label.set_full_text("")
            except Exception:
                pass
        self._bind_all_views()
        self._timer.singleShot(0, self._bind_all_views)

    def _path_from_index(self, index: Any, view: Any) -> str:
        try:
            if index is None or not index.isValid():
                return ""
            model = view.model()
            raw_path = str(model.filePath(index) or "").strip()
            if not raw_path:
                index_item = model.index(index.row(), 0, index.parent())
                raw_path = str(model.filePath(index_item) or "").strip()
            if not raw_path:
                return ""
            return os.path.abspath(os.path.expanduser(raw_path))
        except Exception:
            logger.exception("Unable to resolve the clicked filesystem item")
            return ""

    def _show_status(self, message: str, timeout: int = _STATUS_TIMEOUT_MSEC) -> None:
        if self._status_label is not None:
            try:
                status_bar = getattr(self.window, "status_bar", None)
                if status_bar is None:
                    status_bar = self.window.statusBar()
                status_bar.clearMessage()
                self._status_label.set_full_text(message)
                self._status_label.show()
                return
            except Exception:
                logger.debug(
                    "Unable to update selected-item information", exc_info=True
                )
        try:
            self.window.show_status(message, timeout)
            return
        except Exception:
            pass
        try:
            self.window.statusBar().showMessage(message, timeout)
        except Exception:
            logger.debug("Unable to show file-information status", exc_info=True)

    def on_treeview2_clicked(self, index: Any, view: Any | None = None) -> None:
        """Modern, asynchronous equivalent of the original click callback."""
        if self._shutting_down:
            return
        target_view = view or self.tabs.currentView()
        if target_view is None:
            return
        filepath = self._path_from_index(index, target_view)
        if not filepath:
            return

        self.filepath = filepath
        self.basic = os.path.basename(filepath.rstrip(os.sep)) or filepath
        try:
            self.tabs.address_bar.setText(filepath)
        except Exception:
            logger.debug("Unable to update the Spin FM location bar", exc_info=True)

        if self._active_request is not None:
            self._active_request.cancel_event.set()
        if self._pending_request is not None:
            self._pending_request.cancel_event.set()

        self._serial += 1
        request = _InspectionRequest(
            self._serial,
            filepath,
            id(target_view),
            threading.Event(),
        )
        self._latest_path = filepath
        self._latest_view_id = request.view_id
        self._pending_request = request
        if os.path.isdir(filepath):
            self._show_status(f"Calculating folder size for {self.basic}…")
        else:
            self._show_status(f"Reading file information for {self.basic}…")
        self._start_pending_request()

    def _start_pending_request(self) -> None:
        if self._shutting_down or self._active_request is not None:
            return
        request = self._pending_request
        if request is None:
            return
        self._pending_request = None
        self._active_request = request

        worker = self._tasks.submit(
            inspect_path,
            request.path,
            request.cancel_event,
            on_result=lambda result, current=request: self._inspection_ready(
                current, result
            ),
            on_error=lambda error, current=request: self._inspection_failed(
                current, error
            ),
            on_finished=lambda current=request: self._inspection_finished(current),
        )
        if worker is not None:
            return

        self._active_request = None
        if self._is_current_request(request):
            self._show_status(f"{request.path}  File information is temporarily busy")
        self._timer.singleShot(0, self._start_pending_request)

    def _is_current_request(self, request: _InspectionRequest) -> bool:
        if (
            request.cancel_event.is_set()
            or request.serial != self._serial
            or request.path != self._latest_path
            or request.view_id != self._latest_view_id
        ):
            return False
        try:
            return id(self.tabs.currentView()) == request.view_id
        except Exception:
            return False

    def _inspection_ready(
        self, request: _InspectionRequest, details: FileDetails
    ) -> None:
        if not self._is_current_request(request):
            return
        try:
            if bool(self.tabs.is_busy):
                return
        except Exception:
            pass
        self.info = details.stat_result
        self.filepath = details.path
        self.basic = os.path.basename(details.path.rstrip(os.sep)) or details.path
        self._show_status(format_file_details(details))

    def _inspection_failed(
        self, request: _InspectionRequest, error: dict[str, str]
    ) -> None:
        if error.get("type") == _InspectionCancelled.__name__:
            return
        if not self._is_current_request(request):
            return
        message = str(error.get("message", "Unknown error") or "Unknown error")
        self._show_status(f"{request.path}  File information unavailable: {message}")

    def _inspection_finished(self, request: _InspectionRequest) -> None:
        if self._active_request == request:
            self._active_request = None
        self._timer.singleShot(0, self._start_pending_request)

    def changed(self, current: Any = None) -> str | None:
        """Compatibility callback for the old parent-folder navigation handler."""
        if current:
            return None
        try:
            active_path = self.tabs.currentPath()
        except Exception:
            return None
        parent = parent_directory(active_path)
        if parent == active_path or not os.path.isdir(parent):
            return active_path
        try:
            self.tabs._navigateTo(parent)
            navigated = self.tabs.currentPath() == parent
        except Exception:
            logger.exception("Unable to navigate to the parent directory")
            return None
        if not navigated:
            return None
        self._show_status(parent)
        return parent

    def shutdown(self) -> None:
        if self._shutting_down:
            return
        self._shutting_down = True
        if self._active_request is not None:
            self._active_request.cancel_event.set()
        if self._pending_request is not None:
            self._pending_request.cancel_event.set()
        self._pending_request = None

        try:
            self.tabs.tab_widget.currentChanged.disconnect(self._on_current_tab_changed)
        except Exception:
            pass

        self._disconnect_all_views()

        if self._status_label is not None:
            label = self._status_label
            self._status_label = None
            try:
                status_bar = getattr(self.window, "status_bar", None)
                disk_label = getattr(self.window, "disk_label", None)
                if status_bar is not None:
                    status_bar.removeWidget(label)
                    if disk_label is not None:
                        status_bar.removeWidget(disk_label)
                        status_bar.addPermanentWidget(disk_label, 1)
                        disk_label.show()
                label.deleteLater()
            except Exception:
                pass

        if self._application is not None:
            try:
                self._application.aboutToQuit.disconnect(self.shutdown)
            except Exception:
                pass

        try:
            self._tasks.shutdown(wait_msec=2_000)
        except Exception:
            logger.debug("File-information worker shutdown failed", exc_info=True)


def extension_enabled() -> bool:
    """Return whether automatic integration is enabled for this process."""
    value = os.environ.get("SPIN_FM_FILE_INFO", "1").strip().lower()
    return value not in _DISABLED_VALUES


def install(main_window: Any) -> FileInfoExtension | None:
    """Attach one extension instance to *main_window* and return it."""
    existing = getattr(main_window, FileInfoExtension.ATTRIBUTE_NAME, None)
    if isinstance(existing, FileInfoExtension):
        return existing
    if not extension_enabled():
        return None
    extension = FileInfoExtension(main_window)
    setattr(main_window, FileInfoExtension.ATTRIBUTE_NAME, extension)
    return extension


__all__ = [
    "FileDetails",
    "FileInfoExtension",
    "detect_mime_type",
    "extension_enabled",
    "format_file_details",
    "inspect_path",
    "install",
    "parent_directory",
]
