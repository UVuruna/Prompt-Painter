"""Standalone-tool persistent settings panels — BG removal / Crop (GUI
rework Phase 13), Upscale / Aspect ratio (Phase 14, same family).

Halves, matching gui.py's own "pure helpers get pytest, real Tk/UI
wiring gets a screenshot" split (___tests.md):

* ``gui._filter_files`` — the pre-filter every tool now shares
  (Aspect/Upscale already used it; BG/Crop gain it this phase) — real
  tiny PNGs on disk (it opens each candidate with PIL), no Tk at all.
  First-ever direct coverage (previously only exercised indirectly
  through the Aspect/Upscale flows).
* ``gui._parse_fraction``/``_parse_nonneg_int``/``_parse_int_range`` —
  the Advanced-override field parsers, pure and Tk-free.
* ``ToolSettingsPanel``/``BgSettingsPanel``/``CropSettingsPanel`` —
  real (withdrawn) Tk root widgets, same ``tk_root`` fixture every
  other GUI-phase test file already shares (see test_gui_filters.py's
  own docstring on why a second root breaks gui.py's icon cache):
  the input picker's ``resolve_input()`` (folder/files/nothing-picked),
  the embedded ``FilterEditor`` proxy, the Advanced fields reaching
  ``build_func()``'s engine call (proving a NON-DEFAULT override
  actually arrives, not just accepted and silently ignored — Rule #1),
  run-state/pause/STOP button reflection, and the settings round-trip.
* ``UpscaleSettingsPanel``/``AspectSettingsPanel`` (GUI rework Phase
  14, replacing the retired ``UpscaleParamsDialog``/
  ``AspectRatioDialog`` modals) — the SAME base contract as BG/Crop,
  proven the SAME way: Upscale's min-side spinner + seeded aspect
  condition reaching ``build_func()``'s ``upscale_if_small`` call
  (cross-checked against ``_upscale_params_from_side_and_filter``'s
  own resolution, test_gui_upscale.py's proven table); Aspect's
  target-ratio W/H entries + canvas two-way sync + ``build_func()``'s
  ``change_aspect`` call; both panels' settings round-trip
  (``up_minside``/``ratio`` — the ALWAYS-VISIBLE fields ``HAS_ADVANCED
  = False`` moves out of the collapsible, still carried by
  ``_advanced_settings``/``_apply_advanced_settings`` regardless, see
  ``ToolSettingsPanel``'s own docstring).
* ``PainterGui._start_tool_from_panel`` — the core Phase-13 promise
  ("given a folder + conditions, the right file subset is queued") —
  exercised through a small duck-typed ``FakeGuiForPanel`` (the SAME
  convention test_gui_pipeline.py's/test_gui_running_view.py's own
  FakeGui use: never a full ``PainterGui``). Its ``_run_tool_job`` is
  a RECORDING stand-in, never the real background worker — the worker
  loop itself has its own coverage (should_stop threading — GUI rework
  Phase 14 — in the "Stop" section below); this file only proves WHAT
  gets handed off to it.
* **Stop** (GUI rework Phase 14) — ``_run_tool_job``'s new
  ``stop_event`` halting the loop BETWEEN images (mirrors
  test_runner.py's own ``test_stop_flag_stops_between_items``, over a
  duck-typed fake ``self`` with a real ``queue.Queue`` so ``_q.put``
  has somewhere to land) and ``PainterGui._stop_tool``'s request half
  through ``FakeGuiForPanel``.
* ``ImageCheckerSettingsPanel`` (GUI rework Phase 15) — the SAME base
  contract as the other four, over the SAME ``make_panel``/``root``
  fixture: no Advanced section, the read-only ``_picker_title_suffix``
  override (never claims "runs IN PLACE"), input-picker/settings
  round-trip (only ``conditions`` — no extra fields). ``PainterGui.
  _start_ai_check`` (its OWN Start wiring — NOT
  ``_start_tool_from_panel``, see that method's docstring) gets the
  SAME "given a folder + conditions, the right file subset is queued"
  proof as the four tools, through a dedicated ``FakeGuiForAiCheck``
  (its ``_run_ai_check_job`` a RECORDING stand-in, exactly like
  ``FakeGuiForPanel``'s ``_run_tool_job``). **Stop** reuses
  ``PainterGui._stop_tool`` VERBATIM (no new method — see
  ``ImageCheckerSettingsPanel``'s own docstring for why) — proven
  through the SAME ``FakeGuiForPanel`` the four tools' own Stop tests
  use, just keyed ``"aicheck"``. ``_run_ai_check_job``'s own new
  ``stop_event`` halting BETWEEN images mirrors ``_run_tool_job``'s
  test exactly, with ``painter.ai.check_one_image`` monkeypatched (no
  network/API quota spent).
"""

from __future__ import annotations

import queue
import threading
from pathlib import Path
from types import SimpleNamespace

import pytest
from PIL import Image

import gui
import painter.postprocess as postprocess_module
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
    SAFETY_MAX_REMOVE_FRAC,
    SAFETY_MAX_REMOVE_FRAC_WHITE,
    UPSCALE_ASPECT_MAX,
    UPSCALE_ASPECT_MIN,
    UPSCALE_MIN_SIDE_DEFAULT,
)
from painter.jobtemp import JobTemp, clear_all


@pytest.fixture(autouse=True)
def _sweep_temp():
    """JobTemp's real backup root lives under the PROJECT's own
    .painter_tmp/ regardless of which folder the live images sit in
    (see jobtemp.py's TEMP_ROOT) — _launch_tool_worker really
    constructs one; sweep it after every test, same as
    test_gui_pipeline.py."""
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
# gui._filter_files — pure-ish, real tiny PNGs on disk
# ---------------------------------------------------------------------


def test_filter_files_keeps_only_matching_images(tmp_path):
    small = tmp_path / "small.png"
    Image.new("RGBA", (50, 50)).save(small)
    wide = tmp_path / "wide.png"
    Image.new("RGBA", (200, 50)).save(wide)

    kept = gui._filter_files(
        [small, wide], [cond(FILTER_KIND_WIDTH, FILTER_POLARITY_IF, 100, 9999)],
        print,
    )
    assert kept == [wide]


def test_filter_files_empty_conditions_is_a_no_op(tmp_path):
    a = tmp_path / "a.png"
    Image.new("RGBA", (50, 50)).save(a)
    assert gui._filter_files([a], [], print) == [a]


def test_filter_files_unreadable_file_is_excluded_loudly(tmp_path):
    bad = tmp_path / "bad.png"
    bad.write_bytes(b"not an image")
    log: list[str] = []
    kept = gui._filter_files(
        [bad], [cond(FILTER_KIND_WIDTH, FILTER_POLARITY_IF, 1, 9999)], log.append,
    )
    assert kept == []
    assert len(log) == 1


# ---------------------------------------------------------------------
# Advanced-override field parsers — pure, Tk-free
# ---------------------------------------------------------------------


def test_parse_fraction_accepts_a_valid_value():
    assert gui._parse_fraction(" 0.5 ", "x") == 0.5


def test_parse_fraction_rejects_non_numeric():
    with pytest.raises(ValueError, match="black bg"):
        gui._parse_fraction("abc", "black bg")


@pytest.mark.parametrize("text", ["0", "-0.1", "1.5", "0.0"])
def test_parse_fraction_rejects_out_of_range(text):
    with pytest.raises(ValueError):
        gui._parse_fraction(text, "x")


def test_parse_nonneg_int_accepts_a_valid_value():
    assert gui._parse_nonneg_int(" 5 ", "x") == 5


def test_parse_nonneg_int_rejects_negative():
    with pytest.raises(ValueError, match="margin px"):
        gui._parse_nonneg_int("-1", "margin px")


def test_parse_int_range_accepts_within_bounds():
    assert gui._parse_int_range("128", "x", 0, 255) == 128


def test_parse_int_range_rejects_outside_bounds():
    with pytest.raises(ValueError, match="ink alpha"):
        gui._parse_int_range("300", "ink alpha", 0, 255)


# ---------------------------------------------------------------------
# ToolSettingsPanel — input picker (resolve_input)
# ---------------------------------------------------------------------


def test_resolve_input_raises_when_nothing_picked_yet(root):
    panel = make_panel(gui.BgSettingsPanel, root)
    with pytest.raises(ValueError):
        panel.resolve_input()


def test_resolve_input_folder_mode_rescans_live(root, tmp_path):
    folder = tmp_path / "imgs"
    folder.mkdir()
    Image.new("RGBA", (10, 10)).save(folder / "a.png")
    panel = make_panel(gui.BgSettingsPanel, root)
    panel._input_mode = "folder"  # mirrors _pick_folder's own assignment
    panel._folder = folder

    base, files = panel.resolve_input()
    assert base == folder
    assert [f.name for f in files] == ["a.png"]

    # a folder edited AFTER the pick is honored (live rescan, matching
    # every existing folder-based tool)
    Image.new("RGBA", (10, 10)).save(folder / "b.png")
    _base2, files2 = panel.resolve_input()
    assert sorted(f.name for f in files2) == ["a.png", "b.png"]


def test_resolve_input_files_mode_bases_on_the_common_ancestor(root, tmp_path):
    sub = tmp_path / "a" / "b"
    sub.mkdir(parents=True)
    f1 = tmp_path / "a" / "one.png"
    f2 = sub / "two.png"
    Image.new("RGBA", (5, 5)).save(f1)
    Image.new("RGBA", (5, 5)).save(f2)

    panel = make_panel(gui.CropSettingsPanel, root)
    panel._input_mode = "files"
    panel._files = [f1, f2]

    base, files = panel.resolve_input()
    assert base == tmp_path / "a"
    assert set(files) == {f1, f2}


def test_get_conditions_proxies_the_embedded_filter_editor(root):
    panel = make_panel(gui.CropSettingsPanel, root)
    panel.filter.set_conditions([cond(FILTER_KIND_WIDTH, FILTER_POLARITY_IF, 1.0, 2.0)])
    assert panel.get_conditions() == [cond(FILTER_KIND_WIDTH, FILTER_POLARITY_IF, 1.0, 2.0)]


# ---------------------------------------------------------------------
# Advanced overrides reaching the engine function (build_func)
# ---------------------------------------------------------------------


def test_bg_panel_advanced_defaults_match_config(root):
    panel = make_panel(gui.BgSettingsPanel, root)
    assert panel.safety_black_var.get() == f"{SAFETY_MAX_REMOVE_FRAC:.2f}"
    assert panel.safety_white_var.get() == f"{SAFETY_MAX_REMOVE_FRAC_WHITE:.2f}"


def test_crop_panel_advanced_defaults_match_config(root):
    panel = make_panel(gui.CropSettingsPanel, root)
    assert panel.clean_edge_var.get() == CLEAN_EDGE_ENABLE
    assert panel.margin_var.get() == str(CROP_MARGIN_PX)
    assert panel.ink_alpha_var.get() == str(CROP_INK_ALPHA)
    assert panel.min_ink_var.get() == str(CROP_MIN_INK_PX)


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
    panel.safety_black_var.set("0.10")
    panel.safety_white_var.set("0.20")
    func = panel.build_func()
    func(tmp_path / "x.png", print)

    assert calls == [
        {"safety_max_remove_frac": 0.10, "safety_max_remove_frac_white": 0.20}
    ]


def test_bg_build_func_raises_on_a_non_numeric_safety_field(root):
    panel = make_panel(gui.BgSettingsPanel, root)
    panel.safety_black_var.set("not-a-number")
    with pytest.raises(ValueError, match="black bg safety"):
        panel.build_func()


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


# ---------------------------------------------------------------------
# Run state / pause reflection
# ---------------------------------------------------------------------


def test_set_run_state_disables_start_while_running(root):
    panel = make_panel(gui.BgSettingsPanel, root)
    assert panel.btn_start.cget("state") == "normal"
    panel.set_run_state(running=True)
    assert panel.btn_start.cget("state") == "disabled"
    panel.set_run_state(running=False)
    assert panel.btn_start.cget("state") == "normal"


def test_set_run_state_enables_stop_only_while_running(root):
    """GUI rework Phase 14 — Stop is the MIRROR of Start: disabled
    (outline) while idle, available (filled) exactly while running."""
    panel = make_panel(gui.CropSettingsPanel, root)
    assert panel.btn_stop.cget("state") == "disabled"
    panel.set_run_state(running=True)
    assert panel.btn_stop.cget("state") == "normal"
    panel.set_run_state(running=False)
    assert panel.btn_stop.cget("state") == "disabled"


def test_set_paused_flips_the_button_label(root):
    panel = make_panel(gui.CropSettingsPanel, root)
    assert panel.btn_pause.cget("text") == "Pause"
    panel.set_paused(True)
    assert panel.btn_pause.cget("text") == "Resume"
    panel.set_paused(False)
    assert panel.btn_pause.cget("text") == "Pause"


def test_advanced_collapsible_starts_hidden_and_toggles(root):
    panel = make_panel(gui.CropSettingsPanel, root)
    assert panel._advanced_box.winfo_manager() == ""
    panel._advanced_collapsed_var.set(False)
    panel._apply_advanced_visibility()
    assert panel._advanced_box.winfo_manager() == "pack"


# ---------------------------------------------------------------------
# Settings round-trip
# ---------------------------------------------------------------------


def test_bg_panel_settings_round_trip(root):
    panel = make_panel(gui.BgSettingsPanel, root)
    panel.filter.set_conditions(
        [cond(FILTER_KIND_WIDTH, FILTER_POLARITY_IF, 10.0, 20.0)]
    )
    panel.safety_black_var.set("0.55")
    panel.safety_white_var.set("0.90")
    panel._advanced_collapsed_var.set(False)
    panel._apply_advanced_visibility()

    stored = panel.get_settings()
    assert stored["safety_black"] == "0.55"
    assert stored["safety_white"] == "0.90"
    assert stored["advanced_collapsed"] is False
    assert stored["conditions"] == [
        filters.condition_to_dict(cond(FILTER_KIND_WIDTH, FILTER_POLARITY_IF, 10.0, 20.0))
    ]

    fresh = make_panel(gui.BgSettingsPanel, root)
    conditions = gui._parse_condition_dicts(stored["conditions"], lambda _m: None)
    fresh.apply_settings(stored, conditions=conditions)
    assert fresh.safety_black_var.get() == "0.55"
    assert fresh.safety_white_var.get() == "0.90"
    assert fresh._advanced_collapsed_var.get() is False
    assert fresh._advanced_box.winfo_manager() == "pack"
    assert fresh.filter.get_conditions() == conditions


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


def test_apply_settings_missing_keys_keep_the_current_defaults(root):
    """The universal contract every panel/dialog in this file already
    follows — a fresh settings.json (or a genuinely missing key)
    leaves the widget's own construction-time default untouched."""
    panel = make_panel(gui.CropSettingsPanel, root)
    panel.apply_settings({}, conditions=None)
    assert panel.margin_var.get() == str(CROP_MARGIN_PX)
    assert panel.filter.get_conditions() == []


# ---------------------------------------------------------------------
# PainterGui._start_tool_from_panel — the pre-filter path, end to end
# ---------------------------------------------------------------------


class _FakeDashSlot:
    """Stands in for PainterGui.panels[slot] (a real ToolPanel) —
    _launch_tool_worker only ever sets .folder/.jobtemp and calls
    .reset(active=, total=)."""

    def __init__(self):
        self.folder = None
        self.jobtemp = None
        self.reset_calls: list[tuple] = []

    def reset(self, active, total):
        self.reset_calls.append((active, total))


class FakeGuiForPanel:
    """Duck-typed ``PainterGui`` stand-in for
    ``_start_tool_from_panel``/``_launch_tool_worker`` — the SAME
    convention test_gui_pipeline.py's/test_gui_running_view.py's own
    FakeGui use (never a full ``PainterGui``). ``_run_tool_job`` is a
    RECORDING stand-in: the real background-worker loop is explicitly
    UNCHANGED this phase (event contract preserved) and already has
    its own coverage; this class only proves what gets handed to it."""

    _start_tool_from_panel = gui.PainterGui._start_tool_from_panel
    _launch_tool_worker = gui.PainterGui._launch_tool_worker

    def __init__(self, tool_panels: dict):
        self._tool_panels = tool_panels
        self._tool_workers: dict[str, threading.Thread] = {}
        self._job_temps: dict = {}
        self._paused: set[str] = set()
        self._pause_events = {
            slot: threading.Event() for slot in tool_panels
        }
        # GUI rework Phase 14: _launch_tool_worker also clears+reads a
        # per-slot Stop event (mirrors _pause_events above)
        self._stop_events = {
            slot: threading.Event() for slot in tool_panels
        }
        self.panels = {slot: _FakeDashSlot() for slot in tool_panels}
        self._dashgrid = SimpleNamespace(add=lambda _slot: None)
        self.notebook = SimpleNamespace(select=lambda _i: None)
        self.status_var = SimpleNamespace(set=lambda _s: None)
        self._inline_kind: str | None = next(iter(tool_panels), None)
        self.apply_running_layout_calls = 0
        self.sync_running_state_calls = 0
        self.run_tool_job_calls: list[dict] = []

    def _log(self, _msg: str) -> None:
        pass

    def _apply_running_layout(self) -> None:
        self.apply_running_layout_calls += 1

    def _sync_running_state(self) -> None:
        self.sync_running_state_calls += 1

    def _run_tool_job(
        self, slot, label, func, folder, files, temp, pause_event,
        stop_event,
    ):
        self.run_tool_job_calls.append({
            "slot": slot, "label": label, "func": func,
            "folder": folder, "files": list(files),
        })


def test_start_tool_from_panel_prefilters_by_the_panels_conditions(
    root, tmp_path,
):
    """The core Phase-13 promise: given a folder + stacked filter
    conditions set on the panel, Start queues ONLY the matching
    subset."""
    folder = tmp_path / "images"
    folder.mkdir()
    Image.new("RGBA", (40, 40)).save(folder / "small_square.png")
    Image.new("RGBA", (120, 100)).save(folder / "wide.png")
    Image.new("RGBA", (100, 40)).save(folder / "short_wide.png")

    panel = make_panel(gui.BgSettingsPanel, root)
    panel._input_mode = "folder"
    panel._folder = folder
    panel.filter.set_conditions(
        [cond(FILTER_KIND_WIDTH, FILTER_POLARITY_IF, 80, 99999)]
    )

    fake = FakeGuiForPanel({"bg": panel})
    gui.PainterGui._start_tool_from_panel(fake, "bg")

    worker = fake._tool_workers["bg"]
    worker.join(timeout=5)
    assert not worker.is_alive()

    assert len(fake.run_tool_job_calls) == 1
    call = fake.run_tool_job_calls[0]
    assert call["slot"] == "bg"
    assert call["folder"] == folder
    assert sorted(p.name for p in call["files"]) == ["short_wide.png", "wide.png"]

    # Start hides the panel + re-enables it for a future run
    assert panel.btn_start.cget("state") == "disabled"
    assert fake._inline_kind is None
    assert fake.apply_running_layout_calls == 1
    assert fake.sync_running_state_calls == 1
    assert fake.panels["bg"].reset_calls == [(True, 2)]


def test_start_tool_from_panel_empty_conditions_queues_everything(root, tmp_path):
    folder = tmp_path / "images"
    folder.mkdir()
    Image.new("RGBA", (10, 10)).save(folder / "a.png")
    Image.new("RGBA", (20, 20)).save(folder / "b.png")

    panel = make_panel(gui.CropSettingsPanel, root)
    panel._input_mode = "folder"
    panel._folder = folder

    fake = FakeGuiForPanel({"crop": panel})
    gui.PainterGui._start_tool_from_panel(fake, "crop")

    fake._tool_workers["crop"].join(timeout=5)
    call = fake.run_tool_job_calls[0]
    assert sorted(p.name for p in call["files"]) == ["a.png", "b.png"]


def test_start_tool_from_panel_shows_a_message_when_nothing_picked(
    root, monkeypatch,
):
    errors: list = []
    monkeypatch.setattr(
        gui.messagebox, "showerror", lambda *a, **k: errors.append(a)
    )
    panel = make_panel(gui.CropSettingsPanel, root)
    fake = FakeGuiForPanel({"crop": panel})

    gui.PainterGui._start_tool_from_panel(fake, "crop")

    assert errors
    assert fake.run_tool_job_calls == []
    assert "crop" not in fake._tool_workers


def test_start_tool_from_panel_refuses_a_second_job_of_the_same_kind(
    root, monkeypatch,
):
    errors: list = []
    monkeypatch.setattr(
        gui.messagebox, "showerror", lambda *a, **k: errors.append(a)
    )
    panel = make_panel(gui.BgSettingsPanel, root)
    fake = FakeGuiForPanel({"bg": panel})
    fake._tool_workers["bg"] = object()  # already running

    gui.PainterGui._start_tool_from_panel(fake, "bg")

    assert errors
    assert fake.run_tool_job_calls == []


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


# ---------------------------------------------------------------------
# Stop (GUI rework Phase 14) — PainterGui._stop_tool, the request half
# ---------------------------------------------------------------------


def test_stop_tool_sets_the_stop_event_for_a_running_job(root):
    panel = make_panel(gui.BgSettingsPanel, root)
    fake = FakeGuiForPanel({"bg": panel})
    fake._tool_workers["bg"] = object()  # pretend a worker is running
    gui.PainterGui._stop_tool(fake, "bg")
    assert fake._stop_events["bg"].is_set()


def test_stop_tool_is_a_no_op_when_nothing_is_running(root):
    panel = make_panel(gui.CropSettingsPanel, root)
    fake = FakeGuiForPanel({"crop": panel})
    gui.PainterGui._stop_tool(fake, "crop")
    assert not fake._stop_events["crop"].is_set()


def test_stop_tool_also_clears_a_pending_pause(root):
    """MUST NOT REGRESS (mirrors _stop_site's own contract): Stop wins
    over a pending Pause instead of leaving a stale pre-paused toggle
    for the next Start."""
    panel = make_panel(gui.CropSettingsPanel, root)
    fake = FakeGuiForPanel({"crop": panel})
    fake._tool_workers["crop"] = object()
    fake._paused.add("crop")
    toggled: list[str] = []
    fake._toggle_pause_job = toggled.append
    gui.PainterGui._stop_tool(fake, "crop")
    assert fake._stop_events["crop"].is_set()
    assert toggled == ["crop"]


# ---------------------------------------------------------------------
# Stop (GUI rework Phase 14) — _run_tool_job's should_stop, the worker
# half. Mirrors test_runner.py's own test_stop_flag_stops_between_items:
# should_stop is checked BETWEEN images only, never mid-image, so the
# in-flight item always finishes.
# ---------------------------------------------------------------------


class _FakeGuiForJob:
    """Just enough surface for the UNBOUND ``_run_tool_job`` to run for
    real: a genuine ``queue.Queue`` so its ``log``/``emit`` closures
    (both ``self._q.put``) have somewhere to land — the SAME minimal-
    surface convention ``FakeGuiForPanel``/test_gui_pipeline.py's own
    ``FakeGui`` already use."""

    def __init__(self):
        self._q: "queue.Queue" = queue.Queue()


def _drain(q: "queue.Queue") -> list:
    items = []
    while True:
        try:
            items.append(q.get_nowait())
        except queue.Empty:
            break
    return items


def test_run_tool_job_stop_flag_halts_between_images(tmp_path):
    folder = tmp_path / "images"
    folder.mkdir()
    files = []
    for i in range(3):
        p = folder / f"img_{i}.png"
        Image.new("RGBA", (10, 10)).save(p)
        files.append(p)

    calls = {"n": 0}

    def stop_after_first():
        calls["n"] += 1
        return calls["n"] > 1  # first between-item check passes, second stops

    fake = _FakeGuiForJob()
    temp = JobTemp("upscale", folder)
    try:
        gui.PainterGui._run_tool_job(
            fake, "upscale", "Upscale", lambda path, log: "nothing",
            folder, files, temp,
            pause_event=threading.Event(),
            stop_event=SimpleNamespace(is_set=stop_after_first),
        )
    finally:
        temp.clear()

    msgs = _drain(fake._q)
    text_lines = [m for m in msgs if isinstance(m, str)]
    events = [m for m in msgs if isinstance(m, tuple) and m[0] == "__event__"]
    item_events = [e[2]["type"] for e in events]

    # exactly ONE image reached the engine (item_start once, no second)
    assert item_events.count("item_start") == 1
    assert any("STOPPED on request" in line for line in text_lines)
    assert any("1/3" in line for line in text_lines if "STOPPED" in line)
    # the worker still reports done, even on a Stop (finally: always posted)
    assert msgs[-1] == ("__tool_done__", "upscale")


def test_run_tool_job_without_a_stop_processes_every_image(tmp_path):
    """Regression guard: a should_stop that never fires behaves exactly
    like before this phase — every image runs, same as the previous
    (Stop-less) contract."""
    folder = tmp_path / "images"
    folder.mkdir()
    files = []
    for i in range(2):
        p = folder / f"img_{i}.png"
        Image.new("RGBA", (10, 10)).save(p)
        files.append(p)

    fake = _FakeGuiForJob()
    temp = JobTemp("upscale", folder)
    try:
        gui.PainterGui._run_tool_job(
            fake, "upscale", "Upscale", lambda path, log: "nothing",
            folder, files, temp,
            pause_event=threading.Event(),
            stop_event=threading.Event(),  # never set
        )
    finally:
        temp.clear()

    events = [
        m for m in _drain(fake._q)
        if isinstance(m, tuple) and m[0] == "__event__"
    ]
    assert [e[2]["type"] for e in events].count("item_start") == 2


# ---------------------------------------------------------------------
# ImageCheckerSettingsPanel (GUI rework Phase 15)
# ---------------------------------------------------------------------


def test_ai_check_panel_has_no_advanced_section(root):
    panel = make_panel(gui.ImageCheckerSettingsPanel, root)
    assert not hasattr(panel, "_advanced_box")
    assert not hasattr(panel, "_advanced_btn")


def test_ai_check_panel_picker_titles_read_only_never_claim_in_place(root):
    """Root Rule #1 — a read-only vision pass must never claim to
    write anything, unlike the four tools' shared 'runs IN PLACE'
    wording (ToolSettingsPanel's own default, unchanged for BG)."""
    checker = make_panel(gui.ImageCheckerSettingsPanel, root)
    bg = make_panel(gui.BgSettingsPanel, root)
    assert checker._picker_title_suffix() == "(read-only)"
    assert bg._picker_title_suffix() == "runs IN PLACE"


def test_ai_check_panel_default_conditions_is_empty_check_everything(root):
    panel = make_panel(gui.ImageCheckerSettingsPanel, root)
    assert panel.filter.get_conditions() == []


def test_ai_check_panel_input_and_settings_round_trip(root, tmp_path):
    """The input picker (inherited, unmodified) + the settings round-
    trip (only ``conditions`` — the panel has no extra fields of its
    own, unlike BG/Crop/Upscale/Aspect)."""
    folder = tmp_path / "imgs"
    folder.mkdir()
    Image.new("RGBA", (10, 10)).save(folder / "a.png")

    panel = make_panel(gui.ImageCheckerSettingsPanel, root)
    panel._input_mode = "folder"
    panel._folder = folder
    base, files = panel.resolve_input()
    assert base == folder
    assert [f.name for f in files] == ["a.png"]

    panel.filter.set_conditions(
        [cond(FILTER_KIND_WIDTH, FILTER_POLARITY_IF, 5.0, 50.0)]
    )
    stored = panel.get_settings()
    assert "advanced_collapsed" not in stored  # HAS_ADVANCED = False
    assert stored["conditions"] == [
        filters.condition_to_dict(
            cond(FILTER_KIND_WIDTH, FILTER_POLARITY_IF, 5.0, 50.0)
        )
    ]

    fresh = make_panel(gui.ImageCheckerSettingsPanel, root)
    conditions = gui._parse_condition_dicts(stored["conditions"], lambda _m: None)
    fresh.apply_settings(stored, conditions=conditions)
    assert fresh.filter.get_conditions() == conditions


# ---------------------------------------------------------------------
# PainterGui._start_ai_check — the pre-filter path, end to end (GUI
# rework Phase 15). NOT _start_tool_from_panel (a different worker
# shape — see ImageCheckerSettingsPanel's own docstring), so it gets
# its OWN small duck-typed fake, the same FakeGuiForPanel/FakeGui
# convention every other GUI-phase test file uses.
# ---------------------------------------------------------------------


class _FakeAiCheckDashSlot:
    """Stands in for PainterGui.panels["aicheck"] (a real
    AiCheckPanel) — _start_ai_check only ever sets .folder/.out_base
    and calls .reset(active=, total=)."""

    def __init__(self):
        self.folder = None
        self.out_base = None
        self.reset_calls: list[tuple] = []

    def reset(self, active, total):
        self.reset_calls.append((active, total))


class FakeGuiForAiCheck:
    """Duck-typed ``PainterGui`` stand-in for ``_start_ai_check`` —
    mirrors ``FakeGuiForPanel`` above (never a full ``PainterGui``).
    ``_run_ai_check_job`` is a RECORDING stand-in: the real
    background-worker loop (its OWN should_stop halting BETWEEN
    images) has its own dedicated coverage further below, over the
    UNBOUND real method with a monkeypatched ``ai.check_one_image`` —
    this class only proves what ``_start_ai_check`` hands off to it."""

    def __init__(self, panel, ensure_key: bool = True):
        self._tool_panels = {"image_checker": panel}
        self._tool_workers: dict[str, threading.Thread] = {}
        self._paused: set[str] = set()
        self._pause_events = {"aicheck": threading.Event()}
        self._stop_events = {"aicheck": threading.Event()}
        self.panels = {"aicheck": _FakeAiCheckDashSlot()}
        self._dashgrid = SimpleNamespace(add=lambda _slot: None)
        self.notebook = SimpleNamespace(select=lambda _i: None)
        self.status_var = SimpleNamespace(set=lambda _s: None)
        self._inline_kind: str | None = "image_checker"
        self._ensure_key = ensure_key
        self.apply_running_layout_calls = 0
        self.sync_running_state_calls = 0
        self.run_ai_check_job_calls: list[dict] = []

    def _log(self, _msg: str) -> None:
        pass

    def _ensure_ai_key(self) -> bool:
        return self._ensure_key

    def _out_base(self) -> Path:
        return Path("fake-out-base")

    def _apply_running_layout(self) -> None:
        self.apply_running_layout_calls += 1

    def _sync_running_state(self) -> None:
        self.sync_running_state_calls += 1

    def _toggle_pause_job(self, kind: str) -> None:
        self._paused.discard(kind)

    def _run_ai_check_job(
        self, folder, files, out_base, pause_event, stop_event,
    ):
        self.run_ai_check_job_calls.append({
            "folder": folder, "files": list(files), "out_base": out_base,
        })


def test_start_ai_check_prefilters_by_the_panels_conditions(root, tmp_path):
    """The core Phase-15 promise, mirroring Phase 13's own for the
    tools: given a folder + stacked filter conditions set on the
    panel, Start queues ONLY the matching subset."""
    folder = tmp_path / "images"
    folder.mkdir()
    Image.new("RGBA", (40, 40)).save(folder / "small_square.png")
    Image.new("RGBA", (120, 100)).save(folder / "wide.png")
    Image.new("RGBA", (100, 40)).save(folder / "short_wide.png")

    panel = make_panel(gui.ImageCheckerSettingsPanel, root)
    panel._input_mode = "folder"
    panel._folder = folder
    panel.filter.set_conditions(
        [cond(FILTER_KIND_WIDTH, FILTER_POLARITY_IF, 80, 99999)]
    )

    fake = FakeGuiForAiCheck(panel)
    gui.PainterGui._start_ai_check(fake, "aicheck")

    worker = fake._tool_workers["aicheck"]
    worker.join(timeout=5)
    assert not worker.is_alive()

    assert len(fake.run_ai_check_job_calls) == 1
    call = fake.run_ai_check_job_calls[0]
    assert call["folder"] == folder
    assert sorted(p.name for p in call["files"]) == [
        "short_wide.png", "wide.png",
    ]

    # Start hides the launching panel + re-enables it for a future run
    assert panel.btn_start.cget("state") == "disabled"
    assert fake._inline_kind is None
    assert fake.apply_running_layout_calls == 1
    assert fake.sync_running_state_calls == 1
    assert fake.panels["aicheck"].reset_calls == [(True, 2)]


def test_start_ai_check_empty_conditions_queues_everything(root, tmp_path):
    folder = tmp_path / "images"
    folder.mkdir()
    Image.new("RGBA", (10, 10)).save(folder / "a.png")
    Image.new("RGBA", (20, 20)).save(folder / "b.png")

    panel = make_panel(gui.ImageCheckerSettingsPanel, root)
    panel._input_mode = "folder"
    panel._folder = folder

    fake = FakeGuiForAiCheck(panel)
    gui.PainterGui._start_ai_check(fake, "aicheck")

    fake._tool_workers["aicheck"].join(timeout=5)
    call = fake.run_ai_check_job_calls[0]
    assert sorted(p.name for p in call["files"]) == ["a.png", "b.png"]


def test_start_ai_check_shows_a_message_when_nothing_picked(root, monkeypatch):
    errors: list = []
    monkeypatch.setattr(
        gui.messagebox, "showerror", lambda *a, **k: errors.append(a)
    )
    panel = make_panel(gui.ImageCheckerSettingsPanel, root)
    fake = FakeGuiForAiCheck(panel)

    gui.PainterGui._start_ai_check(fake, "aicheck")

    assert errors
    assert fake.run_ai_check_job_calls == []
    assert "aicheck" not in fake._tool_workers


def test_start_ai_check_refuses_a_second_job(root, monkeypatch):
    errors: list = []
    monkeypatch.setattr(
        gui.messagebox, "showerror", lambda *a, **k: errors.append(a)
    )
    panel = make_panel(gui.ImageCheckerSettingsPanel, root)
    fake = FakeGuiForAiCheck(panel)
    fake._tool_workers["aicheck"] = object()  # already running

    gui.PainterGui._start_ai_check(fake, "aicheck")

    assert errors
    assert fake.run_ai_check_job_calls == []


def test_start_ai_check_gated_on_the_key(root, tmp_path):
    folder = tmp_path / "images"
    folder.mkdir()
    Image.new("RGBA", (10, 10)).save(folder / "a.png")
    panel = make_panel(gui.ImageCheckerSettingsPanel, root)
    panel._input_mode = "folder"
    panel._folder = folder
    fake = FakeGuiForAiCheck(panel, ensure_key=False)

    gui.PainterGui._start_ai_check(fake, "aicheck")

    assert fake.run_ai_check_job_calls == []
    assert "aicheck" not in fake._tool_workers


# ---------------------------------------------------------------------
# Stop (GUI rework Phase 15) — the AI checker reuses PainterGui.
# _stop_tool VERBATIM (Rule #5: already fully generic over any slot
# with a _tool_workers/_stop_events entry — see
# ImageCheckerSettingsPanel's own docstring for why a separate
# _stop_ai_check would only duplicate it byte-for-byte). Proven the
# SAME way the four tools' own Stop request-half is above, just keyed
# "aicheck".
# ---------------------------------------------------------------------


def test_stop_tool_also_works_for_the_ai_checker_slot(root):
    panel = make_panel(gui.ImageCheckerSettingsPanel, root)
    fake = FakeGuiForPanel({"aicheck": panel})
    fake._tool_workers["aicheck"] = object()  # pretend a worker is running
    gui.PainterGui._stop_tool(fake, "aicheck")
    assert fake._stop_events["aicheck"].is_set()


def test_stop_tool_for_the_ai_checker_also_clears_a_pending_pause(root):
    panel = make_panel(gui.ImageCheckerSettingsPanel, root)
    fake = FakeGuiForPanel({"aicheck": panel})
    fake._tool_workers["aicheck"] = object()
    fake._paused.add("aicheck")
    toggled: list[str] = []
    fake._toggle_pause_job = toggled.append
    gui.PainterGui._stop_tool(fake, "aicheck")
    assert fake._stop_events["aicheck"].is_set()
    assert toggled == ["aicheck"]


# ---------------------------------------------------------------------
# Stop (GUI rework Phase 15) — _run_ai_check_job's should_stop, the
# worker half. Mirrors test_run_tool_job_stop_flag_halts_between_images
# above exactly: should_stop is checked BETWEEN images only, never
# mid-call, so the in-flight vision call always finishes.
# painter.ai.check_one_image is MONKEYPATCHED — no network, no API
# quota spent.
# ---------------------------------------------------------------------


def _fake_check_one_image(src, out_base, instructions, *, log=print, **_kw):
    return {
        "rel": src.name, "kind": "ok", "defects": [], "raw": "OK",
        "time": 0.01,
    }


def test_run_ai_check_job_stop_flag_halts_between_images(tmp_path, monkeypatch):
    import painter.ai as ai_module

    folder = tmp_path / "images"
    folder.mkdir()
    files = []
    for i in range(3):
        p = folder / f"img_{i}.png"
        Image.new("RGBA", (10, 10)).save(p)
        files.append(p)

    calls = {"n": 0}

    def counting_check(src, out_base, instructions, *, log=print, **_kw):
        calls["n"] += 1
        return _fake_check_one_image(src, out_base, instructions, log=log)

    monkeypatch.setattr(ai_module, "check_one_image", counting_check)

    stop_state = {"n": 0}

    def stop_after_first():
        stop_state["n"] += 1
        return stop_state["n"] > 1  # first between-item check passes, second stops

    fake = _FakeGuiForJob()
    gui.PainterGui._run_ai_check_job(
        fake, folder, files, tmp_path,
        pause_event=threading.Event(),
        stop_event=SimpleNamespace(is_set=stop_after_first),
    )

    msgs = _drain(fake._q)
    text_lines = [m for m in msgs if isinstance(m, str)]
    events = [m for m in msgs if isinstance(m, tuple) and m[0] == "__event__"]
    item_events = [e[2]["type"] for e in events]

    # exactly ONE image reached the (mocked) AI call
    assert calls["n"] == 1
    assert item_events.count("item_start") == 1
    assert any("STOPPED on request" in line for line in text_lines)
    assert any("1/3" in line for line in text_lines if "STOPPED" in line)
    # the worker still reports done, even on a Stop (finally: always posted)
    assert msgs[-1] == ("__tool_done__", "aicheck")


def test_run_ai_check_job_without_a_stop_processes_every_image(
    tmp_path, monkeypatch,
):
    """Regression guard: a should_stop that never fires behaves exactly
    like before this phase — every image runs, same as the previous
    (Stop-less) contract."""
    import painter.ai as ai_module

    monkeypatch.setattr(ai_module, "check_one_image", _fake_check_one_image)

    folder = tmp_path / "images"
    folder.mkdir()
    files = []
    for i in range(2):
        p = folder / f"img_{i}.png"
        Image.new("RGBA", (10, 10)).save(p)
        files.append(p)

    fake = _FakeGuiForJob()
    gui.PainterGui._run_ai_check_job(
        fake, folder, files, tmp_path,
        pause_event=threading.Event(),
        stop_event=threading.Event(),  # never set
    )

    events = [
        m for m in _drain(fake._q)
        if isinstance(m, tuple) and m[0] == "__event__"
    ]
    assert [e[2]["type"] for e in events].count("item_start") == 2
