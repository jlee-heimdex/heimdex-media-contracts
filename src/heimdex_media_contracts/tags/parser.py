"""Parse VLM output into structured tags.

The VLM produces line-based output in this format::

    설명: 호스트가 수분크림을 손등에 발라 텍스처를 보여주고 있다
    콘텐츠태그: swatch_test, texture_show, product_demo
    상품태그: skincare
    상품명: 수분크림, 히알루론산 세럼

This module parses that output into validated tag lists.
All functions are pure — no I/O, no side effects.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

from heimdex_media_contracts.tags.vocabulary import (
    VALID_KEYWORD_TAGS,
    VALID_PRODUCT_TAGS,
)

_MAX_ENTITIES = 5

# Line prefixes (Korean keys from the VLM prompt)
_CAPTION_PREFIX = re.compile(r"^설명\s*[:：]\s*", re.MULTILINE)
_KEYWORD_PREFIX = re.compile(r"^콘텐츠태그\s*[:：]\s*", re.MULTILINE)
_PRODUCT_PREFIX = re.compile(r"^상품태그\s*[:：]\s*", re.MULTILINE)
_ENTITY_PREFIX = re.compile(r"^상품명\s*[:：]\s*", re.MULTILINE)


@dataclass
class VLMTagResult:
    """Parsed result from VLM tag output."""

    caption: str = ""
    keyword_tags: list[str] = field(default_factory=list)
    product_tags: list[str] = field(default_factory=list)
    product_entities: list[str] = field(default_factory=list)
    parse_success: bool = False


def parse_vlm_tag_output(raw_text: str) -> VLMTagResult:
    """Parse VLM output into structured tags.

    Parsing strategy (ordered by reliability):
      1. Line-based: split on newlines, match Korean prefixes.
      2. Regex fallback: search for tag keys anywhere in text.
      3. Empty result with ``parse_success=False``.

    All returned ``keyword_tags`` and ``product_tags`` are validated
    against the controlled vocabulary.  Unknown tags are dropped.
    ``product_entities`` are passed through with basic cleanup.

    Args:
        raw_text: Raw text output from the VLM.

    Returns:
        Parsed and validated :class:`VLMTagResult`.
    """
    if not raw_text or not raw_text.strip():
        return VLMTagResult()

    text = raw_text.strip()

    # --- Strategy 1: line-based parsing ---
    caption = _extract_line(_CAPTION_PREFIX, text)
    keyword_raw = _extract_line(_KEYWORD_PREFIX, text)
    product_raw = _extract_line(_PRODUCT_PREFIX, text)
    entity_raw = _extract_line(_ENTITY_PREFIX, text)

    keyword_tags = _validate_tags(_parse_comma_list(keyword_raw), VALID_KEYWORD_TAGS)
    product_tags = _validate_tags(_parse_comma_list(product_raw), VALID_PRODUCT_TAGS)
    product_entities = _clean_entities(_parse_comma_list(entity_raw))

    # If we got at least a caption, consider it a successful parse
    if caption:
        return VLMTagResult(
            caption=caption,
            keyword_tags=keyword_tags,
            product_tags=product_tags,
            product_entities=product_entities,
            parse_success=True,
        )

    # --- Strategy 2: regex fallback ---
    # VLM may have produced tags without the expected prefix format.
    # Try to find any valid tag keys mentioned anywhere in the text.
    keyword_tags = _scan_for_tags(text, VALID_KEYWORD_TAGS)
    product_tags = _scan_for_tags(text, VALID_PRODUCT_TAGS)

    if keyword_tags or product_tags:
        # Use the whole text as caption (best effort)
        first_line = text.split("\n")[0].strip()
        return VLMTagResult(
            caption=first_line,
            keyword_tags=keyword_tags,
            product_tags=product_tags,
            product_entities=[],
            parse_success=False,  # partial parse
        )

    # --- Strategy 3: nothing parseable ---
    # Return the raw text as caption, no tags
    first_line = text.split("\n")[0].strip()
    return VLMTagResult(
        caption=first_line,
        keyword_tags=[],
        product_tags=[],
        product_entities=[],
        parse_success=False,
    )


def _extract_line(prefix_re: re.Pattern[str], text: str) -> str:
    """Extract the value after a prefix on its line."""
    match = prefix_re.search(text)
    if not match:
        return ""
    start = match.end()
    # Find end of line
    newline = text.find("\n", start)
    if newline == -1:
        return text[start:].strip()
    return text[start:newline].strip()


def _parse_comma_list(raw: str) -> list[str]:
    """Split comma/space separated values into a list of stripped tokens."""
    if not raw:
        return []
    # Handle both comma and Korean comma (、)
    parts = re.split(r"[,、]\s*", raw)
    return [p.strip() for p in parts if p.strip()]


def _validate_tags(candidates: list[str], valid: frozenset[str]) -> list[str]:
    """Keep only tags that exist in the valid set. Case-insensitive, deduped."""
    seen: set[str] = set()
    result: list[str] = []
    for tag in candidates:
        key = tag.lower().strip()
        if key in valid and key not in seen:
            seen.add(key)
            result.append(key)
    return result


def _clean_entities(raw_entities: list[str]) -> list[str]:
    """Clean and deduplicate product entity strings."""
    if not raw_entities:
        return []
    seen: set[str] = set()
    result: list[str] = []
    for entity in raw_entities:
        cleaned = entity.strip().strip('"\'')
        if not cleaned or cleaned == "없음" or cleaned == "none":
            continue
        if cleaned not in seen:
            seen.add(cleaned)
            result.append(cleaned)
        if len(result) >= _MAX_ENTITIES:
            break
    return result


def _scan_for_tags(text: str, valid: frozenset[str]) -> list[str]:
    """Scan text for any valid tag keys (word boundary match)."""
    found: list[str] = []
    text_lower = text.lower()
    for tag in sorted(valid):  # sorted for deterministic output
        # Match as whole word (surrounded by non-alphanumeric or string boundary)
        if re.search(rf"(?<![a-z_]){re.escape(tag)}(?![a-z_])", text_lower):
            found.append(tag)
    return found
