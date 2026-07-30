# Image Viewer

**Script:** [Image Viewer (script)](image_viewer.py)

## Purpose
`ImageViewer` (GUI rework Phase F4f, owner G6/G7) — the PORTRAIT
per-image dashboard viewer that replaced `DocWindow` for IMAGE-level
rows: Prev/Next/Delete always visible at the top, the image's own
file-stem TITLE, the main image (or a refusal / missing reason in its
place), the prompt in a read-only monospace block with its own "Copy
(for AI)", and two sub-title-styled EXPANDABLE sections — **Check**
and **Steps** — each entirely absent when its lookup has nothing for
the current entry.

Split out of `gui/viewers.py` (root Rule #20 god-file refactor,
2026-07-30). See the class's own docstring for the full contract: the
entries shape and the exact `check_lookup` / `steps_lookup` /
`restore_cb` / `on_restored` / `on_deleted` callables
[Settings Mixin](app_settings.md) wires into it.

Owns its own `IMAGE_VIEWER_*` geometry (Rule #4) — the one PORTRAIT
window in the family, sized so Row 1's three buttons are never cut
off, still clamped to the screen by the shared
[Viewer Shared Rules](viewer_shared.md) `DOC_MAX_FRAC`.

## Connections

### Uses
- [Viewer Shared Rules](viewer_shared.md) — `DOC_MAX_FRAC`,
  `_copy_to_clipboard`, `_readonly_text_keys`
- [Dashboard Support Helpers](dash_helpers.md) — `_scaled_photo` and
  `ai_check_doc_md` (the Check section renders the SAME text
  `DashPanel._show_check` shows)
- [Scroll (script)](scroll.py) — `ScrollFrame`
- [Theme (script)](theme.py) — `THEME_TOPLEVELS`, `skin_text`,
  `skin_toplevel`
- [Themed Widget Toolkit](widgets.md) — `rounded_button`, `tk_font`

### Used by
- [GUI (folder)](___gui.md) — `__init__.py` re-exports `ImageViewer`
- [Settings Mixin](app_settings.md) — `SettingsMixin._show_node` opens
  it for an image-level dashboard row through a PLAIN real-path import
  (see Design Decisions), building its `check_lookup`/`steps_lookup`/
  `restore_cb`/`on_restored` from the clicking `DashPanel`'s own
  `_check_results`/`jobtemp`/`out_base`/`refresh_image_row`

## Classes

### ImageViewer
See the Purpose section above and the class's own docstring.

## Design Decisions
**Opened through a PLAIN real-path import, not the deferred
`import gui; gui.DocWindow(...)` idiom its sibling viewers use.** No
test needs `monkeypatch.setattr(gui, "ImageViewer", fake)` (unlike
`DocWindow`/`StepRestoreWindow`, which `test_gui_checker.py`/
`test_gui_fixer.py`/`test_gui_pipeline.py` DO patch that way), so the
deferred idiom would buy nothing. It IS in `gui/__init__.py`'s
re-export block, so a future test could switch to the deferred form
without touching this module.

**`restore_cb(rel, label) -> bool` / `on_restored(entry)` are
additions beyond the `steps_lookup(rel) -> list[(label, Path)]`
2-tuple the section's PRESENCE/DISPLAY contract uses.** Actually
restoring a step needs the raw `JobTemp` step key and a `JobTemp`
instance — neither travels through a bare `(label, Path)` display
pair. Keeping `steps_lookup` itself pure display data (easy to fake in
tests, no `JobTemp` coupling) and adding one small extra callable for
the restore action was judged simpler than either smuggling the step
key into the display tuple or handing this window a raw `JobTemp` and
re-deriving what `StepRestoreWindow` already knows.
`SettingsMixin._image_viewer_restore_cb` reverses the label back to
the raw step key via `_STEP_LABEL_TO_KEY` (safe: every
`JOBTEMP_STEP_LABEL` value is unique) before calling the shared
`_restore_step`.
