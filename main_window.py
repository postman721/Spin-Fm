#!/usr/bin/env python3
"""Main window for Spin FM.

This file keeps application-level concerns together: menus, persistent UI
settings, USB panel, status bar updates, and clean shutdown handling.
"""

import logging
import os
import sys
from pathlib import Path

from qt_compat import QApplication, QMainWindow, QMessageBox, QPoint, QSettings, QSplitter, QStatusBar, QTimer, Qt
from qt_compat import QAction

from disk_space import DiskSpaceInfo
from empty_trash import empty_trash
from icon_theme_manager import IconThemeManager
from mounted_devices_widget import MountedDevicesWidget
from tabs import Tabs
from theme_manager import ThemeManager

sys.dont_write_bytecode = True

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

SETTINGS_ORG = "Spin"
SETTINGS_APP = "Spin FM"


class MainWindow(QMainWindow):
    """Main application window for the Spin FM file manager."""

    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle("Spin FM")
        logger.info("MainWindow initialized.")

        # Persistent settings are shared across sessions.
        self.settings = QSettings(SETTINGS_ORG, SETTINGS_APP)
        self.show_hidden_files = self._setting_bool("show_hidden_files", False)

        themes_path = Path(__file__).parent / "themes"
        self.theme_manager = ThemeManager(str(themes_path))
        saved_theme = str(self.settings.value("theme", "light"))
        if not self.theme_manager.load_and_apply_theme(saved_theme):
            self.theme_manager.load_and_apply_theme("light")

        self.icon_theme_manager = IconThemeManager()
        saved_icon_theme = self.settings.value("icon_theme", "hicolor")
        self.icon_theme_manager.load_and_apply_theme(saved_icon_theme)

        # Side-by-side layout: USB devices on the left, tabs on the right.
        self.splitter = QSplitter(Qt.Horizontal)
        self.setCentralWidget(self.splitter)

        self.mounted_devices_widget = MountedDevicesWidget()
        self.mounted_devices_widget.setFixedWidth(270)
        self.splitter.addWidget(self.mounted_devices_widget)

        self.tabs = Tabs(self)
        self.tabs.update_hidden_files(self.show_hidden_files)
        self.splitter.addWidget(self.tabs)

        self.mounted_devices_widget.open_device.connect(self.open_usb_device)

        self.setup_menus()

        self.resize(1200, 800)
        self.center_window()

        self.status_bar = QStatusBar()
        self.setStatusBar(self.status_bar)

        self.disk_info = DiskSpaceInfo()
        self.update_disk_space()
        self.disk_timer = QTimer(self)
        self.disk_timer.timeout.connect(self.update_disk_space)
        self.disk_timer.start(5000)

        logger.info("MainWindow setup complete.")

    # ------------------------------------------------------------------
    # Settings helpers
    # ------------------------------------------------------------------
    def _setting_bool(self, key: str, default: bool) -> bool:
        """Read a QSettings value as a robust boolean.

        QSettings can return strings like "true"/"false" depending on the Qt
        backend and platform, so normal bool(value) is not safe here.
        """
        value = self.settings.value(key, default)
        if isinstance(value, bool):
            return value
        if value is None:
            return default
        return str(value).strip().lower() in {"1", "true", "yes", "on"}

    # ------------------------------------------------------------------
    # Menus / theme handling
    # ------------------------------------------------------------------
    def setup_menus(self) -> None:
        """Build the main menu bar."""
        file_menu = self.menuBar().addMenu("File")
        empty_trash_action = QAction("Empty Trash", self)
        empty_trash_action.triggered.connect(self.empty_trash)
        file_menu.addAction(empty_trash_action)

        view_menu = self.menuBar().addMenu("View")
        self.show_hidden_files_action = QAction("Show Hidden Files", self, checkable=True)
        self.show_hidden_files_action.setChecked(self.show_hidden_files)
        self.show_hidden_files_action.triggered.connect(self.toggle_hidden_files)
        view_menu.addAction(self.show_hidden_files_action)

        themes_menu = self.menuBar().addMenu("Themes")
        for theme in self.theme_manager.get_available_themes():
            theme_action = QAction(theme, self)
            theme_action.triggered.connect(self.create_theme_action_handler(theme))
            themes_menu.addAction(theme_action)

        icon_themes_menu = self.menuBar().addMenu("Icon Themes")
        for icon_theme in self.icon_theme_manager.get_available_icon_themes():
            icon_theme_action = QAction(icon_theme, self)
            icon_theme_action.triggered.connect(self.create_icon_theme_action_handler(icon_theme))
            icon_themes_menu.addAction(icon_theme_action)

    def create_theme_action_handler(self, theme_name: str):
        def handler(checked: bool) -> None:
            del checked
            self.change_theme(theme_name)

        return handler

    def change_theme(self, theme_name: str) -> None:
        if self.theme_manager.load_and_apply_theme(theme_name):
            self.settings.setValue("theme", theme_name)
            logger.info("Theme changed to: %s", theme_name)
        else:
            logger.warning("Theme change failed for: %s", theme_name)

    def create_icon_theme_action_handler(self, icon_theme_name: str):
        def handler(checked: bool) -> None:
            del checked
            self.change_icon_theme(icon_theme_name)

        return handler

    def change_icon_theme(self, icon_theme_name: str) -> None:
        try:
            self.icon_theme_manager.load_and_apply_theme(icon_theme_name)
            self.settings.setValue("icon_theme", icon_theme_name)
            self.refresh_icons()
            logger.info("Icon theme changed to: %s", icon_theme_name)
        except Exception as exc:
            logger.info("Icon theme change failed", exc_info=exc)

    def refresh_icons(self) -> None:
        """Force a style refresh so themed icons repaint immediately."""
        app = QApplication.instance()
        if app is not None:
            app.setStyle(app.style())
        self.repaint()

    # ------------------------------------------------------------------
    # View actions
    # ------------------------------------------------------------------
    def toggle_hidden_files(self, checked: bool) -> None:
        self.show_hidden_files = bool(checked)
        self.settings.setValue("show_hidden_files", self.show_hidden_files)
        self.tabs.update_hidden_files(self.show_hidden_files)
        logger.info("Show Hidden Files set to: %s", self.show_hidden_files)

    def confirm_action(self, title: str, message: str) -> bool:
        reply = QMessageBox.question(self, title, message, QMessageBox.Yes | QMessageBox.No, QMessageBox.No)
        return reply == QMessageBox.Yes

    def empty_trash(self) -> None:
        if not self.confirm_action("Confirm Empty Trash", "Are you sure you want to empty the trash?"):
            return

        try:
            empty_trash()
            QMessageBox.information(self, "Success", "Trash emptied successfully.")
        except Exception as exc:
            QMessageBox.critical(self, "Error", f"Failed to empty trash: {exc}")
            logger.error("Failed to empty trash: %s", exc)

    # ------------------------------------------------------------------
    # Status / positioning
    # ------------------------------------------------------------------
    def update_disk_space(self) -> None:
        """Refresh the status bar with system and USB disk usage."""
        system_info = self.disk_info.get_disk_info_string("/")
        usb_info_list = self.disk_info.get_usb_disk_info_strings()
        usb_info = "; ".join(usb_info_list) if usb_info_list else "None"
        combined_info = f"System Disk: {system_info} | USB Disks: {usb_info}"
        self.status_bar.showMessage(combined_info)

    def center_window(self) -> None:
        """Center the window on the current screen."""
        screen = self.screen()
        if not screen:
            logger.warning("Unable to center window: no screen found.")
            return

        screen_geometry = screen.availableGeometry()
        x = (screen_geometry.width() - self.width()) // 2
        y = (screen_geometry.height() - self.height()) // 2
        self.move(screen_geometry.topLeft() + QPoint(x, y))

    # ------------------------------------------------------------------
    # External panels / shutdown
    # ------------------------------------------------------------------
    def open_usb_device(self, mount_point: str) -> None:
        if os.path.exists(mount_point):
            self.tabs.addNewTab(mount_point)
            return

        QMessageBox.warning(self, "Invalid Mount Point", f"The mount point {mount_point} does not exist.")
        logger.warning("Attempted to open invalid mount point: %s", mount_point)

    def closeEvent(self, event) -> None:  # noqa: N802 - Qt API name
        """Stop background observers before the window closes."""
        try:
            self.mounted_devices_widget.shutdown()
        except Exception:
            logger.exception("Failed to stop mounted devices widget cleanly.")
        super().closeEvent(event)


def main():
    app = QApplication(sys.argv)
    window = MainWindow()
    window.show()
    sys.exit(app.exec())


if __name__ == '__main__':
    main()
