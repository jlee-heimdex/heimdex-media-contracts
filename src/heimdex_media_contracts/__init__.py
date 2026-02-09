"""Shared schemas, pure functions, and contracts for Heimdex media pipelines.

This package must NOT depend on heavy ML/media libraries (cv2, torch, whisper,
insightface, pyannote, onnxruntime, ffmpeg).
"""

__version__ = "0.2.0"

from heimdex_media_contracts import scenes  # noqa: F401
