"""Thread-safe filesystem operations used by the Spin FM UI.

This module has no Qt dependency, which keeps destructive work out of the GUI
thread and makes the behavior straightforward to unit test.
"""

from __future__ import annotations

import os
import shutil
import subprocess
import uuid
from collections.abc import Callable, Iterable
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from urllib.parse import quote

MAX_REPORT_DETAILS = 24
TRASH_COMMAND_TIMEOUT = 300
ProgressCallback = Callable[[tuple[int, int, str]], None] | None


@dataclass(frozen=True, slots=True)
class TransferItem:
    """One already-confirmed copy or move operation."""

    source: str
    destination: str
    replace: bool = False
    is_directory: bool = False


@dataclass(slots=True)
class OperationReport:
    """A bounded report suitable for returning from a worker thread."""

    completed: int = 0
    skipped: int = 0
    same_location: int = 0
    error_count: int = 0
    details: list[str] = field(default_factory=list)
    moved_directories: list[tuple[str, str | None]] = field(default_factory=list)

    def add_error(self, message: str) -> None:
        self.error_count += 1
        if len(self.details) < MAX_REPORT_DETAILS:
            self.details.append(message)

    def add_detail(self, message: str) -> None:
        if len(self.details) < MAX_REPORT_DETAILS:
            self.details.append(message)


def _emit_progress(
    callback: ProgressCallback, index: int, total: int, label: str
) -> None:
    if callback is not None:
        callback((index, total, label))


def _remove_path(path: str) -> None:
    if os.path.isdir(path) and not os.path.islink(path):
        shutil.rmtree(path)
    else:
        os.unlink(path)


def _temporary_sibling(destination: str, purpose: str) -> str:
    parent = os.path.dirname(destination) or os.curdir
    name = os.path.basename(destination.rstrip(os.sep)) or "item"
    return os.path.join(
        parent,
        f".{name}.spin-fm-{purpose}-{os.getpid()}-{uuid.uuid4().hex}",
    )


def _copy_entry_atomic(source: str, destination: str, replace: bool) -> str | None:
    """Copy to a sibling temporary path, then publish the completed copy.

    Existing destinations are first renamed to a same-directory backup. This
    keeps the original item recoverable if publishing the completed temporary
    copy fails between the overwrite confirmation and the final rename.
    """
    temporary = _temporary_sibling(destination, "copy")
    backup: str | None = None
    try:
        if os.path.isdir(source) and not os.path.islink(source):
            shutil.copytree(
                source,
                temporary,
                symlinks=True,
                copy_function=shutil.copy2,
            )
        else:
            shutil.copy2(source, temporary, follow_symlinks=False)

        if os.path.lexists(destination):
            if not replace:
                raise FileExistsError(destination)
            backup = _temporary_sibling(destination, "backup")
            os.replace(destination, backup)

        try:
            os.replace(temporary, destination)
        except Exception as publish_error:
            if backup is not None and os.path.lexists(backup):
                try:
                    os.replace(backup, destination)
                except Exception as restore_error:
                    raise RuntimeError(
                        "The new copy could not be published and the original "
                        f"destination could not be restored from {backup}: {restore_error}"
                    ) from publish_error
            raise

        if backup is not None and os.path.lexists(backup):
            try:
                _remove_path(backup)
            except Exception as exc:
                return (
                    "Copy completed, but the replaced destination backup could "
                    f"not be removed: {backup}: {exc}"
                )
        return None
    finally:
        if os.path.lexists(temporary):
            try:
                _remove_path(temporary)
            except OSError:
                pass


def _move_entry(source: str, destination: str, replace: bool) -> str | None:
    """Move an entry, preserving an existing destination until the move starts."""
    if not os.path.lexists(destination):
        shutil.move(source, destination)
        return None
    if not replace:
        raise FileExistsError(destination)

    backup = _temporary_sibling(destination, "backup")
    os.replace(destination, backup)
    try:
        shutil.move(source, destination)
    except Exception:
        if os.path.lexists(destination):
            try:
                _remove_path(destination)
            except OSError:
                pass
        os.replace(backup, destination)
        raise
    else:
        try:
            _remove_path(backup)
        except Exception as exc:
            return (
                "Move completed, but the replaced destination backup could not "
                f"be removed: {backup}: {exc}"
            )
    return None


def execute_transfer(
    items: Iterable[TransferItem],
    move: bool = False,
    progress_callback: ProgressCallback = None,
) -> OperationReport:
    """Execute a prepared copy/move plan without any UI interaction."""
    plan = tuple(items)
    report = OperationReport()
    total = len(plan)

    for index, item in enumerate(plan, start=1):
        _emit_progress(progress_callback, index, total, os.path.basename(item.source))
        try:
            if not os.path.lexists(item.source):
                raise FileNotFoundError("source no longer exists")
            if item.is_directory and resolved_same_or_subpath(
                item.destination, item.source
            ):
                raise ValueError(
                    "cannot copy or move a folder into itself or a descendant"
                )
            if move:
                warning = _move_entry(item.source, item.destination, item.replace)
                if warning:
                    report.add_detail(warning)
                if item.is_directory:
                    report.moved_directories.append((item.source, item.destination))
            else:
                warning = _copy_entry_atomic(
                    item.source, item.destination, item.replace
                )
                if warning:
                    report.add_detail(warning)
            report.completed += 1
        except Exception as exc:
            report.add_error(f"{item.source} → {item.destination}: {exc}")

    return report


def same_or_subpath(child_path: str, parent_path: str) -> bool:
    """Return whether *child_path* is *parent_path* or lies below it."""
    child = os.path.abspath(os.path.expanduser(child_path))
    parent = os.path.abspath(os.path.expanduser(parent_path))
    try:
        return os.path.commonpath([child, parent]) == parent
    except (OSError, ValueError):
        return False


def resolved_same_or_subpath(child_path: str, parent_path: str) -> bool:
    """Containment check for transfer destinations, resolving symlinked dirs."""
    child = os.path.realpath(os.path.abspath(os.path.expanduser(child_path)))
    parent = os.path.realpath(os.path.abspath(os.path.expanduser(parent_path)))
    try:
        return os.path.commonpath([child, parent]) == parent
    except (OSError, ValueError):
        return False


def _unique_trash_name(trash_files: str, trash_info: str, name: str) -> str:
    candidate = name
    root, extension = os.path.splitext(name)
    counter = 2
    while os.path.lexists(os.path.join(trash_files, candidate)) or os.path.exists(
        os.path.join(trash_info, candidate + ".trashinfo")
    ):
        candidate = f"{root} ({counter}){extension}"
        counter += 1
    return candidate


def _write_trash_info(path: str, original_path: str) -> None:
    content = (
        "[Trash Info]\n"
        f"Path={quote(original_path, safe='/')}\n"
        f"DeletionDate={datetime.now().strftime('%Y-%m-%dT%H:%M:%S')}\n"
    )
    with open(path, "x", encoding="utf-8", newline="\n") as handle:
        handle.write(content)


def trash_directories(trash_root: str | None = None) -> tuple[str, str, str]:
    """Return the configured Trash root, payload directory, and metadata directory."""
    root = os.path.abspath(os.path.expanduser(trash_root or "~/.local/share/Trash"))
    return root, os.path.join(root, "files"), os.path.join(root, "info")


def ensure_trash_directories(trash_root: str | None = None) -> str:
    """Create the home Trash directories and return the payload directory."""
    _root, trash_files, trash_info = trash_directories(trash_root)
    os.makedirs(trash_files, mode=0o700, exist_ok=True)
    os.makedirs(trash_info, mode=0o700, exist_ok=True)
    return trash_files


def _mounted_filesystems() -> tuple[str, ...]:
    """Return mounted filesystem roots from Linux mountinfo.

    Mount paths are decoded according to procfs escaping. Failure to read
    mountinfo is non-fatal; removable Trash discovery then returns no entries.
    """
    mounts: list[str] = []
    seen: set[str] = set()
    try:
        lines = Path("/proc/self/mountinfo").read_text(
            encoding="utf-8", errors="replace"
        ).splitlines()
    except OSError:
        return ()

    escapes = {"\\040": " ", "\\011": "\t", "\\012": "\n", "\\134": "\\"}
    for line in lines:
        fields = line.split()
        if len(fields) < 5:
            continue
        mount = fields[4]
        for encoded, decoded in escapes.items():
            mount = mount.replace(encoded, decoded)
        mount = os.path.abspath(mount)
        if mount in seen:
            continue
        seen.add(mount)
        mounts.append(mount)
    return tuple(mounts)


def mounted_trash_directories(
    mount_points: Iterable[str] | None = None, uid: int | None = None
) -> tuple[str, ...]:
    """Return existing freedesktop Trash payloads on mounted filesystems.

    Both permitted layouts are recognized: ``.Trash-$uid/files`` and
    ``.Trash/$uid/files``. Only existing directories are returned, so Spin FM
    never creates Trash structures merely by browsing.
    """
    user_id = str(os.getuid() if uid is None else uid)
    home_files = os.path.realpath(trash_directories()[1])
    found: set[str] = set()
    for mount in mount_points if mount_points is not None else _mounted_filesystems():
        root = os.path.abspath(os.path.expanduser(str(mount)))
        for candidate in (
            os.path.join(root, f".Trash-{user_id}", "files"),
            os.path.join(root, ".Trash", user_id, "files"),
        ):
            if not os.path.isdir(candidate):
                continue
            resolved = os.path.realpath(candidate)
            if resolved == home_files:
                continue
            found.add(resolved)
    return tuple(sorted(found, key=str.casefold))


def _mounted_trash_details(
    trash_files: Path, uid: int | None = None
) -> tuple[Path, Path] | None:
    """Return the mount root and metadata directory for a Trash payload."""
    user_id = str(os.getuid() if uid is None else uid)
    if trash_files.name != "files":
        return None

    parent = trash_files.parent
    if parent.name == f".Trash-{user_id}":
        return parent.parent, parent / "info"
    if parent.name == user_id and parent.parent.name == ".Trash":
        return parent.parent.parent, parent / "info"
    return None


def trash_mount_point(trash_files: str, uid: int | None = None) -> str | None:
    """Return the mounted filesystem root for a recognized Trash payload."""
    path = Path(os.path.abspath(os.path.expanduser(trash_files)))
    details = _mounted_trash_details(path, uid)
    return str(details[0]) if details is not None else None


def _trash_location_for_path(
    path: str, trash_root: str | None = None
) -> tuple[str, str] | None:
    """Return the Trash payload/metadata pair containing *path*, when recognized."""
    _root, home_files, home_info = trash_directories(trash_root)
    if same_or_subpath(path, home_files):
        return home_files, home_info

    absolute = Path(os.path.abspath(os.path.expanduser(path)))
    for candidate in (absolute, *absolute.parents):
        details = _mounted_trash_details(candidate)
        if details is not None:
            _mount_root, info = details
            return str(candidate), str(info)
    return None


def is_path_in_trash(path: str, trash_root: str | None = None) -> bool:
    """Return whether *path* is inside a recognized freedesktop Trash payload."""
    return _trash_location_for_path(path, trash_root) is not None


def _delete_from_trash(path: str, trash_info: str) -> None:
    name = os.path.basename(path.rstrip(os.sep))
    _remove_path(path)
    info_path = os.path.join(trash_info, name + ".trashinfo")
    try:
        os.unlink(info_path)
    except FileNotFoundError:
        pass


def _manual_trash(path: str, trash_files: str, trash_info: str) -> str:
    os.makedirs(trash_files, mode=0o700, exist_ok=True)
    os.makedirs(trash_info, mode=0o700, exist_ok=True)

    base_name = os.path.basename(path.rstrip(os.sep)) or "unnamed"
    unique_name = _unique_trash_name(trash_files, trash_info, base_name)
    destination = os.path.join(trash_files, unique_name)
    final_info = os.path.join(trash_info, unique_name + ".trashinfo")
    temporary_info = _temporary_sibling(final_info, "trashinfo")

    _write_trash_info(temporary_info, path)
    try:
        shutil.move(path, destination)
        os.replace(temporary_info, final_info)
    except Exception:
        try:
            os.unlink(temporary_info)
        except OSError:
            pass
        raise
    return destination


def trash_paths(
    paths: Iterable[str],
    trash_root: str | None = None,
    progress_callback: ProgressCallback = None,
) -> OperationReport:
    """Move paths to Trash, or permanently remove paths already in Trash."""
    targets = tuple(os.path.abspath(os.path.expanduser(path)) for path in paths)
    _root, trash_files, trash_info = trash_directories(trash_root)
    gio = shutil.which("gio")
    report = OperationReport()

    for index, path in enumerate(targets, start=1):
        _emit_progress(progress_callback, index, len(targets), os.path.basename(path))
        was_directory = os.path.isdir(path) and not os.path.islink(path)
        try:
            if not os.path.lexists(path):
                raise FileNotFoundError("item no longer exists")

            trash_location = _trash_location_for_path(path, trash_root)
            if trash_location is not None:
                containing_files, containing_info = trash_location
                if os.path.abspath(path) == os.path.abspath(containing_files):
                    raise ValueError("the Trash container itself cannot be deleted")
                _delete_from_trash(path, containing_info)
            else:
                trashed = False
                if gio is not None:
                    try:
                        subprocess.run(
                            [gio, "trash", path],
                            check=True,
                            stdout=subprocess.DEVNULL,
                            stderr=subprocess.PIPE,
                            text=True,
                            timeout=30,
                        )
                        trashed = True
                    except (
                        OSError,
                        subprocess.CalledProcessError,
                        subprocess.TimeoutExpired,
                    ):
                        trashed = False
                if not trashed:
                    _manual_trash(path, trash_files, trash_info)

            report.completed += 1
            if was_directory:
                report.moved_directories.append((path, None))
        except Exception as exc:
            report.add_error(f"{path}: {exc}")

    return report


def _empty_home_trash(
    trash_root: str | None, progress_callback: ProgressCallback
) -> OperationReport:
    root, _trash_files, _trash_info = trash_directories(trash_root)
    directories = (Path(root) / "files", Path(root) / "info")
    report = OperationReport()
    index = 0
    for directory in directories:
        try:
            with os.scandir(directory) as iterator:
                for entry in iterator:
                    index += 1
                    _emit_progress(progress_callback, index, 0, entry.name)
                    try:
                        _remove_path(entry.path)
                        report.completed += 1
                    except Exception as exc:
                        report.add_error(f"{entry.path}: {exc}")
        except FileNotFoundError:
            continue
    return report


def _empty_desktop_trash_with_gio(gio: str) -> OperationReport:
    listing = subprocess.run(
        [gio, "trash", "--list"],
        check=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        timeout=TRASH_COMMAND_TIMEOUT,
    )
    entry_count = sum(1 for line in listing.stdout.splitlines() if line.strip())
    subprocess.run(
        [gio, "trash", "--empty"],
        check=True,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.PIPE,
        text=True,
        timeout=TRASH_COMMAND_TIMEOUT,
    )
    return OperationReport(completed=entry_count)


def empty_trash(
    trash_root: str | None = None,
    progress_callback: ProgressCallback = None,
) -> OperationReport:
    """Empty the desktop Trash through GIO, with a home-Trash fallback."""
    if trash_root is None:
        gio = shutil.which("gio")
        if gio is not None:
            try:
                return _empty_desktop_trash_with_gio(gio)
            except (
                OSError,
                subprocess.CalledProcessError,
                subprocess.TimeoutExpired,
            ) as exc:
                report = _empty_home_trash(None, progress_callback)
                report.add_error(f"Desktop Trash could not be emptied through GIO: {exc}")
                return report

    return _empty_home_trash(trash_root, progress_callback)
