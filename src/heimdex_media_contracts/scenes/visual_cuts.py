"""Schema for the visual-cuts cache persisted during the transcode
piggyback pass.

The transcode worker obtains scene-cut timestamps in the same ffmpeg
invocation that produces the proxy (Phase 2 of the scene-detect
piggyback plan) and writes them to S3 so phase-2 speech-aware splitting
(Phase 4) can reuse them without re-decoding the proxy.

The cache is **advisory**: consumers treat a missing, unreadable, or
schema-incompatible cache as "no cache" and fall back to fresh
detection. Any hard dependency on the cache is a bug — document it
here if you add one.
"""

from __future__ import annotations

from typing import List, Literal

from pydantic import BaseModel, Field, field_validator


class VisualCutsDoc(BaseModel):
    """Persisted JSON shape for ``scene_visual_cuts_s3_key``.

    Versioning: ``schema_version`` is a ``Literal["1.0"]`` so any future
    major bump requires updating this type AND consumers. Pydantic
    rejects unknown values on parse, so a stale consumer raises
    ``ValidationError`` rather than silently misinterpreting fields.

    Layout at rest::

        {
            "schema_version": "1.0",
            "video_id": "gdrive:abc-123",
            "detector": "ffmpeg_scenecut_piggyback_v1",
            "threshold": 0.3,
            "cuts_ms": [1234, 3510, 5820, ...],
            "total_duration_ms": 100738,
            "detected_at": "2026-04-22T14:22:10Z",
            "ffmpeg_version": "n7.1"
        }
    """

    schema_version: Literal["1.0"] = "1.0"
    video_id: str = Field(..., min_length=1)
    detector: str = Field(
        ...,
        min_length=1,
        description=(
            "Identifier for the detection algorithm + version that "
            "produced these cuts. E.g. 'ffmpeg_scenecut_legacy_v1' or "
            "'ffmpeg_scenecut_piggyback_v1'. Used for drift detection."
        ),
    )
    threshold: float = Field(
        ...,
        ge=0.0,
        le=1.0,
        description="Scene score threshold that produced the cuts.",
    )
    cuts_ms: List[int] = Field(
        default_factory=list,
        description=(
            "Scene-cut timestamps in milliseconds, sorted ascending, "
            "deduped, all strictly positive (frame 0 is never a cut)."
        ),
    )
    total_duration_ms: int = Field(..., gt=0)
    detected_at: str = Field(
        ...,
        min_length=1,
        description="ISO 8601 timestamp of detection (UTC).",
    )
    ffmpeg_version: str = Field(
        ...,
        min_length=1,
        description=(
            "ffmpeg version string (e.g. 'n7.1' for BtbN 7.1). "
            "Pinned here so phase-2 consumers can reject cached cuts "
            "produced by a known-incompatible detector build."
        ),
    )

    @field_validator("cuts_ms")
    @classmethod
    def _validate_cuts(cls, v: List[int]) -> List[int]:
        # Guard the invariants producers are supposed to uphold. We
        # don't *sort* here — that's the producer's contract. A reader
        # receiving unsorted cuts has a bug upstream and should see it.
        for ts in v:
            if ts <= 0:
                raise ValueError(
                    f"cuts_ms must be strictly positive, got {ts}"
                )
        if v != sorted(v):
            raise ValueError("cuts_ms must be sorted ascending")
        if len(v) != len(set(v)):
            raise ValueError("cuts_ms must be deduplicated")
        return v
