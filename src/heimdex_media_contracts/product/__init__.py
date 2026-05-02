"""Auto-shorts product mode v2 contract.

Two-stage lazy pipeline:

* ``ProductEnumerateJob`` / ``ProductTrackJob`` — API → worker via SQS
* ``ProductScanProgress`` / ``ProductScanCompleted`` / ``ProductScanFailed``
  — worker → API via internal HTTP callbacks
* ``ProductCatalogEntry``, ``AppearanceWindow`` — persisted state shared
  across the two stages
* ``StitchingPlan`` / ``StitchWindow`` — handoff to ShortsRenderService
* ``EnumerationPrompt`` — versioned LLM prompt; bumping ``VERSION``
  requires a contracts release + golden eval re-run

These mirror the runtime types in ``heimdex_media_pipelines.product_enum``
and ``heimdex_media_pipelines.product_track`` so workers can validate
on the system / ML library boundary.
"""

from heimdex_media_contracts.product.prompts import (
    ENUMERATION_PROMPT_VERSION,
    EnumerationPrompt,
)
from heimdex_media_contracts.product.schemas import (
    ALLOWED_DURATION_PRESETS,
    ALLOWED_LANGUAGES,
    ALLOWED_PRODUCT_DISTRIBUTIONS,
    ALLOWED_SCAN_INTENTS,
    ALLOWED_SCAN_MODES,
    ALLOWED_SCAN_STAGES,
    PRODUCT_ENUMERATE_JOB_TYPE,
    PRODUCT_SCAN_COMPLETED_TYPE,
    PRODUCT_SCAN_FAILED_TYPE,
    PRODUCT_SCAN_PROGRESS_TYPE,
    PRODUCT_TRACK_JOB_TYPE,
    AppearanceWindow,
    BBoxXYWH,
    DurationPresetSec,
    EnumerationDetection,
    Language,
    ProductCatalogEntry,
    ProductDistribution,
    ProductEnumerateJob,
    ProductScanCompleted,
    ProductScanFailed,
    ProductScanProgress,
    ProductScanStage,
    ProductTrackJob,
    RejectedReason,
    ScanIntent,
    ScanMode,
    StitchingPlan,
    StitchWindow,
)

__all__ = [
    "ALLOWED_DURATION_PRESETS",
    "ALLOWED_LANGUAGES",
    "ALLOWED_PRODUCT_DISTRIBUTIONS",
    "ALLOWED_SCAN_INTENTS",
    "ALLOWED_SCAN_MODES",
    "ALLOWED_SCAN_STAGES",
    "ENUMERATION_PROMPT_VERSION",
    "PRODUCT_ENUMERATE_JOB_TYPE",
    "PRODUCT_SCAN_COMPLETED_TYPE",
    "PRODUCT_SCAN_FAILED_TYPE",
    "PRODUCT_SCAN_PROGRESS_TYPE",
    "PRODUCT_TRACK_JOB_TYPE",
    "AppearanceWindow",
    "BBoxXYWH",
    "DurationPresetSec",
    "EnumerationDetection",
    "EnumerationPrompt",
    "Language",
    "ProductCatalogEntry",
    "ProductDistribution",
    "ProductEnumerateJob",
    "ProductScanCompleted",
    "ProductScanFailed",
    "ProductScanProgress",
    "ProductScanStage",
    "ProductTrackJob",
    "RejectedReason",
    "ScanIntent",
    "ScanMode",
    "StitchingPlan",
    "StitchWindow",
]
