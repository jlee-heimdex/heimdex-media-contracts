"""Ingestion contract types shared between agent, SaaS API, and workers."""

from typing import Literal

SourceType = Literal["gdrive", "removable_disk", "local"]

SOURCE_TYPE_VALUES: list[str] = ["gdrive", "removable_disk", "local"]

__all__ = [
    "SourceType",
    "SOURCE_TYPE_VALUES",
]
