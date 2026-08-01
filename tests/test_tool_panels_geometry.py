"""``CropSettingsPanel``/``UpscaleSettingsPanel``/``AspectSettingsPanel``
— the three geometry-family standalone-tool panels.

Split from the former ``test_gui_tool_panels.py`` god-file (root Rule
#20, second round — the source split into ``gui/tool_panels/`` package
2026-07-30, this test module follows it 1:1: everything
``gui/tool_panels/geometry.py`` defines).

``UpscaleSettingsPanel``/``AspectSettingsPanel`` (GUI rework Phase 14,
replacing the retired ``UpscaleParamsDialog``/``AspectRatioDialog``
modals) follow the SAME base contract as Crop, proven the SAME way:
Upscale's min-side spinner reaching ``build_func()``'s
``upscale_if_small`` call (cross-checked against
``_upscale_params_from_side_and_filter``'s own resolution,
test_gui_upscale.py's proven table); Aspect's target-ratio W/H entries
+ canvas two-way sync + ``build_func()``'s ``change_aspect`` call.
"""

from __future__ import annotations

import pytest

import gui
from painter import filters
from painter.config import (
    ASPECT_DEFAULT_H,
    ASPECT_DEFAULT_W,
    CLEAN_EDGE_ENABLE,
    CROP_INK_ALPHA,
    CROP_MARGIN_PX,
    CROP_MIN_INK_PX,
    FILTER_KIND_ASPECT_RANGE,
    FILTER_KIND_WIDTH,
    FILTER_POLARITY_IF,
    UPSCALE_ASPECT_MAX,
    UPSCALE_ASPECT_MIN,
    UPSCALE_MIN_SIDE_DEFAULT,
)
from painter.jobtemp import clear_all
import painter.postprocess as postprocess_module


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
# CropSettingsPanel — advanced defaults + build_func
# ---------------------------------------------------------------------


def test_crop_panel_advanced_defaults_match_config(root):
    panel = make_panel(gui.CropSettingsPanel, root)
    assert panel.clean_edge_var.get() == CLEAN_EDGE_ENABLE
    assert panel.margin_var.get() == str(CROP_MARGIN_PX)
    assert panel.ink_alpha_var.get() == str(CROP_INK_ALPHA)
    assert panel.min_ink_var.get() == str(CROP_MIN_INK_PX)


def test_crop_build_func_passes_every_overridden_field(root, monkeypatch, tmp_path):
    calls: list[dict] = []

    def fake_crop_transparent(path, log, **kwargs):
        calls.append(kwargs)
        return "done"

    monkeypatch.setattr(
        postprocess_module, "crop_transparent", fake_crop_transparent
    )
    panel = make_panel(gui.CropSettingsPanel, root)
    panel.clean_edge_var.set(False)
    panel.margin_var.set("0")
    panel.ink_alpha_var.set("100")
    panel.min_ink_var.set("7")
    func = panel.build_func()
    func(tmp_path / "x.png", print)

    assert calls == [{
        "clean_edge_enable": False,
        "crop_margin_px": 0,
        "crop_ink_alpha": 100,
        "crop_min_ink_px": 7,
    }]


def test_crop_build_func_raises_on_an_out_of_range_ink_alpha(root):
    panel = make_panel(gui.CropSettingsPanel, root)
    panel.ink_alpha_var.set("999")
    with pytest.raises(ValueError, match="ink alpha"):
        panel.build_func()


def test_crop_panel_settings_round_trip(root):
    panel = make_panel(gui.CropSettingsPanel, root)
    panel.clean_edge_var.set(False)
    panel.margin_var.set("9")
    panel.ink_alpha_var.set("55")
    panel.min_ink_var.set("2")

    stored = panel.get_settings()
    assert stored["clean_edge_enable"] is False
    assert stored["margin_px"] == "9"
    assert stored["ink_alpha"] == "55"
    assert stored["min_ink_px"] == "2"

    fresh = make_panel(gui.CropSettingsPanel, root)
    fresh.apply_settings(stored, conditions=None)
    assert fresh.clean_edge_var.get() is False
    assert fresh.margin_var.get() == "9"
    assert fresh.ink_alpha_var.get() == "55"
    assert fresh.min_ink_var.get() == "2"


# ---------------------------------------------------------------------
# UpscaleSettingsPanel (GUI rework Phase 14)
# ---------------------------------------------------------------------


def test_upscale_panel_seeds_the_default_min_side_and_aspect_condition(root):
    panel = make_panel(gui.UpscaleSettingsPanel, root)
    assert panel.up_minside_var.get() == str(UPSCALE_MIN_SIDE_DEFAULT)
    [c] = panel.filter.get_conditions()
    assert c.kind == FILTER_KIND_ASPECT_RANGE
    assert c.polarity == FILTER_POLARITY_IF
    assert c.lo == UPSCALE_ASPECT_MIN and c.hi == UPSCALE_ASPECT_MAX


def test_upscale_panel_has_no_advanced_section(root):
    """HAS_ADVANCED = False — the min-side spinner is the panel's own
    PRIMARY control (_build_extra), not tucked behind a gear."""
    panel = make_panel(gui.UpscaleSettingsPanel, root)
    assert not hasattr(panel, "_advanced_box")
    assert not hasattr(panel, "_advanced_btn")


def test_upscale_panel_build_func_reaches_the_real_engine(
    root, monkeypatch, tmp_path,
):
    """The exact 'non-default override reaches the engine call' proof
    (same convention as test_bg_build_func_passes_the_overridden_
    safety_fractions): a non-default min-side flows through build_func
    into upscale_if_small's kwargs, resolved the SAME way
    _upscale_params_from_side_and_filter already proves
    (test_gui_upscale.py)."""
    import painter.upscale as upscale_module

    calls: list[dict] = []

    def fake_upscale_if_small(path, log, **params):
        calls.append(params)
        return "done"

    monkeypatch.setattr(
        upscale_module, "upscale_if_small", fake_upscale_if_small
    )
    panel = make_panel(gui.UpscaleSettingsPanel, root)
    panel.up_minside_var.set("950")
    func = panel.build_func()
    func(tmp_path / "x.png", print)

    assert calls == [{
        "min_width": 950, "min_height": 950,
        "aspect_min": UPSCALE_ASPECT_MIN, "aspect_max": UPSCALE_ASPECT_MAX,
    }]


def test_upscale_panel_build_func_raises_on_a_non_numeric_min_side(root):
    panel = make_panel(gui.UpscaleSettingsPanel, root)
    panel.up_minside_var.set("not-a-number")
    with pytest.raises(ValueError, match="Min side must be a number"):
        panel.build_func()


def test_upscale_panel_build_func_raises_on_a_non_positive_min_side(root):
    panel = make_panel(gui.UpscaleSettingsPanel, root)
    panel.up_minside_var.set("0")
    with pytest.raises(ValueError, match="Min side must be positive"):
        panel.build_func()


def test_upscale_panel_settings_round_trip(root):
    """The core Phase-14 promise for Upscale: the min-side spinner
    round-trips through get_settings()/apply_settings() alongside the
    filter stack, and 'advanced_collapsed' is never emitted (HAS_
    ADVANCED = False, same contract ToolSettingsPanel.get_settings
    documents)."""
    panel = make_panel(gui.UpscaleSettingsPanel, root)
    panel.up_minside_var.set("950")
    panel.filter.set_conditions(
        [cond(FILTER_KIND_WIDTH, FILTER_POLARITY_IF, 100.0, 2000.0)]
    )

    stored = panel.get_settings()
    assert stored["up_minside"] == "950"
    assert "advanced_collapsed" not in stored
    assert stored["conditions"] == [
        filters.condition_to_dict(
            cond(FILTER_KIND_WIDTH, FILTER_POLARITY_IF, 100.0, 2000.0)
        )
    ]

    fresh = make_panel(gui.UpscaleSettingsPanel, root)
    conditions = gui._parse_condition_dicts(stored["conditions"], lambda _m: None)
    fresh.apply_settings(stored, conditions=conditions)
    assert fresh.up_minside_var.get() == "950"
    assert fresh.filter.get_conditions() == conditions


def test_upscale_panel_apply_settings_missing_keys_keep_the_seeded_default(
    root,
):
    panel = make_panel(gui.UpscaleSettingsPanel, root)
    panel.apply_settings({}, conditions=None)
    assert panel.up_minside_var.get() == str(UPSCALE_MIN_SIDE_DEFAULT)
    [c] = panel.filter.get_conditions()
    assert c.lo == UPSCALE_ASPECT_MIN and c.hi == UPSCALE_ASPECT_MAX


# ---------------------------------------------------------------------
# AspectSettingsPanel (GUI rework Phase 14)
# ---------------------------------------------------------------------


def test_aspect_panel_seeds_the_default_ratio_and_an_empty_filter(root):
    panel = make_panel(gui.AspectSettingsPanel, root)
    assert panel.target_ratio() == (ASPECT_DEFAULT_W, ASPECT_DEFAULT_H)
    assert panel.filter.get_conditions() == []


def test_aspect_panel_has_no_advanced_section(root):
    panel = make_panel(gui.AspectSettingsPanel, root)
    assert not hasattr(panel, "_advanced_box")
    assert not hasattr(panel, "_advanced_btn")


def test_aspect_panel_canvas_drag_updates_the_wh_fields(root):
    panel = make_panel(gui.AspectSettingsPanel, root)
    panel._on_canvas_drag(4, 3)
    assert panel._ratio_w_var.get() == "4"
    assert panel._ratio_h_var.get() == "3"
    assert panel.target_ratio() == (4, 3)


def test_aspect_panel_typing_reshapes_the_canvas(root):
    panel = make_panel(gui.AspectSettingsPanel, root)
    panel._ratio_w_var.set("21")
    panel._ratio_h_var.set("9")
    assert (
        panel._ratio_canvas._ratio_w, panel._ratio_canvas._ratio_h,
    ) == (21, 9)


def test_aspect_panel_typing_a_bad_value_is_silently_skipped(root):
    panel = make_panel(gui.AspectSettingsPanel, root)
    panel._ratio_w_var.set("not-a-number")  # mid-edit, never an error
    assert (
        panel._ratio_canvas._ratio_w, panel._ratio_canvas._ratio_h,
    ) == (ASPECT_DEFAULT_W, ASPECT_DEFAULT_H)


def test_aspect_panel_target_ratio_raises_on_non_numeric(root):
    panel = make_panel(gui.AspectSettingsPanel, root)
    panel._ratio_w_var.set("abc")
    with pytest.raises(ValueError, match="whole numbers"):
        panel.target_ratio()


def test_aspect_panel_target_ratio_raises_on_non_positive(root):
    panel = make_panel(gui.AspectSettingsPanel, root)
    panel._ratio_w_var.set("0")
    with pytest.raises(ValueError, match="positive"):
        panel.target_ratio()


def test_aspect_panel_build_func_calls_change_aspect_with_the_target_ratio(
    root, monkeypatch, tmp_path,
):
    import painter.aspect as aspect_module

    calls: list[tuple] = []

    def fake_change_aspect(path, w, h, log):
        calls.append((path, w, h))
        return "done"

    monkeypatch.setattr(aspect_module, "change_aspect", fake_change_aspect)
    panel = make_panel(gui.AspectSettingsPanel, root)
    panel._ratio_w_var.set("4")
    panel._ratio_h_var.set("3")
    func = panel.build_func()
    img = tmp_path / "x.png"
    func(img, print)

    assert calls == [(img, 4, 3)]


def test_aspect_panel_target_ratio_and_filter_round_trip(root):
    """The core Phase-14 promise for Aspect: BOTH the target ratio
    (canvas + entries) and the stacked filter survive get_settings()/
    apply_settings() — the same 'missing key = keep default' contract
    every other panel already has, and 'advanced_collapsed' is never
    emitted (HAS_ADVANCED = False)."""
    panel = make_panel(gui.AspectSettingsPanel, root)
    panel._ratio_w_var.set("21")
    panel._ratio_h_var.set("9")
    panel.filter.set_conditions(
        [cond(FILTER_KIND_WIDTH, FILTER_POLARITY_IF, 500.0, 5000.0)]
    )

    stored = panel.get_settings()
    assert stored["ratio"] == ["21", "9"]
    assert "advanced_collapsed" not in stored
    assert stored["conditions"] == [
        filters.condition_to_dict(
            cond(FILTER_KIND_WIDTH, FILTER_POLARITY_IF, 500.0, 5000.0)
        )
    ]

    fresh = make_panel(gui.AspectSettingsPanel, root)
    conditions = gui._parse_condition_dicts(stored["conditions"], lambda _m: None)
    fresh.apply_settings(stored, conditions=conditions)
    assert fresh.target_ratio() == (21, 9)
    assert fresh.filter.get_conditions() == conditions
    # the canvas itself reflects the restored ratio, not just the vars
    assert (
        fresh._ratio_canvas._ratio_w, fresh._ratio_canvas._ratio_h,
    ) == (21, 9)


def test_aspect_panel_apply_settings_missing_keys_keep_the_default(root):
    panel = make_panel(gui.AspectSettingsPanel, root)
    panel.apply_settings({}, conditions=None)
    assert panel.target_ratio() == (ASPECT_DEFAULT_W, ASPECT_DEFAULT_H)
    assert panel.filter.get_conditions() == []


def test_aspect_panel_apply_settings_ignores_a_malformed_ratio(root):
    """A hand-corrupted or partial 'ratio' value never crashes the
    settings load — the widget's own current value survives untouched
    (same 'corrupt value, honest fallback' precedent as every other
    migration/restore path in this file)."""
    panel = make_panel(gui.AspectSettingsPanel, root)
    panel.apply_settings({"ratio": ["not-a-number", "9"]}, conditions=None)
    assert panel.target_ratio() == (ASPECT_DEFAULT_W, ASPECT_DEFAULT_H)

    panel.apply_settings({"ratio": [0, 9]}, conditions=None)
    assert panel.target_ratio() == (ASPECT_DEFAULT_W, ASPECT_DEFAULT_H)
