# Restore Viewers

**Script:** [Restore Viewers (script)](../restore_windows.py) ·
**Flow:** [diagram](../__flow/restore_windows.md)

## Purpose
The two RESTORE viewers and the pure stage list they render — one
cohesive pair: both show what an image looked like BEFORE a pipeline
step ran, and put it back. Split out of the former `gui/viewers.py`
(root Rule #20 god-file refactor, 2026-07-30).

- **`BeforeAfterWindow`** — a standalone tool job's before/after
  viewer (single-image Restore or whole-job RESTORE ALL). Since the
  AFTER of a BG removal/crop is TRANSPARENT where the background was
  cleared, every image with alpha is composited over a neutral
  checkerboard so the removed area visibly reads as removed rather
  than looking unchanged against the window's own background. A
  stacked single column inside a vertical `ScrollFrame`.
- **`_filmstrip_stages(temp, rel, live_path)`** — a PURE, Tk-free
  module function: the per-image pipeline-stage list, one
  `(label, path)` pair per named stage the job's temp-backup store
  actually kept (pipeline order: Original -> BG -> Crop -> Aspect ->
  Upscale -> Fixer, filtered to whichever backed `rel` up), followed
  by exactly one final `(STEP_RESTORE_CURRENT_LABEL, live_path)` entry
  for the CURRENT live file — that last entry carries no restore
  button, it already IS the live state. Shared with `ImageViewer`'s
  own Steps section (which drops that trailing "current" entry).
- **`StepRestoreWindow`** — the per-step restore filmstrip built from
  that list (GUI rework Phase 9): a HORIZONTAL `ScrollFrame`, one
  "Restore to here" button per stage. Clicking one restores that
  step's backup onto the live file and RE-RENDERS the whole filmstrip
  in place straight off disk — both the Current thumbnail and the
  remaining stage list — so a restore is immediately visible without
  closing/reopening the window, then notifies its caller
  (`on_restored`) to refresh the dashboard row's resolution/size. A
  known cosmetic gap (unfixed, tracked here rather than silently
  patched — root Rule #25): the dashboard row's badge dots are NOT
  retroactively recomputed after a restore; the restored file itself
  is always correct regardless.

Structurally the one real difference between the two windows: a
HORIZONTAL scroll frame for the filmstrip (pipeline stages read
left-to-right) versus `BeforeAfterWindow`'s stacked vertical one.

## Connections
### Uses
- [Painter (folder)](../../painter/___painter.md) — `config`
  (`JOBTEMP_STEP_LABEL`, `STEP_RESTORE_CURRENT_LABEL`)
- [Viewer Shared Rules](viewer_shared.md) — the screen clamps and
  `_restore_step` (the ONE `JobTemp.restore_to` call site)
- [Dashboard Support Helpers](dash_helpers.md) — `_scaled_photo`
- [Scroll](scroll.md) — `ScrollFrame` (vertical for before/after,
  horizontal for the filmstrip)
- [Theme](theme.md) — `THEME_TOPLEVELS`, `skin_toplevel`
- [Themed Widget Toolkit](widgets.md) — `rounded_button`

### Used by
- [GUI (folder)](../___gui.md) — `__init__.py` re-exports
  `BeforeAfterWindow`, `StepRestoreWindow`, `_filmstrip_stages`
- [Dashboard Job Panel Base + Site Panel](dash_panels.md) —
  `DashPanel` opens `StepRestoreWindow` through a deferred
  `import gui; gui.StepRestoreWindow(...)`, so
  `monkeypatch.setattr(gui, "StepRestoreWindow", fake)` keeps working
- [Tool + AI-Checker Dashboard Panels + Grid](tool_dash.md) —
  `ToolPanel`'s `BeforeAfterWindow` calls are a plain real-path import
  (`from .restore_windows import BeforeAfterWindow`) — no test
  monkeypatches it
- [Settings Mixin](app_settings.md) — `_image_viewer_steps_lookup`
  calls `_filmstrip_stages` directly (real-path import) to back
  `ImageViewer`'s Steps section, dropping its trailing "current" entry

## Classes
### BeforeAfterWindow
See the Purpose section above. `_add_pair` composites each Before/
After image over a checkerboard via `_scaled_photo(..., on_checker=True)`.

### StepRestoreWindow
See the Purpose section above; built from `_filmstrip_stages`.
`_render` rebuilds every stage block from the CURRENT on-disk state —
called at construction and again after each restore.

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
