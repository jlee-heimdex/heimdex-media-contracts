"""Shorts candidate scoring and selection — pure computation, no I/O.

Scoring weights (configurable):
  - keyword_density: CTA/price cue presence     → 0.30
  - face_presence: people_cluster_ids non-empty  → 0.20
  - transcript_richness: chars-per-second        → 0.15
  - tag_diversity: unique tag count              → 0.15
  - duration_fitness: penalty for too short/long → 0.20

Mode-aware extensions for the auto-shorts feature:
  - ``ScoringMode`` (human / product / both)
  - ``MODE_WEIGHTS`` per-mode component weights
  - ``is_eligible_for_mode`` hard filters before scoring
  - ``score_scene_for_mode`` returns ``ScoreBreakdown`` with reasons

The legacy ``score_scene``/``select_shorts_candidates`` API is preserved
unchanged for backward compatibility — auto-shorts uses the new mode-aware
functions exclusively.
"""

from __future__ import annotations

import unicodedata
from enum import Enum
from typing import Sequence

from pydantic import BaseModel, Field

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

# Demo-intent tags from `tags.vocabulary` — these signal scenes where a
# product is being shown / used / explained, regardless of whether a human
# is in frame. Used by product + both modes.
DEMO_TAGS = frozenset(
    {
        "product_demo",
        "closeup_detail",
        "wearing_show",
        "cooking_show",
        "tutorial",
        "unboxing",
    }
)

# Korean nouns that strongly imply a person is being talked about or shown
# in the scene's VLM caption. Used as a defense-in-depth filter in product
# mode for cases where SCRFD missed a small/profile/occluded face but the
# caption still describes a host/model. Subset of high-precision terms only —
# overly broad lists cause false rejections of product-context captions.
PRODUCT_MODE_PERSON_WORDS = frozenset(
    {
        "호스트",
        "진행자",
        "발표자",
        "모델",
        "사람",
        "인물",
    }
)

MIN_DURATION_MS = 30_000
MAX_DURATION_MS = 60_000
IDEAL_DURATION_MS = 45_000
TARGET_CHARS_PER_SEC = 4.0


class ScoringMode(str, Enum):
    """Auto-shorts selection modes.

    - HUMAN: scenes featuring a specified person (hard-filtered to that person)
    - PRODUCT: scenes with no person AND product signals (hard-filtered)
    - BOTH: no hard filters; weighted blend across signals
    """

    HUMAN = "human"
    PRODUCT = "product"
    BOTH = "both"


# Per-mode component weights. Components must match the keys produced by
# ``score_scene_for_mode``. Missing weights default to 0 (component ignored).
MODE_WEIGHTS: dict[ScoringMode, dict[str, float]] = {
    ScoringMode.HUMAN: {
        "high_value_keyword_density": 0.30,
        "transcript_richness": 0.25,
        "tag_diversity": 0.15,
        "demo_keyword_density": 0.15,
        "duration_fitness": 0.15,
    },
    ScoringMode.PRODUCT: {
        "product_signal": 0.35,
        "demo_keyword_density": 0.25,
        "high_value_keyword_density": 0.15,
        "transcript_richness": 0.15,
        "duration_fitness": 0.10,
    },
    ScoringMode.BOTH: {
        "high_value_keyword_density": 0.25,
        "product_signal": 0.20,
        "demo_keyword_density": 0.15,
        "transcript_richness": 0.15,
        "tag_diversity": 0.10,
        "face_presence": 0.10,
        "duration_fitness": 0.05,
    },
}


class ScoreBreakdown(BaseModel):
    """Result of mode-aware scoring with full per-component breakdown.

    ``components`` carries each named signal's [0,1] value before weighting.
    ``reasons`` is a list of human-readable strings describing why the scene
    scored what it did — surfaced to the API consumer for debugging and
    UX transparency.
    ``eligible`` is False when a hard filter rejected the scene; ``total``
    is forced to 0.0 in that case and ``rejection_reason`` carries the
    specific filter that fired.
    """

    total: float = Field(ge=0.0, le=1.0)
    components: dict[str, float] = Field(default_factory=dict)
    reasons: list[str] = Field(default_factory=list)
    eligible: bool = True
    rejection_reason: str | None = None


def is_eligible_for_mode(
    scene: SceneDocument,
    mode: ScoringMode,
    person_cluster_id: str | None = None,
) -> tuple[bool, str | None]:
    """Apply hard mode filters before scoring.

    Returns ``(eligible, rejection_reason)``. The reason is a stable
    machine-readable string the API surfaces in logs and (optionally) to
    the client. Reasons never carry user-supplied data verbatim — keep
    them safe for log indexing.
    """
    if mode == ScoringMode.HUMAN:
        if not person_cluster_id:
            return False, "human_mode_requires_person_cluster_id"
        if person_cluster_id not in scene.people_cluster_ids:
            return False, "target_person_not_in_scene"
        return True, None

    if mode == ScoringMode.PRODUCT:
        if scene.people_cluster_ids:
            return False, "product_mode_excludes_scenes_with_people"
        if not scene.product_tags and not scene.product_entities:
            return False, "product_mode_requires_product_signals"
        # NFC-normalize before substring matching — Korean VLM outputs
        # sometimes arrive in NFD (decomposed jamo) form, where bare `in`
        # containment fails even on visually identical characters. The
        # hard-coded PRODUCT_MODE_PERSON_WORDS are already NFC.
        caption = unicodedata.normalize("NFC", scene.scene_caption or "")
        for word in PRODUCT_MODE_PERSON_WORDS:
            if word in caption:
                return False, "product_mode_caption_mentions_person"
        return True, None

    # BOTH mode applies no hard filters at the scene level.
    return True, None


def _duration_fitness(duration_ms: int) -> float:
    """Gaussian-ish penalty around ``IDEAL_DURATION_MS``.

    Identical math to legacy ``score_scene`` — extracted so the mode-aware
    path can reuse it without copy-pasting and drifting.
    """
    if duration_ms < MIN_DURATION_MS:
        dist = (MIN_DURATION_MS - duration_ms) / MIN_DURATION_MS
        return max(0.0, 1.0 - dist)
    if duration_ms > MAX_DURATION_MS:
        dist = (duration_ms - MAX_DURATION_MS) / MAX_DURATION_MS
        return max(0.0, 1.0 - dist)
    deviation = abs(duration_ms - IDEAL_DURATION_MS) / (MAX_DURATION_MS - MIN_DURATION_MS)
    return 1.0 - (deviation * 0.5)


def score_scene_for_mode(
    scene: SceneDocument,
    mode: ScoringMode,
    person_cluster_id: str | None = None,
    weights: dict[str, float] | None = None,
) -> ScoreBreakdown:
    """Mode-aware per-scene scorer.

    Returns a ``ScoreBreakdown`` rather than a bare float so the API can
    expose component breakdowns and human-readable reasons to the UI
    without re-deriving them.

    Hard filters are applied first via ``is_eligible_for_mode``. Rejected
    scenes return ``total=0.0`` with ``eligible=False``.

    Pure function: identical inputs always produce identical outputs.
    No I/O. Safe to call from any context including the API request path.
    """
    eligible, rejection = is_eligible_for_mode(scene, mode, person_cluster_id)
    if not eligible:
        return ScoreBreakdown(
            total=0.0,
            eligible=False,
            rejection_reason=rejection,
        )

    w = weights if weights is not None else MODE_WEIGHTS[mode]
    duration_s = max(scene.duration_ms / 1000.0, 0.001)

    components: dict[str, float] = {}
    reasons: list[str] = []

    high_value_matches = sorted(t for t in scene.keyword_tags if t in HIGH_VALUE_TAGS)
    components["high_value_keyword_density"] = min(1.0, len(high_value_matches) / 3.0)
    if high_value_matches:
        reasons.append(f"sales_intent:{','.join(high_value_matches)}")

    demo_matches = sorted(t for t in scene.keyword_tags if t in DEMO_TAGS)
    components["demo_keyword_density"] = min(1.0, len(demo_matches) / 3.0)
    if demo_matches:
        reasons.append(f"demo_keywords:{','.join(demo_matches)}")

    product_signal_count = len(scene.product_tags) + len(scene.product_entities)
    components["product_signal"] = min(1.0, product_signal_count / 5.0)
    if scene.product_tags:
        reasons.append(f"product_tags:{','.join(scene.product_tags[:3])}")
    if scene.product_entities:
        reasons.append(f"product_entities:{','.join(scene.product_entities[:3])}")

    components["face_presence"] = 1.0 if scene.people_cluster_ids else 0.0
    if mode == ScoringMode.HUMAN and person_cluster_id:
        reasons.append(f"target_person_present:{person_cluster_id}")
    elif mode == ScoringMode.BOTH and scene.people_cluster_ids:
        reasons.append(f"persons_in_scene:{len(scene.people_cluster_ids)}")
    elif mode == ScoringMode.PRODUCT:
        # Eligibility already guaranteed people_cluster_ids is empty.
        reasons.append("no_person_detected")

    chars_per_sec = scene.transcript_char_count / duration_s
    components["transcript_richness"] = min(1.0, chars_per_sec / TARGET_CHARS_PER_SEC)

    all_tags = set(scene.keyword_tags) | set(scene.product_tags)
    components["tag_diversity"] = min(1.0, len(all_tags) / 5.0)

    components["duration_fitness"] = _duration_fitness(scene.duration_ms)

    total = sum(w.get(name, 0.0) * value for name, value in components.items())
    total = round(min(1.0, max(0.0, total)), 4)

    return ScoreBreakdown(
        total=total,
        components=components,
        reasons=reasons,
        eligible=True,
    )


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
