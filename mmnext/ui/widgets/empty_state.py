"""Placeholder shown when a list has no rows yet."""

from __future__ import annotations

from typing import Optional

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QLabel, QVBoxLayout, QWidget

__all__ = ["EmptyState"]


class EmptyState(QWidget):
    """Centred icon-less message with an optional hint."""

    def __init__(
        self,
        title: str,
        hint: str = "",
        parent: Optional[QWidget] = None,
    ) -> None:
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.setAlignment(Qt.AlignCenter)
        layout.setSpacing(6)

        self.title_label = QLabel(title)
        self.title_label.setProperty("role", "h3")
        self.title_label.setAlignment(Qt.AlignCenter)

        self.hint_label = QLabel(hint)
        self.hint_label.setProperty("role", "muted")
        self.hint_label.setAlignment(Qt.AlignCenter)
        self.hint_label.setWordWrap(True)
        self.hint_label.setVisible(bool(hint))

        layout.addWidget(self.title_label)
        layout.addWidget(self.hint_label)

    def set_title(self, text: str) -> None:
        self.title_label.setText(text)

    def set_hint(self, text: str) -> None:
        self.hint_label.setText(text)
        self.hint_label.setVisible(bool(text))
