import pytest

from heimdex_media_contracts.speech.schemas import TaggedSegment
from heimdex_media_contracts.speech.ranker import DEFAULT_TAG_WEIGHTS, SegmentRanker


class TestSegmentRankerInit:
    def test_default_weights(self):
        ranker = SegmentRanker()
        assert ranker.weights == DEFAULT_TAG_WEIGHTS

    def test_custom_weights_override_defaults(self):
        custom_weights = {"cta": 2.0, "feature": 0.3}
        ranker = SegmentRanker(weights=custom_weights)
        assert ranker.weights == custom_weights


class TestSegmentRankerScoring:
    def test_cta_scores_higher_than_feature(self):
        ranker = SegmentRanker()
        cta_seg = TaggedSegment(
            start=0.0,
            end=5.0,
            text="Buy now",
            confidence=0.9,
            tags=["cta"],
            tag_scores={"cta": 0.9},
        )
        feature_seg = TaggedSegment(
            start=5.0,
            end=10.0,
            text="Great quality",
            confidence=0.9,
            tags=["feature"],
            tag_scores={"feature": 0.3},
        )
        cta_score = ranker._score_segment(cta_seg)
        feature_score = ranker._score_segment(feature_seg)
        assert cta_score > feature_score

    def test_untagged_segment_scores_zero(self):
        ranker = SegmentRanker()
        seg = TaggedSegment(
            start=0.0,
            end=5.0,
            text="Hello world",
            confidence=0.9,
            tags=[],
            tag_scores={},
        )
        score = ranker._score_segment(seg)
        assert score == 0.0

    def test_all_scores_in_valid_range(self):
        ranker = SegmentRanker()
        segments = [
            TaggedSegment(
                start=0.0,
                end=5.0,
                text="Buy now",
                confidence=0.9,
                tags=["cta"],
                tag_scores={"cta": 0.5},
            ),
            TaggedSegment(
                start=5.0,
                end=10.0,
                text="Great feature",
                confidence=0.9,
                tags=["feature"],
                tag_scores={"feature": 0.3},
            ),
            TaggedSegment(
                start=10.0,
                end=15.0,
                text="Hello",
                confidence=0.9,
                tags=[],
                tag_scores={},
            ),
        ]
        for seg in segments:
            score = ranker._score_segment(seg)
            assert 0.0 <= score <= 1.0

    def test_segments_sorted_by_score_descending(self):
        ranker = SegmentRanker()
        segments = [
            TaggedSegment(
                start=0.0,
                end=5.0,
                text="Feature",
                confidence=0.9,
                tags=["feature"],
                tag_scores={"feature": 0.5},
            ),
            TaggedSegment(
                start=5.0,
                end=10.0,
                text="Buy now",
                confidence=0.9,
                tags=["cta"],
                tag_scores={"cta": 0.8},
            ),
            TaggedSegment(
                start=10.0,
                end=15.0,
                text="Price",
                confidence=0.9,
                tags=["price"],
                tag_scores={"price": 0.6},
            ),
        ]
        ranked = ranker.rank(segments)
        assert ranked[0].rank == 1
        assert ranked[1].rank == 2
        assert ranked[2].rank == 3
        assert ranked[0].importance_score >= ranked[1].importance_score
        assert ranked[1].importance_score >= ranked[2].importance_score

    def test_multi_tag_segment_scores_higher(self):
        ranker = SegmentRanker()
        single_tag = TaggedSegment(
            start=0.0,
            end=5.0,
            text="Buy now",
            confidence=0.9,
            tags=["cta"],
            tag_scores={"cta": 0.5},
        )
        multi_tag = TaggedSegment(
            start=5.0,
            end=10.0,
            text="Buy now at great price",
            confidence=0.9,
            tags=["cta", "price"],
            tag_scores={"cta": 0.8, "price": 0.7},
        )
        single_score = ranker._score_segment(single_tag)
        multi_score = ranker._score_segment(multi_tag)
        assert multi_score > single_score


class TestSegmentRankerRank:
    def test_rank_values_one_indexed(self):
        ranker = SegmentRanker()
        segments = [
            TaggedSegment(
                start=0.0,
                end=5.0,
                text="Buy",
                confidence=0.9,
                tags=["cta"],
                tag_scores={"cta": 0.8},
            ),
            TaggedSegment(
                start=5.0,
                end=10.0,
                text="Feature",
                confidence=0.9,
                tags=["feature"],
                tag_scores={"feature": 0.3},
            ),
        ]
        ranked = ranker.rank(segments)
        assert ranked[0].rank == 1
        assert ranked[1].rank == 2

    def test_empty_input_returns_empty(self):
        ranker = SegmentRanker()
        result = ranker.rank([])
        assert result == []

    def test_preserves_segment_data(self):
        ranker = SegmentRanker()
        seg = TaggedSegment(
            start=1.5,
            end=7.3,
            text="Buy now at sale price",
            confidence=0.92,
            tags=["cta", "price"],
            tag_scores={"cta": 0.6, "price": 0.7},
        )
        ranked = ranker.rank([seg])
        assert len(ranked) == 1
        assert ranked[0].start == 1.5
        assert ranked[0].end == 7.3
        assert ranked[0].text == "Buy now at sale price"
        assert ranked[0].confidence == 0.92
        assert ranked[0].tags == ["cta", "price"]
        assert ranked[0].tag_scores == {"cta": 0.6, "price": 0.7}
