# AspectRatioCanvas

**Script:** [AspectRatioCanvas (script)](aspect_canvas.py)

## Purpose
A live, draggable preview of the TARGET output ratio (GUI rework
Phase 5) — pulled out of `gui/__init__.py` (root Rule #20 god-file
refactor, step 3/8) — separate from `FilterEditor` (which picks WHICH
images a tool touches); this widget shapes WHAT ratio the tool deforms
them TO. A rectangle, centred in a fixed square arena, represents
`w:h`; grabbing any of its 4 edges reshapes it (LEFT/RIGHT change
WIDTH, TOP/BOTTOM change HEIGHT, always centred). A live label below
shows both the decimal form (`aspect.decimal_ratio_label`) and the
smallest-integer form (`aspect.reduced_ratio`).

Public API: `set_ratio(w, h)` (a programmatic reshape that re-fits the
box to the arena) and the `on_change(w, h)` callback (fired once per
drag tick that actually changes the rounded ratio).

A FIXED pixel size (like `DayNightSwitch`, it does not track the font
zoom). Its background is a `skin_canvas` surface (re-tints
automatically on a theme flip); its drawn content is NOT part of that
registry, so it exposes `redraw_theme()` for a host to call
explicitly from its own `apply_theme()`.

## Connections

### Uses
- [Painter (folder)](../painter/___painter.md) — `aspect`
  (`decimal_ratio_label`/`reduced_ratio`), `config`
  (`ASPECT_DEFAULT_W`/`_H`, `THEMES`)
- [Theme (script)](theme.md) — `skin_canvas`
- [Widgets (script)](widgets.md) — `job_color`, `tk_font`, and the
  live `ACTIVE_THEME` global via `widgets.ACTIVE_THEME`
  module-attribute access (never a bare import, which would freeze a
  stale snapshot across a theme flip — see [GUI (folder)](___gui.md)'s
  "Design Decisions")

### Used by
- [GUI (folder)](___gui.md) — `__init__.py` re-exports
  `AspectRatioCanvas`; `AgentPanel`'s Force Aspect Ratio block and
  `AspectSettingsPanel` each construct one and register their own
  `apply_theme()` in `THEME_TOPLEVELS` to call `redraw_theme()` on a
  flip
