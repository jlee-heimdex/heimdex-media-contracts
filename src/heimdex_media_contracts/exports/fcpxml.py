"""FCPXML v1.9 generator — pure string output, no I/O."""

from __future__ import annotations

from typing import Sequence
from xml.sax.saxutils import escape

from heimdex_media_contracts.exports.schemas import ExportClip

_FRAME_DURATION_MAP: dict[int, str] = {
    24: "1/24s",
    25: "1/25s",
    30: "1/30s",
    50: "1/50s",
    60: "1/60s",
}

_NTSC_FRAME_DURATION_MAP: dict[str, tuple[str, str]] = {
    "23.976": ("1001/24000s", "NDF"),
    "29.97":  ("1001/30000s", "DF"),
    "59.94":  ("1001/60000s", "DF"),
}


def _rational_time(ms: int, frame_rate: float) -> str:
    """Convert milliseconds to FCPXML rational time: '{frames}/{fps}s'."""
    frames = round(ms * frame_rate / 1000.0)
    fps_int = round(frame_rate)
    return f"{frames}/{fps_int}s"


def _resolve_frame_params(frame_rate: float) -> tuple[str, str]:
    """Return (frameDuration, tcFormat) for the given frame rate."""
    key = f"{frame_rate:.3f}".rstrip("0").rstrip(".")
    if key in _NTSC_FRAME_DURATION_MAP:
        return _NTSC_FRAME_DURATION_MAP[key]

    fps_int = round(frame_rate)
    frame_dur = _FRAME_DURATION_MAP.get(fps_int, f"1/{fps_int}s")
    return frame_dur, "NDF"


def generate_fcpxml(
    clips: Sequence[ExportClip],
    project_name: str,
    frame_rate: float = 30.0,
) -> str:
    if not clips:
        raise ValueError("clips must not be empty")

    frame_dur, tc_format = _resolve_frame_params(frame_rate)
    fps_int = round(frame_rate)
    esc_project = escape(project_name)

    resource_lines: list[str] = []
    resource_lines.append(
        f'        <format id="r0" name="FFVideoFormat1920x1080p{fps_int}" '
        f'width="1920" height="1080" frameDuration="{frame_dur}"/>'
    )

    for i, clip in enumerate(clips):
        asset_id = f"r{i + 1}"
        src = escape(clip.media_url or f"file://{clip.media_path}")
        name = escape(clip.clip_name)
        dur = _rational_time(clip.duration_ms, frame_rate)
        resource_lines.append(
            f'        <asset id="{asset_id}" name="{name}" '
            f'hasVideo="1" hasAudio="1" format="r0" '
            f'duration="{dur}" start="0/1s" audioSources="1" audioChannels="2">\n'
            f'            <media-rep kind="original-media" src="{src}"/>\n'
            f'        </asset>'
        )

    spine_lines: list[str] = []
    timeline_offset_ms = 0
    for i, clip in enumerate(clips):
        asset_id = f"r{i + 1}"
        name = escape(clip.clip_name)
        offset = _rational_time(timeline_offset_ms, frame_rate)
        start = _rational_time(clip.start_ms, frame_rate)
        dur = _rational_time(clip.duration_ms, frame_rate)
        spine_lines.append(
            f'                        <asset-clip ref="{asset_id}" name="{name}" '
            f'offset="{offset}" start="{start}" duration="{dur}" '
            f'format="r0" tcFormat="{tc_format}" enabled="1"/>'
        )
        timeline_offset_ms += clip.duration_ms

    total_dur = _rational_time(timeline_offset_ms, frame_rate)
    resources_block = "\n".join(resource_lines)
    spine_block = "\n".join(spine_lines)

    return (
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        "<!DOCTYPE fcpxml>\n"
        '<fcpxml version="1.9">\n'
        "    <resources>\n"
        f"{resources_block}\n"
        "    </resources>\n"
        "    <library>\n"
        f'        <event name="{esc_project}">\n'
        f'            <project name="{esc_project}">\n'
        f'                <sequence tcStart="0/1s" tcFormat="{tc_format}" '
        f'duration="{total_dur}" format="r0">\n'
        "                    <spine>\n"
        f"{spine_block}\n"
        "                    </spine>\n"
        "                </sequence>\n"
        "            </project>\n"
        "        </event>\n"
        "    </library>\n"
        "</fcpxml>\n"
    )
