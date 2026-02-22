import re
from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, Field, field_validator

SourceType = Literal["gdrive", "removable_disk", "local"]

SOURCE_TYPE_VALUES: list[str] = ["gdrive", "removable_disk", "local"]

_SCENE_ID_RE = re.compile(r"^[^/\\\x00]+_scene_\d+$")
_PATH_TRAVERSAL_CHARS = re.compile(r"[/\\\x00]")


def _reject_path_traversal(value: str, field_name: str) -> str:
    """Reject values containing path traversal characters (CWE-22)."""
    if _PATH_TRAVERSAL_CHARS.search(value):
        raise ValueError(
            f"{field_name} must not contain '/', '\\', or null bytes, got: {value!r}"
        )
    if ".." in value:
        raise ValueError(
            f"{field_name} must not contain '..', got: {value!r}"
        )
    return value


class IngestSceneDocument(BaseModel):
    scene_id: str = Field(
        ...,
        description="Unique scene identifier. Format: {video_id}_scene_{index}",
    )
    index: int = Field(..., ge=0)
    start_ms: int = Field(..., ge=0)
    end_ms: int = Field(..., ge=0)
    keyframe_timestamp_ms: int = Field(default=0, ge=0)
    transcript_raw: str = Field(default="", max_length=50_000)

    @field_validator("scene_id")
    @classmethod
    def scene_id_format(cls, v: str) -> str:
        _reject_path_traversal(v, "scene_id")
        if not _SCENE_ID_RE.match(v):
            raise ValueError(
                f"scene_id must match '{{video_id}}_scene_{{index}}' pattern, got: {v!r}"
            )
        return v

    speech_segment_count: int = Field(default=0, ge=0)
    people_cluster_ids: list[str] = Field(default_factory=list)
    keyword_tags: list[str] = Field(default_factory=list)
    product_tags: list[str] = Field(default_factory=list)
    product_entities: list[str] = Field(default_factory=list)
    ocr_text_raw: str = Field(default="", max_length=10_000)
    ocr_char_count: int = Field(default=0, ge=0)

    # Scene caption — added in v0.6.0.  Vision-generated natural language
    # description of the scene's representative keyframe.  Empty string when
    # no caption has been produced yet (backward compatible).
    scene_caption: str = Field(default="", max_length=5_000)

    source_type: SourceType = Field(default="gdrive")
    required_drive_nickname: str | None = Field(default=None)
    capture_time: datetime | None = Field(default=None)

    @field_validator("end_ms")
    @classmethod
    def end_after_start(cls, v: int, info) -> int:
        start = info.data.get("start_ms", 0)
        if v < start:
            raise ValueError(f"end_ms ({v}) must be >= start_ms ({start})")
        return v


class IngestScenesRequest(BaseModel):
    video_id: str = Field(..., min_length=1)
    video_title: str = Field(default="", max_length=500)
    library_id: UUID = Field(...)
    pipeline_version: str = Field(default="")
    model_version: str = Field(default="")
    total_duration_ms: int = Field(default=0, ge=0)
    source_path: str | None = Field(default=None, max_length=1000)
    scenes: list[IngestSceneDocument] = Field(...)

    @field_validator("video_id")
    @classmethod
    def video_id_safe(cls, v: str) -> str:
        return _reject_path_traversal(v, "video_id")
