import pytest
from pydantic import ValidationError

from heimdex_media_contracts.shorts.schemas import ShortsCandidate
from heimdex_media_contracts.shorts.scorer import score_scene, select_shorts_candidates
from heimdex_media_contracts.scenes.schemas import SceneDocument


class TestShortsCandidate:
    def test_valid_candidate_construction(self):
        candidate = ShortsCandidate(
            candidate_id="vid_shorts_001",
            video_id="vid",
            scene_ids=["vid_scene_000"],
            start_ms=0,
            end_ms=45000,
        )
        assert candidate.candidate_id == "vid_shorts_001"
        assert candidate.video_id == "vid"
        assert candidate.scene_ids == ["vid_scene_000"]
        assert candidate.start_ms == 0
        assert candidate.end_ms == 45000
        assert candidate.title_suggestion == ""
        assert candidate.reason == ""
        assert candidate.score == 0.0
        assert candidate.tags == []
        assert candidate.product_refs == []
        assert candidate.people_refs == []
        assert candidate.transcript_snippet == ""

    def test_scene_ids_must_be_non_empty(self):
        with pytest.raises(ValidationError, match="scene_ids"):
            ShortsCandidate(
                candidate_id="vid_shorts_001",
                video_id="vid",
                scene_ids=[],
                start_ms=0,
                end_ms=45000,
            )

    def test_end_ms_must_be_gte_start_ms(self):
        with pytest.raises(ValidationError, match="end_ms"):
            ShortsCandidate(
                candidate_id="vid_shorts_001",
                video_id="vid",
                scene_ids=["vid_scene_000"],
                start_ms=45000,
                end_ms=0,
            )

    def test_duration_ms_property(self):
        candidate = ShortsCandidate(
            candidate_id="vid_shorts_001",
            video_id="vid",
            scene_ids=["vid_scene_000"],
            start_ms=10000,
            end_ms=55000,
        )
        assert candidate.duration_ms == 45000

    def test_roundtrip_via_model_dump_and_validate(self):
        original = ShortsCandidate(
            candidate_id="vid_shorts_002",
            video_id="vid",
            scene_ids=["vid_scene_000", "vid_scene_001"],
            start_ms=5000,
            end_ms=50000,
            title_suggestion="Great Product Demo",
            reason="High engagement",
            score=0.85,
            tags=["cta", "price"],
            product_refs=["product_123"],
            people_refs=["person_456"],
            transcript_snippet="Check out this amazing product",
        )
        data = original.model_dump()
        restored = ShortsCandidate(**data)
        assert restored == original
        assert restored.candidate_id == "vid_shorts_002"
        assert restored.score == 0.85


class TestScoreScene:
    def test_scene_with_cta_tags_and_face_presence_scores_higher(self):
        scene_with_tags = SceneDocument(
            scene_id="vid_scene_000",
            video_id="vid",
            index=0,
            start_ms=0,
            end_ms=45000,
            keyframe_timestamp_ms=22500,
            keyword_tags=["cta", "price"],
            people_cluster_ids=["cluster_001"],
            transcript_char_count=100,
        )
        bare_scene = SceneDocument(
            scene_id="vid_scene_001",
            video_id="vid",
            index=1,
            start_ms=0,
            end_ms=45000,
            keyframe_timestamp_ms=22500,
        )
        score_with_tags = score_scene(scene_with_tags)
        score_bare = score_scene(bare_scene)
        assert score_with_tags > score_bare

    def test_scene_with_no_tags_scores_near_zero(self):
        bare_scene = SceneDocument(
            scene_id="vid_scene_000",
            video_id="vid",
            index=0,
            start_ms=0,
            end_ms=45000,
            keyframe_timestamp_ms=22500,
        )
        score = score_scene(bare_scene)
        assert 0.0 <= score < 0.3

    def test_scores_are_in_valid_range(self):
        scene = SceneDocument(
            scene_id="vid_scene_000",
            video_id="vid",
            index=0,
            start_ms=0,
            end_ms=45000,
            keyframe_timestamp_ms=22500,
            keyword_tags=["cta", "price", "benefit"],
            people_cluster_ids=["cluster_001", "cluster_002"],
            transcript_char_count=500,
        )
        score = score_scene(scene)
        assert 0.0 <= score <= 1.0

    def test_custom_weights_override_defaults(self):
        scene = SceneDocument(
            scene_id="vid_scene_000",
            video_id="vid",
            index=0,
            start_ms=0,
            end_ms=45000,
            keyframe_timestamp_ms=22500,
            keyword_tags=["cta"],
            people_cluster_ids=["cluster_001"],
            transcript_char_count=100,
        )
        default_score = score_scene(scene)
        custom_weights = {
            "keyword_density": 0.5,
            "face_presence": 0.5,
            "transcript_richness": 0.0,
            "tag_diversity": 0.0,
            "duration_fitness": 0.0,
        }
        custom_score = score_scene(scene, weights=custom_weights)
        assert default_score != custom_score


class TestSelectShortsCandidates:
    def test_returns_at_most_target_count_candidates(self):
        scenes = [
            SceneDocument(
                scene_id=f"vid_scene_{i:03d}",
                video_id="vid",
                index=i,
                start_ms=i * 50000,
                end_ms=(i + 1) * 50000,
                keyframe_timestamp_ms=i * 50000 + 25000,
                keyword_tags=["cta"] if i % 2 == 0 else [],
                people_cluster_ids=["cluster_001"] if i % 3 == 0 else [],
            )
            for i in range(30)
        ]
        candidates = select_shorts_candidates(scenes, target_count=10)
        assert len(candidates) <= 10

    def test_all_returned_candidates_have_duration_within_range(self):
        scenes = [
            SceneDocument(
                scene_id=f"vid_scene_{i:03d}",
                video_id="vid",
                index=i,
                start_ms=i * 50000,
                end_ms=(i + 1) * 50000,
                keyframe_timestamp_ms=i * 50000 + 25000,
            )
            for i in range(10)
        ]
        min_duration = 30000
        max_duration = 60000
        candidates = select_shorts_candidates(
            scenes,
            target_count=15,
            min_duration_ms=min_duration,
            max_duration_ms=max_duration,
        )
        for candidate in candidates:
            assert min_duration <= candidate.duration_ms <= max_duration

    def test_returns_empty_list_when_no_scenes_fit_duration_filter(self):
        scenes = [
            SceneDocument(
                scene_id=f"vid_scene_{i:03d}",
                video_id="vid",
                index=i,
                start_ms=i * 10000,
                end_ms=(i + 1) * 10000,
                keyframe_timestamp_ms=i * 10000 + 5000,
            )
            for i in range(5)
        ]
        candidates = select_shorts_candidates(
            scenes,
            target_count=15,
            min_duration_ms=30000,
            max_duration_ms=60000,
        )
        assert candidates == []

    def test_candidates_sorted_by_score_descending(self):
        scenes = [
            SceneDocument(
                scene_id=f"vid_scene_{i:03d}",
                video_id="vid",
                index=i,
                start_ms=i * 50000,
                end_ms=(i + 1) * 50000,
                keyframe_timestamp_ms=i * 50000 + 25000,
                keyword_tags=["cta", "price"] if i % 2 == 0 else [],
                people_cluster_ids=["cluster_001"] if i % 3 == 0 else [],
                transcript_char_count=200 if i % 4 == 0 else 0,
            )
            for i in range(10)
        ]
        candidates = select_shorts_candidates(scenes, target_count=15)
        if len(candidates) > 1:
            for i in range(len(candidates) - 1):
                assert candidates[i].score >= candidates[i + 1].score

    def test_candidate_id_format(self):
        scenes = [
            SceneDocument(
                scene_id="vid_scene_000",
                video_id="vid",
                index=0,
                start_ms=0,
                end_ms=50000,
                keyframe_timestamp_ms=25000,
                keyword_tags=["cta"],
            )
        ]
        candidates = select_shorts_candidates(scenes, target_count=15)
        if candidates:
            assert candidates[0].candidate_id.startswith("vid_shorts_")
            parts = candidates[0].candidate_id.split("_shorts_")
            assert len(parts) == 2
            assert parts[0] == "vid"
            assert parts[1].isdigit()
