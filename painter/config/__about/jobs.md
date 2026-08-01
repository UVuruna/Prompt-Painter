# Jobs Config

**Script:** [Jobs Config (script)](../jobs.py) ·
**Flow:** [diagram](../__flow/jobs.md)

## Purpose

Dashboard per-JOB panel config, dashboard status badges, and the Main
Menu landing screen (owner 2026-07-19 / 2026-07-20 / GUI rework Phase
10). All PURE data (strings/numbers/a frozen dataclass tuple), so the
engine and tests import it with no `tkinter`.

## Connections

### Uses
Nothing — a leaf module.

### Used by
- GUI dashboard (`gui/dash_panels.py`, `gui/dash_helpers.py`) — one
  panel per running job, the status-badge dots, the grid/slider layout
- GUI Main Menu (`gui/menu.py`) — `MenuTile`, `MENU_TILES`, the tile
  geometry constants
- GUI running view's IconBar — `TILE_JOB_KINDS`, `tile_for_kind`
- [Job Temp Config](jobtemp.md) — `JOB_LABEL` (the four real pipeline
  stages reuse it rather than duplicating a label)
- Re-exported by [Config Package Index](__init__.md)

## Constants

**Dashboard per-job panels:**
- `JOB_ORDER` — fixed priority placing panels row-major (gen sites
  first)
- `JOB_TOOL_KINDS` — the four in-place tool kinds
- `JOB_LABEL`, `JOB_LOGO`, `JOB_COLORS`, `JOB_METRIC` — per-job button
  text, icon stem, (day, night) colour pair, and metric word
- `job_color_pair(kind)` — lookup helper

**Dashboard grid sizing + display modes:**
- `DASH_CARD_MIN_W`, `DASH_GRID_MAX_COLS` — F4e (owner 2026-07-29):
  columns = however many min-width cards fit, never more than 4
- `DASH_MODE_GRID`, `DASH_MODE_SLIDER`, `DASH_MODES` — the two
  dashboard display modes

**Dashboard status badges:**
- `BADGES` — badge key → (hex colour, label), render order
- `BADGE_ACTION_STEPS` — the runner's action-string step name → badge
  key
- `BADGE_DONE_STATUS` — the only status that earns a badge
- `BADGE_DOT_PX`, `BADGE_DOT_GAP_PX`, `BADGE_DOT_SS` — dot geometry
- `badge_keys_for(actions, retried) -> tuple` — see
  [flow](../__flow/jobs.md)

**Main Menu — geometry + `MENU_TILES`:**
- `MENU_TILE_RADIUS`, `MENU_TILE_COLS`, `MENU_TILE_W`/`_H`,
  `MENU_TILE_GAP_PX`, `MENU_TILE_ICON_PX`, `MENU_TILE_BORDER_PX`/
  `_HOVER_PX` — the 4×2 landing-screen tile grid
- `MenuTile` — frozen dataclass (`id`, `label`, `description`, `icon`,
  `color`, `enabled`)
- `MENU_TILES` — the 8 tiles (website_gen, ai_sheet_gen,
  api_image_gen, image_checker, bg, crop, upscale, aspect)

**Main Menu — `TILE_JOB_KINDS` mapping:**
- `TILE_JOB_KINDS` — tile id → the `JOB_ORDER` kind(s) that light it
  up live
- `tile_for_kind(kind) -> str | None` — the reverse: a kind's OWN
  persistent-panel tile id, or `None` for a multi-kind tile
  (`website_gen`)
