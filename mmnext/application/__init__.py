"""Application layer: orchestration between the UI and the services.

This package must not import PySide6. It owns the job state machine, the
project/session state, the download control loop and the per-mode
coordinators. The UI drives it; the services do the work.
"""

from __future__ import annotations

__all__ = [
    "job_manager",
    "project_controller",
    "download_controller",
    "mode_coordinators",
]
