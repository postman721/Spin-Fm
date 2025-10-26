#!/usr/bin/env python3
# qt_compat.py
# Prefer PyQt6, fall back to PyQt5, and expose PyQt5-like API.

import sys
sys.dont_write_bytecode = True

try:
    from PyQt6 import QtCore, QtWidgets, QtGui  # Prefer PyQt6
    USING_PYQT6 = True
except Exception:
    from PyQt5 import QtCore, QtWidgets, QtGui  # Fallback to PyQt5
    USING_PYQT6 = False

# Print once
if not getattr(sys, "_qt_compat_printed", False):
    print(f"[qt_compat] Using {'PyQt6' if USING_PYQT6 else 'PyQt5'} backend.")
    sys._qt_compat_printed = True

# -----------------
# Re-exports
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

# QAction moved in PyQt6
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

# QFileSystemModel location differs
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
    # Allow legacy exec_ names
    if not hasattr(QApplication, "exec_"):
        QApplication.exec_ = QApplication.exec  # type: ignore[attr-defined]
    if not hasattr(QMenu, "exec_"):
        QMenu.exec_ = QMenu.exec  # type: ignore[attr-defined]

    # QMessageBox standard buttons aliases
    if not hasattr(QMessageBox, "Yes"):
        QMessageBox.Yes = QMessageBox.StandardButton.Yes
    if not hasattr(QMessageBox, "No"):
        QMessageBox.No = QMessageBox.StandardButton.No
    if not hasattr(QMessageBox, "Ok"):
        QMessageBox.Ok = QMessageBox.StandardButton.Ok
    if not hasattr(QMessageBox, "Cancel"):
        QMessageBox.Cancel = QMessageBox.StandardButton.Cancel

    # QStyle SP_* aliases (PyQt5-style names)
    for name in ("SP_ArrowBack", "SP_ArrowForward", "SP_DirHomeIcon", "SP_TrashIcon"):
        if not hasattr(QStyle, name):
            setattr(QStyle, name, getattr(QStyle.StandardPixmap, name))

    # Qt enum aliases (PyQt5-style surface)
    class _QtAlias:
        Horizontal = QtCore.Qt.Orientation.Horizontal
        Vertical = QtCore.Qt.Orientation.Vertical
        UserRole = QtCore.Qt.ItemDataRole.UserRole
        CustomContextMenu = QtCore.Qt.ContextMenuPolicy.CustomContextMenu
        # Arrow + modality (PyQt5-style names)
        LeftArrow = QtCore.Qt.ArrowType.LeftArrow
        RightArrow = QtCore.Qt.ArrowType.RightArrow
        UpArrow = QtCore.Qt.ArrowType.UpArrow
        DownArrow = QtCore.Qt.ArrowType.DownArrow
        ApplicationModal = QtCore.Qt.WindowModality.ApplicationModal
    Qt = _QtAlias()

    # QDir filter flags (PyQt5-style aliases)
    try:
        QDir.AllEntries     = QDir.Filter.AllEntries
        QDir.NoDotAndDotDot = QDir.Filter.NoDotAndDotDot
        QDir.AllDirs        = QDir.Filter.AllDirs
        QDir.Hidden         = QDir.Filter.Hidden
    except Exception:
        pass

    # QListView enum aliases
    try:
        QListView.LeftToRight = QListView.Flow.LeftToRight  # type: ignore[attr-defined]
    except Exception:
        pass
    try:
        QListView.IconMode = QListView.ViewMode.IconMode  # type: ignore[attr-defined]
    except Exception:
        pass

    # QTableWidget enum mappings (PyQt5-style)
    try:
        from PyQt6.QtWidgets import QAbstractItemView
        QTableWidget.NoEditTriggers = QAbstractItemView.EditTrigger.NoEditTriggers  # type: ignore[attr-defined]
        QTableWidget.SelectRows     = QAbstractItemView.SelectionBehavior.SelectRows  # type: ignore[attr-defined]
        QTableWidget.SingleSelection= QAbstractItemView.SelectionMode.SingleSelection  # type: ignore[attr-defined]
    except Exception:
        pass

else:
    # PyQt5 forward-compat: also provide .exec (no underscore)
    if not hasattr(QApplication, "exec"):
        QApplication.exec = QApplication.exec_  # type: ignore[attr-defined]
    if not hasattr(QMenu, "exec"):
        QMenu.exec = QMenu.exec_  # type: ignore[attr-defined]
    # Native Qt on PyQt5
    Qt = QtCore.Qt
