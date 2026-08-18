# AspectRatioCanvas

**Script:** [AspectRatioCanvas (script)](../aspect_canvas.py) ·
**Flow:** [diagram](../__flow/aspect_canvas.md)

## Purpose
A live, draggable preview of the TARGET output ratio (GUI rework
Phase 5) — pulled out of `gui/__init__.py` (root Rule #20 god-file
refactor, step 3/8) — separate from `FilterEditor`: FilterEditor picks
WHICH images a tool touches, this widget shapes WHAT ratio the tool
deforms them TO. A rectangle, centred in a fixed square arena,
represents `w:h`; grabbing any of its 4 edges reshapes it (LEFT/RIGHT
change WIDTH, TOP/BOTTOM change HEIGHT, always centred). A live label
below shows both the decimal form (`aspect.decimal_ratio_label`, e.g.
"1.778:1") and the smallest-integer form (`aspect.reduced_ratio`,
gcd-based, e.g. "16:9"). A live drag EMPHASIZES the box (thicker
outline, bigger handles) as cheap feedback that an edge is actively
grabbed.

Public API: `set_ratio(w, h)` — a PROGRAMMATIC reshape (e.g. the
host's own W/H entries) that re-FITS the box to the arena, the larger
side exactly filling it; NO-OPS when passed the SAME `(w, h)` it
already holds — without that guard, a drag's own `on_change` callback
mirrored back into the host's entry vars would round-trip into a
`set_ratio` call that re-"fits" the box and visibly SNAPS mid-gesture.
The `on_change(w, h)` callback fires once per drag tick that actually
changes the rounded ratio, so a host can mirror it into its own
fields; both current hosts (`AgentPanel`'s Force Aspect Ratio block,
`AspectSettingsPanel`) wire a typed-entry trace back the other way —
parsing both fields and calling `set_ratio` — with a bad/incomplete
value silently skipped as a normal mid-typing state rather than an
error dialog on every keystroke (final validation happens on
Start/Run); that parsing lives in this module's own free function
`apply_typed_wh(w_var, h_var, canvas)`, NOT inside the widget — the
canvas draws, the helper reads the host's two StringVars. The three
hosts (`AgentPanel`, `ApiImageGenPanel`, `AspectSettingsPanel`) each
carried the same seven statements before the 2026-08-18 audit named it
Violation 3.

**Drag math.** Each of the 4 edges (not just 2 axes) is tracked
individually. Grabbing the RIGHT edge clamps its effective x to never
cross the centre, so an overshoot/fast drag HOLDS at the minimum size
instead of "growing" again once the cursor passes the opposite side —
same clamp for LEFT/TOP/BOTTOM against their own axis.

A FIXED pixel size — it does not track the font zoom, like
`DayNightSwitch`. Its background is a `skin_canvas` surface (re-tints
on flip); its drawn content reads `job_color("aspect")`/the active
theme LIVE at draw time, and exposes `redraw_theme()` for a host to
call explicitly on a flip.

Split out of the former single-file `gui.py` (root Rule #20 god-file
refactor, step 3/8).

## Connections

### Uses
- [Change Aspect Ratio](../../painter/__about/aspect.md) —
  `decimal_ratio_label`/`reduced_ratio`
- [Config (subfolder)](../../painter/config/___config.md) —
  `ASPECT_DEFAULT_W`/`_H`, `THEMES`
- [The Theme Engine](theme.md) — `skin_canvas`
- [Themed Widget Toolkit](widgets.md) — `job_color`, `tk_font`, and the
  live `ACTIVE_THEME` global via `widgets.ACTIVE_THEME`
  module-attribute access (never a bare import, which would freeze a
  stale snapshot across a theme flip — see [GUI (folder)](../___gui.md)'s
  "Design Decisions")

### Used by
- [GUI (folder)](../___gui.md) — `__init__.py` re-exports
  `AspectRatioCanvas`; `AgentPanel`'s Force Aspect Ratio block and
  `AspectSettingsPanel` each construct one and register their own
  `apply_theme()` in `THEME_TOPLEVELS` to call `redraw_theme()` on a
  flip — both non-modal, LIVE parts of the main window (a fully-modal
  host, like the old `AspectRatioDialog`, never needed this since a
  flip cannot happen while a `grab_set` dialog is open)

## Functions

### apply_typed_wh(w_var, h_var, canvas)
The one owner of the typed-W/H → `set_ratio` step: read both
StringVars, parse, skip a bad or incomplete MID-EDIT value silently,
skip a non-positive one, then reshape the canvas. A free function, not
a method or a mixin — its three hosts have three different base classes
(`AgentPanel`/`ApiImageGenPanel` frames and a `ToolSettingsPanel`
subclass), and a helper that needs no shared base fits all three.

## Classes

### AspectRatioCanvas
A `tk.Canvas` subclass. See Purpose above for the geometry model, the
`set_ratio`/`on_change` two-way-sync contract, and the drag math.
