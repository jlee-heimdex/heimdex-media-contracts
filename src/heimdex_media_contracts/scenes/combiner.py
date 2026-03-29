"""Pure signal combination algorithm for multi-signal scene splitting.

This module contains **no I/O** — it operates entirely on in-memory lists
of :class:`SplitSignal` objects and a :class:`SplitConfig`.

Algorithm overview
------------------
1. Start with visual cuts as primary boundaries.
2. Compute cuts_per_minute.  If below ``sparse_cut_threshold`` and
   ``speech_split_enabled`` is True, activate speech-aware refinement.
3. For each gap between adjacent boundaries that exceeds
   ``target_scene_duration_ms``:
   a. Collect candidate signals (speech pauses, speaker turns) within the gap.
   b. Score each candidate:
      ``signal_weight * strength * proximity_bonus``
      where *proximity_bonus* rewards candidates near the midpoint of the gap.
   c. Greedily pick the highest-scored candidate, insert it, and re-evaluate
      the gap halves.
4. Enforce ``min_scene_duration_ms`` — merge scenes that are too short into
   their longer neighbour.
5. Enforce ``max_scene_duration_ms`` as a hard ceiling — mechanically split
   any remaining over-long scene at fixed intervals.
6. Return sorted boundary timestamps (always starts with 0, ends with
   ``total_duration_ms``).
"""

from __future__ import annotations

from heimdex_media_contracts.scenes.splitting import SplitConfig, SplitSignal

_WEIGHT_BY_SOURCE: dict[str, str] = {
    "visual_cut": "visual_cut_weight",
    "speech_pause": "speech_pause_weight",
    "speaker_turn": "speaker_turn_weight",
}


def combine_signals(
    visual_cuts_ms: list[int],
    speech_pauses: list[SplitSignal] | None = None,
    speaker_turns: list[SplitSignal] | None = None,
    total_duration_ms: int = 0,
    config: SplitConfig | None = None,
) -> list[int]:
    """Merge multi-signal split candidates into final boundary timestamps.

    Args:
        visual_cuts_ms: Timestamps (ms) of detected visual hard cuts.
        speech_pauses: Candidate split points from speech silence gaps.
        speaker_turns: Candidate split points from speaker changes.
        total_duration_ms: Total video duration in ms.
        config: Splitting parameters.  Uses default ``SplitConfig()`` when
            *None*.

    Returns:
        Sorted list of boundary timestamps in ms.  Always starts with 0
        and ends with *total_duration_ms*.
    """
    if total_duration_ms <= 0:
        return []

    cfg = config or SplitConfig()
    speech_pauses = speech_pauses or []
    speaker_turns = speaker_turns or []

    # --- Step 1: seed boundaries with visual cuts ---
    boundaries: set[int] = {0, total_duration_ms}
    for ts in visual_cuts_ms:
        if 0 < ts < total_duration_ms:
            boundaries.add(ts)

    # --- Step 2: decide whether to activate speech splitting ---
    duration_min = total_duration_ms / 60_000
    num_visual_cuts = len(boundaries) - 2  # exclude 0 and total_duration
    cuts_per_min = num_visual_cuts / duration_min if duration_min > 0 else 0

    use_speech = (
        cfg.speech_split_enabled
        and cuts_per_min < cfg.sparse_cut_threshold
        and (speech_pauses or speaker_turns)
    )

    # --- Step 3: greedily fill oversized gaps with speech signals ---
    if use_speech:
        candidates = _collect_candidates(speech_pauses, speaker_turns)
        boundaries = _fill_gaps(
            boundaries, candidates, cfg.target_scene_duration_ms, cfg,
        )

    # --- Step 4: enforce min_scene_duration (merge tiny scenes) ---
    boundaries = _enforce_min_duration(
        sorted(boundaries), cfg.min_scene_duration_ms,
    )

    # --- Step 5: enforce max_scene_duration (hard ceiling) ---
    boundaries = _enforce_max_duration(
        sorted(boundaries), cfg.max_scene_duration_ms,
    )

    return sorted(boundaries)


def _collect_candidates(
    speech_pauses: list[SplitSignal],
    speaker_turns: list[SplitSignal],
) -> list[SplitSignal]:
    """Merge and deduplicate candidates, keeping stronger signal at each ms."""
    by_ts: dict[int, SplitSignal] = {}
    for sig in speech_pauses + speaker_turns:
        existing = by_ts.get(sig.timestamp_ms)
        if existing is None or sig.strength > existing.strength:
            by_ts[sig.timestamp_ms] = sig
    return sorted(by_ts.values(), key=lambda s: s.timestamp_ms)


def _score_candidate(
    sig: SplitSignal,
    gap_start: int,
    gap_end: int,
    target_ms: int,
    config: SplitConfig,
) -> float:
    """Score a candidate split point within a gap.

    Combines signal weight, signal strength, and a proximity bonus that
    rewards candidates near positions that would produce scenes close to
    ``target_ms``.
    """
    weight_attr = _WEIGHT_BY_SOURCE.get(sig.source, "speech_pause_weight")
    signal_weight = getattr(config, weight_attr)

    gap_len = gap_end - gap_start
    if gap_len <= 0:
        return 0.0

    # How close is this split to producing a target-duration left segment?
    ideal_pos = gap_start + target_ms
    distance = abs(sig.timestamp_ms - ideal_pos)
    max_distance = gap_len
    proximity_bonus = 1.0 - (distance / max_distance) if max_distance > 0 else 1.0
    proximity_bonus = max(0.1, proximity_bonus)  # floor so distant candidates aren't zero

    return signal_weight * sig.strength * proximity_bonus


def _fill_gaps(
    boundaries: set[int],
    candidates: list[SplitSignal],
    target_ms: int,
    config: SplitConfig,
) -> set[int]:
    """Greedily insert candidates into gaps exceeding target duration."""
    result = set(boundaries)
    changed = True

    while changed:
        changed = False
        sorted_bounds = sorted(result)

        for i in range(len(sorted_bounds) - 1):
            gap_start = sorted_bounds[i]
            gap_end = sorted_bounds[i + 1]
            gap_len = gap_end - gap_start

            if gap_len <= target_ms:
                continue

            # Find candidates within this gap (excluding boundaries themselves)
            gap_candidates = [
                c for c in candidates
                if gap_start < c.timestamp_ms < gap_end
            ]
            if not gap_candidates:
                continue

            best = max(
                gap_candidates,
                key=lambda c: _score_candidate(c, gap_start, gap_end, target_ms, config),
            )

            result.add(best.timestamp_ms)
            changed = True
            break  # restart scan with updated boundaries

    return result


def _enforce_min_duration(
    sorted_boundaries: list[int],
    min_ms: int,
) -> set[int]:
    """Remove boundaries that create scenes shorter than min_ms.

    Iterates from left to right; when a scene is too short, its end
    boundary is removed (merging it with the next scene).  The first
    and last boundaries (0 and total_duration) are never removed.
    """
    if len(sorted_boundaries) <= 2:
        return set(sorted_boundaries)

    result: list[int] = [sorted_boundaries[0]]

    for boundary in sorted_boundaries[1:-1]:
        if boundary - result[-1] >= min_ms:
            result.append(boundary)
        # else: skip this boundary, merging the scene forward

    result.append(sorted_boundaries[-1])

    # Also check the last scene isn't too short
    if len(result) >= 3 and result[-1] - result[-2] < min_ms:
        result.pop(-2)

    return set(result)


def _enforce_max_duration(
    sorted_boundaries: list[int],
    max_ms: int,
) -> set[int]:
    """Mechanically split any scene exceeding max_ms at fixed intervals."""
    if max_ms <= 0:
        return set(sorted_boundaries)

    result: list[int] = [sorted_boundaries[0]]

    for boundary in sorted_boundaries[1:]:
        while boundary - result[-1] > max_ms:
            result.append(result[-1] + max_ms)
        result.append(boundary)

    return set(result)
