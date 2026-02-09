"""Segment importance ranker — pure computation, no I/O.

Migrated from:
  dev-heimdex-for-livecommerce/services/worker/src/domain/speech_segments/ranker.py
"""

from heimdex_media_contracts.speech.schemas import RankedSegment, TaggedSegment


class SegmentRanker:
    """Assign importance ranks to tagged speech segments."""

    def __init__(self, weights: dict[str, float] | None = None):
        self.weights = weights or {
            "highlight": 1.0,
            "important": 0.8,
            "question": 0.6,
            "answer": 0.5,
            "transition": 0.2,
        }

    def rank(self, segments: list[TaggedSegment]) -> list[RankedSegment]:
        """Return *segments* with rank and importance_score assigned.

        .. note:: Ranking logic is a stub — segments are numbered sequentially
           with ``importance_score = 0.0``.  A real implementation will compute
           scores based on tag weights and context.
        """
        ranked: list[RankedSegment] = []
        for i, seg in enumerate(segments):
            ranked.append(
                RankedSegment(
                    start=seg.start,
                    end=seg.end,
                    text=seg.text,
                    confidence=seg.confidence,
                    tags=seg.tags,
                    tag_scores=seg.tag_scores,
                    rank=i + 1,
                    importance_score=0.0,
                )
            )
        return ranked
