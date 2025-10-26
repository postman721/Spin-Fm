#!/usr/bin/env python3
# tabs.py
import sys
sys.dont_write_bytecode = True

import os
import shutil
import subprocess

from qt_compat import (
    QWidget, QVBoxLayout, QToolBar, QToolButton, QLineEdit, QTabWidget,
    QMessageBox, QMenu, QAction, QInputDialog, QListView,
    QFileSystemModel, QTabBar, QStyle, Qt, pyqtSignal, QDir
)

# Cross-Qt QSize (for icon sizing)
try:
    from PyQt6.QtCore import QSize
except Exception:
    from PyQt5.QtCore import QSize


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
        if tab_index > 0:
            context_menu = QMenu(self)
            close_action = QAction("Close Tab", self)
            close_action.triggered.connect(lambda: self.closeTabRequested.emit(tab_index))
            context_menu.addAction(close_action)
            pos = self.mapToGlobal(position)
            if hasattr(context_menu, "exec"):
                context_menu.exec(pos)      # PyQt6
            else:
                context_menu.exec_(pos)     # PyQt5


class Tabs(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)

        # Clipboard state
        self.clipboard = None  # ('cut' or 'copy', [paths])

        # History per tab index: {"back": [paths], "forward": [paths]}
        self.history = {}

        self.layout = QVBoxLayout(self)

        # Toolbar (larger icon size)
        self.toolbar = QToolBar(self)
        self.toolbar.setIconSize(QSize(28, 28))  # make toolbar icons bigger
        self.layout.addWidget(self.toolbar)

        # Back / Forward
        self.back_button = QToolButton()
        self.back_button.setIcon(self.style().standardIcon(QStyle.SP_ArrowBack))
        self.back_button.clicked.connect(self.goBack)
        self.toolbar.addWidget(self.back_button)

        self.forward_button = QToolButton()
        self.forward_button.setIcon(self.style().standardIcon(QStyle.SP_ArrowForward))
        self.forward_button.clicked.connect(self.goForward)
        self.toolbar.addWidget(self.forward_button)

        # Home / Trash
        self.home_button = QToolButton()
        self.home_button.setIcon(self.style().standardIcon(QStyle.SP_DirHomeIcon))
        self.home_button.clicked.connect(self.goHome)
        self.toolbar.addWidget(self.home_button)

        self.trash_button = QToolButton()
        self.trash_button.setIcon(self.style().standardIcon(QStyle.SP_TrashIcon))
        self.trash_button.clicked.connect(self.goTrash)
        self.toolbar.addWidget(self.trash_button)

        # Address bar
        self.address_bar = QLineEdit(self)
        self.address_bar.returnPressed.connect(self.navigateToPath)
        self.toolbar.addWidget(self.address_bar)

        # Tabs
        self.tab_widget = QTabWidget(self)
        bar = CustomTabBar(self.tab_widget)
        bar.closeTabRequested.connect(self.closeTab)
        bar.tabDoubleClicked.connect(self.duplicateTab)
        self.tab_widget.setTabBar(bar)

        # Show "x" close buttons on tabs
        self.tab_widget.setTabsClosable(True)
        self.tab_widget.tabCloseRequested.connect(self.closeTab)

        self.layout.addWidget(self.tab_widget)

        # First tab
        self.createNewTab(os.path.expanduser("~"))

    # -------- Tab & view management --------
    def createNewTab(self, path):
        view = QListView()
        model = QFileSystemModel(view)
        model.setRootPath(path)
        # Default filters (hidden handled by update_hidden_files)
        try:
            model.setFilter(QDir.AllEntries | QDir.NoDotAndDotDot | QDir.AllDirs)
        except Exception:
            model.setFilter(QDir.AllEntries)

        view.setModel(model)
        root_index = model.index(path)
        view.setRootIndex(root_index)
        view.setViewMode(QListView.IconMode)

        # Make file/folder icons bigger in the view
        view.setIconSize(QSize(64, 64))

        try:
            view.setSelectionMode(QListView.ExtendedSelection)
        except Exception:
            pass

        # Context menu & activation
        view.setContextMenuPolicy(Qt.CustomContextMenu)
        view.customContextMenuRequested.connect(lambda pos, v=view: self.openFileContextMenu(pos, v))
        view.doubleClicked.connect(lambda idx, v=view: self.onFileActivated(idx, v))

        idx = self.tab_widget.addTab(view, os.path.basename(path) or path)
        self.tab_widget.setCurrentIndex(idx)
        self.address_bar.setText(path)

        # init history for this tab
        self.history[idx] = {"back": [], "forward": []}

    def addNewTab(self, path):
        return self.createNewTab(path)

    def duplicateTab(self, index):
        if index < 0:
            return
        view = self.tab_widget.widget(index)
        if not view:
            return
        path = view.model().filePath(view.rootIndex())
        self.createNewTab(path)

    def closeTab(self, index):
        # keep first tab protected from closing
        if index <= 0:
            return
        self.tab_widget.removeTab(index)
        self.history.pop(index, None)
        # Compact history dict keys
        new_hist = {}
        for i in range(self.tab_widget.count()):
            new_hist[i] = self.history.get(i, {"back": [], "forward": []})
        self.history = new_hist

    def currentView(self):
        return self.tab_widget.currentWidget()

    def currentPath(self):
        v = self.currentView()
        if v is None:
            return os.path.expanduser("~")
        return v.model().filePath(v.rootIndex())

    def refreshCurrentTab(self):
        v = self.currentView()
        if v is None:
            return
        path = v.model().filePath(v.rootIndex())
        v.model().setRootPath(path)
        v.setRootIndex(v.model().index(path))

    # -------- Navigation (history with back/forward stacks) --------
    def goBack(self):
        idx = self.tab_widget.currentIndex()
        hist = self.history.get(idx, {"back": [], "forward": []})
        if not hist["back"]:
            return
        cur = self.currentPath()
        prev = hist["back"].pop()
        # push current onto forward
        hist["forward"].append(cur)
        self._navigateTo(prev, push=False)
        self.history[idx] = hist

    def goForward(self):
        idx = self.tab_widget.currentIndex()
        hist = self.history.get(idx, {"back": [], "forward": []})
        if not hist["forward"]:
            return
        cur = self.currentPath()
        nxt = hist["forward"].pop()
        # push current onto back
        hist["back"].append(cur)
        self._navigateTo(nxt, push=False)
        self.history[idx] = hist

    def goHome(self):
        self._navigateTo(os.path.expanduser("~"))

    def goTrash(self):
        xdg = os.path.expanduser("~/.local/share/Trash/files")
        path = xdg if os.path.isdir(xdg) else os.path.expanduser("~/.local/share/Trash")
        if not os.path.isdir(path):
            path = "/"
        self._navigateTo(path)

    def navigateToPath(self):
        target = self.address_bar.text().strip() or os.path.expanduser("~")
        self._navigateTo(target)

    def _navigateTo(self, path, push=True):
        # Normalize target
        path = os.path.abspath(os.path.expanduser(path))
        if not os.path.exists(path):
            QMessageBox.warning(self, "Not Found", f"Path does not exist:\n{path}")
            return

        view = self.currentView()
        if view is None:
            return

        # Capture previous path BEFORE changing the view
        prev = self.currentPath()
        idx = self.tab_widget.currentIndex()

        # Update history stacks if we are pushing a new location
        if push and prev != path:
            hist = self.history.get(idx, {"back": [], "forward": []})
            hist["back"].append(prev)   # we are leaving 'prev'
            hist["forward"].clear()     # new branch
            self.history[idx] = hist

        # Now actually navigate
        model = view.model()
        model.setRootPath(path)
        view.setRootIndex(model.index(path))
        self.address_bar.setText(path)

    # -------- File activation --------
    def onFileActivated(self, index, file_view):
        model = file_view.model()
        path = model.filePath(index)
        if os.path.isdir(path):
            self._navigateTo(path)
        else:
            self.opens_me([index])

    # -------- Context menu --------
    def openFileContextMenu(self, position, file_view):
        context_menu = QMenu(self)
        selected_indexes = file_view.selectionModel().selectedIndexes()

        if selected_indexes:
            # Gather selection -> paths
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

            # Delete / Cut / Copy (+ Rename if single)
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

                rename_action = QAction("Rename", self)
                rename_action.triggered.connect(lambda: self.renameFileOrFolder(paths, file_view))
                context_menu.addAction(rename_action)

            # Paste (to current root)
            paste_action = QAction("Paste", self)
            paste_action.setEnabled(self.clipboard is not None)
            paste_action.triggered.connect(
                lambda: self.pasteFileOrFolder(file_view.model().filePath(file_view.rootIndex()))
            )
            context_menu.addAction(paste_action)

            # --- Open With... (uses current selection at click time) ---
            open_with_action = QAction("Open With...", self)
            open_with_action.triggered.connect(
                lambda _, v=file_view: self.open_with(v.selectionModel().selectedIndexes())
            )
            context_menu.addAction(open_with_action)

        else:
            # Nothing selected -> new file/folder + paste
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

        pos = file_view.viewport().mapToGlobal(position)
        if hasattr(context_menu, "exec"):
            context_menu.exec(pos)      # PyQt6
        else:
            context_menu.exec_(pos)     # PyQt5

    # -------- File operations --------
    
    def opens_me(self, selected_indexes):
        """
        Opens the selected file(s) using the system default application (xdg-open).
        Falls back to 'Open With...' prompt if default open fails.
        """
        if not selected_indexes:
            return
        try:
            view = self.currentView()
            if view is None:
                return
            model = view.model()

            for idx in selected_indexes:
                try:
                    path = model.filePath(idx)
                    if not os.path.isfile(path):
                        continue  # skip folders

                    # Try default app (Linux)
                    proc = subprocess.Popen(["xdg-open", path])
                    proc.wait(timeout=1)  # quick check to see if it launched

                except Exception as e:
                    # Default failed — fall back to Open With prompt
                    QMessageBox.warning(
                        self,
                        "Open File",
                        f"Failed to open {path} with default application.\n\n"
                        f"Error: {e}\n\n"
                        "You can choose a program manually.",
                    )
                    self.open_with([idx])

        except Exception as e:
            QMessageBox.critical(self, "Open Error", str(e))
        
    def createNewTextFile(self):
        base = self.currentPath()
        name, ok = QInputDialog.getText(self, "New Text File", "Name:")
        if ok and name:
            path = os.path.join(base, name)

            # Prevent overwriting existing files/folders
            if os.path.exists(path):
                QMessageBox.warning(
                    self,
                    "File Exists",
                    f"A file or folder named:\n\n{path}\n\nalready exists.\n"
                    "Please choose a different name."
                )
                return
            try:
                with open(path, "w", encoding="utf-8") as f:
                    f.write("")
                self.refreshCurrentTab()
            except Exception as e:
                QMessageBox.critical(self, "Error", str(e))

    def createNewFolder(self):
        base = self.currentPath()
        name, ok = QInputDialog.getText(self, "New Folder", "Name:")
        if ok and name:
            path = os.path.join(base, name)
            try:
                os.makedirs(path, exist_ok=False)
                self.refreshCurrentTab()
            except FileExistsError:
                QMessageBox.warning(self, "Exists", f"Folder already exists:\n{path}")
            except Exception as e:
                QMessageBox.critical(self, "Error", str(e))

    def confirmDelete(self, paths):
        targets = [paths] if isinstance(paths, str) else list(paths)
        if not targets:
            return

        msg = ("Move the selected item to Trash?"
               if len(targets) == 1
               else f"Move {len(targets)} selected items to Trash?")
        if QMessageBox.question(
            self, "Confirm Delete", msg,
            QMessageBox.Yes | QMessageBox.No, QMessageBox.No
        ) != QMessageBox.Yes:
            return

        errors = []
        for p in targets:
            try:
                self._trash_one(p)
            except Exception as e:
                errors.append(f"{p}: {e}")

        if errors:
            QMessageBox.warning(self, "Trash Summary", "Some items could not be moved:\n\n" + "\n".join(errors))

        self.refreshCurrentTab()

    def _trash_one(self, path: str):
        """
        Move a file/folder to the user's Trash.
        Order of attempts:
          1) gio trash <path>
          2) manual move into ~/.local/share/Trash/files with a unique name
        Raises on failure.
        """

        # 1) Manual spec-like move into ~/.local/share/Trash/files
        trash_files = os.path.expanduser("~/.local/share/Trash/files")
        os.makedirs(trash_files, exist_ok=True)

        base_name = os.path.basename(path.rstrip(os.sep)) or "unnamed"
        target = self._unique_trash_name(trash_files, base_name)

        try:
            shutil.move(path, target)
        except Exception as e:
            # If shutil.move across FS fails for dirs, try copytree + remove
            if os.path.isdir(path) and not os.path.islink(path):
                try:
                    shutil.copytree(path, target)
                    # remove original after copy
                    if os.path.isdir(path):
                        shutil.rmtree(path)
                    else:
                        os.remove(path)
                except Exception as e2:
                    # cleanup partial copy if created
                    try:
                        if os.path.isdir(target):
                            shutil.rmtree(target)
                        elif os.path.exists(target):
                            os.remove(target)
                    except Exception:
                        pass
                    raise RuntimeError(f"manual trash failed: {e2}") from e
            else:
                raise

    def _unique_trash_name(self, parent: str, name: str) -> str:
        """
        Return a unique path under `parent` using 'name', appending ' (n)' if needed.
        """
        candidate = os.path.join(parent, name)
        if not os.path.exists(candidate):
            return candidate

        root, ext = os.path.splitext(name)
        n = 2
        while True:
            # Keep extension for files; for folders ext is usually empty
            alt = f"{root} ({n}){ext}"
            candidate = os.path.join(parent, alt)
            if not os.path.exists(candidate):
                return candidate
            n += 1

    # ------------ Clipboard helpers ------------
    def _as_paths(self, items):
        """
        Normalize a 'paths' arg that might be:
          - a single str,
          - a list of str,
          - a list of QModelIndex (defensive),
        into a unique, absolute list of existing filesystem paths.
        """
        view = self.currentView()
        model = view.model() if view is not None else None

        paths = []
        if isinstance(items, str):
            paths = [items]
        elif isinstance(items, (list, tuple)):
            for it in items:
                if isinstance(it, str):
                    paths.append(it)
                else:
                    # possible QModelIndex (defensive)
                    try:
                        if model is not None and hasattr(model, "filePath"):
                            p = model.filePath(it)
                            if p:
                                paths.append(p)
                    except Exception:
                        pass

        # absolutize + dedupe + only existing
        abs_unique = []
        seen = set()
        for p in paths:
            ap = os.path.abspath(os.path.expanduser(p))
            if ap in seen:
                continue
            seen.add(ap)
            if os.path.exists(ap):
                abs_unique.append(ap)
        return abs_unique

    def _is_subpath(self, child_path: str, parent_path: str) -> bool:
        """
        True if child_path is located inside parent_path.
        """
        try:
            parent = os.path.abspath(parent_path)
            child = os.path.abspath(child_path)
            common = os.path.commonpath([child, parent])
            return common == parent
        except Exception:
            return False

    # ------------ Clipboard ops ------------
    def cutFileOrFolder(self, paths):
        items = self._as_paths(paths)
        if not items:
            QMessageBox.warning(self, "Cut", "No valid items to cut.")
            return
        self.clipboard = ("cut", items)
        QMessageBox.information(self, "Cut", f"Ready to move {len(items)} item(s).")

    def copyFileOrFolder(self, paths):
        items = self._as_paths(paths)
        if not items:
            QMessageBox.warning(self, "Copy", "No valid items to copy.")
            return
        self.clipboard = ("copy", items)
        QMessageBox.information(self, "Copy", f"Ready to copy {len(items)} item(s).")



    def _prompt_overwrite(self, dst_path: str, is_dir: bool) -> str:
        """
        Ask user what to do for an existing destination.
        Returns one of: 'yes', 'no', 'yes_all', 'no_all', 'cancel'
        """
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

        # Use exec_ for PyQt5; our shim maps exec_->exec on PyQt6
        box.exec_()
        clicked = box.clickedButton()

        if clicked is btn_yes:
            return "yes"
        if clicked is btn_no:
            return "no"
        if clicked is btn_yes_all:
            return "yes_all"
        if clicked is btn_no_all:
            return "no_all"
        return "cancel"

    def pasteFileOrFolder(self, dest_dir):
        if not hasattr(self, "clipboard") or not self.clipboard:
            return

        op, items = self.clipboard
        if not items:
            return

        # Overall confirmation
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
        skipped_same = []   # items skipped because src == dst (same folder & same name)
        errors = []

        for src in items:
            name = os.path.basename(src)
            dst = os.path.join(dest_dir, name)
            is_dir = os.path.isdir(src) and not os.path.islink(src)

            # --- Prevent pasting onto itself (same folder + same name) ---
            same = False
            try:
                if os.path.exists(src) and os.path.exists(dst):
                    same = os.path.samefile(src, dst)
            except Exception:
                same = (os.path.abspath(src) == os.path.abspath(dst))

            if same:
                skipped_same.append(dst)
                continue

            # Handle collisions with per-item prompt
            if os.path.exists(dst):
                if skip_all:
                    skipped.append(dst)
                    continue
                if not overwrite_all:
                    choice = self._prompt_overwrite(dst, is_dir)
                    if choice == "cancel":
                        if op == "cut":
                            self.clipboard = None
                        # Summary before exiting if anything happened
                        parts = []
                        if skipped_same:
                            parts.append(
                                f"Skipped {len(skipped_same)} identical-location "
                                f"{'item' if len(skipped_same) == 1 else 'items'}."
                            )
                        if skipped:
                            parts.append(
                                f"Skipped {len(skipped)} existing "
                                f"{'item' if len(skipped) == 1 else 'items'}."
                            )
                        if errors:
                            parts.append(f"{len(errors)} errors occurred before cancel.")
                        if parts:
                            QMessageBox.information(self, "Paste Summary", "\n".join(parts))
                        return
                    elif choice == "no":
                        skipped.append(dst)
                        continue
                    elif choice == "no_all":
                        skip_all = True
                        skipped.append(dst)
                        continue
                    elif choice == "yes_all":
                        overwrite_all = True
                    # elif 'yes': fall through to overwrite this one

                # Overwrite this destination: remove it first
                try:
                    if os.path.isdir(dst) and not os.path.islink(dst):
                        shutil.rmtree(dst)
                    else:
                        os.remove(dst)
                except Exception as e:
                    errors.append(f"Remove existing {dst}: {e}")
                    continue

            # Perform the operation
            try:
                if is_dir:
                    if op == "copy":
                        shutil.copytree(src, dst)
                    else:
                        shutil.move(src, dst)
                else:
                    if op == "copy":
                        shutil.copy2(src, dst)
                    else:
                        shutil.move(src, dst)
            except Exception as e:
                errors.append(f"{src} -> {dst}: {e}")

        # Cleanup if cut
        if op == "cut":
            self.clipboard = None

        # Summary
        parts = []
        if skipped_same:
            parts.append(
                f"Skipped {len(skipped_same)} identical-location "
                f"{'item' if len(skipped_same) == 1 else 'items'} (same folder & name)."
            )
        if skipped:
            parts.append(
                f"Skipped {len(skipped)} existing "
                f"{'item' if len(skipped) == 1 else 'items'}."
            )
        if errors:
            parts.append(f"{len(errors)} errors occurred during operation.")
        if parts:
            QMessageBox.information(self, "Paste Summary", "\n".join(parts))

        self.refreshCurrentTab()


    def open_with(self, indexes):
        """
        Prompt for a program and open selected file(s) with it.
        - Ignores directories (warns if only dirs are selected).
        - Remembers the last program via QSettings.
        """
        import shlex
        import shutil
        from qt_compat import QSettings

        if not indexes:
            return

        # Collect file paths from indexes; ignore directories
        view = self.currentView()
        if view is None:
            return
        model = view.model()

        file_paths = []
        for idx in indexes:
            try:
                p = model.filePath(idx)
                if p and os.path.isfile(p):
                    file_paths.append(p)
            except Exception:
                pass

        if not file_paths:
            QMessageBox.warning(self, "Open With...", "Please select at least one file (not a folder).")
            return

        # Suggest the last program used
        settings = QSettings("SpinFM", "SpinFM")
        last_program = settings.value("open_with/last_program", "")

        # Ask for the program/command
        program_text, ok = QInputDialog.getText(
            self,
            "Open With...",
            "Type the command for the program (you can include arguments):",
            text=last_program
        )
        if not ok or not program_text.strip():
            return

        # Parse command safely: allow args like 'vlc --fullscreen'
        try:
            tokens = shlex.split(program_text.strip())
            if not tokens:
                QMessageBox.warning(self, "Open With...", "No program specified.")
                return
            exe = tokens[0]
            # Resolve executable if not an absolute/relative path
            if not os.path.isabs(exe) and os.sep not in exe:
                resolved = shutil.which(exe)
                if not resolved:
                    QMessageBox.warning(self, "Open With...", f"Program not found in PATH: {exe}")
                    return
                tokens[0] = resolved
        except Exception as e:
            QMessageBox.warning(self, "Open With...", f"Invalid command:\n{e}")
            return

        # Save as last program
        settings.setValue("open_with/last_program", program_text.strip())

        # Try launching with all selected files appended to the command
        try:
            subprocess.Popen(tokens + file_paths)
        except Exception as e:
            QMessageBox.warning(self, "Open With...", f"Failed to launch:\n{e}")

    # -------- Hidden files toggle (used by MainWindow) --------
    def update_hidden_files(self, show_hidden: bool):
        """Show/hide dotfiles across all tab views."""
        flags = QDir.AllEntries | QDir.NoDotAndDotDot | QDir.AllDirs
        if show_hidden:
            try:
                flags = flags | QDir.Hidden
            except Exception:
                pass

        for i in range(self.tab_widget.count()):
            view = self.tab_widget.widget(i)
            if view is None:
                continue
            model = view.model()
            try:
                model.setFilter(flags)
            except Exception:
                try:
                    model.setFilter(int(flags))
                except Exception:
                    pass

        self.refreshCurrentTab()
