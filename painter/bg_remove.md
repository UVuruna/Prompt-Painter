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
- **black void** around a bright subject → cleared while the dark
  parts of the subject stay opaque (largest-bright-blob fill)
- **ambiguous** (gradient, mid-tone) → reported and left alone —
  skip, never guess

## Connections

### Uses
- numpy, scipy (`ndimage`), Pillow
- [Config](config.md) — `CROP_INK_ALPHA`, `CROP_MIN_INK_PX`,
  `CLEAN_EDGE_ALPHA` (the ink-crop / edge-cleanup thresholds).
  Imported package-first (`from painter.config`) with a bare
  `from config` fallback so the standalone script still runs.

### Used by
- [Postprocess](postprocess.md) — uses the internals (`detect`,
  `remove_white_border`, `remove_black_background`, `content_bbox`,
  `clean_edge_halo`) for its two split, composable steps
- The owner, standalone:
  `python painter/bg_remove.py <file-or-folder> --in-place --crop`

## Functions

- `process_file(src, dst, mode, crop, force_full, force_edge) ->
  str` — one image; returns the action taken (the standalone CLI's
  engine — the per-save pipeline goes through
  [Postprocess](postprocess.md) instead).
- `detect(img)` — the auto-detection described above.
- `remove_white_border`, `remove_black_background`, `autocrop` —
  the three operations.
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
