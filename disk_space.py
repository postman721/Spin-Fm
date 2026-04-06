#!/usr/bin/env python3
# disk_space.py
from __future__ import annotations

import os
import shlex
import subprocess
import sys

import pyudev

# Disable the creation of __pycache__ directories
sys.dont_write_bytecode = True


class DiskSpaceInfo:
    def __init__(self):
        self.context = pyudev.Context()

    def _lsblk_entries(self):
        """Return lsblk rows as dictionaries.

        Using key=value output keeps mount points with spaces intact and gives
        us PKNAME so we can suppress parent disks when child partitions exist.
        """
        try:
            result = subprocess.run(
                ["lsblk", "-P", "-o", "NAME,TYPE,PKNAME,MOUNTPOINT"],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                check=True,
            )
        except subprocess.CalledProcessError as exc:
            print(f"[DiskSpaceInfo] lsblk error: {exc.stderr}")
            return []

        entries = []
        for line in result.stdout.strip().splitlines():
            row = {}
            for token in shlex.split(line):
                if "=" not in token:
                    continue
                key, value = token.split("=", 1)
                row[key.lower()] = value
            if row:
                entries.append(row)
        return entries

    def _is_usb_device(self, device_node: str) -> bool:
        try:
            dev = pyudev.Devices.from_device_file(self.context, device_node)
        except Exception as exc:
            print(f"[DiskSpaceInfo] Could not process {device_node}: {exc}")
            return False

        if dev.get("ID_BUS") == "usb":
            return True
        return dev.find_parent(subsystem="usb") is not None

    def get_all_usb_devices_with_mount_points(self):
        """Return removable USB devices as (device_node, mountpoint) tuples.

        Prefer partitions over parent disks. This prevents duplicate rows like
        /dev/sdb and /dev/sdb1 for the same USB stick and avoids trying to mount
        or unmount the wrong node from the UI.
        """
        entries = self._lsblk_entries()
        if not entries:
            return []

        partition_parents = {
            entry.get("pkname", "")
            for entry in entries
            if entry.get("type") == "part" and entry.get("pkname")
        }

        devices_list = []
        seen = set()
        for entry in entries:
            device_type = entry.get("type", "")
            if device_type not in {"disk", "part"}:
                continue

            name = entry.get("name", "")
            if not name:
                continue

            # If a disk has child partitions, show the child partition rows and
            # suppress the parent disk row to avoid duplicate actions.
            if device_type == "disk" and name in partition_parents:
                continue

            device_node = f"/dev/{name}"
            if not self._is_usb_device(device_node):
                continue

            mountpoint = entry.get("mountpoint", "") or ""
            item = (device_node, mountpoint)
            if item in seen:
                continue
            seen.add(item)
            devices_list.append(item)

        return devices_list

    def get_disk_info_string(self, path):
        try:
            result = subprocess.run(["df", "-h", path], capture_output=True, text=True, check=True)
            lines = result.stdout.strip().splitlines()
            if len(lines) >= 2:
                fields = lines[1].split()
                size = fields[1]
                used = fields[2]
                used_pct = fields[4]
                return f"{used} / {size} ({used_pct})"
            else:
                return "N/A"
        except subprocess.CalledProcessError as exc:
            print(f"[DiskSpaceInfo] df error: {exc.stderr}")
            return "N/A"

    def get_usb_disk_info_strings(self):
        usb_devs = self.get_all_usb_devices_with_mount_points()
        info_list = []
        for device_node, mountpt in usb_devs:
            if mountpt:
                usage = self.get_disk_info_string(mountpt)
                info_list.append(f"{device_node} -> {usage}")
            else:
                info_list.append(f"{device_node} -> Not mounted")
        return info_list
