"""Architecture gates.

These tests enforce the layering rules from ``Agent.md``:

* ``ui -> application -> services -> domain``,
* the domain and application layers never import PySide6,
* nothing in the project imports Tkinter,
* the UI layer never imports a concrete infrastructure service directly
  (it goes through the application layer).
"""

from __future__ import annotations

import ast
import pathlib

import pytest

ROOT = pathlib.Path(__file__).resolve().parents[1]

_PACKAGE = ROOT / "mmnext"
_LAYER_DIRS = {
    "domain": _PACKAGE / "domain",
    "application": _PACKAGE / "application",
    "services": _PACKAGE / "services",
    "infrastructure": _PACKAGE / "infrastructure",
    "ui": _PACKAGE / "ui",
}


def _python_files(root: pathlib.Path) -> list[pathlib.Path]:
    return sorted(
        path
        for path in root.rglob("*.py")
        if "__pycache__" not in path.parts
    )


def _imported_modules(path: pathlib.Path) -> set[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    names: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                names.add(alias.name)
        elif isinstance(node, ast.ImportFrom):
            if node.level:  # relative import
                names.add("." * node.level + (node.module or ""))
            elif node.module:
                names.add(node.module)
    return names


def _is_qt_import(name: str) -> bool:
    return name.startswith("PySide6") or name.startswith("PyQt")


def _is_tk_import(name: str) -> bool:
    return name == "tkinter" or name.startswith("tkinter.")


@pytest.mark.parametrize("layer", ["domain", "application"])
def test_low_layers_do_not_import_qt(layer: str) -> None:
    """Domain and application must stay Qt-free so they are testable headless."""
    offenders: list[str] = []
    for path in _python_files(_LAYER_DIRS[layer]):
        for name in _imported_modules(path):
            if _is_qt_import(name):
                offenders.append(f"{path.relative_to(ROOT)} imports {name}")
    assert not offenders, "Qt leaked into a low layer:\n" + "\n".join(offenders)


def test_no_tkinter_anywhere() -> None:
    """The legacy Tkinter UI must not be dragged into the new project."""
    offenders: list[str] = []
    for path in _python_files(_PACKAGE):
        for name in _imported_modules(path):
            if _is_tk_import(name):
                offenders.append(f"{path.relative_to(ROOT)} imports {name}")
    assert not offenders, "Tkinter found:\n" + "\n".join(offenders)


def test_ui_layer_does_not_import_legacy_pipelines() -> None:
    """The UI must not reach into the legacy Tkinter projects."""
    offenders: list[str] = []
    for path in _python_files(_LAYER_DIRS["ui"]):
        text = path.read_text(encoding="utf-8")
        for marker in ("recap-en-to-mm", "movie-recap", "pipeline_master_local"):
            if marker in text:
                offenders.append(f"{path.relative_to(ROOT)} mentions {marker}")
    assert not offenders, "Legacy reference found:\n" + "\n".join(offenders)


def _is_infrastructure_import(name: str) -> bool:
    """Detect relative or absolute imports into the infrastructure layer."""
    return (
        name.startswith(".infrastructure")
        or name.startswith("..infrastructure")
        or name.startswith("...infrastructure")
        or name.startswith("mmnext.infrastructure")
    )


def test_ui_layer_does_not_import_infrastructure() -> None:
    """The UI must depend on the application layer, not infrastructure directly."""
    offenders: list[str] = []
    for path in _python_files(_LAYER_DIRS["ui"]):
        for name in _imported_modules(path):
            if _is_infrastructure_import(name):
                offenders.append(f"{path.relative_to(ROOT)} imports {name}")
    assert not offenders, (
        "UI imports infrastructure directly (use an application-layer facade):\n"
        + "\n".join(offenders)
    )


def test_ui_layer_does_not_call_private_repository_path_helpers() -> None:
    """Private repository path helpers must never be reached for from the UI."""
    offenders: list[str] = []
    for path in _python_files(_LAYER_DIRS["ui"]):
        text = path.read_text(encoding="utf-8")
        for marker in ("_source_dir(", "_job_dir(", "_checkpoint_path("):
            if marker in text:
                offenders.append(f"{path.relative_to(ROOT)} uses {marker}")
    assert not offenders, (
        "UI calls private repository path helpers (use public methods):\n"
        + "\n".join(offenders)
    )


def test_domain_does_not_import_application() -> None:
    """The dependency arrow only points downwards."""
    offenders: list[str] = []
    for path in _python_files(_LAYER_DIRS["domain"]):
        for name in _imported_modules(path):
            if name.startswith("..application") or name.startswith("mmnext.application"):
                offenders.append(f"{path.relative_to(ROOT)} imports {name}")
    assert not offenders, "Domain depends on the application layer:\n" + "\n".join(offenders)


def test_application_does_not_import_ui() -> None:
    """The application layer must not know about widgets."""
    offenders: list[str] = []
    for path in _python_files(_LAYER_DIRS["application"]):
        for name in _imported_modules(path):
            if name.startswith("..ui") or name.startswith("mmnext.ui"):
                offenders.append(f"{path.relative_to(ROOT)} imports {name}")
    assert not offenders, "Application depends on the UI layer:\n" + "\n".join(offenders)


def test_every_package_has_an_init() -> None:
    """Every sub-package is importable."""
    missing: list[str] = []
    for path in _PACKAGE.rglob("*"):
        if path.is_dir() and "__pycache__" not in path.parts:
            if not (path / "__init__.py").exists():
                missing.append(str(path.relative_to(ROOT)))
    assert not missing, f"Missing __init__.py in: {missing}"


def test_no_external_api_clients_in_milestone_one() -> None:
    """Milestone 1 must not depend on a network SDK."""
    banned = ("openai", "anthropic", "google.generativeai", "requests", "httpx", "urllib3")
    offenders: list[str] = []
    for path in _python_files(_PACKAGE):
        for name in _imported_modules(path):
            root = name.split(".")[0]
            if root in banned:
                offenders.append(f"{path.relative_to(ROOT)} imports {name}")
    assert not offenders, "External API client found:\n" + "\n".join(offenders)


# --------------------------------------------------------------------------- #
# Qt teardown safety
# --------------------------------------------------------------------------- #
#
# A lambda (or ``functools.partial``) that captures ``self`` and is connected
# to a *child* widget's signal creates a reference cycle:
#
#     parent -> child widget -> connection -> closure -> parent
#
# PySide6 breaks that cycle automatically for bound methods but not for
# Python closures, so the widget survives until interpreter shutdown and Qt
# then aborts the process (0xC0000409 / 0xC0000005) with no Python frame.
#
# The rule is therefore: connect a bound method, and carry any extra
# payload on the sender (``setProperty``) instead of closing over it.


def _connects_a_self_capturing_closure(path: pathlib.Path) -> list[str]:
    """Return offending ``.connect(...)`` call sites in *path*."""
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    offenders: list[str] = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        func = node.func
        if not isinstance(func, ast.Attribute) or func.attr != "connect":
            continue
        if not node.args:
            continue
        argument = node.args[0]
        is_closure = isinstance(argument, ast.Lambda)
        if isinstance(argument, ast.Call):
            # functools.partial(self._slot, ...) is equally unsafe.
            callee = argument.func
            name = getattr(callee, "id", None) or getattr(callee, "attr", None)
            is_closure = name == "partial"
        if not is_closure:
            continue
        # A closure that never mentions ``self`` cannot form the cycle.
        mentions_self = any(
            isinstance(inner, ast.Name) and inner.id == "self"
            for inner in ast.walk(argument)
        )
        if mentions_self:
            offenders.append(f"{path.relative_to(ROOT)}:{node.lineno}")
    return offenders


def test_ui_layer_never_connects_a_self_capturing_closure() -> None:
    """Signal connections must use bound methods, not ``self`` closures."""
    offenders: list[str] = []
    for path in _python_files(_LAYER_DIRS["ui"]):
        offenders.extend(_connects_a_self_capturing_closure(path))
    assert not offenders, (
        "Self-capturing closure connected to a signal (creates a teardown "
        "reference cycle):\n" + "\n".join(offenders)
    )


def test_ui_layer_never_uses_functools_partial_for_slots() -> None:
    """``functools.partial`` holds the same cycle risk as a lambda."""
    offenders: list[str] = []
    for path in _python_files(_LAYER_DIRS["ui"]):
        text = path.read_text(encoding="utf-8")
        if "from functools import partial" in text or "functools.partial" in text:
            offenders.append(f"{path.relative_to(ROOT)} uses functools.partial")
    assert not offenders, (
        "functools.partial used as a slot (creates a teardown reference "
        "cycle):\n" + "\n".join(offenders)
    )
