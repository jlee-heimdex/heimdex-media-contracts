"""Pure timestamp sampling math for face detection pipelines.

This module contains ONLY pure functions. It does NOT probe media files.
The caller is responsible for determining the video duration and passing it in.

Migrated from (pure portion only):
  dev-heimdex-for-livecommerce/services/worker/src/domain/faces/sampling.py
"""

from typing import Iterable, List, Optional


def _dedupe_sorted(values: Iterable[float], ndigits: int = 3) -> List[float]:
    """Deduplicate and sort a sequence of floats, rounding to ``ndigits``."""
    seen: set[float] = set()
    result: List[float] = []
    for value in sorted(values):
        key = round(value, ndigits)
        if key in seen:
            continue
        seen.add(key)
        result.append(float(key))
    return result


def sample_timestamps(
    duration_s: float,
    fps: float = 1.0,
    scene_boundaries_s: Optional[Iterable[float]] = None,
    boundary_window_s: float = 0.5,
) -> List[float]:
    """Return a sorted, deduplicated list of sample timestamps (seconds).

    Generates timestamps at uniform ``fps`` intervals over ``[0, duration_s]``.
    If ``scene_boundaries_s`` are provided, extra samples are added around each
    boundary (at offsets of ``-w``, ``-w/2``, ``0``, ``+w/2``, ``+w`` where
    ``w = boundary_window_s``).

    Args:
        duration_s: Total video duration in seconds.  Must be > 0.
        fps: Sampling rate in frames per second.  Must be > 0.
        scene_boundaries_s: Optional iterable of scene-change timestamps.
        boundary_window_s: Half-width of the extra-sampling window around
            each boundary (seconds).

    Returns:
        Sorted list of unique timestamps (seconds), rounded to 3 decimals.

    Raises:
        ValueError: If ``fps <= 0`` or ``duration_s < 0``.
    """
    if fps <= 0:
        raise ValueError("fps must be > 0")
    if duration_s < 0:
        raise ValueError("duration_s must be >= 0")
    if duration_s == 0:
        return []

    step = 1.0 / fps
    timestamps: list[float] = []
    t = 0.0
    while t <= duration_s:
        timestamps.append(t)
        t += step

    if scene_boundaries_s:
        offsets = [
            -boundary_window_s,
            -boundary_window_s / 2,
            0.0,
            boundary_window_s / 2,
            boundary_window_s,
        ]
        for boundary in scene_boundaries_s:
            for offset in offsets:
                ts = boundary + offset
                if 0.0 <= ts <= duration_s:
                    timestamps.append(ts)

    return _dedupe_sorted(timestamps)
