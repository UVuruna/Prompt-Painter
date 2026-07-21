# Themed Widget Toolkit

**Script:** [Themed Widget Toolkit (script)](widgets.py)

## Purpose
The dark-palette rounded CTk control factories every panel builds
from — buttons, entries, combos, the compact `[-][entry][+]`
`Spinner`, the on/off switch — plus the status/job-colour lookups,
the font-zoom registry, Start/Stop button styling, the folder-
grouping helpers shared by the dashboard tree and the Select window,
and the Advanced-override numeric field parsers. Split out of the
former single-file `gui.py` (root Rule #20 god-file refactor, step
2/8) — the toolkit's near-leaf module: its only dependency on another
`gui` submodule is `gui.icons.icon` (`rounded_button`'s optional
icon).

Owns the two LIVE mutable globals every theme flip / zoom rewrites:
`ACTIVE_THEME` (the current theme name, rebound by `gui.theme.
_apply_theme_now`) and `FONT_BASE` (the current zoom root size,
rebound by this module's own `set_font_base`). Every OTHER module
that needs the CURRENT value reads it as `widgets.ACTIVE_THEME` /
`widgets.FONT_BASE` — a module-attribute access — never as a bare
imported name, which would freeze a stale copy at import time.

## Connections

### Uses
- [Config (subfolder)](../painter/config/___config.md) — `THEMES`,
  `button_fill_pair`/`button_text_pair`/`job_color_pair`/
  `status_pair`/`theme_pair`
- [Icons (script)](icons.md) — `icon()` (the optional icon drawn on a
  `rounded_button`)

### Used by
- [GUI (folder)](___gui.md) — `__init__.py` re-exports the full API
  (`gui.rounded_button`, `gui.status`, `gui.job_color`, `gui.
  set_font_base`, ...); `gui.theme` (`status`, `tk_font`, `TREE_ROW_
  FACTOR` for `setup_style`); `gui.switch` (the live `ACTIVE_THEME`)

## Classes

### EdgeIconButton
A `CTkButton` whose icon pins to the left edge while the text centers
in the remaining width — for stacked equal-width buttons (Add…/
Remove/Clear), where the default centered icon+text block makes the
icons jitter with the text length.

### Spinner
A compact `[-][entry][+]` numeric field as ONE rounded unit (root
Rule #5 — the pace/action-delay fields are its instances): direct
typing stays allowed (validated on Start), the +/- buttons step the
value by a configurable amount, never below 0.

## Design Decisions
See [GUI (folder)](___gui.md)'s own "Design Decisions" section for
the full reasoning behind the `ACTIVE_THEME`/`FONT_BASE` module-
attribute pattern — it applies identically here, since this is the
module that OWNS both globals.
