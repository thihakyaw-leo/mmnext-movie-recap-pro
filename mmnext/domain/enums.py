"""Enumerations shared by the domain and application layers.

These are plain ``str`` enums so they serialise straight to JSON without a
custom encoder, and so a UI can compare them without importing Qt.
"""

from __future__ import annotations

from enum import Enum

__all__ = [
    "SourceType",
    "AppMode",
    "JobState",
    "TaskState",
    "Severity",
    "Stage",
    "LogLevel",
    "Gender",
    "CutReason",
    "OutputRatio",
    "FrameFill",
    "OverlayKind",
    "JobEventKind",
]


class StrEnum(str, Enum):
    """``str``-backed enum with a friendly ``str()``."""

    def __str__(self) -> str:  # pragma: no cover - trivial
        return str(self.value)


class SourceType(StrEnum):
    """Where the source media came from."""

    LOCAL_FILE = "local_file"
    YOUTUBE = "youtube"


class AppMode(StrEnum):
    """The four production modes.

    ``NARRATOR`` and ``EXACT_DUBBING`` intentionally have *separate* working
    sets and *separate* row types. They are never interchangeable.
    """

    COMMON_EDITING = "common_editing"
    SPLITTER = "splitter"
    NARRATOR = "narrator"
    EXACT_DUBBING = "exact_dubbing"

    @property
    def display_name(self) -> str:
        return {
            AppMode.COMMON_EDITING: "Common Video Editing",
            AppMode.SPLITTER: "Splitter Mode",
            AppMode.NARRATOR: "Narrator Mode",
            AppMode.EXACT_DUBBING: "Exact Dubbing Mode",
        }[self]


class JobState(StrEnum):
    """Lifecycle of a production job.

    Mirrors ``Agent.md`` section 8 and adds the terminal/negative states the UI
    needs in order to render truthful badges.
    """

    NEW = "new"
    SOURCE_ANALYZED = "source_analyzed"
    DOWNLOAD_QUEUED = "download_queued"
    DOWNLOADING = "downloading"
    DOWNLOAD_PAUSED = "download_paused"
    DOWNLOAD_STOPPED = "download_stopped"
    DOWNLOAD_FAILED = "download_failed"
    DOWNLOADED = "downloaded"
    PREPARING = "preparing"
    AWAITING_TRANSLATION_OR_EDIT = "awaiting_translation_or_edit"
    VALIDATING = "validating"
    READY_TO_RENDER = "ready_to_render"
    RENDERING = "rendering"
    COMPLETE = "complete"
    FAILED = "failed"
    STOP_REQUESTED = "stop_requested"
    CANCELLED = "cancelled"

    @property
    def is_terminal(self) -> bool:
        return self in _TERMINAL_JOB_STATES

    @property
    def is_active(self) -> bool:
        return self in _ACTIVE_JOB_STATES


_TERMINAL_JOB_STATES = frozenset(
    {
        JobState.COMPLETE,
        JobState.FAILED,
        JobState.CANCELLED,
        JobState.DOWNLOAD_STOPPED,
    }
)

_ACTIVE_JOB_STATES = frozenset(
    {
        JobState.PREPARING,
        JobState.VALIDATING,
        JobState.RENDERING,
        JobState.DOWNLOADING,
    }
)


class TaskState(StrEnum):
    """Generic worker task state (download, prepare, validate, render).

    The pause/stop lifecycle is deliberately split in two:

    * ``PAUSE_REQUESTED`` / ``STOP_REQUESTED`` mean *"the user asked, the
      worker has not reached a safe checkpoint yet"*.
    * ``PAUSED`` / ``STOPPED`` mean *"the worker is parked on a safe
      checkpoint and a checkpoint file has been written"*.

    A task is never reported as paused/stopped before its checkpoint exists.
    """

    QUEUED = "queued"
    RUNNING = "running"
    PAUSE_REQUESTED = "pause_requested"
    PAUSED = "paused"
    STOP_REQUESTED = "stop_requested"
    STOPPED = "stopped"
    FAILED = "failed"
    COMPLETE = "complete"
    CANCELLED = "cancelled"

    @property
    def is_active(self) -> bool:
        return self in {
            TaskState.RUNNING,
            TaskState.PAUSE_REQUESTED,
            TaskState.PAUSED,
            TaskState.STOP_REQUESTED,
        }

    @property
    def is_terminal(self) -> bool:
        return self in {
            TaskState.COMPLETE,
            TaskState.FAILED,
            TaskState.STOPPED,
            TaskState.CANCELLED,
        }

    @property
    def can_pause(self) -> bool:
        """Pause is only offered while the task is actually running."""
        return self is TaskState.RUNNING

    @property
    def can_resume(self) -> bool:
        """Resume is only offered from a parked state."""
        return self in {TaskState.PAUSED, TaskState.STOPPED}

    @property
    def can_stop(self) -> bool:
        """Stop is offered while the task is running or parked."""
        return self in {
            TaskState.RUNNING,
            TaskState.PAUSE_REQUESTED,
            TaskState.PAUSED,
        }


class Severity(StrEnum):
    """Validation issue severity."""

    INFO = "info"
    WARNING = "warning"
    ERROR = "error"

    @property
    def blocks_render(self) -> bool:
        return self is Severity.ERROR


class Stage(StrEnum):
    """Pipeline stage reported in progress events and the job log."""

    INTAKE = "intake"
    METADATA = "metadata"
    DOWNLOAD = "download"
    PREPARE = "prepare"
    TRANSCRIBE = "transcribe"
    TRANSLATE = "translate"
    SYNTHESIZE = "synthesize"
    VALIDATE = "validate"
    RENDER = "render"
    SPLIT = "split"
    EXPORT = "export"
    IDLE = "idle"


class LogLevel(StrEnum):
    DEBUG = "debug"
    INFO = "info"
    WARNING = "warning"
    ERROR = "error"
    SUCCESS = "success"


class Gender(StrEnum):
    """Speaker gender for exact dubbing.

    ``UNKNOWN`` is valid and maps to the documented fallback voice.
    """

    MALE = "male"
    FEMALE = "female"
    UNKNOWN = "unknown"

    @property
    def voice(self) -> str:
        """Gender -> Edge TTS Myanmar voice (legacy movie-recap mapping)."""
        return {
            Gender.MALE: "my-MM-ThihaNeural",
            Gender.FEMALE: "my-MM-NilarNeural",
            Gender.UNKNOWN: "my-MM-NilarNeural",
        }[self]


class CutReason(StrEnum):
    """Why a splitter part ended (legacy ``plan_parts`` vocabulary)."""

    EXACT = "exact"
    PAUSE = "pause"
    BREATH = "breath"
    QUIETEST = "quietest"
    END = "end"


class OutputRatio(StrEnum):
    ORIGINAL = "Original"
    WIDE = "16:9"
    VERTICAL = "9:16"
    SQUARE = "1:1"


class FrameFill(StrEnum):
    BLUR = "blur"
    BLACK = "black"
    CROP = "crop"


class OverlayKind(StrEnum):
    TITLE = "title"
    LOGO = "logo"
    EXTRA_TEXT = "extra_text"
    BLUR_BOX = "blur_box"


class JobEventKind(StrEnum):
    """Kind of structured event emitted by a worker to the GUI thread."""

    PROGRESS = "progress"
    LOG = "log"
    STATE = "state"
    VALIDATION = "validation"
    RESULT = "result"
    ERROR = "error"
