# Agent Panel

**Script:** [Agent Panel (script)](../agent_panel.py) ·
**Flow:** [diagram](../__flow/agent_panel.md)

## Purpose
`AgentPanel` — one site's (ChatGPT / Gemini) OWN control panel.
UI-SKETCH rework (owner 2026-07-29): the settings are THREE GROUPS,
each switch that owns fine-tune carrying its own indented
`ExpandableSwitch` sub-panel (turning ON auto-expands once, the caret
folds/unfolds by hand, OFF hides it entirely):

- **Pipeline** — BG removal (mode auto/white/black/color + the color
  wheel, tolerance %, reach edge/all — `bg_params()` feeds
  `remove_background` directly), Crop, Force aspect ratio (W:H + the
  two-way `AspectRatioCanvas`), Upscale (min-side + the embedded
  `FilterEditor` gate, pre-seeded with one Aspect-range [0.9, 1.1] IF
  condition), and a "keep every pipeline step" toggle.
- **Run behavior** — Report, Safer retry, Continue nudge; the AI
  checker (its own F6 prompt-match toggle + the Fixer AI living
  INSIDE the checker switch's own expander, reachable only while the
  checker itself is on, plus its api/website mode).
- **Pacing** — its OWN group, ALWAYS OPEN (owner 2026-08-03, UV
  tačka 3 "Pacing uvek otvoren" — the old folded ExpandableSection
  inside Run behavior is gone): pause range, action-delay range, the
  F2 on-degrade choice, in plain sight before every Start.
- **Prompt** — Background (with the F7 custom-colour wheel + swatch),
  Style, New chat mode, the F7 prompt-helper toggles.

The old global Settings gear (and its `settings_collapsed` state) is
GONE — everything it held now lives under its owning switch (or the
always-open Pacing group). The FOUR groups grid as the owner's 2×2
(`_stack_groups`, owner 2026-08-03): Pipeline | Run behavior above,
Pacing | Prompt below, both columns sharing the width evenly — the
setup screen's LEFT settings column is a true half of the window now
(the 50-50 split, same decree), wide enough for two group columns
where the 2026-07-29 single stack was not. Inside the Prompt group
the F7 helper switches WRAP — label on its own line, switches two per
grid row (owner 2026-08-03: "prelomi u 2 reda ako treba" — three on
one line ran off the half-width cell and the last was invisible); a
fourth helper simply opens a third row. Its own Start/Pause/Stop
drives that one site's run. Split out of `gui/__init__.py` (root Rule
#20 god-file refactor, step 4/8).

**Backgrounds and the F7 helper laws.** Background dropdown
(transparent/white/none/custom) preselects to the site's own default
(ChatGPT transparent, Gemini white); a "custom" pick opens a themed
colour wheel and shows a click-to-reopen swatch. The pre-F7 "always
on" per-site laws — Gemini's no-reflections law, ChatGPT's anti-grain
law — are now `helper_vars` toggles (`HELPER_CHOICES`:
`no_mirror`/`no_empty_space`/`no_grainy`, `painter/config/ai.py`),
each site starting with its OWN pre-F7 law ON by default
(`HELPER_DEFAULTS`) so the shipped suffix stays byte-identical; every
other combination is now the owner's switch, not baked-in code. The
Style dropdown's clause (one of `config.STYLES`, default `"None"` =
nothing appended) is appended at the very END of that site's prompt
suffix, after the background rule and the toggled helper laws.

**Post-save pipeline defaults.** BG removal/Crop/Upscale default ON,
Force Aspect Ratio defaults OFF — the pipeline always runs the fixed
order BG → Crop → Aspect(force) → Upscale regardless of which order
the switches were ticked in (`gui.logic._run_pipeline_steps`).
Upscale's gate is ONE min-side `Spinner` + the embedded `FilterEditor`
(`panel.upscale_params()`/`upscale_conditions()` resolve it); Force
Aspect Ratio is a switch + target W:H two-way synced with the embedded
`AspectRatioCanvas` (`panel.force_aspect_ratio()` returns the
validated `(w, h)` int pair, raising `ValueError` on Start's own
validation).

**The AI checker's F6 prompt-match toggle.** `checker_var` (default
OFF — a paced Gemini vision call PER SAVED IMAGE is an explicit
opt-in cost, unlike Report/Safer retry/Continue nudge beside it) gates
a background check per saved image; its own `checker_prompt_var`
(default ON) tells the checker thread to ALSO resolve the item's own
sheet PROMPT (scanning the queued sheets, caching each parse by
mtime — `CheckerFixerMixin._prompt_for_drop`) and pass it into the
vision call, so the model judges content match on top of the banal-
defects check. The Fixer AI (`fixer_var` default OFF, `fixer_mode_var`
api/website default api) is a cost layered on TOP of the checker's own
cost.

**Compact cluster + visibility toggle.** `build_compact()` builds a
thin `[logo] Name [Start][Stop]` cluster for the collapsed-controls
strip, appending its own Start/Stop to `_button_pairs` so the compact
and full-panel buttons always share the same filled/outline
availability (`set_run_state` styles every registered pair).
`build_visibility_toggle()` builds this site's entry in the shared
"Sites:" row above both panels (`visible_var`, default True,
persisted) — `set_run_state` greys that toggle out while the site's
job is running or a quota auto-restart is pending (Stop/Pause live
only on this panel, so hiding it then would strand the job), and
forces `visible_var` back to True — logging why — whenever a HIDDEN
site goes live without a click (a quota auto-restart, an AI-check
resend), so the control and what is on screen can never silently
disagree.

## Connections

### Uses
- [Painter (folder)](../../painter/___painter.md) — `filters` (the
  upscale gate's `FilterCondition`/`condition_to_dict`), `config`
  (every per-agent tunable: `SITES`, the background/style/new-chat/
  degrade/fixer-mode/helper choice lists, the BG mode/reach labels,
  the upscale/aspect defaults, `TIMING`)
- [Aspect Ratio Canvas](aspect_canvas.md) — `AspectRatioCanvas` (the
  Force Aspect Ratio block)
- [Filter Editor](filter_editor.md) — `FilterEditor` (the upscale
  gate's embedded condition stack)
- [Icons](icons.md) — `icon()` (the site-logo header images: this
  panel's own, plus one per OTHER site — `set_shared_header`
  packs them all while the both-sites shared editor is active, so
  the header that NAMES two sites also SHOWS two logos, owner
  2026-08-03)
- [Pure Logic Helpers](logic.md) — `_upscale_params_from_side_and_filter`
  (`upscale_params()`)
- [Theme Engine](theme.md) — `THEME_TOPLEVELS` (the embedded
  `AspectRatioCanvas` repaints on every live Day/Night flip)
- [Themed Widget Toolkit](widgets.md) — `ExpandableSwitch`/
  `ExpandableSection`/`quiet_restore` (the per-switch fine-tune
  expanders), `Spinner`,
  `rounded_button`/`rounded_combo`/`rounded_entry`/`rounded_switch`,
  `style_action_button`, `tk_font`
- [Layout Constants](../tool_panels/__about/layout.md) —
  `DENSE_COL_WRAP_PX`/`ASPECT_DIALOG_ENTRY_W` (imported from the
  `gui.tool_panels` package leaf, not `gui/__init__.py`, to avoid a
  circular import — the ToolSettingsPanel family and `ApiImageGenPanel`
  share the exact same constants)

### Used by
- [GUI (folder)](../___gui.md) — `__init__.py` re-exports `AgentPanel`
- [Build Mixin](app_build.md) — `BuildMixin.__init__` builds one
  `AgentPanel` per site (`self.agents["chatgpt"]`/`self.agents["gemini"]`),
  wiring Start/Stop/Pause and `build_visibility_toggle()`;
  `_relayout_agents` grids the panels STACKED in the setup screen's
  left settings column
- [Site Jobs Mixin](app_jobs.md) — `_start_site_clicked`/`_stop_site`/
  `_toggle_pause_job` drive the panel's Start/Stop/Pause callbacks
- [Checker/Fixer Mixin](app_checker_fixer.md) — reads `checker_var`/
  `checker_prompt_var`/`fixer_var`/`fixer_mode_var` to decide whether
  and how to check/fix a saved image
- [Settings Mixin](app_settings.md) — the settings round-trip
  (`get_settings`/`apply_settings`, the `up_filter_conditions` migration)

## Classes

### AgentPanel
One site's full control surface — see the Purpose section above. The
three groups are ONE vertical stack (`_stack_groups`); `apply_settings`
runs the whole round-trip under `widgets.quiet_restore`, so a
restored-ON switch never auto-expands its fine-tune and the panel
always opens compact — `_expanders()` is the ONE list of switches that
own a sub-panel (BG removal, Force aspect ratio, Upscale, AI checker).

`apply_theme()` is registered in `THEME_TOPLEVELS` even though this
panel is not a `Toplevel` — it is build-once, live for the app's whole
life, exactly like a dashboard `JobPanel` — so a Day/Night flip
repaints the embedded `AspectRatioCanvas` (`redraw_theme()`) whenever
its fine-tune box happens to be expanded.

#### Key methods
- `bg_params()` — BG removal's per-agent kwargs for `remove_background`.
- `force_aspect_ratio()` / `upscale_params()` / `upscale_conditions()` /
  `pace_floats()` — read the fine-tune fields at Start; each raises
  `ValueError` on a bad number, propagating to the caller's validation.
- `helpers()` — this agent's toggled F7 prompt helpers, in
  `HELPER_CHOICES` order.
- `build_compact()` / `build_visibility_toggle()` — the collapsed-strip
  cluster and the "Sites:" row entry (see Purpose above).
- `set_run_state()` / `set_paused()` — button/toggle availability and
  the Pause↔Resume label.
- `get_settings()` / `apply_settings()` / `persist_vars()` — the
  settings round-trip; the upscale `FilterEditor`'s condition stack is
  read fresh every call (not a `tk.Variable`, so it has no per-keystroke
  save trace).
