"""Service layer: interfaces implemented by real adapters and by the demo.

Nothing here imports PySide6. Concrete adapters live in
``mmnext.infrastructure``; the deterministic demo implementations live in
``mmnext.services.demo``.
"""

from __future__ import annotations

__all__ = ["protocols"]
