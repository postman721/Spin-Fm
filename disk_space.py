#!/usr/bin/env python3
# disk_space.py
# Disable the creation of __pycache__ directories
sys.dont_write_bytecode = True

import subprocess
import os
import pyudev

class DiskSpaceInfo:
    def __init__(self):
        self.context = pyudev.Context()

    def get_all_usb_devices_with_mount_points(self):
        devices_list = []
        try:
            cmd = ["lsblk", "-lno", "NAME,TYPE,MOUNTPOINT"]
            result = subprocess.run(cmd, stdout=subprocess.PIPE, text=True, check=True)
            lines = result.stdout.strip().splitlines()
        except subprocess.CalledProcessError as e:
            print(f"[DiskSpaceInfo] lsblk error: {e.stderr}")
            lines = []

        for line in lines:
            parts = line.split(None, 2)
            if len(parts) < 2:
                continue
            name, btype = parts[0], parts[1]
            mountpoint = parts[2] if len(parts) == 3 else ""
            device_node = f"/dev/{name}"
            if btype in ("disk", "part"):
                try:
                    dev = pyudev.Devices.from_device_file(self.context, device_node)
                    parent = dev.find_parent(subsystem='usb')
                    if parent:
                        devices_list.append((device_node, mountpoint))
                except Exception as ex:
                    print(f"[DiskSpaceInfo] Could not process {device_node}: {ex}")
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
        except subprocess.CalledProcessError as e:
            print(f"[DiskSpaceInfo] df error: {e.stderr}")
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
