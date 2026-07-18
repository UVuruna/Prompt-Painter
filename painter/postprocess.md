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
- **`crop_transparent`** — autocrop a transparent image to its
  content bounding box plus the `CROP_MARGIN_PX` safety margin:
  `"done"` when it shrank, `"nothing"` when there is no
  transparency to crop against (fully opaque), the image is fully
  transparent, or it is already tight.

A failed step is LOUD but never kills the run (the runner catches,
counts and reports it; the raw image stays saved).

## Connections

### Uses
- [Config](config.md) — `CROP_MARGIN_PX`, `CROP_ALPHA_THRESH`
- [Background Remover](bg_remove.md) — `detect`,
  `remove_white_border`, `remove_black_background`, `content_bbox`;
  imported lazily (numpy/scipy load only when a step actually runs)

### Used by
- [Main (Entry Point)](../main.md) — composed into the `post_save`
  hook by the `--no-bgfix` / `--no-crop` flags
- [GUI](../gui.md) — its own composed hook + the dependency check

## Functions

- `deps_error() -> str | None` — `None` when numpy/scipy/Pillow are
  importable; otherwise the reason. Callers refuse to start instead
  of failing on every item.
- `remove_background(path, log) -> str` — `"done" | "nothing" |
  "unclear"`, in place; raises `PostprocessError` on real failure.
- `crop_transparent(path, log) -> str` — `"done" | "nothing"`, in
  place; raises `PostprocessError` on real failure.
