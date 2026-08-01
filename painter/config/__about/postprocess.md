# Postprocess Config

**Script:** [Postprocess Config (script)](../postprocess.py) ·
**Flow:** [diagram](../__flow/postprocess.md)

## Purpose

Background-removal and crop thresholds (owner workflow step 6): crop
margin/ink thresholds, the border-connected edge-halo cleanup, the
black-void removal + per-path safety guards, the BACKGROUND MODE
block (auto/black/white/custom colour), the REACH choice (flood-fill
from the border vs. everywhere), and the auto-colour four-corner
detector. Pure numbers and mode-name strings — a leaf module.

## Connections

### Uses
Nothing — a leaf module.

### Used by
- [Postprocess](../../__about/postprocess.md) (`painter/postprocess.py`)
  — `CROP_MARGIN_PX`, `CROP_INK_ALPHA`, `CROP_MIN_INK_PX`,
  `CLEAN_EDGE_ALPHA`, `CLEAN_EDGE_ENABLE`, the `BG_MODE_*`/`BG_COLOR_*`
  block, the three `SAFETY_MAX_REMOVE_FRAC*` guards
- [Background Remover](../../__about/bg_remove.md)
  (`painter/bg_remove.py`) — the same crop/cleanup constants plus
  `BLACK_VOID_MAX`, imported package-or-standalone
- GUI BG panel — the mode dropdown, the custom-colour picker, the
  Advanced fine-tune (guards shown/taken as PERCENT, converted at the
  panel edge from the engine's FRACTION values)
- Re-exported by [Config Package Index](__init__.md)

## Constants

**Crop thresholds:**
- `CROP_MARGIN_PX` — safety margin kept around the content box
- `CROP_INK_ALPHA`, `CROP_MIN_INK_PX` — ink-based content-box
  detection (a row/col needs ≥N pixels at ≥alpha to count as content)

**Edge-halo cleanup:**
- `CLEAN_EDGE_ALPHA`, `CLEAN_EDGE_ENABLE` — border-connected faint-pixel
  cleanup before cropping

**Black-void removal + safety guard:**
- `BLACK_VOID_MAX` — brightness ≤ this AND border-connected = void
- `SAFETY_MAX_REMOVE_FRAC` — BLACK path abort threshold (0.40)
- `SAFETY_MAX_REMOVE_FRAC_WHITE` — WHITE path abort threshold (0.85)

**Background mode:**
- `BG_MODE_AUTO`/`_BLACK`/`_WHITE`/`_COLOR`, `BG_MODE_DEFAULT`,
  `BG_MODE_LABEL` — the four removal modes and their GUI dropdown text

**Reach:**
- `BG_REACH_EDGE`/`_ALL`, `BG_REACH_DEFAULT`, `BG_REACH_LABEL` —
  border-connected flood fill (default) vs. every matching pixel

**Custom color + auto-detection:**
- `BG_COLOR_DEFAULT`, `BG_COLOR_TOLERANCE_PCT` — the custom-colour
  target and its per-channel `±%` fine-tune (0 = exact hex)
- `AUTO_CORNER_PX`, `AUTO_CORNER_AGREE_MAX` — the four-corner vote
  (owner 2026-07-28): corners agreeing within this per channel name
  the background colour
- `SAFETY_MAX_REMOVE_FRAC_COLOR` — CUSTOM/auto-detected colour path
  abort threshold (0.85 — same high ceiling as WHITE, since a custom
  colour is known, not inferred from one median)

All three `SAFETY_MAX_REMOVE_FRAC*` guards are FRACTIONS here (the
engine compares against a fraction); the GUI shows/takes them as
PERCENT, converting at the panel edge.
