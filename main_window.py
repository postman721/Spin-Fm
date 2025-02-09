#!/usr/bin/env python3
# main_window.py
# Disable the creation of __pycache__ directories
sys.dont_write_bytecode = True
import sys
sys.dont_write_bytecode = True
import subprocess
import json
import os
# import logging  # Commented out logging import
from functools import partial

from PyQt5.QtWidgets import (
    QApplication,
    QMainWindow,
    QWidget,
    QVBoxLayout,
    QTableWidget,
    QTableWidgetItem,
    QPushButton,
    QMessageBox,
    QLabel,
    QSplitter,
    QLineEdit,
    QMenuBar,
    QAction,
    QDesktopWidget,
    QStatusBar
)
from PyQt5.QtCore import Qt, pyqtSignal, QObject, QTimer
from PyQt5.QtGui import QIcon

import pyudev


from theme_manager import ThemeManager
from disk_space import DiskSpaceInfo
from mounted_devices_widget import MountedDevicesWidget
from tabs import Tabs
from empty_trash import empty_trash

class MainWindow(QMainWindow):
    def __init__(self):
        super(MainWindow, self).__init__()
        self.setWindowTitle("Spin FM RC4")
        print("[MainWindow] Initialized.")
        # Set up theme.
        self.theme_manager = ThemeManager(os.path.join(os.path.dirname(__file__), 'themes'))
        self.theme_manager.load_and_apply_theme("light")
        # Create splitter and add left and right panels.
        self.splitter = QSplitter(Qt.Horizontal)
        self.setCentralWidget(self.splitter)
        self.mounted_devices_widget = MountedDevicesWidget()
        self.mounted_devices_widget.setMinimumWidth(270)
        self.mounted_devices_widget.setMaximumWidth(270)
        self.splitter.addWidget(self.mounted_devices_widget)
        print("[MainWindow] MountedDevicesWidget added.")
        self.tabs = Tabs(self)
        self.splitter.addWidget(self.tabs)
        print("[MainWindow] Tabs added.")
        self.mounted_devices_widget.open_device.connect(self.open_usb_device)
        # Set up menu bar.
        self.menu_bar = self.menuBar()
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
        print("[MainWindow] Setup complete.")

    def setup_menus(self):
        file_menu = self.menu_bar.addMenu("File")
        empty_trash_action = QAction("Empty Trash", self)
        empty_trash_action.triggered.connect(self.empty_trash)
        file_menu.addAction(empty_trash_action)
        themes_menu = self.menu_bar.addMenu("Themes")
        for theme in self.theme_manager.get_available_themes():
            theme_action = QAction(theme, self)
            theme_action.triggered.connect(self.create_theme_action_handler(theme))
            themes_menu.addAction(theme_action)
        print("[MainWindow] Menus set up.")

    def create_theme_action_handler(self, theme_name):
        def handler(checked):
            self.change_theme(theme_name)
        return handler

    def change_theme(self, theme_name):
        self.theme_manager.load_and_apply_theme(theme_name)
        print(f"[MainWindow] Theme changed to: {theme_name}")

    def confirm_action(self, title, message):
        reply = QMessageBox.question(self, title, message, QMessageBox.Yes | QMessageBox.No, QMessageBox.No)
        return reply == QMessageBox.Yes

    def empty_trash(self):
        if self.confirm_action("Confirm Empty Trash", "Are you sure you want to empty the trash?"):
            try:
                empty_trash()
                QMessageBox.information(self, "Success", "Trash emptied successfully.")
                print("[MainWindow] Trash emptied.")
            except Exception as e:
                QMessageBox.critical(self, "Error", f"Failed to empty trash: {e}")
                print(f"[MainWindow] Failed to empty trash: {e}")

    def update_disk_space(self):
        system_info = self.disk_info.get_disk_info_string('/')
        usb_info_list = self.disk_info.get_usb_disk_info_strings()
        usb_info = "; ".join(usb_info_list)
        combined_info = f"System Disk: {system_info} | USB Disks: {usb_info}"
        self.status_bar.showMessage(combined_info)
        print(f"[MainWindow] Status bar updated: {combined_info}")

    def center_window(self):
        geo = self.frameGeometry()
        cp = QDesktopWidget().availableGeometry().center()
        geo.moveCenter(cp)
        self.move(geo.topLeft())
        print("[MainWindow] Centered on screen.")

    def open_usb_device(self, mount_point):
        if os.path.exists(mount_point):
            self.tabs.addNewTab(mount_point)
            print(f"[MainWindow] Opened USB device at {mount_point} in a new tab.")
        else:
            QMessageBox.warning(self, "Invalid Mount Point", f"The mount point {mount_point} does not exist.")
            print(f"[MainWindow] Attempted to open invalid mount point: {mount_point}")
