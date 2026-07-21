# Dashboard Job Panel Base + Site Panel

**Script:** [Dashboard Job Panel Base + Site Panel (script)](dash_panels.py)

## Purpose
`JobPanel` and `DashPanel`, pulled out of `gui/__init__.py` (root Rule
#20 god-file refactor, step 6/8). `JobPanel` is the shared base every
per-JOB dashboard panel builds on — the coloured header (logo + job
name), the muted state line, the CLOSE button revealed on finish, the
optional Pause/Resume button, the loud persistent cap-warning strip,
and the folder>image tree-node plumbing (`_ensure_root`/
`_ensure_folder`) shared with `gui.tool_dash`'s `ToolPanel`/
`AiCheckPanel`. `DashPanel` is one generation site's own live view:
whole-task + current-collection progress bars, the two-scope
(this-collection / whole-run) stats table with its collapsible
Average breakdown, the collections history tree (collection > folder
> image), the per-step restore viewer ("Steps…") and the parallel
Checker AI's per-row report ("Check…").

## Connections

### Uses
- [Painter (folder)](../painter/___painter.md) — `config` (`JOB_LABEL`,
  `JOB_LOGO`, `job_color_pair`, `theme_pair`, `BADGES`,
  `JOBTEMP_CAP_BANNER_TEXT`, `dest_for`, `fmt_duration`, `fmt_size`,
  `badge_keys_for`); `jobtemp` (the `JobTemp` type only, in a string
  annotation)
- [Dashboard Support Helpers](dash_helpers.md) — `ai_check_doc_md`/
  `ai_check_image_file`/`ai_check_tag`/`badge_dots`
- [Icon Loading + Switch Art](icons.md) — `icon` (the header logo)
- [Pure Logic (script)](logic.md) — `_scope_stats`/`_STAT_KEYS`
- [Themed Widget Toolkit](widgets.md) — `ctk_font`/`tk_font`/
  `folder_of`/`rounded_button`
- [Viewers (script)](viewers.md) — `DocWindow` (`_show_check`),
  `StepRestoreWindow` (`_show_steps`) — both through a DEFERRED
  `import gui`, never a module-level import (see Design Decisions)

### Used by
- [GUI (folder)](___gui.md) — `__init__.py` re-exports `JobPanel`/
  `DashPanel` for `PainterGui` (which constructs one `DashPanel` per
  generation site) and for external tests
- [Tool Dashboard Panels](tool_dash.py) — `ToolPanel`/`AiCheckPanel`
  subclass `JobPanel` (a real-path `from .dash_panels import JobPanel`)

## Design Decisions
- **`DocWindow`/`StepRestoreWindow` are reached through a deferred
  `import gui` inside the method body, never a top-of-module `from
  .viewers import ...`.** Several tests (`test_gui_checker.py`,
  `test_gui_fixer.py`, `test_gui_pipeline.py`) do
  `monkeypatch.setattr(gui, "DocWindow", fake)` /
  `monkeypatch.setattr(gui, "StepRestoreWindow", fake)` and expect
  `DashPanel._show_check`/`_show_steps` to call the PATCHED class — a
  bare import would bind the real class at import time and never see
  the patch. This mirrors the established idiom `gui.viewers`'s own
  `AI_POLL_MS` read and `gui.api_panel`'s `_arm_probe_poll` already use
  for the identical reason.
- **`JOB_PANEL_BANNER_WRAP_PX`/`DASH_CHECK_COL_PX` live here, not in
  `gui/__init__.py`.** Both are private layout constants used only by
  `JobPanel`/`DashPanel`'s own widget construction; no test or sibling
  module reaches them by name, so they moved with their one caller
  instead of staying behind as re-exports nothing needs.
