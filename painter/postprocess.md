# Postprocess (Background Removal + Crop)

**Script:** [Postprocess (script)](postprocess.py)

## Purpose
Owner workflow step 6, SPLIT IN TWO composable steps (owner's #7,
2026-07-18): the pipeline callers ([Main (Entry Point)](../main.md)
`_build_post_save`, the [GUI](../gui.md)'s own hook) compose them
by flags instead of one fused fix. Both work IN PLACE, only on the
file they are given (inside the output folder), and NEVER raise for
a no-op — only for real errors (`PostprocessError`, loud).

- **`remove_background`** — the in-house
  [Background Remover](bg_remove.md) internals, auto-detected per
  file: already-transparent → `"nothing"` (untouched), white
  (Gemini) or black background → cleared, `"done"`, ambiguous
  (gradient, mid-tone) → `"unclear"` (reported via the log,
  left untouched). No cropping any more — that is the second step.
  A **SAFETY GUARD** (owner 2026-07-19) also returns `"unclear"`
  (reported, ORIGINAL untouched) when the removal would clear more
  than the path's guard fraction — it ate the subject rather than the
  background. The guard is PER PATH: the black guard
  (`SAFETY_MAX_REMOVE_FRAC`, 0.40) catches the dark-rondel destruction
  that motivated the fix (a dark subject keyed as black background); the
  white guard (`SAFETY_MAX_REMOVE_FRAC_WHITE`, 0.85) runs high because
  legit white backgrounds are large (real plates reach ~0.57), so it
  fires only on a catastrophic white-subject-eaten. Each `remove_*`
  now returns `(rgba, removed_frac)` and this step checks it before
  saving.
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
byte behaviour. [GUI](../gui.md)'s new `BgSettingsPanel`/
`CropSettingsPanel` (a standalone tool's persistent settings panel) is
the one caller that overrides them, per run, via each panel's
Advanced collapsible: `remove_background`'s
`safety_max_remove_frac`/`safety_max_remove_frac_white` (the SAFETY
GUARD ceilings below) and `crop_transparent`'s `clean_edge_enable`/
`clean_edge_alpha`/`crop_margin_px`/`crop_ink_alpha`/`crop_min_ink_px`.
The site-generation pipeline ([GUI](../gui.md)'s own composed hook)
and [Main (Entry Point)](../main.md) still call both with no
overrides — the config constants remain the single source of truth
for every run that doesn't explicitly override them.

## Connections

### Uses
- [Config](config.md) — `CROP_MARGIN_PX`, `CROP_INK_ALPHA`,
  `CROP_MIN_INK_PX`, `CLEAN_EDGE_ALPHA`, `CLEAN_EDGE_ENABLE`,
  `SAFETY_MAX_REMOVE_FRAC`, `SAFETY_MAX_REMOVE_FRAC_WHITE`
- [Background Remover](bg_remove.md) — `detect`,
  `remove_white_border`, `remove_black_background`, `content_bbox`,
  `clean_edge_halo`; imported lazily (numpy/scipy load only when a
  step actually runs)

### Used by
- [Main (Entry Point)](../main.md) — composed into the `post_save`
  hook by the `--no-bgfix` / `--no-crop` flags
- [GUI](../gui.md) — its own composed hook + the dependency check

## Functions

- `deps_error() -> str | None` — `None` when numpy/scipy/Pillow are
  importable; otherwise the reason. Callers refuse to start instead
  of failing on every item.
- `remove_background(path, log, *, safety_max_remove_frac=SAFETY_MAX_REMOVE_FRAC,
  safety_max_remove_frac_white=SAFETY_MAX_REMOVE_FRAC_WHITE) -> str` —
  `"done" | "nothing" | "unclear"`, in place; `"unclear"` covers both
  an ambiguous background and a SAFETY-guard abort (removal too large
  — original untouched). Raises `PostprocessError` on real failure.
- `crop_transparent(path, log, *, clean_edge_enable=CLEAN_EDGE_ENABLE,
  clean_edge_alpha=CLEAN_EDGE_ALPHA, crop_margin_px=CROP_MARGIN_PX,
  crop_ink_alpha=CROP_INK_ALPHA, crop_min_ink_px=CROP_MIN_INK_PX) ->
  str` — `"done" | "nothing"`, in place; raises `PostprocessError` on
  real failure.
