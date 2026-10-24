"""Background workers."""
from __future__ import annotations
import os, time
from typing import Optional
from PySide6.QtCore import QObject, QThread, Signal, Slot
from ..application.download_controller import DownloadController
from ..domain.enums import TaskState
from ..domain.paths import atomic_write_json, read_json
from ..domain.models import CHECKPOINT_SCHEMA_VERSION

class DownloadWorker(QObject):
    itemUpdated = Signal(object)
    stateChanged = Signal(object, object)
    message = Signal(str)
    log = Signal(str)
    started = Signal()
    progress = Signal(float)
    paused = Signal()
    resumed = Signal()
    pause_requested = Signal()
    stop_requested = Signal()
    stopped = Signal()
    failed = Signal(str)
    completed = Signal()

    def __init__(self, controller, tick_s=0.12, parent=None):
        super().__init__(parent)
        self._controller = controller
        self._tick_s = max(0.01, tick_s)
        self._running = False
        self._known = {}
        self._ckpt_dir = os.path.join(os.getcwd(), ".checkpoints")
        os.makedirs(self._ckpt_dir, exist_ok=True)

    @Slot()
    def start(self):
        self._running = True
        self.started.emit()

    @Slot()
    def stop(self):
        self._running = False
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
                            self._write_checkpoint(item)
                            self.paused.emit()
                        elif item.state == TaskState.RUNNING:
                            self.resumed.emit()
                        elif item.state == TaskState.STOPPED:
                            self._write_checkpoint(item)
                    if item.state in (TaskState.QUEUED, TaskState.RUNNING):
                        did_work = True
                        updated = self._controller.step(item.item_id)
                        if updated:
                            self.itemUpdated.emit(updated)
                            self.progress.emit(updated.percent)
                time.sleep(self._tick_s if did_work else self._tick_s*5)
        except Exception as e:
            self.failed.emit(str(e))
        finally:
            self.stopped.emit()
            self.completed.emit()

    def _ckpt_path(self, item):
        return os.path.join(self._ckpt_dir, f"ckpt_{item.item_id}.json")

    def _write_checkpoint(self, item):
        data = {
            "schema_version": CHECKPOINT_SCHEMA_VERSION,
            "task_id": item.item_id,
            "state": item.state.value,
            "progress": getattr(item, "percent", 0.0),
            "updated_at": time.time(),
            "resume_supported": True,
        }
        atomic_write_json(self._ckpt_path(item), data)

    def load_checkpoint(self, item):
        path = self._ckpt_path(item)
        if not os.path.exists(path):
            return None
        data = read_json(path)
        if not data or data.get("schema_version") != CHECKPOINT_SCHEMA_VERSION:
            try:
                os.remove(path)
            except Exception:
                pass
            return None
        return data

class DownloadWorkerThread(QThread):
    itemUpdated = Signal(object)
    stateChanged = Signal(object, object)
    message = Signal(str)
    def __init__(self, controller, tick_s=0.12, parent=None):
        super().__init__(parent)
        self._worker = DownloadWorker(controller, tick_s=tick_s)
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
