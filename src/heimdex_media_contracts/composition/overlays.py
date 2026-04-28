"""Pydantic models for the V2 overlay system.

Adds object-driven text and background overlays to CompositionSpec, alongside
the legacy SubtitleSpec[] which is kept for back-compat. The new editor writes
to ``CompositionSpec.overlays``; older compositions continue to use
``CompositionSpec.subtitles``.

Design rules (mirrors composition/schemas.py):
- All timing in milliseconds (int).
- Position as normalized floats [0.0, 1.0] relative to output canvas.
- Sizes (width_px / height_px) in absolute pixels — interpreted at render time
  against the output canvas.
- All colors as hex strings (#RRGGBB or #RRGGBBAA).
- Every field has a default so 0.11.0 payloads parse cleanly (overlays simply
  default to []).
- Discriminated union on ``kind`` so consumers can switch on shape statically.

Render contract: each OverlaySpec is baked to a transparent RGBA PNG by
``heimdex_media_pipelines.composition.overlay_render`` (NOT here — contracts
stays pydantic-only) and overlaid via ffmpeg ``overlay=enable='between(t,...)'``
in ``layer_index`` order.
"""

from __future__ import annotations

from typing import Annotated, Literal, Union

from pydantic import BaseModel, Field, field_validator, model_validator

from heimdex_media_contracts.composition._colors import _validate_hex_color


# ---------------------------------------------------------------------------
# Transform / Effects
# ---------------------------------------------------------------------------

class TransformSpec(BaseModel):
    """Position, rotation, and optional explicit size for an overlay.

    Position is the *anchor* point of the overlay (center) on the canvas,
    normalized to [0, 1]. Rotation is in degrees, applied after positioning.

    width_px / height_px are optional: text overlays leave them None and
    auto-size from text + font metrics; background overlays must set them.
    """

    x: float = Field(default=0.5, ge=0.0, le=1.0)
    y: float = Field(default=0.5, ge=0.0, le=1.0)
    rotation_deg: float = Field(default=0.0, ge=-360.0, le=360.0)
    width_px: int | None = Field(default=None, ge=1, le=10_000)
    height_px: int | None = Field(default=None, ge=1, le=10_000)


class StrokeSpec(BaseModel):
    """Outline applied to text glyphs or background rect edges."""

    color: str = Field(default="#000000")
    width_px: int = Field(default=1, ge=0, le=50)

    @field_validator("color")
    @classmethod
    def _valid_color(cls, v: str) -> str:
        return _validate_hex_color(v)


class ShadowSpec(BaseModel):
    """Drop shadow with blur and spread, CSS-style.

    Note: drawtext's native ``shadowx/shadowy/shadowcolor`` is hard-shadow
    only (no blur, no spread). Rendering this spec faithfully requires the
    PNG-overlay path (PIL ``ImageFilter.GaussianBlur`` for blur, dilation
    for spread). The ffmpeg-string filter builder ignores blur/spread; only
    the bake renderer honors them.
    """

    color: str = Field(default="#000000")
    offset_x: int = Field(default=0, ge=-100, le=100)
    offset_y: int = Field(default=4, ge=-100, le=100)
    blur_px: int = Field(default=0, ge=0, le=200)
    spread_px: int = Field(default=0, ge=0, le=100)

    @field_validator("color")
    @classmethod
    def _valid_color(cls, v: str) -> str:
        return _validate_hex_color(v)


class EffectsSpec(BaseModel):
    """Global opacity + optional stroke + optional shadow.

    ``opacity`` is the alpha multiplier applied to the *entire* baked PNG
    (text + its stroke + its shadow) — distinct from ``font_color``'s alpha
    or a highlight box's opacity. Use opacity to fade an overlay without
    re-coloring it.
    """

    opacity: float = Field(default=1.0, ge=0.0, le=1.0)
    stroke: StrokeSpec | None = Field(default=None)
    shadow: ShadowSpec | None = Field(default=None)


# ---------------------------------------------------------------------------
# Text overlay
# ---------------------------------------------------------------------------

class TextOverlaySpec(BaseModel):
    """Rich-text overlay with full typographic + transform + effects controls.

    The ``kind`` discriminator is fixed to ``"text"`` and used by ``OverlaySpec``
    to switch shape statically. Frontend and worker rely on this tag.
    """

    kind: Literal["text"] = "text"

    # Identity / lifecycle
    id: str = Field(min_length=1, max_length=64)
    start_ms: int = Field(ge=0)
    end_ms: int = Field(ge=0)
    layer_index: int = Field(default=0, ge=0)

    transform: TransformSpec = Field(default_factory=TransformSpec)
    effects: EffectsSpec = Field(default_factory=EffectsSpec)

    # Content
    text: str = Field(default="", max_length=500)

    # Font
    font_family: Literal["Pretendard", "Noto Sans KR"] = "Pretendard"
    font_size_px: int = Field(default=36, ge=8, le=200)
    font_weight: int = Field(default=400, ge=100, le=900)
    italic: bool = False
    underline: bool = False
    font_color: str = Field(default="#FFFFFF")

    # Paragraph
    text_align: Literal["left", "center", "right"] = "center"
    line_height: float = Field(default=1.3, ge=0.5, le=3.0)
    letter_spacing: float = Field(default=0.0, ge=-5.0, le=20.0)

    # Optional text-fitted highlight (replaces the legacy
    # SubtitleStyleSpec.background_color — text overlay's own pill background,
    # NOT a free-floating background overlay).
    highlight_color: str | None = Field(default=None)
    highlight_padding_px: int = Field(default=8, ge=0, le=50)
    highlight_opacity: float = Field(default=1.0, ge=0.0, le=1.0)

    @field_validator("font_color")
    @classmethod
    def _valid_font_color(cls, v: str) -> str:
        return _validate_hex_color(v)

    @field_validator("highlight_color")
    @classmethod
    def _valid_highlight_color(cls, v: str | None) -> str | None:
        if v is None:
            return v
        return _validate_hex_color(v)

    @field_validator("end_ms")
    @classmethod
    def _end_after_start(cls, v: int, info) -> int:
        # See composition/schemas.py — pydantic 2.7+ passes info.data=None
        # during JSON-mode round-trip validation.
        data = info.data or {}
        start = data.get("start_ms")
        if start is not None and v <= start:
            raise ValueError(f"end_ms ({v}) must be > start_ms ({start})")
        return v

    @property
    def duration_ms(self) -> int:
        return self.end_ms - self.start_ms

    @property
    def has_highlight(self) -> bool:
        return self.highlight_color is not None


# ---------------------------------------------------------------------------
# Background overlay
# ---------------------------------------------------------------------------

class BackgroundOverlaySpec(BaseModel):
    """Free-floating filled rectangle with transform + effects.

    Unlike text's optional ``highlight_color`` (which auto-sizes to the text),
    a background overlay has explicit ``transform.width_px`` / ``height_px``
    and is independent of any text. Use cases: title cards, color blocks,
    callout shapes.

    Image-backed backgrounds are intentionally OUT OF SCOPE for v0.12 — the
    image-insert button in the editor is rendered disabled. A future spec
    revision can add an ``image_url`` discriminator without breaking this one.
    """

    kind: Literal["background"] = "background"

    # Identity / lifecycle
    id: str = Field(min_length=1, max_length=64)
    start_ms: int = Field(ge=0)
    end_ms: int = Field(ge=0)
    layer_index: int = Field(default=0, ge=0)

    transform: TransformSpec = Field(default_factory=TransformSpec)
    effects: EffectsSpec = Field(default_factory=EffectsSpec)

    # Fill
    fill_color: str = Field(default="#000000")

    @field_validator("fill_color")
    @classmethod
    def _valid_fill_color(cls, v: str) -> str:
        return _validate_hex_color(v)

    @field_validator("end_ms")
    @classmethod
    def _end_after_start(cls, v: int, info) -> int:
        data = info.data or {}
        start = data.get("start_ms")
        if start is not None and v <= start:
            raise ValueError(f"end_ms ({v}) must be > start_ms ({start})")
        return v

    @model_validator(mode="after")
    def _require_dimensions(self) -> "BackgroundOverlaySpec":
        # Background must have explicit size — text auto-sizes from its content
        # and font, but a free-floating rect needs W/H or there's nothing to draw.
        if self.transform.width_px is None or self.transform.height_px is None:
            raise ValueError(
                "BackgroundOverlaySpec requires transform.width_px and "
                "transform.height_px (text overlays auto-size; backgrounds do not)."
            )
        return self

    @property
    def duration_ms(self) -> int:
        return self.end_ms - self.start_ms


# ---------------------------------------------------------------------------
# Discriminated union
# ---------------------------------------------------------------------------

OverlaySpec = Annotated[
    Union[TextOverlaySpec, BackgroundOverlaySpec],
    Field(discriminator="kind"),
]
"""Union type for any overlay. Switch on ``.kind`` to narrow.

Pydantic uses the ``kind`` field for fast validation: a payload with
``kind="text"`` validates only against TextOverlaySpec, never trying
BackgroundOverlaySpec. This keeps error messages targeted and parsing fast.
"""


__all__ = [
    "BackgroundOverlaySpec",
    "EffectsSpec",
    "OverlaySpec",
    "ShadowSpec",
    "StrokeSpec",
    "TextOverlaySpec",
    "TransformSpec",
]
