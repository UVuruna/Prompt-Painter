"""Shared filter framework (GUI rework Phase 3, owner decision
2026-07-21). Pure arithmetic on synthetic ``(width, height)`` ints —
no images, no PIL, no tkinter.

Covers: one test per condition kind (aspect exact / aspect range / any
side / width / height), IF vs IF NOT polarity, several conditions
ANDed together (owner decision: stacking is AND, each condition
narrows what gets through), the empty-list "matches everything"
default, and the exact-aspect (``lo == hi``) float-equality edge the
module docstring documents (no hidden epsilon).
"""

import json

import pytest

from painter.config import (
    FILTER_KIND_ANY_SIDE,
    FILTER_KIND_ASPECT_EXACT,
    FILTER_KIND_ASPECT_RANGE,
    FILTER_KIND_HEIGHT,
    FILTER_KIND_WIDTH,
    FILTER_KINDS,
    FILTER_POLARITY_IF,
    FILTER_POLARITY_IF_NOT,
)
from painter.filters import (
    FilterCondition,
    condition_from_dict,
    condition_to_dict,
    matches,
)


def cond(kind: str, polarity: str, lo: float, hi: float) -> FilterCondition:
    return FilterCondition(kind=kind, polarity=polarity, lo=lo, hi=hi)


# --- config shape (the engine + the future GUI must agree on these) ---


def test_filter_kinds_tuple_lists_all_five_in_declared_order():
    assert FILTER_KINDS == (
        FILTER_KIND_ASPECT_EXACT,
        FILTER_KIND_ASPECT_RANGE,
        FILTER_KIND_ANY_SIDE,
        FILTER_KIND_WIDTH,
        FILTER_KIND_HEIGHT,
    )


def test_polarity_values_are_distinct():
    assert FILTER_POLARITY_IF != FILTER_POLARITY_IF_NOT


# --- empty stack: no conditions = process everything -------------------


def test_empty_conditions_matches_everything():
    assert matches(1, 1, []) is True
    assert matches(99999, 1, []) is True


# --- aspect (exact) — lo == hi pins a single ratio, no hidden epsilon --


def test_aspect_exact_if_matches_only_the_pinned_ratio():
    square = cond(FILTER_KIND_ASPECT_EXACT, FILTER_POLARITY_IF, 1.0, 1.0)
    assert matches(1000, 1000, [square]) is True   # ratio exactly 1.0
    assert matches(1000, 500, [square]) is False   # ratio 2.0


def test_aspect_exact_has_no_hidden_epsilon():
    """lo == hi is a razor-thin float equality (documented design
    decision) — an image one pixel off the pinned ratio just misses
    it; the engine adds no forgiving slop of its own."""
    square = cond(FILTER_KIND_ASPECT_EXACT, FILTER_POLARITY_IF, 1.0, 1.0)
    assert matches(1000, 999, [square]) is False   # ratio 1.001..., not 1.0


def test_aspect_exact_if_not_inverts():
    square = cond(FILTER_KIND_ASPECT_EXACT, FILTER_POLARITY_IF_NOT, 1.0, 1.0)
    assert matches(1000, 1000, [square]) is False
    assert matches(1000, 500, [square]) is True


# --- aspect (range) ------------------------------------------------------


def test_aspect_range_if_matches_the_band():
    near_square = cond(FILTER_KIND_ASPECT_RANGE, FILTER_POLARITY_IF, 0.9, 1.1)
    assert matches(1000, 1000, [near_square]) is True   # 1.0, in band
    assert matches(1050, 1000, [near_square]) is True   # 1.05, in band
    assert matches(2000, 1000, [near_square]) is False  # 2.0, out of band


def test_aspect_range_if_not_inverts():
    near_square = cond(FILTER_KIND_ASPECT_RANGE, FILTER_POLARITY_IF_NOT, 0.9, 1.1)
    assert matches(1000, 1000, [near_square]) is False
    assert matches(2000, 1000, [near_square]) is True


# --- any side: BOTH extremes at once, orientation-agnostic --------------
# lo <= min(w, h) AND max(w, h) <= hi — every side of the image (whichever
# axis happens to be "width" or "height") must sit inside [lo, hi]. An AND
# of both extremes, not an OR of "either side qualifies".


def test_any_side_if_passes_when_both_dimensions_are_in_band():
    band = cond(FILTER_KIND_ANY_SIDE, FILTER_POLARITY_IF, 100, 2000)
    assert matches(1500, 800, [band]) is True
    assert matches(800, 1500, [band]) is True  # portrait — same verdict


def test_any_side_if_fails_when_the_short_side_is_below_lo():
    band = cond(FILTER_KIND_ANY_SIDE, FILTER_POLARITY_IF, 100, 2000)
    assert matches(1500, 50, [band]) is False   # short side (50) < lo
    assert matches(50, 1500, [band]) is False   # same pair, rotated


def test_any_side_if_fails_when_the_long_side_exceeds_hi():
    band = cond(FILTER_KIND_ANY_SIDE, FILTER_POLARITY_IF, 100, 2000)
    assert matches(3000, 800, [band]) is False   # long side (3000) > hi
    assert matches(800, 3000, [band]) is False   # same pair, rotated


def test_any_side_if_not_inverts():
    band = cond(FILTER_KIND_ANY_SIDE, FILTER_POLARITY_IF_NOT, 100, 2000)
    # both sides in band -> the IF condition would pass -> IF NOT fails
    assert matches(1500, 800, [band]) is False
    # an outlier side -> the IF condition would fail -> IF NOT passes
    assert matches(3000, 800, [band]) is True


# --- width / height: ONE dimension only, orientation matters ------------


def test_width_if_ignores_height():
    w = cond(FILTER_KIND_WIDTH, FILTER_POLARITY_IF, 500, 1000)
    assert matches(750, 1, [w]) is True
    assert matches(750, 999999, [w]) is True   # height never consulted
    assert matches(200, 750, [w]) is False     # width itself out of band


def test_height_if_ignores_width():
    h = cond(FILTER_KIND_HEIGHT, FILTER_POLARITY_IF, 500, 1000)
    assert matches(1, 750, [h]) is True
    assert matches(999999, 750, [h]) is True   # width never consulted
    assert matches(750, 200, [h]) is False     # height itself out of band


def test_width_if_not_inverts():
    w = cond(FILTER_KIND_WIDTH, FILTER_POLARITY_IF_NOT, 500, 1000)
    assert matches(750, 1, [w]) is False
    assert matches(200, 1, [w]) is True


# --- stacking: AND across conditions, mixed IF / IF NOT ------------------


def test_multiple_conditions_all_must_pass():
    conditions = [
        cond(FILTER_KIND_WIDTH, FILTER_POLARITY_IF, 500, 2000),
        cond(FILTER_KIND_HEIGHT, FILTER_POLARITY_IF_NOT, 0, 100),
    ]
    # 1000x1000: width 1000 in [500,2000] (IF passes); height 1000 is NOT
    # in [0,100] (IF NOT passes) -> both pass -> AND True
    assert matches(1000, 1000, conditions) is True


def test_multiple_conditions_one_failure_vetoes_the_whole_stack():
    conditions = [
        cond(FILTER_KIND_WIDTH, FILTER_POLARITY_IF, 500, 2000),
        cond(FILTER_KIND_HEIGHT, FILTER_POLARITY_IF_NOT, 0, 100),
    ]
    # same stack, but height=50 IS in [0,100] -> the IF NOT condition now
    # fails, so the AND must fail even though width still passes
    assert matches(1000, 50, conditions) is False


def test_three_conditions_narrow_further_each_time():
    conditions = [
        cond(FILTER_KIND_ASPECT_RANGE, FILTER_POLARITY_IF, 0.9, 1.1),
        cond(FILTER_KIND_ANY_SIDE, FILTER_POLARITY_IF, 500, 5000),
        cond(FILTER_KIND_WIDTH, FILTER_POLARITY_IF_NOT, 0, 600),
    ]
    # 1000x1000: aspect 1.0 in band; any-side both sides in [500,5000];
    # width 1000 is NOT in [0,600] -> all three pass
    assert matches(1000, 1000, conditions) is True
    # 550x550: aspect + any-side still pass, but width 550 IS in [0,600]
    # -> the IF NOT condition now fails -> overall False
    assert matches(550, 550, conditions) is False


# --- loud on an unrecognised kind/polarity (root Rule #1) ---------------


def test_unknown_kind_raises():
    bogus = cond("not-a-real-kind", FILTER_POLARITY_IF, 0, 1)
    with pytest.raises(ValueError):
        matches(100, 100, [bogus])


def test_unknown_polarity_raises():
    bogus = cond(FILTER_KIND_WIDTH, "not-a-real-polarity", 0, 1)
    with pytest.raises(ValueError):
        matches(100, 100, [bogus])


# --- JSON-safe (de)serialization (GUI rework Phase 4) --------------------
# settings.json / a saved preset stores a condition STACK as a plain list
# of these dicts (config.FILTER_PRESETS_SETTING's documented shape).


def test_condition_to_dict_has_the_four_flat_fields():
    c = cond(FILTER_KIND_ASPECT_RANGE, FILTER_POLARITY_IF_NOT, 0.9, 1.1)
    assert condition_to_dict(c) == {
        "kind": FILTER_KIND_ASPECT_RANGE,
        "polarity": FILTER_POLARITY_IF_NOT,
        "lo": 0.9,
        "hi": 1.1,
    }


def test_condition_to_dict_is_json_serializable():
    c = cond(FILTER_KIND_WIDTH, FILTER_POLARITY_IF, 100, 500)
    # round-trips through an ACTUAL json.dumps/loads, like settings.json
    # itself, not just a plain dict comparison
    reloaded = json.loads(json.dumps(condition_to_dict(c)))
    assert condition_from_dict(reloaded) == c


def test_condition_from_dict_is_the_exact_inverse():
    for kind in FILTER_KINDS:
        for polarity in (FILTER_POLARITY_IF, FILTER_POLARITY_IF_NOT):
            c = cond(kind, polarity, 12.5, 34.75)
            assert condition_from_dict(condition_to_dict(c)) == c


def test_condition_from_dict_coerces_lo_hi_to_float():
    """A hand-edited settings.json might hold whole-number JSON ints for
    lo/hi (e.g. Width/Height in pixels) — condition_from_dict must not
    choke on that, matches()'s own arithmetic already tolerates int/float
    mixing, but FilterCondition's declared shape is float."""
    data = {
        "kind": FILTER_KIND_WIDTH, "polarity": FILTER_POLARITY_IF,
        "lo": 100, "hi": 500,
    }
    c = condition_from_dict(data)
    assert c.lo == 100.0 and isinstance(c.lo, float)
    assert c.hi == 500.0 and isinstance(c.hi, float)


def test_condition_from_dict_raises_loudly_on_missing_field():
    with pytest.raises(KeyError):
        condition_from_dict({"kind": FILTER_KIND_WIDTH, "lo": 1, "hi": 2})


def test_condition_from_dict_raises_loudly_on_unparsable_bound():
    with pytest.raises(ValueError):
        condition_from_dict({
            "kind": FILTER_KIND_WIDTH, "polarity": FILTER_POLARITY_IF,
            "lo": "not-a-number", "hi": 2,
        })
