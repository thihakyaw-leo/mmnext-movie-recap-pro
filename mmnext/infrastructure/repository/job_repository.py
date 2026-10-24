"""Disk-backed job repository with versioned schema and recovery.

The repository never touches the current working directory. All paths are
derived from the configured ``jobs_dir`` together with source identity,
mode and job id, so jobs are isolated per source and per mode.

The schema version is explicit and every write is atomic. Corrupt JSON
files are detected and reported without crashing the application.
"""

from __future__ import annotations

import hashlib
from dataclasses import asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Tuple

from mmnext.domain.enums import AppMode, JobState, TaskState, SourceType, Stage
from mmnext.domain.fingerprint import (
    FingerprintError,
    canonical_fingerprint,
    normalize_source_path,
)
from mmnext.domain.models import Job, JobProgress, JobCheckpoint, VideoSource
from mmnext.domain.paths import atomic_write_json, read_json, safe_name
from mmnext.domain.models import CHECKPOINT_SCHEMA_VERSION

__all__ = [
    "JOB_SCHEMA_VERSION",
    "JobRepository",
    "FingerprintError",
    "ResumeCheckResult",
    "canonical_fingerprint",
    "normalize_source_path",
]

JOB_SCHEMA_VERSION = 1

# ``FingerprintError`` is re-exported from the domain layer so there is
# exactly one exception type for the canonical fingerprint contract.  The
# domain never imports infrastructure, so this alias cannot create a cycle.


class ResumeCheckResult:
    """Structured result for a resume eligibility check."""
    def __init__(self, allowed: bool, reasons: Optional[List[str]] = None) -> None:
        self.allowed = allowed
        self.reasons = reasons or []

    def __bool__(self) -> bool:
        return self.allowed

    def __repr__(self) -> str:
        return f"ResumeCheckResult(allowed={self.allowed}, reasons={self.reasons})"


def _iso_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")

def compute_fingerprint(
    source_path: str,
    source_type: str,
    mode: AppMode,
    settings: Optional[Dict[str, Any]] = None,
    schema_version: int = JOB_SCHEMA_VERSION,
) -> str:
    """Return the canonical fingerprint of one artefact's inputs.

    The public name and keyword signature are kept for callers that already
    use this helper, but the algorithm now lives in exactly one place:
    :func:`mmnext.domain.fingerprint.canonical_fingerprint`.  The historic
    implementation hashed a *different* payload than the transcript adapter
    and only stat'ed the source when the source type was the literal string
    ``"local"`` - never for the real enum value ``"local_file"``.  Both
    defects are gone; a repository-computed value and an adapter-computed
    value for the same inputs are now byte-identical.
    """
    return canonical_fingerprint(
        source_path,
        source_type,
        mode,
        settings=settings,
        schema_version=schema_version,
    )


class JobRepository:
    """Versioned, atomic, job-scoped persistence."""

    def __init__(self, jobs_dir: str | Path) -> None:
        self.jobs_dir = Path(jobs_dir)
        self.jobs_dir.mkdir(parents=True, exist_ok=True)

    def _source_hash(self, source_path: str) -> str:
        try:
            resolved = Path(source_path).resolve()
        except Exception:
            resolved = Path(source_path)
        return hashlib.sha1(str(resolved).encode("utf-8")).hexdigest()[:8]

    def _source_dir(self, source_path: str) -> Path:
        stem = safe_name(Path(source_path).stem)
        h = self._source_hash(source_path)
        return self.jobs_dir / f"{stem}_{h}"

    def source_dir(self, source_path: str) -> Path:
        """Public, stable path of the directory that owns ``source_path``."""
        return self._source_dir(source_path)

    def _job_dir(self, job_id: str, source_path: str) -> Path:
        return self._source_dir(source_path) / "jobs" / job_id

    def job_dir(self, job_id: str, source_path: str) -> Path:
        """Public, stable path of one job directory."""
        return self._job_dir(job_id, source_path)

    def _metadata_path(self, job_id: str, source_path: str) -> Path:
        return self._job_dir(job_id, source_path) / "metadata.json"

    def checkpoint_path(self, job_id: str, source_path: str, mode: AppMode) -> Path:
        """Public, stable path of a mode-scoped job checkpoint."""
        return self._checkpoint_path(job_id, source_path, mode)

    def _checkpoint_path(self, job_id: str, source_path: str, mode: AppMode) -> Path:
        ckpt_dir = self._job_dir(job_id, source_path) / "checkpoints" / mode.value
        ckpt_dir.mkdir(parents=True, exist_ok=True)
        return ckpt_dir / "checkpoint.json"

    def _job_to_dict(self, job: Job) -> Dict[str, Any]:
        stage_val = job.progress.stage.value if isinstance(job.progress.stage, Stage) else str(job.progress.stage)
        data = {
            "schema_version": JOB_SCHEMA_VERSION,
            "job_id": job.job_id,
            "title": job.title,
            "mode": job.mode.value,
            "state": job.state.value,
            "task_state": job.task_state.value,
            "is_demo": bool(job.is_demo),
            "created_at": job.created_at or _iso_now(),
            "updated_at": _iso_now(),
            "output_path": job.output_path,
            "error_message": job.error_message,
            "progress": {
                "percent": job.progress.percent,
                "stage": stage_val,
                "message": job.progress.message,
                "bytes_done": job.progress.bytes_done,
                "bytes_total": job.progress.bytes_total,
                "speed_bps": job.progress.speed_bps,
                "eta_s": job.progress.eta_s,
            },
            "source": {
                "type": job.source.source_type.value if job.source else None,
                "location": job.source.location if job.source else "",
                "display_name": job.source.display_name if job.source else "",
                "duration_s": job.source.duration_s if job.source else 0.0,
            } if job.source else None,
            "fingerprint": getattr(job, "fingerprint", ""),
            "artifact_path": getattr(job, "artifact_path", ""),
        }
        return data

    def _dict_to_job(self, data: Dict[str, Any]) -> Job:
        from mmnext.domain.models import VideoSource
        from mmnext.domain.enums import SourceType, Stage
        src_data = data.get("source")
        src = None
        if src_data:
            st = src_data.get("type")
            try:
                st_enum = SourceType(st) if st else SourceType.LOCAL_FILE
            except ValueError:
                st_enum = SourceType.LOCAL_FILE
            src = VideoSource(
                source_type=st_enum,
                location=str(src_data.get("location", "")),
                display_name=str(src_data.get("display_name", "")),
                duration_s=float(src_data.get("duration_s", 0.0) or 0.0),
            )
        prog = data.get("progress", {})
        stage_val = prog.get("stage", Stage.IDLE.value)
        try:
            stage_enum = Stage(stage_val)
        except Exception:
            stage_enum = Stage.IDLE
        progress = JobProgress(
            percent=float(prog.get("percent", 0.0) or 0.0),
            stage=stage_enum,
            message=str(prog.get("message", "") or ""),
            bytes_done=int(prog.get("bytes_done", 0) or 0),
            bytes_total=int(prog.get("bytes_total", 0) or 0),
            speed_bps=float(prog.get("speed_bps", 0.0) or 0.0),
            eta_s=float(prog.get("eta_s", 0.0) or 0.0),
        )
        try:
            mode_enum = AppMode(data.get("mode", AppMode.COMMON_EDITING.value))
        except Exception:
            mode_enum = AppMode.COMMON_EDITING
        try:
            state_enum = JobState(data.get("state", JobState.NEW.value))
        except Exception:
            state_enum = JobState.NEW
        try:
            task_state_enum = TaskState(data.get("task_state", TaskState.QUEUED.value))
        except Exception:
            task_state_enum = TaskState.QUEUED

        job = Job(
            job_id=str(data.get("job_id", "")),
            title=str(data.get("title", "")),
            mode=mode_enum,
            state=state_enum,
            task_state=task_state_enum,
            progress=progress,
            created_at=str(data.get("created_at", "")),
            updated_at=str(data.get("updated_at", "")),
            source=src,
            output_path=str(data.get("output_path", "") or ""),
            error_message=str(data.get("error_message", "") or ""),
            is_demo=bool(data.get("is_demo", True)),
            fingerprint=str(data.get("fingerprint", "") or ""),
            artifact_path=str(data.get("artifact_path", "") or ""),
        )
        return job

    def create(self, job: Job, source_path: str) -> Job:
        path = self._metadata_path(job.job_id, source_path)
        if path.exists():
            raise FileExistsError(f"Job {job.job_id} already exists")
        self.save(job, source_path)
        return job

    def save(self, job: Job, source_path: str) -> None:
        job_dir = self._job_dir(job.job_id, source_path)
        job_dir.mkdir(parents=True, exist_ok=True)
        atomic_write_json(self._metadata_path(job.job_id, source_path), self._job_to_dict(job))

    def load(self, job_id: str, source_path: str) -> Optional[Job]:
        path = self._metadata_path(job_id, source_path)
        if not path.exists():
            return None
        data = read_json(path)
        if not data:
            return None
        sv = int(data.get("schema_version", 0) or 0)
        if sv != JOB_SCHEMA_VERSION:
            return None
        try:
            return self._dict_to_job(data)
        except Exception:
            return None

    def list_jobs(self, source_path: Optional[str] = None) -> List[Job]:
        jobs: List[Job] = []
        if source_path:
            base = self._source_dir(source_path) / "jobs"
            if not base.exists():
                return jobs
            for job_dir in base.iterdir():
                if not job_dir.is_dir():
                    continue
                meta = job_dir / "metadata.json"
                if not meta.exists():
                    continue
                data = read_json(meta)
                if not data:
                    continue
                try:
                    job = self._dict_to_job(data)
                    jobs.append(job)
                except Exception:
                    continue
        else:
            if not self.jobs_dir.exists():
                return jobs
            for src_dir in self.jobs_dir.iterdir():
                if not src_dir.is_dir():
                    continue
                jobs_dir = src_dir / "jobs"
                if not jobs_dir.exists():
                    continue
                for job_dir in jobs_dir.iterdir():
                    if not job_dir.is_dir():
                        continue
                    meta = job_dir / "metadata.json"
                    if not meta.exists():
                        continue
                    data = read_json(meta)
                    if not data:
                        continue
                    try:
                        job = self._dict_to_job(data)
                        jobs.append(job)
                    except Exception:
                        continue
        return jobs

    def list_incomplete(self, source_path: Optional[str] = None) -> List[Job]:
        all_jobs = self.list_jobs(source_path)
        return [j for j in all_jobs if j.state not in (JobState.COMPLETE, JobState.CANCELLED)]

    def update_state(self, job_id: str, source_path: str, new_state: JobState, progress: Optional[JobProgress] = None) -> Optional[Job]:
        job = self.load(job_id, source_path)
        if not job:
            return None
        job.state = new_state
        if progress:
            job.progress = progress
        self.save(job, source_path)
        return job

    def mark_complete(self, job_id: str, source_path: str) -> Optional[Job]:
        return self.update_state(job_id, source_path, JobState.COMPLETE)

    def mark_failed(self, job_id: str, source_path: str, message: str = "") -> Optional[Job]:
        job = self.load(job_id, source_path)
        if not job:
            return None
        job.state = JobState.FAILED
        job.error_message = message
        self.save(job, source_path)
        return job

    def save_checkpoint(self, job_id: str, source_path: str, mode: AppMode, checkpoint: Any) -> None:
        path = self._checkpoint_path(job_id, source_path, mode)
        if hasattr(checkpoint, "to_dict"):
            data = checkpoint.to_dict()
        else:
            data = dict(checkpoint)
        atomic_write_json(path, data)

    def load_checkpoint(self, job_id: str, source_path: str, mode: AppMode) -> Optional[dict]:
        path = self._checkpoint_path(job_id, source_path, mode)
        if not path.exists():
            return None
        data = read_json(path)
        if not data:
            try:
                path.unlink()
            except Exception:
                pass
            return None
        sv = int(data.get("schema_version", 0) or 0)
        if sv != CHECKPOINT_SCHEMA_VERSION:
            return None
        return data

    def scan(self) -> Dict[str, List[Any]]:
        recoverable: List[Tuple[Job, str]] = []
        completed: List[Tuple[Job, str]] = []
        completed_real: List[Tuple[Job, str]] = []
        corrupt: List[Path] = []
        if not self.jobs_dir.exists():
            return {"recoverable": [], "completed": [], "completed_real": [], "corrupt": []}
        for src_dir in self.jobs_dir.iterdir():
            if not src_dir.is_dir():
                continue
            jobs_dir = src_dir / "jobs"
            if not jobs_dir.exists():
                continue
            for job_dir in jobs_dir.iterdir():
                if not job_dir.is_dir():
                    continue
                meta_path = job_dir / "metadata.json"
                if not meta_path.exists():
                    continue
                try:
                    data = read_json(meta_path)
                    if not data:
                        corrupt.append(meta_path)
                        continue
                    sv = int(data.get("schema_version", 0) or 0)
                    if sv != JOB_SCHEMA_VERSION:
                        corrupt.append(meta_path)
                        continue
                    job = self._dict_to_job(data)
                    if job.state == JobState.COMPLETE:
                        completed.append((job, str(src_dir)))
                        if not job.is_demo:
                            completed_real.append((job, str(src_dir)))
                    elif job.state not in (JobState.CANCELLED,):
                        recoverable.append((job, str(src_dir)))
                except Exception:
                    corrupt.append(meta_path)
                    continue
        return {
            "recoverable": recoverable,
            "completed": completed,
            "completed_real": completed_real,
            "corrupt": corrupt,
        }

    def completed_jobs(self) -> List[Job]:
        """Return list of completed REAL jobs (excluding demo and cancelled)."""
        all_jobs = self.list_jobs()
        return [j for j in all_jobs if j.state == JobState.COMPLETE and not j.is_demo]

    def list_completed_real(self, source_path: Optional[str] = None) -> List[Job]:
        """Return completed, non-demo jobs as a flat list of :class:`Job`.

        Completed REAL jobs are discovered from disk so the Jobs screen can
        offer "open transcript" for work that was finished in an earlier
        session.  Nothing is resumed or opened automatically - discovery
        only.  When ``source_path`` is given only jobs belonging to that
        source are returned.
        """
        jobs = self.completed_jobs()
        if source_path:
            try:
                wanted = normalize_source_path(source_path)
            except Exception:
                wanted = str(source_path)
            filtered: List[Job] = []
            for job in jobs:
                if not job.source:
                    continue
                try:
                    have = normalize_source_path(job.source.location)
                except Exception:
                    have = str(job.source.location)
                if have == wanted:
                    filtered.append(job)
            return filtered
        return jobs

    def cleanup_orphans(self) -> list[str]:
        """Remove stale ``.partial`` files and return their paths."""
        removed: list[str] = []
        for path in self.jobs_dir.rglob("*.partial"):
            try:
                path.unlink()
                removed.append(str(path))
            except OSError:
                continue
        return removed

    def can_resume_job(self, job_id: str, source_path: str, mode: AppMode) -> ResumeCheckResult:
        job = self.load(job_id, source_path)
        if not job:
            return ResumeCheckResult(False, ["Job not found"])
        if job.state == JobState.COMPLETE:
            return ResumeCheckResult(False, ["Job already complete"])
        if job.mode != mode:
            return ResumeCheckResult(False, ["Mode mismatch"])
        ckpt_data = self.load_checkpoint(job_id, source_path, mode)
        if not ckpt_data:
            return ResumeCheckResult(False, ["No checkpoint found"])
        try:
            ckpt = JobCheckpoint.from_dict(ckpt_data)
        except Exception:
            return ResumeCheckResult(False, ["Corrupt checkpoint"])
        if not ckpt.resume_supported:
            return ResumeCheckResult(False, ["Resume not supported"])
        if ckpt.state not in (TaskState.PAUSED, TaskState.STOPPED):
            return ResumeCheckResult(False, [f"Checkpoint state not resumable: {ckpt.state.value}"])
        current_fp = compute_fingerprint(
            source_path,
            ckpt.fingerprint_source_type or (job.source.source_type.value if job.source else ""),
            mode,
            settings=ckpt.fingerprint_settings or None,
            schema_version=ckpt.fingerprint_schema_version or JOB_SCHEMA_VERSION,
        )
        if ckpt.fingerprint and ckpt.fingerprint != current_fp:
            return ResumeCheckResult(False, ["Fingerprint mismatch"])
        if ckpt.partial_path and not Path(ckpt.partial_path).exists():
            return ResumeCheckResult(False, ["Partial artifact missing"])
        return ResumeCheckResult(True, [])
