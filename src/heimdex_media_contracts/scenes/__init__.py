"""Scene detection schemas and pure merge functions."""

from heimdex_media_contracts.scenes.merge import (
    SegmentInput,
    SpeechSegmentLike,
    aggregate_scene_tags,
    aggregate_transcript,
    assign_segments_to_scenes,
    merge_ocr_into_scene,
)
from heimdex_media_contracts.scenes.schemas import (
    SceneBoundary,
    SceneDetectionResult,
    SceneDocument,
)

__all__ = [
    "SceneBoundary",
    "SceneDocument",
    "SceneDetectionResult",
    "SpeechSegmentLike",
    "SegmentInput",
    "assign_segments_to_scenes",
    "aggregate_scene_tags",
    "aggregate_transcript",
    "merge_ocr_into_scene",
]
