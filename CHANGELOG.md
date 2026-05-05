# Changelog

All notable changes to `heimdex-media-contracts`. Tags trigger PyPI publish.

## [0.16.0] — Transcript-driven product enumeration for auto-shorts product mode

### Added
- **`TranscriptEnumerationPrompt`** in `product/prompts.py` — own
  `VERSION = "v1.0"`, independent calibration story from
  `EnumerationPrompt` (vision keyframe pass) and `AliasGenerationPrompt`
  (per-entry alias generation). System message is Korean-livecommerce
  tuned, exclude-rules cover comparison brands and generic categories,
  inclusion rules cover both physical-good livecommerce AND no-clear-
  visuals verticals (travel packages, tour services, subscription
  tiers). Aliases are emitted inline so transcript-discovered entries
  skip the second alias-generation hop.
- **`TranscriptEnumeratedProduct`** in `product/schemas.py` — strict-JSON
  per-product output: `llm_label` (1-200 chars), `spoken_aliases`
  (1-10 post-clean, 1-30 char each, dedupe + drop-empties validator
  matching `AliasGenerationResponse` shape), `first_mention_ms`
  (ge=0, anchor for ordering and optional Phase 5 visual back-fill),
  `example_quote` (1-500 char verbatim — API regex-checks substring
  against source transcript before persist), `confidence` (0-1).
- **`TranscriptEnumerationResponse`** — wraps `products` list (max 50,
  empty allowed when no qualifying mentions), `prompt_version`
  (mirrors `TranscriptEnumerationPrompt.VERSION`), `model` (e.g.,
  `"gpt-4o-mini"` — for cost/quality tracing).
- **`TRANSCRIPT_ENUMERATION_PROMPT_VERSION`** module constant —
  consumers persist this on the catalog entry's prompt-version column
  (or a parallel column for the STT path) so a future bump can target
  stale rows for re-enumeration.

### Changed
- (none — all additions are backward-compatible)

### Compatibility
- **Backward compatible**: v0.15.0 payloads parse cleanly against
  v0.16.0 — none of the new types are referenced by existing schemas;
  this release only ADDS new top-level models and exports. Workers
  on v0.15.0 do not need to rebuild before consumers pin to v0.16.0.
- **Forward compatibility**: workers do not produce or consume the
  new types in this release — transcript enumeration runs INLINE in
  the API process (no SQS, no worker). The publish-then-pin protocol
  applies only to the API pin in this release.

### Migration notes for downstream
- `dev-heimdex-for-livecommerce/services/api`: bump pin to `>=0.16.0`,
  add migration `055_add_enumeration_source` (new
  `enumeration_source` CHECK constraint column on
  `product_catalog_entries`, plus `first_mention_ms` and
  `example_quote` nullable columns), implement
  `services/api/app/modules/shorts_auto_product/enumerate_stt/`
  module that fans out alongside vision enumeration on
  `POST /api/shorts/auto/products/{video_id}/scan`.
- `services/product-enumerate-worker`: no changes required;
  vision-keyframe enumeration prompt (`EnumerationPrompt`, v1.0) is
  unchanged.
- `heimdex-media-pipelines`: no changes required.

### Plan reference
- `dev-heimdex-for-livecommerce/.claude/plans/shorts-auto-product-stt-enum-2026-05-06.md`
  — STT-first enumeration alongside vision enumeration. PR 1 of 7.

## [0.15.0] — Spoken-form aliases for STT-based product mention extraction

### Added
- **`ProductCatalogEntry.spoken_aliases: list[str]`** — additional BM25
  query terms used by the new `shorts_auto_product` STT track to bridge
  the catalog-label → host-speech vocabulary gap. Empty default keeps
  v0.14.0 senders backward-compatible.
- **`AliasGenerationResponse`** — strict-JSON schema for the per-entry
  alias generation LLM call. Includes a `field_validator` that rejects
  sentence-shaped aliases (>30 chars), drops empties, and dedupes
  case-insensitively.
- **`AliasGenerationPrompt`** in `product/prompts.py` — own VERSION
  ("v1.0"), independent calibration story from `EnumerationPrompt`.
  System message generates 3-5 spoken-form aliases prioritizing
  brand-Korean-transliteration → brand-only → category-noun → packaging
  abbreviation. Korean livecommerce-tuned.
- **`ALIAS_GENERATION_PROMPT_VERSION`** module constant — consumers
  persist this in `product_catalog_entries.aliases_prompt_version` so a
  future bump can target stale rows for re-generation.

### Changed
- (none — all additions are backward-compatible)

### Compatibility
- **Backward compatible**: v0.14.0 payloads parse cleanly against
  v0.15.0 — `spoken_aliases` defaults to `[]`. The new field is
  populated post-hoc by the API (NOT by the enumerate worker), so
  worker images on v0.14.0 do NOT need to rebuild before the API pin
  bumps to v0.15.0.
- **Forward compatibility**: a v0.14.0 worker reading a v0.15.0 catalog
  payload would 422 because of `extra="forbid"`. Workers do not read
  `ProductCatalogEntry` payloads from the API in current flows (they
  only PRODUCE them), so this is a non-issue today. If a future worker
  flow consumes catalog entries from the API, it must be on v0.15.0+.

### Migration notes for downstream
- `dev-heimdex-for-livecommerce/services/api`: bump pin to `>=0.15.0`,
  add migration `054_add_spoken_aliases`, add backfill CLI
  `app/cli/backfill_spoken_aliases.py`.
- `services/product-enumerate-worker`: no changes required; existing
  enumeration prompt (`EnumerationPrompt`, v1.0) is unchanged.
- `heimdex-media-pipelines`: no changes required.

### Plan reference
- `dev-heimdex-for-livecommerce/.claude/plans/shorts-auto-product-stt-pivot.md`
  — STT-based replacement for the SAM2 track path. PR 1a.

## [0.12.0] — Unreleased

### Added
- **V2 overlay system** for the shorts editor redesign. New `composition.overlays`
  module exposes:
  - `TextOverlaySpec` — rich text overlay (italic, underline, alignment,
    line-height, letter-spacing, highlight box, layer index).
  - `BackgroundOverlaySpec` — free-floating filled rectangle with explicit
    `width_px` / `height_px`.
  - `OverlaySpec` — discriminated union (`kind: "text" | "background"`).
  - `TransformSpec` — position (normalized), rotation, optional W/H.
  - `EffectsSpec` — opacity + optional `StrokeSpec` + optional `ShadowSpec`
    (with blur and spread).
- `CompositionSpec.overlays: list[OverlaySpec]` field (defaults to `[]`).
  Timeline-bounds validator mirrors the existing subtitle rule.
- `composition.filters.build_overlay_filter_chain` — pure ffmpeg-string builder
  that emits the `overlay=enable='between(t,...)'` chain for baked PNG overlays.
  Per-overlay effects (opacity, rotation, stroke, shadow blur/spread) are
  expected to be baked into the PNG by `heimdex_media_pipelines`; this builder
  only positions and gates timing.

### Changed
- Internal: hex-color validator (`_validate_hex_color`) extracted to
  `composition/_colors.py` to break a potential schemas ↔ overlays import cycle.
  Re-exported from `composition/schemas.py` for any downstream that imported it
  privately. Public API unchanged.

### Compatibility
- **Backward compatible**: 0.11.0 payloads parse cleanly against 0.12.0 — the
  new `overlays` field defaults to `[]`. Existing `subtitles` and
  `SubtitleSpec` / `SubtitleStyleSpec` are untouched and remain in service for
  legacy compositions.
- **Forward compatibility for consumers**: API and worker pinned to
  `>=0.12.0` MUST be released together (or worker first, then API), since a
  request emitted by an API on 0.12 with `overlays=[…]` would fail Pydantic
  validation on a worker pinned to 0.11.

### Migration notes for downstream
- `dev-heimdex-for-livecommerce/services/api`: bump pin to `>=0.12.0`.
- `dev-heimdex-for-livecommerce/services/shorts-render-worker`: bump pin to
  `>=0.12.0`. Wire baked PNG overlays into the render filter graph (PR 3 of the
  shorts editor V2 plan).
- `heimdex-media-pipelines`: add `composition.overlay_render.bake_overlay_png`
  (PIL bake) — heavy deps live there, not in contracts.

## [0.11.0] — Composition font resolver hardening

- `SubtitleStyleSpec.font_family` tightened to closed `Literal` allow-list
  (Pretendard / Noto Sans KR).
- Font resolver now requires the file to exist on disk and raises
  `FontNotFoundError` rather than silently substituting.

## [0.10.0] — PII blur layer export schemas

## [0.9.1] — pydantic 2.7 ValidationInfo.data=None compatibility fix

## [0.9.0] — Speech-aware scene splitting contracts (failed publish; see 0.9.1)
