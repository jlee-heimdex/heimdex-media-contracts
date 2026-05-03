"""Versioned LLM prompts for the product-enumeration step.

Per plan §9 rule 5, prompts live in ``heimdex_media_contracts`` (not in
worker code) so a prompt bump is a contracts release plus an env-var
flip, not a coordinated worker redeploy. Workers read these constants
at startup and tag every emitted ``ProductCatalogEntry`` with the
``VERSION`` they used so the API can detect drift.

Bumping ``VERSION`` is gated on the staging-goldens calibration run:
the eval harness in
``services/api/scripts/eval_shorts_auto_product.py`` MUST be re-run
against the goldens at ``services/api/tests/shorts_auto_product/eval/
goldens/`` and metrics must not regress before the new version is
allowed to ship to staging — and a second eval run is required before
the prod rollout flag flips.

These prompts are intentionally English even though the source content
is Korean — gpt-4o-mini's instruction-following on English system
prompts is empirically more stable than on Korean prompts of similar
specificity. The product *labels* the model returns can be Korean.
"""

from __future__ import annotations


class EnumerationPrompt:
    """LLM enumeration prompt — system + user template, versioned.

    Calibration target on staging goldens (gates prod rollout):
    - Recall:    ≥ 0.85 on hand-curated devorg goldens
    - Precision: ≥ 0.80 on the same goldens

    If gpt-4o-mini cannot meet these on Korean livecommerce content,
    the locked decision says fall back to gpt-4o, NOT relax the gates.
    """

    VERSION = "v1.0"

    SYSTEM = (
        "You are an assistant analyzing keyframes from a Korean live-commerce "
        "video stream. Your job is to enumerate the distinct products being "
        "promoted in the segment — every item that the show is selling, "
        "showcasing, or featuring.\n"
        "\n"
        "INCLUDE products that match ANY of these patterns:\n"
        "- Items being held, demonstrated, worn, applied, opened, or "
        "  referenced by the host as the subject of the segment.\n"
        "- Items clearly displayed/staged on a showcase table, demo stand, or "
        "  product layout that's visible in the framing — these are the "
        "  segment's product lineup even if no host hand is on them right "
        "  now. Korean live-commerce wide shots routinely fan products across "
        "  a table; treat that whole spread as in-scope.\n"
        "- Packaged consumer goods with visible product packaging (boxes, "
        "  pouches, bottles, tubes, jars) prominently positioned in the frame "
        "  even when the host is off-screen, AS LONG AS they look like sale "
        "  merchandise rather than studio decor.\n"
        "\n"
        "EXCLUDE only these:\n"
        "- Background props that are clearly NOT merchandise (host's water "
        "  bottle, coffee mug, microphone, studio decor, plants, room "
        "  furniture, wall art, generic kitchen towels).\n"
        "- The host's personal accessories (jewelry, watches, glasses, "
        "  smartphones, hair clips) UNLESS they are the segment's product.\n"
        "- Studio equipment (lights, cameras, monitors, cables, teleprompters).\n"
        "- On-screen graphic overlays / chyron banners / sponsor logos burned "
        "  into the video — i.e., not physical items in the scene.\n"
        "- Reflections of products in mirrors, monitors, or other surfaces.\n"
        "- The host's clothing, unless apparel is the explicit category being "
        "  sold in this stream.\n"
        "\n"
        "Calibration: false negatives (missing a real product) hurt the "
        "wizard UI as much as false positives — the user explicitly opened "
        "a product picker because they want the lineup. If a packaged good is "
        "clearly displayed in the showcase area of a livecommerce frame, "
        "include it; do not require it to be in the host's hand.\n"
        "\n"
        "For each product you list, also estimate:\n"
        "- A short label in the source language (Korean) describing the "
        "  product visually (e.g. '핑크 세럼 병', '베이지 스웨터'). Avoid "
        "  brand names unless they are clearly visible in the frame.\n"
        "- A bounding box in xywh pixel coordinates relative to the keyframe.\n"
        "- A confidence in [0, 1] reflecting how certain you are the item "
        "  meets the inclusion rules above.\n"
        "\n"
        "Return strict JSON matching the schema provided in the response "
        "format. Do not include explanations outside the JSON."
    )

    USER_TEMPLATE = (
        "Below are {num_keyframes} keyframes sampled from a Korean live-"
        "commerce video. Each keyframe has a unique scene_id. List the "
        "distinct products visible across all keyframes, deduplicating items "
        "that appear in multiple frames. For each product, attach the "
        "scene_id of the single keyframe where it is shown most clearly "
        "(largest, sharpest, least occluded), and the bbox in that keyframe."
    )


# Mirror of ``EnumerationPrompt.VERSION`` — workers compare this against
# the version supplied in the job payload to detect a stale worker
# image. If they disagree, the worker MUST fail-fast rather than process
# with the wrong prompt.
ENUMERATION_PROMPT_VERSION = EnumerationPrompt.VERSION
