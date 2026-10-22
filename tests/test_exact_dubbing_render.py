"""Exact Dubbing TTS / render / cache and final output validation.

These tests exercise the *real* chain: a real PCM WAV is synthesised, fitted
with FFmpeg, mixed on an exact timeline, muxed with a real source video and
validated with FFprobe.  Nothing here needs a network: the speech synthesiser
is the deterministic offline one, and every other step is the production
code path.

The legacy contract is preserved: the source rows are never re-ordered,
merged, retimed or edited.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import wave
from pathlib import Path

import pytest

from mmnext.application.exact_dubbing_service import ExactDubbingService
from mmnext.domain.enums import Gender
from mmnext.domain.exact_dubbing import (
    EXACT_DUB_VOICES,
    atempo_chain,
    cache_signature,
    parse_translated_gender,
    speech_window,
    validate_against_source,
    voice_for_gender,
)
from mmnext.domain.models import ExactDubbingRow
from mmnext.services.adapters.exact_dubbing_tts import LocalWaveTtsAdapter

BURMESE_A = "မြန်မာလို ရှင်းပြပါ"
BURMESE_B = "ဒီနေ့ ငါ တရားထိုင်ရာက ထွက်လာပြီး နောက်ဆုံးတော့ ကျင့်ကြံမှုအဆင့်သစ်ကို တက်လှမ်းနိုင်ခဲ့ပြီ။"
BURMESE_C = "ကျင့်ကြံမှုအဆင့်သစ်ကို တက်လှမ်းနိုင်ခဲ့တဲ့အတွက် စီနီယာကြီးကို ကျွန်မ ဂုဏ်ပြုပါတယ်။"

needs_ffmpeg = pytest.mark.skipif(
    not (shutil.which("ffmpeg") and shutil.which("ffprobe")),
    reason="FFmpeg/FFprobe are required for the exact-dubbing render",
)


def make_rows() -> list[ExactDubbingRow]:
    return [
        ExactDubbingRow(
            row_id="s0",
            start=0.0,
            duration=1.5,
            original="Hello there.",
            burmese=BURMESE_A,
            gender=Gender.MALE,
        ),
        ExactDubbingRow(
            row_id="s1",
            start=1.5,
            duration=1.5,
            original="How are you?",
            burmese=BURMESE_B,
            gender=Gender.FEMALE,
        ),
    ]


def make_video(path: Path, seconds: float = 4.0) -> Path:
    """Create a small real video with a silent stereo audio track."""
    subprocess.run(
        [
            "ffmpeg", "-v", "error", "-y",
            "-f", "lavfi", "-i", "color=c=black:s=320x180:r=15",
            "-f", "lavfi", "-i", "anullsrc=r=44100:cl=stereo",
            "-t", f"{seconds}",
            "-c:v", "libx264", "-pix_fmt", "yuv420p",
            "-c:a", "aac",
            str(path),
        ],
        check=True,
    )
    return path


def write_translation(path: Path, rows: list[ExactDubbingRow]) -> Path:
    payload = [
        {
            "id": index,
            "row_id": row.row_id,
            "start": row.start,
            "duration": row.duration,
            "original": row.original,
            "burmese": row.burmese,
            "gender": row.gender.value,
        }
        for index, row in enumerate(rows)
    ]
    path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    return path


def probe(path: Path) -> dict:
    completed = subprocess.run(
        ["ffprobe", "-v", "error", "-show_format", "-show_streams",
         "-of", "json", str(path)],
        capture_output=True, text=True, encoding="utf-8", errors="replace", check=True,
    )
    return json.loads(completed.stdout)


def extract_audio(video: Path, wav: Path) -> Path:
    """Extract the audio track of ``video`` as a mono 44100 Hz WAV."""
    subprocess.run(
        ["ffmpeg", "-v", "error", "-y", "-i", str(video),
         "-ac", "1", "-ar", "44100", "-c:a", "pcm_s16le", str(wav)],
        check=True,
    )
    return wav


def first_sound_sample(wav: Path) -> int:
    """The index of the first non-silent sample in ``wav``."""
    with wave.open(str(wav), "rb") as handle:
        raw = handle.readframes(handle.getnframes())
    samples = memoryview(raw).cast("h")
    for index, value in enumerate(samples):
        if abs(value) > 16:
            return index
    return -1


# --------------------------------------------------------------------------- #
# Domain contract
# --------------------------------------------------------------------------- #


def test_translated_gender_schema_is_accepted() -> None:
    rows = parse_translated_gender(
        [
            {
                "id": 0,
                "start": 0.0,
                "duration": 2.0,
                "original": "Hello",
                "burmese": BURMESE_A,
                "gender": "male",
            }
        ]
    )
    assert len(rows) == 1
    assert rows[0].voice == EXACT_DUB_VOICES["male"]


@pytest.mark.parametrize(
    "payload, message",
    [
        ({}, "JSON array"),
        ([], "no rows"),
        ([{"id": 0}], "missing key"),
        ([{"id": 0, "start": 0.0, "duration": float("nan"), "original": "x",
           "burmese": BURMESE_A, "gender": "male"}], "finite number"),
        ([{"id": 0, "start": 0.0, "duration": 1.0, "original": "x",
           "burmese": "   ", "gender": "male"}], "missing"),
        ([{"id": 0, "start": 0.0, "duration": 1.0, "original": "x",
           "burmese": "still English", "gender": "male"}], "Myanmar Unicode"),
        ([{"id": 0, "start": 0.0, "duration": 1.0, "original": "x",
           "burmese": BURMESE_A, "gender": "MALE"}], "gender must be"),
    ],
)
def test_translated_gender_rejects_broken_rows(payload, message) -> None:
    with pytest.raises(ValueError, match=message):
        parse_translated_gender(payload)


def test_source_rows_are_immutable() -> None:
    source = make_rows()
    payload = [
        {"id": index, "start": row.start, "duration": row.duration,
         "original": row.original, "burmese": row.burmese,
         "gender": row.gender.value}
        for index, row in enumerate(source)
    ]
    rows = parse_translated_gender(payload)
    validate_against_source(rows, source)

    drifted = [dict(payload[0], start=0.5), payload[1]]
    with pytest.raises(ValueError, match="changed start"):
        validate_against_source(parse_translated_gender(drifted), source)

    renamed = [dict(payload[0], original="changed"), payload[1]]
    with pytest.raises(ValueError, match="original mismatch"):
        validate_against_source(parse_translated_gender(renamed), source)

    with pytest.raises(ValueError, match="all 2 segments"):
        validate_against_source(parse_translated_gender(payload[:1]), source)


def test_speech_window_matches_the_legacy_rule() -> None:
    # A row may not overlap the next row.
    assert speech_window(0.0, 4.0, 3.0, 12.0) == pytest.approx(3.0)
    # It may expand into 80 % of the silent gap.
    assert speech_window(0.0, 2.0, 4.0, 12.0) == pytest.approx(3.6)
    # The last row is clamped to the end of the media.
    assert speech_window(10.0, 5.0, None, 12.0) == pytest.approx(2.0)


def test_atempo_chain_splits_faster_ratios() -> None:
    assert "atempo=2" in atempo_chain(5.0)
    assert atempo_chain(1.0).count("atempo") == 1
    with pytest.raises(ValueError):
        atempo_chain(0.0)


def test_voice_mapping_falls_back_for_unknown() -> None:
    assert voice_for_gender("male") == "my-MM-ThihaNeural"
    assert voice_for_gender("female") == "my-MM-NilarNeural"
    assert voice_for_gender("unknown") == voice_for_gender("female")
    # The mapping has a single source of truth: the Gender enum.
    assert EXACT_DUB_VOICES["male"] == Gender.MALE.voice


def test_cache_signature_is_content_addressed() -> None:
    first = cache_signature("my-MM-NilarNeural", BURMESE_A)
    assert first == cache_signature("my-MM-NilarNeural", BURMESE_A)
    assert first != cache_signature("my-MM-ThihaNeural", BURMESE_A)
    assert first != cache_signature("my-MM-NilarNeural", BURMESE_B)


def test_translation_file_with_a_byte_order_mark_is_accepted(tmp_path) -> None:
    """The legacy reader accepted a BOM; a BOM must not look like a crash."""
    rows = make_rows()
    payload = json.dumps(
        [
            {"id": index, "row_id": row.row_id, "start": row.start,
             "duration": row.duration, "original": row.original,
             "burmese": row.burmese, "gender": row.gender.value}
            for index, row in enumerate(rows)
        ],
        ensure_ascii=False,
    )
    path = tmp_path / "translated_gender.json"
    path.write_text(payload, encoding="utf-8-sig")

    service = ExactDubbingService(str(tmp_path / "jobs"))
    parsed = service.load_translated_gender(str(path))
    assert len(parsed) == 2


def test_a_missing_translation_file_is_reported_as_missing(tmp_path) -> None:
    service = ExactDubbingService(str(tmp_path / "jobs"))
    with pytest.raises(FileNotFoundError):
        service.load_translated_gender(str(tmp_path / "nope.json"))


def test_a_malformed_translation_file_is_reported_as_unreadable(tmp_path) -> None:
    path = tmp_path / "translated_gender.json"
    path.write_text("{not json", encoding="utf-8")
    service = ExactDubbingService(str(tmp_path / "jobs"))
    with pytest.raises(ValueError, match="not valid JSON"):
        service.load_translated_gender(str(path))


# --------------------------------------------------------------------------- #
# TTS adapter
# --------------------------------------------------------------------------- #


def test_local_synthesizer_writes_real_audio(tmp_path) -> None:
    adapter = LocalWaveTtsAdapter(cache_dir=str(tmp_path))
    out = tmp_path / "seg.wav"
    result = adapter.synthesize_segment(BURMESE_C, voice="my-MM-NilarNeural",
                                        out_path=str(out))
    assert result == str(out)
    assert out.is_file() and out.stat().st_size > 0

    with wave.open(str(out), "rb") as handle:
        assert handle.getnchannels() == 1
        assert handle.getframerate() == 44100
        assert handle.getsampwidth() == 2
        assert handle.getnframes() / handle.getframerate() > 0.5


def test_local_synthesizer_reuses_the_cache(tmp_path) -> None:
    adapter = LocalWaveTtsAdapter(cache_dir=str(tmp_path))
    out = tmp_path / "seg.wav"
    adapter.synthesize_segment(BURMESE_A, out_path=str(out))
    stamp = out.with_suffix(out.suffix + ".sha256")
    assert stamp.is_file()
    first = out.stat().st_mtime_ns

    adapter.synthesize_segment(BURMESE_A, out_path=str(out))
    assert out.stat().st_mtime_ns == first

    # A different text must invalidate the cached segment.
    adapter.synthesize_segment(BURMESE_B, out_path=str(out))
    assert out.stat().st_mtime_ns != first


# --------------------------------------------------------------------------- #
# Real render
# --------------------------------------------------------------------------- #


@needs_ffmpeg
def test_render_from_translated_gender_produces_a_valid_dub(tmp_path) -> None:
    video = make_video(tmp_path / "source.mp4", seconds=4.0)
    rows = make_rows()
    translation = write_translation(tmp_path / "translated_gender.json", rows)
    output = tmp_path / "final_exact_gender_dub.mp4"

    service = ExactDubbingService(str(tmp_path / "jobs"))
    result = service.render_from_translated_gender(
        str(translation),
        rows,
        str(video),
        4.0,
        str(output),
        settings={"tts_cache_dir": str(tmp_path / "jobs" / "tts")},
    )
    assert result.ok, result.message
    assert output.is_file() and output.stat().st_size > 0

    info = probe(output)
    duration = float(info["format"]["duration"])
    assert abs(duration - 4.0) <= 0.1
    assert any(s["codec_type"] == "audio" for s in info["streams"])
    assert any(s["codec_type"] == "video" for s in info["streams"])

    report = json.loads(
        (output.with_name(output.stem + ".render_report.json")).read_text(encoding="utf-8")
    )
    assert report["source_duration"] == pytest.approx(4.0)
    assert report["output"] == str(output)
    assert Path(report["output"]).exists()
    assert [segment["id"] for segment in report["segments"]] == ["s0", "s1"]
    assert report["segments"][0]["voice"] == "my-MM-ThihaNeural"
    assert report["segments"][1]["voice"] == "my-MM-NilarNeural"


@needs_ffmpeg
def test_render_does_not_touch_the_source_media_or_the_rows(tmp_path) -> None:
    """The source file stays byte-identical and the rows keep their identity."""
    video = make_video(tmp_path / "source.mp4", seconds=4.0)
    rows = make_rows()
    before_bytes = video.read_bytes()
    before = [(r.row_id, r.start, r.duration, r.original) for r in rows]
    translation = write_translation(tmp_path / "translated_gender.json", rows)
    output = tmp_path / "final.mp4"

    service = ExactDubbingService(str(tmp_path / "jobs"))
    result = service.render_from_translated_gender(
        str(translation), rows, str(video), 4.0, str(output),
        settings={"tts_cache_dir": str(tmp_path / "jobs" / "tts")},
    )
    assert result.ok, result.message
    assert [(r.row_id, r.start, r.duration, r.original) for r in rows] == before
    assert video.read_bytes() == before_bytes


@needs_ffmpeg
def test_speech_is_placed_at_the_row_start(tmp_path) -> None:
    """The mix must place the speech exactly at the locked row start."""
    rows = [
        ExactDubbingRow(row_id="s0", start=1.0, duration=1.0,
                        original="Hello there.", burmese=BURMESE_A,
                        gender=Gender.MALE),
    ]
    video = make_video(tmp_path / "source.mp4", seconds=3.0)
    translation = write_translation(tmp_path / "translated_gender.json", rows)
    output = tmp_path / "final.mp4"

    service = ExactDubbingService(str(tmp_path / "jobs"))
    result = service.render_from_translated_gender(
        str(translation), rows, str(video), 3.0, str(output),
        settings={"tts_cache_dir": str(tmp_path / "jobs" / "tts")},
    )
    assert result.ok, result.message

    wav = extract_audio(output, tmp_path / "mix.wav")
    first = first_sound_sample(wav)
    assert first > 0, "the row starts at 1.0s, so the track must start silent"
    assert abs(first - 1.0 * 44100) <= 4410  # within 100 ms


@needs_ffmpeg
def test_the_media_duration_wins_over_a_wrong_caller_duration(tmp_path) -> None:
    """A stale duration must not silently shorten the output."""
    video = make_video(tmp_path / "source.mp4", seconds=4.0)
    rows = make_rows()
    translation = write_translation(tmp_path / "translated_gender.json", rows)
    output = tmp_path / "final.mp4"

    service = ExactDubbingService(str(tmp_path / "jobs"))
    result = service.render_from_translated_gender(
        str(translation), rows, str(video), 1.0, str(output),
        settings={"tts_cache_dir": str(tmp_path / "jobs" / "tts"), "total_duration": 1.0},
    )
    assert result.ok, result.message
    duration = float(probe(output)["format"]["duration"])
    assert abs(duration - 4.0) <= 0.1, "the output must follow the media, not the caller"


@needs_ffmpeg
def test_render_reuses_cached_speech(tmp_path) -> None:
    video = make_video(tmp_path / "source.mp4", seconds=4.0)
    rows = make_rows()
    translation = write_translation(tmp_path / "translated_gender.json", rows)
    service = ExactDubbingService(str(tmp_path / "jobs"))
    settings = {"tts_cache_dir": str(tmp_path / "jobs" / "tts")}

    first = service.render_from_translated_gender(
        str(translation), rows, str(video), 4.0, str(tmp_path / "a.mp4"),
        settings=settings,
    )
    assert first.ok, first.message
    cache = list((tmp_path / "jobs" / "tts").glob("*.audio"))
    assert cache, "the synthesiser must leave cached audio behind"
    stamps = {path.stat().st_mtime_ns for path in cache}

    second = service.render_from_translated_gender(
        str(translation), rows, str(video), 4.0, str(tmp_path / "b.mp4"),
        settings=settings,
    )
    assert second.ok, second.message
    assert {path.stat().st_mtime_ns for path in cache} == stamps


@needs_ffmpeg
def test_render_cleans_up_its_work_files(tmp_path) -> None:
    """The mix scratch file and the fitted clips must not pile up."""
    video = make_video(tmp_path / "source.mp4", seconds=4.0)
    rows = make_rows()
    translation = write_translation(tmp_path / "translated_gender.json", rows)
    output = tmp_path / "final.mp4"

    service = ExactDubbingService(str(tmp_path / "jobs"))
    result = service.render_from_translated_gender(
        str(translation), rows, str(video), 4.0, str(output),
        settings={"tts_cache_dir": str(tmp_path / "jobs" / "tts")},
    )
    assert result.ok, result.message
    leftovers = [
        path for path in (tmp_path / "jobs").rglob("*")
        if path.is_file() and (path.suffix == ".tmp" or path.name == "dubbed_audio.wav")
    ]
    assert leftovers == [], f"work files were left behind: {leftovers}"
    assert list((tmp_path / "jobs").rglob("fitted")) == []


@needs_ffmpeg
def test_render_refuses_a_drifted_translation(tmp_path) -> None:
    video = make_video(tmp_path / "source.mp4", seconds=4.0)
    rows = make_rows()
    payload = [
        {"id": 0, "start": 0.9, "duration": 1.5, "original": rows[0].original,
         "burmese": BURMESE_A, "gender": "male"},
        {"id": 1, "start": 1.5, "duration": 1.5, "original": rows[1].original,
         "burmese": BURMESE_B, "gender": "female"},
    ]
    translation = tmp_path / "translated_gender.json"
    translation.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
    output = tmp_path / "final.mp4"

    service = ExactDubbingService(str(tmp_path / "jobs"))
    with pytest.raises(ValueError, match="changed start"):
        service.render_from_translated_gender(
            str(translation), rows, str(video), 4.0, str(output),
            settings={"tts_cache_dir": str(tmp_path / "jobs" / "tts")},
        )
    assert not output.exists()


@needs_ffmpeg
def test_a_failed_render_reports_the_reason_and_leaves_nothing_behind(tmp_path) -> None:
    """A REAL failure keeps its reason and never leaves a success artefact."""
    rows = make_rows()
    translation = write_translation(tmp_path / "translated_gender.json", rows)
    output = tmp_path / "final.mp4"

    service = ExactDubbingService(str(tmp_path / "jobs"))
    result = service.render_from_translated_gender(
        str(translation), rows, str(tmp_path / "missing.mp4"), 4.0, str(output),
        settings={"tts_cache_dir": str(tmp_path / "jobs" / "tts")},
    )
    assert not result.ok
    assert "missing" in result.message.lower(), result.message
    assert result.message != "Render failed", "the generic message hides the reason"
    assert not output.exists()
    assert not output.with_name(output.stem + ".render_report.json").exists()


@needs_ffmpeg
def test_a_row_id_cannot_escape_the_job_folder(tmp_path) -> None:
    """A row id from an artefact must never become a path."""
    rows = [
        ExactDubbingRow(row_id="../../escape", start=0.0, duration=1.0,
                        original="Hello there.", burmese=BURMESE_A,
                        gender=Gender.MALE),
    ]
    video = make_video(tmp_path / "source.mp4", seconds=2.0)
    translation = write_translation(tmp_path / "translated_gender.json", rows)
    output = tmp_path / "final.mp4"

    service = ExactDubbingService(str(tmp_path / "jobs"))
    result = service.render_from_translated_gender(
        str(translation), rows, str(video), 2.0, str(output),
        settings={"tts_cache_dir": str(tmp_path / "jobs" / "tts")},
    )
    assert result.ok, result.message
    assert not (tmp_path / "escape.wav").exists()
    assert not (tmp_path.parent / "escape.wav").exists()


# --------------------------------------------------------------------------- #
# Export -> validate -> render round trip
# --------------------------------------------------------------------------- #


@needs_ffmpeg
def test_the_ui_render_goes_through_the_exported_translation(tmp_path, qtbot) -> None:
    """The product path must consume ``translated_gender.json`` and label itself."""
    from PySide6.QtTest import QTest

    from mmnext.domain.enums import AppMode
    from mmnext.domain.models import ProjectSession, TranscriptRow, VideoSource
    from mmnext.ui.app_context import AppContext

    context = AppContext(jobs_dir=str(tmp_path / "jobs"))
    try:
        video = make_video(tmp_path / "source.mp4", seconds=4.0)
        context.project.load(
            ProjectSession(
                source=VideoSource.local(str(video)),
                output_folder=str(tmp_path),
                mode=AppMode.EXACT_DUBBING,
                is_demo=False,
            )
        )
        context.project.apply_transcript(
            [
                TranscriptRow("s0", 0.0, 1.5, "Hello there."),
                TranscriptRow("s1", 1.5, 1.5, "How are you?"),
            ]
        )
        rows = context.prepare_exact_dubbing()
        for index, row in enumerate(rows):
            context.project.update_exact_row(
                row.row_id,
                burmese=BURMESE_A if index == 0 else BURMESE_B,
                gender=Gender.MALE if index == 0 else Gender.FEMALE,
            )

        context.start_exact_dubbing_render(
            video_path=str(video),
            output_path=str(tmp_path / "final.mp4"),
        )
        # The exported translation file is the contract the render consumes.
        exported = tmp_path / "jobs" / "exact_dubbing" / "translated_gender.json"
        assert exported.is_file()
        payload = json.loads(exported.read_text(encoding="utf-8"))
        assert [entry["id"] for entry in payload] == [0, 1]

        # The run is labelled honestly: DEMO while the speech is simulated.
        service = ExactDubbingService(str(tmp_path / "jobs"))
        expected = "REAL" if service.tts_available() else "DEMO"
        assert context.exact_render_state == "running"
        assert context.exact_render_message.startswith(expected)

        waited = 0
        while context.exact_render_state not in {"done", "failed"} and waited < 180000:
            QTest.qWait(50)
            waited += 50
        assert context.exact_render_state == "done", context.exact_render_message
        # The result is delivered before the thread's own ``finished`` signal,
        # so the worker may still be tearing down when the state flips.  Wait
        # for it separately instead of racing it.
        waited = 0
        while context.exact_render_running and waited < 30000:
            QTest.qWait(50)
            waited += 50
        assert not context.exact_render_running, "the render worker did not finish"
        assert (tmp_path / "final.mp4").is_file()
        report = tmp_path / "final.render_report.json"
        assert report.is_file()
        payload = json.loads(report.read_text(encoding="utf-8"))
        assert payload["output"] == str(tmp_path / "final.mp4")
        assert payload["is_demo"] is True
    finally:
        if context.exact_render_running:
            context.stop_exact_dubbing_render()
            waited = 0
            while context.exact_render_running and waited < 60000:
                QTest.qWait(50)
                waited += 50
        context.jobs.clear()


@needs_ffmpeg
def test_exported_translation_file_round_trips_into_a_render(tmp_path, qtbot) -> None:
    """The file the UI exports must be the file the renderer accepts."""
    from mmnext.domain.enums import AppMode
    from mmnext.domain.models import ProjectSession, TranscriptRow, VideoSource
    from mmnext.ui.app_context import AppContext

    context = AppContext(jobs_dir=str(tmp_path / "jobs"))
    try:
        video = make_video(tmp_path / "source.mp4", seconds=4.0)
        context.project.load(
            ProjectSession(
                source=VideoSource.local(str(video)),
                output_folder=str(tmp_path),
                mode=AppMode.EXACT_DUBBING,
                is_demo=False,
            )
        )
        context.project.apply_transcript(
            [
                TranscriptRow("s0", 0.0, 1.5, "Hello there."),
                TranscriptRow("s1", 1.5, 1.5, "How are you?"),
            ]
        )
        rows = context.prepare_exact_dubbing()
        for index, row in enumerate(rows):
            context.project.update_exact_row(
                row.row_id,
                burmese=BURMESE_A if index == 0 else BURMESE_B,
                gender=Gender.MALE if index == 0 else Gender.FEMALE,
            )

        translation_path = context.export_exact_dubbing(
            str(tmp_path / "translated_gender.json")
        )
        payload = json.loads(Path(translation_path).read_text(encoding="utf-8"))
        # The legacy contract uses the positional index as ``id``.
        assert [entry["id"] for entry in payload] == [0, 1]
        assert payload[0]["row_id"] == "s0"
        assert payload[0]["original"] == "Hello there."
        assert payload[0]["gender"] == "male"

        source_rows = context.project.session.exact_rows
        service = ExactDubbingService(str(tmp_path / "jobs"))
        validated = service.validate_translation(translation_path, source_rows)
        assert len(validated) == 2
        assert validated[0].voice == "my-MM-ThihaNeural"
        assert validated[1].voice == "my-MM-NilarNeural"

        output = tmp_path / "final.mp4"
        result = service.render_from_translated_gender(
            translation_path,
            source_rows,
            str(video),
            4.0,
            str(output),
            settings={"tts_cache_dir": str(tmp_path / "jobs" / "tts")},
        )
        assert result.ok, result.message
        assert output.is_file()
    finally:
        context.jobs.clear()


# --------------------------------------------------------------------------- #
# Uncovered paths found by the review cycle
# --------------------------------------------------------------------------- #


@needs_ffmpeg
def test_speed_fit_needs_more_than_1_35x_warns_but_still_renders(tmp_path) -> None:
    """A stretch past 1.35x is a warning, never a cap and never a failure."""
    rows = [make_rows()[0]]
    # The offline synthesiser produces a fixed length for this text, so make
    # the locked window very short to force a large fit ratio.
    rows[0].duration = 0.4
    video = make_video(tmp_path / "source.mp4", seconds=2.0)
    translation = write_translation(tmp_path / "translated_gender.json", rows)
    output = tmp_path / "final.mp4"

    service = ExactDubbingService(str(tmp_path / "jobs"))
    result = service.render_from_translated_gender(
        str(translation), rows, str(video), 2.0, str(output),
        settings={"tts_cache_dir": str(tmp_path / "jobs" / "tts")},
    )
    assert result.ok, result.message
    assert any("1.35" in warning or "x the source" in warning for warning in result.warnings), result.warnings
    assert output.is_file()


@needs_ffmpeg
def test_the_window_expands_into_the_gap_before_the_next_row(tmp_path) -> None:
    """A row may use 80% of the following silence; never past the next row."""
    rows = [
        ExactDubbingRow(row_id="s0", start=0.0, duration=1.0,
                        original="Hello there.", burmese=BURMESE_A,
                        gender=Gender.MALE),
        ExactDubbingRow(row_id="s1", start=3.0, duration=1.0,
                        original="How are you?", burmese=BURMESE_B,
                        gender=Gender.FEMALE),
    ]
    # The window for s0 must be min(1.0 + 0.8 * 2.0, 3.0 - 0.0) = 2.6s.
    video = make_video(tmp_path / "source.mp4", seconds=4.0)
    translation = write_translation(tmp_path / "translated_gender.json", rows)
    output = tmp_path / "final.mp4"

    service = ExactDubbingService(str(tmp_path / "jobs"))
    result = service.render_from_translated_gender(
        str(translation), rows, str(video), 4.0, str(output),
        settings={"tts_cache_dir": str(tmp_path / "jobs" / "tts")},
    )
    assert result.ok, result.message
    report = json.loads(
        (output.with_name(output.stem + ".render_report.json")).read_text(encoding="utf-8")
    )
    windows = {segment["id"]: segment["window"] for segment in report["segments"]}
    assert windows["s0"] == pytest.approx(2.6)
    assert windows["s1"] == pytest.approx(1.0)
    # The fitted speech must not run past the window of the next row.
    assert 0.0 <= windows["s0"] <= 3.0


@needs_ffmpeg
def test_a_long_speech_is_sped_up_and_trimmed_to_its_window(tmp_path) -> None:
    """The atempo fit must keep the speech inside the locked window."""
    rows = [make_rows()[1]]
    rows[0].duration = 1.0
    video = make_video(tmp_path / "source.mp4", seconds=3.0)
    translation = write_translation(tmp_path / "translated_gender.json", rows)
    output = tmp_path / "final.mp4"

    service = ExactDubbingService(str(tmp_path / "jobs"))
    result = service.render_from_translated_gender(
        str(translation), rows, str(video), 3.0, str(output),
        settings={"tts_cache_dir": str(tmp_path / "jobs" / "tts")},
    )
    assert result.ok, result.message
    report = json.loads(
        (output.with_name(output.stem + ".render_report.json")).read_text(encoding="utf-8")
    )
    segment = report["segments"][0]
    assert segment["speed"] > 1.0, "the speech was longer than the window"
    # The fitted clip is written into the window, never past it.
    assert segment["raw_duration"] > segment["window"]
    # The published mix holds the whole source duration.
    assert report["output_duration"] == pytest.approx(3.0, abs=0.1)


@needs_ffmpeg
def test_the_duration_tolerance_is_reported_and_reused(tmp_path) -> None:
    """One tolerance drives both gates: the renderer's own number is reused."""
    rows = make_rows()
    video = make_video(tmp_path / "source.mp4", seconds=4.0)
    translation = write_translation(tmp_path / "translated_gender.json", rows)
    output = tmp_path / "final.mp4"

    logs: list[str] = []
    service = ExactDubbingService(str(tmp_path / "jobs"))
    coordinator = service.create_coordinator(
        settings={"tts_cache_dir": str(tmp_path / "jobs" / "tts")}, log=logs.append
    )
    result = coordinator.run(
        rows, str(video), 4.0, str(output),
        {"tts_cache_dir": str(tmp_path / "jobs" / "tts"), "duration_tolerance": 0.25},
    )
    assert result.ok, result.message

    from mmnext.application.exact_dubbing_render_coordinator import (
        ExactDubbingRenderCoordinator,
    )

    report = dict(getattr(coordinator.renderer, "report", {}) or {})
    assert "duration_tolerance" in report, report
    reported = float(report["duration_tolerance"])
    # 4.0s at 15 fps -> max(0.1, 1/15) = 0.1
    assert reported == pytest.approx(0.1)
    assert (
        ExactDubbingRenderCoordinator._reported_tolerance(
            report, "duration_tolerance", {}, 0.25
        )
        == pytest.approx(reported)
    )
    assert any("muxed with" in message for message in logs), logs[-5:]


# --------------------------------------------------------------------------- #
# Offline switch and the opt-in REAL speech path
# --------------------------------------------------------------------------- #


def test_the_offline_switch_keeps_the_suite_off_the_network(tmp_path, monkeypatch) -> None:
    """The suite must never reach the real Edge TTS service.

    ``edge_tts`` may be installed in the project venv (it is, to prove the REAL
    path), so the switch - not the absence of a package - is what keeps a test
    run deterministic and offline.
    """
    from mmnext.application.exact_dubbing_service import (
        OFFLINE_TTS_ENV,
        ExactDubbingService,
    )
    from mmnext.services.adapters.exact_dubbing_tts import (
        LegacyExactDubbingTtsAdapter,
    )

    installed = LegacyExactDubbingTtsAdapter().available()

    monkeypatch.setenv(OFFLINE_TTS_ENV, "1")
    forced = ExactDubbingService(str(tmp_path / "jobs"))
    assert forced.allow_real_tts is False
    assert forced.tts_available() is False
    assert forced.is_demo() is True

    # An explicit opt-in wins over the environment switch.
    opted_in = ExactDubbingService(str(tmp_path / "jobs"), allow_real_tts=True)
    assert opted_in.allow_real_tts is True
    assert opted_in.tts_available() == installed
    assert opted_in.is_demo() is not installed

    monkeypatch.setenv(OFFLINE_TTS_ENV, "")
    monkeypatch.delenv(OFFLINE_TTS_ENV, raising=False)
    default = ExactDubbingService(str(tmp_path / "jobs"))
    assert default.allow_real_tts is True
    assert default.tts_available() == installed

    # The forced-offline run really uses the offline synthesiser, so the label
    # and the cached file reflect simulated speech rather than a network call.
    logs: list[str] = []
    coordinator = forced.create_coordinator(
        settings={"tts_cache_dir": str(tmp_path / "jobs" / "tts")}, log=logs.append
    )
    assert coordinator.is_demo is True
    assert type(coordinator.tts).__name__ == "LocalWaveTtsAdapter"


real_edge_tts = pytest.mark.skipif(
    not os.environ.get("MMNEXT_EDGE_TTS_SMOKE"),
    reason="Opt-in only: set MMNEXT_EDGE_TTS_SMOKE=1 to exercise the real Edge TTS service",
)


@needs_ffmpeg
@real_edge_tts
def test_the_real_edge_tts_path_renders_a_labelled_real_dub(tmp_path) -> None:
    """REAL speech end to end, over the network, on explicit request.

    This is the only test that reaches Microsoft's Edge TTS service, so it is
    opt-in: the suite as a whole stays offline and deterministic (see
    ``test_the_offline_switch_keeps_the_suite_off_the_network``).  It proves what
    the DEMO run cannot - that the real synthesiser, the gender -> voice mapping
    and the REAL labelling all work together through the production path.
    """
    from mmnext.application.exact_dubbing_service import ExactDubbingService

    rows = make_rows()
    video = make_video(tmp_path / "source.mp4", seconds=4.0)
    translation = write_translation(tmp_path / "translated_gender.json", rows)
    output = tmp_path / "final.mp4"

    # The conftest switch is on, so this test opts in explicitly.
    service = ExactDubbingService(str(tmp_path / "jobs"), allow_real_tts=True)
    if not service.tts_available():
        pytest.skip("edge_tts is not installed")
    assert service.is_demo() is False

    result = service.render_from_translated_gender(
        str(translation),
        rows,
        str(video),
        4.0,
        str(output),
        settings={"tts_cache_dir": str(tmp_path / "jobs" / "tts")},
    )
    assert result.ok, result.message
    assert result.is_demo is False, "a REAL speech run must not be labelled DEMO"

    report = json.loads(
        (output.with_name(output.stem + ".render_report.json")).read_text(encoding="utf-8")
    )
    assert report["is_demo"] is False
    voices = {segment["voice"] for segment in report["segments"]}
    # The gender -> voice mapping of the legacy contract, proven with real audio.
    assert EXACT_DUB_VOICES["male"] in voices
    assert EXACT_DUB_VOICES["female"] in voices
    for segment in report["segments"]:
        assert segment["raw_duration"] > 0, "the real synthesiser produced no audio"

    info = probe(output)
    duration = float(info["format"]["duration"])
    assert abs(duration - 4.0) <= 0.25
    audio = [s for s in info["streams"] if s["codec_type"] == "audio"]
    assert audio, "the render must keep an audio stream"
    cached = list((tmp_path / "jobs" / "tts").glob("*.audio"))
    assert cached, "the real speech must be cached for reuse"
