from typing import get_args

from heimdex_media_contracts.ingest import SOURCE_TYPE_VALUES, SourceType


def test_source_type_values_match_literal():
    assert list(get_args(SourceType)) == SOURCE_TYPE_VALUES


def test_all_values_are_strings():
    assert all(isinstance(v, str) for v in SOURCE_TYPE_VALUES)


def test_known_values_present():
    assert "gdrive" in SOURCE_TYPE_VALUES
    assert "removable_disk" in SOURCE_TYPE_VALUES
    assert "local" in SOURCE_TYPE_VALUES
