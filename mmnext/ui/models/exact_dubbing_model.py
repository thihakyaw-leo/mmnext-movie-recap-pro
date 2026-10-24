"""Table model for the exact-dubbing table.

The exact-dubbing table is *not* editable in place for the immutable
columns: ``id``, ``original``, ``start`` and ``duration`` come from the
source transcript and must never change. Only the Burmese text and the
gender are editable, and only the Burmese cell is edited in place - the
gender is changed from the inspector so the fallback-voice rule stays
visible next to the control.
"""

from __future__ import annotations

from typing import Optional, Sequence

from PySide6.QtCore import QAbstractTableModel, QModelIndex, Qt, Signal

from ...domain.models import ExactDubbingRow
from ..theme.palette import Palette
from ..widgets.timecode import format_timecode

__all__ = ["ExactDubbingTableModel"]

_HEADERS = ("#", "In", "Duration", "Speaker", "Original (immutable)", "Burmese", "Voice")


class ExactDubbingTableModel(QAbstractTableModel):
    """Exposes :class:`ExactDubbingRow` rows to a ``QTableView``."""

    burmeseEdited = Signal(str, str)   # row_id, new text

    def __init__(
        self,
        rows: Optional[Sequence[ExactDubbingRow]] = None,
        parent=None,
    ) -> None:
        super().__init__(parent)
        self._rows: list[ExactDubbingRow] = list(rows or [])

    # -- Qt model interface ------------------------------------------------- #
    def rowCount(self, parent=QModelIndex()) -> int:  # noqa: N802
        return 0 if parent.isValid() else len(self._rows)

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
        row = self._rows[index.row()]
        column = index.column()

        if role == Qt.ItemDataRole.DisplayRole:
            return self._display(row, column)
        if role == Qt.ItemDataRole.EditRole:
            return row.burmese if column == 5 else self._display(row, column)
        if role == Qt.ItemDataRole.ToolTipRole:
            return self._tooltip(row, column)
        if role == Qt.ItemDataRole.BackgroundRole:
            if column == 5 and not row.burmese.strip():
                return Palette.DANGER_SOFT
            return None
        if role == Qt.ItemDataRole.ForegroundRole:
            if column == 5 and not row.burmese.strip():
                return Palette.DANGER
            if column == 6 and row.gender.value == "unknown":
                return Palette.WARNING
            return None
        return None

    def flags(self, index: QModelIndex):
        if not index.isValid():
            return Qt.ItemFlag.NoItemFlags
        base = Qt.ItemFlag.ItemIsEnabled | Qt.ItemFlag.ItemIsSelectable
        if index.column() == 5:
            base |= Qt.ItemFlag.ItemIsEditable
        return base

    def setData(self, index: QModelIndex, value, role=Qt.ItemDataRole.EditRole):  # noqa: N802
        if not index.isValid() or role != Qt.ItemDataRole.EditRole:
            return False
        if index.column() != 5:
            return False
        row = self._rows[index.row()]
        text = str(value)
        row.burmese = text
        row.edited = True
        self.dataChanged.emit(index, index)
        self.burmeseEdited.emit(row.row_id, text)
        return True

    # -- data helpers -------------------------------------------------------- #
    def _display(self, row: ExactDubbingRow, column: int) -> str:
        if column == 0:
            return str(self._rows.index(row) + 1)
        if column == 1:
            return format_timecode(row.start)
        if column == 2:
            return f"{row.duration:.1f}s"
        if column == 3:
            return row.gender.value
        if column == 4:
            return row.original
        if column == 5:
            return row.burmese
        if column == 6:
            return row.voice
        return ""

    def _tooltip(self, row: ExactDubbingRow, column: int) -> str:
        if column == 4:
            return (
                "Immutable: the original line is copied verbatim from the "
                "source transcript."
            )
        if column == 5 and not row.burmese.strip():
            return "Missing translation - this blocks rendering."
        if column == 6 and row.gender.value == "unknown":
            return "Unknown speaker - falls back to my-MM-NilarNeural."
        return ""

    # -- public API ---------------------------------------------------------- #
    def set_rows(self, rows: Sequence[ExactDubbingRow]) -> None:
        self.beginResetModel()
        self._rows = list(rows)
        self.endResetModel()

    def row_at(self, row: int) -> Optional[ExactDubbingRow]:
        if 0 <= row < len(self._rows):
            return self._rows[row]
        return None

    def row_for_id(self, row_id: str) -> int:
        for index, row in enumerate(self._rows):
            if row.row_id == row_id:
                return index
        return -1

    def rows(self) -> list[ExactDubbingRow]:
        return list(self._rows)
