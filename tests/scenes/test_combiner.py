"""Tests for the multi-signal scene boundary combiner.

Tests are grouped by the algorithm stages:
  1. Visual-cuts-only (baseline / legacy behaviour)
  2. Speech-pause splitting
  3. Speaker-turn splitting
  4. Mixed signals
  5. Min-duration enforcement
  6. Max-duration enforcement
  7. Edge cases
"""

import pytest

from heimdex_media_contracts.scenes.combiner import (
    combine_signals,
    _enforce_max_duration,
    _enforce_min_duration,
)
from heimdex_media_contracts.scenes.splitting import SplitConfig, SplitSignal


def _pause(ts: int, strength: float = 0.8) -> SplitSignal:
    return SplitSignal(timestamp_ms=ts, source="speech_pause", strength=strength)


def _turn(ts: int, strength: float = 1.0) -> SplitSignal:
    return SplitSignal(timestamp_ms=ts, source="speaker_turn", strength=strength)


# ---------------------------------------------------------------------------
# 1. Visual cuts only (no speech data) — must match legacy behaviour
# ---------------------------------------------------------------------------

class TestVisualCutsOnly:
    def test_no_cuts_single_scene(self):
        result = combine_signals(
            visual_cuts_ms=[],
            total_duration_ms=60_000,
            config=SplitConfig(speech_split_enabled=False),
        )
        assert 0 in result
        assert 60_000 in result

    def test_visual_cuts_preserved(self):
        result = combine_signals(
            visual_cuts_ms=[10_000, 30_000, 50_000],
            total_duration_ms=60_000,
            config=SplitConfig(speech_split_enabled=False),
        )
        assert result == [0, 10_000, 30_000, 50_000, 60_000]

    def test_cuts_outside_duration_ignored(self):
        result = combine_signals(
            visual_cuts_ms=[-100, 70_000, 30_000],
            total_duration_ms=60_000,
            config=SplitConfig(speech_split_enabled=False),
        )
        assert result == [0, 30_000, 60_000]

    def test_duplicate_cuts_deduplicated(self):
        result = combine_signals(
            visual_cuts_ms=[10_000, 10_000, 10_000],
            total_duration_ms=40_000,
            config=SplitConfig(speech_split_enabled=False),
        )
        assert result == [0, 10_000, 40_000]

    def test_max_duration_fallback_without_speech(self):
        """A single 120s scene with max_scene_duration=45s splits mechanically."""
        result = combine_signals(
            visual_cuts_ms=[],
            total_duration_ms=120_000,
            config=SplitConfig(speech_split_enabled=False, max_scene_duration_ms=45_000),
        )
        # 0, 45000, 90000, 120000
        assert 0 in result
        assert 45_000 in result
        assert 90_000 in result
        assert 120_000 in result


# ---------------------------------------------------------------------------
# 2. Speech pause splitting
# ---------------------------------------------------------------------------

class TestSpeechPauseSplitting:
    def test_splits_at_speech_pause_in_long_gap(self):
        """A 60s gap with a speech pause at 25s should split there."""
        result = combine_signals(
            visual_cuts_ms=[],
            speech_pauses=[_pause(25_000)],
            total_duration_ms=60_000,
            config=SplitConfig(target_scene_duration_ms=20_000),
        )
        assert 25_000 in result

    def test_no_split_when_gap_under_target(self):
        """Gap of 15s with target 20s — no split needed."""
        result = combine_signals(
            visual_cuts_ms=[],
            speech_pauses=[_pause(8_000)],
            total_duration_ms=15_000,
            config=SplitConfig(target_scene_duration_ms=20_000),
        )
        assert result == [0, 15_000]

    def test_multiple_pauses_best_scored_wins(self):
        """Among multiple pauses, the one nearest target position should be preferred."""
        result = combine_signals(
            visual_cuts_ms=[],
            speech_pauses=[_pause(10_000), _pause(24_000), _pause(40_000)],
            total_duration_ms=60_000,
            config=SplitConfig(target_scene_duration_ms=25_000),
        )
        # First split should be near 25s (target), so 24_000 should be picked
        assert 24_000 in result

    def test_speech_not_activated_when_many_visual_cuts(self):
        """With enough visual cuts (>sparse_cut_threshold), speech is not used."""
        # 10 cuts in 60s = 10 cuts/min — well above sparse_cut_threshold=0.5
        cuts = list(range(5_000, 55_001, 5_000))  # 5k, 10k, ..., 55k
        result = combine_signals(
            visual_cuts_ms=cuts,
            speech_pauses=[_pause(7_500), _pause(12_500)],
            total_duration_ms=60_000,
            config=SplitConfig(sparse_cut_threshold=0.5),
        )
        # Speech pauses should NOT appear in result (visual cuts dominate)
        assert 7_500 not in result
        assert 12_500 not in result

    def test_speech_activated_when_few_visual_cuts(self):
        """With 0 visual cuts in 120s, speech splitting activates."""
        result = combine_signals(
            visual_cuts_ms=[],
            speech_pauses=[_pause(30_000), _pause(60_000), _pause(90_000)],
            total_duration_ms=120_000,
            config=SplitConfig(
                target_scene_duration_ms=25_000,
                sparse_cut_threshold=0.5,
            ),
        )
        # At least some speech pauses should be used
        speech_used = any(ts in result for ts in [30_000, 60_000, 90_000])
        assert speech_used


# ---------------------------------------------------------------------------
# 3. Speaker turn splitting
# ---------------------------------------------------------------------------

class TestSpeakerTurnSplitting:
    def test_speaker_turn_used_as_boundary(self):
        result = combine_signals(
            visual_cuts_ms=[],
            speaker_turns=[_turn(30_000)],
            total_duration_ms=60_000,
            config=SplitConfig(target_scene_duration_ms=25_000),
        )
        assert 30_000 in result

    def test_speaker_turn_preferred_over_nearby_pause(self):
        """When a turn and pause are close, the turn's higher weight wins."""
        result = combine_signals(
            visual_cuts_ms=[],
            speech_pauses=[_pause(24_000, strength=0.8)],
            speaker_turns=[_turn(26_000, strength=0.8)],
            total_duration_ms=60_000,
            config=SplitConfig(
                target_scene_duration_ms=25_000,
                speech_pause_weight=0.7,
                speaker_turn_weight=0.9,
            ),
        )
        # Turn at 26k should be picked (higher weight) — or both could appear
        # but at minimum the turn should be present
        assert 26_000 in result


# ---------------------------------------------------------------------------
# 4. Mixed signals
# ---------------------------------------------------------------------------

class TestMixedSignals:
    def test_visual_cuts_plus_speech_refinement(self):
        """Visual cut at 30s creates two 30s halves; speech refines the second half."""
        result = combine_signals(
            visual_cuts_ms=[30_000],
            speech_pauses=[_pause(50_000)],
            total_duration_ms=90_000,
            config=SplitConfig(
                target_scene_duration_ms=25_000,
                sparse_cut_threshold=0.5,  # 1 cut in 1.5min = 0.67 cuts/min -> above threshold
            ),
        )
        # With 0.67 cuts/min > 0.5, speech is NOT activated
        assert 50_000 not in result

    def test_visual_cuts_plus_speech_when_sparse(self):
        """1 visual cut in 5 minutes is sparse — speech should activate."""
        result = combine_signals(
            visual_cuts_ms=[150_000],
            speech_pauses=[_pause(50_000), _pause(100_000), _pause(200_000), _pause(250_000)],
            total_duration_ms=300_000,
            config=SplitConfig(
                target_scene_duration_ms=25_000,
                sparse_cut_threshold=0.5,
            ),
        )
        # 1 cut in 5 min = 0.2 cuts/min < 0.5 — speech should activate
        speech_used = any(ts in result for ts in [50_000, 100_000, 200_000, 250_000])
        assert speech_used


# ---------------------------------------------------------------------------
# 5. Min-duration enforcement
# ---------------------------------------------------------------------------

class TestMinDuration:
    def test_tiny_scene_merged(self):
        # boundaries: 0, 200, 10000 -> 200ms scene is below 500ms min
        result = _enforce_min_duration([0, 200, 10_000], 500)
        assert 200 not in result
        assert 0 in result
        assert 10_000 in result

    def test_last_scene_too_short_merged(self):
        result = _enforce_min_duration([0, 9_800, 10_000], 500)
        # 200ms final scene merged
        assert 9_800 not in result

    def test_exact_min_duration_kept(self):
        result = _enforce_min_duration([0, 500, 10_000], 500)
        assert 500 in result

    def test_single_scene_untouched(self):
        result = _enforce_min_duration([0, 100], 500)
        assert result == {0, 100}


# ---------------------------------------------------------------------------
# 6. Max-duration enforcement
# ---------------------------------------------------------------------------

class TestMaxDuration:
    def test_long_scene_split(self):
        result = _enforce_max_duration([0, 100_000], 45_000)
        assert 45_000 in result
        assert 90_000 in result
        assert 100_000 in result

    def test_scene_under_max_untouched(self):
        result = _enforce_max_duration([0, 30_000], 45_000)
        assert result == {0, 30_000}

    def test_exact_max_not_split(self):
        result = _enforce_max_duration([0, 45_000], 45_000)
        assert result == {0, 45_000}

    def test_zero_max_no_splits(self):
        result = _enforce_max_duration([0, 100_000], 0)
        assert result == {0, 100_000}


# ---------------------------------------------------------------------------
# 7. Edge cases
# ---------------------------------------------------------------------------

class TestEdgeCases:
    def test_zero_duration(self):
        result = combine_signals(
            visual_cuts_ms=[],
            total_duration_ms=0,
        )
        assert result == []

    def test_negative_duration(self):
        result = combine_signals(
            visual_cuts_ms=[],
            total_duration_ms=-1,
        )
        assert result == []

    def test_very_short_video(self):
        """A 2s video should produce a single scene."""
        result = combine_signals(
            visual_cuts_ms=[],
            total_duration_ms=2_000,
            config=SplitConfig(min_scene_duration_ms=500),
        )
        assert result == [0, 2_000]

    def test_all_signals_at_same_timestamp(self):
        result = combine_signals(
            visual_cuts_ms=[30_000],
            speech_pauses=[_pause(30_000)],
            speaker_turns=[_turn(30_000)],
            total_duration_ms=60_000,
        )
        assert result.count(30_000) == 1

    def test_three_hour_video_dense_speech(self):
        """Long video with many speech pauses should complete without error."""
        duration = 3 * 60 * 60 * 1000  # 3 hours
        pauses = [_pause(t) for t in range(10_000, duration, 5_000)]  # every 5s
        result = combine_signals(
            visual_cuts_ms=[],
            speech_pauses=pauses,
            total_duration_ms=duration,
            config=SplitConfig(target_scene_duration_ms=25_000),
        )
        assert len(result) >= 2
        assert result[0] == 0
        assert result[-1] == duration
        # Scenes should average around target duration
        scene_durations = [result[i + 1] - result[i] for i in range(len(result) - 1)]
        avg = sum(scene_durations) / len(scene_durations)
        assert 15_000 <= avg <= 35_000

    def test_no_candidates_in_gap_falls_through_to_max_duration(self):
        """A long gap with no speech signals still gets split by max_duration."""
        result = combine_signals(
            visual_cuts_ms=[],
            speech_pauses=[],  # empty
            total_duration_ms=120_000,
            config=SplitConfig(max_scene_duration_ms=45_000),
        )
        assert 45_000 in result

    def test_none_speech_inputs(self):
        """None values for speech inputs are handled gracefully."""
        result = combine_signals(
            visual_cuts_ms=[20_000],
            speech_pauses=None,
            speaker_turns=None,
            total_duration_ms=60_000,
        )
        assert result == [0, 20_000, 60_000]

    def test_visual_only_preset_matches_legacy(self):
        """visual_only preset should produce same result as speech_split_enabled=False."""
        from heimdex_media_contracts.scenes.presets import PRESETS

        visual_only = PRESETS["visual_only"]
        explicit_off = SplitConfig(speech_split_enabled=False)

        pauses = [_pause(25_000), _pause(50_000)]
        args = dict(
            visual_cuts_ms=[30_000],
            speech_pauses=pauses,
            total_duration_ms=60_000,
        )
        r1 = combine_signals(**args, config=visual_only)
        r2 = combine_signals(**args, config=explicit_off)
        assert r1 == r2
