# Checker/Fixer Mixin

**Script:** [Checker/Fixer Mixin (script)](../app_checker_fixer.py) ·
**Flow:** [diagram](../__flow/app_checker_fixer.md)

## Purpose
`CheckerFixerMixin` — the fourth of `PainterGui`'s six mixins (root
Rule #20 god-file refactor, step 8/8; see [GUI (folder)](../___gui.md)
and [App (composition)](../app.py)). Split out of
[Site Jobs Mixin](app_jobs.md)'s `app_jobs.py` once that module grew
past the ~1000-line Rule #20 budget (1334 lines pre-split).

Owns the parallel Checker AI (`_maybe_spawn_checker`/`_run_checker_one`,
GUI rework Phase 16) — fired off the SAME `item_progress` event the
dashboard row was just built from, well before the runner emits
`item_done`, so the vision check overlaps BOTH the remaining "our time"
pause AND the whole of the next item's generation (zero `runner.py`
changes: this hangs off an event the dashboard already consumed). F6
(REWORK.md, owner 2026-07-29): when an `AgentPanel`'s
`checker_prompt_var` is on, the background checker thread ALSO resolves
the item's own sheet PROMPT (`_prompt_for_drop`, scanning the queued
sheets and caching each parse by MTIME so a 200-image run parses each
sheet at most a handful of times, never 200) and passes it into
`ai.check_one_image` — the vision model then judges content match on
top of the banal-defects check. The sheet lookup runs on the checker's
OWN background thread, never the Tk one (parsing a sheet per saved
image on the UI thread would jank it under a real batch).

And the Fixer AI (GUI rework Phase 20) — both its auto-dispatch half
(`_maybe_spawn_fixer`/`_run_fixer_api`/`_queue_website_fix`, wired off
the checker's own `item_checked` result) and its manual-button worker
builders (`_build_fix_workers`/`_run_image_fix`/`_run_website_fix`/
`_backup_before_fix`), shared with `AiCheckPanel`'s own report viewer.

`_maybe_spawn_checker` is called from `SiteJobsMixin._dispatch`
(`gui/app_jobs.py`) for every `item_progress` event, and
`_maybe_spawn_fixer` from the same place for every `item_checked`
event this mixin itself posts back onto the shared GUI queue — both
calls resolve through the shared `PainterGui` MRO (`self.`), exactly
as when the two mixins' code lived in one file.

Both halves follow the event's `rel` — the ACTUAL saved path the
runner emits (owner 2026-07-27: a ticked redo lands as a `_vN`
version file): the checker reads `event["rel"]` for the file it
checks, and the API fixer overwrites the `rel` its `item_checked`
carried (the checker's own flag key) — neither ever re-derives the
canonical `dest_for` guess, which would point at the OLD image for a
version redo.

No `__init__` here — every attribute it reads (`self.agents`, `self.
panels`, `self._job_temps`, `self._q`, `self._running`, `self._log`,
`self._dashgrid`) is set by `BuildMixin.__init__`, with ONE exception:
`self._sheet_cache` (F6's per-sheet parse cache) is lazily created by
`_maybe_spawn_checker` itself on first use, always from the Tk thread
— this mixin carries no constructor of its own to seed it in.

## Connections

### Uses
- [Painter (folder)](../../painter/___painter.md) — `config`
  (`AI_CHECK_INSTRUCTIONS`, `CDP_URL`, `SITES`, `TIMING`); `ai`
  (`check_one_image`/`edit_image`/`build_fix_prompt`/`flag_file`/
  `flag_key`/`drop_and_site_for`/the `AiError`/`PaidFeatureRequired`
  taxonomy) and `driver` (`SiteDriver`/`DriverError`/
  `AttachNotConfigured`, for the manual WEBSITE FIX worker) — both
  imported LOCALLY inside the methods that use them, never at module
  level, matching the original file's own lazy-import shape;
  `sheet_parser` (`SheetError`, `parse_sheet`, local to
  `_prompt_for_drop`)
- [Pure Logic](logic.md) — `_fixer_decision`

### Used by
- [App (composition)](../app.py) — `PainterGui(..., CheckerFixerMixin, ...)`
- [Site Jobs Mixin](app_jobs.md) — `_dispatch` calls
  `_maybe_spawn_checker`/`_maybe_spawn_fixer` here for every
  `item_progress`/`item_checked` event, resolved through the shared
  `PainterGui` MRO
- [Dashboard Job Panel Base + Site Panel](dash_panels.md) —
  `DashPanel._show_check` calls `_build_fix_workers` (via
  `PainterGui`) for its Check… viewer's IMAGE FIX/WEBSITE FIX buttons
- [Tool + AI-Checker Dashboard Panels + Grid](tool_dash.md) —
  `AiCheckPanel._on_activate` calls the same `_build_fix_workers`

## Classes

### CheckerFixerMixin
Key methods: `_maybe_spawn_checker`/`_run_checker_one`/
`_prompt_for_drop` (the parallel per-item Checker AI, F6's prompt-match
lookup), `_maybe_spawn_fixer`/`_run_fixer_api`/`_queue_website_fix`
(the auto-dispatch Fixer AI — `_fixer_decision` resolves "none"/"api"/
"website_queue"), `_build_fix_workers`/`_run_image_fix`/
`_run_website_fix`/`_backup_before_fix` (the manual IMAGE FIX/WEBSITE
FIX buttons shared by both report viewers).

## Design Decisions
- **The split line is exactly the boundary between `_dispatch` and
  the checker/fixer's OWN methods.** Everything the checker/fixer
  needs from a "job" (which panel, which JobTemp, the shared queue)
  arrives as plain `self.` attributes both mixins already share —
  nothing here reaches into a `SiteJobsMixin`-only private helper, so
  the two files could separate with zero new coupling beyond the
  `self._maybe_spawn_checker`/`self._maybe_spawn_fixer` calls
  `_dispatch` already made before the split (unchanged after it,
  since Python resolves both through the composed `PainterGui`'s MRO
  either way).
- **No `__init__` here (Rule #5)** — see [Build Mixin](app_build.md).
- **Every method body moved byte-for-byte.** This was a pure
  structural split (ZERO behavior change) — each method's code, docs
  and comments carried over unchanged from `app_jobs.py`; only the
  imports at the top of the new file were narrowed to what THIS half
  actually uses (e.g. `AI_CHECK_INSTRUCTIONS`/`dest_for` moved here
  since only the checker/fixer methods read them; `SiteJobsMixin` kept
  none of the checker/fixer-only imports it no longer needs).
- **`_queue_website_fix` NEVER drives the browser directly.** The
  site's tab is BUSY generating the next image the instant
  `item_checked` fires — driving `submit_with_image` here would
  collide with the in-flight `submit_prompt`/`await_done`. It instead
  folds the flagged item into `AiCheckPanel`'s own append-only
  `_flagged` bucket (the SAME state the standalone batch checker
  fills) and reveals that panel — the pre-existing "Send flagged to
  generator" button is the ONE send path, reused verbatim, clicked
  once the site is idle again.
- **`_run_website_fix` (the MANUAL button) refuses with a transient
  `"error"`, not a permanent `"gated"`, while its site is running** —
  the same one-tab collision `_queue_website_fix` avoids on the
  auto-dispatch side, just surfaced as a retry-able message since a
  manual click is the owner's own choice of timing.
