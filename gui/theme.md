# The Theme Engine

**Script:** [The Theme Engine (script)](theme.py)

## Purpose
The coordinated ttk/CTk/plain-tk Day/Night flip: swap the
ttkbootstrap theme + re-run `setup_style` (the ttk half), flip
customtkinter's appearance mode (every CTk colour tuple re-resolves
with zero re-walk), recolour the plain-tk registry (`Text`/
`Listbox`/`Canvas`/`Toplevel` — colours CTk's automatic tuple
resolution can't reach), then fire every open Toplevel's own
`apply_theme()`. No window teardown — an active run's worker
threads, dashboard counters and quota countdowns all survive a flip.

Also owns the shared snapshot-cover transition, `smooth_transition`:
grabs the window into a borderless topmost overlay, forces it fully
painted, runs a mutate callback (a theme flip / a relayout) hidden
behind it, then fades the cover out — the ONE mechanism behind the
theme flip itself, the Controls collapse, each agent's Settings gear
reveal and a window maximize/restore jump. A pure visual nicety: any
cover failure (no display grab, alpha unsupported, an unmapped
window) degrades to the plain instant mutate, and the mutate itself
is never guarded — an exception in it propagates loudly (root Rule
#1), with the overlay still fading out via a `finally`.

Split out of the former single-file `gui.py` (root Rule #20 god-file
refactor, step 2/8).

## Connections

### Uses
- [Config (subfolder)](../painter/config/___config.md) — `THEMES`,
  `TRANSITION_FADE_MS`/`TRANSITION_FADE_STEPS` (the snappy default),
  `SWITCH_FADE_MS`/`SWITCH_FADE_STEPS` (the theme flip's own longer,
  ceremonial timing)
- [Widgets (script)](widgets.md) — `status` (tree-tag colours),
  `tk_font`/`TREE_ROW_FACTOR` (`setup_style`'s Treeview rowheight),
  and the live `ACTIVE_THEME`/`FONT_BASE` globals via `widgets.
  ACTIVE_THEME`/`widgets.FONT_BASE` module-attribute access
- [Icons (script)](icons.md) — `_render_theme_cover_icon` (the big
  sun/moon riding the flip's snapshot cover)

### Used by
- [GUI (folder)](___gui.md) — `__init__.py` re-exports the full API
  (`gui.apply_theme`, `gui.skin_text`, ...); `gui.scroll`
  (`skin_canvas`); `gui.switch` (`apply_theme`, `skin_canvas`)

## Design Decisions
- **`ACTIVE_THEME`/`FONT_BASE` are read, never rebound, here.** Both
  mutable globals are OWNED by `gui.widgets`; `_apply_theme_now`
  mutates the theme name via `widgets.ACTIVE_THEME = name` (a
  module-attribute assignment, not a `global` rebind) — see [GUI
  (folder)](___gui.md)'s "Design Decisions" for why a plain
  cross-module import would silently break this.
- **`smooth_transition`'s collaborators stay monkeypatchable through
  `gui`.** `_snapshot_overlay`/`_fade_out_overlay` are called through
  a small `_pkg()` indirection (`import gui; return gui`) instead of
  this module's own globals, specifically so existing tests written
  against the one-file `gui.py` (`monkeypatch.setattr(gui,
  "_snapshot_overlay", fake)`) keep working unmodified post-split —
  see [GUI (folder)](___gui.md)'s "Design Decisions" for the full
  reasoning. Every real caller is unaffected (`gui.X` and `gui.
  theme.X` are the same function object unless a test overrides
  one).
