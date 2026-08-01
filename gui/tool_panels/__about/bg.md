# BG Settings Panel

**Script:** [BG Settings Panel (script)](../bg.py) ·
**Flow:** [diagram](../__flow/bg.md)

## Purpose

`BgSettingsPanel` — the BG-removal tool's own panel (GUI rework Phase
13; the mode + custom-colour block owner 2026-07-28): the
always-visible mode dropdown (auto / white / black / a custom colour
with its wheel, live swatch and ±% tolerance), the reach choice (flood
from the frame vs. everywhere), and the three per-path safety guards
in Advanced. Split out of the single-file `gui/tool_panels.py` (root
Rule #20, 2026-07-30).

## Connections

### Uses
- [Base Tool Settings Panel](base.md) — the shared chrome
  (`ToolSettingsPanel`)
- [Layout Constants](layout.md) — `DENSE_COL_WRAP_PX`
- [Themed Widget Toolkit](../../__about/widgets.md) — `Spinner`,
  `rounded_combo`, `rounded_entry`, `_parse_percent`
- [Config (subfolder)](../../../painter/config/___config.md) —
  `BG_COLOR_DEFAULT`, `BG_COLOR_TOLERANCE_PCT`, `BG_MODE_COLOR`,
  `BG_MODE_DEFAULT`, `BG_MODE_LABEL`, `BG_REACH_ALL`,
  `BG_REACH_DEFAULT`, `BG_REACH_LABEL`, `SAFETY_MAX_REMOVE_FRAC`,
  `SAFETY_MAX_REMOVE_FRAC_COLOR`, `SAFETY_MAX_REMOVE_FRAC_WHITE`,
  `theme_pair`
- [Background Remover](../../../painter/__about/bg_remove.md) —
  `parse_hex_color`, `format_hex_color`, `tolerance_to_distance`
  (validates the typed colour at Start, drives the live swatch and
  tolerance hint) — imported LOCALLY inside the methods that need them
- [Postprocess (Background Removal + Crop)](../../../painter/__about/postprocess.md)
  — `remove_background`, the engine `build_func()` wraps — imported
  LOCALLY inside `build_func`

### Used by
- [Tool Panels (subfolder)](../___tool_panels.md) — re-exported as
  `BgSettingsPanel`/`BG_MODE_BY_LABEL`/`BG_REACH_BY_LABEL`/
  `BG_SWATCH_PX`
- [Tool Jobs Mixin](../../__about/app_tools.md) — the BG tool job

## Classes

### BgSettingsPanel
BG removal's knobs. Its PRIMARY controls are always visible
(`_build_extra`, owner 2026-07-28):

- a **Background** dropdown — Auto (detect), Black, White, or **Custom
  color** — plus, in Custom mode only, the target hex and a `±X %`
  per-channel tolerance spinner. The swatch beside the hex is a
  BUTTON, not decoration: clicking it opens ttkbootstrap's own themed
  `ColorChooserDialog` (Rule #16 — not tkinter's bare OS dialog), which
  also carries an eyedropper. Cancel leaves the field alone; whatever
  the dialog returns is normalised through the run's own parser.
- a **Remove matching pixels** dropdown — *Touching the edge* (the
  flood fill: an ENCLOSED patch of the background colour, like the
  counters inside HOPE's O, survives) or *Everywhere in the image*
  (every matching pixel goes; letters become outlines). Orthogonal to
  the mode, so its own row, with a hint that follows the choice.

Its Advanced collapsible keeps the three safety-guard ceilings
`remove_background` aborts past (black / white / custom), each shown
in **percent of the image** (converted to the engine's fraction in
`build_func`) with a one-line note saying why its default is tight or
high — the guard that hides in Advanced is exactly what silently
blocked the owner's "pointers" run (a hidden 0.40 he never saw), so
the mode itself lives in the always-visible block instead.

Stored keys are the MODE and REACH keys (`BG_MODE_COLOR`,
`BG_REACH_ALL`), never the shown labels, so relabelling a dropdown
cannot invalidate a saved `settings.json` (an unknown stored value
keeps the current default). The guard keys carry a `_pct` SUFFIX
(`safety_black_pct`) because their unit changed from fraction to
percent (owner 2026-07-28) — a settings file from the old fraction
build stores `"0.40"` under the bare key, which read as percent would
be a 0.4 % guard that refuses every image; the renamed key means such
a file falls back to the correct defaults instead of being silently
misread (Rule #6 — no translating shim).

#### Key methods
- `_build_extra` — the mode dropdown, the Custom-mode colour block,
  the reach dropdown.
- `_pick_color` — opens `ColorChooserDialog` on the swatch; a
  cancelled dialog leaves the field untouched.
- `_sync_color_swatch` / `_sync_tolerance_hint` — live preview and the
  "± N levels · #hex…#hex" hint; an unparsable colour greys the swatch
  rather than raising (the loud report is `build_func`'s, at Start).
- `_apply_color_visibility` — packs/hides the colour block for
  Custom vs. every other mode.
- `_build_advanced` — the three safety-guard spinners, in percent.
- `build_func` — parses every field (colour, tolerance, three guards),
  converts guard percent to fraction, returns the closure over
  `remove_background`.
- `_advanced_settings` / `_apply_advanced_settings` — the settings
  round-trip; an unknown stored mode/reach keeps the current default.
