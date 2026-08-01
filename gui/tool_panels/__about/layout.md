# Layout Constants

**Script:** [Layout Constants (script)](../layout.py)

## Purpose

The settings-panel metrics every tool-panel family shares, in ONE leaf
module (root Rule #4; split out with the rest of the package, root
Rule #20, 2026-07-30):

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

**Tier: Standard, not Trivial** — this is not glue/wiring; every
constant carries a real design decision (see Purpose above), so it
earns its own `__about` doc even though it has no algorithm or layout
of its own to sketch in a `__flow` diagram.

## Connections

### Uses
- Nothing — a constants-only leaf, deliberately import-free (so it can
  never cycle back into the panel classes that import it).

### Used by
- [Base Tool Settings Panel](base.md), [BG Settings Panel](bg.md),
  [Geometry Settings Panels](geometry.md),
  [Image Checker Settings Panel](image_checker.md) — `DENSE_COL_GAP_PX`,
  `DENSE_COL_WRAP_PX`, `SETTINGS_GLYPH_COLLAPSED`,
  `SETTINGS_GLYPH_EXPANDED` (base.py); `ASPECT_DIALOG_ENTRY_W`,
  `DENSE_COL_WRAP_PX` (geometry.py); `DENSE_COL_WRAP_PX` (bg.py,
  image_checker.py)
- [Agent Panel](../../__about/agent_panel.md) — `DENSE_COL_WRAP_PX`,
  `ASPECT_DIALOG_ENTRY_W`
- [API Panel](../../__about/api_panel.md) — the full set

## Design Decisions
See [Tool Panels (subfolder)](../___tool_panels.md) — why these live
in a leaf of their own rather than in the package `__init__`.
