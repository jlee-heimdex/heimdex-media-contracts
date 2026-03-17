"""Tests for composition filter graph building functions."""

import pytest

from heimdex_media_contracts.composition.filters import (
    build_filter_graph,
    calc_text_position,
    escape_drawtext,
    resolve_font_path,
)
from heimdex_media_contracts.composition.schemas import (
    OutputSpec,
    SceneClipSpec,
    SubtitleSpec,
    SubtitleStyleSpec,
)


def _make_clip(**overrides) -> SceneClipSpec:
    defaults = {
        "scene_id": "s1",
        "video_id": "v1",
        "start_ms": 0,
        "end_ms": 10000,
        "timeline_start_ms": 0,
    }
    defaults.update(overrides)
    return SceneClipSpec(**defaults)


def _make_subtitle(text: str = "Hello", start_ms: int = 0, end_ms: int = 5000, **style_overrides) -> SubtitleSpec:
    style = SubtitleStyleSpec(**style_overrides) if style_overrides else SubtitleStyleSpec()
    return SubtitleSpec(text=text, start_ms=start_ms, end_ms=end_ms, style=style)


class TestBuildFilterGraph:
    def test_single_clip_no_subs(self):
        graph = build_filter_graph([_make_clip()], [], OutputSpec(), "/fonts")
        assert "color" in graph
        assert "overlay" in graph
        assert "concat" not in graph

    def test_two_clips_no_subs(self):
        clip1 = _make_clip(scene_id="s1", timeline_start_ms=0)
        clip2 = _make_clip(scene_id="s2", start_ms=0, end_ms=10000, timeline_start_ms=10000)
        graph = build_filter_graph([clip1, clip2], [], OutputSpec(), "/fonts")
        assert graph.count("overlay") == 2

    def test_custom_background_color(self):
        out = OutputSpec(background_color="#FF0000")
        graph = build_filter_graph([_make_clip()], [], out, "/fonts")
        assert "color=c=#FF0000" in graph

    def test_default_background_color(self):
        graph = build_filter_graph([_make_clip()], [], OutputSpec(), "/fonts")
        assert "color=c=#000000" in graph

    def test_clip_timeline_position(self):
        clip = _make_clip(start_ms=10000, end_ms=30000, timeline_start_ms=10000)
        graph = build_filter_graph([clip], [], OutputSpec(), "/fonts")
        assert "enable='between(t,10.0,30.0)'" in graph

    def test_canvas_size(self):
        graph = build_filter_graph([_make_clip()], [], OutputSpec(), "/fonts")
        assert "s=405x720" in graph

    def test_multi_subtitle(self):
        sub1 = _make_subtitle("Text1", 0, 5000)
        sub2 = _make_subtitle("Text2", 45000, 50000)
        graph = build_filter_graph([_make_clip()], [sub1, sub2], OutputSpec(), "/fonts")
        assert graph.count("drawtext") == 2


class TestEscapeDrawtext:
    def test_colon_escaped(self):
        assert "\\:" in escape_drawtext("가격: 29,900원")

    def test_quotes_escaped(self):
        result = escape_drawtext("it's a 'test'")
        assert "\\'" in result

    def test_percent_escaped(self):
        assert "%%" in escape_drawtext("100%")

    def test_backslash_escaped(self):
        result = escape_drawtext("a\\b")
        assert "\\\\" in result

    def test_empty_string(self):
        assert escape_drawtext("") == ""

    def test_korean_passthrough(self):
        assert escape_drawtext("한글만") == "한글만"


class TestCalcTextPosition:
    def test_center_align(self):
        x, y = calc_text_position(0.5, 0.85, "center")
        assert x == "(w-text_w)/2"
        assert y == "h*0.85"

    def test_left_align(self):
        x, y = calc_text_position(0.1, 0.15, "left")
        assert x == "w*0.1"
        assert y == "h*0.15"

    def test_right_align(self):
        x, y = calc_text_position(0.9, 0.5, "right")
        assert x == "w*0.9-text_w"
        assert y == "h*0.5"


class TestResolveFontPath:
    def test_bold_weight(self):
        assert resolve_font_path("Noto Sans KR", 700, "/fonts") == "/fonts/NotoSansKR-Bold.ttf"

    def test_regular_weight(self):
        assert resolve_font_path("Noto Sans KR", 400, "/fonts") == "/fonts/NotoSansKR-Regular.ttf"

    def test_threshold_600_is_bold(self):
        assert resolve_font_path("Pretendard", 600, "/fonts") == "/fonts/Pretendard-Bold.ttf"


class TestDrawtextOptions:
    def test_shadow_enabled(self):
        sub = _make_subtitle("Hi", 0, 5000, shadow_enabled=True)
        graph = build_filter_graph([_make_clip()], [sub], OutputSpec(), "/fonts")
        assert "shadowcolor" in graph
        assert "shadowx" in graph
        assert "shadowy" in graph

    def test_shadow_disabled(self):
        sub = _make_subtitle("Hi", 0, 5000, shadow_enabled=False)
        graph = build_filter_graph([_make_clip()], [sub], OutputSpec(), "/fonts")
        assert "shadowcolor" not in graph

    def test_background_enabled(self):
        sub = _make_subtitle(
            "Hi", 0, 5000,
            background_enabled=True,
            background_color="#000000",
        )
        graph = build_filter_graph([_make_clip()], [sub], OutputSpec(), "/fonts")
        assert "box=1" in graph
        assert "boxcolor" in graph

    def test_line_height_mapping(self):
        sub = _make_subtitle("Hi", 0, 5000, line_height=1.4, font_size_px=48)
        graph = build_filter_graph([_make_clip()], [sub], OutputSpec(), "/fonts")
        # line_spacing = 48 * (1.4 - 1.0) = 19.2 -> int = 19
        assert "line_spacing=19" in graph

    def test_letter_spacing_ignored(self):
        sub = _make_subtitle("Hi", 0, 5000, letter_spacing=5.0)
        graph = build_filter_graph([_make_clip()], [sub], OutputSpec(), "/fonts")
        assert "letter_spacing" not in graph

    def test_shadow_blur_ignored(self):
        sub = _make_subtitle("Hi", 0, 5000, shadow_blur=8)
        graph = build_filter_graph([_make_clip()], [sub], OutputSpec(), "/fonts")
        assert "shadow_blur" not in graph
        # Only shadowx/shadowy should be present
        assert "shadowx" in graph
