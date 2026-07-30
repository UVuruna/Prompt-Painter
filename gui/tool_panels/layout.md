# Layout Constants

**Script:** [Layout Constants (script)](layout.py)

## Purpose
The settings-panel metrics every family shares, in ONE leaf module
(root Rule #4; split out with the rest of the package, Rule #20,
2026-07-30):

- `DENSE_COL_GAP_PX` / `DENSE_COL_WRAP_PX` — the two-column-dense fill
  (owner 2026-07-21, Rule #16: a panel with room to spare fills the
  width in two logical columns instead of hugging the left half).
- `ASPECT_DIALOG_ENTRY_W` — the W / H entry width in every ratio
  editor.
- `SETTINGS_GLYPH_EXPANDED` / `SETTINGS_GLYPH_COLLAPSED` — the
  Advanced section's caret label. The wording predates the UI-SKETCH
  rework that retired `AgentPanel`'s own Settings gear (owner
  2026-07-29); these two are the TOOL panels' Advanced header now, and
  nothing else.

## Connections

### Uses
- Nothing — a constants-only leaf, deliberately import-free.

### Used by
- [Base Tool Settings Panel](base.md), [BG Settings Panel](bg.md),
  [Geometry Settings Panels](geometry.md),
  [Image Checker Settings Panel](image_checker.md)
- [Agent Panel](../agent_panel.md) — `DENSE_COL_WRAP_PX`,
  `ASPECT_DIALOG_ENTRY_W`
- [API Panel](../api_panel.md) — the full set

## Design Decisions
See [Tool Panels (subfolder)](___tool_panels.md) — why these live in a
leaf of their own rather than in the package `__init__`.
