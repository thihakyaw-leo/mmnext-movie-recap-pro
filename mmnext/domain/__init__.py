"""Pure domain layer: typed models, enums, events, validators, path rules.

This package must not import PySide6, Qt, or any application/UI module.
"""

from __future__ import annotations

__all__ = [
    "enums",
    "models",
    "events",
    "errors",
    "validation",
    "paths",
    "fingerprint",
    "exact_dubbing",
]
