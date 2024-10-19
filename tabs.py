#Handling all the actions related to tabs.

#Spin FM v. 2.0 Copyright (c) 2021 JJ Posti <techtimejourney.net> This program comes with ABSOLUTELY NO WARRANTY; for details see: http://www.gnu.org/copyleft/gpl.html.  This is free software, and you are welcome to redistribute it under GPL Version 2, June 1991")
#!/usr/bin/env python3

import os,sys
sys.dont_write_bytecode = True
import shutil
import subprocess
from PyQt5.QtWidgets import (
    QWidget, QVBoxLayout, QToolBar, QLineEdit, QPushButton, QTabWidget,
    QStatusBar, QMenu, QAction, QListView, QInputDialog, QMessageBox,
    QTabBar, QFileSystemModel
)
from PyQt5.QtCore import Qt, pyqtSignal
from PyQt5.QtGui import QIcon

# Custom Tab Bar Class
class CustomTabBar(QTabBar):
    """
    A custom QTabBar that emits a signal when a tab is double-clicked
    and shows a context menu on right-click to close a tab.
    """
    tabDoubleClicked = pyqtSignal(int)

    def __init__(self, parent=None):
        super(CustomTabBar, self).__init__(parent)
        self.setContextMenuPolicy(Qt.CustomContextMenu)
        self.customContextMenuRequested.connect(self.showContextMenu)

    def mouseDoubleClickEvent(self, event):
        """
        Overridden method to detect double-click events on tabs.
        Emits tabDoubleClicked signal with the index of the tab.
        """
        tab_index = self.tabAt(event.pos())
        if tab_index >= 0:
            # Double-clicked on a tab; emit the signal
            self.tabDoubleClicked.emit(tab_index)
        else:
            # Double-clicked on empty area; can add functionality if needed
            pass
        super().mouseDoubleClickEvent(event)

    def showContextMenu(self, position):
        """
        Shows a context menu on right-click to close the tab.
        The first tab (index 0) cannot be closed.
        """
        tab_index = self.tabAt(position)
        if tab_index > 0:  # Allow closing tabs except the first one
            context_menu = QMenu(self)
            close_action = QAction("Close Tab", self)
            close_action.triggered.connect(lambda: self.parent().parent().closeTab(tab_index))
            context_menu.addAction(close_action)
            context_menu.exec_(self.mapToGlobal(position))


class Tabs(QWidget):
    """
    A QWidget that contains a tabbed file system browser.
    """
    def __init__(self, parent=None):
        super(Tabs, self).__init__(parent)
        self.layout = QVBoxLayout(self)

        # Toolbar Setup
        self.toolbar = QToolBar()
        self.layout.addWidget(self.toolbar)

        # Address Bar
        self.address_bar = QLineEdit()
        self.address_bar.returnPressed.connect(self.navigateToPath)
        self.toolbar.addWidget(self.address_bar)

        # Navigation Buttons
        self.home_button = QPushButton("Home")
        self.home_button.clicked.connect(lambda: self.goHome())
        self.toolbar.addWidget(self.home_button)

        self.trash_button = QPushButton("Trash")
        self.trash_button.clicked.connect(lambda: self.goTrash())
        self.toolbar.addWidget(self.trash_button)

        self.add_tab_button = QPushButton("Add Tab")
        self.add_tab_button.clicked.connect(lambda: self.addNewTab())
        self.toolbar.addWidget(self.add_tab_button)

        # Tab Widget
        self.tabs_widget = QTabWidget()
        self.layout.addWidget(self.tabs_widget)

        # Set the custom tab bar before setting tabs closable
        self.custom_tab_bar = CustomTabBar(self)
        self.tabs_widget.setTabBar(self.custom_tab_bar)

        # Now set tabs closable
        self.tabs_widget.setTabsClosable(True)
        self.tabs_widget.tabCloseRequested.connect(self.closeTab)

        # Connect the tabDoubleClicked signal to addNewTab
        self.custom_tab_bar.tabDoubleClicked.connect(lambda index: self.addNewTab())

        # Status Bar
        self.status_bar = QStatusBar()
        self.layout.addWidget(self.status_bar)

        # Initialize Clipboard and History
        self.clipboard = None
        self.clipboard_operation = None
        self.current_paths = {}  # To track current path for each tab

        # Initialize Tabs
        self.addInitialTab()

        self.setLayout(self.layout)

    def addInitialTab(self, path=None):
        """
        Adds the initial tab to the QTabWidget.
        If no path is provided, it defaults to the user's home directory.
        """
        if path is None:
            path = os.path.expanduser("~")
        initial_tab = self.createFileSystemTab(path)
        tab_label = "Tab 1"
        self.tabs_widget.addTab(initial_tab, tab_label)
        self.updateAddressBar(path)
        self.updateStatusBar(path)
        # Prevent closing the first tab by disabling the close button
        self.disableTabClosing(0)

    def addNewTab(self, path=None):
        """
        Adds a new tab to the QTabWidget.
        If a path is provided, the tab will display that path.
        Otherwise, it defaults to the user's home directory.
        """
        if path is None:
            path = os.path.expanduser("~")
        tab_count = self.tabs_widget.count()
        new_tab = self.createFileSystemTab(path)
        tab_label = f"Tab {tab_count + 1}"
        self.tabs_widget.addTab(new_tab, tab_label)
        self.tabs_widget.setCurrentWidget(new_tab)
        self.updateAddressBar(path)
        self.updateStatusBar(path)

    def closeTab(self, index):
        """
        Closes the tab at the specified index.
        Prevents closing the first tab (index 0).
        """
        if index == 0:
            # Do not allow closing the first tab
            QMessageBox.information(self, "Information", "The first tab cannot be closed.")
            return
        current_tab = self.tabs_widget.widget(index)
        self.tabs_widget.removeTab(index)
        if current_tab in self.current_paths:
            del self.current_paths[current_tab]

    def disableTabClosing(self, index):
        """
        Disables the close button on the tab at the specified index.
        """
        tab_bar = self.tabs_widget.tabBar()
        close_button = tab_bar.tabButton(index, QTabBar.RightSide)
        if close_button:
            close_button.deleteLater()
        tab_bar.setTabButton(index, QTabBar.RightSide, None)

    def createFileSystemTab(self, path):
        """
        Creates a QListView widget to display the file system at the given path.
        """
        model = QFileSystemModel()
        model.setRootPath(path)

        list_view = QListView()
        list_view.setModel(model)
        list_view.setRootIndex(model.index(path))
        list_view.setFlow(QListView.LeftToRight)  # Arrange items horizontally
        list_view.setResizeMode(QListView.Adjust)
        list_view.setViewMode(QListView.IconMode)

        # Context Menu Setup
        list_view.setContextMenuPolicy(Qt.CustomContextMenu)
        list_view.customContextMenuRequested.connect(lambda position: self.openFileContextMenu(position, list_view))
        list_view.doubleClicked.connect(lambda index: self.openFileOrFolder(index, model))

        # Store initial path for this tab
        self.current_paths[list_view] = path

        return list_view

    def openFileContextMenu(self, position, file_view):
        """
        Creates and displays a context menu at the given position.
        """
        context_menu = QMenu(self)
        index = file_view.indexAt(position)
        if index.isValid():
            path = file_view.model().filePath(index)

            delete_action = QAction("Delete", self)
            delete_action.triggered.connect(lambda: self.confirmDelete(path))
            context_menu.addAction(delete_action)

            cut_action = QAction("Cut", self)
            cut_action.triggered.connect(lambda: self.cutFileOrFolder(path))
            context_menu.addAction(cut_action)

            copy_action = QAction("Copy", self)
            copy_action.triggered.connect(lambda: self.copyFileOrFolder(path))
            context_menu.addAction(copy_action)

            paste_action = QAction("Paste", self)
            paste_action.setEnabled(self.clipboard is not None)
            paste_action.triggered.connect(lambda: self.pasteFileOrFolder(file_view.model().filePath(file_view.rootIndex())))
            context_menu.addAction(paste_action)
        else:
            # Add actions for empty space context menu
            new_file_action = QAction("New Text File", self)
            new_file_action.triggered.connect(self.createNewTextFile)
            context_menu.addAction(new_file_action)

            new_folder_action = QAction("New Folder", self)
            new_folder_action.triggered.connect(self.createNewFolder)
            context_menu.addAction(new_folder_action)

            paste_action = QAction("Paste", self)
            paste_action.setEnabled(self.clipboard is not None)
            paste_action.triggered.connect(lambda: self.pasteFileOrFolder(file_view.model().filePath(file_view.rootIndex())))
            context_menu.addAction(paste_action)

        context_menu.exec_(file_view.viewport().mapToGlobal(position))

    def openFileOrFolder(self, index, file_model):
        """
        Opens the selected file or navigates into the selected folder.
        """
        path = file_model.filePath(index)
        if os.path.isdir(path):
            self.updateCurrentTab(path)
        else:
            subprocess.run(['xdg-open', path])

    def updateCurrentTab(self, path):
        """
        Navigates the current tab to the specified path.
        """
        tab = self.tabs_widget.currentWidget()
        if isinstance(tab, QListView):
            tab.setRootIndex(tab.model().index(path))
            self.current_paths[tab] = path
            self.updateAddressBar(path)
            self.updateStatusBar(path)

    def navigateToPath(self):
        """
        Navigates the current tab to the path specified in the address bar.
        """
        path = self.address_bar.text()
        if os.path.isdir(path):
            self.updateCurrentTab(path)

    def updateAddressBar(self, path):
        """
        Updates the address bar with the current path.
        """
        self.address_bar.setText(path)

    def updateStatusBar(self, path):
        """
        Updates the status bar with the current path.
        """
        self.status_bar.showMessage(f"Current Directory: {path}")

    def goHome(self):
        """
        Navigates to the user's home directory in the current tab.
        """
        home_path = os.path.expanduser("~")
        self.updateCurrentTab(home_path)
        self.updateStatusBar(home_path)

    def goTrash(self):
        """
        Navigates to the system's trash directory in a dedicated tab.
        """
        trash_path = os.path.expanduser("~/.local/share/Trash/files")
        trash_tab = self.getTabByTitle("Trash")
        if trash_tab:
            self.tabs_widget.setCurrentWidget(trash_tab)
            self.updateCurrentTab(trash_path)
            self.updateStatusBar(trash_path)
        else:
            self.addNewTab(trash_path)
            # Rename the tab to "Trash"
            current_index = self.tabs_widget.currentIndex()
            self.tabs_widget.setTabText(current_index, "Trash")
            self.updateStatusBar(trash_path)

    def getTabByTitle(self, title):
        """
        Retrieves a tab widget by its title.
        """
        for index in range(self.tabs_widget.count()):
            if self.tabs_widget.tabText(index) == title:
                return self.tabs_widget.widget(index)
        return None

    def createNewTextFile(self):
        """
        Creates a new text file in the current directory.
        """
        tab = self.tabs_widget.currentWidget()
        if isinstance(tab, QListView):
            current_path = self.current_paths.get(tab, os.path.expanduser("~"))
            file_name, ok = QInputDialog.getText(self, "New Text File", "Enter the name of the new text file:")
            if ok and file_name:
                try:
                    with open(os.path.join(current_path, file_name), 'w') as new_file:
                        new_file.write("")
                    self.refreshCurrentTab()
                except Exception as e:
                    QMessageBox.warning(self, "Error", f"Failed to create new text file: {e}")

    def createNewFolder(self):
        """
        Creates a new folder in the current directory.
        """
        tab = self.tabs_widget.currentWidget()
        if isinstance(tab, QListView):
            current_path = self.current_paths.get(tab, os.path.expanduser("~"))
            folder_name, ok = QInputDialog.getText(self, "New Folder", "Enter the name of the new folder:")
            if ok and folder_name:
                try:
                    os.makedirs(os.path.join(current_path, folder_name))
                    self.refreshCurrentTab()
                except Exception as e:
                    QMessageBox.warning(self, "Error", f"Failed to create new folder: {e}")

    def confirmDelete(self, path):
        """
        Prompts the user to confirm deletion of the specified file or folder.
        """
        reply = QMessageBox.warning(
            self, "Confirm Delete",
            f"Are you sure you want to delete {os.path.basename(path)}?",
            QMessageBox.Yes | QMessageBox.No
        )
        if reply == QMessageBox.Yes:
            self.deleteFileOrFolder(path)

    def deleteFileOrFolder(self, path):
        """
        Deletes the specified file or folder by moving it to the trash.
        """
        trash_path = os.path.expanduser("~/.local/share/Trash/files")
        if os.path.exists(path):
            try:
                shutil.move(path, trash_path)
                self.refreshCurrentTab()
            except Exception as e:
                QMessageBox.warning(self, "Error", f"Failed to delete {path}: {e}")

    def cutFileOrFolder(self, path):
        """
        Cuts the specified file or folder for later pasting.
        """
        self.clipboard = path
        self.clipboard_operation = 'cut'

    def copyFileOrFolder(self, path):
        """
        Copies the specified file or folder for later pasting.
        """
        self.clipboard = path
        self.clipboard_operation = 'copy'

    def pasteFileOrFolder(self, destination):
        """
        Pastes the cut or copied file or folder into the specified destination.
        """
        if self.clipboard and self.clipboard_operation:
            destination_path = os.path.join(destination, os.path.basename(self.clipboard))
            if os.path.exists(destination_path):
                reply = QMessageBox.warning(
                    self, "Warning",
                    f"An item named {os.path.basename(self.clipboard)} already exists in {destination}. Do you want to overwrite it?",
                    QMessageBox.Yes | QMessageBox.No
                )
                if reply == QMessageBox.No:
                    return

            try:
                if self.clipboard_operation == 'cut':
                    shutil.move(self.clipboard, destination)
                elif self.clipboard_operation == 'copy':
                    if os.path.isdir(self.clipboard):
                        shutil.copytree(self.clipboard, destination_path)
                    else:
                        shutil.copy2(self.clipboard, destination)
                self.clipboard = None
                self.clipboard_operation = None
                self.refreshCurrentTab()
            except Exception as e:
                QMessageBox.warning(self, "Error", f"Failed to paste {self.clipboard}: {e}")

    def refreshCurrentTab(self):
        """
        Refreshes the current tab's view.
        """
        tab = self.tabs_widget.currentWidget()
        if isinstance(tab, QListView):
            path = self.current_paths.get(tab, os.path.expanduser("~"))
            self.updateCurrentTab(path)
