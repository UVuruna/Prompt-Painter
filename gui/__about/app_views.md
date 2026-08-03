# View Mixin

**Script:** [View Mixin (script)](../app_views.py) ·
**Flow:** [diagram](../__flow/app_views.md)

## Purpose
`ViewMixin` — the second of `PainterGui`'s six mixins (root Rule #20
god-file refactor, step 7/8; see [GUI (folder)](../___gui.md) and
[App (composition)](../app.py)). Owns the three-way `_view` switch
(`"menu"` / `"main"` / `"running"` — `_set_view`/`_go_view`), the Main
Menu tile router (`_select_tile`/`_tile_handler`, shared with the
running view's `IconBar` via `_click_icon_bar_tile`), the running-view
layout reconciler (`_apply_running_layout` — decides whether
`_controls_box` or one `ToolSettingsPanel` shows beneath the
`IconBar`, or NEITHER), the "which jobs are active" queries
(`_active_kinds`/`_active_tile_ids`/`_sync_running_state`), the Menu
affordance's gate (`_request_menu` — refuses to leave "running" while
any job is still live), a standalone tool's persistent settings-panel
toggle (`_open_tool_panel`), the controls/compact packer
(`_set_collapsed` — its "Controls" toggle button was removed,
owner 2026-08-03), and the F4e dashboard
grid/slider display-mode toggle (`_toggle_dash_mode`).

**The view-transition rules live in one pure, Tk-free function**,
[Pure Logic](logic.md)'s `_next_view(current, active_count,
menu_requested=False)`: ANY active job forces `"running"`; it then
STAYS `"running"` through every Stop, all the way down to zero active
jobs — closing the LAST job never auto-navigates by itself; `"menu"`
is reachable again ONLY on an explicit Menu click, and ONLY once
`active_count == 0` (a click while anything is active is a refused
no-op with a status-bar hint).

**Running view default is the DASHBOARD ALONE** (owner 2026-07-29,
current behavior — supersedes the legacy `gui.md`'s account of Website
GEN's controls auto-showing after Start): `_apply_running_layout`
packs the `IconBar` and, beneath it, EXACTLY the surface named by
`self._inline_kind` — `None` after a fresh Start (nothing extra packs,
just the Dashboard/Log notebook), `"website_gen"` for the shared
`_controls_box` (both `AgentPanel`s + the Collections queue), or one of
the six `_tool_panels` keys. The site/tool settings return only on an
explicit IconBar icon click (`_click_icon_bar_tile`) or a Pause (see
[Site Jobs Mixin](app_jobs.md)'s `_toggle_pause_job` reveal).

**F4b (owner 2026-07-29): the icon strip also shows on the "main"
setup screen** — above the settings, its leftmost HOME icon button
(owner 2026-08-03 — the old text "Menu" buttons, both IconBar's and
the pinned top-strip one, are gone) serving as the one way back to
the Main Menu. A HOTFIX the same day (slika 2) makes
entering "main" always expand the full controls — a persisted
collapsed state used to leave only the thin compact strip on the setup
screen (no visible settings, no way to start); another hotfix (slika
1) keeps the "menu" screen's top strip clean. As of owner
2026-08-03 the strip holds ONLY the title + theme switch on every
view — `Check` moved down beside "Select images…" in each
[Collections Column](collections_column.md) and the "Controls"
toggle was deleted outright, leaving the grid/slider button as the
one thing `_set_view` still packs or unpacks (dashboard on screen).

## Connections

### Uses
- [Painter (folder)](../../painter/___painter.md) — `config`
  (`TILE_JOB_KINDS`, `DASH_MODE_GRID`, `DASH_MODE_SLIDER`)
- [Build Mixin](app_build.md) — `COLLAPSE_GLYPH_EXPANDED`/
  `COLLAPSE_GLYPH_COLLAPSED`
- [Pure Logic](logic.md) — `_next_view`
- [The Theme Engine](theme.md) — `smooth_transition` (every view/
  collapse swap runs behind the shared snapshot-cover fade)

### Used by
- [App (composition)](../app.py) — `PainterGui(..., ViewMixin, ...)`
- [Site Jobs Mixin](app_jobs.md) — `_start_site`/`_start_api_image`/
  `_stop_site`/`_dispatch` call `_sync_running_state`;
  `_toggle_pause_job`'s own inline-panel reveal calls
  `_apply_running_layout`
- [Tool Jobs Mixin](app_tools.md) — `_start_tool_from_panel`/
  `_launch_tool_worker`/`_start_ai_check` call `_apply_running_layout`/
  `_sync_running_state`

## Classes

### ViewMixin
No `__init__` — every attribute it reads (`self._view`,
`self._controls_box`, `self._compact_box`, `self._tool_panels`,
`self._inline_kind`, `self._icon_bar`, ...) is set by
`BuildMixin.__init__`. Key
methods: `_set_view`/`_go_view` (the animated view swap),
`_select_tile`/`_tile_handler`/`_click_icon_bar_tile` (tile routing —
one shared mapping for both the Main Menu and the running IconBar),
`_apply_running_layout`, `_open_tool_panel`, `_active_kinds`/
`_active_tile_ids`/`_sync_running_state`, `_request_menu`,
`_set_collapsed`, `_toggle_dash_mode`.

## Design Decisions
- **No `__init__`, by design (Rule #5).** `BuildMixin` is the single
  place every mixin's shared state is seeded; `ViewMixin` only ever
  reads/mutates it through `self.`, so there is exactly one
  constructor to reason about across all six mixins.
- **`_on_root_configure`/`_resize_settled`/`_clamp_geometry` stayed in
  `BuildMixin`, not here**, even though they are arguably "view"
  concerns — see [Build Mixin](app_build.md)'s own Design Decisions for
  why they travel with the constructor that seeds their state instead.
- **`_view` is deliberately orthogonal to `_collapsed`.** The pair
  stayed independent through the Main-Menu rework — a design that
  traded a tidier `_collapsed`→`_view` rename for zero regression
  risk on its riskiest phase. The user-facing "Controls" toggle is
  gone (owner 2026-08-03), but `_collapsed` still selects which of
  controls_box/compact_box is packed, so the orthogonality holds.
- **`_select_tile`/`_click_icon_bar_tile` special-case the six
  standalone-job tiles to skip straight to `_open_tool_panel`,
  bypassing `_go_view("main")`.** Routing them through "main" first,
  like every other tile, would reveal-then-immediately-hide the old
  controls box behind a wasted extra fade — `_open_tool_panel`
  transitions straight to "running" itself.
