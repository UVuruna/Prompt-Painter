# FilterEditor

**Script:** [FilterEditor (script)](filter_editor.py)

## Purpose
The reusable stacked-filter widget (GUI rework Phase 4) — pulled out
of `gui/__init__.py` (root Rule #20 god-file refactor, step 3/8) — the
UI half of the [Shared Filter Framework](../painter/filters.md): zero
or more removable condition rows (`_FilterConditionRow`, each a
kind/polarity combo pair + one or two numeric fields), an "+ Add
condition" button, and a PRESET row (save/load/delete a NAMED
condition stack, ANDed together via `painter.filters.matches`).
`_filter_row_display_bounds` converts a stored `FilterCondition`'s
`[lo, hi]` band into the strings a row's fields should show (special-
cased for "Aspect (exact)", which shows one ratio field instead of a
lo/hi pair).

Public API: `FilterEditor.get_conditions()`/`set_conditions()`.

## Connections

### Uses
- [Painter (folder)](../painter/___painter.md) — `filters`
  (`FilterCondition`/`matches`/`condition_to_dict`/`condition_from_dict`),
  `config` (`FILTER_KIND_*`/`FILTER_KINDS`/`FILTER_POLARITY_*`/
  `FILTER_ASPECT_EXACT_TOL`/`ASPECT_FILTER_DEFAULT_FROM`/`_TO`)
- [Widgets (script)](widgets.md) — `rounded_button`/`rounded_entry`/
  `rounded_combo`, `INPUT_HEIGHT`

### Used by
- [GUI (folder)](___gui.md) — `__init__.py` re-exports `FilterEditor`;
  `AgentPanel`/`ToolSettingsPanel` (and its Upscale/Aspect subclasses)
  embed one to pick which images a run/tool touches

## Design Decisions
- **Row-geometry constants (`FILTER_ROW_*`) live here, not in
  `painter.config`.** They are pure Tk pixel geometry (combo/entry
  widths, row gap) with no engine meaning — the engine-side kind/
  polarity strings and the exact-aspect tolerance stay in
  `painter/config.py` alongside the rest of the `FILTER_*` constants;
  this module is gui's own Rule #4 home for the widget's own layout
  numbers, same split every other dialog's `*_ENTRY_W`/`*_PAD_PX`
  constant follows.
