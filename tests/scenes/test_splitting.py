"""Tests for SplitSignal and SplitConfig value objects."""

import pytest

from heimdex_media_contracts.scenes.splitting import SplitConfig, SplitSignal


class TestSplitSignal:
    def test_frozen(self):
        sig = SplitSignal(timestamp_ms=1000, source="visual_cut", strength=0.9)
        with pytest.raises(AttributeError):
            sig.timestamp_ms = 2000  # type: ignore[misc]

    def test_fields(self):
        sig = SplitSignal(timestamp_ms=5000, source="speech_pause", strength=0.6)
        assert sig.timestamp_ms == 5000
        assert sig.source == "speech_pause"
        assert sig.strength == 0.6


class TestSplitConfig:
    def test_defaults(self):
        cfg = SplitConfig()
        assert cfg.visual_threshold == 0.3
        assert cfg.min_scene_duration_ms == 500
        assert cfg.max_scene_duration_ms == 45_000
        assert cfg.target_scene_duration_ms == 25_000
        assert cfg.speech_pause_min_gap_ms == 300
        assert cfg.speech_split_enabled is True

    def test_frozen(self):
        cfg = SplitConfig()
        with pytest.raises(AttributeError):
            cfg.visual_threshold = 0.5  # type: ignore[misc]

    def test_replace(self):
        cfg = SplitConfig()
        new = cfg.replace(target_scene_duration_ms=15_000, visual_threshold=0.2)
        assert new.target_scene_duration_ms == 15_000
        assert new.visual_threshold == 0.2
        # unchanged fields preserved
        assert new.max_scene_duration_ms == 45_000

    def test_replace_unknown_field_raises(self):
        cfg = SplitConfig()
        with pytest.raises(ValueError, match="Unknown SplitConfig fields"):
            cfg.replace(nonexistent_field=42)

    def test_to_dict(self):
        cfg = SplitConfig()
        d = cfg.to_dict()
        assert isinstance(d, dict)
        assert d["visual_threshold"] == 0.3
        assert d["speech_split_enabled"] is True

    def test_from_dict(self):
        cfg = SplitConfig.from_dict({
            "visual_threshold": 0.2,
            "target_scene_duration_ms": 10_000,
        })
        assert cfg.visual_threshold == 0.2
        assert cfg.target_scene_duration_ms == 10_000
        # defaults for unspecified fields
        assert cfg.max_scene_duration_ms == 45_000

    def test_from_dict_ignores_unknown_keys(self):
        cfg = SplitConfig.from_dict({"unknown_key": 99, "visual_threshold": 0.1})
        assert cfg.visual_threshold == 0.1

    def test_roundtrip(self):
        original = SplitConfig(target_scene_duration_ms=12_000)
        restored = SplitConfig.from_dict(original.to_dict())
        assert original == restored
