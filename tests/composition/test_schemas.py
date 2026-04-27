"""Tests for composition schema validation, defaults, and computed properties."""

import pytest
from pydantic import ValidationError

from heimdex_media_contracts.composition import (
    CompositionSpec,
    OutputSpec,
    SceneClipSpec,
    SubtitleSpec,
    SubtitleStyleSpec,
    TransitionSpec,
)


# ---------------------------------------------------------------------------
# OutputSpec
# ---------------------------------------------------------------------------

class TestOutputSpec:
    def test_defaults(self):
        spec = OutputSpec()
        assert spec.width == 406
        assert spec.height == 720
        assert spec.fps == 30
        assert spec.format == "mp4"
        assert spec.background_color == "#000000"

    def test_is_vertical(self):
        assert OutputSpec().is_vertical is True
        assert OutputSpec(width=1920, height=1080).is_vertical is False

    def test_aspect_ratio(self):
        spec = OutputSpec(width=1080, height=1920)
        assert abs(spec.aspect_ratio - 1080 / 1920) < 0.001

    def test_resolution_label(self):
        assert OutputSpec(width=406, height=720).resolution_label == "720p"
        assert OutputSpec(width=1080, height=1920).resolution_label == "1920p"
        assert OutputSpec(width=270, height=480).resolution_label == "480p"
        assert OutputSpec(width=1920, height=1080).resolution_label == "1080p"
        assert OutputSpec(width=128, height=128).resolution_label == "480p"

    def test_odd_width_rejected(self):
        with pytest.raises(ValidationError, match="odd"):
            OutputSpec(width=405)

    def test_odd_height_rejected(self):
        with pytest.raises(ValidationError, match="odd"):
            OutputSpec(height=721)

    def test_invalid_background_color(self):
        with pytest.raises(ValidationError, match="hex color"):
            OutputSpec(background_color="red")

    def test_hex_color_uppercased(self):
        spec = OutputSpec(background_color="#aabbcc")
        assert spec.background_color == "#AABBCC"

    def test_8_digit_hex_accepted(self):
        spec = OutputSpec(background_color="#aabbccdd")
        assert spec.background_color == "#AABBCCDD"

    def test_min_max_dimensions(self):
        OutputSpec(width=128, height=128)
        with pytest.raises(ValidationError):
            OutputSpec(width=126, height=128)

    def test_webm_format(self):
        spec = OutputSpec(format="webm")
        assert spec.format == "webm"


# ---------------------------------------------------------------------------
# SceneClipSpec
# ---------------------------------------------------------------------------

class TestSceneClipSpec:
    def test_minimal(self):
        clip = SceneClipSpec(
            scene_id="s1",
            video_id="v1",
            start_ms=0,
            end_ms=10000,
        )
        assert clip.duration_ms == 10000
        assert clip.timeline_start_ms == 0
        assert clip.timeline_end_ms == 10000
        assert clip.source_type == "gdrive"
        assert clip.volume == 1.0

    def test_end_must_be_after_start(self):
        with pytest.raises(ValidationError, match="end_ms"):
            SceneClipSpec(scene_id="s1", video_id="v1", start_ms=5000, end_ms=5000)

    def test_end_before_start_rejected(self):
        with pytest.raises(ValidationError, match="end_ms"):
            SceneClipSpec(scene_id="s1", video_id="v1", start_ms=5000, end_ms=3000)

    def test_timeline_end_ms(self):
        clip = SceneClipSpec(
            scene_id="s1", video_id="v1",
            start_ms=1000, end_ms=6000,
            timeline_start_ms=10000,
        )
        assert clip.duration_ms == 5000
        assert clip.timeline_end_ms == 15000

    def test_has_crop_false_by_default(self):
        clip = SceneClipSpec(scene_id="s1", video_id="v1", start_ms=0, end_ms=1000)
        assert clip.has_crop is False

    def test_has_crop_true(self):
        clip = SceneClipSpec(
            scene_id="s1", video_id="v1", start_ms=0, end_ms=1000,
            crop_x=0.1, crop_y=0.1, crop_w=0.8, crop_h=0.8,
        )
        assert clip.has_crop is True

    def test_crop_out_of_bounds(self):
        with pytest.raises(ValidationError, match="crop_x.*exceeds"):
            SceneClipSpec(
                scene_id="s1", video_id="v1", start_ms=0, end_ms=1000,
                crop_x=0.5, crop_w=0.6,
            )

    def test_crop_y_out_of_bounds(self):
        with pytest.raises(ValidationError, match="crop_y.*exceeds"):
            SceneClipSpec(
                scene_id="s1", video_id="v1", start_ms=0, end_ms=1000,
                crop_y=0.5, crop_h=0.6,
            )

    def test_volume_range(self):
        SceneClipSpec(scene_id="s1", video_id="v1", start_ms=0, end_ms=1000, volume=0.0)
        SceneClipSpec(scene_id="s1", video_id="v1", start_ms=0, end_ms=1000, volume=3.0)
        with pytest.raises(ValidationError):
            SceneClipSpec(scene_id="s1", video_id="v1", start_ms=0, end_ms=1000, volume=-0.1)

    def test_empty_scene_id_rejected(self):
        with pytest.raises(ValidationError):
            SceneClipSpec(scene_id="", video_id="v1", start_ms=0, end_ms=1000)

    def test_negative_start_rejected(self):
        with pytest.raises(ValidationError):
            SceneClipSpec(scene_id="s1", video_id="v1", start_ms=-1, end_ms=1000)


# ---------------------------------------------------------------------------
# SubtitleStyleSpec
# ---------------------------------------------------------------------------

class TestSubtitleStyleSpec:
    def test_defaults(self):
        style = SubtitleStyleSpec()
        assert style.font_family == "Pretendard"
        assert style.font_size_px == 36
        assert style.font_color == "#FFFFFF"
        assert style.font_weight == 700
        assert style.text_align == "center"
        assert style.position_x == 0.5
        assert style.position_y == 0.85

    def test_has_background_false_by_default(self):
        assert SubtitleStyleSpec().has_background is False

    def test_has_background_true(self):
        style = SubtitleStyleSpec(background_color="#000000")
        assert style.has_background is True

    def test_has_stroke(self):
        assert SubtitleStyleSpec().has_stroke is False
        assert SubtitleStyleSpec(stroke_color="#000000", stroke_width=2).has_stroke is True
        assert SubtitleStyleSpec(stroke_color="#000000", stroke_width=0).has_stroke is False

    def test_has_shadow(self):
        assert SubtitleStyleSpec().has_shadow is False
        assert SubtitleStyleSpec(shadow_color="#000000").has_shadow is True
        assert SubtitleStyleSpec(shadow_enabled=False, shadow_color="#000000").has_shadow is False

    def test_invalid_font_color(self):
        with pytest.raises(ValidationError, match="hex color"):
            SubtitleStyleSpec(font_color="white")

    def test_font_size_range(self):
        SubtitleStyleSpec(font_size_px=8)
        SubtitleStyleSpec(font_size_px=200)
        with pytest.raises(ValidationError):
            SubtitleStyleSpec(font_size_px=7)


# ---------------------------------------------------------------------------
# SubtitleSpec
# ---------------------------------------------------------------------------

class TestSubtitleSpec:
    def test_minimal(self):
        sub = SubtitleSpec(text="Hello", start_ms=0, end_ms=5000)
        assert sub.duration_ms == 5000
        assert sub.style.font_family == "Pretendard"

    def test_end_must_be_after_start(self):
        with pytest.raises(ValidationError, match="end_ms"):
            SubtitleSpec(text="Hello", start_ms=5000, end_ms=5000)

    def test_empty_text_rejected(self):
        with pytest.raises(ValidationError):
            SubtitleSpec(text="", start_ms=0, end_ms=1000)

    def test_text_max_length(self):
        SubtitleSpec(text="x" * 500, start_ms=0, end_ms=1000)
        with pytest.raises(ValidationError):
            SubtitleSpec(text="x" * 501, start_ms=0, end_ms=1000)

    def test_korean_text(self):
        sub = SubtitleSpec(text="안녕하세요 세계!", start_ms=0, end_ms=3000)
        assert sub.text == "안녕하세요 세계!"

    def test_custom_style(self):
        sub = SubtitleSpec(
            text="Test",
            start_ms=0,
            end_ms=1000,
            style=SubtitleStyleSpec(font_family="Noto Sans KR", font_size_px=48),
        )
        assert sub.style.font_family == "Noto Sans KR"


# ---------------------------------------------------------------------------
# TransitionSpec
# ---------------------------------------------------------------------------

class TestTransitionSpec:
    def test_defaults(self):
        t = TransitionSpec(clip_index=0)
        assert t.type == "cut"
        assert t.duration_ms == 500

    def test_crossfade(self):
        t = TransitionSpec(clip_index=0, type="crossfade", duration_ms=1000)
        assert t.type == "crossfade"


# ---------------------------------------------------------------------------
# CompositionSpec
# ---------------------------------------------------------------------------

class TestCompositionSpec:
    def _clip(self, scene_id="s1", video_id="v1", start_ms=0, end_ms=10000, timeline_start_ms=0):
        return SceneClipSpec(
            scene_id=scene_id, video_id=video_id,
            start_ms=start_ms, end_ms=end_ms,
            timeline_start_ms=timeline_start_ms,
        )

    def test_minimal(self):
        spec = CompositionSpec(scene_clips=[self._clip()])
        assert spec.total_duration_ms == 10000
        assert spec.clip_count == 1
        assert spec.subtitle_count == 0
        assert spec.output.width == 406

    def test_total_duration_multi_clip(self):
        spec = CompositionSpec(scene_clips=[
            self._clip(scene_id="s1", start_ms=0, end_ms=5000, timeline_start_ms=0),
            self._clip(scene_id="s2", start_ms=0, end_ms=5000, timeline_start_ms=5000),
        ])
        assert spec.total_duration_ms == 10000

    def test_unique_video_ids(self):
        spec = CompositionSpec(scene_clips=[
            self._clip(scene_id="s1", video_id="v1", start_ms=0, end_ms=5000, timeline_start_ms=0),
            self._clip(scene_id="s2", video_id="v2", start_ms=0, end_ms=5000, timeline_start_ms=5000),
            self._clip(scene_id="s3", video_id="v1", start_ms=5000, end_ms=10000, timeline_start_ms=10000),
        ])
        assert spec.unique_video_ids == {"v1", "v2"}

    def test_overlapping_clips_rejected(self):
        with pytest.raises(ValidationError, match="overlap"):
            CompositionSpec(scene_clips=[
                self._clip(scene_id="s1", start_ms=0, end_ms=10000, timeline_start_ms=0),
                self._clip(scene_id="s2", start_ms=0, end_ms=5000, timeline_start_ms=5000),
            ])

    def test_adjacent_clips_ok(self):
        # Clips that touch exactly should be allowed
        CompositionSpec(scene_clips=[
            self._clip(scene_id="s1", start_ms=0, end_ms=5000, timeline_start_ms=0),
            self._clip(scene_id="s2", start_ms=0, end_ms=5000, timeline_start_ms=5000),
        ])

    def test_gap_between_clips_ok(self):
        CompositionSpec(scene_clips=[
            self._clip(scene_id="s1", start_ms=0, end_ms=5000, timeline_start_ms=0),
            self._clip(scene_id="s2", start_ms=0, end_ms=5000, timeline_start_ms=10000),
        ])

    def test_empty_clips_rejected(self):
        with pytest.raises(ValidationError):
            CompositionSpec(scene_clips=[])

    def test_subtitle_beyond_timeline_rejected(self):
        with pytest.raises(ValidationError, match="Subtitle.*starts"):
            CompositionSpec(
                scene_clips=[self._clip(start_ms=0, end_ms=5000)],
                subtitles=[SubtitleSpec(text="Late", start_ms=6000, end_ms=8000)],
            )

    def test_subtitle_within_timeline_ok(self):
        CompositionSpec(
            scene_clips=[self._clip(start_ms=0, end_ms=10000)],
            subtitles=[SubtitleSpec(text="Hello", start_ms=0, end_ms=5000)],
        )

    def test_max_duration_exceeded(self):
        with pytest.raises(ValidationError, match="5 minutes"):
            CompositionSpec(scene_clips=[
                self._clip(start_ms=0, end_ms=301000, timeline_start_ms=0),
            ])

    def test_max_duration_at_limit_ok(self):
        CompositionSpec(scene_clips=[
            self._clip(start_ms=0, end_ms=300000, timeline_start_ms=0),
        ])

    def test_get_clip_at_time(self):
        spec = CompositionSpec(scene_clips=[
            self._clip(scene_id="s1", start_ms=0, end_ms=5000, timeline_start_ms=0),
            self._clip(scene_id="s2", start_ms=0, end_ms=5000, timeline_start_ms=5000),
        ])
        assert spec.get_clip_at_time(2500).scene_id == "s1"
        assert spec.get_clip_at_time(7500).scene_id == "s2"
        assert spec.get_clip_at_time(5000).scene_id == "s2"
        assert spec.get_clip_at_time(10000) is None

    def test_get_source_time(self):
        spec = CompositionSpec(scene_clips=[
            self._clip(scene_id="s1", video_id="v1", start_ms=1000, end_ms=6000, timeline_start_ms=0),
        ])
        result = spec.get_source_time(2000)
        assert result == ("v1", 3000)

    def test_get_source_time_none(self):
        spec = CompositionSpec(scene_clips=[
            self._clip(start_ms=0, end_ms=5000, timeline_start_ms=0),
        ])
        assert spec.get_source_time(6000) is None

    def test_get_active_subtitles(self):
        spec = CompositionSpec(
            scene_clips=[self._clip(start_ms=0, end_ms=20000)],
            subtitles=[
                SubtitleSpec(text="A", start_ms=0, end_ms=5000),
                SubtitleSpec(text="B", start_ms=3000, end_ms=8000),
                SubtitleSpec(text="C", start_ms=10000, end_ms=15000),
            ],
        )
        active = spec.get_active_subtitles(4000)
        assert len(active) == 2
        assert {s.text for s in active} == {"A", "B"}

    def test_to_timeline_summary(self):
        spec = CompositionSpec(scene_clips=[
            self._clip(scene_id="s2", start_ms=5000, end_ms=10000, timeline_start_ms=5000),
            self._clip(scene_id="s1", start_ms=0, end_ms=5000, timeline_start_ms=0),
        ])
        summary = spec.to_timeline_summary()
        assert len(summary) == 2
        assert summary[0]["scene_id"] == "s1"  # sorted by timeline_start_ms
        assert summary[1]["scene_id"] == "s2"

    def test_transition_index_out_of_range(self):
        with pytest.raises(ValidationError, match="Transition clip_index"):
            CompositionSpec(
                scene_clips=[self._clip()],
                transitions=[TransitionSpec(clip_index=0)],
            )

    def test_transition_valid_index(self):
        CompositionSpec(
            scene_clips=[
                self._clip(scene_id="s1", start_ms=0, end_ms=5000, timeline_start_ms=0),
                self._clip(scene_id="s2", start_ms=0, end_ms=5000, timeline_start_ms=5000),
            ],
            transitions=[TransitionSpec(clip_index=0, type="crossfade")],
        )

    def test_version_defaults_to_1(self):
        spec = CompositionSpec(scene_clips=[self._clip()])
        assert spec.version == 1

    def test_title_metadata(self):
        spec = CompositionSpec(scene_clips=[self._clip()], title="My Short")
        assert spec.title == "My Short"


# ---------------------------------------------------------------------------
# Roundtrip serialization
# ---------------------------------------------------------------------------

class TestRoundtrip:
    def test_full_roundtrip(self):
        original = CompositionSpec(
            output=OutputSpec(width=1080, height=1920, fps=60),
            scene_clips=[
                SceneClipSpec(
                    scene_id="s1", video_id="v1", source_type="gdrive",
                    start_ms=0, end_ms=5000, timeline_start_ms=0,
                    volume=0.8, crop_x=0.1, crop_y=0.1, crop_w=0.8, crop_h=0.8,
                ),
                SceneClipSpec(
                    scene_id="s2", video_id="v1", source_type="gdrive",
                    start_ms=10000, end_ms=20000, timeline_start_ms=5000,
                ),
            ],
            subtitles=[
                SubtitleSpec(
                    text="안녕하세요",
                    start_ms=0,
                    end_ms=3000,
                    style=SubtitleStyleSpec(
                        font_family="Pretendard",
                        font_size_px=48,
                        font_color="#FF0000",
                        background_color="#000000",
                        stroke_color="#FFFFFF",
                        stroke_width=2,
                    ),
                ),
            ],
            transitions=[TransitionSpec(clip_index=0, type="crossfade", duration_ms=500)],
            title="Test Short",
            version=2,
        )

        data = original.model_dump()
        restored = CompositionSpec(**data)

        assert restored.output.width == 1080
        assert restored.output.height == 1920
        assert restored.clip_count == 2
        assert restored.subtitle_count == 1
        assert restored.scene_clips[0].volume == 0.8
        assert restored.scene_clips[0].has_crop is True
        assert restored.subtitles[0].text == "안녕하세요"
        assert restored.subtitles[0].style.has_background is True
        assert restored.total_duration_ms == 15000
        assert restored.title == "Test Short"
        assert restored.version == 2
        assert len(restored.transitions) == 1

    def test_json_roundtrip(self):
        original = CompositionSpec(
            scene_clips=[
                SceneClipSpec(scene_id="s1", video_id="v1", start_ms=0, end_ms=10000),
            ],
        )
        json_str = original.model_dump_json()
        restored = CompositionSpec.model_validate_json(json_str)
        assert restored.total_duration_ms == 10000

    def test_backward_compatible_minimal(self):
        """Existing API payloads without new fields should still parse."""
        raw = {
            "output": {"width": 406, "height": 720, "fps": 30, "format": "mp4", "background_color": "#000000"},
            "scene_clips": [
                {
                    "scene_id": "s001",
                    "video_id": "gd_vid1",
                    "source_type": "gdrive",
                    "start_ms": 0,
                    "end_ms": 10000,
                    "timeline_start_ms": 0,
                },
            ],
            "subtitles": [],
        }
        spec = CompositionSpec(**raw)
        assert spec.clip_count == 1
        assert spec.total_duration_ms == 10000
        assert spec.scene_clips[0].volume == 1.0
        assert spec.scene_clips[0].has_crop is False



class TestSubtitleStyleSpecFontFamilyLiteral:
    """font_family is a closed Literal — anything outside SUPPORTED_FONTS rejects."""

    def test_pretendard_accepted(self):
        SubtitleStyleSpec(font_family="Pretendard")

    def test_noto_sans_kr_accepted(self):
        SubtitleStyleSpec(font_family="Noto Sans KR")

    def test_unsupported_font_rejected(self):
        from pydantic import ValidationError
        with pytest.raises(ValidationError):
            SubtitleStyleSpec(font_family="Comic Sans")

    def test_empty_string_rejected(self):
        from pydantic import ValidationError
        with pytest.raises(ValidationError):
            SubtitleStyleSpec(font_family="")
