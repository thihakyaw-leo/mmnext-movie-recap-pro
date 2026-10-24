"""MMNext Movie Recap Pro.

Layering contract (enforced by ``tests/test_architecture_gates.py``)::

    ui -> application -> services -> domain
    infrastructure implements services.protocols and is injected by bootstrap

``domain`` and ``application`` must never import PySide6.
``mmnext`` must never import Tkinter.
"""

from __future__ import annotations

__all__ = ["__version__"]

__version__ = "0.1.0"
