"""OCR detection schemas and pure gating functions."""

from heimdex_media_contracts.ocr.gating import (
    concat_blocks,
    filter_blocks_by_confidence,
    gate_ocr_text,
    is_noise_text,
)
from heimdex_media_contracts.ocr.schemas import (
    OCRBlock,
    OCRFrameResult,
    OCRPipelineResult,
    OCRSceneResult,
)

__all__ = [
    "OCRBlock",
    "OCRFrameResult",
    "OCRSceneResult",
    "OCRPipelineResult",
    "filter_blocks_by_confidence",
    "concat_blocks",
    "is_noise_text",
    "gate_ocr_text",
]
