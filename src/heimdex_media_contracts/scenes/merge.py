"""Pure functions for assigning speech segments to scenes.

All functions in this module are side-effect-free: no I/O, no network,
no filesystem access.  They operate solely on in-memory data structures.
"""

from __future__ import annotations

from typing import Any, Dict, List, Protocol, Sequence, Union, runtime_checkable

from heimdex_media_contracts.scenes.schemas import SceneBoundary


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
