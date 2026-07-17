# Postprocess (Background Fix)

**Script:** [Postprocess (script)](postprocess.py)

## Purpose
Owner workflow step 5: Gemini renders on white, ChatGPT sometimes
forgets transparency. Every saved image is handed to the in-house
[Background Remover](bg_remove.md) (`process_file`, direct call),
which decides PER FILE: already-transparent → skipped untouched,
white background → cleared (edge-connected flood fill + autocrop),
ambiguous → reported and left alone. It only ever touches the file
it is given — always inside the staging folder.

A failed fix is LOUD but never kills the run: the raw image stays
saved, the failure is logged per item and summarized at the end,
and the remover can be rerun over the folder later (rerunning is
safe by its design).

## Connections

### Uses
- [Config](config.md) — `BG_FIX_CROP`
- [Background Remover](bg_remove.md) — imported lazily (numpy/scipy
  load only when a fix actually runs)

### Used by
- [Run Loop](runner.md) — the `post_save` hook
- [Main (CLI)](../main.md) / [GUI](../gui.md) — dependency check
  before a run

## Functions

- `deps_error() -> str | None` — `None` when numpy/scipy/Pillow are
  importable; otherwise the reason. Callers refuse to start a
  bgfix run on an error instead of failing on every item.
- `fix_background(image_path) -> str` — one image, in place;
  returns the remover's action (`white`, `black`,
  `skip-transparent`, `skip-ambiguous`); raises `PostprocessError`
  on failure.
