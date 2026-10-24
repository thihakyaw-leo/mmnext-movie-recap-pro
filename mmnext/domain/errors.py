"""Domain-layer exception types.

These are plain exceptions with no Qt and no I/O.  Infrastructure may raise
them and the UI may catch them without importing a concrete adapter.
"""

from __future__ import annotations

__all__ = ["TranscriptStopped"]


class TranscriptStopped(RuntimeError):
    """Cooperative stop, raised only after durable state has been written."""
