"""Pure string functions for ffmpeg filter graph building.

No subprocess calls, no file I/O — same convention as edl.py.
"""

from __future__ import annotations

from heimdex_media_contracts.composition.schemas import (
    OutputSpec,
    SceneClipSpec,
    SubtitleSpec,
)


def escape_drawtext(text: str) -> str:
    """Escape special characters for ffmpeg drawtext filter.

    Must escape: \\ : ' %  (Korean UTF-8 text passes through unchanged).
    """
    text = text.replace("\\", "\\\\")
    text = text.replace(":", "\\:")
    text = text.replace("'", "\\'")
    text = text.replace("%", "%%")
    return text


def calc_text_position(
    pos_x: float,
    pos_y: float,
    text_align: str,
) -> tuple[str, str]:
    """Convert normalized position (0-1) to ffmpeg x/y expressions.

    center: x=(w-text_w)/2, left: x=w*pos_x, right: x=w*pos_x-text_w
    """
    if text_align == "center":
        x_expr = "(w-text_w)/2"
    elif text_align == "right":
        x_expr = f"w*{pos_x}-text_w"
    else:  # left
        x_expr = f"w*{pos_x}"

    y_expr = f"h*{pos_y}"
    return x_expr, y_expr


def resolve_font_path(
    font_family: str,
    font_weight: int,
    font_dir: str,
) -> str:
    """Resolve font file path from family + weight.

    font_weight >= 600 -> Bold variant, < 600 -> Regular variant.
    Returns: {font_dir}/{family}-{Bold|Regular}.ttf
    """
    variant = "Bold" if font_weight >= 600 else "Regular"
    family_clean = font_family.replace(" ", "")
    return f"{font_dir}/{family_clean}-{variant}.ttf"


def build_filter_graph(
    clips: list[SceneClipSpec],
    subtitles: list[SubtitleSpec],
    output: OutputSpec,
    font_dir: str,
) -> str:
    """Build ffmpeg filter_complex string using timeline-based overlay approach.

    Creates a solid-color canvas for the full output duration and overlays
    each clip at its timeline position. Gaps show background color.

    ffmpeg drawtext limitations applied here:
    - shadow_blur: ignored (hard shadow only via shadowx/shadowy)
    - letter_spacing: not supported by drawtext, ignored
    - line_height: mapped to line_spacing = font_size * (line_height - 1.0)
    - font_weight: >= 600 selects Bold variant, < 600 selects Regular
    """
    from heimdex_media_contracts.composition.schemas import CompositionSpec

    # Calculate total duration from clips and subtitles
    clip_end = max((c.timeline_end_ms for c in clips), default=0)
    sub_end = max((s.end_ms for s in subtitles), default=0)
    total_duration_ms = max(clip_end, sub_end)
    total_duration_s = total_duration_ms / 1000.0

    w, h = output.width, output.height
    parts: list[str] = []

    # Base canvas
    parts.append(
        f"color=c={output.background_color}:s={w}x{h}"
        f":d={total_duration_s}:r={output.fps}[base]"
    )

    # Silent audio track
    parts.append(
        f"anullsrc=r=44100:cl=stereo,atrim=0:{total_duration_s}[silence]"
    )

    # Scale each clip to fit within canvas (maintain aspect ratio, even dims)
    for i, clip in enumerate(clips):
        parts.append(
            f"[{i}:v]scale={w}:{h}"
            f":force_original_aspect_ratio=decrease"
            f":force_divisible_by=2[v{i}_scaled]"
        )

    # Overlay each clip centered on the canvas
    prev_label = "base"
    for i, clip in enumerate(clips):
        t_start = clip.timeline_start_ms / 1000.0
        t_end = clip.timeline_end_ms / 1000.0
        out_label = f"canvas{i + 1}"
        parts.append(
            f"[{prev_label}][v{i}_scaled]overlay=x=(W-w)/2:y=(H-h)/2"
            f":enable='between(t,{t_start},{t_end})'[{out_label}]"
        )
        prev_label = out_label

    # Audio: delay and mix each clip's audio
    if clips:
        for i, clip in enumerate(clips):
            delay_ms = clip.timeline_start_ms
            parts.append(f"[{i}:a]adelay={delay_ms}|{delay_ms}[a{i}_delayed]")

        audio_inputs = "".join(f"[a{i}_delayed]" for i in range(len(clips)))
        parts.append(
            f"[silence]{audio_inputs}amix=inputs={len(clips) + 1}"
            f":duration=first[aout]"
        )

    # Subtitles as drawtext filters
    current_label = prev_label
    for j, sub in enumerate(subtitles):
        style = sub.style
        font_path = resolve_font_path(style.font_family, style.font_weight, font_dir)
        x_expr, y_expr = calc_text_position(
            style.position_x, style.position_y, style.text_align
        )
        escaped_text = escape_drawtext(sub.text)
        t_start = sub.start_ms / 1000.0
        t_end = sub.end_ms / 1000.0

        line_spacing = int(style.font_size_px * (style.line_height - 1.0))

        dt_params = [
            f"text='{escaped_text}'",
            f"fontfile={font_path}",
            f"fontsize={style.font_size_px}",
            f"fontcolor={style.font_color}",
            f"x={x_expr}",
            f"y={y_expr}",
            f"line_spacing={line_spacing}",
            f"enable='between(t,{t_start},{t_end})'",
        ]

        if style.shadow_enabled:
            dt_params.append(f"shadowcolor={style.shadow_color}")
            dt_params.append(f"shadowx={style.shadow_offset_x}")
            dt_params.append(f"shadowy={style.shadow_offset_y}")

        if style.background_enabled and style.background_color:
            dt_params.append("box=1")
            dt_params.append(f"boxcolor={style.background_color}")
            dt_params.append(f"boxborderw={style.background_padding}")

        out_label = f"vt{j + 1}" if j < len(subtitles) - 1 else "final"
        parts.append(
            f"[{current_label}]drawtext={':'.join(dt_params)}[{out_label}]"
        )
        current_label = out_label

    return ";\n".join(parts)
