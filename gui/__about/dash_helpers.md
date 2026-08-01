# Dashboard Support Helpers

**Script:** [Dashboard Support Helpers (script)](../dash_helpers.py)

**Tier: Standard, not Trivial** — every helper here is shared plumbing
behind two or more dashboard surfaces (Rule #5: one home for identical
logic each surface would otherwise re-derive), but none of them is an
algorithm with real branching worth a `__flow` diagram of its own —
the badge-dot cache is a lookup, the checkerboard compositor is
straight-line PIL drawing, the report/tag helpers are string/dict
formatting.

## Purpose
Small, mostly-Tk-facing helpers shared by two or more dashboard
surfaces — pulled out of `gui/__init__.py` (root Rule #20 god-file
refactor, step 3/8): the badge-dot `PhotoImage` cache (`badge_dots`,
PIL-drawn since Tk 8.6 on Windows renders colour emoji as identical
monochrome circles — a step earns its dot only when it actually
CHANGED the file, never on a no-op), the tool-panel timing summary
line (`fmt_time_summary`), the AI-check report/tag helpers shared by
`AiCheckPanel` and `DashPanel` (`ai_check_doc_md`, `ai_check_image_file`,
`ai_check_tag`), the shared `Treeview` builder behind every job-panel
table (`build_job_tree`), and the before/after viewer's
transparency-checkerboard compositing helpers (`_checkerboard`,
`_has_alpha`, `_scaled_photo`) — a BG-removal/crop AFTER image is
TRANSPARENT where the background was cleared, so `_scaled_photo`'s
`on_checker=True` path composites any image WITH ALPHA over a neutral
checkerboard so the removed area visibly reads as removed rather than
looking unchanged.

## Connections

### Uses
- [Painter (folder)](../../painter/___painter.md) — `config`
  (`BADGE_DOT_*`, `BADGES`, `CHECKER_*`, `fmt_op_duration`); `ai`
  (`ai.flag_file`, imported lazily inside `ai_check_image_file`)
- [Theme Engine](theme.md) — `TOOL_CHANGED_TAG`/`TOOL_SKIP_TAG`
  (the row-tag names), `skin_tree` (theme-following Treeview rows)

### Used by
- [GUI (folder)](../___gui.md) — `__init__.py` still re-exports the
  full API (`gui.badge_dots`, `gui.build_job_tree`, `gui._checkerboard`,
  ...) for external tests
- [Dashboard Job Panel Base + Site Panel](dash_panels.md) — `JobPanel`/
  `DashPanel` import `ai_check_doc_md`/`ai_check_image_file`/
  `ai_check_tag`/`badge_dots` directly (real-path, post god-file split)
- [Tool + AI-Checker Dashboard Panels + Grid](tool_dash.md) —
  `ToolPanel`/`AiCheckPanel` import `build_job_tree`/`fmt_time_summary`/
  `ai_check_tag`/`ai_check_doc_md`/`ai_check_image_file` directly
- [Doc Window](doc_window.md) / [Restore Viewers](restore_windows.md)
  / [Image Viewer](image_viewer.md) — all import `_scaled_photo`
  directly (which itself calls `_checkerboard`/`_has_alpha`, kept
  private to this module); the image viewer also imports
  `ai_check_doc_md`

## Design Decisions
- **`_BADGE_DOTS` stays a private module-level cache, not re-exported.**
  It is a process-lifetime `PhotoImage` cache keyed by badge-key
  combination, read and written ONLY from inside `badge_dots` itself
  — no other module or test ever needs to reach into it directly.
