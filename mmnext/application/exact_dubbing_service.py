"""Exact Dubbing application facade.

The UI must not import ``infrastructure`` directly, so this facade owns the
real FFmpeg renderer and the real Edge TTS synthesiser and hands the UI a
ready-to-run coordinator.

It is also the entry point of the *render from* ``translated_gender.json``
flow: the exported translation file is the contract between the translation
step and the render step, exactly as it is in the legacy pipeline.
"""

from __future__ import annotations

from pathlib import Path
from typing import Callable, Optional, Sequence

from ..domain.exact_dubbing import (
    DubbingTranslation,
    parse_translated_gender,
    validate_against_source,
)
from ..domain.models import ExactDubbingRow
from ..domain.paths import read_json
from ..infrastructure.exact_dubbing_render import FfmpegExactDubbingRenderer
from ..services.adapters.exact_dubbing_tts import (
    DemoExactDubbingTtsAdapter,
    LegacyExactDubbingTtsAdapter,
)
from .exact_dubbing_render_coordinator import (
    ExactDubbingRenderCoordinator,
    ExactDubbingRenderResult,
)

__all__ = ["ExactDubbingService"]


class ExactDubbingService:
    """Builds exact-dubbing render coordinators and reads translation files."""

    def __init__(
        self,
        jobs_dir: str,
        ffmpeg: str = "ffmpeg",
        ffprobe: str = "ffprobe",
        legacy_root: Optional[str] = None,
    ) -> None:
        self._jobs_dir = str(jobs_dir)
        self._ffmpeg = ffmpeg
        self._ffprobe = ffprobe
        self._legacy_root = legacy_root

    # -- capabilities -------------------------------------------------------- #
    @property
    def cache_dir(self) -> str:
        return str(Path(self._jobs_dir) / "exact_dubbing_tts")

    def renderer_available(self) -> bool:
        """True when FFmpeg and FFprobe are available."""
        return FfmpegExactDubbingRenderer(self._ffmpeg, self._ffprobe).available()

    def tts_available(self) -> bool:
        """True when the real Edge TTS synthesiser can be used."""
        return LegacyExactDubbingTtsAdapter().available()

    def is_demo(self) -> bool:
        """Whether the run would use simulated speech.

        The renderer is real whenever FFmpeg exists.  Only the *speech* can
        be simulated, and a simulated run is always labelled DEMO.
        """
        return not self.tts_available()

    # -- construction -------------------------------------------------------- #
    def create_coordinator(
        self,
        settings: Optional[dict] = None,
        log: Optional[Callable[[str], None]] = None,
    ) -> ExactDubbingRenderCoordinator:
        """Return a coordinator wired to the real renderer."""
        settings = dict(settings or {})
        cache_dir = str(settings.get("tts_cache_dir") or self.cache_dir)
        Path(cache_dir).mkdir(parents=True, exist_ok=True)
        tts = LegacyExactDubbingTtsAdapter(cache_dir=cache_dir, log=log)
        if not tts.available():
            tts = DemoExactDubbingTtsAdapter(cache_dir=cache_dir, log=log)
        renderer = FfmpegExactDubbingRenderer(
            ffmpeg=self._ffmpeg,
            ffprobe=self._ffprobe,
            log=log,
            work_dir=str(Path(cache_dir).parent / "exact_dubbing_work"),
        )
        return ExactDubbingRenderCoordinator(
            tts=tts,
            renderer=renderer,
            is_demo=not tts.available(),
            log=log,
        )

    # -- translation file ---------------------------------------------------- #
    def load_translated_gender(self, path: str) -> list[DubbingTranslation]:
        """Read and validate a ``translated_gender.json`` file."""
        payload = read_json(path)
        if payload is None:
            raise FileNotFoundError(f"Translation file not found: {path}")
        return parse_translated_gender(payload)

    def validate_translation(
        self,
        path: str,
        source_rows: Sequence[ExactDubbingRow],
    ) -> list[DubbingTranslation]:
        """Read a translation file and check it against the locked source rows."""
        rows = self.load_translated_gender(path)
        validate_against_source(rows, source_rows)
        return rows

    # -- render -------------------------------------------------------------- #
    def render_from_translated_gender(
        self,
        translation_path: str,
        source_rows: Sequence[ExactDubbingRow],
        video_path: str,
        total_duration: float,
        output_path: str,
        settings: Optional[dict] = None,
        sink=None,
        log: Optional[Callable[[str], None]] = None,
    ) -> ExactDubbingRenderResult:
        """Render a dubbed video starting from a ``translated_gender.json`` file.

        The translation is validated against the locked source rows *before*
        any speech is synthesised, so a drifted translation never produces a
        partial render.
        """
        settings = dict(settings or {})
        self.validate_translation(translation_path, source_rows)
        coordinator = self.create_coordinator(settings=settings, log=log)
        return coordinator.run(
            source_rows,
            video_path,
            total_duration,
            output_path,
            settings,
            sink=sink,
        )
