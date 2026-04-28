# Changelog

All notable changes to `heimdex-media-contracts`. Tags trigger PyPI publish.

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
