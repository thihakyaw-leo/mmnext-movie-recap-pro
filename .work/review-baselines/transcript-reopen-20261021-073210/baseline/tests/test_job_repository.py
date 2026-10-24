"""Tests for JobRepository, fingerprints, resume eligibility and recovery."""

import json
import tempfile
from pathlib import Path

import pytest

from mmnext.domain.enums import AppMode, JobState, TaskState
from mmnext.domain.models import Job, JobProgress, VideoSource, SourceType
from mmnext.infrastructure.repository.job_repository import (
    JobRepository,
    JOB_SCHEMA_VERSION,
    compute_fingerprint,
)
from mmnext.domain.models import JobCheckpoint


@pytest.fixture
def repo(tmp_path):
    return JobRepository(tmp_path)


@pytest.fixture
def sample_job():
    src = VideoSource.local("C:/videos/sample.mp4")
    job = Job(
        job_id="job_001",
        title="Test job",
        mode=AppMode.NARRATOR,
        state=JobState.NEW,
        task_state=TaskState.QUEUED,
        progress=JobProgress(percent=0.0),
        source=src,
        is_demo=False,
    )
    return job


def test_repository_create_and_load(repo, sample_job):
    source_path = "C:/videos/sample.mp4"
    repo.create(sample_job, source_path)
    loaded = repo.load("job_001", source_path)
    assert loaded is not None
    assert loaded.job_id == "job_001"
    assert loaded.title == "Test job"


def test_atomic_job_save(repo, sample_job):
    source_path = "C:/videos/sample.mp4"
    repo.save(sample_job, source_path)
    meta_path = repo._metadata_path("job_001", source_path)
    assert meta_path.exists()
    # No .partial left behind
    assert not meta_path.with_name(meta_path.name + ".partial").exists()


def test_schema_version_check(repo, sample_job):
    source_path = "C:/videos/sample.mp4"
    repo.create(sample_job, source_path)
    meta_path = repo._metadata_path("job_001", source_path)
    data = json.loads(meta_path.read_text(encoding="utf-8"))
    assert data["schema_version"] == JOB_SCHEMA_VERSION


def test_corrupt_job_recovery(repo, sample_job):
    source_path = "C:/videos/sample.mp4"
    repo.create(sample_job, source_path)
    meta_path = repo._metadata_path("job_001", source_path)
    meta_path.write_text("{bad json", encoding="utf-8")
    loaded = repo.load("job_001", source_path)
    assert loaded is None


def test_job_scoped_paths(repo, sample_job):
    source_path = "C:/videos/sample.mp4"
    repo.save(sample_job, source_path)
    job_dir = repo._job_dir("job_001", source_path)
    assert job_dir.exists()
    # Different source should be different dir
    other_path = "C:/videos/other.mp4"
    other_dir = repo._job_dir("job_001", other_path)
    assert other_dir != job_dir


def test_different_sources_do_not_collide(repo, sample_job):
    src1 = "C:/videos/a.mp4"
    src2 = "C:/videos/b.mp4"
    job1 = Job(job_id="j1", title="A", mode=AppMode.SPLITTER, source=VideoSource.local(src1))
    job2 = Job(job_id="j1", title="B", mode=AppMode.SPLITTER, source=VideoSource.local(src2))
    repo.create(job1, src1)
    repo.create(job2, src2)
    assert repo.load("j1", src1).title == "A"
    assert repo.load("j1", src2).title == "B"


def test_different_modes_do_not_collide(repo):
    source_path = "C:/videos/sample.mp4"
    job = Job(job_id="j2", title="M", mode=AppMode.EXACT_DUBBING)
    repo.create(job, source_path)
    ckpt1 = JobCheckpoint(task_id="t1", mode="exact_dubbing", state=TaskState.PAUSED, resume_supported=True, fingerprint="fp1", schema_version=2)
    ckpt2 = JobCheckpoint(task_id="t1", mode="narrator", state=TaskState.PAUSED, resume_supported=True, fingerprint="fp2", schema_version=2)
    repo.save_checkpoint("j2", source_path, AppMode.EXACT_DUBBING, ckpt1)
    repo.save_checkpoint("j2", source_path, AppMode.NARRATOR, ckpt2)
    p1 = repo._checkpoint_path("j2", source_path, AppMode.EXACT_DUBBING)
    p2 = repo._checkpoint_path("j2", source_path, AppMode.NARRATOR)
    assert p1 != p2
    assert p1.exists() and p2.exists()


def test_fingerprint_changes_when_settings_change():
    fp1 = compute_fingerprint("/v/a.mp4", "local", AppMode.NARRATOR, settings={"rate": 1.0})
    fp2 = compute_fingerprint("/v/a.mp4", "local", AppMode.NARRATOR, settings={"rate": 1.1})
    assert fp1 != fp2


def test_fingerprint_changes_when_source_changes():
    fp1 = compute_fingerprint("/v/a.mp4", "local", AppMode.NARRATOR)
    fp2 = compute_fingerprint("/v/b.mp4", "local", AppMode.NARRATOR)
    assert fp1 != fp2


def test_resume_rejected_on_fingerprint_mismatch(repo):
    source_path = "C:/videos/sample.mp4"
    job = Job(job_id="j3", title="F", mode=AppMode.NARRATOR, state=JobState.PREPARING, source=VideoSource.local(source_path))
    repo.create(job, source_path)
    ckpt = JobCheckpoint(
        task_id="j3",
        mode=AppMode.NARRATOR.value,
        state=TaskState.PAUSED,
        resume_supported=True,
        fingerprint="badfp",
        schema_version=2,
    )
    repo.save_checkpoint("j3", source_path, AppMode.NARRATOR, ckpt)
    result = repo.can_resume_job("j3", source_path, AppMode.NARRATOR)
    assert not result
    assert any("Fingerprint mismatch" in r for r in result.reasons)


def test_resume_rejected_on_mode_mismatch(repo):
    source_path = "C:/videos/sample.mp4"
    job = Job(job_id="j4", title="M", mode=AppMode.NARRATOR, state=JobState.PREPARING, source=VideoSource.local(source_path))
    repo.create(job, source_path)
    ckpt = JobCheckpoint(
        task_id="j4",
        mode=AppMode.NARRATOR.value,
        state=TaskState.PAUSED,
        resume_supported=True,
        fingerprint=compute_fingerprint(source_path, "local", AppMode.NARRATOR),
        schema_version=2,
    )
    repo.save_checkpoint("j4", source_path, AppMode.SPLITTER, ckpt)
    result = repo.can_resume_job("j4", source_path, AppMode.NARRATOR)
    assert not result


def test_resume_rejected_after_complete(repo):
    source_path = "C:/videos/sample.mp4"
    job = Job(job_id="j5", title="C", mode=AppMode.NARRATOR, state=JobState.COMPLETE, source=VideoSource.local(source_path))
    repo.create(job, source_path)
    result = repo.can_resume_job("j5", source_path, AppMode.NARRATOR)
    assert not result
    assert any("already complete" in r.lower() for r in result.reasons)


def test_recoverable_jobs_are_discovered(repo, sample_job):
    source_path = "C:/videos/sample.mp4"
    repo.create(sample_job, source_path)
    scan = repo.scan()
    recoverable = scan["recoverable"]
    assert len(recoverable) >= 1
    job, src_dir = recoverable[0]
    assert job.job_id == "job_001"


def test_corrupt_jobs_are_reported(repo, sample_job):
    source_path = "C:/videos/sample.mp4"
    repo.create(sample_job, source_path)
    meta_path = repo._metadata_path("job_001", source_path)
    meta_path.write_text("not json", encoding="utf-8")
    scan = repo.scan()
    corrupt = scan["corrupt"]
    assert any(str(meta_path) in str(p) for p in corrupt)


def test_worker_uses_job_repository_checkpoint_path(repo):
    source_path = "C:/videos/sample.mp4"
    job = Job(job_id="w1", title="W", mode=AppMode.DOWNLOAD if hasattr(AppMode, "DOWNLOAD") else AppMode.COMMON_EDITING, state=JobState.NEW, source=VideoSource.local(source_path))
    repo.create(job, source_path)
    ckpt = JobCheckpoint(task_id="t1", mode="download", state=TaskState.PAUSED, resume_supported=True, fingerprint="fp", schema_version=2)
    repo.save_checkpoint("w1", source_path, AppMode.COMMON_EDITING, ckpt)
    path = repo._checkpoint_path("w1", source_path, AppMode.COMMON_EDITING)
    assert path.exists()


def test_demo_jobs_are_marked_as_demo(repo):
    source_path = "C:/videos/demo.mp4"
    job = Job(job_id="demo1", title="Demo", mode=AppMode.NARRATOR, state=JobState.NEW, is_demo=True, source=VideoSource.local(source_path))
    repo.create(job, source_path)
    loaded = repo.load("demo1", source_path)
    assert loaded is not None
    assert loaded.is_demo is True


def test_list_incomplete(repo, sample_job):
    source_path = "C:/videos/sample.mp4"
    repo.create(sample_job, source_path)
    incomplete = repo.list_incomplete(source_path)
    assert any(j.job_id == "job_001" for j in incomplete)


def test_mark_complete(repo, sample_job):
    source_path = "C:/videos/sample.mp4"
    repo.create(sample_job, source_path)
    repo.mark_complete("job_001", source_path)
    loaded = repo.load("job_001", source_path)
    assert loaded.state == JobState.COMPLETE
