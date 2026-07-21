# Site Jobs Mixin

**Script:** [Site Jobs Mixin (script)](app_jobs.py)

## Purpose
`SiteJobsMixin` — the third of `PainterGui`'s six mixins (root Rule
#20 god-file refactor, step 8/8; see [GUI (folder)](___gui.md) and
[App (composition)](app.md)). Owns the two browser-driven SITE jobs
(ChatGPT/Gemini) plus the paid-API image job — all three drive through
the SAME generalized run loop (`_start_site`/`_start_api_image`/
`_drive_site`/`_stop_site`), the shared worker-queue pump
(`_drain_queue`/`_dispatch`), the per-job Pause toggle
(`_toggle_pause_job`, shared by every `JOB_ORDER` kind, not only
sites) and dashboard-panel close (`_close_panel`/`_tool_panel_key`),
the quota auto-restart timers (`_handle_terminal`/`_tick_restart`/
`_cancel_restart`/`_auto_restart`), and the per-site post-save pipeline
composer (`_compose_post_save` — BG→Crop→Aspect→Upscale, shared by
sites and the API-image job via its own panel).

The parallel Checker AI and the Fixer AI used to live here too — this
module had grown past the ~1000-line Rule #20 budget, so step 8/8
split them out into [Checker/Fixer Mixin](app_checker_fixer.md)'s own
`CheckerFixerMixin`. `_dispatch` below still calls
`self._maybe_spawn_checker`/`self._maybe_spawn_fixer` exactly as
before — both resolve through the shared `PainterGui` MRO onto that
sibling mixin.

No `__init__` here — every attribute it reads (`self._running`, `self.
_workers`, `self._stop_events`, `self._pause_events`, `self.
_job_temps`, `self.agents`, `self.panels`, `self._dashgrid`, ...) is
set by `BuildMixin.__init__`.

## Connections

### Uses
- [Painter (folder)](../painter/___painter.md) — `config`
  (`AI_IMAGE_GATE_MESSAGE`, `CDP_URL`, `SITES`, `TIMING`,
  `prompt_suffix`, `tile_for_kind`); `aspect` (`change_aspect`);
  `jobtemp` (`JobTemp`); `driver`/`runner`/`chrome` (all imported
  LOCALLY inside the methods that use them — `_start_site`/
  `_drive_site` — never at module level, matching the original file's
  own lazy-import shape)
- [API Panel](api_panel.md) — `ApiImageAdapter` (the API-image job's
  `SiteDriver`-shaped stand-in)
- [Pure Logic (script)](logic.md) — `_gate_and_upscale` (through a
  DEFERRED `import gui`, see Design Decisions), `_run_pipeline_steps`

### Used by
- [App (composition)](app.md) — `PainterGui(..., SiteJobsMixin, ...)`
- [View Mixin](app_views.md) — `_sync_running_state`/
  `_apply_running_layout` are called from here on every job-state
  change
- [Checker/Fixer Mixin](app_checker_fixer.md) — `_maybe_spawn_checker`/
  `_maybe_spawn_fixer` are called from `_dispatch` here, resolved
  through the shared `PainterGui` MRO
- [Tool Jobs Mixin](app_tools.md) — `_resend_flagged` calls
  `_start_site`; both mixins share `_toggle_pause_job`/`_tool_panel_
  key`'s generic per-kind dispatch

## Design Decisions
- **`_compose_post_save`'s `post_save` closure reaches
  `_gate_and_upscale` through a deferred `import gui`, not a top-level
  `from .logic import _gate_and_upscale`.**
  `tests/test_gui_pipeline.py::test_compose_post_save_all_four_on_
  orders_bg_crop_aspect_upscale` does `monkeypatch.setattr(gui,
  "_gate_and_upscale", fake)` and expects the closure built by
  `_compose_post_save` to call the PATCHED function — a real-path
  import would bind the function at `app_jobs.py`'s OWN import time,
  which the test's patch on the `gui` package object would never
  reach. This is the SAME late-binding idiom already used throughout
  `gui/` for `DocWindow`/`StepRestoreWindow`/`_snapshot_overlay`/
  `_fade_out_overlay` (see [GUI (folder)](___gui.md)) — the split just
  added one more caller to the list, discovered by running the full
  test suite after the mechanical move (spotted, not guessed).
- **No `__init__` here (Rule #5)** — see [Build Mixin](app_build.md).
- **`_close_panel`/`_tool_panel_key` live here, not in `ToolJobsMixin`
  or `ViewMixin`.** Both are read by `_dispatch`'s `__tool_done__`/
  `__worker_done__` branches (this mixin) and by `_toggle_pause_job`
  (also this mixin) far more than by anything in `ToolJobsMixin` — the
  one exception (`ToolJobsMixin`'s own worker-done handling) reaches
  them the normal cross-mixin way, `self._close_panel(...)`.
- **`_update_status`/the quota auto-restart timers live here, not in
  `ViewMixin`.** Both are pure SITE/job-state bookkeeping (which keys
  are running, a pending restart's countdown) with no view-switching
  logic of their own — `_handle_terminal` is only ever invoked from
  `_drive_site`'s own `TerminalState` handling, in this same mixin.
- **Step 8/8 — the Checker/Fixer split line.** Everything up to and
  including `_dispatch` stayed here; the split point is the exact
  boundary between `_dispatch` (still calling into the checker/fixer
  by name) and the checker/fixer's OWN methods, which never call back
  into anything `SiteJobsMixin`-specific beyond generic `self.`
  attributes both mixins already share (`self.agents`, `self.panels`,
  `self._job_temps`, `self._q`, `self._running`, `self._log`) — see
  [Checker/Fixer Mixin](app_checker_fixer.md)'s own Design Decisions.
