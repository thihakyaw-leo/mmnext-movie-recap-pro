"""Finite QThread transcription with separate result and lifecycle signals."""
from __future__ import annotations

from PySide6.QtCore import QObject, QThread, Signal, Slot
from ..domain.events import ProgressEvent, LogEvent, ErrorEvent
from ..domain.errors import TranscriptStopped


class TranscriptWorker(QObject):
    started = Signal()
    finished = Signal(object, str)  # compatibility: successful result only
    progress = Signal(object)
    log = Signal(object)
    error = Signal(object)
    stopped = Signal(str)

    def __init__(self, provider, media_path, language=None, auto_detect=False, parent=None):
        super().__init__(parent)
        self.provider = provider
        self.media_path = media_path
        self.language = language
        self.auto_detect = auto_detect

    @Slot()
    def run(self):
        self.started.emit()
        try:
            def emit(event):
                if isinstance(event, ProgressEvent):
                    self.progress.emit(event)
                elif isinstance(event, LogEvent):
                    self.log.emit(event)
                elif isinstance(event, ErrorEvent):
                    self.error.emit(event)
            rows, language = self.provider.transcribe(
                self.media_path, language=self.language, auto_detect=self.auto_detect, emit=emit)
            self.finished.emit(rows, language)
        except TranscriptStopped as exc:
            self.stopped.emit(str(exc))
        except Exception as exc:
            self.error.emit(ErrorEvent(message=f"Transcribe failed: {exc}",
                                       detail=f"Source: {self.media_path}. Fix dependencies/input and restart; resume unsupported."))

    def stop(self):
        request_stop = getattr(self.provider, "request_stop", None)
        if request_stop is not None:
            request_stop()


class TranscriptWorkerThread(QThread):
    """No event-loop leak; QThread.finished remains the native lifecycle signal."""
    result = Signal(object, str)
    progress = Signal(object)
    log = Signal(object)
    error = Signal(object)
    stopped = Signal(str)

    def __init__(self, provider, media_path, language=None, auto_detect=False, parent=None):
        super().__init__(parent)
        self.provider = provider
        self.media_path = media_path
        self.language = language
        self.auto_detect = auto_detect

    def run(self):
        # Construct the QObject in the actual worker thread, never the GUI.
        worker = TranscriptWorker(self.provider, self.media_path, self.language, self.auto_detect)
        worker.finished.connect(self.result.emit)
        worker.progress.connect(self.progress.emit)
        worker.log.connect(self.log.emit)
        worker.error.connect(self.error.emit)
        worker.stopped.connect(self.stopped.emit)
        worker.run()

    def stop(self):
        request_stop = getattr(self.provider, "request_stop", None)
        if request_stop is not None:
            request_stop()
