"""Analyze / metadata screen.

Shows the metadata record for the current source: title, channel, duration,
published date, stream qualities, and a short explanation of what the
analyze step would do in a production build.
"""

from __future__ import annotations

from typing import Optional

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QComboBox,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from ...domain.models import SourceMetadata
from ..navigation.nav_rail import NavTarget
from ..theme.palette import Palette
from ..widgets.card import Card, CardHeader, StatTile
from ..widgets.empty_state import EmptyState
from .base import BaseScreen, ScreenHeader

__all__ = ["AnalyzeScreen"]


class AnalyzeScreen(BaseScreen):
    """Metadata inspection."""

    screen_key = NavTarget.ANALYZE

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)

        self.layout.addWidget(
            ScreenHeader(
                "Analyze",
                "Metadata for the current source. In demo mode this record "
                "comes from a fixed fixture - no network request is made.",
            )
        )

        self.empty_state = EmptyState(
            "No source loaded",
            "Import a local file or a YouTube URL first.",
        )
        self.layout.addWidget(self.empty_state)

        # -- metadata card ---------------------------------------------------- #
        self.metadata_card = Card()
        self.metadata_card.add(
            CardHeader("Source metadata", "Everything the analyze step returns.")
        )

        self.title_label = QLabel("-")
        self.title_label.setProperty("role", "h2")
        self.title_label.setWordWrap(True)
        self.metadata_card.add(self.title_label)

        grid = QGridLayout()
        grid.setHorizontalSpacing(26)
        grid.setVerticalSpacing(10)

        self.channel_value = self._grid_field(grid, 0, "Channel")
        self.published_value = self._grid_field(grid, 1, "Published")
        self.duration_value = self._grid_field(grid, 2, "Duration")
        self.language_value = self._grid_field(grid, 3, "Language")
        self.streams_value = self._grid_field(grid, 4, "Streams")
        self.source_value = self._grid_field(grid, 5, "Source")
        self.metadata_card.add_layout(grid)

        self.description_label = QLabel("")
        self.description_label.setProperty("role", "muted")
        self.description_label.setWordWrap(True)
        self.metadata_card.add(self.description_label)

        self.layout.addWidget(self.metadata_card)

        # -- quality picker ---------------------------------------------------- #
        self.quality_card = Card()
        self.quality_card.add(
            CardHeader("Available qualities", "Pick the rendition to download.")
        )

        quality_row = QHBoxLayout()
        quality_row.setSpacing(10)

        self.quality_combo = QComboBox()
        self.quality_combo.setMinimumWidth(320)

        self.download_button = QPushButton("Add to download queue")
        self.download_button.setProperty("variant", "primary")
        self.download_button.clicked.connect(self._enqueue_download)

        quality_row.addWidget(self.quality_combo)
        quality_row.addWidget(self.download_button)
        quality_row.addStretch(1)
        self.quality_card.add_layout(quality_row)
        self.layout.addWidget(self.quality_card)

        # -- stats ------------------------------------------------------------- #
        stats_card = Card()
        stats_card.add(CardHeader("Session"))
        stat_row = QHBoxLayout()
        stat_row.setSpacing(12)

        self.stat_transcript = StatTile("Transcript rows", "0")
        self.stat_narration = StatTile("Narration segments", "0")
        self.stat_exact = StatTile("Exact dubbing rows", "0")
        stat_row.addWidget(self.stat_transcript)
        stat_row.addWidget(self.stat_narration)
        stat_row.addWidget(self.stat_exact)
        stat_row.addStretch(1)
        stats_card.add_layout(stat_row)
        self.layout.addWidget(stats_card)

        self.layout.addStretch(1)
        self._show_metadata(None)

    # -- helpers ------------------------------------------------------------ #
    def _grid_field(self, grid: QGridLayout, row: int, caption: str) -> QLabel:
        caption_label = QLabel(caption.upper())
        caption_label.setProperty("role", "sectionTitle")
        value_label = QLabel("-")
        value_label.setProperty("role", "mono")
        grid.addWidget(caption_label, row, 0)
        grid.addWidget(value_label, row, 1)
        return value_label

    def _show_metadata(self, metadata: Optional[SourceMetadata]) -> None:
        has_metadata = metadata is not None
        self.empty_state.setVisible(not has_metadata)
        self.metadata_card.setVisible(has_metadata)
        self.quality_card.setVisible(has_metadata)
        if metadata is None:
            return

        self.title_label.setText(metadata.title)
        self.channel_value.setText(metadata.channel)
        self.published_value.setText(metadata.published)
        self.duration_value.setText(metadata.duration_display)
        self.language_value.setText(metadata.language)
        self.streams_value.setText(
            f"{len(metadata.qualities)} video, "
            f"{'audio' if metadata.has_audio else 'no audio'}"
        )
        source = self._context.session.source if self._context and self._context.session else None
        self.source_value.setText(source.location if source else "-")
        self.description_label.setText(metadata.description)

        self.quality_combo.blockSignals(True)
        self.quality_combo.clear()
        for quality in metadata.qualities:
            self.quality_combo.addItem(quality.display, quality.quality_id)
        self.quality_combo.blockSignals(False)

    # -- actions ------------------------------------------------------------ #
    def _enqueue_download(self) -> None:
        if self._context is None:
            return
        session = self._context.session
        if session is None or session.source is None:
            return
        quality = self.quality_combo.currentData() or "1080"
        self._context.enqueue_download(session.source, quality)

        parent = self.window()
        if parent is not None and hasattr(parent, "navigate_to"):
            parent.navigate_to(NavTarget.DOWNLOADS)

    # -- context ------------------------------------------------------------ #
    def on_bind(self, context) -> None:
        context.metadataChanged.connect(self._show_metadata)
        context.sessionChanged.connect(self._refresh_session)

    def _refresh_session(self) -> None:
        if self._context is None:
            return
        session = self._context.session
        if session is None:
            self._show_metadata(None)
            self.stat_transcript.set_value("0")
            self.stat_narration.set_value("0")
            self.stat_exact.set_value("0")
            return
        self.stat_transcript.set_value(str(len(session.transcript)))
        self.stat_narration.set_value(str(len(session.narration_segments)))
        self.stat_exact.set_value(str(len(session.exact_dubbing_rows)))
        self._show_metadata(session.metadata)

    def on_activate(self) -> None:
        self._refresh_session()
