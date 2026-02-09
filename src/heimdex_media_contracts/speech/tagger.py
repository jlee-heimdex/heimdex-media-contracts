"""Keyword-based speech segment tagger — pure string matching, no I/O.

Migrated from:
  dev-heimdex-for-livecommerce/services/worker/src/domain/speech_segments/tagger.py
"""

from heimdex_media_contracts.speech.schemas import SpeechSegment, TaggedSegment


# Category keyword dictionaries (Korean live-commerce domain)
DEFAULT_KEYWORD_DICT: dict[str, list[str]] = {
    "price": ["가격", "원", "할인", "쿠폰", "특가", "무료배송", "퍼센트", "프로"],
    "benefit": ["혜택", "증정", "사은품", "적립", "포인트"],
    "feature": ["기능", "효과", "성분", "사용", "지속력", "개선", "제형", "함유", "포함"],
    "bundle": ["구성", "세트", "1+1", "묶음", "용량", "리필", "본품"],
    "cta": ["지금", "바로", "구매", "링크", "장바구니", "라이브", "방송"],
}


class SpeechTagger:
    """Keyword-dictionary-based speech segment tagger."""

    def __init__(
        self,
        keyword_dict: dict[str, list[str]] | None = None,
        min_score_threshold: float = 0.0,
    ):
        """
        Args:
            keyword_dict: Category-to-keywords mapping. ``None`` uses
                :data:`DEFAULT_KEYWORD_DICT`.
            min_score_threshold: Minimum score (0–1) to assign a tag.
                0.0 means any single keyword match suffices.
        """
        self.keyword_dict = (
            {k: list(v) for k, v in keyword_dict.items()}
            if keyword_dict is not None
            else {k: list(v) for k, v in DEFAULT_KEYWORD_DICT.items()}
        )
        self.min_score_threshold = min_score_threshold
        self.tag_categories = list(self.keyword_dict.keys())

    def _calculate_tag_scores(self, text: str) -> dict[str, float]:
        """Compute per-category match score for *text*."""
        text_lower = text.lower()
        scores: dict[str, float] = {}

        for category, keywords in self.keyword_dict.items():
            match_count = sum(1 for kw in keywords if kw.lower() in text_lower)
            if match_count > 0:
                scores[category] = match_count / len(keywords)

        return scores

    def _get_tags_from_scores(self, scores: dict[str, float]) -> list[str]:
        """Select tags that exceed the minimum score threshold."""
        tags = [cat for cat, score in scores.items() if score > self.min_score_threshold]
        tags.sort(key=lambda t: scores.get(t, 0), reverse=True)
        return tags

    def tag(self, segments: list[SpeechSegment]) -> list[TaggedSegment]:
        """Assign category tags to each speech segment."""
        tagged: list[TaggedSegment] = []

        for seg in segments:
            tag_scores = self._calculate_tag_scores(seg.text)
            tags = self._get_tags_from_scores(tag_scores)

            tagged.append(
                TaggedSegment(
                    start=seg.start,
                    end=seg.end,
                    text=seg.text,
                    confidence=seg.confidence,
                    tags=tags,
                    tag_scores=tag_scores,
                )
            )

        return tagged

    def add_keywords(self, category: str, keywords: list[str]) -> None:
        """Add keywords to a category (creates the category if new)."""
        if category not in self.keyword_dict:
            self.keyword_dict[category] = []
            self.tag_categories.append(category)

        self.keyword_dict[category].extend(keywords)
        self.keyword_dict[category] = list(set(self.keyword_dict[category]))
