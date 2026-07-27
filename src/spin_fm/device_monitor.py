"""udev-backed removable-device event monitor."""

from __future__ import annotations

import logging
from typing import Any

from .qt_compat import QObject, pyqtSignal

logger = logging.getLogger(__name__)

try:
    import pyudev
except ImportError:  # The sidebar can still refresh manually through lsblk.
    pyudev = None


class DeviceMonitor(QObject):
    """Emit a lightweight signal when a USB block device changes."""

    device_changed = pyqtSignal()

    def __init__(self, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self._observer: Any = None
        self._running = False

        if pyudev is None:
            logger.warning("pyudev is unavailable; live USB monitoring is disabled")
            return

        try:
            context = pyudev.Context()
            monitor = pyudev.Monitor.from_netlink(context)
            monitor.filter_by("block")
            self._observer = pyudev.MonitorObserver(
                monitor, callback=self._device_event
            )
            self._observer.start()
            self._running = True
        except Exception:
            logger.exception("Unable to start udev device monitoring")
            self._observer = None

    @property
    def available(self) -> bool:
        return self._running

    def _device_event(self, device: Any) -> None:
        action = getattr(device, "action", None)
        if action not in {"add", "remove", "change", "move"}:
            return
        try:
            is_usb = (
                device.get("ID_BUS") == "usb"
                or device.find_parent(subsystem="usb") is not None
            )
        except Exception:
            is_usb = False
        if is_usb:
            self.device_changed.emit()

    def stop(self) -> None:
        if not self._running:
            return
        self._running = False
        observer, self._observer = self._observer, None
        try:
            observer.stop()
        except Exception:
            logger.exception("Unable to stop udev monitor cleanly")
