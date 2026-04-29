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

from pydantic import BaseModel, ConfigDict, Field, field_validator
from pydantic_core.core_schema import ValidationInfo


# ---------- type aliases ----------

ProductScanStage = Literal[
    "queued",
    "enumerating",
    "enumeration_done",
    "tracking",
    "assembling",
    "rendering",
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
    "done",
    "failed",
    "cancelled",
})

# Allowed clip durations in seconds. Plan §1 locks these to 30/60/90
# matching the native lengths on Reels / Shorts / TikTok.
DurationPresetSec = Literal[30, 60, 90]
ALLOWED_DURATION_PRESETS: frozenset[int] = frozenset({30, 60, 90})

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

    created_at: datetime
    rejected_at: datetime | None = None
    rejected_reason: RejectedReason | None = None


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
    """Message API enqueues for product-track-worker."""

    model_config = ConfigDict(extra="forbid")

    type: Literal["product.track_job"] = PRODUCT_TRACK_JOB_TYPE
    job_id: UUID
    org_id: UUID
    video_id: UUID
    catalog_entry_id: UUID
    requested_by_user_id: UUID
    duration_preset_sec: DurationPresetSec

    tracker_version: str = Field(..., min_length=1)
    enumeration_prompt_version: str = Field(..., min_length=1)

    callback_base_url: str = Field(..., min_length=1)
