# main.py: The main executable bringing it all together.

#Spin FM v. 2.0 Copyright (c) 2021 JJ Posti <techtimejourney.net> This program comes with ABSOLUTELY NO WARRANTY; for details see: http://www.gnu.org/copyleft/gpl.html.  This is free software, and you are welcome to redistribute it under GPL Version 2, June 1991")
#!/usr/bin/env python3

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

# Import your own modules
from file_system_tab import *  
from css import ThemeManager  
from tabs import Tabs  
from empty_trash import empty_trash  
from disk_space import DiskSpaceInfo

WINDOW_TITLE = "Spin FM RC3"

# Configure logging
# logging.basicConfig(
#     filename='usb_manager.log',
#     level=logging.INFO,
#     format='%(asctime)s:%(levelname)s:%(message)s'
# )


class DeviceMonitor(QObject):
    """
    Monitors USB device events and emits a signal when devices are added or removed.
    """
    device_changed = pyqtSignal()

    def __init__(self):
        super().__init__()
        self.context = pyudev.Context()
        self.monitor = pyudev.Monitor.from_netlink(self.context)
        self.monitor.filter_by(subsystem='block', device_type='partition')
        self.observer = pyudev.MonitorObserver(self.monitor, callback=self.device_event)
        self.observer.start()
        print("DeviceMonitor initialized and observer started.")

    def device_event(self, device):
        """
        Callback function for device events.
        Emits a signal to notify the main thread.
        """
        print(f"Device event detected: {device.device_node}")
        self.device_changed.emit()

    def stop(self):
        """
        Stops the device observer.
        """
        self.observer.stop()
        print("DeviceMonitor observer stopped.")


class MountedDevicesWidget(QWidget):
    """
    Widget that displays mounted and unmounted USB devices.
    Allows mounting and unmounting of devices.
    Emits a signal when a mounted device is double-clicked to open its contents.
    """
    open_device = pyqtSignal(str)  # Signal to emit mount point for opening
    device_changed = pyqtSignal()  # Signal to emit when devices change

    def __init__(self, parent=None):
        super().__init__(parent)
        self.disk_info = DiskSpaceInfo()
        self.init_ui()
        self.previous_devices = set()

        # Initialize the device monitor and connect its signal
        self.device_monitor = DeviceMonitor()
        self.device_monitor.device_changed.connect(self.update_devices)
        self.device_monitor.device_changed.connect(self.device_changed)  # Propagate signal
        print("MountedDevicesWidget initialized and connected to DeviceMonitor.")

        # Populate the table initially
        self.update_devices()

    def init_ui(self):
        """
        Initializes the user interface.
        """
        layout = QVBoxLayout()

        self.label = QLabel("USB Devices")
        layout.addWidget(self.label)

        self.table_widget = QTableWidget()
        self.table_widget.setColumnCount(2)  # "Name" and "Action" columns
        self.table_widget.setHorizontalHeaderLabels(["Name", "Action"])
        self.table_widget.horizontalHeader().setStretchLastSection(True)
        self.table_widget.setEditTriggers(QTableWidget.NoEditTriggers)
        self.table_widget.setSelectionBehavior(QTableWidget.SelectRows)
        self.table_widget.setSelectionMode(QTableWidget.SingleSelection)
        layout.addWidget(self.table_widget)

        # Connect double-click event
        self.table_widget.cellDoubleClicked.connect(self.on_cell_double_clicked)

        self.setLayout(layout)
        print("MountedDevicesWidget UI initialized.")

    def update_devices(self):
        """
        Updates the device list by fetching current USB devices.
        """
        print("Updating USB devices...")
        usb_devices_with_mounts = self.disk_info.get_all_usb_devices_with_mount_points()
        print(f"Current USB devices: {usb_devices_with_mounts}")
        # Convert list to set for comparison
        current_devices = set(usb_devices_with_mounts)
        if current_devices != self.previous_devices:
            self.previous_devices = current_devices
            self.populate_table(usb_devices_with_mounts)
            print("USB devices updated in the table.")

    def populate_table(self, devices):
        """
        Populates the QTableWidget with device information.
        """
        self.table_widget.setRowCount(0)  # Clear existing rows

        for device_node, mountpoint in sorted(devices, key=lambda x: x[0]):
            device_name = os.path.basename(device_node)
            row_position = self.table_widget.rowCount()
            self.table_widget.insertRow(row_position)

            # Name with icon
            name_item = QTableWidgetItem(device_name)
            if mountpoint:
                icon = QIcon("icons/mounted.png")  # Ensure this icon exists
            else:
                icon = QIcon("icons/unmounted.png")  # Ensure this icon exists
            name_item.setIcon(icon)
            # Store mountpoint in item data for later retrieval
            name_item.setData(Qt.UserRole, mountpoint)
            self.table_widget.setItem(row_position, 0, name_item)

            # Action (Mount or Unmount button)
            if mountpoint:
                # If mounted, show Unmount button
                action_button = QPushButton("Unmount")
                action_button.clicked.connect(partial(self.unmount_device, device_node, mountpoint))
            else:
                # If not mounted, show Mount button
                action_button = QPushButton("Mount")
                action_button.clicked.connect(partial(self.mount_device, device_node))
            self.table_widget.setCellWidget(row_position, 1, action_button)
            print(f"Row added: {device_name}, Action: {'Unmount' if mountpoint else 'Mount'}")

    def filter_devices(self, text):
        """
        Filters the table based on the search text.
        """
        for row in range(self.table_widget.rowCount()):
            item = self.table_widget.item(row, 0)  # Only the Name column
            if item and text.lower() in item.text().lower():
                self.table_widget.setRowHidden(row, False)
            else:
                self.table_widget.setRowHidden(row, True)

    def on_cell_double_clicked(self, row, column):
        """
        Handles double-click events on table cells.
        Opens the device's mount point in the file manager if mounted.
        """
        if column == 1:
            # Action column, do nothing on double-click
            return

        # Retrieve mount point from the data stored in the Name item
        name_item = self.table_widget.item(row, 0)
        if name_item:
            mountpoint = name_item.data(Qt.UserRole)
            if mountpoint and os.path.exists(mountpoint):
                # Emit signal to open the device
                self.open_device.emit(mountpoint)
                print(f"Opening device at mount point: {mountpoint}")
            else:
                QMessageBox.warning(self, "Not Mounted", "This device is not mounted. Please mount it first.")
                print("Attempted to open an unmounted device.")
        else:
            QMessageBox.warning(self, "No Mountpoint", "Unable to retrieve mount point for this device.")
            print("No mount point found for the selected device.")

    def mount_device(self, device_node):
        """
        Mounts the device at an appropriate mount point using udisksctl.
        """
        device_name = os.path.basename(device_node)
        print(f"Attempting to mount device: {device_node}")

        # Execute the mount command using udisksctl
        try:
            # 'udisksctl mount' automatically handles mount points
            result = subprocess.run(
                ['udisksctl', 'mount', '-b', device_node],
                check=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True
            )
            # Parse the mount point from the output
            # Example output: Mounted /dev/sdb1 at /media/username/Label.
            output = result.stdout.strip()
            print(f"udisksctl output: {output}")
            if "Mounted" in output and "at" in output:
                parts = output.split(" at ")
                if len(parts) == 2:
                    mount_point = parts[1].rstrip('.')
                    QMessageBox.information(self, "Success", f"Successfully mounted {device_node} at {mount_point}.")
                    print(f"Successfully mounted {device_node} at {mount_point}.")
                else:
                    QMessageBox.information(self, "Success", f"Successfully mounted {device_node}.")
                    print(f"Successfully mounted {device_node}.")
            else:
                QMessageBox.information(self, "Success", f"Successfully mounted {device_node}.")
                print(f"Successfully mounted {device_node}.")
            self.update_devices()
        except subprocess.CalledProcessError as e:
            QMessageBox.critical(self, "Error", f"Failed to mount {device_node}.\nError: {e.stderr.strip()}")
            print(f"Failed to mount device: {device_node}. Error: {e.stderr.strip()}")

    def unmount_device(self, device_node, mount_point):
        """
        Unmounts the device at the given mount point using udisksctl.
        """
        device_name = os.path.basename(device_node)
        reply = QMessageBox.question(
            self,
            'Confirm Unmount',
            f"Are you sure you want to unmount {device_node} from {mount_point}?",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No
        )
        if reply == QMessageBox.Yes:
            print(f"Attempting to unmount device: {device_node} from {mount_point}")
            try:
                # Execute the unmount command using udisksctl
                result = subprocess.run(
                    ['udisksctl', 'unmount', '-b', device_node],
                    check=True,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    text=True
                )
                QMessageBox.information(self, "Success", f"Successfully unmounted {device_node}.")
                print(f"Successfully unmounted {device_node}.")
                self.update_devices()
            except subprocess.CalledProcessError as e:
                QMessageBox.critical(self, "Error", f"Failed to unmount {device_node}.\nError: {e.stderr.strip()}")
                print(f"Failed to unmount device: {device_node}. Error: {e.stderr.strip()}")


class MainWindow(QMainWindow):
    """
    Main window of the file manager that integrates the USB Manager on the left side.
    """
    def __init__(self):
        super(MainWindow, self).__init__()
        self.setWindowTitle(WINDOW_TITLE)
        self.theme_manager = ThemeManager(os.path.join(os.path.dirname(__file__), 'themes'))
        print("MainWindow initialized.")

        # Set up the main window layout with a splitter
        self.splitter = QSplitter(Qt.Horizontal)
        self.setCentralWidget(self.splitter)
        print("Splitter initialized and set as central widget.")

        # Initialize MountedDevicesWidget and add to splitter
        self.mounted_devices_widget = MountedDevicesWidget()
        self.mounted_devices_widget.setMinimumWidth(270)  # Set minimum width for the USB panel
        self.mounted_devices_widget.setMaximumWidth(270)  # Set maximum width for the USB panel
        self.splitter.addWidget(self.mounted_devices_widget)
        print("MountedDevicesWidget added to splitter.")

        # Initialize Tabs and add to splitter
        self.tabs = Tabs(self)
        self.splitter.addWidget(self.tabs)
        print("Tabs added to splitter.")

        # Connect the open_device signal to the open_usb_device method
        self.mounted_devices_widget.open_device.connect(self.open_usb_device)
        print("Connected open_device signal to open_usb_device method.")

        # Menu bar for theme selection and other actions
        self.menu_bar = self.menuBar()
        self.setup_menus()
        print("Menu bar set up.")

        # Load default theme
        self.theme_manager.load_and_apply_theme('default')
        print("Default theme loaded.")

        # Set the default size of the window
        self.resize(1200, 800)
        self.center_window()
        print("MainWindow resized and centered.")

        # Initialize status bar
        self.status_bar = QStatusBar()
        self.setStatusBar(self.status_bar)
        print("Status bar initialized.")

        # Initialize DiskSpaceInfo
        self.disk_info = DiskSpaceInfo()
        print("DiskSpaceInfo initialized.")

        # Display disk space in the status bar
        self.update_disk_space()
        print("Initial disk space information displayed.")

        # Set a timer to update disk space every 5 seconds
        self.disk_timer = QTimer(self)
        self.disk_timer.timeout.connect(self.update_disk_space)
        self.disk_timer.start(5000)  # 5000 milliseconds = 5 seconds
        print("QTimer set up to update disk space every 5 seconds.")

    def update_disk_space(self):
        """
        Updates the status bar with disk space information.
        """
        # Get system disk space
        system_info = self.disk_info.get_disk_info_string('/')
        print(f"System Disk Info: {system_info}")

        # Get USB disk space information
        usb_info_list = self.disk_info.get_usb_disk_info_strings()
        usb_info = "; ".join(usb_info_list)  # Replace newline characters with semicolons for single-line status bar
        print(f"USB Disk Info: {usb_info}")

        # Combine system and USB info
        combined_info = f"System Disk: {system_info} | USB Disks: {usb_info}"

        # Update the status bar
        self.status_bar.showMessage(combined_info)
        print("Status bar updated with disk space information.")

    def setup_menus(self):
        """
        Sets up the menu bar with Themes and File menus.
        """
        # Uncomment and implement theme functionality if needed
        # themes_menu = self.menu_bar.addMenu('Themes')

        # for theme in self.theme_manager.get_available_themes():
        #     theme_action = QAction(theme, self)
        #     theme_action.triggered.connect(self.create_theme_action_handler(theme))
        #     themes_menu.addAction(theme_action)

        # Add empty trash action
        file_menu = self.menu_bar.addMenu('File')
        empty_trash_action = QAction('Empty Trash', self)
        empty_trash_action.triggered.connect(self.empty_trash)
        file_menu.addAction(empty_trash_action)
        print("File menu with 'Empty Trash' action added.")

    def create_theme_action_handler(self, theme_name):
        """
        Creates a handler function for theme actions.
        """
        def handler(checked):
            self.change_theme(theme_name)
        return handler

    def change_theme(self, theme_name):
        """
        Changes the application's theme.
        """
        self.theme_manager.load_and_apply_theme(theme_name)
        print(f"Theme changed to: {theme_name}")

    def empty_trash(self):
        """
        Empties the trash by calling the empty_trash function.
        """
        try:
            empty_trash()
            QMessageBox.information(self, "Success", "Trash emptied successfully.")
            print("Trash emptied successfully.")
        except Exception as e:
            QMessageBox.critical(self, "Error", f"Failed to empty trash: {e}")
            print(f"Failed to empty trash: {e}")

    def center_window(self):
        """
        Centers the window on the screen.
        """
        qr = self.frameGeometry()
        cp = QDesktopWidget().availableGeometry().center()
        qr.moveCenter(cp)
        self.move(qr.topLeft())
        print("MainWindow centered on the screen.")

    def open_usb_device(self, mount_point):
        """
        Opens the USB device's mount point in a new tab.
        """
        if os.path.exists(mount_point):
            self.tabs.addNewTab(mount_point)
            print(f"Opened USB device at {mount_point} in a new tab.")
        else:
            QMessageBox.warning(self, "Invalid Mount Point", f"The mount point {mount_point} does not exist.")
            print(f"Attempted to open invalid mount point: {mount_point}")


def main():
    """
    Entry point of the application.
    """
    app = QApplication(sys.argv)
    main_window = MainWindow()
    main_window.show()
    print("Application started.")
    sys.exit(app.exec_())


if __name__ == "__main__":
    main()
