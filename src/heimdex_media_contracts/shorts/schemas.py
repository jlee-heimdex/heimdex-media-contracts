"""Pydantic models for YouTube Shorts candidate selection."""

from typing import List, Optional

from pydantic import BaseModel, Field, field_validator


class ShortsCandidate(BaseModel):
    """A candidate clip for YouTube Shorts generation.

    Produced by the scorer after evaluating scene metadata against
    duration constraints and importance signals.
    """

    candidate_id: str
    video_id: str
    scene_ids: List[str] = Field(min_length=1)
    start_ms: int
    end_ms: int
    title_suggestion: str = ""
    reason: str = ""
    score: float = 0.0
    tags: List[str] = Field(default_factory=list)
    product_refs: List[str] = Field(default_factory=list)
    people_refs: List[str] = Field(default_factory=list)
    transcript_snippet: str = ""

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
