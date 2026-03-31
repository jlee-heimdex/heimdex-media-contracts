# Heimdex Media Contracts

Shared schemas, pure functions, and contracts for the Heimdex media pipeline ecosystem.

## Quick Reference

```bash
# Install for development
pip install -e ".[dev]"

# Run tests
pytest tests/ -v

# Run tests in Docker
docker build -f Dockerfile.test -t contracts-test . && docker run contracts-test
```

## Design Philosophy

This package is **intentionally lightweight**. It contains ONLY:
- Pydantic models (schemas)
- Pure functions (no I/O, no subprocess calls)
- Zero heavy dependencies (no torch, cv2, whisper, insightface, onnxruntime, ffmpeg)

The only runtime dependency is `pydantic>=2,<3`.

**Why:** This package is imported by everything — agent (via pipelines), livecommerce, playground, and all workers. Heavy dependencies here would cascade to every consumer.

## Package Structure

```
src/heimdex_media_contracts/
├── faces/
│   ├── schemas.py     # FacePresenceResponse, IdentityPresence, Interval
│   └── sampling.py    # Pure timestamp sampling math
├── speech/
│   ├── schemas.py     # SpeechSegment, Transcript
│   ├── tagger.py      # Keyword-based segment tagging
│   └── ranker.py      # Segment importance ranking
├── scenes/
│   ├── splitting.py   # SplitSignal, SplitConfig (speech-aware split contracts)
│   ├── combiner.py    # combine_signals() — merges multiple SplitSignal lists
│   └── presets.py     # default/fine/coarse/visual_only presets (Korean labels), resolve_config()
├── tags/
│   ├── vocabulary.py  # Controlled tag vocabulary (27 keyword + 16 product tags, English keys + Korean display)
│   └── parser.py      # parse_vlm_tag_output() → VLMTagResult (caption, keyword_tags, product_tags, product_entities, ai_tags)
├── ingest/            # Cloud ingest contract models (IngestScenesRequest, IngestSceneDocument with ai_tags)
├── ocr/               # OCR result schemas
├── exports/           # Export format schemas
└── shorts/            # Short-form video schemas
```

## Consumers

**Changes here affect ALL downstream repos. Always verify impact before merging.**

| Consumer | How it imports | Version constraint |
|---|---|---|
| `heimdex-media-pipelines` | Direct Python import | `>=0.8.0` in pyproject.toml |
| `dev-heimdex-for-livecommerce` (API) | Editable volume mount | `>=0.8.0` |
| `dev-heimdex-for-livecommerce` (workers) | Editable volume mount | Same as API |
| `heimdex-agent` | Indirectly via pipelines JSON output | N/A (JSON schema only) |
| `dev-heimdex-playground` | Standalone (no import) | N/A |

### Version Pinning Risk

The livecommerce API's constraint should be `>=0.8.0` to include speech-aware scene splitting contracts (SplitSignal, SplitConfig, presets).

## Making Changes

1. **Add a new field to a schema:** Add with `Optional` default to maintain backward compatibility
2. **Remove a field:** Check ALL consumers first. Mark deprecated before removing.
3. **Add a new module:** Create directory with `schemas.py`, add tests, update `__init__.py` exports
4. **Bump version:** Update `pyproject.toml` version, tag, push — PyPI publish is automatic

## Testing

14+ test files covering:
- Face sampling math
- Speech tagging/ranking logic
- Pydantic schema roundtrip serialization
- Ingest request validation
- OCR schema parsing
- Scene splitting contracts (SplitSignal, SplitConfig, combine_signals, presets) — 53 tests

All tests are pure function tests — no external dependencies, no mocking needed.

## Release

- **Trigger:** Git tag `v*`
- **Pipeline:** Test (Python 3.11) → Build (wheel + sdist) → Publish (PyPI) → GitHub Release
- **Current version:** 0.8.0

## Rules

- Never add heavy ML dependencies (torch, cv2, etc.)
- All models must roundtrip to/from JSON via Pydantic
- All functions must be pure (no I/O, no side effects)
- Every schema change must include roundtrip tests
- Version bumps must consider downstream consumer compatibility
