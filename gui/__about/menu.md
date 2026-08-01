# Main Menu + Icon Bar

**Script:** [Main Menu + Icon Bar (script)](../menu.py) ·
**Flow:** [diagram](../__flow/menu.md)

## Purpose
`MainMenu` and `IconBar`, pulled out of `gui/__init__.py` (root Rule
#20 god-file refactor, step 6/8; GUI rework Phases 10–11). `MainMenu`
is the startup landing screen — a responsive full-window grid of big
tiles, one per `config.MENU_TILES` functionality, that reflows its
column count (down to 1) as the window narrows so tiles never clip.
Each tile is built by ONE factory (`_make_tile`, Rule #5 — not eight
copy-pasted blocks): a rounded, accent-bordered card with a centred
icon+title+description, whose border WIDENS on hover — the one thing
that changes, deliberately, since widening a border needs no child
widget to update in lockstep the way a fill-colour hover would. A
disabled tile (`tile.enabled` False — the mechanism for a
not-yet-wired functionality) renders muted with no accent and binds no
hover/click at all; every `MenuTile` in `config.MENU_TILES` today has
`enabled=True` (the default), including `api_image_gen` since GUI
rework Phase 19 wired it up — the mechanism exists for a future
placeholder, it is simply unused right now.

`IconBar` is the compact top strip shown while a job is running — one
small button per tile plus a "Menu" button, reusing the SAME tile data
and factory pattern (not two copies): `set_active(active_ids)`
recolours every enabled tile — FILLED with its accent while any of its
`config.TILE_JOB_KINDS` is live, a quiet outline otherwise.

Neither class decides what picking a tile DOES — both only call back
into `PainterGui` (`_select_tile`/`_click_icon_bar_tile`).

## Connections

### Uses
- [Painter (folder)](../../painter/___painter.md) — `config`
  (`MENU_TILES` and its layout constants, `theme_pair`)
- [Icons](icons.md) — `icon` (a tile's picture)
- [Pure Logic Helpers](logic.md) — `MENU_TILE_CELL_MIN_PX`/
  `_menu_tile_columns` (the reflow math)
- [Themed Widget Toolkit](widgets.md) — `_style_icon_bar_button`/
  `ctk_font`/`rounded_button`

### Used by
- [GUI (folder)](../___gui.md) — `__init__.py` re-exports `MainMenu`/
  `IconBar` for external tests
- [Build Mixin](app_build.md) — `BuildMixin.__init__` builds ONE
  `MainMenu` (`on_select=self._select_tile`) and ONE `IconBar`
  (`on_select=self._select_tile`, `on_menu=...`)
- [View Mixin](app_views.md) — `_select_tile`/`_click_icon_bar_tile`
  (what picking a tile actually does) and `_icon_bar.set_active(...)`
  after every change to the running job set

## Classes

### MainMenu
The startup landing screen's responsive tile grid — see Purpose
above. Tiles are built ONCE in `__init__` (`self._tiles`); `_reflow`
only re-`grid()`s them at a new row/column and resets/reassigns
column-and-row weights on every `<Configure>` that actually changes
the column count (the change-guard in `_on_grid_configure` skips
every other resize).

### IconBar
The compact top strip shown while a job is running — see Purpose
above.

## Design Decisions
- **`_menu_tile_columns`/`MENU_TILE_CELL_MIN_PX` stayed in
  `gui.logic`, imported here rather than re-derived** — the reflow
  math is pure (no Tk) and `test_gui_running_view.py` already reaches
  it as `gui._menu_tile_columns`/`gui.MENU_TILE_CELL_MIN_PX`, both
  still re-exported unchanged from `gui/__init__.py`'s existing
  `.logic` import block.
- **`ICON_BAR_GAP_PX` moved here with its one caller
  (`IconBar.__init__`)** — a private layout constant no test or
  sibling module reaches by name.
