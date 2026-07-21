# Agent Panel

**Script:** [Agent Panel (script)](agent_panel.py)

## Purpose
`AgentPanel` — one site's (ChatGPT / Gemini) OWN control panel: the
background/style dropdowns, the three composable post-save switches
(BG removal / Crop / Upscale), Report, Safer retry, Continue nudge,
the parallel Checker/Fixer AI toggles, the Force Aspect Ratio block
(a live two-way-synced `AspectRatioCanvas`), the collapsible pause/
action-delay/upscale-gate fine-tune behind its own Settings gear, and
its own Start/Pause/Stop. Split out of `gui/__init__.py` (root
Rule #20 god-file refactor, step 4/8) — a single class, ~825 lines.

## Connections

### Uses
- [Painter (folder)](../painter/___painter.md) — `filters` (the
  upscale gate's `FilterCondition`/`condition_to_dict`), `config`
  (every per-agent tunable: `SITES`, the background/style/new-chat
  choice lists, the fixer mode choices, the upscale/aspect defaults)
- [Aspect Ratio Canvas](aspect_canvas.md) — `AspectRatioCanvas` (the
  Force Aspect Ratio block)
- [Filter Editor](filter_editor.md) — `FilterEditor` (the upscale
  gate's embedded condition stack)
- [Icons](icons.md) — `icon()` (the site-logo header image)
- [Logic](logic.md) — `_upscale_params_from_side_and_filter`
  (`upscale_params()`)
- [Theme (script)](theme.py) — `THEME_TOPLEVELS`, `smooth_transition`
  (the Settings-gear reveal animation)
- [Themed Widget Toolkit](widgets.md) — `Spinner`,
  `rounded_button`/`rounded_combo`/`rounded_entry`/`rounded_switch`,
  `style_action_button`, `tk_font`
- [Standalone-Tool Settings Panels](tool_panels.md) —
  `DENSE_COL_GAP_PX`/`DENSE_COL_WRAP_PX`/`ASPECT_DIALOG_ENTRY_W`/
  `SETTINGS_GLYPH_EXPANDED`/`SETTINGS_GLYPH_COLLAPSED` (the
  two-column-dense layout constants every control-panel family
  shares — imported from THERE, not `gui/__init__.py`, to avoid a
  circular import; see that module's own docstring)

### Used by
- [GUI (folder)](___gui.md) — `__init__.py` re-exports `AgentPanel`
- `PainterGui` (still in `gui/__init__.py`) — builds one `AgentPanel`
  per site (`self.agents["chatgpt"]`/`self.agents["gemini"]`), drives
  Start/Stop/Pause, the settings round-trip, and
  `set_dense_columns()`/`build_compact()`/`build_visibility_toggle()`
  for the responsive controls layout

## Classes

### AgentPanel
One site's full control surface — see the Purpose section above. Two
content layouts (`_apply_dense_columns`/`set_dense_columns`): the
narrow single-column stack while both sites share the row, and a
two-column-dense fill (switches left, dropdowns right) while this is
the SOLE visible panel — driven by `PainterGui._relayout_agents` off
the known visible-count state, never a `<Configure>` width probe.

## Design Decisions
See [GUI (folder)](___gui.md)'s own "Design Decisions" section for
why the shared two-column-dense layout constants live in
`gui.tool_panels` rather than here or in `gui/__init__.py`.
