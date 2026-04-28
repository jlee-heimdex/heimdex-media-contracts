"""Video composition schemas and filter graph builder.

The CompositionSpec is the single contract between the editor UI,
the API layer, and the ffmpeg render pipeline.
"""

from heimdex_media_contracts.composition.filters import (
    SUPPORTED_FONTS,
    FontNotFoundError,
    build_filter_graph,
    build_overlay_filter_chain,
)
from heimdex_media_contracts.composition.overlays import (
    BackgroundOverlaySpec,
    EffectsSpec,
    OverlaySpec,
    ShadowSpec,
    StrokeSpec,
    TextOverlaySpec,
    TransformSpec,
)
from heimdex_media_contracts.composition.schemas import (
    CompositionSpec,
    OutputSpec,
    SceneClipSpec,
    SubtitleSpec,
    SubtitleStyleSpec,
    TransitionSpec,
)

__all__ = [
    "BackgroundOverlaySpec",
    "CompositionSpec",
    "EffectsSpec",
    "FontNotFoundError",
    "OutputSpec",
    "OverlaySpec",
    "SUPPORTED_FONTS",
    "SceneClipSpec",
    "ShadowSpec",
    "StrokeSpec",
    "SubtitleSpec",
    "SubtitleStyleSpec",
    "TextOverlaySpec",
    "TransformSpec",
    "TransitionSpec",
    "build_filter_graph",
    "build_overlay_filter_chain",
]
