"""Pydantic models for face presence pipeline responses.

Migrated from:
  dev-heimdex-for-livecommerce/services/worker/src/domain/faces/schemas.py
"""

from typing import List, Optional

from pydantic import BaseModel


class Interval(BaseModel):
    start_s: float
    end_s: float
    confidence: float


class SceneSummary(BaseModel):
    scene_id: str
    present: Optional[bool] = None  # true / false / unknown
    confidence: float


class IdentityPresence(BaseModel):
    identity_id: str
    intervals: List[Interval]
    scene_summary: List[SceneSummary]


class FacePresenceResponse(BaseModel):
    video_id: str
    identities: List[IdentityPresence]
    meta: dict
