"""Finite QThread that reopens a completed REAL transcript off the GUI thread."""
from __future__ import annotations

from PySide6.QtCore import QObject, QThread, Signal, Slot


class ReopenTranscriptWorker(QObject):
    finished = Signal(object)   # (session, rows, language) on success
    error = Signal(str)         # human-readable failure

    def __init__(self, context, job_id, source_path, parent=None):
        super().__init__(parent)
        self.context = context
        self.job_id = job_id
        self.source_path = source_path

    @Slot()
    def run(self):
        try:
            # Read and validate off the GUI thread.  Nothing is applied here:
            # the prepared result is applied in a GUI-thread slot, after the
            # stale-request guard has confirmed it is still current.
            payload = self.context.prepare_transcript_from_job(
                self.job_id, self.source_path
            )
            self.finished.emit(payload)
        except Exception as exc:  # noqa: BLE001 - surfaced to UI
            self.error.emit(str(exc))


class ReopenTranscriptThread(QThread):
    result = Signal(object)
    error = Signal(str)

    def __init__(self, context, job_id, source_path, parent=None):
        super().__init__(parent)
        self.context = context
        self.job_id = job_id
        self.source_path = source_path
        # Identifies the request this thread serves.  The owner compares it
        # with its own counter to decide whether a result is still current.
        self.request_id = 0

    def run(self):
        worker = ReopenTranscriptWorker(self.context, self.job_id, self.source_path)
        worker.finished.connect(self.result.emit)
        worker.error.connect(self.error.emit)
        worker.run()

    def stop(self):
        pass
