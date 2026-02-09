"""Tests for heimdex_media_contracts.speech.tagger — keyword-based tagging.

This replaces the stale test at:
  dev-heimdex-for-livecommerce/services/worker/.../test_speech_tagger.py
which had incorrect constructor params and wrong default category assertions.
"""

import pytest

from heimdex_media_contracts.speech.schemas import SpeechSegment, TaggedSegment
from heimdex_media_contracts.speech.tagger import (
    DEFAULT_KEYWORD_DICT,
    SpeechTagger,
)


class TestSpeechTaggerInit:
    def test_default_categories(self):
        tagger = SpeechTagger()
        assert len(tagger.tag_categories) > 0
        # Actual defaults are: price, benefit, feature, bundle, cta
        assert "price" in tagger.tag_categories
        assert "benefit" in tagger.tag_categories
        assert "cta" in tagger.tag_categories

    def test_custom_keyword_dict(self):
        custom = {"promo": ["sale", "discount"], "urgent": ["now", "hurry"]}
        tagger = SpeechTagger(keyword_dict=custom)
        assert tagger.tag_categories == ["promo", "urgent"]

    def test_min_score_threshold_default(self):
        tagger = SpeechTagger()
        assert tagger.min_score_threshold == 0.0


class TestSpeechTaggerTag:
    def test_empty_segments(self):
        tagger = SpeechTagger()
        result = tagger.tag([])
        assert result == []

    def test_single_segment_no_match(self):
        tagger = SpeechTagger()
        seg = SpeechSegment(start=0.0, end=5.0, text="Hello world", confidence=0.95)
        result = tagger.tag([seg])

        assert len(result) == 1
        assert isinstance(result[0], TaggedSegment)
        assert result[0].start == 0.0
        assert result[0].end == 5.0
        assert result[0].text == "Hello world"
        assert result[0].tags == []
        assert result[0].tag_scores == {}

    def test_preserves_original_data(self):
        tagger = SpeechTagger()
        segments = [
            SpeechSegment(start=0.0, end=3.0, text="First", confidence=0.9),
            SpeechSegment(start=3.0, end=6.0, text="Second", confidence=0.85),
        ]
        result = tagger.tag(segments)

        assert len(result) == 2
        assert result[0].confidence == 0.9
        assert result[1].confidence == 0.85

    def test_korean_price_keywords(self):
        tagger = SpeechTagger()
        seg = SpeechSegment(
            start=0.0, end=5.0,
            text="이 제품 가격은 할인 중입니다",
            confidence=0.9,
        )
        result = tagger.tag([seg])

        assert len(result) == 1
        assert "price" in result[0].tags
        assert "price" in result[0].tag_scores
        assert result[0].tag_scores["price"] > 0

    def test_korean_cta_keywords(self):
        tagger = SpeechTagger()
        seg = SpeechSegment(
            start=0.0, end=5.0,
            text="지금 바로 구매하세요",
            confidence=0.9,
        )
        result = tagger.tag([seg])
        assert "cta" in result[0].tags

    def test_multiple_categories_match(self):
        tagger = SpeechTagger()
        seg = SpeechSegment(
            start=0.0, end=5.0,
            # price: "가격", cta: "지금", "구매"
            text="가격이 좋으니 지금 구매하세요",
            confidence=0.9,
        )
        result = tagger.tag([seg])
        assert "price" in result[0].tags
        assert "cta" in result[0].tags

    def test_min_score_threshold_filters(self):
        tagger = SpeechTagger(min_score_threshold=0.5)
        # "가격" matches 1 out of 8 price keywords → score = 0.125 < 0.5
        seg = SpeechSegment(
            start=0.0, end=5.0,
            text="가격",
            confidence=0.9,
        )
        result = tagger.tag([seg])
        assert "price" not in result[0].tags

    def test_score_calculation(self):
        custom = {"test": ["a", "b", "c", "d"]}
        tagger = SpeechTagger(keyword_dict=custom)
        seg = SpeechSegment(start=0.0, end=1.0, text="a b", confidence=1.0)
        result = tagger.tag([seg])
        # 2 out of 4 keywords matched
        assert result[0].tag_scores["test"] == pytest.approx(0.5)


class TestSpeechTaggerAddKeywords:
    def test_add_to_existing_category(self):
        tagger = SpeechTagger()
        original_count = len(tagger.keyword_dict["price"])
        tagger.add_keywords("price", ["세일"])
        assert "세일" in tagger.keyword_dict["price"]
        assert len(tagger.keyword_dict["price"]) == original_count + 1

    def test_add_new_category(self):
        tagger = SpeechTagger()
        assert "promo" not in tagger.tag_categories
        tagger.add_keywords("promo", ["flash", "sale"])
        assert "promo" in tagger.tag_categories
        assert "flash" in tagger.keyword_dict["promo"]

    def test_deduplicates_keywords(self):
        custom = {"test": ["a", "b"]}
        tagger = SpeechTagger(keyword_dict=custom)
        tagger.add_keywords("test", ["a", "c"])  # "a" already exists
        assert len(tagger.keyword_dict["test"]) == 3  # a, b, c


class TestDefaultKeywordDict:
    def test_has_expected_categories(self):
        assert set(DEFAULT_KEYWORD_DICT.keys()) == {
            "price", "benefit", "feature", "bundle", "cta",
        }

    def test_all_values_are_nonempty_lists(self):
        for cat, keywords in DEFAULT_KEYWORD_DICT.items():
            assert isinstance(keywords, list), f"{cat} should be a list"
            assert len(keywords) > 0, f"{cat} should not be empty"
