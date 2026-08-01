# Tool Jobs Mixin

**Script:** [Tool Jobs Mixin (script)](../app_tools.py) ·
**Flow:** [diagram](../__flow/app_tools.md)

## Purpose
`ToolJobsMixin` — the fifth of `PainterGui`'s six mixins (root Rule
#20 god-file refactor, step 7/8; see [GUI (folder)](../___gui.md) and
[App (composition)](../app.py)). Owns every standalone-tool job's Start/
worker/Stop — BG removal / Crop / Upscale / Aspect ratio, all four
panel-driven since GUI rework Phase 14 (`_start_tool_from_panel`/
`_launch_tool_worker`/`_run_tool_job`/`_stop_tool`, ONE shared tail —
Rule #5) — and the AI image checker's own job, which shares the same
one-job-per-kind shape but has no JobTemp/engine-callable to share with
`_run_tool_job`, so it is spawned by hand (`_start_ai_check`/
`_run_ai_check_job`), plus its two report-viewer actions
(`_resend_flagged` — maps flagged images back to a queued site's
Select-window ticks and starts a re-send run via
`SiteJobsMixin._start_site`; `_clear_ai_flags`).

**F6 (REWORK.md, owner E2): the AI checker's OPTIONAL second input.**
`ImageCheckerSettingsPanel.sheets_path()` may point at a prompt-sheet
`.md` FILE or FOLDER; when given, `_sheet_prompt_map` builds a
`drop_path -> prompt` map (walking a folder via `config.iter_md_files`,
mirroring the Collections queue's own "Add folder…") and
`_run_ai_check_job` checks ONLY the images whose reversed drop path
(`ai.drop_and_site_for`) matches an entry — WITH that entry's own
prompt — logging the unmatched count rather than silently truncating.
`None` (the default) keeps the pre-F6 behavior: every image gets a
quality-only check.

No `__init__` here — every attribute it reads (`self._tool_workers`,
`self._job_temps`, `self._tool_panels`, `self.panels`, `self.
_paused`, `self._stop_events`, `self._pause_events`, ...) is set by
`BuildMixin.__init__`.

## Connections

### Uses
- [Painter (folder)](../../painter/___painter.md) — `config`
  (`AI_CALL_PAUSE_S`, `AI_CHECK_INSTRUCTIONS`, `GEMINI_VISION_MODEL`,
  `JOB_LABEL`, `iter_md_files`); `jobtemp` (`JobTemp`, `measure`);
  `runner` (`wait_while_paused`, imported locally); `ai` (imported
  locally — the checker's vision calls + the flagged-image re-send
  planner); `sheet_parser` (`SheetError`, `parse_sheet`, local to
  `_sheet_prompt_map`)
- [Pure Logic](logic.md) — `_filter_files`

### Used by
- [App (composition)](../app.py) — `PainterGui(..., ToolJobsMixin, ...)`
- [View Mixin](app_views.md) — `_apply_running_layout`/
  `_sync_running_state` are called from here on every tool-job state
  change
- [Site Jobs Mixin](app_jobs.md) — `_resend_flagged` calls
  `SiteJobsMixin._start_site`

## Classes

### ToolJobsMixin
Key methods: `_start_tool_from_panel`/`_launch_tool_worker`/
`_run_tool_job`/`_stop_tool` (the four standalone tools' shared
Start/worker/Stop tail), `_start_ai_check`/`_run_ai_check_job`
(the AI checker's own hand-spawned job), `_sheet_prompt_map`
(module-level, F6's prompt-match lookup builder), `_resend_flagged`,
`_clear_ai_flags`.

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
- **`_run_tool_job`/`_run_ai_check_job` each thread a REAL
  `stop_event` into `wait_while_paused`** (GUI rework Phase 14/15,
  closing this mixin's own previously-flagged gap) — a Stop wins over
  a pending Pause instead of hanging the worker until Resume, mirroring
  `run_sheet`'s own `should_stop` contract exactly.
- **"Changed" keys ONLY on the engine actually rewriting the file**
  (a `"done"` status), never on the measured metric size — a 3px crop
  or a small BG clear is a genuine, restorable change even though its
  percentage rounds to nothing, so its backup and before/after must
  survive. A true no-op returns `"nothing"` and its backup is dropped
  right back (`temp.drop(rel)`).
