"""Pydantic models for scene detection pipeline outputs.

A scene is a visually coherent, time-bounded unit within a video, detected
by visual cut analysis (e.g., ffmpeg scenecut filter).  Each scene aggregates
zero or more speech segments and carries a representative keyframe timestamp.

These schemas are consumed by:
  - heimdex-media-pipelines (scene assembler output)
  - heimdex-agent (opaque JSON validation via 3-field contract)
  - dev-heimdex-for-livecommerce (OpenSearch indexing + API responses)
"""

import re
from typing import List, Optional

from pydantic import BaseModel, Field, field_validator


# Enforced format: {video_id}_scene_{index:03d}
_SCENE_ID_PATTERN = re.compile(r"^.+_scene_\d{3,}$")


class SceneBoundary(BaseModel):
    """A single detected scene boundary within a video."""

    scene_id: str
    index: int
    start_ms: int
    end_ms: int
    keyframe_timestamp_ms: int
    keyframe_path: Optional[str] = None

    @field_validator("scene_id")
    @classmethod
    def _validate_scene_id(cls, v: str) -> str:
        if not _SCENE_ID_PATTERN.match(v):
            raise ValueError(
                f"scene_id must match '{{video_id}}_scene_{{index:03d}}', got {v!r}"
            )
        return v

    @field_validator("end_ms")
    @classmethod
    def _end_after_start(cls, v: int, info) -> int:
        start = info.data.get("start_ms")
        if start is not None and v < start:
            raise ValueError(f"end_ms ({v}) must be >= start_ms ({start})")
        return v


class SceneDocument(BaseModel):
    """Complete scene document ready for OpenSearch indexing.

    Produced by the scene assembler after merging scene boundaries with
    speech segment transcripts.
    """

    scene_id: str
    video_id: str
    index: int
    start_ms: int
    end_ms: int
    keyframe_timestamp_ms: int
    transcript_raw: str = ""
    transcript_norm: str = ""
    transcript_char_count: int = 0
    speech_segment_count: int = 0
    people_cluster_ids: List[str] = Field(default_factory=list)
    thumbnail_path: Optional[str] = None
    thumbnail_url: Optional[str] = None

    @field_validator("scene_id")
    @classmethod
    def _validate_scene_id(cls, v: str) -> str:
        if not _SCENE_ID_PATTERN.match(v):
            raise ValueError(
                f"scene_id must match '{{video_id}}_scene_{{index:03d}}', got {v!r}"
            )
        return v


class SceneDetectionResult(BaseModel):
    """Output of the scene detection + assembly pipeline.

    Carries the 3-field agent validation contract (schema_version,
    pipeline_version, model_version) plus the full list of scene documents.
    """

    schema_version: str = "1.0"
    pipeline_version: str
    model_version: str
    video_path: str
    video_id: str
    total_duration_ms: int
    scenes: List[SceneDocument] = Field(default_factory=list)
    processing_time_s: float = 0.0
    status: str = "success"
    error: Optional[str] = None
