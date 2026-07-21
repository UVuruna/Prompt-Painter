# View Mixin

**Script:** [View Mixin (script)](app_views.py)

## Purpose
`ViewMixin` — the second of `PainterGui`'s six mixins (root Rule #20
god-file refactor, step 7/8 — a sixth mixin, `CheckerFixerMixin`, was
split out of `SiteJobsMixin` in step 8/8; see [GUI (folder)](___gui.md) and
[App (composition)](app.md)). Owns the three-way `_view` switch (menu /
main / running — `_set_view`/`_go_view`), the Main Menu tile router
(`_select_tile`/`_tile_handler`, shared with the running view's
`IconBar` via `_click_icon_bar_tile`), the running-view layout
reconciler (`_apply_running_layout`, which decides whether
`_controls_box` or one `ToolSettingsPanel` shows beneath the
`IconBar`), the "which jobs are active" queries (`_active_kinds`/
`_active_tile_ids`/`_sync_running_state`), the Menu-affordance gate
(`_request_menu` — refuses to leave "running" while any job is still
live), a standalone tool's persistent settings-panel toggle
(`_open_tool_panel`), and the Controls collapse toggle
(`_set_collapsed`/`_toggle_collapsed`).

No `__init__` here — every attribute it reads (`self._view`, `self.
_controls_box`, `self._compact_box`, `self._tool_panels`, `self.
_inline_kind`, `self._icon_bar`, `self._menu_btn`, `self.
_collapse_btn`, ...) is set by `BuildMixin.__init__`.

## Connections

### Uses
- [Painter (folder)](../painter/___painter.md) — `config`
  (`TILE_JOB_KINDS`)
- [Build Mixin](app_build.md) — `COLLAPSE_GLYPH_EXPANDED`/
  `COLLAPSE_GLYPH_COLLAPSED`
- [Pure Logic (script)](logic.md) — `_next_view`
- [The Theme Engine](theme.md) — `smooth_transition` (every view/
  collapse swap runs behind the shared snapshot-cover fade)

### Used by
- [App (composition)](app.md) — `PainterGui(..., ViewMixin, ...)`
- [Site Jobs Mixin](app_jobs.md) — `_start_site`/`_start_api_image`/
  `_stop_site`/`_dispatch` call `_sync_running_state`/
  `_toggle_pause_job`'s own inline-panel reveal reads `_apply_running_
  layout`
- [Tool Jobs Mixin](app_tools.md) — `_start_tool_from_panel`/
  `_launch_tool_worker`/`_start_ai_check` call `_apply_running_layout`/
  `_sync_running_state`

## Design Decisions
- **No `__init__`, by design (Rule #5).** `BuildMixin` is the single
  place every mixin's shared state is seeded; `ViewMixin` only ever
  reads/mutates it through `self.`, so there is exactly one
  constructor to reason about across all six mixins.
- **`_on_root_configure`/`_resize_settled`/`_clamp_geometry` stayed in
  `BuildMixin`, not here**, even though they are arguably "view"
  concerns — see [Build Mixin](app_build.md)'s own Design Decisions for
  why they travel with the constructor that seeds their state instead.
