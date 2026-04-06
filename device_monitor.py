#!/usr/bin/env python3
"""USB/block-device monitor wrapper for Spin FM."""

import sys

sys.dont_write_bytecode = True

import pyudev

from qt_compat import QObject, pyqtSignal


class DeviceMonitor(QObject):
    """Emit a Qt signal whenever USB block devices change."""

    device_changed = pyqtSignal()

    def __init__(self):
        super().__init__()
        self.context = pyudev.Context()
        self.monitor = pyudev.Monitor.from_netlink(self.context)
        self.monitor.filter_by("block")
        self.observer = pyudev.MonitorObserver(self.monitor, callback=self.device_event)
        self._running = True
        self.observer.start()
        print("[DeviceMonitor] started. Checking for USB devices...")

    def device_event(self, device):
        """Forward relevant udev events to the Qt UI thread."""
        action = getattr(device, "action", None)
        node = getattr(device, "device_node", None)
        print(f"[DeviceMonitor] event: action={action}, node={node}")

        if action not in ("add", "remove", "change"):
            return

        if device.get("ID_BUS") == "usb":
            print("[DeviceMonitor] device has ID_BUS=usb => device_changed")
            self.device_changed.emit()
            return

        parent = device.find_parent(subsystem="usb")
        if parent is not None:
            print("[DeviceMonitor] device parent is USB => device_changed")
            self.device_changed.emit()

    def stop(self):
        """Stop the observer safely and idempotently."""
        if not self._running:
            return
        self._running = False
        self.observer.stop()
        print("[DeviceMonitor] Stopped")
