# Main Menu + Icon Bar

**Script:** [Main Menu + Icon Bar (script)](menu.py)

## Purpose
`MainMenu` and `IconBar`, pulled out of `gui/__init__.py` (root Rule
#20 god-file refactor, step 6/8; GUI rework Phases 10–11). `MainMenu`
is the startup landing screen — a responsive full-window grid of big
tiles, one per `config.MENU_TILES` functionality, that reflows its
column count (down to 1) as the window narrows so tiles never clip.
`IconBar` is the compact top strip shown while a job is running — one
small button per tile plus a "Menu" button, each tile lighting up
while any of its job kinds is live. Neither class decides what
picking a tile DOES — both only call back into `PainterGui`
(`_select_tile`/`_click_icon_bar_tile`).

## Connections

### Uses
- [Painter (folder)](../painter/___painter.md) — `config`
  (`MENU_TILES` and its layout constants, `theme_pair`)
- [Icon Loading + Switch Art](icons.md) — `icon` (a tile's picture)
- [Pure Logic (script)](logic.md) — `MENU_TILE_CELL_MIN_PX`/
  `_menu_tile_columns` (the reflow math)
- [Themed Widget Toolkit](widgets.md) — `_style_icon_bar_button`/
  `ctk_font`/`rounded_button`

### Used by
- [GUI (folder)](___gui.md) — `__init__.py` re-exports `MainMenu`/
  `IconBar` for `PainterGui` (which builds one of each alongside the
  rest of the app) and for external tests

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
