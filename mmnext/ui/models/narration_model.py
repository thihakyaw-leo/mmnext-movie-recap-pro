"""Table model for the narrator-mode segment list."""

from __future__ import annotations

from typing import Optional, Sequence

from PySide6.QtCore import QAbstractTableModel, QModelIndex, Qt, Signal

from ...domain.models import NarrationSegment
from ..theme.palette import Palette
from ..widgets.timecode import format_timecode

__all__ = ["NarrationTableModel"]

_HEADERS = ("#", "In", "Out", "Duration", "Source", "Narration (Myanmar)")


class NarrationTableModel(QAbstractTableModel):
    """Exposes :class:`NarrationSegment` rows to a ``QTableView``."""

    narrationEdited = Signal(str, str)   # segment_id, new text

    def __init__(
        self,
        segments: Optional[Sequence[NarrationSegment]] = None,
        parent=None,
    ) -> None:
        super().__init__(parent)
        self._segments: list[NarrationSegment] = list(segments or [])

    # -- Qt model interface ------------------------------------------------- #
    def rowCount(self, parent=QModelIndex()) -> int:  # noqa: N802
        return 0 if parent.isValid() else len(self._segments)

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
        segment = self._segments[index.row()]
        column = index.column()

        if role == Qt.ItemDataRole.DisplayRole:
            return self._display(segment, column)
        if role == Qt.ItemDataRole.EditRole:
            if column == 5:
                return segment.narration
            return self._display(segment, column)
        if role == Qt.ItemDataRole.ToolTipRole:
            return self._tooltip(segment, column)
        if role == Qt.ItemDataRole.ForegroundRole:
            if column == 5 and segment.dirty:
                return Palette.WARNING
            return None
        if role == Qt.ItemDataRole.FontRole and column == 5 and segment.dirty:
            from PySide6.QtGui import QFont

            font = QFont()
            font.setBold(True)
            return font
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
        segment = self._segments[index.row()]
        text = str(value)
        segment.narration = text
        segment.dirty = True
        self.dataChanged.emit(index, index)
        self.narrationEdited.emit(segment.segment_id, text)
        return True

    # -- data helpers -------------------------------------------------------- #
    def _display(self, segment: NarrationSegment, column: int) -> str:
        if column == 0:
            return str(segment.order + 1)
        if column == 1:
            return format_timecode(segment.start)
        if column == 2:
            return format_timecode(segment.end)
        if column == 3:
            return f"{segment.duration:.1f}s"
        if column == 4:
            return segment.source_text
        if column == 5:
            return segment.narration
        return ""

    def _tooltip(self, segment: NarrationSegment, column: int) -> str:
        if column == 4:
            return segment.source_text
        if column == 5:
            flags = []
            if segment.semantic_boundary:
                flags.append("semantic boundary")
            if segment.forced_boundary:
                flags.append("forced boundary")
            if segment.visual_reason:
                flags.append(segment.visual_reason)
            suffix = f"\n{', '.join(flags)}" if flags else ""
            return f"{segment.narration}{suffix}"
        return ""

    # -- public API ---------------------------------------------------------- #
    def set_segments(self, segments: Sequence[NarrationSegment]) -> None:
        self.beginResetModel()
        self._segments = list(segments)
        self.endResetModel()

    def segment_at(self, row: int) -> Optional[NarrationSegment]:
        if 0 <= row < len(self._segments):
            return self._segments[row]
        return None

    def row_for_segment(self, segment_id: str) -> int:
        for index, segment in enumerate(self._segments):
            if segment.segment_id == segment_id:
                return index
        return -1

    def segments(self) -> list[NarrationSegment]:
        return list(self._segments)
