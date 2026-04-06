#!/usr/bin/env python3
from __future__ import annotations

"""Tabbed file-browser widget used by Spin FM.

This module intentionally keeps file operations local and straightforward.
The most important changes in this revision are:

- one shared QFileSystemModel for all tabs (lower memory usage than one model
  per tab);
- history tracked per view instead of per tab index (more robust when tabs are
  closed);
- safer clipboard paste/move logic, including self/descendant checks;
- tab/address-bar synchronisation and stronger context-menu behaviour.
"""

import os
import shutil
import subprocess
import sys
from datetime import datetime
from urllib.parse import quote
from typing import Optional

SETTINGS_ORG = "Spin"
SETTINGS_APP = "Spin FM"

sys.dont_write_bytecode = True

from qt_compat import (
    QAction,
    QAbstractItemView,
    QDir,
    QFileSystemModel,
    QIcon,
    QInputDialog,
    QLineEdit,
    QListView,
    QMenu,
    QMessageBox,
    QStyle,
    QTabBar,
    QTabWidget,
    QToolBar,
    QToolButton,
    Qt,
    QVBoxLayout,
    QWidget,
    pyqtSignal,
)

# Cross-Qt QSize import.
try:
    from PyQt6.QtCore import QSize
except Exception:
    from PyQt5.QtCore import QSize


class CustomTabBar(QTabBar):
    """Tab bar with a small context menu for common tab actions."""

    tabDoubleClicked = pyqtSignal(int)
    closeTabRequested = pyqtSignal(int)
    newTabRequested = pyqtSignal()
    duplicateTabRequested = pyqtSignal(int)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setContextMenuPolicy(Qt.CustomContextMenu)
        self.customContextMenuRequested.connect(self.showContextMenu)

    def mouseDoubleClickEvent(self, event):
        tab_index = self.tabAt(event.pos())
        if tab_index >= 0:
            self.tabDoubleClicked.emit(tab_index)
        else:
            # Double-clicking empty space behaves like "new tab".
            self.newTabRequested.emit()
        super().mouseDoubleClickEvent(event)

    def showContextMenu(self, position):
        tab_index = self.tabAt(position)
        context_menu = QMenu(self)

        new_action = context_menu.addAction("New Tab")
        duplicate_action = None
        close_action = None
        if tab_index >= 0:
            duplicate_action = context_menu.addAction("Duplicate Tab")
            close_action = context_menu.addAction("Close Tab")

        pos = self.mapToGlobal(position)
        action = context_menu.exec(pos) if hasattr(context_menu, "exec") else context_menu.exec_(pos)

        if action == new_action:
            self.newTabRequested.emit()
        elif duplicate_action is not None and action == duplicate_action:
            self.duplicateTabRequested.emit(tab_index)
        elif close_action is not None and action == close_action:
            self.closeTabRequested.emit(tab_index)


class Tabs(QWidget):
    """Main tabbed file-manager widget.

    A single QFileSystemModel instance is shared by every tab. QFileSystemModel
    already caches directory data internally, so sharing it keeps the UI lighter
    than creating a fresh model per tab.
    """

    def __init__(self, parent=None):
        super().__init__(parent)

        # Clipboard state: None or ("cut" | "copy", [absolute_paths]).
        self.clipboard = None

        # History is keyed by the view object itself rather than by the current
        # tab index. That avoids stale/shifted history when tabs are closed.
        self.history = {}

        # The hidden-files flag is owned by Tabs so newly created tabs inherit
        # the current setting immediately.
        self.show_hidden_files = False
        self.home_path = self._default_home_path()

        self.layout = QVBoxLayout(self)

        # Shared file-system model: this is the main memory-usage improvement.
        self.fs_model = self._create_shared_model()

        # Toolbar.
        self.toolbar = QToolBar(self)
        self.toolbar.setIconSize(QSize(28, 28))
        self.layout.addWidget(self.toolbar)

        self.back_button = QToolButton()
        self.back_button.setIcon(self.style().standardIcon(QStyle.SP_ArrowBack))
        self.back_button.setToolTip("Back")
        self.back_button.clicked.connect(self.goBack)
        self.toolbar.addWidget(self.back_button)

        self.forward_button = QToolButton()
        self.forward_button.setIcon(self.style().standardIcon(QStyle.SP_ArrowForward))
        self.forward_button.setToolTip("Forward")
        self.forward_button.clicked.connect(self.goForward)
        self.toolbar.addWidget(self.forward_button)

        self.home_button = QToolButton()
        self.home_button.setIcon(self.style().standardIcon(QStyle.SP_DirHomeIcon))
        self.home_button.setToolTip("Home")
        self.home_button.clicked.connect(self.goHome)
        self.toolbar.addWidget(self.home_button)

        self.trash_button = QToolButton()
        self.trash_button.setIcon(self.style().standardIcon(QStyle.SP_TrashIcon))
        self.trash_button.setToolTip("Trash / Delete")
        self.trash_button.clicked.connect(self.trashOrGoTrash)
        self.toolbar.addWidget(self.trash_button)

        self.cut_button = QToolButton()
        self.cut_button.setIcon(self._theme_icon("edit-cut", QStyle.SP_FileIcon))
        self.cut_button.setToolTip("Cut (Ctrl+X)")
        self.cut_button.clicked.connect(self.cutSelection)
        self.toolbar.addWidget(self.cut_button)

        self.copy_button = QToolButton()
        self.copy_button.setIcon(self._theme_icon("edit-copy", QStyle.SP_FileIcon))
        self.copy_button.setToolTip("Copy (Ctrl+C)")
        self.copy_button.clicked.connect(self.copySelection)
        self.toolbar.addWidget(self.copy_button)

        self.paste_button = QToolButton()
        self.paste_button.setIcon(self._theme_icon("edit-paste", QStyle.SP_FileDialogNewFolder))
        self.paste_button.setToolTip("Paste (Ctrl+V)")
        self.paste_button.clicked.connect(self.pasteToCurrentFolder)
        self.paste_button.setEnabled(False)
        self.toolbar.addWidget(self.paste_button)

        self.address_bar = QLineEdit(self)
        self.address_bar.returnPressed.connect(self.navigateToPath)
        self.toolbar.addWidget(self.address_bar)

        self.tab_widget = QTabWidget(self)
        self.tab_widget.setTabsClosable(True)
        self.tab_widget.tabCloseRequested.connect(self.closeTab)
        self.tab_widget.currentChanged.connect(self._on_current_tab_changed)

        bar = CustomTabBar(self.tab_widget)
        bar.closeTabRequested.connect(self.closeTab)
        bar.tabDoubleClicked.connect(self.duplicateTab)
        bar.newTabRequested.connect(lambda: self.createNewTab(self.currentPath()))
        bar.duplicateTabRequested.connect(self.duplicateTab)
        self.tab_widget.setTabBar(bar)

        self.layout.addWidget(self.tab_widget)

        # First tab.
        self.createNewTab(self.home_path)

    # ------------------------------------------------------------------
    # UI / model helpers
    # ------------------------------------------------------------------
    def _theme_icon(self, theme_name: str, fallback_pixmap: QStyle.StandardPixmap):
        """Return a themed icon with a standard-icon fallback."""
        icon = QIcon.fromTheme(theme_name)
        if hasattr(icon, "isNull") and icon.isNull():
            icon = self.style().standardIcon(fallback_pixmap)
        return icon

    def _create_shared_model(self):
        """Create and configure a single QFileSystemModel for all tabs.

        Sharing the model is cheaper than one-model-per-tab because Qt already
        caches directory data and file icons internally.
        """
        model = QFileSystemModel(self)

        try:
            model.setReadOnly(False)
        except Exception:
            pass

        # Custom directory icons can trigger expensive lookups on some desktop
        # setups and network mounts. Disabling them keeps navigation snappier.
        try:
            option_owner = getattr(QFileSystemModel, "Option", QFileSystemModel)
            option = getattr(option_owner, "DontUseCustomDirectoryIcons", None)
            if option is not None and hasattr(model, "setOption"):
                model.setOption(option, True)
        except Exception:
            pass

        self._apply_hidden_filter_to_model(model)

        # QFileSystemModel only starts populating after setRootPath() is called.
        # Prime it with the user's home directory first so the initial tab does
        # not momentarily fall back to the filesystem root on slower systems.
        root_path = self.home_path
        if not os.path.isdir(root_path):
            try:
                root_path = QDir.rootPath()
            except Exception:
                root_path = os.path.abspath(os.sep)
        model.setRootPath(root_path)
        return model

    def _apply_hidden_filter_to_model(self, model) -> None:
        """Apply the current hidden-files filter to the shared model."""
        flags = QDir.AllEntries | QDir.NoDotAndDotDot | QDir.AllDirs
        if self.show_hidden_files:
            try:
                flags = flags | QDir.Hidden
            except Exception:
                pass

        try:
            model.setFilter(flags)
        except Exception:
            try:
                model.setFilter(int(flags))
            except Exception:
                pass

    def _default_home_path(self) -> str:
        """Return the best available user-home directory.

        QDir.homePath() tracks the desktop user better than hard-coding the
        filesystem root fallback. If it is unavailable or invalid, fall back to
        os.path.expanduser("~").
        """
        candidates = []

        try:
            candidates.append(QDir.homePath())
        except Exception:
            pass

        try:
            candidates.append(os.path.expanduser("~"))
        except Exception:
            pass

        for candidate in candidates:
            if not candidate:
                continue
            resolved = os.path.abspath(os.path.expanduser(str(candidate)))
            if os.path.isdir(resolved):
                return resolved

        try:
            return os.path.abspath(os.path.expanduser("~"))
        except Exception:
            return os.path.abspath(os.sep)

    def _display_name_for_path(self, path: str) -> str:
        """Return a compact tab title for a filesystem path."""
        cleaned = os.path.normpath(path)
        name = os.path.basename(cleaned)
        return name or cleaned

    def _install_tab_close_button(self, tab_index: int) -> None:
        """Install an always-visible small “x” close button on a tab.

        Relying only on Qt's themed close icon can make the button effectively
        invisible on some desktops/themes. A tiny text button keeps the close
        affordance visible everywhere.
        """
        if tab_index < 0:
            return

        button = QToolButton(self.tab_widget)
        button.setText("×")
        button.setToolTip("Close tab")
        button.setAutoRaise(True)
        cursor_shape = getattr(Qt, "PointingHandCursor", None)
        if cursor_shape is not None:
            try:
                button.setCursor(cursor_shape)
            except Exception:
                pass
        button.setFixedSize(16, 16)
        button.setStyleSheet(
            "QToolButton { border: none; padding: 0px; margin: 0px; font-size: 12pt; font-weight: bold; }"
            "QToolButton:hover { border-radius: 8px; }"
        )
        button.clicked.connect(lambda _checked=False, b=button: self.closeTab(self._tab_index_for_close_button(b)))

        self.tab_widget.tabBar().setTabButton(tab_index, self._tab_button_side(), button)

    def _tab_button_side(self):
        try:
            return QTabBar.ButtonPosition.RightSide
        except Exception:
            return QTabBar.RightSide

    def _tab_index_for_close_button(self, button) -> int:
        tab_bar = self.tab_widget.tabBar()
        side = self._tab_button_side()
        for i in range(self.tab_widget.count()):
            if tab_bar.tabButton(i, side) is button:
                return i
        return -1

    def _model_index_for_directory(self, path: str):
        """Return a stable model index for *path*.

        QFileSystemModel can briefly hand back an invalid index when a directory
        has not been primed yet. Calling setRootPath() for the target directory
        ensures the model starts watching/populating it, which avoids the view
        dropping back to '/'.
        """
        target = self._normalize_existing_directory(path)

        index = None
        try:
            index = self.fs_model.setRootPath(target)
        except Exception:
            index = None

        try:
            if index is not None and index.isValid():
                return index
        except Exception:
            pass

        try:
            index = self.fs_model.index(target)
        except Exception:
            index = None

        return index

    def _path_from_index(self, index) -> str:
        """Resolve a QFileSystemModel index to a filesystem path safely."""
        try:
            if index is None or not index.isValid():
                return ""
        except Exception:
            return ""

        try:
            model = index.model()
        except Exception:
            model = None

        if model is None or not hasattr(model, "filePath"):
            return ""

        try:
            return model.filePath(index)
        except Exception:
            return ""

    def _normalize_existing_directory(self, path: str) -> str:
        """Normalize a path and return a directory path when possible.

        If the input points to a file, its parent directory is used. If the path
        does not exist, the current directory (or home) is used as a safe
        fallback.
        """
        if not path:
            return self.home_path

        target = os.path.abspath(os.path.expanduser(path))
        if os.path.isfile(target):
            target = os.path.dirname(target)

        if os.path.isdir(target):
            return target

        fallback = self.currentPath() if self.currentView() is not None else self.home_path
        fallback = os.path.abspath(os.path.expanduser(fallback))
        return fallback if os.path.isdir(fallback) else self.home_path

    def _history_for_view(self, view) -> dict:
        """Return the history bucket for a given view."""
        return self.history.setdefault(view, {"back": [], "forward": []})

    def _set_view_root(self, view, path: str) -> bool:
        """Point a view at a directory and synchronise related tab UI."""
        if view is None:
            return False

        target = self._normalize_existing_directory(path)
        index = self._model_index_for_directory(target)
        try:
            if index is None or not index.isValid():
                return False
        except Exception:
            pass

        view.setRootIndex(index)
        try:
            view.setProperty("current_path", target)
        except Exception:
            setattr(view, "_spinfm_current_path", target)

        tab_index = self.tab_widget.indexOf(view)
        if tab_index >= 0:
            self.tab_widget.setTabText(tab_index, self._display_name_for_path(target))
            self.tab_widget.setTabToolTip(tab_index, target)

        if view is self.currentView():
            self.address_bar.setText(target)
            self._update_navigation_buttons()

        return True

    def _sync_current_view_ui(self) -> None:
        """Refresh address bar and button state after a tab/view change."""
        view = self.currentView()
        if view is None:
            self.address_bar.clear()
            self.back_button.setEnabled(False)
            self.forward_button.setEnabled(False)
            return

        self.address_bar.setText(self.currentPath(view))
        self._update_navigation_buttons()

    def _on_current_tab_changed(self, index: int) -> None:
        """Keep the address bar in sync with the selected tab."""
        del index
        self._sync_current_view_ui()

    def _update_navigation_buttons(self) -> None:
        """Enable/disable Back and Forward based on the active tab history."""
        view = self.currentView()
        hist = self._history_for_view(view) if view is not None else {"back": [], "forward": []}
        self.back_button.setEnabled(bool(hist["back"]))
        self.forward_button.setEnabled(bool(hist["forward"]))

    def _reset_view_history(self, view) -> None:
        """Clear navigation history for a single view."""
        if view is None:
            return
        hist = self._history_for_view(view)
        hist["back"].clear()
        hist["forward"].clear()
        if view is self.currentView():
            self._update_navigation_buttons()

    def _retarget_open_tabs(self, old_path: str, new_path: Optional[str]) -> None:
        """Retarget tabs whose current directory moved/was renamed.

        This keeps already-open tabs usable when a directory is renamed or moved
        elsewhere by the file manager itself.
        """
        old_path = os.path.abspath(os.path.expanduser(old_path))
        old_prefix = old_path + os.sep

        for i in range(self.tab_widget.count()):
            view = self.tab_widget.widget(i)
            if view is None:
                continue

            current = self.currentPath(view)
            if current == old_path:
                suffix = ""
            elif current.startswith(old_prefix):
                suffix = current[len(old_path):]
            else:
                continue

            if new_path is None:
                replacement = os.path.dirname(old_path)
            else:
                replacement = new_path + suffix

            replacement = os.path.abspath(os.path.expanduser(replacement))
            if not os.path.isdir(replacement):
                replacement = os.path.dirname(replacement)

            if not os.path.isdir(replacement):
                replacement = self.home_path

            self._set_view_root(view, replacement)
            self._reset_view_history(view)

        self._sync_current_view_ui()

    # ------------------------------------------------------------------
    # Tab / view management
    # ------------------------------------------------------------------
    def createNewTab(self, path):
        """Create a new file view rooted at *path*."""
        path = self._normalize_existing_directory(path)

        view = QListView(self.tab_widget)
        view.setModel(self.fs_model)
        view.setRootIndex(self._model_index_for_directory(path))
        try:
            view.setProperty("current_path", path)
        except Exception:
            setattr(view, "_spinfm_current_path", path)
        view.setViewMode(QListView.IconMode)
        view.setIconSize(QSize(64, 64))

        # Batched layout keeps large folders responsive.
        try:
            view.setLayoutMode(QListView.Batched)
            view.setBatchSize(100)
        except Exception:
            pass

        try:
            view.setSelectionMode(QAbstractItemView.ExtendedSelection)
        except Exception:
            try:
                view.setSelectionMode(QListView.ExtendedSelection)
            except Exception:
                pass

        try:
            view.setSelectionRectVisible(True)
        except Exception:
            pass

        view.setContextMenuPolicy(Qt.CustomContextMenu)
        view.customContextMenuRequested.connect(lambda pos, v=view: self.openFileContextMenu(pos, v))
        view.doubleClicked.connect(lambda idx, v=view: self.onFileActivated(idx, v))

        self._install_shortcuts(view)

        tab_index = self.tab_widget.addTab(view, self._display_name_for_path(path))
        self.tab_widget.setTabToolTip(tab_index, path)
        self._install_tab_close_button(tab_index)
        self.history[view] = {"back": [], "forward": []}

        self.tab_widget.setCurrentWidget(view)
        self._sync_current_view_ui()
        return tab_index

    def addNewTab(self, path):
        return self.createNewTab(path)

    def duplicateTab(self, index):
        if index < 0:
            return
        view = self.tab_widget.widget(index)
        if view is None:
            return
        self.createNewTab(self.currentPath(view))

    def closeTab(self, index):
        """Close a tab, but always keep at least one working tab alive."""
        if index < 0 or index >= self.tab_widget.count():
            return

        view = self.tab_widget.widget(index)
        if view is None:
            return

        if self.tab_widget.count() == 1:
            # Keep one usable tab instead of leaving the UI empty.
            self._reset_view_history(view)
            self._set_view_root(view, self.home_path)
            self.tab_widget.setCurrentWidget(view)
            return

        self.history.pop(view, None)
        self.tab_widget.removeTab(index)
        try:
            view.deleteLater()
        except Exception:
            pass

        self._sync_current_view_ui()

    def currentView(self):
        return self.tab_widget.currentWidget()

    def currentPath(self, view=None):
        target_view = view or self.currentView()
        if target_view is None:
            return self.home_path

        path = None

        try:
            path = target_view.property("current_path")
        except Exception:
            path = None

        if not path:
            path = getattr(target_view, "_spinfm_current_path", None)

        if not path:
            try:
                path = self.fs_model.filePath(target_view.rootIndex())
            except Exception:
                path = None

        if not path:
            path = self.home_path

        path = os.path.abspath(os.path.expanduser(str(path)))
        if os.path.isfile(path):
            path = os.path.dirname(path)
        if not os.path.isdir(path):
            path = self.home_path
        return path

    def refreshCurrentTab(self):
        self.refreshView(self.currentView())

    def refreshView(self, view):
        """Refresh a view without rebuilding the shared model.

        QFileSystemModel already watches directories and updates itself. Calling
        QAbstractItemView.reset() here can discard the current rooted directory
        on some Qt builds, so keep the refresh lightweight and explicitly pin the
        view back to its saved folder.
        """
        if view is None:
            return
        path = self.currentPath(view)
        self._set_view_root(view, path)
        try:
            self.fs_model.setRootPath(path)
        except Exception:
            pass
        try:
            view.scheduleDelayedItemsLayout()
        except Exception:
            pass
        try:
            view.viewport().update()
        except Exception:
            pass

    # ------------------------------------------------------------------
    # Selection and shortcuts
    # ------------------------------------------------------------------
    def _install_shortcuts(self, view: QListView) -> None:
        """Install view-scoped shortcuts.

        Widget-with-children scope keeps these shortcuts active only while the
        file view has focus, so Ctrl+C in the address bar still copies text.
        """

        def _bind(action_text: str, shortcut: str, slot):
            action = QAction(action_text, view)
            action.setShortcut(shortcut)
            try:
                action.setShortcutContext(Qt.WidgetWithChildrenShortcut)
            except Exception:
                pass
            action.triggered.connect(slot)
            view.addAction(action)
            return action

        _bind("Cut", "Ctrl+X", self.cutSelection)
        _bind("Copy", "Ctrl+C", self.copySelection)
        _bind("Paste", "Ctrl+V", self.pasteToCurrentFolder)
        _bind("Delete", "Delete", self.deleteSelection)
        _bind("Refresh", "F5", self.refreshCurrentTab)

        select_all = QAction("Select All", view)
        select_all.setShortcut("Ctrl+A")
        try:
            select_all.setShortcutContext(Qt.WidgetWithChildrenShortcut)
        except Exception:
            pass
        select_all.triggered.connect(view.selectAll)
        view.addAction(select_all)

        new_tab_action = QAction("New Tab", view)
        new_tab_action.setShortcut("Ctrl+T")
        try:
            new_tab_action.setShortcutContext(Qt.WidgetWithChildrenShortcut)
        except Exception:
            pass
        new_tab_action.triggered.connect(lambda: self.createNewTab(self.currentPath()))
        view.addAction(new_tab_action)

    def selectedPaths(self, view=None):
        """Return a unique list of selected filesystem paths."""
        target_view = view or self.currentView()
        if target_view is None:
            return []

        try:
            selected_indexes = target_view.selectionModel().selectedIndexes()
        except Exception:
            return []

        paths = []
        seen = set()
        for index in selected_indexes:
            path = self._path_from_index(index)
            if not path or path in seen:
                continue
            seen.add(path)
            paths.append(path)
        return paths

    # ------------------------------------------------------------------
    # Toolbar actions
    # ------------------------------------------------------------------
    def cutSelection(self):
        paths = self.selectedPaths()
        if not paths:
            QMessageBox.information(self, "Cut", "Select one or more items to cut.")
            return
        self.cutFileOrFolder(paths)

    def copySelection(self):
        paths = self.selectedPaths()
        if not paths:
            QMessageBox.information(self, "Copy", "Select one or more items to copy.")
            return
        self.copyFileOrFolder(paths)

    def pasteToCurrentFolder(self):
        self.pasteFileOrFolder(self.currentPath())

    def deleteSelection(self):
        paths = self.selectedPaths()
        if not paths:
            QMessageBox.information(self, "Delete", "Select one or more items to delete or move to Trash.")
            return
        self.confirmDelete(paths)

    def trashOrGoTrash(self):
        """Trash the current selection, or open the Trash folder if nothing is selected."""
        paths = self.selectedPaths()
        if paths:
            self.confirmDelete(paths)
        else:
            self.goTrash()

    # ------------------------------------------------------------------
    # Navigation
    # ------------------------------------------------------------------
    def goBack(self):
        view = self.currentView()
        if view is None:
            return

        hist = self._history_for_view(view)
        if not hist["back"]:
            return

        current = self.currentPath(view)
        previous = hist["back"].pop()
        hist["forward"].append(current)
        self._navigateTo(previous, push=False, view=view)

    def goForward(self):
        view = self.currentView()
        if view is None:
            return

        hist = self._history_for_view(view)
        if not hist["forward"]:
            return

        current = self.currentPath(view)
        next_path = hist["forward"].pop()
        hist["back"].append(current)
        self._navigateTo(next_path, push=False, view=view)

    def goHome(self):
        self._navigateTo(self.home_path)

    def goTrash(self):
        trash_files = os.path.expanduser("~/.local/share/Trash/files")
        trash_root = os.path.expanduser("~/.local/share/Trash")
        path = trash_files if os.path.isdir(trash_files) else trash_root
        if not os.path.isdir(path):
            path = self.home_path
        self._navigateTo(path)

    def navigateToPath(self):
        target = self.address_bar.text().strip() or self.home_path
        self._navigateTo(target)

    def _navigateTo(self, path, push=True, view=None):
        """Navigate a view to *path* and update history if needed."""
        target_view = view or self.currentView()
        if target_view is None:
            return

        target = os.path.abspath(os.path.expanduser(path))
        if os.path.isfile(target):
            target = os.path.dirname(target)

        if not os.path.isdir(target):
            QMessageBox.warning(self, "Not Found", f"Directory does not exist:\n{target}")
            return

        previous = self.currentPath(target_view)
        if push and previous != target:
            hist = self._history_for_view(target_view)
            hist["back"].append(previous)
            hist["forward"].clear()

        if self._set_view_root(target_view, target):
            if target_view is self.currentView():
                self.address_bar.setText(target)
                self._update_navigation_buttons()

    # ------------------------------------------------------------------
    # File activation / launch helpers
    # ------------------------------------------------------------------
    def _launch_default_application(self, path: str):
        """Open a file with the desktop default application.

        Popen is used intentionally so the UI does not block waiting for the
        launched application.
        """
        if not shutil.which("xdg-open"):
            raise RuntimeError("xdg-open was not found in PATH.")

        subprocess.Popen(
            ["xdg-open", path],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            start_new_session=True,
            close_fds=True,
        )

    def _open_paths(self, paths, new_tab=False):
        """Open files/directories from a list of paths."""
        items = self._as_paths(paths)
        if not items:
            return

        errors = []

        if new_tab:
            for path in items:
                if os.path.isdir(path):
                    self.createNewTab(path)
                else:
                    try:
                        self._launch_default_application(path)
                    except Exception as exc:
                        errors.append(f"{path}: {exc}")
        else:
            if len(items) == 1 and os.path.isdir(items[0]):
                self._navigateTo(items[0])
            else:
                for path in items:
                    if os.path.isdir(path):
                        self.createNewTab(path)
                    else:
                        try:
                            self._launch_default_application(path)
                        except Exception as exc:
                            errors.append(f"{path}: {exc}")

        if errors:
            QMessageBox.warning(
                self,
                "Open Error",
                "Some items could not be opened:\n\n" + "\n".join(errors),
            )

    def onFileActivated(self, index, file_view):
        path = self._path_from_index(index)
        if not path:
            return
        if os.path.isdir(path):
            self._navigateTo(path, view=file_view)
        else:
            self.opens_me([index])

    def opens_me(self, selected_indexes):
        """Open files using the system default handler.

        If the default open fails, the user is given the chance to choose a
        command manually via "Open With...".
        """
        if not selected_indexes:
            return

        file_indexes = []
        errors = []
        for index in selected_indexes:
            path = self._path_from_index(index)
            if not path or os.path.isdir(path):
                continue
            file_indexes.append(index)
            try:
                self._launch_default_application(path)
            except Exception as exc:
                errors.append(f"{path}: {exc}")

        if not file_indexes:
            return

        if errors:
            QMessageBox.warning(
                self,
                "Open File",
                "Default open failed for one or more files.\n\n"
                + "\n".join(errors)
                + "\n\nYou can choose a program manually next.",
            )
            self.open_with(file_indexes)

    # ------------------------------------------------------------------
    # Context menu
    # ------------------------------------------------------------------
    def openFileContextMenu(self, position, file_view):
        """Open a context menu for the clicked item or for empty space.

        If the user right-clicks an unselected item, the menu acts on that item.
        If the user right-clicks empty space, the menu shows folder-level
        actions such as new file/folder, paste, and refresh.
        """
        context_menu = QMenu(self)

        clicked_index = file_view.indexAt(position)
        clicked_path = self._path_from_index(clicked_index)
        selected_paths = self.selectedPaths(file_view)

        if clicked_path:
            if clicked_path in selected_paths:
                target_paths = selected_paths or [clicked_path]
            else:
                target_paths = [clicked_path]
        else:
            target_paths = []

        open_action = None
        open_new_tab_action = None
        rename_action = None
        open_with_action = None
        delete_action = None
        cut_action = None
        copy_action = None
        paste_action = None
        new_file_action = None
        new_folder_action = None
        refresh_action = None

        if target_paths:
            if len(target_paths) == 1:
                open_action = context_menu.addAction("Open")
                if os.path.isdir(target_paths[0]):
                    open_new_tab_action = context_menu.addAction("Open in New Tab")
                rename_action = context_menu.addAction("Rename")

            delete_action = context_menu.addAction("Delete")
            cut_action = context_menu.addAction("Cut")
            copy_action = context_menu.addAction("Copy")

            if any(os.path.isfile(p) or os.path.islink(p) for p in target_paths):
                open_with_action = context_menu.addAction("Open With...")

            paste_action = context_menu.addAction("Paste")
            paste_action.setEnabled(self.clipboard is not None)
            refresh_action = context_menu.addAction("Refresh")
        else:
            new_file_action = context_menu.addAction("New Text File")
            new_folder_action = context_menu.addAction("New Folder")
            paste_action = context_menu.addAction("Paste")
            paste_action.setEnabled(self.clipboard is not None)
            refresh_action = context_menu.addAction("Refresh")

        pos = file_view.viewport().mapToGlobal(position)
        chosen = context_menu.exec(pos) if hasattr(context_menu, "exec") else context_menu.exec_(pos)

        if chosen == open_action:
            self._open_paths(target_paths)
        elif chosen == open_new_tab_action:
            self._open_paths(target_paths, new_tab=True)
        elif chosen == rename_action:
            self.renameFileOrFolder(target_paths[0], file_view)
        elif chosen == delete_action:
            self.confirmDelete(target_paths)
        elif chosen == cut_action:
            self.cutFileOrFolder(target_paths)
        elif chosen == copy_action:
            self.copyFileOrFolder(target_paths)
        elif chosen == open_with_action:
            indexes = []
            target_set = set(target_paths)
            for index in file_view.selectionModel().selectedIndexes():
                path = self._path_from_index(index)
                if path in target_set:
                    indexes.append(index)
            if not indexes and clicked_path:
                indexes = [clicked_index]
            self.open_with(indexes)
        elif chosen == paste_action:
            self.pasteFileOrFolder(self.currentPath(file_view))
        elif chosen == new_file_action:
            self.createNewTextFile()
        elif chosen == new_folder_action:
            self.createNewFolder()
        elif chosen == refresh_action:
            self.refreshView(file_view)

    # ------------------------------------------------------------------
    # Name validation helpers
    # ------------------------------------------------------------------
    def _validate_child_name(self, name: str, title: str) -> Optional[str]:
        """Validate a new file/folder name entered by the user."""
        value = (name or "").strip()
        if not value:
            QMessageBox.warning(self, title, "Please enter a name.")
            return None

        if value in {".", ".."}:
            QMessageBox.warning(self, title, "'.' and '..' are not valid names here.")
            return None

        if "/" in value or "\\" in value:
            QMessageBox.warning(self, title, "Name must not contain path separators.")
            return None

        return value

    # ------------------------------------------------------------------
    # File operations
    # ------------------------------------------------------------------
    def createNewTextFile(self):
        base = self.currentPath()
        name, ok = QInputDialog.getText(self, "New Text File", "Name:")
        if not ok:
            return

        name = self._validate_child_name(name, "New Text File")
        if not name:
            return

        path = os.path.join(base, name)
        if os.path.exists(path):
            QMessageBox.warning(
                self,
                "File Exists",
                f"A file or folder named:\n\n{path}\n\nalready exists.\nPlease choose a different name.",
            )
            return

        try:
            with open(path, "w", encoding="utf-8"):
                pass
            self.refreshCurrentTab()
        except Exception as exc:
            QMessageBox.critical(self, "Error", str(exc))

    def createNewFolder(self):
        base = self.currentPath()
        name, ok = QInputDialog.getText(self, "New Folder", "Name:")
        if not ok:
            return

        name = self._validate_child_name(name, "New Folder")
        if not name:
            return

        path = os.path.join(base, name)
        try:
            os.makedirs(path, exist_ok=False)
            self.refreshCurrentTab()
        except FileExistsError:
            QMessageBox.warning(self, "Exists", f"Folder already exists:\n{path}")
        except Exception as exc:
            QMessageBox.critical(self, "Error", str(exc))

    def renameFileOrFolder(self, paths, file_view=None):
        """Rename a single file or folder."""
        if isinstance(paths, (list, tuple)):
            if len(paths) != 1:
                QMessageBox.information(self, "Rename", "Please select a single item to rename.")
                return
            target = paths[0]
        else:
            target = paths

        if not target or not isinstance(target, str):
            QMessageBox.warning(self, "Rename", "No valid item to rename.")
            return

        target = os.path.abspath(os.path.expanduser(target))
        if not os.path.exists(target):
            QMessageBox.warning(self, "Rename", f"Item not found:\n{target}")
            return

        old_name = os.path.basename(target.rstrip(os.sep))
        parent = os.path.dirname(target.rstrip(os.sep)) or self.currentPath()

        try:
            new_name, ok = QInputDialog.getText(self, "Rename", "New name:", text=old_name)
        except TypeError:
            new_name, ok = QInputDialog.getText(self, "Rename", "New name:")

        if not ok:
            return

        new_name = self._validate_child_name(new_name, "Rename")
        if not new_name or new_name == old_name:
            return

        new_path = os.path.join(parent, new_name)
        if os.path.exists(new_path):
            QMessageBox.warning(self, "Rename", f"An item with that name already exists:\n{new_path}")
            return

        try:
            os.rename(target, new_path)
        except Exception as exc:
            QMessageBox.critical(self, "Rename Error", str(exc))
            return

        # If an open tab points into the renamed directory, follow the rename.
        if os.path.isdir(new_path):
            self._retarget_open_tabs(target, new_path)

        if file_view is not None:
            self.refreshView(file_view)
        else:
            self.refreshCurrentTab()

    def confirmDelete(self, paths):
        targets = self._as_paths(paths)
        if not targets:
            return

        trash_files = os.path.expanduser("~/.local/share/Trash/files")
        all_in_trash = all(self._same_or_subpath(p, trash_files) for p in targets)

        if all_in_trash:
            msg = (
                "Permanently delete the selected item?"
                if len(targets) == 1
                else f"Permanently delete {len(targets)} selected items?"
            )
            title = "Confirm Permanent Delete"
        else:
            msg = (
                "Move the selected item to Trash?"
                if len(targets) == 1
                else f"Move {len(targets)} selected items to Trash?"
            )
            title = "Confirm Delete"

        if QMessageBox.question(
            self,
            title,
            msg,
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No,
        ) != QMessageBox.Yes:
            return

        errors = []
        for path in targets:
            try:
                self._trash_one(path)
            except Exception as exc:
                errors.append(f"{path}: {exc}")

        if errors:
            QMessageBox.warning(
                self,
                "Delete Summary",
                "Some items could not be deleted:\n\n" + "\n".join(errors),
            )

        self.refreshCurrentTab()

    # ------------------------------------------------------------------
    # Trash helpers
    # ------------------------------------------------------------------
    def _same_or_subpath(self, child_path: str, parent_path: str) -> bool:
        """Return True when child_path == parent_path or child_path is inside it."""
        child = os.path.abspath(os.path.expanduser(child_path))
        parent = os.path.abspath(os.path.expanduser(parent_path))
        try:
            return os.path.commonpath([child, parent]) == parent
        except Exception:
            return False

    def _is_subpath(self, child_path: str, parent_path: str) -> bool:
        """Return True when child_path is strictly inside parent_path."""
        child = os.path.abspath(os.path.expanduser(child_path))
        parent = os.path.abspath(os.path.expanduser(parent_path))
        if child == parent:
            return False
        try:
            return os.path.commonpath([child, parent]) == parent
        except Exception:
            return False

    def _trash_one(self, path: str):
        """Move a path to Trash, or permanently delete it if it is already in Trash."""
        path = os.path.abspath(os.path.expanduser(path))
        if not os.path.exists(path):
            raise FileNotFoundError("Item no longer exists.")

        trash_root = os.path.expanduser("~/.local/share/Trash")
        trash_files = os.path.join(trash_root, "files")
        trash_info = os.path.join(trash_root, "info")

        if self._same_or_subpath(path, trash_files):
            self._delete_from_trash(path, trash_files, trash_info)
            return

        # Prefer gio when available because it integrates with the desktop's
        # native trash implementation and metadata handling.
        gio_path = shutil.which("gio")
        if gio_path:
            try:
                subprocess.run(
                    [gio_path, "trash", path],
                    check=True,
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.PIPE,
                    text=True,
                )
                if os.path.isdir(path):
                    self._retarget_open_tabs(path, None)
                return
            except Exception:
                # Fall back to the manual implementation below.
                pass

        os.makedirs(trash_files, exist_ok=True)
        os.makedirs(trash_info, exist_ok=True)

        base_name = os.path.basename(path.rstrip(os.sep)) or "unnamed"
        unique_name = self._unique_trash_name(trash_files, trash_info, base_name)
        target = os.path.join(trash_files, unique_name)
        final_info_path = os.path.join(trash_info, unique_name + ".trashinfo")
        temp_info_path = os.path.join(trash_info, f".{unique_name}.{os.getpid()}.tmp")

        self._write_trashinfo(temp_info_path, path)
        try:
            shutil.move(path, target)
            os.replace(temp_info_path, final_info_path)
        except Exception as exc:
            try:
                if os.path.exists(temp_info_path):
                    os.remove(temp_info_path)
            except Exception:
                pass
            raise RuntimeError(f"Could not move item to Trash: {exc}") from exc

        if os.path.isdir(target):
            self._retarget_open_tabs(path, None)

    def _delete_from_trash(self, path: str, trash_files: str, trash_info: str) -> None:
        """Permanently remove an item that is already inside Trash."""
        name = os.path.basename(path.rstrip(os.sep))
        if os.path.isdir(path) and not os.path.islink(path):
            shutil.rmtree(path)
        else:
            os.remove(path)

        info_path = os.path.join(trash_info, name + ".trashinfo")
        if os.path.exists(info_path):
            try:
                os.remove(info_path)
            except Exception:
                pass

        self._retarget_open_tabs(path, None)

    def _write_trashinfo(self, info_path: str, original_path: str) -> None:
        """Write a freedesktop-style .trashinfo metadata file."""
        encoded_path = quote(original_path, safe="/")
        deletion_date = datetime.now().strftime("%Y-%m-%dT%H:%M:%S")
        content = (
            "[Trash Info]\n"
            f"Path={encoded_path}\n"
            f"DeletionDate={deletion_date}\n"
        )
        with open(info_path, "w", encoding="utf-8", newline="\n") as handle:
            handle.write(content)

    def _unique_trash_name(self, trash_files: str, trash_info: str, name: str) -> str:
        """Return a unique basename for Trash files and .trashinfo metadata."""
        candidate = name
        root, ext = os.path.splitext(name)
        counter = 2

        while True:
            target = os.path.join(trash_files, candidate)
            info = os.path.join(trash_info, candidate + ".trashinfo")
            if not os.path.exists(target) and not os.path.exists(info):
                return candidate
            candidate = f"{root} ({counter}){ext}"
            counter += 1

    # ------------------------------------------------------------------
    # Clipboard helpers
    # ------------------------------------------------------------------
    def _as_paths(self, items):
        """Normalise strings / lists / QModelIndex values into existing paths."""
        paths = []

        if isinstance(items, str):
            paths = [items]
        elif isinstance(items, (list, tuple, set)):
            for item in items:
                if isinstance(item, str):
                    paths.append(item)
                else:
                    path = self._path_from_index(item)
                    if path:
                        paths.append(path)

        unique_paths = []
        seen = set()
        for path in paths:
            normalized = os.path.abspath(os.path.expanduser(path))
            if normalized in seen or not os.path.exists(normalized):
                continue
            seen.add(normalized)
            unique_paths.append(normalized)
        return unique_paths

    def cutFileOrFolder(self, paths):
        items = self._as_paths(paths)
        if not items:
            QMessageBox.warning(self, "Cut", "No valid items to cut.")
            return
        self.clipboard = ("cut", items)
        self.paste_button.setEnabled(True)
        QMessageBox.information(self, "Cut", f"Ready to move {len(items)} item(s).")

    def copyFileOrFolder(self, paths):
        items = self._as_paths(paths)
        if not items:
            QMessageBox.warning(self, "Copy", "No valid items to copy.")
            return
        self.clipboard = ("copy", items)
        self.paste_button.setEnabled(True)
        QMessageBox.information(self, "Copy", f"Ready to copy {len(items)} item(s).")

    def _prompt_overwrite(self, dst_path: str, is_dir: bool) -> str:
        """Ask the user how to handle an existing destination path."""
        box = QMessageBox(self)
        box.setWindowTitle("Overwrite?")
        what = "folder" if is_dir else "file"
        box.setText(f"“{dst_path}” already exists.\n\nOverwrite this {what}?")
        box.setIcon(QMessageBox.Question)

        btn_yes = box.addButton("Yes", QMessageBox.YesRole)
        btn_no = box.addButton("No", QMessageBox.NoRole)
        btn_yes_all = box.addButton("Yes to All", QMessageBox.YesRole)
        btn_no_all = box.addButton("No to All", QMessageBox.NoRole)
        btn_cancel = box.addButton("Cancel", QMessageBox.RejectRole)

        exec_method = getattr(box, "exec", None) or getattr(box, "exec_", None)
        if exec_method is None:
            raise RuntimeError("QMessageBox has no exec/exec_ method")
        exec_method()
        clicked = box.clickedButton()

        if clicked is btn_yes:
            return "yes"
        if clicked is btn_no:
            return "no"
        if clicked is btn_yes_all:
            return "yes_all"
        if clicked is btn_no_all:
            return "no_all"
        if clicked is btn_cancel:
            return "cancel"
        return "cancel"

    def _copy_entry(self, src: str, dst: str) -> None:
        """Copy a single filesystem entry while preserving metadata when possible."""
        if os.path.isdir(src) and not os.path.islink(src):
            shutil.copytree(src, dst, symlinks=True, copy_function=shutil.copy2)
        else:
            shutil.copy2(src, dst, follow_symlinks=False)

    def _remove_existing_destination(self, dst: str) -> None:
        """Remove an existing destination before a directory/symlink overwrite."""
        if os.path.isdir(dst) and not os.path.islink(dst):
            shutil.rmtree(dst)
        else:
            os.remove(dst)

    def _finish_cut_clipboard(self, original_items):
        """Keep only still-existing sources after a cut operation.

        This makes partial cut/move failures less confusing. Successfully moved
        items disappear from the clipboard; items that were skipped or failed
        stay available for a later retry.
        """
        remaining = [path for path in original_items if os.path.exists(path)]
        if remaining:
            self.clipboard = ("cut", remaining)
            self.paste_button.setEnabled(True)
        else:
            self.clipboard = None
            self.paste_button.setEnabled(False)

    def pasteFileOrFolder(self, dest_dir):
        if not self.clipboard:
            return

        dest_dir = os.path.abspath(os.path.expanduser(dest_dir))
        if not os.path.isdir(dest_dir):
            QMessageBox.warning(self, "Paste", f"Destination is not a folder:\n{dest_dir}")
            return

        op, items = self.clipboard
        items = self._as_paths(items)
        if not items:
            if op == "cut":
                self.clipboard = None
                self.paste_button.setEnabled(False)
            return

        op_name = "move" if op == "cut" else "copy"
        msg = (
            f"Are you sure you want to {op_name} "
            f"{len(items)} {'item' if len(items) == 1 else 'items'} "
            f"to:\n{dest_dir} ?"
        )
        reply = QMessageBox.question(
            self,
            "Confirm Paste",
            msg,
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No,
        )
        if reply != QMessageBox.Yes:
            return

        overwrite_all = False
        skip_all = False
        skipped = []
        skipped_same = []
        errors = []

        for src in items:
            if not os.path.exists(src):
                errors.append(f"{src}: source no longer exists.")
                continue

            name = os.path.basename(src.rstrip(os.sep))
            dst = os.path.join(dest_dir, name)
            is_dir = os.path.isdir(src) and not os.path.islink(src)

            # Prevent paste-into-self / paste-into-descendant for directories.
            if is_dir and (self._same_or_subpath(dest_dir, src) or self._same_or_subpath(dst, src)):
                errors.append(f"{src}: cannot {op_name} a folder into itself or one of its subfolders.")
                continue

            same = False
            try:
                if os.path.exists(dst):
                    same = os.path.samefile(src, dst)
            except Exception:
                same = os.path.abspath(src) == os.path.abspath(dst)

            if same:
                skipped_same.append(dst)
                continue

            if os.path.exists(dst):
                if skip_all:
                    skipped.append(dst)
                    continue

                if not overwrite_all:
                    choice = self._prompt_overwrite(dst, is_dir)
                    if choice == "cancel":
                        if op == "cut":
                            self._finish_cut_clipboard(items)
                        self._show_paste_summary(skipped_same, skipped, errors)
                        return
                    if choice == "no":
                        skipped.append(dst)
                        continue
                    if choice == "no_all":
                        skip_all = True
                        skipped.append(dst)
                        continue
                    if choice == "yes_all":
                        overwrite_all = True

            try:
                if op == "copy":
                    if os.path.exists(dst):
                        # QFileSystemModel paths can legally collide with an
                        # existing directory, symlink, or other non-regular
                        # destination. Remove those first so copy2/copytree do
                        # not reinterpret the target path unexpectedly.
                        if is_dir or os.path.islink(src) or os.path.isdir(dst) or os.path.islink(dst):
                            self._remove_existing_destination(dst)
                        # For regular file-to-file copies, copy2 can overwrite
                        # in place without a pre-delete.
                    self._copy_entry(src, dst)
                else:
                    # Prefer atomic replace for simple file-to-file moves on the
                    # same filesystem; fall back to shutil.move otherwise.
                    if os.path.exists(dst):
                        if not is_dir and not os.path.islink(src) and not os.path.isdir(dst):
                            try:
                                os.replace(src, dst)
                                continue
                            except Exception:
                                self._remove_existing_destination(dst)
                        else:
                            self._remove_existing_destination(dst)

                    shutil.move(src, dst)
                    if os.path.isdir(dst):
                        self._retarget_open_tabs(src, dst)
            except Exception as exc:
                errors.append(f"{src} -> {dst}: {exc}")

        if op == "cut":
            self._finish_cut_clipboard(items)

        self._show_paste_summary(skipped_same, skipped, errors)
        self.refreshCurrentTab()

    def _show_paste_summary(self, skipped_same, skipped, errors) -> None:
        """Show a compact summary after paste/copy/move operations."""
        parts = []
        if skipped_same:
            parts.append(
                f"Skipped {len(skipped_same)} identical-location "
                f"{'item' if len(skipped_same) == 1 else 'items'} (same folder and name)."
            )
        if skipped:
            parts.append(
                f"Skipped {len(skipped)} existing "
                f"{'item' if len(skipped) == 1 else 'items'}."
            )
        if errors:
            parts.append(f"{len(errors)} errors occurred during the operation.")

        if parts:
            QMessageBox.information(self, "Paste Summary", "\n".join(parts))

    # ------------------------------------------------------------------
    # Open With...
    # ------------------------------------------------------------------
    def open_with(self, indexes):
        """Prompt for a program and open selected file(s) with it."""
        import shlex
        from qt_compat import QSettings

        if not indexes:
            return

        file_paths = []
        seen = set()
        for index in indexes:
            path = self._path_from_index(index)
            if not path or os.path.isdir(path) or path in seen:
                continue
            seen.add(path)
            file_paths.append(path)

        if not file_paths:
            QMessageBox.warning(self, "Open With...", "Please select at least one file (not a folder).")
            return

        settings = QSettings(SETTINGS_ORG, SETTINGS_APP)
        last_program = settings.value("open_with/last_program", "")

        try:
            program_text, ok = QInputDialog.getText(
                self,
                "Open With...",
                "Type the command for the program (you can include arguments):",
                text=last_program,
            )
        except TypeError:
            program_text, ok = QInputDialog.getText(
                self,
                "Open With...",
                "Type the command for the program (you can include arguments):",
            )

        if not ok or not program_text.strip():
            return

        try:
            tokens = shlex.split(program_text.strip())
            if not tokens:
                QMessageBox.warning(self, "Open With...", "No program specified.")
                return

            executable = tokens[0]
            if not os.path.isabs(executable) and os.sep not in executable:
                resolved = shutil.which(executable)
                if not resolved:
                    QMessageBox.warning(self, "Open With...", f"Program not found in PATH: {executable}")
                    return
                tokens[0] = resolved
        except Exception as exc:
            QMessageBox.warning(self, "Open With...", f"Invalid command:\n{exc}")
            return

        settings.setValue("open_with/last_program", program_text.strip())

        try:
            subprocess.Popen(tokens + file_paths, start_new_session=True, close_fds=True)
        except Exception as exc:
            QMessageBox.warning(self, "Open With...", f"Failed to launch:\n{exc}")

    # ------------------------------------------------------------------
    # Hidden files toggle (used by MainWindow)
    # ------------------------------------------------------------------
    def update_hidden_files(self, show_hidden: bool):
        """Show or hide hidden files across all tabs."""
        self.show_hidden_files = bool(show_hidden)
        self._apply_hidden_filter_to_model(self.fs_model)

        for i in range(self.tab_widget.count()):
            view = self.tab_widget.widget(i)
            if view is not None:
                self.refreshView(view)
