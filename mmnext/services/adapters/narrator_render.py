"""Smart Sync narrator renderer adapter.

Wraps the legacy Smart Sync renderer behind the ``SmartSyncRenderer``
protocol.  The legacy project is read-only, so its module is loaded
defensively and the render is reported as failed when it is unavailable -
the adapter never reports a successful render it did not perform.
"""

from __future__ import annotations

from importlib.util import module_from_spec, spec_from_file_location
from pathlib import Path
from types import ModuleType
from typing import Callable, Optional, Sequence

from ...domain.models import NarrationSegment
from ..protocols import SmartSyncRenderer

__all__ = ["LegacySmartSyncRenderer", "DemoSmartSyncRenderer"]

DEFAULT_LEGACY_ROOT = r"J:\recap-en-to-mm-main\recap-en-to-mm-main"
LEGACY_RENDER_REL = "app/render_worker.py"


def _load_legacy_module(legacy_root: Optional[str]) -> Optional[ModuleType]:
    """Load the external legacy renderer defensively."""
    if not legacy_root:
        return None
    path = Path(legacy_root) / LEGACY_RENDER_REL
    if not path.is_file():
        return None
    try:
        spec = spec_from_file_location("mmnext_legacy_render", str(path))
        if spec is None or spec.loader is None:
            return None
        mod = module_from_spec(spec)
        spec.loader.exec_module(mod)
        return mod
    except Exception:
        return None


class LegacySmartSyncRenderer(SmartSyncRenderer):
    """Render the Smart Sync recap through the legacy renderer."""

    def __init__(
        self,
        legacy_root: Optional[str] = None,
        log: Optional[Callable[[str], None]] = None,
    ) -> None:
        self.legacy_root = legacy_root
        self._mod = _load_legacy_module(legacy_root)
        self.log = log or (lambda msg: None)
        self._stage = "idle"

    def available(self) -> bool:
        """True when the legacy renderer module and an entry point are available."""
        if self._mod is None:
            return False
        return (
            getattr(self._mod, "render_recap", None) is not None
            or getattr(self._mod, "render", None) is not None
        )

    def stage_progress(self) -> dict:
        return {"stage": self._stage, "percent": 0.0}

    def render(
        self,
        video_path: str,
        segments: Sequence[NarrationSegment],
        output_path: str,
        settings: dict,
    ) -> bool:
        self._stage = "render"
        try:
            if self._mod is None:
                self.log("Legacy Smart Sync renderer unavailable; no video was rendered")
                return False
            render = getattr(self._mod, "render_recap", None) or getattr(
                self._mod, "render", None
            )
            if render is None:
                self.log("Legacy renderer exposes no render entry point; no video was rendered")
                return False
            render(video_path, list(segments), output_path, dict(settings or {}))
            return True
        except Exception as exc:  # noqa: BLE001 - legacy is external/untrusted
            self.log(f"Smart Sync render failed: {exc}")
            return False
        finally:
            self._stage = "idle"


class DemoSmartSyncRenderer(SmartSyncRenderer):
    """Deterministic demo renderer used by the offline test suite."""

    def available(self) -> bool:
        return True

    def stage_progress(self) -> dict:
        return {"stage": "idle", "percent": 100.0}

    def render(
        self,
        video_path: str,
        segments: Sequence[NarrationSegment],
        output_path: str,
        settings: dict,
    ) -> bool:
        if not output_path:
            return False
        Path(output_path).parent.mkdir(parents=True, exist_ok=True)
        Path(output_path).write_bytes(b"demo")
        return True
