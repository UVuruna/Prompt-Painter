# Build Mixin

**Script:** [Build Mixin (script)](../app_build.py) ·
**Flow:** [diagram](../__flow/app_build.md)

## Purpose
`BuildMixin` — the first of `PainterGui`'s six mixins (root Rule #20
god-file refactor, step 7/8 — a sixth mixin, `CheckerFixerMixin`, was
split out of `SiteJobsMixin` in step 8/8; see [GUI (folder)](../___gui.md)
and [App (composition)](../app.py)). The ONLY mixin that defines
`__init__` — every attribute the other five mixins read (`self.agents`,
`self._tool_panels`, `self._workers`, `self._job_temps`, `self._view`,
`self._collapsed`, `self._pause_events`, `self._stop_events`, ...) is
set here, once, at construction.

Also owns the `_build_*` widget-construction helpers it calls from
`__init__` (`_build_queue`/`_build_inputs_tail`/`_build_options`/
`_build_toolbar`/`_build_compact`/`_build_views`), the global font-zoom
bindings (`_bind_zoom`/`_zoom_wheel`/`_zoom_key`/`_zoom_step`) and wheel
routing (`_bind_wheel_routing`/`_inner_wheel`), `_relayout_agents` (the
per-site visibility reconciler `_build_compact` wires onto every
`AgentPanel.visible_var`), the F4c shared both-sites mirror editor
(`_set_agent_mirror` — live var mirroring from the primary site to the
others while both are ticked and idle), `_apply_min_size` (owner
2026-08-03, UI rework tačka 1: the COMPUTED `root.minsize` — the pure
tile math from `gui.logic.menu_min_size` plus the chrome measured
here at the current font zoom, so the Main Menu's fixed 4×2 grid
always renders whole with no menu scrolling; `WINDOW_MIN_W`/`_H` stay
as absolute floors, only ever raised; re-run after every `_zoom_step`,
which also calls `IconBar.refresh_measure`), and the drag-resize
event-buffering watcher (`_on_root_configure`/`_resize_settled`/
`_clamp_geometry`) bound at the tail of `__init__`.

The old pinned top-strip "Menu" button is GONE (owner 2026-08-03, UI
rework tačka 2) — IconBar's leftmost HOME icon button (`home.svg`) is
the single way back to the Main Menu.

A window maximize/restore is tracked in `_on_root_configure` for
bookkeeping ONLY (owner 2026-07-21 perf fix) — it is deliberately NOT
wrapped in `smooth_transition` any more (it was, 2026-07-20 through
2026-07-21): a real-window repro proved the cover breaks the OS-level
transition itself (the window gets stuck at its old size on maximize,
or renders a corrupted frame on restore) while Tk's own
`state()`/`winfo_*` insist the change already happened — see
`_on_root_configure`'s own docstring for the full mechanism and why the
OS/DWM's native animation needs no help from us. A continuous drag
(same window state, changing size) marks `_resize_active` and re-arms a
`RESIZE_SETTLE_MS` settle timer; while active, `SiteJobsMixin._drain_queue`
BUFFERS dashboard `__event__` messages into `_pending_events`, flushed
in order by `_resize_settled` once the drag stops — so a live run's
tree/label updates stop re-rendering per drag frame.

**The setup screen's two columns** (UI-SKETCH, owner 2026-07-29;
widths/heights owner 2026-08-03, UV tačka 3): `__init__` grids
`_controls_box`'s content as LEFT settings (the `Agents` labelframe —
the "Sites:" show/hide row + the per-site `AgentPanel`s, stacked by
`_relayout_agents`, each panel's own groups in a 2×2) and RIGHT input
(`_build_queue`'s Collections list + `_build_inputs_tail`'s Output
folder, `Select images…` and the `Prompt + Image` toggle) — the
columns split the WIDTH 50-50 (uniform + weight 1). The right column
splits its HEIGHT 50-50: Collections above, and the
`PromptImageSection` (`_pi_section`, faza 2 — see
[Prompt + Image Section](prompt_image.md)) gridded into the lower
half only while the mode is ON (`_toggle_prompt_image`/
`_apply_prompt_image_state`, restored once at startup).
`WINDOW_DEFAULT_W`/`WINDOW_DEFAULT_H` (1120×840, owner 2026-07-29
hotfix) are also what a maximized-close geometry falls back to on
restore (`_clamp_geometry`) — a stale full-screen `WxH` would
otherwise reopen the app huge.

Also builds, unpacked at construction (each shown only by
`ViewMixin._apply_running_layout`): the Main Menu (`MainMenu`) and
running-view `IconBar`, and the SIX persistent `_tool_panels` (BG/Crop/
Upscale/Aspect's `ToolSettingsPanel` family, the AI checker's
`ImageCheckerSettingsPanel`, and API Image GEN's `ApiImageGenPanel` —
each wired to the shared `on_stop=self._stop_tool` "smart stop"
handler except API Image GEN, which uses `on_stop=self._stop_site`
since its worker lives in `self._running`/`self._workers`, not
`self._tool_workers`).

Owns the window-sizing/collapse-glyph constants every other mixin that
touches the same widgets needs: `WINDOW_MIN_W`/`WINDOW_MIN_H`/
`WINDOW_SCREEN_MARGIN_PX`/`WINDOW_DEFAULT_W`/`WINDOW_DEFAULT_H`/
`COMPACT_CLUSTER_GAP_PX` (used only here) and
`COLLAPSE_GLYPH_EXPANDED`/`COLLAPSE_GLYPH_COLLAPSED` (also read by
`ViewMixin._set_collapsed` — imported from this module rather than
duplicated, Rule #5).

## Connections

### Uses
- [Painter (folder)](../../painter/___painter.md) — `config`
  (`DEFAULT_OUT_DIR`, `JOB_ORDER`, `JOB_TOOL_KINDS`, `RESIZE_SETTLE_MS`,
  `SITES`, `THEMES`); `jobtemp` (`JobTemp`, `clear_all`); `settings`
  (`load_settings`)
- [Agent Panel](agent_panel.md) — `AgentPanel` (one per site)
- [API Panel](api_panel.md) — `ApiImageGenPanel`
- [Dashboard Job Panel Base + Site Panel](dash_panels.md) — `DashPanel`,
  `JobPanel`
- [Pure Logic](logic.md) — `_visible_agent_slots`
- [Main Menu + Icon Bar](menu.md) — `IconBar`, `MainMenu`
- [ScrollFrame](scroll.md) — `ScrollFrame`, `WHEEL_DELTA_UNIT`
- [DayNightSwitch](switch.md) — `DayNightSwitch`
- [Widgets](widgets.md) — `rounded_button`/`rounded_entry`/
  `set_font_base`/`tk_font`, plus the live `widgets.FONT_BASE` global
  (module-attribute access, never a frozen `from` import — same reason
  as [The Theme Engine](theme.md)'s own read)
- [Tool + AI-Checker Dashboard Panels + Grid](tool_dash.md) —
  `AiCheckPanel`, `DashGrid`, `ToolPanel`
- [Tool Panels (subfolder)](../tool_panels/___tool_panels.md) — the base +
  five concrete panels
- [The Theme Engine](theme.md) — `apply_theme`, `register_painter_day`,
  `skin_listbox`, `skin_text` (NOT `smooth_transition` — removed
  2026-07-21 perf fix, see Design Decisions)

### Used by
- [App (composition)](../app.py) — `PainterGui(BuildMixin, ...)`
- [View Mixin](app_views.md) — reads `COLLAPSE_GLYPH_EXPANDED`/
  `COLLAPSE_GLYPH_COLLAPSED`

## Classes

### BuildMixin
`PainterGui`'s constructor and every `_build_*` widget-construction
helper. Key attributes it seeds: `self.agents` (site key → `AgentPanel`),
`self._tool_panels` (tile id → settings panel), `self.panels` (job kind →
dashboard `JobPanel`), `self._workers`/`self._tool_workers` (running
threads), `self._stop_events`/`self._pause_events` (per-kind
`threading.Event`s), `self._job_temps` (per-kind `JobTemp`), `self._view`/
`self._inline_kind` (the view-state-machine seeds `ViewMixin` reads),
`self._cooldowns` (F2 persisted quota-reset info), `self._agent_mirror_on`
(F4c shared-editor flag). Key methods: `_build_queue`, `_build_options`,
`_build_toolbar`, `_build_compact`, `_build_views`, `_relayout_agents`,
`_set_agent_mirror`, `_on_root_configure`, `_resize_settled`,
`_clamp_geometry`, `_bind_zoom`, `_bind_wheel_routing`.

## Design Decisions
- **Only `BuildMixin` defines `__init__`.** Every other mixin's methods
  run on the SAME instance, via `self.` — moving the constructor
  anywhere else would mean two mixins both claiming to initialize the
  object, which the Python MRO does not support cleanly (Rule #5, one
  source of truth for construction).
- **The maximize/restore/drag-resize watcher stayed here rather than
  moving to `ViewMixin`.** It is armed once, at the tail of `__init__`,
  and its job (buffer dashboard events mid-drag; track window state) is
  about the ROOT WINDOW itself, not about which app view is showing —
  grouping it with the constructor that seeds its state
  (`self._win_state`/`self._win_size`/`self._resize_active`) keeps that
  state and its one reader together (Rule #5).
- **Maximize/restore is NOT covered by `smooth_transition` (owner
  2026-07-21 perf fix, reverting owner 2026-07-20's own addition of
  it).** The owner reported "lag + a BUG when I click MAXIMIZE"; a real
  Windows repro (screenshots, ImageGrab) proved the cover itself was the
  bug — creating the borderless topmost overlay Toplevel and force-
  painting it while the WM is mid-transition interrupts the actual
  resize/repaint, so the real window stays stuck at its OLD size
  (maximize) or renders a corrupted frame (restore) even though Tk's own
  `state()`/`winfo_width`/`winfo_height` already report the change. A
  bare `ttkbootstrap.Window` with none of this code maximizes cleanly;
  patching out ONLY the `smooth_transition` call (keeping everything
  else — ScrollFrame's own settle-debounced re-fit included) also
  maximizes/restores cleanly. The OS/DWM already animates the state
  change smoothly on its own; the cover was never needed here, only for
  our OWN Tk-level jumps (theme flip, Controls collapse, a Settings
  gear/Advanced section) where no native transition exists. NOTE for
  readers of the legacy `gui.md`: that pre-split doc still describes
  maximize/restore as covered by `smooth_transition` — that description
  is now FALSE; this file (and [The Theme Engine](theme.md)) are the
  current, correct account.
- **F4c's live variable mirroring copies values, never the FilterEditor
  condition stack** (that is not a `tk.Variable`) — a Start-both instead
  copies the whole upscale-gate stack explicitly at click time (see
  [Site Jobs Mixin](app_jobs.md)'s `_start_site_clicked`).
