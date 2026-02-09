import json
from typing import Any

import pytest
from pydantic import ValidationError

from heimdex_media_contracts.scenes.schemas import (
    SceneBoundary,
    SceneDetectionResult,
    SceneDocument,
)


class TestSceneBoundary:
    def test_valid_boundary(self):
        b = SceneBoundary(
            scene_id="vid001_scene_000",
            index=0,
            start_ms=0,
            end_ms=5000,
            keyframe_timestamp_ms=2500,
        )
        assert b.scene_id == "vid001_scene_000"
        assert b.start_ms == 0
        assert b.end_ms == 5000

    def test_scene_id_format_enforced(self):
        with pytest.raises(ValidationError, match="scene_id"):
            SceneBoundary(
                scene_id="bad_format",
                index=0,
                start_ms=0,
                end_ms=1000,
                keyframe_timestamp_ms=500,
            )

    def test_scene_id_requires_three_digit_index(self):
        with pytest.raises(ValidationError, match="scene_id"):
            SceneBoundary(
                scene_id="vid_scene_1",
                index=1,
                start_ms=0,
                end_ms=1000,
                keyframe_timestamp_ms=500,
            )

    def test_scene_id_accepts_long_index(self):
        b = SceneBoundary(
            scene_id="vid_scene_0001",
            index=1,
            start_ms=0,
            end_ms=1000,
            keyframe_timestamp_ms=500,
        )
        assert b.scene_id == "vid_scene_0001"

    def test_end_before_start_rejected(self):
        with pytest.raises(ValidationError, match="end_ms"):
            SceneBoundary(
                scene_id="vid_scene_000",
                index=0,
                start_ms=5000,
                end_ms=1000,
                keyframe_timestamp_ms=3000,
            )

    def test_zero_duration_boundary_allowed(self):
        b = SceneBoundary(
            scene_id="vid_scene_000",
            index=0,
            start_ms=1000,
            end_ms=1000,
            keyframe_timestamp_ms=1000,
        )
        assert b.start_ms == b.end_ms

    def test_keyframe_path_optional(self):
        b = SceneBoundary(
            scene_id="vid_scene_000",
            index=0,
            start_ms=0,
            end_ms=1000,
            keyframe_timestamp_ms=500,
        )
        assert b.keyframe_path is None

        b2 = SceneBoundary(
            scene_id="vid_scene_000",
            index=0,
            start_ms=0,
            end_ms=1000,
            keyframe_timestamp_ms=500,
            keyframe_path="/tmp/frame.jpg",
        )
        assert b2.keyframe_path == "/tmp/frame.jpg"


class TestSceneDocument:
    def test_required_fields(self):
        doc = SceneDocument(
            scene_id="vid_scene_000",
            video_id="vid",
            index=0,
            start_ms=0,
            end_ms=5000,
            keyframe_timestamp_ms=2500,
        )
        assert doc.transcript_raw == ""
        assert doc.transcript_norm == ""
        assert doc.transcript_char_count == 0
        assert doc.speech_segment_count == 0
        assert doc.people_cluster_ids == []
        assert doc.thumbnail_path is None
        assert doc.thumbnail_url is None

    def test_scene_id_validated_on_document(self):
        with pytest.raises(ValidationError, match="scene_id"):
            SceneDocument(
                scene_id="not_valid",
                video_id="vid",
                index=0,
                start_ms=0,
                end_ms=1000,
                keyframe_timestamp_ms=500,
            )

    def test_full_document_roundtrip(self):
        doc = SceneDocument(
            scene_id="vid_scene_002",
            video_id="vid",
            index=2,
            start_ms=10000,
            end_ms=20000,
            keyframe_timestamp_ms=15000,
            transcript_raw="hello world",
            transcript_norm="hello world",
            transcript_char_count=11,
            speech_segment_count=2,
            people_cluster_ids=["cluster_001"],
            thumbnail_url="https://example.com/thumb.jpg",
        )
        data = doc.model_dump()
        restored = SceneDocument(**data)
        assert restored == doc


class TestSceneDetectionResult:
    def _make_result(self, **overrides: Any) -> SceneDetectionResult:
        defaults: dict[str, Any] = dict(
            pipeline_version="0.2.0",
            model_version="ffmpeg_scenecut",
            video_path="/tmp/test.mp4",
            video_id="vid001",
            total_duration_ms=60000,
            scenes=[
                SceneDocument(
                    scene_id="vid001_scene_000",
                    video_id="vid001",
                    index=0,
                    start_ms=0,
                    end_ms=30000,
                    keyframe_timestamp_ms=15000,
                    transcript_raw="first scene",
                    transcript_norm="first scene",
                    transcript_char_count=11,
                    speech_segment_count=1,
                ),
                SceneDocument(
                    scene_id="vid001_scene_001",
                    video_id="vid001",
                    index=1,
                    start_ms=30000,
                    end_ms=60000,
                    keyframe_timestamp_ms=45000,
                ),
            ],
            processing_time_s=1.5,
        )
        defaults.update(overrides)
        return SceneDetectionResult(**defaults)

    def test_roundtrip_json(self):
        result = self._make_result()
        json_str = result.model_dump_json()
        data = json.loads(json_str)
        restored = SceneDetectionResult(**data)
        assert restored == result
        assert len(restored.scenes) == 2

    def test_default_values(self):
        result = self._make_result()
        assert result.schema_version == "1.0"
        assert result.status == "success"
        assert result.error is None

    def test_error_state(self):
        result = self._make_result(
            status="error",
            error="ffmpeg not found",
            scenes=[],
        )
        assert result.status == "error"
        assert result.error == "ffmpeg not found"
        assert result.scenes == []

    def test_three_field_contract(self):
        result = self._make_result()
        assert result.schema_version != ""
        assert result.pipeline_version != ""
        assert result.model_version != ""
