# Geometry Settings Panels

**Script:** [Geometry Settings Panels (script)](geometry.py)

## Purpose
The three panels that change an already-saved image's pixel GEOMETRY,
each a thin subclass over [Base Tool Settings Panel](base.md) — split
out of the single-file `gui/tool_panels.py` (root Rule #20,
2026-07-30) and kept together because they share one responsibility in
three shapes.

## Connections

### Uses
- [Base Tool Settings Panel](base.md) — the shared chrome
- [Layout Constants](layout.md) — `ASPECT_DIALOG_ENTRY_W`,
  `DENSE_COL_WRAP_PX`
- [Aspect Ratio Canvas](../aspect_canvas.md) — the live W:H editor
- [Logic](../logic.md) — `_upscale_params_from_side_and_filter`
- [Themed Widget Toolkit](../widgets.md) — `Spinner`, `rounded_entry`,
  `rounded_switch`, the Advanced field parsers

### Used by
- [Tool Panels (subfolder)](___tool_panels.md) — re-exported
- [Tool Jobs Mixin](../app_tools.md) — the Crop / Upscale / Aspect
  tool jobs

## Classes

### CropSettingsPanel
Crop's Advanced holds the border-halo-cleanup toggle, safety margin
and ink-detection thresholds `crop_transparent` reads; the panel body
itself is the base chrome.

### UpscaleSettingsPanel / AspectSettingsPanel
No Advanced section — the min-side spinner (Upscale) / target-ratio
`AspectRatioCanvas` (Aspect) IS the panel's one primary control,
always visible via `_build_extra`.


