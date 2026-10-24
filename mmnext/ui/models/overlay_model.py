"""Table model for the common-editing overlay list."""

from __future__ import annotations

from typing import Optional, Sequence

from PySide6.QtCore import QAbstractTableModel, QModelIndex, Qt

from ...domain.models import Overlay
from ..widgets.timecode import format_timecode

__all__ = ["OverlayTableModel"]

_HEADERS = ("Kind", "Text", "Start", "End", "Position", "Enabled")


class OverlayTableModel(QAbstractTableModel):
    """Exposes :class:`Overlay` rows to a ``QTableView``."""

    def __init__(
        self, overlays: Optional[Sequence[Overlay]] = None, parent=None
    ) -> None:
        super().__init__(parent)
        self._overlays: list[Overlay] = list(overlays or [])

    def rowCount(self, parent=QModelIndex()) -> int:  # noqa: N802
        return 0 if parent.isValid() else len(self._overlays)

    def columnCount(self, parent=QModelIndex()) -> int:  # noqa: N802
        return 0 if parent.isValid() else len(_HEADERS)

    def headerData(self, section, orientation, role=Qt.ItemDataRole.DisplayRole):  # noqa: N802
        if role != Qt.ItemDataRole.DisplayRole:
            return None
        if orientation == Qt.Orientation.Horizontal:
            return _HEADERS[section]
        return section + 1

    def data(self, index: QModelIndex, role=Qt.ItemDataRole.DisplayRole):
        if not index.isValid():
            return None
        overlay = self._overlays[index.row()]
        column = index.column()

        if role == Qt.ItemDataRole.DisplayRole:
            return self._display(overlay, column)
        if role == Qt.ItemDataRole.CheckStateRole and column == 5:
            return (
                Qt.CheckState.Checked if overlay.enabled else Qt.CheckState.Unchecked
            )
        return None

    def flags(self, index: QModelIndex):
        if not index.isValid():
            return Qt.ItemFlag.NoItemFlags
        base = Qt.ItemFlag.ItemIsEnabled | Qt.ItemFlag.ItemIsSelectable
        if index.column() == 5:
            base |= Qt.ItemFlag.ItemIsUserCheckable
        return base

    def setData(self, index: QModelIndex, value, role=Qt.ItemDataRole.EditRole):  # noqa: N802
        if not index.isValid() or role != Qt.ItemDataRole.CheckStateRole:
            return False
        if index.column() != 5:
            return False
        overlay = self._overlays[index.row()]
        overlay.enabled = (
            Qt.CheckState(value) == Qt.CheckState.Checked
            if isinstance(value, int)
            else bool(value)
        )
        self.dataChanged.emit(index, index)
        return True

    def _display(self, overlay: Overlay, column: int) -> str:
        if column == 0:
            return overlay.kind.value.replace("_", " ").title()
        if column == 1:
            return overlay.text
        if column == 2:
            return format_timecode(overlay.start)
        if column == 3:
            return format_timecode(overlay.end)
        if column == 4:
            return overlay.position
        return ""

    def set_overlays(self, overlays: Sequence[Overlay]) -> None:
        self.beginResetModel()
        self._overlays = list(overlays)
        self.endResetModel()

    def overlay_at(self, row: int) -> Optional[Overlay]:
        if 0 <= row < len(self._overlays):
            return self._overlays[row]
        return None

    def overlays(self) -> list[Overlay]:
        return list(self._overlays)
