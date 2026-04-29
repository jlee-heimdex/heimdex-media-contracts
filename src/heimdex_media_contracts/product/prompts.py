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
        "video stream. Your job is to enumerate the distinct products that the "
        "host is actively presenting to viewers — items being held up, "
        "demonstrated, worn, applied, opened, or referenced as the subject of "
        "the segment.\n"
        "\n"
        "Strict exclusion rules — do NOT list any of:\n"
        "- Background props on the desk or shelf that the host is not handling "
        "  (water bottles, mugs, microphones, studio decor, plants).\n"
        "- The host's personal accessories (jewelry, watches, glasses, "
        "  smartphones, hair clips).\n"
        "- Studio equipment (lights, cameras, monitors, cables, teleprompters).\n"
        "- Sponsor logos, banners, or on-screen graphics that contain product "
        "  imagery but are not physical items in the scene.\n"
        "- Reflections of products in mirrors, monitors, or other surfaces.\n"
        "- The host's clothing, unless apparel is the explicit category being "
        "  sold in this stream.\n"
        "\n"
        "When in doubt, exclude. False positives are more expensive than "
        "false negatives in this pipeline — a missed product can be recovered "
        "by a manual rescan, but a noisy product list pollutes the user's "
        "picker UI.\n"
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
