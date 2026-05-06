"""Tests for ffmpeg filter graph generation."""

import pytest

from heimdex_media_contracts.composition import (
    CompositionSpec,
    OutputSpec,
    SceneClipSpec,
    SubtitleSpec,
    SubtitleStyleSpec,
    build_filter_graph,
)
from heimdex_media_contracts.composition.filters import (
    FontNotFoundError,
    _escape_ffmpeg_text,
    _ms_to_s,
    _position_to_ffmpeg_x,
    _resolve_font_path,
)


# ---------------------------------------------------------------------------
# Helper function tests
# ---------------------------------------------------------------------------

class TestMsToS:
    def test_zero(self):
        assert _ms_to_s(0) == "0.000"

    def test_whole_seconds(self):
        assert _ms_to_s(5000) == "5.000"

    def test_fractional(self):
        assert _ms_to_s(1500) == "1.500"

    def test_large(self):
        assert _ms_to_s(300000) == "300.000"


class TestEscapeFfmpegText:
    def test_plain_text(self):
        assert _escape_ffmpeg_text("Hello") == "Hello"

    def test_colon(self):
        result = _escape_ffmpeg_text("key:value")
        assert "\\\\:" in result

    def test_percent(self):
        assert _escape_ffmpeg_text("100%") == "100%%"

    def test_newline(self):
        # Output must contain TWO backslashes before the ``n`` so the
        # lavfi filter-graph parser unescapes one and drawtext receives
        # the literal ``\n`` it needs to render a line break. Prior to
        # the 2026-05-06 fix this asserted a single backslash, which
        # caused ``\n`` to be unescaped away and drawtext to render the
        # literal letter "n" instead of breaking the line — first hit
        # in production by the auto-shorts Korean line-wrap.
        assert _escape_ffmpeg_text("line1\nline2") == "line1\\\\nline2"

    def test_korean(self):
        assert _escape_ffmpeg_text("안녕하세요") == "안녕하세요"


class TestResolveFontPath:
    """Resolver returns an existing file path or raises FontNotFoundError.

    Tests use ``tmp_path`` and create empty fixture files (the resolver
    only checks existence, not validity).
    """

    @staticmethod
    def _make_font(tmp_path, base, ext=".ttf"):
        (tmp_path / f"{base}{ext}").write_bytes(b"")

    def test_pretendard_bold_ttf(self, tmp_path):
        self._make_font(tmp_path, "Pretendard-Bold")
        assert _resolve_font_path("Pretendard", 700, str(tmp_path)).endswith(
            "Pretendard-Bold.ttf"
        )

    def test_pretendard_regular_ttf(self, tmp_path):
        self._make_font(tmp_path, "Pretendard-Regular")
        assert _resolve_font_path("Pretendard", 400, str(tmp_path)).endswith(
            "Pretendard-Regular.ttf"
        )

    def test_noto_sans_kr_bold(self, tmp_path):
        self._make_font(tmp_path, "NotoSansKR-Bold")
        assert _resolve_font_path("Noto Sans KR", 700, str(tmp_path)).endswith(
            "NotoSansKR-Bold.ttf"
        )

    def test_otf_used_when_only_otf_exists(self, tmp_path):
        self._make_font(tmp_path, "Pretendard-Regular", ext=".otf")
        assert _resolve_font_path("Pretendard", 400, str(tmp_path)).endswith(".otf")

    def test_ttf_preferred_over_otf(self, tmp_path):
        self._make_font(tmp_path, "Pretendard-Regular", ext=".ttf")
        self._make_font(tmp_path, "Pretendard-Regular", ext=".otf")
        assert _resolve_font_path("Pretendard", 400, str(tmp_path)).endswith(".ttf")

    def test_raises_when_no_extension_matches(self, tmp_path):
        with pytest.raises(FontNotFoundError):
            _resolve_font_path("Pretendard", 400, str(tmp_path))

    def test_raises_for_unsupported_family(self, tmp_path):
        self._make_font(tmp_path, "Pretendard-Regular")
        with pytest.raises(FontNotFoundError):
            _resolve_font_path("Comic Sans", 400, str(tmp_path))

    def test_font_dir_trailing_slash(self, tmp_path):
        self._make_font(tmp_path, "Pretendard-Bold")
        assert _resolve_font_path("Pretendard", 700, str(tmp_path) + "/").endswith(
            "Pretendard-Bold.ttf"
        )

    def test_weight_boundary(self, tmp_path):
        self._make_font(tmp_path, "Pretendard-Bold")
        self._make_font(tmp_path, "Pretendard-Regular")
        assert "Bold" in _resolve_font_path("Pretendard", 600, str(tmp_path))
        assert "Regular" in _resolve_font_path("Pretendard", 599, str(tmp_path))

class TestPositionToFfmpegX:
    def test_center(self):
        expr = _position_to_ffmpeg_x(0.5, "center")
        assert expr == "w*0.5-tw/2"

    def test_left(self):
        expr = _position_to_ffmpeg_x(0.1, "left")
        assert expr == "w*0.1"

    def test_right(self):
        expr = _position_to_ffmpeg_x(0.9, "right")
        assert expr == "w*0.9-tw"


# ---------------------------------------------------------------------------
# build_filter_graph tests
# ---------------------------------------------------------------------------

def _clip(scene_id="s1", video_id="v1", start_ms=0, end_ms=10000, timeline_start_ms=0, **kw):
    return SceneClipSpec(
        scene_id=scene_id, video_id=video_id,
        start_ms=start_ms, end_ms=end_ms,
        timeline_start_ms=timeline_start_ms, **kw,
    )


class TestBuildFilterGraph:
    def test_single_clip_no_subtitles(self, fake_font_dir):
        fg = build_filter_graph(
            clips=[_clip()],
            subtitles=[],
            output=OutputSpec(),
            font_dir=fake_font_dir,
        )
        # Should have: scale, audio, canvas, overlay, concat
        assert "[s0]" in fg
        assert "[a0]" in fg
        assert "[canvas0]" in fg
        assert "[canvas1]" in fg
        assert "[aout]" in fg
        # No subtitle labels
        assert "[final]" not in fg
        assert "drawtext" not in fg

    def test_two_clips_no_subtitles(self, fake_font_dir):
        fg = build_filter_graph(
            clips=[
                _clip(scene_id="s1", timeline_start_ms=0),
                _clip(scene_id="s2", timeline_start_ms=10000),
            ],
            subtitles=[],
            output=OutputSpec(),
            font_dir=fake_font_dir,
        )
        assert "[s0]" in fg
        assert "[s1]" in fg
        assert "[a0]" in fg
        assert "[a1]" in fg
        assert "[canvas2]" in fg
        assert "concat=n=2:v=0:a=1" in fg

    def test_single_clip_with_subtitle(self, fake_font_dir):
        fg = build_filter_graph(
            clips=[_clip()],
            subtitles=[SubtitleSpec(text="Hello", start_ms=0, end_ms=5000)],
            output=OutputSpec(),
            font_dir=fake_font_dir,
        )
        assert "drawtext" in fg
        assert "[final]" in fg
        assert "Pretendard" in fg

    def test_multiple_subtitles(self, fake_font_dir):
        fg = build_filter_graph(
            clips=[_clip()],
            subtitles=[
                SubtitleSpec(text="First", start_ms=0, end_ms=5000),
                SubtitleSpec(text="Second", start_ms=5000, end_ms=10000),
            ],
            output=OutputSpec(),
            font_dir=fake_font_dir,
        )
        assert "[sub0]" in fg
        assert "[final]" in fg
        assert fg.count("drawtext") == 2

    def test_overlay_enable_timing(self, fake_font_dir):
        fg = build_filter_graph(
            clips=[
                _clip(scene_id="s1", start_ms=0, end_ms=5000, timeline_start_ms=0),
                _clip(scene_id="s2", start_ms=0, end_ms=5000, timeline_start_ms=5000),
            ],
            subtitles=[],
            output=OutputSpec(),
            font_dir=fake_font_dir,
        )
        assert "between(t,0.000,5.000)" in fg
        assert "between(t,5.000,10.000)" in fg

    def test_subtitle_enable_timing(self, fake_font_dir):
        fg = build_filter_graph(
            clips=[_clip()],
            subtitles=[SubtitleSpec(text="Hello", start_ms=1000, end_ms=3000)],
            output=OutputSpec(),
            font_dir=fake_font_dir,
        )
        assert "between(t,1.000,3.000)" in fg

    def test_custom_output_dimensions(self, fake_font_dir):
        fg = build_filter_graph(
            clips=[_clip()],
            subtitles=[],
            output=OutputSpec(width=1080, height=1920),
            font_dir=fake_font_dir,
        )
        assert "scale=1080:1920" in fg
        assert "pad=1080:1920" in fg
        assert "s=1080x1920" in fg

    def test_volume_adjustment(self, fake_font_dir):
        fg = build_filter_graph(
            clips=[_clip(volume=0.5)],
            subtitles=[],
            output=OutputSpec(),
            font_dir=fake_font_dir,
        )
        assert "volume=0.5" in fg

    def test_crop_in_filter(self, fake_font_dir):
        fg = build_filter_graph(
            clips=[_clip(crop_x=0.1, crop_y=0.1, crop_w=0.8, crop_h=0.8)],
            subtitles=[],
            output=OutputSpec(),
            font_dir=fake_font_dir,
        )
        assert "crop=" in fg
        assert "iw*0.8" in fg
        assert "ih*0.8" in fg

    def test_no_crop_when_defaults(self, fake_font_dir):
        fg = build_filter_graph(
            clips=[_clip()],
            subtitles=[],
            output=OutputSpec(),
            font_dir=fake_font_dir,
        )
        assert "crop=" not in fg

    def test_background_box(self, fake_font_dir):
        fg = build_filter_graph(
            clips=[_clip()],
            subtitles=[SubtitleSpec(
                text="Hello",
                start_ms=0,
                end_ms=5000,
                style=SubtitleStyleSpec(background_color="#000000"),
            )],
            output=OutputSpec(),
            font_dir=fake_font_dir,
        )
        assert "box=1" in fg
        assert "boxcolor=#000000" in fg

    def test_stroke_in_filter(self, fake_font_dir):
        fg = build_filter_graph(
            clips=[_clip()],
            subtitles=[SubtitleSpec(
                text="Hello",
                start_ms=0,
                end_ms=5000,
                style=SubtitleStyleSpec(stroke_color="#000000", stroke_width=3),
            )],
            output=OutputSpec(),
            font_dir=fake_font_dir,
        )
        assert "borderw=3" in fg
        assert "bordercolor=#000000" in fg

    def test_shadow_in_filter(self, fake_font_dir):
        fg = build_filter_graph(
            clips=[_clip()],
            subtitles=[SubtitleSpec(
                text="Hello",
                start_ms=0,
                end_ms=5000,
                style=SubtitleStyleSpec(shadow_color="#333333"),
            )],
            output=OutputSpec(),
            font_dir=fake_font_dir,
        )
        assert "shadowcolor=#333333" in fg

    def test_output_labels_without_subtitles(self, fake_font_dir):
        """Without subtitles, last video label is canvas{N}."""
        fg = build_filter_graph(
            clips=[_clip()],
            subtitles=[],
            output=OutputSpec(),
            font_dir=fake_font_dir,
        )
        assert "[canvas1]" in fg
        assert "[final]" not in fg

    def test_output_labels_with_subtitles(self, fake_font_dir):
        """With subtitles, last label is [final]."""
        fg = build_filter_graph(
            clips=[_clip()],
            subtitles=[SubtitleSpec(text="Hello", start_ms=0, end_ms=5000)],
            output=OutputSpec(),
            font_dir=fake_font_dir,
        )
        assert "[final]" in fg

    def test_korean_subtitle_text(self, fake_font_dir):
        fg = build_filter_graph(
            clips=[_clip()],
            subtitles=[SubtitleSpec(text="프리텐다드 테스트", start_ms=0, end_ms=5000)],
            output=OutputSpec(),
            font_dir=fake_font_dir,
        )
        assert "프리텐다드 테스트" in fg

    def test_noto_sans_kr_font(self, fake_font_dir):
        fg = build_filter_graph(
            clips=[_clip()],
            subtitles=[SubtitleSpec(
                text="Hello",
                start_ms=0,
                end_ms=5000,
                style=SubtitleStyleSpec(font_family="Noto Sans KR"),
            )],
            output=OutputSpec(),
            font_dir=fake_font_dir,
        )
        assert "NotoSansKR-Bold.ttf" in fg
