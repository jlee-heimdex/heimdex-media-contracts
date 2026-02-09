# heimdex-media-contracts

Shared schemas, pure functions, and contracts for Heimdex media pipelines.

This package is intentionally **dependency-light** — it depends only on `pydantic`
and the Python standard library. It must **never** import heavy ML/media libraries
such as `cv2`, `torch`, `whisper`, `insightface`, `pyannote`, `onnxruntime`, or `ffmpeg`.

## Modules

| Module | Contents |
|--------|----------|
| `heimdex_media_contracts.faces.schemas` | Pydantic models for face presence responses |
| `heimdex_media_contracts.faces.sampling` | Pure timestamp sampling math (no file I/O) |
| `heimdex_media_contracts.speech.schemas` | Dataclass models for speech segment pipelines |
| `heimdex_media_contracts.speech.tagger` | Keyword-based segment tagger (pure string matching) |
| `heimdex_media_contracts.speech.ranker` | Segment importance ranker (pure computation) |

## Usage

```python
from heimdex_media_contracts.faces.schemas import FacePresenceResponse
from heimdex_media_contracts.faces.sampling import sample_timestamps
from heimdex_media_contracts.speech.tagger import SpeechTagger
```

## Running tests

```bash
cd heimdex-media-contracts
pip install -e ".[dev]"
python -m pytest -q
```
