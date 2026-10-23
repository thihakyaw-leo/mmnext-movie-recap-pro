"""Narrator translation adapter.

Wraps the legacy Gemini-based translator behind the ``TranslationProvider``
protocol.  The legacy project is read-only, so the module is loaded
defensively; when it cannot be loaded the adapter reports the failure through
its log callback instead of silently pretending to translate.
"""

from __future__ import annotations

from importlib.util import module_from_spec, spec_from_file_location
from pathlib import Path
from types import ModuleType
from typing import Callable, Optional, Sequence

from ...domain.models import NarrationSegment
from ..protocols import TranslationProvider

__all__ = ["LegacyNarratorTranslationAdapter", "DemoTranslationProvider"]

DEFAULT_LEGACY_ROOT = r"J:\recap-en-to-mm-main\recap-en-to-mm-main"
LEGACY_TRANSLATOR_REL = "app/recap_planner.py"


def _load_legacy_module(legacy_root: Optional[str]) -> Optional[ModuleType]:
    """Load the external legacy translator defensively."""
    if not legacy_root:
        return None
    path = Path(legacy_root) / LEGACY_TRANSLATOR_REL
    if not path.is_file():
        return None
    try:
        spec = spec_from_file_location("mmnext_legacy_translator", str(path))
        if spec is None or spec.loader is None:
            return None
        mod = module_from_spec(spec)
        spec.loader.exec_module(mod)
        return mod
    except Exception:
        return None


class LegacyNarratorTranslationAdapter(TranslationProvider):
    """Translate narrator units through the legacy Gemini translator."""

    def __init__(
        self,
        legacy_root: Optional[str] = None,
        log: Optional[Callable[[str], None]] = None,
        api_key: Optional[str] = None,
    ) -> None:
        self.legacy_root = legacy_root
        self._mod = _load_legacy_module(legacy_root)
        self.log = log or (lambda msg: None)
        self._stage = "idle"
        self._api_key = api_key or __import__("os").environ.get("GEMINI_API_KEY") or __import__("os").environ.get("GOOGLE_API_KEY")

    def available(self) -> bool:
        """True when the legacy translator module and credentials are available."""
        return self._mod is not None and bool(self._api_key)

    def stage_progress(self) -> dict:
        return {"stage": self._stage, "percent": 0.0}

    def translate_segments(
        self,
        segments: Sequence[NarrationSegment],
        language_code: Optional[str] = None,
        context: Optional[str] = None,
        glossary: Optional[dict[str, str]] = None,
    ) -> list[str]:
        self._stage = "translate"
        try:
            if self._mod is None:
                self.log("Legacy translator unavailable; no translation produced")
                return ["" for _ in segments]
            texts = [segment.source_text for segment in segments]
            translate = getattr(self._mod, "translate_segments", None)
            if translate is None:
                self.log("Legacy translator exposes no translate_segments(); no translation produced")
                return ["" for _ in segments]
            result = translate(
                texts,
                language_code=language_code,
                context=context or "",
                glossary=glossary or {},
            )
            if not isinstance(result, list) or len(result) != len(texts):
                self.log("Legacy translator returned an unexpected shape; no translation produced")
                return ["" for _ in segments]
            return [str(item) for item in result]
        except Exception as exc:  # noqa: BLE001 - legacy is external/untrusted
            self.log(f"Translation failed: {exc}")
            return ["" for _ in segments]
        finally:
            self._stage = "idle"


class DemoTranslationProvider(TranslationProvider):
    """Deterministic demo translation used by the offline test suite."""

    def __init__(self) -> None:
        self._stage = "idle"

    def available(self) -> bool:
        return True

    def stage_progress(self) -> dict:
        return {"stage": self._stage, "percent": 100.0}

    def translate_segments(
        self,
        segments: Sequence[NarrationSegment],
        language_code: Optional[str] = None,
        context: Optional[str] = None,
        glossary: Optional[dict[str, str]] = None,
    ) -> list[str]:
        # Deterministic Myanmar placeholder that round-trips unchanged.
        return [f"ဘာသာပြန်ချက် {index + 1}" for index in range(len(segments))]
