"""Roundtrip + validation tests for blur schemas.

No I/O, no network — pure pydantic exercise. Matches the style of the
existing ``test_schemas_roundtrip.py`` for other modules.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from uuid import uuid4

import pytest
from pydantic import ValidationError

from heimdex_media_contracts.blur import (
    ALLOWED_BLUR_CATEGORIES,
    BLUR_EXPORT_COMPLETED_TYPE,
    BLUR_EXPORT_CREATED_TYPE,
    BLUR_JOB_COMPLETED_TYPE,
    BLUR_JOB_CREATED_TYPE,
    BLUR_JOB_PROGRESS_TYPE,
    BlurDetectionRecord,
    BlurDetectionSummary,
    BlurExportCreated,
    BlurExportOptions,
    BlurExportResult,
    BlurJobCreated,
    BlurJobProgress,
    BlurJobResult,
    BlurManifest,
    BlurOptions,
    BlurTimingInfo,
    BlurVideoInfo,
)


# ---------- BlurOptions ----------

def test_options_defaults_match_policy():
    opts = BlurOptions()
    assert opts.do_faces is True
    assert opts.do_owl is True
    # Logo MUST be off by default — livecommerce would blur the product.
    assert "logo" not in opts.categories
    assert "face" in opts.categories
    assert "license_plate" in opts.categories
    assert "card_object" in opts.categories
    assert opts.owl_stride == 5
    assert 0 < opts.owl_score_threshold < 1


def test_options_rejects_unknown_category():
    with pytest.raises(ValidationError):
        BlurOptions(categories=("face", "totally-not-real"))  # type: ignore[arg-type]


def test_options_rejects_bad_stride():
    with pytest.raises(ValidationError):
        BlurOptions(owl_stride=0)


def test_options_rejects_out_of_range_threshold():
    with pytest.raises(ValidationError):
        BlurOptions(owl_score_threshold=1.5)


def test_options_allows_logo_opt_in():
    opts = BlurOptions(categories=("face", "logo"))
    assert "logo" in opts.categories


def test_options_custom_queries():
    opts = BlurOptions(custom_owl_queries=("red square", "blue circle"))
    assert opts.custom_owl_queries == ("red square", "blue circle")


# ---------- BlurDetectionRecord ----------

def test_detection_roundtrip():
    d = BlurDetectionRecord(
        frame_idx=3, t_ms=120, category="license_plate",
        label="korean license plate", confidence=0.87,
        bbox_norm=(0.1, 0.2, 0.3, 0.4),
    )
    data = d.model_dump()
    d2 = BlurDetectionRecord.model_validate(data)
    assert d2 == d
    # JSON roundtrip
    payload = d.model_dump_json()
    d3 = BlurDetectionRecord.model_validate_json(payload)
    assert d3 == d


def test_detection_rejects_out_of_range_confidence():
    with pytest.raises(ValidationError):
        BlurDetectionRecord(
            frame_idx=0, t_ms=0, category="face", label="face",
            confidence=1.1, bbox_norm=(0, 0, 1, 1),
        )


def test_detection_rejects_negative_frame():
    with pytest.raises(ValidationError):
        BlurDetectionRecord(
            frame_idx=-1, t_ms=0, category="face", label="face",
            confidence=0.5, bbox_norm=(0, 0, 1, 1),
        )


# ---------- BlurDetectionSummary ----------

def test_summary_from_counts():
    s = BlurDetectionSummary.from_counts({"face": 5, "license_plate": 2})
    assert s.face == 5
    assert s.license_plate == 2
    assert s.card_object == 0  # default


def test_summary_allows_extra_categories():
    s = BlurDetectionSummary.from_counts({"face": 1, "object": 3})
    assert s.object == 3


# ---------- BlurManifest ----------

def _manifest_fixture() -> dict:
    return {
        "schema_version": "1",
        "pipeline_version": "0.10.0",
        "input_path": "/tmp/in.mp4",
        "output_path": "/tmp/out.mp4",
        "video": {"fps": 25.0, "width": 1280, "height": 720, "frame_count": 100},
        "timing": {"total_ms": 1000.0, "owl_infer_ms": 700.0, "owl_infer_frames": 20, "avg_fps": 100.0},
        "config": {"do_faces": True, "owl_stride": 5},
        "summary": {"face": 3, "license_plate": 1, "logo": 0, "card_object": 0, "object": 0},
        "detections": [
            {
                "frame_idx": 0, "t_ms": 0, "category": "face", "label": "face",
                "confidence": 0.95, "bbox_norm": [0.1, 0.1, 0.2, 0.2], "from_cache": False,
            },
        ],
    }


def test_manifest_roundtrip():
    raw = _manifest_fixture()
    m = BlurManifest.model_validate(raw)
    assert m.video.frame_count == 100
    assert m.summary.face == 3
    assert len(m.detections) == 1
    # JSON roundtrip — exact shape preserved
    restored = BlurManifest.model_validate_json(m.model_dump_json())
    assert restored == m


def test_manifest_rejects_missing_video_info():
    raw = _manifest_fixture()
    del raw["video"]
    with pytest.raises(ValidationError):
        BlurManifest.model_validate(raw)


def test_manifest_rejects_extra_top_level_keys():
    raw = _manifest_fixture()
    raw["bogus_field"] = "nope"
    with pytest.raises(ValidationError):
        BlurManifest.model_validate(raw)


def test_timing_and_video_info_reject_zero_fps():
    with pytest.raises(ValidationError):
        BlurVideoInfo(fps=0, width=1, height=1, frame_count=0)


def test_timing_accepts_zero_total():
    # Degenerate case: empty input video.
    t = BlurTimingInfo(total_ms=0, owl_infer_ms=0, owl_infer_frames=0, avg_fps=0)
    assert t.total_ms == 0


# ---------- BlurJobCreated / BlurJobResult ----------

def test_job_created_roundtrip():
    msg = BlurJobCreated(
        timestamp=datetime(2026, 4, 14, tzinfo=timezone.utc),
        job_id=uuid4(),
        file_id=uuid4(),
        org_id=uuid4(),
        video_id="vid-abc",
        source_s3_key="proxies/vid-abc/proxy.mp4",
    )
    data = msg.model_dump_json()
    restored = BlurJobCreated.model_validate_json(data)
    assert restored.type == "blur.job_created"
    assert restored.version == "1"
    assert restored.source_kind == "proxy"
    assert restored.job_id == msg.job_id


def test_job_created_requires_job_id():
    with pytest.raises(ValidationError):
        BlurJobCreated(
            timestamp=datetime.now(timezone.utc),
            file_id=uuid4(), org_id=uuid4(), video_id="v",
            source_s3_key="k",
        )  # type: ignore[call-arg]


def test_job_created_literal_type_enforced():
    with pytest.raises(ValidationError):
        BlurJobCreated(
            type="other.event",  # type: ignore[arg-type]
            timestamp=datetime.now(timezone.utc),
            job_id=uuid4(),
            file_id=uuid4(), org_id=uuid4(), video_id="v",
            source_s3_key="k",
        )


def test_job_result_done():
    r = BlurJobResult(
        job_id=uuid4(), lease_token=uuid4(),
        file_id=uuid4(), org_id=uuid4(), video_id="v",
        status="done",
        blurred_s3_key="blurred/v/job-1/blurred.mp4",
        manifest_s3_key="blurred/v/job-1/manifest.json",
        detections_summary=BlurDetectionSummary.from_counts({"face": 2}),
    )
    payload = r.model_dump_json()
    restored = BlurJobResult.model_validate_json(payload)
    assert restored.status == "done"
    assert restored.detections_summary is not None
    assert restored.detections_summary.face == 2


def test_job_result_failed_needs_no_keys():
    r = BlurJobResult(
        job_id=uuid4(), lease_token=uuid4(),
        file_id=uuid4(), org_id=uuid4(), video_id="v",
        status="failed", error="timeout",
    )
    assert r.blurred_s3_key is None
    assert r.manifest_s3_key is None


def test_job_result_requires_lease_token():
    with pytest.raises(ValidationError):
        BlurJobResult(
            job_id=uuid4(),
            file_id=uuid4(), org_id=uuid4(), video_id="v",
            status="done",
        )  # type: ignore[call-arg]


def test_status_literal_enforced():
    with pytest.raises(ValidationError):
        BlurJobResult(
            job_id=uuid4(), lease_token=uuid4(),
            file_id=uuid4(), org_id=uuid4(), video_id="v",
            status="weird",  # type: ignore[arg-type]
        )


# ---------- invariants shared with the pipeline library ----------

def test_allowed_categories_match_runtime_enum():
    """``ALLOWED_BLUR_CATEGORIES`` is what the worker uses to validate
    without importing the pipeline package. Must match the library's
    ``ALLOWED_CATEGORIES`` set exactly.
    """
    # The literal enum used by BlurDetectionRecord and BlurCategory.
    expected = {"face", "license_plate", "logo", "card_object", "object"}
    assert ALLOWED_BLUR_CATEGORIES == expected


# ---------- schema_version back-compat (v0.10 added "2") ----------

def test_manifest_accepts_schema_version_1_legacy():
    """Old manifests predating v0.10 have schema_version="1" and no
    mask_s3_keys. They must still parse so historical S3 objects stay
    readable across contracts bumps.
    """
    raw = _manifest_fixture()
    raw["schema_version"] = "1"
    m = BlurManifest.model_validate(raw)
    assert m.schema_version == "1"
    assert m.mask_s3_keys is None


def test_manifest_new_writes_default_to_schema_version_2():
    m = BlurManifest(
        pipeline_version="0.11.0",
        input_path="/tmp/in.mp4",
        output_path="/tmp/out.mp4",
        video=BlurVideoInfo(fps=30.0, width=1920, height=1080, frame_count=900),
        timing=BlurTimingInfo(total_ms=0, owl_infer_ms=0, owl_infer_frames=0, avg_fps=0),
        summary=BlurDetectionSummary(),
        detections=[],
    )
    assert m.schema_version == "2"


def test_manifest_rejects_unknown_schema_version():
    raw = _manifest_fixture()
    raw["schema_version"] = "99"
    with pytest.raises(ValidationError):
        BlurManifest.model_validate(raw)


def test_manifest_accepts_mask_s3_keys():
    raw = _manifest_fixture()
    raw["schema_version"] = "2"
    raw["mask_s3_keys"] = {
        "face": "blurred/v/job-1/masks/face.mkv",
        "license_plate": "blurred/v/job-1/masks/license_plate.mkv",
    }
    m = BlurManifest.model_validate(raw)
    assert m.mask_s3_keys is not None
    assert m.mask_s3_keys["face"].endswith("face.mkv")


def test_manifest_rejects_unknown_category_in_mask_keys():
    raw = _manifest_fixture()
    raw["mask_s3_keys"] = {"totally-not-real": "some/key.mkv"}
    with pytest.raises(ValidationError):
        BlurManifest.model_validate(raw)


# ---------- BlurJobResult.mask_s3_keys ----------

def test_job_result_with_mask_keys_roundtrip():
    r = BlurJobResult(
        job_id=uuid4(), lease_token=uuid4(),
        file_id=uuid4(), org_id=uuid4(), video_id="v",
        status="done",
        blurred_s3_key="blurred/v/job-1/blurred.mp4",
        manifest_s3_key="blurred/v/job-1/manifest.json",
        mask_s3_keys={
            "face": "blurred/v/job-1/masks/face.mkv",
            "logo": "blurred/v/job-1/masks/logo.mkv",
        },
    )
    restored = BlurJobResult.model_validate_json(r.model_dump_json())
    assert restored.mask_s3_keys is not None
    assert set(restored.mask_s3_keys.keys()) == {"face", "logo"}


def test_job_result_without_mask_keys_still_valid():
    # Pre-v0.10 consumers that don't emit masks should continue to work.
    r = BlurJobResult(
        job_id=uuid4(), lease_token=uuid4(),
        file_id=uuid4(), org_id=uuid4(), video_id="v",
        status="done",
        blurred_s3_key="k",
        manifest_s3_key="k2",
    )
    assert r.mask_s3_keys is None


# ---------- BlurJobProgress ----------

def test_job_progress_roundtrip():
    p = BlurJobProgress(
        job_id=uuid4(),
        lease_token=uuid4(),
        progress_pct=42.5,
        phase="detecting",
        message="owl inference on frame 120/300",
        eta_seconds=87.3,
    )
    restored = BlurJobProgress.model_validate_json(p.model_dump_json())
    assert restored.type == "blur.job_progress"
    assert restored.version == "1"
    assert restored.phase == "detecting"
    assert restored.progress_pct == 42.5
    assert restored.eta_seconds == 87.3


def test_job_progress_rejects_pct_out_of_range():
    with pytest.raises(ValidationError):
        BlurJobProgress(
            job_id=uuid4(), lease_token=uuid4(),
            progress_pct=100.01, phase="encoding",
        )


def test_job_progress_rejects_negative_eta():
    with pytest.raises(ValidationError):
        BlurJobProgress(
            job_id=uuid4(), lease_token=uuid4(),
            progress_pct=50.0, phase="encoding", eta_seconds=-1.0,
        )


def test_job_progress_rejects_unknown_phase():
    with pytest.raises(ValidationError):
        BlurJobProgress(
            job_id=uuid4(), lease_token=uuid4(),
            progress_pct=50.0, phase="bogus",  # type: ignore[arg-type]
        )


def test_job_progress_allows_missing_optional_fields():
    p = BlurJobProgress(
        job_id=uuid4(), lease_token=uuid4(),
        progress_pct=0.0, phase="queued",
    )
    assert p.message is None
    assert p.eta_seconds is None


# ---------- BlurExportOptions / BlurExportCreated / BlurExportResult ----------

def test_export_options_defaults_format():
    opts = BlurExportOptions(categories=("face",))
    assert opts.format == "prores_4444"


def test_export_options_requires_at_least_one_category():
    with pytest.raises(ValidationError):
        BlurExportOptions(categories=())


def test_export_options_rejects_unknown_category():
    with pytest.raises(ValidationError):
        BlurExportOptions(categories=("face", "totally-not-real"))  # type: ignore[arg-type]


def test_export_created_roundtrip():
    msg = BlurExportCreated(
        timestamp=datetime(2026, 4, 15, tzinfo=timezone.utc),
        export_id=uuid4(),
        blur_job_id=uuid4(),
        file_id=uuid4(),
        org_id=uuid4(),
        video_id="vid-abc",
        source_s3_key="proxies/vid-abc/proxy.mp4",
        mask_s3_keys={
            "face": "blurred/vid-abc/job-1/masks/face.mkv",
            "license_plate": "blurred/vid-abc/job-1/masks/license_plate.mkv",
        },
        options=BlurExportOptions(categories=("face", "license_plate")),
    )
    restored = BlurExportCreated.model_validate_json(msg.model_dump_json())
    assert restored.type == "blur.export_created"
    assert restored.version == "1"
    assert restored.options.format == "prores_4444"
    assert set(restored.mask_s3_keys.keys()) == {"face", "license_plate"}


def test_export_created_requires_at_least_one_mask():
    with pytest.raises(ValidationError):
        BlurExportCreated(
            timestamp=datetime.now(timezone.utc),
            export_id=uuid4(), blur_job_id=uuid4(),
            file_id=uuid4(), org_id=uuid4(), video_id="v",
            source_s3_key="k",
            mask_s3_keys={},
            options=BlurExportOptions(categories=("face",)),
        )


def test_export_created_rejects_stray_type():
    with pytest.raises(ValidationError):
        BlurExportCreated(
            type="wrong.event",  # type: ignore[arg-type]
            timestamp=datetime.now(timezone.utc),
            export_id=uuid4(), blur_job_id=uuid4(),
            file_id=uuid4(), org_id=uuid4(), video_id="v",
            source_s3_key="k",
            mask_s3_keys={"face": "k"},
            options=BlurExportOptions(categories=("face",)),
        )


def test_export_result_done():
    r = BlurExportResult(
        export_id=uuid4(),
        lease_token=uuid4(),
        status="done",
        layer_s3_key="blur_exports/vid/export-1/layer.mov",
    )
    restored = BlurExportResult.model_validate_json(r.model_dump_json())
    assert restored.status == "done"
    assert restored.layer_s3_key is not None
    assert restored.error is None


def test_export_result_failed_allows_null_key():
    r = BlurExportResult(
        export_id=uuid4(),
        lease_token=uuid4(),
        status="failed",
        error="ffmpeg alphamerge timeout",
    )
    assert r.layer_s3_key is None
    assert r.error == "ffmpeg alphamerge timeout"


def test_export_result_rejects_unknown_status():
    with pytest.raises(ValidationError):
        BlurExportResult(
            export_id=uuid4(), lease_token=uuid4(),
            status="weird",  # type: ignore[arg-type]
        )


# ---------- message-type constants match model literals ----------

def test_message_type_constants_match_models():
    """Dispatchers import the constants instead of hardcoding strings.
    If a model's ``type`` literal drifts from its constant, routing
    silently breaks — catch it here at build time.
    """
    assert BLUR_JOB_CREATED_TYPE == BlurJobCreated.model_fields["type"].default
    assert BLUR_JOB_COMPLETED_TYPE == BlurJobResult.model_fields["type"].default
    assert BLUR_JOB_PROGRESS_TYPE == BlurJobProgress.model_fields["type"].default
    assert BLUR_EXPORT_CREATED_TYPE == BlurExportCreated.model_fields["type"].default
    assert BLUR_EXPORT_COMPLETED_TYPE == BlurExportResult.model_fields["type"].default
