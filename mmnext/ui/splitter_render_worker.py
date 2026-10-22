"""Finite QThread for Splitter render."""

from __future__ import annotations

from PySide6.QtCore import QObject, QThread, Signal, Slot


class SplitterRenderWorker(QObject):
    progress = Signal(object)
    log = Signal(str)
    result = Signal(object)
    error = Signal(str)

    def __init__(self, coordinator, parts, video_path, output_dir, settings, parent=None):
        super().__init__(parent)
        self.coordinator = coordinator
        self.parts = parts
        self.video_path = video_path
        self.output_dir = output_dir
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
                self.parts,
                self.video_path,
                self.output_dir,
                self.settings,
                sink=sink,
            )
            self.result.emit(result)
        except Exception as exc:
            self.error.emit(str(exc))


class SplitterRenderThread(QThread):
    progress = Signal(object)
    log = Signal(str)
    result = Signal(object)
    error = Signal(str)

    def __init__(self, coordinator, parts, video_path, output_dir, settings, parent=None):
        super().__init__(parent)
        self.coordinator = coordinator
        self.parts = parts
        self.video_path = video_path
        self.output_dir = output_dir
        self.settings = settings

    def run(self):
        worker = SplitterRenderWorker(
            self.coordinator,
            self.parts,
            self.video_path,
            self.output_dir,
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
