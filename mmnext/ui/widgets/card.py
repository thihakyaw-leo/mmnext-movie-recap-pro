"""Card, header, section title and stat tile widgets."""

from __future__ import annotations

from typing import Optional

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

from ..theme.palette import Palette

__all__ = ["Card", "CardHeader", "SectionTitle", "StatTile"]


class Card(QFrame):
    """A bordered surface used for most content blocks."""

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.setObjectName("card")
        self.setFrameShape(QFrame.NoFrame)
        self.setStyleSheet(
            f"""
            QFrame#card {{
                background: {Palette.BG_CARD};
                border: 1px solid {Palette.BORDER};
                border-radius: 8px;
            }}
            """
        )
        self._layout = QVBoxLayout(self)
        self._layout.setContentsMargins(16, 14, 16, 16)
        self._layout.setSpacing(10)

    def body(self) -> QVBoxLayout:
        """The card's main vertical layout."""
        return self._layout

    def add(self, widget: QWidget) -> QWidget:
        self._layout.addWidget(widget)
        return widget

    def add_layout(self, layout) -> None:
        self._layout.addLayout(layout)


class CardHeader(QWidget):
    """A title + optional trailing widget row."""

    def __init__(
        self,
        title: str,
        subtitle: str = "",
        parent: Optional[QWidget] = None,
    ) -> None:
        super().__init__(parent)
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(10)

        text_box = QVBoxLayout()
        text_box.setContentsMargins(0, 0, 0, 0)
        text_box.setSpacing(2)

        self.title_label = QLabel(title)
        self.title_label.setProperty("role", "h2")
        text_box.addWidget(self.title_label)

        self.subtitle_label = QLabel(subtitle)
        self.subtitle_label.setProperty("role", "muted")
        self.subtitle_label.setWordWrap(True)
        if subtitle:
            text_box.addWidget(self.subtitle_label)
        else:
            self.subtitle_label.hide()

        layout.addLayout(text_box)
        layout.addStretch(1)

    def set_subtitle(self, text: str) -> None:
        self.subtitle_label.setText(text)
        self.subtitle_label.setVisible(bool(text))

    def add_trailing(self, widget: QWidget) -> QWidget:
        self.layout().addWidget(widget)
        return widget


class SectionTitle(QLabel):
    """A small uppercase section heading."""

    def __init__(self, text: str, parent: Optional[QWidget] = None) -> None:
        super().__init__(text.upper(), parent)
        self.setProperty("role", "sectionTitle")


class StatTile(QFrame):
    """A compact metric tile: big number, label underneath."""

    def __init__(
        self,
        label: str,
        value: str = "-",
        parent: Optional[QWidget] = None,
    ) -> None:
        super().__init__(parent)
        self.setStyleSheet(
            f"""
            QFrame {{
                background: {Palette.BG_PANEL};
                border: 1px solid {Palette.BORDER};
                border-radius: 6px;
            }}
            """
        )
        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 10, 12, 10)
        layout.setSpacing(2)

        self.value_label = QLabel(value)
        self.value_label.setProperty("role", "h2")
        self.value_label.setTextInteractionFlags(Qt.TextSelectableByMouse)

        self.caption_label = QLabel(label)
        self.caption_label.setProperty("role", "faint")

        layout.addWidget(self.value_label)
        layout.addWidget(self.caption_label)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)

    def set_value(self, value: str) -> None:
        self.value_label.setText(value)
