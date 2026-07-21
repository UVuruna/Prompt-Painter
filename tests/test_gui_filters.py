"""FilterEditor + the aspect-filter settings migration (GUI rework
Phase 4, owner decision 2026-07-21).

Two halves:

* the settings migration (``gui._migrate_legacy_aspect_filter``) is a
  PURE dict -> list[dict] function — no Tk, no widget, runs like any
  other pytest test;
* ``FilterEditor`` is a real ``ttk.Frame``/CTk composite widget, so
  exercising its public ``get_conditions``/``set_conditions`` API for
  real needs an actual (but withdrawn, never mapped/mainloop'd) Tk
  root — the FIRST tests in the suite to do so (gui.py's other tests
  stick to pure helpers + fakes, per its own "barely Tk-unit-tested by
  design" convention). They share conftest.py's session-scoped
  ``tk_root`` — see that fixture's docstring for why a SECOND
  independently created-and-destroyed root breaks gui.py's icon cache.
"""

import pytest

import gui
from painter import filters
from painter.config import (
    ASPECT_FILTER_IF,
    ASPECT_FILTER_IF_NOT,
    ASPECT_FILTER_OFF,
    FILTER_ASPECT_EXACT_TOL,
    FILTER_KIND_ASPECT_EXACT,
    FILTER_KIND_ASPECT_RANGE,
    FILTER_KIND_WIDTH,
    FILTER_POLARITY_IF,
    FILTER_POLARITY_IF_NOT,
)

# ---------------------------------------------------------------------
# _migrate_legacy_aspect_filter — pure, Tk-free
# ---------------------------------------------------------------------


def test_migrate_owners_real_dict_to_one_if_not_aspect_range_condition():
    """The exact shape the owner's real settings.json carries today
    (2026-07-21): a 0.9-1.1 IF-NOT band. Must become ONE Aspect (range)
    condition with the SAME numbers and polarity — only the container
    changes, so the migrated filter behaves identically to the old
    scalar one."""
    stored = {"from": 0.9, "to": 1.1, "mode": "IF NOT"}
    migrated = gui._migrate_legacy_aspect_filter(stored)
    assert migrated == [
        {
            "kind": FILTER_KIND_ASPECT_RANGE,
            "polarity": FILTER_POLARITY_IF_NOT,
            "lo": 0.9,
            "hi": 1.1,
        }
    ]
    # and it round-trips through the real deserializer into something
    # that reproduces the OLD change_aspect(filter_mode=IF_NOT) verdict
    [condition] = [filters.condition_from_dict(d) for d in migrated]
    assert filters.matches(1000, 1000, [condition]) is False  # 1.0 in-band -> IF NOT fails
    assert filters.matches(2000, 1000, [condition]) is True   # 2.0 out-of-band -> IF NOT passes


def test_migrate_off_mode_is_an_empty_list():
    """off carried no filtering — an empty conditions list already
    matches everything, so no special-casing is needed downstream."""
    assert gui._migrate_legacy_aspect_filter(
        {"from": 0.9, "to": 1.1, "mode": ASPECT_FILTER_OFF}
    ) == []


def test_migrate_missing_mode_defaults_to_off():
    assert gui._migrate_legacy_aspect_filter({}) == []


def test_migrate_if_mode_uses_if_polarity():
    stored = {"from": 0.5, "to": 2.0, "mode": ASPECT_FILTER_IF}
    [d] = gui._migrate_legacy_aspect_filter(stored)
    assert d["polarity"] == FILTER_POLARITY_IF
    assert d["kind"] == FILTER_KIND_ASPECT_RANGE
    assert d["lo"] == 0.5 and d["hi"] == 2.0


def test_migrate_missing_from_to_falls_back_to_config_defaults():
    from painter.config import ASPECT_FILTER_DEFAULT_FROM, ASPECT_FILTER_DEFAULT_TO

    [d] = gui._migrate_legacy_aspect_filter({"mode": ASPECT_FILTER_IF})
    assert d["lo"] == ASPECT_FILTER_DEFAULT_FROM
    assert d["hi"] == ASPECT_FILTER_DEFAULT_TO


def test_migrate_unrecognised_mode_raises_loudly():
    with pytest.raises(ValueError):
        gui._migrate_legacy_aspect_filter({"from": 0.9, "to": 1.1, "mode": "bogus"})


# --- _parse_condition_dicts: tolerant, loud-on-drop ----------------------


def test_parse_condition_dicts_round_trips_good_data():
    log: list[str] = []
    dicts = [
        {"kind": FILTER_KIND_WIDTH, "polarity": FILTER_POLARITY_IF, "lo": 1, "hi": 2},
    ]
    out = gui._parse_condition_dicts(dicts, log.append)
    assert out == [filters.FilterCondition(FILTER_KIND_WIDTH, FILTER_POLARITY_IF, 1.0, 2.0)]
    assert log == []


def test_parse_condition_dicts_drops_bad_entries_loudly():
    log: list[str] = []
    dicts = [
        {"kind": FILTER_KIND_WIDTH, "polarity": FILTER_POLARITY_IF, "lo": 1, "hi": 2},
        {"kind": FILTER_KIND_WIDTH},  # missing polarity/lo/hi
        "not-even-a-dict",
    ]
    out = gui._parse_condition_dicts(dicts, log.append)
    assert len(out) == 1  # only the good one survives
    assert len(log) == 2  # both bad entries logged, not silently dropped


# ---------------------------------------------------------------------
# FilterEditor — a real (withdrawn) Tk root
# ---------------------------------------------------------------------


@pytest.fixture
def root(tk_root):
    """This module's tests were written against the name ``root``;
    ``tk_root`` (conftest.py, session-scoped) is the actual shared Tk
    interpreter they all reuse."""
    return tk_root


def test_filter_editor_starts_empty_with_no_conditions_argument(root):
    editor = gui.FilterEditor(root)
    assert editor.get_conditions() == []


def test_filter_editor_starts_with_the_given_conditions(root):
    seed = [
        filters.FilterCondition(FILTER_KIND_ASPECT_RANGE, FILTER_POLARITY_IF, 0.9, 1.1),
    ]
    editor = gui.FilterEditor(root, conditions=seed)
    assert editor.get_conditions() == seed


def test_filter_editor_set_then_get_round_trips_multiple_conditions(root):
    editor = gui.FilterEditor(root)
    conditions = [
        filters.FilterCondition(FILTER_KIND_ASPECT_RANGE, FILTER_POLARITY_IF, 0.9, 1.1),
        filters.FilterCondition(FILTER_KIND_WIDTH, FILTER_POLARITY_IF_NOT, 100.0, 500.0),
    ]
    editor.set_conditions(conditions)
    assert editor.get_conditions() == conditions


def test_filter_editor_set_conditions_replaces_not_appends(root):
    editor = gui.FilterEditor(root)
    editor.set_conditions(
        [filters.FilterCondition(FILTER_KIND_WIDTH, FILTER_POLARITY_IF, 1.0, 2.0)]
    )
    editor.set_conditions(
        [filters.FilterCondition(FILTER_KIND_WIDTH, FILTER_POLARITY_IF, 3.0, 4.0)]
    )
    got = editor.get_conditions()
    assert len(got) == 1
    assert got[0].lo == 3.0 and got[0].hi == 4.0


def test_filter_editor_add_default_row_then_remove(root):
    editor = gui.FilterEditor(root)
    editor._add_default_row()
    assert len(editor.get_conditions()) == 1
    editor._remove_row(editor._rows[0])
    assert editor.get_conditions() == []


def test_filter_editor_get_conditions_raises_on_unparsable_row(root):
    editor = gui.FilterEditor(root)
    editor._add_default_row()
    editor._rows[0].lo_var.set("not-a-number")
    with pytest.raises(ValueError):
        editor.get_conditions()


def test_filter_editor_get_conditions_raises_when_from_exceeds_to(root):
    editor = gui.FilterEditor(root)
    editor._add_default_row()
    editor._rows[0].lo_var.set("5")
    editor._rows[0].hi_var.set("1")
    with pytest.raises(ValueError):
        editor.get_conditions()


# --- the exact-aspect tolerance band (fixes Phase 3's flagged caveat) ---


def test_aspect_exact_round_trips_through_the_tolerance_band(root):
    """A single-ratio 'Aspect (exact)' condition round-trips through
    display (midpoint) <-> store (+/-FILTER_ASPECT_EXACT_TOL band): the
    band width must be exactly 2*tol, centred on the original ratio —
    never the razor-thin lo==hi Phase 3 flagged as unmatchable against
    a real decoded image."""
    editor = gui.FilterEditor(root)
    editor.set_conditions([
        filters.FilterCondition(FILTER_KIND_ASPECT_EXACT, FILTER_POLARITY_IF, 1.0, 1.0),
    ])
    [got] = editor.get_conditions()
    assert got.kind == FILTER_KIND_ASPECT_EXACT
    assert got.lo == pytest.approx(1.0 - FILTER_ASPECT_EXACT_TOL)
    assert got.hi == pytest.approx(1.0 + FILTER_ASPECT_EXACT_TOL)
    assert got.hi - got.lo == pytest.approx(2 * FILTER_ASPECT_EXACT_TOL)


def test_aspect_exact_tolerance_band_matches_a_real_near_square_image(root):
    """The concrete motivating example: a 1000x1001 export is NOT
    exactly ratio 1.0, so the OLD razor-thin lo==hi would miss it — the
    widened band must catch it."""
    editor = gui.FilterEditor(root)
    editor.set_conditions([
        filters.FilterCondition(FILTER_KIND_ASPECT_EXACT, FILTER_POLARITY_IF, 1.0, 1.0),
    ])
    [got] = editor.get_conditions()
    assert filters.matches(1000, 1001, [got]) is True


# --- presets: save / load / delete, shared-dict + change callback -------


def test_filter_editor_save_load_delete_preset_round_trip(root):
    presets: dict = {}
    changes = []
    editor = gui.FilterEditor(
        root, presets=presets, on_presets_changed=lambda: changes.append(1)
    )
    editor.set_conditions([
        filters.FilterCondition(FILTER_KIND_WIDTH, FILTER_POLARITY_IF, 1.0, 2.0),
    ])
    editor._preset_var.set("square badges")
    editor._save_preset()

    assert "square badges" in presets  # the CALLER's own dict reference saw it
    assert changes == [1]

    editor.set_conditions([])
    editor._preset_var.set("square badges")
    editor._load_preset()
    assert editor.get_conditions() == [
        filters.FilterCondition(FILTER_KIND_WIDTH, FILTER_POLARITY_IF, 1.0, 2.0),
    ]

    editor._delete_preset()
    assert presets == {}
    assert changes == [1, 1]  # save + delete each triggered the callback once


def test_filter_editor_without_injected_presets_still_works_standalone(root):
    """No presets dict / callback given (the headless-test / future
    standalone-panel case) — Save/Load/Delete must still work against
    a private dict, never raise on the missing callback."""
    editor = gui.FilterEditor(root)
    editor._preset_var.set("temp")
    editor._save_preset()
    assert "temp" in editor._presets
    editor._delete_preset()
    assert "temp" not in editor._presets
