"""Application-facing video player facade."""

from __future__ import annotations

from typing import Any

from ..infrastructure.player import PlaceholderPlayer, create_player

__all__ = ["PlayerService"]


class PlayerService:
    """Wraps the optional real player adapters for the UI layer."""

    def create(self) -> Any:
        return create_player()

    @staticmethod
    def info(player: Any) -> Any:
        return player.info

    @staticmethod
    def is_placeholder(player: Any) -> bool:
        return isinstance(player, PlaceholderPlayer)

    @staticmethod
    def tick_placeholder(player: Any, delta_seconds: float) -> None:
        if isinstance(player, PlaceholderPlayer):
            player.tick(delta_seconds)
