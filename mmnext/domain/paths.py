"""Canonical job folder layout and safe file-name rules.

Mirrors the legacy layout from ``recap-en-to-mm-main``::

    JOBS_DIR/<safe_name>_<sha1(resolved_path)[:8]>/
        edge_tts_smart_sync/
            tts_parts/
            video_parts/
            work/
            checkpoint.json
            smart_sync_plan_edge_tts.json
            final_edge_tts_smart_sync.mp4
        _planner_worker.json
        _render_worker.json
        run.log
        .stop_requested

The same folder root is reused for every mode so a user can see all the
artefacts of one source video in one place.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
from pathlib import Path
from typing import Any

__all__ = [
    "safe_name",
    "job_dir_name",
    "job_root",
    "ensure_job_tree",
    "stop_request_path",
    "run_log_path",
    "checkpoint_path",
    "final_output_name",
    "atomic_write_text",
    "atomic_write_json",
    "read_json",
    "partial_path_for",
]

_UNSAFE = re.compile(r"[^\w\-. ]+", re.UNICODE)
_WINDOWS_RESERVED = {
    "CON", "PRN", "AUX", "NUL",
    *(f"COM{i}" for i in range(1, 10)),
    *(f"LPT{i}" for i in range(1, 10)),
}

MODE_FOLDER = {
    "common_editing": "common_editing",
    "splitter": "splitter",
    "narrator": "edge_tts_smart_sync",
    "exact_dubbing": "exact_dubbing",
}


def safe_name(name: str) -> str:
    """Return a Windows-safe stem for ``name``.

    Mirrors the legacy behaviour: strip unsafe characters, collapse
    whitespace, and avoid reserved device names.
    """
    cleaned = _UNSAFE.sub("_", (name or "").strip())
    cleaned = re.sub(r"\s+", " ", cleaned).strip(" .")
    if not cleaned:
        cleaned = "job"
    if cleaned.upper() in _WINDOWS_RESERVED:
        cleaned = f"_{cleaned}"
    return cleaned[:80]


def job_dir_name(source_path: str | Path) -> str:
    """``<safe_name>_<sha1(resolved_path)[:8]>`` - the legacy folder name."""
    path = Path(source_path)
    try:
        resolved = str(path.resolve())
    except OSError:  # pragma: no cover - defensive
        resolved = str(path)
    digest = hashlib.sha1(resolved.encode("utf-8")).hexdigest()[:8]
    return f"{safe_name(path.stem)}_{digest}"


def job_root(jobs_dir: str | Path, source_path: str | Path) -> Path:
    """Full path of the job folder for ``source_path``."""
    return Path(jobs_dir) / job_dir_name(source_path)


def mode_dir(jobs_dir: str | Path, source_path: str | Path, mode: str) -> Path:
    """Mode specific sub-folder inside a job folder."""
    return job_root(jobs_dir, source_path) / MODE_FOLDER.get(mode, mode)


def ensure_job_tree(jobs_dir: str | Path, source_path: str | Path, mode: str) -> Path:
    """Create (idempotently) and return the mode directory."""
    target = mode_dir(jobs_dir, source_path, mode)
    for sub in ("tts_parts", "video_parts", "work"):
        (target / sub).mkdir(parents=True, exist_ok=True)
    target.mkdir(parents=True, exist_ok=True)
    return target


def stop_request_path(jobs_dir: str | Path, source_path: str | Path) -> Path:
    """Path of the cooperative stop flag file used by the legacy workers."""
    return job_root(jobs_dir, source_path) / ".stop_requested"


def run_log_path(jobs_dir: str | Path, source_path: str | Path) -> Path:
    return job_root(jobs_dir, source_path) / "run.log"


def checkpoint_path(jobs_dir: str | Path, source_path: str | Path, mode: str) -> Path:
    return mode_dir(jobs_dir, source_path, mode) / "checkpoint.json"


def final_output_name(stem: str, mode: str) -> str:
    """Name of the finished artefact for a mode."""
    return {
        "narrator": f"{stem}_Myanmar.mp4",
        "exact_dubbing": "final_exact_gender_dub.mp4",
        "splitter": f"{stem}_part.mp4",
        "common_editing": f"{stem}_edited.mp4",
    }.get(mode, f"{stem}.mp4")


# --------------------------------------------------------------------------- #
# Atomic writes
# --------------------------------------------------------------------------- #
def atomic_write_text(path: str | Path, text: str, encoding: str = "utf-8") -> Path:
    """Write ``text`` to ``path`` atomically.

    The content is written to a sibling ``*.partial`` file and then renamed
    over the target with :func:`os.replace`, which is atomic on both NTFS and
    POSIX. A reader therefore never observes a half-written file, and a crash
    mid-write leaves the previous version intact.
    """
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    tmp = target.with_name(target.name + ".partial")
    try:
        with open(tmp, "w", encoding=encoding, newline="\n") as handle:
            handle.write(text)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(tmp, target)
    finally:
        if tmp.exists():
            try:
                tmp.unlink()
            except OSError:  # pragma: no cover - best effort cleanup
                pass
    return target


def atomic_write_json(path: str | Path, payload: Any) -> Path:
    """Serialise ``payload`` as UTF-8 JSON and write it atomically.

    ``ensure_ascii`` is disabled so Myanmar text stays readable in the file
    and round-trips byte-for-byte.
    """
    text = json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True)
    return atomic_write_text(path, text + "\n")


def read_json(path: str | Path, default: Any = None) -> Any:
    """Read a JSON document, returning ``default`` when it is missing/invalid."""
    try:
        with open(path, "r", encoding="utf-8") as handle:
            return json.load(handle)
    except (OSError, ValueError):
        return default


def partial_path_for(path: str | Path) -> Path:
    """The ``.partial`` companion of a media artefact.

    Media output is always written to this file first and only renamed to
    ``path`` once the artefact is complete.
    """
    target = Path(path)
    return target.with_name(target.name + ".partial")
