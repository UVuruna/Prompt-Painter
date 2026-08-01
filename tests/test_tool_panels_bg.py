"""``BgSettingsPanel`` — the background-removal standalone-tool panel.

Split from the former ``test_gui_tool_panels.py`` god-file (root Rule
#20, second round — the source split into ``gui/tool_panels/`` package
2026-07-30, this test module follows it 1:1: everything
``gui/tool_panels/bg.py`` defines). Base-class contract tests that
merely use ``BgSettingsPanel`` as a convenient instantiation vehicle
live in test_tool_panels_base.py instead — see that module's docstring.

Covers the Advanced overrides reaching ``build_func()``'s engine call
(proving a NON-DEFAULT override actually arrives, not just accepted
and silently ignored — root Rule #1), the background mode + custom
colour block (owner 2026-07-28), and the settings round-trip.
"""

from __future__ import annotations

from types import SimpleNamespace

import pytest

import gui
import painter.postprocess as postprocess_module
from painter import filters
from painter.config import (
    BG_COLOR_DEFAULT,
    BG_COLOR_TOLERANCE_PCT,
    BG_MODE_AUTO,
    BG_MODE_BLACK,
    BG_MODE_COLOR,
    BG_MODE_LABEL,
    BG_REACH_ALL,
    BG_REACH_EDGE,
    BG_REACH_LABEL,
    FILTER_KIND_WIDTH,
    FILTER_POLARITY_IF,
    SAFETY_MAX_REMOVE_FRAC,
    SAFETY_MAX_REMOVE_FRAC_COLOR,
    SAFETY_MAX_REMOVE_FRAC_WHITE,
)
from painter.jobtemp import clear_all


@pytest.fixture(autouse=True)
def _sweep_temp():
    yield
    clear_all()


@pytest.fixture
def root(tk_root):
    return tk_root


def cond(kind: str, polarity: str, lo: float, hi: float) -> filters.FilterCondition:
    return filters.FilterCondition(kind=kind, polarity=polarity, lo=lo, hi=hi)


def make_panel(cls, root):
    return cls(
        root, on_start=lambda *_a: None, on_pause=lambda *_a: None,
        on_stop=lambda *_a: None,
    )


# ---------------------------------------------------------------------
# Advanced overrides reaching the engine function (build_func)
# ---------------------------------------------------------------------


def test_bg_panel_advanced_defaults_match_config(root):
    panel = make_panel(gui.BgSettingsPanel, root)
    # the guards are shown as PERCENT, not the engine's raw fraction
    assert panel.safety_black_var.get() == "40"
    assert panel.safety_white_var.get() == "85"
    assert panel.safety_color_var.get() == "85"
    assert float(panel.safety_black_var.get()) / 100 == SAFETY_MAX_REMOVE_FRAC
    assert (float(panel.safety_white_var.get()) / 100
            == SAFETY_MAX_REMOVE_FRAC_WHITE)
    assert (float(panel.safety_color_var.get()) / 100
            == SAFETY_MAX_REMOVE_FRAC_COLOR)
    assert panel.bg_mode_var.get() == BG_MODE_LABEL[BG_MODE_AUTO]
    assert panel.bg_color_var.get() == BG_COLOR_DEFAULT
    assert panel.bg_tolerance_var.get() == f"{BG_COLOR_TOLERANCE_PCT:.2f}"


def test_bg_build_func_passes_the_overridden_safety_fractions(
    root, monkeypatch, tmp_path,
):
    """The exact 'non-default override reaches the engine function'
    proof: a NON-default panel value flows through build_func's
    closure into remove_background's own kwargs."""
    calls: list[dict] = []

    def fake_remove_background(path, log, **kwargs):
        calls.append(kwargs)
        return "done"

    monkeypatch.setattr(
        postprocess_module, "remove_background", fake_remove_background
    )
    panel = make_panel(gui.BgSettingsPanel, root)
    # typed as PERCENT — the engine still receives the fraction
    panel.safety_black_var.set("10")
    panel.safety_white_var.set("20")
    panel.safety_color_var.set("30")
    func = panel.build_func()
    func(tmp_path / "x.png", print)

    assert calls == [{
        "mode": BG_MODE_AUTO,
        "color": BG_COLOR_DEFAULT,
        "tolerance_pct": BG_COLOR_TOLERANCE_PCT,
        "reach": BG_REACH_EDGE,
        "safety_max_remove_frac": 0.10,
        "safety_max_remove_frac_white": 0.20,
        "safety_max_remove_frac_color": 0.30,
    }]


def test_bg_build_func_raises_on_a_non_numeric_safety_field(root):
    panel = make_panel(gui.BgSettingsPanel, root)
    panel.safety_black_var.set("not-a-number")
    with pytest.raises(ValueError, match="black bg safety"):
        panel.build_func()


def test_bg_build_func_raises_on_an_out_of_range_safety_percent(root):
    panel = make_panel(gui.BgSettingsPanel, root)
    panel.safety_black_var.set("140")
    with pytest.raises(ValueError, match="black bg safety"):
        panel.build_func()


def test_bg_guard_settings_from_the_fraction_build_are_not_misread(root):
    """The guard fields changed UNIT (fraction -> percent). A
    settings.json written by the fraction build holds "0.40" under the
    OLD bare key; read as percent that would be a 0.4 % guard that
    refuses every image. The renamed _pct key means such a file falls
    back to the correct defaults instead."""
    panel = make_panel(gui.BgSettingsPanel, root)
    panel.apply_settings({
        "safety_black": "0.40", "safety_white": "0.85",
        "safety_color": "0.85",
    })
    assert panel.safety_black_var.get() == "40"
    assert panel.safety_white_var.get() == "85"


# --- background mode + custom colour (owner 2026-07-28) ---------------


def test_bg_build_func_passes_the_chosen_mode_and_custom_colour(
    root, monkeypatch, tmp_path,
):
    """The owner's 'pointers' way through: state the colour, and the
    mode/colour/tolerance really reach the engine call."""
    calls: list[dict] = []
    monkeypatch.setattr(
        postprocess_module, "remove_background",
        lambda path, log, **kw: (calls.append(kw), "done")[1],
    )
    panel = make_panel(gui.BgSettingsPanel, root)
    panel.bg_mode_var.set(BG_MODE_LABEL[BG_MODE_COLOR])
    panel.bg_color_var.set("#FF0000")
    panel.bg_tolerance_var.set("6.67")
    panel.build_func()(tmp_path / "x.png", print)

    assert calls[0]["mode"] == BG_MODE_COLOR
    assert calls[0]["color"] == "#FF0000"
    assert calls[0]["tolerance_pct"] == 6.67


def test_bg_build_func_raises_on_a_mistyped_custom_colour(root):
    """Rule #1 — a bad colour stops Start, it does not start a run that
    silently clears the wrong thing."""
    panel = make_panel(gui.BgSettingsPanel, root)
    panel.bg_mode_var.set(BG_MODE_LABEL[BG_MODE_COLOR])
    panel.bg_color_var.set("#GGGGGG")
    with pytest.raises(ValueError, match="background color"):
        panel.build_func()


def test_bg_a_bad_colour_is_ignored_while_the_mode_does_not_use_it(root):
    """The same unparsable text is HARMLESS in Auto/Black/White — the
    colour field is not part of those modes."""
    panel = make_panel(gui.BgSettingsPanel, root)
    panel.bg_color_var.set("#GGGGGG")
    panel.bg_mode_var.set(BG_MODE_LABEL[BG_MODE_BLACK])
    assert panel.build_func() is not None


def test_bg_build_func_raises_on_an_out_of_range_tolerance(root):
    panel = make_panel(gui.BgSettingsPanel, root)
    panel.bg_tolerance_var.set("150")
    with pytest.raises(ValueError, match="background tolerance"):
        panel.build_func()


def test_bg_colour_fields_show_only_in_custom_mode(root):
    """A colour field sitting live beside 'Auto' would read as if it
    applied (Rule #1) — it is packed only in Custom mode."""
    panel = make_panel(gui.BgSettingsPanel, root)
    assert not panel._color_box.winfo_manager()

    panel.bg_mode_var.set(BG_MODE_LABEL[BG_MODE_COLOR])
    panel._apply_color_visibility()
    assert panel._color_box.winfo_manager()

    panel.bg_mode_var.set(BG_MODE_LABEL[BG_MODE_AUTO])
    panel._apply_color_visibility()
    assert not panel._color_box.winfo_manager()


def test_bg_reach_choice_reaches_the_engine(root, monkeypatch, tmp_path):
    """The owner's added option (2026-07-28) is a REAL parameter, not a
    dropdown that does nothing."""
    calls: list[dict] = []
    monkeypatch.setattr(
        postprocess_module, "remove_background",
        lambda path, log, **kw: (calls.append(kw), "done")[1],
    )
    panel = make_panel(gui.BgSettingsPanel, root)
    panel.bg_reach_var.set(BG_REACH_LABEL[BG_REACH_ALL])
    panel.build_func()(tmp_path / "x.png", print)
    assert calls[0]["reach"] == BG_REACH_ALL


def test_bg_reach_defaults_to_border_connected(root):
    """The default must stay the flood fill — enclosed regions (the
    counters inside letters, the black leading between glass) survive
    unless the owner asks otherwise."""
    panel = make_panel(gui.BgSettingsPanel, root)
    assert panel.bg_reach_var.get() == BG_REACH_LABEL[BG_REACH_EDGE]


def test_bg_reach_round_trips_and_keeps_its_hint_in_step(root):
    panel = make_panel(gui.BgSettingsPanel, root)
    panel.bg_reach_var.set(BG_REACH_LABEL[BG_REACH_ALL])
    panel._sync_reach_hint()
    assert "enclosed ones too" in panel._reach_hint.get()

    fresh = make_panel(gui.BgSettingsPanel, root)
    fresh.apply_settings(panel.get_settings())
    assert fresh.bg_reach_var.get() == BG_REACH_LABEL[BG_REACH_ALL]
    assert "enclosed ones too" in fresh._reach_hint.get()


def test_bg_swatch_click_opens_the_picker_and_writes_the_hex_back(
    root, monkeypatch,
):
    """Clicking the swatch opens a real color chooser (owner
    2026-07-28); whatever it returns is normalised to #RRGGBB."""
    import ttkbootstrap.dialogs.colorchooser as chooser

    class FakeDialog:
        def __init__(self, parent, title, initialcolor):
            FakeDialog.initial = initialcolor
            self.result = SimpleNamespace(hex="#3a5f7d")

        def show(self):
            pass

    monkeypatch.setattr(chooser, "ColorChooserDialog", FakeDialog)
    panel = make_panel(gui.BgSettingsPanel, root)
    panel.bg_color_var.set("#f00")
    panel._pick_color()

    assert FakeDialog.initial == "#FF0000"   # opened on the current color
    assert panel.bg_color_var.get() == "#3A5F7D"


def test_bg_swatch_click_cancelled_leaves_the_colour_alone(root, monkeypatch):
    import ttkbootstrap.dialogs.colorchooser as chooser

    class CancelledDialog:
        def __init__(self, *_a):
            self.result = None

        def show(self):
            pass

    monkeypatch.setattr(chooser, "ColorChooserDialog", CancelledDialog)
    panel = make_panel(gui.BgSettingsPanel, root)
    panel.bg_color_var.set("#123456")
    panel._pick_color()
    assert panel.bg_color_var.get() == "#123456"


def test_bg_settings_round_trip_carries_mode_colour_and_guards(root):
    panel = make_panel(gui.BgSettingsPanel, root)
    panel.bg_mode_var.set(BG_MODE_LABEL[BG_MODE_COLOR])
    panel.bg_color_var.set("#3A5F7D")
    panel.bg_tolerance_var.set("8.5")
    panel.safety_color_var.set("55")
    stored = panel.get_settings()
    assert stored["bg_mode"] == BG_MODE_COLOR  # the KEY, never the label

    fresh = make_panel(gui.BgSettingsPanel, root)
    fresh.apply_settings(stored)
    assert fresh.bg_mode_var.get() == BG_MODE_LABEL[BG_MODE_COLOR]
    assert fresh.bg_color_var.get() == "#3A5F7D"
    assert fresh.bg_tolerance_var.get() == "8.5"
    assert fresh.safety_color_var.get() == "55"
    assert fresh._color_box.winfo_manager()  # visibility followed the mode


def test_bg_settings_round_trip_ignores_an_unknown_stored_mode(root):
    """A settings.json from a build whose mode list differed keeps the
    current default instead of putting an unresolvable label in the
    dropdown."""
    panel = make_panel(gui.BgSettingsPanel, root)
    panel.apply_settings({"bg_mode": "no-such-mode"})
    assert panel.bg_mode_var.get() == BG_MODE_LABEL[BG_MODE_AUTO]


# ---------------------------------------------------------------------
# Settings round-trip
# ---------------------------------------------------------------------


def test_bg_panel_settings_round_trip(root):
    panel = make_panel(gui.BgSettingsPanel, root)
    panel.filter.set_conditions(
        [cond(FILTER_KIND_WIDTH, FILTER_POLARITY_IF, 10.0, 20.0)]
    )
    panel.safety_black_var.set("55")
    panel.safety_white_var.set("90")
    panel._advanced_collapsed_var.set(False)
    panel._apply_advanced_visibility()

    stored = panel.get_settings()
    assert stored["safety_black_pct"] == "55"
    assert stored["safety_white_pct"] == "90"
    assert stored["advanced_collapsed"] is False
    assert stored["conditions"] == [
        filters.condition_to_dict(cond(FILTER_KIND_WIDTH, FILTER_POLARITY_IF, 10.0, 20.0))
    ]

    fresh = make_panel(gui.BgSettingsPanel, root)
    conditions = gui._parse_condition_dicts(stored["conditions"], lambda _m: None)
    fresh.apply_settings(stored, conditions=conditions)
    assert fresh.safety_black_var.get() == "55"
    assert fresh.safety_white_var.get() == "90"
    assert fresh._advanced_collapsed_var.get() is False
    assert fresh._advanced_box.winfo_manager() == "pack"
    assert fresh.filter.get_conditions() == conditions
