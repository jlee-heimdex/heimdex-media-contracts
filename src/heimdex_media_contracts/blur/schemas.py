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

BlurJobPhase = Literal[
    "queued",
    "initializing",
    "detecting",
    "encoding",
    "uploading",
    "finalizing",
]

BlurExportFormat = Literal["prores_4444"]

BlurExportStatus = Literal["queued", "running", "done", "failed", "cancelled"]


# ---------- SQS / HTTP message type constants ----------
#
# Published so dispatchers on the worker side can route by message type
# without duplicating string literals. Each constant matches the ``type``
# field on the corresponding pydantic model below.

BLUR_JOB_CREATED_TYPE = "blur.job_created"
BLUR_JOB_COMPLETED_TYPE = "blur.job_completed"
BLUR_JOB_PROGRESS_TYPE = "blur.job_progress"
BLUR_EXPORT_CREATED_TYPE = "blur.export_created"
BLUR_EXPORT_COMPLETED_TYPE = "blur.export_completed"

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

    ``schema_version`` accepts ``"1"`` (pre-0.10 manifests, no mask
    layers) and ``"2"`` (current — adds per-category FFV1 mask layers
    stored under ``mask_s3_keys``). New writes always default to ``"2"``;
    old manifests remain parseable so re-reads never break.
    """

    model_config = ConfigDict(extra="forbid")

    schema_version: Literal["1", "2"] = "2"
    pipeline_version: str
    input_path: str
    output_path: str
    video: BlurVideoInfo
    timing: BlurTimingInfo
    config: dict[str, Any] | None = None
    summary: BlurDetectionSummary
    detections: list[BlurDetectionRecord]
    mask_s3_keys: dict[BlurCategory, str] | None = None


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
    mask_s3_keys: dict[BlurCategory, str] | None = None
    detections_summary: BlurDetectionSummary | None = None
    error: str | None = None


# ---------- progress heartbeat ----------

class BlurJobProgress(BaseModel):
    """Heartbeat posted by the worker to the API while a blur job runs.

    The pipeline emits progress events through a callback provided by
    the worker (keeping the pipeline library dependency-free — no HTTP
    client). The worker converts each event into this payload and POSTs
    to ``/internal/blur/{job_id}/progress``. The API persists
    ``progress_pct`` + ``phase`` on the ``blur_jobs`` row so the frontend
    can render a live bar without polling S3.
    """

    model_config = ConfigDict(extra="forbid")

    version: Literal["1"] = "1"
    type: Literal["blur.job_progress"] = "blur.job_progress"
    job_id: UUID
    lease_token: UUID
    progress_pct: float = Field(..., ge=0.0, le=100.0)
    phase: BlurJobPhase
    message: str | None = None
    eta_seconds: float | None = Field(None, ge=0.0)


# ---------- layer export (NLE-compatible ProRes 4444 + alpha) ----------

class BlurExportOptions(BaseModel):
    """User-selectable options when creating a layer export.

    Immutable once persisted — customers who want a different category
    subset create a new export against the same parent ``blur_job_id``.
    Dedupe on ``(blur_job_id, hash(categories|format))`` lives in the
    API service layer, not the schema.
    """

    model_config = ConfigDict(extra="forbid")

    categories: tuple[BlurCategory, ...] = Field(..., min_length=1)
    format: BlurExportFormat = "prores_4444"


class BlurExportCreated(BaseModel):
    """SQS message body for ``blur.export_created``.

    Consumed by drive-blur-worker's dispatcher. The worker downloads the
    source proxy + the per-category FFV1 masks listed in
    ``mask_s3_keys`` and composites a single ProRes 4444 ``.mov`` layer
    (yuva444p10le, alpha-on-blur-regions) using ``ffmpeg -filter_complex``.

    ``mask_s3_keys`` is already filtered to the categories requested by
    the user — the worker doesn't re-filter.
    """

    model_config = ConfigDict(extra="forbid")

    version: Literal["1"] = "1"
    type: Literal["blur.export_created"] = "blur.export_created"
    timestamp: datetime
    export_id: UUID
    blur_job_id: UUID
    file_id: UUID
    org_id: UUID
    video_id: str
    source_s3_key: str
    mask_s3_keys: dict[BlurCategory, str] = Field(..., min_length=1)
    options: BlurExportOptions


class BlurExportResult(BaseModel):
    """Callback envelope from drive-blur-worker to the API export
    ``/internal/blur/exports/{export_id}/complete`` endpoint.

    On success, ``layer_s3_key`` points at the uploaded
    ``.mov``; on failure, ``error`` carries a short human-readable
    string and ``layer_s3_key`` stays ``None``. Consumers fetch the
    layer itself via a presigned URL from the API — the key is never
    exposed to the frontend directly.
    """

    model_config = ConfigDict(extra="forbid")

    version: Literal["1"] = "1"
    type: Literal["blur.export_completed"] = "blur.export_completed"
    export_id: UUID
    lease_token: UUID
    status: BlurExportStatus
    layer_s3_key: str | None = None
    error: str | None = None
