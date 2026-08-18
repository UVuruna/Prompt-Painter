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
  than looking unchanged against the window's own background. Each
  pair lays its Before and After SIDE BY SIDE (owner 2026-08-07), the
  pairs themselves stacked inside a vertical `ScrollFrame`.
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
left-to-right) versus `BeforeAfterWindow`'s vertical one (which
scrolls between PAIRS — each pair is itself horizontal).

## Connections
### Uses
- [Painter (folder)](../../painter/___painter.md) — `config`
  (`JOBTEMP_STEP_LABEL`, `STEP_RESTORE_CURRENT_LABEL`)
- [Viewer Shared Rules](viewer_shared.md) — the screen clamps and
  `_restore_step` (the ONE `JobTemp.restore_to` call site)
- [Dashboard Support Helpers](dash_helpers.md) — `_scaled_photo`
- [Scroll](scroll.md) — `ScrollFrame` (vertical for before/after,
  horizontal for the filmstrip)
- [Theme](theme.md) — `finish_toplevel` (the shared Toplevel setup
  ritual), `THEME_TOPLEVELS` (unregister on `<Destroy>`)
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
See the Purpose section above. Three collaborating methods own the
sizing:

- `_render(width)` rebuilds every pair's photos for a given window
  width. `_add_pair` builds one horizontal `row` holding two columns —
  Before left, After right — each scaled into
  `(avail - BEFORE_AFTER_COL_GAP_PX) // 2` wide AND a per-pair height
  `budget`, composited over a checkerboard via
  `_scaled_photo(..., on_checker=True, avail_h=budget, allow_upscale=True)`.
  With more than one pair the budget halves, so several pairs each keep
  a readable slice and the window scrolls between them.
- `_fit_to_content(width)` measures the laid-out content
  (`bar.winfo_reqheight() + scroll.body.winfo_reqheight() + chrome`) and
  sets the geometry to it, clamped to `DOC_MAX_FRAC` of the screen and
  to `DOC_MIN_H`.
- `_on_configure` / `_apply_resize` re-render the photos after a user
  resize — debounced `BEFORE_AFTER_RESIZE_DEBOUNCE_MS`, and only past a
  `BEFORE_AFTER_RESIZE_STEP_PX` width change, so a re-render cannot
  chase its own `<Configure>` events. `_apply_resize` deliberately does
  NOT call `_fit_to_content`: the user chose that frame size, only the
  pictures follow it.

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
**Before/after reads LEFT to RIGHT, not top to bottom** (owner
2026-08-07). Stacked vertically, a tall plate (the 1664x2550 Greek
alphabet sheet) pushed the After a full screen below the Before, so the
one comparison the window exists for could never be seen at once — the
owner had to scroll and remember. Side by side, each column takes half
the available width; the whole pair now fits in a 760x1382 window with
nothing clipped (THE SPACE & LEGIBILITY LAW: reflow before raising the
minimum).

**A window opens at the size of what is IN it, and a resize grows the
CONTENT** (owner 2026-08-07, stated after an independent grader failed
the first side-by-side pass at 4/10). The first fix laid the pair out
correctly but kept the old blind `screen_h * DOC_HEIGHT_FRAC` height, so
the 1664x2550 pair sat in the top third of a 1382px-tall window with
over half the frame empty — the owner's rule is that the elements must
never occupy less than 50 % of the window. Two consequences in the code:
`_scaled_photo` now fits BOTH axes (a width-only fit is what starved the
tall plate) and can upscale into its box, and the geometry is MEASURED
off the laid-out content instead of guessed from the screen. The same
pair now opens 760x730. `_on_configure` closes the other half of the
rule: enlarging the window re-renders the pictures at the new width
rather than adding dead space around them.

**Both windows' top bars wrap their hint/subtitle via
`gui.widgets.wrap_bar_label`** (2026-08-06, THE SPACE & LEGIBILITY LAW
rollout, `tests/test_layout_audit_tk.py`): `BeforeAfterWindow`'s own
PRODUCTION MULTI-mode subtitle and `StepRestoreWindow`'s own fixed hint
string are each long enough, on their own, to force the bar past
`DOC_MIN_W` — both now wrap into the bar's live remaining width instead of
widening the window.

**Why the two windows share a module.** They are the same
responsibility in two shapes — "show the earlier state of this image
and restore it" — over the same `JobTemp` backups and the same
`_filmstrip_stages` data. Splitting them further would produce two
~140-line files that always change together (Rule #20's
over-fragmentation warning).
