import pytest

from heimdex_media_contracts.scenes.merge import (
    aggregate_transcript,
    assign_segments_to_scenes,
)
from heimdex_media_contracts.scenes.schemas import SceneBoundary


def _boundary(scene_id: str, index: int, start_ms: int, end_ms: int) -> SceneBoundary:
    return SceneBoundary(
        scene_id=scene_id,
        index=index,
        start_ms=start_ms,
        end_ms=end_ms,
        keyframe_timestamp_ms=(start_ms + end_ms) // 2,
    )


def _seg(start: float, end: float, text: str) -> dict:
    return {"start": start, "end": end, "text": text}


class TestAssignSegmentsToScenes:
    def test_segment_fully_inside_one_scene(self):
        scenes = [_boundary("v_scene_000", 0, 0, 10000)]
        segments = [_seg(1.0, 3.0, "hello")]
        result = assign_segments_to_scenes(scenes, segments)
        assert len(result["v_scene_000"]) == 1
        assert result["v_scene_000"][0]["text"] == "hello"

    def test_segment_spanning_two_scenes_assigned_to_max_overlap(self):
        scenes = [
            _boundary("v_scene_000", 0, 0, 5000),
            _boundary("v_scene_001", 1, 5000, 10000),
        ]
        segments = [_seg(3.0, 8.0, "spanning")]
        result = assign_segments_to_scenes(scenes, segments)
        assert len(result["v_scene_001"]) == 1
        assert len(result["v_scene_000"]) == 0

    def test_no_segments_returns_empty_lists(self):
        scenes = [_boundary("v_scene_000", 0, 0, 5000)]
        result = assign_segments_to_scenes(scenes, [])
        assert result["v_scene_000"] == []

    def test_multiple_segments_in_one_scene_sorted_by_time(self):
        scenes = [_boundary("v_scene_000", 0, 0, 10000)]
        segments = [
            _seg(5.0, 7.0, "second"),
            _seg(1.0, 3.0, "first"),
            _seg(8.0, 9.0, "third"),
        ]
        result = assign_segments_to_scenes(scenes, segments)
        texts = [s["text"] for s in result["v_scene_000"]]
        assert texts == ["first", "second", "third"]

    def test_segment_exactly_at_scene_boundary(self):
        scenes = [
            _boundary("v_scene_000", 0, 0, 5000),
            _boundary("v_scene_001", 1, 5000, 10000),
        ]
        segments = [_seg(5.0, 7.0, "at boundary")]
        result = assign_segments_to_scenes(scenes, segments)
        assert len(result["v_scene_001"]) == 1
        assert len(result["v_scene_000"]) == 0

    def test_zero_duration_scene(self):
        scenes = [_boundary("v_scene_000", 0, 5000, 5000)]
        segments = [_seg(4.9, 5.1, "near zero")]
        result = assign_segments_to_scenes(scenes, segments)
        assert result["v_scene_000"] == []

    def test_segment_outside_all_scenes_dropped(self):
        scenes = [_boundary("v_scene_000", 0, 0, 5000)]
        segments = [_seg(10.0, 12.0, "outside")]
        result = assign_segments_to_scenes(scenes, segments)
        assert result["v_scene_000"] == []

    def test_multiple_scenes_correct_assignment(self):
        scenes = [
            _boundary("v_scene_000", 0, 0, 10000),
            _boundary("v_scene_001", 1, 10000, 20000),
            _boundary("v_scene_002", 2, 20000, 30000),
        ]
        segments = [
            _seg(2.0, 4.0, "in first"),
            _seg(12.0, 14.0, "in second"),
            _seg(22.0, 24.0, "in third"),
        ]
        result = assign_segments_to_scenes(scenes, segments)
        assert len(result["v_scene_000"]) == 1
        assert len(result["v_scene_001"]) == 1
        assert len(result["v_scene_002"]) == 1

    def test_empty_scenes_list(self):
        result = assign_segments_to_scenes([], [_seg(1.0, 2.0, "orphan")])
        assert result == {}


class TestAggregateTranscript:
    def test_single_segment(self):
        assert aggregate_transcript([_seg(0, 1, "hello")]) == "hello"

    def test_multiple_segments_joined(self):
        segs = [_seg(0, 1, "hello"), _seg(1, 2, "world")]
        assert aggregate_transcript(segs) == "hello world"

    def test_empty_segments(self):
        assert aggregate_transcript([]) == ""

    def test_whitespace_only_text_skipped(self):
        segs = [_seg(0, 1, "hello"), _seg(1, 2, "   "), _seg(2, 3, "world")]
        assert aggregate_transcript(segs) == "hello world"

    def test_strips_individual_segments(self):
        segs = [_seg(0, 1, "  hello  "), _seg(1, 2, "  world  ")]
        assert aggregate_transcript(segs) == "hello world"

    def test_missing_text_key_skipped(self):
        segs = [{"start": 0, "end": 1}, {"start": 1, "end": 2, "text": "kept"}]
        assert aggregate_transcript(segs) == "kept"
