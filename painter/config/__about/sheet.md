# Sheet

**Script:** [Sheet (script)](../sheet.py) ·
**Flow:** [diagram](../__flow/sheet.md)

## Purpose

The sheet contract's file-name rule and skip-marker regex, plus the
shared file/folder enumerators the four in-place tools and the
Collections queue use: a multi-file selection base resolver (the
Aspect tool's per-file picker) and two recursive folder walks (images,
`.md` files).

## Connections

### Uses
Nothing at module scope — a leaf module. `selection_base_and_rels`,
`iter_images` and `iter_md_files` import `os`/`pathlib` lazily inside
their own bodies.

### Used by
- [Sheet Parser](../../__about/sheet_parser.md) — `IMAGE_EXTENSIONS`,
  `SKIP_MARKER_PATTERN`
- GUI (folder) — the Collections queue's "Add folder…" (`iter_md_files`),
  the BG/Crop/Upscale tools' folder walk and the Aspect tool's
  multi-file picker (`iter_images`, `TOOL_IMAGE_EXTENSIONS`,
  `selection_base_and_rels`)
- Re-exported by [Config Package Index](__init__.md)

## Constants

- `IMAGE_EXTENSIONS` — `(".png",)`, the sheet contract's arrow-line
  file extension rule
- `SKIP_MARKER_PATTERN` — regex matching `REUSE` / `SUPERSEDED` /
  `DO-NOT-GENERATE` inside a `**bold**` span
- `TOOL_IMAGE_EXTENSIONS` — `(".png", ".jpg", ".jpeg", ".webp")`, the
  four in-place tools' accepted extensions

## Functions

### `selection_base_and_rels(paths) -> (base, [rel, ...])`
The common-ancestor DIRECTORY of a list of selected file paths, plus
each file's POSIX path relative to it. Raises `ValueError` on an
empty selection. See [flow](../__flow/sheet.md).

### `iter_images(folder) -> list`
Every image file under `folder` (recursive), sorted, filtered by
`TOOL_IMAGE_EXTENSIONS`.

### `iter_md_files(folder) -> list`
Every `.md` file under `folder` (recursive), sorted — mirrors
`iter_images`.
