# Postprocess (Background Fix)

**Script:** [Postprocess (script)](postprocess.py)

## Purpose
Owner workflow step 5: Gemini renders on white, ChatGPT sometimes
forgets transparency. Every saved image is handed to the DOMY Watch
background tool (`tools/bg_remove.py`, run as a subprocess), which
decides PER FILE: already-transparent → skipped untouched, white
background → cleared (edge-connected flood fill + autocrop),
ambiguous → reported and left alone. The tool only ever touches the
file it is given — always inside the output folder.

A failed fix is LOUD but never kills the run: the raw image stays
saved, the failure is logged per item and summarized at the end,
and the DOMY tool can be rerun over the folder later (rerunning is
safe by its design).

## Connections

### Uses
- [Config](config.md) — `BG_TOOL_PY`, `BG_TOOL_ARGS`,
  `BG_TOOL_TIMEOUT_S`
- DOMY Watch `tools/bg_remove.py` — the tool itself (subprocess;
  needs numpy, scipy, Pillow)

### Used by
- [Run Loop](runner.md) — the `post_save` hook
- [Main (CLI)](../main.md) / [GUI](../gui.md) — dependency check
  before a run

## Functions

- `deps_error() -> str | None` — `None` when the tool can run;
  otherwise the reason (missing tool path or missing
  numpy/scipy/Pillow). Callers refuse to start a bgfix run on an
  error instead of failing on every item.
- `fix_background(image_path) -> str` — one image, in place;
  returns the tool's action (`white`, `black`, `skip-transparent`,
  `skip-ambiguous`); raises `PostprocessError` on failure.
