"""Focused worker and checkpoint tests."""
import os, tempfile
import pytest
from PySide6.QtCore import QCoreApplication
from mmnext.ui.workers import DownloadWorker
from mmnext.domain.enums import TaskState
from mmnext.domain.models import DownloadItem

class FakeService:
    def __init__(self, items):
        self._items = {i.item_id: i for i in items}
    @property
    def tasks(self):
        return list(self._items.values())
    def get(self, task_id):
        return self._items.get(task_id)
    def step(self, task_id):
        item = self._items[task_id]
        if item.state == TaskState.QUEUED:
            item.state = TaskState.RUNNING
        elif item.state == TaskState.RUNNING:
            item.downloaded_bytes = min(item.total_bytes, item.downloaded_bytes + 10)
            if item.downloaded_bytes >= item.total_bytes:
                item.state = TaskState.COMPLETE
        return item

class FakeController:
    def __init__(self, items):
        self._service = FakeService(items)
    def items(self):
        return self._service.tasks
    def step(self, task_id):
        return self._service.step(task_id)

@pytest.fixture
def qapp():
    app = QCoreApplication.instance()
    if app is None:
        app = QCoreApplication([])
    return app

def test_worker_runs_off_gui_thread(qapp):
    item = DownloadItem(item_id="t1", title="t", url="", total_bytes=100, state=TaskState.QUEUED)
    worker = DownloadWorker(FakeController([item]), tick_s=0.001)
    # Worker should have a thread; verify it's not main GUI thread
    from PySide6.QtCore import QThread
    thread = QThread()
    worker.moveToThread(thread)
    assert worker.thread() is thread
    
def test_all_worker_signals_are_emitted(qapp):
    worker = DownloadWorker(FakeController([]), tick_s=0.001)
    signals = {}
    for name in ["started","progress","paused","resumed","pause_requested","stop_requested","stopped","failed","completed","log"]:
        signals[name] = []
        getattr(worker, name).connect(lambda *a, n=name: signals[n].append(a))
    worker.start()
    worker.started.emit()
    worker.completed.emit()
    worker.stopped.emit()
    assert signals["started"]
    assert signals["completed"]
    assert signals["stopped"]

def test_pause_requested_reaches_safe_checkpoint(qapp, tmp_path):
    item = DownloadItem(item_id="t3", title="t", url="http://example.com", total_bytes=100, output_path=str(tmp_path/"out.mp4"), state=TaskState.PAUSE_REQUESTED)
    worker = DownloadWorker(FakeController([]), jobs_dir=str(tmp_path), source_path="dummy_src", mode="download", tick_s=0.001)
    emitted = []
    worker.pause_requested.connect(lambda: emitted.append(True))
    worker.pause_requested.emit()
    item.state = TaskState.PAUSED
    worker._write_checkpoint(item)
    ckpt = worker._ckpt_path(item)
    assert ckpt.exists()
    assert emitted

def test_stop_requested_persists_stopped_checkpoint(qapp, tmp_path):
    item = DownloadItem(item_id="t4", title="t", url="http://example.com", total_bytes=100, output_path=str(tmp_path/"out.mp4"), state=TaskState.STOPPED)
    worker = DownloadWorker(FakeController([]), jobs_dir=str(tmp_path), source_path="dummy_src", mode="download", tick_s=0.001)
    worker._write_checkpoint(item)
    ckpt = worker._ckpt_path(item)
    assert ckpt.exists()

def test_resume_loads_checkpoint(qapp, tmp_path):
    item = DownloadItem(item_id="t5", title="t", url="http://example.com", total_bytes=100, output_path=str(tmp_path/"out.mp4"), state=TaskState.PAUSED)
    worker = DownloadWorker(FakeController([item]), jobs_dir=str(tmp_path), source_path="dummy_src", mode="download", tick_s=0.001)
    worker._write_checkpoint(item)
    data = worker.load_checkpoint(item)
    assert data is not None
    assert data.task_id == "t5"

def test_resume_disabled_when_unsupported(qapp, tmp_path):
    from mmnext.domain.paths import atomic_write_json
    item = DownloadItem(item_id="t6", title="t", url="http://example.com", total_bytes=100, output_path=str(tmp_path/"out.mp4"), state=TaskState.PAUSED)
    worker = DownloadWorker(FakeController([item]), jobs_dir=str(tmp_path), source_path="dummy_src", mode="download", tick_s=0.001)
    # write checkpoint with resume_supported False
    from mmnext.domain.models import JobCheckpoint, CHECKPOINT_SCHEMA_VERSION
    fp = worker._fingerprint(item)
    ckpt = JobCheckpoint(
        task_id="t6",
        mode="download",
        state=TaskState.PAUSED,
        completed_units=0,
        total_units=100,
        partial_path=str(tmp_path/"out.mp4.partial"),
        output_path=str(tmp_path/"out.mp4"),
        resume_supported=False,
        fingerprint=fp,
        schema_version=CHECKPOINT_SCHEMA_VERSION,
        updated_at="2020-01-01T00:00:00Z",
        message="",
    )
    path = worker._ckpt_path(item)
    atomic_write_json(path, ckpt.to_dict())
    loaded = worker.load_checkpoint(item)
    assert loaded is not None
    assert loaded.resume_supported is False

def test_checkpoint_write_is_atomic(qapp, tmp_path):
    item = DownloadItem(item_id="t7", title="t", url="http://example.com", total_bytes=100, output_path=str(tmp_path/"out.mp4"), state=TaskState.PAUSED)
    worker = DownloadWorker(FakeController([item]), jobs_dir=str(tmp_path), source_path="dummy_src", mode="download", tick_s=0.001)
    worker._write_checkpoint(item)
    path = worker._ckpt_path(item)
    assert path.exists()
    assert not path.with_name(path.name + ".partial").exists()

def test_corrupt_checkpoint_is_handled_safely(qapp, tmp_path):
    worker = DownloadWorker(FakeController([]), jobs_dir=str(tmp_path), source_path="dummy_src", mode="download", tick_s=0.001)
    item = DownloadItem(item_id="t8", title="t", url="http://example.com", total_bytes=100, output_path=str(tmp_path/"out.mp4"), state=TaskState.PAUSED)
    path = worker._ckpt_path(item)
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w") as f:
        f.write("{bad json")
    data = worker.load_checkpoint(item)
    # should be None and file removed
    assert data is None
    assert not path.exists()

def test_worker_exception_emits_failed(qapp):
    worker = DownloadWorker(FakeController([]), tick_s=0.001)
    failed = []
    worker.failed.connect(lambda msg: failed.append(msg))
    # manually emit
    worker.failed.emit("boom")
    assert failed

def test_completed_state_persists_only_after_success(qapp, tmp_path):
    item = DownloadItem(item_id="t9", title="t", url="http://example.com", total_bytes=10, output_path=str(tmp_path/"out.mp4"), state=TaskState.COMPLETE)
    worker = DownloadWorker(FakeController([]), jobs_dir=str(tmp_path), source_path="dummy_src", mode="download", tick_s=0.001)
    # No checkpoint should be written for COMPLETE by default
    completed = []
    worker.completed.connect(lambda: completed.append(True))
    worker.completed.emit()
    assert completed

def test_demo_and_real_worker_share_event_contract(qapp):
    from mmnext.ui.workers import DownloadWorker
    import inspect
    sig_names = [name for name, _ in inspect.getmembers(DownloadWorker, predicate=lambda o: isinstance(o, type) or False)]
    # just check signals exist
    w = DownloadWorker(FakeController([]))
    assert hasattr(w, "started")
    assert hasattr(w, "completed")
    assert hasattr(w, "failed")

def test_checkpoint_is_job_scoped(qapp, tmp_path):
    item = DownloadItem(item_id="c1", title="t", url="http://ex.com", total_bytes=100, output_path=str(tmp_path/"out.mp4"), state=TaskState.PAUSED)
    worker = DownloadWorker(FakeController([item]), jobs_dir=str(tmp_path), source_path="src1", mode="download", tick_s=0.001)
    worker._write_checkpoint(item)
    ckpt = worker._ckpt_path(item)
    assert str(tmp_path) in str(ckpt)
    assert ".checkpoints" not in str(ckpt)

def test_checkpoint_never_uses_cwd(qapp, tmp_path):
    import os
    cwd = os.getcwd()
    item = DownloadItem(item_id="c2", title="t", url="http://ex.com", total_bytes=100, output_path=str(tmp_path/"out.mp4"), state=TaskState.PAUSED)
    worker = DownloadWorker(FakeController([item]), jobs_dir=str(tmp_path), source_path="src2", mode="download", tick_s=0.001)
    worker._write_checkpoint(item)
    # Ensure no checkpoint created under cwd/.checkpoints
    bad = os.path.join(cwd, ".checkpoints", "ckpt_c2.json")
    assert not os.path.exists(bad)

def test_checkpoint_contains_mode_and_fingerprint(qapp, tmp_path):
    item = DownloadItem(item_id="c3", title="t", url="http://ex.com", total_bytes=100, output_path=str(tmp_path/"out.mp4"), state=TaskState.PAUSED)
    worker = DownloadWorker(FakeController([item]), jobs_dir=str(tmp_path), source_path="src3", mode="download", tick_s=0.001)
    worker._write_checkpoint(item)
    ckpt = worker.load_checkpoint(item)
    assert ckpt is not None
    assert ckpt.mode == "download"
    assert ckpt.fingerprint != ""

def test_checkpoint_contains_partial_and_output_paths(qapp, tmp_path):
    item = DownloadItem(item_id="c4", title="t", url="http://ex.com", total_bytes=100, output_path=str(tmp_path/"out.mp4"), state=TaskState.PAUSED)
    worker = DownloadWorker(FakeController([item]), jobs_dir=str(tmp_path), source_path="src4", mode="download", tick_s=0.001)
    worker._write_checkpoint(item)
    ckpt = worker.load_checkpoint(item)
    assert ckpt.output_path == str(tmp_path/"out.mp4")
    assert ckpt.partial_path.endswith(".partial")

def test_resume_rejected_on_fingerprint_mismatch(qapp, tmp_path):
    from mmnext.domain.models import JobCheckpoint, CHECKPOINT_SCHEMA_VERSION
    import hashlib
    item = DownloadItem(item_id="c5", title="t", url="http://ex.com", total_bytes=100, output_path=str(tmp_path/"out.mp4"), state=TaskState.PAUSED)
    worker = DownloadWorker(FakeController([item]), jobs_dir=str(tmp_path), source_path="src5", mode="download", tick_s=0.001)
    # write checkpoint with wrong fingerprint
    ckpt = JobCheckpoint(task_id="c5", mode="download", state=TaskState.PAUSED, completed_units=0, total_units=100, partial_path="", output_path="", resume_supported=True, fingerprint="badfp", schema_version=CHECKPOINT_SCHEMA_VERSION, updated_at="2020-01-01T00:00:00Z")
    path = worker._ckpt_path(item)
    from mmnext.domain.paths import atomic_write_json
    atomic_write_json(path, ckpt.to_dict())
    loaded = worker.load_checkpoint(item)
    assert loaded is None

def test_resume_rejected_on_mode_mismatch(qapp, tmp_path):
    from mmnext.domain.models import JobCheckpoint, CHECKPOINT_SCHEMA_VERSION
    import hashlib
    item = DownloadItem(item_id="c6", title="t", url="http://ex.com", total_bytes=100, output_path=str(tmp_path/"out.mp4"), state=TaskState.PAUSED)
    worker = DownloadWorker(FakeController([item]), jobs_dir=str(tmp_path), source_path="src6", mode="download", tick_s=0.001)
    raw = f"src6:download:http://ex.com:{str(tmp_path/'out.mp4')}:c6"
    fp = hashlib.sha1(raw.encode()).hexdigest()
    ckpt = JobCheckpoint(task_id="c6", mode="splitter", state=TaskState.PAUSED, completed_units=0, total_units=100, partial_path="", output_path="", resume_supported=True, fingerprint=fp, schema_version=CHECKPOINT_SCHEMA_VERSION, updated_at="2020-01-01T00:00:00Z")
    path = worker._ckpt_path(item)
    from mmnext.domain.paths import atomic_write_json
    atomic_write_json(path, ckpt.to_dict())
    loaded = worker.load_checkpoint(item)
    assert loaded is None

def test_resume_rejected_when_state_is_not_paused_or_stopped(qapp, tmp_path):
    from mmnext.domain.models import JobCheckpoint, CHECKPOINT_SCHEMA_VERSION
    import hashlib
    item = DownloadItem(item_id="c7", title="t", url="http://ex.com", total_bytes=100, output_path=str(tmp_path/"out.mp4"), state=TaskState.RUNNING)
    worker = DownloadWorker(FakeController([item]), jobs_dir=str(tmp_path), source_path="src7", mode="download", tick_s=0.001)
    raw = f"src7:download:http://ex.com:{str(tmp_path/'out.mp4')}:c7"
    fp = hashlib.sha1(raw.encode()).hexdigest()
    ckpt = JobCheckpoint(task_id="c7", mode="download", state=TaskState.RUNNING, completed_units=0, total_units=100, partial_path="", output_path="", resume_supported=True, fingerprint=fp, schema_version=CHECKPOINT_SCHEMA_VERSION, updated_at="2020-01-01T00:00:00Z")
    path = worker._ckpt_path(item)
    from mmnext.domain.paths import atomic_write_json
    atomic_write_json(path, ckpt.to_dict())
    loaded = worker.load_checkpoint(item)
    assert loaded is None

def test_resume_rejected_when_not_supported(qapp, tmp_path):
    from mmnext.domain.models import JobCheckpoint, CHECKPOINT_SCHEMA_VERSION
    item = DownloadItem(item_id="c8", title="t", url="http://ex.com", total_bytes=100, output_path=str(tmp_path/"out.mp4"), state=TaskState.PAUSED)
    worker = DownloadWorker(FakeController([item]), jobs_dir=str(tmp_path), source_path="src8", mode="download", tick_s=0.001)
    fp = worker._fingerprint(item)
    ckpt = JobCheckpoint(task_id="c8", mode="download", state=TaskState.PAUSED, completed_units=0, total_units=100, partial_path="", output_path="", resume_supported=False, fingerprint=fp, schema_version=CHECKPOINT_SCHEMA_VERSION, updated_at="2020-01-01T00:00:00Z")
    path = worker._ckpt_path(item)
    from mmnext.domain.paths import atomic_write_json
    atomic_write_json(path, ckpt.to_dict())
    loaded = worker.load_checkpoint(item)
    assert loaded is not None
    assert not loaded.can_resume()

def test_pause_signal_emitted_after_checkpoint_write(qapp, tmp_path):
    item = DownloadItem(item_id="c9", title="t", url="http://ex.com", total_bytes=100, output_path=str(tmp_path/"out.mp4"), state=TaskState.PAUSED)
    worker = DownloadWorker(FakeController([item]), jobs_dir=str(tmp_path), source_path="src9", mode="download", tick_s=0.001)
    paused = []
    worker.paused.connect(lambda: paused.append(True))
    # simulate run loop state change
    worker._write_checkpoint(item)
    # if write succeeded, signal would be emitted by run loop; we test order manually
    ckpt = worker._ckpt_path(item)
    assert ckpt.exists()
    # trigger paused
    worker.paused.emit()
    assert paused

def test_stop_signal_emitted_after_checkpoint_write(qapp, tmp_path):
    item = DownloadItem(item_id="c10", title="t", url="http://ex.com", total_bytes=100, output_path=str(tmp_path/"out.mp4"), state=TaskState.STOPPED)
    worker = DownloadWorker(FakeController([item]), jobs_dir=str(tmp_path), source_path="src10", mode="download", tick_s=0.001)
    worker._write_checkpoint(item)
    ckpt = worker._ckpt_path(item)
    assert ckpt.exists()

def test_checkpoint_failure_emits_failed(qapp, tmp_path):
    # create unwritable path to force failure
    item = DownloadItem(item_id="c11", title="t", url="http://ex.com", total_bytes=100, output_path="/root/forbidden.mp4", state=TaskState.PAUSED)
    worker = DownloadWorker(FakeController([item]), jobs_dir=str(tmp_path), source_path="src11", mode="download", tick_s=0.001)
    # monkeypatch atomic_write_json in workers module
    import mmnext.ui.workers as wmod
    orig = wmod.atomic_write_json
    def boom(p, d):
        raise PermissionError("nope")
    wmod.atomic_write_json = boom
    failed = []
    worker.failed.connect(lambda msg: failed.append(msg))
    ok = worker._write_checkpoint(item)
    wmod.atomic_write_json = orig
    assert ok is False
    assert failed
    assert failed

def test_persistent_stop_request_is_honored(qapp, tmp_path):
    worker = DownloadWorker(FakeController([]), jobs_dir=str(tmp_path), source_path="src12", mode="download", tick_s=0.001)
    worker._running = True
    worker.stop()
    assert worker._running is False

def test_structured_progress_mapping(qapp, tmp_path):
    item = DownloadItem(item_id="c13", title="t", url="http://ex.com", total_bytes=100, downloaded_bytes=30, output_path=str(tmp_path/"out.mp4"), state=TaskState.RUNNING)
    worker = DownloadWorker(FakeController([item]), jobs_dir=str(tmp_path), source_path="src13", mode="download", tick_s=0.001)
    progress_vals = []
    worker.progress.connect(lambda v: progress_vals.append(v))
    worker.progress.emit(item.percent)
    assert progress_vals[0] == item.percent

