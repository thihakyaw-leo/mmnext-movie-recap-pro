"""Structured events emitted by workers and consumed by the UI.

Events are plain dataclasses so they can cross a thread boundary unchanged.
The application layer translates them into Qt signals; the domain never knows
about Qt.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Optional

from .enums import JobEventKind, LogLevel, Severity, Stage, TaskState
from .models import LogEntry, ValidationIssue

__all__ = [
    "ProgressEvent",
    "LogEvent",
    "StateEvent",
    "ValidationEvent",
    "ResultEvent",
    "ErrorEvent",
    "JobEvent",
]


@dataclass(slots=True)
class ProgressEvent:
    kind: JobEventKind = JobEventKind.PROGRESS
    job_id: str = ""
    task_id: str = ""
    percent: float = 0.0
    stage: Stage = Stage.IDLE
    message: str = ""
    bytes_done: int = 0
    bytes_total: int = 0
    speed_bps: float = 0.0
    eta_s: float = 0.0


@dataclass(slots=True)
class LogEvent:
    kind: JobEventKind = JobEventKind.LOG
    job_id: str = ""
    level: LogLevel = LogLevel.INFO
    stage: Stage = Stage.IDLE
    message: str = ""


@dataclass(slots=True)
class StateEvent:
    kind: JobEventKind = JobEventKind.STATE
    job_id: str = ""
    task_id: str = ""
    state: TaskState = TaskState.QUEUED
    message: str = ""


@dataclass(slots=True)
class ValidationEvent:
    kind: JobEventKind = JobEventKind.VALIDATION
    job_id: str = ""
    issues: list[ValidationIssue] = field(default_factory=list)
    checked_rows: int = 0


@dataclass(slots=True)
class ResultEvent:
    kind: JobEventKind = JobEventKind.RESULT
    job_id: str = ""
    task_id: str = ""
    output_path: str = ""
    payload: dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True)
class ErrorEvent:
    kind: JobEventKind = JobEventKind.ERROR
    job_id: str = ""
    task_id: str = ""
    message: str = ""
    detail: str = ""


JobEvent = (
    ProgressEvent
    | LogEvent
    | StateEvent
    | ValidationEvent
    | ResultEvent
    | ErrorEvent
)


def to_log_entry(event: LogEvent, timestamp: str = "") -> LogEntry:
    """Convert a :class:`LogEvent` into a :class:`LogEntry` for the drawer."""
    return LogEntry(
        level=event.level,
        stage=event.stage,
        message=event.message,
        timestamp=timestamp,
        job_id=event.job_id,
    )


def severity_from_name(name: str) -> Severity:
    """Tolerant severity parsing used by the event decoders."""
    try:
        return Severity(name.lower())
    except ValueError:
        return Severity.INFO


def optional_job_id(event: JobEvent) -> Optional[str]:
    return getattr(event, "job_id", "") or None
