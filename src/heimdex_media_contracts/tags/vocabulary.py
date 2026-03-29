"""Controlled tag vocabulary for VLM-based scene tagging.

English keys are stored in OpenSearch and used programmatically.
Korean values are display names for the frontend UI.
"""

from __future__ import annotations

# --- Content & Selling Categories (keyword_tags) ---

VLM_KEYWORD_TAGS: dict[str, str] = {
    # Content type
    "product_demo": "제품 시연",
    "product_review": "제품 리뷰",
    "unboxing": "언박싱",
    "tutorial": "사용법/튜토리얼",
    "comparison": "비교",
    "before_after": "비포/애프터",

    # Selling techniques
    "price_announce": "가격 공개",
    "discount_offer": "할인/특가",
    "bundle_deal": "세트/구성 소개",
    "limited_time": "한정 수량/타임딜",
    "coupon_event": "쿠폰/이벤트",
    "free_shipping": "무료배송",
    "gift_with_purchase": "사은품 증정",

    # Audience engagement
    "qna": "질문/답변",
    "viewer_request": "시청자 요청",
    "live_reaction": "실시간 반응",
    "giveaway": "경품 추첨",

    # Presentation style
    "closeup_detail": "클로즈업/디테일",
    "swatch_test": "발색/테스트",
    "ingredient_explain": "성분 설명",
    "texture_show": "제형/텍스처",
    "size_reference": "사이즈 비교",
    "packaging_show": "패키징",
    "wearing_show": "착용/착화",
    "cooking_show": "조리/시식",
}

# --- Product Categories (product_tags) ---

VLM_PRODUCT_TAGS: dict[str, str] = {
    # Beauty
    "skincare": "스킨케어",
    "makeup": "메이크업",
    "haircare": "헤어케어",
    "bodycare": "바디케어",
    "fragrance": "향수/프래그런스",
    "nail": "네일",
    "beauty_device": "뷰티 디바이스",

    # Fashion
    "clothing": "의류",
    "shoes": "신발",
    "bag": "가방",
    "accessories": "액세서리/주얼리",

    # Living
    "food": "식품",
    "health_supplement": "건강식품/영양제",
    "home_appliance": "가전",
    "kitchenware": "주방용품",
    "interior": "인테리어/리빙",
    "pet": "반려동물",

    # Digital / Kids
    "electronics": "전자기기",
    "mobile_acc": "모바일 액세서리",
    "kids": "유아/아동",
}

VALID_KEYWORD_TAGS: frozenset[str] = frozenset(VLM_KEYWORD_TAGS)
VALID_PRODUCT_TAGS: frozenset[str] = frozenset(VLM_PRODUCT_TAGS)

# Combined lookup for display names
ALL_TAG_LABELS: dict[str, str] = {**VLM_KEYWORD_TAGS, **VLM_PRODUCT_TAGS}
