#!/usr/bin/env python3
# tabs.py
# Disable the creation of __pycache__ directories
sys.dont_write_bytecode = True
import os
import subprocess
import shutil
import time  # for formatting timestamps

from PyQt5.QtWidgets import (
    QWidget, QVBoxLayout, QToolBar, QToolButton, QLineEdit, QTabWidget,
    QStatusBar, QMessageBox, QMenu, QAction, QInputDialog, QListView,
    QFileSystemModel, QTabBar, QStyle
)
from PyQt5.QtCore import Qt, pyqtSignal

class CustomTabBar(QTabBar):
    tabDoubleClicked = pyqtSignal(int)
    closeTabRequested = pyqtSignal(int)

    def __init__(self, parent=None):
        super(CustomTabBar, self).__init__(parent)
        self.setContextMenuPolicy(Qt.CustomContextMenu)
        self.customContextMenuRequested.connect(self.showContextMenu)

    def mouseDoubleClickEvent(self, event):
        tab_index = self.tabAt(event.pos())
        if tab_index >= 0:
            self.tabDoubleClicked.emit(tab_index)
        super().mouseDoubleClickEvent(event)

    def showContextMenu(self, position):
        tab_index = self.tabAt(position)
        if tab_index > 0:  # Do not allow closing the first tab.
            context_menu = QMenu(self)
            close_action = QAction("Close Tab", self)
            close_action.triggered.connect(lambda: self.closeTabRequested.emit(tab_index))
            context_menu.addAction(close_action)
            context_menu.exec_(self.mapToGlobal(position))

class Tabs(QWidget):
    def __init__(self, parent=None):
        super(Tabs, self).__init__(parent)
        self.layout = QVBoxLayout(self)
        self.toolbar = QToolBar()
        self.layout.addWidget(self.toolbar)
        # --- Back and Forward Navigation Buttons ---
        self.back_button = QToolButton()
        self.back_button.setIcon(self.style().standardIcon(QStyle.SP_ArrowBack))
        self.back_button.clicked.connect(self.goBack)
        self.toolbar.addWidget(self.back_button)

        self.forward_button = QToolButton()
        self.forward_button.setIcon(self.style().standardIcon(QStyle.SP_ArrowForward))
        self.forward_button.clicked.connect(self.goForward)
        self.toolbar.addWidget(self.forward_button)

        # --- Address Bar ---
        self.address_bar = QLineEdit()
        self.address_bar.returnPressed.connect(self.navigateToPath)
        self.toolbar.addWidget(self.address_bar)

        # --- Styled Home and Trash Buttons ---
        self.home_button = QToolButton()
        self.home_button.setIcon(self.style().standardIcon(QStyle.SP_DirHomeIcon))
        self.home_button.setToolTip("Home")
        self.home_button.clicked.connect(self.goHome)
        self.toolbar.addWidget(self.home_button)

        self.trash_button = QToolButton()
        self.trash_button.setIcon(self.style().standardIcon(QStyle.SP_TrashIcon))
        self.trash_button.setToolTip("Trash")
        self.trash_button.clicked.connect(self.goTrash)
        self.toolbar.addWidget(self.trash_button)

        # --- Tabs Widget ---
        self.tabs_widget = QTabWidget()
        self.layout.addWidget(self.tabs_widget)
        self.custom_tab_bar = CustomTabBar(self.tabs_widget)
        self.tabs_widget.setTabBar(self.custom_tab_bar)
        self.tabs_widget.setTabsClosable(True)
        self.tabs_widget.tabCloseRequested.connect(self.closeTab)
        self.custom_tab_bar.tabDoubleClicked.connect(lambda index: self.addNewTab())
        self.custom_tab_bar.closeTabRequested.connect(self.closeTab)
        self.tabs_widget.tabBar().setVisible(True)

        # Status bar
        self.status_bar = QStatusBar()
        self.layout.addWidget(self.status_bar)

        # Internal state for cut/copy/paste operations, paths, and tab navigation
        self.clipboard = None
        self.clipboard_operation = None
        self.current_paths = {}
        self.history = {}  # Navigation history for each tab

        # When switching tabs, update address bar and nav buttons
        self.tabs_widget.currentChanged.connect(self.onTabChanged)

        # Add initial tab, finalize
        self.addInitialTab()
        self.setLayout(self.layout)
        self.updateNavigationButtons()

    def addInitialTab(self, path=None):
        if path is None:
            path = os.path.expanduser("~")
        initial_tab = self.createFileSystemTab(path)
        tab_label = "Tab 1"
        self.tabs_widget.addTab(initial_tab, tab_label)
        self.updateAddressBar(path)
        self.updateStatusBar(path)
        self.disableTabClosing(0)

    def addNewTab(self, path=None):
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
        if index == 0:
            QMessageBox.information(self, "Information", "The first tab cannot be closed.")
            return
        current_tab = self.tabs_widget.widget(index)
        self.tabs_widget.removeTab(index)
        if current_tab in self.current_paths:
            del self.current_paths[current_tab]
        if current_tab in self.history:
            del self.history[current_tab]

    def disableTabClosing(self, index):
        self.tabs_widget.tabBar().setTabButton(index, QTabBar.RightSide, None)

    def createFileSystemTab(self, path):
        """
        Creates a new tab that contains a QListView for file browsing.
        """
        model = QFileSystemModel()
        model.setRootPath(path)
        list_view = QListView()
        list_view.setModel(model)
        list_view.setRootIndex(model.index(path))
        list_view.setFlow(QListView.LeftToRight)
        list_view.setWrapping(True)
        list_view.setViewMode(QListView.IconMode)
        list_view.setSelectionMode(QListView.ExtendedSelection)
        list_view.setContextMenuPolicy(Qt.CustomContextMenu)

        # Context menu
        list_view.customContextMenuRequested.connect(lambda pos: self.openFileContextMenu(pos, list_view))
        list_view.doubleClicked.connect(lambda index: self.openFileOrFolder(index, model))

        # Remember path and history
        self.current_paths[list_view] = path
        self.history[list_view] = {"paths": [path], "current": 0}
        return list_view

    def openFileContextMenu(self, position, file_view):
        context_menu = QMenu(self)
        selected_indexes = file_view.selectionModel().selectedIndexes()

        if selected_indexes:
            # Gather selection: if exactly 1 item, use that path as a string
            if len(selected_indexes) == 1:
                idx = file_view.indexAt(position)
                if not idx.isValid():
                    idx = selected_indexes[0]
                paths = file_view.model().filePath(idx)
            else:
                paths = []
                for idx in selected_indexes:
                    p = file_view.model().filePath(idx)
                    if p not in paths:
                        paths.append(p)

            # Cut / Copy / Delete
            if isinstance(paths, list):
                delete_action = QAction("Delete Selected", self)
                delete_action.triggered.connect(lambda: self.confirmDelete(paths))
                context_menu.addAction(delete_action)

                cut_action = QAction("Cut Selected", self)
                cut_action.triggered.connect(lambda: self.cutFileOrFolder(paths))
                context_menu.addAction(cut_action)

                copy_action = QAction("Copy Selected", self)
                copy_action.triggered.connect(lambda: self.copyFileOrFolder(paths))
                context_menu.addAction(copy_action)

                # NEW: If only one item is selected, enable "Rename" for that path
                if len(paths) == 1:
                    rename_action = QAction("Rename", self)
                    rename_action.triggered.connect(lambda: self.renameFileOrFolder(paths[0], file_view))
                    context_menu.addAction(rename_action)

            else:
                delete_action = QAction("Delete", self)
                delete_action.triggered.connect(lambda: self.confirmDelete(paths))
                context_menu.addAction(delete_action)

                cut_action = QAction("Cut", self)
                cut_action.triggered.connect(lambda: self.cutFileOrFolder(paths))
                context_menu.addAction(cut_action)

                copy_action = QAction("Copy", self)
                copy_action.triggered.connect(lambda: self.copyFileOrFolder(paths))
                context_menu.addAction(copy_action)

                # NEW: single path, rename
                rename_action = QAction("Rename", self)
                rename_action.triggered.connect(lambda: self.renameFileOrFolder(paths, file_view))
                context_menu.addAction(rename_action)

            # Paste
            paste_action = QAction("Paste", self)
            paste_action.setEnabled(self.clipboard is not None)
            paste_action.triggered.connect(
                lambda: self.pasteFileOrFolder(file_view.model().filePath(file_view.rootIndex()))
            )
            context_menu.addAction(paste_action)

            # --- "Open With..." -> calls opens_me
            open_with_action = QAction("Open With...", self)
            open_with_action.triggered.connect(lambda: self.opens_me(selected_indexes))
            context_menu.addAction(open_with_action)

            # --- "Properties"
            properties_action = QAction("Properties", self)
            properties_action.triggered.connect(lambda: self.showProperties(selected_indexes))
            context_menu.addAction(properties_action)

        else:
            # If nothing is selected, show new file/folder + paste
            new_file_action = QAction("New Text File", self)
            new_file_action.triggered.connect(self.createNewTextFile)
            context_menu.addAction(new_file_action)

            new_folder_action = QAction("New Folder", self)
            new_folder_action.triggered.connect(self.createNewFolder)
            context_menu.addAction(new_folder_action)

            paste_action = QAction("Paste", self)
            paste_action.setEnabled(self.clipboard is not None)
            paste_action.triggered.connect(
                lambda: self.pasteFileOrFolder(file_view.model().filePath(file_view.rootIndex()))
            )
            context_menu.addAction(paste_action)

        context_menu.exec_(file_view.viewport().mapToGlobal(position))

    # NEW: Rename method
    def renameFileOrFolder(self, old_path, file_view):
        """
        Opens a dialog for the user to input a new name for the file/folder,
        then renames it.
        """
        base_dir = os.path.dirname(old_path)
        old_name = os.path.basename(old_path)

        new_name, ok = QInputDialog.getText(self, "Rename", f"Rename '{old_name}' to:")
        if ok and new_name:
            new_path = os.path.join(base_dir, new_name)
            if os.path.exists(new_path):
                QMessageBox.warning(
                    self,
                    "Error",
                    f"A file or folder with the name '{new_name}' already exists."
                )
                return
            try:
                os.rename(old_path, new_path)
                self.refreshCurrentTab()
            except Exception as e:
                QMessageBox.warning(self, "Error", f"Failed to rename: {e}")

    def openFileOrFolder(self, index, file_model):
        path = file_model.filePath(index)
        if os.path.isdir(path):
            self.updateCurrentTab(path)
        else:
            subprocess.run(['xdg-open', path])

    def updateCurrentTab(self, path, record_history=True):
        tab = self.tabs_widget.currentWidget()
        if tab:
            tab.setRootIndex(tab.model().index(path))
            self.current_paths[tab] = path
            self.updateAddressBar(path)
            self.updateStatusBar(path)

            if record_history:
                hist = self.history.get(tab, {"paths": [], "current": -1})
                # If the new path differs from the last in the list, update history
                if not hist["paths"] or hist["paths"][hist["current"]] != path:
                    hist["paths"] = hist["paths"][:hist["current"]+1]
                    hist["paths"].append(path)
                    hist["current"] = len(hist["paths"]) - 1
                self.history[tab] = hist
                self.updateNavigationButtons()

    def navigateToPath(self):
        path = self.address_bar.text()
        if os.path.isdir(path):
            self.updateCurrentTab(path)
        else:
            QMessageBox.warning(self, "Invalid Path", f"Path does not exist:\n{path}")

    def updateAddressBar(self, path):
        self.address_bar.setText(path)

    def updateStatusBar(self, path):
        self.status_bar.showMessage(f"Current Directory: {path}")

    def goHome(self):
        home_path = os.path.expanduser("~")
        self.updateCurrentTab(home_path)
        self.updateStatusBar(home_path)

    def goTrash(self):
        trash_path = os.path.expanduser("~/.local/share/Trash/files")
        trash_tab = self.getTabByTitle("Trash")
        if trash_tab:
            self.tabs_widget.setCurrentWidget(trash_tab)
            self.updateCurrentTab(trash_path)
            self.updateStatusBar(trash_path)
        else:
            self.addNewTab(trash_path)
            current_index = self.tabs_widget.currentIndex()
            self.tabs_widget.setTabText(current_index, "Trash")
            self.updateStatusBar(trash_path)

    def getTabByTitle(self, title):
        for index in range(self.tabs_widget.count()):
            if self.tabs_widget.tabText(index) == title:
                return self.tabs_widget.widget(index)
        return None

    def createNewTextFile(self):
        tab = self.tabs_widget.currentWidget()
        if tab:
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
        tab = self.tabs_widget.currentWidget()
        if tab:
            current_path = self.current_paths.get(tab, os.path.expanduser("~"))
            folder_name, ok = QInputDialog.getText(self, "New Folder", "Enter the name of the new folder:")
            if ok and folder_name:
                try:
                    os.makedirs(os.path.join(current_path, folder_name))
                    self.refreshCurrentTab()
                except Exception as e:
                    QMessageBox.warning(self, "Error", f"Failed to create new folder: {e}")

    def confirmDelete(self, paths):
        if isinstance(paths, list):
            names = ", ".join([os.path.basename(p) for p in paths])
            reply = QMessageBox.question(
                self, "Confirm Delete",
                f"Are you sure you want to delete the following items:\n{names}?",
                QMessageBox.Yes | QMessageBox.No
            )
            if reply == QMessageBox.Yes:
                for p in paths:
                    self.deleteFileOrFolder(p)
        else:
            reply = QMessageBox.question(
                self, "Confirm Delete",
                f"Are you sure you want to delete {os.path.basename(paths)}?",
                QMessageBox.Yes | QMessageBox.No
            )
            if reply == QMessageBox.Yes:
                self.deleteFileOrFolder(paths)

    def deleteFileOrFolder(self, path):
        trash_path = os.path.expanduser("~/.local/share/Trash/files")
        if os.path.exists(path):
            try:
                shutil.move(path, trash_path)
                self.refreshCurrentTab()
            except Exception as e:
                QMessageBox.warning(self, "Error", f"Failed to delete {path}: {e}")

    def cutFileOrFolder(self, paths):
        self.clipboard = paths if isinstance(paths, list) else [paths]
        self.clipboard_operation = 'cut'

    def copyFileOrFolder(self, paths):
        self.clipboard = paths if isinstance(paths, list) else [paths]
        self.clipboard_operation = 'copy'

    def pasteFileOrFolder(self, destination):
        if self.clipboard and self.clipboard_operation:
            for item in self.clipboard:
                destination_path = os.path.join(destination, os.path.basename(item))
                if os.path.exists(destination_path):
                    reply = QMessageBox.warning(
                        self, "Warning",
                        f"An item named {os.path.basename(item)} already exists in {destination}. Overwrite?",
                        QMessageBox.Yes | QMessageBox.No
                    )
                    if reply == QMessageBox.No:
                        continue
                try:
                    if self.clipboard_operation == 'cut':
                        shutil.move(item, destination)
                    elif self.clipboard_operation == 'copy':
                        if os.path.isdir(item):
                            shutil.copytree(item, destination_path)
                        else:
                            shutil.copy2(item, destination)
                except Exception as e:
                    QMessageBox.warning(self, "Error", f"Failed to paste {item}: {e}")
            self.clipboard = None
            self.clipboard_operation = None
            self.refreshCurrentTab()

    def refreshCurrentTab(self):
        tab = self.tabs_widget.currentWidget()
        if tab:
            path = self.current_paths.get(tab, os.path.expanduser("~"))
            self.updateCurrentTab(path)

    def updateNavigationButtons(self):
        tab = self.tabs_widget.currentWidget()
        hist = self.history.get(tab, {"paths": [], "current": -1})
        self.back_button.setEnabled(hist["current"] > 0)
        self.forward_button.setEnabled(hist["current"] < len(hist["paths"]) - 1)

    def goBack(self):
        tab = self.tabs_widget.currentWidget()
        hist = self.history.get(tab, None)
        if hist and hist["current"] > 0:
            hist["current"] -= 1
            path = hist["paths"][hist["current"]]
            self.current_paths[tab] = path
            self.updateCurrentTab(path, record_history=False)
            self.history[tab] = hist
            self.updateNavigationButtons()

    def goForward(self):
        tab = self.tabs_widget.currentWidget()
        hist = self.history.get(tab, None)
        if hist and hist["current"] < len(hist["paths"]) - 1:
            hist["current"] += 1
            path = hist["paths"][hist["current"]]
            self.current_paths[tab] = path
            self.updateCurrentTab(path, record_history=False)
            self.history[tab] = hist
            self.updateNavigationButtons()

    def onTabChanged(self, index):
        tab = self.tabs_widget.widget(index)
        if tab in self.current_paths:
            path = self.current_paths[tab]
            self.updateAddressBar(path)
            self.updateNavigationButtons()

    ################################
    # "Open With…" Program (opens_me)
    ################################
    def opens_me(self, indexes):
        """
        Prompts user for a program and opens the first selected file with that program.
        """
        if not indexes:
            return

        # Use the first selected item
        index = indexes[0]
        file_path = index.model().filePath(index)

        # If the user selected a directory, warn
        if os.path.isdir(file_path):
            QMessageBox.warning(self, "Open With...", "Cannot use 'Open With' on a directory.")
            return

        # Prompt for the program name
        program, ok = QInputDialog.getText(
            self, "Open with a program",
            "Type the name of the program you want to use:"
        )
        if ok and program:
            try:
                print(f"Attempting to open {file_path} with {program}")
                subprocess.Popen([program, file_path])
            except Exception as e:
                QMessageBox.warning(
                    self, "Error",
                    f"Failed to open file with {program}:\n{e}"
                )

    def showProperties(self, indexes):
        """
        Shows file properties (size, timestamps, permissions) for the first selected item.
        """
        if not indexes:
            return
        index = indexes[0]
        file_path = index.model().filePath(index)
        try:
            stat_info = os.stat(file_path)
            size = stat_info.st_size
            modified = time.ctime(stat_info.st_mtime)
            created = time.ctime(stat_info.st_ctime)
            permissions = oct(stat_info.st_mode)
            properties = (
                f"Path: {file_path}\n"
                f"Size: {size} bytes\n"
                f"Modified: {modified}\n"
                f"Created: {created}\n"
                f"Permissions: {permissions}"
            )
            QMessageBox.information(self, "Properties", properties)
        except Exception as e:
            QMessageBox.warning(self, "Error", f"Failed to get properties: {e}")
