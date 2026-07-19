"""Main application window for Spin FM."""

from __future__ import annotations

import logging
import os
from collections.abc import Sequence
from pathlib import Path

from . import __version__
from .audio_player import AudioPlayerWidget
from .config import SETTINGS_APPLICATION, SETTINGS_ORGANIZATION
from .disk_space import DiskSpaceInfo, StorageSnapshot
from .file_ops import OperationReport, empty_trash
from .icon_theme_manager import IconThemeManager
from .launch import launch_default
from .mounted_devices_widget import MountedDevicesWidget
from .qt_compat import (
    QAction,
    QActionGroup,
    QApplication,
    QEvent,
    QIcon,
    QLabel,
    QMainWindow,
    QMessageBox,
    QPixmapCache,
    QPoint,
    QProgressBar,
    QSettings,
    QSplitter,
    QStatusBar,
    Qt,
    QTimer,
    QVBoxLayout,
    QWidget,
)
from .tabs import Tabs
from .theme_manager import ThemeManager
from .workers import TaskManager

logger = logging.getLogger(__name__)


class MainWindow(QMainWindow):
    """Own application-level state, menus, tasks, and persistent layout."""

    def __init__(self, startup_paths: Sequence[str] | None = None) -> None:
        super().__init__()
        self.setObjectName("mainWindow")
        self.setWindowTitle("Spin FM")
        self.setMinimumSize(900, 560)

        self.settings = QSettings(SETTINGS_ORGANIZATION, SETTINGS_APPLICATION)
        self.background_tasks = TaskManager(self, max_threads=2)
        self.disk_info = DiskSpaceInfo()
        self._disk_refresh_pending = False
        self._empty_trash_busy = False
        self._shortcut_filter_installed = False
        self._closing = False
        self._last_sidebar_width = self._setting_int(
            "window/sidebar_width",
            MountedDevicesWidget.DEFAULT_WIDTH,
            MountedDevicesWidget.MINIMUM_WIDTH,
            MountedDevicesWidget.MAXIMUM_WIDTH,
        )
        self.show_hidden_files = self._setting_bool("view/show_hidden_files", False)

        self.theme_manager = ThemeManager(
            str(Path(__file__).resolve().parent / "themes")
        )
        saved_theme = str(self.settings.value("appearance/theme", "light"))
        if not self.theme_manager.load_and_apply_theme(saved_theme):
            saved_theme = "light"
            self.theme_manager.load_and_apply_theme(saved_theme)

        self.icon_theme_manager = IconThemeManager()
        saved_icon_theme = str(self.settings.value("appearance/icon_theme", "") or "")
        if self.icon_theme_manager.load_and_apply_theme(saved_icon_theme):
            applied_icon_theme = self.icon_theme_manager.current_theme
            if applied_icon_theme and applied_icon_theme != saved_icon_theme:
                self.settings.setValue("appearance/icon_theme", applied_icon_theme)

        self._build_central_ui()
        self._build_status_bar()
        self._build_menus(saved_theme)
        self._install_application_shortcut_filter()
        self._connect_activity_signals()
        self._restore_window_state()

        self.disk_timer = QTimer(self)
        self.disk_timer.setInterval(15_000)
        self.disk_timer.timeout.connect(self.update_disk_space)
        self.disk_timer.start()
        QTimer.singleShot(0, self.update_disk_space)

        startup_items = tuple(startup_paths or ())
        if startup_items:
            QTimer.singleShot(
                0, lambda paths=startup_items: self.open_startup_paths(paths)
            )

    def _build_central_ui(self) -> None:
        self.central_container = QWidget(self)
        self.central_container.setObjectName("centralContainer")
        central_layout = QVBoxLayout(self.central_container)
        central_layout.setContentsMargins(0, 0, 0, 0)
        central_layout.setSpacing(0)
        self.setCentralWidget(self.central_container)

        self.splitter = QSplitter(Qt.Horizontal, self.central_container)
        self.splitter.setObjectName("mainSplitter")
        self.splitter.setChildrenCollapsible(False)
        self.splitter.setHandleWidth(5)
        central_layout.addWidget(self.splitter, 1)

        self.tabs = Tabs(self.splitter)
        self.tabs.update_hidden_files(self.show_hidden_files)

        self.mounted_devices_widget = MountedDevicesWidget(
            self.splitter,
            task_manager=self.background_tasks,
            disk_info=self.disk_info,
            operation_guard=self._device_operation_allowed,
        )
        self.splitter.addWidget(self.mounted_devices_widget)

        self.splitter.addWidget(self.tabs)
        self.splitter.setStretchFactor(0, 0)
        self.splitter.setStretchFactor(1, 1)
        self.splitter.setSizes([self._last_sidebar_width, 820])
        self.splitter.splitterMoved.connect(self._sidebar_splitter_moved)

        self.mounted_devices_widget.open_device.connect(self.open_usb_device)
        self.mounted_devices_widget.status_message.connect(self.show_status)
        self.mounted_devices_widget.operation_activity_changed.connect(
            self.tabs.set_external_operation_busy
        )

        self.audio_player = AudioPlayerWidget(self.central_container)
        self.audio_player.hide()
        central_layout.addWidget(self.audio_player)
        self.tabs.audio_requested.connect(self.play_audio_file)
        self.audio_player.status_message.connect(self.show_status)
        self.audio_player.open_externally_requested.connect(self.open_audio_externally)

    def _device_operation_allowed(self) -> bool:
        return not self.tabs.is_busy and not self._empty_trash_busy

    def _build_status_bar(self) -> None:
        self.status_bar = QStatusBar(self)
        self.status_bar.setObjectName("mainStatusBar")
        self.setStatusBar(self.status_bar)

        self.activity_bar = QProgressBar(self.status_bar)
        self.activity_bar.setObjectName("activityProgress")
        self.activity_bar.setTextVisible(False)
        self.activity_bar.setFixedWidth(110)
        self.activity_bar.setFixedHeight(10)
        self.activity_bar.hide()
        self.status_bar.addPermanentWidget(self.activity_bar)

        self.disk_label = QLabel("Checking storage…", self.status_bar)
        self.disk_label.setObjectName("diskStatusLabel")
        self.disk_label.setToolTip("System and removable storage usage")
        self.status_bar.addPermanentWidget(self.disk_label, 1)

    def _build_menus(self, selected_theme: str) -> None:
        file_menu = self.menuBar().addMenu("&File")

        new_tab = QAction("New Tab", self)
        new_tab.setShortcut("Ctrl+T")
        new_tab.triggered.connect(
            lambda: self.tabs.createNewTab(self.tabs.currentPath())
        )
        file_menu.addAction(new_tab)

        new_folder = QAction("New Folder", self)
        new_folder.setShortcut("Ctrl+Shift+N")
        new_folder.triggered.connect(self.tabs.createNewFolder)
        file_menu.addAction(new_folder)

        file_menu.addSeparator()
        empty_action = QAction("Empty Trash…", self)
        empty_action.triggered.connect(self.empty_trash)
        file_menu.addAction(empty_action)

        file_menu.addSeparator()
        quit_action = QAction("Quit", self)
        quit_action.setShortcut("Ctrl+Q")
        quit_action.triggered.connect(self.close)
        file_menu.addAction(quit_action)

        view_menu = self.menuBar().addMenu("&View")
        self.show_hidden_files_action = QAction(
            "Show Hidden Files", self, checkable=True
        )
        self.show_hidden_files_action.setShortcut("Ctrl+H")
        self.show_hidden_files_action.setChecked(self.show_hidden_files)
        self.show_hidden_files_action.toggled.connect(self.toggle_hidden_files)
        view_menu.addAction(self.show_hidden_files_action)

        refresh_action = QAction("Refresh", self)
        refresh_action.setShortcut("F5")
        refresh_action.triggered.connect(self.tabs.refreshCurrentTab)
        view_menu.addAction(refresh_action)

        view_menu.addSeparator()
        self.play_pause_action = QAction("Play/Pause Audio", self)
        self.play_pause_action.setShortcut("Alt+P")
        self.play_pause_action.setShortcutContext(Qt.WindowShortcut)
        self.play_pause_action.setStatusTip("Toggle the embedded audio player")
        self.play_pause_action.triggered.connect(self.toggle_audio_playback)
        view_menu.addAction(self.play_pause_action)

        self.mute_audio_action = QAction("Mute/Unmute Audio", self)
        self.mute_audio_action.setShortcut("Alt+M")
        self.mute_audio_action.setShortcutContext(Qt.WindowShortcut)
        self.mute_audio_action.setStatusTip("Mute or unmute the embedded audio player")
        self.mute_audio_action.triggered.connect(self.toggle_audio_muted)
        view_menu.addAction(self.mute_audio_action)

        self.sidebar_action = QAction("Show Devices Sidebar", self, checkable=True)
        self.sidebar_action.setChecked(True)
        self.sidebar_action.setShortcut("F9")
        self.sidebar_action.toggled.connect(self.set_devices_sidebar_visible)
        view_menu.addAction(self.sidebar_action)

        appearance_menu = self.menuBar().addMenu("&Appearance")
        themes_menu = appearance_menu.addMenu("Application Theme")
        self.theme_action_group = QActionGroup(self)
        self.theme_action_group.setExclusive(True)
        for theme in self.theme_manager.get_available_themes():
            action = QAction(self._friendly_name(theme), self, checkable=True)
            action.setData(theme)
            action.setChecked(theme == selected_theme)
            action.triggered.connect(
                lambda _checked=False, name=theme: self.change_theme(name)
            )
            self.theme_action_group.addAction(action)
            themes_menu.addAction(action)

        self.icon_themes_menu = appearance_menu.addMenu("Icon Theme")
        self.icon_themes_menu.aboutToShow.connect(self._populate_icon_theme_menu)
        self._icon_menu_populated = False

        help_menu = self.menuBar().addMenu("&Help")
        about_action = QAction("About Spin FM", self)
        about_action.triggered.connect(self.show_about)
        help_menu.addAction(about_action)

    def _install_application_shortcut_filter(self) -> None:
        """Route audio shortcuts before focused child widgets can consume them."""
        application = QApplication.instance()
        if application is None or self._shortcut_filter_installed:
            return
        application.installEventFilter(self)
        self._shortcut_filter_installed = True

    @staticmethod
    def _audio_shortcut_command(event) -> str | None:
        try:
            if event.type() not in (QEvent.ShortcutOverride, QEvent.KeyPress):
                return None
            relevant_modifiers = (
                Qt.AltModifier | Qt.ControlModifier | Qt.ShiftModifier | Qt.MetaModifier
            )
            pressed_modifiers = event.modifiers() & relevant_modifiers
            if pressed_modifiers != Qt.AltModifier:
                return None
            if event.key() == Qt.Key_P:
                return "play_pause"
            if event.key() == Qt.Key_M:
                return "mute"
        except Exception:
            return None
        return None

    def eventFilter(self, watched, event):  # noqa: N802 - Qt API name
        command = self._audio_shortcut_command(event)
        if command is None or not self.isVisible():
            return super().eventFilter(watched, event)

        try:
            active_window = QApplication.activeWindow()
            if active_window is not None and active_window is not self:
                return super().eventFilter(watched, event)
            if QApplication.activeModalWidget() is not None:
                return super().eventFilter(watched, event)
        except Exception:
            pass

        if event.type() == QEvent.ShortcutOverride:
            event.accept()
            return True

        event.accept()
        try:
            auto_repeat = bool(event.isAutoRepeat())
        except Exception:
            auto_repeat = False
        if not auto_repeat:
            if command == "play_pause":
                self.toggle_audio_playback()
            else:
                self.toggle_audio_muted()
        return True

    def toggle_audio_playback(self, _checked: bool = False) -> bool:
        """Toggle the embedded player and provide feedback when none is loaded."""
        toggled = self.audio_player.toggle_playback()
        if not toggled and not self.audio_player.current_path:
            self.show_status("No audio track is loaded")
        return toggled

    def toggle_audio_muted(self, _checked: bool = False) -> bool:
        """Mute or unmute the embedded player when a track is loaded."""
        if not self.audio_player.current_path:
            self.show_status("No audio track is loaded")
            return False
        self.audio_player.toggle_muted()
        return True

    @staticmethod
    def _friendly_name(value: str) -> str:
        return value.replace("_", " ").replace("-", " ").title()

    def _populate_icon_theme_menu(self) -> None:
        if self._icon_menu_populated:
            return
        self._icon_menu_populated = True
        current_name = QIcon.themeName()

        group = QActionGroup(self)
        group.setExclusive(True)
        self.icon_theme_action_group = group
        themes = self.icon_theme_manager.get_available_icon_themes()
        if not themes:
            action = self.icon_themes_menu.addAction("No icon themes found")
            action.setEnabled(False)
            return
        for theme in themes:
            action = QAction(self._friendly_name(theme), self, checkable=True)
            action.setChecked(theme == current_name)
            action.triggered.connect(
                lambda _checked=False, name=theme: self.change_icon_theme(name)
            )
            group.addAction(action)
            self.icon_themes_menu.addAction(action)

    def _connect_activity_signals(self) -> None:
        self.tabs.status_message.connect(self.show_status)
        self.tabs.operation_started.connect(self._operation_started)
        self.tabs.operation_progress.connect(self._operation_progress)
        self.tabs.operation_finished.connect(self._operation_finished)

    def _setting_bool(self, key: str, default: bool) -> bool:
        value = self.settings.value(key, default)
        if isinstance(value, bool):
            return value
        if value is None:
            return default
        return str(value).strip().lower() in {"1", "true", "yes", "on"}

    def _setting_int(
        self, key: str, default: int, minimum: int, maximum: int
    ) -> int:
        try:
            value = int(self.settings.value(key, default))
        except (TypeError, ValueError):
            value = default
        return max(minimum, min(maximum, value))

    def _sidebar_splitter_moved(self, _position: int, _index: int) -> None:
        self._remember_sidebar_width()
        self.mounted_devices_widget.ensure_action_column_visible()

    def _remember_sidebar_width(self) -> None:
        if self.mounted_devices_widget.isHidden():
            return
        sizes = self.splitter.sizes()
        if not sizes or sizes[0] < MountedDevicesWidget.MINIMUM_WIDTH:
            return
        self._last_sidebar_width = max(
            MountedDevicesWidget.MINIMUM_WIDTH,
            min(MountedDevicesWidget.MAXIMUM_WIDTH, sizes[0]),
        )

    def _ensure_sidebar_width(self) -> None:
        if self.mounted_devices_widget.isHidden():
            return

        sizes = self.splitter.sizes()
        if len(sizes) < 2:
            return
        target = max(
            MountedDevicesWidget.MINIMUM_WIDTH,
            min(MountedDevicesWidget.MAXIMUM_WIDTH, self._last_sidebar_width),
        )
        total = max(sum(sizes), target + 420)
        if sizes[0] < target:
            self.splitter.setSizes([target, max(420, total - target)])
        self.mounted_devices_widget.ensure_action_column_visible()

    def set_devices_sidebar_visible(self, visible: bool) -> None:
        visible = bool(visible)
        if not visible:
            self._remember_sidebar_width()
        self.mounted_devices_widget.setVisible(visible)
        if visible:
            self.mounted_devices_widget.schedule_refresh(force=False)
            QTimer.singleShot(0, self._ensure_sidebar_width)

    def _restore_window_state(self) -> None:
        geometry = self.settings.value("window/geometry")
        state = self.settings.value("window/state")
        splitter_state = self.settings.value("window/splitter")
        restored = False
        if geometry is not None:
            try:
                restored = bool(self.restoreGeometry(geometry))
            except Exception:
                restored = False
        if state is not None:
            try:
                self.restoreState(state)
            except Exception:
                pass
        if splitter_state is not None:
            try:
                self.splitter.restoreState(splitter_state)
            except Exception:
                pass
        self._remember_sidebar_width()
        sidebar_visible = self._setting_bool("view/sidebar_visible", True)
        self.sidebar_action.blockSignals(True)
        self.sidebar_action.setChecked(sidebar_visible)
        self.sidebar_action.blockSignals(False)
        self.set_devices_sidebar_visible(sidebar_visible)

        if not restored:
            self.resize(1280, 800)
            self.center_window()

    def _save_window_state(self) -> None:
        self._remember_sidebar_width()
        self.settings.setValue("window/geometry", self.saveGeometry())
        self.settings.setValue("window/state", self.saveState())
        self.settings.setValue("window/splitter", self.splitter.saveState())
        self.settings.setValue("window/sidebar_width", self._last_sidebar_width)
        self.settings.setValue(
            "view/sidebar_visible", not self.mounted_devices_widget.isHidden()
        )
        self.settings.sync()

    def change_theme(self, theme_name: str) -> None:
        if self.theme_manager.load_and_apply_theme(theme_name):
            self.settings.setValue("appearance/theme", theme_name)
            self.show_status(f"Theme changed to {self._friendly_name(theme_name)}")

    def change_icon_theme(self, icon_theme_name: str) -> None:
        if not self.icon_theme_manager.load_and_apply_theme(icon_theme_name):
            self.show_status("Unable to apply the selected icon theme")
            return
        self.settings.setValue("appearance/icon_theme", icon_theme_name)
        self.refresh_icons()
        self.show_status(
            f"Icon theme changed to {self._friendly_name(icon_theme_name)}"
        )

    def refresh_icons(self) -> None:
        try:
            QPixmapCache.clear()
        except Exception:
            pass
        self.tabs.refresh_icon_theme()
        self.mounted_devices_widget.refresh_icon_theme()
        self.audio_player.refresh_icons()

    def toggle_hidden_files(self, checked: bool) -> None:
        self.show_hidden_files = bool(checked)
        self.settings.setValue("view/show_hidden_files", self.show_hidden_files)
        self.tabs.update_hidden_files(self.show_hidden_files)
        self.show_status("Hidden files shown" if checked else "Hidden files hidden")

    def show_status(self, message: str, timeout: int = 4_000) -> None:
        self.status_bar.showMessage(message, timeout)

    def _operation_started(self, label: str, total: int) -> None:
        self.activity_bar.show()
        if total > 0:
            self.activity_bar.setRange(0, total)
            self.activity_bar.setValue(0)
        else:
            self.activity_bar.setRange(0, 0)
        self.show_status(label, 0)

    def _operation_progress(self, current: int, total: int, label: str) -> None:
        if total > 0:
            self.activity_bar.setRange(0, total)
            self.activity_bar.setValue(current)
        if label:
            self.show_status(label, 0)

    def _operation_finished(self, message: str) -> None:
        self.activity_bar.hide()
        self.activity_bar.setRange(0, 1)
        self.activity_bar.setValue(0)
        self.show_status(message)

    def empty_trash(self) -> None:
        if self._empty_trash_busy:
            self.show_status("Trash cleanup is already running")
            return
        if self.tabs.is_busy or self.mounted_devices_widget.has_active_device_action:
            self.show_status("Wait for the current file or device operation to finish")
            return
        answer = QMessageBox.question(
            self,
            "Empty Trash",
            "Permanently remove everything from Trash?",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No,
        )
        if answer != QMessageBox.Yes:
            return

        self._empty_trash_busy = True
        self.tabs.set_external_operation_busy(True)
        self._operation_started("Emptying Trash…", 0)
        worker = self.background_tasks.submit(
            empty_trash,
            with_progress=True,
            on_progress=self._trash_progress,
            on_result=self._trash_finished,
            on_error=self._trash_worker_error,
            on_finished=self._trash_task_released,
        )
        if worker is None:
            self._trash_task_released()
            self._operation_finished("Trash cleanup could not be started")

    def _trash_progress(self, payload: tuple[int, int, str]) -> None:
        current, total, name = payload
        self._operation_progress(current, total, f"Removing {name}…")

    def _trash_finished(self, report: OperationReport) -> None:
        if report.error_count:
            details = "\n".join(report.details)
            QMessageBox.warning(
                self,
                "Trash Cleanup",
                f"Removed {report.completed} entries; {report.error_count} failed.\n\n{details}",
            )
        message = (
            "Trash is already empty"
            if report.completed == 0 and not report.error_count
            else f"Removed {report.completed} Trash entries"
        )
        self._operation_finished(message)
        self.tabs.refreshCurrentTab()

    def _trash_worker_error(self, error: dict[str, str]) -> None:
        QMessageBox.critical(
            self, "Trash Cleanup Failed", error.get("message", "Unknown error")
        )
        self._operation_finished("Trash cleanup failed")

    def _trash_task_released(self) -> None:
        self._empty_trash_busy = False
        self.tabs.set_external_operation_busy(False)

    def update_disk_space(self) -> None:
        if self._disk_refresh_pending:
            return
        self._disk_refresh_pending = True
        worker = self.background_tasks.submit(
            self.disk_info.get_storage_snapshot,
            on_result=self._apply_storage_snapshot,
            on_error=self._storage_error,
            on_finished=self._storage_finished,
        )
        if worker is None:
            self._storage_finished()

    def _apply_storage_snapshot(self, snapshot: StorageSnapshot) -> None:
        usb = " • ".join(snapshot.usb_usage) if snapshot.usb_usage else "No USB storage"
        self.disk_label.setText(f"System {snapshot.system_usage}   |   {usb}")

    def _storage_error(self, error: dict[str, str]) -> None:
        logger.debug("Storage refresh failed: %s", error.get("message", ""))
        self.disk_label.setText("Storage information unavailable")

    def _storage_finished(self) -> None:
        self._disk_refresh_pending = False

    def center_window(self) -> None:
        screen = self.screen()
        if screen is None:
            return
        geometry = screen.availableGeometry()
        x = max(0, (geometry.width() - self.width()) // 2)
        y = max(0, (geometry.height() - self.height()) // 2)
        self.move(geometry.topLeft() + QPoint(x, y))

    def open_startup_paths(self, paths: Sequence[str]) -> None:
        try:
            self.tabs.openStartupPaths(paths)
        except Exception as exc:
            logger.exception("Unable to open startup path arguments")
            QMessageBox.warning(
                self, "Open Path", f"Could not open the requested path(s):\n{exc}"
            )

    def play_audio_file(self, path: str) -> None:
        """Play a supported audio file in the embedded, lazy-loaded player."""
        if self.audio_player.play_file(path):
            return

        reason = self.audio_player.backend_error or "Embedded playback unavailable"
        self.show_status(f"{reason}; opening the file externally")
        self.open_audio_externally(path, stop_internal=False)

    def open_audio_externally(self, path: str, stop_internal: bool = True) -> None:
        """Open an audio file with the desktop default application."""
        if stop_internal:
            self.audio_player.stop()
        self.audio_player.notify_external_open(path)
        try:
            launch_default(path)
        except Exception as exc:
            QMessageBox.warning(
                self,
                "Open Audio",
                f"The audio file could not be opened:\n\n{exc}",
            )
            self.show_status("Audio file could not be opened")

    def open_usb_device(self, mount_point: str) -> None:
        if os.path.isdir(mount_point):
            self.tabs.createNewTab(mount_point)
        else:
            self.show_status("The selected mount point is no longer available")
            self.mounted_devices_widget.schedule_refresh(force=True)

    def show_about(self) -> None:
        QMessageBox.about(
            self,
            "About Spin FM",
            f"<b>Spin FM {__version__}</b><br><br>"
            "A lightweight, tabbed file manager for Linux with removable-device "
            "support, asynchronous file operations, a seekable embedded audio "
            "player, optional Wayland_OSD integration, and Qt5/Qt6 "
            "compatibility.<br><br>"
            "Copyright © 2021–2026 JJ Posti<br>GNU GPL version 2 or later.",
        )

    def closeEvent(self, event) -> None:  # noqa: N802 - Qt API name
        if self._closing:
            event.accept()
            return
        if (
            self.tabs.is_busy
            or self._empty_trash_busy
            or self.mounted_devices_widget.has_active_device_action
        ):
            QMessageBox.information(
                self,
                "Operation in Progress",
                "A file or device operation is still running. Close Spin FM after it finishes.",
            )
            event.ignore()
            return

        self._closing = True
        self._save_window_state()
        self.disk_timer.stop()
        application = QApplication.instance()
        if application is not None and self._shortcut_filter_installed:
            application.removeEventFilter(self)
            self._shortcut_filter_installed = False
        for name, shutdown in (
            ("audio player", self.audio_player.shutdown),
            ("tabs", self.tabs.shutdown),
            ("device sidebar", self.mounted_devices_widget.shutdown),
        ):
            try:
                shutdown()
            except Exception:
                logger.exception("Unable to shut down the %s cleanly", name)
        # Storage probes have a five-second subprocess timeout. Give them enough
        # time to exit cleanly so no worker outlives its QObject receivers.
        if not self.background_tasks.shutdown(wait_msec=6_000):
            logger.warning("Background tasks were still active during shutdown")
        super().closeEvent(event)
