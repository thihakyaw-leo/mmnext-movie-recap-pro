"""Exact Dubbing TTS adapters.

The exact-dubbing contract differs from the narrator contract in three ways
that matter here:

* the voice comes from the **speaker gender** of the row, not from a global
  narrator voice setting (``male`` -> ``my-MM-ThihaNeural``, ``female`` and
  ``unknown`` -> ``my-MM-NilarNeural``);
* the cache signature covers **only** the voice and the Burmese text, so
  re-ordering rows never invalidates a cached segment and changing a single
  word always does;
* the speech is fitted to the locked source window with FFmpeg ``atempo``
  downstream, so the synthesiser itself never applies a rate.

Two adapters are provided:

``LegacyExactDubbingTtsAdapter``
    The real Edge TTS synthesiser.  It writes through a ``.partial`` file and
    renames it into place, and it uses the documented retry ladder
    (6 attempts, 5/10/20/40/60 second backoff) because the Edge WebSocket
    service fails transiently.

``DemoExactDubbingTtsAdapter``
    A deterministic **offline** synthesiser that emits a real PCM WAV whose
    length follows the Burmese text.  It is simulated speech - it is always
    labelled DEMO - but the audio is real, so the fitting, mixing, muxing and
    final validation chain is exercised end to end without a network.
"""

from __future__ import annotations

import asyncio
import hashlib
import math
import os
import struct
import time
import wave
from pathlib import Path
from typing import Callable, Optional

from ...domain.exact_dubbing import EXACT_DUB_VOICES, cache_signature, voice_for_gender

__all__ = [
    "LegacyExactDubbingTtsAdapter",
    "DemoExactDubbingTtsAdapter",
    "LocalWaveTtsAdapter",
    "EXACT_DUB_VOICES",
]

#: The documented Edge TTS retry ladder (seconds between attempts).
RETRY_BACKOFF_SECONDS = (5, 10, 20, 40, 60)


class _BaseExactDubbingTts:
    """Shared cache handling for the exact-dubbing synthesizers."""

    def __init__(
        self,
        cache_dir: Optional[str] = None,
        log: Optional[Callable[[str], None]] = None,
    ) -> None:
        self.cache_dir = Path(cache_dir) if cache_dir else None
        self.log = log or (lambda msg: None)

    # -- protocol ---------------------------------------------------------- #
    def voice_discovery(self) -> list[str]:
        return sorted(set(EXACT_DUB_VOICES.values()))

    def voice_for_gender(self, gender: str) -> str:
        return voice_for_gender(gender)

    def cache_key(self, text: str, voice: str = "my-MM-NilarNeural", rate: float = 1.0) -> str:
        """Return the content-addressed cache signature.

        ``rate`` is deliberately ignored: the exact-dubbing fit is applied
        with FFmpeg ``atempo`` after synthesis, so two calls that differ only
        in ``rate`` must share one cache entry.
        """
        return cache_signature(voice, text)

    # -- cache ------------------------------------------------------------- #
    def _signature_path(self, out_path: Path) -> Path:
        return out_path.with_suffix(out_path.suffix + ".sha256")

    def _cache_hit(self, out_path: Path, signature: str) -> bool:
        stamp = self._signature_path(out_path)
        try:
            return (
                out_path.is_file()
                and out_path.stat().st_size > 0
                and stamp.is_file()
                and stamp.read_text(encoding="ascii").strip() == signature
            )
        except OSError:
            return False

    def _commit(self, temporary: Path, out_path: Path, signature: str) -> str:
        """Atomically publish ``temporary`` as ``out_path`` with its stamp."""
        out_path.parent.mkdir(parents=True, exist_ok=True)
        os.replace(temporary, out_path)
        self._signature_path(out_path).write_text(signature, encoding="ascii")
        return str(out_path)


class LegacyExactDubbingTtsAdapter(_BaseExactDubbingTts):
    """Synthesise Burmese exact-dubbing speech with Microsoft Edge TTS."""

    def __init__(
        self,
        cache_dir: Optional[str] = None,
        log: Optional[Callable[[str], None]] = None,
        voice: str = "my-MM-NilarNeural",
    ) -> None:
        super().__init__(cache_dir=cache_dir, log=log)
        self.voice = voice

    def available(self) -> bool:
        """True when the ``edge_tts`` package is importable."""
        try:
            import edge_tts  # noqa: F401
        except Exception:
            return False
        return True

    def synthesize_segment(
        self,
        text: str,
        voice: str = "my-MM-NilarNeural",
        rate: float = 1.0,
        out_path: str = "",
    ) -> str:
        if not out_path or not text.strip():
            return ""
        target = Path(out_path)
        voice = voice or self.voice
        signature = self.cache_key(text, voice, rate)
        if self._cache_hit(target, signature):
            self.log(f"Exact dubbing speech cache hit: {signature[:12]}")
            return str(target)
        if not self.available():
            self.log("edge-tts is not installed; no audio was produced")
            return ""

        target.parent.mkdir(parents=True, exist_ok=True)
        temporary = target.with_name(target.name + ".partial")
        last_error: Optional[Exception] = None
        for attempt in range(len(RETRY_BACKOFF_SECONDS) + 1):
            try:
                import edge_tts

                asyncio.run(
                    edge_tts.Communicate(text, voice).save(str(temporary))
                )
                last_error = None
                break
            except Exception as exc:  # noqa: BLE001 - external dependency
                last_error = exc
                if attempt >= len(RETRY_BACKOFF_SECONDS):
                    break
                delay = RETRY_BACKOFF_SECONDS[attempt]
                self.log(
                    f"Exact dubbing TTS retry {attempt + 1}: {exc}; retry in {delay}s"
                )
                time.sleep(delay)
        if last_error is not None:
            self.log(f"Exact dubbing speech synthesis failed: {last_error}")
            if temporary.exists():
                try:
                    temporary.unlink()
                except OSError:
                    pass
            return ""
        if not temporary.is_file() or temporary.stat().st_size <= 0:
            self.log("Exact dubbing speech synthesis produced no audio")
            return ""
        return self._commit(temporary, target, signature)


class LocalWaveTtsAdapter(_BaseExactDubbingTts):
    """Offline synthesiser that emits a real PCM WAV of a plausible length.

    The generated length follows the Burmese text, so the speech-fitting maths
    (window, ``atempo`` ratio, mixing) is exercised against real audio
    instead of a placeholder file.  The waveform is a quiet tone, not speech:
    the result is always labelled DEMO.
    """

    def __init__(
        self,
        cache_dir: Optional[str] = None,
        log: Optional[Callable[[str], None]] = None,
        chars_per_second: float = 7.0,
        sample_rate: int = 44100,
        frequency: float = 220.0,
    ) -> None:
        super().__init__(cache_dir=cache_dir, log=log)
        self.chars_per_second = float(chars_per_second)
        self.sample_rate = int(sample_rate)
        self.frequency = float(frequency)

    def available(self) -> bool:
        return True

    def _duration_for(self, text: str) -> float:
        # Myanmar text is dense; count every codepoint, but ignore spaces.
        units = sum(1 for ch in text if not ch.isspace())
        return max(0.25, units / max(0.5, self.chars_per_second))

    def _write_wave(self, path: Path, duration: float) -> None:
        frames = int(round(duration * self.sample_rate))
        path.parent.mkdir(parents=True, exist_ok=True)
        step = 2 * math.pi * self.frequency / self.sample_rate
        with wave.open(str(path), "wb") as handle:
            handle.setnchannels(1)
            handle.setsampwidth(2)
            handle.setframerate(self.sample_rate)
            for index in range(frames):
                value = int(3000 * math.sin(step * index))
                handle.writeframesraw(struct.pack("<h", value))

    def synthesize_segment(
        self,
        text: str,
        voice: str = "my-MM-NilarNeural",
        rate: float = 1.0,
        out_path: str = "",
    ) -> str:
        if not out_path or not text.strip():
            return ""
        target = Path(out_path)
        voice = voice or self.voice_for_gender("unknown")
        signature = self.cache_key(text, voice, rate)
        if self._cache_hit(target, signature):
            self.log(f"Exact dubbing speech cache hit: {signature[:12]}")
            return str(target)
        temporary = target.with_name(target.name + ".partial")
        self._write_wave(temporary, self._duration_for(text))
        if not temporary.is_file() or temporary.stat().st_size <= 0:
            return ""
        return self._commit(temporary, target, signature)


#: The offline synthesiser is also the demo adapter.
DemoExactDubbingTtsAdapter = LocalWaveTtsAdapter


def _sha256_hex(data: bytes) -> str:
    """Small helper kept for callers that hash raw bytes."""
    return hashlib.sha256(data).hexdigest()
