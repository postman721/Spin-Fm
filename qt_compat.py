#!/usr/bin/env python3
"""PyQt6/PyQt5 compatibility helpers for Spin FM.

The project prefers PyQt6 when it is available, but it still supports PyQt5.
This module exposes a mostly PyQt5-shaped API surface so the rest of the
application can stay small and readable.
"""

import sys

sys.dont_write_bytecode = True

try:
    from PyQt6 import QtCore, QtWidgets, QtGui  # Prefer PyQt6.
    USING_PYQT6 = True
except Exception:
    from PyQt5 import QtCore, QtWidgets, QtGui  # Fallback to PyQt5.
    USING_PYQT6 = False

# Print the selected backend once so startup diagnostics stay readable.
if not getattr(sys, "_qt_compat_printed", False):
    print(f"[qt_compat] Using {'PyQt6' if USING_PYQT6 else 'PyQt5'} backend.")
    sys._qt_compat_printed = True

# -----------------
# Re-exports used by the rest of the application
# -----------------
QObject = QtCore.QObject
pyqtSignal = QtCore.pyqtSignal
QTimer = QtCore.QTimer
QPoint = QtCore.QPoint
QSettings = QtCore.QSettings
QDir = QtCore.QDir

QApplication = QtWidgets.QApplication
QMainWindow = QtWidgets.QMainWindow
QSplitter = QtWidgets.QSplitter
QMessageBox = QtWidgets.QMessageBox
QStatusBar = QtWidgets.QStatusBar

# QAction moved from QtWidgets to QtGui in PyQt6.
if USING_PYQT6:
    QAction = QtGui.QAction
else:
    QAction = QtWidgets.QAction

QWidget = QtWidgets.QWidget
QVBoxLayout = QtWidgets.QVBoxLayout
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

# QFileSystemModel lives in different Qt modules depending on the binding.
if USING_PYQT6:
    from PyQt6.QtGui import QFileSystemModel  # type: ignore
else:
    QFileSystemModel = QtWidgets.QFileSystemModel  # type: ignore

QTabBar = QtWidgets.QTabBar
QStyle = QtWidgets.QStyle
QProgressDialog = QtWidgets.QProgressDialog
QIcon = QtGui.QIcon

# -----------------
# Compatibility surface
# -----------------
if USING_PYQT6:
    # Keep PyQt5-style exec_ names available. Assign small wrapper methods
    # instead of copying the built-in Qt method object directly, because some
    # PyQt6 bindings expose QDialog.exec in a way that becomes an unbound method
    # when reattached to QMessageBox, which then crashes at runtime.
    if not hasattr(QApplication, "exec_"):
        def _application_exec_(self):
            return self.exec()
        QApplication.exec_ = _application_exec_  # type: ignore[attr-defined]
    if not hasattr(QMenu, "exec_"):
        def _menu_exec_(self, *args, **kwargs):
            return self.exec(*args, **kwargs)
        QMenu.exec_ = _menu_exec_  # type: ignore[attr-defined]
    if not hasattr(QMessageBox, "exec_"):
        def _messagebox_exec_(self):
            return self.exec()
        QMessageBox.exec_ = _messagebox_exec_  # type: ignore[attr-defined]

    # QMessageBox standard button / icon / role aliases.
    if not hasattr(QMessageBox, "Yes"):
        QMessageBox.Yes = QMessageBox.StandardButton.Yes
    if not hasattr(QMessageBox, "No"):
        QMessageBox.No = QMessageBox.StandardButton.No
    if not hasattr(QMessageBox, "Ok"):
        QMessageBox.Ok = QMessageBox.StandardButton.Ok
    if not hasattr(QMessageBox, "Cancel"):
        QMessageBox.Cancel = QMessageBox.StandardButton.Cancel

    if not hasattr(QMessageBox, "Question"):
        QMessageBox.Question = QMessageBox.Icon.Question
    if not hasattr(QMessageBox, "Information"):
        QMessageBox.Information = QMessageBox.Icon.Information
    if not hasattr(QMessageBox, "Warning"):
        QMessageBox.Warning = QMessageBox.Icon.Warning
    if not hasattr(QMessageBox, "Critical"):
        QMessageBox.Critical = QMessageBox.Icon.Critical

    if not hasattr(QMessageBox, "YesRole"):
        QMessageBox.YesRole = QMessageBox.ButtonRole.YesRole
    if not hasattr(QMessageBox, "NoRole"):
        QMessageBox.NoRole = QMessageBox.ButtonRole.NoRole
    if not hasattr(QMessageBox, "RejectRole"):
        QMessageBox.RejectRole = QMessageBox.ButtonRole.RejectRole

    # QStyle SP_* aliases (PyQt5-style names).
    for name in (
        "SP_ArrowBack",
        "SP_ArrowForward",
        "SP_DirHomeIcon",
        "SP_TrashIcon",
        "SP_FileIcon",
        "SP_FileDialogNewFolder",
    ):
        if not hasattr(QStyle, name):
            setattr(QStyle, name, getattr(QStyle.StandardPixmap, name))

    # Qt enum aliases so older PyQt5-style code keeps working.
    class _QtAlias:
        Horizontal = QtCore.Qt.Orientation.Horizontal
        Vertical = QtCore.Qt.Orientation.Vertical
        UserRole = QtCore.Qt.ItemDataRole.UserRole
        CustomContextMenu = QtCore.Qt.ContextMenuPolicy.CustomContextMenu

        # Arrow + modality (PyQt5-style names).
        LeftArrow = QtCore.Qt.ArrowType.LeftArrow
        RightArrow = QtCore.Qt.ArrowType.RightArrow
        UpArrow = QtCore.Qt.ArrowType.UpArrow
        DownArrow = QtCore.Qt.ArrowType.DownArrow
        ApplicationModal = QtCore.Qt.WindowModality.ApplicationModal

        # Shortcut contexts used by the file views.
        WidgetShortcut = QtCore.Qt.ShortcutContext.WidgetShortcut
        WidgetWithChildrenShortcut = QtCore.Qt.ShortcutContext.WidgetWithChildrenShortcut

        # Cursor shape aliases.
        PointingHandCursor = QtCore.Qt.CursorShape.PointingHandCursor

    Qt = _QtAlias()

    # QDir filter flag aliases.
    try:
        QDir.AllEntries = QDir.Filter.AllEntries
        QDir.NoDotAndDotDot = QDir.Filter.NoDotAndDotDot
        QDir.AllDirs = QDir.Filter.AllDirs
        QDir.Hidden = QDir.Filter.Hidden
    except Exception:
        pass

    # QListView enum aliases.
    try:
        QListView.LeftToRight = QListView.Flow.LeftToRight  # type: ignore[attr-defined]
    except Exception:
        pass
    try:
        QListView.IconMode = QListView.ViewMode.IconMode  # type: ignore[attr-defined]
    except Exception:
        pass
    try:
        QListView.Batched = QListView.LayoutMode.Batched  # type: ignore[attr-defined]
    except Exception:
        pass

    # Selection mode aliases (PyQt5-style surface) for QListView/QAbstractItemView.
    try:
        QAbstractItemView.SingleSelection = QAbstractItemView.SelectionMode.SingleSelection  # type: ignore[attr-defined]
        QAbstractItemView.ExtendedSelection = QAbstractItemView.SelectionMode.ExtendedSelection  # type: ignore[attr-defined]
        QListView.SingleSelection = QAbstractItemView.SelectionMode.SingleSelection  # type: ignore[attr-defined]
        QListView.ExtendedSelection = QAbstractItemView.SelectionMode.ExtendedSelection  # type: ignore[attr-defined]
    except Exception:
        pass

    # QTableWidget enum mappings (PyQt5-style names).
    try:
        QTableWidget.NoEditTriggers = QAbstractItemView.EditTrigger.NoEditTriggers  # type: ignore[attr-defined]
        QTableWidget.SelectRows = QAbstractItemView.SelectionBehavior.SelectRows  # type: ignore[attr-defined]
        QTableWidget.SingleSelection = QAbstractItemView.SelectionMode.SingleSelection  # type: ignore[attr-defined]
    except Exception:
        pass

else:
    # PyQt5 forward-compat: also provide .exec without underscore.
    if not hasattr(QApplication, "exec"):
        QApplication.exec = QApplication.exec_  # type: ignore[attr-defined]
    if not hasattr(QMenu, "exec"):
        QMenu.exec = QMenu.exec_  # type: ignore[attr-defined]

    # Native Qt enums already have the old layout in PyQt5.
    Qt = QtCore.Qt
