from uuid import uuid4

import pytest
from pydantic import ValidationError

from heimdex_media_contracts.ingest import IngestSceneDocument, IngestScenesRequest


class TestIngestSceneDocument:
    def test_minimal_valid(self):
        doc = IngestSceneDocument(
            scene_id="vid1_scene_0",
            index=0,
            start_ms=0,
            end_ms=5000,
        )
        assert doc.scene_id == "vid1_scene_0"
        assert doc.source_type == "gdrive"

    def test_scene_id_format_rejected(self):
        with pytest.raises(ValidationError, match="scene_id"):
            IngestSceneDocument(
                scene_id="bad_format",
                index=0,
                start_ms=0,
                end_ms=1000,
            )

    def test_end_before_start_rejected(self):
        with pytest.raises(ValidationError, match="end_ms"):
            IngestSceneDocument(
                scene_id="vid1_scene_0",
                index=0,
                start_ms=5000,
                end_ms=1000,
            )

    def test_all_source_types_accepted(self):
        for st in ["gdrive", "removable_disk", "local"]:
            doc = IngestSceneDocument(
                scene_id="v_scene_0",
                index=0,
                start_ms=0,
                end_ms=1000,
                source_type=st,
            )
            assert doc.source_type == st


    def test_scene_caption_defaults_empty(self):
        doc = IngestSceneDocument(
            scene_id="vid1_scene_0",
            index=0,
            start_ms=0,
            end_ms=5000,
        )
        assert doc.scene_caption == ""

    def test_scene_caption_roundtrip(self):
        caption = "진행자가 카메라 앞에서 핑크색 립스틱을 시연하고 있습니다."
        doc = IngestSceneDocument(
            scene_id="vid1_scene_0",
            index=0,
            start_ms=0,
            end_ms=5000,
            scene_caption=caption,
        )
        assert doc.scene_caption == caption
        rebuilt = IngestSceneDocument.model_validate(doc.model_dump())
        assert rebuilt.scene_caption == caption

    def test_scene_caption_max_length_rejected(self):
        with pytest.raises(ValidationError, match="scene_caption"):
            IngestSceneDocument(
                scene_id="vid1_scene_0",
                index=0,
                start_ms=0,
                end_ms=5000,
                scene_caption="x" * 5_001,
            )


class TestIngestScenesRequest:
    def test_minimal_valid(self):
        req = IngestScenesRequest(
            video_id="test-video",
            library_id=uuid4(),
            scenes=[
                IngestSceneDocument(
                    scene_id="test-video_scene_0",
                    index=0,
                    start_ms=0,
                    end_ms=1000,
                )
            ],
        )
        assert req.video_id == "test-video"
        assert len(req.scenes) == 1

    def test_empty_video_id_rejected(self):
        with pytest.raises(ValidationError, match="video_id"):
            IngestScenesRequest(
                video_id="",
                library_id=uuid4(),
                scenes=[],
            )
