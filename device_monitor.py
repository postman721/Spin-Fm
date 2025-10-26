#!/usr/bin/env python3
# device_monitor.py
import sys
# Disable the creation of __pycache__ directories
sys.dont_write_bytecode = True
from qt_compat import QObject, pyqtSignal
import pyudev

class DeviceMonitor(QObject):
    device_changed = pyqtSignal()

    def __init__(self):
        super().__init__()
        self.context = pyudev.Context()
        self.monitor = pyudev.Monitor.from_netlink(self.context)
        self.monitor.filter_by('block')
        self.observer = pyudev.MonitorObserver(self.monitor, callback=self.device_event)
        self.observer.start()
        print("[DeviceMonitor] started. Checking for USB devices...")

    def device_event(self, device):
        action = getattr(device, 'action', None)
        node = getattr(device, 'device_node', None)
        print(f"[DeviceMonitor] event: action={action}, node={node}")
        if action in ("add", "remove", "change"):
            if device.get("ID_BUS") == "usb":
                print("[DeviceMonitor] device has ID_BUS=usb => device_changed")
                self.device_changed.emit()
            else:
                parent = device.find_parent(subsystem='usb')
                if parent:
                    print("[DeviceMonitor] device parent is USB => device_changed")
                    self.device_changed.emit()

    def stop(self):
        self.observer.stop()
        print("[DeviceMonitor] Stopped")
