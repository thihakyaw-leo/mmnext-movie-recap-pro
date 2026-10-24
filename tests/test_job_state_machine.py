"""Job state machine tests.

``JobManager.ALLOWED_TRANSITIONS`` is the source of truth. The tests below
assert both that the legal moves work and that the illegal ones are
refused, because the UI derives every button from this table.
"""

from __future__ import annotations

import pytest

from mmnext.application.job_manager import (
    ALLOWED_TRANSITIONS,
    IllegalTransitionError,
    JobManager,
)
from mmnext.domain.enums import JobState, TaskState
from mmnext.domain.models import Job, JobProgress
from mmnext.services.demo import demo_data


@pytest.fixture()
def manager() -> JobManager:
    return JobManager(demo_data.build_demo_jobs())


def _job_in(state: JobState, manager: JobManager) -> Job:
    """Create a job that already sits in ``state``."""
    job = Job(job_id=f"probe-{state.value}", title="probe")
    manager.add(job)
    job.state = state
    return job


def test_demo_jobs_are_loaded(manager: JobManager) -> None:
    jobs = manager.all()
    assert jobs
    assert all(isinstance(job, Job) for job in jobs)
    assert len({job.job_id for job in jobs}) == len(jobs)


def test_new_job_starts_in_new(manager: JobManager) -> None:
    job = Job(job_id="j1", title="Test job")
    manager.add(job)
    assert manager.get("j1").state is JobState.NEW


def test_legal_transition_is_applied(manager: JobManager) -> None:
    job = Job(job_id="j-legal", title="Test job")
    manager.add(job)
    assert manager.can_transition(job.job_id, JobState.SOURCE_ANALYZED)
    updated = manager.transition(job.job_id, JobState.SOURCE_ANALYZED)
    assert updated.state is JobState.SOURCE_ANALYZED


def test_illegal_transition_is_refused(manager: JobManager) -> None:
    job = Job(job_id="j-illegal", title="Test job")
    manager.add(job)
    manager.transition(job.job_id, JobState.SOURCE_ANALYZED)
    # SOURCE_ANALYZED -> COMPLETE is not a legal move.
    assert not manager.can_transition(job.job_id, JobState.COMPLETE)
    with pytest.raises(IllegalTransitionError):
        manager.transition(job.job_id, JobState.COMPLETE)


def test_transition_to_the_same_state_is_a_no_op(manager: JobManager) -> None:
    job = Job(job_id="j-same", title="Test job")
    manager.add(job)
    before = manager.get(job.job_id).state
    manager.transition(job.job_id, before)
    assert manager.get(job.job_id).state is before


def test_every_allowed_transition_is_reachable(manager: JobManager) -> None:
    """Each declared edge must actually be accepted by the manager."""
    for source, targets in ALLOWED_TRANSITIONS.items():
        job = _job_in(source, manager)
        for target in targets:
            assert manager.can_transition(job.job_id, target), (
                f"{source.value} -> {target.value} should be allowed"
            )


def test_terminal_states_allow_nothing(manager: JobManager) -> None:
    for state in (JobState.COMPLETE, JobState.CANCELLED):
        job = _job_in(state, manager)
        assert ALLOWED_TRANSITIONS[state] == frozenset()
        assert not manager.can_transition(job.job_id, JobState.RENDERING)


def test_render_can_be_stopped_but_not_resumed_silently(manager: JobManager) -> None:
    job = _job_in(JobState.RENDERING, manager)
    assert manager.can_transition(job.job_id, JobState.STOP_REQUESTED)
    manager.transition(job.job_id, JobState.STOP_REQUESTED)
    assert manager.can_transition(job.job_id, JobState.CANCELLED)
    assert not manager.can_transition(job.job_id, JobState.RENDERING)


def test_progress_update_is_visible(manager: JobManager) -> None:
    job = Job(job_id="j-progress", title="Test job")
    manager.add(job)
    manager.update_progress(job.job_id, JobProgress(percent=42.0, message="halfway"))
    stored = manager.get(job.job_id)
    assert stored.progress.percent == pytest.approx(42.0)
    assert stored.progress.message == "halfway"
    assert stored.progress.percent_int == 42


def test_error_is_recorded_on_the_job(manager: JobManager) -> None:
    job = Job(job_id="j-error", title="Test job")
    manager.add(job)
    manager.set_error(job.job_id, "boom")
    assert manager.get(job.job_id).error_message == "boom"


def test_task_state_is_tracked_separately(manager: JobManager) -> None:
    job = Job(job_id="j-task", title="Test job")
    manager.add(job)
    manager.set_task_state(job.job_id, TaskState.RUNNING)
    assert manager.get(job.job_id).task_state is TaskState.RUNNING
    assert manager.get(job.job_id).state is JobState.NEW


def test_remove_and_clear(manager: JobManager) -> None:
    job_id = manager.all()[0].job_id
    manager.remove(job_id)
    assert job_id not in {j.job_id for j in manager.all()}
    manager.clear()
    assert manager.all() == []


def test_duplicate_job_id_is_refused(manager: JobManager) -> None:
    job_id = manager.all()[0].job_id
    with pytest.raises(ValueError):
        manager.add(Job(job_id=job_id, title="dup"))


def test_progress_dataclass_defaults() -> None:
    progress = JobProgress()
    assert progress.percent == 0.0
    assert progress.percent_int == 0
    assert progress.speed_display == "-"
    assert progress.eta_display == "-"
