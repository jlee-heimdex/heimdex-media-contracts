"""Mode-aware scorer tests.

Covers:
- Hard filters (HUMAN/PRODUCT eligibility)
- Component math
- Reason population
- Custom weight override
- Determinism on identical inputs
"""

from __future__ import annotations

import pytest

from heimdex_media_contracts.scenes.schemas import SceneDocument
from heimdex_media_contracts.shorts.scorer import (
    MODE_WEIGHTS,
    PRODUCT_MODE_PERSON_WORDS,
    ScoreBreakdown,
    ScoringMode,
    is_eligible_for_mode,
    score_scene_for_mode,
)


def _scene(
    scene_id: str = "vid_scene_000",
    *,
    video_id: str = "vid",
    index: int = 0,
    start_ms: int = 0,
    end_ms: int = 45_000,
    people: list[str] | None = None,
    keyword_tags: list[str] | None = None,
    product_tags: list[str] | None = None,
    product_entities: list[str] | None = None,
    transcript_char_count: int = 0,
    scene_caption: str = "",
) -> SceneDocument:
    return SceneDocument(
        scene_id=scene_id,
        video_id=video_id,
        index=index,
        start_ms=start_ms,
        end_ms=end_ms,
        keyframe_timestamp_ms=(start_ms + end_ms) // 2,
        people_cluster_ids=people or [],
        keyword_tags=keyword_tags or [],
        product_tags=product_tags or [],
        product_entities=product_entities or [],
        transcript_char_count=transcript_char_count,
        scene_caption=scene_caption,
    )


class TestEligibility:
    def test_human_mode_requires_person_cluster_id(self):
        scene = _scene(people=["p1"])
        ok, reason = is_eligible_for_mode(scene, ScoringMode.HUMAN, person_cluster_id=None)
        assert ok is False
        assert reason == "human_mode_requires_person_cluster_id"

    def test_human_mode_rejects_when_target_person_absent(self):
        scene = _scene(people=["p_other"])
        ok, reason = is_eligible_for_mode(scene, ScoringMode.HUMAN, person_cluster_id="p_target")
        assert ok is False
        assert reason == "target_person_not_in_scene"

    def test_human_mode_accepts_when_target_person_present(self):
        scene = _scene(people=["p_target", "p_other"])
        ok, reason = is_eligible_for_mode(scene, ScoringMode.HUMAN, person_cluster_id="p_target")
        assert ok is True
        assert reason is None

    def test_product_mode_rejects_scenes_with_any_person(self):
        scene = _scene(people=["p1"], product_tags=["스킨케어"])
        ok, reason = is_eligible_for_mode(scene, ScoringMode.PRODUCT)
        assert ok is False
        assert reason == "product_mode_excludes_scenes_with_people"

    def test_product_mode_rejects_scenes_without_product_signals(self):
        scene = _scene(people=[], product_tags=[], product_entities=[])
        ok, reason = is_eligible_for_mode(scene, ScoringMode.PRODUCT)
        assert ok is False
        assert reason == "product_mode_requires_product_signals"

    def test_product_mode_accepts_product_entities_only(self):
        scene = _scene(people=[], product_tags=[], product_entities=["세럼"])
        ok, reason = is_eligible_for_mode(scene, ScoringMode.PRODUCT)
        assert ok is True
        assert reason is None

    def test_product_mode_caption_person_word_rejection(self):
        for word in PRODUCT_MODE_PERSON_WORDS:
            scene = _scene(
                people=[],
                product_tags=["스킨케어"],
                scene_caption=f"이 장면에서 {word}가 제품을 보여주고 있다",
            )
            ok, reason = is_eligible_for_mode(scene, ScoringMode.PRODUCT)
            assert ok is False, f"caption with {word!r} should be rejected"
            assert reason == "product_mode_caption_mentions_person"

    def test_product_mode_caption_without_person_words_passes(self):
        scene = _scene(
            people=[],
            product_tags=["스킨케어"],
            scene_caption="제품 패키지를 클로즈업으로 보여주는 장면",
        )
        ok, reason = is_eligible_for_mode(scene, ScoringMode.PRODUCT)
        assert ok is True
        assert reason is None

    def test_both_mode_has_no_hard_filters(self):
        # Even an empty scene is eligible for BOTH; the scorer just gives it a low score.
        scene = _scene()
        ok, reason = is_eligible_for_mode(scene, ScoringMode.BOTH)
        assert ok is True
        assert reason is None


class TestScoreScene:
    def test_human_mode_rejected_returns_zero_with_breakdown(self):
        scene = _scene(people=["p_other"])
        bd = score_scene_for_mode(scene, ScoringMode.HUMAN, person_cluster_id="p_target")
        assert isinstance(bd, ScoreBreakdown)
        assert bd.eligible is False
        assert bd.total == 0.0
        assert bd.rejection_reason == "target_person_not_in_scene"
        assert bd.components == {}
        assert bd.reasons == []

    def test_product_mode_rejected_returns_zero_with_breakdown(self):
        scene = _scene(people=["p1"], product_tags=["스킨케어"])
        bd = score_scene_for_mode(scene, ScoringMode.PRODUCT)
        assert bd.eligible is False
        assert bd.total == 0.0
        assert bd.rejection_reason == "product_mode_excludes_scenes_with_people"

    def test_score_in_unit_interval(self):
        scene = _scene(
            people=["p1"],
            keyword_tags=["cta", "price", "benefit", "product_demo"],
            product_tags=["스킨케어"],
            product_entities=["세럼"],
            transcript_char_count=200,
        )
        for mode in ScoringMode:
            kwargs = {"person_cluster_id": "p1"} if mode == ScoringMode.HUMAN else {}
            bd = score_scene_for_mode(scene, mode, **kwargs)
            assert 0.0 <= bd.total <= 1.0, f"{mode}: {bd.total}"

    def test_components_match_mode_weights_keys(self):
        # Every component returned should be referenced by the mode's
        # weight dict (or be 0 if not weighted in that mode).
        scene = _scene(keyword_tags=["cta"], transcript_char_count=100)
        for mode in ScoringMode:
            kwargs = {"person_cluster_id": None} if mode != ScoringMode.HUMAN else {}
            if mode == ScoringMode.HUMAN:
                # supply matching person to pass eligibility
                scene = _scene(
                    people=["p1"], keyword_tags=["cta"], transcript_char_count=100
                )
                kwargs = {"person_cluster_id": "p1"}
            bd = score_scene_for_mode(scene, mode, **kwargs)
            if not bd.eligible:
                continue
            for component_name in bd.components:
                # component value must be in [0,1]
                assert 0.0 <= bd.components[component_name] <= 1.0

    def test_human_mode_rich_scene_outscores_bare_scene(self):
        rich = _scene(
            scene_id="vid_scene_000",
            people=["p1"],
            keyword_tags=["cta", "price"],
            transcript_char_count=300,
        )
        bare = _scene(scene_id="vid_scene_001", index=1, people=["p1"])
        rich_bd = score_scene_for_mode(rich, ScoringMode.HUMAN, person_cluster_id="p1")
        bare_bd = score_scene_for_mode(bare, ScoringMode.HUMAN, person_cluster_id="p1")
        assert rich_bd.total > bare_bd.total

    def test_product_mode_strong_product_outscores_weak_product(self):
        strong = _scene(
            scene_id="vid_scene_000",
            people=[],
            keyword_tags=["product_demo", "closeup_detail", "price"],
            product_tags=["스킨케어", "메이크업"],
            product_entities=["세럼", "토너"],
            transcript_char_count=200,
        )
        weak = _scene(
            scene_id="vid_scene_001",
            index=1,
            people=[],
            product_tags=["스킨케어"],
        )
        strong_bd = score_scene_for_mode(strong, ScoringMode.PRODUCT)
        weak_bd = score_scene_for_mode(weak, ScoringMode.PRODUCT)
        assert strong_bd.total > weak_bd.total
        assert strong_bd.eligible and weak_bd.eligible

    def test_reasons_populated_with_signal_origins(self):
        scene = _scene(
            people=["p1"],
            keyword_tags=["cta", "product_demo"],
            product_tags=["스킨케어"],
            product_entities=["세럼"],
            transcript_char_count=200,
        )
        bd = score_scene_for_mode(scene, ScoringMode.BOTH)
        # Sales-intent + demo + product reasons should all be present
        joined = " | ".join(bd.reasons)
        assert "sales_intent:cta" in joined
        assert "demo_keywords:product_demo" in joined
        assert "product_tags:스킨케어" in joined
        assert "product_entities:세럼" in joined
        assert "persons_in_scene:1" in joined

    def test_product_mode_reasons_include_no_person_marker(self):
        scene = _scene(people=[], product_tags=["스킨케어"])
        bd = score_scene_for_mode(scene, ScoringMode.PRODUCT)
        assert "no_person_detected" in bd.reasons

    def test_custom_weights_override_mode_defaults(self):
        scene = _scene(
            people=[],
            keyword_tags=["cta"],
            product_tags=["스킨케어"],
            transcript_char_count=100,
        )
        default_bd = score_scene_for_mode(scene, ScoringMode.PRODUCT)
        # Drop everything except product_signal to weight=1.0 → score equals
        # raw product_signal component value.
        custom = {k: 0.0 for k in MODE_WEIGHTS[ScoringMode.PRODUCT]}
        custom["product_signal"] = 1.0
        custom_bd = score_scene_for_mode(
            scene, ScoringMode.PRODUCT, weights=custom
        )
        assert custom_bd.total != default_bd.total
        assert custom_bd.total == round(custom_bd.components["product_signal"], 4)

    def test_determinism_identical_input_identical_output(self):
        scene = _scene(
            people=["p1"],
            keyword_tags=["cta", "price", "product_demo"],
            product_tags=["스킨케어"],
            transcript_char_count=180,
        )
        runs = [score_scene_for_mode(scene, ScoringMode.BOTH) for _ in range(5)]
        assert all(r.total == runs[0].total for r in runs)
        assert all(r.components == runs[0].components for r in runs)
        assert all(r.reasons == runs[0].reasons for r in runs)

    def test_breakdown_roundtrips_through_pydantic(self):
        scene = _scene(people=["p1"], keyword_tags=["cta"])
        bd = score_scene_for_mode(scene, ScoringMode.BOTH)
        data = bd.model_dump()
        restored = ScoreBreakdown(**data)
        assert restored == bd
