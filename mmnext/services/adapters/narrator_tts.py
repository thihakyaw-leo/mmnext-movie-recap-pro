"""Narrator speech synthesiser adapters.

``LegacyEdgeTtsAdapter`` wraps the Burmese Edge TTS voices behind the
``SpeechSynthesizer`` protocol. ``DemoSpeechSynthesizer`` is the deterministic
offline stand-in the test suite uses.

Both keep a content-addressed cache: the key is derived from the voice, the
rate and the text, so a segment whose narration has not changed is reused
instead of being synthesised again.  The cached file carries a **neutral**
``.audio`` extension because the format depends on the synthesiser (Edge TTS
writes MP3 bytes, the offline one writes text), and naming it ``.wav`` or
``.mp3`` would claim a format it does not have.

Writes go through a ``.partial`` file that is renamed into place, so an
interrupted synthesis can never leave a half-written file that a later run
mistakes for a finished one.
"""

from __future__ import annotations

import hashlib
import os
from pathlib import Path
from typing import Callable, Optional

from ..protocols import SpeechSynthesizer

__all__ = ["LegacyEdgeTtsAdapter", "DemoSpeechSynthesizer"]

DEFAULT_VOICES = ["my-MM-ThihaNeural", "my-MM-NilarNeural"]

#: Memoised "is ``edge_tts`` importable" answer.
#
# ``edge_tts`` pulls in ``aiohttp``, so the first import costs seconds, and the
# answer cannot change while the process runs.  Asking on every status read
# made a UI refresh pay that cost repeatedly.
_EDGE_TTS_STATE: Optional[bool] = None


def _edge_tts_importable() -> bool:
    global _EDGE_TTS_STATE
    if _EDGE_TTS_STATE is None:
        try:
            import edge_tts  # noqa: F401
        except Exception:
            _EDGE_TTS_STATE = False
        else:
            _EDGE_TTS_STATE = True
    return _EDGE_TTS_STATE


class _BaseSynthesizer:
    """Shared cache handling."""

    def __init__(self, cache_dir: Optional[str] = None,
                 log: Optional[Callable[[str], None]] = None) -> None:
        self.cache_dir = Path(cache_dir) if cache_dir else None
        self.log = log or (lambda msg: None)

    def cache_key(self, text: str, voice: str, rate: float) -> str:
        raw = f"{voice}|{rate}|{text}".encode("utf-8")
        return hashlib.sha256(raw).hexdigest()

    def cached_path(self, key: str) -> Optional[Path]:
        """The cache file for ``key``, or ``None`` when caching is off."""
        if self.cache_dir is None:
            return None
        return self.cache_dir / f"{key}.audio"

    def cache_hit(self, key: str) -> Optional[Path]:
        """The cached file when it exists and is non-empty."""
        cached = self.cached_path(key)
        try:
            if cached is not None and cached.is_file() and cached.stat().st_size > 0:
                return cached
        except OSError:
            return None
        return None

    def _publish(self, temporary: Path, target: Path) -> str:
        """Atomically move ``temporary`` onto ``target``."""
        target.parent.mkdir(parents=True, exist_ok=True)
        os.replace(temporary, target)
        return str(target)

    def _write_text(self, target: Path, text: str) -> str:
        target.parent.mkdir(parents=True, exist_ok=True)
        temporary = target.with_name(target.name + ".partial")
        temporary.write_text(text, encoding="utf-8")
        return self._publish(temporary, target)


class LegacyEdgeTtsAdapter(_BaseSynthesizer, SpeechSynthesizer):
    """Synthesise Burmese narration with Microsoft Edge TTS."""

    def __init__(self, cache_dir: Optional[str] = None,
                 log: Optional[Callable[[str], None]] = None) -> None:
        super().__init__(cache_dir=cache_dir, log=log)

    def available(self) -> bool:
        """True when the ``edge_tts`` package is importable."""
        return _edge_tts_importable()

    def voice_discovery(self) -> list[str]:
        return list(DEFAULT_VOICES)

    def synthesize_segment(
        self,
        text: str,
        voice: str = "my-MM-ThihaNeural",
        rate: float = 1.0,
        out_path: str = "",
    ) -> str:
        if not out_path:
            return ""
        key = self.cache_key(text, voice, rate)
        cached = self.cache_hit(key)
        if cached is not None:
            self.log(f"Speech cache hit: {key[:12]}")
            return self._publish_bytes(cached, Path(out_path))
        if not self.available():
            self.log("edge-tts is not installed; no audio was produced")
            return ""
        try:
            import asyncio

            import edge_tts

            target = Path(out_path)
            target.parent.mkdir(parents=True, exist_ok=True)
            temporary = target.with_name(target.name + ".partial")
            percent = int(round(float(rate) * 100))
            asyncio.run(
                edge_tts.Communicate(text, voice, rate=f"{percent:+d}%").save(
                    str(temporary)
                )
            )
            if not temporary.is_file() or temporary.stat().st_size <= 0:
                raise RuntimeError("edge-tts produced no audio")
            published = self._publish(temporary, target)
            cached = self.cached_path(key)
            if cached is not None:
                cached.parent.mkdir(parents=True, exist_ok=True)
                cached.write_bytes(Path(published).read_bytes())
            return published
        except Exception as exc:  # noqa: BLE001 - external dependency
            self.log(f"Speech synthesis failed: {exc}")
            return ""

    def _publish_bytes(self, source: Path, target: Path) -> str:
        """Copy cached bytes onto ``target`` through a ``.partial`` file."""
        target.parent.mkdir(parents=True, exist_ok=True)
        temporary = target.with_name(target.name + ".partial")
        temporary.write_bytes(source.read_bytes())
        return self._publish(temporary, target)


class DemoSpeechSynthesizer(_BaseSynthesizer, SpeechSynthesizer):
    """Deterministic offline synthesiser used by the test suite."""

    def available(self) -> bool:
        return True

    def voice_discovery(self) -> list[str]:
        return list(DEFAULT_VOICES)

    def synthesize_segment(
        self,
        text: str,
        voice: str = "my-MM-ThihaNeural",
        rate: float = 1.0,
        out_path: str = "",
    ) -> str:
        if not out_path:
            return ""
        key = self.cache_key(text, voice, rate)
        cached = self.cache_hit(key)
        if cached is not None:
            self.log(f"Speech cache hit: {key[:12]}")
            target = Path(out_path)
            target.parent.mkdir(parents=True, exist_ok=True)
            temporary = target.with_name(target.name + ".partial")
            temporary.write_bytes(cached.read_bytes())
            return self._publish(temporary, target)
        published = self._write_text(Path(out_path), text)
        cached = self.cached_path(key)
        if cached is not None:
            cached.parent.mkdir(parents=True, exist_ok=True)
            cached.write_text(text, encoding="utf-8")
        return published