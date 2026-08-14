"""``ImageCheckerSettingsPanel`` — the AI image-checker standalone panel
(GUI rework Phase 15), plus its Start/Stop worker wiring in
``gui/app_tools.py`` (``_start_ai_check``/``_run_ai_check_job``).

Split from the former ``test_gui_tool_panels.py`` god-file (root Rule
#20, second round — the source split into ``gui/tool_panels/`` package
2026-07-30, this test module follows it 1:1: everything
``gui/tool_panels/image_checker.py`` defines).

``PainterGui._start_ai_check`` is NOT ``_start_tool_from_panel`` (a
different worker shape — see ``ImageCheckerSettingsPanel``'s own
docstring), so it gets its OWN small duck-typed fake
(``FakeGuiForAiCheck``), the same convention every other GUI-phase test
file uses. **Stop** reuses ``PainterGui._stop_tool`` VERBATIM (Rule #5:
already fully generic over any slot with a ``_tool_workers``/
``_stop_events`` entry) — proven here with a minimal local
``FakeGuiForPanel``, keyed ``"aicheck"``.
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
from painter.config import FILTER_KIND_WIDTH, FILTER_POLARITY_IF
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


class _FakeDashSlot:
    """Stands in for PainterGui.panels[slot] (a real ToolPanel) — see
    test_tool_panels_base.py's own copy for the full rationale; needed
    here too because ``test_stop_tool_also_works_for_the_ai_checker_slot``
    below exercises the GENERIC ``_stop_tool`` (not the AI-check-only
    ``FakeGuiForAiCheck``)."""

    def __init__(self):
        self.folder = None
        self.jobtemp = None
        self.reset_calls: list[tuple] = []

    def reset(self, active, total):
        self.reset_calls.append((active, total))


class FakeGuiForPanel:
    """Minimal duck-typed ``PainterGui`` stand-in for the GENERIC
    ``_stop_tool`` — see test_tool_panels_base.py's own copy for the
    full rationale. ``status_var`` is required because ``_stop_tool``
    posts a "stopping after the current item" status message."""

    def __init__(self, tool_panels: dict):
        self._tool_panels = tool_panels
        self._tool_workers: dict[str, threading.Thread] = {}
        self._paused: set[str] = set()
        self._pause_events = {slot: threading.Event() for slot in tool_panels}
        self._stop_events = {slot: threading.Event() for slot in tool_panels}
        self.panels = {slot: _FakeDashSlot() for slot in tool_panels}
        self.status_var = SimpleNamespace(set=lambda _s: None)


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
# ImageCheckerSettingsPanel.sheets_path() (F6, REWORK.md, owner E2) —
# the OPTIONAL second input, mirroring the primary picker's own
# "set the private field directly, never invoke a real dialog" test
# convention (folder/files above).
# ---------------------------------------------------------------------


def test_ai_check_panel_sheets_path_defaults_none(root):
    panel = make_panel(gui.ImageCheckerSettingsPanel, root)
    assert panel.sheets_path() is None


def test_ai_check_panel_pick_sheets_file_sets_the_path(root, tmp_path, monkeypatch):
    sheet = tmp_path / "theme.md"
    sheet.write_text("# Theme\n", encoding="utf-8")
    monkeypatch.setattr(gui.filedialog, "askopenfilename", lambda **_k: str(sheet))

    panel = make_panel(gui.ImageCheckerSettingsPanel, root)
    panel._pick_sheets_file()
    assert panel.sheets_path() == sheet
    assert "theme.md" in panel._sheets_var.get()


def test_ai_check_panel_pick_sheets_folder_sets_the_path(root, tmp_path, monkeypatch):
    folder = tmp_path / "sheets"
    folder.mkdir()
    monkeypatch.setattr(gui.filedialog, "askdirectory", lambda **_k: str(folder))

    panel = make_panel(gui.ImageCheckerSettingsPanel, root)
    panel._pick_sheets_folder()
    assert panel.sheets_path() == folder


def test_ai_check_panel_pick_sheets_cancelled_leaves_it_none(root, monkeypatch):
    """An empty string (Cancel) from either dialog must not clobber a
    previous pick with an empty path — mirrors the base picker's own
    ``if not folder/picks: return`` guard."""
    monkeypatch.setattr(gui.filedialog, "askopenfilename", lambda **_k: "")
    monkeypatch.setattr(gui.filedialog, "askdirectory", lambda **_k: "")

    panel = make_panel(gui.ImageCheckerSettingsPanel, root)
    panel._pick_sheets_file()
    panel._pick_sheets_folder()
    assert panel.sheets_path() is None


# ---------------------------------------------------------------------
# gui.app_tools._sheet_prompt_map (F6, REWORK.md, owner E2) — the pure
# drop_path -> prompt builder over a sheet FILE or FOLDER, offline,
# no Tk at all.
# ---------------------------------------------------------------------


def _write_sheet_md(path: Path, drop: str, prompt: str) -> None:
    path.write_text(
        f"# Theme\n\n**Entry** → `{drop}`\n\n```\n{prompt}\n```\n",
        encoding="utf-8",
    )


def test_sheet_prompt_map_over_a_single_file(tmp_path):
    sheet = tmp_path / "theme.md"
    _write_sheet_md(sheet, "assets/emblem/Glory.png", "A golden sun disc.")
    prompts = gui.app_tools._sheet_prompt_map(sheet, log=lambda _l: None)
    assert prompts == {"assets/emblem/Glory.png": "A golden sun disc."}


def test_sheet_prompt_map_over_a_folder_reads_every_md_recursively(tmp_path):
    folder = tmp_path / "sheets"
    (folder / "sub").mkdir(parents=True)
    _write_sheet_md(folder / "a.md", "assets/emblem/Glory.png", "prompt A")
    _write_sheet_md(folder / "sub" / "b.md", "assets/emblem/Mercy.png", "prompt B")

    prompts = gui.app_tools._sheet_prompt_map(folder, log=lambda _l: None)
    assert prompts == {
        "assets/emblem/Glory.png": "prompt A",
        "assets/emblem/Mercy.png": "prompt B",
    }


def test_sheet_prompt_map_a_bad_sheet_is_logged_not_fatal(tmp_path):
    """A sheet with no '# H1' theme heading is not a prompt sheet at
    all (SheetError) — a loud per-file log line, never a run kill; its
    sibling sheets still contribute (root Rule #1)."""
    folder = tmp_path / "sheets"
    folder.mkdir()
    (folder / "broken.md").write_text("no theme heading here\n", encoding="utf-8")
    _write_sheet_md(folder / "good.md", "assets/emblem/Glory.png", "prompt A")

    logs: list[str] = []
    prompts = gui.app_tools._sheet_prompt_map(folder, log=logs.append)
    assert prompts == {"assets/emblem/Glory.png": "prompt A"}
    assert any("broken.md" in line and "failed to parse" in line for line in logs)


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
        sheets_path=None,
    ):
        self.run_ai_check_job_calls.append({
            "folder": folder, "files": list(files), "out_base": out_base,
            "sheets_path": sheets_path,
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


def test_start_ai_check_passes_the_panels_sheets_path(root, tmp_path):
    """F6 (REWORK.md, owner E2): the panel's OPTIONAL second input
    reaches the worker UNCHANGED — resolved (folder-walked) only on
    the worker thread, never here."""
    folder = tmp_path / "images"
    folder.mkdir()
    Image.new("RGBA", (10, 10)).save(folder / "a.png")
    sheets_dir = tmp_path / "sheets"
    sheets_dir.mkdir()

    panel = make_panel(gui.ImageCheckerSettingsPanel, root)
    panel._input_mode = "folder"
    panel._folder = folder
    panel._sheets_path = sheets_dir

    fake = FakeGuiForAiCheck(panel)
    gui.PainterGui._start_ai_check(fake, "aicheck")

    fake._tool_workers["aicheck"].join(timeout=5)
    assert fake.run_ai_check_job_calls[0]["sheets_path"] == sheets_dir


def test_start_ai_check_with_no_sheets_picked_passes_none(root, tmp_path):
    folder = tmp_path / "images"
    folder.mkdir()
    Image.new("RGBA", (10, 10)).save(folder / "a.png")

    panel = make_panel(gui.ImageCheckerSettingsPanel, root)
    panel._input_mode = "folder"
    panel._folder = folder

    fake = FakeGuiForAiCheck(panel)
    gui.PainterGui._start_ai_check(fake, "aicheck")

    fake._tool_workers["aicheck"].join(timeout=5)
    assert fake.run_ai_check_job_calls[0]["sheets_path"] is None


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
# SAME way the four tools' own Stop request-half is in
# test_tool_panels_base.py, just keyed "aicheck".
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
# worker half. Mirrors test_tool_panels_base.py's own
# test_run_tool_job_stop_flag_halts_between_images exactly: should_stop
# is checked BETWEEN images only, never mid-call, so the in-flight
# vision call always finishes. painter.ai.check_one_image is
# MONKEYPATCHED — no network, no API quota spent.
# ---------------------------------------------------------------------


class _FakeGuiForJob:
    """Just enough surface for the UNBOUND ``_run_ai_check_job`` to run
    for real — see test_tool_panels_base.py's own copy for the full
    rationale."""

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


# ---------------------------------------------------------------------
# _run_ai_check_job — the F6 (REWORK.md, owner E2) TWO-INPUT flow:
# given a sheets_path, only images whose reversed drop path
# (ai.drop_and_site_for) matches a sheet entry are checked, WITH that
# entry's prompt; the rest are loud-skipped (never a silent
# truncation). No sheets_path keeps every image quality-only
# (prompt=None) — the pre-F6 contract, unchanged.
# ---------------------------------------------------------------------


def _capturing_check_one_image(calls: list):
    def _check(src, out_base, instructions, *, prompt=None, log=print, **_kw):
        calls.append((src.name, prompt))
        return {
            "rel": src.name, "kind": "ok", "defects": [], "raw": "OK",
            "time": 0.01,
        }
    return _check


def test_run_ai_check_job_with_sheets_checks_only_matched_images(
    tmp_path, monkeypatch,
):
    import painter.ai as ai_module

    # the layout ai.drop_and_site_for reverses: <out>/<drop>/<File>_<sfx>
    # .png -> ('<drop>/<File>.png', site) — the sheet's path, verbatim
    out_base = tmp_path / "out"
    (out_base / "assets" / "emblem").mkdir(parents=True)
    (out_base / "emblem").mkdir(parents=True, exist_ok=True)
    matched = out_base / "assets" / "emblem" / "Glory_gem.png"
    unmatched = out_base / "emblem" / "Mystery_gem.png"
    Image.new("RGBA", (10, 10)).save(matched)
    Image.new("RGBA", (10, 10)).save(unmatched)

    sheets_dir = tmp_path / "sheets"
    sheets_dir.mkdir()
    _write_sheet_md(
        sheets_dir / "theme.md", "assets/emblem/Glory.png",
        "A golden sun disc.",
    )

    calls: list = []
    monkeypatch.setattr(
        ai_module, "check_one_image", _capturing_check_one_image(calls),
    )

    fake = _FakeGuiForJob()
    gui.PainterGui._run_ai_check_job(
        fake, out_base, [matched, unmatched], out_base,
        pause_event=threading.Event(), stop_event=threading.Event(),
        sheets_path=sheets_dir,
    )

    # ONLY the matched image was checked, WITH its sheet prompt
    assert calls == [("Glory_gem.png", "A golden sun disc.")]

    msgs = _drain(fake._q)
    text_lines = [m for m in msgs if isinstance(m, str)]
    events = [
        m for m in msgs if isinstance(m, tuple) and m[0] == "__event__"
    ]
    # the unmatched skip is a LOUD log line — never a silent truncation
    assert any(
        "1 image(s) matched" in line and "1 skipped" in line
        for line in text_lines
    )
    item_starts = [e[2] for e in events if e[2]["type"] == "item_start"]
    assert len(item_starts) == 1
    assert item_starts[0]["title"] == "Glory_gem.png"


def test_run_ai_check_job_with_sheet_file_input_matches_too(
    tmp_path, monkeypatch,
):
    """The sheets_path may be a single .md FILE, not only a folder."""
    import painter.ai as ai_module

    out_base = tmp_path / "out"
    (out_base / "assets" / "emblem").mkdir(parents=True)
    (out_base / "emblem").mkdir(parents=True, exist_ok=True)
    matched = out_base / "assets" / "emblem" / "Glory_gem.png"
    Image.new("RGBA", (10, 10)).save(matched)

    sheet = tmp_path / "theme.md"
    _write_sheet_md(sheet, "assets/emblem/Glory.png", "A golden sun disc.")

    calls: list = []
    monkeypatch.setattr(
        ai_module, "check_one_image", _capturing_check_one_image(calls),
    )

    fake = _FakeGuiForJob()
    gui.PainterGui._run_ai_check_job(
        fake, out_base, [matched], out_base,
        pause_event=threading.Event(), stop_event=threading.Event(),
        sheets_path=sheet,
    )
    assert calls == [("Glory_gem.png", "A golden sun disc.")]


def test_run_ai_check_job_without_sheets_is_quality_only_for_everyone(
    tmp_path, monkeypatch,
):
    """Regression guard (pre-F6 contract): no sheets_path -> every
    image is checked, WITH prompt=None — nothing skipped, nothing
    matched, exactly like before this phase."""
    import painter.ai as ai_module

    folder = tmp_path / "images"
    folder.mkdir()
    files = []
    for i in range(2):
        p = folder / f"img_{i}.png"
        Image.new("RGBA", (10, 10)).save(p)
        files.append(p)

    calls: list = []
    monkeypatch.setattr(
        ai_module, "check_one_image", _capturing_check_one_image(calls),
    )

    fake = _FakeGuiForJob()
    gui.PainterGui._run_ai_check_job(
        fake, folder, files, tmp_path,
        pause_event=threading.Event(), stop_event=threading.Event(),
    )
    assert sorted(calls) == [("img_0.png", None), ("img_1.png", None)]
