# Background Remover

**Script:** [Background Remover (script)](bg_remove.py)

## Purpose
Makes a generated image's background transparent. Originally built
inside DOMY Watch (`tools/bg_remove.py`); moved here 2026-07-17 on
the owner's rule that no part of this program lives in another
project. The code is the proven original, unchanged.

Per image it auto-detects (sampling the outer 1% frame):

- **already transparent** → skipped untouched (safe to re-run)
- **white / off-white background** → removes only the white
  connected to the border (flood fill), so bright detail inside
  the subject survives; softly feathered edge, halo-free
- **black void** around the subject → the BORDER-CONNECTED near-black
  (brightness ≤ `BLACK_VOID_MAX`) is cleared, while dark regions
  ENCLOSED by the subject (the black leading between glass, dark inner
  areas) stay opaque — the SAME edge-connected flood the white path
  uses (owner 2026-07-19). This replaced the old "largest bright blob
  + fill holes" disc, which could not tell a DARK subject from a black
  background and ate the dark stone frame of the bible/dark rondels
  (50-78% turned transparent — swiss cheese).
- **ambiguous** (gradient, mid-tone) → reported and left alone —
  skip, never guess

A **SAFETY GUARD** wraps both removals (owner 2026-07-19): each
`remove_*` returns `(rgba, removed_frac)`, and the caller ABORTS when
the fraction cleared exceeds the path's guard (`SAFETY_MAX_REMOVE_FRAC`
for black, `SAFETY_MAX_REMOVE_FRAC_WHITE` for white — legit white
backgrounds run large, reaching ~0.57, so their guard is higher). An
aborted removal leaves the ORIGINAL untouched (never a destroyed save):
`process_file` returns `"skip-risky"` and [Postprocess](postprocess.md)
returns `"unclear"`.

## Connections

### Uses
- numpy, scipy (`ndimage`), Pillow
- [Config (subfolder)](config/___config.md) — `CROP_INK_ALPHA`, `CROP_MIN_INK_PX`,
  `CLEAN_EDGE_ALPHA` (the ink-crop / edge-cleanup thresholds),
  `BLACK_VOID_MAX` (the black-void brightness ceiling), and the two
  SAFETY guards `SAFETY_MAX_REMOVE_FRAC` /
  `SAFETY_MAX_REMOVE_FRAC_WHITE`. Imported package-first
  (`from painter.config`) with a bare `from config` fallback so the
  standalone script still runs.

### Used by
- [Postprocess](postprocess.md) — uses the internals (`detect`,
  `remove_white_border`, `remove_black_background`, `content_bbox`,
  `clean_edge_halo`) for its two split, composable steps
- The owner, standalone:
  `python painter/bg_remove.py <file-or-folder> --in-place --crop`

## Functions

- `process_file(src, dst, mode, crop, force_full, force_edge) ->
  str` — one image; returns the action taken, or `"skip-risky"` when
  the SAFETY guard fires (removal too large — source left untouched,
  nothing written). The standalone CLI's engine — the per-save
  pipeline goes through [Postprocess](postprocess.md) instead.
- `detect(img)` — the auto-detection described above.
- `remove_white_border(img, white_full, white_edge) -> (rgba,
  removed_frac)` — edge-connected white made transparent; the second
  value is the fraction the removal clears (the guard checks it).
- `remove_black_background(img, void_max, sigma) -> (rgba,
  removed_frac)` — the BORDER-CONNECTED black void cleared (brightness
  ≤ `void_max`, connected to the frame), interior enclosed dark
  regions kept opaque; returns the cleared fraction too.
- `autocrop` — crop to the ink-based content box.
- `content_bbox(img, ink_alpha, min_ink_px) -> (l, t, r, b) | None`
  — the INK-BASED content box shared by `autocrop` and the
  postprocess crop step (owner 2026-07-18, the OldAge.png case). A
  row/col counts as content only when it holds at least `min_ink_px`
  pixels that are at least `ink_alpha` opaque, so a sparse faint
  stray line hugging the border no longer extends the box; `None`
  when no row/col qualifies (fully transparent / faint speckle).
- `clean_edge_halo(img, edge_alpha) -> (rgba_copy, n_cleaned)` — the
  CONSERVATIVE edge-halo cleanup: faint pixels (alpha < `edge_alpha`)
  that connect to the image border are zeroed (reusing
  `edge_connected_background`), while faint pixels enclosed by the
  solid subject (interior soft edges) are never border-connected and
  stay untouched. Returns the cleaned copy and the count of pixels
  that actually lost visible alpha.
- `main(argv)` — the standalone CLI (`--in-place`, `--crop`,
  `--backup`, `--mode auto|white|black`).
