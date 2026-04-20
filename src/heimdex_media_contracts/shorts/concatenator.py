"""Auto-shorts clip concatenator — pure function over scored scenes.

The concatenator turns a list of mode-scored scenes into ``count`` clips
of approximately ``target_duration_ms`` each, suitable for feeding into
the existing ``CompositionSpec`` render pipeline.

Algorithm (greedy, deterministic):
  1. Sort eligible scenes by score descending; build a chronological index
     for adjacency lookups.
  2. Walk seeds in score order. For each seed, build a clip:
     a. Extend forward to adjacent scenes (gap ≤ ``max_adjacent_gap_ms``)
        until total source duration reaches ``target_duration_ms``.
     b. If still below ``min_duration_ms``, extend backward under the same
        adjacency rule.
     c. If still below min and ``prefer_continuous=False``, cherry-pick
        the next-best non-adjacent eligible scenes until min is reached.
     d. If the clip can't reach min via either path, skip the seed and
        try the next.
  3. Stop at ``count`` clips or when no candidates remain.
  4. Sort emitted clips chronologically by source start so the short
     reads forward in time, regardless of selection order.

This module imports only from `heimdex_media_contracts.scenes.schemas`
and `heimdex_media_contracts.shorts.scorer` — no app.* imports, no I/O.
"""

from __future__ import annotations

from typing import Sequence

from pydantic import BaseModel, Field

from heimdex_media_contracts.scenes.schemas import SceneDocument
from heimdex_media_contracts.shorts.scorer import ScoreBreakdown

DEFAULT_TARGET_DURATION_MS = 60_000
DEFAULT_MIN_DURATION_MS = 30_000

# Two consecutive scenes are considered "continuous" if the gap between
# the previous scene's end and the next scene's start is no greater than
# this. 2s is enough to absorb scene-detector quirks (cuts on speech
# boundaries, brief black frames) without bridging across an ad break or
# a true narrative jump.
DEFAULT_MAX_ADJACENT_GAP_MS = 2_000

# Allow a clip to overshoot the target by this much when it lets us
# include one more strong adjacent scene. Keeps the rendered short
# close to ``target`` while not punishing a 65s "natural" boundary.
DEFAULT_OVERSHOOT_HEADROOM_MS = 10_000


class ScoredScene(BaseModel):
    """Pairing of a SceneDocument with its mode-aware ScoreBreakdown.

    Convenience wrapper so callers can pass a single sequence to the
    concatenator instead of two parallel lists. Pure data — no behavior.
    """

    scene: SceneDocument
    breakdown: ScoreBreakdown


class ClipMember(BaseModel):
    """One scene's contribution to an AutoClip.

    Carries the per-scene span so downstream renderers can emit one
    ``SceneClipSpec`` per scene and pass the ``ShortsRenderService``
    boundary validator (which checks ``clip.start_ms/end_ms`` against
    the *named* scene's span, not the composite clip's span).
    """

    scene_id: str = Field(min_length=1)
    start_ms: int = Field(ge=0)
    end_ms: int = Field(ge=0)
    score: float = Field(ge=0.0, le=1.0)


class AutoClip(BaseModel):
    """A single auto-generated clip composed of one or more adjacent or
    cherry-picked scenes.

    ``duration_ms`` is the SOURCE duration (sum of member scene durations).
    ``start_ms``/``end_ms`` describe the source-time span of the clip's
    chronologically first and last members — for continuous clips this
    equals the contiguous source range; for cherry-picked clips this only
    bounds the selection and does NOT equal duration_ms.

    ``members`` is the authoritative per-scene breakdown for rendering;
    ``scene_ids`` is a convenience mirror preserved for readability and
    backward compat with existing downstream code.

    ``is_continuous`` is True iff every adjacent pair of members has a
    gap ≤ ``max_adjacent_gap_ms``.
    """

    scene_ids: list[str] = Field(min_length=1)
    members: list[ClipMember] = Field(min_length=1)
    start_ms: int = Field(ge=0)
    end_ms: int = Field(ge=0)
    duration_ms: int = Field(ge=0)
    score: float = Field(ge=0.0, le=1.0)
    reasons: list[str] = Field(default_factory=list)
    is_continuous: bool = True


def _filter_eligible(scored: Sequence[ScoredScene]) -> list[ScoredScene]:
    return [s for s in scored if s.breakdown.eligible]


def _aggregate_reasons(members: list[ScoredScene]) -> list[str]:
    """Dedup-preserving merge of per-scene reasons across clip members."""
    seen: set[str] = set()
    out: list[str] = []
    for m in members:
        for r in m.breakdown.reasons:
            if r not in seen:
                seen.add(r)
                out.append(r)
    return out


def _is_continuous(members: list[ScoredScene], max_adjacent_gap_ms: int) -> bool:
    """True iff each consecutive pair (chrono-sorted) has gap ≤ max."""
    if len(members) <= 1:
        return True
    ordered = sorted(members, key=lambda m: (m.scene.start_ms, m.scene.index))
    for i in range(len(ordered) - 1):
        gap = ordered[i + 1].scene.start_ms - ordered[i].scene.end_ms
        if gap > max_adjacent_gap_ms:
            return False
    return True


def build_clips(
    scored: Sequence[ScoredScene],
    *,
    count: int = 5,
    target_duration_ms: int = DEFAULT_TARGET_DURATION_MS,
    min_duration_ms: int = DEFAULT_MIN_DURATION_MS,
    prefer_continuous: bool = True,
    max_adjacent_gap_ms: int = DEFAULT_MAX_ADJACENT_GAP_MS,
    overshoot_headroom_ms: int = DEFAULT_OVERSHOOT_HEADROOM_MS,
) -> list[AutoClip]:
    """Compose up to ``count`` clips from ``scored`` scenes.

    Pure function. Identical inputs produce identical outputs (stable sort
    keys throughout — score+start_ms for selection order, start_ms+index
    for chrono).

    Returns a list with ``len <= count`` — fewer if the eligible corpus
    can't yield ``count`` valid clips.
    """
    if count <= 0:
        return []

    eligible = _filter_eligible(scored)
    if not eligible:
        return []

    # Chrono index for adjacency walks. Tie-break by scene.index so two
    # scenes with the same start_ms (rare but possible after splitter
    # quirks) order deterministically.
    chrono = sorted(eligible, key=lambda m: (m.scene.start_ms, m.scene.index))
    chrono_pos: dict[str, int] = {m.scene.scene_id: i for i, m in enumerate(chrono)}

    # Selection order: best score first, deterministic tie-break by start_ms
    # then scene_id so identical-score scenes don't flip on Python set order.
    by_score = sorted(
        eligible,
        key=lambda m: (-m.breakdown.total, m.scene.start_ms, m.scene.scene_id),
    )

    used: set[str] = set()
    clips: list[AutoClip] = []

    for seed in by_score:
        if len(clips) >= count:
            break
        if seed.scene.scene_id in used:
            continue

        members: list[ScoredScene] = [seed]
        seed_idx = chrono_pos[seed.scene.scene_id]
        right_idx = seed_idx
        left_idx = seed_idx

        def _total_duration() -> int:
            return sum(m.scene.duration_ms for m in members)

        # --- Extend forward (chronologically later) ---
        while _total_duration() < target_duration_ms and right_idx + 1 < len(chrono):
            cand = chrono[right_idx + 1]
            if cand.scene.scene_id in used:
                break
            last = members[-1].scene
            gap = cand.scene.start_ms - last.end_ms
            if gap > max_adjacent_gap_ms:
                break
            if _total_duration() + cand.scene.duration_ms > target_duration_ms + overshoot_headroom_ms:
                break
            members.append(cand)
            right_idx += 1

        # --- Extend backward toward target (symmetric with forward) ---
        # The seed is often a high-scoring scene mid-video; backward extension
        # fills toward the target the same way forward did. Falls out at the
        # same headroom limit.
        while _total_duration() < target_duration_ms and left_idx - 1 >= 0:
            cand = chrono[left_idx - 1]
            if cand.scene.scene_id in used:
                break
            first = members[0].scene
            gap = first.start_ms - cand.scene.end_ms
            if gap > max_adjacent_gap_ms:
                break
            if _total_duration() + cand.scene.duration_ms > target_duration_ms + overshoot_headroom_ms:
                break
            members.insert(0, cand)
            left_idx -= 1

        is_continuous = _is_continuous(members, max_adjacent_gap_ms)

        # --- Cherry-pick fallback when adjacency couldn't fill the clip ---
        if _total_duration() < min_duration_ms and not prefer_continuous:
            existing_ids = {m.scene.scene_id for m in members}
            for cand in by_score:
                if _total_duration() >= min_duration_ms:
                    break
                if cand.scene.scene_id in used or cand.scene.scene_id in existing_ids:
                    continue
                members.append(cand)
                existing_ids.add(cand.scene.scene_id)
                is_continuous = False

        if _total_duration() < min_duration_ms:
            # Couldn't satisfy min duration without violating adjacency or
            # consuming used scenes — skip this seed, try the next.
            continue

        # Sort members chronologically for emission and continuity check.
        members.sort(key=lambda m: (m.scene.start_ms, m.scene.index))
        # Re-verify continuity on final ordering (cherry-pick may have set
        # is_continuous=False but adjacency walk could still have produced
        # a continuous block in some edge cases).
        is_continuous = _is_continuous(members, max_adjacent_gap_ms)

        for m in members:
            used.add(m.scene.scene_id)

        avg_score = round(
            sum(m.breakdown.total for m in members) / len(members), 4
        )
        reasons = _aggregate_reasons(members)
        reasons.insert(
            0,
            f"continuous_block:{len(members)}_scenes" if is_continuous
            else f"cherry_picked:{len(members)}_scenes",
        )

        clips.append(
            AutoClip(
                scene_ids=[m.scene.scene_id for m in members],
                members=[
                    ClipMember(
                        scene_id=m.scene.scene_id,
                        start_ms=m.scene.start_ms,
                        end_ms=m.scene.end_ms,
                        score=m.breakdown.total,
                    )
                    for m in members
                ],
                start_ms=members[0].scene.start_ms,
                end_ms=members[-1].scene.end_ms,
                duration_ms=_total_duration(),
                score=avg_score,
                reasons=reasons,
                is_continuous=is_continuous,
            )
        )

    # Final ordering: chronological by source start so the rendered short
    # reads forward in time regardless of which clip was selected first.
    clips.sort(key=lambda c: (c.start_ms, c.scene_ids[0]))
    return clips
