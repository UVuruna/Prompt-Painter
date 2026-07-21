# Dashboard Support Helpers

**Script:** [Dashboard Support Helpers (script)](dash_helpers.py)

## Purpose
Small, mostly-Tk-facing helpers shared by two or more dashboard
surfaces — pulled out of `gui/__init__.py` (root Rule #20 god-file
refactor, step 3/8): the badge-dot `PhotoImage` cache (`badge_dots`,
PIL-drawn since Tk 8.6 on Windows renders colour emoji as identical
monochrome circles), the tool-panel timing summary line
(`fmt_time_summary`), the AI-check report/tag helpers shared by
`AiCheckPanel` and `DashPanel` (`ai_check_doc_md`, `ai_check_image_file`,
`ai_check_tag`), the shared `Treeview` builder behind every job-panel
table (`build_job_tree`), and the before/after viewer's
transparency-checkerboard compositing helpers (`_checkerboard`,
`_has_alpha`, `_scaled_photo`).

## Connections

### Uses
- [Painter (folder)](../painter/___painter.md) — `config`
  (`BADGE_DOT_*`, `BADGES`, `CHECKER_*`, `fmt_op_duration`); `ai`
  (`ai.flag_file`, imported lazily inside `ai_check_image_file`)
- [Theme (script)](theme.md) — `TOOL_CHANGED_TAG`/`TOOL_SKIP_TAG`
  (the row-tag names), `skin_tree` (theme-following Treeview rows)

### Used by
- [GUI (folder)](___gui.md) — `__init__.py` still re-exports the full
  API (`gui.badge_dots`, `gui.build_job_tree`, `gui._checkerboard`,
  ...) for external tests
- [Dashboard Job Panel Base + Site Panel](dash_panels.md) — `JobPanel`/
  `DashPanel` import `ai_check_doc_md`/`ai_check_image_file`/
  `ai_check_tag`/`badge_dots` directly (real-path, post god-file split)
- [Tool + AI-Checker Dashboard Panels + Grid](tool_dash.md) —
  `ToolPanel`/`AiCheckPanel` import `build_job_tree`/`fmt_time_summary`/
  `ai_check_tag`/`ai_check_doc_md`/`ai_check_image_file` directly
- [Read-Only Viewers](viewers.md) — `DocWindow`/`BeforeAfterWindow`
  import `_scaled_photo` directly (which itself calls `_checkerboard`/
  `_has_alpha`, kept private to this module)

## Design Decisions
- **`_BADGE_DOTS` stays a private module-level cache, not re-exported.**
  It is a process-lifetime `PhotoImage` cache keyed by badge-key
  combination, read and written ONLY from inside `badge_dots` itself
  — no other module or test ever needs to reach into it directly.
