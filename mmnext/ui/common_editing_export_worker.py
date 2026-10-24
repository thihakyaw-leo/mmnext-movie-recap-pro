"""Finite QThread for Common Editing export."""

from __future__ import annotations

from PySide6.QtCore import QObject, QThread, Signal, Slot


class CommonEditingExportWorker(QObject):
    progress = Signal(object)
    log = Signal(str)
    result = Signal(object)
    error = Signal(str)

    def __init__(self, service, video_path, session, output_path, settings, parent=None):
        super().__init__(parent)
        self.service = service
        self.video_path = video_path
        self.session = session
        self.output_path = output_path
        self.settings = settings

    @Slot()
    def run(self):
        try:
            ok = self.service.export(self.video_path, self.session, self.output_path, self.settings)
            self.result.emit(ok)
        except Exception as exc:
            self.error.emit(str(exc))


class CommonEditingExportThread(QThread):
    progress = Signal(object)
    log = Signal(str)
    result = Signal(object)
    error = Signal(str)

    def __init__(self, service, video_path, session, output_path, settings, parent=None):
        super().__init__(parent)
        self.service = service
        self.video_path = video_path
        self.session = session
        self.output_path = output_path
        self.settings = settings

    def run(self):
        worker = CommonEditingExportWorker(
            self.service, self.video_path, self.session, self.output_path, self.settings
        )
        worker.result.connect(self.result.emit)
        worker.error.connect(self.error.emit)
        worker.run()

    def stop(self):
        pass
