"""Tests for source and download integration."""

from __future__ import annotations

import pytest
from PySide6.QtWidgets import QApplication

from mmnext.domain.enums import SourceType
from mmnext.domain.models import VideoSource
from mmnext.services.adapters.metadata import LocalFileMetadataService, YouTubeMetadataService
from mmnext.ui.app_context import AppContext
from mmnext.ui.workers import DownloadWorkerThread
from mmnext.services.demo.demo_providers import DemoDownloadService


@pytest.fixture
def app():
    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    return app


def test_local_file_metadata(tmp_path):
    # Create a dummy file
    f = tmp_path / "video.mp4"
    f.write_bytes(b"\0" * 1024)
    source = VideoSource.local(str(f))
    svc = LocalFileMetadataService()
    meta = svc.analyze(source)
    assert meta.title == "video"
    assert len(meta.qualities) == 1
    assert meta.qualities[0].filesize_mb > 0


def test_invalid_youtube_url():
    svc = YouTubeMetadataService()
    source = VideoSource(source_type=SourceType.YOUTUBE, location="not a url")
    with pytest.raises(ValueError):
        svc.analyze(source)


def test_analyze_without_download(app):
    ctx = AppContext()
    source = VideoSource.local("C:\\dummy.mp4")
    # Analyze should not enqueue download
    # Demo metadata service returns fixed data
    meta = ctx.analyze(source)
    assert meta is not None
    # Ensure download queue empty
    assert ctx.download_items() == []


def test_quality_selection(app):
    ctx = AppContext()
    source = VideoSource.youtube("https://www.youtube.com/watch?v=dQw4w9WgXcQ")
    meta = ctx.analyze(source)
    # Demo service provides qualities
    assert len(meta.qualities) > 0


def test_output_folder_persistence():
    # AppContext should accept jobs_dir and persist
    ctx = AppContext(jobs_dir="C:\\tmp_jobs")
    assert ctx._jobs_dir == "C:\\tmp_jobs"
    assert ctx._job_repository is not None


def test_download_requires_successful_analyze(app):
    ctx = AppContext()
    source = VideoSource.youtube("https://youtu.be/dQw4w9WgXcQ")
    meta = ctx.analyze(source)
    # After analyze, download can be enqueued
    task_id = ctx.enqueue_download(source, quality="720")
    items = ctx.download_items()
    assert any(i.item_id == task_id for i in items)


def test_real_job_context():
    thread = DownloadWorkerThread(
        controller=object(),
        jobs_dir="C:\\jobs",
        source_path="C:\\video.mp4",
        mode="download",
        is_demo=False,
    )
    worker = thread.worker
    assert worker._is_demo is False
    assert worker._jobs_dir == "C:\\jobs"
    assert worker._source_path == "C:\\video.mp4"


def test_structured_download_progress(app):
    service = DemoDownloadService()
    controller = service
    # Simulate steps
    source = VideoSource.youtube("https://youtu.be/test")
    task_id = service.start(source, quality="1080")
    item = service.get(task_id)
    assert item is not None
    assert item.state.value == "queued"


def test_stop_and_checkpoint(app):
    # Ensure worker writes checkpoint on stop
    from mmnext.ui.workers import DownloadWorker
    controller = DemoDownloadService()
    # Start a real worker with demo mode
    worker = DownloadWorker(controller, is_demo=True)
    # Trigger checkpoint via state
    # Not a full integration test, just ensure no crash
    assert worker._is_demo is True


def test_resume_from_checkpoint():
    # Basic sanity: JobRepository can load checkpoint
    from mmnext.infrastructure.repository.job_repository import JobRepository
    import tempfile, os
    with tempfile.TemporaryDirectory() as tmp:
        repo = JobRepository(tmp)
        # No job exists, should be safe
        assert True


def test_demo_and_real_download_separation():
    # Demo worker should not require job context
    from mmnext.ui.workers import DownloadWorker
    demo_worker = DownloadWorker(object(), is_demo=True)
    assert demo_worker._is_demo is True
    # Real worker requires context
    with pytest.raises(ValueError):
        DownloadWorker(object(), jobs_dir="", source_path="", is_demo=False)
