"""Pydantic schemas for the auto-shorts product mode v2 pipeline.

Two-stage lazy pipeline:
1. Enumeration — given a video, produce a catalog of distinct products
   (LLM vision + SigLIP2 clustering). Triggered when a user opens the
   "상품 중심" tab on a video that has not been scanned.
2. Tracking + assembly — given a chosen catalog entry, locate every
   qualifying appearance window in the video (SigLIP2 retrieval + SAM2
   mask propagation), score subsets, and emit a stitching plan that
   the existing render pipeline turns into a clip.

Every field is additive — landing this module does not affect any
existing consumer. The API and the two new GPU workers (product-
enumerate-worker, product-track-worker) all import from here.

The pipeline runtime lives in ``heimdex_media_pipelines.product_enum``
and ``heimdex_media_pipelines.product_track``; that package keeps the
torch/transformers/SAM2 dependencies and uses these models at the
worker boundary.

See ``dev-heimdex-for-livecommerce/.claude/plans/shorts-auto-product-v2.md``
for the full design and locked decisions.
"""

from __future__ import annotations

from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator
from pydantic_core.core_schema import ValidationInfo


# ---------- type aliases ----------

ProductScanStage = Literal[
    "queued",
    "enumerating",
    "enumeration_done",
    "tracking",
    "assembling",
    "rendering",
    # v0.14.0 — Phase 4 wizard parent state machine.
    "preview_ready",   # parent waiting on user commit (Phase 6)
    "fanned_out",      # parent waiting on N children to terminate
    "committed",       # parent terminal once all children terminate
    "done",
    "failed",
    "cancelled",
]

# Workers and the API both validate against this set so a stale worker
# can never push the API into an unknown stage.
ALLOWED_SCAN_STAGES: frozenset[str] = frozenset({
    "queued",
    "enumerating",
    "enumeration_done",
    "tracking",
    "assembling",
    "rendering",
    "preview_ready",
    "fanned_out",
    "committed",
    "done",
    "failed",
    "cancelled",
})

# Allowed clip durations in seconds. Plan §1 locked these to 30/60/90
# matching the native lengths on Reels / Shorts / TikTok. v0.14.0
# adds the wizard flow which broadens the range to 10..120 via
# ``length_seconds`` on ``ProductTrackJob`` (see below). The 30/60/90
# preset literal stays for backward compat with the legacy
# enqueue_clip flow during its +4wk deprecation window.
DurationPresetSec = Literal[30, 60, 90]
ALLOWED_DURATION_PRESETS: frozenset[int] = frozenset({30, 60, 90})


# ---------- v0.14.0 wizard discriminators ----------
#
# Phase 4 wizard introduces parent / render-child orchestration on
# top of the legacy enumerate / track flows. The new fields on
# ``ProductTrackJob`` below are guarded by ``ScanMode``:
#
#   mode='enumerate'    → legacy / current behavior; new fields ignored
#   mode='scan_order'   → wizard parent — track the whole catalog
#   mode='render_child' → wizard child — pick a subset + render
#
# All new fields are Optional with None default for backward compat:
# v0.13.0 senders that omit ``mode`` (or set it to 'enumerate') still
# round-trip through v0.14.0 schemas without modification.
ScanMode = Literal["enumerate", "scan_order", "render_child"]
ALLOWED_SCAN_MODES: frozenset[str] = frozenset({
    "enumerate", "scan_order", "render_child",
})

# Wizard-only field — drives the picker in the runner / worker.
ProductDistribution = Literal["single", "multi"]
ALLOWED_PRODUCT_DISTRIBUTIONS: frozenset[str] = frozenset({"single", "multi"})

# Wizard-only field — drives alignment tokenizer choice.
Language = Literal["ko", "en"]
ALLOWED_LANGUAGES: frozenset[str] = frozenset({"ko", "en"})

# Wizard intent — separates preview-flow dedupe from commit-flow dedupe
# in the API's settings_hash keyspace. Persisted on the parent row.
ScanIntent = Literal["preview", "commit"]
ALLOWED_SCAN_INTENTS: frozenset[str] = frozenset({"preview", "commit"})

# Reasons a window or catalog entry was filtered out. Persisted on the
# row so threshold tuning can be done without re-running tracking.
RejectedReason = Literal[
    "too_short",
    "low_confidence",
    "low_prominence",
    "single_keyframe",
    "rescan_invalidated",
    "version_invalidated",
    "admin_reject",
    "low_confidence_global",
]


# ---------- SQS / HTTP message type constants ----------
#
# Match the ``type`` field on the corresponding pydantic model so
# dispatchers can route by message type without duplicating string
# literals.

PRODUCT_ENUMERATE_JOB_TYPE = "product.enumerate_job"
PRODUCT_TRACK_JOB_TYPE = "product.track_job"

PRODUCT_SCAN_PROGRESS_TYPE = "product.scan_progress"
PRODUCT_SCAN_COMPLETED_TYPE = "product.scan_completed"
PRODUCT_SCAN_FAILED_TYPE = "product.scan_failed"


# ---------- bbox primitives ----------

class BBoxXYWH(BaseModel):
    """Pixel-space bounding box in xywh order. Source-frame coordinates."""

    model_config = ConfigDict(extra="forbid")

    x: int = Field(..., ge=0)
    y: int = Field(..., ge=0)
    w: int = Field(..., gt=0)
    h: int = Field(..., gt=0)


# ---------- enumeration output (worker → API) ----------

class EnumerationDetection(BaseModel):
    """One product detection produced by the LLM enumeration step,
    before clustering. Multiple of these may merge into a single
    ``ProductCatalogEntry`` after SigLIP2 clustering deduplicates
    cross-keyframe sightings of the same product.
    """

    model_config = ConfigDict(extra="forbid")

    keyframe_scene_id: str
    keyframe_frame_idx: int = Field(..., ge=0)
    label: str = Field(..., min_length=1, max_length=200)
    bbox: BBoxXYWH
    confidence: float = Field(..., ge=0.0, le=1.0)


class ProductCatalogEntry(BaseModel):
    """One distinct product detected in a video.

    Identity is per-video in v1; cross-video matching is a v2 feature
    that will join entries by ``siglip2_embedding`` cosine similarity
    above a calibrated threshold (and only with explicit user opt-in).
    """

    model_config = ConfigDict(extra="forbid")

    id: UUID
    org_id: UUID
    video_id: UUID

    # Best reference frame — chosen by the reference picker's quality
    # composite (prominence + sharpness + centeredness − occlusion +
    # temporal stability), NOT by first appearance.
    canonical_crop_s3_key: str = Field(..., min_length=1)
    canonical_video_id: UUID
    canonical_frame_idx: int = Field(..., ge=0)
    canonical_bbox: BBoxXYWH

    # Identity. ``user_label`` is reserved for v2 curation UI.
    llm_label: str = Field(..., min_length=1, max_length=200)
    user_label: str | None = Field(default=None, max_length=200)

    # SigLIP2 embedding (variant: google/siglip2-base-patch16-256 — must
    # match drive-visual-embed-worker exactly so existing scene-level
    # OS embeddings can serve as the coarse pre-filter for tracking).
    # 768-dim. Sent over the wire as float list; persisted as
    # pgvector(768).
    siglip2_embedding: list[float] = Field(..., min_length=768, max_length=768)

    enumeration_confidence: float = Field(..., ge=0.0, le=1.0)
    prominence_score: float = Field(..., ge=0.0, le=1.0)

    # Versioning lets the API mark entries stale when algos bump.
    enumeration_version: str = Field(..., min_length=1)
    enumeration_prompt_version: str = Field(..., min_length=1)

    # v0.15.0 — spoken-form aliases for STT mention extraction.
    # Populated post-hoc by the API (NOT by the enumerate worker)
    # via a per-entry gpt-4o-mini call against ``canonical_crop_s3_key``
    # + ``llm_label``. The ``shorts_auto_product`` STT track uses
    # these as additional BM25 query terms against scene
    # ``transcript_raw`` / ``scene_caption`` to bridge the gap
    # between catalog labels (read off thumbnails) and how Korean
    # livecommerce hosts actually pronounce the product
    # (transliteration variants, brand-only forms, generic
    # category phrases like "이 클렌즈"). Empty default keeps
    # v0.14.0 senders backward-compatible — old senders just omit
    # the field and the default applies on parse.
    spoken_aliases: list[str] = Field(default_factory=list, max_length=10)

    created_at: datetime
    rejected_at: datetime | None = None
    rejected_reason: RejectedReason | None = None


# ---------- alias generation response (LLM → API) ----------
#
# v0.15.0 — separate post-hoc step: given an existing catalog entry's
# ``canonical_crop`` image + ``llm_label``, ask gpt-4o-mini to enumerate
# 3-5 spoken-form aliases. Output validated through this strict schema
# so a hallucinated response can't poison the catalog.
#
# Distinct from ``EnumerationDetection`` because:
#   - input is a single image + a known label, not a batch of keyframes
#   - output is name strings, not bboxes / detections
#   - calibration story is independent — adding aliases doesn't shift
#     the enumeration recall/precision gates


class AliasGenerationResponse(BaseModel):
    """Strict-JSON output from the alias generation LLM call.

    The model is asked to return up to 5 spoken-form aliases for the
    given catalog entry (the host's likely pronunciations, brand-only
    forms, common abbreviations, generic category phrases). Each alias
    is a short BM25-friendly substring — sentences are rejected.
    """

    model_config = ConfigDict(extra="forbid")

    aliases: list[str] = Field(
        ...,
        min_length=0,
        max_length=10,
        description=(
            "Spoken-form aliases. Each entry is 1-30 characters, "
            "substring-matchable against transcript text."
        ),
    )

    @field_validator("aliases")
    @classmethod
    def _alias_shape(cls, v: list[str]) -> list[str]:
        """Reject sentence-shaped or pathological aliases.

        BM25 + nori works on tokens; an alias that is itself a sentence
        ('이 제품은 정말 좋습니다') would match too broadly and inject
        noise. The 30-char cap is generous enough for compound brand
        names like 'Dalsim fresh-kitchen 오렌지 주스' but tight enough
        to reject sentence fragments.
        """
        cleaned: list[str] = []
        for raw in v:
            stripped = raw.strip()
            if not stripped:
                # Drop empties silently; LLMs sometimes pad.
                continue
            if len(stripped) > 30:
                raise ValueError(
                    f"alias too long (>30 chars): {stripped[:40]!r}"
                )
            cleaned.append(stripped)
        # Deduplicate while preserving order — LLMs occasionally repeat.
        seen: set[str] = set()
        deduped: list[str] = []
        for alias in cleaned:
            key = alias.casefold()
            if key in seen:
                continue
            seen.add(key)
            deduped.append(alias)
        return deduped


# ---------- tracking output (worker → API) ----------

class AppearanceWindow(BaseModel):
    """One contiguous span where the catalog entry's product is
    detected. Frame-level bbox track lives in S3; this model carries
    only the rolled-up scoring metadata the API and assembler need.
    """

    model_config = ConfigDict(extra="forbid")

    catalog_entry_id: UUID
    scene_id: str
    window_start_ms: int = Field(..., ge=0)
    window_end_ms: int = Field(..., gt=0)

    avg_bbox_area_pct: float = Field(..., ge=0.0, le=1.0)
    avg_confidence: float = Field(..., ge=0.0, le=1.0)
    has_narration_mention: bool = False
    has_ocr_overlap: bool = False
    co_appearing_catalog_entry_ids: list[UUID] = Field(default_factory=list)

    # Compressed JSON track on S3 (per (catalog_entry_id, video_id) —
    # not per-window — so the API never reads frame-level data).
    raw_bbox_track_s3_key: str | None = None

    tracker_version: str = Field(..., min_length=1)
    rejected_reason: RejectedReason | None = None

    @field_validator("window_end_ms")
    @classmethod
    def _end_after_start(cls, v: int, info: ValidationInfo) -> int:
        # pydantic 2.7+ passes info.data=None during JSON-mode roundtrip;
        # the `(info.data or {}).get` guard is required (see contracts CLAUDE.md).
        start = (info.data or {}).get("window_start_ms")
        if start is not None and v <= start:
            raise ValueError("window_end_ms must be greater than window_start_ms")
        return v


# ---------- assembly output (worker → API) ----------

class StitchWindow(BaseModel):
    """One source window selected by the subset picker for inclusion
    in the final clip. Ordering is chronological per plan §1 — list
    position in ``StitchingPlan.windows`` is the playback order.
    """

    model_config = ConfigDict(extra="forbid")

    scene_id: str
    source_start_ms: int = Field(..., ge=0)
    source_end_ms: int = Field(..., gt=0)
    composite_score: float = Field(..., ge=0.0, le=1.0)
    score_components: dict[str, float] = Field(default_factory=dict)

    @field_validator("source_end_ms")
    @classmethod
    def _end_after_start(cls, v: int, info: ValidationInfo) -> int:
        start = (info.data or {}).get("source_start_ms")
        if start is not None and v <= start:
            raise ValueError("source_end_ms must be greater than source_start_ms")
        return v


class StitchingPlan(BaseModel):
    """Hand-off between product-track-worker and the existing
    ShortsRenderService. The worker writes this; the API converts to a
    CompositionSpec and POSTs to /api/shorts/render.
    """

    model_config = ConfigDict(extra="forbid")

    catalog_entry_id: UUID
    video_id: UUID
    duration_target_sec: DurationPresetSec
    duration_actual_ms: int = Field(..., gt=0)
    windows: list[StitchWindow] = Field(..., min_length=1)
    scorer_version: str = Field(..., min_length=1)
    subset_picker_version: str = Field(..., min_length=1)


# ---------- worker → API status callbacks ----------

class ProductScanProgress(BaseModel):
    """Heartbeat payload — extends the lease, advances progress, and
    accumulates running cost. The API guards on ``claimed_by`` so a
    stale worker cannot overwrite a re-claimed job.
    """

    model_config = ConfigDict(extra="forbid")

    type: Literal["product.scan_progress"] = PRODUCT_SCAN_PROGRESS_TYPE
    job_id: UUID
    claimed_by: str = Field(..., min_length=1)
    stage: ProductScanStage
    progress_pct: int = Field(..., ge=0, le=100)
    progress_label: str | None = Field(default=None, max_length=200)
    cost_delta_usd: float = Field(default=0.0, ge=0.0)


class ProductScanCompleted(BaseModel):
    """Terminal success callback. ``catalog_entries`` is non-empty for
    enumeration jobs; ``stitching_plan`` + ``render_job_id`` are present
    for tracking jobs.
    """

    model_config = ConfigDict(extra="forbid")

    type: Literal["product.scan_completed"] = PRODUCT_SCAN_COMPLETED_TYPE
    job_id: UUID
    claimed_by: str = Field(..., min_length=1)
    cost_delta_usd: float = Field(default=0.0, ge=0.0)

    catalog_entries: list[ProductCatalogEntry] = Field(default_factory=list)
    appearances: list[AppearanceWindow] = Field(default_factory=list)
    stitching_plan: StitchingPlan | None = None
    render_job_id: UUID | None = None


class ProductScanFailed(BaseModel):
    """Terminal failure callback. ``error_code`` is a stable enum so
    the UI can switch on it; ``error_message`` is human-readable.
    """

    model_config = ConfigDict(extra="forbid")

    type: Literal["product.scan_failed"] = PRODUCT_SCAN_FAILED_TYPE
    job_id: UUID
    claimed_by: str = Field(..., min_length=1)
    cost_delta_usd: float = Field(default=0.0, ge=0.0)

    error_code: Literal[
        "llm_timeout",
        "llm_schema_mismatch",
        "no_products_detected",
        "tracker_low_confidence_global",
        "render_enqueue_failed",
        "internal_error",
        "cost_cap_exceeded",
        "video_not_found",
        "cancelled",
    ]
    error_message: str = Field(..., min_length=1, max_length=2000)


# ---------- API → worker job messages ----------

class ProductEnumerateJob(BaseModel):
    """Message API enqueues for product-enumerate-worker."""

    model_config = ConfigDict(extra="forbid")

    type: Literal["product.enumerate_job"] = PRODUCT_ENUMERATE_JOB_TYPE
    job_id: UUID
    org_id: UUID
    video_id: UUID
    requested_by_user_id: UUID

    # Versions the API expects the worker to honor. Workers that read a
    # mismatched version on dequeue should requeue or fail-fast.
    enumeration_version: str = Field(..., min_length=1)
    enumeration_prompt_version: str = Field(..., min_length=1)

    max_keyframes: int = Field(default=60, ge=10, le=200)
    callback_base_url: str = Field(..., min_length=1)


class ProductTrackJob(BaseModel):
    """Message API enqueues for product-track-worker.

    v0.14.0 — Phase 4 wizard fields are additive + Optional. A v0.13.0
    sender that omits ``mode`` (or sets it to ``"enumerate"``) and
    sets the existing ``catalog_entry_id`` round-trips identically.

    Mode dispatch (worker-side):
      * ``mode == 'enumerate'`` (default) AND ``catalog_entry_id`` set
        → legacy single-product flow.
      * ``mode == 'scan_order'`` AND ``catalog_entry_id`` is None
        → wizard parent — process the whole video catalog. Wizard
        fields (``length_seconds``, ``time_range_*_ms``,
        ``requested_count``, ``product_distribution``, ``language``,
        ``intent``) are required in this case.
      * ``mode == 'render_child'`` is reserved — children are NOT
        enqueued via SQS, they're picked up by the API-process
        runner from the DB. This literal is kept here so
        ``ScanMode`` stays a single source of truth across the
        contract surface.

    The publish-then-pin protocol (see CLAUDE.md):
    workers MUST be on >= 0.14.0 BEFORE the API publishes
    ``mode='scan_order'`` messages — ``extra='forbid'`` means a
    v0.13.0 worker reading a v0.14.0 message with new fields will
    422. Until v0.14.0 is widely deployed on workers, the API code
    that publishes scan_order messages should stay flag-gated off.
    """

    model_config = ConfigDict(extra="forbid")

    type: Literal["product.track_job"] = PRODUCT_TRACK_JOB_TYPE
    job_id: UUID
    org_id: UUID
    video_id: UUID
    # v0.14.0: now optional. None for ``mode='scan_order'`` parents
    # (which process the whole catalog); required for legacy
    # single-product tracking.
    catalog_entry_id: UUID | None = None
    requested_by_user_id: UUID
    # Legacy field for the +4wk enqueue_clip deprecation window.
    # Workers on v0.14.0+ should read ``length_seconds`` first and
    # fall back to ``duration_preset_sec`` only when the new field
    # is None.
    duration_preset_sec: DurationPresetSec | None = None

    tracker_version: str = Field(..., min_length=1)
    enumeration_prompt_version: str = Field(..., min_length=1)

    callback_base_url: str = Field(..., min_length=1)

    # ---------- v0.14.0 wizard fields (all Optional) ----------

    mode: ScanMode = "enumerate"

    # Length the worker / runner targets when stitching. Wizard
    # accepts 10..120; legacy callers that omit this fall back to
    # duration_preset_sec on the worker side.
    length_seconds: int | None = Field(default=None, ge=10, le=120)

    # Number of shorts the parent should fan out into. Required when
    # mode='scan_order'; ignored otherwise.
    requested_count: int | None = Field(default=None, ge=1, le=50)

    # Optional source-range filter — pre-filters scenes at coarse
    # retrieval (codex Q3 corrected: with ±30s soft padding so windows
    # straddling the boundary aren't lost; the worker handles the
    # padding logic).
    time_range_start_ms: int | None = Field(default=None, ge=0)
    time_range_end_ms: int | None = Field(default=None, gt=0)

    product_distribution: ProductDistribution | None = None
    language: Language | None = None
    intent: ScanIntent | None = None

    @model_validator(mode="after")
    def _time_range_consistent(self) -> "ProductTrackJob":
        """Cross-field validation for time-range bounds.

        Field validators don't run on default ``None`` values for
        Optional fields, so a model-level check is the right primitive
        for "both must be set or both must be None" + "end > start".
        """
        start = self.time_range_start_ms
        end = self.time_range_end_ms
        if (start is None) != (end is None):
            raise ValueError(
                "time_range_start_ms and time_range_end_ms must both be "
                "set or both be None"
            )
        if start is not None and end is not None and end <= start:
            raise ValueError(
                "time_range_end_ms must be greater than time_range_start_ms"
            )
        return self
