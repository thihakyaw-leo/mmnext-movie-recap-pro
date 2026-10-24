"""A small inline status chip.

Used by the top bar to show the source status, the dependency status, the
language and the save indicator without turning the bar into a wall of
labels.
"""

from __future__ import annotations

from typing import Optional

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QLabel, QSizePolicy, QWidget

from ..theme.palette import Palette

__all__ = ["StatusChip"]


class StatusChip(QLabel):
    """A ``label: value`` pill.

    The colour is applied inline because the colour comes from a runtime
    lookup (dependency status, validation severity) rather than the
    stylesheet.
    """

    def __init__(
        self,
        label: str = "",
        value: str = "",
        color: str = Palette.TEXT_MUTED,
        parent: Optional[QWidget] = None,
    ) -> None:
        super().__init__(parent)
        self._label = label
        self.setAlignment(Qt.AlignLeft | Qt.AlignVCenter)
        self.setSizePolicy(QSizePolicy.Maximum, QSizePolicy.Fixed)
        self.set_state(value, color)

    def set_state(self, value: str, color: str = Palette.TEXT_MUTED) -> None:
        """Replace the value part and recolour the chip."""
        self._value = value
        text = f"{self._label} {value}" if self._label else value
        self.setText(text)
        self.setToolTip(f"{self._label}: {value}" if self._label else value)
        self.setStyleSheet(
            f"""
            QLabel {{
                background: {Palette.BG_CARD};
                color: {color};
                border: 1px solid {Palette.BORDER};
                border-radius: 4px;
                padding: 2px 8px;
                font-size: 11px;
            }}
            """
        )

    def set_value(self, value: str, color: str = Palette.TEXT_MUTED) -> None:
        self.set_state(value, color)

    def value(self) -> str:
        """Return the current value part (without the label)."""
        return self._value
