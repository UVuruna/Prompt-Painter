# FilterEditor

**Script:** [FilterEditor (script)](../filter_editor.py) ·
**Flow:** [diagram](../__flow/filter_editor.md)

## Purpose
The reusable stacked-filter widget (GUI rework Phase 4) — pulled out
of `gui/__init__.py` (root Rule #20 god-file refactor, step 3/8) — the
UI half of [Shared Filter Framework](../../painter/__about/filters.md):
zero or more removable condition rows (`_FilterConditionRow`, each a
kind combo from `FILTER_KINDS` + an IF/IF-NOT polarity combo, and
either ONE numeric field — "Aspect (exact)" — or a lo/hi pair for
every other kind), a rounded "+ Add condition" button that seeds a
fresh row at the ~square default aspect-range band
(`ASPECT_FILTER_DEFAULT_FROM`/`_TO`, 0.9–1.1), and a PRESET row
(editable combo of saved names + Save/Load/Delete). Stacked conditions
AND together (`painter.filters.matches`, owner decision 2026-07-21) —
an empty stack matches everything.

Public API: `get_conditions() -> list[FilterCondition]` raises
`ValueError` (naming the offending kind, via
`_FilterConditionRow.to_condition`) on an unparsable or inverted row
rather than returning a partial list — the caller decides how to
surface it (`_save_preset` below is one such caller, and shows a
messagebox on its own call); `set_conditions(conditions)` rebuilds the
row stack from scratch.

**Exact-aspect tolerance.** A pinned "Aspect (exact)" `lo == hi` is a
razor-thin float equality a real decoded image's W/H division almost
never lands on exactly, so its row shows only ONE ratio field —
`to_condition` widens it into
`[ratio - FILTER_ASPECT_EXACT_TOL, ratio + FILTER_ASPECT_EXACT_TOL]`
(0.02) before building the `FilterCondition`; the reverse display
(`_filter_row_display_bounds`) shows the stored band's MIDPOINT, so a
round-trip through `set_conditions()`/`get_conditions()` reproduces
the same band as long as the tolerance constant hasn't changed in
between.

**Presets are a SHARED LIBRARY**, not per-widget state — ONE
`settings.json` key (`config.FILTER_PRESETS_SETTING`,
`{name: [condition-dict, ...]}`) every `FilterEditor` instance reads/
writes via DEPENDENCY INJECTION, not a direct file open: the
constructor takes the owner's LIVE `presets` dict (mutated IN PLACE by
Save/Delete — the caller's own reference sees the change immediately)
and an OPTIONAL `on_presets_changed` callback to persist through it.
Both are optional, so a standalone construction (a test, or a future
panel with no host GUI yet) still works against a private in-memory
dict. `painter.filters.condition_to_dict`/`condition_from_dict` is
what makes both this shared-preset JSON and `settings.json`'s own
per-panel condition stack JSON-safe — the same (de)serializers back
both persistence paths.

## Connections

### Uses
- [Shared Filter Framework](../../painter/__about/filters.md) —
  `FilterCondition`/`matches`/`condition_to_dict`/`condition_from_dict`
- [Config (subfolder)](../../painter/config/___config.md) —
  `FILTER_KIND_*`/`FILTER_KINDS`/`FILTER_POLARITY_*`/
  `FILTER_ASPECT_EXACT_TOL`/`ASPECT_FILTER_DEFAULT_FROM`/`_TO`
- [Themed Widget Toolkit](widgets.md) — `rounded_button`/
  `rounded_entry`/`rounded_combo`, `INPUT_HEIGHT`

### Used by
- [GUI (folder)](../___gui.md) — `__init__.py` re-exports `FilterEditor`;
  `AgentPanel`/`ToolSettingsPanel` (and its Upscale/Aspect subclasses)
  embed one to pick which images a run/tool touches

## Classes

### _FilterConditionRow
One stacked row: kind + polarity combos, one or two numeric fields, a
remove button. Bridges a single `FilterCondition` to live Tk Vars and
back via `to_condition()`. Switching a row's kind does NOT reinterpret
or clear whatever is already typed — the field(s) simply show/hide;
the owner retypes the value for the newly-chosen kind.

### FilterEditor
See Purpose above. Owns the row stack (`self._rows`), the "+ Add
condition" button, and the preset row's Save/Load/Delete.

## Design Decisions
- **Row-geometry constants (`FILTER_ROW_*`) live here, not in
  `painter.config`.** They are pure Tk pixel geometry (combo/entry
  widths, row gap) with no engine meaning — the engine-side kind/
  polarity strings and the exact-aspect tolerance stay in
  `painter/config.py` alongside the rest of the `FILTER_*` constants;
  this module is gui's own Rule #4 home for the widget's own layout
  numbers, same split every other dialog's `*_ENTRY_W`/`*_PAD_PX`
  constant follows.
- **Presets via dependency injection, not a hardcoded settings path**
  — see the Purpose section's "shared library" note. This is what lets
  a `FilterEditor` be constructed headless (a test, or a panel with no
  settings file yet) without any special-casing in this module itself.
