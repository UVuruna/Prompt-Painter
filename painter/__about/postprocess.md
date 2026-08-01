# Postprocess (Background Removal + Crop)

**Script:** [Postprocess (script)](../postprocess.py) ·
**Flow:** [diagram](../__flow/postprocess.md)

## Purpose

Owner workflow step 6, SPLIT IN TWO composable steps (owner's #7,
2026-07-18): the pipeline callers ([Main (Entry Point)](../../__about/main.md)'s
`_build_post_save`, the [GUI (folder)](../../gui/___gui.md)'s own hook)
compose them by flags instead of one fused fix. Both work IN PLACE,
only on the file they are given (inside the output folder), and
NEVER raise for a no-op — only for real errors (`PostprocessError`,
loud).

- **`remove_background`** — the in-house [Background Remover](bg_remove.md)
  internals. Already-transparent → `"nothing"` (untouched, in EVERY
  mode); the background cleared → `"done"`; nothing done →
  `"unclear"` (reported via the log, ORIGINAL left untouched). No
  cropping any more — that is the second step.

  Its **`mode`** (owner 2026-07-28) picks WHICH background is cleared:
  `BG_MODE_AUTO` sniffs the border for white or black and then asks the
  FOUR CORNERS for any other uniform colour (logging which colour it
  decided on — an auto decision is never silent); only disagreeing
  corners give `"unclear"`, and that report names the colour it saw so
  the owner can state it. `BG_MODE_BLACK` / `BG_MODE_WHITE` force one
  and skip the sniff, and `BG_MODE_COLOR` clears ANY `color` (hex)
  within `tolerance_pct` % of 255 per channel — `0 %` keys the typed
  colour exactly. A mistyped colour is parsed BEFORE the image is
  opened, so it is reported as the configuration error it is rather
  than as a per-image failure.

  Its **`reach`** (owner 2026-07-28) decides WHERE a matching pixel
  counts: `BG_REACH_EDGE` clears only what connects to the frame (so a
  same-coloured region ENCLOSED by the subject — the counters inside
  letters — stays), `BG_REACH_ALL` clears every matching pixel wherever
  it sits. Orthogonal to the mode: any background, detected or stated,
  runs either way.

  A **SAFETY GUARD** (owner 2026-07-19) also returns `"unclear"` when
  the removal would clear more than the path's guard fraction — it ate
  the subject rather than the background. The guard is PER PATH: black
  (`SAFETY_MAX_REMOVE_FRAC`, 0.40) is tight because it fences a GUESS —
  it catches the dark-rondel destruction that motivated the fix (a dark
  subject keyed as black background); white
  (`SAFETY_MAX_REMOVE_FRAC_WHITE`, 0.85) and custom colour
  (`SAFETY_MAX_REMOVE_FRAC_COLOR`, 0.85) run high because their legit
  backgrounds are large (real white plates reach ~0.57) and, for a
  colour, the background is known rather than inferred. The abort
  message NAMES the guard that fired and its value in PERCENT. All
  three are owner-editable per run, as percent.
- **`crop_transparent`** — halo cleanup THEN autocrop in place (owner
  2026-07-18, the OldAge.png case): (1) `clean_edge_halo` zeroes the
  faint stray line / halo CONNECTED TO THE IMAGE BORDER
  (`CLEAN_EDGE_ENABLE`) — its ONLY job is to ENABLE a tighter box, then
  (2) autocrop to the INK-BASED content box (a row/col needs
  `CROP_MIN_INK_PX` pixels at alpha ≥ `CROP_INK_ALPHA`, so a sparse
  faint line no longer defeats the crop) plus the `CROP_MARGIN_PX`
  safety margin. CHANGED vs SKIPPED is STRICTLY DIMENSIONAL (owner
  2026-07-19): `"done"` **only** when the cropped output resolution is
  smaller than the input on some side (≥ 1px) — that alone saves the
  file. When the box + margin lands on the FULL frame (0px change) the
  result is `"nothing"`, the file left BYTE-UNCHANGED, **even if the
  halo cleanup zeroed pixels** — that cleanup is discarded, never
  written (the sun_eclipse 801×800 → 801×800 case: there is no such
  thing as a halo-only `"done"`). `"nothing"` also covers a fully
  opaque / fully transparent image and a box that cannot be found.

A failed step is LOUD but never kills the run (the runner catches,
counts and reports it; the raw image stays saved).

**Per-call overrides** (GUI rework Phase 13, owner 2026-07-21): both
functions accept OPTIONAL keyword-only arguments — one per config
constant they read — defaulting to the matching constant, so every
EXISTING caller (which passes neither) keeps today's exact byte-for-
byte behaviour. The GUI's `BgSettingsPanel`/`CropSettingsPanel` (a
standalone tool's persistent settings panel) is the one caller that
overrides them, per run.

## Connections

### Uses
- [Config (subfolder)](../config/___config.md) — `CROP_MARGIN_PX`,
  `CROP_INK_ALPHA`, `CROP_MIN_INK_PX`, `CLEAN_EDGE_ALPHA`,
  `CLEAN_EDGE_ENABLE`, `BG_MODE_*`, `BG_COLOR_DEFAULT`,
  `BG_COLOR_TOLERANCE_PCT`, `SAFETY_MAX_REMOVE_FRAC`,
  `SAFETY_MAX_REMOVE_FRAC_WHITE`, `SAFETY_MAX_REMOVE_FRAC_COLOR`
- [Background Remover](bg_remove.md) — `plan`, `apply_plan`,
  `parse_hex_color`, `content_bbox`, `clean_edge_halo`; imported
  lazily (numpy/scipy load only when a step actually runs)

### Used by
- [Main (Entry Point)](../../__about/main.md) — composed into the
  `post_save` hook by the `--no-bgfix` / `--no-crop` flags
- [GUI (folder)](../../gui/___gui.md) — its own composed hook + the
  dependency check

## Functions

- `deps_error() -> str | None` — `None` when numpy/scipy/Pillow are
  importable; otherwise the reason. Callers refuse to start instead
  of failing on every item.
- `remove_background(path, log, *, mode=BG_MODE_DEFAULT,
  color=BG_COLOR_DEFAULT, tolerance_pct=BG_COLOR_TOLERANCE_PCT,
  reach=BG_REACH_DEFAULT,
  safety_max_remove_frac=SAFETY_MAX_REMOVE_FRAC,
  safety_max_remove_frac_white=SAFETY_MAX_REMOVE_FRAC_WHITE,
  safety_max_remove_frac_color=SAFETY_MAX_REMOVE_FRAC_COLOR) -> str` —
  `"done" | "nothing" | "unclear"`, in place; `"unclear"` covers both
  an ambiguous background (auto mode) and a SAFETY-guard abort (removal
  too large — original untouched). Raises `ValueError` for a mistyped
  `color` (before any image is read) and `PostprocessError` on real
  failure.
- `crop_transparent(path, log, *, clean_edge_enable=CLEAN_EDGE_ENABLE,
  clean_edge_alpha=CLEAN_EDGE_ALPHA, crop_margin_px=CROP_MARGIN_PX,
  crop_ink_alpha=CROP_INK_ALPHA, crop_min_ink_px=CROP_MIN_INK_PX) ->
  str` — `"done" | "nothing"`, in place; raises `PostprocessError` on
  real failure.
