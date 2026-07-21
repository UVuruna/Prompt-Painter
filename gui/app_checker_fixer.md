# Checker/Fixer Mixin

**Script:** [Checker/Fixer Mixin (script)](app_checker_fixer.py)

## Purpose
`CheckerFixerMixin` — the fourth of `PainterGui`'s six mixins (root
Rule #20 god-file refactor, step 8/8; see [GUI (folder)](___gui.md)
and [App (composition)](app.md)). Split out of
[Site Jobs Mixin](app_jobs.md)'s `app_jobs.py` once that module grew
past the ~1000-line Rule #20 budget (1334 lines pre-split). Owns the
parallel Checker AI (`_maybe_spawn_checker`/`_run_checker_one`, GUI
rework Phase 16 — fired off the SAME `item_progress` event the
dashboard row was just built from, so the vision check overlaps BOTH
the remaining "our time" pause and the next item's whole generation)
and the Fixer AI (GUI rework Phase 20) — both its auto-dispatch half
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

No `__init__` here — every attribute it reads (`self.agents`, `self.
panels`, `self._job_temps`, `self._q`, `self._running`, `self._log`,
`self._dashgrid`) is set by `BuildMixin.__init__`.

## Connections

### Uses
- [Painter (folder)](../painter/___painter.md) — `config`
  (`AI_CHECK_INSTRUCTIONS`, `CDP_URL`, `SITES`, `TIMING`, `dest_for`);
  `ai` (`check_one_image`/`edit_image`/`build_fix_prompt`/`flag_file`/
  `flag_key`/`drop_and_site_for`/the `AiError`/`PaidFeatureRequired`
  taxonomy) and `driver` (`SiteDriver`/`DriverError`/
  `FixNotConfigured`, for the manual WEBSITE FIX worker) — both
  imported LOCALLY inside the methods that use them, never at module
  level, matching the original file's own lazy-import shape
- [Pure Logic (script)](logic.md) — `_fixer_decision`

### Used by
- [App (composition)](app.md) — `PainterGui(..., CheckerFixerMixin, ...)`
- [Site Jobs Mixin](app_jobs.md) — `_dispatch` calls
  `_maybe_spawn_checker`/`_maybe_spawn_fixer` here for every
  `item_progress`/`item_checked` event, resolved through the shared
  `PainterGui` MRO
- [Dashboard Job Panel Base + Site Panel](dash_panels.md) —
  `DashPanel._show_check` calls `_build_fix_workers` (via
  `PainterGui`) for its Check… viewer's IMAGE FIX/WEBSITE FIX buttons
- [Tool + AI-Checker Dashboard Panels + Grid](tool_dash.md) —
  `AiCheckPanel._on_activate` calls the same `_build_fix_workers`

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
