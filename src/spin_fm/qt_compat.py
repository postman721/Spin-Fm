"""Small PyQt6/PyQt5 compatibility surface used by Spin FM.

PyQt6 is preferred. PyQt5 remains supported so the application can run on
older Debian-family systems without maintaining two UI implementations.
"""

from __future__ import annotations

try:
    from PyQt6 import QtCore, QtGui, QtWidgets

    USING_PYQT6 = True
except ImportError:
    try:
        from PyQt5 import QtCore, QtGui, QtWidgets

        USING_PYQT6 = False
    except ImportError as pyqt5_error:
        raise ImportError(
            "Spin FM requires PyQt6 or PyQt5. Install python3-pyqt6 "
            "(preferred) or python3-pyqt5."
        ) from pyqt5_error

# QtCore
QObject = QtCore.QObject
QRunnable = QtCore.QRunnable
QThreadPool = QtCore.QThreadPool
QTimer = QtCore.QTimer
QPoint = QtCore.QPoint
QSize = QtCore.QSize
QSettings = QtCore.QSettings
QDir = QtCore.QDir
QEvent = QtCore.QEvent
QRect = QtCore.QRect
pyqtSignal = QtCore.pyqtSignal
pyqtSlot = QtCore.pyqtSlot
pyqtProperty = QtCore.pyqtProperty
pyqtClassInfo = getattr(QtCore, "pyqtClassInfo", None)

# QtWidgets
QApplication = QtWidgets.QApplication
QMainWindow = QtWidgets.QMainWindow
QDialog = QtWidgets.QDialog
QDialogButtonBox = QtWidgets.QDialogButtonBox
QSplitter = QtWidgets.QSplitter
QMessageBox = QtWidgets.QMessageBox
QStatusBar = QtWidgets.QStatusBar
QWidget = QtWidgets.QWidget
QFrame = QtWidgets.QFrame
QVBoxLayout = QtWidgets.QVBoxLayout
QHBoxLayout = QtWidgets.QHBoxLayout
QLabel = QtWidgets.QLabel
QTableWidget = QtWidgets.QTableWidget
QTableWidgetItem = QtWidgets.QTableWidgetItem
QPushButton = QtWidgets.QPushButton
QMenu = QtWidgets.QMenu
QTabWidget = QtWidgets.QTabWidget
QToolBar = QtWidgets.QToolBar
QToolButton = QtWidgets.QToolButton
QLineEdit = QtWidgets.QLineEdit
QInputDialog = QtWidgets.QInputDialog
QListView = QtWidgets.QListView
QAbstractItemView = QtWidgets.QAbstractItemView
QTabBar = QtWidgets.QTabBar
QStyle = QtWidgets.QStyle
QStyleFactory = QtWidgets.QStyleFactory
QProgressBar = QtWidgets.QProgressBar
QSlider = QtWidgets.QSlider
QHeaderView = QtWidgets.QHeaderView
QSizePolicy = QtWidgets.QSizePolicy
QStyledItemDelegate = QtWidgets.QStyledItemDelegate
QStyleOptionViewItem = QtWidgets.QStyleOptionViewItem

# QFileSystemModel and QAction moved in Qt6.
if USING_PYQT6:
    QFileSystemModel = QtGui.QFileSystemModel
    QAction = QtGui.QAction
    QActionGroup = QtGui.QActionGroup
else:
    QFileSystemModel = QtWidgets.QFileSystemModel
    QAction = QtWidgets.QAction
    QActionGroup = QtWidgets.QActionGroup

QIcon = QtGui.QIcon
QPixmapCache = QtGui.QPixmapCache
QGuiApplication = QtGui.QGuiApplication


if USING_PYQT6:
    # PyQt5-shaped exec helpers.
    if not hasattr(QApplication, "exec_"):
        QApplication.exec_ = lambda self: self.exec()  # type: ignore[attr-defined]
    if not hasattr(QMenu, "exec_"):
        QMenu.exec_ = lambda self, *a, **kw: self.exec(*a, **kw)  # type: ignore[attr-defined]
    if not hasattr(QMessageBox, "exec_"):
        QMessageBox.exec_ = lambda self: self.exec()  # type: ignore[attr-defined]
    if not hasattr(QDialog, "exec_"):
        QDialog.exec_ = lambda self: self.exec()  # type: ignore[attr-defined]

    # QMessageBox aliases.
    for name in ("Yes", "No", "Ok", "Cancel", "Close"):
        if not hasattr(QMessageBox, name):
            setattr(QMessageBox, name, getattr(QMessageBox.StandardButton, name))
    for name in ("Question", "Information", "Warning", "Critical"):
        if not hasattr(QMessageBox, name):
            setattr(QMessageBox, name, getattr(QMessageBox.Icon, name))
    for name in ("YesRole", "NoRole", "RejectRole", "AcceptRole"):
        if not hasattr(QMessageBox, name):
            setattr(QMessageBox, name, getattr(QMessageBox.ButtonRole, name))

    # Dialog aliases keep the application code identical on PyQt5 and PyQt6.
    for name in ("Accepted", "Rejected"):
        if not hasattr(QDialog, name):
            setattr(QDialog, name, getattr(QDialog.DialogCode, name))
    for name in ("Open", "Cancel"):
        if not hasattr(QDialogButtonBox, name):
            setattr(
                QDialogButtonBox,
                name,
                getattr(QDialogButtonBox.StandardButton, name),
            )

    # QStyle aliases used by themed fallback icons.
    for name in (
        "SP_ArrowBack",
        "SP_ArrowForward",
        "SP_ArrowUp",
        "SP_DirHomeIcon",
        "SP_DirIcon",
        "SP_TrashIcon",
        "SP_FileIcon",
        "SP_FileDialogNewFolder",
        "SP_BrowserReload",
        "SP_DriveHDIcon",
        "SP_DriveFDIcon",
        "SP_MessageBoxInformation",
        "SP_DialogCloseButton",
        "SP_DialogOpenButton",
        "SP_MediaPlay",
        "SP_MediaPause",
        "SP_MediaStop",
        "SP_MediaSeekBackward",
        "SP_MediaSeekForward",
        "SP_MediaSkipBackward",
        "SP_MediaSkipForward",
        "SP_MediaVolume",
        "SP_MediaVolumeMuted",
    ):
        if not hasattr(QStyle, name):
            try:
                setattr(QStyle, name, getattr(QStyle.StandardPixmap, name))
            except AttributeError:
                # A few older Qt builds do not expose every media pixmap.
                pass

    class _QtAlias:
        Horizontal = QtCore.Qt.Orientation.Horizontal
        Vertical = QtCore.Qt.Orientation.Vertical
        UserRole = QtCore.Qt.ItemDataRole.UserRole
        DisplayRole = QtCore.Qt.ItemDataRole.DisplayRole
        CustomContextMenu = QtCore.Qt.ContextMenuPolicy.CustomContextMenu
        LeftArrow = QtCore.Qt.ArrowType.LeftArrow
        RightArrow = QtCore.Qt.ArrowType.RightArrow
        UpArrow = QtCore.Qt.ArrowType.UpArrow
        DownArrow = QtCore.Qt.ArrowType.DownArrow
        ApplicationModal = QtCore.Qt.WindowModality.ApplicationModal
        WidgetShortcut = QtCore.Qt.ShortcutContext.WidgetShortcut
        WidgetWithChildrenShortcut = (
            QtCore.Qt.ShortcutContext.WidgetWithChildrenShortcut
        )
        WindowShortcut = QtCore.Qt.ShortcutContext.WindowShortcut
        ApplicationShortcut = QtCore.Qt.ShortcutContext.ApplicationShortcut
        Key_P = QtCore.Qt.Key.Key_P
        Key_M = QtCore.Qt.Key.Key_M
        AltModifier = QtCore.Qt.KeyboardModifier.AltModifier
        ControlModifier = QtCore.Qt.KeyboardModifier.ControlModifier
        ShiftModifier = QtCore.Qt.KeyboardModifier.ShiftModifier
        MetaModifier = QtCore.Qt.KeyboardModifier.MetaModifier
        PointingHandCursor = QtCore.Qt.CursorShape.PointingHandCursor
        LeftButton = QtCore.Qt.MouseButton.LeftButton
        CopyAction = QtCore.Qt.DropAction.CopyAction
        MoveAction = QtCore.Qt.DropAction.MoveAction
        LinkAction = QtCore.Qt.DropAction.LinkAction
        IgnoreAction = QtCore.Qt.DropAction.IgnoreAction
        ElideMiddle = QtCore.Qt.TextElideMode.ElideMiddle
        ElideNone = QtCore.Qt.TextElideMode.ElideNone
        AlignLeft = QtCore.Qt.AlignmentFlag.AlignLeft
        AlignRight = QtCore.Qt.AlignmentFlag.AlignRight
        AlignVCenter = QtCore.Qt.AlignmentFlag.AlignVCenter
        AlignCenter = QtCore.Qt.AlignmentFlag.AlignCenter
        AlignHCenter = QtCore.Qt.AlignmentFlag.AlignHCenter
        AlignTop = QtCore.Qt.AlignmentFlag.AlignTop
        TextWordWrap = QtCore.Qt.TextFlag.TextWordWrap
        TextWrapAnywhere = QtCore.Qt.TextFlag.TextWrapAnywhere

    Qt = _QtAlias()

    for name in ("KeyPress", "ShortcutOverride"):
        if not hasattr(QEvent, name):
            setattr(QEvent, name, getattr(QEvent.Type, name))

    # QDir filter aliases.
    for name in ("AllEntries", "NoDotAndDotDot", "AllDirs", "Hidden"):
        try:
            setattr(QDir, name, getattr(QDir.Filter, name))
        except Exception:
            pass

    # QListView aliases.
    list_aliases = {
        "LeftToRight": (QListView.Flow, "LeftToRight"),
        "IconMode": (QListView.ViewMode, "IconMode"),
        "Batched": (QListView.LayoutMode, "Batched"),
        "Adjust": (QListView.ResizeMode, "Adjust"),
        "Static": (QListView.Movement, "Static"),
    }
    for alias, (owner, name) in list_aliases.items():
        try:
            setattr(QListView, alias, getattr(owner, name))
        except Exception:
            pass

    # Abstract item-view aliases.
    abstract_aliases = {
        "SingleSelection": (QAbstractItemView.SelectionMode, "SingleSelection"),
        "ExtendedSelection": (QAbstractItemView.SelectionMode, "ExtendedSelection"),
        "NoDragDrop": (QAbstractItemView.DragDropMode, "NoDragDrop"),
        "DragOnly": (QAbstractItemView.DragDropMode, "DragOnly"),
        "DropOnly": (QAbstractItemView.DragDropMode, "DropOnly"),
        "DragDrop": (QAbstractItemView.DragDropMode, "DragDrop"),
        "InternalMove": (QAbstractItemView.DragDropMode, "InternalMove"),
        "ScrollPerPixel": (QAbstractItemView.ScrollMode, "ScrollPerPixel"),
        "NoEditTriggers": (QAbstractItemView.EditTrigger, "NoEditTriggers"),
        "SelectRows": (QAbstractItemView.SelectionBehavior, "SelectRows"),
    }
    for alias, (owner, name) in abstract_aliases.items():
        try:
            setattr(QAbstractItemView, alias, getattr(owner, name))
        except Exception:
            pass

    for alias in ("SingleSelection", "ExtendedSelection"):
        try:
            setattr(QListView, alias, getattr(QAbstractItemView, alias))
        except Exception:
            pass

    for alias in ("NoEditTriggers", "SelectRows", "SingleSelection"):
        try:
            setattr(QTableWidget, alias, getattr(QAbstractItemView, alias))
        except Exception:
            pass

    # QStyleOptionViewItem aliases used by custom item delegates.
    for alias, owner_name in (("WrapText", "ViewItemFeature"), ("Top", "Position")):
        if hasattr(QStyleOptionViewItem, alias):
            continue
        try:
            owner = getattr(QStyleOptionViewItem, owner_name)
            setattr(QStyleOptionViewItem, alias, getattr(owner, alias))
        except Exception:
            pass

    for name in ("Stretch", "ResizeToContents", "Interactive", "Fixed"):
        try:
            setattr(QHeaderView, name, getattr(QHeaderView.ResizeMode, name))
        except Exception:
            pass

    for name in ("Expanding", "Preferred", "Minimum", "Fixed"):
        try:
            setattr(QSizePolicy, name, getattr(QSizePolicy.Policy, name))
        except Exception:
            pass
else:
    if not hasattr(QApplication, "exec"):
        QApplication.exec = QApplication.exec_  # type: ignore[attr-defined]
    if not hasattr(QMenu, "exec"):
        QMenu.exec = QMenu.exec_  # type: ignore[attr-defined]
    if not hasattr(QDialog, "exec"):
        QDialog.exec = QDialog.exec_  # type: ignore[attr-defined]
    Qt = QtCore.Qt
