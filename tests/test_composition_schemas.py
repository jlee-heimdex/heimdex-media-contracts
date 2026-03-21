"""Tests for composition schema validation."""

import pytest
from pydantic import ValidationError

from heimdex_media_contracts.composition.schemas import (
    CompositionSpec,
    OutputSpec,
    SceneClipSpec,
    SubtitleSpec,
    SubtitleStyleSpec,
)


def _make_clip(**overrides) -> dict:
    defaults = {
        "scene_id": "s1",
        "video_id": "v1",
        "start_ms": 0,
        "end_ms": 10000,
        "timeline_start_ms": 0,
    }
    defaults.update(overrides)
    return defaults


class TestCompositionSpec:
    def test_valid_composition(self):
        spec = CompositionSpec(scene_clips=[SceneClipSpec(**_make_clip())])
        assert len(spec.scene_clips) == 1

    def test_empty_scene_clips_rejected(self):
        with pytest.raises(ValidationError):
            CompositionSpec(scene_clips=[])

    def test_total_duration_ms(self):
        clip = SceneClipSpec(**_make_clip(start_ms=0, end_ms=10000, timeline_start_ms=5000))
        spec = CompositionSpec(scene_clips=[clip])
        assert spec.total_duration_ms == 15000

    def test_total_duration_ms_with_subtitle_past_clips(self):
        clip = SceneClipSpec(**_make_clip(start_ms=10000, end_ms=30000, timeline_start_ms=10000))
        sub = SubtitleSpec(text="Hello", start_ms=45000, end_ms=50000)
        spec = CompositionSpec(scene_clips=[clip], subtitles=[sub])
        assert spec.total_duration_ms == 50000


class TestSceneClipSpec:
    def test_gdrive_source_type(self):
        clip = SceneClipSpec(**_make_clip(source_type="gdrive"))
        assert clip.source_type == "gdrive"

    def test_youtube_source_type(self):
        clip = SceneClipSpec(**_make_clip(source_type="youtube"))
        assert clip.source_type == "youtube"

    def test_invalid_source_type_rejected(self):
        with pytest.raises(ValidationError):
            SceneClipSpec(**_make_clip(source_type="invalid"))

    def test_end_before_start_rejected(self):
        with pytest.raises(ValidationError):
            SceneClipSpec(**_make_clip(start_ms=5000, end_ms=3000))

    def test_end_ms_zero_rejected(self):
        with pytest.raises(ValidationError):
            SceneClipSpec(**_make_clip(start_ms=0, end_ms=0))

    def test_negative_start_ms_rejected(self):
        with pytest.raises(ValidationError):
            SceneClipSpec(**_make_clip(start_ms=-1))

    def test_timeline_end_ms(self):
        clip = SceneClipSpec(**_make_clip(start_ms=0, end_ms=10000, timeline_start_ms=10000))
        assert clip.timeline_end_ms == 20000

    def test_negative_timeline_start_ms_rejected(self):
        with pytest.raises(ValidationError):
            SceneClipSpec(**_make_clip(timeline_start_ms=-1))

    def test_adjacent_clips_pass(self):
        clip1 = SceneClipSpec(**_make_clip(scene_id="s1", start_ms=0, end_ms=10000, timeline_start_ms=0))
        clip2 = SceneClipSpec(**_make_clip(scene_id="s2", start_ms=0, end_ms=10000, timeline_start_ms=10000))
        spec = CompositionSpec(scene_clips=[clip1, clip2])
        assert len(spec.scene_clips) == 2

    def test_overlapping_clips_rejected(self):
        clip1 = SceneClipSpec(**_make_clip(scene_id="s1", start_ms=0, end_ms=15000, timeline_start_ms=0))
        clip2 = SceneClipSpec(**_make_clip(scene_id="s2", start_ms=0, end_ms=10000, timeline_start_ms=10000))
        with pytest.raises(ValidationError, match="overlap"):
            CompositionSpec(scene_clips=[clip1, clip2])

    def test_gap_between_clips_pass(self):
        clip1 = SceneClipSpec(**_make_clip(scene_id="s1", start_ms=0, end_ms=10000, timeline_start_ms=0))
        clip2 = SceneClipSpec(**_make_clip(scene_id="s2", start_ms=0, end_ms=10000, timeline_start_ms=20000))
        spec = CompositionSpec(scene_clips=[clip1, clip2])
        assert len(spec.scene_clips) == 2


class TestSubtitleSpec:
    def test_empty_text_rejected(self):
        with pytest.raises(ValidationError):
            SubtitleSpec(text="", start_ms=0, end_ms=1000)

    def test_text_too_long_rejected(self):
        with pytest.raises(ValidationError):
            SubtitleSpec(text="x" * 201, start_ms=0, end_ms=1000)

    def test_end_before_start_rejected(self):
        with pytest.raises(ValidationError):
            SubtitleSpec(text="hello", start_ms=5000, end_ms=3000)


class TestSubtitleStyleSpec:
    def test_font_size_too_large_rejected(self):
        with pytest.raises(ValidationError):
            SubtitleStyleSpec(font_size_px=200)

    def test_font_size_too_small_rejected(self):
        with pytest.raises(ValidationError):
            SubtitleStyleSpec(font_size_px=5)

    def test_position_x_out_of_range_rejected(self):
        with pytest.raises(ValidationError):
            SubtitleStyleSpec(position_x=1.5)

    def test_default_weight(self):
        style = SubtitleStyleSpec(font_weight=700)
        assert style.font_weight == 700

    def test_weight_too_large_rejected(self):
        with pytest.raises(ValidationError):
            SubtitleStyleSpec(font_weight=1000)

    def test_default_line_height(self):
        style = SubtitleStyleSpec(line_height=1.4)
        assert style.line_height == 1.4

    def test_custom_letter_spacing(self):
        style = SubtitleStyleSpec(letter_spacing=5.0)
        assert style.letter_spacing == 5.0


class TestOutputSpec:
    def test_defaults(self):
        out = OutputSpec()
        assert out.width == 406
        assert out.height == 720
        assert out.fps == 30
        assert out.background_color == "#000000"
