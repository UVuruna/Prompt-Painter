# Dashboard Job Panel Base + Site Panel

**Script:** [Dashboard Job Panel Base + Site Panel (script)](../dash_panels.py) ·
**Flow:** [diagram](../__flow/dash_panels.md)

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

## The tree's five columns (owner 2026-08-11)

`Name | Done | Time | Res | Size | Check` — down from seven.

- **Time is the ONE time column at every level.** An image row carries
  the SUM of the AI's generation and our own processing (the former
  separate `AI` + `Ours` columns), so the column reads top to bottom as
  one quantity instead of three columns saying the same thing at three
  levels. It shows `107s…` from `item_progress` and becomes the sum on
  `item_done`.
- **Res is the DELIVERED resolution only.** The old
  `1254x1254→1254x1246` pair is gone from the tree; the full processing
  history lives on in the report txt, where it belongs.
- **Widths follow content; Name takes the rest.** `_autosize_columns`
  measures every value column's widest real content in the tree's own
  font (never below its configured floor) and `#0` alone has
  `stretch=True` — THE SPACE & LEGIBILITY LAW: before this the widths
  were fixed guesses and Name was capped at 230px, so long collection
  and folder paths were cut while the panel held empty space beside
  them.
- **The sixth badge dot.** `item_checked` adds a teal `check` dot via
  `_add_badge`, which rebuilds the row's dot strip from the keys kept
  in `_badge_keys` (the strip is a rendered image, not a list). The dot
  asserts only that the check RAN — the verdict stays in the Check
  column, so an errored check still earns it.

Every image row remembers `rel` — the ACTUAL saved out-relative path
off its `item_progress` event (owner 2026-07-27: a ticked redo lands
as a `_vN` version file) — in `_node_info`; "Steps…" and
`refresh_image_row` resolve the live file through it, falling back to
the canonical `dest_for` only for rows that never saved (a REFUSED
row). "Check…" already follows the checker's own `rel` result key.

**F3 (owner 2026-07-29) — Start never wipes.** `begin_run` prepares a
new run while KEEPING everything already shown: the table and counters
SURVIVE every restart (manual or quota auto-restart), with the new
pending count stacking on top of what already finished. `clear()` is
the ONLY full wipe (tree, counters, checker results) — behind the
panel header's explicit Clear button, confirmed with a dialog, never
implicit. A refused drop path counts ONCE per panel lifetime (not once
per restart — the "176/161 over-count" fix), tracked in
`_refused_drops`, which `clear()` resets but `begin_run` does not.

## Connections

### Uses
- [Painter (folder)](../../painter/___painter.md) — `config` (`JOB_LABEL`,
  `JOB_LOGO`, `job_color_pair`, `theme_pair`, `BADGES`,
  `JOBTEMP_CAP_BANNER_TEXT`, `dest_for`, `fmt_duration`, `fmt_size`,
  `badge_keys_for`); `jobtemp` (the `JobTemp` type only, in a string
  annotation)
- [Dashboard Support Helpers](dash_helpers.md) — `ai_check_doc_md`/
  `ai_check_image_file`/`ai_check_tag`/`badge_dots`
- [Icons](icons.md) — `icon` (the header logo)
- [Pure Logic Helpers](logic.md) — `_scope_stats`/`_STAT_KEYS`
- [Themed Widget Toolkit](widgets.md) — `ctk_font`/`tk_font`/
  `folder_of`/`rounded_button`
- [Doc Window](doc_window.md) — `DocWindow` (`_show_check`) and
  [Restore Viewers](restore_windows.md) — `StepRestoreWindow`
  (`_show_steps`) — both through a DEFERRED `import gui`, never a
  module-level import (see Design Decisions)

### Used by
- [GUI (folder)](../___gui.md) — `__init__.py` re-exports `JobPanel`/
  `DashPanel` for external tests
- [Build Mixin](app_build.md) — `BuildMixin.__init__` constructs one
  `DashPanel` per generation site (`self.panels["chatgpt"]`/
  `self.panels["gemini"]`/`self.panels["api_image"]`)
- [Site Jobs Mixin](app_jobs.md) — the queue-pump dispatch loop calls
  `panel.handle(event)` for every event the runner (and the parallel
  Checker AI) posts; also drives `finish()`/`reset_finished()`/the
  state line directly on quota-restart/Stop
- [Checker/Fixer Mixin](app_checker_fixer.md) — posts the parallel
  Checker AI's `item_checking`/`item_checked` events onto the SAME
  worker queue `DashPanel.handle` consumes; reads `self.panels["aicheck"]`
  for the standalone checker's own panel
- [Tool Dashboard Panels](../tool_dash.py) — `ToolPanel`/`AiCheckPanel`
  subclass `JobPanel` (a real-path `from .dash_panels import JobPanel`)

## Classes

### JobPanel
Base for a per-job dashboard panel — see Purpose above. `self.jobtemp`
is declared here (not on a subclass) since both `DashPanel` and
`ToolPanel` need a per-step backup store; `AiCheckPanel` simply never
populates it. `_ensure_root`/`_ensure_folder` are the shared
folder>image tree-node plumbing for the FOLDER-based panels
(`ToolPanel`, `AiCheckPanel`) — `DashPanel` builds its own
theme-keyed collection>folder>image nodes and never calls these.

### DashPanel
One generation site's live view — see Purpose above.

#### Key methods
- `begin_run()` / `clear()` — the F3 append-vs-wipe split (see
  Purpose above).
- `handle(event)` — the single entry point for every runner and
  parallel-checker event (`sheet_start`/`item_start`/`item_progress`/
  `item_done`/`item_refused`/`item_retry`/`item_nudge`/
  `item_checking`/`item_checked`/`sheet_done`/`over_cap`/`item_fixed`).
- `_show_steps()` / `_show_check()` — open the per-step restore
  filmstrip / the parallel checker's report for the focused row.
- `refresh_image_row()` — re-reads one row's resolution/size off disk
  after a restore or an auto-fix overwrite.

## Design Decisions
- **`DocWindow`/`StepRestoreWindow` are reached through a deferred
  `import gui` inside the method body, never a top-of-module `from
  .viewers import ...`.** Several tests (`test_gui_checker.py`,
  `test_gui_fixer.py`, `test_gui_pipeline.py`) do
  `monkeypatch.setattr(gui, "DocWindow", fake)` /
  `monkeypatch.setattr(gui, "StepRestoreWindow", fake)` and expect
  `DashPanel._show_check`/`_show_steps` to call the PATCHED class — a
  bare import would bind the real class at import time and never see
  the patch. This mirrors the established idiom `gui.api_panel`'s
  `_arm_probe_poll` already uses for the identical reason.
- **`JOB_PANEL_BANNER_WRAP_PX`/`DASH_CHECK_COL_PX` live here, not in
  `gui/__init__.py`.** Both are private layout constants used only by
  `JobPanel`/`DashPanel`'s own widget construction; no test or sibling
  module reaches them by name, so they moved with their one caller
  instead of staying behind as re-exports nothing needs.

## 2026-08-11 — the refusal's WHY

`DashPanel._refused_info` (drop path -> `{"reason", "diagnosis"}`)
keeps each `item_refused` event's actual refusal message + the site's
diagnostic answer — panel-lifetime scoped like `_refused_drops`, but
stored even on the duplicate-refusal early-out so a rerun's fresher
reason replaces the stale one. Consumed by `app_settings.py`'s
`_image_viewer_entries` (the double-click viewer shows it where the
image would be).

## 2026-08-11b — Stop + Pause in the dashboard header

`JobPanel` accepts `on_stop` (and DashPanel forwards `on_pause`/
`on_stop`): the three gen/API DashPanel slots now carry Stop
(danger-outline) + Pause buttons in the header — the SAME
`_stop_site`/`_toggle_pause_job` the AgentPanel/ApiPanel buttons call,
so either surface works and labels stay in sync via `set_paused`.
`finish()` swaps Stop/Pause for Close; `reset_finished()` swaps back.
