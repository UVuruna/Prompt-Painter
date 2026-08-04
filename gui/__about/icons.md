# Icon Loading + Switch Art

**Script:** [Icon Loading + Switch Art (script)](../icons.py) ·
**Flow:** [diagram](../__flow/icons.md)

## Purpose

SVG-first icon loading for every button in the app (`icon()`, cached
per `(name, size)` for the whole process), rasterized through Qt's
`QSvgRenderer` (PySide6, already a monorepo build dependency) at 4x
and LANCZOS-downscaled for crispness. PNG is the fallback for icons
with no svg (`crop`/`upscale`/`aspect`, the owner's own marks) AND
for svgs QtSvg's *Tiny* profile cannot
render — detected by tag-sniffing the raw bytes for `<clipPath`/
`<mask`/`<filter`. `gemini.svg` is the concrete case: an Illustrator
raster-trace export, 12 embedded rasters under 28 `clipPath`s, which
QtSvg turns to garbage — its `gemini.png` sibling was pre-rasterized
ONCE from the svg via a browser (Chromium), transparent, 512 px. A
missing icon — or a Tiny-unrenderable svg with no png sibling — raises
`FileNotFoundError` loudly (root Rule #1), never a silent icon-less
button; callers keep the button's own text visible via
`compound="left"` regardless.

## The grouping folders (owner 2026-08-04)

The ~45 marks are filed **by kinship**, not in one flat heap:

| Folder | Holds |
|--------|-------|
| `jobs/` | one mark per functionality — the Home tiles + dashboard headers |
| `actions/` | verbs — every button that DOES something |
| `nav/` | navigation & view (home, back/next, close, expand/collapse, grid/slider, the cog) |
| `files/` | inputs & documents (reference, papyrus, key) |
| `brand/` | third-party marks — never redrawn |
| `theme/` | the Day/Night switch tracks + the owner's sun/moon SVGs |

**Call sites never name a folder.** They pass a BARE STEM
(`icon("crop")`, `icon_name="save"`, `JOB_LOGO`, `MenuTile.icon`);
`icon_paths()` walks `ICON_GROUPS` and answers where that stem lives.
Identity is the stem, filing is the folder — so a mark can be re-filed
without touching a widget. Two folders claiming one stem would make
the answer depend on `ICON_GROUPS` order rather than on intent, so
`tests/test_icons.py` fails on any such clash, on any stem the GUI
asks for that has no file, on any asked mark that will not actually
render, and on any project-drawn SVG using `clipPath`/`mask`/`filter`.

The coloured `jobs/` + `files/` marks are drawn in each job's own
`JOB_COLORS` accent, from plain shapes and gradients ONLY — the SVG
Tiny limitation above is a design constraint, not just a loader note.
The regrouping also cost one live crash worth remembering:
`_render_switch_track` built its path off the flat `ICON_DIR`, so
filing the two track SVGs into `theme/` raised inside
`DayNightSwitch.__init__` and took the WHOLE window down at startup.
It resolves through `icon_paths` now, pinned by a regression test.

Also holds the Day/Night switch's hand-rendered art, all built on the
same SVG->PIL rasterizer as the button icons:
- anti-aliased radial-gradient sun/moon knobs — the MOON has 7 craters
  of varied sizes, each with a lit rim arc facing the light direction,
  a terminator shading band (brightness ramps from the lit limb to a
  dark floor across a smoothstep), and a deterministic low-amplitude
  value-noise surface mottling (fixed seed — identical every build);
  the SUN is a gold gradient disc over a blurred glow;
- the track-pill rasterizer (`_render_switch_track`, the owner's
  website switch SVGs resized to the exact pill box);
- `render_knob(kind, d, ss)` — WHICH sun/moon the switch and the
  theme-flip cover wear, per `config.SWITCH_KNOB_SOURCE` (owner
  2026-08-04): `"svg"` (the default now) rasterizes HIS OWN
  `theme/{sun,moon}.svg`, the same artwork his website uses beside
  the two track pills; `"drawn"` keeps the in-code renderers below.
  Both versions stay on disk and in code — flipping that ONE config
  value is the whole switch-back, no code edit;
- the big theme-cover icon renderer (`_render_theme_cover_icon`,
  reusing the same knob renderers at `SWITCH_COVER_ICON_FRAC` — 30% —
  of the theme-flip cover window's smaller dimension).

Split out of the former single-file `gui.py` (root Rule #20 god-file
refactor, step 2/8) — the toolkit's LEAF module: no dependency on any
other `gui` submodule.

## Connections

### Uses
- [Config (subfolder)](../../painter/config/___config.md) —
  `PROJECT_ROOT` (resolves `ICON_DIR` beside the project, never the
  CWD), `THEMES`, every `SWITCH_*` rendering constant
- PySide6's `QtSvg`/`QtGui` (a lazy, never-`exec()`-ed
  `QGuiApplication` — serves only offscreen painting; tkinter keeps
  the event loop)
- Pillow + numpy (the moon's terminator shading and surface mottling)

### Used by
- [GUI (folder)](../___gui.md) — `__init__.py` re-exports the full API
  (`gui.icon`, `gui.ICON_DIR`, ...)
- [Themed Widget Toolkit](widgets.md) — `icon()` (`rounded_button`'s
  optional icon)
- [The Theme Engine](theme.md) — `_render_theme_cover_icon` (the
  big sun/moon riding the theme-flip snapshot cover)
- [DayNightSwitch](switch.md) — `render_knob` (the SOURCE-aware door)
  + `_render_switch_track`

## Functions

- `icon(name, size=20) -> ctk.CTkImage` — the named icon, resolved
  beside `gui/` (never the CWD), loaded once per `(name, size)` and
  cached in `_ICONS` for the process lifetime.
- `_svg_to_pil(path, target_px) -> Image.Image` — one SVG rasterized
  via `QSvgRenderer`, aspect-fit on the longer side, rendered at
  `SVG_OVERSAMPLE` (4x) and LANCZOS-downscaled.
- `_radial_disc(px, center_hex, edge_hex, hilite) -> Image.Image` — a
  supersampled RGBA disc: a radial gradient from `center_hex` at the
  `hilite` point to `edge_hex` at the rim, circular alpha mask.
- `_render_moon_knob(d_px, ss) -> Image.Image` /
  `_render_sun_knob(d_px, ss) -> Image.Image` — the switch knob art
  (see Purpose above).
- `render_knob(kind, d_px, ss) -> Image.Image` — the sun/moon from
  whichever SOURCE `config.SWITCH_KNOB_SOURCE` names ("svg" = the
  owner's `theme/{sun,moon}.svg`, "drawn" = the two renderers above).
  The ONE door the switch and the theme cover both go through.
- `_render_theme_cover_icon(target_name, min_dim) -> Image.Image` —
  the big sun (day) or moon (night) for the theme-flip cover.
- `_render_switch_track(stem, w, h) -> Image.Image` — one track pill,
  rasterized from its SVG and sized to the exact pill box.

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
