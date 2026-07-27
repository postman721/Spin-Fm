"""Fast disk/device discovery helpers.

The UI calls these functions from a worker thread. ``lsblk`` is executed once
per refresh and results are cached briefly so the sidebar and status bar do not
perform duplicate hardware scans.
"""

from __future__ import annotations

import json
import logging
import os
import shutil
import subprocess
import threading
import time
from dataclasses import dataclass
from typing import Any

logger = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class DeviceInfo:
    device_node: str
    mount_point: str
    fs_type: str
    label: str
    model: str
    size_bytes: int

    @property
    def display_name(self) -> str:
        return self.label or self.model or os.path.basename(self.device_node)

    @property
    def mounted(self) -> bool:
        return bool(self.mount_point)


@dataclass(frozen=True, slots=True)
class StorageSnapshot:
    system_usage: str
    usb_usage: tuple[str, ...]


def human_size(size_bytes: int) -> str:
    value = float(max(0, size_bytes))
    units = ("B", "KiB", "MiB", "GiB", "TiB", "PiB")
    for unit in units:
        if value < 1024.0 or unit == units[-1]:
            return f"{value:.0f} {unit}" if unit == "B" else f"{value:.1f} {unit}"
        value /= 1024.0
    return f"{value:.1f} PiB"


class DiskSpaceInfo:
    """Discover USB block devices and format disk-space summaries."""

    CACHE_TTL_SECONDS = 2.0

    def __init__(self) -> None:
        self._cache: tuple[DeviceInfo, ...] = ()
        self._cache_time = 0.0
        self._generation = 0
        self._cache_generation = -1
        self._scan_in_progress = False
        self._condition = threading.Condition()

    @staticmethod
    def _flatten_devices(
        devices: list[dict[str, Any]], parent: str = ""
    ) -> list[dict[str, Any]]:
        rows: list[dict[str, Any]] = []
        for raw in devices:
            row = dict(raw)
            name = str(row.get("name") or row.get("kname") or "")
            if parent and not row.get("pkname"):
                row["pkname"] = parent
            children = row.pop("children", None) or []
            rows.append(row)
            rows.extend(DiskSpaceInfo._flatten_devices(children, name))
        return rows

    @staticmethod
    def _run_lsblk() -> list[dict[str, Any]]:
        columns = (
            "NAME,KNAME,TYPE,PKNAME,MOUNTPOINTS,TRAN,RM,HOTPLUG,FSTYPE,LABEL,SIZE,MODEL"
        )
        command = ["lsblk", "--json", "--bytes", "--output", columns]
        try:
            result = subprocess.run(
                command,
                check=True,
                capture_output=True,
                text=True,
                timeout=5,
            )
        except (
            OSError,
            subprocess.CalledProcessError,
            subprocess.TimeoutExpired,
        ) as exc:
            logger.warning("Unable to query block devices with lsblk: %s", exc)
            return []

        try:
            payload = json.loads(result.stdout)
        except json.JSONDecodeError as exc:
            logger.warning("Invalid lsblk JSON: %s", exc)
            return []
        return DiskSpaceInfo._flatten_devices(payload.get("blockdevices") or [])

    @staticmethod
    def _mount_point(row: dict[str, Any]) -> str:
        points = row.get("mountpoints")
        if isinstance(points, list):
            for value in points:
                if value:
                    return str(value)
        value = row.get("mountpoint")
        return str(value) if value else ""

    @staticmethod
    def _int_value(value: Any) -> int:
        try:
            return int(value or 0)
        except (TypeError, ValueError):
            return 0

    @staticmethod
    def _devices_from_rows(rows: list[dict[str, Any]]) -> tuple[DeviceInfo, ...]:
        by_name = {
            str(row.get("name") or row.get("kname") or ""): row
            for row in rows
            if row.get("name") or row.get("kname")
        }
        partition_parents = {
            str(row.get("pkname") or "")
            for row in rows
            if str(row.get("type") or "") == "part" and row.get("pkname")
        }

        def transport_is_usb(row: dict[str, Any]) -> bool:
            current = row
            visited: set[str] = set()
            while current:
                if str(current.get("tran") or "").lower() == "usb":
                    return True
                parent = str(current.get("pkname") or "")
                if not parent or parent in visited:
                    break
                visited.add(parent)
                current = by_name.get(parent, {})
            return False

        devices: list[DeviceInfo] = []
        seen_nodes: set[str] = set()
        for row in rows:
            device_type = str(row.get("type") or "")
            name = str(row.get("kname") or row.get("name") or "")
            logical_name = str(row.get("name") or name)
            if device_type not in {"disk", "part"} or not name:
                continue
            if device_type == "disk" and logical_name in partition_parents:
                continue
            if not transport_is_usb(row):
                continue

            node = f"/dev/{name}"
            if node in seen_nodes:
                continue
            seen_nodes.add(node)
            devices.append(
                DeviceInfo(
                    device_node=node,
                    mount_point=DiskSpaceInfo._mount_point(row),
                    fs_type=str(row.get("fstype") or "").lower(),
                    label=str(row.get("label") or "").strip(),
                    model=str(row.get("model") or "").strip(),
                    size_bytes=DiskSpaceInfo._int_value(row.get("size")),
                )
            )

        return tuple(sorted(devices, key=lambda item: item.device_node))

    def discover_usb_devices(self, force: bool = False) -> tuple[DeviceInfo, ...]:
        """Return USB devices while coalescing concurrent ``lsblk`` scans.

        The status bar and device sidebar share one :class:`DiskSpaceInfo`
        instance. A generation counter prevents a scan that started before a
        udev invalidation from publishing stale results, while the condition
        variable ensures only one worker runs ``lsblk`` at a time.
        """
        if force:
            self.invalidate()

        while True:
            with self._condition:
                now = time.monotonic()
                cache_is_current = self._cache_generation == self._generation
                cache_is_fresh = now - self._cache_time < self.CACHE_TTL_SECONDS
                if cache_is_current and cache_is_fresh:
                    return self._cache

                if self._scan_in_progress:
                    self._condition.wait()
                    continue

                self._scan_in_progress = True
                scan_generation = self._generation

            try:
                rows = self._run_lsblk()
                result = self._devices_from_rows(rows)
            except Exception:
                with self._condition:
                    self._scan_in_progress = False
                    self._condition.notify_all()
                raise

            with self._condition:
                generation_is_current = scan_generation == self._generation
                if generation_is_current:
                    self._cache = result
                    self._cache_time = time.monotonic()
                    self._cache_generation = scan_generation
                self._scan_in_progress = False
                self._condition.notify_all()

            if generation_is_current:
                return result
            # A device event invalidated the cache during this scan. Loop once
            # more so callers never receive a knowingly stale snapshot.

    def invalidate(self) -> None:
        with self._condition:
            self._generation += 1
            self._cache_time = 0.0
            self._condition.notify_all()

    @staticmethod
    def get_disk_info_string(path: str) -> str:
        try:
            usage = shutil.disk_usage(path)
        except OSError as exc:
            logger.debug("Unable to read disk usage for %s: %s", path, exc)
            return "Unavailable"
        percent = (usage.used / usage.total * 100.0) if usage.total else 0.0
        return f"{human_size(usage.used)} / {human_size(usage.total)} ({percent:.0f}%)"

    def get_usb_disk_info_strings(self) -> list[str]:
        result: list[str] = []
        for device in self.discover_usb_devices():
            if device.mount_point:
                usage = self.get_disk_info_string(device.mount_point)
                result.append(f"{device.display_name}: {usage}")
            else:
                size = (
                    human_size(device.size_bytes)
                    if device.size_bytes
                    else "unknown size"
                )
                result.append(f"{device.display_name}: not mounted ({size})")
        return result

    def get_storage_snapshot(self) -> StorageSnapshot:
        return StorageSnapshot(
            system_usage=self.get_disk_info_string(os.path.abspath(os.sep)),
            usb_usage=tuple(self.get_usb_disk_info_strings()),
        )
