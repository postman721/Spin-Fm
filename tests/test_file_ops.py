from __future__ import annotations

import subprocess
from pathlib import Path

import spin_fm.file_ops as file_ops
from spin_fm.file_ops import TransferItem, empty_trash, execute_transfer, trash_paths


def test_copy_directory_and_replace_file(tmp_path: Path) -> None:
    source_dir = tmp_path / "source"
    source_dir.mkdir()
    (source_dir / "nested.txt").write_text("nested", encoding="utf-8")
    destination_root = tmp_path / "destination"
    destination_root.mkdir()

    report = execute_transfer(
        [
            TransferItem(
                str(source_dir), str(destination_root / "source"), is_directory=True
            )
        ]
    )
    assert report.completed == 1
    assert report.error_count == 0
    assert (destination_root / "source" / "nested.txt").read_text(
        encoding="utf-8"
    ) == "nested"

    source_file = tmp_path / "replacement.txt"
    source_file.write_text("new", encoding="utf-8")
    target_file = destination_root / "replacement.txt"
    target_file.write_text("old", encoding="utf-8")
    report = execute_transfer(
        [TransferItem(str(source_file), str(target_file), replace=True)]
    )
    assert report.completed == 1
    assert target_file.read_text(encoding="utf-8") == "new"


def test_move_directory_reports_retarget(tmp_path: Path) -> None:
    source = tmp_path / "folder"
    source.mkdir()
    (source / "file.txt").write_text("data", encoding="utf-8")
    destination = tmp_path / "target" / "folder"
    destination.parent.mkdir()

    report = execute_transfer(
        [TransferItem(str(source), str(destination), is_directory=True)],
        move=True,
    )
    assert report.completed == 1
    assert report.moved_directories == [(str(source), str(destination))]
    assert not source.exists()
    assert (destination / "file.txt").exists()


def test_manual_trash_and_empty(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr(file_ops.shutil, "which", lambda _name: None)
    trash_root = tmp_path / "Trash"
    source = tmp_path / "delete-me.txt"
    source.write_text("payload", encoding="utf-8")

    report = trash_paths([str(source)], trash_root=str(trash_root))
    assert report.completed == 1
    assert not source.exists()
    assert (trash_root / "files" / "delete-me.txt").exists()
    assert (trash_root / "info" / "delete-me.txt.trashinfo").exists()

    cleanup = empty_trash(str(trash_root))
    assert cleanup.error_count == 0
    assert cleanup.completed == 2
    assert not any((trash_root / "files").iterdir())
    assert not any((trash_root / "info").iterdir())


def test_progress_is_top_level_and_bounded(tmp_path: Path) -> None:
    source = tmp_path / "source.txt"
    source.write_text("x", encoding="utf-8")
    destination = tmp_path / "destination.txt"
    progress = []
    report = execute_transfer(
        [TransferItem(str(source), str(destination))],
        progress_callback=progress.append,
    )
    assert progress == [(1, 1, "source.txt")]
    assert report.completed == 1


def test_failed_copy_publish_restores_existing_destination(
    tmp_path: Path, monkeypatch
) -> None:
    source = tmp_path / "source.txt"
    source.write_text("new", encoding="utf-8")
    destination = tmp_path / "destination.txt"
    destination.write_text("old", encoding="utf-8")

    real_replace = file_ops.os.replace
    failed_once = False

    def fail_publish_once(src, dst):
        nonlocal failed_once
        if (
            not failed_once
            and ".spin-fm-copy-" in str(src)
            and str(dst) == str(destination)
        ):
            failed_once = True
            raise OSError("simulated publish failure")
        return real_replace(src, dst)

    monkeypatch.setattr(file_ops.os, "replace", fail_publish_once)
    report = execute_transfer(
        [TransferItem(str(source), str(destination), replace=True)]
    )

    assert report.completed == 0
    assert report.error_count == 1
    assert destination.read_text(encoding="utf-8") == "old"
    assert source.read_text(encoding="utf-8") == "new"
    assert not list(tmp_path.glob(".*.spin-fm-*"))


def test_transfer_rejects_symlinked_descendant_destination(tmp_path: Path) -> None:
    source = tmp_path / "source"
    inner = source / "inner"
    inner.mkdir(parents=True)
    destination_link = tmp_path / "destination-link"
    destination_link.symlink_to(inner, target_is_directory=True)
    destination = destination_link / source.name

    report = execute_transfer(
        [TransferItem(str(source), str(destination), is_directory=True)]
    )
    assert report.completed == 0
    assert report.error_count == 1
    assert "descendant" in report.details[0]
    assert not destination.exists()



def test_delete_from_home_trash_is_permanent_and_removes_metadata(
    tmp_path: Path, monkeypatch
) -> None:
    monkeypatch.setattr(file_ops.shutil, "which", lambda _name: None)
    trash_root = tmp_path / "Trash"
    source = tmp_path / "permanent.txt"
    source.write_text("payload", encoding="utf-8")

    trashed = trash_paths([str(source)], trash_root=str(trash_root))
    assert trashed.completed == 1
    payload = trash_root / "files" / source.name
    metadata = trash_root / "info" / f"{source.name}.trashinfo"
    assert payload.exists()
    assert metadata.exists()

    deleted = trash_paths([str(payload)], trash_root=str(trash_root))
    assert deleted.completed == 1
    assert deleted.error_count == 0
    assert not payload.exists()
    assert not metadata.exists()


def test_delete_from_mount_trash_is_permanent(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr(file_ops.os, "getuid", lambda: 1000)
    monkeypatch.setattr(file_ops.shutil, "which", lambda _name: None)
    trash_root = tmp_path / ".Trash-1000"
    payload_dir = trash_root / "files"
    info_dir = trash_root / "info"
    payload_dir.mkdir(parents=True)
    info_dir.mkdir()
    payload = payload_dir / "mounted.txt"
    metadata = info_dir / "mounted.txt.trashinfo"
    payload.write_text("payload", encoding="utf-8")
    metadata.write_text("[Trash Info]\n", encoding="utf-8")

    report = trash_paths([str(payload)])

    assert report.completed == 1
    assert report.error_count == 0
    assert not payload.exists()
    assert not metadata.exists()


def test_empty_trash_uses_gio_for_complete_desktop_trash(monkeypatch) -> None:
    calls: list[list[str]] = []

    def fake_run(arguments, **kwargs):
        calls.append(list(arguments))
        if arguments[-1] == "--list":
            return subprocess.CompletedProcess(
                arguments,
                0,
                stdout="trash:///one\t/tmp/one\ntrash:///two\t/tmp/two\n",
                stderr="",
            )
        return subprocess.CompletedProcess(arguments, 0, stdout="", stderr="")

    monkeypatch.setattr(
        file_ops.shutil,
        "which",
        lambda name: "/usr/bin/gio" if name == "gio" else None,
    )
    monkeypatch.setattr(file_ops.subprocess, "run", fake_run)

    report = empty_trash()

    assert report.completed == 2
    assert report.error_count == 0
    assert calls == [
        ["/usr/bin/gio", "trash", "--list"],
        ["/usr/bin/gio", "trash", "--empty"],
    ]


def test_mounted_trash_directories_discovers_both_freedesktop_layouts(
    tmp_path: Path, monkeypatch
) -> None:
    monkeypatch.setattr(file_ops.os, "getuid", lambda: 1000)
    first_mount = tmp_path / "USB One"
    second_mount = tmp_path / "USB Two"
    first = first_mount / ".Trash-1000" / "files"
    second = second_mount / ".Trash" / "1000" / "files"
    first.mkdir(parents=True)
    second.mkdir(parents=True)

    assert file_ops.mounted_trash_directories(
        [str(first_mount), str(second_mount)]
    ) == tuple(sorted((str(first.resolve()), str(second.resolve())), key=str.casefold))


def test_mounted_trash_directories_does_not_create_missing_trash(tmp_path: Path) -> None:
    mount = tmp_path / "USB"
    mount.mkdir()

    assert file_ops.mounted_trash_directories([str(mount)], uid=1000) == ()
    assert not (mount / ".Trash-1000").exists()
    assert not (mount / ".Trash").exists()


def test_trash_mount_point_recognizes_both_freedesktop_layouts(
    tmp_path: Path,
) -> None:
    first_mount = tmp_path / "USB One"
    second_mount = tmp_path / "USB Two"
    first = first_mount / ".Trash-1000" / "files"
    second = second_mount / ".Trash" / "1000" / "files"

    assert file_ops.trash_mount_point(str(first), uid=1000) == str(first_mount)
    assert file_ops.trash_mount_point(str(second), uid=1000) == str(second_mount)
    assert file_ops.trash_mount_point(str(tmp_path / "not-trash"), uid=1000) is None
