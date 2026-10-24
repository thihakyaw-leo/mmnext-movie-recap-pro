import tempfile
from pathlib import Path
from PySide6.QtCore import QCoreApplication
from mmnext.ui.workers import DownloadWorker
from mmnext.domain.enums import TaskState, AppMode
from mmnext.domain.models import DownloadItem, JobCheckpoint, CHECKPOINT_SCHEMA_VERSION
from mmnext.infrastructure.repository.job_repository import JobRepository
import hashlib, os

def test_worker_checkpoint_round_trip_through_repository(tmp_path, monkeypatch):
    # tmp_path may legitimately live inside the checkout. Isolate cwd from
    # the configured jobs root instead of assuming unrelated parent paths.
    cwd = tmp_path / "unrelated-cwd"
    cwd.mkdir()
    monkeypatch.chdir(cwd)
    app = QCoreApplication.instance() or QCoreApplication([])
    jobs_dir = str(tmp_path)
    source_path = str(tmp_path / "source.mp4")
    Path(source_path).write_bytes(b"dummy")
    worker = DownloadWorker(controller=None, jobs_dir=jobs_dir, source_path=source_path, mode='common_editing', is_demo=False)
    item = DownloadItem(item_id="job123", title="t", url="http://x", total_bytes=100, downloaded_bytes=50, output_path=str(tmp_path/"out.mp4"), state=TaskState.PAUSED)
    # write checkpoint via worker
    ok = worker._write_checkpoint(item)
    assert ok
    repo = JobRepository(jobs_dir)
    ckpt_data = repo.load_checkpoint("job123", source_path, AppMode.COMMON_EDITING)
    assert ckpt_data is not None
    assert ckpt_data["task_id"] == "job123"
    # verify path under jobs_dir, not cwd
    ckpt_path = repo._checkpoint_path("job123", source_path, AppMode.COMMON_EDITING)
    assert ckpt_path.resolve().is_relative_to(tmp_path.resolve())
    assert not ckpt_path.resolve().is_relative_to(cwd.resolve())
    assert not list(cwd.rglob("checkpoint.json"))

def test_worker_fingerprint_includes_source_size(tmp_path):
    app = QCoreApplication.instance() or QCoreApplication([])
    source_path = str(tmp_path / "src.mp4")
    Path(source_path).write_bytes(b"12345")
    worker = DownloadWorker(controller=None, jobs_dir=str(tmp_path), source_path=source_path, mode='common_editing', is_demo=False)
    item = DownloadItem(item_id="i1", title="t", url="http://x", total_bytes=10, output_path="", state=TaskState.QUEUED)
    fp1 = worker._fingerprint(item)
    # change size
    Path(source_path).write_bytes(b"1234567890")
    fp2 = worker._fingerprint(item)
    assert fp1 != fp2

def test_worker_fingerprint_includes_mtime(tmp_path):
    import time
    app = QCoreApplication.instance() or QCoreApplication([])
    source_path = str(tmp_path / "src2.mp4")
    Path(source_path).write_bytes(b"data")
    worker = DownloadWorker(controller=None, jobs_dir=str(tmp_path), source_path=source_path, mode='common_editing', is_demo=False)
    item = DownloadItem(item_id="i2", title="t", url="http://x", total_bytes=10, output_path="", state=TaskState.QUEUED)
    fp1 = worker._fingerprint(item)
    time.sleep(0.01)
    os.utime(source_path, None)
    fp2 = worker._fingerprint(item)
    assert fp1 != fp2

def test_real_worker_requires_job_context():
    app = QCoreApplication.instance() or QCoreApplication([])
    try:
        worker = DownloadWorker(controller=None, jobs_dir=None, source_path=None, mode='common_editing', is_demo=False)
        assert False, "Should raise"
    except ValueError:
        pass

def test_demo_fallback_is_explicit():
    app = QCoreApplication.instance() or QCoreApplication([])
    # demo mode should not require context
    worker = DownloadWorker(controller=None, jobs_dir=None, source_path=None, mode='download', is_demo=True)
    assert worker._ckpt_base is None
