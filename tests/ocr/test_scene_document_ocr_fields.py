import pytest
from pydantic import ValidationError

from heimdex_media_contracts.ocr.schemas import OCRSceneResult
from heimdex_media_contracts.scenes.merge import merge_ocr_into_scene
from heimdex_media_contracts.scenes.schemas import SceneDocument


def _make_scene(**overrides) -> SceneDocument:
    defaults = dict(
        scene_id="vid_scene_0",
        video_id="vid",
        index=0,
        start_ms=0,
        end_ms=5000,
        keyframe_timestamp_ms=2500,
    )
    defaults.update(overrides)
    return SceneDocument(**defaults)


class TestSceneDocumentOCRDefaults:
    def test_ocr_fields_default_to_empty(self):
        doc = _make_scene()
        assert doc.ocr_text_raw == ""
        assert doc.ocr_char_count == 0

    def test_backward_compat_no_ocr_fields_in_data(self):
        data = {
            "scene_id": "vid_scene_0",
            "video_id": "vid",
            "index": 0,
            "start_ms": 0,
            "end_ms": 5000,
            "keyframe_timestamp_ms": 2500,
        }
        doc = SceneDocument(**data)
        assert doc.ocr_text_raw == ""
        assert doc.ocr_char_count == 0
        assert doc.transcript_raw == ""
        assert doc.keyword_tags == []

    def test_ocr_fields_set_explicitly(self):
        doc = _make_scene(
            ocr_text_raw="₩39,900 수분크림",
            ocr_char_count=12,
        )
        assert doc.ocr_text_raw == "₩39,900 수분크림"
        assert doc.ocr_char_count == 12

    def test_roundtrip_with_ocr_fields(self):
        doc = _make_scene(
            transcript_raw="hello world",
            ocr_text_raw="₩39,900",
            ocr_char_count=7,
            keyword_tags=["price"],
        )
        data = doc.model_dump()
        restored = SceneDocument(**data)
        assert restored == doc
        assert restored.ocr_text_raw == "₩39,900"
        assert restored.ocr_char_count == 7

    def test_transcript_fields_independent_from_ocr(self):
        doc = _make_scene(
            transcript_raw="spoken text",
            transcript_char_count=11,
            ocr_text_raw="screen text",
            ocr_char_count=11,
        )
        assert doc.transcript_raw == "spoken text"
        assert doc.ocr_text_raw == "screen text"


class TestMergeOCRIntoScene:
    def test_merge_with_valid_ocr(self):
        scene = _make_scene(transcript_raw="hello")
        ocr = OCRSceneResult(
            scene_id="vid_scene_0",
            ocr_text_raw="₩39,900 수분크림",
        )
        merged = merge_ocr_into_scene(scene, ocr)
        assert merged.ocr_text_raw == "₩39,900 수분크림"
        assert merged.ocr_char_count == len("₩39,900 수분크림")
        assert merged.transcript_raw == "hello"

    def test_merge_does_not_modify_original(self):
        scene = _make_scene()
        ocr = OCRSceneResult(
            scene_id="vid_scene_0",
            ocr_text_raw="test",
        )
        merged = merge_ocr_into_scene(scene, ocr)
        assert scene.ocr_text_raw == ""
        assert merged.ocr_text_raw == "test"

    def test_merge_with_none_ocr_is_noop(self):
        scene = _make_scene(transcript_raw="hello")
        merged = merge_ocr_into_scene(scene, None)
        assert merged.ocr_text_raw == ""
        assert merged.ocr_char_count == 0
        assert merged.transcript_raw == "hello"

    def test_merge_applies_gating_short_text_rejected(self):
        scene = _make_scene()
        ocr = OCRSceneResult(scene_id="vid_scene_0", ocr_text_raw="ab")
        merged = merge_ocr_into_scene(scene, ocr)
        assert merged.ocr_text_raw == ""
        assert merged.ocr_char_count == 0

    def test_merge_applies_gating_noise_rejected(self):
        scene = _make_scene()
        ocr = OCRSceneResult(scene_id="vid_scene_0", ocr_text_raw="---===***!!!")
        merged = merge_ocr_into_scene(scene, ocr)
        assert merged.ocr_text_raw == ""
        assert merged.ocr_char_count == 0

    def test_merge_applies_gating_valid_text_accepted(self):
        scene = _make_scene()
        ocr = OCRSceneResult(scene_id="vid_scene_0", ocr_text_raw="SALE 50%")
        merged = merge_ocr_into_scene(scene, ocr)
        assert merged.ocr_text_raw == "SALE 50%"
        assert merged.ocr_char_count == 8

    def test_merge_preserves_all_existing_fields(self):
        scene = _make_scene(
            transcript_raw="spoken",
            transcript_norm="spoken",
            transcript_char_count=6,
            speech_segment_count=1,
            keyword_tags=["tag1"],
            product_tags=["prod1"],
            product_entities=["entity1"],
        )
        ocr = OCRSceneResult(scene_id="vid_scene_0", ocr_text_raw="screen text")
        merged = merge_ocr_into_scene(scene, ocr)
        assert merged.transcript_raw == "spoken"
        assert merged.transcript_norm == "spoken"
        assert merged.transcript_char_count == 6
        assert merged.speech_segment_count == 1
        assert merged.keyword_tags == ["tag1"]
        assert merged.product_tags == ["prod1"]
        assert merged.product_entities == ["entity1"]
        assert merged.ocr_text_raw == "screen text"

    def test_merge_strips_whitespace_from_ocr(self):
        scene = _make_scene()
        ocr = OCRSceneResult(scene_id="vid_scene_0", ocr_text_raw="  hello world  ")
        merged = merge_ocr_into_scene(scene, ocr)
        assert merged.ocr_text_raw == "hello world"
        assert merged.ocr_char_count == 11

    def test_merge_with_empty_ocr_text(self):
        scene = _make_scene()
        ocr = OCRSceneResult(scene_id="vid_scene_0", ocr_text_raw="")
        merged = merge_ocr_into_scene(scene, ocr)
        assert merged.ocr_text_raw == ""
        assert merged.ocr_char_count == 0
