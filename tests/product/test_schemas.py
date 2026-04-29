"""Roundtrip + validation tests for the product mode v2 schemas.

No I/O, no network — pure pydantic exercise. Matches the style of the
existing ``tests/blur/test_schemas.py`` and the conventions in
``heimdex-media-contracts/.claude/CLAUDE.md`` (every schema change must
include roundtrip tests; ``field_validator`` reading ``info.data`` must
survive the pydantic 2.7+ JSON-mode ``info.data=None`` case).
"""

from __future__ import annotations

from datetime import datetime, timezone
from uuid import uuid4

import pytest
from pydantic import ValidationError

from heimdex_media_contracts.product import (
    ALLOWED_DURATION_PRESETS,
    ALLOWED_SCAN_STAGES,
    ENUMERATION_PROMPT_VERSION,
    PRODUCT_ENUMERATE_JOB_TYPE,
    PRODUCT_SCAN_COMPLETED_TYPE,
    PRODUCT_SCAN_FAILED_TYPE,
    PRODUCT_SCAN_PROGRESS_TYPE,
    PRODUCT_TRACK_JOB_TYPE,
    AppearanceWindow,
    BBoxXYWH,
    EnumerationDetection,
    EnumerationPrompt,
    ProductCatalogEntry,
    ProductEnumerateJob,
    ProductScanCompleted,
    ProductScanFailed,
    ProductScanProgress,
    ProductTrackJob,
    StitchingPlan,
    StitchWindow,
)


# ---------- module-level constants ----------

def test_enumeration_prompt_version_is_a_string():
    assert isinstance(EnumerationPrompt.VERSION, str)
    assert EnumerationPrompt.VERSION
    assert ENUMERATION_PROMPT_VERSION == EnumerationPrompt.VERSION


def test_enumeration_prompt_system_message_present():
    # Plan §6 requires explicit exclusion rules for hosts / sponsor /
    # studio props. If any of these phrases get edited out of the
    # prompt, the precision floor on goldens will collapse — guard it.
    assert "host" in EnumerationPrompt.SYSTEM.lower()
    assert "exclude" in EnumerationPrompt.SYSTEM.lower()
    assert "background" in EnumerationPrompt.SYSTEM.lower()


def test_duration_presets_locked_to_three_values():
    # Plan §1 locks 30/60/90; if this changes, the migration's
    # CHECK constraint and the plan need updating too.
    assert ALLOWED_DURATION_PRESETS == frozenset({30, 60, 90})


def test_scan_stages_match_migration_enum():
    # Mirrors the product_scan_stage Postgres ENUM in migration 051.
    # Drift here = state machine bugs at runtime.
    assert ALLOWED_SCAN_STAGES == frozenset({
        "queued",
        "enumerating",
        "enumeration_done",
        "tracking",
        "assembling",
        "rendering",
        "done",
        "failed",
        "cancelled",
    })


def test_message_type_constants():
    # Routers and dispatchers switch on these strings; renaming them
    # is a breaking change for every consumer.
    assert PRODUCT_ENUMERATE_JOB_TYPE == "product.enumerate_job"
    assert PRODUCT_TRACK_JOB_TYPE == "product.track_job"
    assert PRODUCT_SCAN_PROGRESS_TYPE == "product.scan_progress"
    assert PRODUCT_SCAN_COMPLETED_TYPE == "product.scan_completed"
    assert PRODUCT_SCAN_FAILED_TYPE == "product.scan_failed"


# ---------- BBoxXYWH ----------

def test_bbox_roundtrip():
    b = BBoxXYWH(x=10, y=20, w=100, h=200)
    assert BBoxXYWH.model_validate_json(b.model_dump_json()) == b


def test_bbox_rejects_zero_width():
    with pytest.raises(ValidationError):
        BBoxXYWH(x=0, y=0, w=0, h=10)


def test_bbox_rejects_negative_origin():
    with pytest.raises(ValidationError):
        BBoxXYWH(x=-1, y=0, w=10, h=10)


# ---------- EnumerationDetection ----------

def test_enumeration_detection_roundtrip():
    d = EnumerationDetection(
        keyframe_scene_id="gd_X_scene_007",
        keyframe_frame_idx=42,
        label="핑크 세럼 병",
        bbox=BBoxXYWH(x=100, y=50, w=200, h=300),
        confidence=0.87,
    )
    assert EnumerationDetection.model_validate_json(d.model_dump_json()) == d


def test_enumeration_detection_rejects_high_confidence():
    with pytest.raises(ValidationError):
        EnumerationDetection(
            keyframe_scene_id="s",
            keyframe_frame_idx=0,
            label="x",
            bbox=BBoxXYWH(x=0, y=0, w=1, h=1),
            confidence=1.5,
        )


# ---------- ProductCatalogEntry ----------

def _catalog_kwargs():
    return {
        "id": uuid4(),
        "org_id": uuid4(),
        "video_id": uuid4(),
        "canonical_crop_s3_key": "products/abc/canonical.jpg",
        "canonical_video_id": uuid4(),
        "canonical_frame_idx": 1234,
        "canonical_bbox": BBoxXYWH(x=10, y=10, w=200, h=300),
        "llm_label": "pink serum bottle",
        "siglip2_embedding": [0.1] * 768,
        "enumeration_confidence": 0.9,
        "prominence_score": 0.42,
        "enumeration_version": "v1.0",
        "enumeration_prompt_version": "v1.0",
        "created_at": datetime(2026, 4, 29, tzinfo=timezone.utc),
    }


def test_catalog_entry_roundtrip():
    entry = ProductCatalogEntry(**_catalog_kwargs())
    assert ProductCatalogEntry.model_validate_json(entry.model_dump_json()) == entry


def test_catalog_entry_rejects_wrong_embedding_dim():
    # 768-dim is locked to match drive-visual-embed-worker's deployed
    # google/siglip2-base-patch16-256 model. Drift breaks the OS coarse
    # pre-filter silently.
    kwargs = _catalog_kwargs()
    kwargs["siglip2_embedding"] = [0.1] * 1024  # wrong (Large)
    with pytest.raises(ValidationError):
        ProductCatalogEntry(**kwargs)
    kwargs["siglip2_embedding"] = [0.1] * 512  # also wrong
    with pytest.raises(ValidationError):
        ProductCatalogEntry(**kwargs)


def test_catalog_entry_user_label_optional():
    kwargs = _catalog_kwargs()
    entry = ProductCatalogEntry(**kwargs)
    assert entry.user_label is None
    kwargs["user_label"] = "Cosrx Snail 96 Mucin Essence"
    assert ProductCatalogEntry(**kwargs).user_label.startswith("Cosrx")


# ---------- AppearanceWindow ----------

def _appearance_kwargs():
    return {
        "catalog_entry_id": uuid4(),
        "scene_id": "gd_X_scene_007",
        "window_start_ms": 1000,
        "window_end_ms": 4500,
        "avg_bbox_area_pct": 0.12,
        "avg_confidence": 0.88,
        "tracker_version": "v1.0",
    }


def test_appearance_window_roundtrip():
    w = AppearanceWindow(**_appearance_kwargs())
    # Survives the pydantic 2.7+ info.data=None case in _end_after_start.
    assert AppearanceWindow.model_validate_json(w.model_dump_json()) == w


def test_appearance_window_rejects_inverted_window():
    kwargs = _appearance_kwargs()
    kwargs["window_start_ms"] = 5000
    kwargs["window_end_ms"] = 4000
    with pytest.raises(ValidationError, match="greater than"):
        AppearanceWindow(**kwargs)


def test_appearance_window_rejects_equal_endpoints():
    # Exactly equal must fail — a zero-length window is meaningless and
    # would break duration math downstream.
    kwargs = _appearance_kwargs()
    kwargs["window_start_ms"] = 1000
    kwargs["window_end_ms"] = 1000
    with pytest.raises(ValidationError):
        AppearanceWindow(**kwargs)


def test_appearance_window_co_appearing_default():
    w = AppearanceWindow(**_appearance_kwargs())
    assert w.co_appearing_catalog_entry_ids == []


# ---------- StitchWindow + StitchingPlan ----------

def test_stitch_window_validator_survives_json_roundtrip():
    sw = StitchWindow(
        scene_id="gd_X_scene_007",
        source_start_ms=1000,
        source_end_ms=4500,
        composite_score=0.77,
        score_components={"prominence": 0.4, "narration": 0.25, "ocr": 0.12},
    )
    # The _end_after_start validator must handle info.data=None during
    # JSON-mode roundtrip — this would have raised AttributeError before
    # the (info.data or {}).get guard.
    assert StitchWindow.model_validate_json(sw.model_dump_json()) == sw


def test_stitching_plan_requires_at_least_one_window():
    with pytest.raises(ValidationError):
        StitchingPlan(
            catalog_entry_id=uuid4(),
            video_id=uuid4(),
            duration_target_sec=60,
            duration_actual_ms=58_000,
            windows=[],  # not allowed; min_length=1
            scorer_version="v1.0",
            subset_picker_version="v1.0",
        )


def test_stitching_plan_locks_duration_preset():
    # 45s is not in {30, 60, 90} — Literal validation must reject.
    with pytest.raises(ValidationError):
        StitchingPlan(
            catalog_entry_id=uuid4(),
            video_id=uuid4(),
            duration_target_sec=45,  # type: ignore[arg-type]
            duration_actual_ms=45_000,
            windows=[
                StitchWindow(
                    scene_id="s",
                    source_start_ms=0,
                    source_end_ms=1000,
                    composite_score=0.5,
                ),
            ],
            scorer_version="v1.0",
            subset_picker_version="v1.0",
        )


def test_stitching_plan_roundtrip_with_preset_60():
    plan = StitchingPlan(
        catalog_entry_id=uuid4(),
        video_id=uuid4(),
        duration_target_sec=60,
        duration_actual_ms=58_000,
        windows=[
            StitchWindow(
                scene_id="a", source_start_ms=0, source_end_ms=20_000,
                composite_score=0.8,
            ),
            StitchWindow(
                scene_id="b", source_start_ms=120_000, source_end_ms=158_000,
                composite_score=0.6,
            ),
        ],
        scorer_version="v1.0",
        subset_picker_version="v1.0",
    )
    assert StitchingPlan.model_validate_json(plan.model_dump_json()) == plan


# ---------- worker → API callbacks ----------

def test_scan_progress_type_is_locked():
    p = ProductScanProgress(
        job_id=uuid4(),
        claimed_by="enum-worker-1",
        stage="enumerating",
        progress_pct=42,
        progress_label="Enumerating products (3/12 batches)",
        cost_delta_usd=0.04,
    )
    assert p.type == PRODUCT_SCAN_PROGRESS_TYPE
    assert ProductScanProgress.model_validate_json(p.model_dump_json()) == p


def test_scan_progress_rejects_unknown_stage():
    with pytest.raises(ValidationError):
        ProductScanProgress(
            job_id=uuid4(),
            claimed_by="w",
            stage="not-a-real-stage",  # type: ignore[arg-type]
            progress_pct=0,
        )


def test_scan_completed_supports_enum_payload():
    entry = ProductCatalogEntry(**_catalog_kwargs())
    msg = ProductScanCompleted(
        job_id=uuid4(),
        claimed_by="enum-worker-1",
        cost_delta_usd=0.23,
        catalog_entries=[entry],
    )
    assert msg.appearances == []
    assert msg.stitching_plan is None
    assert msg.render_job_id is None
    assert ProductScanCompleted.model_validate_json(msg.model_dump_json()) == msg


def test_scan_completed_supports_track_payload():
    plan = StitchingPlan(
        catalog_entry_id=uuid4(),
        video_id=uuid4(),
        duration_target_sec=60,
        duration_actual_ms=58_000,
        windows=[
            StitchWindow(
                scene_id="a", source_start_ms=0, source_end_ms=20_000,
                composite_score=0.8,
            ),
        ],
        scorer_version="v1.0",
        subset_picker_version="v1.0",
    )
    msg = ProductScanCompleted(
        job_id=uuid4(),
        claimed_by="track-worker-1",
        cost_delta_usd=0.53,
        appearances=[AppearanceWindow(**_appearance_kwargs())],
        stitching_plan=plan,
        render_job_id=uuid4(),
    )
    assert msg.catalog_entries == []
    assert ProductScanCompleted.model_validate_json(msg.model_dump_json()) == msg


def test_scan_failed_locks_error_codes():
    # Failure code is a Literal — the UI switches on these. New codes
    # must be added in a coordinated contracts release.
    msg = ProductScanFailed(
        job_id=uuid4(),
        claimed_by="enum-worker-1",
        cost_delta_usd=0.0,
        error_code="no_products_detected",
        error_message="0 products met the inclusion threshold.",
    )
    assert msg.type == PRODUCT_SCAN_FAILED_TYPE
    assert ProductScanFailed.model_validate_json(msg.model_dump_json()) == msg

    with pytest.raises(ValidationError):
        ProductScanFailed(
            job_id=uuid4(),
            claimed_by="w",
            error_code="totally-new-code",  # type: ignore[arg-type]
            error_message="x",
        )


# ---------- API → worker job messages ----------

def test_enumerate_job_roundtrip():
    job = ProductEnumerateJob(
        job_id=uuid4(),
        org_id=uuid4(),
        video_id=uuid4(),
        requested_by_user_id=uuid4(),
        enumeration_version="v1.0",
        enumeration_prompt_version=ENUMERATION_PROMPT_VERSION,
        callback_base_url="https://api.example.com/internal/products",
    )
    assert job.type == PRODUCT_ENUMERATE_JOB_TYPE
    assert job.max_keyframes == 60  # default
    assert ProductEnumerateJob.model_validate_json(job.model_dump_json()) == job


def test_enumerate_job_clamps_max_keyframes():
    # Cap is locked at 200 in the schema to bound LLM cost.
    with pytest.raises(ValidationError):
        ProductEnumerateJob(
            job_id=uuid4(),
            org_id=uuid4(),
            video_id=uuid4(),
            requested_by_user_id=uuid4(),
            enumeration_version="v1.0",
            enumeration_prompt_version="v1.0",
            max_keyframes=500,
            callback_base_url="https://x",
        )


def test_track_job_roundtrip():
    job = ProductTrackJob(
        job_id=uuid4(),
        org_id=uuid4(),
        video_id=uuid4(),
        catalog_entry_id=uuid4(),
        requested_by_user_id=uuid4(),
        duration_preset_sec=60,
        tracker_version="v1.0",
        enumeration_prompt_version=ENUMERATION_PROMPT_VERSION,
        callback_base_url="https://api.example.com/internal/products",
    )
    assert ProductTrackJob.model_validate_json(job.model_dump_json()) == job


def test_track_job_rejects_off_preset_duration():
    with pytest.raises(ValidationError):
        ProductTrackJob(
            job_id=uuid4(),
            org_id=uuid4(),
            video_id=uuid4(),
            catalog_entry_id=uuid4(),
            requested_by_user_id=uuid4(),
            duration_preset_sec=45,  # type: ignore[arg-type]
            tracker_version="v1.0",
            enumeration_prompt_version="v1.0",
            callback_base_url="https://x",
        )
