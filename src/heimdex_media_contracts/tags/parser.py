"""Parse VLM output into structured tags.

The VLM produces line-based output in this format::

    설명: <scene description>
    콘텐츠태그: <keyword_tag1>, <keyword_tag2>
    상품태그: <product_tag1>
    상품명: <product_name1>, <product_name2>
    AI태그: <free_form_tag1>, <free_form_tag2>

This module parses that output into validated tag lists.
All functions are pure — no I/O, no side effects.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

from heimdex_media_contracts.tags.vocabulary import (
    ALL_TAG_LABELS,
    VALID_KEYWORD_TAGS,
    VALID_PRODUCT_TAGS,
)

_MAX_ENTITIES = 5
_MAX_AI_TAGS = 7
_AI_TAG_MIN_LEN = 2
_AI_TAG_MAX_LEN = 15

# Line prefixes (Korean keys from the VLM prompt)
_CAPTION_PREFIX = re.compile(r"^설명\s*[:：]\s*", re.MULTILINE)
_KEYWORD_PREFIX = re.compile(r"^콘텐츠태그\s*[:：]\s*", re.MULTILINE)
_PRODUCT_PREFIX = re.compile(r"^상품태그\s*[:：]\s*", re.MULTILINE)
_ENTITY_PREFIX = re.compile(r"^상품명\s*[:：]\s*", re.MULTILINE)
_AI_TAG_PREFIX = re.compile(r"^AI태그\s*[:：]\s*", re.MULTILINE)


@dataclass
class VLMTagResult:
    """Parsed result from VLM tag output."""

    caption: str = ""
    keyword_tags: list[str] = field(default_factory=list)
    product_tags: list[str] = field(default_factory=list)
    product_entities: list[str] = field(default_factory=list)
    ai_tags: list[str] = field(default_factory=list)
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

    # If no "설명:" prefix found, the VLM may have started directly with
    # the caption text (prompt ended with "설명:" so output continues from there).
    # Use the first line before any tag prefix as the caption.
    if not caption:
        lines = text.split("\n")
        for line in lines:
            stripped = line.strip()
            if not stripped:
                continue
            if (_KEYWORD_PREFIX.match(stripped) or _PRODUCT_PREFIX.match(stripped)
                    or _ENTITY_PREFIX.match(stripped) or _AI_TAG_PREFIX.match(stripped)):
                break
            caption = stripped
            break

    ai_tag_raw = _extract_line(_AI_TAG_PREFIX, text)

    keyword_tags = _validate_tags(_parse_comma_list(keyword_raw), VALID_KEYWORD_TAGS)
    product_tags = _validate_tags(_parse_comma_list(product_raw), VALID_PRODUCT_TAGS)
    product_entities = _clean_entities(_parse_comma_list(entity_raw))
    ai_tags = _clean_ai_tags(_parse_comma_list(ai_tag_raw))

    # If we got at least a caption, consider it a successful parse
    if caption and (keyword_tags or product_tags or product_entities):
        return VLMTagResult(
            caption=caption,
            keyword_tags=keyword_tags,
            product_tags=product_tags,
            product_entities=product_entities,
            ai_tags=ai_tags,
            parse_success=True,
        )
    # --- Strategy 2: regex fallback ---
    # If no structured tags found, scan for any valid tag keys in the text.
    if not keyword_tags and not product_tags:
        keyword_tags = _scan_for_tags(text, VALID_KEYWORD_TAGS)
        product_tags = _scan_for_tags(text, VALID_PRODUCT_TAGS)

    # Return with whatever we found
    if caption:
        return VLMTagResult(
            caption=caption,
            keyword_tags=keyword_tags,
            product_tags=product_tags,
            product_entities=product_entities,
            ai_tags=ai_tags,
            parse_success=bool(keyword_tags or product_tags or product_entities),
        )

    if keyword_tags or product_tags:
        # Use the whole text as caption (best effort)
        first_line = text.split("\n")[0].strip()
        return VLMTagResult(
            caption=first_line,
            keyword_tags=keyword_tags,
            product_tags=product_tags,
            product_entities=[],
            ai_tags=ai_tags,
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
        ai_tags=[],
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


def _clean_ai_tags(raw_tags: list[str]) -> list[str]:
    """Clean, validate, and deduplicate free-form AI tags.

    Guardrails:
      - Strip whitespace
      - Drop empty strings and "없음"/"none"
      - Enforce 2-15 character length per tag
      - Deduplicate (case-preserving, normalized comparison)
      - Drop tags that match controlled vocabulary Korean display names
      - Cap at 7 tags max
    """
    if not raw_tags:
        return []

    # Build set of Korean display names from controlled vocabulary for overlap check
    vocab_display_names = {v.lower() for v in ALL_TAG_LABELS.values()}

    seen: set[str] = set()
    result: list[str] = []
    for tag in raw_tags:
        cleaned = tag.strip()
        if not cleaned or cleaned == "없음" or cleaned.lower() == "none":
            continue
        if len(cleaned) < _AI_TAG_MIN_LEN or len(cleaned) > _AI_TAG_MAX_LEN:
            continue
        normalized = cleaned.lower()
        if normalized in seen:
            continue
        # Drop if it exactly matches a controlled vocabulary display name
        if normalized in vocab_display_names:
            continue
        seen.add(normalized)
        result.append(cleaned)
        if len(result) >= _MAX_AI_TAGS:
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
