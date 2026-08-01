# Base Tool Settings Panel

**Script:** [Base Tool Settings Panel (script)](../base.py) ·
**Flow:** [diagram](../__flow/base.md)

## Purpose

`ToolSettingsPanel` — the shared chrome every standalone in-place
tool's persistent settings panel is built from (GUI rework Phase 13):
an input picker (**Folder…** / **Files…**), an optional always-visible
subclass block (`_build_extra`), the embedded `FilterEditor` gate, an
optional **Advanced** collapsible (`HAS_ADVANCED` — `False` for
Upscale/Aspect/the image checker, which have no hidden engine knobs),
an optional footer note, and the Start/Pause/Stop row with its
run-state styling.

Split out of the single-file `gui/tool_panels.py` (root Rule #20,
2026-07-30). Its `resolve_input()`/`get_conditions()`/`build_func()`/
`set_run_state()`/`set_paused()`/`get_settings()`/`apply_settings()`
surface is what `PainterGui`'s tool jobs drive, identically for every
tool. Subclasses set `SLOT` and contribute `_build_extra`/
`_build_advanced`/`_build_footer`/`build_func`/`_advanced_settings`/
`_apply_advanced_settings`/`_default_conditions`/`_picker_title_suffix`
(Rule #5 — one shared body, not five near-identical panels).

**Stop** (GUI rework Phase 14) mirrors `AgentPanel.btn_stop`'s
availability styling and calls `PainterGui._stop_tool` — a "smart"
stop: the worker finishes the in-flight image then halts; once it
confirms the halt, `PainterGui` closes this tool's dashboard panel and
clears its JobTemp, returning to the Main Menu if that was the last
active job. This is a deliberate divergence from a site's own Stop
(which leaves its panel up for review) — a quick, disk-based tool run
has nothing left worth reviewing once stopped.

## Connections

### Uses
- [Layout Constants](layout.md) — `DENSE_COL_GAP_PX`,
  `DENSE_COL_WRAP_PX`, `SETTINGS_GLYPH_COLLAPSED`,
  `SETTINGS_GLYPH_EXPANDED`
- [Shared Filter Framework](../../../painter/__about/filters.md) —
  `filters.FilterCondition`, `filters.condition_to_dict`
  (`get_conditions()`/`get_settings()`)
- [FilterEditor](../../__about/filter_editor.md) — the embedded stacked filter
  widget itself
- [The Theme Engine](../../__about/theme.md) — `THEME_TOPLEVELS`,
  `smooth_transition` (the Advanced-reveal animation)
- [Themed Widget Toolkit](../../__about/widgets.md) — `rounded_button`,
  `style_action_button`
- [Icon Loading + Switch Art](../../__about/icons.md) — `icon()` (the tool's
  logo, keyed by `JOB_LOGO[self.slot]`)
- [Config (subfolder)](../../../painter/config/___config.md) —
  `JOB_LABEL`, `JOB_LOGO`, `iter_images`, `selection_base_and_rels`,
  `theme_pair`

### Used by
- [BG Settings Panel](bg.md), [Geometry Settings Panels](geometry.md),
  [Image Checker Settings Panel](image_checker.md) — every concrete
  panel subclasses `ToolSettingsPanel`
- [Tool Jobs Mixin](../../__about/app_tools.md) — drives the panel surface via
  `resolve_input()`/`get_conditions()`/`build_func()`/
  `set_run_state()`/`set_paused()`

## Classes

### ToolSettingsPanel
See Purpose above. Class attributes `SLOT: str = ""` (subclass sets
this to a `JOB_ORDER` tool kind) and `HAS_ADVANCED: bool = True`
(subclass sets `False` to skip building the Advanced collapsible
entirely — a dead affordance otherwise, per Rule #16).

#### Key methods
- `resolve_input() -> tuple[Path, list[Path]]` — raises `ValueError`
  when nothing is picked yet; folder mode re-scans live via
  `iter_images`, files mode replays the exact picked list based via
  `selection_base_and_rels`.
- `get_conditions()` / `_default_conditions()` — the embedded filter's
  live conditions and its subclass-seeded default (base: empty).
- `_build_extra` / `_build_advanced` / `_build_footer` — subclass
  hooks for always-visible primary controls, the Advanced gear's body,
  and a short note above the button row; all base no-ops.
- `build_func()` — subclass hook, raises `NotImplementedError` in the
  base; returns a `(path, log) -> str` callable closing over this
  run's Advanced/extra overrides.
- `set_run_state(running)` / `set_paused(is_paused)` — mirror
  `AgentPanel`'s own run-state styling.
- `get_settings()` / `apply_settings(stored, conditions=...)` — the
  settings round-trip; `_apply_advanced_settings` always runs
  regardless of `HAS_ADVANCED` since it also carries a subclass's
  always-visible extra fields (e.g. Upscale's min-side, Aspect's
  target ratio).
