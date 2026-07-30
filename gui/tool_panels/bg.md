# BG Settings Panel

**Script:** [BG Settings Panel (script)](bg.py)

## Purpose
BG removal's own panel (GUI rework Phase 13; the mode + custom-colour
block owner 2026-07-28). Split out of the single-file
`gui/tool_panels.py` (root Rule #20, 2026-07-30).

## Connections

### Uses
- [Base Tool Settings Panel](base.md) — the shared chrome
- [Layout Constants](layout.md) — `DENSE_COL_WRAP_PX`
- [Themed Widget Toolkit](../widgets.md) — `Spinner`, `rounded_combo`,
  `rounded_entry`, `_parse_percent`
- [Config (subfolder)](../../painter/config/___config.md) — the
  `BG_MODE_*`/`BG_REACH_*`/`SAFETY_*` block
- [Background Remover](../../painter/bg_remove.md) — the engine every
  knob here feeds

### Used by
- [Tool Panels (subfolder)](___tool_panels.md) — re-exported
- [Tool Jobs Mixin](../app_tools.md) — the BG tool job

## Classes

### BgSettingsPanel
BG removal's/Crop's knobs. BG's PRIMARY controls are always visible
(`_build_extra`, owner 2026-07-28):

- a **Background** dropdown — Auto (detect), Black, White, or **Custom
  color** — plus, in Custom mode only, the target hex and a `±X %`
  per-channel tolerance spinner. The swatch beside the hex is a
  BUTTON, not decoration: clicking it opens ttkbootstrap's own themed
  `ColorChooserDialog` (Rule #16 — not tkinter's bare OS dialog),
  which also carries an EYEDROPPER, the fastest way to answer "what
  color is this background?". Cancel leaves the field alone; whatever
  the dialog returns is normalised through the run's own parser.
- a **Remove matching pixels** dropdown — *Touching the edge* (the
  flood fill: an ENCLOSED patch of the background color, like the
  counters inside HOPE's O, survives) or *Everywhere in the image*
  (every matching pixel goes; letters become outlines). Orthogonal to
  the mode, so its own row, with a hint that follows the choice.

Its Advanced collapsible keeps the three safety-guard ceilings
`remove_background` aborts past (black / white / custom). Crop's
Advanced holds the border-halo-cleanup toggle, safety margin and
ink-detection thresholds `crop_transparent` reads.

**Every number is shown in the unit the owner thinks in, and says what
it means** (owner 2026-07-28 — *"sta znace ti brojevi 0.4, 0.85"*):

- the guards are **percent of the image**, converted to the engine's
  fraction in `build_func`, each with a one-line note saying why its
  default is tight or high;
- the tolerance carries a LIVE hint spelling `%` out in colour levels
  and the span it covers (`± 15 levels · #2B506E…#496E8C`), because
  "% of 255" means nothing at a glance. `0 %` is legal — exactly the
  typed colour.

The mode lives in the ALWAYS-VISIBLE block rather than behind the gear
because the guard that hides there is exactly what silently blocked
the owner's "pointers" run: a hidden 0.40 he never saw.

Stored keys: the MODE and REACH keys (`BG_MODE_COLOR`, `BG_REACH_ALL`),
never the shown labels, so relabelling a dropdown cannot invalidate a
saved `settings.json` (an unknown stored value keeps the current
default). The guard keys carry a
`_pct` SUFFIX (`safety_black_pct`) because their UNIT changed — a file
written by the fraction build holds `"0.40"` under the old bare key,
which read as percent would be a 0.4 % guard that refuses every image;
the renamed key means such a file falls back to the correct defaults
instead of being silently misread (Rule #6 — no translating shim).

