#!/usr/bin/env python3
# mounted_devices_widget.py
import sys
# Disable the creation of __pycache__ directories
sys.dont_write_bytecode = True
import os
import subprocess
from functools import partial

from qt_compat import QWidget, QVBoxLayout, QLabel, QTableWidget, QTableWidgetItem, QPushButton, QMenu, QMessageBox
from qt_compat import Qt, QPoint
from qt_compat import QIcon
from qt_compat import pyqtSignal

from disk_space import DiskSpaceInfo
from device_monitor import DeviceMonitor


class MountedDevicesWidget(QWidget):
    # Signal to emit the mount point of a device to open.
    open_device = pyqtSignal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.disk_info = DiskSpaceInfo()
        self.previous_devices = set()
        self.init_ui()
        self.device_monitor = DeviceMonitor()
        self.device_monitor.device_changed.connect(self.update_devices)
        print("[MountedDevicesWidget] Initialized and monitoring USB devices.")
        self.update_devices()

    def init_ui(self):
        layout = QVBoxLayout()
        label = QLabel("USB Devices")
        layout.addWidget(label)

        self.table_widget = QTableWidget()
        self.table_widget.setColumnCount(2)
        self.table_widget.setHorizontalHeaderLabels(["Name", "Action"])
        self.table_widget.horizontalHeader().setStretchLastSection(True)
        self.table_widget.setEditTriggers(QTableWidget.NoEditTriggers)
        self.table_widget.setSelectionBehavior(QTableWidget.SelectRows)
        self.table_widget.setSelectionMode(QTableWidget.SingleSelection)
        self.table_widget.setContextMenuPolicy(Qt.CustomContextMenu)
        self.table_widget.customContextMenuRequested.connect(self.show_context_menu)
        self.table_widget.cellDoubleClicked.connect(self.on_double_click)
        layout.addWidget(self.table_widget)

        self.setLayout(layout)

    def update_devices(self):
        print("[MountedDevicesWidget] update_devices() called")
        usb_devs = self.disk_info.get_all_usb_devices_with_mount_points()
        current_set = set(usb_devs)
        if current_set != self.previous_devices:
            self.previous_devices = current_set
            self.populate_table(usb_devs)
            print("[MountedDevicesWidget] Table updated with new USB devices")

    def populate_table(self, devices):
        self.table_widget.setRowCount(0)
        for device_node, mountpt in sorted(devices, key=lambda x: x[0]):
            row = self.table_widget.rowCount()
            self.table_widget.insertRow(row)

            dev_name = os.path.basename(device_node)
            name_item = QTableWidgetItem(dev_name)
            icon_path = "icons/mounted.png" if mountpt else "icons/unmounted.png"
            name_item.setIcon(QIcon(icon_path))
            # Store (device_node, mountpt) in the item's user data.
            name_item.setData(Qt.UserRole, (device_node, mountpt))
            self.table_widget.setItem(row, 0, name_item)

            btn = QPushButton("Unmount" if mountpt else "Mount")
            if mountpt:
                btn.clicked.connect(partial(self.unmount_device, device_node, mountpt))
            else:
                btn.clicked.connect(partial(self.mount_device, device_node))
            self.table_widget.setCellWidget(row, 1, btn)

            print(f"[MountedDevicesWidget] Row added: {dev_name}, Action: {'Unmount' if mountpt else 'Mount'}")

    def on_double_click(self, row, col):
        if col == 1:
            return
        item = self.table_widget.item(row, 0)
        if not item:
            return
        device_info = item.data(Qt.UserRole)
        if not device_info:
            return
        device_node, mountpt = device_info
        if mountpt and os.path.exists(mountpt):
            print(f"[MountedDevicesWidget] Opening device at {mountpt}")
            self.open_device.emit(mountpt)
        else:
            QMessageBox.warning(self, "Not Mounted", "This device is not mounted. Please mount it first.")

    def show_context_menu(self, pos: QPoint):
        index = self.table_widget.indexAt(pos)
        if not index.isValid():
            return

        row = index.row()
        item = self.table_widget.item(row, 0)
        if not item:
            return

        device_info = item.data(Qt.UserRole)
        if not device_info:
            return

        device_node, mountpt = device_info

        menu = QMenu(self)

        if mountpt:
            open_action = menu.addAction("Open")
            unmount_action = menu.addAction("Unmount")

            gpos = self.table_widget.viewport().mapToGlobal(pos)
            action = menu.exec(gpos) if hasattr(menu, "exec") else menu.exec_(gpos)

            if action == open_action:
                if os.path.exists(mountpt):
                    self.open_device.emit(mountpt)
                else:
                    QMessageBox.warning(self, "Not Mounted", "This device is not mounted.")
            elif action == unmount_action:
                self.unmount_device(device_node, mountpt)

        else:
            mount_action = menu.addAction("Mount")

            gpos = self.table_widget.viewport().mapToGlobal(pos)
            action = menu.exec(gpos) if hasattr(menu, "exec") else menu.exec_(gpos)

            if action == mount_action:
                self.mount_device(device_node)

    def get_fs_type(self, device_node):
        try:
            r = subprocess.run(["lsblk", "-no", "FSTYPE", device_node],
                               check=True, stdout=subprocess.PIPE, text=True)
            return r.stdout.strip().lower()
        except Exception as e:
            print(f"[MountedDevicesWidget] get_fs_type error: {e}")
            return None

    def mount_device(self, device_node):
        print(f"[MountedDevicesWidget] Mounting {device_node}")
        fstype = self.get_fs_type(device_node)
        cmd = ["udisksctl", "mount", "-b", device_node]
        if fstype in ("vfat", "ntfs", "exfat"):
            uid = os.getuid()
            gid = os.getgid()
            opts = f"uid={uid},gid={gid},umask=002"
            cmd += ["-o", opts]
        try:
            r = subprocess.run(cmd, check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
            out = r.stdout.strip()
            print(f"[MountedDevicesWidget] mount output: {out}")
            if "Mounted" in out and "at" in out:
                parts = out.split(" at ")
                if len(parts) == 2:
                    mp = parts[1].rstrip('.')
                    QMessageBox.information(self, "Success", f"Mounted at {mp}")
            else:
                QMessageBox.information(self, "Success", "Mount command succeeded")
            self.update_devices()
        except subprocess.CalledProcessError as e:
            err_msg = e.stderr.strip()
            print(f"[MountedDevicesWidget] mount error: {err_msg}")
            QMessageBox.critical(self, "Mount Error", err_msg)

    def unmount_device(self, device_node, mount_point):
        print(f"[MountedDevicesWidget] Unmounting {device_node} from {mount_point}")
        reply = QMessageBox.question(
            self, "Confirm Unmount",
            f"Are you sure you want to unmount {device_node} from {mount_point}?",
            QMessageBox.Yes | QMessageBox.No, QMessageBox.No
        )
        if reply == QMessageBox.Yes:
            try:
                r = subprocess.run(["udisksctl", "unmount", "-b", device_node],
                                   check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
                print(f"[MountedDevicesWidget] unmount output: {r.stdout.strip()}")
                QMessageBox.information(self, "Success", f"Unmounted {device_node}")
                self.update_devices()
            except subprocess.CalledProcessError as e:
                err = e.stderr.strip()
                print(f"[MountedDevicesWidget] unmount error: {err}")
                QMessageBox.critical(self, "Unmount Error", err)
