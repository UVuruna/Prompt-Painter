# DayNightSwitch

**Script:** [DayNightSwitch (script)](../switch.py) ·
**Flow:** [diagram](../__flow/switch.md)

## Purpose
The mini Day/Night toggle, top-right — an image pill ported from the
owner's website switch. OFF/left = MOON on the dark starfield track;
ON/right = SUN (with a soft glow) on the sky-and-clouds track. A click
flips the theme SYNCHRONOUSLY (via `gui.theme.apply_theme`, riding the
shared snapshot-cover transition so the whole app's repaint cascade
never shows) while the knob itself slides as a ~600ms smoothstep-eased
flourish underneath the cover — the slide runs CONCURRENTLY on the
switch's own canvas, revealed as the cover fades away.

CRISP art: tkinter `Canvas` has no anti-aliasing, so the pill
composites anti-aliased PIL images instead of raw ovals — the two
track pills straight from the owner's website SVGs, the sun/moon
knobs from `gui.icons`' supersampled radial-gradient renderers. All
six images (two tracks, sun/moon at rest, sun/moon hover) are built
ONCE at construction and held on `self._imgs` so tkinter cannot
garbage-collect them; every `_redraw` after that just re-places the
track (hard-swapped night/day at the knob's midpoint) and the knob at
the animated x — no re-rendering. A missing track SVG is a loud
`FileNotFoundError` (root Rule #1), never a blank pill. The switch is
a FIXED pixel size — unlike most other GUI text/controls, it does not
follow the font zoom. Its canvas is registered as a `canvas` surface
so its background re-tints with the window on a flip.

Split out of the former single-file `gui.py` (root Rule #20 god-file
refactor, step 2/8).

## Connections

### Uses
- [Config (subfolder)](../../painter/config/___config.md) — `THEMES`,
  every `SWITCH_*` geometry/timing constant
- [Themed Widget Toolkit](widgets.md) — the live `ACTIVE_THEME` global
  via `widgets.ACTIVE_THEME` module-attribute access (reflects the
  CURRENT theme at construction, without freezing a stale copy)
- [Icon Loading + Switch Art](icons.md) — `_render_sun_knob`/
  `_render_moon_knob`/`_render_switch_track`
- [The Theme Engine](theme.md) — `apply_theme` (the click handler),
  `skin_canvas` (the canvas background re-tints on a flip)

### Used by
- [GUI (folder)](../___gui.md) — `__init__.py` re-exports
  `DayNightSwitch`; built once in `PainterGui`'s pinned top strip

## Classes

### DayNightSwitch
A `tk.Canvas` subclass. See Purpose above for the composited-image
approach and the click/slide split (theme flips synchronously, the
knob slide is pure flourish underneath the cover). Public API:
`set(name, animate=False)` — reflect a theme name on the knob without
going through a click (no `apply_theme` call, no recursion), used when
the theme changes from something other than this widget.

## Design Decisions
See [GUI (folder)](../___gui.md)'s "Design Decisions" for why this
module reads `widgets.ACTIVE_THEME` (a module-attribute access)
rather than importing the bare name.
