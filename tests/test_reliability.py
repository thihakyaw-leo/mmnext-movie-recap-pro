"""Diagnostics and recovery tests."""

from __future__ import annotations

from mmnext.application.diagnostics_service import DiagnosticsService
from mmnext.infrastructure.repository.job_repository import JobRepository


def test_diagnostics_service_reports(tmp_path):
    svc = DiagnosticsService(jobs_dir=tmp_path)
    report = svc.report()
    assert "python" in report
    assert "dependencies" in report
    assert report["jobs_dir"] == str(tmp_path)


def test_orphan_cleanup(tmp_path):
    repo = JobRepository(tmp_path / "jobs")
    repo.jobs_dir.mkdir(parents=True, exist_ok=True)
    partial = repo.jobs_dir / "orphan.partial"
    partial.write_bytes(b"x")
    removed = repo.cleanup_orphans()
    assert str(partial) in removed
    assert not partial.exists()
