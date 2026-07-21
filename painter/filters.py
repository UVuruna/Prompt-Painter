"""Shared filter framework — the universal "what should this tool
touch" gate (owner decision 2026-07-21, GUI rework Phase 3).

Every per-tool file picker (BG removal / Crop / Upscale / the Aspect
tool's own scalar ``ASPECT_FILTER_*`` today) is meant to grow a stack
of zero or more ``FilterCondition`` rows, ANDed together, deciding
whether ONE image should be processed. This module is the pure,
engine-side half of that framework — no PIL, no tkinter, just
arithmetic on the ``(width, height)`` a caller already has from a
decoded image. The GUI widget that edits the stack (``FilterEditor``)
and the migration of the existing tools onto it are later phases;
nothing here is wired into any tool yet.

THE MODEL — one shape covers five kinds
----------------------------------------
A ``FilterCondition`` is ``(kind, polarity, lo, hi)``. ``kind`` (a
``FILTER_KIND_*`` value) picks what is measured on the image;
``polarity`` (``FILTER_POLARITY_IF`` / ``FILTER_POLARITY_IF_NOT``)
picks whether the measured value must land INSIDE ``[lo, hi]`` or
OUTSIDE it for the condition to PASS:

* ``FILTER_KIND_ASPECT_EXACT`` / ``FILTER_KIND_ASPECT_RANGE`` — the
  image's aspect ratio ``width / height``. Both kinds measure and
  compare IDENTICALLY (a plain ``lo <= ratio <= hi`` containment); the
  exact/range split is a GUI-authoring distinction only (one target
  value vs a typed band) — a caller wanting an "exact" ratio pins
  ``lo == hi``, collapsing the range to a single point. There is NO
  hidden epsilon: two floats must compare equal, so a pinned "exact
  1:1" (``lo = hi = 1.0``) reliably matches any perfectly square image
  (``width == height`` divides to exactly ``1.0``), but a pinned
  "exact 16:9" only matches sources whose division rounds to that
  SAME double as ``16 / 9`` — deliberate (root Rule #7: no defensive
  slop for a scenario the caller controls by choosing ``lo``/``hi``).
  A caller that wants a forgiving "exact" match passes a tiny
  ``[target - tol, target + tol]`` band instead, the same pattern
  ``aspect.py``'s ``ASPECT_TOL`` already uses for its own "already at
  ratio" check.
* ``FILTER_KIND_ANY_SIDE`` — BOTH sides at once, orientation-agnostic:
  passes when ``lo <= min(width, height)`` AND ``max(width, height) <=
  hi``. Read as "every side of the image — whichever axis happens to
  be width or height — sits inside ``[lo, hi]``": a portrait 800x1500
  and a landscape 1500x800 are judged identically (min/max don't care
  which axis is which). This is an AND of both extremes, not an OR of
  "either side qualifies" — one outlier axis (too small OR too big)
  fails the whole condition even when the other axis is comfortably in
  range.
* ``FILTER_KIND_WIDTH`` / ``FILTER_KIND_HEIGHT`` — that ONE dimension,
  in pixels, against ``[lo, hi]``. Unlike ``ANY_SIDE``, orientation
  matters: the other dimension is ignored entirely.

``matches(width, height, conditions)`` ANDs every condition's pass/fail
(owner decision 2026-07-21: stacking is AND, each condition further
narrows what gets through). An empty list matches everything — no
conditions means no filter, process everything.

WIRED IN — GUI rework Phase 4
------------------------------
``FilterEditor`` (``gui.py``) is the reusable stacked-condition widget
this module was built for; the standalone Aspect-ratio tool
(``AspectRatioDialog``) is its first caller, replacing the old scalar
``ASPECT_FILTER_*`` from/to/mode dialog fields one-for-one (a settings
migration converts an owner's already-saved scalar filter into a single
``FILTER_KIND_ASPECT_RANGE`` condition — see ``gui._migrate_legacy_
aspect_filter``). ``condition_to_dict``/``condition_from_dict`` below
are the JSON-safe (de)serializers that let a condition stack round-trip
through ``settings.json`` — both the Aspect tool's own remembered
filter and the shared preset library under
``config.FILTER_PRESETS_SETTING``.
"""

from __future__ import annotations

from dataclasses import dataclass

from painter.config import (
    FILTER_KIND_ANY_SIDE,
    FILTER_KIND_ASPECT_EXACT,
    FILTER_KIND_ASPECT_RANGE,
    FILTER_KIND_HEIGHT,
    FILTER_KIND_WIDTH,
    FILTER_POLARITY_IF,
    FILTER_POLARITY_IF_NOT,
)


@dataclass(frozen=True)
class FilterCondition:
    """One stacked filter row: measure ``kind`` (a ``FILTER_KIND_*``
    value) on the image and test it against ``[lo, hi]`` under
    ``polarity`` (a ``FILTER_POLARITY_*`` value). An "exact" aspect
    condition is expressed by setting ``lo == hi`` — see the module
    docstring for the float-equality caveat that implies."""

    kind: str
    polarity: str
    lo: float
    hi: float


def _in_range(kind: str, width: int, height: int, lo: float, hi: float) -> bool:
    """Whether one image's ``kind`` measurement falls in ``[lo, hi]`` —
    the per-kind value extraction the module docstring documents.
    Raises ``ValueError`` loudly on an unrecognised kind (root Rule
    #1 — never silently treat a typo'd kind as a pass or a fail)."""
    if kind in (FILTER_KIND_ASPECT_EXACT, FILTER_KIND_ASPECT_RANGE):
        return lo <= (width / height) <= hi
    if kind == FILTER_KIND_ANY_SIDE:
        return lo <= min(width, height) and max(width, height) <= hi
    if kind == FILTER_KIND_WIDTH:
        return lo <= width <= hi
    if kind == FILTER_KIND_HEIGHT:
        return lo <= height <= hi
    raise ValueError(f"unknown filter kind: {kind!r}")


def _condition_passes(width: int, height: int, condition: FilterCondition) -> bool:
    """One condition's verdict: IF passes when the measurement is in
    range, IF NOT passes when it is out of range. Raises ``ValueError``
    loudly on an unrecognised polarity."""
    in_range = _in_range(
        condition.kind, width, height, condition.lo, condition.hi
    )
    if condition.polarity == FILTER_POLARITY_IF:
        return in_range
    if condition.polarity == FILTER_POLARITY_IF_NOT:
        return not in_range
    raise ValueError(f"unknown filter polarity: {condition.polarity!r}")


def matches(width: int, height: int, conditions: list[FilterCondition]) -> bool:
    """Whether an image ``width x height`` PASSES the whole stacked
    filter — i.e. should be processed.

    Every condition must pass (AND, owner decision 2026-07-21): each
    one further narrows what gets through. An empty ``conditions``
    list matches everything (no filter = process everything).
    """
    return all(_condition_passes(width, height, c) for c in conditions)


def condition_to_dict(condition: FilterCondition) -> dict:
    """One condition -> a JSON-safe dict (``settings.json`` / a saved
    preset) — the flat field-for-field shape ``kind``/``polarity``/
    ``lo``/``hi``, no encoding beyond what ``json.dumps`` already
    handles natively."""
    return {
        "kind": condition.kind,
        "polarity": condition.polarity,
        "lo": condition.lo,
        "hi": condition.hi,
    }


def condition_from_dict(data: dict) -> FilterCondition:
    """The inverse of ``condition_to_dict`` — a JSON-loaded dict back
    into a ``FilterCondition``. Raises ``KeyError``/``TypeError``/
    ``ValueError`` loudly (root Rule #1) on a malformed dict — an
    absent field, or a ``lo``/``hi`` that will not ``float()`` — rather
    than silently fabricating a condition from partial data; a caller
    reading untrusted persisted data (a hand-edited ``settings.json``)
    is expected to catch and report, not this function to guess."""
    return FilterCondition(
        kind=data["kind"],
        polarity=data["polarity"],
        lo=float(data["lo"]),
        hi=float(data["hi"]),
    )
