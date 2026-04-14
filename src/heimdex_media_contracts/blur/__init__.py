"""PII blur pipeline schemas.

Covers the full blur subsystem contract surface:

* Job messages (API → worker via SQS)
* Result callbacks (worker → API)
* The on-disk manifest format (worker → S3 → downstream consumers)
* Detection records (one entry per blurred region)

These mirror the dataclasses in ``heimdex_media_pipelines.blur`` so the
worker can cross the ML library / system boundary with a validated
pydantic model on each side.
"""

from heimdex_media_contracts.blur.schemas import (
    ALLOWED_BLUR_CATEGORIES,
    BLUR_EXPORT_COMPLETED_TYPE,
    BLUR_EXPORT_CREATED_TYPE,
    BLUR_JOB_COMPLETED_TYPE,
    BLUR_JOB_CREATED_TYPE,
    BLUR_JOB_PROGRESS_TYPE,
    BlurCategory,
    BlurDetectionRecord,
    BlurDetectionSummary,
    BlurExportCreated,
    BlurExportFormat,
    BlurExportOptions,
    BlurExportResult,
    BlurExportStatus,
    BlurJobCreated,
    BlurJobPhase,
    BlurJobProgress,
    BlurJobResult,
    BlurJobStatus,
    BlurManifest,
    BlurOptions,
    BlurSourceKind,
    BlurTimingInfo,
    BlurVideoInfo,
)

__all__ = [
    "ALLOWED_BLUR_CATEGORIES",
    "BLUR_EXPORT_COMPLETED_TYPE",
    "BLUR_EXPORT_CREATED_TYPE",
    "BLUR_JOB_COMPLETED_TYPE",
    "BLUR_JOB_CREATED_TYPE",
    "BLUR_JOB_PROGRESS_TYPE",
    "BlurCategory",
    "BlurDetectionRecord",
    "BlurDetectionSummary",
    "BlurExportCreated",
    "BlurExportFormat",
    "BlurExportOptions",
    "BlurExportResult",
    "BlurExportStatus",
    "BlurJobCreated",
    "BlurJobPhase",
    "BlurJobProgress",
    "BlurJobResult",
    "BlurJobStatus",
    "BlurManifest",
    "BlurOptions",
    "BlurSourceKind",
    "BlurTimingInfo",
    "BlurVideoInfo",
]
