"""Pydantic models for OCR pipeline outputs.

An OCR block is a single text region detected in a keyframe image.
Blocks are grouped by frame, frames by scene, and scenes comprise
the full OCR pipeline result for a video.

These schemas are consumed by:
  - heimdex-media-pipelines (OCR pipeline output)
  - heimdex-agent (opaque JSON read + merge into SceneIngestDoc)
  - dev-heimdex-for-livecommerce (ingest validation via ocr_text_raw field)

Constraints from OCR_MINIMAL_CONTEXT_CONTRACT.md:
  - ocr_text_raw capped at 10,000 chars
  - max 50 frames per scene (v1 uses 1; cap prevents abuse)
  - bbox is normalized [x1, y1, x2, y2] in 0..1 range
"""

import re
from typing import Any, List, Optional

from pydantic import BaseModel, Field, field_validator, model_validator

# Scene ID pattern — reuse the same format as scenes/schemas.py
_SCENE_ID_PATTERN = re.compile(r"^.+_scene_\d+$")

OCR_TEXT_MAX_LENGTH = 10_000
OCR_MAX_FRAMES_PER_SCENE = 50


class OCRBlock(BaseModel):
    """A single text region detected by OCR in a keyframe image."""

    text: str
    confidence: float = Field(ge=0.0, le=1.0)
    bbox: List[float] = Field(min_length=4, max_length=4)

    @field_validator("bbox")
    @classmethod
    def _validate_bbox_values(cls, v: List[float]) -> List[float]:
        for i, val in enumerate(v):
            if val < 0.0 or val > 1.0:
                raise ValueError(
                    f"bbox[{i}] must be in [0.0, 1.0], got {val}"
                )
        return v


class OCRFrameResult(BaseModel):
    """OCR results for a single keyframe image."""

    frame_ts_ms: int = Field(ge=0)
    blocks: List[OCRBlock] = Field(default_factory=list)
    text_concat: str = ""
    processing_time_ms: Optional[float] = Field(default=None, ge=0.0)


class OCRSceneResult(BaseModel):
    """Aggregated OCR output for a single scene (one or more keyframes)."""

    scene_id: str
    frames: List[OCRFrameResult] = Field(default_factory=list)
    ocr_text_raw: str = Field(default="", max_length=OCR_TEXT_MAX_LENGTH)
    ocr_char_count: int = Field(default=0, ge=0)

    @field_validator("scene_id")
    @classmethod
    def _validate_scene_id(cls, v: str) -> str:
        if not _SCENE_ID_PATTERN.match(v):
            raise ValueError(
                f"scene_id must match '{{video_id}}_scene_{{index}}', got {v!r}"
            )
        return v

    @field_validator("frames")
    @classmethod
    def _validate_frame_count(cls, v: List[OCRFrameResult]) -> List[OCRFrameResult]:
        if len(v) > OCR_MAX_FRAMES_PER_SCENE:
            raise ValueError(
                f"Too many OCR frames: {len(v)} > {OCR_MAX_FRAMES_PER_SCENE}"
            )
        return v

    @model_validator(mode="after")
    def _sync_char_count(self) -> "OCRSceneResult":
        """Auto-compute ocr_char_count from ocr_text_raw if inconsistent."""
        if self.ocr_text_raw:
            self.ocr_char_count = len(self.ocr_text_raw)
        else:
            self.ocr_char_count = 0
        return self


class OCRPipelineResult(BaseModel):
    """Full output of the OCR detection pipeline for a video.

    Carries the 3-field agent validation contract (schema_version,
    pipeline_version, model_version) consistent with SceneDetectionResult.
    """

    schema_version: str = "1.0"
    pipeline_version: str = ""
    model_version: str = ""
    video_id: str
    scenes: List[OCRSceneResult] = Field(default_factory=list)
    total_frames_processed: int = Field(default=0, ge=0)
    processing_time_s: float = Field(default=0.0, ge=0.0)
    status: str = "success"
    error: Optional[str] = None
    meta: dict[str, Any] = Field(default_factory=dict)
