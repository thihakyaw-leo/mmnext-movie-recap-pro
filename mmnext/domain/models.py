"""Typed domain models.

Every model is a frozen-ish dataclass with explicit fields. Nothing in this
module imports Qt, and nothing in this module performs I/O.

Important contract
-----------------
``NarrationSegment`` and ``ExactDubbingRow`` are **separate** types with **no
shared base class and no converter**. The legacy narrator pipeline summarises
and re-orders dialogue; the legacy exact-dubbing pipeline must never
summarise, omit, reorder or merge a single row. Merging the two types would
make that distinction unrepresentable, so it is forbidden by design.
"""

from __future__ import annotations

from dataclasses import dataclass, field, replace
from pathlib import Path
from typing import Any, Dict, Optional, Sequence

from .enums import (
    AppMode,
    CutReason,
    FrameFill,
    Gender,
    JobState,
    LogLevel,
    OutputRatio,
    OverlayKind,
    Severity,
    SourceType,
    Stage,
    TaskState,
)

__all__ = [
    "VideoSource",
    "VideoQuality",
    "SourceMetadata",
    "TranscriptRow",
    "TranscriptMetadata",
    "NarrationSegment",
    "ExactDubbingRow",
    "SplitPart",
    "TimelineRange",
    "Overlay",
    "TimelineRange",
    "ExportPreset",
    "ValidationIssue",
    "ValidationReport",
    "Job",
    "JobProgress",
    "JobCheckpoint",
    "LogEntry",
    "ProjectSession",
    "DownloadItem",
    "TimelineMarker",
]


# --------------------------------------------------------------------------- #
# Source
# --------------------------------------------------------------------------- #
@dataclass(slots=True)
class VideoQuality:
    """One selectable rendition of a remote source."""

    quality_id: str
    label: str
    width: int
    height: int
    fps: float
    bitrate_kbps: int
    filesize_mb: float
    container: str = "mp4"

    @property
    def resolution(self) -> str:
        return f"{self.width}x{self.height}"

    @property
    def display(self) -> str:
        return f"{self.label}  {self.resolution}  {self.fps:.0f}fps  {self.filesize_mb:.0f} MB"


@dataclass(slots=True)
class VideoSource:
    """A local file or a YouTube reference selected by the user."""

    source_type: SourceType
    location: str
    display_name: str = ""
    duration_s: float = 0.0

    @property
    def is_remote(self) -> bool:
        return self.source_type is SourceType.YOUTUBE

    @property
    def name(self) -> str:
        return self.display_name or Path(self.location).name or self.location

    @classmethod
    def local(cls, path: str | Path) -> "VideoSource":
        p = Path(path)
        return cls(
            source_type=SourceType.LOCAL_FILE,
            location=str(p),
            display_name=p.name,
        )

    @classmethod
    def youtube(cls, url: str) -> "VideoSource":
        return cls(
            source_type=SourceType.YOUTUBE,
            location=url,
            display_name=url.rsplit("/", 1)[-1] or url,
        )


@dataclass(slots=True)
class SourceMetadata:
    """Metadata produced by the analyze step (real or demo)."""

    title: str
    channel: str
    duration_s: float
    published: str
    description: str
    thumbnail_hint: str = ""
    qualities: list[VideoQuality] = field(default_factory=list)
    has_audio: bool = True
    has_video: bool = True
    language: str = "en"

    @property
    def duration_display(self) -> str:
        total = int(self.duration_s)
        hours, rem = divmod(total, 3600)
        minutes, seconds = divmod(rem, 60)
        if hours:
            return f"{hours}:{minutes:02d}:{seconds:02d}"
        return f"{minutes}:{seconds:02d}"


# --------------------------------------------------------------------------- #
# Transcript / narration  (narrator world)
# --------------------------------------------------------------------------- #
@dataclass(slots=True)
class TranscriptRow:
    """A verbatim source transcript row.

    In narrator mode rows are the *source of truth*; the narrator text is a
    derived artefact. In exact-dubbing mode the row identity
    (``id``/``original``/``start``/``duration``) is immutable.
    """

    row_id: str
    start: float
    duration: float
    text: str

    @property
    def end(self) -> float:
        return self.start + self.duration


@dataclass(slots=True)
class TranscriptMetadata:
    """Metadata produced by the transcription step."""

    language: str
    language_confidence: float = 0.0
    model: str = ""
    duration_s: float = 0.0
    is_demo: bool = False
    source_fingerprint: str = ""


@dataclass(slots=True)
class NarrationSegment:
    """A narrator-mode segment.

    Carries both the source excerpt it covers and the Myanmar narration written
    over it, plus the boundary metadata the legacy planner produced.
    """

    segment_id: str
    source_segment_ids: list[str]
    source_text: str
    narration: str
    video_start: float
    video_end: float
    order: int = 0
    translation: str = ""
    semantic_boundary: bool = False
    forced_boundary: bool = False
    visual_reason: str = ""
    dirty: bool = False

    @property
    def duration(self) -> float:
        return max(0.0, self.video_end - self.video_start)

    @property
    def start(self) -> float:
        return self.video_start

    @property
    def end(self) -> float:
        return self.video_end

    def with_narration(self, text: str) -> "NarrationSegment":
        return replace(self, narration=text, dirty=True)


# --------------------------------------------------------------------------- #
# Exact dubbing
# --------------------------------------------------------------------------- #
@dataclass(slots=True)
class ExactDubbingRow:
    """One exact-dubbing table row.

    Contract (from the legacy exact-dubbing pipeline):
      * row count and order must match the source transcript exactly;
      * ``row_id`` and ``original`` are immutable;
      * ``start`` and ``duration`` must match the source within 1e-6;
      * ``burmese`` must be non-empty and contain Myanmar codepoints;
      * ``gender`` is one of male/female/unknown and is derived from the
        *speaker*, never from a mentioned character.
    """

    row_id: str
    start: float
    duration: float
    original: str
    burmese: str = ""
    gender: Gender = Gender.UNKNOWN
    edited: bool = False

    @property
    def end(self) -> float:
        return self.start + self.duration

    @property
    def voice(self) -> str:
        return self.gender.voice

    def is_translatable(self) -> bool:
        return bool(self.original.strip())


# --------------------------------------------------------------------------- #
# Splitter
# --------------------------------------------------------------------------- #
@dataclass(slots=True)
class SplitPart:
    """A planned output part of the splitter mode."""

    number: int
    start: float
    end: float
    cut_reason: CutReason = CutReason.EXACT
    label: str = ""
    include: bool = True

    @property
    def duration(self) -> float:
        return max(0.0, self.end - self.start)


# --------------------------------------------------------------------------- #
# Overlays (common editing)
# --------------------------------------------------------------------------- #
@dataclass(slots=True)
class Overlay:
    """A production overlay such as title, logo or extra text."""

    kind: OverlayKind
    text: str = ""
    start: float = 0.0
    end: float = 0.0
    position: str = "center"
    enabled: bool = True

    @property
    def duration(self) -> float:
        return max(0.0, self.end - self.start)


@dataclass(slots=True)
class TimelineRange:
    """A non-destructive trim range for common editing."""

    start: float = 0.0
    end: float = 0.0

    def __post_init__(self) -> None:
        if self.start < 0 or self.end < self.start:
            raise ValueError("Invalid trim range")

    @property
    def duration(self) -> float:
        return max(0.0, self.end - self.start)


# --------------------------------------------------------------------------- #
# Validation
# --------------------------------------------------------------------------- #
@dataclass(slots=True)
class ExportPreset:
    """Common-editing export settings."""

    ratio: OutputRatio = OutputRatio.ORIGINAL
    fill: FrameFill = FrameFill.BLUR
    trim_start: float = 0.0
    trim_end: float = 0.0
    overlays: list[Overlay] = field(default_factory=list)


@dataclass(slots=True)
class ValidationIssue:
    """A single validation finding."""

    code: str
    message: str
    severity: Severity = Severity.ERROR
    row_id: str = ""
    field: str = ""

    @property
    def blocks_render(self) -> bool:
        return self.severity.blocks_render


@dataclass(slots=True)
class ValidationReport:
    """Aggregated validation result for a working set."""

    issues: list[ValidationIssue] = field(default_factory=list)
    checked_rows: int = 0

    @property
    def errors(self) -> list[ValidationIssue]:
        return [i for i in self.issues if i.severity is Severity.ERROR]

    @property
    def warnings(self) -> list[ValidationIssue]:
        return [i for i in self.issues if i.severity is Severity.WARNING]

    @property
    def ok(self) -> bool:
        return not self.errors

    @property
    def summary(self) -> str:
        if not self.issues:
            return f"{self.checked_rows} rows validated, no issues"
        return (
            f"{self.checked_rows} rows validated - "
            f"{len(self.errors)} errors, {len(self.warnings)} warnings"
        )


# --------------------------------------------------------------------------- #
# Jobs
# --------------------------------------------------------------------------- #
@dataclass(slots=True)
class JobProgress:
    """Progress snapshot for a running job."""

    percent: float = 0.0
    stage: Stage = Stage.IDLE
    message: str = ""
    bytes_done: int = 0
    bytes_total: int = 0
    speed_bps: float = 0.0
    eta_s: float = 0.0

    @property
    def percent_int(self) -> int:
        return int(max(0.0, min(100.0, self.percent)))

    @property
    def speed_display(self) -> str:
        if self.speed_bps <= 0:
            return "-"
        mbps = self.speed_bps / (1024 * 1024)
        return f"{mbps:.2f} MB/s"

    @property
    def eta_display(self) -> str:
        if self.eta_s <= 0:
            return "-"
        total = int(self.eta_s)
        minutes, seconds = divmod(total, 60)
        hours, minutes = divmod(minutes, 60)
        if hours:
            return f"{hours}h {minutes:02d}m {seconds:02d}s"
        return f"{minutes:02d}m {seconds:02d}s"

    @property
    def size_display(self) -> str:
        if self.bytes_total <= 0:
            return "-"
        done = self.bytes_done / (1024 * 1024)
        total = self.bytes_total / (1024 * 1024)
        return f"{done:.1f} / {total:.1f} MB"


# --------------------------------------------------------------------------- #
# Checkpoints
# --------------------------------------------------------------------------- #
CHECKPOINT_SCHEMA_VERSION = 2


@dataclass(slots=True)
class JobCheckpoint:
    """A safe-stop checkpoint for one long-running task.

    The checkpoint is the *only* evidence that a task may be reported as
    paused or stopped. It records:

    * how much work is durably done (``completed_units`` / ``total_units``);
    * where the partially written artefact lives (``partial_path``);
    * whether the adapter is able to continue from this point
      (``resume_supported``);
    * the fingerprint of the inputs, so a checkpoint written for different
      inputs is never reused.

    A checkpoint is written atomically: a temporary ``.partial`` file is
    written and then renamed over the target, so a crash can never leave a
    half-written checkpoint behind.
    """

    task_id: str
    mode: str = ""
    state: TaskState = TaskState.RUNNING
    completed_units: int = 0
    total_units: int = 0
    partial_path: str = ""
    output_path: str = ""
    resume_supported: bool = False
    fingerprint: str = ""
    schema_version: int = CHECKPOINT_SCHEMA_VERSION
    updated_at: str = ""
    message: str = ""
    # Appended at the end so the positional order of the original fields is
    # preserved for any existing caller.
    fingerprint_settings: Dict[str, Any] = field(default_factory=dict)
    fingerprint_source_type: str = ""
    fingerprint_schema_version: int = 0

    @property
    def percent(self) -> float:
        if self.total_units <= 0:
            return 0.0
        return min(100.0, self.completed_units * 100.0 / self.total_units)

    @property
    def is_parked(self) -> bool:
        """True when the task is parked on this checkpoint."""
        return self.state in {TaskState.PAUSED, TaskState.STOPPED}

    def can_resume(self) -> bool:
        """Whether the adapter may continue from this checkpoint.

        A checkpoint is resumable only when the adapter says so *and* the
        work is genuinely parked (not running, not failed, not complete).
        """
        if not self.resume_supported:
            return False
        if self.state not in {TaskState.PAUSED, TaskState.STOPPED}:
            return False
        return self.completed_units < self.total_units or self.total_units <= 0

    def to_dict(self) -> dict:
        """Serialise to a JSON-safe dictionary."""
        return {
            "schema_version": self.schema_version,
            "task_id": self.task_id,
            "mode": self.mode,
            "state": self.state.value,
            "completed_units": self.completed_units,
            "total_units": self.total_units,
            "partial_path": self.partial_path,
            "output_path": self.output_path,
            "resume_supported": self.resume_supported,
            "fingerprint": self.fingerprint,
            "fingerprint_settings": dict(self.fingerprint_settings or {}),
            "fingerprint_source_type": self.fingerprint_source_type,
            "fingerprint_schema_version": int(self.fingerprint_schema_version or 0),
            "updated_at": self.updated_at,
            "message": self.message,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "JobCheckpoint":
        """Rebuild a checkpoint from :meth:`to_dict` output.

        Unknown keys are ignored and an unknown ``state`` falls back to
        ``RUNNING`` so a newer/older checkpoint file can still be read.
        """
        try:
            state = TaskState(str(data.get("state", TaskState.RUNNING.value)))
        except ValueError:
            state = TaskState.RUNNING
        return cls(
            task_id=str(data.get("task_id", "")),
            mode=str(data.get("mode", "")),
            state=state,
            completed_units=int(data.get("completed_units", 0) or 0),
            total_units=int(data.get("total_units", 0) or 0),
            partial_path=str(data.get("partial_path", "") or ""),
            output_path=str(data.get("output_path", "") or ""),
            resume_supported=bool(data.get("resume_supported", False)),
            fingerprint=str(data.get("fingerprint", "") or ""),
            fingerprint_settings=dict(data.get("fingerprint_settings", {}) or {}),
            fingerprint_source_type=str(data.get("fingerprint_source_type", "") or ""),
            fingerprint_schema_version=int(data.get("fingerprint_schema_version", 0) or 0),
            schema_version=int(data.get("schema_version", CHECKPOINT_SCHEMA_VERSION) or 0),
            updated_at=str(data.get("updated_at", "") or ""),
            message=str(data.get("message", "") or ""),
        )


@dataclass(slots=True)
class LogEntry:
    """A structured log line shown in the bottom drawer."""

    level: LogLevel = LogLevel.INFO
    stage: Stage = Stage.IDLE
    message: str = ""
    timestamp: str = ""
    job_id: str = ""

    def display(self) -> str:
        prefix = f"[{self.timestamp}] " if self.timestamp else ""
        return f"{prefix}{self.level.value.upper():<7} {self.stage.value:<11} {self.message}"

@dataclass(slots=True)
class Job:
    """A production job tracked by the job manager."""

    job_id: str
    title: str
    mode: AppMode = AppMode.COMMON_EDITING
    state: JobState = JobState.NEW
    task_state: TaskState = TaskState.QUEUED
    progress: JobProgress = field(default_factory=JobProgress)
    created_at: str = ""
    updated_at: str = ""
    source: Optional[VideoSource] = None
    output_path: str = ""
    error_message: str = ""
    is_demo: bool = True
    fingerprint: str = ""
    artifact_path: str = ""

    def clone(self) -> "Job":
        return replace(self, progress=replace(self.progress))


@dataclass(slots=True)
class DownloadItem:
    """A row in the download queue."""

    item_id: str
    title: str
    url: str
    total_bytes: int
    downloaded_bytes: int = 0
    speed_bps: float = 0.0
    state: TaskState = TaskState.QUEUED
    error_message: str = ""
    output_path: str = ""
    quality_label: str = "1080p"

    @property
    def percent(self) -> float:
        if self.total_bytes <= 0:
            return 0.0
        return min(100.0, self.downloaded_bytes * 100.0 / self.total_bytes)

    @property
    def eta_s(self) -> float:
        if self.speed_bps <= 0:
            return 0.0
        remaining = max(0, self.total_bytes - self.downloaded_bytes)
        return remaining / self.speed_bps


# --------------------------------------------------------------------------- #
# Session
# --------------------------------------------------------------------------- #
@dataclass(slots=True)
class ProjectSession:
    """Everything the UI needs to describe "the current project"."""

    source: Optional[VideoSource] = None
    metadata: Optional[SourceMetadata] = None
    transcript: list[TranscriptRow] = field(default_factory=list)
    narration_segments: list[NarrationSegment] = field(default_factory=list)
    exact_dubbing_rows: list[ExactDubbingRow] = field(default_factory=list)
    split_parts: list[SplitPart] = field(default_factory=list)
    overlays: list[Overlay] = field(default_factory=list)
    mode: AppMode = AppMode.COMMON_EDITING
    output_ratio: OutputRatio = OutputRatio.ORIGINAL
    frame_fill: FrameFill = FrameFill.BLUR
    output_folder: str = ""
    trim_start: float = 0.0
    trim_end: float = 0.0
    is_demo: bool = True

    # --- narrator helpers -------------------------------------------------- #
    @property
    def narrator_rows(self) -> list[NarrationSegment]:
        return self.narration_segments

    @property
    def narrator_dirty_count(self) -> int:
        return sum(1 for s in self.narration_segments if s.dirty)

    # --- exact dubbing helpers --------------------------------------------- #
    @property
    def exact_rows(self) -> list[ExactDubbingRow]:
        return self.exact_dubbing_rows

    @property
    def exact_dirty_count(self) -> int:
        return sum(1 for r in self.exact_dubbing_rows if r.edited)

    def rows_for_mode(self, mode: AppMode) -> Sequence:
        """Return the working set that belongs to ``mode``.

        Only narrator and exact-dubbing have row sets; the other modes work on
        the timeline / parts / overlays.
        """
        if mode is AppMode.NARRATOR:
            return self.narration_segments
        if mode is AppMode.EXACT_DUBBING:
            return self.exact_dubbing_rows
        return ()

    def total_duration(self) -> float:
        if self.metadata:
            return self.metadata.duration_s
        if self.transcript:
            return max(r.end for r in self.transcript)
        return 0.0


@dataclass(slots=True)
class TimelineMarker:
    """A small marker rendered on the workspace timeline."""

    position: float
    label: str = ""
    kind: str = "segment"
    duration: float = 0.0
