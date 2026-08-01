"""``ToolSettingsPanel`` base contract + the generic tool-job wiring —
NOT any one panel's own engine behavior (see test_tool_panels_bg.py /
test_tool_panels_geometry.py / test_tool_panels_image_checker.py for
those).

Split from the former ``test_gui_tool_panels.py`` god-file (root Rule
#20, second round — the source split into ``gui/tool_panels/`` package
2026-07-30, this test module follows it 1:1: everything
``gui/tool_panels/base.py`` defines, plus the cross-panel wiring in
``gui/app_tools.py`` (``_start_tool_from_panel``, ``_stop_tool``,
``_run_tool_job``) that every concrete panel shares.

Covers:
* ``gui._filter_files`` — the pre-filter every tool shares, real tiny
  PNGs on disk, no Tk at all.
* ``gui._parse_fraction``/``_parse_nonneg_int``/``_parse_int_range`` —
  the Advanced-override field parsers, pure and Tk-free.
* ``ToolSettingsPanel``'s own contract (input picker, run-state/pause
  reflection, advanced collapsible, settings-round-trip fallback) —
  exercised through concrete subclasses (``BgSettingsPanel``/
  ``CropSettingsPanel``) purely as INSTANTIATION VEHICLES, since the
  base class itself is never constructed directly; the assertions are
  about the base behavior, not those panels' own fields.
* ``PainterGui._start_tool_from_panel``/``_stop_tool``/``_run_tool_job``
  — the generic tool-job lifecycle, over a duck-typed ``FakeGuiForPanel``
  (never a full ``PainterGui``), the same convention test_gui_pipeline.py
  and test_gui_running_view.py use.
"""

from __future__ import annotations

import queue
import threading
from pathlib import Path
from types import SimpleNamespace

import pytest
from PIL import Image

import gui
from painter import filters
from painter.config import CROP_MARGIN_PX, FILTER_KIND_WIDTH, FILTER_POLARITY_IF
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


def test_toggle_advanced_calls_on_layout_change_after_the_reveal(root):
    """The real click path (_toggle_advanced, not the bare
    _apply_advanced_visibility above): the outer ScrollFrame's refresh
    hook (owner 2026-07-21 perf fix, replacing the old perpetual
    self-heal poll) must fire exactly once per toggle, AFTER the box is
    actually packed/forgotten — on a withdrawn root smooth_transition's
    own mapped/viewable guard fails, so mutate runs instantly and
    synchronously, making the ordering directly observable here."""
    calls: list[str] = []
    panel = gui.CropSettingsPanel(
        root, on_start=lambda *_a: None, on_pause=lambda *_a: None,
        on_stop=lambda *_a: None, on_layout_change=lambda: calls.append(
            panel_box_state()
        ),
    )

    def panel_box_state() -> str:
        return panel._advanced_box.winfo_manager()

    panel._toggle_advanced()  # collapsed -> expanded
    assert panel._advanced_box.winfo_manager() == "pack"
    assert calls == ["pack"]

    panel._toggle_advanced()  # expanded -> collapsed
    assert panel._advanced_box.winfo_manager() == ""
    assert calls == ["pack", ""]


def test_on_layout_change_defaults_to_a_harmless_noop(root):
    """Every OTHER make_panel() in this suite passes no on_layout_change
    at all — must not raise."""
    panel = make_panel(gui.CropSettingsPanel, root)
    panel._toggle_advanced()  # must not raise
    assert panel._advanced_box.winfo_manager() == "pack"


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
