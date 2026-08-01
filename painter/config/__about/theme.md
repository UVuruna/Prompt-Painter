# Theme Config

**Script:** [Theme Config (script)](../theme.py) ·
**Flow:** [diagram](../__flow/theme.md)

## Purpose

GUI themes: the single source of truth (owner 2026-07-18) for the two
coordinated day/night palettes, the per-kind solid-button fills, the
Day/Night switch's full image-based art block, and a few
window-mechanics timing constants that fit no other domain module.
Pure hex/number data — no `tkinter`/`PIL` import — so the engine and
tests stay framework-free.

**Distinct from `gui/theme.py`:** this module is the DATA (palettes,
button fills, switch timing); `gui/theme.py` is the rendering/factory
ENGINE that turns this data into `ttkbootstrap`/`customtkinter`
widgets and PIL-rendered switch art. Same name, different folder,
different responsibility — never confuse the two when reading a
traceback.

## Connections

### Uses
Nothing — a leaf module.

### Used by
- GUI theme engine `gui/theme.py` — turns `THEMES` into the
  `ttkbootstrap` palette + `customtkinter` appearance mode
- `gui/switch.py` — the Day/Night switch's PIL-rendered art
  (`SWITCH_*`)
- `gui/scroll.py` — `RESIZE_SETTLE_MS` (ScrollFrame resize debounce)
- `gui/app_build.py` and every collapsible panel — `TRANSITION_FADE_MS`/
  `_STEPS` (the Controls collapse, a Settings gear, an Advanced section)
- Re-exported by [Config Package Index](__init__.md)

## Constants

**Palettes:**
- `THEMES` — the `"night"`/`"day"` dicts (`ttkname`, `mode`,
  `switch_on`, `ttk` palette, `status` semantic colours)
- `theme_pair(key)`, `status_pair(role)` — (day, night) tuple helpers
  for `customtkinter`'s light/dark auto-flip

**Solid button fills:**
- `BUTTON_FILL`, `BUTTON_TEXT` — per-kind (day, night) fill + text,
  decoupled from the ttk palette so DAY can differ from NIGHT per kind
- `button_fill_pair(kind)`, `button_text_pair(kind)` — lookup helpers

**Switch — geometry + animation timing:**
- `SWITCH_H`, `SWITCH_ASPECT`, `SWITCH_KNOB_FACTOR`, `SWITCH_PAD_PX`,
  `SWITCH_ANIM_MS`, `SWITCH_FRAME_MS`, `SWITCH_HOVER_SCALE`,
  `SWITCH_FADE_MS`, `SWITCH_FADE_STEPS`, `SWITCH_SUPERSAMPLE`,
  `SWITCH_COVER_ICON_FRAC`, `SWITCH_COVER_ICON_SS`

**Visual mechanics — transition fade + resize debounce:**
- `TRANSITION_FADE_MS`, `TRANSITION_FADE_STEPS` — the snapshot-cover
  fade for discrete Tk-level relayouts (NOT window maximize/restore —
  owner 2026-07-21 perf fix)
- `RESIZE_SETTLE_MS` — ScrollFrame's re-fit debounce after the LAST
  `<Configure>` event

**Switch art — track SVGs + knob highlight:**
- `SWITCH_TRACK_NIGHT_SVG`, `SWITCH_TRACK_DAY_SVG` — the pill SVG stems
- `SWITCH_KNOB_HILIGHT` — shared radial-gradient light point

**Switch art — moon knob:**
- `SWITCH_MOON_CENTER`/`_EDGE`, `SWITCH_CRATER*`, `SWITCH_MOON_LIGHT_DIR`,
  `SWITCH_MOON_TERMINATOR_SOFT`, `SWITCH_MOON_DARK_FLOOR`,
  `SWITCH_MOON_NOISE_*`, `SWITCH_CRATERS` (7-tuple of diameter/x/y)

**Switch art — sun knob:**
- `SWITCH_SUN_CENTER`/`_EDGE`, `SWITCH_SUN_GLOW*`, `SWITCH_SUN_CELL_SCALE`
