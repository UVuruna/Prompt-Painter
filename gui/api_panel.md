# API Panel

**Script:** [API Panel (script)](api_panel.py)

## Purpose
`ApiImageGenPanel` (the paid Gemini image-API job's own settings
panel, GUI rework Phase 19) and `ApiImageAdapter` (a `SiteDriver`-
shaped stand-in over that API so the "api_image" job reuses
`PainterGui._drive_site`/`painter.runner.run_sheet` COMPLETELY
UNCHANGED). Split out of `gui/__init__.py` (root Rule #20 god-file
refactor, step 4/8).

`ApiImageGenPanel` does NOT subclass `ToolSettingsPanel` — its input
is the SAME queued `.md` sheet Collections list Website GEN already
drives, never a folder of existing images — so it mirrors
`AgentPanel` instead (background/style dropdowns feeding the same
`prompt_suffix` machinery, the composable post-save switches, its own
Start/Pause/Stop), while its `get_settings()`/`apply_settings()` use
the SAME `(stored, conditions=...)` shape `ToolSettingsPanel` already
has, so it round-trips through the existing generic "tool_panels"
settings loop with no changes there.

`ApiImageAdapter` remaps a free-tier-exhausted 429
(`ai.PaidFeatureRequired`) to `driver.TerminalState` so the EXISTING
quota-stop plumbing handles it with no new code; `retry_after_s` is
always `None` (the free-tier-zero condition is permanent, unlike a
website quota with a known reset time).

## Connections

### Uses
- [Painter (folder)](../painter/___painter.md) — `filters` (the
  upscale gate's `FilterCondition`/`condition_to_dict`), `config`
  (background/style choices, the upscale/aspect defaults, the AI
  gate/probe message + model constants); `ai`/`driver.TerminalState`
  (imported LOCALLY inside `_probe_access`/`extract_image`, not at
  module level — mirrors the original file's own lazy-import
  convention for these two)
- [Aspect Ratio Canvas](aspect_canvas.md) — `AspectRatioCanvas` (the
  Force Aspect Ratio target editor)
- [Filter Editor](filter_editor.md) — `FilterEditor` (the upscale
  gate's embedded condition stack)
- [Icons](icons.md) — `icon()` (the job-logo header image)
- [Logic](logic.md) — `_upscale_params_from_side_and_filter`
  (`upscale_params()`)
- [Theme (script)](theme.py) — `THEME_TOPLEVELS` (the Force-Aspect
  canvas's Day/Night repaint registration)
- [Themed Widget Toolkit](widgets.md) — `Spinner`,
  `rounded_button`/`rounded_combo`/`rounded_entry`/`rounded_switch`,
  `style_action_button`, `tk_font`
- [Standalone-Tool Settings Panels](tool_panels.md) —
  `DENSE_COL_GAP_PX`/`DENSE_COL_WRAP_PX`/`ASPECT_DIALOG_ENTRY_W` (the
  two-column-dense layout constants every control-panel family
  shares — imported from THERE, not `gui/__init__.py`)

### Used by
- [GUI (folder)](___gui.md) — `__init__.py` re-exports
  `ApiImageGenPanel`/`ApiImageAdapter`
- `PainterGui` (still in `gui/__init__.py`) — builds ONE
  `ApiImageGenPanel` (`self._tool_panels["api_image_gen"]`) and drives
  it the SAME way as the `ToolSettingsPanel` family; `_drive_site`
  hands `ApiImageAdapter()` to `run_sheet` in place of a real
  `SiteDriver` for the "api_image" job

## Classes

### ApiImageGenPanel
See the Purpose section above — the paid-API job's settings panel,
including the "Check API access" gating probe (`_probe_access`/
`_arm_probe_poll`/`_poll_probe`/`_apply_probe_result`, its own
private queue+poll mirroring `_AiDialog`'s established pattern since
this is a `ttk.Frame`, not a `Toplevel`). `_arm_probe_poll` reaches
`AI_POLL_MS` through a deferred `import gui` — that one constant
stays defined in `gui/__init__.py` (also read there by `_AiDialog`,
which never moved), so a real-path import would be circular; see the
module docstring and `gui.theme._pkg()` for the same established
late-binding idiom.

### ApiImageAdapter
A `SiteDriver`-shaped stand-in — `attach`/`close`/`await_done` are
no-ops, `submit_prompt` only remembers the prompt text, and
`extract_image` makes the real `ai.generate_image` call.

## Design Decisions
See [GUI (folder)](___gui.md)'s own "Design Decisions" section for
why the shared two-column-dense layout constants live in
`gui.tool_panels` rather than here or in `gui/__init__.py`, and why
`AI_POLL_MS` alone stays behind in `gui/__init__.py` with a deferred-
import indirection instead.
