"""Per-mode control panels.

Each mode owns its own panel class. The narrator panel and the exact-dubbing
panel are deliberately separate classes with separate widgets - they never
share a row editor, so a narrator edit can not leak into the exact-dubbing
working set.
"""

from __future__ import annotations

from .common_editing_panel import CommonEditingPanel
from .exact_dubbing_panel import ExactDubbingPanel
from .narrator_panel import NarratorPanel
from .splitter_panel import SplitterPanel

__all__ = [
    "NarratorPanel",
    "ExactDubbingPanel",
    "SplitterPanel",
    "CommonEditingPanel",
]
