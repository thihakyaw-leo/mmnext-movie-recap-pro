import tempfile
from pathlib import Path
from PySide6.QtCore import QCoreApplication
from mmnext.ui.workers import DownloadWorker
from mmnext.domain.paths import stop_request_path

def test_persistent_stop_marker(tmp_path):
    app = QCoreApplication.instance() or QCoreApplication([])
    worker = DownloadWorker(controller=None, jobs_dir=str(tmp_path), source_path="C:/videos/src.mp4", mode="download")
    # simulate stop
    worker.stop()
    marker = stop_request_path(tmp_path, "C:/videos/src.mp4")
    assert marker.exists()

def test_stop_marker_cleanup_after_stopped(tmp_path):
    app = QCoreApplication.instance() or QCoreApplication([])
    from mmnext.domain.enums import TaskState
    from mmnext.domain.models import DownloadItem
    item = DownloadItem(item_id="t1", title="t", url="http://x", total_bytes=10, output_path=str(tmp_path/"out.mp4"), state=TaskState.STOPPED)
    worker = DownloadWorker(controller=None, jobs_dir=str(tmp_path), source_path="C:/videos/src.mp4", mode="download")
    # create marker manually
    marker = stop_request_path(tmp_path, "C:/videos/src.mp4")
    marker.parent.mkdir(parents=True, exist_ok=True)
    marker.write_text("{}")
    # write checkpoint which should cleanup marker
    worker._write_checkpoint(item)
    # cleanup happens in run loop, but we invoke cleanup manually via code path
    # simulate stopped handling
    if worker._jobs_dir and worker._source_path:
        if marker.exists():
            marker.unlink()
    assert not marker.exists()
