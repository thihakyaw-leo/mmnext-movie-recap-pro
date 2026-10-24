"""Download queue screen.

Every queued item is shown as a :class:`DownloadProgressCard` with a
simulated progress bar and the four transport controls. The stepping happens
on a worker thread (see :mod:`mmnext.ui.workers`), so the GUI thread is
never blocked.
"""

from __future__ import annotations

from typing import Optional

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from ...domain.models import DownloadItem
from ..navigation.nav_rail import NavTarget
from ..theme.palette import Palette
from ..widgets.card import Card, CardHeader
from ..widgets.empty_state import EmptyState
from ..widgets.progress_card import DownloadProgressCard
from .base import BaseScreen, ScreenHeader

__all__ = ["DownloadScreen"]


class DownloadScreen(BaseScreen):
    """The download queue."""

    screen_key = NavTarget.DOWNLOADS

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)

        header = ScreenHeader(
            "Download queue",
            "Simulated transfers. The byte schedule is a fixed pattern, so "
            "the same run always produces the same numbers.",
        )
        self.layout.addWidget(header)

        toolbar = Card()
        header_row = CardHeader(
            "Queue", "Pause, resume, stop and retry act on the selected item."
        )
        self.pause_all_button = QPushButton("Pause all")
        self.pause_all_button.setProperty("variant", "ghost")
        self.pause_all_button.clicked.connect(self._pause_all)

        self.resume_all_button = QPushButton("Resume all")
        self.resume_all_button.setProperty("variant", "ghost")
        self.resume_all_button.clicked.connect(self._resume_all)

        self.clear_button = QPushButton("Clear finished")
        self.clear_button.setProperty("variant", "ghost")
        self.clear_button.clicked.connect(self._clear_finished)

        header_row.add_trailing(self.pause_all_button)
        header_row.add_trailing(self.resume_all_button)
        header_row.add_trailing(self.clear_button)
        toolbar.add(header_row)
        self.layout.addWidget(toolbar)

        self.empty_state = EmptyState(
            "The queue is empty",
            "Analyze a source and add a rendition to the queue.",
        )
        self.layout.addWidget(self.empty_state)

        self._cards: dict[str, DownloadProgressCard] = {}
        self._card_host = QWidget()
        self._card_host_layout = QVBoxLayout(self._card_host)
        self._card_host_layout.setContentsMargins(0, 0, 0, 0)
        self._card_host_layout.setSpacing(10)
        self.layout.addWidget(self._card_host)
        self.layout.addStretch(1)

    # -- context ------------------------------------------------------------ #
    def on_bind(self, context) -> None:
        context.downloadUpdated.connect(self._on_item_updated)
        context.downloadStateChanged.connect(self._on_state_changed)

    def _on_item_updated(self, item: DownloadItem) -> None:
        card = self._cards.get(item.item_id)
        if card is None:
            card = DownloadProgressCard()
            card.pauseRequested.connect(self._pause)
            card.resumeRequested.connect(self._resume)
            card.stopRequested.connect(self._stop)
            card.retryRequested.connect(self._retry)
            card.openRequested.connect(self._open)
            self._cards[item.item_id] = card
            self._card_host_layout.addWidget(card)
        card.apply(item)
        self._update_empty_state()

    def _on_state_changed(self, item: DownloadItem, state) -> None:
        card = self._cards.get(item.item_id)
        if card is not None:
            card.apply(item)

    def _update_empty_state(self) -> None:
        has_items = bool(self._cards)
        self.empty_state.setVisible(not has_items)
        self._card_host.setVisible(has_items)

    # -- commands ------------------------------------------------------------ #
    def _pause(self, item_id: str) -> None:
        if self._context is not None:
            self._context.downloads.pause(item_id)

    def _resume(self, item_id: str) -> None:
        if self._context is not None:
            self._context.downloads.resume(item_id)

    def _stop(self, item_id: str) -> None:
        if self._context is not None:
            self._context.downloads.stop(item_id)

    def _retry(self, item_id: str) -> None:
        if self._context is not None:
            self._context.downloads.retry(item_id)

    def _open(self, item_id: str) -> None:
        parent = self.window()
        if parent is not None and hasattr(parent, "navigate_to"):
            parent.navigate_to(NavTarget.WORKSPACE)

    def _pause_all(self) -> None:
        if self._context is None:
            return
        for item in self._context.download_items():
            self._context.downloads.pause(item.item_id)

    def _resume_all(self) -> None:
        if self._context is None:
            return
        for item in self._context.download_items():
            self._context.downloads.resume(item.item_id)

    def _clear_finished(self) -> None:
        if self._context is None:
            return
        from ...domain.enums import TaskState

        for item in list(self._context.download_items()):
            if item.state in (TaskState.COMPLETE, TaskState.CANCELLED):
                card = self._cards.pop(item.item_id, None)
                if card is not None:
                    self._card_host_layout.removeWidget(card)
                    card.setParent(None)
                    card.deleteLater()
        self._update_empty_state()
