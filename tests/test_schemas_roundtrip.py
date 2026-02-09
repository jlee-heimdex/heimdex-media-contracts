"""Schema serialization round-trip tests.

Ensures all schemas can be serialized to dict/JSON and deserialized back
without data loss.
"""

import json

from heimdex_media_contracts.faces.schemas import (
    FacePresenceResponse,
    IdentityPresence,
    Interval,
    SceneSummary,
)
from heimdex_media_contracts.speech.schemas import (
    PipelineResult,
    RankedSegment,
    SpeechSegment,
    TaggedSegment,
)


class TestFaceSchemasRoundTrip:
    def test_interval_roundtrip(self):
        orig = Interval(start_s=1.5, end_s=3.0, confidence=0.9)
        data = orig.model_dump()
        restored = Interval(**data)
        assert restored == orig

    def test_scene_summary_roundtrip(self):
        orig = SceneSummary(scene_id="s1", present=True, confidence=0.8)
        data = orig.model_dump()
        restored = SceneSummary(**data)
        assert restored == orig

    def test_scene_summary_none_present(self):
        orig = SceneSummary(scene_id="s2", present=None, confidence=0.5)
        data = orig.model_dump()
        restored = SceneSummary(**data)
        assert restored.present is None

    def test_identity_presence_roundtrip(self):
        orig = IdentityPresence(
            identity_id="host_1",
            intervals=[
                Interval(start_s=0.0, end_s=5.0, confidence=0.9),
                Interval(start_s=10.0, end_s=15.0, confidence=0.7),
            ],
            scene_summary=[
                SceneSummary(scene_id="s1", present=True, confidence=0.8),
            ],
        )
        data = orig.model_dump()
        restored = IdentityPresence(**data)
        assert restored == orig

    def test_face_presence_response_roundtrip(self):
        orig = FacePresenceResponse(
            video_id="video_001",
            identities=[
                IdentityPresence(
                    identity_id="host_1",
                    intervals=[Interval(start_s=0.0, end_s=5.0, confidence=0.9)],
                    scene_summary=[],
                ),
            ],
            meta={"detector": "scrfd", "fps": 1.0},
        )
        data = orig.model_dump()
        restored = FacePresenceResponse(**data)
        assert restored == orig

    def test_face_presence_response_json(self):
        orig = FacePresenceResponse(
            video_id="vid",
            identities=[],
            meta={"key": "value"},
        )
        json_str = orig.model_dump_json()
        data = json.loads(json_str)
        restored = FacePresenceResponse(**data)
        assert restored == orig


class TestSpeechSchemasRoundTrip:
    def test_speech_segment_roundtrip(self):
        orig = SpeechSegment(start=0.0, end=5.0, text="hello", confidence=0.95)
        assert orig.duration == 5.0

    def test_tagged_segment_roundtrip(self):
        orig = TaggedSegment(
            start=0.0, end=5.0, text="할인 가격",
            confidence=0.9, tags=["price"], tag_scores={"price": 0.25},
        )
        assert orig.tags == ["price"]
        assert orig.duration == 5.0

    def test_ranked_segment_roundtrip(self):
        orig = RankedSegment(
            start=0.0, end=5.0, text="ranked",
            confidence=0.8, tags=["cta"], tag_scores={"cta": 0.5},
            rank=1, importance_score=0.75,
        )
        assert orig.rank == 1
        assert orig.importance_score == 0.75

    def test_pipeline_result_to_dict(self):
        seg = RankedSegment(
            start=0.0, end=3.0, text="test",
            confidence=0.9, tags=[], tag_scores={},
            rank=1, importance_score=0.0,
        )
        result = PipelineResult(
            video_path="/tmp/test.mp4",
            segments=[seg],
            total_duration=3.0,
            processing_time=1.5,
            status="success",
        )
        d = result.to_dict()
        assert d["video_path"] == "/tmp/test.mp4"
        assert len(d["segments"]) == 1
        assert d["segments"][0]["text"] == "test"
        assert d["status"] == "success"

    def test_pipeline_result_to_json(self):
        result = PipelineResult(
            video_path="/tmp/test.mp4",
            segments=[],
            total_duration=0.0,
            processing_time=0.1,
            status="success",
        )
        json_str = result.to_json()
        parsed = json.loads(json_str)
        assert parsed["video_path"] == "/tmp/test.mp4"
        assert parsed["segments"] == []

    def test_pipeline_result_error_state(self):
        result = PipelineResult(
            video_path="/tmp/bad.mp4",
            status="error",
            error="File not found",
        )
        d = result.to_dict()
        assert d["status"] == "error"
        assert d["error"] == "File not found"
        assert d["segments"] == []
