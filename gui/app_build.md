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
`AgentPanel.visible_var`), and the maximize/restore cover + drag-resize
event-buffering watcher (`_on_root_configure`/`_resize_settled`/
`_clamp_geometry`) bound at the tail of `__init__`.

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
  `skin_listbox`, `skin_text`, `smooth_transition`

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
  and its job (cover a discrete window-state jump, buffer dashboard
  events mid-drag) is about the ROOT WINDOW itself, not about which
  app view is showing — grouping it with the constructor that seeds
  its state (`self._win_state`/`self._win_size`/`self._resize_active`)
  keeps that state and its one reader together (Rule #5).
