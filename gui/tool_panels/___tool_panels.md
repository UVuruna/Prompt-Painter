# tool_panels/

The standalone in-place tools' persistent settings panels — the shared
`ToolSettingsPanel` chrome plus its concrete subclasses (BG removal /
Crop / Upscale / Aspect ratio) and the AI image checker's own panel.

Split by tool family into five submodules (was one 1,283-line
`tool_panels.py`, root Rule #20 god-file split, 2026-07-30).
`__init__.py` re-exports the full public API — the same pure-shell
shape [Config (subfolder)](../../painter/config/___config.md) and
[AI (subfolder)](../../painter/ai/___ai.md) already use — so every
existing `from .tool_panels import BgSettingsPanel` / `gui.
UpscaleSettingsPanel` call site kept working UNCHANGED.

## Files

### `layout.py` — Layout Constants
The metrics every settings-panel family shares: `DENSE_COL_GAP_PX`/
`DENSE_COL_WRAP_PX` (the two-column-dense fill, owner 2026-07-21),
`ASPECT_DIALOG_ENTRY_W` and the Advanced caret glyphs. A true leaf —
`gui.agent_panel` and `gui.api_panel` import it without pulling in a
single panel class, so no cycle is possible. See
[Layout Constants](layout.md).

### `base.py` — Base Tool Settings Panel
`ToolSettingsPanel` — the input picker, the shared `FilterEditor`
gate, the optional Advanced collapsible and the Start/Pause/Stop row
with its run-state styling. See
[Base Tool Settings Panel](base.md).

### `bg.py` — BG Settings Panel
`BgSettingsPanel` — the mode dropdown (auto / white / black / custom
colour with its wheel, live swatch and ±% tolerance), the reach
choice, and the three safety guards in Advanced. See
[BG Settings Panel](bg.md).

### `geometry.py` — Geometry Settings Panels
`CropSettingsPanel`, `UpscaleSettingsPanel`, `AspectSettingsPanel` —
the three panels that change an already-saved image's pixel GEOMETRY,
each a thin subclass. See [Geometry Settings Panels](geometry.md).

### `image_checker.py` — Image Checker Settings Panel
`ImageCheckerSettingsPanel` — the AI checker's own panel: the base
chrome, its instructions box, the optional prompt-sheet source (F6)
and the model/pacing footer. See
[Image Checker Settings Panel](image_checker.md).

## Connections

### Uses
- [Painter (folder)](../painter/___painter.md) — `filters` (the
  embedded `FilterEditor`'s condition model), `config` (every tunable
  the five panels expose), `postprocess`/`upscale`/`aspect` (imported
  LOCALLY inside each subclass's `build_func()`, not at module level)
- [Aspect Ratio Canvas](aspect_canvas.md) — `AspectRatioCanvas`
  (`AspectSettingsPanel`'s target-ratio editor)
- [Filter Editor](filter_editor.md) — `FilterEditor` (every panel's
  embedded "which images this run touches" stack)
- [Icons](icons.md) — `icon()` (the job-logo header image)
- [Logic](logic.md) — `_upscale_params_from_side_and_filter`
  (`UpscaleSettingsPanel.build_func`)
- [Theme (script)](theme.py) — `THEME_TOPLEVELS`, `smooth_transition`
  (the Advanced-gear reveal animation)
- [ScrollFrame](scroll.md) — indirectly, via the optional
  `on_layout_change` constructor callback: `PainterGui` wires it to the
  outer fill_height `ScrollFrame`'s own `refresh()` (owner 2026-07-21
  perf fix, replacing an old perpetual self-heal poll) — `_toggle_
  advanced` calls it right after `_apply_advanced_visibility`, inside
  the same `smooth_transition`-covered mutate. Defaults to a no-op so
  every headless panel in the test suite still works unchanged.
- [Themed Widget Toolkit](widgets.md) — `Spinner`, the numeric-field
  parsers (`_parse_fraction`/`_parse_nonneg_int`/`_parse_int_range`/
  `_parse_percent`), `rounded_button`/`rounded_combo`/`rounded_entry`/
  `rounded_switch`, `style_action_button`, `tk_font`
- [Background Remover](../painter/bg_remove.md) — `parse_hex_color`,
  `format_hex_color`, `tolerance_to_distance` (`BgSettingsPanel`
  validates the typed colour at Start and drives its live swatch and
  tolerance hint with them)

### Used by
- [GUI (folder)](___gui.md) — `__init__.py` re-exports
  `ToolSettingsPanel`/`BgSettingsPanel`/`CropSettingsPanel`/
  `UpscaleSettingsPanel`/`AspectSettingsPanel`/
  `ImageCheckerSettingsPanel`
- [Agent Panel](agent_panel.md) / [API Panel](api_panel.md) — import
  this module's layout constants (`ApiImageGenPanel` the full
  `DENSE_COL_GAP_PX`/`DENSE_COL_WRAP_PX`/`ASPECT_DIALOG_ENTRY_W` set,
  `AgentPanel` the wrap length + aspect entry width since its own
  groups always stack)
- `PainterGui` (still in `gui/__init__.py`) — builds one instance of
  each subclass per tool tile, drives `resolve_input()`/
  `get_conditions()`/`build_func()`/`set_run_state()`/`set_paused()`/
  the settings round-trip


## Design Decisions
**Why `layout.py` is its own leaf.** The constants used to sit in the
single `tool_panels.py` precisely so `gui.agent_panel`/`gui.api_panel`
could import them without touching `gui/__init__.py`. With the family
split into a package, importing them from the package `__init__` would
drag every panel class along; a constants-only leaf keeps the original
no-cycle guarantee AND makes the dependency honest.

**One module per tool FAMILY, not per class.** Crop / Upscale /
Aspect are ~80-130 lines each and always change together (the same
base hooks, the same "geometry of an existing image" job); three
separate files would be the over-fragmentation Rule #20 warns about.
BG is its own module because its colour/tolerance/reach block is a
third of the old file on its own.
