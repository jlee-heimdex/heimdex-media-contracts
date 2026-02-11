"""Speech segment schemas, tagger, and ranker — pure logic only."""

from heimdex_media_contracts.speech.ranker import DEFAULT_TAG_WEIGHTS, SegmentRanker
from heimdex_media_contracts.speech.schemas import (
    PipelineResult,
    RankedSegment,
    SpeechSegment,
    TaggedSegment,
)
from heimdex_media_contracts.speech.tagger import (
    DEFAULT_KEYWORD_DICT,
    PRODUCT_KEYWORD_DICT,
    SpeechTagger,
)

__all__ = [
    "SpeechSegment",
    "TaggedSegment",
    "RankedSegment",
    "PipelineResult",
    "DEFAULT_KEYWORD_DICT",
    "PRODUCT_KEYWORD_DICT",
    "DEFAULT_TAG_WEIGHTS",
    "SpeechTagger",
    "SegmentRanker",
]
