"""Dataclass schemas for speech segment pipelines.

Migrated from:
  dev-heimdex-for-livecommerce/services/worker/src/domain/speech_segments/schemas.py
"""

import json
from dataclasses import asdict, dataclass, field
from typing import Optional


@dataclass
class SpeechSegment:
    """A single speech segment with timing and transcription."""

    start: float  # start time (seconds)
    end: float  # end time (seconds)
    text: str  # STT result text
    confidence: float = 0.0  # STT confidence

    @property
    def duration(self) -> float:
        return self.end - self.start


@dataclass
class TaggedSegment(SpeechSegment):
    """A speech segment annotated with category tags."""

    tags: list[str] = field(default_factory=list)
    tag_scores: dict[str, float] = field(default_factory=dict)


@dataclass
class RankedSegment(TaggedSegment):
    """A tagged segment with an importance rank and score."""

    rank: int = 0
    importance_score: float = 0.0


@dataclass
class PipelineResult:
    """Full pipeline output containing ranked segments and metadata."""

    video_path: str
    segments: list[RankedSegment] = field(default_factory=list)
    total_duration: float = 0.0
    processing_time: float = 0.0
    status: str = "success"
    error: Optional[str] = None

    def to_dict(self) -> dict:
        return {
            "video_path": self.video_path,
            "segments": [asdict(s) for s in self.segments],
            "total_duration": self.total_duration,
            "processing_time": self.processing_time,
            "status": self.status,
            "error": self.error,
        }

    def to_json(self, indent: int = 2) -> str:
        return json.dumps(self.to_dict(), indent=indent, ensure_ascii=False)
