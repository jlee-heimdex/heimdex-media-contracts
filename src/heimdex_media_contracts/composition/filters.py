"""Pure-function ffmpeg filter graph builder for composition rendering.

Takes a CompositionSpec and produces a filtergraph string that ffmpeg
can consume via `-filter_complex`. No I/O, no subprocess calls.

Filter graph structure:
  1. Scale each input to output dimensions (with optional crop)
  2. Create a black canvas at output dimensions
  3. Overlay each clip onto the canvas in sequence
  4. Concatenate audio streams
  5. Optionally draw subtitle text on top

Label conventions:
  [s0], [s1], ...       — scaled video inputs
  [a0], [a1], ...       — volume-adjusted audio inputs
  [canvas0]             — initial black canvas
  [canvas1], [canvas2]  — after overlaying each clip
  [sub0], [sub1], ...   — after each subtitle drawtext
  [final]               — after all subtitles (if any)
  [aout]                — concatenated audio output
"""

from __future__ import annotations

import os

from heimdex_media_contracts.composition.overlays import OverlaySpec
from heimdex_media_contracts.composition.schemas import (
    CompositionSpec,
    OutputSpec,
    SceneClipSpec,
    SubtitleSpec,
    SubtitleStyleSpec,
)


def build_filter_graph(
    *,
    clips: list[SceneClipSpec],
    subtitles: list[SubtitleSpec],
    output: OutputSpec,
    font_dir: str,
) -> str:
    """Build a complete ffmpeg filter_complex string.

    Args:
        clips: Ordered scene clips (each maps to an ffmpeg input by index).
        subtitles: Text overlays with timing and styling.
        output: Output dimensions and background color.
        font_dir: Absolute path to font directory on the render machine.

    Returns:
        A single filtergraph string for `-filter_complex`.
    """
    parts: list[str] = []

    # 1. Scale + crop each input to output dimensions
    for i, clip in enumerate(clips):
        parts.append(_build_scale_filter(i, clip, output))
        parts.append(_build_audio_filter(i, clip))

    # 2. Create black canvas
    parts.append(
        f"color=c={output.background_color.replace('#', '0x')}"
        f":s={output.width}x{output.height}"
        f":d={_ms_to_s(clips[-1].timeline_start_ms + clips[-1].duration_ms)}"
        f":r={output.fps}"
        f"[canvas0]"
    )

    # 3. Overlay each clip onto canvas at its timeline position
    for i in range(len(clips)):
        canvas_in = f"canvas{i}"
        canvas_out = f"canvas{i + 1}"
        enable_start = _ms_to_s(clips[i].timeline_start_ms)
        enable_end = _ms_to_s(clips[i].timeline_start_ms + clips[i].duration_ms)
        parts.append(
            f"[{canvas_in}][s{i}]overlay=0:0"
            f":enable='between(t,{enable_start},{enable_end})'"
            f"[{canvas_out}]"
        )

    # 4. Concatenate audio
    n = len(clips)
    audio_inputs = "".join(f"[a{i}]" for i in range(n))
    parts.append(f"{audio_inputs}concat=n={n}:v=0:a=1[aout]")

    # 5. Subtitle drawtext filters
    if subtitles:
        last_video_label = f"canvas{n}"
        for j, sub in enumerate(subtitles):
            label_in = last_video_label
            label_out = f"sub{j}" if j < len(subtitles) - 1 else "final"
            parts.append(
                _build_drawtext_filter(
                    label_in=label_in,
                    label_out=label_out,
                    subtitle=sub,
                    output=output,
                    font_dir=font_dir,
                )
            )
            last_video_label = label_out

    return ";\n".join(parts)


# ---------------------------------------------------------------------------
# Individual filter builders
# ---------------------------------------------------------------------------

def _build_scale_filter(index: int, clip: SceneClipSpec, output: OutputSpec) -> str:
    """Scale (and optionally crop) input to output dimensions.

    Also offsets PTS so the extracted clip's timestamps align with its
    position on the composition canvas. Without this, the overlay
    ``enable='between(t,...)'`` cannot find matching frames in clips
    whose timeline_start_ms > 0 (they start at t=0 after extraction).
    """
    pts_offset = _ms_to_s(clip.timeline_start_ms)
    if clip.has_crop:
        # Crop first (in source pixel space), then scale to output
        return (
            f"[{index}:v]crop="
            f"iw*{clip.crop_w}:ih*{clip.crop_h}"
            f":iw*{clip.crop_x}:ih*{clip.crop_y},"
            f"scale={output.width}:{output.height}:force_original_aspect_ratio=decrease,"
            f"pad={output.width}:{output.height}:(ow-iw)/2:(oh-ih)/2"
            f":color={output.background_color.replace('#', '0x')},"
            f"setpts=PTS+{pts_offset}/TB"
            f"[s{index}]"
        )
    return (
        f"[{index}:v]scale={output.width}:{output.height}"
        f":force_original_aspect_ratio=decrease,"
        f"pad={output.width}:{output.height}:(ow-iw)/2:(oh-ih)/2"
        f":color={output.background_color.replace('#', '0x')},"
        f"setpts=PTS+{pts_offset}/TB"
        f"[s{index}]"
    )


def _build_audio_filter(index: int, clip: SceneClipSpec) -> str:
    """Volume adjustment for a clip's audio."""
    return f"[{index}:a]volume={clip.volume}[a{index}]"


def _build_drawtext_filter(
    *,
    label_in: str,
    label_out: str,
    subtitle: SubtitleSpec,
    output: OutputSpec,
    font_dir: str,
) -> str:
    """Build a drawtext filter for a single subtitle."""
    style = subtitle.style
    escaped_text = _escape_ffmpeg_text(subtitle.text)

    # Resolve font file path
    font_file = _resolve_font_path(style.font_family, style.font_weight, font_dir)

    # Position: convert normalized coordinates to pixel expressions
    x_expr = _position_to_ffmpeg_x(style.position_x, style.text_align)
    y_expr = f"h*{style.position_y}-th/2"

    # Enable window
    enable_start = _ms_to_s(subtitle.start_ms)
    enable_end = _ms_to_s(subtitle.end_ms)

    # Line spacing from line_height
    line_spacing = int(style.font_size_px * (style.line_height - 1.0))

    parts = [
        f"fontfile='{font_file}'",
        f"text='{escaped_text}'",
        f"fontsize={style.font_size_px}",
        f"fontcolor={style.font_color}",
        f"x={x_expr}",
        f"y={y_expr}",
        f"line_spacing={line_spacing}",
        f"enable='between(t,{enable_start},{enable_end})'",
    ]

    # Background box
    if style.has_background:
        parts.append(f"box=1")
        parts.append(f"boxcolor={style.background_color}@{style.background_opacity}")
        parts.append(f"boxborderw={style.background_padding}")

    # Border/stroke
    if style.has_stroke:
        parts.append(f"borderw={style.stroke_width}")
        parts.append(f"bordercolor={style.stroke_color}")

    # Shadow
    if style.has_shadow:
        parts.append(f"shadowcolor={style.shadow_color}")
        parts.append(f"shadowx={style.shadow_offset_x}")
        parts.append(f"shadowy={style.shadow_offset_y}")

    drawtext_args = ":".join(parts)
    return f"[{label_in}]drawtext={drawtext_args}[{label_out}]"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _ms_to_s(ms: int) -> str:
    """Convert milliseconds to seconds string with 3 decimal places."""
    return f"{ms / 1000:.3f}"


def _escape_ffmpeg_text(text: str) -> str:
    """Escape special characters for ffmpeg drawtext filter.

    FFmpeg drawtext requires escaping: ' \\ : %

    Newlines need FOUR backslashes in the filter expression to
    survive lavfi's two-pass unescape and reach drawtext as the
    two-character ``\\n`` it interprets as a newline:

      filter expr     →  pass 1 unescape  →  pass 2 unescape  →  drawtext sees
      ──────────      ──────────────       ──────────────       ─────────────
      ``\\n`` (1)     →  ``n``            →  ``n``            →  literal "n"
      ``\\\\n`` (2)   →  ``\\n`` (1)      →  ``n``            →  literal "n"
      ``\\\\\\\\n``(4)→  ``\\\\n`` (2)    →  ``\\n`` (1)      →  newline ✓

    Same reasoning is why the literal ``\\`` replacement above goes
    through quadruple-doubling (1 → 4) — both passes have to chew
    through equally before drawtext gets the un-escaped char.

    First exposed by the auto-shorts Korean line-wrap on staging
    2026-05-06: pre-fix used a single backslash and rendered the
    literal letter "n"; the 2-backslash intermediate fix was
    pixel-identical to the 1-backslash output, confirming both
    escape passes consume backslashes pairwise. Verified
    empirically by rendering 1/2/4-backslash variants through the
    actual ffmpeg+drawtext stack on staging and pixel-comparing
    the output.
    """
    text = text.replace("\\", "\\\\\\\\")
    text = text.replace("'", "'\\\\\\''")
    text = text.replace(":", "\\\\:")
    text = text.replace("%", "%%")
    text = text.replace("\n", "\\\\\\\\n")
    return text


class FontNotFoundError(LookupError):
    """Raised when a font_family cannot be resolved to a file on disk."""


# Map of supported family → weight → base filename (no extension).
# The resolver tries _FONT_EXTENSIONS in order and returns the first that
# exists on disk.
_FONT_FILE_BASES: dict[str, dict[str, str]] = {
    "Pretendard": {
        "Bold": "Pretendard-Bold",
        "Regular": "Pretendard-Regular",
    },
    "Noto Sans KR": {
        "Bold": "NotoSansKR-Bold",
        "Regular": "NotoSansKR-Regular",
    },
}

# TTF first because that's what we ship today; OTF kept as a fallback so a
# future asset swap doesn't require a coordinated code change.
_FONT_EXTENSIONS: tuple[str, ...] = (".ttf", ".otf")

# Public allow-list. Mirrored by SubtitleStyleSpec.font_family Literal in
# schemas.py and by the frontend FONT_OPTIONS in services/web. Adding a font
# means: drop the file in every consumer's fonts dir AND extend this tuple
# AND extend the Literal AND extend the FE list.
SUPPORTED_FONTS: tuple[str, ...] = tuple(_FONT_FILE_BASES.keys())


def _resolve_font_path(family: str, weight: int, font_dir: str) -> str:
    """Resolve a font family + weight to an existing file on disk.

    Raises ``FontNotFoundError`` if ``family`` is not supported or if no file
    matching any allowed extension exists in ``font_dir``. We deliberately
    fail loudly rather than silently substituting a default — a missing font
    on a render worker is a deploy bug and should crash the job, not produce
    a video with the wrong typeface.
    """
    font_dir = font_dir.rstrip("/")
    weight_suffix = "Bold" if weight >= 600 else "Regular"

    family_bases = _FONT_FILE_BASES.get(family)
    if family_bases is None:
        raise FontNotFoundError(
            f"Unsupported font_family={family!r}; "
            f"supported families: {SUPPORTED_FONTS}"
        )
    base = family_bases[weight_suffix]

    for ext in _FONT_EXTENSIONS:
        candidate = f"{font_dir}/{base}{ext}"
        if os.path.exists(candidate):
            return candidate

    raise FontNotFoundError(
        f"No font file found for family={family!r} weight={weight} "
        f"in {font_dir!r} with extensions {_FONT_EXTENSIONS}"
    )

def _position_to_ffmpeg_x(position_x: float, text_align: str) -> str:
    """Convert normalized x position + alignment to ffmpeg x expression."""
    if text_align == "center":
        return f"w*{position_x}-tw/2"
    if text_align == "right":
        return f"w*{position_x}-tw"
    # left
    return f"w*{position_x}"


# ---------------------------------------------------------------------------
# V2 overlay filter chain (PNG-overlay path)
# ---------------------------------------------------------------------------

def build_overlay_filter_chain(
    *,
    overlays: list[OverlaySpec],
    overlay_input_indices: list[int],
    label_in: str,
    final_label: str = "vout",
) -> list[str]:
    """Build ffmpeg overlay filter strings for V2 overlays.

    Each overlay's effects (opacity, rotation, stroke, shadow with blur and
    spread) MUST already be baked into the PNG by
    ``heimdex_media_pipelines.composition.overlay_render.bake_overlay_png``.
    This function only positions the PNG on the canvas and gates its visibility
    by ``enable='between(t, start, end)'``.

    Args:
        overlays: Overlays in render order (back → front). Caller is responsible
            for sorting by ``layer_index``; this function does NOT re-sort.
        overlay_input_indices: ffmpeg ``-i`` input index for each overlay's PNG
            (parallel to ``overlays``). E.g. if 2 clip inputs feed indices 0–1,
            three overlay PNGs would be at indices [2, 3, 4].
        label_in: Filtergraph label feeding the first overlay (typically
            ``f"canvas{n}"`` after clip overlays, or ``"final"`` if the legacy
            subtitle drawtext chain ran).
        final_label: Label assigned to the last overlay's output. Caller wires
            this to ``-map`` for the final video stream.

    Returns:
        A list of filter strings, one per overlay. Caller appends/extends into
        its own parts list and joins with ``";\\n"`` like ``build_filter_graph``.

    Raises:
        ValueError: if ``overlays`` and ``overlay_input_indices`` have mismatched
            lengths.
    """
    if not overlays:
        return []
    if len(overlays) != len(overlay_input_indices):
        raise ValueError(
            f"overlays ({len(overlays)}) and overlay_input_indices "
            f"({len(overlay_input_indices)}) must be the same length"
        )

    parts: list[str] = []
    current_label = label_in
    last_idx = len(overlays) - 1

    for i, (ov, input_idx) in enumerate(zip(overlays, overlay_input_indices)):
        out_label = final_label if i == last_idx else f"ovl{i}"

        # transform.x / .y are normalized [0, 1] and represent the CENTER of
        # the overlay. ffmpeg's overlay= takes top-left, so subtract w/2 and
        # h/2 (where w, h are the overlay PNG's intrinsic dims, known to ffmpeg).
        x_expr = f"W*{ov.transform.x:.4f}-w/2"
        y_expr = f"H*{ov.transform.y:.4f}-h/2"

        enable_start = _ms_to_s(ov.start_ms)
        enable_end = _ms_to_s(ov.end_ms)

        parts.append(
            f"[{current_label}][{input_idx}:v]overlay="
            f"x={x_expr}:y={y_expr}"
            f":enable='between(t,{enable_start},{enable_end})'"
            f"[{out_label}]"
        )
        current_label = out_label

    return parts
