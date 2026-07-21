# Build Mixin

**Script:** [Build Mixin (script)](app_build.py)

## Purpose
`BuildMixin` — the first of `PainterGui`'s six mixins (root Rule #20
god-file refactor, step 7/8 — a sixth mixin, `CheckerFixerMixin`, was
split out of `SiteJobsMixin` in step 8/8; see [GUI (folder)](___gui.md)
and [App (composition)](app.md)). The ONLY mixin that defines
`__init__` — every attribute the other five mixins read (`self.agents`, `self.
_tool_panels`, `self._workers`, `self._job_temps`, `self._view`,
`self._collapsed`, ...) is set here, once, at construction. Also owns
the `_build_*` widget-construction helpers it calls from `__init__`
(`_build_queue`/`_build_options`/`_build_toolbar`/`_build_compact`/
`_build_views`), the global font-zoom bindings (`_bind_zoom`/
`_zoom_wheel`/`_zoom_key`/`_zoom_step`) and wheel routing
(`_bind_wheel_routing`/`_inner_wheel`), `_relayout_agents` (the
per-site visibility reconciler `_build_compact` wires onto every
`AgentPanel.visible_var`), and the drag-resize event-buffering watcher
(`_on_root_configure`/`_resize_settled`/`_clamp_geometry`) bound at the
tail of `__init__`. A window maximize/restore is tracked in
`_on_root_configure` for bookkeeping ONLY (owner 2026-07-21 perf fix) —
it is deliberately NOT wrapped in `smooth_transition` any more (it was,
2026-07-20 through 2026-07-21): a real-window repro proved the cover
breaks the OS-level transition itself (the window gets stuck at its
old size on maximize, or renders a corrupted frame on restore) while
Tk's own `state()`/`winfo_*` insist the change already happened. See
`_on_root_configure`'s own docstring for the full mechanism and why the
OS/DWM's native animation needs no help from us.

Owns the window-sizing/collapse-glyph constants every other mixin that
touches the same widgets needs: `WINDOW_MIN_W`/`WINDOW_MIN_H`/
`WINDOW_SCREEN_MARGIN_PX`/`COMPACT_CLUSTER_GAP_PX` (used only here) and
`COLLAPSE_GLYPH_EXPANDED`/`COLLAPSE_GLYPH_COLLAPSED` (also read by
`ViewMixin._set_collapsed` — imported from this module rather than
duplicated, Rule #5).

## Connections

### Uses
- [Painter (folder)](../painter/___painter.md) — `config`
  (`DEFAULT_OUT_DIR`, `JOB_ORDER`, `JOB_TOOL_KINDS`, `RESIZE_SETTLE_MS`,
  `SITES`, `THEMES`); `jobtemp` (`JobTemp`, `clear_all`); `settings`
  (`load_settings`)
- [Agent Panel](agent_panel.md) — `AgentPanel` (one per site)
- [API Panel](api_panel.md) — `ApiImageGenPanel`
- [Dashboard Job Panel Base + Site Panel](dash_panels.md) — `DashPanel`,
  `JobPanel`
- [Pure Logic (script)](logic.md) — `_visible_agent_columns`
- [Main Menu + Icon Bar](menu.md) — `IconBar`, `MainMenu`
- [ScrollFrame (script)](scroll.md) — `ScrollFrame`, `WHEEL_DELTA_UNIT`
- [DayNightSwitch (script)](switch.md) — `DayNightSwitch`
- [Themed Widget Toolkit](widgets.md) — `rounded_button`/`rounded_entry`/
  `set_font_base`/`tk_font`, plus the live `widgets.FONT_BASE` global
  (module-attribute access, never a frozen `from` import — same reason
  as `gui/theme.py`'s own read, see [GUI (folder)](___gui.md))
- [Tool + AI-Checker Dashboard Panels + Grid](tool_dash.md) —
  `AiCheckPanel`, `DashGrid`, `ToolPanel`
- [Standalone-Tool Settings Panels](tool_panels.md) — the base +
  five concrete panels
- [The Theme Engine](theme.md) — `apply_theme`, `register_painter_day`,
  `skin_listbox`, `skin_text` (NOT `smooth_transition` — removed
  2026-07-21 perf fix, see Design Decisions)

### Used by
- [App (composition)](app.md) — `PainterGui(BuildMixin, ...)`
- [View Mixin](app_views.md) — reads `COLLAPSE_GLYPH_EXPANDED`/
  `COLLAPSE_GLYPH_COLLAPSED`

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
  gear/Advanced section) where no native transition exists.
