# Site Jobs Mixin

**Script:** [Site Jobs Mixin (script)](../app_jobs.py) ·
**Flow:** [diagram](../__flow/app_jobs.md)

## Purpose
`SiteJobsMixin` — one of `PainterGui`'s responsibility slices (root
Rule #20 god-file refactor, step 8/8; see [GUI (folder)](../___gui.md)
and [App (composition)](../app.py)). Owns the two browser-driven SITE
jobs (ChatGPT/Gemini) end to end: start (`_start_site` /
`_start_site_clicked`), the worker body that drives one site through
`run_sheet` (`_drive_site`), stop (`_stop_site`), the per-job Pause
toggle (`_toggle_pause_job`, shared by every `JOB_ORDER` kind, not only
sites), dashboard-panel close (`_close_panel`/`_tool_panel_key`), the
F2 model-degradation question (`_ask_degrade_blocking`), the quota
auto-restart timers (`_handle_terminal`/`_refresh_cooldown_labels`/
`_tick_restart`/`_cancel_restart`/`_auto_restart`), and the per-site
post-save pipeline composer (`_compose_post_save` — BG→Crop→Aspect→
Upscale, shared by sites and the API-image job via its own panel).

PROMPT + IMAGE mode (faza 2, owner 2026-08-03): every Start — the two
sites AND the API job — reads the shared `_pi_section`
([Prompt + Image Section](prompt_image.md)) and passes
`reference_dir` (the ← resolution's second rung, always) plus
`require_input_image` (the eligibility narrowing, only while the mode
is ON) through `_drive_site` into `run_sheet` — one mode, every
generator.

**Three things used to live here too, and no longer do.** The parallel
Checker AI and the Fixer AI moved to
[Checker/Fixer Mixin](app_checker_fixer.md) in step 8/8 (2026-08-01);
then, on 2026-08-18 (audit
[AUDIT-OOP-2026-08-18](../../docs/AUDIT-OOP-2026-08-18.md) → R5 — the
exact three-way split the structure ratchet had already named), the
paid-API image job moved to [API Image Job](app_api_image_job.md) and
the worker-queue pump with its dispatch table to
[Queue Pump](app_dispatch.md). Every cross-call between them resolves
through the shared `PainterGui` MRO exactly as when they were one
class, so nothing changed behaviorally — and the file dropped from
1,110 to 779 lines, under the wall, its RATCHET entry gone.

**`_drive_site` is GENERALIZED, not forked, to cover API Image GEN**
(GUI rework Phase 19): its `driver` parameter is supplied ALREADY
CONSTRUCTED by the caller — `_start_site`'s own `SiteDriver(SITES[key],
timing, CDP_URL)` for chatgpt/gemini, `_start_api_image`'s
`ApiImageAdapter` for `"api_image"` (not a browser site, no
`SiteConfig`) — instead of this method building a `SiteDriver`
internally. The method's own body never branches on which kind of
object it got.

**F2 (owner 2026-07-29): model-degradation handling.** When a site's
model quality drops (a known degraded-response signal), `on_degrade`
resolves the panel's own choice — continue on the weaker model, wait,
or (on "ask") block the worker thread on ONE popup answered on the main
thread (`_ask_degrade_blocking`, a 10-minute timeout defaulting to the
safe "wait"). Quota reset moments are additionally PERSISTED
(`settings.json`'s `"site_cooldowns"`, unix epoch seconds) so a fresh
app launch still knows about an active cooldown — INFO ONLY (a setup-
panel label + a one-time startup warning dialog), never a Start gate;
`_refresh_cooldown_labels` self-reschedules every 30s to keep the
per-site label current and drop expired entries.

**F4c (owner 2026-07-29): the shared both-sites Start entry point.**
`_start_site_clicked` is the Start button's real handler — while the
shared both-sites mirror editor is active (see [Build Mixin](app_build.md)'s
`_set_agent_mirror`), ONE click on the primary site's Start first
copies its FULL settings (including the FilterEditor stack the live
mirror cannot reach) onto every other site, then starts EVERY ticked
site as its own independent job; outside that mode it is a plain
per-site start.

No `__init__` here — every attribute it reads (`self._running`, `self.
_workers`, `self._stop_events`, `self._pause_events`, `self.
_job_temps`, `self.agents`, `self.panels`, `self._dashgrid`, ...) is
set by `BuildMixin.__init__`.

## Connections

### Uses
- [Painter (folder)](../../painter/___painter.md) — `config`
  (`AI_IMAGE_GATE_MESSAGE`, `CDP_URL`, `DEGRADE_ASK`/`DEGRADE_CONTINUE`/
  `DEGRADE_WAIT`, `SITES`, `TIMING`, `prompt_suffix`, `tile_for_kind`);
  `aspect` (`change_aspect`); `jobtemp` (`JobTemp`); `driver`/`runner`/
  `chrome` (all imported LOCALLY inside the methods that use them —
  `_start_site`/`_drive_site` — never at module level, matching the
  original file's own lazy-import shape)
- [API Panel](api_panel.md) — `ApiImageAdapter` (the API-image job's
  `SiteDriver`-shaped stand-in)
- [Pure Logic](logic.md) — `_gate_and_upscale` (through a DEFERRED
  `import gui`, see Design Decisions), `_run_pipeline_steps`

### Used by
- [App (composition)](../app.py) — `PainterGui(..., SiteJobsMixin, ...)`
- [View Mixin](app_views.md) — `_sync_running_state`/
  `_apply_running_layout` are called from here on every job-state
  change
- [Checker/Fixer Mixin](app_checker_fixer.md) — `_maybe_spawn_checker`/
  `_maybe_spawn_fixer` are called from `_dispatch` here, resolved
  through the shared `PainterGui` MRO
- [Tool Jobs Mixin](app_tools.md) — `_resend_flagged` calls
  `_start_site`; both mixins share `_toggle_pause_job`/`_tool_panel_
  key`'s generic per-kind dispatch

## Classes

### SiteJobsMixin
Key methods: `_start_site`, `_start_api_image`, `_start_site_clicked`
(F4c entry point), `_drive_site` (the generalized run loop, one worker
thread per job), `_stop_site`, `_compose_post_save` (the pipeline-order
composer), `_toggle_pause_job` (shared by ALL `JOB_ORDER` kinds, not
just sites), `_close_panel`/`_tool_panel_key`, `_handle_terminal`/
`_tick_restart`/`_cancel_restart`/`_auto_restart` (quota auto-restart),
`_refresh_cooldown_labels` (F2), `_ask_degrade_blocking` (F2),
`_drain_queue`/`_dispatch` (the queue pump and message router).

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
  `_fade_out_overlay` (see [GUI (folder)](../___gui.md)) — the split just
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
- **API Image GEN's `TerminalState` always carries `retry_after_s=None`**
  (the paid model's zero free-tier quota is a PERMANENT condition, no
  wait ever fixes it) — so `_handle_terminal`'s auto-restart branch is
  simply unreachable for this job; it stops and posts
  `__worker_done__` like any other loud, non-retryable failure.
