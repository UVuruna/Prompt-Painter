# Tool + AI-Checker Dashboard Panels + Grid

**Script:** [Tool + AI-Checker Dashboard Panels + Grid (script)](tool_dash.py)

## Purpose
`ToolPanel`, `AiCheckPanel` and `DashGrid`, pulled out of
`gui/__init__.py` (root Rule #20 god-file refactor, step 6/8).
`ToolPanel` is one standalone in-place tool's (BG removal / Crop /
Upscale / Aspect ratio) live view — a progress bar, an aggregate
metric label, and a collection>folder>image table with striking
CHANGED rows and muted SKIPPED rows, plus the before/after viewer +
restore (whole job / one folder / one image). `AiCheckPanel` is the
standalone AI image checker's own dashboard panel — flagged/OK/error
counts, the defect viewer, and the "Send flagged to generator"/"Clear
flags" actions. `DashGrid` lays out every active job panel (both
these plus `DashPanel`) in a responsive up-to-6-cell grid, gen sites
first.

Both panels subclass `JobPanel` (`gui.dash_panels`) for the shared
header/close/pause chrome and the folder>image tree-node helpers.

## Connections

### Uses
- [Painter (folder)](../painter/___painter.md) — `config`
  (`GRID_COLS_BY_COUNT`, `JOB_LABEL`, `JOB_METRIC`, `JOB_ORDER`,
  `fmt_op_duration`, `fmt_pct`, `fmt_size`)
- [Dashboard Support Helpers](dash_helpers.md) — `ai_check_doc_md`/
  `ai_check_image_file`/`ai_check_tag`/`build_job_tree`/
  `fmt_time_summary`
- [Dashboard Job Panel Base + Site Panel](dash_panels.md) — `JobPanel`
  (the shared base, real-path import)
- [Theme (script)](theme.md) — `TOOL_CHANGED_TAG`/`TOOL_SKIP_TAG` (the
  changed/skipped row tags)
- [Viewers (script)](viewers.md) — `BeforeAfterWindow` (real-path,
  `ToolPanel`'s before/after viewer), `DocWindow` (`AiCheckPanel`'s
  defect viewer, through a DEFERRED `import gui` — see Design
  Decisions)
- [Themed Widget Toolkit](widgets.md) — `folder_of`/`rels_in_folder`/
  `rounded_button`

### Used by
- [GUI (folder)](___gui.md) — `__init__.py` re-exports `ToolPanel`/
  `AiCheckPanel`/`DashGrid` for `PainterGui` (which constructs one
  `ToolPanel` per standalone tool, one `AiCheckPanel`, and the shared
  `DashGrid`) and for external tests

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
