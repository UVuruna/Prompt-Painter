# Icon Loading + Switch Art

**Script:** [Icon Loading + Switch Art (script)](icons.py)

## Purpose
SVG-first icon loading for every button in the app (`icon()`, cached
per `(name, size)`), rasterized through Qt's `QSvgRenderer` (PySide6,
already a monorepo build dependency) at 4x and LANCZOS-downscaled for
crispness; PNG is the fallback for icons with no svg and for svgs
QtSvg's Tiny profile cannot render (detected by tag-sniffing the raw
bytes). A missing icon — or an unrenderable svg with no png sibling —
raises `FileNotFoundError` loudly (root Rule #1), never a silent
icon-less button.

Also holds the Day/Night switch's hand-rendered art: anti-aliased
radial-gradient sun/moon knobs (7 varied craters with lit rim arcs, a
terminator shade band and seeded surface mottling on the moon; a soft
blurred glow on the sun) and the track-pill rasterizer, all built on
the same SVG->PIL path as the button icons.

Split out of the former single-file `gui.py` (root Rule #20 god-file
refactor, step 2/8) — the toolkit's LEAF module: no dependency on any
other `gui` submodule.

## Connections

### Uses
- [Config (subfolder)](../painter/config/___config.md) — `PROJECT_
  ROOT` (resolves `ICON_DIR` beside the project, never the CWD),
  `THEMES`, every `SWITCH_*` rendering constant
- PySide6's `QtSvg`/`QtGui` (lazy, never-`exec()`-ed `QGuiApplication`
  — serves only offscreen painting, tkinter keeps the event loop)
- Pillow + numpy (the moon's terminator shading and surface mottling)

### Used by
- [GUI (folder)](___gui.md) — `__init__.py` re-exports the full API
  (`gui.icon`, `gui.ICON_DIR`, ...); `gui.widgets` (`icon()` for
  `rounded_button`); `gui.theme` (`_render_theme_cover_icon`, the big
  sun/moon riding the theme-flip snapshot cover); `gui.switch`
  (`_render_sun_knob`/`_render_moon_knob`/`_render_switch_track`)

## Design Decisions
- **SVG-first, PNG fallback, never silent.** See the module
  docstring's own reasoning — a themed app with an icon quietly
  missing is a worse failure mode than a loud crash naming the exact
  file.
- **The moon renders real geometry, not a flat disc** (owner
  2026-07-20) — craters, a lit rim per crater facing the light
  direction, terminator shading and mottling all driven by
  `painter.config`'s `SWITCH_MOON_*`/`SWITCH_CRATER*` constants, so
  the art is tunable without touching this module.
