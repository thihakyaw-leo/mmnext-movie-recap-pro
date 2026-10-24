"""Tests for explicit opening of completed REAL transcript from Jobs."""
from __future__ import annotations

import json
from pathlib import Path
from tempfile import TemporaryDirectory

import pytest

from mmnext.domain.enums import AppMode, JobState
from mmnext.domain.models import Job, JobProgress, VideoSource, ProjectSession
from mmnext.infrastructure.repository.job_repository import JobRepository, compute_fingerprint
from mmnext.ui.app_context import AppContext
from mmnext.domain.paths import atomic_write_json


def make_job_repo(tmp_path):
    jobs_dir = tmp_path / "jobs"
    repo = JobRepository(str(jobs_dir))
    return repo, jobs_dir


def default_settings():
    return {"language": "en", "auto_detect": False, "model": "base", "schema": 1}


class _Collector:
    """Bound-method signal sink (a lambda would be a self-capturing closure)."""

    def __init__(self):
        self.calls = []

    def __call__(self, session, error):
        self.calls.append((session, error))


def write_transcript_artifact(repo, job_id, source_path, mode, rows, is_demo=False,
                              settings=None, artifact_mode=None, fingerprint_override=None,
                              drop_contract_keys=False):
    """Write a transcript artefact that satisfies the current contract.

    The artefact carries the exact fingerprint inputs that produced it, so a
    reopen can re-derive the same canonical value instead of guessing.
    """
    from mmnext.infrastructure.repository.job_repository import compute_fingerprint
    job_dir = repo._job_dir(job_id, source_path)
    artifact_dir = job_dir / mode.value / "transcripts"
    artifact_dir.mkdir(parents=True, exist_ok=True)
    stem = Path(source_path).stem
    artifact_path = artifact_dir / f"{stem}.transcript.json"
    source_type = "local_file"
    if settings is None:
        settings = default_settings()
    fp = fingerprint_override
    if fp is None:
        fp = compute_fingerprint(source_path, source_type, mode, settings=settings,
                                 schema_version=1)
    written_mode = artifact_mode if artifact_mode is not None else mode
    payload = {
        "schema_version": 1,
        "source_path": source_path,
        "fingerprint": fp,
        "model": "base",
        "language": "en",
        "duration_s": 120.0,
        "created_at": "2025-01-01T00:00:00Z",
        "is_demo": is_demo,
        "mode": getattr(written_mode, "value", written_mode),
        "fingerprint_settings": dict(settings),
        "fingerprint_source_type": source_type,
        "fingerprint_schema_version": 1,
        "rows": [{"row_id": r["row_id"], "start": r["start"], "duration": r["duration"], "text": r["text"]} for r in rows],
    }
    if drop_contract_keys:
        for key in ("mode", "fingerprint_settings", "fingerprint_source_type",
                    "fingerprint_schema_version"):
            payload.pop(key, None)
    atomic_write_json(artifact_path, payload)
    return artifact_path


def test_open_valid_completed_transcript(tmp_path):
    repo, jobs_dir = make_job_repo(tmp_path)
    source_path = str(tmp_path / "video.mp4")
    Path(source_path).touch()
    job_id = "job1"
    mode = AppMode.EXACT_DUBBING
    job = Job(job_id=job_id, title="Test", mode=mode, state=JobState.COMPLETE, is_demo=False,
              source=VideoSource.local(source_path), progress=JobProgress(percent=100.0))
    repo.save(job, source_path)
    rows = [{"row_id": "r1", "start": 0.0, "duration": 2.0, "text": "hello"},
            {"row_id": "r2", "start": 2.0, "duration": 3.0, "text": "world"}]
    write_transcript_artifact(repo, job_id, source_path, mode, rows, is_demo=False)

    ctx = AppContext(jobs_dir=str(jobs_dir))
    ctx._job_repository = repo
    # Need a job in manager
    try:
        ctx.jobs.add(job)
    except ValueError:
        pass
    ctx.open_transcript_from_job(job_id, source_path)
    session = ctx.project.session
    assert session is not None
    assert session.is_demo is False
    assert session.mode == mode
    assert len(session.transcript) == 2
    assert session.transcript[0].row_id == "r1"
    assert session.exact_dubbing_rows[0].original == "hello"
    # Burmese remains blank
    assert session.exact_dubbing_rows[0].burmese == ""


def test_open_missing_artifact(tmp_path):
    repo, jobs_dir = make_job_repo(tmp_path)
    source_path = str(tmp_path / "video.mp4")
    Path(source_path).touch()
    job_id = "job2"
    mode = AppMode.NARRATOR
    job = Job(job_id=job_id, title="Test", mode=mode, state=JobState.COMPLETE, is_demo=False,
              source=VideoSource.local(source_path), progress=JobProgress(percent=100.0))
    repo.save(job, source_path)
    ctx = AppContext(jobs_dir=str(jobs_dir))
    ctx._job_repository = repo
    try:
        ctx.jobs.add(job)
    except ValueError:
        pass
    with pytest.raises(FileNotFoundError):
        ctx.open_transcript_from_job(job_id, source_path)


def test_open_demo_artifact_rejected(tmp_path):
    repo, jobs_dir = make_job_repo(tmp_path)
    source_path = str(tmp_path / "video.mp4")
    Path(source_path).touch()
    job_id = "job3"
    mode = AppMode.NARRATOR
    job = Job(job_id=job_id, title="Test", mode=mode, state=JobState.COMPLETE, is_demo=False,
              source=VideoSource.local(source_path), progress=JobProgress(percent=100.0))
    repo.save(job, source_path)
    rows = [{"row_id": "r1", "start": 0.0, "duration": 1.0, "text": "demo"}]
    write_transcript_artifact(repo, job_id, source_path, mode, rows, is_demo=True)
    ctx = AppContext(jobs_dir=str(jobs_dir))
    ctx._job_repository = repo
    try:
        ctx.jobs.add(job)
    except ValueError:
        pass
    with pytest.raises(ValueError, match="demo"):
        ctx.open_transcript_from_job(job_id, source_path)


def test_open_incomplete_job_rejected(tmp_path):
    repo, jobs_dir = make_job_repo(tmp_path)
    source_path = str(tmp_path / "video.mp4")
    Path(source_path).touch()
    job_id = "job4"
    mode = AppMode.NARRATOR
    job = Job(job_id=job_id, title="Test", mode=mode, state=JobState.PREPARING, is_demo=False,
              source=VideoSource.local(source_path), progress=JobProgress(percent=10.0))
    repo.save(job, source_path)
    ctx = AppContext(jobs_dir=str(jobs_dir))
    ctx._job_repository = repo
    # job is loaded automatically by AppContext recovery scan; do not add again
    with pytest.raises(ValueError, match="not complete"):
        ctx.open_transcript_from_job(job_id, source_path)


def test_open_source_mismatch_rejected(tmp_path):
    repo, jobs_dir = make_job_repo(tmp_path)
    source_path = str(tmp_path / "video.mp4")
    other_path = str(tmp_path / "other.mp4")
    Path(source_path).touch()
    Path(other_path).touch()
    job_id = "job5"
    mode = AppMode.NARRATOR
    job = Job(job_id=job_id, title="Test", mode=mode, state=JobState.COMPLETE, is_demo=False,
              source=VideoSource.local(source_path), progress=JobProgress(percent=100.0))
    repo.save(job, source_path)
    rows = [{"row_id": "r1", "start": 0.0, "duration": 1.0, "text": "x"}]
    # Write artifact with different source_path
    write_transcript_artifact(repo, job_id, other_path, mode, rows, is_demo=False)
    # Move artifact to expected location but with mismatched source inside json
    # The artifact file name uses stem of other_path, so we need to create correct file name
    job_dir = repo._job_dir(job_id, source_path)
    artifact_dir = job_dir / mode.value / "transcripts"
    artifact_dir.mkdir(parents=True, exist_ok=True)
    stem = Path(source_path).stem
    artifact_path = artifact_dir / f"{stem}.transcript.json"
    # Write artifact with mismatched source
    atomic_write_json(artifact_path, {
        "schema_version": 1,
        "source_path": other_path,
        "fingerprint": "abc",
        "model": "base",
        "language": "en",
        "duration_s": 1.0,
        "created_at": "2025-01-01T00:00:00Z",
        "is_demo": False,
        "rows": rows,
    })
    ctx = AppContext(jobs_dir=str(jobs_dir))
    ctx._job_repository = repo
    try:
        ctx.jobs.add(job)
    except ValueError:
        pass
    with pytest.raises(ValueError, match="source path"):
        ctx.open_transcript_from_job(job_id, source_path)


def test_open_exact_dubbing_immutability(tmp_path):
    repo, jobs_dir = make_job_repo(tmp_path)
    source_path = str(tmp_path / "video.mp4")
    Path(source_path).touch()
    job_id = "job6"
    mode = AppMode.EXACT_DUBBING
    job = Job(job_id=job_id, title="Test", mode=mode, state=JobState.COMPLETE, is_demo=False,
              source=VideoSource.local(source_path), progress=JobProgress(percent=100.0))
    repo.save(job, source_path)
    rows = [{"row_id": "r1", "start": 0.0, "duration": 2.0, "text": "original"}]
    write_transcript_artifact(repo, job_id, source_path, mode, rows, is_demo=False)
    ctx = AppContext(jobs_dir=str(jobs_dir))
    ctx._job_repository = repo
    try:
        ctx.jobs.add(job)
    except ValueError:
        pass
    ctx.open_transcript_from_job(job_id, source_path)
    session = ctx.project.session
    row = session.exact_dubbing_rows[0]
    # Source fields immutable
    assert row.row_id == "r1"
    assert row.start == 0.0
    assert row.duration == 2.0
    assert row.original == "original"
    assert row.burmese == ""


def test_reopen_rejects_missing_source_media(tmp_path):
    """A vanished media file produces a clear message, not an OS error."""
    repo, jobs_dir = make_job_repo(tmp_path)
    source_path = str(tmp_path / "video.mp4")
    Path(source_path).touch()
    job_id = "job14"
    mode = AppMode.NARRATOR
    job = Job(job_id=job_id, title="Test", mode=mode, state=JobState.COMPLETE, is_demo=False,
              source=VideoSource.local(source_path), progress=JobProgress(percent=100.0))
    repo.save(job, source_path)
    rows = [{"row_id": "r1", "start": 0.0, "duration": 1.0, "text": "hello"}]
    write_transcript_artifact(repo, job_id, source_path, mode, rows)
    # The media disappears before the reopen.
    Path(source_path).unlink()
    ctx = AppContext(jobs_dir=str(jobs_dir))
    ctx._job_repository = repo
    try:
        ctx.jobs.add(job)
    except ValueError:
        pass
    with pytest.raises(ValueError, match="Source media is unavailable"):
        ctx.open_transcript_from_job(job_id, source_path)


# --------------------------------------------------------------------------- #
# Fingerprint re-derivation
# --------------------------------------------------------------------------- #
def test_reopen_recomputes_fingerprint_from_artifact_settings(tmp_path):
    """The artefact's own fingerprint inputs are used to re-derive the value.

    Recomputing *without* the settings hashes a different payload, so a real
    adapter-written artefact would never match and every REAL reopen would be
    rejected.
    """
    from mmnext.domain.fingerprint import canonical_fingerprint

    repo, jobs_dir = make_job_repo(tmp_path)
    source_path = str(tmp_path / "video.mp4")
    Path(source_path).touch()
    job_id = "job7"
    mode = AppMode.NARRATOR
    job = Job(job_id=job_id, title="Test", mode=mode, state=JobState.COMPLETE, is_demo=False,
              source=VideoSource.local(source_path), progress=JobProgress(percent=100.0))
    repo.save(job, source_path)
    settings = {"language": "en", "auto_detect": True, "model": "base", "schema": 1}
    rows = [{"row_id": "r1", "start": 0.0, "duration": 2.0, "text": "hello"}]
    write_transcript_artifact(repo, job_id, source_path, mode, rows, settings=settings)

    # The artefact's fingerprint is exactly the canonical value for its inputs.
    expected = canonical_fingerprint(source_path, "local_file", mode,
                                     settings=settings, schema_version=1)
    ctx = AppContext(jobs_dir=str(jobs_dir))
    ctx._job_repository = repo
    try:
        ctx.jobs.add(job)
    except ValueError:
        pass
    ctx.open_transcript_from_job(job_id, source_path)
    assert len(ctx.project.session.transcript) == 1


def test_reopen_rejects_fingerprint_mismatch(tmp_path):
    """A fingerprint that does not match the current source is refused."""
    repo, jobs_dir = make_job_repo(tmp_path)
    source_path = str(tmp_path / "video.mp4")
    Path(source_path).touch()
    job_id = "job8"
    mode = AppMode.NARRATOR
    job = Job(job_id=job_id, title="Test", mode=mode, state=JobState.COMPLETE, is_demo=False,
              source=VideoSource.local(source_path), progress=JobProgress(percent=100.0))
    repo.save(job, source_path)
    rows = [{"row_id": "r1", "start": 0.0, "duration": 1.0, "text": "hello"}]
    # A fingerprint computed for *different* settings must not be accepted.
    other_fp = compute_fingerprint(
        source_path, "local_file", mode,
        settings={"language": "de", "auto_detect": False, "model": "base", "schema": 1},
        schema_version=1,
    )
    write_transcript_artifact(repo, job_id, source_path, mode, rows,
                              settings=default_settings(), fingerprint_override=other_fp)
    ctx = AppContext(jobs_dir=str(jobs_dir))
    ctx._job_repository = repo
    try:
        ctx.jobs.add(job)
    except ValueError:
        pass
    with pytest.raises(ValueError, match="Fingerprint mismatch"):
        ctx.open_transcript_from_job(job_id, source_path)


def test_reopen_rejects_legacy_artifact(tmp_path):
    """An artefact without the new contract keys is refused explicitly."""
    repo, jobs_dir = make_job_repo(tmp_path)
    source_path = str(tmp_path / "video.mp4")
    Path(source_path).touch()
    job_id = "job9"
    mode = AppMode.NARRATOR
    job = Job(job_id=job_id, title="Test", mode=mode, state=JobState.COMPLETE, is_demo=False,
              source=VideoSource.local(source_path), progress=JobProgress(percent=100.0))
    repo.save(job, source_path)
    rows = [{"row_id": "r1", "start": 0.0, "duration": 1.0, "text": "hello"}]
    write_transcript_artifact(repo, job_id, source_path, mode, rows, drop_contract_keys=True)
    ctx = AppContext(jobs_dir=str(jobs_dir))
    ctx._job_repository = repo
    try:
        ctx.jobs.add(job)
    except ValueError:
        pass
    with pytest.raises(ValueError, match="re-transcribe required"):
        ctx.open_transcript_from_job(job_id, source_path)


def test_reopen_rejects_non_canonical_fingerprint(tmp_path):
    """A pre-contract (non ``fp2:``) fingerprint is unverifiable and refused."""
    repo, jobs_dir = make_job_repo(tmp_path)
    source_path = str(tmp_path / "video.mp4")
    Path(source_path).touch()
    job_id = "job10"
    mode = AppMode.NARRATOR
    job = Job(job_id=job_id, title="Test", mode=mode, state=JobState.COMPLETE, is_demo=False,
              source=VideoSource.local(source_path), progress=JobProgress(percent=100.0))
    repo.save(job, source_path)
    rows = [{"row_id": "r1", "start": 0.0, "duration": 1.0, "text": "hello"}]
    write_transcript_artifact(repo, job_id, source_path, mode, rows,
                              fingerprint_override="legacyhash")
    ctx = AppContext(jobs_dir=str(jobs_dir))
    ctx._job_repository = repo
    try:
        ctx.jobs.add(job)
    except ValueError:
        pass
    with pytest.raises(ValueError, match="re-transcribe required"):
        ctx.open_transcript_from_job(job_id, source_path)


# --------------------------------------------------------------------------- #
# Mode contract
# --------------------------------------------------------------------------- #
def test_reopen_rejects_artifact_mode_mismatch(tmp_path):
    """A narrator artefact must not be opened as an exact-dubbing job."""
    repo, jobs_dir = make_job_repo(tmp_path)
    source_path = str(tmp_path / "video.mp4")
    Path(source_path).touch()
    job_id = "job11"
    mode = AppMode.EXACT_DUBBING
    job = Job(job_id=job_id, title="Test", mode=mode, state=JobState.COMPLETE, is_demo=False,
              source=VideoSource.local(source_path), progress=JobProgress(percent=100.0))
    repo.save(job, source_path)
    rows = [{"row_id": "r1", "start": 0.0, "duration": 1.0, "text": "hello"}]
    write_transcript_artifact(repo, job_id, source_path, mode, rows,
                              artifact_mode=AppMode.NARRATOR)
    ctx = AppContext(jobs_dir=str(jobs_dir))
    ctx._job_repository = repo
    try:
        ctx.jobs.add(job)
    except ValueError:
        pass
    with pytest.raises(ValueError, match="does not match job mode"):
        ctx.open_transcript_from_job(job_id, source_path)


# --------------------------------------------------------------------------- #
# Path containment
# --------------------------------------------------------------------------- #
def test_reopen_rejects_artifact_outside_job_directory(tmp_path):
    """A job id that would place the artefact outside the repository is refused."""
    repo, jobs_dir = make_job_repo(tmp_path)
    source_path = str(tmp_path / "video.mp4")
    Path(source_path).touch()
    job_id = "../../escaped"
    mode = AppMode.NARRATOR
    job = Job(job_id=job_id, title="Test", mode=mode, state=JobState.COMPLETE, is_demo=False,
              source=VideoSource.local(source_path), progress=JobProgress(percent=100.0))
    repo.save(job, source_path)
    rows = [{"row_id": "r1", "start": 0.0, "duration": 1.0, "text": "hello"}]
    write_transcript_artifact(repo, job_id, source_path, mode, rows)
    ctx = AppContext(jobs_dir=str(jobs_dir))
    ctx._job_repository = repo
    try:
        ctx.jobs.add(job)
    except ValueError:
        pass
    with pytest.raises(ValueError, match="outside the job directory"):
        ctx.open_transcript_from_job(job_id, source_path)


# --------------------------------------------------------------------------- #
# Stale-result guard
# --------------------------------------------------------------------------- #
def test_reopen_rejects_stale_request(tmp_path):
    """A request that no longer matches the in-flight reopen is refused."""
    repo, jobs_dir = make_job_repo(tmp_path)
    source_path = str(tmp_path / "video.mp4")
    Path(source_path).touch()
    job_id = "job12"
    mode = AppMode.NARRATOR
    job = Job(job_id=job_id, title="Test", mode=mode, state=JobState.COMPLETE, is_demo=False,
              source=VideoSource.local(source_path), progress=JobProgress(percent=100.0))
    repo.save(job, source_path)
    rows = [{"row_id": "r1", "start": 0.0, "duration": 1.0, "text": "hello"}]
    write_transcript_artifact(repo, job_id, source_path, mode, rows)
    ctx = AppContext(jobs_dir=str(jobs_dir))
    ctx._job_repository = repo
    try:
        ctx.jobs.add(job)
    except ValueError:
        pass
    # A different request is in flight; this one is stale.
    ctx._reopen_token = ("other-job", source_path)
    with pytest.raises(ValueError, match="Stale reopen request"):
        ctx.open_transcript_from_job(job_id, source_path)


def test_reopen_result_is_not_bound_when_the_token_moved_on(tmp_path):
    """A prepared result is dropped when the request changed while loading."""
    repo, jobs_dir = make_job_repo(tmp_path)
    source_path = str(tmp_path / "video.mp4")
    Path(source_path).touch()
    job_id = "job13"
    mode = AppMode.NARRATOR
    job = Job(job_id=job_id, title="Test", mode=mode, state=JobState.COMPLETE, is_demo=False,
              source=VideoSource.local(source_path), progress=JobProgress(percent=100.0))
    repo.save(job, source_path)
    rows = [{"row_id": "r1", "start": 0.0, "duration": 1.0, "text": "hello"}]
    write_transcript_artifact(repo, job_id, source_path, mode, rows)
    ctx = AppContext(jobs_dir=str(jobs_dir))
    ctx._job_repository = repo
    try:
        ctx.jobs.add(job)
    except ValueError:
        pass

    received = _Collector()
    ctx.transcriptReopened.connect(received)

    session, prepared_rows, language = ctx.prepare_transcript_from_job(job_id, source_path)
    assert len(prepared_rows) == 1

    # The request moved on before the result could be bound.
    ctx._reopen_token = ("other-job", source_path)
    ctx._on_reopen_result((session, prepared_rows, language))
    assert received.calls and received.calls[-1][0] is None
    assert "Stale reopen result" in received.calls[-1][1]
    # Nothing was applied to the project.
    assert ctx.project.session is None or ctx.project.session.is_demo
