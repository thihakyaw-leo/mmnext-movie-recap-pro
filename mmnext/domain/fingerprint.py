"""One canonical fingerprint contract for every persisted artefact.

A fingerprint answers a single question: *is the artefact I am about to
reuse still describing the same inputs?*  Historically this repository had
three different answers (the job repository helper, the transcript adapter
method and the download worker method), and they disagreed - a transcript
written by the real adapter could never be re-opened by the job repository.

This module defines the single canonical algorithm.  Every producer (the
transcript adapter, the job repository) and every consumer (the re-open
path, the resume check) must use it, so a value computed while writing an
artefact is byte-identical to the value computed while verifying it.

Rules of the canonical form:

* the source type is normalised, so ``"local"`` and ``"local_file"`` (and
  :class:`~mmnext.domain.enums.SourceType.LOCAL_FILE`) are one identity;
* the source path is normalised once (extended-length prefix removed, path
  made absolute and case-folded) so a forward-slash path and a back-slash
  path for the same file agree;
* a local file contributes its *real* size and nanosecond mtime;
* a missing local file is hashed with an explicit ``absent`` marker and
  never with zero-filled metadata, so an unavailable source can never be
  mistaken for the file it replaced;
* the mode, the fingerprint schema version and the settings that produced
  the artefact all participate, so the same video in a different mode or
  with different transcription settings never shares a fingerprint.

The module is part of the pure domain layer: it imports no Qt, no
application and no infrastructure code.
"""

from __future__ import annotations

import hashlib
import json
import os
from typing import Any, Dict, Mapping, Optional, Tuple

from .enums import AppMode, SourceType

__all__ = [
    "FINGERPRINT_PREFIX",
    "FINGERPRINT_SCHEME",
    "FINGERPRINT_SCHEMA_VERSION",
    "FingerprintError",
    "canonical_fingerprint",
    "is_canonical_fingerprint",
    "is_source_available",
    "require_source_available",
    "normalize_source_path",
    "normalize_source_type",
]

#: Prefix of every canonical fingerprint.  A value without it is a legacy
#: (pre-contract) fingerprint and must be treated as unverifiable.
FINGERPRINT_PREFIX = "fp2:"

#: Scheme marker mixed into the hashed payload.
FINGERPRINT_SCHEME = "mmnext-fingerprint-v2"

#: Version of the *fingerprint input* schema.  Bump it when the hashed
#: payload layout changes so old values can never be compared silently.
FINGERPRINT_SCHEMA_VERSION = 1

_LOCAL_ALIASES = frozenset({"local", "local_file", "localfile", "file"})
_REMOTE_ALIASES = frozenset({"youtube", "yt", "remote", "url"})


class FingerprintError(ValueError):
    """Raised when a fingerprint cannot be computed or verified."""


def normalize_source_type(source_type: Any) -> str:
    """Return the canonical name of ``source_type``.

    Accepts a plain string or a :class:`~mmnext.domain.enums.SourceType`
    member.  ``"local"`` and ``"local_file"`` collapse onto
    ``"local_file"`` so the historic alias cannot produce a second,
    conflicting identity for the same file.
    """
    if source_type is None:
        return ""
    value = getattr(source_type, "value", source_type)
    text = str(value).strip().lower()
    if text in _LOCAL_ALIASES:
        return SourceType.LOCAL_FILE.value
    if text in _REMOTE_ALIASES:
        return SourceType.YOUTUBE.value
    return text


def normalize_source_path(source_path: Any) -> str:
    """Return the canonical absolute form of ``source_path``.

    The Windows extended-length prefix (``\\\\?\\``) is removed, the path is
    made absolute against the current working directory and case-folded, so
    ``"C:/videos/a.mp4"`` and ``"c:\\videos\\a.mp4"`` describe one file.
    """
    text = str(source_path or "").strip()
    if not text:
        return ""
    if text.startswith("\\\\?\\"):
        text = text[4:]
        if text.startswith("UNC\\"):
            text = "\\\\" + text[4:]
    try:
        resolved = os.path.realpath(text)
    except (OSError, ValueError):  # pragma: no cover - defensive
        resolved = os.path.abspath(text)
    return os.path.normcase(os.path.abspath(resolved))


def _file_state(identity: str) -> Tuple[str, str, str]:
    """Return ``(state, size, mtime_ns)`` for a local file.

    ``state`` is ``"present"`` or ``"absent"``.  An absent file never
    reports zero size and zero mtime as if they were real metadata: the
    explicit ``"absent"`` marker is hashed instead, which can never match a
    fingerprint recorded for the file itself.
    """
    if not identity:
        return ("absent", "0", "0")
    try:
        stat = os.stat(identity)
    except OSError:
        return ("absent", "0", "0")
    return ("present", str(int(stat.st_size)), str(int(stat.st_mtime_ns)))


def _settings_payload(settings: Any) -> Dict[str, Any]:
    if settings is None:
        return {}
    if isinstance(settings, dict):
        return settings
    if isinstance(settings, Mapping):
        return dict(settings)
    try:
        return dict(settings)
    except (TypeError, ValueError):
        return {"_settings": str(settings)}


def canonical_fingerprint(
    source_path: str,
    source_type: str,
    mode: AppMode,
    settings: Optional[Dict[str, Any]] = None,
    schema_version: int = FINGERPRINT_SCHEMA_VERSION,
) -> str:
    """Return the canonical fingerprint of one artefact's inputs.

    The same inputs always produce the same value, and the value changes
    whenever the source file, the source type, the mode, the fingerprint
    schema version or the settings change.  The result is prefixed with
    ``"fp2:"`` so legacy values stay recognisable.
    """
    stype = normalize_source_type(source_type)
    identity = normalize_source_path(source_path)
    mode_value = str(getattr(mode, "value", mode) or "")

    if stype == SourceType.LOCAL_FILE.value:
        state, size, mtime_ns = _file_state(identity)
    elif stype == SourceType.YOUTUBE.value:
        state, size, mtime_ns = ("remote", "0", "0")
    else:
        state, size, mtime_ns = ("unknown", "0", "0")

    settings_json = json.dumps(
        _settings_payload(settings),
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        default=str,
    )
    try:
        schema = int(schema_version)
    except (TypeError, ValueError):
        schema = 0

    raw = "|".join(
        (
            FINGERPRINT_SCHEME,
            stype,
            identity,
            state,
            size,
            mtime_ns,
            mode_value,
            str(schema),
            settings_json,
        )
    )
    digest = hashlib.sha1(raw.encode("utf-8")).hexdigest()
    return f"{FINGERPRINT_PREFIX}{digest}"


def is_canonical_fingerprint(value: Any) -> bool:
    """Whether ``value`` was produced by :func:`canonical_fingerprint`."""
    text = str(value or "")
    if not text.startswith(FINGERPRINT_PREFIX):
        return False
    digest = text[len(FINGERPRINT_PREFIX):]
    if len(digest) != 40:
        return False
    return all(char in "0123456789abcdefABCDEF" for char in digest)


def is_source_available(source_path: str, source_type: Any = SourceType.LOCAL_FILE.value) -> bool:
    """Whether the media behind ``source_path`` can still be read."""
    stype = normalize_source_type(source_type)
    if stype != SourceType.LOCAL_FILE.value:
        return True
    identity = normalize_source_path(source_path)
    if not identity:
        return False
    return os.path.isfile(identity)


def require_source_available(
    source_path: str,
    source_type: Any = SourceType.LOCAL_FILE.value,
) -> str:
    """Return the normalised path of ``source_path`` or raise.

    Raises :class:`FingerprintError` when a local source is missing, so a
    caller can offer a clear "the media is gone" message instead of
    comparing fingerprints of two different states of the world.
    """
    if not is_source_available(source_path, source_type):
        raise FingerprintError(f"Source media is unavailable: {source_path}")
    return normalize_source_path(source_path)
