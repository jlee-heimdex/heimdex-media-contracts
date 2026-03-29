"""Scene detection schemas, pure merge functions, and multi-signal splitting."""

from heimdex_media_contracts.scenes.combiner import combine_signals
from heimdex_media_contracts.scenes.merge import (
    SegmentInput,
    SpeechSegmentLike,
    aggregate_scene_tags,
    aggregate_transcript,
    assign_segments_to_scenes,
    merge_ocr_into_scene,
)
from heimdex_media_contracts.scenes.presets import (
    PRESET_LABELS,
    PRESETS,
    resolve_config,
)
from heimdex_media_contracts.scenes.schemas import (
    SceneBoundary,
    SceneDetectionResult,
    SceneDocument,
)
from heimdex_media_contracts.scenes.splitting import SplitConfig, SplitSignal

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
    "SplitSignal",
    "SplitConfig",
    "combine_signals",
    "PRESETS",
    "PRESET_LABELS",
    "resolve_config",
]
