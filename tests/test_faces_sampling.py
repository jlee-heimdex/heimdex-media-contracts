"""Tests for heimdex_media_contracts.faces.sampling — pure timestamp math."""

import pytest

from heimdex_media_contracts.faces.sampling import _dedupe_sorted, sample_timestamps


class TestDedupeSorted:
    def test_empty(self):
        assert _dedupe_sorted([]) == []

    def test_already_unique(self):
        assert _dedupe_sorted([1.0, 2.0, 3.0]) == [1.0, 2.0, 3.0]

    def test_removes_duplicates(self):
        assert _dedupe_sorted([1.0, 1.0, 2.0]) == [1.0, 2.0]

    def test_sorts(self):
        assert _dedupe_sorted([3.0, 1.0, 2.0]) == [1.0, 2.0, 3.0]

    def test_rounds_to_ndigits(self):
        # 1.0001 and 1.0002 both round to 1.0 at ndigits=3
        result = _dedupe_sorted([1.0001, 1.0002], ndigits=3)
        assert len(result) == 1
        assert result[0] == 1.0

    def test_near_duplicates_kept_with_enough_precision(self):
        result = _dedupe_sorted([1.001, 1.002], ndigits=3)
        assert len(result) == 2


class TestSampleTimestamps:
    def test_basic_one_fps(self):
        ts = sample_timestamps(duration_s=3.0, fps=1.0)
        assert ts == [0.0, 1.0, 2.0, 3.0]

    def test_basic_two_fps(self):
        ts = sample_timestamps(duration_s=1.0, fps=2.0)
        assert ts == [0.0, 0.5, 1.0]

    def test_zero_duration_returns_empty(self):
        assert sample_timestamps(duration_s=0.0, fps=1.0) == []

    def test_negative_duration_raises(self):
        with pytest.raises(ValueError, match="duration_s must be >= 0"):
            sample_timestamps(duration_s=-1.0, fps=1.0)

    def test_zero_fps_raises(self):
        with pytest.raises(ValueError, match="fps must be > 0"):
            sample_timestamps(duration_s=10.0, fps=0)

    def test_negative_fps_raises(self):
        with pytest.raises(ValueError, match="fps must be > 0"):
            sample_timestamps(duration_s=10.0, fps=-1.0)

    def test_scene_boundaries_add_extra_samples(self):
        ts = sample_timestamps(
            duration_s=10.0,
            fps=1.0,
            scene_boundaries_s=[5.0],
            boundary_window_s=0.5,
        )
        # Uniform: 0,1,2,3,4,5,6,7,8,9,10
        # Boundary around 5.0: 4.5, 4.75, 5.0 (dup), 5.25, 5.5
        assert 4.5 in ts
        assert 4.75 in ts
        assert 5.25 in ts
        assert 5.5 in ts
        # Still sorted and deduplicated
        assert ts == sorted(ts)
        assert len(ts) == len(set(round(t, 3) for t in ts))

    def test_boundary_clamped_to_duration(self):
        ts = sample_timestamps(
            duration_s=5.0,
            fps=1.0,
            scene_boundaries_s=[0.1],  # near start
            boundary_window_s=0.5,
        )
        # Offset -0.5 from 0.1 = -0.4 → clamped out
        assert all(t >= 0.0 for t in ts)

    def test_no_boundaries_is_default(self):
        ts1 = sample_timestamps(duration_s=3.0, fps=1.0)
        ts2 = sample_timestamps(duration_s=3.0, fps=1.0, scene_boundaries_s=None)
        assert ts1 == ts2

    def test_results_are_rounded(self):
        ts = sample_timestamps(duration_s=1.0, fps=3.0)
        for t in ts:
            assert t == round(t, 3)

    def test_fractional_duration(self):
        ts = sample_timestamps(duration_s=2.5, fps=1.0)
        assert ts == [0.0, 1.0, 2.0]
