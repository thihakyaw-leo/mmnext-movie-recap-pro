"""Runtime dependency probing.

The top bar of the main window has to tell the truth about what is actually
installed on the machine. This module probes the environment once at start-up
and returns a plain, Qt-free description of every optional dependency.

Nothing here is imported by the domain or application layers, and nothing
here raises: a missing tool is a *result*, not an error.
"""

from __future__ import annotations

import importlib.util
import shutil
from dataclasses import dataclass

from .player import mpv_available

__all__ = ["DependencyStatus", "detect_dependencies", "DEPENDENCY_ORDER"]


@dataclass(frozen=True, slots=True)
class DependencyStatus:
    """The state of one optional dependency."""

    name: str
    available: bool
    detail: str = ""

    @property
    def display(self) -> str:
        """Short text for the top bar."""
        if self.available:
            return self.detail or "available"
        return self.detail or "not installed"


#: Display order used by the top bar and the settings screen.
DEPENDENCY_ORDER: tuple[str, ...] = (
    "ffmpeg",
    "ffprobe",
    "numpy",
    "mpv",
    "nvidia",
    "whisper",
    "yt_dlp",
    "edge_tts",
)


def _binary(name: str) -> bool:
    return shutil.which(name) is not None


def _module(name: str) -> bool:
    try:
        return importlib.util.find_spec(name) is not None
    except (ImportError, ValueError):  # pragma: no cover - broken installs
        return False


def detect_dependencies() -> dict[str, DependencyStatus]:
    """Probe every optional dependency.

    Returns a mapping keyed by the names in :data:`DEPENDENCY_ORDER`.
    """
    ffmpeg = _binary("ffmpeg")
    ffprobe = _binary("ffprobe")
    numpy = _module("numpy")
    mpv = mpv_available()
    nvidia = _binary("nvidia-smi")
    whisper = _module("whisper")
    yt_dlp = _module("yt_dlp")
    edge_tts = _module("edge_tts")

    found: dict[str, DependencyStatus] = {
        "ffmpeg": DependencyStatus(
            "FFmpeg", ffmpeg, "found" if ffmpeg else "not installed"
        ),
        "ffprobe": DependencyStatus(
            "FFprobe", ffprobe, "found" if ffprobe else "not installed"
        ),
        "numpy": DependencyStatus(
            "NumPy", numpy, "installed" if numpy else "not installed"
        ),
        "mpv": DependencyStatus(
            "mpv", mpv, "available" if mpv else "not installed"
        ),
        "nvidia": DependencyStatus(
            "NVIDIA GPU", nvidia, "detected" if nvidia else "not detected"
        ),
        "whisper": DependencyStatus(
            "Whisper", whisper, "installed" if whisper else "not installed"
        ),
        "yt_dlp": DependencyStatus(
            "yt-dlp", yt_dlp, "installed" if yt_dlp else "not installed"
        ),
        "edge_tts": DependencyStatus(
            "Edge TTS", edge_tts, "installed" if edge_tts else "not installed"
        ),
    }
    return {key: found[key] for key in DEPENDENCY_ORDER}
