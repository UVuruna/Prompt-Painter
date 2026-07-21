# Tool Jobs Mixin

**Script:** [Tool Jobs Mixin (script)](app_tools.py)

## Purpose
`ToolJobsMixin` — the fourth of `PainterGui`'s five mixins (root Rule
#20 god-file refactor, step 7/8; see [GUI (folder)](___gui.md) and
[App (composition)](app.md)). Owns every standalone-tool job's Start/
worker/Stop — BG removal / Crop / Upscale / Aspect ratio, all four
panel-driven since GUI rework Phase 14 (`_start_tool_from_panel`/
`_launch_tool_worker`/`_run_tool_job`/`_stop_tool`, ONE shared tail —
Rule #5) — and the AI image checker's own job, which shares the same
one-job-per-kind/JobTemp-free shape but is spawned by hand
(`_start_ai_check`/`_run_ai_check_job`), plus its two report-viewer
actions (`_resend_flagged` — maps flagged images back to a queued
site's Select-window ticks and starts a re-send run via
`SiteJobsMixin._start_site`; `_clear_ai_flags`).

No `__init__` here — every attribute it reads (`self._tool_workers`,
`self._job_temps`, `self._tool_panels`, `self.panels`, `self.
_paused`, `self._stop_events`, `self._pause_events`, ...) is set by
`BuildMixin.__init__`.

## Connections

### Uses
- [Painter (folder)](../painter/___painter.md) — `config`
  (`AI_CALL_PAUSE_S`, `AI_CHECK_INSTRUCTIONS`, `GEMINI_VISION_MODEL`,
  `JOB_LABEL`); `jobtemp` (`JobTemp`, `measure`); `runner`
  (`wait_while_paused`, imported locally); `ai` (imported locally, the
  checker's vision calls + the flagged-image re-send planner)
- [Pure Logic (script)](logic.md) — `_filter_files`

### Used by
- [App (composition)](app.md) — `PainterGui(..., ToolJobsMixin, ...)`
- [View Mixin](app_views.md) — `_apply_running_layout`/
  `_sync_running_state` are called from here on every tool-job state
  change
- [Site Jobs Mixin](app_jobs.md) — `_resend_flagged` calls
  `SiteJobsMixin._start_site`

## Design Decisions
- **`AI_CHECK_LOG_EVERY` lives here, not in `Build Mixin`.** It is
  read by exactly one method, `_run_ai_check_job`'s own progress-log
  cadence — a module constant beside its one caller, not a
  cross-mixin re-export nothing else needs (Rule #5).
- **No `__init__` here (Rule #5)** — see [Build Mixin](app_build.md).
- **`_resend_flagged`/`_clear_ai_flags` live here, not in
  `SiteJobsMixin`, even though `_resend_flagged` calls
  `_start_site`.** Both are wired directly to `AiCheckPanel`'s own
  buttons (`on_resend=self._resend_flagged`, `on_clear=self.
  _clear_ai_flags` in `BuildMixin._build_views`) — they are AI-checker
  report actions first, and reach the site-starting machinery only as
  their LAST step, the same way `_start_tool_from_panel`/
  `_start_ai_check` reach dashboard/JobTemp machinery that also lives
  in other mixins.
