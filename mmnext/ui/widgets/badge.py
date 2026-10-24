"""A small coloured pill used for job / task / validation states."""

from __future__ import annotations

from typing import Optional

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QLabel, QSizePolicy, QWidget

from ..theme.palette import Palette

__all__ = ["StateBadge"]


class StateBadge(QLabel):
    """Coloured status pill.

    The colour is applied inline because the state colour comes from a
    lookup table rather than the stylesheet.
    """

    def __init__(self, text: str = "", color: str = Palette.NEUTRAL,
                 parent: Optional[QWidget] = None) -> None:
        super().__init__(text, parent)
        self.setAlignment(Qt.AlignCenter)
        self.setSizePolicy(QSizePolicy.Maximum, QSizePolicy.Fixed)
        self.apply_color(color)

    def apply_color(self, color: str) -> None:
        self.setStyleSheet(
            f"""
            QLabel {{
                background: {color}22;
                color: {color};
                border: 1px solid {color}66;
                border-radius: 9px;
                padding: 2px 9px;
                font-size: 11px;
                font-weight: 700;
            }}
            """
        )

    def set_state(self, text: str, color: str) -> None:
        self.setText(text)
        self.apply_color(color)
