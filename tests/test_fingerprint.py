"""Contract tests for the single canonical fingerprint algorithm.

Every producer and consumer of a persisted artefact must agree on one
algorithm.  These tests pin that agreement so the repository helper, the
transcript adapter and the re-open path can never drift apart again.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from mmnext.domain.enums import AppMode, JobState, SourceType
from mmnext.domain.fingerprint import (
    FINGERPRINT_PREFIX,
    FINGERPRINT_SCHEMA_VERSION,
    FingerprintError,
    canonical_fingerprint,
    is_canonical_fingerprint,
    is_source_available,
    normalize_source_path,
    normalize_source_type,
    require_source_available,
)
from mmnext.domain.models import Job, JobCheckpoint, VideoSource
from mmnext.infrastructure.repository.job_repository import (
    JOB_SCHEMA_VERSION,
    JobRepository,
    compute_fingerprint,
)


# --------------------------------------------------------------------------- #
# The public helper must stay a thin, stable façade over the canonical
# function - the UI and the tests both call it by name.
# --------------------------------------------------------------------------- #
def test_repository_helper_delegates_to_canonical_function():
    source = "C:/videos/a.mp4"
    assert compute_fingerprint(source, "local", AppMode.NARRATOR) == canonical_fingerprint(
        source, "local", AppMode.NARRATOR
    )


def test_repository_helper_keeps_its_keyword_signature():
    source = "C:/videos/a.mp4"
    by_positional = compute_fingerprint(source, "local", AppMode.NARRATOR, {"rate": 1.0}, 1)
    by_keyword = compute_fingerprint(
        source_path=source,
        source_type="local",
        mode=AppMode.NARRATOR,
        settings={"rate": 1.0},
        schema_version=1,
    )
    assert by_positional == by_keyword


def test_canonical_values_carry_the_prefix():
    value = canonical_fingerprint("C:/videos/a.mp4", "local", AppMode.NARRATOR)
    assert value.startswith(FINGERPRINT_PREFIX)
    assert is_canonical_fingerprint(value)


def test_legacy_fingerprint_is_not_canonical():
    import hashlib

    legacy = hashlib.sha1(b"old").hexdigest()
    assert not is_canonical_fingerprint(legacy)
    assert not is_canonical_fingerprint("")
    assert not is_canonical_fingerprint(None)


# --------------------------------------------------------------------------- #
# Determinism
# --------------------------------------------------------------------------- #
def test_same_inputs_produce_the_same_value():
    a = canonical_fingerprint("C:/videos/a.mp4", "local_file", AppMode.NARRATOR)
    b = canonical_fingerprint("C:/videos/a.mp4", "local_file", AppMode.NARRATOR)
    assert a == b


def test_adapter_and_repository_agree(tmp_path):
    source = tmp_path / "movie.mp4"
    source.write_bytes(b"media bytes")
    settings = {"language": "en", "auto_detect": False, "model": "base", "schema": 1}
    from_adapter = canonical_fingerprint(str(source), "local_file", AppMode.NARRATOR, settings=settings)
    from_repository = compute_fingerprint(
        str(source), "local_file", AppMode.NARRATOR, settings=settings
    )
    assert from_adapter == from_repository


# --------------------------------------------------------------------------- #
# Sensitivity: every input that changes the artefact must change the value
# --------------------------------------------------------------------------- #
def test_settings_change_the_value():
    a = canonical_fingerprint("C:/videos/a.mp4", "local", AppMode.NARRATOR, settings={"rate": 1.0})
    b = canonical_fingerprint("C:/videos/a.mp4", "local", AppMode.NARRATOR, settings={"rate": 1.1})
    assert a != b


def test_mode_changes_the_value():
    a = canonical_fingerprint("C:/videos/a.mp4", "local", AppMode.NARRATOR)
    b = canonical_fingerprint("C:/videos/a.mp4", "local", AppMode.EXACT_DUBBING)
    assert a != b


def test_source_path_changes_the_value():
    a = canonical_fingerprint("C:/videos/a.mp4", "local", AppMode.NARRATOR)
    b = canonical_fingerprint("C:/videos/b.mp4", "local", AppMode.NARRATOR)
    assert a != b


def test_schema_version_changes_the_value():
    a = canonical_fingerprint("C:/videos/a.mp4", "local", AppMode.NARRATOR, schema_version=1)
    b = canonical_fingerprint("C:/videos/a.mp4", "local", AppMode.NARRATOR, schema_version=2)
    assert a != b


def test_file_content_change_changes_the_value(tmp_path):
    source = tmp_path / "movie.mp4"
    source.write_bytes(b"one")
    first = canonical_fingerprint(str(source), "local_file", AppMode.NARRATOR)
    source.write_bytes(b"two-different")
    second = canonical_fingerprint(str(source), "local_file", AppMode.NARRATOR)
    assert first != second


# --------------------------------------------------------------------------- #
# Source-type aliases must not create a second identity for the same file
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize(
    "alias",
    ["local", "local_file", "localfile", "file", SourceType.LOCAL_FILE, SourceType.LOCAL_FILE.value],
)
def test_local_aliases_collapse_onto_one_identity(alias):
    assert normalize_source_type(alias) == SourceType.LOCAL_FILE.value
    reference = canonical_fingerprint("C:/videos/a.mp4", "local_file", AppMode.NARRATOR)
    assert canonical_fingerprint("C:/videos/a.mp4", alias, AppMode.NARRATOR) == reference


@pytest.mark.parametrize(
    "alias",
    ["youtube", "yt", "remote", "url", SourceType.YOUTUBE, SourceType.YOUTUBE.value],
)
def test_remote_aliases_collapse_onto_one_identity(alias):
    assert normalize_source_type(alias) == SourceType.YOUTUBE.value
    reference = canonical_fingerprint("https://youtu.be/x", "youtube", AppMode.NARRATOR)
    assert canonical_fingerprint("https://youtu.be/x", alias, AppMode.NARRATOR) == reference


def test_local_and_remote_source_types_differ():
    a = canonical_fingerprint("C:/videos/a.mp4", "local_file", AppMode.NARRATOR)
    b = canonical_fingerprint("C:/videos/a.mp4", "youtube", AppMode.NARRATOR)
    assert a != b


# --------------------------------------------------------------------------- #
# Path normalisation: the same file described two ways is one identity
# --------------------------------------------------------------------------- #
def test_path_normalisation_equates_separator_and_case_variants():
    forward = canonical_fingerprint("C:/videos/a.mp4", "local_file", AppMode.NARRATOR)
    backward = canonical_fingerprint("c:\\videos\\a.mp4", "local_file", AppMode.NARRATOR)
    assert forward == backward


def test_path_normalisation_strips_windows_extended_length_prefix():
    plain = canonical_fingerprint("C:/videos/a.mp4", "local_file", AppMode.NARRATOR)
    extended = canonical_fingerprint("\\\\?\\C:/videos/a.mp4", "local_file", AppMode.NARRATOR)
    assert plain == extended


def test_relative_and_absolute_paths_agree(tmp_path, monkeypatch):
    source = tmp_path / "a.mp4"
    source.write_bytes(b"x")
    monkeypatch.chdir(tmp_path)
    absolute = canonical_fingerprint(str(source), "local_file", AppMode.NARRATOR)
    relative = canonical_fingerprint("a.mp4", "local_file", AppMode.NARRATOR)
    assert absolute == relative


def test_normalize_source_path_is_idempotent():
    once = normalize_source_path("C:/videos/a.mp4")
    assert normalize_source_path(once) == once


# --------------------------------------------------------------------------- #
# A missing source must never look like a real file
# --------------------------------------------------------------------------- #
def test_missing_source_is_hashed_as_absent(tmp_path):
    missing = str(tmp_path / "not-here.mp4")
    assert not is_source_available(missing)
    value = canonical_fingerprint(missing, "local_file", AppMode.NARRATOR)
    assert is_canonical_fingerprint(value)


def test_absent_source_never_matches_a_present_one(tmp_path):
    source = tmp_path / "movie.mp4"
    source.write_bytes(b"media")
    present = canonical_fingerprint(str(source), "local_file", AppMode.NARRATOR)
    absent = canonical_fingerprint(str(tmp_path / "movie.mp4.gone"), "local_file", AppMode.NARRATOR)
    assert present != absent


def test_require_source_available_raises_for_missing_media(tmp_path):
    with pytest.raises(FingerprintError):
        require_source_available(str(tmp_path / "gone.mp4"))
    present = tmp_path / "here.mp4"
    present.write_bytes(b"x")
    assert require_source_available(str(present))


def test_remote_source_is_always_available():
    assert is_source_available("https://youtu.be/x", "youtube")


# --------------------------------------------------------------------------- #
# Persistence round-trips
# --------------------------------------------------------------------------- #
def test_job_fingerprint_round_trips_through_the_repository(tmp_path):
    repo = JobRepository(tmp_path)
    source = str(tmp_path / "movie.mp4")
    Path(source).write_bytes(b"media")
    fingerprint = canonical_fingerprint(source, "local_file", AppMode.NARRATOR)
    job = Job(
        job_id="fp_job",
        title="Fingerprint",
        mode=AppMode.NARRATOR,
        state=JobState.COMPLETE,
        is_demo=False,
        source=VideoSource.local(source),
        fingerprint=fingerprint,
    )
    repo.save(job, source)
    loaded = repo.load("fp_job", source)
    assert loaded is not None
    assert loaded.fingerprint == fingerprint


def test_legacy_metadata_without_fingerprint_loads_with_empty_value(tmp_path):
    repo = JobRepository(tmp_path)
    source = str(tmp_path / "movie.mp4")
    job = Job(job_id="legacy", title="Legacy", mode=AppMode.NARRATOR, source=VideoSource.local(source))
    repo.save(job, source)
    meta_path = repo._metadata_path("legacy", source)
    data = json.loads(meta_path.read_text(encoding="utf-8"))
    data.pop("fingerprint", None)
    data.pop("artifact_path", None)
    meta_path.write_text(json.dumps(data), encoding="utf-8")
    loaded = repo.load("legacy", source)
    assert loaded is not None
    assert loaded.fingerprint == ""


def test_checkpoint_fingerprint_inputs_round_trip(tmp_path):
    repo = JobRepository(tmp_path)
    source = str(tmp_path / "movie.mp4")
    settings = {"language": "en", "auto_detect": False, "model": "base", "schema": 1}
    fingerprint = canonical_fingerprint(source, "local_file", AppMode.NARRATOR, settings=settings)
    checkpoint = JobCheckpoint(
        task_id="t1",
        mode=AppMode.NARRATOR.value,
        fingerprint=fingerprint,
        fingerprint_settings=dict(settings),
        fingerprint_source_type="local_file",
        fingerprint_schema_version=FINGERPRINT_SCHEMA_VERSION,
    )
    repo.save_checkpoint("j1", source, AppMode.NARRATOR, checkpoint)
    data = repo.load_checkpoint("j1", source, AppMode.NARRATOR)
    assert data is not None
    assert data["fingerprint"] == fingerprint
    assert data["fingerprint_settings"] == settings
    assert data["fingerprint_source_type"] == "local_file"
    assert data["fingerprint_schema_version"] == FINGERPRINT_SCHEMA_VERSION


# --------------------------------------------------------------------------- #
# Completed REAL discovery
# --------------------------------------------------------------------------- #
def test_completed_real_jobs_are_discovered_separately(tmp_path):
    repo = JobRepository(tmp_path)
    source = str(tmp_path / "movie.mp4")
    real = Job(
        job_id="real_done",
        title="Real",
        mode=AppMode.NARRATOR,
        state=JobState.COMPLETE,
        is_demo=False,
        source=VideoSource.local(source),
        fingerprint=canonical_fingerprint(source, "local_file", AppMode.NARRATOR),
    )
    demo = Job(
        job_id="demo_done",
        title="Demo",
        mode=AppMode.NARRATOR,
        state=JobState.COMPLETE,
        is_demo=True,
        source=VideoSource.local(source),
    )
    repo.save(real, source)
    repo.save(demo, source)

    scan = repo.scan()
    assert "completed_real" in scan
    real_ids = {job.job_id for job, _ in scan["completed_real"]}
    assert real_ids == {"real_done"}

    listed = repo.list_completed_real()
    assert [job.job_id for job in listed] == ["real_done"]
    assert listed[0].fingerprint == real.fingerprint
    assert listed[0].source is not None


def test_completed_real_discovery_can_be_scoped_to_one_source(tmp_path):
    repo = JobRepository(tmp_path)
    first = str(tmp_path / "first.mp4")
    second = str(tmp_path / "second.mp4")
    for index, path in enumerate((first, second)):
        job = Job(
            job_id=f"job{index}",
            title=f"Job {index}",
            mode=AppMode.NARRATOR,
            state=JobState.COMPLETE,
            is_demo=False,
            source=VideoSource.local(path),
        )
        repo.save(job, path)
    scoped = repo.list_completed_real(source_path=first)
    assert [job.job_id for job in scoped] == ["job0"]


# --------------------------------------------------------------------------- #
# The real adapter must produce a verifiable artefact
# --------------------------------------------------------------------------- #
def test_real_adapter_artifact_carries_verifiable_fingerprint(tmp_path, monkeypatch):
    from types import SimpleNamespace
    from unittest.mock import MagicMock

    import mmnext.infrastructure.transcript_adapter as module
    from mmnext.infrastructure.transcript_adapter import WhisperTranscriptAdapter

    source = tmp_path / "movie.mp4"
    source.write_bytes(b"source media")
    adapter = WhisperTranscriptAdapter(str(tmp_path / "jobs"), str(source))
    monkeypatch.setattr(adapter, "_probe_duration", lambda p: 10.0)
    monkeypatch.setattr(adapter, "_prepare_audio", lambda p, d: (str(tmp_path / "audio.wav"), ""))
    model = MagicMock()
    model.transcribe.return_value = (
        iter([SimpleNamespace(start=1.0, end=3.0, text="hello")]),
        SimpleNamespace(language="en"),
    )
    monkeypatch.setattr(module, "WhisperModel", MagicMock(return_value=model))

    rows, _ = adapter.transcribe(str(source), language="en")
    assert rows

    payload = json.loads(adapter.artifact_path.read_text(encoding="utf-8"))
    assert payload["mode"] == AppMode.NARRATOR.value
    assert payload["fingerprint_source_type"] == "local_file"
    assert payload["fingerprint_schema_version"] == FINGERPRINT_SCHEMA_VERSION
    assert payload["fingerprint_settings"] == {
        "language": "en",
        "auto_detect": False,
        "model": adapter.whisper_model,
        "schema": 1,
    }
    # A consumer can re-derive the value from the artefact alone.
    recomputed = canonical_fingerprint(
        payload["source_path"],
        payload["fingerprint_source_type"],
        AppMode(payload["mode"]),
        settings=payload["fingerprint_settings"],
        schema_version=payload["fingerprint_schema_version"],
    )
    assert recomputed == payload["fingerprint"]
    # ... and the repository agrees with the adapter.
    assert compute_fingerprint(
        payload["source_path"],
        payload["fingerprint_source_type"],
        AppMode(payload["mode"]),
        settings=payload["fingerprint_settings"],
        schema_version=payload["fingerprint_schema_version"],
    ) == payload["fingerprint"]


def test_adapter_checkpoint_fingerprint_equals_artifact_fingerprint(tmp_path, monkeypatch):
    from types import SimpleNamespace
    from unittest.mock import MagicMock

    import mmnext.infrastructure.transcript_adapter as module
    from mmnext.infrastructure.transcript_adapter import WhisperTranscriptAdapter

    source = tmp_path / "movie.mp4"
    source.write_bytes(b"source media")
    adapter = WhisperTranscriptAdapter(str(tmp_path / "jobs"), str(source))
    monkeypatch.setattr(adapter, "_probe_duration", lambda p: 10.0)
    monkeypatch.setattr(adapter, "_prepare_audio", lambda p, d: (str(tmp_path / "audio.wav"), ""))
    model = MagicMock()
    model.transcribe.return_value = (
        iter([SimpleNamespace(start=1.0, end=3.0, text="hello")]),
        SimpleNamespace(language="en"),
    )
    monkeypatch.setattr(module, "WhisperModel", MagicMock(return_value=model))

    adapter.transcribe(str(source), language="en")
    payload = json.loads(adapter.artifact_path.read_text(encoding="utf-8"))
    assert adapter.fingerprint == payload["fingerprint"]
    checkpoint = adapter.repo.load_checkpoint(source.stem, str(source), adapter.mode)
    assert checkpoint["fingerprint"] == payload["fingerprint"]
    assert checkpoint["fingerprint_settings"] == payload["fingerprint_settings"]
    assert checkpoint["fingerprint_source_type"] == payload["fingerprint_source_type"]


def test_job_schema_version_is_unchanged():
    assert JOB_SCHEMA_VERSION == 1
