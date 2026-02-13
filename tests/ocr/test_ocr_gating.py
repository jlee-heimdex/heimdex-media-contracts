import pytest

from heimdex_media_contracts.ocr.gating import (
    concat_blocks,
    filter_blocks_by_confidence,
    gate_ocr_text,
    is_noise_text,
)
from heimdex_media_contracts.ocr.schemas import OCRBlock


def _block(text: str, confidence: float) -> OCRBlock:
    return OCRBlock(text=text, confidence=confidence, bbox=[0.0, 0.0, 0.5, 0.5])


class TestFilterBlocksByConfidence:
    def test_filters_below_threshold(self):
        blocks = [_block("a", 0.1), _block("b", 0.5), _block("c", 0.3)]
        result = filter_blocks_by_confidence(blocks, min_conf=0.3)
        assert [b.text for b in result] == ["b", "c"]

    def test_default_threshold_is_0_3(self):
        blocks = [_block("low", 0.29), _block("exact", 0.3), _block("high", 0.9)]
        result = filter_blocks_by_confidence(blocks)
        assert [b.text for b in result] == ["exact", "high"]

    def test_empty_input(self):
        assert filter_blocks_by_confidence([]) == []

    def test_all_below_threshold(self):
        blocks = [_block("a", 0.1), _block("b", 0.2)]
        assert filter_blocks_by_confidence(blocks, min_conf=0.5) == []

    def test_all_above_threshold(self):
        blocks = [_block("a", 0.8), _block("b", 0.9)]
        result = filter_blocks_by_confidence(blocks, min_conf=0.5)
        assert len(result) == 2


class TestConcatBlocks:
    def test_single_block(self):
        assert concat_blocks([_block("hello", 0.9)]) == "hello"

    def test_multiple_blocks(self):
        blocks = [_block("hello", 0.9), _block("world", 0.8)]
        assert concat_blocks(blocks) == "hello world"

    def test_strips_whitespace(self):
        blocks = [_block("  hello  ", 0.9), _block("  world  ", 0.8)]
        assert concat_blocks(blocks) == "hello world"

    def test_empty_text_skipped(self):
        blocks = [_block("hello", 0.9), _block("", 0.5), _block("world", 0.8)]
        assert concat_blocks(blocks) == "hello world"

    def test_whitespace_only_text_skipped(self):
        blocks = [_block("hello", 0.9), _block("   ", 0.5), _block("world", 0.8)]
        assert concat_blocks(blocks) == "hello world"

    def test_empty_input(self):
        assert concat_blocks([]) == ""

    def test_korean_and_price(self):
        blocks = [_block("₩39,900", 0.99), _block("수분크림", 0.97)]
        assert concat_blocks(blocks) == "₩39,900 수분크림"


class TestIsNoiseText:
    def test_empty_string_is_noise(self):
        assert is_noise_text("") is True

    def test_whitespace_only_is_noise(self):
        assert is_noise_text("   ") is True

    def test_symbols_only_is_noise(self):
        assert is_noise_text("---===***") is True

    def test_dots_and_dashes_is_noise(self):
        assert is_noise_text("...---...") is True

    def test_korean_text_is_not_noise(self):
        assert is_noise_text("수분크림") is False

    def test_price_is_not_noise(self):
        assert is_noise_text("₩39900") is False

    def test_mixed_korean_price_not_noise(self):
        assert is_noise_text("₩39,900 PRODUCT X 수분크림") is False

    def test_english_word_not_noise(self):
        assert is_noise_text("Hello World") is False

    def test_custom_threshold(self):
        assert is_noise_text("a!!", threshold=0.5) is True
        assert is_noise_text("a!!!!", threshold=0.3) is True
        assert is_noise_text("a!!!!!", threshold=0.5) is True

    def test_exactly_at_threshold(self):
        assert is_noise_text("ab", threshold=1.0) is False
        assert is_noise_text("!!", threshold=0.5) is True


class TestGateOCRText:
    def test_empty_string_returns_empty(self):
        assert gate_ocr_text("") == ""

    def test_whitespace_only_returns_empty(self):
        assert gate_ocr_text("   ") == ""

    def test_too_short_returns_empty(self):
        assert gate_ocr_text("ab") == ""

    def test_exactly_min_chars_accepted(self):
        assert gate_ocr_text("abc") == "abc"

    def test_noise_text_returns_empty(self):
        assert gate_ocr_text("---===***!!!") == ""

    def test_valid_korean_price_accepted(self):
        result = gate_ocr_text("₩39,900 수분크림")
        assert result == "₩39,900 수분크림"

    def test_max_length_clamp(self):
        long_text = "가" * 15_000
        result = gate_ocr_text(long_text, max_chars=10_000)
        assert len(result) == 10_000

    def test_strips_leading_trailing_whitespace(self):
        assert gate_ocr_text("  hello world  ") == "hello world"

    def test_custom_min_chars(self):
        assert gate_ocr_text("ab", min_chars=2) == "ab"
        assert gate_ocr_text("a", min_chars=2) == ""

    def test_custom_noise_threshold(self):
        assert gate_ocr_text("a!!!!", noise_threshold=0.3) == ""
        assert gate_ocr_text("abc!", noise_threshold=0.1) == "abc!"

    def test_full_pipeline_korean_product(self):
        text = "  ₩39,900 PRODUCT X 수분크림  "
        result = gate_ocr_text(text)
        assert result == "₩39,900 PRODUCT X 수분크림"
        assert len(result) > 3
