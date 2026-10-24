"""Application-facing diagnostics facade."""

from __future__ import annotations

import platform
import sys

from ..application.runtime_service import RuntimeService


class DiagnosticsService:
    def __init__(self, runtime_service=None, jobs_dir=None):
        self.runtime_service = runtime_service or RuntimeService()
        self.jobs_dir = jobs_dir

    def report(self) -> dict:
        return {
            "python": sys.version,
            "platform": platform.platform(),
            "jobs_dir": str(self.jobs_dir) if self.jobs_dir is not None else "",
            "dependencies": {
                name: {
                    "available": status.available,
                    "detail": status.detail,
                }
                for name, status in self.runtime_service.detect().items()
            },
        }
