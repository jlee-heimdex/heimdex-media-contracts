"""Tests for V2 overlay specs + filter chain builder + back-compat.

These cover the schema-side of the overlay redesign (PR 1). The PIL bake path
lives in heimdex-media-pipelines (PR 1B) and has its own goldens.
"""

import pytest
from pydantic import TypeAdapter, ValidationError

from heimdex_media_contracts.composition import (
    BackgroundOverlaySpec,
    CompositionSpec,
    EffectsSpec,
    OverlaySpec,
    SceneClipSpec,
    ShadowSpec,
    StrokeSpec,
    SubtitleSpec,
    TextOverlaySpec,
    TransformSpec,
    build_overlay_filter_chain,
)


# ---------------------------------------------------------------------------
# TransformSpec
# ---------------------------------------------------------------------------

class TestTransformSpec:
    def test_defaults(self):
        t = TransformSpec()
        assert t.x == 0.5
        assert t.y == 0.5
        assert t.rotation_deg == 0.0
        assert t.width_px is None
        assert t.height_px is None

    def test_position_range(self):
        TransformSpec(x=0.0, y=1.0)
        with pytest.raises(ValidationError):
            TransformSpec(x=-0.1)
        with pytest.raises(ValidationError):
            TransformSpec(y=1.1)

    def test_rotation_range(self):
        TransformSpec(rotation_deg=-360.0)
        TransformSpec(rotation_deg=360.0)
        with pytest.raises(ValidationError):
            TransformSpec(rotation_deg=361.0)

    def test_explicit_dimensions(self):
        t = TransformSpec(width_px=200, height_px=100)
        assert t.width_px == 200
        assert t.height_px == 100

    def test_zero_width_rejected(self):
        with pytest.raises(ValidationError):
            TransformSpec(width_px=0)


# ---------------------------------------------------------------------------
# StrokeSpec / ShadowSpec / EffectsSpec
# ---------------------------------------------------------------------------

class TestStrokeSpec:
    def test_defaults(self):
        s = StrokeSpec()
        assert s.color == "#000000"
        assert s.width_px == 1

    def test_invalid_color(self):
        with pytest.raises(ValidationError, match="hex color"):
            StrokeSpec(color="black")

    def test_color_uppercased(self):
        assert StrokeSpec(color="#aabbcc").color == "#AABBCC"

    def test_width_range(self):
        StrokeSpec(width_px=0)
        StrokeSpec(width_px=50)
        with pytest.raises(ValidationError):
            StrokeSpec(width_px=51)


class TestShadowSpec:
    def test_defaults(self):
        s = ShadowSpec()
        assert s.color == "#000000"
        assert s.offset_x == 0
        assert s.offset_y == 4
        assert s.blur_px == 0
        assert s.spread_px == 0

    def test_blur_and_spread(self):
        s = ShadowSpec(blur_px=12, spread_px=4)
        assert s.blur_px == 12
        assert s.spread_px == 4

    def test_negative_offsets_allowed(self):
        ShadowSpec(offset_x=-100, offset_y=-100)
        with pytest.raises(ValidationError):
            ShadowSpec(offset_x=-101)


class TestEffectsSpec:
    def test_defaults(self):
        e = EffectsSpec()
        assert e.opacity == 1.0
        assert e.stroke is None
        assert e.shadow is None

    def test_opacity_range(self):
        EffectsSpec(opacity=0.0)
        EffectsSpec(opacity=1.0)
        with pytest.raises(ValidationError):
            EffectsSpec(opacity=1.1)

    def test_with_stroke_and_shadow(self):
        e = EffectsSpec(
            opacity=0.5,
            stroke=StrokeSpec(color="#ff0000", width_px=2),
            shadow=ShadowSpec(blur_px=8, spread_px=2),
        )
        assert e.stroke.width_px == 2
        assert e.shadow.blur_px == 8


# ---------------------------------------------------------------------------
# TextOverlaySpec
# ---------------------------------------------------------------------------

class TestTextOverlaySpec:
    def _minimal(self, **kw):
        defaults = dict(id="t1", start_ms=0, end_ms=3000)
        defaults.update(kw)
        return TextOverlaySpec(**defaults)

    def test_defaults(self):
        t = self._minimal()
        assert t.kind == "text"
        assert t.font_family == "Pretendard"
        assert t.font_size_px == 36
        assert t.font_weight == 400
        assert t.italic is False
        assert t.underline is False
        assert t.text_align == "center"
        assert t.line_height == 1.3
        assert t.letter_spacing == 0.0
        assert t.font_color == "#FFFFFF"
        assert t.layer_index == 0
        assert t.has_highlight is False

    def test_text_max_length(self):
        self._minimal(text="x" * 500)
        with pytest.raises(ValidationError):
            self._minimal(text="x" * 501)

    def test_korean_text(self):
        t = self._minimal(text="안녕하세요 라이브 특가")
        assert t.text == "안녕하세요 라이브 특가"

    def test_italic_underline(self):
        t = self._minimal(italic=True, underline=True)
        assert t.italic is True
        assert t.underline is True

    def test_font_family_literal(self):
        self._minimal(font_family="Pretendard")
        self._minimal(font_family="Noto Sans KR")
        with pytest.raises(ValidationError):
            self._minimal(font_family="Comic Sans")

    def test_font_color_validated(self):
        with pytest.raises(ValidationError, match="hex color"):
            self._minimal(font_color="white")

    def test_highlight(self):
        t = self._minimal(highlight_color="#000000")
        assert t.has_highlight is True

    def test_end_after_start(self):
        with pytest.raises(ValidationError, match="end_ms"):
            TextOverlaySpec(id="t1", start_ms=1000, end_ms=1000)

    def test_layer_index_negative_rejected(self):
        with pytest.raises(ValidationError):
            self._minimal(layer_index=-1)

    def test_duration_ms(self):
        t = self._minimal(start_ms=1000, end_ms=4000)
        assert t.duration_ms == 3000

    def test_full_styling(self):
        t = self._minimal(
            text="라이브 특가",
            font_family="Pretendard",
            font_size_px=48,
            font_weight=700,
            italic=True,
            underline=True,
            text_align="left",
            line_height=1.5,
            letter_spacing=2.0,
            font_color="#FF00FF",
            highlight_color="#000000",
            highlight_padding_px=12,
            highlight_opacity=0.7,
            layer_index=3,
            transform=TransformSpec(x=0.3, y=0.2, rotation_deg=15.0),
            effects=EffectsSpec(
                opacity=0.8,
                stroke=StrokeSpec(color="#FFFFFF", width_px=2),
                shadow=ShadowSpec(
                    color="#333333",
                    offset_x=2,
                    offset_y=4,
                    blur_px=8,
                    spread_px=2,
                ),
            ),
        )
        assert t.italic is True
        assert t.transform.rotation_deg == 15.0
        assert t.effects.shadow.blur_px == 8


# ---------------------------------------------------------------------------
# BackgroundOverlaySpec
# ---------------------------------------------------------------------------

class TestBackgroundOverlaySpec:
    def _minimal(self, **kw):
        defaults = dict(
            id="b1",
            start_ms=0,
            end_ms=3000,
            transform=TransformSpec(width_px=200, height_px=100),
        )
        defaults.update(kw)
        return BackgroundOverlaySpec(**defaults)

    def test_defaults(self):
        b = self._minimal()
        assert b.kind == "background"
        assert b.fill_color == "#000000"
        assert b.layer_index == 0
        assert b.transform.width_px == 200
        assert b.transform.height_px == 100

    def test_dimensions_required(self):
        with pytest.raises(ValidationError, match="width_px and"):
            BackgroundOverlaySpec(id="b1", start_ms=0, end_ms=3000)

    def test_only_width_rejected(self):
        with pytest.raises(ValidationError, match="width_px and"):
            BackgroundOverlaySpec(
                id="b1",
                start_ms=0,
                end_ms=3000,
                transform=TransformSpec(width_px=200),
            )

    def test_only_height_rejected(self):
        with pytest.raises(ValidationError, match="width_px and"):
            BackgroundOverlaySpec(
                id="b1",
                start_ms=0,
                end_ms=3000,
                transform=TransformSpec(height_px=100),
            )

    def test_fill_color_validated(self):
        with pytest.raises(ValidationError, match="hex color"):
            self._minimal(fill_color="red")

    def test_end_after_start(self):
        with pytest.raises(ValidationError, match="end_ms"):
            BackgroundOverlaySpec(
                id="b1",
                start_ms=1000,
                end_ms=1000,
                transform=TransformSpec(width_px=200, height_px=100),
            )


# ---------------------------------------------------------------------------
# OverlaySpec discriminated union
# ---------------------------------------------------------------------------

class TestOverlaySpecUnion:
    def test_discriminator_text(self):
        adapter = TypeAdapter(OverlaySpec)
        payload = {
            "kind": "text",
            "id": "t1",
            "start_ms": 0,
            "end_ms": 1000,
            "text": "Hello",
        }
        parsed = adapter.validate_python(payload)
        assert isinstance(parsed, TextOverlaySpec)

    def test_discriminator_background(self):
        adapter = TypeAdapter(OverlaySpec)
        payload = {
            "kind": "background",
            "id": "b1",
            "start_ms": 0,
            "end_ms": 1000,
            "transform": {"width_px": 200, "height_px": 100},
        }
        parsed = adapter.validate_python(payload)
        assert isinstance(parsed, BackgroundOverlaySpec)

    def test_unknown_kind_rejected(self):
        adapter = TypeAdapter(OverlaySpec)
        with pytest.raises(ValidationError):
            adapter.validate_python(
                {"kind": "image", "id": "i1", "start_ms": 0, "end_ms": 1000}
            )

    def test_text_payload_against_bg_discriminator_rejected(self):
        # A text-shaped payload with kind=background should fail (missing W/H).
        adapter = TypeAdapter(OverlaySpec)
        with pytest.raises(ValidationError):
            adapter.validate_python(
                {"kind": "background", "id": "x", "start_ms": 0, "end_ms": 1000}
            )

    def test_json_roundtrip_text(self):
        adapter = TypeAdapter(OverlaySpec)
        original: TextOverlaySpec = TextOverlaySpec(
            id="t1",
            start_ms=0,
            end_ms=2000,
            text="라이브 특가",
            italic=True,
            underline=True,
            effects=EffectsSpec(
                opacity=0.5,
                stroke=StrokeSpec(color="#ff0000", width_px=2),
                shadow=ShadowSpec(blur_px=12, spread_px=4),
            ),
        )
        restored = adapter.validate_json(original.model_dump_json())
        assert isinstance(restored, TextOverlaySpec)
        assert restored.text == "라이브 특가"
        assert restored.italic is True
        assert restored.effects.shadow.blur_px == 12
        assert restored.effects.opacity == 0.5

    def test_json_roundtrip_background(self):
        adapter = TypeAdapter(OverlaySpec)
        original = BackgroundOverlaySpec(
            id="b1",
            start_ms=0,
            end_ms=3000,
            fill_color="#1A1A1A",
            transform=TransformSpec(
                x=0.3, y=0.4, rotation_deg=45.0, width_px=300, height_px=150
            ),
        )
        restored = adapter.validate_json(original.model_dump_json())
        assert isinstance(restored, BackgroundOverlaySpec)
        assert restored.fill_color == "#1A1A1A"
        assert restored.transform.rotation_deg == 45.0


# ---------------------------------------------------------------------------
# CompositionSpec integration with overlays
# ---------------------------------------------------------------------------

class TestCompositionSpecOverlays:
    def _clip(self, **kw):
        defaults = dict(scene_id="s1", video_id="v1", start_ms=0, end_ms=10000)
        defaults.update(kw)
        return SceneClipSpec(**defaults)

    def test_overlays_default_empty(self):
        spec = CompositionSpec(scene_clips=[self._clip()])
        assert spec.overlays == []
        assert spec.overlay_count == 0

    def test_overlays_within_timeline_ok(self):
        spec = CompositionSpec(
            scene_clips=[self._clip(end_ms=10000)],
            overlays=[
                TextOverlaySpec(id="t1", start_ms=0, end_ms=5000, text="Hi"),
                BackgroundOverlaySpec(
                    id="b1",
                    start_ms=2000,
                    end_ms=8000,
                    transform=TransformSpec(width_px=200, height_px=100),
                ),
            ],
        )
        assert spec.overlay_count == 2

    def test_overlay_beyond_timeline_rejected(self):
        with pytest.raises(ValidationError, match="Overlay 0 \\(text\\) starts"):
            CompositionSpec(
                scene_clips=[self._clip(end_ms=5000)],
                overlays=[
                    TextOverlaySpec(id="t1", start_ms=6000, end_ms=8000, text="Late")
                ],
            )

    def test_total_duration_includes_overlays(self):
        spec = CompositionSpec(
            scene_clips=[self._clip(end_ms=10000)],
            overlays=[
                TextOverlaySpec(id="t1", start_ms=0, end_ms=12000, text="Long")
            ],
        )
        assert spec.total_duration_ms == 12000

    def test_full_roundtrip_with_overlays(self):
        original = CompositionSpec(
            scene_clips=[self._clip(end_ms=15000)],
            overlays=[
                TextOverlaySpec(
                    id="t1",
                    start_ms=0,
                    end_ms=3000,
                    text="안녕",
                    italic=True,
                    layer_index=0,
                ),
                BackgroundOverlaySpec(
                    id="b1",
                    start_ms=1000,
                    end_ms=5000,
                    fill_color="#FFFFFF",
                    layer_index=1,
                    transform=TransformSpec(width_px=400, height_px=80),
                ),
            ],
        )
        restored = CompositionSpec(**original.model_dump())
        assert restored.overlay_count == 2
        assert isinstance(restored.overlays[0], TextOverlaySpec)
        assert isinstance(restored.overlays[1], BackgroundOverlaySpec)
        assert restored.overlays[0].italic is True
        assert restored.overlays[1].fill_color == "#FFFFFF"


# ---------------------------------------------------------------------------
# Back-compat: 0.11.0 payloads (no `overlays` field) must still parse
# ---------------------------------------------------------------------------

class TestBackCompat0_11_0:
    """Payloads written by API/frontend pinned to contracts 0.11.0 must still
    parse against 0.12.0+. Only mechanism: every new field has a default.
    """

    def test_minimal_0_11_payload(self):
        raw = {
            "output": {
                "width": 406,
                "height": 720,
                "fps": 30,
                "format": "mp4",
                "background_color": "#000000",
            },
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
        assert spec.overlays == []
        assert spec.overlay_count == 0
        assert spec.total_duration_ms == 10000

    def test_payload_with_subtitles_no_overlays(self):
        raw = {
            "scene_clips": [
                {
                    "scene_id": "s001",
                    "video_id": "v1",
                    "start_ms": 0,
                    "end_ms": 8000,
                    "timeline_start_ms": 0,
                }
            ],
            "subtitles": [
                {
                    "text": "Legacy subtitle",
                    "start_ms": 0,
                    "end_ms": 3000,
                    "style": {
                        "font_family": "Pretendard",
                        "font_size_px": 36,
                        "font_color": "#FFFFFF",
                        "font_weight": 700,
                    },
                }
            ],
        }
        spec = CompositionSpec(**raw)
        assert len(spec.subtitles) == 1
        assert spec.overlays == []


# ---------------------------------------------------------------------------
# build_overlay_filter_chain — pure ffmpeg-string builder
# ---------------------------------------------------------------------------

class TestBuildOverlayFilterChain:
    def _text(self, **kw):
        defaults = dict(id="t1", start_ms=0, end_ms=3000)
        defaults.update(kw)
        return TextOverlaySpec(**defaults)

    def _bg(self, **kw):
        defaults = dict(
            id="b1",
            start_ms=0,
            end_ms=3000,
            transform=TransformSpec(width_px=200, height_px=100),
        )
        defaults.update(kw)
        return BackgroundOverlaySpec(**defaults)

    def test_empty_overlays_returns_empty(self):
        result = build_overlay_filter_chain(
            overlays=[],
            overlay_input_indices=[],
            label_in="canvas2",
        )
        assert result == []

    def test_single_overlay_emits_final_label(self):
        ov = self._text(start_ms=0, end_ms=2000)
        ov.transform.x = 0.5
        ov.transform.y = 0.85
        result = build_overlay_filter_chain(
            overlays=[ov],
            overlay_input_indices=[2],
            label_in="canvas2",
            final_label="vout",
        )
        assert len(result) == 1
        assert result[0].startswith("[canvas2][2:v]overlay=")
        assert "x=W*0.5000-w/2" in result[0]
        assert "y=H*0.8500-h/2" in result[0]
        assert "enable='between(t,0.000,2.000)'" in result[0]
        assert result[0].endswith("[vout]")

    def test_multi_overlay_chains_intermediate_labels(self):
        a = self._text(id="a", start_ms=0, end_ms=1000)
        b = self._bg(id="b", start_ms=500, end_ms=2500)
        c = self._text(id="c", start_ms=1000, end_ms=3000)
        result = build_overlay_filter_chain(
            overlays=[a, b, c],
            overlay_input_indices=[2, 3, 4],
            label_in="final",
            final_label="vout",
        )
        assert len(result) == 3
        # First feeds from label_in → ovl0
        assert result[0].startswith("[final][2:v]overlay=")
        assert result[0].endswith("[ovl0]")
        # Middle chains
        assert result[1].startswith("[ovl0][3:v]overlay=")
        assert result[1].endswith("[ovl1]")
        # Last writes to final_label
        assert result[2].startswith("[ovl1][4:v]overlay=")
        assert result[2].endswith("[vout]")

    def test_mismatched_lengths_raises(self):
        with pytest.raises(ValueError, match="must be the same length"):
            build_overlay_filter_chain(
                overlays=[self._text()],
                overlay_input_indices=[2, 3],
                label_in="canvas2",
            )

    def test_caller_controls_layer_order(self):
        # Function does NOT re-sort by layer_index — caller is responsible.
        front = self._text(id="front", layer_index=10, start_ms=0, end_ms=1000)
        back = self._text(id="back", layer_index=0, start_ms=0, end_ms=1000)
        result = build_overlay_filter_chain(
            overlays=[back, front],  # caller sorted back→front
            overlay_input_indices=[2, 3],
            label_in="canvas2",
        )
        assert "[2:v]" in result[0]  # back first
        assert "[3:v]" in result[1]  # front last (on top)

    def test_position_precision(self):
        ov = self._text()
        ov.transform.x = 0.123456
        ov.transform.y = 0.789012
        result = build_overlay_filter_chain(
            overlays=[ov],
            overlay_input_indices=[2],
            label_in="canvas2",
        )
        # 4-decimal precision
        assert "x=W*0.1235-w/2" in result[0]
        assert "y=H*0.7890-h/2" in result[0]
