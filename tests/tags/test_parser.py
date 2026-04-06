"""Tests for VLM tag output parser."""

import pytest

from heimdex_media_contracts.tags.parser import VLMTagResult, parse_vlm_tag_output
from heimdex_media_contracts.tags.vocabulary import VALID_KEYWORD_TAGS, VALID_PRODUCT_TAGS


class TestCleanVLMOutput:
    """Well-formatted VLM output."""

    def test_full_output(self):
        text = (
            "설명: 호스트가 운동화를 들고 디자인을 보여주고 있다\n"
            "콘텐츠태그: swatch_test, texture_show, product_demo\n"
            "상품태그: shoes\n"
            "상품명: 에어맥스, 나이키 러닝화"
        )
        result = parse_vlm_tag_output(text)
        assert result.parse_success is True
        assert result.caption == "호스트가 운동화를 들고 디자인을 보여주고 있다"
        assert result.keyword_tags == ["swatch_test", "texture_show", "product_demo"]
        assert result.product_tags == ["shoes"]
        assert result.product_entities == ["에어맥스", "나이키 러닝화"]

    def test_multiple_product_tags(self):
        text = (
            "설명: 메이크업 세트를 보여주고 있다\n"
            "콘텐츠태그: bundle_deal, packaging_show\n"
            "상품태그: makeup, skincare\n"
            "상품명: 쿠션, 세럼"
        )
        result = parse_vlm_tag_output(text)
        assert result.product_tags == ["makeup", "skincare"]

    def test_no_entities(self):
        text = (
            "설명: 라이브 방송 오프닝\n"
            "콘텐츠태그: live_reaction\n"
            "상품태그: \n"
            "상품명: 없음"
        )
        result = parse_vlm_tag_output(text)
        assert result.parse_success is True
        assert result.keyword_tags == ["live_reaction"]
        assert result.product_tags == []
        assert result.product_entities == []

    def test_korean_comma_separator(self):
        text = (
            "설명: 가격 안내\n"
            "콘텐츠태그: price_announce、discount_offer\n"
            "상품태그: food\n"
            "상품명: 김치"
        )
        result = parse_vlm_tag_output(text)
        assert result.keyword_tags == ["price_announce", "discount_offer"]


class TestNoPrefixOutput:
    """VLM output when prompt ends with '설명:' and model continues directly."""

    def test_caption_without_prefix(self):
        text = (
            "호스트가 제모기를 들고 기능을 설명하고 있다\n"
            "콘텐츠태그: product_demo, tutorial\n"
            "상품태그: beauty_device\n"
            "상품명: 라피타 제모기"
        )
        result = parse_vlm_tag_output(text)
        assert result.parse_success is True
        assert result.caption == "호스트가 제모기를 들고 기능을 설명하고 있다"
        assert result.keyword_tags == ["product_demo", "tutorial"]
        assert result.product_tags == ["beauty_device"]
        assert result.product_entities == ["라피타 제모기"]

    def test_caption_only_no_tags(self):
        text = "호스트가 카메라를 보며 인사하고 있다"
        result = parse_vlm_tag_output(text)
        assert result.caption == "호스트가 카메라를 보며 인사하고 있다"
        assert result.keyword_tags == []


class TestMalformedOutput:
    """VLM produces imperfect output."""

    def test_extra_whitespace(self):
        text = (
            "설명:  호스트가 제품을 들고 있다  \n"
            "콘텐츠태그:  product_demo ,  price_announce  \n"
            "상품태그:  electronics  \n"
            "상품명:  에어팟  "
        )
        result = parse_vlm_tag_output(text)
        assert result.parse_success is True
        assert result.keyword_tags == ["product_demo", "price_announce"]
        assert result.product_tags == ["electronics"]

    def test_missing_tag_lines(self):
        text = "설명: 호스트가 이야기하고 있다"
        result = parse_vlm_tag_output(text)
        assert result.parse_success is False  # no tags = not a successful structured parse
        assert result.caption == "호스트가 이야기하고 있다"
        assert result.keyword_tags == []
        assert result.product_tags == []

    def test_full_colon_variant(self):
        text = (
            "설명： 호스트가 제품을 설명하고 있다\n"
            "콘텐츠태그： tutorial\n"
            "상품태그： haircare\n"
            "상품명： 샴푸"
        )
        result = parse_vlm_tag_output(text)
        assert result.parse_success is True
        assert result.keyword_tags == ["tutorial"]

    def test_reordered_lines(self):
        text = (
            "콘텐츠태그: product_demo\n"
            "설명: 제품을 보여주고 있다\n"
            "상품명: 립스틱\n"
            "상품태그: makeup"
        )
        result = parse_vlm_tag_output(text)
        assert result.parse_success is True
        assert result.caption == "제품을 보여주고 있다"
        assert result.keyword_tags == ["product_demo"]
        assert result.product_tags == ["makeup"]


class TestTagValidation:
    """Unknown and duplicate tags are handled."""

    def test_unknown_tags_dropped(self):
        text = (
            "설명: 캡션\n"
            "콘텐츠태그: product_demo, fake_tag, nonexistent\n"
            "상품태그: skincare, unknown_category"
        )
        result = parse_vlm_tag_output(text)
        assert result.keyword_tags == ["product_demo"]
        assert result.product_tags == ["skincare"]

    def test_duplicate_tags_deduped(self):
        text = (
            "설명: 캡션\n"
            "콘텐츠태그: product_demo, product_demo, tutorial\n"
            "상품태그: skincare, skincare"
        )
        result = parse_vlm_tag_output(text)
        assert result.keyword_tags == ["product_demo", "tutorial"]
        assert result.product_tags == ["skincare"]

    def test_case_insensitive(self):
        text = (
            "설명: 캡션\n"
            "콘텐츠태그: Product_Demo, TUTORIAL\n"
            "상품태그: Skincare"
        )
        result = parse_vlm_tag_output(text)
        assert result.keyword_tags == ["product_demo", "tutorial"]
        assert result.product_tags == ["skincare"]


class TestProductEntities:
    """product_entities parsing and cleanup."""

    def test_entities_capped_at_5(self):
        text = (
            "설명: 캡션\n"
            "콘텐츠태그: product_demo\n"
            "상품태그: skincare\n"
            "상품명: a, b, c, d, e, f, g"
        )
        result = parse_vlm_tag_output(text)
        assert len(result.product_entities) == 5

    def test_none_entity_filtered(self):
        text = (
            "설명: 캡션\n"
            "콘텐츠태그: qna\n"
            "상품태그: \n"
            "상품명: 없음"
        )
        result = parse_vlm_tag_output(text)
        assert result.product_entities == []

    def test_quoted_entities_stripped(self):
        text = (
            "설명: 캡션\n"
            "상품명: \"수분크림\", '세럼'"
        )
        result = parse_vlm_tag_output(text)
        assert result.product_entities == ["수분크림", "세럼"]


class TestRegexFallback:
    """VLM output without expected prefix format."""

    def test_tags_mentioned_in_text(self):
        text = "This scene shows a product_demo with skincare items and a swatch_test"
        result = parse_vlm_tag_output(text)
        assert result.parse_success is True  # tags found via regex scan
        assert "product_demo" in result.keyword_tags
        assert "swatch_test" in result.keyword_tags
        assert "skincare" in result.product_tags

    def test_no_tags_in_text(self):
        text = "호스트가 카메라를 보며 인사하고 있다"
        result = parse_vlm_tag_output(text)
        assert result.parse_success is False
        assert result.keyword_tags == []
        assert result.product_tags == []
        assert result.caption == "호스트가 카메라를 보며 인사하고 있다"


class TestAITags:
    """Free-form AI tag parsing and quality guardrails."""

    def test_ai_tags_extracted(self):
        text = (
            "설명: 호스트가 가방을 들고 수납공간을 보여주고 있다\n"
            "콘텐츠태그: closeup_detail, product_demo\n"
            "상품태그: bag\n"
            "상품명: 캔버스 토트백\n"
            "AI태그: 캔버스백, 수납공간, 데일리백, 숄더스트랩"
        )
        result = parse_vlm_tag_output(text)
        assert result.parse_success is True
        assert result.ai_tags == ["캔버스백", "수납공간", "데일리백", "숄더스트랩"]

    def test_ai_tags_empty_when_missing(self):
        """Backward compat: old VLM output without AI태그 line."""
        text = (
            "설명: 호스트가 제품을 들고 있다\n"
            "콘텐츠태그: product_demo\n"
            "상품태그: skincare\n"
            "상품명: 세럼"
        )
        result = parse_vlm_tag_output(text)
        assert result.ai_tags == []

    def test_ai_tags_max_7(self):
        tags = ", ".join([f"태그{i}" for i in range(10)])
        text = f"설명: 캡션\n콘텐츠태그: product_demo\n상품태그: skincare\nAI태그: {tags}"
        result = parse_vlm_tag_output(text)
        assert len(result.ai_tags) == 7

    def test_ai_tags_length_filter(self):
        text = (
            "설명: 캡션\n"
            "콘텐츠태그: product_demo\n"
            "AI태그: 짧, 적절한태그, 이것은너무긴태그라서열다섯글자를초과합니다"
        )
        result = parse_vlm_tag_output(text)
        # "짧" is 1 char (< 2 min), long tag is > 15 chars
        assert result.ai_tags == ["적절한태그"]

    def test_ai_tags_dedup(self):
        text = (
            "설명: 캡션\n"
            "콘텐츠태그: product_demo\n"
            "AI태그: 수분크림, 수분크림, 보습효과"
        )
        result = parse_vlm_tag_output(text)
        assert result.ai_tags == ["수분크림", "보습효과"]

    def test_ai_tags_dedup_case_preserving(self):
        text = (
            "설명: 캡션\n"
            "콘텐츠태그: product_demo\n"
            "AI태그: BB크림, bb크림, CC크림"
        )
        result = parse_vlm_tag_output(text)
        assert result.ai_tags == ["BB크림", "CC크림"]

    def test_ai_tags_vocab_overlap_removed(self):
        """Tags matching controlled vocabulary Korean display names are dropped."""
        text = (
            "설명: 캡션\n"
            "콘텐츠태그: product_demo\n"
            "상품태그: skincare\n"
            "AI태그: 스킨케어, 제품 시연, 수분감, 촉촉한 피부"
        )
        result = parse_vlm_tag_output(text)
        # "스킨케어" matches skincare display name, "제품 시연" matches product_demo display name
        assert "스킨케어" not in result.ai_tags
        assert "제품 시연" not in result.ai_tags
        assert "수분감" in result.ai_tags
        assert "촉촉한 피부" in result.ai_tags

    def test_ai_tags_none_filtered(self):
        text = (
            "설명: 캡션\n"
            "콘텐츠태그: qna\n"
            "AI태그: 없음"
        )
        result = parse_vlm_tag_output(text)
        assert result.ai_tags == []

    def test_ai_tags_with_fullwidth_colon(self):
        text = (
            "설명: 캡션\n"
            "콘텐츠태그: product_demo\n"
            "AI태그： 보습크림, 피부관리"
        )
        result = parse_vlm_tag_output(text)
        assert result.ai_tags == ["보습크림", "피부관리"]

    def test_ai_tags_whitespace_stripped(self):
        text = (
            "설명: 캡션\n"
            "콘텐츠태그: product_demo\n"
            "AI태그:  수분크림 ,  피부관리  ,  보습  "
        )
        result = parse_vlm_tag_output(text)
        assert result.ai_tags == ["수분크림", "피부관리", "보습"]


class TestEdgeCases:
    def test_empty_string(self):
        result = parse_vlm_tag_output("")
        assert result.parse_success is False
        assert result.caption == ""

    def test_none_like(self):
        result = parse_vlm_tag_output("   ")
        assert result.parse_success is False

    def test_all_tags_in_vocabulary(self):
        """Sanity: every tag in vocabulary is recognized by the parser."""
        for tag in VALID_KEYWORD_TAGS:
            text = f"설명: test\n콘텐츠태그: {tag}"
            result = parse_vlm_tag_output(text)
            assert tag in result.keyword_tags, f"keyword tag {tag} not recognized"

        for tag in VALID_PRODUCT_TAGS:
            text = f"설명: test\n상품태그: {tag}"
            result = parse_vlm_tag_output(text)
            assert tag in result.product_tags, f"product tag {tag} not recognized"
