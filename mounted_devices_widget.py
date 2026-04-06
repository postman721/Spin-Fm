#!/usr/bin/env python3
"""USB devices side panel for Spin FM."""

import os
import subprocess
import sys
from functools import partial

from qt_compat import QLabel, QMenu, QMessageBox, QPoint, QPushButton, QTableWidget, QTableWidgetItem, QVBoxLayout, QWidget
from qt_compat import QIcon, Qt, pyqtSignal

from device_monitor import DeviceMonitor
from disk_space import DiskSpaceInfo

sys.dont_write_bytecode = True


class MountedDevicesWidget(QWidget):
    """Display removable USB devices and allow mount/unmount actions."""

    open_device = pyqtSignal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.disk_info = DiskSpaceInfo()
        self.previous_devices = set()
        self.device_monitor = None
        self.init_ui()

        # DeviceMonitor may start a background observer thread, so we keep a
        # handle to it and stop it explicitly during application shutdown.
        self.device_monitor = DeviceMonitor()
        self.device_monitor.device_changed.connect(self.update_devices)

        print("[MountedDevicesWidget] Initialized and monitoring USB devices.")
        self.update_devices()

    def init_ui(self):
        layout = QVBoxLayout()
        layout.addWidget(QLabel("USB Devices"))

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

    def shutdown(self) -> None:
        """Stop background monitoring cleanly."""
        if self.device_monitor is None:
            return
        try:
            self.device_monitor.stop()
        finally:
            self.device_monitor = None

    def update_devices(self):
        print("[MountedDevicesWidget] update_devices() called")
        usb_devices = self.disk_info.get_all_usb_devices_with_mount_points()
        current_set = set(usb_devices)
        if current_set != self.previous_devices:
            self.previous_devices = current_set
            self.populate_table(usb_devices)
            print("[MountedDevicesWidget] Table updated with new USB devices")

    def _device_icon(self, mounted: bool) -> QIcon:
        """Return a themed icon for mounted/unmounted removable media."""
        if mounted:
            return QIcon.fromTheme("drive-removable-media")
        return QIcon.fromTheme("drive-removable-media-usb")

    def populate_table(self, devices):
        """Rebuild the USB device table.

        Row count is allocated up front to avoid repeated insertRow() churn.
        """
        devices = sorted(devices, key=lambda item: item[0])
        self.table_widget.clearContents()
        self.table_widget.setRowCount(len(devices))

        for row, (device_node, mount_point) in enumerate(devices):
            device_name = os.path.basename(device_node)
            name_item = QTableWidgetItem(device_name)
            name_item.setIcon(self._device_icon(bool(mount_point)))
            name_item.setData(Qt.UserRole, (device_node, mount_point))
            self.table_widget.setItem(row, 0, name_item)

            button = QPushButton("Unmount" if mount_point else "Mount")
            if mount_point:
                button.clicked.connect(partial(self.unmount_device, device_node, mount_point))
            else:
                button.clicked.connect(partial(self.mount_device, device_node))
            self.table_widget.setCellWidget(row, 1, button)

            print(f"[MountedDevicesWidget] Row added: {device_name}, Action: {'Unmount' if mount_point else 'Mount'}")

    def on_double_click(self, row, column):
        if column == 1:
            return

        item = self.table_widget.item(row, 0)
        if item is None:
            return

        device_info = item.data(Qt.UserRole)
        if not device_info:
            return

        device_node, mount_point = device_info
        if mount_point and os.path.exists(mount_point):
            print(f"[MountedDevicesWidget] Opening device at {mount_point}")
            self.open_device.emit(mount_point)
        else:
            QMessageBox.warning(self, "Not Mounted", "This device is not mounted. Please mount it first.")

    def show_context_menu(self, pos: QPoint):
        index = self.table_widget.indexAt(pos)
        if not index.isValid():
            return

        item = self.table_widget.item(index.row(), 0)
        if item is None:
            return

        device_info = item.data(Qt.UserRole)
        if not device_info:
            return

        device_node, mount_point = device_info
        menu = QMenu(self)

        if mount_point:
            open_action = menu.addAction("Open")
            unmount_action = menu.addAction("Unmount")
            gpos = self.table_widget.viewport().mapToGlobal(pos)
            action = menu.exec(gpos) if hasattr(menu, "exec") else menu.exec_(gpos)

            if action == open_action:
                if os.path.exists(mount_point):
                    self.open_device.emit(mount_point)
                else:
                    QMessageBox.warning(self, "Not Mounted", "This device is not mounted.")
            elif action == unmount_action:
                self.unmount_device(device_node, mount_point)
        else:
            mount_action = menu.addAction("Mount")
            gpos = self.table_widget.viewport().mapToGlobal(pos)
            action = menu.exec(gpos) if hasattr(menu, "exec") else menu.exec_(gpos)
            if action == mount_action:
                self.mount_device(device_node)

    def get_fs_type(self, device_node):
        try:
            result = subprocess.run(
                ["lsblk", "-no", "FSTYPE", device_node],
                check=True,
                stdout=subprocess.PIPE,
                text=True,
            )
            return result.stdout.strip().lower()
        except Exception as exc:
            print(f"[MountedDevicesWidget] get_fs_type error: {exc}")
            return None

    def mount_device(self, device_node):
        print(f"[MountedDevicesWidget] Mounting {device_node}")
        fstype = self.get_fs_type(device_node)
        command = ["udisksctl", "mount", "-b", device_node]
        if fstype in ("vfat", "ntfs", "exfat"):
            uid = os.getuid()
            gid = os.getgid()
            options = f"uid={uid},gid={gid},umask=002"
            command += ["-o", options]

        try:
            result = subprocess.run(
                command,
                check=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
            )
            output = result.stdout.strip()
            print(f"[MountedDevicesWidget] mount output: {output}")

            if "Mounted" in output and "at" in output:
                parts = output.split(" at ", 1)
                if len(parts) == 2:
                    mount_point = parts[1].rstrip('.')
                    QMessageBox.information(self, "Success", f"Mounted at {mount_point}")
                    self.update_devices()
                    return

            QMessageBox.information(self, "Success", "Mount command succeeded")
            self.update_devices()
        except subprocess.CalledProcessError as exc:
            error_message = exc.stderr.strip() or "Mount failed."
            print(f"[MountedDevicesWidget] mount error: {error_message}")
            QMessageBox.critical(self, "Mount Error", error_message)

    def unmount_device(self, device_node, mount_point):
        print(f"[MountedDevicesWidget] Unmounting {device_node} from {mount_point}")
        reply = QMessageBox.question(
            self,
            "Confirm Unmount",
            f"Are you sure you want to unmount {device_node} from {mount_point}?",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No,
        )
        if reply != QMessageBox.Yes:
            return

        try:
            result = subprocess.run(
                ["udisksctl", "unmount", "-b", device_node],
                check=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
            )
            print(f"[MountedDevicesWidget] unmount output: {result.stdout.strip()}")
            QMessageBox.information(self, "Success", f"Unmounted {device_node}")
            self.update_devices()
        except subprocess.CalledProcessError as exc:
            error_message = exc.stderr.strip() or "Unmount failed."
            print(f"[MountedDevicesWidget] unmount error: {error_message}")
            QMessageBox.critical(self, "Unmount Error", error_message)
