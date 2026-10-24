"""UI layer.

Everything in this package may import PySide6. Nothing below
:mod:`mmnext.ui` may import PySide6 - the dependency arrow only points one
way (``ui -> application -> services -> domain``).
"""

from __future__ import annotations

__all__ = ["app_context"]
