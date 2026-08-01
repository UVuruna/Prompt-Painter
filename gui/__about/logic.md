# Pure Logic Helpers

**Script:** [Pure Logic Helpers (script)](../logic.py) ·
**Flow:** [diagram](../__flow/logic.md)

## Purpose
The Tk-free module-level functions pulled out of `gui/__init__.py`
(root Rule #20 god-file refactor, step 3/8): the shared-filter engine
glue (`_filter_files`, `_parse_condition_dicts`, the legacy
aspect-filter/upscale-gate migrations `_migrate_legacy_aspect_filter`/
`_migrate_legacy_upscale_gate`, `_upscale_params_from_side_and_filter`,
`_gate_and_upscale`), the per-image post-save pipeline runner
(`_run_pipeline_steps`), the dashboard's per-scope stat formatter
(`_scope_stats`), the fixer auto-dispatch decision (`_fixer_decision`),
the manual-fix result-to-UI mapping (`_fix_result_ui`), and small pure
view-layout helpers (`_visible_agent_slots`, `_menu_tile_columns`,
`_next_view`). Every function takes plain values (paths, dicts,
duck-typed objects) and returns plain values — no widget is ever built
or touched, so this module is directly unit-testable with no Tk
display required (the codebase's own established "pure helpers get
pytest, real Tk/UI wiring gets a screenshot" split).

**The per-image pipeline runner and its backup contract.**
`_run_pipeline_steps(path, steps, temp, keep_all_steps, on_cap)` —
given caller-built `(label, step_name, fn)` triples for whichever
switches are ON — ALWAYS runs them in fixed pipeline order BG → Crop →
Aspect(force) → Upscale, never reordered by which happen to be ticked
(with Force Aspect off, its default, this is byte-identical to the
pre-Force-Aspect pipeline). Its per-step backup contract: the FIRST
enabled step's PRE-state is tagged `step="original"` and ALWAYS taken
(the pristine, restore-everything baseline), deduped against that same
step's own named backup if it is also first; every LATER enabled
step's pre-state gets its OWN named backup ONLY when `keep_all_steps`
is on AND the job has not yet gone over its temp-storage cap — once
over cap, new per-step backups stop (falls back to "original-only")
and `on_cap()` fires once; toggling the switch off produces the
identical original-only outcome silently (a deliberate choice, not a
disk emergency). A step's own named backup whose result was a genuine
no-op is dropped right back (nothing worth restoring); "original" is
never dropped.

**The view-transition state machine.** `_next_view(current,
active_count, menu_requested)` — a Menu click is honoured ONLY once
NOTHING is active; absent a Menu click, ANY active job forces
"running"; once "running", it STAYS "running" through every Stop down
to zero active jobs — Stop closing the LAST active job never
auto-navigates by itself, only a SUBSEQUENT explicit Menu click does.

## Connections

### Uses
- [Painter (folder)](../../painter/___painter.md) — `filters`
  (`FilterCondition`/`matches`/`condition_to_dict`/`condition_from_dict`),
  `jobtemp` (the `JobTemp` type annotation), `config` (the
  `ASPECT_FILTER_*`/`FILTER_KIND_*`/`FILTER_POLARITY_*`/
  `FIXER_MODE_WEBSITE`/`MENU_TILE_*` constants)

### Used by
- [GUI (folder)](../___gui.md) — `__init__.py` still re-exports the
  full API (`gui._filter_files`, `gui._scope_stats`, `gui._next_view`,
  `gui._gate_and_upscale`, ...) for external tests and for the
  deferred-import call sites below
- [Build Mixin](app_build.md) — `_visible_agent_slots` (which
  AgentPanel row each visible site occupies)
- [Site Jobs Mixin](app_jobs.md) — `_run_pipeline_steps` (the post-save
  composer) directly; `_gate_and_upscale` through a deferred
  `import gui` (the SAME late-binding idiom this codebase uses
  elsewhere — a test patches `gui._gate_and_upscale`, so the call site
  must resolve it off the `gui` package, not a frozen module-level
  name)
- [Checker/Fixer Mixin](app_checker_fixer.md) — `_fixer_decision`
- [Settings Mixin](app_settings.md) — `_migrate_legacy_aspect_filter`/
  `_migrate_legacy_upscale_gate`/`_parse_condition_dicts` (settings.json
  migrations)
- [Tool Jobs Mixin](app_tools.md) — `_filter_files` (the standalone
  tools' pre-filtered file list)
- [View Mixin](app_views.md) — `_next_view`
- [Doc Window](doc_window.md) — `_fix_result_ui` (the manual Fixer AI
  buttons' result-to-UI mapping)
- [Main Menu + Icon Bar](menu.md) — `MainMenu` imports
  `_menu_tile_columns`/`MENU_TILE_CELL_MIN_PX` directly (real-path,
  post god-file split)
- [Dashboard Job Panel Base + Site Panel](dash_panels.md) — `DashPanel`
  imports `_scope_stats`/`_STAT_KEYS` directly

## Design Decisions
- **`MENU_TILE_CELL_MIN_PX` moved here too, not just the functions.**
  `_menu_tile_columns`'s own docstring requires it to agree EXACTLY
  with `MainMenu._reflow`'s grid `minsize` floor — the two must share
  one source of truth. It is defined here (derived from
  `painter.config`'s `MENU_TILE_W`/`MENU_TILE_GAP_PX`) and imported
  directly by `gui/menu.py`'s `MainMenu` (real-path, since step 6/8),
  plus still re-exported through `gui/__init__.py` for
  `test_gui_running_view.py`'s own `gui.MENU_TILE_CELL_MIN_PX` reads.
- **`_STAT_KEYS` moved alongside `_scope_stats`, for the same reason.**
  `DashPanel` (`gui/dash_panels.py`) iterates `_STAT_KEYS` right
  after calling `_scope_stats` — the two are inseparable in practice —
  so both live here and both are re-exported.
- **`_gate_and_upscale` is reached through a deferred `import gui`
  from `SiteJobsMixin`, not a real-path import.** A test patches
  `monkeypatch.setattr(gui, "_gate_and_upscale", fake)` (found only by
  running the full suite after the god-file split, see
  [GUI (folder)](../___gui.md)'s own step 7/8 notes) — a top-level
  `from .logic import _gate_and_upscale` would bind the real function
  at import time and never see the patch.
