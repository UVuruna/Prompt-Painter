# Aspect Config

**Script:** [Aspect Config (script)](../aspect.py) ·
**Flow:** [diagram](../__flow/aspect.md)

## Purpose

Two things sharing one file (owner decision 2026-07-21 keeps them
together until migration finishes): the batch deform (Change Aspect
Ratio) tool's own constants and legacy scalar input filter, and the
newer shared stackable filter framework meant to eventually replace
that legacy filter across every tool.

## Connections

### Uses
Nothing — a leaf module.

### Used by
- [Change Aspect Ratio](../../__about/aspect.md) (`painter/aspect.py`)
  — `ASPECT_TOL`, `ASPECT_DEFAULT_W`/`_H`, `ASPECT_LABEL_DECIMALS`,
  `ASPECT_FILTER_OFF`/`_IF`/`_IF_NOT`
- [Shared Filter Framework](../../__about/filters.md)
  (`painter/filters.py`) — `FILTER_KIND_ASPECT_EXACT`,
  `FILTER_KIND_ASPECT_RANGE`, `FILTER_KIND_ANY_SIDE`,
  `FILTER_KIND_WIDTH`, `FILTER_KIND_HEIGHT`, `FILTER_POLARITY_IF`,
  `FILTER_POLARITY_IF_NOT`
- GUI (`gui/aspect_canvas.py`, `gui/filter_editor.py`) — the ratio
  editor's label precision, the FilterEditor widget's kind combobox
  and preset-library key
- Re-exported by [Config Package Index](__init__.md)

## Constants

**Aspect tool core + legacy filter:**
- `ASPECT_TOL`, `ASPECT_DEFAULT_W`, `ASPECT_DEFAULT_H` — the deform
  tolerance and the GUI's default 16:9 ratio prompt
- `ASPECT_FILTER_OFF`/`_IF`/`_IF_NOT`, `ASPECT_FILTER_MODES` — the
  legacy scalar input-filter's three modes (also the dropdown labels)
- `ASPECT_FILTER_DEFAULT_FROM`/`_TO` — 0.9/1.1, the dialog's pre-filled
  ~square band
- `ASPECT_LABEL_DECIMALS` — the visual editor's target-ratio decimal
  precision (GUI rework Phase 5)

**Shared filter framework (owner decision 2026-07-21):**
- `FILTER_KIND_ASPECT_EXACT`, `FILTER_KIND_ASPECT_RANGE`,
  `FILTER_KIND_ANY_SIDE`, `FILTER_KIND_WIDTH`, `FILTER_KIND_HEIGHT`,
  `FILTER_KINDS` — the five condition kinds (identifier strings ARE
  the GUI's display text)
- `FILTER_POLARITY_IF`, `FILTER_POLARITY_IF_NOT` — IN-band / OUT-of-band
- `FILTER_PRESETS_SETTING` — the `settings.json` key a saved condition
  stack will live under (GUI rework Phase 4, reserved ahead of the
  GUI work)
- `FILTER_ASPECT_EXACT_TOL` — widens a pinned "Aspect (exact)"
  condition into a real `[ratio-tol, ratio+tol]` band, since a real
  decoded image's W/H almost never lands on the exact float

The matching LOGIC (`FilterCondition`, `matches()`) lives in
`painter/filters.py`, not here — this module only holds the stable
identifier strings.
