"""BG removal / Crop persistent settings panels (GUI rework Phase 13).

Four halves, matching gui.py's own "pure helpers get pytest, real
Tk/UI wiring gets a screenshot" split (___tests.md):

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
  run-state/pause button reflection, and the settings round-trip.
* ``PainterGui._start_tool_from_panel`` — the core Phase-13 promise
  ("given a folder + conditions, the right file subset is queued") —
  exercised through a small duck-typed ``FakeGuiForPanel`` (the SAME
  convention test_gui_pipeline.py's/test_gui_running_view.py's own
  FakeGui use: never a full ``PainterGui``). Its ``_run_tool_job`` is
  a RECORDING stand-in, never the real background worker — the worker
  loop itself is explicitly UNCHANGED this phase (see
  ``_launch_tool_worker``'s own docstring) and already has its own
  coverage; this file only proves WHAT gets hidden off to it.
"""

from __future__ import annotations

import threading
from pathlib import Path
from types import SimpleNamespace

import pytest
from PIL import Image

import gui
import painter.postprocess as postprocess_module
from painter import filters
from painter.config import (
    CLEAN_EDGE_ENABLE,
    CROP_INK_ALPHA,
    CROP_MARGIN_PX,
    CROP_MIN_INK_PX,
    FILTER_KIND_WIDTH,
    FILTER_POLARITY_IF,
    SAFETY_MAX_REMOVE_FRAC,
    SAFETY_MAX_REMOVE_FRAC_WHITE,
)
from painter.jobtemp import clear_all


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
    return cls(root, on_start=lambda *_a: None, on_pause=lambda *_a: None)


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

    def _run_tool_job(self, slot, label, func, folder, files, temp, pause_event):
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
