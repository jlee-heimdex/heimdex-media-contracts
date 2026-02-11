"""CMX 3600 EDL generator — pure string output, no I/O."""

from __future__ import annotations

from typing import Sequence

from heimdex_media_contracts.exports.schemas import ExportClip


def _ms_to_timecode(ms: int, fps: int) -> str:
    """Convert milliseconds to HH:MM:SS:FF timecode."""
    total_frames = round(ms * fps / 1000.0)
    f = total_frames % fps
    total_seconds = total_frames // fps
    s = total_seconds % 60
    total_minutes = total_seconds // 60
    m = total_minutes % 60
    h = total_minutes // 60
    return f"{h:02d}:{m:02d}:{s:02d}:{f:02d}"


def generate_edl(
    clips: Sequence[ExportClip],
    title: str,
    frame_rate: float = 30.0,
) -> str:
    if not clips:
        raise ValueError("clips must not be empty")

    fps = round(frame_rate)
    is_drop_frame = abs(frame_rate - 29.97) < 0.01 or abs(frame_rate - 59.94) < 0.01

    lines: list[str] = [f"TITLE: {title}"]
    if is_drop_frame:
        lines.append("FCM: DROP FRAME")
    else:
        lines.append("FCM: NON-DROP FRAME")
    lines.append("")

    record_offset_ms = 0
    for i, clip in enumerate(clips, start=1):
        src_in = _ms_to_timecode(clip.start_ms, fps)
        src_out = _ms_to_timecode(clip.end_ms, fps)
        rec_in = _ms_to_timecode(record_offset_ms, fps)
        rec_out = _ms_to_timecode(record_offset_ms + clip.duration_ms, fps)

        reel = "AX"
        lines.append(
            f"{i:03d}  {reel:<8s} {'V':<5s} C        "
            f"{src_in} {src_out} {rec_in} {rec_out}"
        )
        lines.append(f"* FROM CLIP NAME:  {clip.clip_name}")

        record_offset_ms += clip.duration_ms

    lines.append("")
    return "\n".join(lines)
