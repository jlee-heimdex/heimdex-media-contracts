"""Pydantic schemas for the PII blur pipeline.

Every field is additive — no existing consumer is affected by this
module landing. The worker and API both import from here; the pipeline
library does not (it uses plain dataclasses to stay dependency-free).

See ``heimdex_media_pipelines.blur`` for the runtime implementation
whose ``BlurResult.to_manifest()`` output these models validate.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


# ---------- type aliases ----------

BlurCategory = Literal[
    "face",
    "license_plate",
    "logo",
    "card_object",
    "object",  # fallback bucket for user-supplied custom queries
]

BlurJobStatus = Literal["done", "failed", "skipped"]

BlurSourceKind = Literal["proxy", "original"]

# Mirror of ``heimdex_media_pipelines.blur.config.ALLOWED_CATEGORIES`` so
# workers can validate without importing the pipeline package. Any change
# here must land in both repos on the same version.
ALLOWED_BLUR_CATEGORIES: frozenset[str] = frozenset({
    "face",
    "license_plate",
    "logo",
    "card_object",
    "object",
})


# ---------- detection record ----------

class BlurDetectionRecord(BaseModel):
    """One region blurred in the output video.

    Mirrors ``heimdex_media_pipelines.blur.config.DetectionRecord`` 1:1.
    Tuple fields serialize as JSON arrays by pydantic default.
    """

    model_config = ConfigDict(extra="forbid")

    frame_idx: int = Field(..., ge=0)
    t_ms: int = Field(..., ge=0)
    category: BlurCategory
    label: str
    confidence: float = Field(..., ge=0.0, le=1.0)
    bbox_norm: tuple[float, float, float, float]
    from_cache: bool = False


# ---------- manifest (on-disk JSON) ----------

class BlurVideoInfo(BaseModel):
    model_config = ConfigDict(extra="forbid")

    fps: float = Field(..., gt=0)
    width: int = Field(..., gt=0)
    height: int = Field(..., gt=0)
    frame_count: int = Field(..., ge=0)


class BlurTimingInfo(BaseModel):
    model_config = ConfigDict(extra="forbid")

    total_ms: float = Field(..., ge=0)
    owl_infer_ms: float = Field(..., ge=0)
    owl_infer_frames: int = Field(..., ge=0)
    avg_fps: float = Field(..., ge=0)


class BlurDetectionSummary(BaseModel):
    """Category → count of blurred regions.

    Represented as a normal model rather than ``dict[str, int]`` so new
    optional fields can be added later (e.g. ``unique_objects``) without
    breaking old consumers.
    """

    model_config = ConfigDict(extra="allow")

    face: int = 0
    license_plate: int = 0
    logo: int = 0
    card_object: int = 0
    object: int = 0

    @classmethod
    def from_counts(cls, counts: dict[str, int]) -> "BlurDetectionSummary":
        return cls.model_validate(counts)


class BlurManifest(BaseModel):
    """Top-level on-disk manifest written by the worker to S3.

    Consumers that want to index or audit blur detections should load
    the JSON file and validate via ``BlurManifest.model_validate_json``.
    The ``config`` field stays an untyped dict so library-side changes
    to ``BlurConfig`` don't force a contracts bump.
    """

    model_config = ConfigDict(extra="forbid")

    schema_version: Literal["1"] = "1"
    pipeline_version: str
    input_path: str
    output_path: str
    video: BlurVideoInfo
    timing: BlurTimingInfo
    config: dict[str, Any] | None = None
    summary: BlurDetectionSummary
    detections: list[BlurDetectionRecord]


# ---------- control-plane messages ----------

class BlurOptions(BaseModel):
    """Per-job options. Defaults match the production policy: faces +
    license plates + cards; logos OFF (livecommerce would blur the
    product being sold). Tenants opt into logo blur by overriding
    ``categories``.
    """

    model_config = ConfigDict(extra="forbid")

    do_faces: bool = True
    do_owl: bool = True
    categories: tuple[BlurCategory, ...] = ("face", "license_plate", "card_object")
    owl_stride: int = Field(5, ge=1)
    owl_score_threshold: float = Field(0.35, ge=0.0, le=1.0)
    owl_model: str = "google/owlv2-base-patch16-ensemble"
    min_face_confidence: float = Field(0.5, ge=0.0, le=1.0)
    mosaic_cells: int = Field(100, ge=1)
    feather: int = Field(3, ge=0)
    custom_owl_queries: tuple[str, ...] | None = None


class BlurJobCreated(BaseModel):
    """SQS message body for ``blur.job_created``.

    Published by the API when a user explicitly requests a blur on a
    video via ``POST /api/videos/{file_id}/blur``. Consumed by
    ``drive-blur-worker``. Blur is a *user-initiated* side-pipeline — it
    does not fire automatically from the ingest / transcode / index
    critical path, so each published message is traceable to a single
    persisted ``blur_jobs`` row via ``job_id``.
    """

    model_config = ConfigDict(extra="forbid")

    version: Literal["1"] = "1"
    type: Literal["blur.job_created"] = "blur.job_created"
    timestamp: datetime
    job_id: UUID
    file_id: UUID
    org_id: UUID
    video_id: str
    source_s3_key: str
    source_kind: BlurSourceKind = "proxy"
    options: BlurOptions = Field(default_factory=BlurOptions)


class BlurJobResult(BaseModel):
    """Result envelope sent back to the API's internal callback endpoint.

    The full manifest is NOT inlined — it lives in S3 at
    ``manifest_s3_key`` and can be orders of magnitude larger than an
    SQS/HTTP payload budget on long videos. Consumers that want the
    detections re-download and validate with ``BlurManifest``.

    The ``job_id`` points at the row in ``blur_jobs`` to update; the
    ``lease_token`` proves the worker still holds the claim (rejects
    stale callbacks from workers that lost their lease to a watchdog).
    """

    model_config = ConfigDict(extra="forbid")

    version: Literal["1"] = "1"
    type: Literal["blur.job_completed"] = "blur.job_completed"
    job_id: UUID
    lease_token: UUID
    file_id: UUID
    org_id: UUID
    video_id: str
    status: BlurJobStatus
    blurred_s3_key: str | None = None
    manifest_s3_key: str | None = None
    detections_summary: BlurDetectionSummary | None = None
    error: str | None = None
