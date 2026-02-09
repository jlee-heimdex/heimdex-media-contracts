"""Pure functions for assigning speech segments to scenes.

All functions in this module are side-effect-free: no I/O, no network,
no filesystem access.  They operate solely on in-memory data structures.
"""

from __future__ import annotations

from typing import Dict, List, Sequence

from heimdex_media_contracts.scenes.schemas import SceneBoundary


def assign_segments_to_scenes(
    scenes: Sequence[SceneBoundary],
    segments: Sequence[dict],
) -> Dict[str, List[dict]]:
    """Assign each speech segment to the scene with maximum temporal overlap.

    Each segment dict must have ``"start"`` and ``"end"`` keys (in seconds).
    Segments with zero overlap with all scenes are dropped.

    Args:
        scenes: Scene boundaries, typically sorted by ``start_ms``.
        segments: Speech segment dicts with at minimum ``start`` (float, seconds),
            ``end`` (float, seconds), and ``text`` (str) keys.

    Returns:
        Mapping of ``scene_id`` → list of segment dicts assigned to that scene,
        ordered by segment start time within each scene.
    """
    result: Dict[str, List[dict]] = {s.scene_id: [] for s in scenes}

    for seg in segments:
        seg_start_ms = int(seg["start"] * 1000)
        seg_end_ms = int(seg["end"] * 1000)

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
        result[scene_id].sort(key=lambda s: s["start"])

    return result


def aggregate_transcript(segments: Sequence[dict]) -> str:
    """Concatenate segment texts in time order with single space separator.

    Args:
        segments: Speech segment dicts (must have ``"text"`` key), assumed
            already sorted by start time.

    Returns:
        Single string of all segment texts joined by spaces.  Returns empty
        string if no segments or all texts are empty.
    """
    texts = [seg["text"].strip() for seg in segments if seg.get("text", "").strip()]
    return " ".join(texts)
