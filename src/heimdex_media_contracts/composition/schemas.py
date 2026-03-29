"""Pydantic models for video composition rendering.

Defines the CompositionSpec — the single contract between the editor UI,
the API layer, and the ffmpeg render pipeline. Every field here maps to
a concrete ffmpeg filter parameter or encoding setting.

Design rules:
- All timing in milliseconds (int).
- All positions/coordinates as normalized floats [0.0, 1.0].
- All colors as hex strings (#RRGGBB or #RRGGBBAA).
- Defaults produce a valid 9:16 vertical short with sane encoding.
"""

from __future__ import annotations

import re
from typing import Literal

from pydantic import BaseModel, Field, field_validator, model_validator


# ---------------------------------------------------------------------------
# Color validation
# ---------------------------------------------------------------------------

_HEX_COLOR_RE = re.compile(r"^#(?:[0-9a-fA-F]{6}|[0-9a-fA-F]{8})$")


def _validate_hex_color(v: str) -> str:
    if not _HEX_COLOR_RE.match(v):
        raise ValueError(f"Invalid hex color: {v!r} (expected #RRGGBB or #RRGGBBAA)")
    return v.upper()


# ---------------------------------------------------------------------------
# OutputSpec
# ---------------------------------------------------------------------------

class OutputSpec(BaseModel):
    """Final rendered video output settings.

    Defaults to 9:16 vertical short at 720p (406x720).
    Width/height must be even (libx264 requirement).
    """

    width: int = Field(default=406, ge=128, le=3840)
    height: int = Field(default=720, ge=128, le=3840)
    fps: int = Field(default=30, ge=1, le=120)
    format: Literal["mp4", "webm"] = "mp4"
    background_color: str = Field(default="#000000")

    @field_validator("width", "height")
    @classmethod
    def _must_be_even(cls, v: int) -> int:
        if v % 2 != 0:
            raise ValueError(
                f"Dimension {v} is odd — libx264 requires even width/height. "
                f"Use {v + 1} or {v - 1} instead."
            )
        return v

    @field_validator("background_color")
    @classmethod
    def _valid_bg_color(cls, v: str) -> str:
        return _validate_hex_color(v)

    @property
    def aspect_ratio(self) -> float:
        return self.width / self.height

    @property
    def is_vertical(self) -> bool:
        return self.height > self.width

    @property
    def resolution_label(self) -> str:
        """Resolution label based on vertical line count (height)."""
        if self.height <= 480:
            return "480p"
        if self.height <= 720:
            return "720p"
        if self.height <= 1080:
            return "1080p"
        return f"{self.height}p"


# ---------------------------------------------------------------------------
# SceneClipSpec
# ---------------------------------------------------------------------------

class SceneClipSpec(BaseModel):
    """A single clip segment in the composition timeline.

    Represents a time range [start_ms, end_ms) from a source video,
    placed at timeline_start_ms on the composition timeline.

    The clip can optionally be cropped to a sub-region of the source frame
    using crop_x/crop_y/crop_w/crop_h (normalized 0.0-1.0).
    """

    scene_id: str = Field(min_length=1)
    video_id: str = Field(min_length=1)
    source_type: Literal["gdrive", "removable_disk", "local", "youtube"] = "gdrive"
    start_ms: int = Field(ge=0)
    end_ms: int = Field(ge=0)
    timeline_start_ms: int = Field(default=0, ge=0)

    # Volume control (0.0 = mute, 1.0 = original, >1.0 = amplify)
    volume: float = Field(default=1.0, ge=0.0, le=3.0)

    # Optional spatial crop (normalized coordinates, applied before scaling)
    crop_x: float = Field(default=0.0, ge=0.0, le=1.0)
    crop_y: float = Field(default=0.0, ge=0.0, le=1.0)
    crop_w: float = Field(default=1.0, gt=0.0, le=1.0)
    crop_h: float = Field(default=1.0, gt=0.0, le=1.0)

    @field_validator("end_ms")
    @classmethod
    def _end_after_start(cls, v: int, info) -> int:
        start = info.data.get("start_ms")
        if start is not None and v <= start:
            raise ValueError(f"end_ms ({v}) must be > start_ms ({start})")
        return v

    @property
    def duration_ms(self) -> int:
        return self.end_ms - self.start_ms

    @property
    def timeline_end_ms(self) -> int:
        return self.timeline_start_ms + self.duration_ms

    @property
    def has_crop(self) -> bool:
        return not (
            self.crop_x == 0.0
            and self.crop_y == 0.0
            and self.crop_w == 1.0
            and self.crop_h == 1.0
        )

    @model_validator(mode="after")
    def _crop_bounds_valid(self) -> "SceneClipSpec":
        if self.crop_x + self.crop_w > 1.0 + 1e-6:
            raise ValueError(
                f"crop_x ({self.crop_x}) + crop_w ({self.crop_w}) exceeds 1.0"
            )
        if self.crop_y + self.crop_h > 1.0 + 1e-6:
            raise ValueError(
                f"crop_y ({self.crop_y}) + crop_h ({self.crop_h}) exceeds 1.0"
            )
        return self


# ---------------------------------------------------------------------------
# SubtitleStyleSpec
# ---------------------------------------------------------------------------

class SubtitleStyleSpec(BaseModel):
    """Visual styling for a subtitle overlay.

    Positions are normalized [0.0, 1.0] relative to the output canvas.
    Defaults produce a centered white bold caption near the bottom.
    """

    font_family: str = Field(default="Pretendard")
    font_size_px: int = Field(default=36, ge=8, le=200)
    font_color: str = Field(default="#FFFFFF")
    font_weight: int = Field(default=700, ge=100, le=900)
    text_align: Literal["left", "center", "right"] = "center"
    line_height: float = Field(default=1.3, ge=0.5, le=3.0)
    letter_spacing: float = Field(default=0, ge=-5.0, le=20.0)

    # Position (normalized 0.0-1.0, anchor = center of text block)
    position_x: float = Field(default=0.5, ge=0.0, le=1.0)
    position_y: float = Field(default=0.85, ge=0.0, le=1.0)

    # Background box behind text
    background_color: str | None = Field(default=None)
    background_padding: int = Field(default=8, ge=0, le=50)
    background_opacity: float = Field(default=0.6, ge=0.0, le=1.0)

    # Text effects
    stroke_color: str | None = Field(default=None)
    stroke_width: int = Field(default=0, ge=0, le=10)
    shadow_enabled: bool = True
    shadow_color: str | None = Field(default=None)
    shadow_offset_x: int = Field(default=0, ge=-20, le=20)
    shadow_offset_y: int = Field(default=2, ge=-20, le=20)

    @field_validator("font_color")
    @classmethod
    def _valid_font_color(cls, v: str) -> str:
        return _validate_hex_color(v)

    @field_validator("background_color", "stroke_color", "shadow_color")
    @classmethod
    def _valid_optional_color(cls, v: str | None) -> str | None:
        if v is None:
            return v
        return _validate_hex_color(v)

    @property
    def has_background(self) -> bool:
        return self.background_color is not None

    @property
    def has_stroke(self) -> bool:
        return self.stroke_color is not None and self.stroke_width > 0

    @property
    def has_shadow(self) -> bool:
        return self.shadow_enabled and self.shadow_color is not None


# ---------------------------------------------------------------------------
# SubtitleSpec
# ---------------------------------------------------------------------------

class SubtitleSpec(BaseModel):
    """A single subtitle overlay on the composition timeline.

    The text appears between start_ms and end_ms on the timeline,
    styled according to the SubtitleStyleSpec.
    """

    text: str = Field(min_length=1, max_length=500)
    start_ms: int = Field(ge=0)
    end_ms: int = Field(ge=0)
    template_id: str | None = None
    style: SubtitleStyleSpec = Field(default_factory=SubtitleStyleSpec)

    @field_validator("end_ms")
    @classmethod
    def _end_after_start(cls, v: int, info) -> int:
        start = info.data.get("start_ms")
        if start is not None and v <= start:
            raise ValueError(f"end_ms ({v}) must be > start_ms ({start})")
        return v

    @property
    def duration_ms(self) -> int:
        return self.end_ms - self.start_ms


# ---------------------------------------------------------------------------
# TransitionSpec (for future use)
# ---------------------------------------------------------------------------

class TransitionSpec(BaseModel):
    """Transition between two adjacent clips.

    Applied between clip at `clip_index` and clip at `clip_index + 1`.
    Duration is subtracted from the gap/overlap between clips.
    """

    clip_index: int = Field(ge=0)
    type: Literal["crossfade", "fade_black", "fade_white", "cut"] = "cut"
    duration_ms: int = Field(default=500, ge=0, le=5000)


# ---------------------------------------------------------------------------
# CompositionSpec
# ---------------------------------------------------------------------------

class CompositionSpec(BaseModel):
    """Top-level composition contract.

    This is THE schema that flows through the entire render pipeline:
    Editor UI -> API -> SQS -> Render Worker -> FFmpeg.

    All consumers must agree on this shape. Changes here require
    coordinated updates to: livecommerce API, render worker, media
    pipelines, and the frontend editor.
    """

    output: OutputSpec = Field(default_factory=OutputSpec)
    scene_clips: list[SceneClipSpec] = Field(min_length=1)
    subtitles: list[SubtitleSpec] = Field(default_factory=list)
    transitions: list[TransitionSpec] = Field(default_factory=list)

    # Metadata (not used by render pipeline, stored for editor state)
    title: str | None = Field(default=None, max_length=255)
    version: int = Field(default=1, ge=1)

    @property
    def total_duration_ms(self) -> int:
        """Total timeline duration (clips + subtitles)."""
        clip_end = max((c.timeline_end_ms for c in self.scene_clips), default=0)
        sub_end = max((s.end_ms for s in self.subtitles), default=0)
        return max(clip_end, sub_end)

    @property
    def clip_count(self) -> int:
        return len(self.scene_clips)

    @property
    def subtitle_count(self) -> int:
        return len(self.subtitles)

    @property
    def unique_video_ids(self) -> set[str]:
        return {clip.video_id for clip in self.scene_clips}

    @model_validator(mode="after")
    def _validate_timeline_consistency(self) -> "CompositionSpec":
        """Verify clips don't overlap on the timeline."""
        if len(self.scene_clips) < 2:
            return self

        sorted_clips = sorted(self.scene_clips, key=lambda c: c.timeline_start_ms)
        for i in range(len(sorted_clips) - 1):
            current = sorted_clips[i]
            next_clip = sorted_clips[i + 1]
            if current.timeline_end_ms > next_clip.timeline_start_ms:
                raise ValueError(
                    f"Clip overlap detected: clip ending at {current.timeline_end_ms}ms "
                    f"overlaps with clip starting at {next_clip.timeline_start_ms}ms. "
                    f"Clips: {current.scene_id} and {next_clip.scene_id}."
                )
        return self

    @model_validator(mode="after")
    def _validate_subtitle_bounds(self) -> "CompositionSpec":
        """Subtitles should fall within the timeline duration."""
        clip_end = max((c.timeline_end_ms for c in self.scene_clips), default=0)
        for i, sub in enumerate(self.subtitles):
            if sub.start_ms > clip_end:
                raise ValueError(
                    f"Subtitle {i} starts at {sub.start_ms}ms but clip timeline "
                    f"ends at {clip_end}ms."
                )
        return self

    @model_validator(mode="after")
    def _validate_max_duration(self) -> "CompositionSpec":
        """Enforce 5-minute maximum composition duration."""
        max_ms = 5 * 60 * 1000  # 300_000
        if self.total_duration_ms > max_ms:
            raise ValueError(
                f"Composition duration {self.total_duration_ms}ms exceeds "
                f"maximum of {max_ms}ms (5 minutes)."
            )
        return self

    @model_validator(mode="after")
    def _validate_transition_indices(self) -> "CompositionSpec":
        """Transition clip_index must refer to a valid clip pair."""
        max_idx = len(self.scene_clips) - 2  # last valid index for transitions
        for t in self.transitions:
            if t.clip_index > max_idx:
                raise ValueError(
                    f"Transition clip_index {t.clip_index} is out of range "
                    f"(max: {max_idx} for {len(self.scene_clips)} clips)."
                )
        return self

    def get_clip_at_time(self, time_ms: int) -> SceneClipSpec | None:
        """Return the clip playing at a given timeline position."""
        for clip in self.scene_clips:
            if clip.timeline_start_ms <= time_ms < clip.timeline_end_ms:
                return clip
        return None

    def get_source_time(self, timeline_ms: int) -> tuple[str, int] | None:
        """Map a timeline position to (video_id, source_ms).

        Used by the preview player to seek the correct source video.
        """
        clip = self.get_clip_at_time(timeline_ms)
        if clip is None:
            return None
        offset = timeline_ms - clip.timeline_start_ms
        source_ms = clip.start_ms + offset
        return (clip.video_id, source_ms)

    def get_active_subtitles(self, time_ms: int) -> list[SubtitleSpec]:
        """Return all subtitles visible at a given timeline position."""
        return [
            sub for sub in self.subtitles
            if sub.start_ms <= time_ms < sub.end_ms
        ]

    def to_timeline_summary(self) -> list[dict]:
        """Return a simplified timeline for UI rendering."""
        return [
            {
                "scene_id": clip.scene_id,
                "video_id": clip.video_id,
                "start_ms": clip.timeline_start_ms,
                "end_ms": clip.timeline_end_ms,
                "source_start_ms": clip.start_ms,
                "source_end_ms": clip.end_ms,
                "duration_ms": clip.duration_ms,
            }
            for clip in sorted(self.scene_clips, key=lambda c: c.timeline_start_ms)
        ]
