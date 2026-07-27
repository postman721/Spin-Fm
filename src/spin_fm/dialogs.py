"""Reusable application dialogs with production-safe sizing defaults."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass

from .qt_compat import (
    QAbstractItemView,
    QDialog,
    QDialogButtonBox,
    QHeaderView,
    QIcon,
    QLabel,
    QSize,
    QStyle,
    QTableWidget,
    QTableWidgetItem,
    Qt,
    QVBoxLayout,
    QWidget,
)


@dataclass(frozen=True, slots=True)
class TrashLocation:
    """One visible Trash payload directory."""

    name: str
    path: str
    detail: str
    removable: bool = False


class TrashLocationDialog(QDialog):
    """Large, resizable chooser for home and mounted-device Trash folders."""

    MINIMUM_SIZE = QSize(720, 360)
    INITIAL_SIZE = QSize(860, 460)
    SCREEN_MARGIN = 72
    ROW_MINIMUM_HEIGHT = 64

    def __init__(
        self,
        locations: Sequence[TrashLocation],
        parent: QWidget | None = None,
    ) -> None:
        location_rows = tuple(locations)
        if not location_rows:
            raise ValueError("at least one Trash location is required")

        super().__init__(parent)
        self.setObjectName("trashLocationDialog")
        self.setWindowTitle("Open Trash")
        self.setModal(True)
        self.setSizeGripEnabled(True)
        self._apply_sensible_size(parent)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(22, 20, 22, 20)
        layout.setSpacing(12)

        title = QLabel("Choose a Trash location", self)
        title.setObjectName("dialogTitle")
        title_font = title.font()
        title_font.setBold(True)
        title_font.setPointSize(max(13, title_font.pointSize() + 2))
        title.setFont(title_font)
        layout.addWidget(title)

        description = QLabel(
            "Home Trash is stored in your user profile. USB and mounted-volume "
            "Trash stays on that filesystem. Select a row; complete paths are "
            "shown without shortening.",
            self,
        )
        description.setObjectName("dialogDescription")
        description.setWordWrap(True)
        layout.addWidget(description)

        self.location_table = QTableWidget(len(location_rows), 2, self)
        table = self.location_table
        table.setObjectName("trashLocationTable")
        table.setAccessibleName("Available Trash locations")
        table.setHorizontalHeaderLabels(["Location", "Folder"])
        table.verticalHeader().setVisible(False)
        table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        table.setSelectionBehavior(QAbstractItemView.SelectRows)
        table.setSelectionMode(QAbstractItemView.SingleSelection)
        table.setShowGrid(False)
        # QPalette.AlternateBase can remain a light desktop-style color even
        # under a dark application stylesheet. Avoid painting the second Trash
        # location with that stale system color before it is selected.
        table.setAlternatingRowColors(False)
        table.setSortingEnabled(False)
        table.setWordWrap(True)
        table.setTextElideMode(Qt.ElideNone)
        table.setHorizontalScrollMode(QAbstractItemView.ScrollPerPixel)
        table.setVerticalScrollMode(QAbstractItemView.ScrollPerPixel)

        header = table.horizontalHeader()
        header.setMinimumSectionSize(140)
        header.setStretchLastSection(False)
        header.setSectionResizeMode(0, QHeaderView.Interactive)
        header.setSectionResizeMode(1, QHeaderView.Stretch)
        table.setColumnWidth(0, 300)

        for row, location in enumerate(location_rows):
            label = location.name
            if location.detail:
                label = f"{label}\n{location.detail}"
            name_item = QTableWidgetItem(label)
            name_item.setIcon(self._location_icon(location.removable))
            name_item.setToolTip(location.detail or location.name)
            table.setItem(row, 0, name_item)

            path_item = QTableWidgetItem(location.path)
            path_item.setToolTip(location.path)
            table.setItem(row, 1, path_item)

        table.resizeRowsToContents()
        for row in range(table.rowCount()):
            table.setRowHeight(row, max(self.ROW_MINIMUM_HEIGHT, table.rowHeight(row)))
        layout.addWidget(table, 1)

        self.buttons = QDialogButtonBox(
            QDialogButtonBox.Open | QDialogButtonBox.Cancel,
            parent=self,
        )
        self.buttons.accepted.connect(self.accept)
        self.buttons.rejected.connect(self.reject)
        layout.addWidget(self.buttons)

        self.open_button = self.buttons.button(QDialogButtonBox.Open)
        if self.open_button is not None:
            self.open_button.setObjectName("primaryDialogButton")
            self.open_button.setText("Open Trash")
            self.open_button.setMinimumWidth(120)
            self.open_button.setDefault(True)
            self.open_button.setToolTip("Open the selected Trash folder")

        table.itemSelectionChanged.connect(self._update_open_button)
        table.cellDoubleClicked.connect(self._open_row)
        table.selectRow(0)
        table.setFocus()
        self._update_open_button()

    def _apply_sensible_size(self, parent: QWidget | None) -> None:
        """Use roomy defaults while remaining usable on compact displays."""
        screen = parent.screen() if parent is not None else self.screen()
        if screen is None:
            self.setMinimumSize(self.MINIMUM_SIZE)
            self.resize(self.INITIAL_SIZE)
            return

        available = screen.availableGeometry().size()
        minimum = QSize(
            min(self.MINIMUM_SIZE.width(), max(520, available.width() - self.SCREEN_MARGIN)),
            min(
                self.MINIMUM_SIZE.height(),
                max(300, available.height() - self.SCREEN_MARGIN),
            ),
        )
        initial = QSize(
            min(self.INITIAL_SIZE.width(), max(minimum.width(), int(available.width() * 0.72))),
            min(
                self.INITIAL_SIZE.height(),
                max(minimum.height(), int(available.height() * 0.62)),
            ),
        )
        self.setMinimumSize(minimum)
        self.resize(initial)

    def _location_icon(self, removable: bool) -> QIcon:
        icon_name = "drive-removable-media" if removable else "user-trash"
        icon = QIcon.fromTheme(icon_name)
        if icon.isNull():
            fallback = QStyle.SP_DriveHDIcon if removable else QStyle.SP_TrashIcon
            icon = self.style().standardIcon(fallback)
        return icon

    def _update_open_button(self) -> None:
        if self.open_button is not None:
            self.open_button.setEnabled(self.selected_path() is not None)

    def _open_row(self, row: int, _column: int) -> None:
        if 0 <= row < self.location_table.rowCount():
            self.location_table.selectRow(row)
            self.accept()

    def selected_path(self) -> str | None:
        """Return the selected Trash payload path."""
        row = self.location_table.currentRow()
        if row < 0:
            return None
        item = self.location_table.item(row, 1)
        if item is None:
            return None
        path = item.text().strip()
        return path or None

    @classmethod
    def choose(
        cls,
        parent: QWidget,
        locations: Sequence[TrashLocation],
    ) -> str | None:
        """Show the chooser and release it immediately after use."""
        dialog = cls(locations, parent)
        try:
            if dialog.exec() != QDialog.Accepted:
                return None
            return dialog.selected_path()
        finally:
            dialog.deleteLater()
