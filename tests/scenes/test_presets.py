"""Tests for preset profiles and resolve_config."""

import pytest

from heimdex_media_contracts.scenes.presets import (
    PRESET_LABELS,
    PRESETS,
    resolve_config,
)
from heimdex_media_contracts.scenes.splitting import SplitConfig


class TestPresets:
    def test_all_presets_are_split_config(self):
        for name, cfg in PRESETS.items():
            assert isinstance(cfg, SplitConfig), f"Preset {name!r} is not SplitConfig"

    def test_default_preset_exists(self):
        assert "default" in PRESETS

    def test_visual_only_disables_speech(self):
        assert PRESETS["visual_only"].speech_split_enabled is False

    def test_fine_has_shorter_target(self):
        assert PRESETS["fine"].target_scene_duration_ms < PRESETS["default"].target_scene_duration_ms

    def test_coarse_has_longer_target(self):
        assert PRESETS["coarse"].target_scene_duration_ms > PRESETS["default"].target_scene_duration_ms

    def test_all_presets_have_labels(self):
        for name in PRESETS:
            assert name in PRESET_LABELS, f"Preset {name!r} missing Korean label"


class TestResolveConfig:
    def test_none_returns_default(self):
        cfg = resolve_config(None)
        assert cfg == PRESETS["default"]

    def test_empty_string_returns_default(self):
        cfg = resolve_config("")
        assert cfg == PRESETS["default"]

    def test_named_preset(self):
        cfg = resolve_config("fine")
        assert cfg == PRESETS["fine"]

    def test_unknown_preset_raises(self):
        with pytest.raises(ValueError, match="Unknown preset"):
            resolve_config("nonexistent")

    def test_overrides_on_preset(self):
        cfg = resolve_config("default", overrides={"target_scene_duration_ms": 10_000})
        assert cfg.target_scene_duration_ms == 10_000
        # base preset fields preserved
        assert cfg.speech_split_enabled is True

    def test_overrides_without_preset(self):
        cfg = resolve_config(None, overrides={"visual_threshold": 0.15})
        assert cfg.visual_threshold == 0.15

    def test_invalid_override_raises(self):
        with pytest.raises(ValueError, match="Unknown SplitConfig fields"):
            resolve_config("default", overrides={"bad_field": 1})
