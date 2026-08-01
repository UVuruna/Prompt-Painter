# Viewer Shared Rules

**Script:** [Viewer Shared Rules (script)](../viewer_shared.py)

## Purpose
The sizing rules and the three tiny read-only-window helpers every
viewer Toplevel shares — the leaf of the viewer family created by the
`gui/viewers.py` god-file split (root Rule #20, 2026-07-30: one window
family per module — [Doc Window](doc_window.md),
[Restore Viewers](restore_windows.md),
[Image Viewer](image_viewer.md)).

- **The `DOC_*` sizing family** (Rule #4) — `DOC_A4_RATIO`,
  `DOC_HEIGHT_FRAC`, `DOC_MAX_FRAC`, `DOC_MIN_W`, `DOC_MIN_H`,
  `DOC_IMG_PAD_PX`, `DOC_CHROME_PAD_PX`. `DOC_MAX_FRAC`/
  `DOC_HEIGHT_FRAC` are the single "never bigger than the screen" /
  "tall open" clamps EVERY doc-shaped window shares — the two restore
  viewers, the image viewer and
  [Select Window](select_window.md) all read them. The last two are
  `DocWindow`'s own, kept with the family so the sizing rules read as
  one block rather than scattering across three modules.
- **`_copy_to_clipboard(widget, text)`** — clipboard copy plus its
  confirmation dialog (Rule #5: `DocWindow`'s "Copy (for AI)" and
  `ImageViewer`'s prompt copy are the same action).
- **`_readonly_text_keys(event)`** — the key filter that keeps a Text
  read-only while copy / select-all / navigation still work.
- **`_restore_step(temp, rel, step)`** — the ONE `JobTemp.restore_to`
  call site every "Restore to here / this step" button goes through,
  in the whole `gui/` package.

A true leaf: plain tkinter only, no other `gui` submodule, so every
viewer imports it with no cycle risk. This is a Standard-tier file —
plain shared rules/helpers, no real branching algorithm — so it carries
no `__flow` diagram.

## Connections

### Uses
- Nothing in `gui` — plain `tkinter`/`tkinter.messagebox` only.

### Used by
- [Doc Window](doc_window.md) — the whole `DOC_*` family plus the
  clipboard and read-only-Text helpers
- [Restore Viewers](restore_windows.md) — the screen clamps and
  `_restore_step`
- [Image Viewer](image_viewer.md) — `DOC_MAX_FRAC`, the clipboard and
  read-only-Text helpers
- [Select Window](select_window.md) — `DOC_HEIGHT_FRAC`/`DOC_MAX_FRAC`
- [Settings Mixin](app_settings.md) — `_restore_step`, through the
  `restore_cb` it builds for a dashboard-opened image

## Design Decisions
**Why a shared leaf instead of leaving the constants with
`DocWindow`.** Four windows and the Select window all size themselves
by the same two clamps; hanging them off whichever class happened to
define them first would make every other module import a SIBLING
window just to learn how big it may be. The leaf has no imports of its
own, so it can never take part in a cycle.
