"""Pure gating functions for OCR text quality control.

All functions are side-effect-free: no I/O, no network, no filesystem
access.  They operate solely on in-memory data structures.

Gating rules from OCR_MINIMAL_CONTEXT_CONTRACT.md §4:
  G1: Confidence threshold — drop blocks below min_conf
  G2: Min chars — reject text_concat shorter than min_chars
  G3: Noise score — reject if >threshold fraction of chars are non-useful
  G4: Max length — clamp ocr_text_raw to max_chars
"""

from __future__ import annotations

import re
from typing import TYPE_CHECKING, Sequence

if TYPE_CHECKING:
    from heimdex_media_contracts.ocr.schemas import OCRBlock

# Matches word characters (ASCII + digits + underscore) plus Hangul syllables
# and Hangul compatibility jamo.
_USEFUL_CHAR_RE = re.compile(r"[\w\u3131-\u318E\uAC00-\uD7A3]")


def filter_blocks_by_confidence(
    blocks: Sequence[OCRBlock],
    min_conf: float = 0.3,
) -> list[OCRBlock]:
    """Return only blocks whose confidence >= min_conf.

    Args:
        blocks: Sequence of OCRBlock objects.
        min_conf: Minimum confidence threshold (inclusive). Default 0.3
            per OCR_MINIMAL_CONTEXT_CONTRACT.md gate G1.

    Returns:
        Filtered list of OCRBlock objects.
    """
    return [b for b in blocks if b.confidence >= min_conf]


def concat_blocks(blocks: Sequence[OCRBlock]) -> str:
    """Space-join block texts, trimmed.

    Args:
        blocks: Sequence of OCRBlock objects.

    Returns:
        Single string of all block texts joined by spaces, stripped.
    """
    texts = [b.text.strip() for b in blocks if b.text.strip()]
    return " ".join(texts)


def is_noise_text(text: str, threshold: float = 0.5) -> bool:
    """Check if text is likely UI chrome / watermark noise.

    Returns True if the ratio of useful characters (word chars + Hangul)
    to total characters is below the threshold.

    Args:
        text: Input text to evaluate.
        threshold: Minimum ratio of useful characters. Default 0.5
            per OCR_MINIMAL_CONTEXT_CONTRACT.md gate G3.

    Returns:
        True if text is noise (should be discarded).
    """
    stripped = text.strip()
    if not stripped:
        return True
    useful_count = len(_USEFUL_CHAR_RE.findall(stripped))
    return useful_count / len(stripped) < threshold


def gate_ocr_text(
    text: str,
    *,
    min_chars: int = 3,
    max_chars: int = 10_000,
    noise_threshold: float = 0.5,
) -> str:
    """Apply all gating rules to OCR text, returning clean text or empty string.

    Pipeline:
      1. Strip whitespace
      2. If empty or too short (< min_chars) → ""
      3. If noise ratio exceeds threshold → ""
      4. Clamp to max_chars

    Args:
        text: Raw OCR text to gate.
        min_chars: Minimum character count after stripping. Default 3
            per OCR_MINIMAL_CONTEXT_CONTRACT.md gate G2.
        max_chars: Maximum character count. Default 10,000
            per OCR_MINIMAL_CONTEXT_CONTRACT.md gate G4.
        noise_threshold: Minimum ratio of useful characters. Default 0.5.

    Returns:
        Gated text string, or empty string if text fails any gate.
    """
    stripped = text.strip()

    # G2: min chars
    if len(stripped) < min_chars:
        return ""

    # G3: noise ratio
    if is_noise_text(stripped, threshold=noise_threshold):
        return ""

    # G4: max length clamp
    if len(stripped) > max_chars:
        stripped = stripped[:max_chars]

    return stripped
