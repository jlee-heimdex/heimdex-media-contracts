"""Tests for the VisualCutsDoc advisory-cache schema."""
from __future__ import annotations

import json

import pytest
from pydantic import ValidationError

from heimdex_media_contracts.scenes.visual_cuts import VisualCutsDoc


_VALID = {
    "schema_version": "1.0",
    "video_id": "vid-abc",
    "detector": "ffmpeg_scenecut_piggyback_v1",
    "threshold": 0.3,
    "cuts_ms": [1000, 3500, 8700],
    "total_duration_ms": 30_000,
    "detected_at": "2026-04-22T14:22:10Z",
    "ffmpeg_version": "n7.1",
}


def test_round_trip_json() -> None:
    doc = VisualCutsDoc(**_VALID)
    payload = doc.model_dump_json()
    restored = VisualCutsDoc.model_validate_json(payload)
    assert restored == doc
    assert json.loads(payload)["cuts_ms"] == [1000, 3500, 8700]


def test_unknown_schema_version_rejected() -> None:
    bad = dict(_VALID, schema_version="2.0")
    with pytest.raises(ValidationError):
        VisualCutsDoc(**bad)


def test_unsorted_cuts_rejected() -> None:
    bad = dict(_VALID, cuts_ms=[5000, 1000, 3000])
    with pytest.raises(ValidationError, match="sorted"):
        VisualCutsDoc(**bad)


def test_duplicate_cuts_rejected() -> None:
    bad = dict(_VALID, cuts_ms=[1000, 1000, 2000])
    with pytest.raises(ValidationError, match="deduplicated"):
        VisualCutsDoc(**bad)


def test_zero_or_negative_cut_rejected() -> None:
    for bad_value in ([0, 1000], [-5, 1000]):
        with pytest.raises(ValidationError, match="strictly positive"):
            VisualCutsDoc(**dict(_VALID, cuts_ms=bad_value))


def test_threshold_bounds_enforced() -> None:
    for bad in (-0.1, 1.1):
        with pytest.raises(ValidationError):
            VisualCutsDoc(**dict(_VALID, threshold=bad))


def test_total_duration_must_be_positive() -> None:
    with pytest.raises(ValidationError):
        VisualCutsDoc(**dict(_VALID, total_duration_ms=0))
    with pytest.raises(ValidationError):
        VisualCutsDoc(**dict(_VALID, total_duration_ms=-1))


def test_empty_cuts_list_accepted() -> None:
    doc = VisualCutsDoc(**dict(_VALID, cuts_ms=[]))
    assert doc.cuts_ms == []


def test_required_string_fields_cannot_be_empty() -> None:
    for field in ("video_id", "detector", "detected_at", "ffmpeg_version"):
        with pytest.raises(ValidationError):
            VisualCutsDoc(**dict(_VALID, **{field: ""}))
