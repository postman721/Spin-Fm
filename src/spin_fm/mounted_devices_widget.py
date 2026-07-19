"""Responsive removable-device sidebar for Spin FM."""

from __future__ import annotations

import logging
import os
import subprocess
from collections.abc import Callable
from functools import partial

from .device_monitor import DeviceMonitor
from .disk_space import DeviceInfo, DiskSpaceInfo, human_size
from .qt_compat import (
    QAbstractItemView,
    QHBoxLayout,
    QHeaderView,
    QIcon,
    QLabel,
    QMenu,
    QMessageBox,
    QPoint,
    QPushButton,
    QSizePolicy,
    QStyle,
    Qt,
    QTableWidget,
    QTableWidgetItem,
    QTimer,
    QToolButton,
    QVBoxLayout,
    QWidget,
    pyqtSignal,
)
from .workers import TaskManager

logger = logging.getLogger(__name__)


class MountedDevicesWidget(QWidget):
    """Display USB storage without blocking the GUI during scans/actions."""

    MINIMUM_WIDTH = 400
    DEFAULT_WIDTH = 460
    MAXIMUM_WIDTH = 780
    ACTION_COLUMN_WIDTH = 124
    ACTION_BUTTON_WIDTH = 104
    ROW_HEIGHT = 54

    open_device = pyqtSignal(str)
    status_message = pyqtSignal(str)
    operation_activity_changed = pyqtSignal(bool)

    def __init__(
        self,
        parent: QWidget | None = None,
        task_manager: TaskManager | None = None,
        disk_info: DiskSpaceInfo | None = None,
        operation_guard: Callable[[], bool] | None = None,
    ) -> None:
        super().__init__(parent)
        self.setObjectName("deviceSidebar")
        self.setMinimumWidth(self.MINIMUM_WIDTH)
        self.setMaximumWidth(self.MAXIMUM_WIDTH)
        self.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Expanding)
        self.disk_info = disk_info or DiskSpaceInfo()
        self._devices: tuple[DeviceInfo, ...] = ()
        self._refresh_pending = False
        self._refresh_queued = False
        self._device_actions: set[str] = set()
        self._shutting_down = False
        self._operation_guard = operation_guard
        self._owns_tasks = task_manager is None
        self.tasks = task_manager or TaskManager(self, max_threads=2)

        self._build_ui()

        self._refresh_timer = QTimer(self)
        self._refresh_timer.setSingleShot(True)
        self._refresh_timer.setInterval(300)
        self._refresh_timer.timeout.connect(self._start_refresh)

        self.device_monitor = DeviceMonitor(self)
        self.device_monitor.device_changed.connect(self._device_changed)
        self.schedule_refresh(force=True)

    def _device_changed(self) -> None:
        self.schedule_refresh(force=True)

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 18, 16, 16)
        layout.setSpacing(10)

        header = QHBoxLayout()
        title = QLabel("Devices", self)
        title.setObjectName("sidebarTitle")
        header.addWidget(title)
        header.addStretch(1)

        self.refresh_button = QToolButton(self)
        self.refresh_button.setObjectName("sidebarRefreshButton")
        self.refresh_button.setToolTip("Refresh removable devices")
        self._update_refresh_icon()
        self.refresh_button.clicked.connect(self._request_refresh)
        header.addWidget(self.refresh_button)
        layout.addLayout(header)

        subtitle = QLabel("USB storage and mount controls", self)
        subtitle.setObjectName("sidebarSubtitle")
        subtitle.setWordWrap(True)
        layout.addWidget(subtitle)

        self.empty_label = QLabel("No USB storage detected", self)
        self.empty_label.setObjectName("deviceEmptyState")
        self.empty_label.setAlignment(Qt.AlignCenter)
        self.empty_label.setWordWrap(True)
        layout.addWidget(self.empty_label, 1)

        self.table_widget = QTableWidget(self)
        self.table_widget.setObjectName("deviceTable")
        self.table_widget.setColumnCount(3)
        self.table_widget.setHorizontalHeaderLabels(["Device", "Status", "Action"])
        self.table_widget.verticalHeader().setVisible(False)
        header_view = self.table_widget.horizontalHeader()
        header_view.setMinimumSectionSize(96)
        header_view.setStretchLastSection(False)
        header_view.setSectionResizeMode(0, QHeaderView.Stretch)
        header_view.setSectionResizeMode(1, QHeaderView.Stretch)
        header_view.setSectionResizeMode(2, QHeaderView.Fixed)
        self.table_widget.setColumnWidth(2, self.ACTION_COLUMN_WIDTH)
        self.table_widget.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.table_widget.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.table_widget.setSelectionMode(QAbstractItemView.SingleSelection)
        self.table_widget.setHorizontalScrollMode(QAbstractItemView.ScrollPerPixel)
        self.table_widget.setVerticalScrollMode(QAbstractItemView.ScrollPerPixel)
        self.table_widget.setShowGrid(False)
        self.table_widget.setSortingEnabled(False)
        self.table_widget.setContextMenuPolicy(Qt.CustomContextMenu)
        self.table_widget.customContextMenuRequested.connect(self.show_context_menu)
        self.table_widget.cellDoubleClicked.connect(self.on_double_click)
        layout.addWidget(self.table_widget, 1)
        self.table_widget.hide()

    @property
    def devices(self) -> tuple[DeviceInfo, ...]:
        return self._devices

    @property
    def has_active_device_action(self) -> bool:
        return bool(self._device_actions)

    def _request_refresh(self) -> None:
        self.schedule_refresh(force=True)

    def schedule_refresh(self, force: bool = False) -> None:
        if self._shutting_down:
            return
        if force:
            self.disk_info.invalidate()
        if self._refresh_pending:
            self._refresh_queued = True
            return
        self._refresh_timer.start()

    def _start_refresh(self) -> None:
        if self._shutting_down:
            return
        if self._refresh_pending:
            self._refresh_queued = True
            return
        self._refresh_pending = True
        self.refresh_button.setEnabled(False)
        worker = self.tasks.submit(
            self.disk_info.discover_usb_devices,
            on_result=self._apply_devices,
            on_error=self._refresh_error,
            on_finished=self._refresh_finished,
        )
        if worker is None:
            self._refresh_finished()

    def _apply_devices(self, devices: tuple[DeviceInfo, ...]) -> None:
        if self._shutting_down:
            return
        if devices == self._devices:
            return
        self.populate_table(devices)

    def _refresh_error(self, error: dict[str, str]) -> None:
        logger.warning(
            "Device refresh failed: %s", error.get("message", "unknown error")
        )
        if not self._shutting_down:
            self.status_message.emit("Unable to refresh removable devices")

    def _refresh_finished(self) -> None:
        self._refresh_pending = False
        if self._shutting_down:
            self._refresh_queued = False
            return
        self.refresh_button.setEnabled(True)
        if self._refresh_queued:
            self._refresh_queued = False
            # The event that queued this refresh already invalidated the shared
            # cache. Avoid incrementing the generation a second time.
            self.schedule_refresh(force=False)

    def _device_icon(self, mounted: bool) -> QIcon:
        icon_name = "drive-removable-media" if mounted else "drive-removable-media-usb"
        icon = QIcon.fromTheme(icon_name)
        if icon.isNull():
            icon = self.style().standardIcon(QStyle.SP_DriveHDIcon)
        return icon

    def _update_refresh_icon(self) -> None:
        icon = QIcon.fromTheme("view-refresh")
        if icon.isNull():
            icon = self.style().standardIcon(QStyle.SP_BrowserReload)
        self.refresh_button.setIcon(icon)

    def refresh_icon_theme(self) -> None:
        """Refresh icons without reallocating rows and action buttons."""
        self._update_refresh_icon()
        for row, device in enumerate(self._devices):
            item = self.table_widget.item(row, 0)
            if item is not None:
                item.setIcon(self._device_icon(device.mounted))

    def ensure_action_column_visible(self) -> None:
        """Reassert the fixed action width after splitter or theme changes."""
        header = self.table_widget.horizontalHeader()
        header.setSectionResizeMode(2, QHeaderView.Fixed)
        self.table_widget.setColumnWidth(2, self.ACTION_COLUMN_WIDTH)
        # Keep the rightmost controls in view if a desktop style applies wider
        # header sections than Qt reported during construction.
        scrollbar = self.table_widget.horizontalScrollBar()
        if scrollbar.maximum() > 0:
            scrollbar.setValue(scrollbar.maximum())

    @staticmethod
    def _status_text(device: DeviceInfo) -> str:
        if not device.mounted:
            return "Not mounted"
        label = os.path.basename(device.mount_point.rstrip(os.sep))
        return f"Mounted · {label}" if label else "Mounted"

    def _clear_device_rows(self) -> None:
        """Release previous cell widgets before replacing device rows."""
        for row in range(self.table_widget.rowCount()):
            widget = self.table_widget.cellWidget(row, 2)
            if widget is None:
                continue
            self.table_widget.removeCellWidget(row, 2)
            widget.deleteLater()
        self.table_widget.clearContents()
        self.table_widget.setRowCount(0)

    def _update_action_buttons(self) -> None:
        for row, device in enumerate(self._devices):
            button = self.table_widget.cellWidget(row, 2)
            if button is not None:
                button.setEnabled(device.device_node not in self._device_actions)

    def populate_table(self, devices: tuple[DeviceInfo, ...]) -> None:
        devices = tuple(devices)
        self._devices = devices
        self.table_widget.setUpdatesEnabled(False)
        try:
            self._clear_device_rows()
            self.table_widget.setRowCount(len(devices))
            for row, device in enumerate(devices):
                name_item = QTableWidgetItem(device.display_name)
                name_item.setIcon(self._device_icon(device.mounted))
                name_item.setToolTip(
                    f"{device.device_node}\n"
                    f"{human_size(device.size_bytes) if device.size_bytes else 'Unknown size'}"
                )
                self.table_widget.setItem(row, 0, name_item)

                status = self._status_text(device)
                status_item = QTableWidgetItem(status)
                status_item.setToolTip(device.mount_point or status)
                self.table_widget.setItem(row, 1, status_item)

                action = QPushButton(
                    "Unmount" if device.mounted else "Mount", self.table_widget
                )
                action.setObjectName("deviceActionButton")
                action.setMinimumWidth(self.ACTION_BUTTON_WIDTH)
                action.setMinimumHeight(34)
                action.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Fixed)
                action.setEnabled(device.device_node not in self._device_actions)
                if device.mounted:
                    action.clicked.connect(partial(self.unmount_device, device))
                else:
                    action.clicked.connect(partial(self.mount_device, device))
                self.table_widget.setCellWidget(row, 2, action)
                self.table_widget.setRowHeight(row, self.ROW_HEIGHT)
        finally:
            self.table_widget.setUpdatesEnabled(True)

        self.ensure_action_column_visible()

        has_devices = bool(devices)
        self.empty_label.setVisible(not has_devices)
        self.table_widget.setVisible(has_devices)

    def _device_at_row(self, row: int) -> DeviceInfo | None:
        if 0 <= row < len(self._devices):
            return self._devices[row]
        return None

    def on_double_click(self, row: int, column: int) -> None:
        if column == 2:
            return
        device = self._device_at_row(row)
        if device is None:
            return
        if device.mount_point and os.path.isdir(device.mount_point):
            self.open_device.emit(device.mount_point)
        else:
            self.status_message.emit(f"{device.display_name} is not mounted")

    def show_context_menu(self, pos: QPoint) -> None:
        index = self.table_widget.indexAt(pos)
        if not index.isValid():
            return
        device = self._device_at_row(index.row())
        if device is None:
            return

        menu = QMenu(self)
        open_action = None
        if device.mounted:
            open_action = menu.addAction("Open")
            mount_action = menu.addAction("Unmount")
        else:
            mount_action = menu.addAction("Mount")
        action = menu.exec(self.table_widget.viewport().mapToGlobal(pos))
        if open_action is not None and action == open_action:
            self.open_device.emit(device.mount_point)
        elif action == mount_action:
            if device.mounted:
                self.unmount_device(device)
            else:
                self.mount_device(device)

    @staticmethod
    def _run_udisks(command: list[str]) -> str:
        try:
            result = subprocess.run(
                command,
                check=True,
                capture_output=True,
                text=True,
                timeout=30,
            )
        except subprocess.TimeoutExpired as exc:
            raise RuntimeError(
                "The device operation timed out after 30 seconds."
            ) from exc
        except subprocess.CalledProcessError as exc:
            detail = (exc.stderr or exc.stdout or str(exc)).strip()
            raise RuntimeError(detail or "The device operation failed.") from exc
        return result.stdout.strip()

    @classmethod
    def _mount_command(cls, device: DeviceInfo) -> str:
        command = ["udisksctl", "mount", "-b", device.device_node]
        if device.fs_type in {"vfat", "ntfs", "exfat"}:
            options = f"uid={os.getuid()},gid={os.getgid()},umask=002"
            command.extend(("-o", options))
        return cls._run_udisks(command)

    @classmethod
    def _unmount_command(cls, device: DeviceInfo) -> str:
        return cls._run_udisks(["udisksctl", "unmount", "-b", device.device_node])

    def mount_device(self, device: DeviceInfo) -> None:
        self._start_device_action(device, "Mounting", self._mount_command)

    def unmount_device(self, device: DeviceInfo) -> None:
        answer = QMessageBox.question(
            self,
            "Unmount Device",
            f"Unmount {device.display_name}?",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No,
        )
        if answer != QMessageBox.Yes:
            return
        self._start_device_action(device, "Unmounting", self._unmount_command)

    def _start_device_action(self, device: DeviceInfo, verb: str, function) -> None:
        if device.device_node in self._device_actions:
            return
        if self._operation_guard is not None and not self._operation_guard():
            self.status_message.emit("Wait for the current file operation to finish")
            return
        self._device_actions.add(device.device_node)
        self.operation_activity_changed.emit(True)
        self._update_action_buttons()
        self.status_message.emit(f"{verb} {device.display_name}…")

        worker = self.tasks.submit(
            function,
            device,
            on_result=lambda _output, d=device, v=verb: self._device_action_succeeded(
                d, v
            ),
            on_error=lambda error, d=device, v=verb: self._device_action_failed(
                d, v, error
            ),
            on_finished=lambda d=device: self._device_action_finished(d),
        )
        if worker is None:
            self._device_action_finished(device)
            self.status_message.emit(f"Could not start the {verb.lower()} operation")

    def _device_action_succeeded(self, device: DeviceInfo, verb: str) -> None:
        if self._shutting_down:
            return
        past_tense = "Mounted" if verb == "Mounting" else "Unmounted"
        self.status_message.emit(f"{past_tense} {device.display_name}")
        self.schedule_refresh(force=True)

    def _device_action_failed(
        self, device: DeviceInfo, verb: str, error: dict[str, str]
    ) -> None:
        if self._shutting_down:
            return
        message = error.get("message", "Unknown error")
        QMessageBox.critical(self, f"{verb} Failed", message)
        self.status_message.emit(f"Could not {verb.lower()} {device.display_name}")

    def _device_action_finished(self, device: DeviceInfo) -> None:
        self._device_actions.discard(device.device_node)
        if self._shutting_down:
            return
        self.operation_activity_changed.emit(bool(self._device_actions))
        self._update_action_buttons()

    def shutdown(self) -> None:
        if self._shutting_down:
            return
        self._shutting_down = True
        self._refresh_timer.stop()
        self._refresh_queued = False
        self.device_monitor.stop()
        if self._owns_tasks:
            self.tasks.shutdown(wait_msec=6_000)
        self._clear_device_rows()
        self._devices = ()
        self._device_actions.clear()
