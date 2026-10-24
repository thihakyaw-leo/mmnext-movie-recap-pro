"""Job persistence facade.

The UI talks to this object, not to ``infrastructure`` directly. It owns the
job repository, exposes stable public methods for the paths and checks that
the transcript reopen path needs, and can create the real transcript adapter
without the UI importing an infrastructure module.
"""

from __future__ import annotations

import math
from pathlib import Path
from typing import Optional

from ..domain.enums import JobState
from ..domain.fingerprint import (
    FINGERPRINT_SCHEMA_VERSION,
    is_canonical_fingerprint,
    is_source_available,
)
from ..domain.models import (
    Job,
    JobProgress,
    ProjectSession,
    TranscriptRow,
    VideoSource,
)
from ..domain.paths import read_json
from ..infrastructure.repository.job_repository import (
    JobRepository,
    compute_fingerprint,
)

__all__ = ["JobService"]


class JobService:
    """Application-facing wrapper around the disk-backed job repository."""

    def __init__(self, jobs_dir: str, repository: Optional[JobRepository] = None) -> None:
        self._jobs_dir = jobs_dir
        self._repository = repository or JobRepository(jobs_dir)

    # -- repository ------------------------------------------------------- #
    @property
    def jobs_dir(self) -> str:
        return str(self._jobs_dir)

    @property
    def repository(self) -> JobRepository:
        return self._repository

    @repository.setter
    def repository(self, repository: JobRepository) -> None:
        self._repository = repository

    def scan(self) -> dict:
        return self._repository.scan()

    def load(self, job_id: str, source_path: str) -> Optional[Job]:
        return self._repository.load(job_id, source_path)

    def save(self, job: Job, source_path: str) -> None:
        self._repository.save(job, source_path)

    def list_completed_real(self, source_path: Optional[str] = None) -> list[Job]:
        return self._repository.list_completed_real(source_path)

    # -- stable public paths ---------------------------------------------- #
    def source_dir(self, source_path: str) -> Path:
        return self._repository.source_dir(source_path)

    def job_dir(self, job_id: str, source_path: str) -> Path:
        return self._repository.job_dir(job_id, source_path)

    def checkpoint_path(self, job_id: str, source_path: str, mode) -> Path:
        return self._repository.checkpoint_path(job_id, source_path, mode)

    # -- fingerprints ----------------------------------------------------- #
    def compute_fingerprint(
        self,
        source_path: str,
        source_type: str,
        mode,
        settings: Optional[dict] = None,
        schema_version: Optional[int] = None,
    ) -> str:
        return compute_fingerprint(
            source_path,
            source_type,
            mode,
            settings=settings,
            schema_version=(
                FINGERPRINT_SCHEMA_VERSION if schema_version is None else schema_version
            ),
        )

    # -- real transcript provider ----------------------------------------- #
    def create_transcript_provider(
        self,
        source_path: str,
        mode,
        is_demo: bool = False,
        whisper_model: Optional[str] = None,
    ):
        from ..infrastructure.transcript_adapter import WhisperTranscriptAdapter

        if whisper_model is None:
            return WhisperTranscriptAdapter(
                self.jobs_dir, source_path, mode=mode, is_demo=is_demo
            )
        return WhisperTranscriptAdapter(
            self.jobs_dir,
            source_path,
            mode=mode,
            whisper_model=whisper_model,
            is_demo=is_demo,
        )

    # -- completed REAL transcript artefacts ------------------------------- #
    def prepare_transcript_from_job(
        self, job_id: str, source_path: str
    ) -> tuple[ProjectSession, list[TranscriptRow], str]:
        job = self._repository.load(job_id, source_path)
        if job is None:
            raise FileNotFoundError(f"Job {job_id} not found for source {source_path}")
        if job.state != JobState.COMPLETE:
            raise ValueError(f"Job {job_id} is not complete (state={job.state.value})")
        if job.is_demo:
            raise ValueError("Demo transcripts cannot be opened as REAL data")
        if job.source is None:
            raise ValueError("Job has no source metadata")

        mode = job.mode
        job_dir = self._repository.job_dir(job_id, source_path)
        stem = Path(source_path).stem
        artifact_dir = job_dir / mode.value / "transcripts"
        artifact_path = artifact_dir / f"{stem}.transcript.json"
        if not artifact_path.exists():
            raise FileNotFoundError(f"Transcript artifact missing at {artifact_path}")

        data = read_json(artifact_path)
        if not isinstance(data, dict) or not data:
            raise ValueError("Transcript artifact is corrupt or unreadable")
        try:
            schema_version = int(data.get("schema_version", 0) or 0)
        except (TypeError, ValueError):
            schema_version = -1
        if schema_version != 1:
            raise ValueError(f"Unsupported transcript schema version {data.get('schema_version')}")
        if bool(data.get("is_demo", True)):
            raise ValueError("Artifact is marked as demo; REAL data required")

        artifact_source = str(data.get("source_path", ""))
        if not artifact_source:
            raise ValueError("Transcript artifact has no source path")
        source_type_val = getattr(job.source.source_type, "value", job.source.source_type)
        if not is_source_available(job.source.location, source_type_val):
            raise ValueError(
                f"Source media is unavailable: {job.source.location}. "
                "Restore the file and reopen, or re-transcribe."
            )
        try:
            same_source = Path(artifact_source).resolve().samefile(
                Path(job.source.location)
            )
        except OSError:
            same_source = False
        if not same_source:
            raise ValueError("Artifact source path does not match job source")

        artifact_fp = str(data.get("fingerprint", "") or "")
        artifact_mode = str(data.get("mode", "") or "")
        fingerprint_settings = data.get("fingerprint_settings")
        fingerprint_source_type = str(data.get("fingerprint_source_type", "") or "")
        try:
            fingerprint_schema_version = int(data.get("fingerprint_schema_version", 0) or 0)
        except (TypeError, ValueError):
            fingerprint_schema_version = 0

        if not is_canonical_fingerprint(artifact_fp):
            raise ValueError("Legacy transcript artifact - re-transcribe required")
        if not isinstance(fingerprint_settings, dict) or not fingerprint_settings:
            raise ValueError("Legacy transcript artifact - re-transcribe required")
        if not fingerprint_source_type or fingerprint_schema_version <= 0:
            raise ValueError("Legacy transcript artifact - re-transcribe required")
        if artifact_mode != mode.value:
            raise ValueError(
                f"Artifact mode {artifact_mode!r} does not match job mode {mode.value!r}"
            )

        try:
            artifact_path.resolve().relative_to(
                self._repository.source_dir(source_path).resolve()
            )
        except ValueError:
            raise ValueError("Transcript artifact is outside the job directory")

        current_fp = compute_fingerprint(
            source_path,
            fingerprint_source_type,
            mode,
            settings=dict(fingerprint_settings),
            schema_version=fingerprint_schema_version,
        )
        if artifact_fp != current_fp:
            raise ValueError("Fingerprint mismatch between artifact and current source")

        rows_raw = data.get("rows", [])
        if not isinstance(rows_raw, list) or not rows_raw:
            raise ValueError("Transcript artifact contains no rows")
        rows: list[TranscriptRow] = []
        seen_ids: set[str] = set()
        try:
            artifact_duration = float(data.get("duration_s", 0.0) or 0.0)
        except (TypeError, ValueError):
            artifact_duration = 0.0
        for r in rows_raw:
            try:
                row_id = str(r["row_id"])
                start = float(r["start"])
                row_duration = float(r["duration"])
                text = str(r["text"])
            except Exception as exc:
                raise ValueError(f"Invalid transcript row: {exc}")
            if not row_id:
                raise ValueError("Empty row_id in transcript artifact")
            if row_id in seen_ids:
                raise ValueError(f"Duplicate row_id {row_id} in transcript artifact")
            seen_ids.add(row_id)
            if not (math.isfinite(start) and start >= 0):
                raise ValueError(f"Invalid start time for row {row_id}: {start}")
            if not (math.isfinite(row_duration) and row_duration > 0):
                raise ValueError(f"Invalid duration for row {row_id}: {row_duration}")
            end = start + row_duration
            if not math.isfinite(end):
                raise ValueError(f"Invalid end time for row {row_id}: {end}")
            if artifact_duration > 0 and end > artifact_duration + 0.01:
                raise ValueError(
                    f"Row {row_id} end {end}s exceeds artifact duration {artifact_duration}s"
                )
            rows.append(TranscriptRow(row_id=row_id, start=start, duration=row_duration, text=text))

        source = VideoSource.local(job.source.location)
        output_folder = str(job_dir.parent.parent)
        session = ProjectSession(
            source=source, output_folder=output_folder, mode=mode, is_demo=False
        )
        return session, rows, str(data.get("language", ""))

    # -- completed transcript metadata -------------------------------------- #
    def persist_completed_transcript(self, provider) -> Job:
        """Persist completed REAL transcript metadata for restart discovery."""
        source_path = provider.source_path
        mode = provider.mode
        source_type = getattr(provider, "fingerprint_source_type", None) or "local_file"
        artifact_path = str(provider.artifact_path)
        fingerprint = (
            getattr(provider, "fingerprint", "")
            or self.compute_fingerprint(source_path, source_type, mode)
        )
        job = Job(
            job_id=provider.job_id,
            title=Path(source_path).name,
            mode=mode,
            state=JobState.COMPLETE,
            is_demo=False,
            source=VideoSource.local(source_path),
            progress=JobProgress(percent=100.0),
            fingerprint=fingerprint,
            output_path=artifact_path,
            artifact_path=artifact_path,
        )
        self._repository.save(job, source_path)
        return job
