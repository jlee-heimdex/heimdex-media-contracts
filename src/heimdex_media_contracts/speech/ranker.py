"""Segment importance ranker — pure computation, no I/O.

Migrated from:
  dev-heimdex-for-livecommerce/services/worker/src/domain/speech_segments/ranker.py
"""

from heimdex_media_contracts.speech.schemas import RankedSegment, TaggedSegment

DEFAULT_TAG_WEIGHTS: dict[str, float] = {
    "cta": 1.0,
    "price": 0.9,
    "benefit": 0.7,
    "coupon": 0.7,
    "feature": 0.5,
    "bundle": 0.5,
    "comparison": 0.4,
    "tutorial": 0.4,
    "qna": 0.3,
    "delivery": 0.2,
}


class SegmentRanker:
    """Assign importance ranks to tagged speech segments."""

    def __init__(self, weights: dict[str, float] | None = None):
        self.weights = weights if weights is not None else dict(DEFAULT_TAG_WEIGHTS)

    def _score_segment(self, seg: TaggedSegment) -> float:
        if not seg.tags:
            return 0.0

        weighted_sum = sum(
            self.weights.get(tag, 0.1) * seg.tag_scores.get(tag, 0.0)
            for tag in seg.tags
        )
        max_possible = sum(
            self.weights.get(tag, 0.1)
            for tag in seg.tags
        )
        if max_possible == 0:
            return 0.0

        return min(1.0, weighted_sum / max_possible)

    def rank(self, segments: list[TaggedSegment]) -> list[RankedSegment]:
        scored = [
            (self._score_segment(seg), seg)
            for seg in segments
        ]
        scored.sort(key=lambda pair: pair[0], reverse=True)

        ranked: list[RankedSegment] = []
        for i, (score, seg) in enumerate(scored):
            ranked.append(
                RankedSegment(
                    start=seg.start,
                    end=seg.end,
                    text=seg.text,
                    confidence=seg.confidence,
                    tags=seg.tags,
                    tag_scores=seg.tag_scores,
                    rank=i + 1,
                    importance_score=round(score, 4),
                )
            )
        return ranked
