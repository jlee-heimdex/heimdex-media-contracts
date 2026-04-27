"""Shared fixtures for composition tests."""

import pytest


@pytest.fixture
def fake_font_dir(tmp_path):
    """Create a tmp directory with empty TTF files for every supported font.

    The resolver in filters._resolve_font_path now requires the file to
    exist on disk; tests that call build_filter_graph need this fixture
    so the resolver returns a path instead of raising FontNotFoundError.
    """
    bases = [
        "Pretendard-Regular",
        "Pretendard-Bold",
        "NotoSansKR-Regular",
        "NotoSansKR-Bold",
    ]
    for base in bases:
        (tmp_path / f"{base}.ttf").write_bytes(b"")
    return str(tmp_path)
