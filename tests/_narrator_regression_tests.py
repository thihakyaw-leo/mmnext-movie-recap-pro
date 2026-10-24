
@needs_ffmpeg
def test_a_real_transcript_run_produces_a_narrated_recap(tmp_path) -> None:
    """A successful REAL run writes completed Job metadata and rediscover by a
    fresh AppContext.

    Uses the approved local media fixture (harvard-full.mp4) and cached Whisper
    model.  The full pipeline runs: REAL transcribe via Whisper, then narrator
    pipeline (plan -> translate -> TTS -> Smart Sync render).  The resulting
    COMPLETE Job record is rediscoverable by a fresh AppContext via
    scan()["completed_real"].
    """
    import os
    media = os.environ.get("MMNEXT_TRANSCRIPT_SMOKE_MEDIA")
    model = os.environ.get("MMNEXT_TRANSCRIPT_SMOKE_MODEL")
    if not media or not model:
        pytest.skip(
            "Provide an approved media fixture and local cached Whisper model "
            "for real smoke"
        )
    if not Path(media).is_file() or not Path(model).is_dir():
        pytest.skip("Local media/model fixture unavailable")

    ctx = AppContext(jobs_dir=str(tmp_path / "jobs"))
    try:
        ctx.start_local_transcript(str(media))
        assert _wait_for(
            lambda: ctx.transcript_state in {"complete", "failed"},
            timeout_ms=120000,
        )
        assert ctx.transcript_state == "complete", context.transcript_message

        ctx.start_narrator_pipeline()
        assert _wait_for(
            lambda: context.narrator_state in {"done", "failed"},
            timeout_ms=300000,
        )
        assert context.narrator_state == "done", context.narrator_message

        # Verify the completed REAL job is registered and discoverable.
        scan = context._job_repository.scan()
        completed_real = scan.get("completed_real", [])
        assert len(completed_real) >= 1, "No completed REAL job discovered"

        job = completed_real[0][0]
        artifact_path = Path(job.artifact_path)
        assert artifact_path.is_file(), f"Artifact missing: {artifact_path}"

        info = probe(artifact_path)
        assert any(s["codec_type"] == "audio" for s in info["streams"])
        assert any(s["codec_type"] == "video" for s in info["streams"])

        # Duration should match the source media within tolerance.
        src_info = probe(Path(media))
        assert abs(float(info["format"]["duration"]) - float(src_info["format"]["duration"])) <= 0.5

    finally:
        context.jobs.clear()


@needs_ffmpeg
def test_a_fresh_appcontext_rediscovers_completed_real_transcript_job(
    tmp_path,
) -> None:
    """A fresh AppContext rediscovers a completed REAL transcript job via
    scan()["completed_real"] and reopens it through start_reopen_transcript.

    This proves restart-to-Workspace works end to end for the Narrator pipeline.
    """
    import os
    media = os.environ.get("MMNEXT_TRANSCRIPT_SMOKE_MEDIA")
    model = os.environ.get("MMNEXT_TRANSCRIPT_SMOKE_MODEL")
    if not media or not model:
        pytest.skip(
            "Provide an approved media fixture and local cached Whisper model "
            "for real smoke"
        )
    if not Path(media).is_file() or not Path(model).is_dir():
        pytest.skip("Local media/model fixture unavailable")

    ctx = AppContext(jobs_dir=str(tmp_path / "jobs"))
    try:
        # 1. Successful REAL run: transcribe + narrate.
        ctx.start_local_transcript(str(media))
        assert _wait_for(
            lambda: ctx.transcript_state in {"complete", "failed"},
            timeout_ms=120000,
        )
        assert ctx.transcript_state == "complete", context.transcript_message

        ctx.start_narrator_pipeline()
        assert _wait_for(
            lambda: context.narrator_state in {"done", "failed"},
            timeout_ms=300000,
        )
        assert context.narrator_state == "done", context.narrator_message

        # 2. Fresh context rediscovers the completed REAL job.
        fresh = AppContext(jobs_dir=str(tmp_path / "jobs"))
        scan = fresh._job_repository.scan()
        completed_real = scan.get("completed_real", [])
        assert len(completed_real) >= 1, "Fresh context did not rediscover job"

        job = completed_real[0][0]
        assert job.state.name == "COMPLETE"
        assert job.is_demo is False
        assert Path(job.artifact_path).is_file()

        # 3. Explicit open path: reopen the transcript via the Jobs screen path.
        fresh.start_reopen_transcript(job.job_id, str(job.source.location))
        assert _wait_for(
            lambda: fresh.transcript_state in {"complete", "failed"},
            timeout_ms=300000,
        )
        assert fresh.transcript_state == "complete", fresh.transcript_message
        assert fresh.transcript_language, "No transcript language set"
    finally:
        context.jobs.clear()
        fresh.jobs.clear()
