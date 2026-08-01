# The Theme Engine

**Script:** [The Theme Engine (script)](../theme.py) ·
**Flow:** [diagram](../__flow/theme.md)

## Purpose
The coordinated ttk/CTk/plain-tk Day/Night flip: swap the
ttkbootstrap theme + re-run `setup_style` (the ttk half), flip
customtkinter's appearance mode (every CTk colour tuple re-resolves
with zero re-walk), recolour the plain-tk registry (`Text`/`Listbox`/
`Canvas`/`Toplevel` — colours CTk's automatic tuple resolution can't
reach), then fire every open Toplevel's own `apply_theme()`. No window
teardown — an active run's worker threads, dashboard counters and
quota countdowns all survive a flip.

**Three widget families, three flip mechanisms — each covered so no
widget is ever stranded in the other theme** (the bug the owner once
caught in an accidental half-light window):
- **customtkinter** — every colour kwarg in [Widgets](widgets.md)'
  factories is a fixed `(day, night)` tuple; CTk re-resolves it per
  mode on `ctk.set_appearance_mode()`, repainting every CTk control
  with zero per-widget re-walk.
- **ttkbootstrap** — `Style().theme_use()` swaps the theme and
  `setup_style()` re-runs (it reads `style.colors` live, reproducing
  the named styles in the new palette); ttk looks styles up at draw
  time, so this updates every style-driven widget automatically.
- **plain tk** (`Text`/`Listbox`/`Canvas`/`Toplevel`) — created through
  `skin_text`/`skin_listbox`/`skin_canvas`/`skin_toplevel`, which
  colour the widget AND append `(widget, role)` to the flat
  `THEMED_TK` registry; `recolor_tk_registry()` re-walks it on a flip,
  re-applying each role's skin and pruning dead widgets via
  `tk.TclError`. This is the ONLY place plain-tk colours live.

Also owns the shared snapshot-cover transition, `smooth_transition`:
grabs the window into a borderless topmost overlay, forces it fully
painted, runs a mutate callback (a theme flip / a relayout) hidden
behind it, then fades the cover out — the ONE mechanism behind the
theme flip itself, the Controls collapse, each agent's Settings-gear
reveal and each tool panel's Advanced-section reveal. A pure visual
nicety: any cover failure (no display grab, alpha unsupported, an
unmapped window) degrades to the plain instant mutate, and the mutate
itself is never guarded — an exception in it propagates loudly (root
Rule #1), with the overlay still fading out via a `finally`.

**NOT used for a window maximize/restore** (owner 2026-07-21 perf fix,
reverting owner 2026-07-20's own use of it there) — a real-window repro
proved covering that OS-level state jump breaks it (the window gets
stuck at its old size, or renders corrupted on restore) instead of
hiding it. See [Build Mixin](app_build.md)'s `_on_root_configure` for
the full story. (The legacy pre-split `gui.md` doc still describes
maximize/restore as covered by `smooth_transition` — that account is
now FALSE; this file is the current, correct one.)

`THEME_TOPLEVELS` means "anything exposing `apply_theme()`", not
literally "every Toplevel": `SelectWindow`/`DocWindow` register on
`__init__`/unregister on `<Destroy>` (their per-widget foregrounds
don't follow ttk styles); non-Toplevel LIVE surfaces with an embedded
`AspectRatioCanvas` (`AgentPanel`, `AspectSettingsPanel`) also register,
calling their canvas's `redraw_theme()`; FULLY MODAL dialogs
(`grab_set`+`wait_window`, e.g. `AiKeyWizard`) deliberately do NOT
register — the grab blocks all input including the theme switch, so a
flip genuinely cannot happen while one is open.

Split out of the former single-file `gui.py` (root Rule #20 god-file
refactor, step 2/8).

## Connections

### Uses
- [Config (subfolder)](../../painter/config/___config.md) — `THEMES`,
  `TRANSITION_FADE_MS`/`TRANSITION_FADE_STEPS` (the snappy default),
  `SWITCH_FADE_MS`/`SWITCH_FADE_STEPS` (the theme flip's own longer,
  ceremonial timing)
- [Widgets](widgets.md) — `status` (tree-tag colours), `tk_font`/
  `TREE_ROW_FACTOR` (`setup_style`'s Treeview rowheight), and the live
  `ACTIVE_THEME`/`FONT_BASE` globals via `widgets.ACTIVE_THEME`/
  `widgets.FONT_BASE` module-attribute access
- [Icons](icons.md) — `_render_theme_cover_icon` (the big sun/moon
  riding the flip's snapshot cover)

### Used by
- [GUI (folder)](../___gui.md) — `__init__.py` re-exports the full API
  (`gui.apply_theme`, `gui.skin_text`, ...); [ScrollFrame](scroll.md)
  (`skin_canvas`); [DayNightSwitch](switch.md) (`apply_theme`,
  `skin_canvas`)
- [Build Mixin](app_build.md) — calls `apply_theme`/
  `register_painter_day`/`skin_listbox`/`skin_text` at construction
- [View Mixin](app_views.md) — `smooth_transition` wraps the Controls
  collapse and view swaps

## Classes
This module has no classes — it is a set of module-level functions plus
two module-level registries (`THEMED_TK`, `THEME_TOPLEVELS`) and two
Treeview tag-name constants (`TOOL_CHANGED_TAG`, `TOOL_SKIP_TAG`). Key
functions: `apply_theme`/`_apply_theme_now` (the coherent flip),
`setup_style` (the ttk style patch), `skin_text`/`skin_listbox`/
`skin_canvas`/`skin_toplevel`/`skin_tree` + `recolor_tk_registry` (the
plain-tk skin registry), `smooth_transition`/`_snapshot_overlay`/
`_fade_out_overlay` (the shared cover-and-fade transition),
`register_painter_day` (the custom light ttkbootstrap theme,
registered once, idempotent).

## Design Decisions
- **`ACTIVE_THEME`/`FONT_BASE` are read, never rebound, here.** Both
  mutable globals are OWNED by `gui.widgets`; `_apply_theme_now`
  mutates the theme name via `widgets.ACTIVE_THEME = name` (a
  module-attribute assignment, not a `global` rebind) — a plain
  cross-module `from .widgets import ACTIVE_THEME` would silently
  freeze a stale copy at import time and never again see a later
  flip/zoom.
- **`smooth_transition`'s collaborators stay monkeypatchable through
  `gui`.** `_snapshot_overlay`/`_fade_out_overlay` are called through
  a small `_pkg()` indirection (`import gui; return gui`) instead of
  this module's own globals, specifically so existing tests written
  against the one-file `gui.py` (`monkeypatch.setattr(gui,
  "_snapshot_overlay", fake)`) keep working unmodified post-split.
  Every real caller is unaffected (`gui.X` and `gui.theme.X` are the
  same function object unless a test overrides one).
- **The snapshot-cover ORDER is what kills the visible jump**: the
  overlay is forced fully mapped and painted by the window manager
  FIRST (`deiconify` → `lift` → `update_idletasks` → `update()`, so
  DWM really shows it) — only THEN does the mutate callback run and
  settle behind it, and only then does the fade start. Skipping this
  order (mutate first, cover after) would let the repaint cascade
  flash through before the cover exists.
