"""Video playback adapters.

Two implementations of the same interface:

* :class:`MpvPlayer` - the real player. Requires ``mpv`` (python-mpv or the
  ``mpv`` binary) to be installed; it is optional.
* :class:`PlaceholderPlayer` - a dependency-free fallback that renders a
  synthetic frame description and drives a synthetic position clock. The
  workspace timeline, inspector and segment list all work against it, so the
  app is fully usable on a machine without mpv.

The class is deliberately Qt-free: the UI drives the placeholder clock with a
``QTimer`` and forwards ticks into :meth:`PlaceholderPlayer.tick`.
"""

from __future__ import annotations

import os
import shutil
from typing import Optional

__all__ = [
    "PlayerInfo",
    "PlaceholderPlayer",
    "MpvPlayer",
    "create_player",
    "mpv_available",
]


class PlayerInfo:
    """What the player is actually backed by - shown in the UI chrome."""

    def __init__(self, name: str, available: bool, detail: str = "") -> None:
        self.name = name
        self.available = available
        self.detail = detail

    def __repr__(self) -> str:  # pragma: no cover - debug helper
        return f"PlayerInfo({self.name!r}, available={self.available})"


class PlaceholderPlayer:
    """A no-dependency stand-in for a real video player.

    It keeps a synthetic position, honours play / pause / seek / rate and
    reports a duration. The UI renders a placeholder frame instead of video.
    """

    def __init__(self, duration: float = 0.0) -> None:
        self._position = 0.0
        self._duration = max(0.0, duration)
        self._playing = False
        self._rate = 1.0
        self._path: str = ""
        self.info = PlayerInfo(
            "Placeholder player",
            available=True,
            detail="No video output - playback is simulated.",
        )

    # -- interface --------------------------------------------------------- #
    def open(self, path: str) -> bool:
        self._path = path
        self._position = 0.0
        return True

    def close(self) -> None:
        self._path = ""
        self._position = 0.0
        self._playing = False

    def play(self) -> None:
        self._playing = True

    def pause(self) -> None:
        self._playing = False

    def seek(self, seconds: float) -> None:
        self._position = max(0.0, min(self._duration or seconds, seconds))

    def set_rate(self, rate: float) -> None:
        self._rate = max(0.1, min(4.0, rate))

    def set_duration(self, duration: float) -> None:
        self._duration = max(0.0, duration)

    # -- state ------------------------------------------------------------- #
    @property
    def position(self) -> float:
        return self._position

    @property
    def duration(self) -> float:
        return self._duration

    @property
    def is_playing(self) -> bool:
        return self._playing

    @property
    def rate(self) -> float:
        return self._rate

    @property
    def path(self) -> str:
        return self._path

    # -- synthetic clock --------------------------------------------------- #
    def tick(self, dt_s: float) -> float:
        """Advance the synthetic clock by ``dt_s`` seconds."""
        if not self._playing:
            return self._position
        self._position += dt_s * self._rate
        if self._duration and self._position >= self._duration:
            self._position = self._duration
            self._playing = False
        return self._position


class MpvPlayer:
    """Real playback through mpv.

    The import is deliberately lazy so the app starts fine on a machine
    without mpv. If mpv is unavailable the object still constructs, but
    :meth:`open` returns ``False`` and :attr:`info` reports the reason.
    """

    def __init__(self) -> None:
        self._impl = None
        self._position = 0.0
        self._duration = 0.0
        self._playing = False
        self._rate = 1.0
        self._path = ""
        self._error = ""
        self.info = PlayerInfo("mpv", available=mpv_available(), detail="")

    # -- setup ------------------------------------------------------------- #
    def _ensure_impl(self) -> bool:
        if self._impl is not None:
            return True
        try:  # pragma: no cover - depends on the host machine
            import mpv  # type: ignore
        except Exception as exc:  # pragma: no cover
            self._error = f"python-mpv is not installed ({exc})"
            self.info.available = False
            self.info.detail = self._error
            return False
        try:  # pragma: no cover
            self._impl = mpv.MPV(ytdl=False, quiet=True)
        except Exception as exc:  # pragma: no cover
            self._error = str(exc)
            self.info.available = False
            self.info.detail = self._error
            return False
        self.info.available = True
        self.info.detail = "mpv playback active"
        return True

    # -- interface --------------------------------------------------------- #
    def open(self, path: str) -> bool:
        if not self._ensure_impl():
            return False
        self._path = path
        try:  # pragma: no cover
            self._impl.play(path)
            self._duration = float(self._impl.get_property("duration") or 0.0)
            self._playing = True
            return True
        except Exception as exc:  # pragma: no cover
            self._error = str(exc)
            return False

    def close(self) -> None:
        if self._impl is not None:  # pragma: no cover
            try:
                self._impl.terminate()
            except Exception:
                pass
            self._impl = None
        self._playing = False
        self._position = 0.0

    def play(self) -> None:
        if self._impl is not None:  # pragma: no cover
            self._impl.play()
        self._playing = True

    def pause(self) -> None:
        if self._impl is not None:  # pragma: no cover
            self._impl.pause()
        self._playing = False

    def seek(self, seconds: float) -> None:
        self._position = max(0.0, seconds)
        if self._impl is not None:  # pragma: no cover
            self._impl.seek(seconds, reference="absolute")

    def set_rate(self, rate: float) -> None:
        self._rate = max(0.1, min(4.0, rate))
        if self._impl is not None:  # pragma: no cover
            self._impl.speed = self._rate

    @property
    def position(self) -> float:
        if self._impl is not None:  # pragma: no cover
            try:
                self._position = float(
                    self._impl.get_property("time-pos") or self._position
                )
            except Exception:
                pass
        return self._position

    @property
    def duration(self) -> float:
        if self._impl is not None:  # pragma: no cover
            try:
                self._duration = float(
                    self._impl.get_property("duration") or self._duration
                )
            except Exception:
                pass
        return self._duration

    @property
    def is_playing(self) -> bool:
        return self._playing

    @property
    def rate(self) -> float:
        return self._rate

    @property
    def path(self) -> str:
        return self._path


def mpv_available() -> bool:
    """True when either python-mpv or the mpv binary can be used."""
    if shutil.which("mpv"):
        return True
    try:  # pragma: no cover - depends on the host machine
        import mpv  # type: ignore  # noqa: F401
    except Exception:
        return False
    return True


def create_player(prefer_mpv: bool = True):
    """Return the best available player.

    Falls back to :class:`PlaceholderPlayer` whenever mpv is unavailable, so
    the caller never has to special-case a missing dependency.
    """
    if prefer_mpv and mpv_available():
        player = MpvPlayer()
        if player.info.available:
            return player
    return PlaceholderPlayer()
