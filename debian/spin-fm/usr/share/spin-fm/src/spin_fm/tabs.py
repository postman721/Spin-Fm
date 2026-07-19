#!/usr/bin/env python3
"""Tabbed file browser and filesystem interaction layer for Spin FM."""

from __future__ import annotations

import os
from collections import deque
from urllib.parse import unquote, urlparse

from .audio import is_supported_audio_file
from .config import SETTINGS_APPLICATION, SETTINGS_ORGANIZATION
from .dialogs import TrashLocation, TrashLocationDialog
from .file_ops import (
    OperationReport,
    TransferItem,
    ensure_trash_directories,
    execute_transfer,
    is_path_in_trash,
    mounted_trash_directories,
    resolved_same_or_subpath,
    trash_mount_point,
    trash_paths,
)
from .launch import launch_default, launch_paths
from .qt_compat import (
    QAbstractItemView,
    QAction,
    QApplication,
    QDir,
    QFileSystemModel,
    QIcon,
    QInputDialog,
    QLineEdit,
    QListView,
    QMenu,
    QMessageBox,
    QSettings,
    QRect,
    QSize,
    QSizePolicy,
    QStyle,
    QStyledItemDelegate,
    QStyleOptionViewItem,
    Qt,
    QTabBar,
    QTabWidget,
    QTimer,
    QToolBar,
    QToolButton,
    QVBoxLayout,
    QWidget,
    pyqtSignal,
)
from .workers import TaskManager


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
        action = (
            context_menu.exec(pos)
            if hasattr(context_menu, "exec")
            else context_menu.exec_(pos)
        )

        if action == new_action:
            self.newTabRequested.emit()
        elif duplicate_action is not None and action == duplicate_action:
            self.duplicateTabRequested.emit(tab_index)
        elif close_action is not None and action == close_action:
            self.closeTabRequested.emit(tab_index)


class FullNameIconDelegate(QStyledItemDelegate):
    """Give wrapped icon labels enough height to show the complete name."""

    HORIZONTAL_PADDING = 18
    VERTICAL_PADDING = 18
    ICON_TEXT_GAP = 8
    MINIMUM_HEIGHT = 112

    def __init__(self, item_width: int, icon_height: int, parent=None) -> None:
        super().__init__(parent)
        self.item_width = max(112, int(item_width))
        self.icon_height = max(32, int(icon_height))

    def initStyleOption(self, option, index) -> None:  # noqa: N802 - Qt API
        super().initStyleOption(option, index)
        try:
            option.textElideMode = Qt.ElideNone
            option.displayAlignment = Qt.AlignHCenter | Qt.AlignTop
            option.decorationAlignment = Qt.AlignHCenter
            option.decorationPosition = QStyleOptionViewItem.Top
            option.features |= QStyleOptionViewItem.WrapText
        except Exception:
            pass

    def sizeHint(self, option, index):  # noqa: N802 - Qt API
        try:
            prepared = QStyleOptionViewItem(option)
        except Exception:
            prepared = option
        self.initStyleOption(prepared, index)
        try:
            text = str(index.data(Qt.DisplayRole) or "")
        except Exception:
            text = ""

        text_width = max(72, self.item_width - self.HORIZONTAL_PADDING * 2)
        flags = Qt.AlignHCenter | Qt.AlignTop | Qt.TextWordWrap | Qt.TextWrapAnywhere
        try:
            bounds = prepared.fontMetrics.boundingRect(
                QRect(0, 0, text_width, 100_000), flags, text
            )
            text_height = max(prepared.fontMetrics.height(), bounds.height())
        except Exception:
            text_height = prepared.fontMetrics.height()

        height = (
            self.VERTICAL_PADDING
            + self.icon_height
            + self.ICON_TEXT_GAP
            + text_height
        )
        return QSize(self.item_width, max(self.MINIMUM_HEIGHT, height))


class FileIconListView(QListView):
    """Icon view with resize-friendly layout and file drag-and-drop support."""

    def __init__(self, tabs_widget=None, parent=None):
        super().__init__(parent)
        self.tabs_widget = tabs_widget

    def resizeEvent(self, event):  # noqa: N802 - Qt API name
        super().resizeEvent(event)
        try:
            self.scheduleDelayedItemsLayout()
        except Exception:
            pass

    def _event_position(self, event):
        """Return the event position for PyQt5 and PyQt6 drop events."""
        try:
            return event.position().toPoint()
        except Exception:
            try:
                return event.pos()
            except Exception:
                return None

    def _local_paths_from_mime_data(self, mime_data):
        """Extract local filesystem paths from a drag payload."""
        if mime_data is None or not mime_data.hasUrls():
            return []

        paths = []
        for url in mime_data.urls():
            try:
                local_path = url.toLocalFile()
            except Exception:
                local_path = ""
            if local_path:
                paths.append(local_path)
        return paths

    def _drop_destination_directory(self, event):
        """Return the folder that dropped items should be copied/moved into."""
        if self.tabs_widget is None:
            return ""

        position = self._event_position(event)
        clicked_path = ""
        if position is not None:
            try:
                clicked_path = self.tabs_widget._path_from_index(self.indexAt(position))
            except Exception:
                clicked_path = ""

        if clicked_path and os.path.isdir(clicked_path):
            return clicked_path
        return self.tabs_widget.currentPath(self)

    @staticmethod
    def _accept_manual_move_drop(event) -> None:
        """Accept as CopyAction because Spin FM performs the move itself."""
        copy_action = getattr(Qt, "CopyAction", None)
        if copy_action is not None:
            try:
                event.setDropAction(copy_action)
                event.accept()
                return
            except Exception:
                pass
        event.acceptProposedAction()

    def dragEnterEvent(self, event):  # noqa: N802 - Qt API name
        if self._local_paths_from_mime_data(event.mimeData()):
            self._accept_manual_move_drop(event)
            return
        super().dragEnterEvent(event)

    def dragMoveEvent(self, event):  # noqa: N802 - Qt API name
        if self._local_paths_from_mime_data(event.mimeData()):
            self._accept_manual_move_drop(event)
            return
        super().dragMoveEvent(event)

    def dropEvent(self, event):  # noqa: N802 - Qt API name
        paths = self._local_paths_from_mime_data(event.mimeData())
        if not paths or self.tabs_widget is None:
            super().dropEvent(event)
            return

        destination = self._drop_destination_directory(event)
        handled = self.tabs_widget.dropFileOrFolder(paths, destination)
        if handled:
            self._accept_manual_move_drop(event)
        else:
            event.ignore()


class Tabs(QWidget):
    """Main tabbed file-manager widget.

    A single QFileSystemModel instance is shared by every tab. QFileSystemModel
    already caches directory data internally, so sharing it keeps the UI lighter
    than creating a fresh model per tab.
    """

    status_message = pyqtSignal(str)
    operation_started = pyqtSignal(str, int)
    operation_progress = pyqtSignal(int, int, str)
    operation_finished = pyqtSignal(str)
    audio_requested = pyqtSignal(str)

    MAX_HISTORY_ITEMS = 100

    def __init__(self, parent=None):
        super().__init__(parent)

        # Clipboard state: None or ("cut" | "copy", [absolute_paths]).
        self.clipboard = None
        self.file_tasks = TaskManager(self, max_threads=1)
        self._file_operation_active = False
        self._external_operation_busy = False

        # History is keyed by the view object itself rather than by the current
        # tab index. That avoids stale/shifted history when tabs are closed.
        self.history = {}

        # The hidden-files flag is owned by Tabs so newly created tabs inherit
        # the current setting immediately.
        self.show_hidden_files = False
        self.home_path = self._default_home_path()
        self.file_icon_size = QSize(64, 64)
        self.file_item_width = 148
        self.file_item_spacing = 10

        self.layout = QVBoxLayout(self)
        self.layout.setContentsMargins(12, 12, 12, 12)
        self.layout.setSpacing(8)

        # Shared file-system model: this is the main memory-usage improvement.
        self.fs_model = self._create_shared_model()

        # Toolbar.
        self.toolbar = QToolBar(self)
        self.toolbar.setObjectName("fileToolbar")
        self.toolbar.setIconSize(QSize(22, 22))
        self.toolbar.setMovable(False)
        self.toolbar.setFloatable(False)
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

        self.up_button = QToolButton()
        self.up_button.setIcon(self._theme_icon("go-up", QStyle.SP_ArrowUp))
        self.up_button.setToolTip("Up (Ctrl+Up)")
        self.up_button.clicked.connect(self.goUp)
        self.toolbar.addWidget(self.up_button)

        self.home_button = QToolButton()
        self.home_button.setIcon(self.style().standardIcon(QStyle.SP_DirHomeIcon))
        self.home_button.setToolTip("Home")
        self.home_button.clicked.connect(self.goHome)
        self.toolbar.addWidget(self.home_button)
        self.toolbar.addSeparator()

        self.new_tab_button = QToolButton()
        self.new_tab_button.setIcon(
            self._theme_icon("tab-new", QStyle.SP_FileDialogNewFolder)
        )
        self.new_tab_button.setToolTip("New Tab (Ctrl+T)")
        self.new_tab_button.clicked.connect(
            lambda: self.createNewTab(self.currentPath())
        )
        self.toolbar.addWidget(self.new_tab_button)

        self.refresh_button = QToolButton()
        self.refresh_button.setIcon(
            self._theme_icon("view-refresh", QStyle.SP_BrowserReload)
        )
        self.refresh_button.setToolTip("Refresh (F5)")
        self.refresh_button.clicked.connect(self.refreshCurrentTab)
        self.toolbar.addWidget(self.refresh_button)

        self.trash_button = QToolButton()
        self.trash_button.setIcon(self.style().standardIcon(QStyle.SP_TrashIcon))
        self.trash_button.setToolTip("Open Trash")
        self.trash_button.clicked.connect(self.goTrash)
        self.toolbar.addWidget(self.trash_button)
        self.toolbar.addSeparator()

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
        self.paste_button.setIcon(
            self._theme_icon("edit-paste", QStyle.SP_FileDialogNewFolder)
        )
        self.paste_button.setToolTip("Paste (Ctrl+V)")
        self.paste_button.clicked.connect(self.pasteToCurrentFolder)
        self.paste_button.setEnabled(False)
        self.toolbar.addWidget(self.paste_button)

        self._update_toolbar_icons()

        self.address_bar = QLineEdit(self)
        self.address_bar.setObjectName("locationBar")
        self.address_bar.setPlaceholderText("Type a folder path and press Enter")
        self.address_bar.setClearButtonEnabled(True)
        self.address_bar.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        self.address_bar.returnPressed.connect(self.navigateToPath)
        self.toolbar.addWidget(self.address_bar)

        self.tab_widget = QTabWidget(self)
        self.tab_widget.setObjectName("fileTabs")
        self.tab_widget.setDocumentMode(True)
        self.tab_widget.setMovable(True)
        self.tab_widget.setUsesScrollButtons(True)
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

    def _update_toolbar_icons(self) -> None:
        """Re-read all toolbar icons from the active icon theme."""
        themed_buttons = (
            ("back_button", "go-previous", QStyle.SP_ArrowBack),
            ("forward_button", "go-next", QStyle.SP_ArrowForward),
            ("up_button", "go-up", QStyle.SP_ArrowUp),
            ("home_button", "go-home", QStyle.SP_DirHomeIcon),
            ("new_tab_button", "tab-new", QStyle.SP_FileDialogNewFolder),
            ("refresh_button", "view-refresh", QStyle.SP_BrowserReload),
            ("trash_button", "user-trash", QStyle.SP_TrashIcon),
            ("cut_button", "edit-cut", QStyle.SP_FileIcon),
            ("copy_button", "edit-copy", QStyle.SP_FileIcon),
            ("paste_button", "edit-paste", QStyle.SP_FileDialogNewFolder),
        )
        for attr, icon_name, fallback in themed_buttons:
            button = getattr(self, attr, None)
            if button is not None:
                button.setIcon(self._theme_icon(icon_name, fallback))

    def _configure_icon_view(self, view: QListView) -> None:
        """Apply a responsive, smoothly scrolling icon layout."""
        view.setObjectName("fileIconView")
        view.setViewMode(QListView.IconMode)
        view.setIconSize(self.file_icon_size)
        view.setMouseTracking(True)
        try:
            view.setVerticalScrollMode(QAbstractItemView.ScrollPerPixel)
            view.setHorizontalScrollMode(QAbstractItemView.ScrollPerPixel)
        except Exception:
            pass

        # These options are the core of the resize fix: items flow from left to
        # right, wrap to the next row, and relayout whenever the viewport width
        # changes instead of staying in a stale single-column arrangement.
        for setter, value in (
            ("setFlow", getattr(QListView, "LeftToRight", None)),
            ("setResizeMode", getattr(QListView, "Adjust", None)),
            ("setMovement", getattr(QListView, "Static", None)),
        ):
            if value is None:
                continue
            try:
                getattr(view, setter)(value)
            except Exception:
                pass

        # A fixed grid forces Qt to shorten long names. Let the delegate choose
        # a per-item height so complete file and folder names can wrap naturally.
        for setter, value in (
            ("setWrapping", True),
            ("setUniformItemSizes", False),
            ("setWordWrap", True),
            ("setGridSize", QSize()),
            ("setSpacing", self.file_item_spacing),
        ):
            try:
                getattr(view, setter)(value)
            except Exception:
                pass

        try:
            view.setTextElideMode(Qt.ElideNone)
            view.setItemDelegate(
                FullNameIconDelegate(
                    self.file_item_width,
                    self.file_icon_size.height(),
                    view,
                )
            )
        except Exception:
            pass

        # Renaming is an explicit context-menu action. Disabling implicit edit
        # triggers prevents a double-click from being consumed by an inline
        # editor instead of opening the item.
        try:
            view.setEditTriggers(QAbstractItemView.NoEditTriggers)
        except Exception:
            pass

        # Enable outgoing drags and incoming local-file drops. The custom drop
        # handler performs a confirmed move with the same overwrite and containment
        # checks used by Cut/Paste.
        for setter, value in (
            ("setDragEnabled", True),
            ("setAcceptDrops", True),
            ("setDropIndicatorShown", True),
        ):
            try:
                getattr(view, setter)(value)
            except Exception:
                pass

        try:
            view.viewport().setAcceptDrops(True)
        except Exception:
            pass

        drag_drop_mode = getattr(QAbstractItemView, "DragDrop", None)
        if drag_drop_mode is not None:
            try:
                view.setDragDropMode(drag_drop_mode)
            except Exception:
                pass

        # Report CopyAction back to the drag source because Spin FM performs the
        # confirmed move itself asynchronously. This prevents a source application
        # from deleting the same path a second time after the drop returns.
        default_drop_action = getattr(Qt, "CopyAction", None)
        if default_drop_action is not None:
            try:
                view.setDefaultDropAction(default_drop_action)
            except Exception:
                pass

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

        # Keep one stable model root. Repeatedly changing QFileSystemModel's root
        # can retain extra directory watchers and cached branches after long
        # browsing sessions. Views are rooted with model.index(path) instead.
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
        button.clicked.connect(
            lambda _checked=False, b=button: self.closeTab(
                self._tab_index_for_close_button(b)
            )
        )

        self.tab_widget.tabBar().setTabButton(
            tab_index, self._tab_button_side(), button
        )

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
        """Return a valid shared-model index for an existing directory.

        QFileSystemModel may not have indexed hidden ancestor directories yet.
        This is common for the freedesktop Trash path under ``~/.local``.  Prime
        the requested directory explicitly when the first lookup is invalid so
        toolbar navigation cannot silently do nothing.
        """
        target = self._normalize_existing_directory(path)
        try:
            index = self.fs_model.index(target)
            if index is not None and index.isValid():
                return index
        except Exception:
            index = None

        try:
            index = self.fs_model.setRootPath(target)
            if index is not None and index.isValid():
                return index
        except Exception:
            pass
        return None

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

        fallback = (
            self.currentPath() if self.currentView() is not None else self.home_path
        )
        fallback = os.path.abspath(os.path.expanduser(fallback))
        return fallback if os.path.isdir(fallback) else self.home_path

    def _history_for_view(self, view) -> dict:
        """Return the history bucket for a given view."""
        return self.history.setdefault(
            view,
            {
                "back": deque(maxlen=self.MAX_HISTORY_ITEMS),
                "forward": deque(maxlen=self.MAX_HISTORY_ITEMS),
            },
        )

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
            view._spinfm_current_path = target

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
        hist = (
            self._history_for_view(view)
            if view is not None
            else {"back": [], "forward": []}
        )
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

    def _retarget_open_tabs(self, old_path: str, new_path: str | None) -> None:
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
                suffix = current[len(old_path) :]
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

        view = FileIconListView(self, self.tab_widget)
        view.setModel(self.fs_model)
        view.setRootIndex(self._model_index_for_directory(path))
        try:
            view.setProperty("current_path", path)
        except Exception:
            view._spinfm_current_path = path
        self._configure_icon_view(view)

        # Batched layout keeps large folders responsive.
        try:
            view.setLayoutMode(QListView.Batched)
            view.setBatchSize(128)
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
        view.customContextMenuRequested.connect(
            lambda pos, v=view: self.openFileContextMenu(pos, v)
        )
        # ``activated`` follows the desktop style hint and can fire on a single
        # click. Use the unambiguous double-click signal and explicit keyboard
        # actions so selection never starts playback or opens a folder.
        view.doubleClicked.connect(lambda idx, v=view: self.onFileActivated(idx, v))
        self._connect_selection_model(view)

        self._install_shortcuts(view)

        tab_index = self.tab_widget.addTab(view, self._display_name_for_path(path))
        self.tab_widget.setTabToolTip(tab_index, path)
        self._install_tab_close_button(tab_index)
        self.history[view] = {
            "back": deque(maxlen=self.MAX_HISTORY_ITEMS),
            "forward": deque(maxlen=self.MAX_HISTORY_ITEMS),
        }

        self.tab_widget.setCurrentWidget(view)
        self._sync_current_view_ui()
        return tab_index

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
        _bind("Open", "Return", lambda v=view: self._activate_current_item(v))
        _bind("Open", "Enter", lambda v=view: self._activate_current_item(v))
        _bind("Refresh", "F5", self.refreshCurrentTab)
        _bind("Refresh", "Ctrl+R", self.refreshCurrentTab)
        _bind("Up", "Ctrl+Up", self.goUp)
        _bind(
            "Close Tab", "Ctrl+W", lambda: self.closeTab(self.tab_widget.currentIndex())
        )
        _bind("Focus Location", "Ctrl+L", self.focusLocationBar)

        select_all = QAction("Select All", view)
        select_all.setShortcut("Ctrl+A")
        try:
            select_all.setShortcutContext(Qt.WidgetWithChildrenShortcut)
        except Exception:
            pass
        select_all.triggered.connect(view.selectAll)
        view.addAction(select_all)

    def _activate_current_item(self, view) -> None:
        """Open the current item from Return/Enter without style-dependent signals."""
        if view is None:
            return
        try:
            index = view.currentIndex()
            if index is None or not index.isValid():
                selected = view.selectionModel().selectedIndexes()
                index = selected[0] if selected else None
        except Exception:
            index = None
        if index is not None:
            self.onFileActivated(index, view)

    def _selection_changed(self, view) -> None:
        if view is not self.currentView() or self.is_busy:
            return
        count = len(self.selectedPaths(view))
        if count:
            self.status_message.emit(
                f"{count} {'item' if count == 1 else 'items'} selected"
            )

    def _connect_selection_model(self, view) -> None:
        """Reconnect selection feedback after a QFileSystemModel replacement."""
        try:
            view.selectionModel().selectionChanged.connect(
                lambda *_args, v=view: self._selection_changed(v)
            )
        except Exception:
            pass

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
    def focusLocationBar(self):
        self.address_bar.setFocus()
        self.address_bar.selectAll()

    def cutSelection(self):
        paths = self.selectedPaths()
        if not paths:
            self.status_message.emit("Select one or more items to cut")
            return
        self._set_file_clipboard("cut", paths)

    def copySelection(self):
        paths = self.selectedPaths()
        if not paths:
            self.status_message.emit("Select one or more items to copy")
            return
        self._set_file_clipboard("copy", paths)

    def copyPathsToClipboard(self, paths):
        items = self._as_paths(paths)
        if not items:
            return
        clipboard = QApplication.clipboard()
        if clipboard is not None:
            clipboard.setText("\n".join(items))

    def pasteToCurrentFolder(self):
        self._paste_clipboard_to(self.currentPath())

    def deleteSelection(self):
        paths = self.selectedPaths()
        if not paths:
            self.status_message.emit(
                "Select one or more items to delete or move to Trash"
            )
            return
        self._confirm_delete(paths)

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

    def goUp(self):
        current = self.currentPath()
        parent = os.path.dirname(current.rstrip(os.sep)) or current
        if parent and parent != current and os.path.isdir(parent):
            self._navigateTo(parent)

    def goTrash(self):
        """Open Home Trash directly or show a readable mounted-Trash chooser."""
        try:
            home_trash = ensure_trash_directories()
            mounted = mounted_trash_directories()
        except OSError as exc:
            QMessageBox.warning(self, "Trash", f"Could not open Trash:\n{exc}")
            return

        home_real = os.path.realpath(home_trash)
        locations = [
            TrashLocation(
                name="Home Trash",
                path=home_trash,
                detail="User profile",
            )
        ]
        for path in mounted:
            if os.path.realpath(path) == home_real:
                continue
            mount_point = trash_mount_point(path)
            if not mount_point:
                continue
            device_name = os.path.basename(mount_point.rstrip(os.sep)) or mount_point
            locations.append(
                TrashLocation(
                    name=f"{device_name} Trash",
                    path=path,
                    detail=f"Mounted filesystem: {mount_point}",
                    removable=True,
                )
            )

        if len(locations) == 1:
            self._navigateTo(home_trash)
            return

        selected_path = TrashLocationDialog.choose(self, locations)
        if selected_path:
            self._navigateTo(selected_path)

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
            QMessageBox.warning(
                self, "Not Found", f"Directory does not exist:\n{target}"
            )
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
        return launch_default(path)

    def _request_audio_playback(self, path: str) -> bool:
        """Emit an embedded-player request for recognized audio files."""
        if not is_supported_audio_file(path):
            return False
        self.audio_requested.emit(path)
        return True

    def _open_file_path(self, path: str, *, externally: bool = False) -> None:
        """Open one file internally when possible, otherwise through the desktop."""
        if not externally and self._request_audio_playback(path):
            return
        self._launch_default_application(path)

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
                        self._open_file_path(path)
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
                            self._open_file_path(path)
                        except Exception as exc:
                            errors.append(f"{path}: {exc}")

        if errors:
            QMessageBox.warning(
                self,
                "Open Error",
                "Some items could not be opened:\n\n" + "\n".join(errors),
            )

    def _path_from_user_argument(self, argument: str) -> str | None:
        """Resolve a command-line path/URI to an existing local path."""
        if argument is None:
            return None

        value = str(argument).strip().strip("\0")
        if not value:
            return None

        # Desktop launchers and browsers commonly pass file:// URIs to file
        # managers. Convert them back to local filesystem paths, preserving
        # spaces and non-ASCII characters.
        if value.lower().startswith("file:"):
            parsed = urlparse(value)
            if parsed.scheme.lower() != "file":
                return None
            if parsed.netloc and parsed.netloc not in {"", "localhost"}:
                raw_path = f"//{parsed.netloc}{parsed.path}"
            else:
                raw_path = parsed.path
            candidates = [unquote(raw_path)]
        else:
            expanded = os.path.expandvars(unquote(value))
            candidates = [expanded]

            # Relative arguments are resolved from the current process directory
            # first, then from the user's home. The home fallback lets commands
            # such as `spin-fm Downloads` land on ~/Downloads even when the app
            # was started by a launcher with an arbitrary working directory.
            if not os.path.isabs(expanded):
                candidates.append(os.path.join(os.getcwd(), expanded))
                candidates.append(os.path.join(self.home_path, expanded))

        # Common convenience aliases for browser/download workflows.
        lowered = value.strip().lower()
        if lowered in {"download", "downloads", "download folder", "downloads folder"}:
            candidates.append(os.path.join(self.home_path, "Downloads"))

        for candidate in candidates:
            if not candidate:
                continue
            path = os.path.abspath(os.path.expanduser(candidate))
            if os.path.exists(path):
                return path
        return None

    def _paths_from_user_arguments(self, arguments):
        """Resolve command-line arguments, including unquoted paths with spaces."""
        raw_args = [str(arg) for arg in (arguments or []) if str(arg).strip()]
        paths = []
        errors = []
        seen = set()
        index = 0

        while index < len(raw_args):
            matched_path = None
            matched_end = index + 1

            # Be forgiving when a path containing spaces was appended to the
            # command without quotes. Prefer the longest existing reconstruction.
            for end in range(len(raw_args), index, -1):
                candidate = " ".join(raw_args[index:end])
                path = self._path_from_user_argument(candidate)
                if path:
                    matched_path = path
                    matched_end = end
                    break

            if matched_path:
                if matched_path not in seen:
                    seen.add(matched_path)
                    paths.append(matched_path)
                index = matched_end
                continue

            errors.append(raw_args[index])
            index += 1

        return paths, errors

    def _select_path_in_view(self, view, path: str) -> None:
        """Make a file argument visible after opening its parent folder."""
        if view is None or not path:
            return
        try:
            index = self.fs_model.index(path)
            if index is None or not index.isValid():
                return
            view.setCurrentIndex(index)
            try:
                view.scrollTo(index)
            except Exception:
                pass
        except Exception:
            pass

    def openStartupPaths(self, arguments) -> None:
        """Open file/folder arguments supplied after the Spin FM command."""
        paths, errors = self._paths_from_user_arguments(arguments)
        if not paths and not errors:
            return

        first = True
        for path in paths:
            if os.path.isdir(path):
                folder = path
                selected_file = None
            else:
                folder = os.path.dirname(path)
                selected_file = path

            if first:
                view = self.currentView()
                self._navigateTo(folder, push=False, view=view)
                first = False
            else:
                self.createNewTab(folder)
                view = self.currentView()

            if selected_file:
                QTimer.singleShot(
                    250, lambda v=view, p=selected_file: self._select_path_in_view(v, p)
                )

        if errors:
            QMessageBox.warning(
                self,
                "Open Path",
                "Some command-line paths could not be found:\n\n" + "\n".join(errors),
            )

    def onFileActivated(self, index, file_view=None):
        file_view = file_view or self.currentView()
        path = self._path_from_index(index)
        if not path:
            return
        if os.path.isdir(path):
            self._navigateTo(path, view=file_view)
        else:
            self._open_indexes([index])

    def _open_indexes(self, selected_indexes):
        """Open files internally when supported, otherwise via the desktop.

        If a desktop launch fails, the user is given the chance to choose a
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
                self._open_file_path(path)
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
        open_external_action = None
        open_new_tab_action = None
        rename_action = None
        open_with_action = None
        delete_action = None
        cut_action = None
        copy_action = None
        copy_path_action = None
        paste_action = None
        new_file_action = None
        new_folder_action = None
        refresh_action = None

        if target_paths:
            if len(target_paths) == 1:
                target = target_paths[0]
                audio_target = os.path.isfile(target) and is_supported_audio_file(
                    target
                )
                open_action = context_menu.addAction(
                    "Play in Spin FM" if audio_target else "Open"
                )
                if audio_target:
                    open_external_action = context_menu.addAction("Open Externally")
                if os.path.isdir(target):
                    open_new_tab_action = context_menu.addAction("Open in New Tab")
                rename_action = context_menu.addAction("Rename")

            delete_label = (
                "Delete Permanently"
                if all(is_path_in_trash(path) for path in target_paths)
                else "Move to Trash"
            )
            delete_action = context_menu.addAction(delete_label)
            cut_action = context_menu.addAction("Cut")
            copy_action = context_menu.addAction("Copy")
            copy_path_action = context_menu.addAction("Copy Path")

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
        chosen = (
            context_menu.exec(pos)
            if hasattr(context_menu, "exec")
            else context_menu.exec_(pos)
        )

        if chosen == open_action:
            self._open_paths(target_paths)
        elif chosen == open_external_action:
            try:
                self._open_file_path(target_paths[0], externally=True)
            except Exception as exc:
                QMessageBox.warning(self, "Open Error", f"Could not open file:\n{exc}")
        elif chosen == open_new_tab_action:
            self._open_paths(target_paths, new_tab=True)
        elif chosen == rename_action:
            self.renameFileOrFolder(target_paths[0], file_view)
        elif chosen == delete_action:
            self._confirm_delete(target_paths)
        elif chosen == cut_action:
            self._set_file_clipboard("cut", target_paths)
        elif chosen == copy_action:
            self._set_file_clipboard("copy", target_paths)
        elif chosen == copy_path_action:
            self.copyPathsToClipboard(target_paths)
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
            self._paste_clipboard_to(self.currentPath(file_view))
        elif chosen == new_file_action:
            self.createNewTextFile()
        elif chosen == new_folder_action:
            self.createNewFolder()
        elif chosen == refresh_action:
            self.refreshView(file_view)

    # ------------------------------------------------------------------
    # Name validation helpers
    # ------------------------------------------------------------------
    def _validate_child_name(self, name: str, title: str) -> str | None:
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
        if self.is_busy:
            self.status_message.emit("Wait for the current operation to finish")
            return
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
        if self.is_busy:
            self.status_message.emit("Wait for the current operation to finish")
            return
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
        if self.is_busy:
            self.status_message.emit("Wait for the current operation to finish")
            return
        if isinstance(paths, (list, tuple)):
            if len(paths) != 1:
                QMessageBox.information(
                    self, "Rename", "Please select a single item to rename."
                )
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
            new_name, ok = QInputDialog.getText(
                self, "Rename", "New name:", text=old_name
            )
        except TypeError:
            new_name, ok = QInputDialog.getText(self, "Rename", "New name:")

        if not ok:
            return

        new_name = self._validate_child_name(new_name, "Rename")
        if not new_name or new_name == old_name:
            return

        new_path = os.path.join(parent, new_name)
        if os.path.exists(new_path):
            QMessageBox.warning(
                self, "Rename", f"An item with that name already exists:\n{new_path}"
            )
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

    @property
    def is_busy(self) -> bool:
        return (
            self._external_operation_busy
            or self._file_operation_active
            or self.file_tasks.is_busy
        )

    def set_external_operation_busy(self, busy: bool) -> None:
        """Block destructive tab operations while an app-level task runs."""
        self._external_operation_busy = bool(busy)
        self.paste_button.setEnabled(self.clipboard is not None and not self.is_busy)

    def shutdown(self) -> None:
        """Release queued worker resources during a clean application exit."""
        self.file_tasks.shutdown(wait_msec=1_000)

    def _begin_file_operation(self, label: str, total: int) -> bool:
        if self.is_busy:
            self.status_message.emit("Another file operation is already running")
            return False
        self._file_operation_active = True
        self.paste_button.setEnabled(False)
        self.operation_started.emit(label, total)
        return True

    def _release_file_operation(self) -> None:
        self._file_operation_active = False
        self.paste_button.setEnabled(self.clipboard is not None and not self.is_busy)

    def _file_operation_progress(self, payload, verb: str) -> None:
        current, total, name = payload
        self.operation_progress.emit(current, total, f"{verb} {name}…")

    def _show_report_errors(self, title: str, report: OperationReport) -> None:
        if not report.error_count:
            return
        details = "\n".join(report.details)
        hidden = report.error_count - len(report.details)
        if hidden > 0:
            details += f"\n…and {hidden} more errors."
        QMessageBox.warning(
            self,
            title,
            f"{report.error_count} item(s) could not be processed.\n\n{details}",
        )

    def _confirm_delete(self, paths):
        if self.is_busy:
            self.status_message.emit("Wait for the current operation to finish")
            return
        targets = self._as_paths(paths)
        if not targets:
            return

        permanent = all(is_path_in_trash(path) for path in targets)
        title = "Confirm Permanent Delete" if permanent else "Move to Trash"
        if permanent:
            message = (
                "Permanently delete the selected item?"
                if len(targets) == 1
                else f"Permanently delete {len(targets)} selected items?"
            )
        else:
            message = (
                "Move the selected item to Trash?"
                if len(targets) == 1
                else f"Move {len(targets)} selected items to Trash?"
            )

        if (
            QMessageBox.question(
                self,
                title,
                message,
                QMessageBox.Yes | QMessageBox.No,
                QMessageBox.No,
            )
            != QMessageBox.Yes
        ):
            return

        label = "Deleting items…" if permanent else "Moving items to Trash…"
        if not self._begin_file_operation(label, len(targets)):
            return

        worker = self.file_tasks.submit(
            trash_paths,
            tuple(targets),
            with_progress=True,
            on_progress=lambda payload: self._file_operation_progress(
                payload, "Deleting" if permanent else "Trashing"
            ),
            on_result=lambda report: self._delete_completed(report, permanent),
            on_error=self._delete_worker_error,
            on_finished=self._release_file_operation,
        )
        if worker is None:
            self._release_file_operation()
            self.operation_finished.emit("File operation could not be started")

    def _delete_completed(self, report: OperationReport, permanent: bool) -> None:
        for old_path, new_path in report.moved_directories:
            self._retarget_open_tabs(old_path, new_path)
        self._show_report_errors("Delete Summary", report)
        self.refreshCurrentTab()
        verb = "Deleted" if permanent else "Moved to Trash"
        message = f"{verb} {report.completed} item(s)"
        if report.error_count:
            message += f"; {report.error_count} failed"
        self.operation_finished.emit(message)

    def _delete_worker_error(self, error: dict[str, str]) -> None:
        QMessageBox.critical(
            self, "Delete Failed", error.get("message", "Unknown error")
        )
        self.operation_finished.emit("Delete operation failed")

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
            if normalized in seen or not os.path.lexists(normalized):
                continue
            seen.add(normalized)
            unique_paths.append(normalized)
        return unique_paths

    def _set_file_clipboard(self, operation: str, paths) -> None:
        """Store a validated cut/copy selection through one code path."""
        if operation not in {"cut", "copy"}:
            raise ValueError(f"unsupported clipboard operation: {operation}")
        items = self._as_paths(paths)
        if not items:
            title = "Cut" if operation == "cut" else "Copy"
            QMessageBox.warning(self, title, f"No valid items to {operation}.")
            return
        self.clipboard = (operation, items)
        self.paste_button.setEnabled(True)
        verb = "move" if operation == "cut" else "copy"
        self.status_message.emit(f"Ready to {verb} {len(items)} item(s)")

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

    def _finish_cut_clipboard(self, original_items):
        """Keep only sources that still exist after a partial move."""
        remaining = [path for path in original_items if os.path.lexists(path)]
        if remaining:
            self.clipboard = ("cut", remaining)
        else:
            self.clipboard = None
        self.paste_button.setEnabled(self.clipboard is not None and not self.is_busy)

    def _paste_clipboard_to(self, dest_dir):
        if not self.clipboard:
            self.status_message.emit("Nothing to paste")
            return
        op, items = self.clipboard
        self._transfer_file_or_folder(
            items,
            dest_dir,
            op,
            confirm_title="Confirm Paste",
            summary_title="Paste Summary",
            update_cut_clipboard=True,
        )

    def dropFileOrFolder(self, paths, dest_dir):
        """Move dropped local items after the same confirmation used by Cut/Paste."""
        return self._transfer_file_or_folder(
            paths,
            dest_dir,
            "cut",
            confirm_title="Confirm Drop",
            summary_title="Drop Summary",
            update_cut_clipboard=False,
        )

    @staticmethod
    def _merge_reports(
        report: OperationReport, preflight: OperationReport
    ) -> OperationReport:
        report.skipped += preflight.skipped
        report.same_location += preflight.same_location
        report.error_count += preflight.error_count
        if preflight.details:
            report.details = (preflight.details + report.details)[:24]
        return report

    def _transfer_file_or_folder(
        self,
        items,
        dest_dir,
        op,
        confirm_title="Confirm Paste",
        summary_title="Paste Summary",
        update_cut_clipboard=False,
    ):
        """Validate and confirm a transfer, then execute it off the UI thread."""
        if op not in {"copy", "cut"}:
            QMessageBox.warning(self, "File Operation", f"Unknown operation: {op}")
            return False
        if self.is_busy:
            self.status_message.emit("Another file operation is already running")
            return False

        destination_dir = os.path.abspath(os.path.expanduser(str(dest_dir)))
        if not os.path.isdir(destination_dir):
            QMessageBox.warning(
                self,
                confirm_title,
                f"Destination is not a folder:\n{destination_dir}",
            )
            return False

        sources = self._as_paths(items)
        if not sources:
            if op == "cut" and update_cut_clipboard:
                self.clipboard = None
                self.paste_button.setEnabled(False)
            return False

        verb = "move" if op == "cut" else "copy"
        answer = QMessageBox.question(
            self,
            confirm_title,
            f"{verb.title()} {len(sources)} "
            f"{'item' if len(sources) == 1 else 'items'} to:\n{destination_dir}?",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No,
        )
        if answer != QMessageBox.Yes:
            return False

        overwrite_all = False
        skip_all = False
        preflight = OperationReport()
        plan: list[TransferItem] = []

        for source in sources:
            if not os.path.lexists(source):
                preflight.add_error(f"{source}: source no longer exists")
                continue

            name = os.path.basename(source.rstrip(os.sep))
            destination = os.path.join(destination_dir, name)
            is_directory = os.path.isdir(source) and not os.path.islink(source)

            if is_directory and resolved_same_or_subpath(destination, source):
                preflight.add_error(
                    f"{source}: cannot {verb} a folder into itself or a subfolder"
                )
                continue

            destination_exists = os.path.lexists(destination)
            same_location = False
            if destination_exists:
                try:
                    same_location = os.path.samefile(source, destination)
                except OSError:
                    same_location = os.path.abspath(source) == os.path.abspath(
                        destination
                    )
            if same_location:
                preflight.same_location += 1
                continue

            replace = False
            if destination_exists:
                if skip_all:
                    preflight.skipped += 1
                    continue
                if overwrite_all:
                    replace = True
                else:
                    destination_is_directory = os.path.isdir(
                        destination
                    ) and not os.path.islink(destination)
                    choice = self._prompt_overwrite(
                        destination, destination_is_directory
                    )
                    if choice == "cancel":
                        self.status_message.emit("File operation cancelled")
                        return False
                    if choice == "no":
                        preflight.skipped += 1
                        continue
                    if choice == "no_all":
                        skip_all = True
                        preflight.skipped += 1
                        continue
                    if choice == "yes_all":
                        overwrite_all = True
                    replace = True

            plan.append(
                TransferItem(
                    source=source,
                    destination=destination,
                    replace=replace,
                    is_directory=is_directory,
                )
            )

        if not plan:
            self._show_report_errors(summary_title, preflight)
            parts = ["No items were queued"]
            if preflight.same_location:
                parts.append(f"{preflight.same_location} already in that location")
            if preflight.skipped:
                parts.append(f"{preflight.skipped} skipped")
            self.status_message.emit("; ".join(parts))
            return True

        display_verb = "Moving" if op == "cut" else "Copying"
        if not self._begin_file_operation(f"{display_verb} items…", len(plan)):
            return False

        worker = self.file_tasks.submit(
            execute_transfer,
            tuple(plan),
            op == "cut",
            with_progress=True,
            on_progress=lambda payload: self._file_operation_progress(
                payload, display_verb
            ),
            on_result=lambda report: self._transfer_completed(
                report,
                preflight,
                op,
                sources,
                update_cut_clipboard,
                summary_title,
            ),
            on_error=lambda error: self._transfer_worker_error(error, display_verb),
            on_finished=self._release_file_operation,
        )
        if worker is None:
            self._release_file_operation()
            self.operation_finished.emit("File operation could not be started")
            return False
        return True

    def _transfer_completed(
        self,
        report: OperationReport,
        preflight: OperationReport,
        op: str,
        original_sources,
        update_cut_clipboard: bool,
        summary_title: str,
    ) -> None:
        report = self._merge_reports(report, preflight)
        for old_path, new_path in report.moved_directories:
            self._retarget_open_tabs(old_path, new_path)

        if op == "cut" and update_cut_clipboard:
            self._finish_cut_clipboard(original_sources)

        self._show_report_errors(summary_title, report)
        self.refreshCurrentTab()

        past_tense = "Moved" if op == "cut" else "Copied"
        parts = [f"{past_tense} {report.completed} item(s)"]
        if report.same_location:
            parts.append(f"{report.same_location} already there")
        if report.skipped:
            parts.append(f"{report.skipped} skipped")
        if report.error_count:
            parts.append(f"{report.error_count} failed")
        self.operation_finished.emit("; ".join(parts))

    def _transfer_worker_error(self, error: dict[str, str], display_verb: str) -> None:
        QMessageBox.critical(
            self,
            f"{display_verb} Failed",
            error.get("message", "Unknown error"),
        )
        self.operation_finished.emit(f"{display_verb} failed")

    # ------------------------------------------------------------------
    # Open With...
    # ------------------------------------------------------------------
    def open_with(self, indexes):
        """Prompt for a program and open selected file(s) with it."""
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
            QMessageBox.warning(
                self, "Open With...", "Please select at least one file (not a folder)."
            )
            return

        settings = QSettings(SETTINGS_ORGANIZATION, SETTINGS_APPLICATION)
        last_program = str(settings.value("open_with/last_program", "") or "")

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
            launch_paths(program_text, file_paths)
        except Exception as exc:
            QMessageBox.warning(self, "Open With...", f"Failed to launch:\n{exc}")
            return

        settings.setValue("open_with/last_program", program_text.strip())

    # ------------------------------------------------------------------
    # Icon theme refresh (used by MainWindow)
    # ------------------------------------------------------------------
    def refresh_icon_theme(self) -> None:
        """Rebuild cached file icons after QIcon.setThemeName changes."""
        self._update_toolbar_icons()

        tab_paths = []
        for i in range(self.tab_widget.count()):
            view = self.tab_widget.widget(i)
            if view is not None:
                tab_paths.append((view, self.currentPath(view)))

        old_model = self.fs_model
        self.fs_model = self._create_shared_model()

        for view, path in tab_paths:
            try:
                view.setUpdatesEnabled(False)
            except Exception:
                pass
            try:
                view.setModel(self.fs_model)
                self._connect_selection_model(view)
                self._configure_icon_view(view)
                self._set_view_root(view, path)
            finally:
                try:
                    view.setUpdatesEnabled(True)
                except Exception:
                    pass
            try:
                view.scheduleDelayedItemsLayout()
                view.viewport().update()
            except Exception:
                pass

        try:
            old_model.deleteLater()
        except Exception:
            pass

        self._sync_current_view_ui()

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
