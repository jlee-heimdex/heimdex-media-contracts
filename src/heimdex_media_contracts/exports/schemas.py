"""Pydantic models for NLE export formats (FCPXML, EDL)."""

from typing import List, Optional

from pydantic import BaseModel, Field, field_validator


class ExportMarker(BaseModel):
    name: str
    time_ms: int
    note: str = ""


class ExportClip(BaseModel):
    clip_name: str
    video_id: str
    media_path: str = ""
    media_url: str = ""
    start_ms: int
    end_ms: int
    scene_id: str = ""
    markers: List[ExportMarker] = Field(default_factory=list)

    @property
    def duration_ms(self) -> int:
        return self.end_ms - self.start_ms

    @field_validator("end_ms")
    @classmethod
    def _end_after_start(cls, v: int, info) -> int:
        start = info.data.get("start_ms")
        if start is not None and v < start:
            raise ValueError(f"end_ms ({v}) must be >= start_ms ({start})")
        return v
