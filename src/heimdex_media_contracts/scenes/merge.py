"""Pure functions for assigning speech segments to scenes.

All functions in this module are side-effect-free: no I/O, no network,
no filesystem access.  They operate solely on in-memory data structures.
"""

from __future__ import annotations

from typing import Any, Dict, List, Protocol, Sequence, Union, runtime_checkable

from heimdex_media_contracts.ocr.gating import gate_ocr_text
from heimdex_media_contracts.ocr.schemas import OCRSceneResult
from heimdex_media_contracts.scenes.schemas import SceneBoundary, SceneDocument
from heimdex_media_contracts.speech.schemas import TaggedSegment


@runtime_checkable
class SpeechSegmentLike(Protocol):
    """Structural type for objects with start/end times and text.

    Satisfied by SpeechSegment, TaggedSegment, RankedSegment, or any
    object/dataclass with these three attributes.
    """

    @property
    def start(self) -> float: ...
    @property
    def end(self) -> float: ...
    @property
    def text(self) -> str: ...


SegmentInput = Union[SpeechSegmentLike, Dict[str, Any]]


def _get_start(seg: SegmentInput) -> float:
    return seg["start"] if isinstance(seg, dict) else seg.start


def _get_end(seg: SegmentInput) -> float:
    return seg["end"] if isinstance(seg, dict) else seg.end


def _get_text(seg: SegmentInput) -> str:
    if isinstance(seg, dict):
        return seg.get("text", "")
    return seg.text


def _get_speaker_id(seg: SegmentInput) -> str | None:
    if isinstance(seg, dict):
        return seg.get("speaker_id")
    return getattr(seg, "speaker_id", None)


def assign_segments_to_scenes(
    scenes: Sequence[SceneBoundary],
    segments: Sequence[SegmentInput],
) -> Dict[str, List[SegmentInput]]:
    """Assign each speech segment to the scene with maximum temporal overlap.

    Args:
        scenes: Scene boundaries, typically sorted by ``start_ms``.
        segments: Objects with ``start`` (float, seconds), ``end`` (float,
            seconds), and ``text`` (str).  Accepts dicts, dataclasses, or
            Pydantic models implementing ``SpeechSegmentLike``.

    Returns:
        Mapping of ``scene_id`` to list of segments assigned to that scene,
        ordered by segment start time within each scene.
    """
    result: Dict[str, List[SegmentInput]] = {s.scene_id: [] for s in scenes}

    for seg in segments:
        seg_start_ms = int(_get_start(seg) * 1000)
        seg_end_ms = int(_get_end(seg) * 1000)

        best_scene_id: str | None = None
        best_overlap: int = 0

        for scene in scenes:
            overlap_start = max(seg_start_ms, scene.start_ms)
            overlap_end = min(seg_end_ms, scene.end_ms)
            overlap = max(0, overlap_end - overlap_start)

            if overlap > best_overlap:
                best_overlap = overlap
                best_scene_id = scene.scene_id

        if best_scene_id is not None:
            result[best_scene_id].append(seg)

    for scene_id in result:
        result[scene_id].sort(key=lambda s: _get_start(s))

    return result


def aggregate_transcript(segments: Sequence[SegmentInput]) -> str:
    """Concatenate segment texts in time order with single space separator.

    Args:
        segments: Objects with a ``text`` attribute or ``"text"`` dict key.
            Assumed already sorted by start time.

    Returns:
        Single string of all segment texts joined by spaces.  Returns empty
        string if no segments or all texts are empty.
    """
    texts = [_get_text(seg).strip() for seg in segments if _get_text(seg).strip()]
    return " ".join(texts)


def _format_timestamp(seconds: float) -> str:
    total = int(seconds)
    h = total // 3600
    m = (total % 3600) // 60
    s = total % 60
    if h > 0:
        return f"{h}:{m:02d}:{s:02d}"
    return f"{m}:{s:02d}"


def aggregate_speaker_transcript(segments: Sequence[SegmentInput]) -> str:
    """Build speaker-labelled transcript from diarized segments.

    Merges consecutive segments by the same speaker into single lines.
    Each line includes the start timestamp of the first segment in the turn.
    Returns empty string when no segments have speaker labels.

    Example output::

        SPEAKER_00 [0:00]: 안녕하세요 오늘 라이브에 오신 걸 환영합니다
        SPEAKER_01 [0:15]: 네 감사합니다 잘 부탁드립니다
    """
    if not segments:
        return ""

    has_any_speaker = any(_get_speaker_id(s) is not None for s in segments)
    if not has_any_speaker:
        return ""

    lines: list[str] = []
    current_speaker: str | None = None
    current_texts: list[str] = []
    current_start: float = 0.0

    for seg in segments:
        speaker = _get_speaker_id(seg) or "UNKNOWN"
        text = _get_text(seg).strip()
        if not text:
            continue
        if speaker != current_speaker:
            if current_texts and current_speaker is not None:
                ts = _format_timestamp(current_start)
                lines.append(f"{current_speaker} [{ts}]: {' '.join(current_texts)}")
            current_speaker = speaker
            current_texts = [text]
            current_start = _get_start(seg)
        else:
            current_texts.append(text)

    if current_texts and current_speaker is not None:
        ts = _format_timestamp(current_start)
        lines.append(f"{current_speaker} [{ts}]: {' '.join(current_texts)}")

    return "\n".join(lines)


def count_distinct_speakers(segments: Sequence[SegmentInput]) -> int:
    speakers: set[str] = set()
    for seg in segments:
        sid = _get_speaker_id(seg)
        if sid is not None:
            speakers.add(sid)
    return len(speakers)


def aggregate_scene_tags(segments: Sequence[TaggedSegment]) -> list[str]:
    """Deduplicated, sorted union of all segment tags within a scene."""
    tags: set[str] = set()
    for seg in segments:
        tags.update(seg.tags)
    return sorted(tags)


def merge_ocr_into_scene(
    scene: SceneDocument,
    ocr: OCRSceneResult | None,
) -> SceneDocument:
    """Merge OCR results into a scene document (additive, never replaces transcript).

    Applies gating rules from OCR_MINIMAL_CONTEXT_CONTRACT.md:
      - gate_ocr_text() handles min_chars, noise ratio, max_length
      - ocr_char_count is auto-computed from gated text

    Args:
        scene: Existing scene document with transcript fields populated.
        ocr: OCR result for the same scene, or None if no OCR available.

    Returns:
        New SceneDocument with OCR fields populated.  If *ocr* is None or
        the gated text is empty, OCR fields remain at their defaults.
    """
    if ocr is None:
        return scene.model_copy()

    gated = gate_ocr_text(ocr.ocr_text_raw)

    return scene.model_copy(
        update={
            "ocr_text_raw": gated,
            "ocr_char_count": len(gated),
        },
    )
