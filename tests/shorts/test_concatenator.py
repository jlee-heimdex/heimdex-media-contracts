"""Concatenator tests.

Covers:
- Empty / all-ineligible input
- Continuous block extension
- Gap-break behavior
- Cherry-pick fallback
- Count cap
- Min duration enforcement
- Chronological output order
- Determinism
- Used-scene exclusion across clips
- Reason aggregation
"""

from __future__ import annotations

import pytest

from heimdex_media_contracts.scenes.schemas import SceneDocument
from heimdex_media_contracts.shorts.concatenator import (
    DEFAULT_MAX_ADJACENT_GAP_MS,
    AutoClip,
    ScoredScene,
    build_clips,
)
from heimdex_media_contracts.shorts.scorer import (
    ScoreBreakdown,
    ScoringMode,
    score_scene_for_mode,
)


def _scene(
    index: int,
    *,
    start_ms: int,
    end_ms: int,
    video_id: str = "vid",
) -> SceneDocument:
    return SceneDocument(
        scene_id=f"{video_id}_scene_{index:03d}",
        video_id=video_id,
        index=index,
        start_ms=start_ms,
        end_ms=end_ms,
        keyframe_timestamp_ms=(start_ms + end_ms) // 2,
    )


def _scored(
    scene: SceneDocument,
    *,
    score: float = 0.5,
    eligible: bool = True,
    reasons: list[str] | None = None,
) -> ScoredScene:
    return ScoredScene(
        scene=scene,
        breakdown=ScoreBreakdown(
            total=score,
            components={},
            reasons=reasons or [],
            eligible=eligible,
            rejection_reason=None if eligible else "test_rejection",
        ),
    )


class TestEmptyAndIneligible:
    def test_empty_input_returns_empty(self):
        assert build_clips([]) == []

    def test_all_ineligible_returns_empty(self):
        scenes = [_scored(_scene(i, start_ms=i * 10_000, end_ms=(i + 1) * 10_000), eligible=False) for i in range(5)]
        assert build_clips(scenes) == []

    def test_zero_count_returns_empty(self):
        scenes = [_scored(_scene(0, start_ms=0, end_ms=60_000), score=0.9)]
        assert build_clips(scenes, count=0) == []


class TestContinuousExtension:
    def test_single_scene_meeting_min_emitted_as_clip(self):
        # 30s scene → meets min_duration_ms=30_000
        s = _scored(_scene(0, start_ms=0, end_ms=30_000), score=0.9)
        clips = build_clips([s], count=1, target_duration_ms=60_000, min_duration_ms=30_000)
        assert len(clips) == 1
        assert clips[0].scene_ids == ["vid_scene_000"]
        assert clips[0].is_continuous is True
        assert clips[0].duration_ms == 30_000

    def test_extends_forward_to_target(self):
        # 6 × 10s scenes back-to-back, target 60s → one continuous clip with all 6
        scenes = [
            _scored(_scene(i, start_ms=i * 10_000, end_ms=(i + 1) * 10_000), score=0.5 + i * 0.01)
            for i in range(6)
        ]
        clips = build_clips(scenes, count=1, target_duration_ms=60_000, min_duration_ms=30_000)
        assert len(clips) == 1
        assert clips[0].is_continuous is True
        # Highest seed is index=5 (score 0.55); algorithm extends forward only — no scene 6 exists
        # Then extends backward to reach target. Should pull in scenes 0..5.
        assert len(clips[0].scene_ids) == 6
        assert clips[0].duration_ms == 60_000

    def test_extends_backward_only_after_forward_exhausted(self):
        # Top-scoring scene is index=4; only one scene after it.
        # Forward gets 4+5 (20s); backward then pulls 3, 2, 1, 0 (or stops at min)
        scenes = []
        for i in range(6):
            score = 0.99 if i == 4 else 0.5
            scenes.append(_scored(_scene(i, start_ms=i * 10_000, end_ms=(i + 1) * 10_000), score=score))
        clips = build_clips(scenes, count=1, target_duration_ms=60_000, min_duration_ms=30_000)
        assert len(clips) == 1
        assert clips[0].is_continuous is True
        assert clips[0].duration_ms >= 30_000

    def test_overshoot_headroom_allows_one_extra_scene(self):
        # 6×11s scenes, target 60s, headroom 10s → 6 scenes = 66s ≤ 70s
        scenes = [
            _scored(_scene(i, start_ms=i * 11_000, end_ms=(i + 1) * 11_000), score=0.5 + i * 0.01)
            for i in range(6)
        ]
        clips = build_clips(
            scenes,
            count=1,
            target_duration_ms=60_000,
            min_duration_ms=30_000,
            overshoot_headroom_ms=10_000,
        )
        assert len(clips) == 1
        # Should hit headroom limit: 6×11 = 66 ≤ 70, 7×11 would be 77 > 70 (but we only have 6 anyway)
        assert clips[0].duration_ms <= 70_000


class TestGapBreaksContinuity:
    def test_gap_above_threshold_breaks_extension(self):
        # Scene 0: 0-10000, Scene 1: 15000-25000 → gap 5000ms > default 2000
        # Two clips should be returned, each containing only one scene.
        scenes = [
            _scored(_scene(0, start_ms=0, end_ms=30_000), score=0.9),
            _scored(_scene(1, start_ms=35_000, end_ms=65_000), score=0.85),
        ]
        clips = build_clips(scenes, count=2, target_duration_ms=60_000, min_duration_ms=30_000)
        assert len(clips) == 2
        for c in clips:
            assert len(c.scene_ids) == 1
            assert c.is_continuous is True  # single-scene clips are trivially continuous

    def test_small_gap_within_threshold_extends(self):
        # Gap of exactly DEFAULT_MAX_ADJACENT_GAP_MS should still extend
        scenes = [
            _scored(_scene(0, start_ms=0, end_ms=15_000), score=0.9),
            _scored(_scene(1, start_ms=15_000 + DEFAULT_MAX_ADJACENT_GAP_MS, end_ms=45_000), score=0.5),
        ]
        clips = build_clips(scenes, count=1, target_duration_ms=60_000, min_duration_ms=30_000)
        assert len(clips) == 1
        assert len(clips[0].scene_ids) == 2
        assert clips[0].is_continuous is True


class TestCherryPick:
    def test_prefer_continuous_true_skips_seed_unable_to_meet_min(self):
        # Top scene is isolated (others far away), and < min duration
        # prefer_continuous=True → should skip and try next seed
        scenes = [
            _scored(_scene(0, start_ms=0, end_ms=10_000), score=0.99),  # 10s, isolated
            _scored(_scene(1, start_ms=100_000, end_ms=140_000), score=0.5),  # 40s
        ]
        clips = build_clips(scenes, count=2, target_duration_ms=60_000, min_duration_ms=30_000, prefer_continuous=True)
        # Top seed (scene 0) can't reach 30s alone, no adjacency. Skipped.
        # Scene 1 alone meets min.
        assert len(clips) == 1
        assert clips[0].scene_ids == ["vid_scene_001"]

    def test_prefer_continuous_false_cherry_picks_to_meet_min(self):
        scenes = [
            _scored(_scene(0, start_ms=0, end_ms=10_000), score=0.99),
            _scored(_scene(1, start_ms=100_000, end_ms=130_000), score=0.5),  # 30s
            _scored(_scene(2, start_ms=200_000, end_ms=215_000), score=0.4),  # 15s
        ]
        clips = build_clips(
            scenes,
            count=1,
            target_duration_ms=60_000,
            min_duration_ms=30_000,
            prefer_continuous=False,
        )
        assert len(clips) == 1
        # Seed = scene 0 (10s). Cherry-pick adds scene 1 (30s) → 40s ≥ 30s min.
        assert "vid_scene_000" in clips[0].scene_ids
        assert "vid_scene_001" in clips[0].scene_ids
        assert clips[0].is_continuous is False


class TestCountCap:
    def test_count_cap_respected(self):
        scenes = [
            _scored(_scene(i, start_ms=i * 50_000, end_ms=i * 50_000 + 35_000), score=0.5 + i * 0.01)
            for i in range(10)
        ]
        clips = build_clips(scenes, count=3, target_duration_ms=60_000, min_duration_ms=30_000)
        assert len(clips) == 3

    def test_returns_fewer_when_corpus_exhausted(self):
        scenes = [_scored(_scene(0, start_ms=0, end_ms=35_000), score=0.9)]
        clips = build_clips(scenes, count=5, target_duration_ms=60_000, min_duration_ms=30_000)
        assert len(clips) == 1


class TestUsedSceneExclusion:
    def test_each_scene_appears_in_at_most_one_clip(self):
        # 10 isolated 35s scenes — each becomes its own clip
        scenes = [
            _scored(_scene(i, start_ms=i * 100_000, end_ms=i * 100_000 + 35_000), score=0.5 + i * 0.01)
            for i in range(10)
        ]
        clips = build_clips(scenes, count=5, target_duration_ms=60_000, min_duration_ms=30_000)
        assert len(clips) == 5
        all_scene_ids = [sid for c in clips for sid in c.scene_ids]
        assert len(all_scene_ids) == len(set(all_scene_ids))


class TestChronologicalOutput:
    def test_clips_sorted_by_source_start_not_score(self):
        # Highest score is scene 5 (last in time). Then scene 0 (first).
        # Output should be ordered by start_ms ascending.
        scenes = [
            _scored(_scene(0, start_ms=0, end_ms=35_000), score=0.7),
            _scored(_scene(5, start_ms=500_000, end_ms=535_000), score=0.99),
            _scored(_scene(2, start_ms=200_000, end_ms=235_000), score=0.5),
        ]
        clips = build_clips(scenes, count=3, target_duration_ms=60_000, min_duration_ms=30_000)
        assert len(clips) == 3
        starts = [c.start_ms for c in clips]
        assert starts == sorted(starts)


class TestDeterminism:
    def test_identical_input_yields_identical_output(self):
        scenes = [
            _scored(_scene(i, start_ms=i * 12_000, end_ms=(i + 1) * 12_000), score=0.5 + (i % 3) * 0.1)
            for i in range(8)
        ]
        runs = [build_clips(scenes, count=3, target_duration_ms=60_000, min_duration_ms=30_000) for _ in range(5)]
        for r in runs[1:]:
            assert r == runs[0]


class TestReasonAggregation:
    def test_reasons_dedup_and_preserve_order_across_members(self):
        s0 = _scored(
            _scene(0, start_ms=0, end_ms=15_000),
            score=0.6,
            reasons=["sales_intent:cta", "product_tags:스킨케어"],
        )
        s1 = _scored(
            _scene(1, start_ms=15_000, end_ms=35_000),
            score=0.7,
            reasons=["sales_intent:cta", "demo_keywords:product_demo"],  # cta repeats
        )
        clips = build_clips([s0, s1], count=1, target_duration_ms=35_000, min_duration_ms=30_000)
        assert len(clips) == 1
        # First reason should be the continuity marker, then deduplicated member reasons.
        assert clips[0].reasons[0].startswith("continuous_block:")
        rest = clips[0].reasons[1:]
        # cta should appear once, in original order
        assert rest.count("sales_intent:cta") == 1
        assert rest.index("sales_intent:cta") < rest.index("demo_keywords:product_demo")


class TestEndToEndWithRealScorer:
    """Glue test: real scorer + concatenator on a representative video."""

    def test_product_mode_filters_then_concatenates(self):
        # Build 8 scenes, mix of person and product.
        # Indexes 0,1: product-only (eligible for PRODUCT)
        # Indexes 2,3: person+product (NOT eligible for PRODUCT)
        # Indexes 4,5: product-only (eligible)
        # Indexes 6,7: person-only (not eligible for PRODUCT)
        scenes = []
        for i in range(8):
            people = ["p1"] if i in (2, 3, 6, 7) else []
            product_tags = ["스킨케어"] if i in (0, 1, 2, 3, 4, 5) else []
            scenes.append(
                SceneDocument(
                    scene_id=f"vid_scene_{i:03d}",
                    video_id="vid",
                    index=i,
                    start_ms=i * 35_000,
                    end_ms=(i + 1) * 35_000 - 5_000,  # 30s scenes, 5s gap
                    keyframe_timestamp_ms=i * 35_000 + 15_000,
                    people_cluster_ids=people,
                    product_tags=product_tags,
                    keyword_tags=["product_demo"] if i in (0, 1, 4, 5) else [],
                    transcript_char_count=120,
                )
            )

        scored = [
            ScoredScene(scene=s, breakdown=score_scene_for_mode(s, ScoringMode.PRODUCT))
            for s in scenes
        ]
        # Use prefer_continuous=False since 5s gaps fall under DEFAULT_MAX_ADJACENT_GAP_MS=2s
        clips = build_clips(
            scored,
            count=3,
            target_duration_ms=60_000,
            min_duration_ms=30_000,
            prefer_continuous=False,
        )

        # Eligible: scenes 0,1,4,5 (4 scenes, 30s each = 120s of eligible content)
        # Should produce up to 2 clips (each ~60s) + maybe a partial third
        assert 1 <= len(clips) <= 3
        # No clip should reference an ineligible scene
        ineligible_ids = {"vid_scene_002", "vid_scene_003", "vid_scene_006", "vid_scene_007"}
        for c in clips:
            assert not (set(c.scene_ids) & ineligible_ids), (
                f"clip {c.scene_ids} contains ineligible scene"
            )
