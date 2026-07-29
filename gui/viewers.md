# Read-Only Viewers

**Script:** [Read-Only Viewers (script)](viewers.py)

## Purpose
Four read-only Toplevel viewers + a handful of small shared helpers,
pulled out of `gui/__init__.py` (root Rule #20 god-file refactor):

- `DocWindow` — the Markdown/prompt/image viewer (headings, code,
  bullets, bold, an optional saved-image section, a "Copy for AI"
  button), PLUS the optional Fixer-AI manual buttons (IMAGE FIX /
  WEBSITE FIX) shown only when the caller passed one or both
  zero-arg workers. Since GUI rework Phase F4f it backs only the
  sheet/folder-level dashboard rows — `ImageViewer` (below) took over
  the image level.
- `BeforeAfterWindow` — a tool job's before/after viewer (single-image
  Restore or whole-job RESTORE ALL).
- `_filmstrip_stages` — the pure, Tk-free per-image pipeline-stage
  list `StepRestoreWindow` (and `ImageViewer`'s own Steps section)
  render from (one `(label, path)` pair per named backed-up stage plus
  the current live file).
- `StepRestoreWindow` — the per-step restore filmstrip built from it,
  with a horizontal `ScrollFrame` and a **Restore to here** button per
  stage.
- `ImageViewer` (GUI rework Phase F4f, owner G6/G7) — the PORTRAIT
  per-image dashboard viewer: Prev/Next/Delete always visible at the
  top, the image's own file-stem TITLE, the main image (or a refusal/
  missing reason in its place), the prompt in a read-only monospace
  block with its own "Copy (for AI)", and two sub-title-styled
  EXPANDABLE sections — Check and Steps — each entirely absent when
  its lookup has nothing for the current entry. See the class's own
  docstring for the full contract (entries shape, the `check_lookup`/
  `steps_lookup`/`restore_cb`/`on_restored`/`on_deleted` callables).
- `_copy_to_clipboard`, `_readonly_text_keys`, `_restore_step` — the
  three small module-level helpers `DocWindow`, `StepRestoreWindow`
  and `ImageViewer` all share (Rule #5): clipboard-copy-plus-dialog,
  the read-only-but-selectable Text key filter, and the one
  `JobTemp.restore_to` call site every "Restore to here/this step"
  button in this module goes through.

Also owns the shared `DOC_*`/`BEFORE_AFTER_*`/`STEP_RESTORE_*`/
`IMAGE_VIEWER_*` sizing constants (Rule #4) — `DOC_HEIGHT_FRAC`/
`DOC_MAX_FRAC` are also read by `gui.select_window.SelectWindow` (the
"tall open" / "never bigger than screen" clamps every doc-shaped
window shares) and by `ImageViewer` itself for its own screen clamp.

## Connections

### Uses
- [Painter (folder)](../painter/___painter.md) — `config`
  (`JOBTEMP_STEP_LABEL`, `STEP_RESTORE_CURRENT_LABEL`)
- [Dashboard Support Helpers](dash_helpers.md) — `_scaled_photo` (the
  transparency-checkerboard-composited thumbnail) and, since GUI
  rework Phase F4f, `ai_check_doc_md` (`ImageViewer`'s Check section
  renders the SAME text `DashPanel._show_check` shows)
- [Logic](logic.md) — `_fix_result_ui` (`DocWindow`'s pure Fixer
  result-to-UI mapping)
- [Scroll (script)](scroll.py) — `ScrollFrame`
- [Theme (script)](theme.py) — `THEME_TOPLEVELS`, `skin_text`,
  `skin_toplevel`
- [Themed Widget Toolkit](widgets.md) — `rounded_button`, `status`,
  `tk_font`
- `gui.dialogs.AI_POLL_MS` — `DocWindow._arm_fix_poll`'s OWN Fixer poll
  (unrelated to any AI dialog) reads the same cadence constant. A
  real-path `from .dialogs import AI_POLL_MS` would be circular
  (`gui.dialogs` imports `DocWindow` from THIS module for
  `AiSheetDialog._finish`'s "not loaded" viewer), so it reaches the
  constant through a deferred `import gui; gui.AI_POLL_MS` instead —
  the same late-binding idiom `gui.theme._pkg()` and
  `gui.api_panel`'s `_arm_probe_poll` already established

### Used by
- [GUI (folder)](___gui.md) — `__init__.py` re-exports `DocWindow`,
  `BeforeAfterWindow`, `StepRestoreWindow`, `_filmstrip_stages`.
  `ImageViewer` is NOT yet in that re-export block — see Design
  Decisions below
- [Dialogs](dialogs.md) — `AiSheetDialog._finish` opens a `DocWindow`
  when the AI-generated sheet still fails the contract after the
  repair round
- `PainterGui` (`gui/__init__.py`), `DashPanel`
  ([Dashboard Job Panel Base + Site Panel](dash_panels.md)),
  `ToolPanel`/`AiCheckPanel`
  ([Tool + AI-Checker Dashboard Panels + Grid](tool_dash.md)) — open
  `DocWindow`/`StepRestoreWindow` through a deferred
  `import gui; gui.DocWindow(...)` / `gui.StepRestoreWindow(...)`
  (never a module-level import), so
  `monkeypatch.setattr(gui, "DocWindow"/"StepRestoreWindow", fake)` in
  the test suite still reaches them regardless of which module the
  caller now lives in; `ToolPanel`'s own `BeforeAfterWindow` calls stay
  a plain real-path import (no test monkeypatches it)
- [Settings Mixin](app_settings.md) — `SettingsMixin._show_node`
  opens `ImageViewer` for an image-level dashboard row through a
  PLAIN real-path `from .viewers import ImageViewer` (see Design
  Decisions below for why this one breaks the deferred-`import gui`
  convention above), building its `check_lookup`/`steps_lookup`/
  `restore_cb`/`on_restored` from the clicking `DashPanel`'s own
  `_check_results`/`jobtemp`/`out_base`/`refresh_image_row`

## Classes

### DocWindow
See the Purpose section above.

### BeforeAfterWindow
See the Purpose section above.

### StepRestoreWindow
See the Purpose section above; built from `_filmstrip_stages`.

### ImageViewer
See the Purpose section above and the class's own docstring (entries
shape, every callable's exact contract).

## Functions

### `_filmstrip_stages(temp, rel, live_path)`
Pure, Tk-free — see the Purpose section above and the function's own
docstring for the exact ordering contract `StepRestoreWindow._render`
(and `SettingsMixin._image_viewer_steps_lookup`) relies on.

### `_copy_to_clipboard(widget, text)` / `_readonly_text_keys(event)` / `_restore_step(temp, rel, step)`
The three Rule #5 helpers factored out of `DocWindow`/`StepRestoreWindow`
while building `ImageViewer`, so all three viewers share ONE clipboard-
copy dialog, ONE read-only-Text key filter, and ONE `JobTemp.restore_to`
call site instead of three near-identical copies.

## Design Decisions
**`AI_POLL_MS` lives in `gui.dialogs`, not here.** `_AiDialog` (the
key wizard, the sheet generator) is the class that actually paces its
worker-queue poll loop with it, so it moved there rather than staying
behind in `gui/__init__.py` or duplicating into this module.

**`ImageViewer` is opened through a PLAIN real-path import, not the
deferred `import gui; gui.DocWindow(...)` idiom every other viewer
call site in this file's "Used by" uses.** Two reasons: (1)
`gui/__init__.py` is mid-edit by a PARALLEL session on an unrelated
GUI-rework phase at the time this class was built — out of this
session's edit scope — so it cannot re-export `ImageViewer` as
`gui.ImageViewer` yet; (2) no test currently needs to
`monkeypatch.setattr(gui, "ImageViewer", fake)` (unlike `DocWindow`/
`StepRestoreWindow`, which `test_gui_checker.py`/`test_gui_fixer.py`/
`test_gui_pipeline.py` DO patch that way), so the deferred idiom would
buy nothing today. Follow-up: once `gui/__init__.py` settles, add
`ImageViewer` to its `.viewers` re-export block for consistency, and
`SettingsMixin._show_node` MAY switch to the deferred form then (not
required — only needed if/when a test starts monkeypatching it).

**`ImageViewer`'s `restore_cb(rel, label) -> bool` / `on_restored(entry)`
are additions beyond the "steps_lookup(rel) -> list[(label, Path)]"
2-tuple the section's PRESENCE/DISPLAY contract uses.** Actually
restoring a step needs the raw `JobTemp` step key and a `JobTemp`
instance — neither travels through a bare `(label, Path)` display
pair. Keeping `steps_lookup` itself pure display data (easy to fake in
tests, no `JobTemp` coupling) and adding one small extra callable for
the actual restore action was judged simpler than either (a) smuggling
the step key into the display tuple, or (b) handing `ImageViewer` a
raw `JobTemp` reference and re-deriving everything `StepRestoreWindow`
already knows how to do. `SettingsMixin._image_viewer_restore_cb`
reverses the label back to the raw step key via `_STEP_LABEL_TO_KEY`
(`{v: k for k, v in JOBTEMP_STEP_LABEL.items()}` — safe: every
`JOBTEMP_STEP_LABEL` value is unique) before calling the shared
`_restore_step`.
`DocWindow`'s own, unrelated Fixer poll reads the SAME constant via a
deferred `import gui` rather than a module-level import specifically
to avoid the cycle `gui.dialogs` (needs `DocWindow`) <-> `gui.viewers`
(would need `AI_POLL_MS`) — see the module docstring.
