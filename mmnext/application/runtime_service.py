"""Application-facing runtime dependency probe facade."""

from __future__ import annotations

from ..infrastructure.runtime import detect_dependencies

__all__ = ["RuntimeService"]


class RuntimeService:
    """Wraps dependency detection so the UI never imports infrastructure."""

    def detect(self) -> dict:
        return detect_dependencies()
