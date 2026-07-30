# Agent Panel

**Script:** [Agent Panel (script)](agent_panel.py)

## Purpose
`AgentPanel` — one site's (ChatGPT / Gemini) OWN control panel.
UI-SKETCH rework (owner 2026-07-29): THREE GROUPS, each switch that
owns fine-tune carrying its own indented `ExpandableSwitch`
sub-panel (turning ON auto-expands, the caret folds, OFF hides):

- **Pipeline** — BG removal (mode auto/white/black/color + the color
  wheel, tolerance %, reach edge/all — `bg_params()` feeds
  `remove_background` directly), Crop, Force aspect ratio (W:H + the
  two-way `AspectRatioCanvas`), Upscale (min-side + the embedded
  `FilterEditor` gate), keep-every-step.
- **Run behavior** — Report, Safer retry, Continue nudge; AI checker
  (prompt-match toggle + the Fixer AI + its api/website mode); the
  Pacing section (pause range, action delay, F2 on-degrade).
- **Prompt** — Background (with the F7 custom color wheel + swatch),
  Style, New chat, the F7 helper toggles.

The old global Settings gear (and its `settings_collapsed` state) is
GONE. The narrow view stacks the groups; the dense (sole/shared F4c)
editor grids them side by side. Its own Start/Pause/Stop closes the
panel. Split out of `gui/__init__.py` (root Rule #20 god-file
refactor, step 4/8).

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
- [Theme (script)](theme.py) — `THEME_TOPLEVELS` (the embedded
  `AspectRatioCanvas` repaints on every live Day/Night flip)
- [ScrollFrame](scroll.md) — indirectly, via the optional
  `on_layout_change` constructor callback: `PainterGui` wires it to the
  outer fill_height `ScrollFrame`'s own `refresh()` (owner 2026-07-21
  perf fix, replacing an old perpetual self-heal poll) — every
  `ExpandableSwitch`/`ExpandableSection` in the panel calls it right
  after its sub-panel is packed/forgotten. Defaults to a no-op so
  every headless `AgentPanel` in the test suite still works
  unchanged.
- [Themed Widget Toolkit](widgets.md) — `ExpandableSwitch`/
  `ExpandableSection`/`quiet_restore` (the per-switch fine-tune
  expanders), `Spinner`,
  `rounded_button`/`rounded_combo`/`rounded_entry`/`rounded_switch`,
  `style_action_button`, `tk_font`
- [Standalone-Tool Settings Panels](tool_panels.md) —
  `DENSE_COL_WRAP_PX`/`ASPECT_DIALOG_ENTRY_W` (layout constants every
  control-panel family shares — imported from THERE, not
  `gui/__init__.py`, to avoid a circular import; see that module's
  own docstring)

### Used by
- [GUI (folder)](___gui.md) — `__init__.py` re-exports `AgentPanel`
- `PainterGui` (still in `gui/__init__.py`) — builds one `AgentPanel`
  per site (`self.agents["chatgpt"]`/`self.agents["gemini"]`), drives
  Start/Stop/Pause, the settings round-trip, and
  `build_compact()`/`build_visibility_toggle()`; `_relayout_agents`
  grids the panels STACKED in the setup screen's left settings
  column

## Classes

### AgentPanel
One site's full control surface — see the Purpose section above. The
three groups are ONE vertical stack (`_stack_groups`): the panel
lives in the setup screen's LEFT settings column, whose width is the
column's, never the window's. (The pre-sketch responsive
`set_dense_columns` mode — three groups abreast while this was the
sole visible panel — is deleted: measured at 1322 px it pushed the
right-hand collections/output/Select column clean off a default-sized
window.)

`apply_settings` runs the whole round-trip under
`widgets.quiet_restore`, so a restored-ON switch never auto-expands
its fine-tune and the panel always opens compact; `_expanders()` is
the ONE list of switches that own a sub-panel (BG removal, Force
aspect ratio, Upscale, AI checker).

## Design Decisions
See [GUI (folder)](___gui.md)'s own "Design Decisions" section for
why the shared layout constants live in `gui.tool_panels` rather than
here or in `gui/__init__.py`.
