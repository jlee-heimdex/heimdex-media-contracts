"""Video composition schemas and filter graph builder.

The CompositionSpec is the single contract between the editor UI,
the API layer, and the ffmpeg render pipeline.
"""

from heimdex_media_contracts.composition.filters import build_filter_graph
from heimdex_media_contracts.composition.schemas import (
    CompositionSpec,
    OutputSpec,
    SceneClipSpec,
    SubtitleSpec,
    SubtitleStyleSpec,
    TransitionSpec,
)

__all__ = [
    "CompositionSpec",
    "OutputSpec",
    "SceneClipSpec",
    "SubtitleSpec",
    "SubtitleStyleSpec",
    "TransitionSpec",
    "build_filter_graph",
]
