# Main Menu + Icon Bar

**Script:** [Main Menu + Icon Bar (script)](../menu.py) ·
**Flow:** [diagram](../__flow/menu.md)

## Purpose
`MainMenu` and `IconBar`, pulled out of `gui/__init__.py` (root Rule
#20 god-file refactor, step 6/8; GUI rework Phases 10–11). `MainMenu`
is the startup landing screen — a full-window FIXED grid of big tiles
(always `MENU_TILE_COLS` columns — owner 2026-08-03, UI rework
tačka 1, reverting the 2026-07-21 responsive column reflow): instead
of the grid adapting to a narrow window, the WINDOW can never get that
narrow — `BuildMixin._apply_min_size` computes `root.minsize` from
this grid's own floor (`gui.logic.menu_min_size` + the measured
chrome, re-run after every font-zoom step), so every tile always
renders whole and the menu never scrolls (the `ScrollFrame` bar
auto-hides when content fits — see [Scroll](scroll.md)).
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

`IconBar` is the compact nav strip shown on the setup ("main") and
"running" views — the HOME icon button leftmost (`home.svg`; owner
2026-08-03, UI rework tačka 2 — replacing the old right-side text
"Menu" button AND the old pinned top-strip one as the single way back
to the Main Menu), then one small button per tile, reusing the SAME
tile data and factory pattern (not two copies). The strip NEVER clips
a button: its own `<Configure>` compares the allocated width against
the measured full-text width and, when too narrow, EVERY tile button
drops its label at once (uniform icon-only mode; labels return with
`ICON_BAR_HYSTERESIS_PX` slack so the boundary never flickers; the
cached measurement is invalidated by `refresh_measure` after a font
zoom). `set_active(active_ids)` recolours every enabled tile — FILLED
with its accent while any of its `config.TILE_JOB_KINDS` is live, a
quiet outline otherwise.

Neither class decides what picking a tile DOES — both only call back
into `PainterGui` (`_select_tile`/`_click_icon_bar_tile`;
`on_menu=_request_menu` for HOME).

## Connections

### Uses
- [Painter (folder)](../../painter/___painter.md) — `config`
  (`MENU_TILES` and its layout constants, `theme_pair`)
- [Icons](icons.md) — `icon` (a tile's picture; the HOME button's
  `home.svg`)
- [Pure Logic Helpers](logic.md) — `MENU_TILE_CELL_MIN_PX` (the shared
  per-column footprint; `menu_min_size` reads it there too)
- [Themed Widget Toolkit](widgets.md) — `_style_icon_bar_button`/
  `ctk_font`/`rounded_button`

### Used by
- [GUI (folder)](../___gui.md) — `__init__.py` re-exports `MainMenu`/
  `IconBar` for external tests
- [Build Mixin](app_build.md) — `BuildMixin.__init__` builds ONE
  `MainMenu` (`on_select=self._select_tile`) and ONE `IconBar`
  (`on_select=self._click_icon_bar_tile`, `on_menu=self._request_menu`);
  `_apply_min_size` reads `MENU_GRID_PADX` + `MainMenu.chrome_height()`
  + `MainMenu.cell_min_px()` (the MEASURED per-column footprint — it
  re-applies itself as every column's Tk `minsize` on the way out, so
  no tile can be clipped at any font zoom), `_zoom_step` calls
  `IconBar.refresh_measure`
- [View Mixin](app_views.md) — `_select_tile`/`_click_icon_bar_tile`
  (what picking a tile actually does) and `_icon_bar.set_active(...)`
  after every change to the running job set

## Classes

### MainMenu
The startup landing screen's fixed tile grid — see Purpose above.
Tiles are built and gridded ONCE in `__init__` (`self._tiles`); every
column/row carries weight 1 + `uniform` + a real Tk `minsize`
(`MENU_TILE_CELL_MIN_PX` per column — the SAME constant
`menu_min_size` assumes, so the computed window minimum and the grid
floor can never disagree). `chrome_height()` reports the header +
paddings above/around the grid at the current font zoom for
`_apply_min_size`.

### IconBar
The compact nav strip shown on the setup and running views — see
Purpose above. `_on_configure` measures the full-text width lazily
(first `<Configure>` in text mode) and toggles `_set_icon_only`;
restoring labels clears the cached width so the next pass re-measures
at the current font.

## Design Decisions
- **Fixed 4×2 over responsive reflow (owner decree 2026-08-03)** —
  "uvek mora 4x2 grid; min width/height toliki da svi elementi stanu".
  The old `_menu_tile_columns` reflow math is DELETED (not kept
  dormant); `menu_min_size` in `gui.logic` is its pure replacement,
  tested the same way (`gui.menu_min_size` via the established
  re-export convention).
- **`MENU_HEADER_PADY`/`MENU_GRID_PADX`/`MENU_GRID_PADY` are module
  constants** — shared between the packs they describe and
  `chrome_height()`/`_apply_min_size`'s chrome math, so the computed
  minsize and the real layout cannot drift apart.
- **Icon-only is all-or-nothing** — a mixed strip (some labels, some
  not) reads as broken; one threshold flips every tile button
  together (owner's slika: "umesto ikone i teksta se pretvore u samo
  ikone — na taj način mogu svi da stanu").
- **`ICON_BAR_GAP_PX` moved here with its one caller
  (`IconBar.__init__`)** — a private layout constant no test or
  sibling module reaches by name.
