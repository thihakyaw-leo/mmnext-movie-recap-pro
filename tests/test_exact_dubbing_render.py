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
import shutil
import subprocess
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

pytestmark = pytest.mark.skipif(
    not (shutil.which("ffmpeg") and shutil.which("ffprobe")),
    reason="FFmpeg/FFprobe are required for the exact-dubbing render",
)

BURMESE_A = "မြန်မာလို ရှင်းပြပါ"
BURMESE_B = "ဒီနေ့ ငါ တရားထိုင်ရာက ထွက်လာပြီး နောက်ဆုံးတော့ ကျင့်ကြံမှုအဆင့်သစ်ကို တက်လှမ်းနိုင်ခဲ့ပြီ။"
BURMESE_C = "ကျင့်ကြံမှုအဆင့်သစ်ကို တက်လှမ်းနိုင်ခဲ့တဲ့အတွက် စီနီယာကြီးကို ကျွန်မ ဂုဏ်ပြုပါတယ်။"


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
            "-f", "lavfi", "-i", f"color=c=black:s=320x180:r=15",
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
        capture_output=True, text=True, check=True,
    )
    return json.loads(completed.stdout)


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


def test_cache_signature_is_content_addressed() -> None:
    first = cache_signature("my-MM-NilarNeural", BURMESE_A)
    assert first == cache_signature("my-MM-NilarNeural", BURMESE_A)
    assert first != cache_signature("my-MM-ThihaNeural", BURMESE_A)
    assert first != cache_signature("my-MM-NilarNeural", BURMESE_B)


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
    import wave

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
    assert [segment["id"] for segment in report["segments"]] == ["s0", "s1"]
    assert report["segments"][0]["voice"] == "my-MM-ThihaNeural"
    assert report["segments"][1]["voice"] == "my-MM-NilarNeural"


def test_render_never_changes_the_source_rows(tmp_path) -> None:
    video = make_video(tmp_path / "source.mp4", seconds=4.0)
    rows = make_rows()
    before = [(r.row_id, r.start, r.duration, r.original) for r in rows]
    translation = write_translation(tmp_path / "translated_gender.json", rows)
    output = tmp_path / "final.mp4"

    service = ExactDubbingService(str(tmp_path / "jobs"))
    result = service.render_from_translated_gender(
        str(translation), rows, str(video), 4.0, str(output),
        settings={"tts_cache_dir": str(tmp_path / "jobs" / "tts")},
    )
    assert result.ok, result.message
    after = [(r.row_id, r.start, r.duration, r.original) for r in rows]
    assert after == before


def test_render_reuses_cached_speech(tmp_path) -> None:
    video = make_video(tmp_path / "source.mp4", seconds=4.0)
    rows = make_rows()
    translation = write_translation(tmp_path / "translated_gender.json", rows)
    service = ExactDubbingService(str(tmp_path / "jobs"))
    settings = {"tts_cache_dir": str(tmp_path / "jobs" / "tts")}

    service.render_from_translated_gender(
        str(translation), rows, str(video), 4.0, str(tmp_path / "a.mp4"),
        settings=settings,
    )
    cache = list((tmp_path / "jobs" / "tts").glob("*.wav"))
    assert cache, "the synthesiser must leave cached audio behind"
    stamps = {path.stat().st_mtime_ns for path in cache}

    service.render_from_translated_gender(
        str(translation), rows, str(video), 4.0, str(tmp_path / "b.mp4"),
        settings=settings,
    )
    assert {path.stat().st_mtime_ns for path in cache} == stamps


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


def test_render_reports_failure_without_a_final_file(tmp_path) -> None:
    rows = make_rows()
    translation = write_translation(tmp_path / "translated_gender.json", rows)
    output = tmp_path / "final.mp4"

    service = ExactDubbingService(str(tmp_path / "jobs"))
    result = service.render_from_translated_gender(
        str(translation), rows, str(tmp_path / "missing.mp4"), 4.0, str(output),
        settings={"tts_cache_dir": str(tmp_path / "jobs" / "tts")},
    )
    assert not result.ok
    assert not output.exists()


# --------------------------------------------------------------------------- #
# Export -> validate -> render round trip
# --------------------------------------------------------------------------- #


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
