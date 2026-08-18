# Geometry Settings Panels

**Script:** [Geometry Settings Panels (script)](../geometry.py) ·
**Flow:** [diagram](../__flow/geometry.md)

## Purpose

The three panels that change an already-saved image's pixel GEOMETRY,
each a thin subclass over [Base Tool Settings Panel](base.md):
`CropSettingsPanel` (GUI rework Phase 13), `UpscaleSettingsPanel` /
`AspectSettingsPanel` (Phase 14). Split out of the single-file
`gui/tool_panels.py` (root Rule #20, 2026-07-30) and kept together
because they share one responsibility in three shapes and each panel
body is thin — the engine does the work.

## Connections

### Uses
- [Base Tool Settings Panel](base.md) — the shared chrome
- [Layout Constants](layout.md) — `ASPECT_DIALOG_ENTRY_W`,
  `DENSE_COL_WRAP_PX`
- [Shared Filter Framework](../../../painter/__about/filters.md) —
  `filters.FilterCondition` (`UpscaleSettingsPanel._default_conditions`
  seeds the aspect-range filter)
- [Config (subfolder)](../../../painter/config/___config.md) —
  `ASPECT_DEFAULT_H`, `ASPECT_DEFAULT_W`, `CLEAN_EDGE_ENABLE`,
  `CROP_INK_ALPHA`, `CROP_MARGIN_PX`, `CROP_MIN_INK_PX`,
  `FILTER_KIND_ASPECT_RANGE`, `FILTER_POLARITY_IF`,
  `UPSCALE_ASPECT_MAX`, `UPSCALE_ASPECT_MIN`, `UPSCALE_MINDIM_STEP`,
  `UPSCALE_MIN_SIDE_DEFAULT`
- [AspectRatioCanvas](../../__about/aspect_canvas.md) — the live W:H editor
  (`AspectSettingsPanel._build_extra`) + `apply_typed_wh` (the shared
  typed-W/H reshape behind `_on_wh_typed`)
- [Pure Logic Helpers](../../__about/logic.md) —
  `_upscale_params_from_side_and_filter`
  (`UpscaleSettingsPanel.build_func`)
- [Themed Widget Toolkit](../../__about/widgets.md) — `Spinner`,
  `rounded_entry`, `rounded_switch`, `tk_font`, the Advanced field
  parsers `_parse_int_range`/`_parse_nonneg_int`
- [Postprocess (Background Removal + Crop)](../../../painter/__about/postprocess.md)
  — `crop_transparent`, the engine `CropSettingsPanel.build_func`
  wraps — imported LOCALLY inside `build_func`
- [Upscale (Real-ESRGAN)](../../../painter/__about/upscale.md) —
  `upscale_if_small`, the engine `UpscaleSettingsPanel.build_func`
  wraps — imported LOCALLY inside `build_func`
- [Change Aspect Ratio](../../../painter/__about/aspect.md) — `change_aspect`,
  the engine `AspectSettingsPanel.build_func` wraps — imported LOCALLY
  inside `build_func`

### Used by
- [Tool Panels (subfolder)](../___tool_panels.md) — re-exported as
  `CropSettingsPanel`/`UpscaleSettingsPanel`/`AspectSettingsPanel`
- [Tool Jobs Mixin](../../__about/app_tools.md) — the Crop / Upscale / Aspect
  tool jobs

## Classes

### CropSettingsPanel
`SLOT = "crop"`. Advanced exposes every knob `crop_transparent`
actually reads: the border-halo cleanup toggle (`clean_edge_enable` —
only ever serves to ENABLE a tighter crop), the safety MARGIN kept
around the content box, and the ink-detection thresholds (the alpha
floor + the minimum ink pixels a row/col needs to count as content).
`CLEAN_EDGE_ALPHA` (the halo's own alpha threshold, a finer sub-knob)
stays at its config default — not surfaced as a field.

### UpscaleSettingsPanel
`SLOT = "upscale"`, `HAS_ADVANCED = False` — the min-SIDE spinner
(`_build_extra`) plus the base's own embedded `FilterEditor`
(pre-seeded via `_default_conditions` with the aspect-range default)
is the whole gate; there is nothing left to tuck behind a gear.
`build_func` re-reads `get_conditions()` — a harmless duplicate read,
since `PainterGui._start_tool_from_panel` already reads it once to
pre-filter the candidate file list, but this closure needs the same
conditions to resolve the aspect band, and every panel's `build_func`
has the same fixed no-argument signature.

### AspectSettingsPanel
`SLOT = "aspect"`, `HAS_ADVANCED = False` — the target-ratio editor
(`_build_extra`: `AspectRatioCanvas` two-way synced with plain W/H
entries) IS the panel's one primary control; the base's own embedded
`FilterEditor` decides WHICH images qualify. `_build_footer` carries
the non-proportional-stretch warning the old modal's confirm
`askyesno` used to show — Start itself, deliberately configured then
clicked, already IS the confirmation; there is no separate confirm
dialog here.

#### Key methods
- `target_ratio()` — the validated target W:H; raises `ValueError`
  (propagates to Start's messagebox) on a non-positive or unparsable
  value.
- `_on_canvas_drag` / `_on_wh_typed` — the two-way sync between the
  canvas drag and the typed W/H fields (mirrors `AgentPanel`'s own
  Force Aspect Ratio block and `AspectRatioDialog` — the third
  instance of the same sync, Rule #5 candidate if a fourth appears).
- `apply_theme()` — repaints the canvas on a Day/Night flip
  (`AspectRatioCanvas.redraw_theme()`); the only one of the three
  geometry panels that overrides the base's no-op `apply_theme`.

## Design Decisions

**Doc-vs-code gap found and closed during migration.** The pre-2.0
`geometry.md` listed only Base/Layout/AspectRatioCanvas/Logic/Themed
Widget Toolkit as dependencies — it never named `painter.config` (all
twelve constants imported at module level) nor `painter.filters`
(`UpscaleSettingsPanel._default_conditions`) nor the three engine
functions each `build_func` wraps (`crop_transparent`,
`upscale_if_small`, `change_aspect`). Verified against the current
`geometry.py` imports and added above.
