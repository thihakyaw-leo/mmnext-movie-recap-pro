"""Finite QThread that runs the narrator pipeline off the GUI thread.

The pipeline calls translation, speech synthesis and Smart Sync render -
all of which are slow.  They must never run on the GUI thread, so the
coordinator is executed here and reports back through signals.
"""
from __future__ import annotations

from PySide6.QtCore import QObject, QThread, Signal, Slot


class NarratorPipelineWorker(QObject):
    """Runs the narrator pipeline and streams progress back to the UI."""

    progress = Signal(object)     # ProgressEvent
    log = Signal(str)             # human-readable stage message
    result = Signal(object)       # NarratorPipelineResult
    error = Signal(str)           # human-readable failure

    def __init__(self, coordinator, transcript, video_path, video_duration,
                 output_path, settings, parent=None):
        super().__init__(parent)
        self.coordinator = coordinator
        self.transcript = transcript
        self.video_path = video_path
        self.video_duration = video_duration
        self.output_path = output_path
        self.settings = settings

    @Slot()
    def run(self):
        try:
            def sink(event):
                self.progress.emit(event)

            def log(message: str) -> None:
                self.log.emit(message)

            self.coordinator.log = log
            result = self.coordinator.run(
                self.transcript,
                self.video_path,
                self.video_duration,
                self.output_path,
                self.settings,
                sink=sink,
            )
            self.result.emit(result)
        except Exception as exc:  # noqa: BLE001 - surfaced to the UI
            self.error.emit(str(exc))


class NarratorPipelineThread(QThread):
    """QThread wrapper around :class:`NarratorPipelineWorker`."""

    progress = Signal(object)
    log = Signal(str)
    result = Signal(object)
    error = Signal(str)

    def __init__(self, coordinator, transcript, video_path, video_duration,
                 output_path, settings, parent=None):
        super().__init__(parent)
        self.coordinator = coordinator
        self.transcript = transcript
        self.video_path = video_path
        self.video_duration = video_duration
        self.output_path = output_path
        self.settings = settings

    def run(self):
        # Construct the QObject in the actual worker thread, never the GUI.
        worker = NarratorPipelineWorker(
            self.coordinator,
            self.transcript,
            self.video_path,
            self.video_duration,
            self.output_path,
            self.settings,
        )
        worker.progress.connect(self.progress.emit)
        worker.log.connect(self.log.emit)
        worker.result.connect(self.result.emit)
        worker.error.connect(self.error.emit)
        worker.run()

    def stop(self):
        request_stop = getattr(self.coordinator, "request_stop", None)
        if request_stop is not None:
            request_stop()
