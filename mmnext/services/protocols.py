"""Protocols (structural interfaces) for every external capability.

These are ``typing.Protocol`` classes, so an implementation does not need to
inherit from anything - the demo adapters and the future real adapters are
interchangeable as long as they match the shape.
"""

from __future__ import annotations

from typing import Callable, Optional, Protocol, Sequence, runtime_checkable

from ..domain.enums import AppMode
from ..domain.events import JobEvent

@runtime_checkable
class CommonEditingExporter(Protocol):
    def available(self) -> bool:  # pragma: no cover
        ...

    def export(
        self,
        video_path: str,
        session: object,
        output_path: str,
        settings: dict,
    ) -> bool:  # pragma: no cover
        ...

__all__ = [
    "EventSink",
    "MetadataService",
    "DownloadService",
    "JobRunner",
    "TranscriptionService",
    "TranscriptProvider",
    "TranslationService",
    "TtsService",
    "SplitterService",
    "VideoPlayer",
    "PlayerState",
    "TranslationProvider",
    "SpeechSynthesizer",
    "ExactDubbingRenderer",
]


@runtime_checkable
class EventSink(Protocol):
    """Receives structured events produced by a worker."""

    def emit(self, event: JobEvent) -> None:  # pragma: no cover - protocol
        ...


@runtime_checkable
class MetadataService(Protocol):
    """Resolves metadata for a source (real: yt-dlp; demo: fixture)."""

    def analyze(self, source: VideoSource) -> SourceMetadata:  # pragma: no cover
        ...


@runtime_checkable
class DownloadService(Protocol):
    """Downloads a remote source with pause / resume / stop / retry."""

    def start(self, source: VideoSource, quality: str = "best") -> str:
        """Begin a download and return the task id."""

    def pause(self, task_id: str) -> None:  # pragma: no cover
        ...

    def resume(self, task_id: str) -> None:  # pragma: no cover
        ...

    def stop(self, task_id: str) -> None:  # pragma: no cover
        ...

    def retry(self, task_id: str) -> None:  # pragma: no cover
        ...

    @property
    def tasks(self) -> Sequence[object]:  # pragma: no cover
        ...

    def resume_supported(self) -> bool: ...


@runtime_checkable
class JobRunner(Protocol):
    """Runs a job stage and streams events."""

    def run(self, job: Job, sink: EventSink) -> None:  # pragma: no cover
        ...


@runtime_checkable
class TranscriptionService(Protocol):
    """Produces a verbatim transcript."""

    def transcribe(self, media_path: str) -> list[TranscriptRow]:  # pragma: no cover
        ...


@runtime_checkable
class TranscriptProvider(Protocol):
    """Transcript provider with language selection, auto-detect and progress."""

    def transcribe(
        self,
        media_path: str,
        language: Optional[str] = None,
        auto_detect: bool = False,
        emit: Optional[Callable[[JobEvent], None]] = None,
    ) -> tuple[list[TranscriptRow], str]:  # pragma: no cover
        """Return rows and detected language. Emit events via emit if supplied."""
        ...


@runtime_checkable
class TranslationService(Protocol):
    """Translates source rows into Burmese."""

    def translate(
        self, rows: Sequence[TranscriptRow], mode: AppMode
    ) -> list[ExactDubbingRow]:  # pragma: no cover
        ...


@runtime_checkable
class TtsService(Protocol):
    """Synthesises Burmese speech."""

    def synthesize(self, rows: Sequence[ExactDubbingRow], out_dir: str) -> list[str]:
        # pragma: no cover
        ...


@runtime_checkable
class SplitterService(Protocol):
    """Plans split parts for the splitter mode."""

    def plan(self, duration_s: float, part_seconds: float) -> list[object]:
        # pragma: no cover
        ...


@runtime_checkable
class PlayerState(Protocol):
    """Snapshot of a player, used by the workspace preview."""

    position: float
    duration: float
    playing: bool


@runtime_checkable
class VideoPlayer(Protocol):
    """Video playback adapter interface.

    ``MpvPlayer`` (infrastructure) is the real implementation; the UI ships
    with a ``PlaceholderPlayer`` fallback that renders a synthetic frame and
    drives a synthetic position clock, so the workspace is fully usable when
    mpv is absent.
    """

    def open(self, path: str) -> bool:  # pragma: no cover
        ...

    def close(self) -> None:  # pragma: no cover
        ...

    def play(self) -> None:  # pragma: no cover
        ...

    def pause(self) -> None:  # pragma: no cover
        ...

    def seek(self, seconds: float) -> None:  # pragma: no cover
        ...

    def set_rate(self, rate: float) -> None:  # pragma: no cover
        ...

    @property
    def position(self) -> float:  # pragma: no cover
        ...

    @property
    def duration(self) -> float:  # pragma: no cover
        ...

    @property
    def is_playing(self) -> bool:  # pragma: no cover
        ...


@runtime_checkable
class TranslationProvider(Protocol):
    """Translates narrator units into Burmese narration text.

    The input is the *narrator* unit list, never the exact-dubbing rows:
    narrator translation is a separate contract from dubbing translation.
    """

    def translate_segments(
        self,
        segments: Sequence[NarrationSegment],
        language_code: Optional[str] = None,
        context: Optional[str] = None,
        glossary: Optional[dict[str, str]] = None,
    ) -> list[str]:  # pragma: no cover
        """Return one Myanmar translation per segment, in the same order."""
        ...

    def stage_progress(self) -> dict:  # pragma: no cover
        ...


@runtime_checkable
class SpeechSynthesizer(Protocol):
    """Synthesises Burmese speech for narrator segments."""

    def synthesize_segment(
        self,
        text: str,
        voice: str = "my-MM-ThihaNeural",
        rate: float = 1.0,
        out_path: str = "",
    ) -> str:  # pragma: no cover
        ...

    def voice_discovery(self) -> list[str]:  # pragma: no cover
        ...

    def cache_key(self, text: str, voice: str, rate: float) -> str:  # pragma: no cover
        ...


@runtime_checkable
class SmartSyncRenderer(Protocol):
    """Renders the Smart Sync timeline for a narrator recap."""

    def render(
        self,
        video_path: str,
        segments: Sequence[NarrationSegment],
        output_path: str,
        settings: dict,
    ) -> bool:  # pragma: no cover
        ...

    def stage_progress(self) -> dict:  # pragma: no cover
        ...


@runtime_checkable
class ExactDubbingRenderer(Protocol):
    """Renders an exact-dubbing recap without changing source rows."""

    def render(
        self,
        video_path: str,
        rows: Sequence[ExactDubbingRow],
        output_path: str,
        settings: dict,
    ) -> bool:  # pragma: no cover
        ...

    def stage_progress(self) -> dict:  # pragma: no cover
        ...
@runtime_checkable
class SplitterPlanner(Protocol):
    def plan(
        self,
        duration: float,
        part_seconds: float,
        max_extra_wait: float = 5.0,
        pause_times: Optional[Sequence[float]] = None,
        smart_cut: bool = False,
    ) -> list:  # pragma: no cover
        ...


@runtime_checkable
class SplitterRenderer(Protocol):
    def available(self) -> bool:  # pragma: no cover
        ...

    def stage_progress(self) -> dict:  # pragma: no cover
        ...

    def render_part(
        self,
        video_path: str,
        part: object,
        output_path: str,
        settings: dict,
    ) -> bool:  # pragma: no cover
        ...

    def render(
        self,
        video_path: str,
        parts: Sequence[object],
        output_path: str,
        settings: dict,
    ) -> bool:  # pragma: no cover
        ...
