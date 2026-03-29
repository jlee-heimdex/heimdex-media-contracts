"""Data structures for multi-signal scene splitting.

All types here are pure value objects with no I/O or side effects.
They are consumed by the combiner (this package) and signal extractors
(heimdex-media-pipelines).
"""

from __future__ import annotations

from dataclasses import dataclass, field, fields
from typing import Any


@dataclass(frozen=True)
class SplitSignal:
    """A candidate split point from a specific detection source.

    Attributes:
        timestamp_ms: Position in the video (milliseconds from start).
        source: Origin of this signal — one of ``"visual_cut"``,
            ``"speech_pause"``, ``"speaker_turn"``, ``"max_duration"``.
        strength: Normalised confidence in [0.0, 1.0].  Higher means
            the signal is a stronger indicator that a scene boundary
            belongs here.
    """

    timestamp_ms: int
    source: str
    strength: float


@dataclass(frozen=True)
class SplitConfig:
    """Per-org tunable parameters for scene splitting.

    Presets provide named configurations; individual fields can be
    overridden on top of a preset via :func:`resolve_config`.
    """

    # --- visual cut detection (passed through to ffmpeg) ---
    visual_threshold: float = 0.3

    # --- scene duration bounds ---
    min_scene_duration_ms: int = 500
    max_scene_duration_ms: int = 45_000
    target_scene_duration_ms: int = 25_000

    # --- speech-aware splitting ---
    speech_pause_min_gap_ms: int = 300
    speech_pause_weight: float = 0.7
    speaker_turn_weight: float = 0.9
    visual_cut_weight: float = 1.0

    # --- activation control ---
    speech_split_enabled: bool = True
    sparse_cut_threshold: float = 0.5  # cuts/min below this activates speech splitting

    def replace(self, **overrides: Any) -> SplitConfig:
        """Return a copy with the given fields replaced."""
        valid = {f.name for f in fields(self)}
        unknown = set(overrides) - valid
        if unknown:
            raise ValueError(f"Unknown SplitConfig fields: {unknown}")
        current = {f.name: getattr(self, f.name) for f in fields(self)}
        current.update(overrides)
        return SplitConfig(**current)

    def to_dict(self) -> dict[str, Any]:
        """Serialise to a plain dict (JSON-safe)."""
        return {f.name: getattr(self, f.name) for f in fields(self)}

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> SplitConfig:
        """Deserialise from a dict, ignoring unknown keys."""
        valid = {f.name for f in fields(cls)}
        return cls(**{k: v for k, v in data.items() if k in valid})
