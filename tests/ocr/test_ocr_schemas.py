import json

import pytest
from pydantic import ValidationError

from heimdex_media_contracts.ocr.schemas import (
    OCR_MAX_FRAMES_PER_SCENE,
    OCR_TEXT_MAX_LENGTH,
    OCRBlock,
    OCRFrameResult,
    OCRPipelineResult,
    OCRSceneResult,
)


class TestOCRBlock:
    def test_valid_block(self):
        b = OCRBlock(text="hello", confidence=0.95, bbox=[0.1, 0.2, 0.3, 0.4])
        assert b.text == "hello"
        assert b.confidence == 0.95
        assert b.bbox == [0.1, 0.2, 0.3, 0.4]

    def test_zero_confidence_accepted(self):
        b = OCRBlock(text="", confidence=0.0, bbox=[0.0, 0.0, 0.0, 0.0])
        assert b.confidence == 0.0

    def test_max_confidence_accepted(self):
        b = OCRBlock(text="x", confidence=1.0, bbox=[0.0, 0.0, 1.0, 1.0])
        assert b.confidence == 1.0

    def test_confidence_above_one_rejected(self):
        with pytest.raises(ValidationError, match="confidence"):
            OCRBlock(text="x", confidence=1.1, bbox=[0.0, 0.0, 0.5, 0.5])

    def test_negative_confidence_rejected(self):
        with pytest.raises(ValidationError, match="confidence"):
            OCRBlock(text="x", confidence=-0.1, bbox=[0.0, 0.0, 0.5, 0.5])

    def test_bbox_too_short_rejected(self):
        with pytest.raises(ValidationError, match="bbox"):
            OCRBlock(text="x", confidence=0.5, bbox=[0.1, 0.2, 0.3])

    def test_bbox_too_long_rejected(self):
        with pytest.raises(ValidationError, match="bbox"):
            OCRBlock(text="x", confidence=0.5, bbox=[0.1, 0.2, 0.3, 0.4, 0.5])

    def test_bbox_value_out_of_range_rejected(self):
        with pytest.raises(ValidationError, match="bbox"):
            OCRBlock(text="x", confidence=0.5, bbox=[0.1, 0.2, 1.5, 0.4])

    def test_bbox_negative_value_rejected(self):
        with pytest.raises(ValidationError, match="bbox"):
            OCRBlock(text="x", confidence=0.5, bbox=[-0.1, 0.2, 0.3, 0.4])

    def test_empty_text_accepted(self):
        b = OCRBlock(text="", confidence=0.5, bbox=[0.0, 0.0, 0.5, 0.5])
        assert b.text == ""

    def test_roundtrip(self):
        b = OCRBlock(text="₩39,900", confidence=0.996, bbox=[0.12, 0.45, 0.28, 0.52])
        data = b.model_dump()
        restored = OCRBlock(**data)
        assert restored == b


class TestOCRFrameResult:
    def test_defaults(self):
        f = OCRFrameResult(frame_ts_ms=2500)
        assert f.blocks == []
        assert f.text_concat == ""
        assert f.processing_time_ms is None

    def test_negative_frame_ts_rejected(self):
        with pytest.raises(ValidationError, match="frame_ts_ms"):
            OCRFrameResult(frame_ts_ms=-1)

    def test_negative_processing_time_rejected(self):
        with pytest.raises(ValidationError, match="processing_time_ms"):
            OCRFrameResult(frame_ts_ms=0, processing_time_ms=-1.0)

    def test_with_blocks(self):
        f = OCRFrameResult(
            frame_ts_ms=1000,
            blocks=[OCRBlock(text="a", confidence=0.9, bbox=[0.0, 0.0, 0.5, 0.5])],
            text_concat="a",
            processing_time_ms=87.3,
        )
        assert len(f.blocks) == 1
        assert f.processing_time_ms == 87.3


class TestOCRSceneResult:
    def test_valid_scene(self):
        s = OCRSceneResult(
            scene_id="vid_scene_0",
            ocr_text_raw="₩39,900",
        )
        assert s.ocr_char_count == 7

    def test_scene_id_format_enforced(self):
        with pytest.raises(ValidationError, match="scene_id"):
            OCRSceneResult(scene_id="bad_format")

    def test_scene_id_accepts_single_digit(self):
        s = OCRSceneResult(scene_id="v_scene_1")
        assert s.scene_id == "v_scene_1"

    def test_empty_ocr_text_gives_zero_char_count(self):
        s = OCRSceneResult(scene_id="v_scene_0", ocr_text_raw="")
        assert s.ocr_char_count == 0

    def test_char_count_auto_computed(self):
        s = OCRSceneResult(scene_id="v_scene_0", ocr_text_raw="hello world")
        assert s.ocr_char_count == 11

    def test_char_count_overridden_by_auto_compute(self):
        s = OCRSceneResult(scene_id="v_scene_0", ocr_text_raw="abc", ocr_char_count=999)
        assert s.ocr_char_count == 3

    def test_max_text_length_enforced(self):
        with pytest.raises(ValidationError, match="ocr_text_raw"):
            OCRSceneResult(
                scene_id="v_scene_0",
                ocr_text_raw="x" * (OCR_TEXT_MAX_LENGTH + 1),
            )

    def test_exactly_max_length_accepted(self):
        s = OCRSceneResult(
            scene_id="v_scene_0",
            ocr_text_raw="x" * OCR_TEXT_MAX_LENGTH,
        )
        assert s.ocr_char_count == OCR_TEXT_MAX_LENGTH

    def test_max_frames_enforced(self):
        frames = [OCRFrameResult(frame_ts_ms=i) for i in range(OCR_MAX_FRAMES_PER_SCENE + 1)]
        with pytest.raises(ValidationError, match="frames"):
            OCRSceneResult(scene_id="v_scene_0", frames=frames)

    def test_exactly_max_frames_accepted(self):
        frames = [OCRFrameResult(frame_ts_ms=i) for i in range(OCR_MAX_FRAMES_PER_SCENE)]
        s = OCRSceneResult(scene_id="v_scene_0", frames=frames)
        assert len(s.frames) == OCR_MAX_FRAMES_PER_SCENE

    def test_defaults(self):
        s = OCRSceneResult(scene_id="v_scene_0")
        assert s.frames == []
        assert s.ocr_text_raw == ""
        assert s.ocr_char_count == 0


class TestOCRPipelineResult:
    def test_defaults(self):
        r = OCRPipelineResult(video_id="vid001")
        assert r.schema_version == "1.0"
        assert r.pipeline_version == ""
        assert r.model_version == ""
        assert r.scenes == []
        assert r.total_frames_processed == 0
        assert r.processing_time_s == 0.0
        assert r.status == "success"
        assert r.error is None
        assert r.meta == {}

    def test_error_state(self):
        r = OCRPipelineResult(
            video_id="vid001",
            status="error",
            error="paddleocr not installed",
        )
        assert r.status == "error"
        assert r.error == "paddleocr not installed"

    def test_roundtrip_json(self):
        scene = OCRSceneResult(
            scene_id="vid001_scene_0",
            frames=[
                OCRFrameResult(
                    frame_ts_ms=2500,
                    blocks=[
                        OCRBlock(text="₩39,900", confidence=0.996, bbox=[0.12, 0.45, 0.28, 0.52]),
                    ],
                    text_concat="₩39,900",
                    processing_time_ms=87.3,
                ),
            ],
            ocr_text_raw="₩39,900",
        )
        result = OCRPipelineResult(
            video_id="vid001",
            pipeline_version="0.1.0",
            model_version="paddleocr_ppv5_korean_mobile",
            scenes=[scene],
            total_frames_processed=1,
            processing_time_s=2.32,
            meta={"engine": "paddleocr"},
        )
        json_str = result.model_dump_json()
        data = json.loads(json_str)
        restored = OCRPipelineResult(**data)
        assert restored == result
        assert len(restored.scenes) == 1
        assert restored.scenes[0].ocr_text_raw == "₩39,900"

    def test_three_field_contract(self):
        r = OCRPipelineResult(
            video_id="vid",
            pipeline_version="0.1.0",
            model_version="test",
        )
        assert r.schema_version == "1.0"
        assert r.pipeline_version == "0.1.0"
        assert r.model_version == "test"
