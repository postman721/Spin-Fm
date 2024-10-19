# disk_space.py

#Spin FM v. 2.0 Copyright (c) 2021 JJ Posti <techtimejourney.net> This program comes with ABSOLUTELY NO WARRANTY; for details see: http://www.gnu.org/copyleft/gpl.html.  This is free software, and you are welcome to redistribute it under GPL Version 2, June 1991")
#!/usr/bin/env python3

import os,sys
sys.dont_write_bytecode = True
import shutil
import pyudev
import subprocess
import json

class DiskSpaceInfo:
    """
    A class to provide disk space information for USB devices.
    """

    def __init__(self):
        """
        Initializes the DiskSpaceInfo.
        """
        pass

    def get_all_usb_devices_with_mount_points(self):
        """
        Retrieves all connected USB devices along with their mount points (if any).
        
        Returns:
            A list of tuples: (device_node, mount_point)
        """
        usb_devices = []
        context = pyudev.Context()

        print("Identifying all USB partition devices...")
        for device in context.list_devices(subsystem='block', DEVTYPE='partition'):
            # Check if device is connected via USB
            is_usb = False
            if device.get('ID_BUS') == 'usb':
                is_usb = True
            elif 'ID_USB_DRIVER' in device:
                is_usb = True
            elif 'ID_USB_INTERFACE_NUM' in device:
                is_usb = True

            print(f"\nDevice: {device.device_node}")
            print(f"  ID_BUS: {device.get('ID_BUS')}")
            print(f"  ID_USB_DRIVER: {device.get('ID_USB_DRIVER')}")
            print(f"  ID_USB_INTERFACE_NUM: {device.get('ID_USB_INTERFACE_NUM')}")
            print(f"  Is USB: {is_usb}")

            if is_usb:
                # Get mount point, if any
                mount_point = self.get_mount_point(device.device_node)
                usb_devices.append((device.device_node, mount_point))
                if mount_point:
                    print(f"  USB device {device.device_node} is mounted at {mount_point}")
                else:
                    print(f"  USB device {device.device_node} is not mounted.")

        if not usb_devices:
            print("No USB partition devices found.")

        return usb_devices

    def get_mount_point(self, device_node):
        """
        Retrieves the mount point of a given device node.
        
        Args:
            device_node (str): The device node (e.g., '/dev/sda1').
        
        Returns:
            str or None: The mount point path, or None if not mounted.
        """
        try:
            result = subprocess.run(['lsblk', '-no', 'MOUNTPOINT', device_node],
                                    check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
            mount_point = result.stdout.strip()
            if mount_point:
                return mount_point
            else:
                return None
        except subprocess.CalledProcessError as e:
            print(f"Failed to get mount point for {device_node}: {e.stderr.strip()}")
            return None

    def get_disk_space_for_path(self, path):
        """
        Retrieves disk space info for a given path.
        
        Args:
            path (str): The path to check disk space for.
        
        Returns:
            dict: Disk space information or None if error.
        """
        try:
            total, used, free = shutil.disk_usage(path)
            print(f"Disk space for {path} - Total: {total}, Used: {used}, Free: {free}")
            return {
                'total_space': total,
                'used_space': used,
                'free_space': free
            }
        except FileNotFoundError as e:
            print(f"Error: {e}")
            return None

    def format_size(self, size):
        """
        Converts the size from bytes to a more human-readable format 
        (KB, MB, GB, TB).
        
        Args:
            size (int): Size in bytes.
            
        Returns:
            str: Formatted size as a string.
        """
        for unit in ['B', 'KB', 'MB', 'GB', 'TB']:
            if size < 1024:
                return f"{size:.2f} {unit}"
            size /= 1024
        return f"{size:.2f} TB"

    def get_disk_info_string(self, path='/'):
        """
        Returns the disk space information for a given path as a formatted string.
        """
        disk_space = self.get_disk_space_for_path(path)
        if disk_space:
            total = self.format_size(disk_space['total_space'])
            used = self.format_size(disk_space['used_space'])
            free = self.format_size(disk_space['free_space'])
            info = f"Path: {path} | Total: {total}, Used: {used}, Free: {free}"
            print(info)
            return info
        print("Disk space info unavailable.")
        return "Disk space info unavailable."

    def get_usb_disk_info_strings(self):
        """
        Detects and retrieves disk space information for all connected USB devices.
        
        Returns:
            A list of formatted disk space information strings for each USB device.
        """
        usb_devices_with_mounts = self.get_all_usb_devices_with_mount_points()
        usb_info_strings = []
        if not usb_devices_with_mounts:
            usb_info_strings.append("No USB devices detected.")
            print("No USB devices detected.")
            return usb_info_strings

        for device_node, mount_point in usb_devices_with_mounts:
            if mount_point:
                disk_space = self.get_disk_space_for_path(mount_point)
                if disk_space:
                    total = self.format_size(disk_space['total_space'])
                    used = self.format_size(disk_space['used_space'])
                    free = self.format_size(disk_space['free_space'])
                    info = f"USB Mount Point: {mount_point} | Total: {total}, Used: {used}, Free: {free}"
                    usb_info_strings.append(info)
                    print(info)
                else:
                    info = f"Failed to retrieve disk space for {mount_point}."
                    usb_info_strings.append(info)
                    print(info)
            else:
                # Device is not mounted
                info = f"USB Device: {device_node} is not mounted."
                usb_info_strings.append(info)
                print(info)
        return usb_info_strings

if __name__ == "__main__":
    # Example usage
    disk_info = DiskSpaceInfo()
    print("\nChecking USB devices...")
    usb_infos = disk_info.get_usb_disk_info_strings()
    for info in usb_infos:
        print(info)
