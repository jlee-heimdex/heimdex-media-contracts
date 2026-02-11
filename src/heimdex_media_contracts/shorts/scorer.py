"""Shorts candidate scoring and selection — pure computation, no I/O.

Scoring weights (configurable):
  - keyword_density: CTA/price cue presence     → 0.30
  - face_presence: people_cluster_ids non-empty  → 0.20
  - transcript_richness: chars-per-second        → 0.15
  - tag_diversity: unique tag count              → 0.15
  - duration_fitness: penalty for too short/long → 0.20
"""

from __future__ import annotations

from typing import Sequence

from heimdex_media_contracts.scenes.schemas import SceneDocument
from heimdex_media_contracts.shorts.schemas import ShortsCandidate

DEFAULT_SCORING_WEIGHTS: dict[str, float] = {
    "keyword_density": 0.30,
    "face_presence": 0.20,
    "transcript_richness": 0.15,
    "tag_diversity": 0.15,
    "duration_fitness": 0.20,
}

HIGH_VALUE_TAGS = frozenset({"cta", "price", "benefit", "coupon"})

MIN_DURATION_MS = 30_000
MAX_DURATION_MS = 60_000
IDEAL_DURATION_MS = 45_000
TARGET_CHARS_PER_SEC = 4.0


def score_scene(
    scene: SceneDocument,
    weights: dict[str, float] | None = None,
) -> float:
    w = weights if weights is not None else DEFAULT_SCORING_WEIGHTS
    duration_s = max(scene.duration_ms / 1000.0, 0.001)

    high_value_count = sum(1 for t in scene.keyword_tags if t in HIGH_VALUE_TAGS)
    keyword_score = min(1.0, high_value_count / 3.0)

    face_score = 1.0 if scene.people_cluster_ids else 0.0

    chars_per_sec = scene.transcript_char_count / duration_s
    richness_score = min(1.0, chars_per_sec / TARGET_CHARS_PER_SEC)

    all_tags = set(scene.keyword_tags) | set(scene.product_tags)
    diversity_score = min(1.0, len(all_tags) / 5.0)

    if scene.duration_ms < MIN_DURATION_MS:
        dist = (MIN_DURATION_MS - scene.duration_ms) / MIN_DURATION_MS
        fitness_score = max(0.0, 1.0 - dist)
    elif scene.duration_ms > MAX_DURATION_MS:
        dist = (scene.duration_ms - MAX_DURATION_MS) / MAX_DURATION_MS
        fitness_score = max(0.0, 1.0 - dist)
    else:
        deviation = abs(scene.duration_ms - IDEAL_DURATION_MS) / (MAX_DURATION_MS - MIN_DURATION_MS)
        fitness_score = 1.0 - (deviation * 0.5)

    total = (
        w.get("keyword_density", 0.3) * keyword_score
        + w.get("face_presence", 0.2) * face_score
        + w.get("transcript_richness", 0.15) * richness_score
        + w.get("tag_diversity", 0.15) * diversity_score
        + w.get("duration_fitness", 0.2) * fitness_score
    )
    return round(min(1.0, max(0.0, total)), 4)


def select_shorts_candidates(
    scenes: Sequence[SceneDocument],
    target_count: int = 15,
    min_duration_ms: int = MIN_DURATION_MS,
    max_duration_ms: int = MAX_DURATION_MS,
    weights: dict[str, float] | None = None,
) -> list[ShortsCandidate]:
    scored: list[tuple[float, SceneDocument]] = []
    for scene in scenes:
        if scene.duration_ms < min_duration_ms or scene.duration_ms > max_duration_ms:
            continue
        scored.append((score_scene(scene, weights), scene))

    scored.sort(key=lambda pair: pair[0], reverse=True)

    candidates: list[ShortsCandidate] = []
    for i, (score, scene) in enumerate(scored[:target_count]):
        snippet = scene.transcript_raw[:200] if scene.transcript_raw else ""
        candidates.append(
            ShortsCandidate(
                candidate_id=f"{scene.video_id}_shorts_{i:03d}",
                video_id=scene.video_id,
                scene_ids=[scene.scene_id],
                start_ms=scene.start_ms,
                end_ms=scene.end_ms,
                score=score,
                tags=scene.keyword_tags,
                product_refs=scene.product_tags,
                people_refs=scene.people_cluster_ids,
                transcript_snippet=snippet,
            )
        )
    return candidates
