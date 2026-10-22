"""Shared pytest fixtures for the MMNext test-suite.

The suite runs fully offline: no API keys, no network, no FFmpeg, no mpv,
no Whisper, no GPU. Every test uses the deterministic demo data.
"""

from __future__ import annotations

import os
import pathlib
import sys

import pytest

# The repository root must be importable when the tests are run from a
# checkout that was never pip-installed.
ROOT = pathlib.Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

# Qt must run headless in CI and in the sandbox.
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ.setdefault("QT_LOGGING_RULES", "*.debug=false")

# The exact-dubbing suite must stay offline and deterministic.  ``edge_tts``
# may be installed in the project venv, but a test that reached the real Edge
# TTS network service would make the mixed audio lengths vary and would depend
# on an external site.  The real path is proven by an opt-in test that opts
# back in explicitly.
os.environ["MMNEXT_EXACT_DUB_OFFLINE_TTS"] = "1"


@pytest.fixture(scope="session")
def repo_root() -> pathlib.Path:
    """The repository root."""
    return ROOT


#: Holds the process-wide QApplication alive for the whole session.
#:
#: ``QApplication.instance()`` is only a weak reference in PySide6, so a
#: function-scoped fixture would let the application be garbage collected
#: between tests.  That aborts the interpreter during teardown, so the
#: reference is kept here, exactly like pytest-qt does internally.
_QAPP = None


@pytest.fixture(scope="session")
def qapp():
    """A single QApplication for the whole session."""
    global _QAPP
    from mmnext.bootstrap import create_application

    if _QAPP is None:
        _QAPP = create_application([])
    yield _QAPP


@pytest.fixture()
def context(qapp):
    """A fresh AppContext with the demo project loaded."""
    from mmnext.ui.app_context import AppContext

    ctx = AppContext()
    ctx.load_demo_project()
    yield ctx
    ctx.jobs.clear()
