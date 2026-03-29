"""Named preset profiles for scene splitting configuration.

Each preset is a frozen :class:`SplitConfig` instance targeting a
different content style or user preference.  ``resolve_config`` merges
a preset with optional per-field overrides.
"""

from __future__ import annotations

from typing import Any

from heimdex_media_contracts.scenes.splitting import SplitConfig

PRESETS: dict[str, SplitConfig] = {
    # Balanced — good default for Korean live commerce (15-30s scenes).
    "default": SplitConfig(),
    # Granular — search-optimised, shorter scenes for precise navigation.
    "fine": SplitConfig(
        target_scene_duration_ms=15_000,
        max_scene_duration_ms=30_000,
        speech_pause_min_gap_ms=200,
    ),
    # Coarse — fewer, longer scenes for topic-level browsing.
    "coarse": SplitConfig(
        target_scene_duration_ms=45_000,
        max_scene_duration_ms=90_000,
        speech_pause_min_gap_ms=500,
    ),
    # Visual-only — legacy behaviour, no speech splitting.
    "visual_only": SplitConfig(
        speech_split_enabled=False,
    ),
}

# UI-facing labels (Korean).  Keys match PRESETS.
PRESET_LABELS: dict[str, str] = {
    "default": "기본 (균형)",
    "fine": "세밀 (검색 최적화)",
    "coarse": "넓은 (주제 단위)",
    "visual_only": "영상 컷 기준",
}


def resolve_config(
    preset_name: str | None = None,
    overrides: dict[str, Any] | None = None,
) -> SplitConfig:
    """Resolve a :class:`SplitConfig` from a preset name and optional overrides.

    Args:
        preset_name: Key in :data:`PRESETS`.  Defaults to ``"default"``
            when *None* or empty.
        overrides: Per-field overrides applied on top of the preset.

    Returns:
        A fully resolved :class:`SplitConfig`.

    Raises:
        ValueError: If *preset_name* is not a known preset.
    """
    name = preset_name or "default"
    if name not in PRESETS:
        raise ValueError(
            f"Unknown preset {name!r}. Choose from: {sorted(PRESETS)}"
        )
    config = PRESETS[name]
    if overrides:
        config = config.replace(**overrides)
    return config
