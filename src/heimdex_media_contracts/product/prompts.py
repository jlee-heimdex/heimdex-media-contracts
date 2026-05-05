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


# ----------------------------------------------------------------------
# v0.15.0 — Alias generation prompt
# ----------------------------------------------------------------------


class AliasGenerationPrompt:
    """Per-entry post-hoc prompt for spoken-form alias generation.

    Why a separate prompt class instead of extending
    :class:`EnumerationPrompt`:

    1. **Calibration isolation** — the enumeration prompt is gated
       on staging goldens (recall ≥ 0.85, precision ≥ 0.80). Bumping
       its VERSION forces a re-run of the full eval before prod
       rollout. Alias generation is a different operation with
       different gates (recall on catalog→speech mapping); it
       shouldn't share a versioning lifecycle.

    2. **Input shape differs** — enumeration takes a batch of N
       keyframes per call; alias generation takes a single
       (canonical_crop, llm_label) pair. Same-prompt-different-input
       complicates the API surface.

    3. **Cost** — alias generation is one image + a label per call.
       Bundling with enumeration would force re-enumerating to add
       aliases to existing catalogs.

    Calibration target (gates STT-track prod rollout per
    ``shorts-auto-product-stt-pivot.md``):

    - For ≥0.7 of catalog entries on the validation video set, at
      least one alias must substring-match the host's transcript on
      ≥3 distinct scenes. This is the
      ``mention_recall_per_catalog_entry`` gate.

    Like :class:`EnumerationPrompt`, the system message is English
    even though source content is Korean — gpt-4o-mini's
    instruction-following on English system prompts is empirically
    more stable. The aliases the model returns ARE Korean (the
    expected speech).
    """

    VERSION = "v1.0"

    SYSTEM = (
        "You are an assistant generating spoken-form aliases for a "
        "product detected in a Korean live-commerce video. The product "
        "has a visual label (read off the on-screen packaging by a "
        "vision LLM) but the live host may pronounce, abbreviate, or "
        "transliterate the brand differently. Your job is to enumerate "
        "the alternative ways a Korean live-commerce host would refer "
        "to this product in spoken Korean, so that downstream STT-based "
        "search can find the relevant scenes.\n"
        "\n"
        "GIVE 3-5 aliases covering, in priority order:\n"
        "1. The most likely Korean spoken form of the brand "
        "   (transliterated from any English/Latin text on packaging — "
        "   e.g. 'Dalsim' → '달심', 'Dr.ForHair' → '닥터포헤어', "
        "   'OnRitual' may be heard as '온리츄얼' / '올리주얼').\n"
        "2. Brand-only forms when the label includes a model/variant "
        "   (e.g. 'Dalsim fresh-kitchen 오렌지 주스' → '달심', "
        "   '닥터포헤어 폴리젠 샴푸' → '닥터포헤어' or '폴리젠').\n"
        "3. Category-only generic forms a host would use as the segment "
        "   centers on the product (e.g. '이 클렌즈', '이 주스', "
        "   '이 샴푸', '이 패키지'). Korean livecommerce hosts use "
        "   demonstratives constantly; surface the most likely category "
        "   noun.\n"
        "4. Common abbreviations or product codes IF they are clearly "
        "   visible on the packaging in the image.\n"
        "\n"
        "RULES:\n"
        "- Each alias MUST be a substring-matchable phrase (1-30 chars), "
        "  not a sentence. '이 제품은 정말 좋습니다' is NOT an alias.\n"
        "- Each alias MUST be something a host would plausibly say "
        "  during a livestream segment about this product.\n"
        "- Do NOT include the original ``llm_label`` verbatim — "
        "  callers add it as a search term automatically.\n"
        "- Do NOT include translations to English unless the host "
        "  would actually code-switch (rare in Korean livecommerce).\n"
        "- Lower-case Latin letters (e.g. 'dalsim') is acceptable for "
        "  Romanization variants the host might pronounce in Korean.\n"
        "- If the image clearly shows packaging in a language other "
        "  than Korean / English, mark the brand transliterated to "
        "  Korean as the highest-priority alias.\n"
        "\n"
        "Return strict JSON matching the schema in the response format. "
        "Do not include explanations outside the JSON. If you cannot "
        "generate any plausible aliases (e.g., the image is unreadable), "
        "return an empty list rather than guessing."
    )

    USER_TEMPLATE = (
        "Generate spoken-form aliases for the following product.\n"
        "\n"
        "Product label (from vision LLM reading the packaging): {label}\n"
        "\n"
        "The image attached is the canonical reference crop of this "
        "product. Use it to ground brand transliteration and category "
        "noun choices."
    )


# Mirror of ``AliasGenerationPrompt.VERSION`` — the API persists this
# in ``product_catalog_entries.aliases_prompt_version`` so a future
# prompt bump can target only the stale rows for re-generation.
ALIAS_GENERATION_PROMPT_VERSION = AliasGenerationPrompt.VERSION


# ----------------------------------------------------------------------
# v0.16.0 — Transcript-driven enumeration prompt
# ----------------------------------------------------------------------


class TranscriptEnumerationPrompt:
    """Transcript-only product enumeration — no frames involved.

    Complements :class:`EnumerationPrompt` (vision over keyframes). The
    vision path misses two video classes: banner-heavy intros where the
    keyframe sampler biases toward graphic overlays, and no-clear-visuals
    verticals like travel commerce (destinations, tours, services that
    aren't physical objects in frame). This prompt enumerates products
    purely from what the host says.

    The two paths run in parallel on the same scan trigger; the API
    merges their catalog outputs by alias overlap. Inline in the API
    process — no GPU, no worker. Cost is ~$0.003/video against
    gpt-4o-mini, roughly 10× cheaper than vision enumeration.

    Why a separate prompt class instead of extending
    :class:`EnumerationPrompt`:

    1. **Input modality differs** — enumeration takes N keyframes;
       transcript enumeration takes a single concatenated text blob.
       Same-prompt-different-input complicates the API surface.

    2. **Calibration story is independent** — vision enumeration is
       gated on visual recall/precision goldens; transcript enumeration
       is gated on mention precision/recall, which is a different
       failure mode (host comparison-mention vs actual SKU).

    3. **Aliases are emitted inline** — unlike vision enumeration which
       produces only a label and requires a separate
       :class:`AliasGenerationPrompt` pass to produce spoken aliases,
       this prompt knows the spoken form directly (it just read the
       transcript) so it returns aliases in the same call. Skips the
       second LLM hop entirely.

    Calibration target on staging goldens (gates prod rollout per
    ``shorts-auto-product-stt-enum-2026-05-06.md``):

    - Mention recall: ≥ 0.75 of ground-truth products surfaced
    - Precision:      ≤ 0.20 false-positive rate (no comparison-brand
      bleed; no generic-category bleed)
    - Quote fidelity: 100% of ``example_quote`` substrings must appear
      verbatim in the source transcript (post-LLM regex check)

    Like :class:`EnumerationPrompt`, the system message is English even
    though source content is Korean — gpt-4o-mini's instruction-following
    on English system prompts is empirically more stable. The labels and
    aliases the model returns ARE Korean.
    """

    VERSION = "v1.0"

    SYSTEM = (
        "You are an assistant analyzing a Korean live-commerce video "
        "transcript to identify the products the host is actively "
        "selling. The transcript is the only signal — there are no "
        "frames in this task. Some live-commerce videos sell physical "
        "goods that are visible on stage; others sell services like "
        "travel packages, subscriptions, or experiences that have no "
        "on-camera object at all. Your job covers both.\n"
        "\n"
        "INCLUDE products that match ALL of these patterns:\n"
        "- The host introduces, prices, demonstrates, recommends, or "
        "  asks viewers to buy the item.\n"
        "- The mention is sustained — at least two sentences worth of "
        "  attention, OR a price is named, OR availability/quantity is "
        "  named.\n"
        "- The host treats the item as a SKU the viewer can purchase, "
        "  not a casual reference. Travel destinations, tour packages, "
        "  subscription tiers, and experiences ALL count when the "
        "  segment is selling them.\n"
        "\n"
        "EXCLUDE these:\n"
        "- Brands the host names only for comparison ('스타벅스보다 "
        "  싸요' does NOT make Starbucks a product; the comparator is "
        "  a foil, not a SKU).\n"
        "- Generic category nouns ('커피', '옷', '스킨케어') unless "
        "  the host clearly anchors to a specific SKU within that "
        "  category in the same passage.\n"
        "- Items mentioned in a single sentence with no price, no "
        "  availability, no demonstration — those are passing "
        "  references, not the segment's product.\n"
        "- Things the host's voice references but disclaims ('이건 "
        "  파는 게 아니고요...'). Honor the disclaimer.\n"
        "- Show sponsors, channel names, or platform branding "
        "  ('오늘도 G쇼핑과 함께해주셔서') — those are show furniture.\n"
        "\n"
        "For each product you list, return:\n"
        "- llm_label: the canonical Korean name as the host says it. "
        "  Prefer the form the host uses most often. For travel-like "
        "  intangibles, use the descriptive phrase the host anchors on "
        "  (e.g., '제주도 5박6일 패키지').\n"
        "- spoken_aliases: 2-5 alternative ways the host actually "
        "  refers to it within the transcript — abbreviations, "
        "  brand-only forms, demonstratives bound to context "
        "  ('이 패키지', '요 제품'), transliteration variants. Each "
        "  alias must be a 1-30 char substring-matchable phrase a host "
        "  plausibly says, NOT a sentence.\n"
        "- first_mention_ms: integer milliseconds, the timestamp of the "
        "  first sustained mention. Use the timestamp marker on the "
        "  transcript line where the host begins talking about this "
        "  product, not earlier passing references.\n"
        "- example_quote: 1-2 sentences VERBATIM from the transcript. "
        "  Must be a substring of the source transcript text — no "
        "  paraphrasing, no summarizing, no joining of separate lines. "
        "  The downstream system will regex-check this; failed checks "
        "  reject the product.\n"
        "- confidence: [0.0, 1.0]. Lower for casual mentions, higher "
        "  when the host names a price, calls out availability, or "
        "  spends sustained attention on the item.\n"
        "\n"
        "Calibration: false positives (extracting a comparison brand or "
        "a generic category mention) are MORE damaging than false "
        "negatives in this pipeline — a vision pass runs in parallel "
        "and catches what you miss. Be conservative. If you cannot "
        "find any products meeting the inclusion criteria, return an "
        "empty products list rather than guessing.\n"
        "\n"
        "Return strict JSON matching the schema in the response format. "
        "Do not include explanations outside the JSON."
    )

    USER_TEMPLATE = (
        "Below is the transcript of a Korean live-commerce video, "
        "ordered chronologically. Each line is prefixed with a "
        "timestamp marker ``[mm:ss]`` indicating when that segment "
        "begins. List the distinct products the host is selling across "
        "the whole transcript, deduplicating across multiple mentions "
        "of the same product.\n"
        "\n"
        "Transcript:\n"
        "{transcript}"
    )


# Mirror of ``TranscriptEnumerationPrompt.VERSION`` — the API persists
# this in the catalog entry's enumeration_prompt_version (or a parallel
# column for the STT path) so a future prompt bump can target only the
# stale rows for re-enumeration. Goldens key on this version.
TRANSCRIPT_ENUMERATION_PROMPT_VERSION = TranscriptEnumerationPrompt.VERSION
