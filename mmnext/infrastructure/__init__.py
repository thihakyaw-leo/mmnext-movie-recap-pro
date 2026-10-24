"""Infrastructure adapters.

This package implements the :mod:`mmnext.services.protocols` interfaces with
concrete, external-facing code (mpv, FFmpeg, Whisper, Edge TTS...). It is
the only place allowed to know about third-party binaries.

Nothing here is imported at start-up except by
:mod:`mmnext.bootstrap`, and every adapter degrades gracefully when the
external tool is missing.
"""

from __future__ import annotations

__all__ = ["player", "runtime"]
