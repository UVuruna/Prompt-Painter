# Standalone-Tool Settings Panels

**Script:** [Standalone-Tool Settings Panels (script)](tool_panels.py)

## Purpose
The persistent settings panel family for the four in-place tools
(BG removal / Crop / Upscale / Aspect ratio, GUI rework Phases 13–14)
plus the AI image checker's own panel (Phase 15): `ToolSettingsPanel`
(the shared base — input picker, embedded `FilterEditor`, an optional
Advanced collapsible, Start/Pause/Stop) and its five concrete
subclasses `BgSettingsPanel`/`CropSettingsPanel`/`UpscaleSettingsPanel`/
`AspectSettingsPanel`/`ImageCheckerSettingsPanel`. Split out of
`gui/__init__.py` (root Rule #20 god-file refactor, step 4/8) — a
leaf-ish module: depends only on `painter.*` and the already-split
`gui.aspect_canvas`/`gui.filter_editor`/`gui.icons`/`gui.logic`/
`gui.theme`/`gui.widgets` submodules, never on `gui/__init__.py`
itself.

Also owns the two-column-dense settings-panel layout constants
(`DENSE_COL_GAP_PX`/`DENSE_COL_WRAP_PX`, the Settings-gear caret
glyphs `SETTINGS_GLYPH_EXPANDED`/`SETTINGS_GLYPH_COLLAPSED`, and
`ASPECT_DIALOG_ENTRY_W`) — they used to sit as bare module constants
in `gui/__init__.py` right above `AgentPanel`, and all THREE control-
panel families (`AgentPanel`, this module's own family, and
`ApiImageGenPanel`) read them identically (root Rule #5). They live
HERE — not in `gui/__init__.py` — so `gui.agent_panel` and
`gui.api_panel` can import them by a real path (`from .tool_panels
import ...`) with no circular import back into the still-monolithic
`gui/__init__.py`.

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
- [Agent Panel](agent_panel.md) / [API Panel](api_panel.md) — both
  import this module's `DENSE_COL_GAP_PX`/`DENSE_COL_WRAP_PX`/
  `ASPECT_DIALOG_ENTRY_W` (`AgentPanel` also imports the Settings-gear
  glyphs)
- `PainterGui` (still in `gui/__init__.py`) — builds one instance of
  each subclass per tool tile, drives `resolve_input()`/
  `get_conditions()`/`build_func()`/`set_run_state()`/`set_paused()`/
  the settings round-trip

## Classes

### ToolSettingsPanel
Base: an input picker (**Folder…**/**Files…**), an optional always-
visible subclass block (`_build_extra`), the embedded `FilterEditor`,
an optional **Advanced** collapsible (`HAS_ADVANCED` — False for
Upscale/Aspect/the checker, which have no hidden engine knobs), an
optional footer note, and Start/Pause/Stop. Subclasses set `SLOT` and
contribute `_build_advanced`/`build_func`/`_advanced_settings`/
`_apply_advanced_settings`.

### BgSettingsPanel / CropSettingsPanel
BG removal's/Crop's knobs. BG's PRIMARY control is always visible
(`_build_extra`, owner 2026-07-28): a **Background** dropdown — Auto
(detect), Black, White, or **Custom colour** — plus, in Custom mode
only, the target hex (with a live swatch) and a `±X %` per-channel
tolerance spinner. Its Advanced collapsible keeps the three
safety-guard ceilings `remove_background` aborts past (black / white /
custom). Crop's Advanced holds the border-halo-cleanup toggle, safety
margin and ink-detection thresholds `crop_transparent` reads.

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

Stored keys: the MODE key (`BG_MODE_COLOR`), never the shown label, so
relabelling the dropdown cannot invalidate a saved `settings.json` (an
unknown stored mode keeps the current default). The guard keys carry a
`_pct` SUFFIX (`safety_black_pct`) because their UNIT changed — a file
written by the fraction build holds `"0.40"` under the old bare key,
which read as percent would be a 0.4 % guard that refuses every image;
the renamed key means such a file falls back to the correct defaults
instead of being silently misread (Rule #6 — no translating shim).

### UpscaleSettingsPanel / AspectSettingsPanel
No Advanced section — the min-side spinner (Upscale) / target-ratio
`AspectRatioCanvas` (Aspect) IS the panel's one primary control,
always visible via `_build_extra`.

### ImageCheckerSettingsPanel
The AI image checker's settings panel — no engine knobs, just the
base's own picker + an optional unseeded `FilterEditor` and an
informational footer (model, pacing, where flags persist). Its Start
bypasses `build_func`/`_launch_tool_worker` entirely, wired straight
to `PainterGui._start_ai_check` instead (a fundamentally different
worker shape — no JobTemp backup, since the run is read-only).

## Design Decisions
See [GUI (folder)](___gui.md)'s own "Design Decisions" section for
why the two-column-dense layout constants live in this module rather
than `gui/__init__.py` or `gui/agent_panel.py`.
