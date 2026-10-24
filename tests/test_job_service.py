"""Application job facade tests."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from mmnext.application.job_service import JobService
from mmnext.domain.enums import AppMode, JobState
from mmnext.domain.models import Job, VideoSource
from mmnext.infrastructure.repository.job_repository import JobRepository


def test_service_exposes_public_repository_path_helpers(tmp_path):
    service = JobService(str(tmp_path / "jobs"))
    source = tmp_path / "video.mp4"
    source.write_bytes(b"source")

    repository = service.repository
    assert service.source_dir(str(source)) == repository.source_dir(str(source))
    assert service.job_dir("job_1", str(source)) == repository.job_dir("job_1", str(source))
    assert service.checkpoint_path(
        "job_1", str(source), AppMode.NARRATOR
    ) == repository.checkpoint_path("job_1", str(source), AppMode.NARRATOR)


def test_service_repository_is_injectable(tmp_path):
    repository = JobRepository(str(tmp_path / "jobs"))
    service = JobService(str(tmp_path / "other"))
    service.repository = repository
    assert service.repository is repository


def test_service_scan_uses_repository(tmp_path):
    jobs_dir = tmp_path / "jobs"
    repository = JobRepository(str(jobs_dir))
    source = tmp_path / "video.mp4"
    source.write_bytes(b"source")
    job = Job(
        job_id="job_1",
        title="video",
        mode=AppMode.NARRATOR,
        state=JobState.COMPLETE,
        is_demo=False,
        source=VideoSource.local(str(source)),
        fingerprint="fp2:abc",
        artifact_path=str(jobs_dir / "artifact.json"),
    )
    repository.save(job, str(source))

    service = JobService(str(jobs_dir))
    scan = service.scan()
    assert len(scan["completed_real"]) == 1
    assert scan["completed_real"][0][0].job_id == "job_1"


def test_persist_completed_transcript_uses_provider_fingerprint(tmp_path):
    jobs_dir = tmp_path / "jobs"
    service = JobService(str(jobs_dir))
    source = tmp_path / "video.mp4"
    source.write_bytes(b"source")

    class Provider:
        source_path = str(source)
        mode = AppMode.NARRATOR
        job_id = "job_from_provider"
        artifact_path = jobs_dir / "mode" / "transcript.json"
        fingerprint = "fp2:abc123"

    job = service.persist_completed_transcript(Provider())
    assert job.job_id == "job_from_provider"
    assert job.fingerprint == "fp2:abc123"
    assert job.state == JobState.COMPLETE
    assert job.is_demo is False
    metadata_path = service.job_dir("job_from_provider", str(source)) / "metadata.json"
    assert metadata_path.exists()
    assert json.loads(metadata_path.read_text(encoding="utf-8"))["fingerprint"] == "fp2:abc123"


def test_prepare_rejects_non_complete_job(tmp_path):
    service = JobService(str(tmp_path / "jobs"))
    source = tmp_path / "video.mp4"
    source.write_bytes(b"source")
    job = Job(
        job_id="job_incomplete",
        title="video",
        mode=AppMode.NARRATOR,
        state=JobState.PREPARING,
        is_demo=False,
        source=VideoSource.local(str(source)),
    )
    service.repository.save(job, str(source))
    with pytest.raises(ValueError, match="not complete"):
        service.prepare_transcript_from_job("job_incomplete", str(source))
