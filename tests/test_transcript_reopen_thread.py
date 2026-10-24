"""End-to-end tests for the persisted transcript reopen path.

These cover the hardened reopen contract:

* the artefact is read and validated **off the GUI thread**;
* the result is bound only while the request is still the current one;
* a REAL adapter-written artefact reopens successfully (the fingerprint is
  re-derived from the artefact's own settings);
* the Jobs screen offers the explicit open action for completed REAL jobs
  and routes it through the threaded path.
"""

from __future__ import annotations

import json
import threading
from pathlib import Path

import pytest
from PySide6.QtCore import QEventLoop, QTimer

from mmnext.domain.enums import AppMode, JobState
from mmnext.domain.models import Job, JobProgress, TranscriptRow, VideoSource
from mmnext.domain.paths import atomic_write_json
from mmnext.infrastructure.repository.job_repository import JobRepository
from mmnext.ui.app_context import AppContext

pytestmark = pytest.mark.usefixtures("qapp")


# --------------------------------------------------------------------------- #
# Helpers
# --------------------------------------------------------------------------- #
class _Waiter:
    """Bound-method signal sink that also stops a nested event loop."""

    def __init__(self) -> None:
        self.session = None
        self.error = ""
        self.called = False
        self.loop = QEventLoop()

    def __call__(self, session, error: str) -> None:
        self.session = session
        self.error = error
        self.called = True
        self.loop.quit()

    def wait(self, timeout_ms: int = 5000) -> bool:
        QTimer.singleShot(timeout_ms, self.loop.quit)
        self.loop.exec()
        return self.called


class _Collector:
    """Bound-method signal sink (a lambda would be a self-capturing closure)."""

    def __init__(self) -> None:
        self.calls = []

    def __call__(self, session, error: str) -> None:
        self.calls.append((session, error))


def _repo(tmp_path):
    jobs_dir = tmp_path / "jobs"
    return JobRepository(str(jobs_dir)), jobs_dir


def _settings():
    return {"language": "en", "auto_detect": False, "model": "base", "schema": 1}


def _write_artifact(repo, job_id, source_path, mode, rows):
    from mmnext.infrastructure.repository.job_repository import compute_fingerprint

    job_dir = repo._job_dir(job_id, source_path)
    artifact_dir = job_dir / mode.value / "transcripts"
    artifact_dir.mkdir(parents=True, exist_ok=True)
    stem = Path(source_path).stem
    artifact_path = artifact_dir / f"{stem}.transcript.json"
    settings = _settings()
    atomic_write_json(artifact_path, {
        "schema_version": 1,
        "source_path": source_path,
        "fingerprint": compute_fingerprint(
            source_path, "local_file", mode, settings=settings, schema_version=1),
        "model": "base",
        "language": "en",
        "duration_s": 120.0,
        "created_at": "2025-01-01T00:00:00Z",
        "is_demo": False,
        "mode": mode.value,
        "fingerprint_settings": settings,
        "fingerprint_source_type": "local_file",
        "fingerprint_schema_version": 1,
        "rows": [{"row_id": r["row_id"], "start": r["start"],
                  "duration": r["duration"], "text": r["text"]} for r in rows],
    })
    return artifact_path


def _completed_job(repo, source_path, job_id="rt1", mode=AppMode.NARRATOR):
    job = Job(job_id=job_id, title="Test", mode=mode, state=JobState.COMPLETE,
              is_demo=False, source=VideoSource.local(source_path),
              progress=JobProgress(percent=100.0))
    repo.save(job, source_path)
    return job


def _context(repo, jobs_dir, job):
    ctx = AppContext(jobs_dir=str(jobs_dir))
    ctx._job_repository = repo
    try:
        ctx.jobs.add(job)
    except ValueError:
        pass
    return ctx


# --------------------------------------------------------------------------- #
# Off the GUI thread
# --------------------------------------------------------------------------- #
def test_reopen_reads_the_artifact_off_the_gui_thread(tmp_path):
    """The artefact read and every validation check run on a worker thread."""
    repo, jobs_dir = _repo(tmp_path)
    source_path = str(tmp_path / "video.mp4")
    Path(source_path).touch()
    job = _completed_job(repo, source_path)
    _write_artifact(repo, job.job_id, source_path, job.mode,
                    [{"row_id": "r1", "start": 0.0, "duration": 2.0, "text": "hello"}])
    ctx = _context(repo, jobs_dir, job)

    gui_thread = threading.get_ident()
    seen = {}
    original = ctx.prepare_transcript_from_job

    def recording(job_id, source_path_):
        seen["thread"] = threading.get_ident()
        return original(job_id, source_path_)

    ctx.prepare_transcript_from_job = recording

    waiter = _Waiter()
    ctx.transcriptReopened.connect(waiter)
    ctx.start_reopen_transcript(job.job_id, source_path)
    assert waiter.wait(), "the reopen never reported a result"

    assert seen.get("thread") not in (None, gui_thread), (
        "the artefact was read on the GUI thread"
    )
    assert waiter.error == ""
    assert waiter.session is not None
    assert len(ctx.project.session.transcript) == 1


def test_reopen_reports_a_failure_through_the_signal(tmp_path):
    """A refused reopen surfaces the reason; nothing is applied."""
    repo, jobs_dir = _repo(tmp_path)
    source_path = str(tmp_path / "video.mp4")
    Path(source_path).touch()
    job = _completed_job(repo, source_path)
    # No artefact was written at all.
    ctx = _context(repo, jobs_dir, job)

    waiter = _Waiter()
    ctx.transcriptReopened.connect(waiter)
    ctx.start_reopen_transcript(job.job_id, source_path)
    assert waiter.wait(), "the reopen never reported a result"

    assert waiter.session is None
    assert "missing" in waiter.error.lower()


def test_reopen_applies_the_result_on_the_gui_thread(tmp_path):
    """The prepared result is applied, and the session is a REAL one."""
    repo, jobs_dir = _repo(tmp_path)
    source_path = str(tmp_path / "video.mp4")
    Path(source_path).touch()
    job = _completed_job(repo, source_path, mode=AppMode.EXACT_DUBBING)
    _write_artifact(repo, job.job_id, source_path, job.mode,
                    [{"row_id": "r1", "start": 0.0, "duration": 2.0, "text": "original"}])
    ctx = _context(repo, jobs_dir, job)

    waiter = _Waiter()
    ctx.transcriptReopened.connect(waiter)
    ctx.start_reopen_transcript(job.job_id, source_path)
    assert waiter.wait(), "the reopen never reported a result"

    session = ctx.project.session
    assert session is not None
    assert session.is_demo is False
    assert session.mode is AppMode.EXACT_DUBBING
    # The Exact Dubbing source row is bound unchanged and the Burmese column
    # stays blank: the reopen never invents a translation.
    assert session.exact_dubbing_rows[0].original == "original"
    assert session.exact_dubbing_rows[0].burmese == ""


# --------------------------------------------------------------------------- #
# A REAL adapter-written artefact
# --------------------------------------------------------------------------- #
def test_real_adapter_artifact_reopens_end_to_end(tmp_path):
    """An artefact written by the real adapter's writer reopens successfully.

    The adapter hashes the transcription settings into the fingerprint; the
    reopen has to re-derive the value from those settings, otherwise every
    REAL reopen is rejected.
    """
    from mmnext.infrastructure.transcript_adapter import WhisperTranscriptAdapter

    repo, jobs_dir = _repo(tmp_path)
    source_path = str(tmp_path / "video.mp4")
    Path(source_path).touch()
    mode = AppMode.NARRATOR
    # The real adapter derives its job id from the source stem, so the
    # persisted job and the artefact live in the same job directory.
    job = _completed_job(repo, source_path, job_id=Path(source_path).stem, mode=mode)

    adapter = WhisperTranscriptAdapter(str(jobs_dir), source_path, mode=mode, is_demo=False)
    rows = [TranscriptRow("s0", 0.0, 2.0, "hello from whisper")]
    adapter._write_transcript_artifact(source_path, rows, "en", 12.0)

    # The adapter writes its own contract keys; the reopen must accept them.
    artifact = Path(adapter.artifact_path)
    assert artifact.exists()
    import json

    payload = json.loads(artifact.read_text(encoding="utf-8"))
    assert payload["fingerprint"].startswith("fp2:")
    assert payload["mode"] == mode.value
    assert payload["fingerprint_settings"]

    ctx = _context(repo, jobs_dir, job)
    waiter = _Waiter()
    ctx.transcriptReopened.connect(waiter)
    ctx.start_reopen_transcript(job.job_id, source_path)
    assert waiter.wait(), "the reopen never reported a result"

    assert waiter.error == ""
    assert waiter.session is not None
    assert len(ctx.project.session.transcript) == 1
    assert ctx.project.session.transcript[0].text == "hello from whisper"


# --------------------------------------------------------------------------- #
# Jobs screen wiring
# --------------------------------------------------------------------------- #
def test_jobs_screen_offers_open_only_for_completed_real_jobs(qtbot, tmp_path):
    """The explicit open action is offered for a completed REAL job only."""
    from mmnext.ui.screens.jobs_screen import JobsScreen

    repo, jobs_dir = _repo(tmp_path)
    source_path = str(tmp_path / "video.mp4")
    Path(source_path).touch()
    real_job = _completed_job(repo, source_path, job_id="rt_jobs")
    demo_job = Job(job_id="rt_demo", title="Demo", mode=AppMode.NARRATOR,
                   state=JobState.COMPLETE, is_demo=True,
                   source=VideoSource.local(source_path), progress=JobProgress(percent=100.0))
    repo.save(demo_job, source_path)

    ctx = _context(repo, jobs_dir, real_job)
    try:
        ctx.jobs.add(demo_job)
    except ValueError:
        pass

    screen = JobsScreen()
    qtbot.addWidget(screen)
    screen.bind(ctx)
    screen.on_activate()

    index = screen._job_ids.index(real_job.job_id)
    screen.table.selectRow(index)
    assert screen.open_transcript_button.isEnabled() is True

    demo_index = screen._job_ids.index(demo_job.job_id)
    screen.table.selectRow(demo_index)
    assert screen.open_transcript_button.isEnabled() is False


def test_jobs_screen_open_does_not_read_the_artifact_on_the_gui_thread(qtbot, tmp_path):
    """The Jobs screen routes the open through the threaded path."""
    from mmnext.ui.screens.jobs_screen import JobsScreen

    repo, jobs_dir = _repo(tmp_path)
    source_path = str(tmp_path / "video.mp4")
    Path(source_path).touch()
    job = _completed_job(repo, source_path, job_id="rt_jobs2")
    _write_artifact(repo, job.job_id, source_path, job.mode,
                    [{"row_id": "r1", "start": 0.0, "duration": 1.0, "text": "hello"}])
    ctx = _context(repo, jobs_dir, job)

    calls = []

    def _record(job_id, source_path_):
        calls.append((job_id, source_path_))

    ctx.start_reopen_transcript = _record

    screen = JobsScreen()
    qtbot.addWidget(screen)
    screen.bind(ctx)
    screen.on_activate()
    screen.table.selectRow(screen._job_ids.index(job.job_id))
    screen.open_transcript_button.click()

    assert calls == [(job.job_id, source_path)]


# --------------------------------------------------------------------------- #
# Review fixes
# --------------------------------------------------------------------------- #
def test_reopen_refuses_when_edits_appeared_during_the_load(tmp_path):
    """Edits made while the artefact was loading are never discarded.

    ``project.load`` replaces the whole session, so an edit made after the
    unsaved check would be lost silently.  The check is repeated on the GUI
    thread, where the apply happens.
    """
    from mmnext.domain.models import ExactDubbingRow

    repo, jobs_dir = _repo(tmp_path)
    source_path = str(tmp_path / "video.mp4")
    Path(source_path).touch()
    job = _completed_job(repo, source_path, job_id="rt_dirty")
    _write_artifact(repo, job.job_id, source_path, job.mode,
                    [{"row_id": "r1", "start": 0.0, "duration": 1.0, "text": "hello"}])
    ctx = _context(repo, jobs_dir, job)

    session, rows, language = ctx.prepare_transcript_from_job(job.job_id, source_path)

    # The user edits the working set while the load is still in flight.
    session.exact_dubbing_rows = [
        ExactDubbingRow("r1", 0.0, 1.0, "hello", burmese="မြန်မာ", edited=True)
    ]
    ctx.project.load(session)
    assert ctx.dirty.total_dirty() > 0

    with pytest.raises(ValueError, match="Unsaved edits appeared"):
        ctx._apply_prepared_transcript(session, rows, language, job.job_id)


def test_reopen_syncs_the_workspace_mode(tmp_path):
    """The reopened session's mode reaches the workspace.

    ``project.load`` does not notify a mode change, so without an explicit
    sync the workspace would keep showing the previous mode and the reopened
    rows would be hidden behind the wrong panel.
    """
    repo, jobs_dir = _repo(tmp_path)
    source_path = str(tmp_path / "video.mp4")
    Path(source_path).touch()
    job = _completed_job(repo, source_path, job_id="rt_mode", mode=AppMode.EXACT_DUBBING)
    _write_artifact(repo, job.job_id, source_path, job.mode,
                    [{"row_id": "r1", "start": 0.0, "duration": 1.0, "text": "original"}])
    ctx = _context(repo, jobs_dir, job)

    modes = []
    ctx.modeChanged.connect(modes.append)

    waiter = _Waiter()
    ctx.transcriptReopened.connect(waiter)
    ctx.start_reopen_transcript(job.job_id, source_path)
    assert waiter.wait(), "the reopen never reported a result"
    assert waiter.error == ""

    assert ctx.mode is AppMode.EXACT_DUBBING
    assert modes == [AppMode.EXACT_DUBBING]
    assert ctx.project.session.mode is AppMode.EXACT_DUBBING


def test_reopen_rejects_a_non_object_artifact(tmp_path):
    """A JSON document that is not an object is a corrupt artefact."""
    repo, jobs_dir = _repo(tmp_path)
    source_path = str(tmp_path / "video.mp4")
    Path(source_path).touch()
    job = _completed_job(repo, source_path, job_id="rt_notdict")
    artifact = _write_artifact(repo, job.job_id, source_path, job.mode,
                               [{"row_id": "r1", "start": 0.0, "duration": 1.0, "text": "x"}])
    Path(artifact).write_text("[1, 2, 3]", encoding="utf-8")
    ctx = _context(repo, jobs_dir, job)
    with pytest.raises(ValueError, match="corrupt or unreadable"):
        ctx.open_transcript_from_job(job.job_id, source_path)


def test_reopen_rejects_a_non_numeric_schema_version(tmp_path):
    """A malformed schema version is refused, not raised as a TypeError."""
    repo, jobs_dir = _repo(tmp_path)
    source_path = str(tmp_path / "video.mp4")
    Path(source_path).touch()
    job = _completed_job(repo, source_path, job_id="rt_schema")
    artifact = _write_artifact(repo, job.job_id, source_path, job.mode,
                               [{"row_id": "r1", "start": 0.0, "duration": 1.0, "text": "x"}])
    payload = json.loads(Path(artifact).read_text(encoding="utf-8"))
    payload["schema_version"] = "one"
    Path(artifact).write_text(json.dumps(payload), encoding="utf-8")
    ctx = _context(repo, jobs_dir, job)
    with pytest.raises(ValueError, match="Unsupported transcript schema version"):
        ctx.open_transcript_from_job(job.job_id, source_path)


def test_reopen_rejects_an_artifact_whose_source_vanished(tmp_path):
    """A recorded source path that no longer exists is refused cleanly."""
    repo, jobs_dir = _repo(tmp_path)
    source_path = str(tmp_path / "video.mp4")
    Path(source_path).touch()
    job = _completed_job(repo, source_path, job_id="rt_vanished")
    artifact = _write_artifact(repo, job.job_id, source_path, job.mode,
                               [{"row_id": "r1", "start": 0.0, "duration": 1.0, "text": "x"}])
    payload = json.loads(Path(artifact).read_text(encoding="utf-8"))
    payload["source_path"] = str(tmp_path / "gone.mp4")
    Path(artifact).write_text(json.dumps(payload), encoding="utf-8")
    ctx = _context(repo, jobs_dir, job)
    with pytest.raises(ValueError, match="source path"):
        ctx.open_transcript_from_job(job.job_id, source_path)


def test_reopen_result_is_dropped_for_a_superseded_request(tmp_path):
    """A result from a request that was superseded is never bound."""
    repo, jobs_dir = _repo(tmp_path)
    source_path = str(tmp_path / "video.mp4")
    Path(source_path).touch()
    job = _completed_job(repo, source_path, job_id="rt_superseded")
    _write_artifact(repo, job.job_id, source_path, job.mode,
                    [{"row_id": "r1", "start": 0.0, "duration": 1.0, "text": "x"}])
    ctx = _context(repo, jobs_dir, job)

    session, rows, language = ctx.prepare_transcript_from_job(job.job_id, source_path)
    received = _Collector()
    ctx.transcriptReopened.connect(received)

    # A newer request superseded this one.
    ctx._reopen_request_id += 1
    ctx._on_reopen_result((session, rows, language))

    assert received.calls and received.calls[-1][0] is None
    assert "Stale reopen result" in received.calls[-1][1]


def test_main_window_lands_in_the_workspace_after_a_reopen(qtbot, tmp_path):
    """The Jobs -> Workspace flow completes: the user lands in the workspace."""
    from mmnext.ui.main_window import MainWindow
    from mmnext.ui.navigation.nav_rail import NavTarget

    repo, jobs_dir = _repo(tmp_path)
    source_path = str(tmp_path / "video.mp4")
    Path(source_path).touch()
    job = _completed_job(repo, source_path, job_id="rt_window")
    _write_artifact(repo, job.job_id, source_path, job.mode,
                    [{"row_id": "r1", "start": 0.0, "duration": 1.0, "text": "x"}])

    win = MainWindow()

    def _clear_dirty(widget) -> None:
        widget.context.project.mark_narration_clean()
        widget.context.project.mark_exact_rows_clean()

    qtbot.addWidget(win, before_close_func=_clear_dirty)
    win.context._job_repository = repo
    try:
        win.context.jobs.add(job)
    except ValueError:
        pass

    win.navigate_to(NavTarget.JOBS)
    waiter = _Waiter()
    win.context.transcriptReopened.connect(waiter)
    win.context.start_reopen_transcript(job.job_id, source_path)
    assert waiter.wait(), "the reopen never reported a result"
    assert waiter.error == ""

    assert win.nav.active_key == NavTarget.WORKSPACE
    assert win.stack.currentWidget() is win._screens[NavTarget.WORKSPACE]
    win._worker.shutdown(wait_ms=1000)
