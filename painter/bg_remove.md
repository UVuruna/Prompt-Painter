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

### Used by
- [Postprocess](postprocess.md) — calls `process_file` directly
  after every saved image
- The owner, standalone:
  `python painter/bg_remove.py <file-or-folder> --in-place --crop`

## Functions

- `process_file(src, dst, mode, crop, force_full, force_edge) ->
  str` — one image; returns the action taken.
- `detect(img)` — the auto-detection described above.
- `remove_white_border`, `remove_black_background`, `autocrop` —
  the three operations.
- `main(argv)` — the standalone CLI (`--in-place`, `--crop`,
  `--backup`, `--mode auto|white|black`).
