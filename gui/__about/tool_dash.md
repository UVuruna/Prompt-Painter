# Tool + AI-Checker Dashboard Panels + Grid

**Script:** [Tool + AI-Checker Dashboard Panels + Grid (script)](../tool_dash.py) ·
**Flow:** [diagram](../__flow/tool_dash.md)

## Purpose
`ToolPanel`, `AiCheckPanel` and `DashGrid`, pulled out of
`gui/__init__.py` (root Rule #20 god-file refactor, step 6/8).
`ToolPanel` is one standalone in-place tool's (BG removal / Crop /
Upscale / Aspect ratio) live view — a progress bar, an aggregate
metric label (BG removal = % removed pixels, Crop = % area reduction,
Upscale = % area increase, Aspect = % growth of the stretched axis),
a time label (total + average, both counting ONLY processed images —
skipped images add no time), and a collection>folder>image table with
striking CHANGED rows and muted SKIPPED rows. The dimensional tools
(Crop/Upscale/Aspect) show Before/After resolution columns; BG removal
DROPS those columns entirely since it changes ALPHA, not dimensions —
before==after resolution would be meaningless. Double-clicking an
image row opens a before/after viewer with Restore (reverts only it);
double-clicking a FOLDER node opens a viewer of just that folder's
changed images with RESTORE ALL (scoped to that folder only — a past
bug used to revert the WHOLE job on a folder click); double-clicking
the collection's top node opens ALL the job's changed images with a
whole-job RESTORE ALL.

`AiCheckPanel` is the standalone AI image checker's own dashboard
panel (the "aicheck" job slot — the DASHBOARD half only; the launch
surface, folder/files picker + Start/Pause/Stop, lives in
`ImageCheckerSettingsPanel` under `gui/tool_panels/`): a progress bar,
flagged/OK/error counts, and a folder>image table where FLAGGED rows
carry their defect count as the row metric, OK rows are muted, and API
failures count loudly as errors without killing the batch.
Double-clicking any checked row opens a defect-report viewer (a
`DocWindow`) with the parsed defects, the verbatim AI response, and
the image itself. Two panel actions: "Send flagged to generator"
re-queues each flagged image's own site with a note about the previous
attempt's flaws, and "Clear flags" wipes this run's entries from
`<out>/_state/ai_flags.json` — the panel never touches images or flags
itself, both actions go through GUI callbacks.

`DashGrid` lays out every active job panel (both these plus
`DashPanel`) — F4e (owner 2026-07-29): TWO display modes. GRID
(default) treats every card identically; the column count comes from
the WINDOW WIDTH against one card's `DASH_CARD_MIN_W` (1×N when very
narrow, up to `DASH_GRID_MAX_COLS` full-screen), re-flowing on a
debounced `<Configure>` (the old fixed per-active-count column table
is retired). SLIDER shows exactly ONE card at full width with a
prev/next arrow row above it — the owner flips modes from the top
strip's toggle (`set_mode`). Panels are added on job START and removed
on CLOSE, rendered in `JOB_ORDER`; a muted placeholder shows when no
job has run yet.

Both `ToolPanel` and `AiCheckPanel` subclass `JobPanel`
(`gui.dash_panels`) for the shared header/close/pause chrome and the
folder>image tree-node helpers.

## Connections

### Uses
- [Painter (folder)](../../painter/___painter.md) — `config`
  (`DASH_CARD_MIN_W`, `DASH_GRID_MAX_COLS`, `DASH_MODE_GRID`/
  `DASH_MODE_SLIDER`, `JOB_LABEL`, `JOB_METRIC`, `JOB_ORDER`,
  `fmt_op_duration`, `fmt_pct`, `fmt_size`)
- [Dashboard Support Helpers](dash_helpers.md) — `ai_check_doc_md`/
  `ai_check_image_file`/`ai_check_tag`/`build_job_tree`/
  `fmt_time_summary`
- [Dashboard Job Panel Base + Site Panel](dash_panels.md) — `JobPanel`
  (the shared base, real-path import)
- [Theme Engine](theme.md) — `TOOL_CHANGED_TAG`/`TOOL_SKIP_TAG` (the
  changed/skipped row tags)
- [Restore Viewers](restore_windows.md) — `BeforeAfterWindow`
  (real-path, `ToolPanel`'s before/after viewer)
- [Doc Window](doc_window.md) — `DocWindow` (`AiCheckPanel`'s defect
  viewer, through a DEFERRED `import gui` — see Design Decisions)
- [Themed Widget Toolkit](widgets.md) — `folder_of`/`rels_in_folder`/
  `rounded_button`

### Used by
- [GUI (folder)](../___gui.md) — `__init__.py` re-exports `ToolPanel`/
  `AiCheckPanel`/`DashGrid` for external tests
- [Build Mixin](app_build.md) — `BuildMixin.__init__` constructs one
  `ToolPanel` per standalone tool, the one `AiCheckPanel` (wired to
  `_resend_flagged`/`_clear_ai_flags`/`_build_fix_workers`), the shared
  `DashGrid`, and `attach()`es it to `self.panels`
- [View Mixin](app_views.md) — reads `_dashgrid.mode`/`.active()` and
  calls `set_mode()` for the top strip's grid↔slider toggle
- [Site Jobs Mixin](app_jobs.md) — `_dashgrid.add`/`.remove`/`.relayout`
  on a site/API-image job's start/close
- [Tool Jobs Mixin](app_tools.md) — `_dashgrid.add` on a standalone
  tool/checker job's start; `_resend_flagged`/`_clear_ai_flags` are its
  own methods, called back from `AiCheckPanel`
- [Checker/Fixer Mixin](app_checker_fixer.md) — `_build_fix_workers`
  (the Fixer AI's manual-button builder `AiCheckPanel._on_activate`
  calls back into)

## Classes

### ToolPanel
One in-place tool's live view — see Purpose above.

### AiCheckPanel
The standalone AI checker's dashboard panel — see Purpose above.

### DashGrid
The responsive job-panel layout (GRID/SLIDER) — see Purpose above.

## Design Decisions
- **`DocWindow` is reached through a deferred `import gui` inside
  `AiCheckPanel._on_activate`, never a top-of-module import.** Tests
  (`test_gui_checker.py`, `test_gui_fixer.py`) do
  `monkeypatch.setattr(gui, "DocWindow", fake)` and expect the PATCHED
  class — the same reasoning `gui.dash_panels.DashPanel._show_check`
  documents for its own identical case (Rule #5: one idiom, two call
  sites).
- **`BeforeAfterWindow` stays a plain real-path import.** Nothing in
  the test suite monkeypatches it (confirmed by grep across
  `tests/*.py` before this split) — `ToolPanel`'s three before/after
  call sites (`_show_image_beforeafter`/`_show_folder_beforeafter`/
  `_show_all_beforeafter`) bind the real class directly; adding a
  deferred `import gui` here would be unearned indirection with no
  test depending on it.
- **`AI_CHECK_DEFECT_COL_PX`/`AI_CHECK_TIME_COL_PX`/
  `AI_CHECK_FIRST_COL_PX` live here, not in `gui/__init__.py`.** All
  three are private tree-column widths used only by `AiCheckPanel`'s
  own construction; no test or sibling module reaches them by name.
