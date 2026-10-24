"""The deterministic demo project.

Everything the UI shows in milestone 1 comes from here. The data is
byte-stable: the same project is produced on every launch, which keeps tests,
screenshots and tutorials reproducible.

The demo project deliberately contains **one broken exact-dubbing row**
(row 12 has no Burmese translation) and **one ``unknown`` gender** (row 3) so
the validation drawer shows a real blocker and a real fallback instead of an
empty, meaningless list.
"""

from __future__ import annotations

import copy
from dataclasses import dataclass, field

from ...domain.enums import (
    AppMode,
    CutReason,
    FrameFill,
    Gender,
    JobState,
    OutputRatio,
    OverlayKind,
    Severity,
    SourceType,
    Stage,
    TaskState,
)
from ...domain.models import (
    DownloadItem,
    ExactDubbingRow,
    Job,
    JobProgress,
    NarrationSegment,
    Overlay,
    ProjectSession,
    SourceMetadata,
    SplitPart,
    TranscriptRow,
    ValidationIssue,
    VideoQuality,
    VideoSource,
)

__all__ = [
    "DEMO_VIDEO_ID",
    "DEMO_TITLE",
    "DEMO_SOURCE_PATH",
    "DEMO_OUTPUT_FOLDER",
    "DEMO_PROJECT",
    "DemoProject",
    "BROKEN_EXACT_ROW_INDEX",
    "build_demo_session",
    "build_demo_jobs",
    "demo_qualities",
    "demo_transcript",
    "demo_narration_segments",
    "demo_exact_dubbing_rows",
    "demo_split_parts",
    "demo_overlays",
    "demo_metadata",
    "demo_source",
    "demo_validation_issues",
    "demo_download_item",
    "DEMO_TOTAL_BYTES",
    "CHUNK_PATTERN",
]

DEMO_VIDEO_ID = "dQw4w9WgXcQ"
DEMO_TITLE = "The Last Signal - Episode 7 (Official Clip)"
DEMO_SOURCE_PATH = r"J:\Movies\The Last Signal\The Last Signal - E07.mp4"
DEMO_OUTPUT_FOLDER = r"J:\Movies\The Last Signal\MMNext Output"

#: Index of the exact-dubbing row that intentionally has no Burmese text.
BROKEN_EXACT_ROW_INDEX = 11

#: Total size of the simulated download (508.7 MB, the 1080p demo quality).
DEMO_TOTAL_BYTES = int(508.7 * 1024 * 1024)

#: Percentage points delivered by each simulated chunk. The pattern cycles,
#: so a full download takes a fixed number of steps (see
#: :func:`mmnext.services.demo.demo_providers.DemoDownloadService.step`).
CHUNK_PATTERN: tuple[int, ...] = (3, 5, 2, 8, 4, 6, 1, 7)

# --------------------------------------------------------------------------- #
# Source + metadata
# --------------------------------------------------------------------------- #
_SOURCE = VideoSource(
    source_type=SourceType.YOUTUBE,
    location=f"https://www.youtube.com/watch?v={DEMO_VIDEO_ID}",
    display_name="The Last Signal - E07 (demo)",
    duration_s=6875.4,
)

_QUALITIES: list[VideoQuality] = [
    VideoQuality("2160", "2160p", 3840, 2160, 60.0, 18500, 1520.4),
    VideoQuality("1440", "1440p", 2560, 1440, 60.0, 11000, 903.2),
    VideoQuality("1080", "1080p", 1920, 1080, 60.0, 6200, 508.7),
    VideoQuality("720", "720p", 1280, 720, 30.0, 3100, 254.3),
]

_METADATA = SourceMetadata(
    title=DEMO_TITLE,
    channel="Northlight Studios (demo)",
    duration_s=6875.4,
    published="2024-11-03",
    description=(
        "Demo metadata. No network call was made - this record is a fixed "
        "fixture so the analyze screen can be exercised offline."
    ),
    thumbnail_hint="demo://thumb/the-last-signal-e07",
    qualities=list(_QUALITIES),
    has_audio=True,
    has_video=True,
    language="en",
)


def demo_source() -> VideoSource:
    """The demo remote source."""
    return _SOURCE


def demo_metadata() -> SourceMetadata:
    """The demo metadata record."""
    return _METADATA


def demo_qualities() -> list[VideoQuality]:
    """The four demo quality options."""
    return list(_QUALITIES)


# --------------------------------------------------------------------------- #
# Transcript (24 verbatim source rows)
# --------------------------------------------------------------------------- #
_TRANSCRIPT: list[tuple[float, float, str]] = [
    (0.0, 6.4, "The city was already asleep when the signal came through."),
    (6.4, 5.1, "Mara heard it first, a low pulse under the radio static."),
    (11.5, 7.8, "It was the same frequency that had been silent for eleven years."),
    (19.3, 6.2, "She reached for the receiver with a shaking hand."),
    (25.5, 8.6, "Your name, it said. Just her name, nothing else."),
    (34.1, 5.9, "Then the voice asked her to come to the northern tower."),
    (40.0, 9.2, "By the time she crossed the yard, the fog had covered the road."),
    (49.2, 6.7, "Her brother was waiting beside the old transmitter."),
    (55.9, 7.4, "You knew it would work, he said without looking at her."),
    (63.3, 5.2, "Mara did not answer him, she was listening to the rain."),
    (68.5, 8.8, "The tower had been cold for a decade, and it still was."),
    (77.3, 6.1, "Then the panel lights came on, one row at a time."),
    (83.4, 7.9, "Every light was a name, and every name was a person she knew."),
    (91.3, 5.6, "Her father, her teacher, the doctor from the old district."),
    (96.9, 9.5, "The transmitter hummed, and the fog lit up like a paper lantern."),
    (106.4, 6.8, "There was no message, only a signal that kept repeating."),
    (113.2, 8.1, "Three short pulses, then a long one, then silence."),
    (121.3, 5.3, "Mara finally understood the rhythm, she had heard it as a child."),
    (126.6, 9.8, "It was the emergency code used during the flood of ninety one."),
    (136.4, 6.5, "The city had forgotten, but the tower had not."),
    (142.9, 7.2, "Her brother finally looked at her, and he was afraid too."),
    (150.1, 6.9, "We have to answer it, she said and reached for the microphone."),
    (157.0, 10.4, "The whole city woke up behind them, one light after another."),
    (167.4, 8.6, "And for the first time in eleven years, the signal was not alone."),
]

# --------------------------------------------------------------------------- #
# Burmese narration for the narrator mode (24 strings, index aligned)
# --------------------------------------------------------------------------- #
_BURMESE: list[str] = [
    "မြို့တော်က အိပ်ပြီးသား ဖြစ်နေချိန် အခု လျှင်္လင်းက ဝင်လာခဲ့သည်။",
    "မာရာက ပထမဆုံး ကြားလိုက်ရသည်။ ရေမီးလွှာအောက်မှ နိမ့်လျော့သော ခုန်ခွန်းတစ်ခု။",
    "တစ်နှစ်ကြား ဆိတ်နေခဲ့သည့် အင်္ဂါရှိုးများထဲမှ အသံပြန်ပင် မရှိတော့ပေ။",
    "လက်မောင်းက တုန်ခါသောကြောင့် လက်ဖဝါးကို ဆန်းချောက်ကာ လှုပ်ရှားလိုက်သည်။",
    "အသံက သူ့နာမည်ကိုသာ ပြောလိုက်ပြီး အခြားမည်လည်း မပြောခဲ့ပေ။",
    "ထို့နောက် အသံက မြောက်ခြောက်သော စစ်စောင့်တိုက်သို့ သွားရန် တောင်းခဲ့သည်။",
    "ခြောင်းကွဲကားသည်အထိ ရောက်ရန် မွေးပြီးတည်း မြူရွေ့ထွက်ကာ လမ်းမကြောင်းမြင့် ရန် ကူညီသွားသည်။",
    "သူ့အစ်ကိုက ဟင်တီလိုင်တစ်ခုနှင့် မောက်မောင်းတို့နှင့် ကြိုတွေ့နေသည်။",
    "သူသိလိုက်မည်ကို သိသည်ဟု မျက်လုံးမထိုးဘဲ ပြောလိုက်သည်။",
    "မာရာက ပြန်စာမဖြေပေ၊ မိုးသံကိုသာ နောက်နေသည်။",
    "တိုက်က တစ်ဆယ်နှစ်ကြား အေးချမ်းနေပြီး ယခုလည်း အေးချမ်းပင် ဖြစ်နေသေးသည်။",
    "ထို့နောက် ပန်းချီမီးများက တစ်စီးလိုက် တစ်စီးတိုင်း တလ်တစ်ခုချင်းစီ တလ်လိုက်လာသည်။",
    "တလ်တစ်ခုချင်းစီသည် လူတစ်ယောက်၏ အမည်ဖြစ်ပြီး အမည်အားလုံးက သူ့သိကြားသူများ ဖြစ်ကြသည်။",
    "သူ့ဖခင်၊ ဆရာ၊ ခနလောက်လိုင်းရှိ ဆရာဝန်ထမ်းမှုထောင်သူ တို့ ဖြစ်ကြသည်။",
    "ထုည်ခေါင်းက ဟုန်းထိုးလာပြီး မြူထုည်က ရေမီးရှင်းကို ရောက်ရှိလာသည်။",
    "မည်သည့်စာသားများမျိုးလုံး မရှိခဲ့ဘဲ ထပ်ခါထပ်ခါ လက်နက်ရွေ့ကူးနေသည့် လျှင်္လင်းတစ်ခုသာ ရှိသည်။",
    "လက်တစ်ကြိမ်၊ ရှည်ကြားကြားတစ်ကြိမ်၊ ပြီးလျှင် ငြိမ်သက်ခြင်း။",
    "မာရာက နောက်ဆုံး ထိုစွန့်သံကို နားလည်လိုက်သည်။",
    "သူက ငယ်စဉ်ကတည်းက ကြားခဲ့သော အရေးအထူးအလုပ် သံကြားကို ဖြစ်သည်။",
    "ရွံ့ထိုးကားမှု ကင်းဟန်မှု အတွက် အသုံးပြုသော အရေးအထူးကိုဒ် ဖြစ်သည်။",
    "မြို့တော်က မေ့လေမေ့လေ မှတ်မိုးနေပြီး စစ်စောင့်က မေ့တော်တော် မကျော်က်ခဲ့ပေ။",
    "နောက်ဆုံး မာရာက သူ့အစ်ကိုကို ကြည့်လိုက်သည်။",
    "သူ့ကိုယ်တိုင်ကလည်း ကြောက်ရွံ့နေကြောင်း ထင်လာသည်။",
    "ကျွန်ုပ်တို့ ပြန်စာပို့ရမည် ဟု ပြောလိုက်ပြီး မိုခရိုဖိုင်ကို လက်ဆန်းလိုက်သည်။",
    "မြို့တစ်ခုလုံးက နောက်တစ်ခုတိုင်း နိုးထိန်းလာပြီး သူတို့က သာမန်မကျန်တော့ပေ။",
]

#: Gender per transcript row. Row 3 is deliberately ``unknown``.
_GENDERS: list[Gender] = [
    Gender.FEMALE, Gender.FEMALE, Gender.UNKNOWN, Gender.MALE,
    Gender.MALE, Gender.FEMALE, Gender.FEMALE, Gender.MALE,
    Gender.MALE, Gender.FEMALE, Gender.MALE, Gender.MALE,
    Gender.FEMALE, Gender.FEMALE, Gender.MALE, Gender.MALE,
    Gender.FEMALE, Gender.MALE, Gender.FEMALE, Gender.MALE,
    Gender.MALE, Gender.FEMALE, Gender.MALE, Gender.FEMALE,
]


def demo_transcript() -> list[TranscriptRow]:
    """The 24 verbatim source rows."""
    return [
        TranscriptRow(
            row_id=f"seg_{i + 1:04d}",
            start=start,
            duration=duration,
            text=text,
        )
        for i, (start, duration, text) in enumerate(_TRANSCRIPT)
    ]


def demo_narration_segments() -> list[NarrationSegment]:
    """24 narrator segments, each covering the matching source row."""
    rows = demo_transcript()
    segments: list[NarrationSegment] = []
    for index, row in enumerate(rows):
        segments.append(
            NarrationSegment(
                segment_id=f"narr_{index + 1:03d}",
                source_segment_ids=[row.row_id],
                source_text=row.text,
                narration=_BURMESE[index],
                translation="",
                video_start=row.start,
                video_end=row.end,
                order=index,
                semantic_boundary=index % 4 == 3,
                forced_boundary=index % 7 == 6,
                visual_reason="character reaction" if index % 3 == 0 else "",
            )
        )
    return segments


def demo_exact_dubbing_rows() -> list[ExactDubbingRow]:
    """24 exact-dubbing rows.

    Row 12 intentionally has **no** Burmese translation so the validation
    surface shows a genuine error instead of an empty list.
    """
    rows = demo_transcript()
    result: list[ExactDubbingRow] = []
    for index, row in enumerate(rows):
        burmese = "" if index == BROKEN_EXACT_ROW_INDEX else _BURMESE[index]
        result.append(
            ExactDubbingRow(
                row_id=row.row_id,
                start=row.start,
                duration=row.duration,
                original=row.text,
                burmese=burmese,
                gender=_GENDERS[index],
            )
        )
    return result


def demo_split_parts() -> list[SplitPart]:
    """Six planned splitter parts covering the first six minutes."""
    raw = [
        (1, 0.0, 60.0, CutReason.EXACT, "Part 1"),
        (2, 60.0, 120.0, CutReason.PAUSE, "Part 2"),
        (3, 120.0, 180.0, CutReason.BREATH, "Part 3"),
        (4, 180.0, 240.0, CutReason.QUIETEST, "Part 4"),
        (5, 240.0, 300.0, CutReason.EXACT, "Part 5"),
        (6, 300.0, 360.0, CutReason.END, "Part 6"),
    ]
    return [
        SplitPart(number=n, start=start, end=end, cut_reason=reason, label=label)
        for n, start, end, reason, label in raw
    ]


def demo_overlays() -> list[Overlay]:
    """Four production overlays used by common editing mode."""
    return [
        Overlay(
            kind=OverlayKind.TITLE,
            text="The Last Signal",
            start=0.0,
            end=6.0,
            position="lower_third",
        ),
        Overlay(
            kind=OverlayKind.EXTRA_TEXT,
            text="မာရာသည် လျှင်္လင်းကို ပထမဆုံး ကြားလိုက်ရသည်",
            start=6.4,
            end=13.0,
            position="top",
        ),
        Overlay(
            kind=OverlayKind.BLUR_BOX,
            text="",
            start=19.3,
            end=25.5,
            position="center",
        ),
        Overlay(
            kind=OverlayKind.LOGO,
            text="Northlight",
            start=0.0,
            end=6875.4,
            position="top_right",
        ),
    ]


def demo_download_item(
    state: TaskState = TaskState.QUEUED,
    downloaded_bytes: int = 0,
) -> DownloadItem:
    """A snapshot of a queued download, for cards and tests.

    The numbers match :mod:`mmnext.services.demo.demo_providers` so the
    progress card renders the same figures the simulated service produces.
    """
    return DownloadItem(
        item_id="dl_001",
        title=DEMO_TITLE,
        url=f"https://www.youtube.com/watch?v={DEMO_VIDEO_ID}",
        total_bytes=DEMO_TOTAL_BYTES,
        downloaded_bytes=downloaded_bytes,
        speed_bps=2_400_000.0,
        state=state,
        quality_label="1080p",
    )


def demo_validation_issues() -> list[ValidationIssue]:
    """The validation findings the demo project intentionally contains."""
    return [
        ValidationIssue(
            code="missing_burmese",
            message="Row 12 has no Burmese translation",
            severity=Severity.ERROR,
            row_id="seg_0012",
            field="burmese",
        ),
        ValidationIssue(
            code="unknown_gender",
            message=(
                "Row 3 has gender 'unknown' - voice falls back to "
                "my-MM-NilarNeural"
            ),
            severity=Severity.INFO,
            row_id="seg_0003",
            field="gender",
        ),
        ValidationIssue(
            code="narration_too_long",
            message="Segment narr_009 narration is too long for 5.2s",
            severity=Severity.WARNING,
            row_id="narr_009",
            field="narration",
        ),
    ]


@dataclass(slots=True)
class DemoProject:
    """A complete, deterministic demo project."""

    source: VideoSource
    metadata: SourceMetadata
    transcript: list[TranscriptRow]
    narration_segments: list[NarrationSegment]
    exact_dubbing_rows: list[ExactDubbingRow]
    split_parts: list[SplitPart]
    overlays: list[Overlay]
    validation_issues: list[ValidationIssue] = field(default_factory=list)

    def to_session(self, mode: AppMode = AppMode.COMMON_EDITING) -> ProjectSession:
        """Return a fresh, independent :class:`ProjectSession` copy.

        The rows are deep-copied on purpose: the demo rows are mutable
        (``dirty`` / ``edited`` / ``burmese``), so a shallow copy would let an
        edit in one session leak into every other session built from the same
        module-level fixture.
        """
        return ProjectSession(
            source=copy.deepcopy(self.source),
            metadata=copy.deepcopy(self.metadata),
            transcript=copy.deepcopy(self.transcript),
            narration_segments=copy.deepcopy(self.narration_segments),
            exact_dubbing_rows=copy.deepcopy(self.exact_dubbing_rows),
            split_parts=copy.deepcopy(self.split_parts),
            overlays=copy.deepcopy(self.overlays),
            mode=mode,
            output_ratio=OutputRatio.ORIGINAL,
            frame_fill=FrameFill.BLUR,
            output_folder=DEMO_OUTPUT_FOLDER,
            is_demo=True,
        )


DEMO_PROJECT = DemoProject(
    source=_SOURCE,
    metadata=_METADATA,
    transcript=demo_transcript(),
    narration_segments=demo_narration_segments(),
    exact_dubbing_rows=demo_exact_dubbing_rows(),
    split_parts=demo_split_parts(),
    overlays=demo_overlays(),
    validation_issues=demo_validation_issues(),
)


def build_demo_session(mode: AppMode = AppMode.COMMON_EDITING) -> ProjectSession:
    """A fresh copy of the demo project as a :class:`ProjectSession`."""
    return DEMO_PROJECT.to_session(mode)


def build_demo_jobs() -> list[Job]:
    """Six preset jobs that cover every interesting badge and button state."""
    specs = [
        (
            "job_demo_001",
            AppMode.NARRATOR,
            JobState.COMPLETE,
            TaskState.COMPLETE,
            100.0,
            Stage.RENDER,
            "Render complete: final_edge_tts_smart_sync.mp4",
        ),
        (
            "job_demo_002",
            AppMode.EXACT_DUBBING,
            JobState.VALIDATING,
            TaskState.RUNNING,
            62.0,
            Stage.VALIDATE,
            "Validating 24 translation rows",
        ),
        (
            "job_demo_003",
            AppMode.SPLITTER,
            JobState.RENDERING,
            TaskState.RUNNING,
            38.0,
            Stage.SPLIT,
            "Rendering part 3 of 6",
        ),
        (
            "job_demo_004",
            AppMode.COMMON_EDITING,
            JobState.AWAITING_TRANSLATION_OR_EDIT,
            TaskState.QUEUED,
            0.0,
            Stage.IDLE,
            "Waiting for narration edit",
        ),
        (
            "job_demo_005",
            AppMode.EXACT_DUBBING,
            JobState.FAILED,
            TaskState.FAILED,
            12.0,
            Stage.VALIDATE,
            "Source duration drift 0.412s exceeds 0.05s tolerance",
        ),
        (
            "job_demo_006",
            AppMode.NARRATOR,
            JobState.DOWNLOAD_PAUSED,
            TaskState.PAUSED,
            44.0,
            Stage.DOWNLOAD,
            "Paused by user",
        ),
    ]
    jobs: list[Job] = []
    for job_id, mode, state, task_state, percent, stage, message in specs:
        jobs.append(
            Job(
                job_id=job_id,
                title=DEMO_TITLE,
                mode=mode,
                state=state,
                task_state=task_state,
                progress=JobProgress(
                    percent=percent,
                    message=message,
                    stage=stage,
                ),
                created_at="2026-01-14 09:12:00",
                updated_at="2026-01-14 09:41:00",
                source=_SOURCE,
                is_demo=True,
            )
        )
    return jobs
