#!/usr/bin/env python3
"""
Main window module for Spin FM.
This module defines the MainWindow class which sets up the primary interface,
including menus, status bar, and USB device management.
"""

import sys
import os
import subprocess
import logging
from functools import partial
from pathlib import Path

from PyQt5.QtWidgets import (
    QApplication,
    QMainWindow,
    QSplitter,
    QMessageBox,
    QStatusBar,
    QAction,
)
from PyQt5.QtCore import Qt, QTimer, QPoint, QSettings
from PyQt5.QtGui import QIcon

from theme_manager import ThemeManager
from disk_space import DiskSpaceInfo
from mounted_devices_widget import MountedDevicesWidget
from tabs import Tabs
from empty_trash import empty_trash

# Configure logging
logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger(__name__)


class MainWindow(QMainWindow):
    """
    Main application window for Spin FM.
    Provides a UI to manage USB devices, themes, and system status.
    """
    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle("Spin FM")
        logger.info("MainWindow initialized.")

        # Set up persistent settings.
        self.settings = QSettings("MyOrganization", "Spin FM")

        # Set up the theme manager.
        themes_path = Path(__file__).parent / "themes"
        self.theme_manager = ThemeManager(str(themes_path))
        saved_theme = self.settings.value("theme", "light")
        self.theme_manager.load_and_apply_theme(saved_theme)
        logger.info(f"Loaded theme: {saved_theme}")

        # Create a horizontal splitter for side-by-side layout.
        self.splitter = QSplitter(Qt.Horizontal)
        self.setCentralWidget(self.splitter)

        # Initialize and configure the MountedDevicesWidget.
        self.mounted_devices_widget = MountedDevicesWidget()
        self.mounted_devices_widget.setFixedWidth(270)
        self.splitter.addWidget(self.mounted_devices_widget)
        logger.debug("MountedDevicesWidget added to the splitter.")

        # Initialize the Tabs widget and add it to the splitter.
        self.tabs = Tabs(self)
        self.splitter.addWidget(self.tabs)
        logger.debug("Tabs widget added to the splitter.")

        # Connect signals.
        self.mounted_devices_widget.open_device.connect(self.open_usb_device)

        # Set up the menu bar.
        self.setup_menus()

        # Configure window size and centering.
        self.resize(1200, 800)
        self.center_window()

        # Set up status bar.
        self.status_bar = QStatusBar()
        self.setStatusBar(self.status_bar)

        # Initialize disk space info and start a timer for periodic updates.
        self.disk_info = DiskSpaceInfo()
        self.update_disk_space()
        self.disk_timer = QTimer(self)
        self.disk_timer.timeout.connect(self.update_disk_space)
        self.disk_timer.start(5000)
        logger.info("MainWindow setup complete.")

    def setup_menus(self) -> None:
        """
        Sets up the File and Themes menus in the menu bar.
        """
        # File menu.
        file_menu = self.menuBar().addMenu("File")
        empty_trash_action = QAction("Empty Trash", self)
        empty_trash_action.triggered.connect(self.empty_trash)
        file_menu.addAction(empty_trash_action)

        # Themes menu.
        themes_menu = self.menuBar().addMenu("Themes")
        for theme in self.theme_manager.get_available_themes():
            theme_action = QAction(theme, self)
            theme_action.triggered.connect(self.create_theme_action_handler(theme))
            themes_menu.addAction(theme_action)
        logger.debug("Menus set up.")

    def create_theme_action_handler(self, theme_name: str):
        """
        Creates a handler for changing themes.
        
        :param theme_name: Name of the theme to switch to.
        :return: Callable function that changes the theme.
        """
        def handler(checked: bool) -> None:
            self.change_theme(theme_name)
        return handler

    def change_theme(self, theme_name: str) -> None:
        """
        Applies a new theme to the application and saves the choice.
        
        :param theme_name: The theme to load.
        """
        self.theme_manager.load_and_apply_theme(theme_name)
        self.settings.setValue("theme", theme_name)
        logger.info(f"Theme changed to: {theme_name} and saved to settings.")

    def confirm_action(self, title: str, message: str) -> bool:
        """
        Displays a confirmation dialog.
        
        :param title: Title of the dialog.
        :param message: Confirmation message.
        :return: True if the user confirms, otherwise False.
        """
        reply = QMessageBox.question(self, title, message, QMessageBox.Yes | QMessageBox.No, QMessageBox.No)
        return reply == QMessageBox.Yes

    def empty_trash(self) -> None:
        """
        Attempts to empty the trash after user confirmation.
        """
        if self.confirm_action("Confirm Empty Trash", "Are you sure you want to empty the trash?"):
            try:
                empty_trash()
                QMessageBox.information(self, "Success", "Trash emptied successfully.")
                logger.info("Trash emptied.")
            except Exception as e:
                QMessageBox.critical(self, "Error", f"Failed to empty trash: {e}")
                logger.error(f"Failed to empty trash: {e}")

    def update_disk_space(self) -> None:
        """
        Updates the status bar with current disk and USB storage info.
        """
        system_info = self.disk_info.get_disk_info_string('/')
        usb_info_list = self.disk_info.get_usb_disk_info_strings()
        usb_info = "; ".join(usb_info_list)
        combined_info = f"System Disk: {system_info} | USB Disks: {usb_info}"
        self.status_bar.showMessage(combined_info)
        logger.debug(f"Status bar updated: {combined_info}")

    def center_window(self) -> None:
        """
        Centers the window on the primary screen using QScreen.
        """
        screen = self.screen()  # Gets the primary screen.
        if screen:
            screen_geometry = screen.availableGeometry()
            x = (screen_geometry.width() - self.width()) // 2
            y = (screen_geometry.height() - self.height()) // 2
            self.move(screen_geometry.topLeft() + QPoint(x, y))
            logger.debug("Window centered on screen.")
        else:
            logger.warning("Unable to center window: No screen found.")

    def open_usb_device(self, mount_point: str) -> None:
        """
        Opens a new tab for the given USB device mount point if it exists.
        
        :param mount_point: The mount point of the USB device.
        """
        if os.path.exists(mount_point):
            self.tabs.addNewTab(mount_point)
            logger.info(f"Opened USB device at {mount_point} in a new tab.")
        else:
            QMessageBox.warning(self, "Invalid Mount Point", f"The mount point {mount_point} does not exist.")
            logger.warning(f"Attempted to open invalid mount point: {mount_point}")


def main():
    """
    Entry point for the application.
    """
    app = QApplication(sys.argv)
    window = MainWindow()
    window.show()
    sys.exit(app.exec())


if __name__ == '__main__':
    main()
