from pydantic import BaseModel, Field, model_validator
from typing import Literal


class OutputSpec(BaseModel):
    width: int = Field(405, gt=0)
    height: int = Field(720, gt=0)
    fps: int = Field(30, gt=0)
    format: str = "mp4"
    background_color: str = "#000000"


class SceneClipSpec(BaseModel):
    """A scene clip placed on the output timeline.

    - start_ms / end_ms: source video range (trimmable portion of the scene)
    - timeline_start_ms: where this clip begins on the output timeline
    - Gaps between clips are filled with OutputSpec.background_color
    """

    scene_id: str
    video_id: str
    source_type: Literal["gdrive", "removable_disk", "local", "youtube"] = "gdrive"
    start_ms: int = Field(ge=0)
    end_ms: int = Field(gt=0)
    timeline_start_ms: int = Field(ge=0)

    @model_validator(mode="after")
    def end_after_start(self):
        if self.end_ms <= self.start_ms:
            raise ValueError("end_ms must be greater than start_ms")
        return self

    @property
    def duration_ms(self) -> int:
        return self.end_ms - self.start_ms

    @property
    def timeline_end_ms(self) -> int:
        return self.timeline_start_ms + self.duration_ms


class SubtitleStyleSpec(BaseModel):
    font_family: str = "Noto Sans KR"
    font_size_px: int = Field(48, ge=12, le=120)
    font_color: str = "#FFFFFF"
    font_weight: int = Field(700, ge=100, le=900)
    line_height: float = Field(1.4, ge=0.5, le=3.0)
    letter_spacing: float = Field(0, ge=-5.0, le=20.0)
    text_align: Literal["left", "center", "right"] = "center"
    position_x: float = Field(0.5, ge=0.0, le=1.0)
    position_y: float = Field(0.85, ge=0.0, le=1.0)
    shadow_enabled: bool = True
    shadow_color: str = "#000000"
    shadow_offset_x: int = 2
    shadow_offset_y: int = 2
    shadow_blur: int = Field(4, ge=0)
    background_enabled: bool = False
    background_color: str | None = None
    background_padding: int = Field(8, ge=0)


class SubtitleSpec(BaseModel):
    """Text overlay on the output timeline.

    start_ms / end_ms are absolute positions on the OUTPUT timeline,
    not relative to any clip.
    """

    text: str = Field(min_length=1, max_length=200)
    start_ms: int = Field(ge=0)
    end_ms: int = Field(gt=0)
    template_id: str | None = None
    style: SubtitleStyleSpec = SubtitleStyleSpec()

    @model_validator(mode="after")
    def end_after_start(self):
        if self.end_ms <= self.start_ms:
            raise ValueError("end_ms must be greater than start_ms")
        return self


class CompositionSpec(BaseModel):
    """Timeline-based composition spec.

    Scene clips are placed at arbitrary positions on the output timeline via timeline_start_ms.
    Gaps between clips are filled with output.background_color.
    Subtitle start_ms/end_ms are positions on the OUTPUT timeline (absolute).
    Total output duration = max(scene clip timeline ends, subtitle ends).
    """

    output: OutputSpec = OutputSpec()
    scene_clips: list[SceneClipSpec] = Field(min_length=1)
    subtitles: list[SubtitleSpec] = []

    @model_validator(mode="after")
    def no_scene_clip_overlaps(self):
        sorted_clips = sorted(self.scene_clips, key=lambda c: c.timeline_start_ms)
        for i in range(len(sorted_clips) - 1):
            if sorted_clips[i].timeline_end_ms > sorted_clips[i + 1].timeline_start_ms:
                raise ValueError(
                    f"Scene clips overlap on timeline: clip ending at {sorted_clips[i].timeline_end_ms}ms "
                    f"overlaps clip starting at {sorted_clips[i + 1].timeline_start_ms}ms"
                )
        return self

    @property
    def total_duration_ms(self) -> int:
        clip_end = max((c.timeline_end_ms for c in self.scene_clips), default=0)
        sub_end = max((s.end_ms for s in self.subtitles), default=0)
        return max(clip_end, sub_end)
