#!/usr/bin/env python3
"""Tabbed file browser and filesystem interaction layer for Spin FM."""

from __future__ import annotations

from io import BytesIO
import os
import uuid
import weakref
from collections import deque
from collections.abc import Iterable
from dataclasses import dataclass
from urllib.parse import unquote, urlparse

from .audio import is_supported_audio_file
from .config import SETTINGS_APPLICATION, SETTINGS_ORGANIZATION
from .dialogs import TrashLocation, TrashLocationDialog
from .file_ops import (
    OperationReport,
    TransferItem,
    delete_paths,
    ensure_trash_directories,
    execute_transfer,
    is_path_in_trash,
    mounted_trash_directories,
    resolved_same_or_subpath,
    same_or_subpath,
    trash_mount_point,
    trash_paths,
)
from .launch import launch_default, launch_paths
from .qt_compat import (
    QAbstractItemView,
    QAction,
    QApplication,
    QDir,
    QEvent,
    QFileDialog,
    QFileSystemModel,
    QIcon,
    QInputDialog,
    QLineEdit,
    QListView,
    QMenu,
    QMessageBox,
    QMimeData,
    QPixmapCache,
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
    QUrl,
    QVBoxLayout,
    QWidget,
    pyqtSignal,
)
from .workers import TaskManager


@dataclass(slots=True)
class _TransferContext:
    preflight: OperationReport
    operation: str
    summary_title: str
    display_verb: str
    clipboard_token: bytes | None = None


@dataclass(slots=True)
class _DeleteContext:
    mode: str
    progress_verb: str


def _exec_temporary_menu(menu: QMenu, position):
    """Execute a short-lived menu and queue its native resources for deletion."""
    try:
        return menu.exec(position) if hasattr(menu, "exec") else menu.exec_(position)
    finally:
        try:
            menu.deleteLater()
        except Exception:
            pass


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
        action = _exec_temporary_menu(context_menu, pos)

        if action == new_action:
            self.newTabRequested.emit()
        elif duplicate_action is not None and action == duplicate_action:
            self.duplicateTabRequested.emit(tab_index)
        elif close_action is not None and action == close_action:
            self.closeTabRequested.emit(tab_index)


class FullNameIconDelegate(QStyledItemDelegate):
    """Paint complete wrapped item names without delegating elision to Qt styles."""

    HORIZONTAL_PADDING = 18
    VERTICAL_PADDING = 18
    ICON_TEXT_GAP = 8
    TEXT_HEIGHT_SAFETY = 4
    MINIMUM_HEIGHT = 112

    def __init__(self, item_width: int, icon_height: int, parent=None) -> None:
        super().__init__(parent)
        self.update_geometry(item_width, icon_height)

    def update_geometry(self, item_width: int, icon_height: int) -> None:
        """Reuse one delegate while allowing icon/item geometry to change."""
        self.item_width = max(112, int(item_width))
        self.icon_height = max(32, int(icon_height))

    @staticmethod
    def _enum_value(owner, group_name: str, value_name: str):
        """Return a Qt5/Qt6 enum value without binding-version branches."""
        direct = getattr(owner, value_name, None)
        if direct is not None:
            return direct
        group = getattr(owner, group_name, None)
        return getattr(group, value_name, None) if group is not None else None

    @staticmethod
    def _flag_int(value) -> int:
        """Return a numeric Qt flag on both PyQt5 and strict PyQt6 enums."""
        try:
            return int(value)
        except (TypeError, ValueError):
            return int(getattr(value, "value", 0))

    @classmethod
    def _text_flags(cls) -> int:
        # PyQt6 keeps AlignmentFlag and TextFlag as separate enum classes, so
        # combining the enum objects directly can raise TypeError. QPainter and
        # QFontMetrics accept the corresponding integer bit mask on both Qt 5/6.
        flags = 0
        for value in (
            Qt.AlignHCenter,
            Qt.AlignTop,
            Qt.TextWordWrap,
            Qt.TextWrapAnywhere,
        ):
            flags |= cls._flag_int(value)
        return flags

    def _icon_rect(self, item_rect: QRect) -> QRect:
        icon_size = min(
            self.icon_height,
            max(0, item_rect.width() - self.HORIZONTAL_PADDING * 2),
        )
        return QRect(
            item_rect.x() + max(0, (item_rect.width() - icon_size) // 2),
            item_rect.y() + self.VERTICAL_PADDING,
            icon_size,
            icon_size,
        )

    def _text_rect(self, item_rect: QRect) -> QRect:
        top_offset = self.VERTICAL_PADDING + self.icon_height + self.ICON_TEXT_GAP
        return QRect(
            item_rect.x() + self.HORIZONTAL_PADDING,
            item_rect.y() + top_offset,
            max(0, item_rect.width() - self.HORIZONTAL_PADDING * 2),
            max(0, item_rect.height() - top_offset - self.VERTICAL_PADDING),
        )

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

    def _paint_background(self, painter, option) -> None:
        """Let the active style paint hover, selection, focus, and item borders."""
        try:
            background = QStyleOptionViewItem(option)
        except Exception:
            background = option

        try:
            background.text = ""
            background.icon = QIcon()
            for feature_name in ("HasDisplay", "HasDecoration"):
                feature = self._enum_value(
                    QStyleOptionViewItem,
                    "ViewItemFeature",
                    feature_name,
                )
                if feature is not None:
                    background.features &= ~feature
        except Exception:
            pass

        control = self._enum_value(QStyle, "ControlElement", "CE_ItemViewItem")
        if control is None:
            return
        try:
            style = (
                option.widget.style()
                if option.widget is not None
                else QApplication.style()
            )
            style.drawControl(control, background, painter, option.widget)
        except Exception:
            pass

    def _paint_icon(self, painter, option) -> None:
        try:
            icon = option.icon
            if icon is None or icon.isNull():
                return
            icon.paint(painter, self._icon_rect(option.rect), Qt.AlignCenter)
        except Exception:
            pass

    def _paint_text(self, painter, option, text: str) -> None:
        if not text:
            return
        text_rect = self._text_rect(option.rect)
        if text_rect.width() <= 0 or text_rect.height() <= 0:
            return

        selected_flag = self._enum_value(QStyle, "StateFlag", "State_Selected")
        try:
            selected = selected_flag is not None and bool(option.state & selected_flag)
        except Exception:
            selected = False

        saved = False
        try:
            brush = (
                option.palette.highlightedText()
                if selected
                else option.palette.text()
            )
            painter.save()
            saved = True
            painter.setPen(brush.color())
            # Draw the original name directly.  No pre-elision or style-managed
            # text layout is involved, so every character can wrap onto another line.
            flags = self._text_flags()
            try:
                painter.drawText(text_rect, flags, text)
            except TypeError:
                painter.drawText(text_rect, int(flags), text)
        except Exception:
            pass
        finally:
            if saved:
                try:
                    painter.restore()
                except Exception:
                    pass

    def paint(self, painter, option, index) -> None:
        """Paint the style chrome, icon, and complete wrapped name separately."""
        try:
            prepared = QStyleOptionViewItem(option)
        except Exception:
            prepared = option
        self.initStyleOption(prepared, index)
        try:
            text = str(prepared.text or index.data(Qt.DisplayRole) or "")
        except Exception:
            text = ""

        self._paint_background(painter, prepared)
        self._paint_icon(painter, prepared)
        self._paint_text(painter, prepared, text)

    def sizeHint(self, option, index):  # noqa: N802 - Qt API
        try:
            prepared = QStyleOptionViewItem(option)
        except Exception:
            prepared = option
        self.initStyleOption(prepared, index)
        try:
            text = str(prepared.text or index.data(Qt.DisplayRole) or "")
        except Exception:
            text = ""

        text_width = max(1, self.item_width - self.HORIZONTAL_PADDING * 2)
        font_metrics = prepared.fontMetrics
        flags = self._text_flags()
        try:
            try:
                bounds = font_metrics.boundingRect(
                    QRect(0, 0, text_width, 100_000),
                    flags,
                    text,
                )
            except TypeError:
                bounds = font_metrics.boundingRect(
                    QRect(0, 0, text_width, 100_000),
                    int(flags),
                    text,
                )
            text_height = max(font_metrics.height(), bounds.height())
        except Exception:
            # This should never be needed on supported Qt builds.  Keep the
            # fallback deliberately generous rather than risking clipped text.
            explicit_lines = text.splitlines() or [""]
            line_count = sum(max(1, len(line)) for line in explicit_lines)
            try:
                line_height = font_metrics.lineSpacing()
            except Exception:
                line_height = font_metrics.height()
            text_height = max(font_metrics.height(), line_count * line_height)

        height = (
            self.VERTICAL_PADDING
            + self.icon_height
            + self.ICON_TEXT_GAP
            + text_height
            + self.TEXT_HEIGHT_SAFETY
            + self.VERTICAL_PADDING
        )
        return QSize(self.item_width, max(self.MINIMUM_HEIGHT, height))


class FileIconListView(QListView):
    """Icon view with resize-friendly layout and file drag-and-drop support."""

    _ENTER_KEY_CODES: frozenset[int] | None = None

    def __init__(self, tabs_widget=None, parent=None):
        super().__init__(parent)
        self._tabs_widget_ref = None
        self.tabs_widget = tabs_widget
        try:
            # QAbstractItemView uses a child viewport as the actual focus/event
            # target. Installing the view itself as the viewport filter catches
            # Return before style/platform handlers can consume it.
            self.viewport().installEventFilter(self)
        except Exception:
            pass

    @property
    def tabs_widget(self):
        """Return the owning Tabs widget without creating a Python reference cycle."""
        reference = self._tabs_widget_ref
        return reference() if reference is not None else None

    @tabs_widget.setter
    def tabs_widget(self, value) -> None:
        self._tabs_widget_ref = weakref.ref(value) if value is not None else None

    @staticmethod
    def _key_code(value) -> int:
        """Normalize PyQt5 integers and PyQt6 enum values to one integer code."""
        try:
            return int(value)
        except (TypeError, ValueError):
            try:
                return int(value.value)
            except (AttributeError, TypeError, ValueError):
                return -1

    @classmethod
    def _is_enter_key(cls, event) -> bool:
        try:
            pressed = cls._key_code(event.key())
        except Exception:
            return False
        if cls._ENTER_KEY_CODES is None:
            cls._ENTER_KEY_CODES = frozenset(
                code
                for code in (
                    cls._key_code(getattr(Qt, "Key_Return", None)),
                    cls._key_code(getattr(Qt, "Key_Enter", None)),
                )
                if code >= 0
            )
        return pressed in cls._ENTER_KEY_CODES

    def resizeEvent(self, event):  # noqa: N802 - Qt API name
        super().resizeEvent(event)
        try:
            self.scheduleDelayedItemsLayout()
        except Exception:
            pass

    def eventFilter(self, watched, event):  # noqa: N802 - Qt API name
        """Catch Return on the focused viewport before Qt consumes it."""
        try:
            is_viewport = watched is self.viewport()
            event_type = event.type()
        except Exception:
            is_viewport = False
            event_type = None
        if (
            is_viewport
            and event_type in (QEvent.ShortcutOverride, QEvent.KeyPress)
            and self._is_enter_key(event)
        ):
            try:
                event.accept()
            except Exception:
                pass
            if event_type == QEvent.ShortcutOverride:
                return True
            owner = self.tabs_widget
            if owner is not None:
                try:
                    auto_repeat = bool(event.isAutoRepeat())
                except Exception:
                    auto_repeat = False
                if not auto_repeat:
                    owner.activateCurrentSelection(self)
            return True
        return super().eventFilter(watched, event)

    def keyPressEvent(self, event):  # noqa: N802 - Qt API name
        """Open the selected item with Return or keypad Enter.

        MainWindow also intercepts these keys at application level because some
        Qt styles deliver them to the viewport before QListView.keyPressEvent.
        This view-level handler remains as a lightweight fallback.
        """
        owner = self.tabs_widget
        if self._is_enter_key(event) and owner is not None:
            owner.activateCurrentSelection(self)
            try:
                event.accept()
            except Exception:
                pass
            return
        super().keyPressEvent(event)

    def _event_position(self, event):
        """Return the event position for PyQt5 and PyQt6 drop events."""
        try:
            return event.position().toPoint()
        except Exception:
            try:
                return event.pos()
            except Exception:
                return None

    @staticmethod
    def _has_file_urls(mime_data) -> bool:
        """Check a drag payload without allocating a Python path list."""
        if mime_data is None:
            return False
        try:
            return bool(mime_data.hasUrls())
        except Exception:
            return False

    def _local_paths_from_mime_data(self, mime_data) -> tuple[str, ...]:
        """Extract unique local paths once, when a drop is actually committed."""
        if not self._has_file_urls(mime_data):
            return ()

        paths: list[str] = []
        seen: set[str] = set()
        try:
            urls = mime_data.urls()
        except Exception:
            return ()
        for url in urls:
            try:
                local_path = url.toLocalFile()
            except Exception:
                local_path = ""
            if not local_path:
                continue
            local_path = os.path.abspath(os.path.expanduser(local_path))
            if local_path in seen:
                continue
            seen.add(local_path)
            paths.append(local_path)
        return tuple(paths)

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
    def _event_modifiers(event):
        """Combine event and application modifiers for cross-window drags."""
        combined = None
        accessors = [
            getattr(event, "keyboardModifiers", None),
            getattr(event, "modifiers", None),
            getattr(QApplication, "keyboardModifiers", None),
        ]
        for accessor in accessors:
            if not callable(accessor):
                continue
            try:
                value = accessor()
            except Exception:
                continue
            if combined is None:
                combined = value
                continue
            try:
                combined = combined | value
            except Exception:
                try:
                    combined = int(combined) | int(value)
                except Exception:
                    pass
        return combined

    @classmethod
    def _drop_operation(cls, event) -> str:
        """Use Ctrl+drop for copy; an unmodified drop remains a move."""
        modifiers = cls._event_modifiers(event)
        control = Qt.ControlModifier
        if modifiers is not None and control is not None:
            try:
                if bool(modifiers & control):
                    return "copy"
            except Exception:
                try:
                    if int(modifiers) & int(control):
                        return "copy"
                except Exception:
                    pass

        # Respect sources that deliberately expose only copy, while Spin FM
        # sources advertise both actions through startDrag().
        try:
            if not bool(event.possibleActions() & Qt.MoveAction):
                return "copy"
        except Exception:
            pass
        return "cut"

    @classmethod
    def _accept_drag_preview(cls, event) -> None:
        """Show move normally and the standard copy cursor while Ctrl is held."""
        action = (
            Qt.CopyAction
            if cls._drop_operation(event) == "copy"
            else Qt.MoveAction
        )
        try:
            possible_actions = event.possibleActions()
            if not bool(possible_actions & action):
                action = Qt.CopyAction
        except Exception:
            pass
        try:
            event.setDropAction(action)
            event.accept()
        except Exception:
            event.acceptProposedAction()

    @staticmethod
    def _accept_manual_drop(event) -> None:
        """Report CopyAction because Spin FM executes the transfer itself."""
        copy_action = getattr(Qt, "CopyAction", None)
        if copy_action is not None:
            try:
                event.setDropAction(copy_action)
                event.accept()
                return
            except Exception:
                pass
        event.acceptProposedAction()

    def startDrag(self, supported_actions):  # noqa: N802 - Qt API name
        """Advertise both move and copy so Ctrl works across Spin FM windows."""
        actions = supported_actions
        try:
            actions = actions | Qt.CopyAction | Qt.MoveAction
        except Exception:
            pass
        super().startDrag(actions)

    def dragEnterEvent(self, event):  # noqa: N802 - Qt API name
        if self._has_file_urls(event.mimeData()):
            self._accept_drag_preview(event)
            return
        super().dragEnterEvent(event)

    def dragMoveEvent(self, event):  # noqa: N802 - Qt API name
        if self._has_file_urls(event.mimeData()):
            self._accept_drag_preview(event)
            return
        super().dragMoveEvent(event)

    def dropEvent(self, event):  # noqa: N802 - Qt API name
        paths = self._local_paths_from_mime_data(event.mimeData())
        if not paths or self.tabs_widget is None:
            super().dropEvent(event)
            return

        destination = self._drop_destination_directory(event)
        operation = self._drop_operation(event)
        handled = self.tabs_widget.dropFileOrFolder(
            paths,
            destination,
            operation=operation,
        )
        if handled:
            self._accept_manual_drop(event)
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

    FILE_OPERATION_MIME = "application/x-spin-fm-file-operation"
    FILE_CLIPBOARD_TOKEN_MIME = "application/x-spin-fm-clipboard-token"
    GNOME_COPIED_FILES_MIME = "x-special/gnome-copied-files"
    KDE_CUT_SELECTION_MIME = "application/x-kde-cutselection"

    MAX_HISTORY_ITEMS = 64
    MAX_UI_ERROR_DETAILS = 24
    MAX_MODEL_PATHS_BEFORE_RECYCLE = 24
    MAX_SELECTION_PATHS_TO_RESTORE = 512
    MODEL_RECYCLE_DELAY_MSEC = 1_500
    MODEL_RECYCLE_RETRY_MSEC = 1_500

    def __init__(self, parent=None):
        super().__init__(parent)

        # File clipboard data lives in the desktop clipboard so Ctrl+C/Ctrl+X
        # can be pasted by another Spin FM process without duplicating a large
        # Python path list for the lifetime of this widget.
        self._system_clipboard = None
        self._fallback_clipboard = None
        self._clipboard_has_files = False
        self._clipboard_revision = 0
        self.file_tasks = TaskManager(self, max_threads=1)
        self._file_operation_active = False
        self._external_operation_busy = False
        self._active_transfer_context: _TransferContext | None = None
        self._active_delete_context: _DeleteContext | None = None
        self._shutting_down = False

        # QFileSystemModel retains populated directory branches and filesystem
        # watchers. Recycle the shared model after a bounded number of distinct
        # navigations, while preserving visible tabs and ordinary selections.
        self._model_paths_since_recycle: set[str] = set()
        self._model_recycle_requested = False
        self._model_recycle_in_progress = False
        self._model_recycle_timer = QTimer(self)
        self._model_recycle_timer.setSingleShot(True)
        self._model_recycle_timer.timeout.connect(self._recycle_shared_model)

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

        self.copy_to_button = QToolButton()
        self.copy_to_button.setIcon(
            self._theme_icon("folder-copy", QStyle.SP_DirIcon)
        )
        self.copy_to_button.setToolTip("Copy selected items to another folder…")
        self.copy_to_button.clicked.connect(self.copySelectionToFolder)
        self.copy_to_button.setEnabled(False)
        self.toolbar.addWidget(self.copy_to_button)

        self.move_to_button = QToolButton()
        self.move_to_button.setIcon(
            self._theme_icon("folder-move", QStyle.SP_DirIcon)
        )
        self.move_to_button.setToolTip("Move selected items to another folder…")
        self.move_to_button.clicked.connect(self.moveSelectionToFolder)
        self.move_to_button.setEnabled(False)
        self.toolbar.addWidget(self.move_to_button)

        self.delete_button = QToolButton()
        self.delete_button.setIcon(
            self._theme_icon("edit-delete", QStyle.SP_TrashIcon)
        )
        self.delete_button.setToolTip(
            "Move selected items to Trash (Delete); Shift+Delete deletes permanently"
        )
        self.delete_button.clicked.connect(self.deleteSelection)
        self.delete_button.setEnabled(False)
        self.toolbar.addWidget(self.delete_button)

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
        self._connect_system_clipboard()

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
            ("copy_to_button", "folder-copy", QStyle.SP_DirIcon),
            ("move_to_button", "folder-move", QStyle.SP_DirIcon),
            ("delete_button", "edit-delete", QStyle.SP_TrashIcon),
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
            delegate = getattr(view, "_spinfm_full_name_delegate", None)
            if isinstance(delegate, FullNameIconDelegate):
                delegate.update_geometry(
                    self.file_item_width,
                    self.file_icon_size.height(),
                )
            else:
                delegate = FullNameIconDelegate(
                    self.file_item_width,
                    self.file_icon_size.height(),
                    view,
                )
                view._spinfm_full_name_delegate = delegate
            if view.itemDelegate() is not delegate:
                view.setItemDelegate(delegate)
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
            for option_name in (
                "DontUseCustomDirectoryIcons",
                "DontResolveSymlinks",
            ):
                option = getattr(option_owner, option_name, None)
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

    def _record_model_path(self, path: str) -> None:
        """Count unique navigation roots loaded by the current shared model."""
        if self._shutting_down or self._model_recycle_in_progress:
            return

        # Once maintenance has been requested, retaining every additional path
        # offers no benefit. Keeping the set capped is especially important when
        # recycling is postponed by a long drag, modal dialog, or file operation.
        if self._model_recycle_requested:
            return
        self._model_paths_since_recycle.add(path)
        if len(self._model_paths_since_recycle) >= self.MAX_MODEL_PATHS_BEFORE_RECYCLE:
            self._request_model_recycle()

    def _request_model_recycle(self, *, force: bool = False) -> None:
        """Coalesce cache-recycle requests into one idle-time model replacement."""
        if self._shutting_down:
            return
        if not force and (
            len(self._model_paths_since_recycle)
            < self.MAX_MODEL_PATHS_BEFORE_RECYCLE
        ):
            return
        self._model_recycle_requested = True
        if not self._model_recycle_timer.isActive():
            self._model_recycle_timer.start(self.MODEL_RECYCLE_DELAY_MSEC)

    def _retry_model_recycle(self) -> None:
        if self._shutting_down or not self._model_recycle_requested:
            return
        self._model_recycle_timer.start(self.MODEL_RECYCLE_RETRY_MSEC)

    @staticmethod
    def _temporary_ui_is_active() -> bool:
        """Avoid replacing view models while dragging or a popup/modal is active."""
        try:
            if QApplication.mouseButtons():
                return True
        except Exception:
            pass
        for getter_name in ("activePopupWidget", "activeModalWidget"):
            try:
                if getattr(QApplication, getter_name)() is not None:
                    return True
            except Exception:
                pass
        return False

    def _selection_paths_for_restore(
        self, view, limit: int | None = None
    ) -> list[str] | None:
        """Read selection ranges without materialising an unbounded index list."""
        try:
            selection_model = view.selectionModel()
            ranges = selection_model.selection()
        except Exception:
            return []

        paths: list[str] = []
        seen: set[str] = set()
        selection_limit = max(
            0,
            int(
                self.MAX_SELECTION_PATHS_TO_RESTORE
                if limit is None
                else limit
            ),
        )
        try:
            for selected_range in ranges:
                parent = selected_range.parent()
                for row in range(selected_range.top(), selected_range.bottom() + 1):
                    if len(paths) >= selection_limit:
                        return None
                    index = self.fs_model.index(row, 0, parent)
                    path = self._path_from_index(index)
                    if path and path not in seen:
                        seen.add(path)
                        paths.append(path)
        except Exception:
            return []
        return paths

    def _capture_view_states(self) -> list[dict[str, object]] | None:
        """Capture small view state needed for a transparent model replacement."""
        states: list[dict[str, object]] = []
        remaining_selection_paths = self.MAX_SELECTION_PATHS_TO_RESTORE
        for index in range(self.tab_widget.count()):
            view = self.tab_widget.widget(index)
            if view is None:
                continue
            selected_paths = self._selection_paths_for_restore(
                view, remaining_selection_paths
            )
            if selected_paths is None:
                # Preserve very large selections by postponing maintenance until
                # the user finishes the operation rather than silently clearing it.
                return None
            remaining_selection_paths -= len(selected_paths)
            try:
                current_item = self._path_from_index(view.currentIndex())
            except Exception:
                current_item = ""
            try:
                horizontal_scroll = int(view.horizontalScrollBar().value())
                vertical_scroll = int(view.verticalScrollBar().value())
            except Exception:
                horizontal_scroll = 0
                vertical_scroll = 0
            states.append(
                {
                    "view": view,
                    "path": self.currentPath(view),
                    "selected_paths": selected_paths,
                    "current_item": current_item,
                    "horizontal_scroll": horizontal_scroll,
                    "vertical_scroll": vertical_scroll,
                }
            )
        return states

    @staticmethod
    def _selection_flags():
        """Return Select|Rows flags on both Qt 5 and Qt 6."""
        from .qt_compat import QtCore

        owner = getattr(
            QtCore.QItemSelectionModel,
            "SelectionFlag",
            QtCore.QItemSelectionModel,
        )
        return getattr(owner, "Select") | getattr(owner, "Rows")

    def _restore_view_state(self, state: dict[str, object]) -> None:
        view = state["view"]
        selection_model = view.selectionModel()
        try:
            selection_model.blockSignals(True)
        except Exception:
            pass
        try:
            flags = self._selection_flags()
            for path in state["selected_paths"]:
                index = self.fs_model.index(str(path))
                if index is not None and index.isValid():
                    selection_model.select(index, flags)
            current_path = str(state["current_item"] or "")
            if current_path:
                current_index = self.fs_model.index(current_path)
                if current_index is not None and current_index.isValid():
                    view.setCurrentIndex(current_index)
        except Exception:
            pass
        finally:
            try:
                selection_model.blockSignals(False)
            except Exception:
                pass

        horizontal = int(state["horizontal_scroll"])
        vertical = int(state["vertical_scroll"])
        try:
            view.horizontalScrollBar().setValue(horizontal)
            view.verticalScrollBar().setValue(vertical)
        except Exception:
            pass

    def _replace_shared_model(
        self, states: list[dict[str, object]] | None = None
    ) -> bool:
        """Replace QFileSystemModel so stale branches/watchers can be reclaimed."""
        if self._shutting_down or self._model_recycle_in_progress:
            return False
        if states is None:
            states = self._capture_view_states()
        if states is None:
            return False

        old_model = self.fs_model
        try:
            new_model = self._create_shared_model()
        except Exception:
            return False

        self._model_recycle_in_progress = True
        self.fs_model = new_model
        try:
            for state in states:
                view = state["view"]
                try:
                    view.setUpdatesEnabled(False)
                    self._disconnect_selection_model(view)
                    view.setModel(new_model)
                    self._connect_selection_model(view)
                    self._configure_icon_view(view)
                    self._set_view_root(view, str(state["path"]))
                    self._restore_view_state(state)
                    view.scheduleDelayedItemsLayout()
                    view.viewport().update()
                except (AttributeError, RuntimeError, TypeError):
                    continue
                finally:
                    try:
                        view.setUpdatesEnabled(True)
                    except Exception:
                        pass
        finally:
            self._model_recycle_in_progress = False

        self._model_paths_since_recycle.clear()
        self._model_recycle_requested = False
        try:
            old_model.deleteLater()
        except Exception:
            pass
        try:
            QPixmapCache.clear()
        except Exception:
            pass
        self._sync_current_view_ui()
        return True

    def _recycle_shared_model(self) -> None:
        """Run bounded model-cache maintenance only at a safe UI idle point."""
        if self._shutting_down or not self._model_recycle_requested:
            return
        if self.is_busy or self._temporary_ui_is_active():
            self._retry_model_recycle()
            return
        states = self._capture_view_states()
        if states is None or not self._replace_shared_model(states):
            self._retry_model_recycle()

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
        button.clicked.connect(self._close_tab_from_button)

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

    def _close_tab_from_button(self, _checked: bool = False) -> None:
        button = self.sender()
        self.closeTab(self._tab_index_for_close_button(button))

    def _model_index_for_directory(self, path: str):
        """Return a valid shared-model index for an existing directory.

        QFileSystemModel may not have indexed hidden ancestor directories yet.
        This is common for the freedesktop Trash path under ``~/.local``.  Prime
        the requested directory explicitly when the first lookup is invalid so
        toolbar navigation cannot silently do nothing.
        """
        target = self._normalize_existing_directory(path)
        self._record_model_path(target)
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
            self._update_file_action_state(0)
            return

        self.address_bar.setText(self.currentPath(view))
        self._update_navigation_buttons()
        self._update_file_action_state()

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
            view.setBatchSize(64)
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

        view_id = id(view)
        view.setContextMenuPolicy(Qt.CustomContextMenu)
        view.customContextMenuRequested.connect(
            lambda pos, bound_id=view_id: self._open_context_menu_for_view(
                pos, bound_id
            )
        )
        # ``activated`` follows the desktop style hint and can fire on a single
        # click. Use the unambiguous double-click signal and explicit keyboard
        # actions so selection never starts playback or opens a folder.
        view.doubleClicked.connect(
            lambda item_index, bound_id=view_id: self._activate_index_for_view(
                item_index, bound_id
            )
        )
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
            previous_path = self.currentPath(view)
            self._reset_view_history(view)
            self._set_view_root(view, self.home_path)
            self.tab_widget.setCurrentWidget(view)
            if previous_path != self.home_path:
                self._request_model_recycle(force=True)
            return

        self.history.pop(view, None)
        tab_bar = self.tab_widget.tabBar()
        side = self._tab_button_side()
        try:
            close_button = tab_bar.tabButton(index, side)
            tab_bar.setTabButton(index, side, None)
            if close_button is not None:
                close_button.clicked.disconnect(self._close_tab_from_button)
                close_button.setParent(None)
                close_button.deleteLater()
        except Exception:
            pass
        self._prepare_view_for_deletion(view)
        self.tab_widget.removeTab(index)
        try:
            view.setParent(None)
            view.deleteLater()
        except Exception:
            pass

        self._sync_current_view_ui()
        self._request_model_recycle(force=True)

    def _view_by_id(self, view_id: int):
        try:
            for index in range(self.tab_widget.count()):
                view = self.tab_widget.widget(index)
                if view is not None and id(view) == view_id:
                    return view
        except (AttributeError, RuntimeError):
            pass
        return None

    def _open_context_menu_for_view(self, position, view_id: int) -> None:
        view = self._view_by_id(view_id)
        if view is not None:
            self.openFileContextMenu(position, view)

    def _activate_index_for_view(self, index, view_id: int) -> None:
        view = self._view_by_id(view_id)
        if view is not None:
            self.onFileActivated(index, view)

    def _prepare_view_for_deletion(self, view) -> None:
        """Disconnect callbacks and release closed-tab objects before deletion."""
        self._disconnect_selection_model(view)
        try:
            view.viewport().removeEventFilter(view)
        except Exception:
            pass
        for signal_name in ("customContextMenuRequested", "doubleClicked"):
            try:
                getattr(view, signal_name).disconnect()
            except Exception:
                pass
        try:
            actions = view.actions()
        except Exception:
            actions = ()
        for action in actions:
            try:
                action.triggered.disconnect()
            except Exception:
                pass
            try:
                view.removeAction(action)
                action.setParent(None)
                action.deleteLater()
            except Exception:
                pass
        try:
            view.setModel(None)
        except Exception:
            pass
        try:
            view.tabs_widget = None
        except Exception:
            pass
        try:
            view.setProperty("current_path", None)
            view._spinfm_current_path = None
            view._spinfm_full_name_delegate = None
        except Exception:
            pass

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
        _bind("Copy to Folder", "Ctrl+Shift+C", self.copySelectionToFolder)
        _bind("Move to Folder", "Ctrl+Shift+M", self.moveSelectionToFolder)
        _bind("Delete", "Delete", self.deleteSelection)
        _bind(
            "Delete Permanently",
            "Shift+Delete",
            lambda: self.deleteSelection(permanent=True),
        )
        _bind("Refresh", "F5", self.refreshCurrentTab)
        _bind("Refresh", "Ctrl+R", self.refreshCurrentTab)
        _bind("Up", "Ctrl+Up", self.goUp)
        _bind(
            "Close Tab", "Ctrl+W", lambda: self.closeTab(self.tab_widget.currentIndex())
        )
        _bind("Focus Location", "Ctrl+L", self.focusLocationBar)
        _bind("Clear Selection", "Escape", view.clearSelection)

        select_all = QAction("Select All", view)
        select_all.setShortcut("Ctrl+A")
        try:
            select_all.setShortcutContext(Qt.WidgetWithChildrenShortcut)
        except Exception:
            pass
        select_all.triggered.connect(view.selectAll)
        view.addAction(select_all)

    def activateCurrentSelection(self, view=None) -> bool:
        """Open the selected file/folder and report whether activation occurred."""
        target_view = view or self.currentView()
        if target_view is None:
            return False

        index = None
        try:
            current = target_view.currentIndex()
            selection_model = target_view.selectionModel()
            if (
                current is not None
                and current.isValid()
                and selection_model is not None
                and selection_model.isSelected(current)
            ):
                index = current
        except Exception:
            index = None

        # Prefer an actually selected row over a stale current index. Extended
        # selections can leave currentIndex() pointing at an item that is no
        # longer selected after keyboard/mouse selection changes.
        if index is None:
            index = next(self._iter_selected_row_indexes(target_view), None)

        # Preserve normal QListView behavior when there is a current item but no
        # explicit selection (for example after keyboard navigation).
        if index is None:
            try:
                current = target_view.currentIndex()
                if current is not None and current.isValid():
                    index = current
            except Exception:
                index = None

        if index is None:
            self.status_message.emit("Select a file or folder to open")
            return False

        self.onFileActivated(index, target_view)
        return True

    def _activate_current_item(self, view) -> bool:
        """Compatibility wrapper for older internal callers."""
        return self.activateCurrentSelection(view)

    @staticmethod
    def _selected_row_count(view) -> int:
        """Count selected rows from ranges without allocating one index per item."""
        try:
            selection = view.selectionModel().selection()
        except Exception:
            return 0

        count = 0
        try:
            for selected_range in selection:
                if selected_range.left() <= 0 <= selected_range.right():
                    count += selected_range.bottom() - selected_range.top() + 1
        except Exception:
            return 0
        return max(0, count)

    def _selection_changed(self, view) -> None:
        if view is not self.currentView():
            return
        count = self._selected_row_count(view)
        self._update_file_action_state(count)
        if count and not self.is_busy:
            self.status_message.emit(
                f"{count} {'item' if count == 1 else 'items'} selected"
            )

    def _update_file_action_state(self, selected_count: int | None = None) -> None:
        """Keep bulk-operation controls aligned with selection and task state."""

        if selected_count is None:
            view = self.currentView()
            selected_count = self._selected_row_count(view) if view is not None else 0
        selection_enabled = bool(selected_count) and not self.is_busy
        for button_name in (
            "cut_button",
            "copy_button",
            "copy_to_button",
            "move_to_button",
            "delete_button",
        ):
            button = getattr(self, button_name, None)
            if button is not None:
                button.setEnabled(selection_enabled)
        paste_button = getattr(self, "paste_button", None)
        if paste_button is not None:
            paste_button.setEnabled(self._has_file_clipboard() and not self.is_busy)

    def _connect_selection_model(self, view) -> None:
        """Reconnect selection feedback after a QFileSystemModel replacement."""
        self._disconnect_selection_model(view)
        try:
            selection_model = view.selectionModel()
            view_id = id(view)

            def selection_changed(*_args, bound_id=view_id):
                bound_view = self._view_by_id(bound_id)
                if bound_view is not None:
                    self._selection_changed(bound_view)

            selection_model.selectionChanged.connect(selection_changed)
            view._spinfm_selection_model = selection_model
            view._spinfm_selection_slot = selection_changed
        except Exception:
            pass

    @staticmethod
    def _disconnect_selection_model(view) -> None:
        selection_model = getattr(view, "_spinfm_selection_model", None)
        slot = getattr(view, "_spinfm_selection_slot", None)
        if selection_model is not None and slot is not None:
            try:
                selection_model.selectionChanged.disconnect(slot)
            except Exception:
                pass
        for attribute in ("_spinfm_selection_model", "_spinfm_selection_slot"):
            try:
                delattr(view, attribute)
            except Exception:
                pass

    def _iter_selected_row_indexes(self, view):
        """Yield column-zero indexes without allocating ``selectedRows()``."""

        try:
            selection_model = view.selectionModel()
            selection = selection_model.selection()
            model = view.model()
        except Exception:
            return

        try:
            for selected_range in selection:
                if not (selected_range.left() <= 0 <= selected_range.right()):
                    continue
                parent = selected_range.parent()
                for row in range(selected_range.top(), selected_range.bottom() + 1):
                    index = model.index(row, 0, parent)
                    if index is not None and index.isValid():
                        yield index
            return
        except Exception:
            pass

        # Binding/platform fallback. It is used only if compact range iteration
        # is unavailable, rather than being the default large-selection path.
        try:
            for index in selection_model.selectedRows(0):
                yield index
        except Exception:
            return

    def selectedPaths(self, view=None):
        """Return unique top-level selected paths in visible selection order."""
        target_view = view or self.currentView()
        if target_view is None:
            return ()

        return self._as_paths(
            (
                self._path_from_index(index)
                for index in self._iter_selected_row_indexes(target_view)
            ),
            # A file view exposes only direct children of its current folder,
            # so no selected row can contain another selected row. Defer the
            # comparatively expensive directory-stat pruning to operation
            # boundaries, where external drag/clipboard paths can be nested.
            prune_nested=False,
        )

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
        items = self._prepared_paths(paths, prune_nested=False)
        if not items:
            return
        clipboard = self._system_clipboard
        if clipboard is not None:
            self._fallback_clipboard = None
            self._clipboard_has_files = False
            before = self._clipboard_revision
            clipboard.setText("\n".join(items))
            if self._clipboard_revision == before:
                self._clipboard_revision += 1
                self._update_file_action_state()
        else:
            self._fallback_clipboard = None
            self._clipboard_has_files = False
            self._clipboard_revision += 1
            self._update_file_action_state()

    def pasteToCurrentFolder(self):
        self._paste_clipboard_to(self.currentPath())

    def deleteSelection(self, permanent: bool = False):
        paths = self.selectedPaths()
        if not paths:
            self.status_message.emit(
                "Select one or more items to delete or move to Trash"
            )
            return
        self._confirm_delete(paths, permanent=permanent)

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
        """Open files/directories while keeping large failure reports bounded."""
        items = self._prepared_paths(paths)
        if not items:
            return

        error_count = 0
        errors: list[str] = []

        def record_error(path: str, exc: Exception) -> None:
            nonlocal error_count
            error_count += 1
            if len(errors) < self.MAX_UI_ERROR_DETAILS:
                errors.append(f"{path}: {exc}")

        if new_tab:
            for path in items:
                if os.path.isdir(path):
                    self.createNewTab(path)
                else:
                    try:
                        self._open_file_path(path)
                    except Exception as exc:
                        record_error(path, exc)
        elif len(items) == 1 and os.path.isdir(items[0]):
            self._navigateTo(items[0])
        else:
            for path in items:
                if os.path.isdir(path):
                    self.createNewTab(path)
                else:
                    try:
                        self._open_file_path(path)
                    except Exception as exc:
                        record_error(path, exc)

        if error_count:
            details = "\n".join(errors)
            hidden = error_count - len(errors)
            if hidden:
                details += f"\n…and {hidden} more errors."
            QMessageBox.warning(
                self,
                "Open Error",
                f"{error_count} item(s) could not be opened:\n\n{details}",
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

        failed_indexes = []
        error_details: list[str] = []
        opened_or_failed = 0
        error_count = 0
        for index in selected_indexes:
            path = self._path_from_index(index)
            if not path or os.path.isdir(path):
                continue
            opened_or_failed += 1
            try:
                self._open_file_path(path)
            except Exception as exc:
                error_count += 1
                failed_indexes.append(index)
                if len(error_details) < self.MAX_UI_ERROR_DETAILS:
                    error_details.append(f"{path}: {exc}")

        if not opened_or_failed:
            return

        if failed_indexes:
            hidden = error_count - len(error_details)
            details = "\n".join(error_details)
            if hidden > 0:
                details += f"\n…and {hidden} more errors."
            QMessageBox.warning(
                self,
                "Open File",
                "Default open failed for one or more files.\n\n"
                + details
                + "\n\nYou can choose a program manually next.",
            )
            # Re-open only the files whose default launch failed, rather than
            # retaining/relaunching every successful QModelIndex in the batch.
            self.open_with(failed_indexes)

    # ------------------------------------------------------------------
    # Context menu
    # ------------------------------------------------------------------
    def openFileContextMenu(self, position, file_view):
        """Show item or folder actions without expanding unrelated selections."""
        context_menu = QMenu(self)

        clicked_index = file_view.indexAt(position)
        clicked_path = self._path_from_index(clicked_index)
        target_paths: tuple[str, ...] = ()
        if clicked_path:
            clicked_selected = False
            try:
                clicked_selected = bool(
                    file_view.selectionModel().isSelected(clicked_index)
                )
            except Exception:
                pass
            target_paths = (
                self.selectedPaths(file_view)
                if clicked_selected
                else (os.path.abspath(clicked_path),)
            )
            if not target_paths:
                target_paths = (os.path.abspath(clicked_path),)

        actions: dict[str, object] = {}
        paste_destination = self.currentPath(file_view)

        if target_paths:
            single_target = target_paths[0] if len(target_paths) == 1 else ""
            if single_target:
                is_directory = os.path.isdir(single_target)
                is_audio = os.path.isfile(single_target) and is_supported_audio_file(
                    single_target
                )
                actions["open"] = context_menu.addAction(
                    "Play in Spin FM" if is_audio else "Open"
                )
                if is_audio:
                    actions["open_external"] = context_menu.addAction(
                        "Open Externally"
                    )
                if is_directory:
                    actions["open_new_tab"] = context_menu.addAction(
                        "Open in New Tab"
                    )
                    paste_destination = single_target
                actions["rename"] = context_menu.addAction("Rename")
                actions["rename"].setEnabled(not self.is_busy)
            else:
                actions["open"] = context_menu.addAction("Open Selected Items")

            if any(
                os.path.isfile(path) or os.path.islink(path)
                for path in target_paths
            ):
                actions["open_with"] = context_menu.addAction("Open With…")

            context_menu.addSeparator()
            actions["cut"] = context_menu.addAction("Cut")
            actions["copy"] = context_menu.addAction("Copy")
            actions["copy_to"] = context_menu.addAction("Copy to Folder…")
            actions["move_to"] = context_menu.addAction("Move to Folder…")
            actions["copy_path"] = context_menu.addAction(
                "Copy Paths" if len(target_paths) > 1 else "Copy Path"
            )

            paste_label = (
                "Paste Into Folder"
                if single_target and os.path.isdir(single_target)
                else "Paste Into Current Folder"
            )
            actions["paste"] = context_menu.addAction(paste_label)
            actions["paste"].setEnabled(
                self._has_file_clipboard() and not self.is_busy
            )

            for key in ("cut", "copy", "copy_to", "move_to"):
                actions[key].setEnabled(not self.is_busy)

            context_menu.addSeparator()
            in_trash_count = sum(
                1 for path in target_paths if is_path_in_trash(path)
            )
            if in_trash_count == len(target_paths):
                actions["delete"] = context_menu.addAction("Delete Permanently")
            elif in_trash_count:
                actions["delete"] = context_menu.addAction(
                    "Move to Trash / Delete from Trash"
                )
                actions["delete_permanently"] = context_menu.addAction(
                    "Delete All Permanently…"
                )
            else:
                actions["delete"] = context_menu.addAction("Move to Trash")
                actions["delete_permanently"] = context_menu.addAction(
                    "Delete Permanently…"
                )
            actions["delete"].setEnabled(not self.is_busy)
            if "delete_permanently" in actions:
                actions["delete_permanently"].setEnabled(not self.is_busy)

            context_menu.addSeparator()
            actions["refresh"] = context_menu.addAction("Refresh")
        else:
            actions["new_file"] = context_menu.addAction("New Text File")
            actions["new_folder"] = context_menu.addAction("New Folder")
            actions["paste"] = context_menu.addAction("Paste")
            actions["paste"].setEnabled(
                self._has_file_clipboard() and not self.is_busy
            )
            actions["new_file"].setEnabled(not self.is_busy)
            actions["new_folder"].setEnabled(not self.is_busy)
            context_menu.addSeparator()
            actions["refresh"] = context_menu.addAction("Refresh")

        chosen = _exec_temporary_menu(
            context_menu, file_view.viewport().mapToGlobal(position)
        )
        if chosen is None:
            return

        if chosen == actions.get("open"):
            self._open_paths(target_paths)
        elif chosen == actions.get("open_external"):
            try:
                self._open_file_path(target_paths[0], externally=True)
            except Exception as exc:
                QMessageBox.warning(self, "Open Error", f"Could not open file:\n{exc}")
        elif chosen == actions.get("open_new_tab"):
            self._open_paths(target_paths, new_tab=True)
        elif chosen == actions.get("rename"):
            self.renameFileOrFolder(target_paths[0], file_view)
        elif chosen == actions.get("open_with"):
            self.open_with(target_paths)
        elif chosen == actions.get("cut"):
            self._set_file_clipboard("cut", target_paths)
        elif chosen == actions.get("copy"):
            self._set_file_clipboard("copy", target_paths)
        elif chosen == actions.get("copy_to"):
            self._transfer_selection_to_folder("copy", target_paths)
        elif chosen == actions.get("move_to"):
            self._transfer_selection_to_folder("cut", target_paths)
        elif chosen == actions.get("copy_path"):
            self.copyPathsToClipboard(target_paths)
        elif chosen == actions.get("paste"):
            self._paste_clipboard_to(paste_destination)
        elif chosen == actions.get("delete"):
            self._confirm_delete(target_paths)
        elif chosen == actions.get("delete_permanently"):
            self._confirm_delete(target_paths, permanent=True)
        elif chosen == actions.get("new_file"):
            self.createNewTextFile()
        elif chosen == actions.get("new_folder"):
            self.createNewFolder()
        elif chosen == actions.get("refresh"):
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
        self._update_file_action_state()

    def shutdown(self) -> None:
        """Release workers, model caches, callbacks, and retained path state."""
        if self._shutting_down:
            return
        self._shutting_down = True
        try:
            self._model_recycle_timer.stop()
        except Exception:
            pass
        self.file_tasks.shutdown(wait_msec=1_000)

        self._active_transfer_context = None
        self._active_delete_context = None
        self._fallback_clipboard = None
        self._clipboard_has_files = False
        clipboard, self._system_clipboard = self._system_clipboard, None
        if clipboard is not None:
            try:
                clipboard.dataChanged.disconnect(self._clipboard_changed)
            except Exception:
                pass

        self.history.clear()
        self._model_paths_since_recycle.clear()
        self._model_recycle_requested = False
        for index in range(self.tab_widget.count()):
            view = self.tab_widget.widget(index)
            if view is not None:
                self._prepare_view_for_deletion(view)

        model, self.fs_model = self.fs_model, None
        if model is not None:
            try:
                model.deleteLater()
            except Exception:
                pass
        try:
            QPixmapCache.clear()
        except Exception:
            pass

    def _begin_file_operation(self, label: str, total: int) -> bool:
        if self.is_busy:
            self.status_message.emit("Another file operation is already running")
            return False
        self._file_operation_active = True
        self._update_file_action_state()
        self.operation_started.emit(label, total)
        return True

    def _release_file_operation(self) -> None:
        self._file_operation_active = False
        # Result/error signals are emitted before finished by Worker, so these
        # are fallback releases for interrupted callbacks rather than the main
        # completion path.
        self._active_transfer_context = None
        self._active_delete_context = None
        self._update_file_action_state()

    def _file_operation_progress(self, payload, verb: str) -> None:
        try:
            current, total, name = payload
        except Exception:
            return
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

    def _tracked_directory_sources(self, paths: Iterable[str]) -> tuple[str, ...]:
        """Retain directory changes only when an open tab needs retargeting."""
        open_paths: list[str] = []
        for index in range(self.tab_widget.count()):
            view = self.tab_widget.widget(index)
            if view is not None:
                open_paths.append(self.currentPath(view))
        if not open_paths:
            return ()

        tracked: list[str] = []
        for path in paths:
            if not os.path.isdir(path) or os.path.islink(path):
                continue
            if any(same_or_subpath(open_path, path) for open_path in open_paths):
                tracked.append(path)
        return tuple(tracked)

    # ------------------------------------------------------------------
    # Delete / Trash operations
    # ------------------------------------------------------------------
    def _confirm_delete(self, paths, permanent: bool = False) -> None:
        if self.is_busy:
            self.status_message.emit("Wait for the current operation to finish")
            return
        targets = self._prepared_paths(paths, prune_nested=True)
        if not targets:
            return

        in_trash = sum(1 for path in targets if is_path_in_trash(path))
        total = len(targets)
        delete_directly = bool(permanent or in_trash == total)
        mixed = bool(in_trash and in_trash < total and not permanent)

        if delete_directly:
            title = "Confirm Permanent Delete"
            message = (
                "Permanently delete the selected item?\n\nThis cannot be undone."
                if total == 1
                else f"Permanently delete {total} selected items?\n\nThis cannot be undone."
            )
            mode = "delete"
            progress_verb = "Deleting"
            label = "Deleting items…"
            worker_function = delete_paths
        elif mixed:
            title = "Confirm Delete"
            move_count = total - in_trash
            message = (
                f"Move {move_count} item(s) to Trash and permanently delete "
                f"{in_trash} item(s) already in Trash?"
            )
            mode = "mixed"
            progress_verb = "Processing"
            label = "Processing selected items…"
            worker_function = trash_paths
        else:
            title = "Move to Trash"
            message = (
                "Move the selected item to Trash?"
                if total == 1
                else f"Move {total} selected items to Trash?"
            )
            mode = "trash"
            progress_verb = "Trashing"
            label = "Moving items to Trash…"
            worker_function = trash_paths

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

        tracked = self._tracked_directory_sources(targets)
        self._active_delete_context = _DeleteContext(mode, progress_verb)
        if not self._begin_file_operation(label, total):
            self._active_delete_context = None
            return

        submit_kwargs = {
            "with_progress": True,
            "on_progress": self._delete_progress,
            "on_result": self._delete_completed,
            "on_error": self._delete_worker_error,
            "on_finished": self._release_file_operation,
        }
        if worker_function is delete_paths:
            submit_kwargs["track_deleted_directories"] = tracked
        else:
            submit_kwargs["track_moved_directories"] = tracked

        worker = self.file_tasks.submit(worker_function, targets, **submit_kwargs)
        if worker is None:
            self._active_delete_context = None
            self._release_file_operation()
            self.operation_finished.emit("File operation could not be started")

    def _delete_progress(self, payload) -> None:
        context = self._active_delete_context
        self._file_operation_progress(
            payload,
            context.progress_verb if context is not None else "Processing",
        )

    def _delete_completed(self, report: OperationReport) -> None:
        context, self._active_delete_context = self._active_delete_context, None
        mode = context.mode if context is not None else "delete"
        for old_path, new_path in report.moved_directories:
            self._retarget_open_tabs(old_path, new_path)
        self._show_report_errors("Delete Summary", report)
        self.refreshCurrentTab()

        if mode == "trash":
            verb = "Moved to Trash"
        elif mode == "mixed":
            verb = "Processed"
        else:
            verb = "Deleted"
        message = f"{verb} {report.completed} item(s)"
        if report.error_count:
            message += f"; {report.error_count} failed"
        self.operation_finished.emit(message)

    def _delete_worker_error(self, error: dict[str, str]) -> None:
        self._active_delete_context = None
        QMessageBox.critical(
            self, "Delete Failed", error.get("message", "Unknown error")
        )
        self.operation_finished.emit("Delete operation failed")

    # ------------------------------------------------------------------
    # Clipboard helpers
    # ------------------------------------------------------------------
    @staticmethod
    def _prune_nested_paths(paths: tuple[str, ...]) -> tuple[str, ...]:
        """Drop descendants when their selected parent directory is also present."""
        if len(paths) < 2:
            return paths
        selected_directories = {
            path
            for path in paths
            if os.path.isdir(path) and not os.path.islink(path)
        }
        if not selected_directories:
            return paths

        top_level: list[str] = []
        for path in paths:
            parent = os.path.dirname(path.rstrip(os.sep))
            nested = False
            while parent and parent != path:
                if parent in selected_directories:
                    nested = True
                    break
                next_parent = os.path.dirname(parent.rstrip(os.sep))
                if next_parent == parent:
                    break
                parent = next_parent
            if not nested:
                top_level.append(path)
        return tuple(top_level)

    def _prepared_paths(
        self,
        items,
        *,
        existing_only: bool = True,
        prune_nested: bool = False,
    ) -> tuple[str, ...]:
        """Reuse an internal normalized tuple instead of rebuilding it.

        Selection, drag, and clipboard readers already return absolute, unique
        path tuples. Reusing those tuples avoids a second list/set/tuple cycle
        for very large multi-item operations. Other iterables still go through
        full normalization and validation.
        """
        if isinstance(items, tuple) and all(
            isinstance(path, str) and os.path.isabs(path) for path in items
        ):
            result = items
            if existing_only and any(not os.path.lexists(path) for path in result):
                result = tuple(path for path in result if os.path.lexists(path))
            return self._prune_nested_paths(result) if prune_nested else result
        return self._as_paths(
            items,
            existing_only=existing_only,
            prune_nested=prune_nested,
        )

    def _as_paths(
        self,
        items,
        *,
        existing_only: bool = True,
        prune_nested: bool = False,
    ) -> tuple[str, ...]:
        """Stream strings, URLs, or model indexes into a compact path tuple."""
        if items is None:
            return ()
        if isinstance(items, (str, os.PathLike)):
            iterable: Iterable = (items,)
        else:
            try:
                iterable = iter(items)
            except TypeError:
                iterable = (items,)

        unique_paths: list[str] = []
        seen: set[str] = set()
        for item in iterable:
            raw_path = ""
            if isinstance(item, (str, os.PathLike)):
                raw_path = os.fspath(item)
            elif hasattr(item, "toLocalFile"):
                try:
                    raw_path = item.toLocalFile()
                except Exception:
                    raw_path = ""
            else:
                raw_path = self._path_from_index(item)
            if not raw_path:
                continue

            normalized = os.path.abspath(os.path.expanduser(str(raw_path)))
            if normalized in seen:
                continue
            if existing_only and not os.path.lexists(normalized):
                continue
            seen.add(normalized)
            unique_paths.append(normalized)

        result = tuple(unique_paths)
        return self._prune_nested_paths(result) if prune_nested else result

    def _connect_system_clipboard(self) -> None:
        try:
            clipboard = QApplication.clipboard()
        except Exception:
            clipboard = None
        self._system_clipboard = clipboard
        if clipboard is not None:
            try:
                clipboard.dataChanged.connect(self._clipboard_changed)
            except Exception:
                pass
        self._refresh_clipboard_state()
        self._update_file_action_state(0)

    def _clipboard_changed(self) -> None:
        if self._shutting_down:
            return
        self._clipboard_revision += 1
        self._fallback_clipboard = None
        self._refresh_clipboard_state()
        self._update_file_action_state()

    def _refresh_clipboard_state(self) -> None:
        """Cache whether Paste can operate without repeatedly querying Qt."""

        mime_data = self._clipboard_mime_data()
        if mime_data is None:
            self._clipboard_has_files = False
            return
        try:
            self._clipboard_has_files = bool(
                mime_data.hasUrls()
                or mime_data.hasFormat(self.GNOME_COPIED_FILES_MIME)
            )
        except Exception:
            self._clipboard_has_files = False

    def _clipboard_mime_data(self):
        clipboard = self._system_clipboard
        if clipboard is None:
            return None
        try:
            return clipboard.mimeData()
        except Exception:
            return None

    @staticmethod
    def _mime_bytes(mime_data, mime_name: str) -> bytes:
        try:
            if not mime_data.hasFormat(mime_name):
                return b""
            return bytes(mime_data.data(mime_name))
        except Exception:
            return b""

    def _has_file_clipboard(self) -> bool:
        return bool(self._fallback_clipboard or self._clipboard_has_files)

    def _clipboard_operation(self, mime_data) -> str:
        custom = self._mime_bytes(mime_data, self.FILE_OPERATION_MIME)
        if custom.strip().lower() == b"cut":
            return "cut"

        gnome = self._mime_bytes(mime_data, self.GNOME_COPIED_FILES_MIME)
        if gnome:
            first_line = gnome.partition(b"\n")[0].rstrip(b"\r").strip().lower()
            if first_line == b"cut":
                return "cut"

        kde = self._mime_bytes(mime_data, self.KDE_CUT_SELECTION_MIME)
        if kde.strip() == b"1":
            return "cut"
        return "copy"

    def _file_clipboard_payload(self, *, existing_only: bool = True):
        fallback = self._fallback_clipboard
        if fallback:
            operation, fallback_items, token = fallback
            items = self._prepared_paths(
                fallback_items,
                existing_only=existing_only,
                prune_nested=True,
            )
            if not items:
                return None
            return operation, items, token

        mime_data = self._clipboard_mime_data()
        if mime_data is None:
            return None

        urls = ()
        try:
            if mime_data.hasUrls():
                urls = mime_data.urls()
        except Exception:
            urls = ()

        if not urls:
            gnome = self._mime_bytes(mime_data, self.GNOME_COPIED_FILES_MIME)
            if gnome:
                stream = BytesIO(gnome)
                stream.readline()
                urls = (
                    QUrl(line.decode("utf-8", errors="replace").strip())
                    for line in stream
                    if line.strip()
                )

        items = self._as_paths(
            urls,
            existing_only=existing_only,
            prune_nested=True,
        )
        if not items:
            return None
        token = self._mime_bytes(mime_data, self.FILE_CLIPBOARD_TOKEN_MIME).strip()
        return self._clipboard_operation(mime_data), items, token or None

    def _write_file_clipboard(
        self,
        operation: str,
        items: tuple[str, ...],
        *,
        token: bytes | None = None,
    ) -> bytes:
        clipboard_token = token or uuid.uuid4().hex.encode("ascii")
        clipboard = self._system_clipboard
        if clipboard is None:
            self._fallback_clipboard = (operation, items, clipboard_token)
            self._clipboard_has_files = True
            self._clipboard_revision += 1
            self._update_file_action_state()
            return clipboard_token

        mime_data = QMimeData()
        urls = [QUrl.fromLocalFile(path) for path in items]
        mime_data.setUrls(urls)
        mime_data.setData(self.FILE_OPERATION_MIME, operation.encode("ascii"))
        mime_data.setData(self.FILE_CLIPBOARD_TOKEN_MIME, clipboard_token)
        gnome_payload = bytearray(operation.encode("ascii"))
        for url in urls:
            encoded_url = bytes(url.toEncoded())
            if encoded_url:
                gnome_payload.extend(b"\n")
                gnome_payload.extend(encoded_url)
        mime_data.setData(self.GNOME_COPIED_FILES_MIME, bytes(gnome_payload))
        mime_data.setData(
            self.KDE_CUT_SELECTION_MIME,
            b"1" if operation == "cut" else b"0",
        )
        del urls, gnome_payload

        self._fallback_clipboard = None
        self._clipboard_has_files = True
        before = self._clipboard_revision
        clipboard.setMimeData(mime_data)
        if self._clipboard_revision == before:
            self._clipboard_revision += 1
            self._update_file_action_state()
        return clipboard_token

    def _clear_file_clipboard(self) -> None:
        self._fallback_clipboard = None
        self._clipboard_has_files = False
        clipboard = self._system_clipboard
        if clipboard is None:
            self._clipboard_revision += 1
            self._update_file_action_state()
            return
        before = self._clipboard_revision
        try:
            clipboard.clear()
        except Exception:
            pass
        if self._clipboard_revision == before:
            self._clipboard_revision += 1
            self._update_file_action_state()

    def _set_file_clipboard(self, operation: str, paths) -> None:
        """Publish a validated cut/copy selection to the desktop clipboard."""
        if operation not in {"cut", "copy"}:
            raise ValueError(f"unsupported clipboard operation: {operation}")
        items = self._prepared_paths(paths, prune_nested=True)
        if not items:
            title = "Cut" if operation == "cut" else "Copy"
            QMessageBox.warning(self, title, f"No valid items to {operation}.")
            return
        self._write_file_clipboard(operation, items)
        verb = "move" if operation == "cut" else "copy"
        self.status_message.emit(f"Ready to {verb} {len(items)} item(s)")

    def _finish_cut_clipboard(self, clipboard_token: bytes | None) -> None:
        """Clear only the exact cut payload that produced the completed move."""
        if clipboard_token is None:
            return
        payload = self._file_clipboard_payload(existing_only=False)
        if not payload:
            return
        operation, items, current_token = payload
        if operation != "cut" or current_token != clipboard_token:
            return
        remaining = tuple(path for path in items if os.path.lexists(path))
        if remaining:
            self._write_file_clipboard("cut", remaining, token=clipboard_token)
        else:
            self._clear_file_clipboard()

    def _paste_clipboard_to(self, dest_dir) -> None:
        payload = self._file_clipboard_payload()
        if not payload:
            self.status_message.emit("Nothing to paste")
            self._update_file_action_state()
            return
        operation, items, token = payload
        self._transfer_file_or_folder(
            items,
            dest_dir,
            operation,
            confirm_title="Confirm Paste",
            summary_title="Paste Summary",
            cut_clipboard_token=token if operation == "cut" else None,
        )

    def dropFileOrFolder(self, paths, dest_dir, operation="cut"):
        """Move a normal drop or copy a Ctrl-modified drop after confirmation."""
        return self._transfer_file_or_folder(
            paths,
            dest_dir,
            operation,
            confirm_title="Confirm Drop",
            summary_title="Drop Summary",
        )

    def _choose_transfer_destination(self, title: str) -> str | None:
        settings = QSettings(SETTINGS_ORGANIZATION, SETTINGS_APPLICATION)
        saved = str(settings.value("file_operations/last_destination", "") or "")
        initial = saved if os.path.isdir(saved) else self.currentPath()
        try:
            destination = QFileDialog.getExistingDirectory(self, title, initial)
        except Exception:
            destination = ""
        if not destination:
            return None
        destination = os.path.abspath(os.path.expanduser(str(destination)))
        if not os.path.isdir(destination):
            return None
        settings.setValue("file_operations/last_destination", destination)
        return destination

    def _transfer_selection_to_folder(self, operation: str, paths=None) -> bool:
        items = paths if paths is not None else self.selectedPaths()
        if not items:
            self.status_message.emit("Select one or more items first")
            return False
        verb = "Copy" if operation == "copy" else "Move"
        destination = self._choose_transfer_destination(f"{verb} to Folder")
        if not destination:
            return False
        return self._transfer_file_or_folder(
            items,
            destination,
            operation,
            confirm_title=f"Confirm {verb}",
            summary_title=f"{verb} Summary",
        )

    def copySelectionToFolder(self) -> bool:
        return self._transfer_selection_to_folder("copy")

    def moveSelectionToFolder(self) -> bool:
        return self._transfer_selection_to_folder("cut")

    @staticmethod
    def _merge_reports(
        report: OperationReport, preflight: OperationReport
    ) -> OperationReport:
        report.skipped += preflight.skipped
        report.same_location += preflight.same_location
        report.renamed += preflight.renamed
        report.error_count += preflight.error_count
        if preflight.details:
            report.details = (preflight.details + report.details)[
                : Tabs.MAX_UI_ERROR_DETAILS
            ]
        return report

    @staticmethod
    def _unique_destination_path(
        destination: str, reserved: set[str]
    ) -> str:
        parent = os.path.dirname(destination)
        name = os.path.basename(destination)
        root, extension = os.path.splitext(name)
        counter = 2
        while True:
            candidate = os.path.join(parent, f"{root} ({counter}){extension}")
            if candidate not in reserved and not os.path.lexists(candidate):
                return candidate
            counter += 1

    def _prompt_overwrite(self, dst_path: str, is_dir: bool) -> str:
        """Ask how to handle one existing destination, including Keep Both."""
        box = QMessageBox(self)
        try:
            box.setWindowTitle("Destination Exists")
            what = "folder" if is_dir else "file"
            box.setText(
                f"“{dst_path}” already exists.\n\n"
                f"Replace this {what}, skip it, or keep both items?"
            )
            box.setIcon(QMessageBox.Question)

            btn_yes = box.addButton("Replace", QMessageBox.YesRole)
            btn_no = box.addButton("Skip", QMessageBox.NoRole)
            btn_keep = box.addButton("Keep Both", QMessageBox.AcceptRole)
            btn_yes_all = box.addButton("Replace All", QMessageBox.YesRole)
            btn_no_all = box.addButton("Skip All", QMessageBox.NoRole)
            btn_keep_all = box.addButton(
                "Keep Both for All", QMessageBox.AcceptRole
            )
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
            if clicked is btn_keep:
                return "keep_both"
            if clicked is btn_yes_all:
                return "yes_all"
            if clicked is btn_no_all:
                return "no_all"
            if clicked is btn_keep_all:
                return "keep_both_all"
            if clicked is btn_cancel:
                return "cancel"
            return "cancel"
        finally:
            try:
                box.deleteLater()
            except Exception:
                pass

    def _transfer_file_or_folder(
        self,
        items,
        dest_dir,
        op,
        confirm_title="Confirm Paste",
        summary_title="Paste Summary",
        cut_clipboard_token: bytes | None = None,
    ) -> bool:
        """Validate and confirm a bulk transfer, then execute it off the UI thread."""
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

        sources = self._prepared_paths(items, prune_nested=True)
        if not sources:
            self._finish_cut_clipboard(cut_clipboard_token)
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
        keep_both_all = False
        preflight = OperationReport()
        plan: list[TransferItem] = []
        reserved_destinations: set[str] = set()

        for source in sources:
            if not os.path.lexists(source):
                preflight.add_error(f"{source}: source no longer exists")
                continue

            name = os.path.basename(source.rstrip(os.sep))
            destination = os.path.join(destination_dir, name)
            is_directory = os.path.isdir(source) and not os.path.islink(source)
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
                if op == "copy":
                    destination = self._unique_destination_path(
                        destination, reserved_destinations
                    )
                    destination_exists = False
                    preflight.renamed += 1
                else:
                    preflight.same_location += 1
                    continue

            if is_directory and resolved_same_or_subpath(destination, source):
                preflight.add_error(
                    f"{source}: cannot {verb} a folder into itself or a subfolder"
                )
                continue

            if destination in reserved_destinations:
                destination = self._unique_destination_path(
                    destination, reserved_destinations
                )
                destination_exists = False
                preflight.renamed += 1

            replace = False
            if destination_exists:
                if keep_both_all:
                    destination = self._unique_destination_path(
                        destination, reserved_destinations
                    )
                    preflight.renamed += 1
                elif skip_all:
                    preflight.skipped += 1
                    continue
                elif overwrite_all:
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
                    if choice in {"keep_both", "keep_both_all"}:
                        keep_both_all = choice == "keep_both_all"
                        destination = self._unique_destination_path(
                            destination, reserved_destinations
                        )
                        preflight.renamed += 1
                    else:
                        if choice == "yes_all":
                            overwrite_all = True
                        replace = True

            reserved_destinations.add(destination)
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
            self._finish_cut_clipboard(cut_clipboard_token)
            return True

        display_verb = "Moving" if op == "cut" else "Copying"
        tracked = (
            self._tracked_directory_sources(item.source for item in plan)
            if op == "cut"
            else ()
        )
        self._active_transfer_context = _TransferContext(
            preflight=preflight,
            operation=op,
            summary_title=summary_title,
            display_verb=display_verb,
            clipboard_token=cut_clipboard_token,
        )
        if not self._begin_file_operation(f"{display_verb} items…", len(plan)):
            self._active_transfer_context = None
            return False

        worker = self.file_tasks.submit(
            execute_transfer,
            plan,
            op == "cut",
            with_progress=True,
            track_moved_directories=tracked,
            on_progress=self._transfer_progress,
            on_result=self._transfer_completed,
            on_error=self._transfer_worker_error,
            on_finished=self._release_file_operation,
        )
        if worker is None:
            self._active_transfer_context = None
            self._release_file_operation()
            self.operation_finished.emit("File operation could not be started")
            return False
        return True

    def _transfer_progress(self, payload) -> None:
        context = self._active_transfer_context
        self._file_operation_progress(
            payload,
            context.display_verb if context is not None else "Transferring",
        )

    def _transfer_completed(self, report: OperationReport) -> None:
        context, self._active_transfer_context = self._active_transfer_context, None
        if context is None:
            context = _TransferContext(
                preflight=OperationReport(),
                operation="copy",
                summary_title="File Operation Summary",
                display_verb="Copying",
            )
        report = self._merge_reports(report, context.preflight)
        for old_path, new_path in report.moved_directories:
            self._retarget_open_tabs(old_path, new_path)

        if context.operation == "cut":
            self._finish_cut_clipboard(context.clipboard_token)

        self._show_report_errors(context.summary_title, report)
        self.refreshCurrentTab()

        past_tense = "Moved" if context.operation == "cut" else "Copied"
        parts = [f"{past_tense} {report.completed} item(s)"]
        if report.renamed:
            parts.append(f"{report.renamed} kept with a new name")
        if report.same_location:
            parts.append(f"{report.same_location} already there")
        if report.skipped:
            parts.append(f"{report.skipped} skipped")
        if report.error_count:
            parts.append(f"{report.error_count} failed")
        self.operation_finished.emit("; ".join(parts))

    def _transfer_worker_error(self, error: dict[str, str]) -> None:
        context, self._active_transfer_context = self._active_transfer_context, None
        display_verb = context.display_verb if context is not None else "Transfer"
        QMessageBox.critical(
            self,
            f"{display_verb} Failed",
            error.get("message", "Unknown error"),
        )
        self.operation_finished.emit(f"{display_verb} failed")

    # ------------------------------------------------------------------
    # Open With...
    # ------------------------------------------------------------------
    def open_with(self, items):
        """Prompt for a program and open selected file(s) with it."""
        if not items:
            return

        file_paths = tuple(
            path
            for path in self._prepared_paths(items, prune_nested=False)
            if not os.path.isdir(path)
        )

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
        if not self._replace_shared_model():
            self._request_model_recycle(force=True)

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
