# Shared Filter Framework

**Script:** [Shared Filter Framework (script)](filters.py)

## Purpose
GUI rework Phase 3 (owner decision 2026-07-21): ONE stackable "what
should this tool touch" gate meant to eventually replace every tool's
bespoke filter — the Aspect tool's own scalar `ASPECT_FILTER_*`
(`from`/`to`/mode`) and Upscale's four-field aspect/size gate — with a
single reusable shape. This module is the PURE, engine-side half:
no PIL, no tkinter, just arithmetic on the `(width, height)` a caller
already has from a decoded image.

**Wired in since Phase 4:** [GUI](../gui.md)'s `FilterEditor` widget
edits a condition stack through this module's `FilterCondition` /
`condition_to_dict` / `condition_from_dict`, and the standalone
Aspect-ratio tool (`AspectRatioDialog`) is its first caller — replacing
the old scalar `ASPECT_FILTER_*` dialog fields one-for-one, with a
one-time settings migration (`gui._migrate_legacy_aspect_filter`) for
an owner who already had a scalar filter saved.

**GUI rework Phase 6:** Upscale's own four-field aspect/size gate
migrated too — each `AgentPanel` and the standalone `UpscaleParamsDialog`
now embed a `FilterEditor` (pre-seeded with one Aspect (range)
condition) beside a single min-side number, resolved back into
`upscale_if_small`'s unchanged kwargs by the pure `gui.
_upscale_params_from_side_and_filter`; a stacked condition this
resolution cannot express (a Width/Height/Any-side row, or a second/
IF-NOT aspect row) is still honored — never silently dropped — via a
direct `matches()` call at the two upscale call sites (`gui.
_gate_and_upscale` per image on the site pipeline; `gui._filter_files`
pre-filtering the standalone tool's file list). `gui.
_migrate_legacy_upscale_gate` is the one-time settings migration for an
owner who already had the old four scalar fields saved. The BG/Crop
tools stay on their pre-existing behaviour until a later phase
migrates them too.

## The Model — one shape, five kinds
A `FilterCondition` is `(kind, polarity, lo, hi)`. `kind` (a
`FILTER_KIND_*` value) picks what is measured on the image;
`polarity` (`FILTER_POLARITY_IF` / `FILTER_POLARITY_IF_NOT`) picks
whether the measured value must land INSIDE `[lo, hi]` or OUTSIDE it
for the condition to PASS. `matches(width, height, conditions)` ANDs
every condition's pass/fail (owner decision: stacking is AND, each
condition further narrows) — an empty list matches everything.

| Kind | Measures | `[lo, hi]` check |
|------|----------|-------------------|
| `FILTER_KIND_ASPECT_EXACT` | `width / height` | `lo <= ratio <= hi` — caller pins `lo == hi` for a single target point |
| `FILTER_KIND_ASPECT_RANGE` | `width / height` | `lo <= ratio <= hi` — a typed band; IDENTICAL comparison to EXACT, only the GUI authoring differs |
| `FILTER_KIND_ANY_SIDE` | both sides at once | `lo <= min(w, h)` AND `max(w, h) <= hi` |
| `FILTER_KIND_WIDTH` | `width` alone | `lo <= width <= hi` |
| `FILTER_KIND_HEIGHT` | `height` alone | `lo <= height <= hi` |

**"Any side" — orientation-agnostic, both extremes at once.** Passes
when `lo <= min(width, height)` AND `max(width, height) <= hi`: read
as "every side of the image — whichever axis happens to be width or
height — sits inside `[lo, hi]`". A portrait 800×1500 and a landscape
1500×800 are judged IDENTICALLY (min/max don't care which axis is
which). This is an AND of both extremes, not an OR of "either side
qualifies" — one outlier axis (too small OR too big) fails the whole
condition even when the other axis is comfortably in range. `WIDTH` /
`HEIGHT` are the orientation-SENSITIVE counterpart: they read one
named dimension and ignore the other entirely.

**"Exact" aspect has no hidden epsilon.** Pinning `lo == hi` collapses
the range to a single point tested by plain float equality — a pinned
"exact 1:1" (`lo = hi = 1.0`) reliably matches any perfectly square
image (`width == height` divides to exactly `1.0`), but a pinned
"exact 16:9" only matches sources whose division rounds to that SAME
double as `16 / 9`. Deliberate (root Rule #7: no defensive slop for a
scenario the caller controls by choosing `lo`/`hi`) — a caller that
wants a forgiving "exact" match passes a tiny
`[target - tol, target + tol]` band instead, the same pattern
`aspect.py`'s own `ASPECT_TOL` already uses for its "already at
ratio" check.

## Connections

### Uses
- [Config (subfolder)](config/___config.md) — `FILTER_KIND_ASPECT_EXACT`,
  `FILTER_KIND_ASPECT_RANGE`, `FILTER_KIND_ANY_SIDE`,
  `FILTER_KIND_WIDTH`, `FILTER_KIND_HEIGHT`, `FILTER_POLARITY_IF`,
  `FILTER_POLARITY_IF_NOT`

### Used by
- [GUI](../gui.md) — `FilterEditor` (the reusable stacked-condition
  widget), `AspectRatioDialog` (its first caller, GUI rework Phase 4),
  and — GUI rework Phase 6 — each `AgentPanel`'s upscale gate plus
  `UpscaleParamsDialog`. The BG/Crop tools are still unmigrated — a
  later phase.

## Classes

### FilterCondition
`@dataclass(frozen=True)` — `kind: str`, `polarity: str`, `lo: float`,
`hi: float`. One stacked filter row.

## Functions

- `matches(width: int, height: int, conditions: list[FilterCondition])
  -> bool` — whether an image PASSES the whole stacked filter (i.e.
  should be processed). Every condition must pass (AND); an empty list
  matches everything.
- `condition_to_dict(condition: FilterCondition) -> dict` /
  `condition_from_dict(data: dict) -> FilterCondition` — the JSON-safe
  (de)serializers (GUI rework Phase 4) behind every place a condition
  STACK is persisted: settings.json's `aspect_filter_conditions` key,
  and the shared preset library under `config.FILTER_PRESETS_SETTING`
  (`{name: [condition-dict, ...]}`). `condition_from_dict` raises
  `KeyError`/`TypeError`/`ValueError` loudly (root Rule #1) on a
  malformed dict — an absent field or an unparsable `lo`/`hi` — rather
  than fabricating a condition from partial data; callers reading
  untrusted persisted data (a hand-edited settings.json) catch and
  report instead (see `gui._parse_condition_dicts`).

## Design Decisions

- **AND stacking, not OR** (owner decision 2026-07-21): each condition
  further narrows what gets through, matching how the owner described
  "stack a few conditions to zero in on the right images" — a single
  failing condition vetoes the whole image.
- **One shape for five kinds**, not five dataclasses — `kind` is a
  dispatch key, not a type tag, so the GUI can swap a row's kind in
  place (combo change) without rebuilding the row's data structure.
- **Polarity strings reuse the legacy wording exactly**
  (`FILTER_POLARITY_IF = "IF"`, `FILTER_POLARITY_IF_NOT = "IF NOT"`,
  the same spelling as today's `ASPECT_FILTER_IF` /
  `ASPECT_FILTER_IF_NOT`) so a future migration reads an old saved
  mode string straight across with no translation table.
- **No hidden tolerance anywhere in `matches()`.** Every kind is a
  plain closed-interval containment test; "exact" is achieved entirely
  by the caller pinning `lo == hi`, never by the engine guessing an
  acceptable slop. Keeps the function pure/deterministic and keeps the
  "exact vs range" distinction where it belongs — with the caller who
  chose the bounds.
- **Kind/polarity strings ARE the GUI's future combo values**
  (Rule #4 — `FILTER_KINDS` is the ordered tuple `FilterEditor`'s kind
  dropdown will list directly), the same convention already used by
  `ASPECT_FILTER_MODES` and `STYLE_CHOICES` — no separate ID-to-label
  table to keep in sync.
- **Loud on a bad kind/polarity.** An unrecognised string raises
  `ValueError` immediately (root Rule #1) rather than silently passing
  or failing every image — a typo in a hand-built condition (or a
  future settings-file migration bug) surfaces at once.
- **The exact-aspect tolerance lives in the GUI layer, not here**
  (`config.FILTER_ASPECT_EXACT_TOL`, GUI rework Phase 4). This
  module's own "no hidden epsilon" design decision above still holds
  literally — `matches()` never adds slop of its own. What changed is
  WHO chooses `lo`/`hi` for an "Aspect (exact)" condition: `FilterEditor`
  authors it from a single typed ratio and widens it into
  `[ratio - tol, ratio + tol]` before ever constructing the
  `FilterCondition`, so the ENGINE still only ever sees a plain
  closed-interval containment test — it has no idea the interval was
  derived from one number instead of two.
