"""Finite QThread for Exact Dubbing render."""

from __future__ import annotations

from PySide6.QtCore import QObject, QThread, Signal, Slot


class ExactDubbingRenderWorker(QObject):
    progress = Signal(object)
    log = Signal(str)
    result = Signal(object)
    error = Signal(str)

    def __init__(self, coordinator, rows, video_path, video_duration, output_path, settings, parent=None):
        super().__init__(parent)
        self.coordinator = coordinator
        self.rows = rows
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
                self.rows,
                self.video_path,
                self.video_duration,
                self.output_path,
                self.settings,
                sink=sink,
            )
            self.result.emit(result)
        except Exception as exc:
            self.error.emit(str(exc))


class ExactDubbingRenderThread(QThread):
    progress = Signal(object)
    log = Signal(str)
    result = Signal(object)
    error = Signal(str)

    def __init__(self, coordinator, rows, video_path, video_duration, output_path, settings, parent=None):
        super().__init__(parent)
        self.coordinator = coordinator
        self.rows = rows
        self.video_path = video_path
        self.video_duration = video_duration
        self.output_path = output_path
        self.settings = settings

    def run(self):
        worker = ExactDubbingRenderWorker(
            self.coordinator,
            self.rows,
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
