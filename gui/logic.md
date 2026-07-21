# Pure Logic Helpers

**Script:** [Pure Logic Helpers (script)](logic.py)

## Purpose
The Tk-free module-level functions pulled out of `gui/__init__.py`
(root Rule #20 god-file refactor, step 3/8): the shared-filter engine
glue (`_filter_files`, `_parse_condition_dicts`, the legacy
aspect-filter/upscale-gate migrations, `_upscale_params_from_
side_and_filter`, `_gate_and_upscale`), the per-image post-save
pipeline runner (`_run_pipeline_steps`), the dashboard's per-scope
stat formatter (`_scope_stats`), the fixer auto-dispatch decision
(`_fixer_decision`), the manual-fix result-to-UI mapping
(`_fix_result_ui`), and two small pure view-layout helpers
(`_visible_agent_columns`, `_menu_tile_columns`, `_next_view`). Every
function takes plain values (paths, dicts, duck-typed objects) and
returns plain values — no widget is ever built or touched, so this
module is directly unit-testable with no Tk display required (gui.py's
own established "pure helpers get pytest, real Tk/UI wiring gets a
screenshot" split).

## Connections

### Uses
- [Painter (folder)](../painter/___painter.md) — `filters`
  (`FilterCondition`/`matches`/`condition_to_dict`/`condition_from_dict`),
  `jobtemp` (the `JobTemp` type annotation), `config` (the
  `ASPECT_FILTER_*`/`FILTER_KIND_*`/`FILTER_POLARITY_*`/
  `FIXER_MODE_WEBSITE`/`MENU_TILE_*` constants)

### Used by
- [GUI (folder)](___gui.md) — `__init__.py` re-exports the full API
  (`gui._filter_files`, `gui._scope_stats`, `gui._next_view`, ...) for
  `PainterGui`, `MainMenu`, `DashPanel` and the tool panels, which all
  still call these functions by their bare names

## Design Decisions
- **`MENU_TILE_CELL_MIN_PX` moved here too, not just the functions.**
  `_menu_tile_columns`'s own docstring requires it to agree EXACTLY
  with `MainMenu._reflow`'s grid `minsize` floor — the two must share
  one source of truth. It is defined here (derived from
  `painter.config`'s `MENU_TILE_W`/`MENU_TILE_GAP_PX`) and re-exported
  through `gui/__init__.py` for `MainMenu`'s own use, rather than kept
  in `__init__.py` and imported backward into this leaf module (which
  would risk a circular import).
- **`_STAT_KEYS` moved alongside `_scope_stats`, for the same reason.**
  `DashPanel` (still in `__init__.py`) iterates `_STAT_KEYS` right
  after calling `_scope_stats` — the two are inseparable in practice —
  so both live here and both are re-exported.
