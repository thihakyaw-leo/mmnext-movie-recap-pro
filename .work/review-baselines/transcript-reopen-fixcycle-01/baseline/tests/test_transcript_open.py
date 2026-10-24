"""Tests for explicit opening of completed REAL transcript from Jobs."""
from __future__ import annotations

import json
from pathlib import Path
from tempfile import TemporaryDirectory

import pytest

from mmnext.domain.enums import AppMode, JobState
from mmnext.domain.models import Job, JobProgress, VideoSource, ProjectSession
from mmnext.infrastructure.repository.job_repository import JobRepository
from mmnext.ui.app_context import AppContext
from mmnext.domain.paths import atomic_write_json


def make_job_repo(tmp_path):
    jobs_dir = tmp_path / "jobs"
    repo = JobRepository(str(jobs_dir))
    return repo, jobs_dir


def write_transcript_artifact(repo, job_id, source_path, mode, rows, is_demo=False):
    from mmnext.infrastructure.repository.job_repository import compute_fingerprint
    job_dir = repo._job_dir(job_id, source_path)
    artifact_dir = job_dir / mode.value / "transcripts"
    artifact_dir.mkdir(parents=True, exist_ok=True)
    stem = Path(source_path).stem
    artifact_path = artifact_dir / f"{stem}.transcript.json"
    source_type = "local_file"
    fp = compute_fingerprint(source_path, source_type, mode, schema_version=1)
    atomic_write_json(artifact_path, {
        "schema_version": 1,
        "source_path": source_path,
        "fingerprint": fp,
        "model": "base",
        "language": "en",
        "duration_s": 120.0,
        "created_at": "2025-01-01T00:00:00Z",
        "is_demo": is_demo,
        "rows": [{"row_id": r["row_id"], "start": r["start"], "duration": r["duration"], "text": r["text"]} for r in rows],
    })
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
    ctx.jobs.add(job)
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
    ctx.jobs.add(job)
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
    ctx.jobs.add(job)
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
    ctx.jobs.add(job)
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
    ctx.jobs.add(job)
    ctx.open_transcript_from_job(job_id, source_path)
    session = ctx.project.session
    row = session.exact_dubbing_rows[0]
    # Source fields immutable
    assert row.row_id == "r1"
    assert row.start == 0.0
    assert row.duration == 2.0
    assert row.original == "original"
    assert row.burmese == ""
