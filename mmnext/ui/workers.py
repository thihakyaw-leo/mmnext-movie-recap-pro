"""Background workers."""
from __future__ import annotations
import hashlib
import os, time
from datetime import datetime
from typing import Optional
from PySide6.QtCore import QObject, QThread, Signal, Slot
from ..application.download_controller import DownloadController
from ..application.job_service import JobService
from ..domain.enums import TaskState
from ..domain.paths import atomic_write_json, read_json, mode_dir, job_root, stop_request_path
from ..domain.models import CHECKPOINT_SCHEMA_VERSION, JobCheckpoint

class DownloadWorker(QObject):
    itemUpdated = Signal(object)
    stateChanged = Signal(object, object)
    message = Signal(str)
    log = Signal(str)
    started = Signal()
    progress = Signal(float)
    progressDetailed = Signal(dict)
    paused = Signal()
    resumed = Signal()
    pause_requested = Signal()
    stop_requested = Signal()
    stopped = Signal()
    failed = Signal(str)
    completed = Signal()

    def __init__(self, controller, jobs_dir=None, source_path=None, mode='download', tick_s=0.12, is_demo=None, parent=None):
        super().__init__(parent)
        self._controller = controller
        self._tick_s = max(0.01, tick_s)
        self._running = False
        self._known = {}
        self._jobs_dir = jobs_dir
        self._source_path = source_path
        self._mode = mode
        # infer demo mode if not explicit
        if is_demo is None:
            is_demo = not (bool(jobs_dir) and bool(source_path))
        self._is_demo = is_demo
        # job-scoped base directory; never use cwd for real jobs
        if self._is_demo:
            self._ckpt_base = None
            self._jobs = None
        elif self._jobs_dir and self._source_path:
            base = mode_dir(self._jobs_dir, self._source_path, self._mode)
            base.mkdir(parents=True, exist_ok=True)
            self._ckpt_base = base
            self._jobs = JobService(self._jobs_dir)
        else:
            raise ValueError("Real jobs require jobs_dir and source_path; missing job context")

    @Slot()
    def start(self):
        self._running = True
        self.started.emit()

    @Slot()
    def stop(self):
        self._running = False
        # persistent stop marker for real jobs
        try:
            if self._jobs_dir and self._source_path:
                marker = stop_request_path(self._jobs_dir, self._source_path)
                marker.parent.mkdir(parents=True, exist_ok=True)
                atomic_write_json(marker, {"requested_at": datetime.utcnow().isoformat() + "Z"})
        except Exception:
            pass
        self.stop_requested.emit()

    @Slot()
    def run(self):
        self._running = True
        try:
            while self._running:
                did_work = False
                for item in self._controller.items():
                    if not self._running:
                        break
                    prev = self._known.get(item.item_id)
                    if prev is not item.state:
                        self._known[item.item_id] = item.state
                        self.stateChanged.emit(item, item.state)
                        msg = f"{item.title}: {item.state.value}"
                        self.message.emit(msg)
                        self.log.emit(msg)
                        if item.state == TaskState.PAUSE_REQUESTED:
                            self.pause_requested.emit()
                        elif item.state == TaskState.PAUSED:
                            ok = self._write_checkpoint(item)
                            if ok:
                                self.paused.emit()
                            else:
                                self.failed.emit("Checkpoint write failed for PAUSED")
                        elif item.state == TaskState.RUNNING:
                            self.resumed.emit()
                        elif item.state == TaskState.STOPPED:
                            ok = self._write_checkpoint(item)
                            if ok:
                                # cleanup persistent stop marker
                                try:
                                    if self._jobs_dir and self._source_path:
                                        marker = stop_request_path(self._jobs_dir, self._source_path)
                                        if marker.exists():
                                            marker.unlink(missing_ok=True)
                                except Exception:
                                    pass
                                self.stopped.emit()
                            else:
                                self.failed.emit("Checkpoint write failed for STOPPED")
                    if item.state in (TaskState.QUEUED, TaskState.RUNNING):
                        did_work = True
                        updated = self._controller.step(item.item_id)
                        if updated:
                            self.itemUpdated.emit(updated)
                            self.progress.emit(updated.percent)
                            # structured progress mapping
                            progress_data = {
                                "stage": "download",
                                "current": updated.downloaded_bytes,
                                "total": updated.total_bytes,
                                "percent": updated.percent,
                                "bytes_done": updated.downloaded_bytes,
                                "bytes_total": updated.total_bytes,
                                "speed_bps": updated.speed_bps,
                                "eta_s": updated.eta_s,
                                "message": f"{updated.title}: {updated.state.value}",
                                "simulated": self._is_demo,
                            }
                            self.progressDetailed.emit(progress_data)
                time.sleep(self._tick_s if did_work else self._tick_s*5)
        except Exception as e:
            self.failed.emit(str(e))
        finally:
            # stopped/completed only if not already emitted due to state
            if self._running:
                self.stopped.emit()
            self.completed.emit()

    def _ckpt_path(self, item):
        if self._is_demo:
            return os.path.join(os.getcwd(), ".checkpoints", f"ckpt_{item.item_id}.json")
        if self._jobs_dir and self._source_path and self._ckpt_base:
            # Use public repository-style path for real jobs
            from ..domain.enums import AppMode
            try:
                mode_enum = AppMode(self._mode)
            except ValueError:
                mode_enum = AppMode.COMMON_EDITING
            return self._jobs.checkpoint_path(item.item_id, self._source_path, mode_enum)
        # legacy fallback
        return os.path.join(os.getcwd(), ".checkpoints", f"ckpt_{item.item_id}.json")

    def _fingerprint(self, item):
        # deterministic fingerprint for source identity, mode, settings, schema
        src = self._source_path or ""
        # source size/mtime if local file
        size = 0
        mtime = 0.0
        try:
            if src and os.path.isfile(src):
                st = os.stat(src)
                size = int(st.st_size)
                mtime = float(st.st_mtime)
        except OSError:
            pass
        # settings hash placeholder
        settings = {"url": item.url, "output_path": item.output_path, "item_id": item.item_id}
        import json
        settings_bytes = json.dumps(settings, sort_keys=True, separators=(",", ":")).encode("utf-8")
        raw = f"{src}|{size}|{mtime:.3f}|{self._mode}|{2}|"
        raw_bytes = raw.encode("utf-8") + settings_bytes
        return hashlib.sha1(raw_bytes).hexdigest()

    def _write_checkpoint(self, item):
        try:
            ckpt = JobCheckpoint(
                task_id=item.item_id,
                mode=self._mode,
                state=item.state,
                completed_units=int(item.downloaded_bytes),
                total_units=int(item.total_bytes),
                partial_path=(item.output_path + ".partial") if item.output_path else "",
                output_path=item.output_path,
                resume_supported=True,
                fingerprint=self._fingerprint(item),
                schema_version=CHECKPOINT_SCHEMA_VERSION,
                updated_at=datetime.utcnow().isoformat() + "Z",
                message=f"{item.title}: {item.state.value}",
            )
            path = self._ckpt_path(item)
            atomic_write_json(path, ckpt.to_dict())
            return True
        except Exception as e:
            self.failed.emit(f"Checkpoint write error: {e}")
            return False

    def load_checkpoint(self, item):
        path = self._ckpt_path(item)
        if not path.exists():
            return None
        data = read_json(path)
        if not data:
            try:
                path.unlink()
            except Exception:
                pass
            return None
        if data.get("schema_version") != CHECKPOINT_SCHEMA_VERSION:
            try:
                path.unlink()
            except Exception:
                pass
            return None
        try:
            ckpt = JobCheckpoint.from_dict(data)
        except Exception:
            try:
                path.unlink()
            except Exception:
                pass
            return None
        # fingerprint / mode validation
        if ckpt.mode != self._mode:
            return None
        if ckpt.fingerprint != self._fingerprint(item):
            return None
        if not ckpt.resume_supported:
            return ckpt
        if ckpt.state not in (TaskState.PAUSED, TaskState.STOPPED):
            return None
        return ckpt

class DownloadWorkerThread(QThread):
    itemUpdated = Signal(object)
    stateChanged = Signal(object, object)
    message = Signal(str)
    def __init__(self, controller, jobs_dir=None, source_path=None, mode='download', tick_s=0.12, is_demo=True, parent=None):
        super().__init__(parent)
        self._worker = DownloadWorker(controller, jobs_dir=jobs_dir, source_path=source_path, mode=mode, tick_s=tick_s, is_demo=is_demo)
        self._worker.moveToThread(self)
        self._worker.itemUpdated.connect(self.itemUpdated)
        self._worker.stateChanged.connect(self.stateChanged)
        self._worker.message.connect(self.message)
        self.started.connect(self._worker.run)
    @property
    def worker(self):
        return self._worker
    def shutdown(self, wait_ms=2000):
        if self._worker:
            self._worker.stop()
        if self.isRunning():
            self.quit()
            self.wait(wait_ms)
