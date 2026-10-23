"""Table model for the splitter-mode part list."""

from __future__ import annotations

from typing import Optional, Sequence

from PySide6.QtCore import QAbstractTableModel, QModelIndex, Qt

from ...domain.models import SplitPart
from ..widgets.timecode import format_timecode

__all__ = ["SplitPartTableModel"]

_HEADERS = ("Part", "Start", "End", "Duration", "Cut reason", "Include")


class SplitPartTableModel(QAbstractTableModel):
    """Exposes :class:`SplitPart` rows to a ``QTableView``."""

    def __init__(
        self, parts: Optional[Sequence[SplitPart]] = None, parent=None
    ) -> None:
        super().__init__(parent)
        self._parts: list[SplitPart] = list(parts or [])

    def rowCount(self, parent=QModelIndex()) -> int:  # noqa: N802
        return 0 if parent.isValid() else len(self._parts)

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
        part = self._parts[index.row()]
        column = index.column()

        if role == Qt.ItemDataRole.DisplayRole:
            return self._display(part, column)
        if role == Qt.ItemDataRole.CheckStateRole and column == 5:
            return (
                Qt.CheckState.Checked if part.include else Qt.CheckState.Unchecked
            )
        if role == Qt.ItemDataRole.ToolTipRole and column == 3:
            return (
                "Why this part ends here - the legacy planner used the same "
                "vocabulary."
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
        part = self._parts[index.row()]
        part.include = (
            Qt.CheckState(value) == Qt.CheckState.Checked
            if isinstance(value, int)
            else bool(value)
        )
        self.dataChanged.emit(index, index)
        return True

    def _display(self, part: SplitPart, column: int) -> str:
        if column == 0:
            return f"Part {part.number}"
        if column == 1:
            return format_timecode(part.start)
        if column == 2:
            return format_timecode(part.end)
        if column == 3:
            return f"{part.duration:.1f}s"
        if column == 4:
            return part.cut_reason.value
        return ""

    def set_parts(self, parts: Sequence[SplitPart]) -> None:
        self.beginResetModel()
        self._parts = list(parts)
        self.endResetModel()

    def part_at(self, row: int) -> Optional[SplitPart]:
        if 0 <= row < len(self._parts):
            return self._parts[row]
        return None

    def parts(self) -> list[SplitPart]:
        return list(self._parts)
