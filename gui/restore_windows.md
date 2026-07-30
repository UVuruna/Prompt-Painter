# Restore Viewers

**Script:** [Restore Viewers (script)](restore_windows.py)

## Purpose
The two RESTORE viewers and the pure stage list they render — one
cohesive pair: both show what an image looked like BEFORE a pipeline
step ran, and put it back. Split out of `gui/viewers.py` (root
Rule #20 god-file refactor, 2026-07-30).

- **`BeforeAfterWindow`** — a standalone tool job's before/after
  viewer (single-image Restore or whole-job RESTORE ALL), a stacked
  single column inside a vertical `ScrollFrame`.
- **`_filmstrip_stages(temp, rel, live_path)`** — the pure, Tk-free
  per-image pipeline-stage list: one `(label, path)` pair per named
  backed-up stage, oldest first, ending with the current live file.
  Shared with `ImageViewer`'s own Steps section (which drops the
  trailing "current" entry).
- **`StepRestoreWindow`** — the per-step restore filmstrip built from
  that list (GUI rework Phase 9): a HORIZONTAL `ScrollFrame` with a
  **Restore to here** button per stage.

Both windows size themselves off the shared
[Viewer Shared Rules](viewer_shared.md) clamps and own only their two
private width/thumbnail constants (`BEFORE_AFTER_*`,
`STEP_RESTORE_*`, Rule #4).

## Connections

### Uses
- [Painter (folder)](../painter/___painter.md) — `config`
  (`JOBTEMP_STEP_LABEL`, `STEP_RESTORE_CURRENT_LABEL`)
- [Viewer Shared Rules](viewer_shared.md) — the screen clamps and
  `_restore_step` (the ONE `JobTemp.restore_to` call site)
- [Dashboard Support Helpers](dash_helpers.md) — `_scaled_photo`
- [Scroll (script)](scroll.py) — `ScrollFrame` (vertical for
  before/after, horizontal for the filmstrip)
- [Theme (script)](theme.py) — `THEME_TOPLEVELS`, `skin_toplevel`
- [Themed Widget Toolkit](widgets.md) — `rounded_button`

### Used by
- [GUI (folder)](___gui.md) — `__init__.py` re-exports
  `BeforeAfterWindow`, `StepRestoreWindow`, `_filmstrip_stages`
- [Dashboard Job Panel Base + Site Panel](dash_panels.md) —
  `DashPanel` opens `StepRestoreWindow` through a deferred
  `import gui; gui.StepRestoreWindow(...)`, so
  `monkeypatch.setattr(gui, "StepRestoreWindow", fake)` keeps working
- [Tool + AI-Checker Dashboard Panels + Grid](tool_dash.md) —
  `ToolPanel`'s `BeforeAfterWindow` calls are a plain real-path import
  (no test monkeypatches it)
- [Settings Mixin](app_settings.md) — `_filmstrip_stages` backs
  `ImageViewer`'s `steps_lookup`

## Classes

### BeforeAfterWindow
See the Purpose section above.

### StepRestoreWindow
See the Purpose section above; built from `_filmstrip_stages`.

## Functions

### `_filmstrip_stages(temp, rel, live_path)`
Pure, Tk-free — see the function's own docstring for the exact
ordering contract `StepRestoreWindow._render` and
`SettingsMixin._image_viewer_steps_lookup` both rely on.

## Design Decisions
**Why the two windows share a module.** They are the same
responsibility in two shapes — "show the earlier state of this image
and restore it" — over the same `JobTemp` backups and the same
`_filmstrip_stages` data. Splitting them further would produce two
~140-line files that always change together (Rule #20's
over-fragmentation warning).
