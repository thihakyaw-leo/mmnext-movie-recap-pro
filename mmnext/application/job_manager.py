"""Job state machine.

The transition table below is the single source of truth for "what may happen
next". UI buttons are derived from it, so a button can never offer an action
that the state machine would reject.
"""

from __future__ import annotations

from typing import Iterable, Optional

from ..domain.enums import JobState, TaskState
from ..domain.models import Job, JobProgress

__all__ = ["IllegalTransitionError", "JobManager", "ALLOWED_TRANSITIONS"]


class IllegalTransitionError(RuntimeError):
    """Raised when a job is asked to move to a state it cannot reach."""


#: Allowed job state transitions. A missing key means "terminal".
ALLOWED_TRANSITIONS: dict[JobState, frozenset[JobState]] = {
    JobState.NEW: frozenset(
        {
            JobState.SOURCE_ANALYZED,
            JobState.DOWNLOAD_QUEUED,
            JobState.DOWNLOADED,
            JobState.CANCELLED,
            JobState.FAILED,
        }
    ),
    JobState.SOURCE_ANALYZED: frozenset(
        {
            JobState.DOWNLOAD_QUEUED,
            JobState.DOWNLOADED,
            JobState.CANCELLED,
            JobState.FAILED,
        }
    ),
    JobState.DOWNLOAD_QUEUED: frozenset(
        {
            JobState.DOWNLOADING,
            JobState.DOWNLOAD_STOPPED,
            JobState.DOWNLOAD_FAILED,
            JobState.CANCELLED,
        }
    ),
    JobState.DOWNLOADING: frozenset(
        {
            JobState.DOWNLOAD_PAUSED,
            JobState.DOWNLOADED,
            JobState.DOWNLOAD_STOPPED,
            JobState.DOWNLOAD_FAILED,
            JobState.CANCELLED,
        }
    ),
    JobState.DOWNLOAD_PAUSED: frozenset(
        {
            JobState.DOWNLOADING,
            JobState.DOWNLOAD_STOPPED,
            JobState.DOWNLOAD_FAILED,
            JobState.CANCELLED,
        }
    ),
    JobState.DOWNLOAD_STOPPED: frozenset(
        {JobState.DOWNLOAD_QUEUED, JobState.CANCELLED}
    ),
    JobState.DOWNLOAD_FAILED: frozenset(
        {JobState.DOWNLOAD_QUEUED, JobState.CANCELLED}
    ),
    JobState.DOWNLOADED: frozenset(
        {JobState.PREPARING, JobState.CANCELLED, JobState.FAILED}
    ),
    JobState.PREPARING: frozenset(
        {
            JobState.AWAITING_TRANSLATION_OR_EDIT,
            JobState.VALIDATING,
            JobState.FAILED,
            JobState.CANCELLED,
        }
    ),
    JobState.AWAITING_TRANSLATION_OR_EDIT: frozenset(
        {
            JobState.VALIDATING,
            JobState.PREPARING,
            JobState.CANCELLED,
            JobState.FAILED,
        }
    ),
    JobState.VALIDATING: frozenset(
        {
            JobState.READY_TO_RENDER,
            JobState.AWAITING_TRANSLATION_OR_EDIT,
            JobState.FAILED,
            JobState.CANCELLED,
        }
    ),
    JobState.READY_TO_RENDER: frozenset(
        {JobState.RENDERING, JobState.FAILED, JobState.CANCELLED}
    ),
    JobState.RENDERING: frozenset(
        {
            JobState.COMPLETE,
            JobState.FAILED,
            JobState.CANCELLED,
            JobState.STOP_REQUESTED,
        }
    ),
    JobState.STOP_REQUESTED: frozenset(
        {JobState.CANCELLED, JobState.FAILED}
    ),
    JobState.COMPLETE: frozenset(),
    JobState.FAILED: frozenset(
        {
            JobState.DOWNLOAD_QUEUED,
            JobState.PREPARING,
            JobState.CANCELLED,
        }
    ),
    JobState.CANCELLED: frozenset(),
}


class JobManager:
    """Owns every :class:`~mmnext.domain.models.Job` and its transitions."""

    def __init__(self, jobs: Optional[Iterable[Job]] = None) -> None:
        self._jobs: dict[str, Job] = {}
        for job in jobs or ():
            self.add(job)

    # -- collection -------------------------------------------------------- #
    def add(self, job: Job) -> Job:
        if job.job_id in self._jobs:
            raise ValueError(f"Duplicate job id: {job.job_id}")
        self._jobs[job.job_id] = job
        return job

    def get(self, job_id: str) -> Job:
        try:
            return self._jobs[job_id]
        except KeyError as exc:
            raise KeyError(f"Unknown job id: {job_id}") from exc

    def all(self) -> list[Job]:
        return list(self._jobs.values())

    def remove(self, job_id: str) -> None:
        self._jobs.pop(job_id, None)

    def clear(self) -> None:
        self._jobs.clear()

    # -- state machine ----------------------------------------------------- #
    def can_transition(self, job_id: str, new_state: JobState) -> bool:
        job = self.get(job_id)
        return new_state in ALLOWED_TRANSITIONS.get(job.state, frozenset())

    def transition(self, job_id: str, new_state: JobState) -> Job:
        """Move a job to ``new_state`` or raise :class:`IllegalTransitionError`."""
        job = self.get(job_id)
        if new_state is job.state:
            return job
        allowed = ALLOWED_TRANSITIONS.get(job.state, frozenset())
        if new_state not in allowed:
            raise IllegalTransitionError(
                f"Job {job_id}: cannot move from {job.state.value} to "
                f"{new_state.value}"
            )
        job.state = new_state
        return job

    def set_task_state(self, job_id: str, task_state: TaskState) -> Job:
        job = self.get(job_id)
        job.task_state = task_state
        return job

    def update_progress(self, job_id: str, progress: JobProgress) -> Job:
        job = self.get(job_id)
        job.progress = progress
        return job

    def set_error(self, job_id: str, message: str) -> Job:
        job = self.get(job_id)
        job.error_message = message
        return job
