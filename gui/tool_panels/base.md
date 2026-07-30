# Base Tool Settings Panel

**Script:** [Base Tool Settings Panel (script)](base.py)

## Purpose
Base: an input picker (**Folder…**/**Files…**), an optional always-
visible subclass block (`_build_extra`), the embedded `FilterEditor`,
an optional **Advanced** collapsible (`HAS_ADVANCED` — False for
Upscale/Aspect/the checker, which have no hidden engine knobs), an
optional footer note, and Start/Pause/Stop. Subclasses set `SLOT` and
contribute `_build_advanced`/`build_func`/`_advanced_settings`/
`_apply_advanced_settings`.

Split out of the single-file `gui/tool_panels.py` (root Rule #20,
2026-07-30). Its `resolve_input()`/`get_conditions()`/`build_func()`/
`set_run_state()`/`set_paused()` surface is what `PainterGui`'s tool
jobs drive, identically for every tool.

## Connections

### Uses
- [Layout Constants](layout.md) — the dense-column metrics and the
  Advanced caret glyphs
- [Filter Editor](../filter_editor.md) — the shared stacked filter
- [Theme (script)](../theme.py) — `THEME_TOPLEVELS`,
  `smooth_transition` (the Advanced reveal)
- [Themed Widget Toolkit](../widgets.md) — `rounded_button`,
  `style_action_button`
- [Icons](../icons.md) — the tool's own logo
- [Config (subfolder)](../../painter/config/___config.md) —
  `JOB_LABEL`/`JOB_LOGO`, `iter_images`, `selection_base_and_rels`

### Used by
- [BG Settings Panel](bg.md), [Geometry Settings Panels](geometry.md),
  [Image Checker Settings Panel](image_checker.md) — every concrete
  panel subclasses it
- [Tool Jobs Mixin](../app_tools.md) — drives the panel surface

## Classes

### ToolSettingsPanel
See the Purpose section above; the subclass hooks are `_build_extra`,
`_build_advanced`, `build_func`, `_advanced_settings` and
`_apply_advanced_settings`.
