from __future__ import annotations

from spin_fm.disk_space import DiskSpaceInfo, human_size


def test_human_size() -> None:
    assert human_size(0) == "0 B"
    assert human_size(1024) == "1.0 KiB"
    assert human_size(1024**3) == "1.0 GiB"


def test_usb_partition_inherits_parent_transport(monkeypatch) -> None:
    rows = [
        {
            "name": "sdb",
            "kname": "sdb",
            "type": "disk",
            "pkname": None,
            "tran": "usb",
            "mountpoints": [None],
            "size": 64_000,
            "model": "Flash Drive",
        },
        {
            "name": "sdb1",
            "kname": "sdb1",
            "type": "part",
            "pkname": "sdb",
            "tran": None,
            "mountpoints": ["/media/user/USB"],
            "fstype": "vfat",
            "label": "BACKUP",
            "size": 63_000,
        },
    ]
    monkeypatch.setattr(DiskSpaceInfo, "_run_lsblk", staticmethod(lambda: rows))
    info = DiskSpaceInfo()
    devices = info.discover_usb_devices(force=True)
    assert len(devices) == 1
    assert devices[0].device_node == "/dev/sdb1"
    assert devices[0].mount_point == "/media/user/USB"
    assert devices[0].display_name == "BACKUP"


def _usb_rows(label: str = "BACKUP") -> list[dict[str, object]]:
    return [
        {
            "name": "sdb",
            "kname": "sdb",
            "type": "disk",
            "pkname": None,
            "tran": "usb",
            "mountpoints": [None],
            "size": 64_000,
            "model": "Flash Drive",
        },
        {
            "name": "sdb1",
            "kname": "sdb1",
            "type": "part",
            "pkname": "sdb",
            "tran": None,
            "mountpoints": ["/media/user/USB"],
            "fstype": "vfat",
            "label": label,
            "size": 63_000,
        },
    ]


def test_concurrent_cache_misses_share_one_scan(monkeypatch) -> None:
    import threading
    import time
    from concurrent.futures import ThreadPoolExecutor

    started = threading.Event()
    release = threading.Event()
    calls = 0
    calls_lock = threading.Lock()

    def fake_lsblk() -> list[dict[str, object]]:
        nonlocal calls
        with calls_lock:
            calls += 1
        started.set()
        assert release.wait(2)
        return _usb_rows()

    monkeypatch.setattr(DiskSpaceInfo, "_run_lsblk", staticmethod(fake_lsblk))
    info = DiskSpaceInfo()

    with ThreadPoolExecutor(max_workers=2) as pool:
        first = pool.submit(info.discover_usb_devices)
        assert started.wait(1)
        second = pool.submit(info.discover_usb_devices)
        time.sleep(0.05)
        release.set()
        assert first.result(timeout=2) == second.result(timeout=2)

    assert calls == 1
    assert info.discover_usb_devices()[0].display_name == "BACKUP"
    assert calls == 1


def test_invalidation_during_scan_retries_before_returning(monkeypatch) -> None:
    import threading
    from concurrent.futures import ThreadPoolExecutor

    first_started = threading.Event()
    release_first = threading.Event()
    calls = 0

    def fake_lsblk() -> list[dict[str, object]]:
        nonlocal calls
        calls += 1
        if calls == 1:
            first_started.set()
            assert release_first.wait(2)
            return _usb_rows("STALE")
        return _usb_rows("FRESH")

    monkeypatch.setattr(DiskSpaceInfo, "_run_lsblk", staticmethod(fake_lsblk))
    info = DiskSpaceInfo()

    with ThreadPoolExecutor(max_workers=1) as pool:
        future = pool.submit(info.discover_usb_devices)
        assert first_started.wait(1)
        info.invalidate()
        release_first.set()
        devices = future.result(timeout=3)

    assert calls == 2
    assert devices[0].display_name == "FRESH"
