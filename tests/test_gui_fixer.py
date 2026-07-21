"""Fixer AI wiring (GUI rework Phase 20, owner 2026-07-21,
UV/prompt.txt item 1: "ako ustanovi gresku salje fikseru da ispravi i
to u situaciji ako su oba ukljucena"; item 2: "Checker double click ->
... buttone za IMAGE FIX i WEBSITE fix ... kreira PROMPT koji salje uz
sliku"). Mirrors test_gui_checker.py's own structure and conventions —
NO real quota, NO real Chrome: every test monkeypatches
``painter.ai.edit_image`` and ``painter.driver.SiteDriver``.

Six halves, matching gui.py's own "pure helpers get pytest, real Tk/UI
wiring gets a screenshot" split:

* ``ai.build_fix_prompt`` — covered in test_ai.py, not repeated here.
* ``AgentPanel``'s new ``fixer_var``/``fixer_mode_var`` — defaults,
  persistence round-trip, and visibility TIED to ``checker_var``
  (``_apply_fixer_visibility``'s pack state), the same "hidden until
  its own gate switch is on" contract the Upscale gate sub-block
  already established.
* ``gui._fixer_decision`` — the auto-dispatch's pure branch table
  (fixer off; not flagged; empty defects; api mode; website mode),
  headless, no Tk.
* ``PainterGui._maybe_spawn_fixer``/``_run_fixer_api``/
  ``_queue_website_fix`` — the auto-dispatch engine, run for REAL
  through a small duck-typed ``_FakeGuiForFixer`` (the SAME minimal-
  surface convention test_gui_checker.py's own ``_FakeGuiForChecker``
  uses): API mode spawns a background thread that calls the MOCKED
  ``ai.edit_image``, backs the pre-fix file up under JobTemp
  ``step="fixer"``, overwrites it and posts ``item_fixed``; website
  mode NEVER touches ``ai.edit_image``/``driver.SiteDriver`` at all —
  it folds the item into ``AiCheckPanel``'s own ``_flagged`` bucket and
  reveals the dashboard slot; a ``PaidFeatureRequired`` is gated and
  non-fatal (loud log line, no file write, no crash).
* ``PainterGui._build_fix_workers``/``_run_image_fix``/
  ``_run_website_fix`` — the MANUAL buttons' engine: site resolution
  (an explicit ``jobtemp_slot`` from ``DashPanel`` vs
  ``ai.drop_and_site_for`` fallback for ``AiCheckPanel``), IMAGE FIX's
  gate/success paths, and WEBSITE FIX's "site currently running -> a
  transient error, the browser is NEVER touched" guard plus its
  configured attach -> submit_fix -> await_done -> extract_image ->
  close sequence (a duck-typed fake ``SiteDriver``, mirroring
  test_driver.py's own fakes) and its ``FixNotConfigured`` gate.
* ``DocWindow``'s manual buttons + ``gui._fix_result_ui`` — the pure
  result-to-UI mapping behind ``_apply_fix_result`` (headless, Tk-free
  — no test in this suite constructs a real ``tk.Toplevel``; the real
  window is screenshot-verified) — and ``DashPanel._show_check``/
  ``AiCheckPanel._on_activate`` only ever pass fix workers into
  ``DocWindow`` when the report actually carries defects.
"""

from __future__ import annotations

import queue
import threading
from pathlib import Path
from types import SimpleNamespace

import pytest
from PIL import Image

import gui
from painter import ai as ai_module
from painter import driver as driver_module
from painter.config import FIXER_MODE_API, FIXER_MODE_WEBSITE, SITES
from painter.jobtemp import JobTemp, clear_all

# a real 1x1 PNG (same fixture bytes as test_ai.py/test_runner.py)
PNG_1PX = bytes.fromhex(
    "89504e470d0a1a0a0000000d49484452000000010000000108060000001f15c489"
    "0000000d4944415478da63fcffff3f030005fe02fea72d994800000000"
    "49454e44ae426082"
)
FIXED_PNG = bytes.fromhex(
    "89504e470d0a1a0a0000000d49484452000000010000000108060000001f15c489"
    "0000000a4944415478da63626000000005000164005c1c2c8a0000000049454e44"
    "ae426082"
)


@pytest.fixture(autouse=True)
def _sweep_temp():
    """JobTemp's real backup root is PROJECT-relative (jobtemp.py's
    TEMP_ROOT), not tmp_path-relative — sweep it after every test, same
    as test_gui_pipeline.py/test_gui_api_image.py."""
    yield
    clear_all()


@pytest.fixture
def root(tk_root):
    return tk_root


def make_panel(root, site: str = "gemini") -> gui.AgentPanel:
    return gui.AgentPanel(
        root, site,
        on_start=lambda *_a: None, on_stop=lambda *_a: None,
        on_pause=lambda *_a: None,
    )


def make_png(path: Path, width: int = 10, height: int = 10) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    Image.new("RGBA", (width, height)).save(path, "PNG")


def flagged_event(drop_path: str, rel: str, defects=("halo off-centre",)):
    return {
        "type": "item_checked", "drop_path": drop_path, "kind": "flagged",
        "defects": list(defects), "raw": "DEFECTS:\n- halo off-centre",
        "rel": rel, "time": 0.2,
    }


# ---------------------------------------------------------------------
# AgentPanel.fixer_var / fixer_mode_var — defaults, persistence,
# visibility tied to checker_var
# ---------------------------------------------------------------------


def test_fixer_var_defaults_false_mode_defaults_api(root):
    panel = make_panel(root)
    assert panel.fixer_var.get() is False
    assert panel.fixer_mode_var.get() == FIXER_MODE_API


def test_fixer_is_in_persist_and_vars(root):
    panel = make_panel(root)
    assert "fixer" in panel._PERSIST
    assert "fixer_mode" in panel._PERSIST
    assert panel._vars()["fixer"] is panel.fixer_var
    assert panel._vars()["fixer_mode"] is panel.fixer_mode_var


def test_get_settings_round_trips_fixer_fields(root):
    panel = make_panel(root)
    panel.fixer_var.set(True)
    panel.fixer_mode_var.set(FIXER_MODE_WEBSITE)
    stored = panel.get_settings()
    assert stored["fixer"] is True
    assert stored["fixer_mode"] == FIXER_MODE_WEBSITE

    fresh = make_panel(root)
    fresh.apply_settings(stored)
    assert fresh.fixer_var.get() is True
    assert fresh.fixer_mode_var.get() == FIXER_MODE_WEBSITE


def test_apply_settings_missing_fixer_keys_keep_the_defaults(root):
    panel = make_panel(root)
    panel.apply_settings({"background": "white"})  # no fixer/fixer_mode key
    assert panel.fixer_var.get() is False
    assert panel.fixer_mode_var.get() == FIXER_MODE_API


def test_fixer_box_hidden_until_checker_is_on(root):
    """_apply_fixer_visibility mirrors _apply_upscale_gate_visibility
    exactly: the sub-block is packed only while checker_var is True,
    independently of the Settings gear's own collapse state. Checked
    via winfo_manager() (empty = unmanaged/pack_forget'd, "pack" = under
    pack management) rather than winfo_ismapped() — the shared tk_root
    fixture is withdrawn, so nothing in this panel's ancestor chain is
    ever actually mapped on screen, which winfo_ismapped() requires."""
    panel = make_panel(root)
    assert panel.checker_var.get() is False
    assert panel._fixer_box.winfo_manager() == ""

    panel.checker_var.set(True)
    assert panel._fixer_box.winfo_manager() == "pack"

    panel.checker_var.set(False)
    assert panel._fixer_box.winfo_manager() == ""


# ---------------------------------------------------------------------
# gui._fixer_decision — the auto-dispatch's pure branch table
# ---------------------------------------------------------------------


class _FakeAgentSwitches:
    """Bare duck-typed stand-in for _fixer_decision's own read surface
    (only .fixer_var/.fixer_mode_var are read) — a plain object, no Tk,
    no full AgentPanel needed for the pure decision table."""

    def __init__(self, fixer_on: bool, mode: str = FIXER_MODE_API):
        self.fixer_var = SimpleNamespace(get=lambda: fixer_on)
        self.fixer_mode_var = SimpleNamespace(get=lambda: mode)


def test_fixer_decision_off_is_none():
    agent = _FakeAgentSwitches(fixer_on=False)
    event = {"kind": "flagged", "defects": ["x"]}
    assert gui._fixer_decision(agent, event) == "none"


def test_fixer_decision_on_but_not_flagged_is_none():
    agent = _FakeAgentSwitches(fixer_on=True)
    for kind in ("ok", "error"):
        event = {"kind": kind, "defects": []}
        assert gui._fixer_decision(agent, event) == "none"


def test_fixer_decision_flagged_but_empty_defects_is_none():
    """A malformed/edge-case flagged result with no actual defect text
    — nothing to fix, never dispatched."""
    agent = _FakeAgentSwitches(fixer_on=True)
    event = {"kind": "flagged", "defects": []}
    assert gui._fixer_decision(agent, event) == "none"


def test_fixer_decision_api_mode_with_defects_is_api():
    agent = _FakeAgentSwitches(fixer_on=True, mode=FIXER_MODE_API)
    event = {"kind": "flagged", "defects": ["x"]}
    assert gui._fixer_decision(agent, event) == "api"


def test_fixer_decision_website_mode_with_defects_is_website_queue():
    agent = _FakeAgentSwitches(fixer_on=True, mode=FIXER_MODE_WEBSITE)
    event = {"kind": "flagged", "defects": ["x"]}
    assert gui._fixer_decision(agent, event) == "website_queue"


# ---------------------------------------------------------------------
# PainterGui._maybe_spawn_fixer / _run_fixer_api / _queue_website_fix
# ---------------------------------------------------------------------


class _FakeDashGrid:
    def __init__(self):
        self.added: list[str] = []

    def add(self, kind: str) -> None:
        self.added.append(kind)


class _FakeGuiForFixer:
    """Just enough surface for the UNBOUND _maybe_spawn_fixer/
    _run_fixer_api/_queue_website_fix/_backup_before_fix to run for
    real — the SAME minimal-surface FakeGui convention
    test_gui_checker.py's own _FakeGuiForChecker uses. _log is a plain
    list-append (PainterGui._log touches a real tk.Text — everything
    that reaches it here runs on the MAIN thread synchronously, so a
    fake is enough; the background half posts through self._q instead,
    exactly like production)."""

    _maybe_spawn_fixer = gui.PainterGui._maybe_spawn_fixer
    _run_fixer_api = gui.PainterGui._run_fixer_api
    _queue_website_fix = gui.PainterGui._queue_website_fix
    _backup_before_fix = gui.PainterGui._backup_before_fix

    def __init__(self, agents: dict, panels: dict, job_temps: dict | None = None):
        self.agents = agents
        self.panels = panels
        self._dashgrid = _FakeDashGrid()
        self._job_temps = job_temps if job_temps is not None else {}
        self._running: set[str] = set()
        self._q: "queue.Queue" = queue.Queue()
        self.log_lines: list[str] = []

    def _log(self, line: str) -> None:
        self.log_lines.append(line)


def _drain(q: queue.Queue) -> list:
    out = []
    while True:
        try:
            out.append(q.get_nowait())
        except queue.Empty:
            return out


def _wait_for_event(q: queue.Queue, event_type: str, timeout: float = 5.0) -> tuple:
    """Bounded wait for the ``("__event__", key, {...})`` tuple carrying
    ``event_type`` — unlike a bare ``q.get(timeout=...)``, this tolerates
    (and discards) any plain log STRINGS the background worker posts
    first (``_run_fixer_api`` logs "FIXED (API): …" before it emits the
    event, exactly like production interleaves text lines and events).
    Never a sleep loop — each ``get`` still blocks with a shrinking
    deadline."""
    import time

    deadline = time.monotonic() + timeout
    while True:
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            raise AssertionError(
                f"no {event_type!r} event arrived within {timeout}s"
            )
        msg = q.get(timeout=remaining)
        if (
            isinstance(msg, tuple) and msg[0] == "__event__"
            and msg[2].get("type") == event_type
        ):
            return msg


def test_maybe_spawn_fixer_off_does_nothing(root, tmp_path):
    agent = make_panel(root, "gemini")
    assert agent.fixer_var.get() is False
    dash = gui.DashPanel(root, "gemini")
    dash.out_base = tmp_path

    fake = _FakeGuiForFixer({"gemini": agent}, {"gemini": dash})
    gui.PainterGui._maybe_spawn_fixer(
        fake, "gemini",
        flagged_event("assets/x/a.png", "emblem/gemini/a.png"),
    )
    assert fake._q.empty()
    assert fake.log_lines == []
    assert fake._dashgrid.added == []


def test_maybe_spawn_fixer_api_mode_calls_edit_image_and_overwrites(
    root, tmp_path, monkeypatch,
):
    out_base = tmp_path / "out"
    drop = "assets/emblem/Glory.png"
    rel = gui.dest_for(drop, "gemini")
    live = out_base / rel
    make_png(live)

    captured = {}

    def fake_edit_image(image_path, prompt, *, key=None, model=None, log=print):
        captured["image_path"] = image_path
        captured["prompt"] = prompt
        return FIXED_PNG

    monkeypatch.setattr(ai_module, "edit_image", fake_edit_image)

    agent = make_panel(root, "gemini")
    agent.fixer_var.set(True)
    agent.fixer_mode_var.set(FIXER_MODE_API)
    dash = gui.DashPanel(root, "gemini")
    dash.out_base = out_base

    temp = JobTemp("gemini", out_base)
    fake = _FakeGuiForFixer(
        {"gemini": agent}, {"gemini": dash}, job_temps={"gemini": temp},
    )
    gui.PainterGui._maybe_spawn_fixer(
        fake, "gemini", flagged_event(drop, rel, ["halo off-centre"]),
    )

    # the background thread posts a log line THEN the event — bounded
    # wait that skips past the log string (see _wait_for_event)
    msg = _wait_for_event(fake._q, "item_fixed")
    assert msg == ("__event__", "gemini", {
        "type": "item_fixed", "drop_path": drop, "mode": "api",
    })
    assert live.read_bytes() == FIXED_PNG
    assert temp.has_backup(rel, step="fixer") is True
    assert "halo off-centre" in captured["prompt"]
    assert captured["image_path"] == live


def test_maybe_spawn_fixer_api_mode_paid_feature_required_is_gated_non_fatal(
    root, tmp_path, monkeypatch,
):
    out_base = tmp_path / "out"
    drop = "assets/emblem/Glory.png"
    rel = gui.dest_for(drop, "gemini")
    live = out_base / rel
    make_png(live)
    original_bytes = live.read_bytes()

    def fake_edit_image(*a, **k):
        raise ai_module.PaidFeatureRequired("free_tier limit: 0")

    monkeypatch.setattr(ai_module, "edit_image", fake_edit_image)

    agent = make_panel(root, "gemini")
    agent.fixer_var.set(True)
    agent.fixer_mode_var.set(FIXER_MODE_API)
    dash = gui.DashPanel(root, "gemini")
    dash.out_base = out_base

    fake = _FakeGuiForFixer({"gemini": agent}, {"gemini": dash})
    gui.PainterGui._maybe_spawn_fixer(
        fake, "gemini", flagged_event(drop, rel),
    )

    # a LOUD log string lands (proving the thread ran to completion),
    # never an item_fixed event, never a crash, never a file write
    msg = fake._q.get(timeout=5)
    assert isinstance(msg, str)
    assert "GATED" in msg
    assert live.read_bytes() == original_bytes  # untouched


def test_maybe_spawn_fixer_website_mode_never_touches_edit_image_or_driver(
    root, tmp_path, monkeypatch,
):
    """The core Phase-20 physical-constraint proof: website mode must
    NEVER drive ai.edit_image or construct a SiteDriver from the
    auto-dispatch path — both are monkeypatched to raise if touched."""

    def _boom(*a, **k):
        raise AssertionError("the auto-fixer must never drive this")

    monkeypatch.setattr(ai_module, "edit_image", _boom)
    monkeypatch.setattr(driver_module, "SiteDriver", _boom)

    drop = "assets/emblem/Glory.png"
    rel = gui.dest_for(drop, "gemini")
    agent = make_panel(root, "gemini")
    agent.fixer_var.set(True)
    agent.fixer_mode_var.set(FIXER_MODE_WEBSITE)
    dash = gui.DashPanel(root, "gemini")
    dash.out_base = tmp_path

    aicheck = gui.AiCheckPanel(root)
    fake = _FakeGuiForFixer(
        {"gemini": agent}, {"gemini": dash, "aicheck": aicheck},
    )
    gui.PainterGui._maybe_spawn_fixer(
        fake, "gemini", flagged_event(drop, rel, ["halo off-centre"]),
    )

    # synchronous — no thread, no queue traffic at all
    assert fake._q.empty()
    # QUEUED, visibly: the SAME bucket "Send flagged to generator" reads
    assert aicheck._flagged[rel] == ["halo off-centre"]
    assert fake._dashgrid.added == ["aicheck"]
    assert any("queued" in line for line in fake.log_lines)


def test_maybe_spawn_fixer_website_mode_merges_with_existing_batch_flags(
    root, tmp_path,
):
    """The queue reuses AiCheckPanel's OWN append-only _flagged bucket —
    an existing standalone-batch flag for a DIFFERENT image survives
    the merge untouched."""
    aicheck = gui.AiCheckPanel(root)
    aicheck.out_base = tmp_path
    aicheck.handle({
        "type": "item_flagged", "rel": "other/img.png",
        "defects": ["pre-existing"], "raw": "DEFECTS:\n- pre-existing",
        "time": 0.1,
    })

    agent = make_panel(root, "gemini")
    agent.fixer_var.set(True)
    agent.fixer_mode_var.set(FIXER_MODE_WEBSITE)
    dash = gui.DashPanel(root, "gemini")
    dash.out_base = tmp_path

    fake = _FakeGuiForFixer(
        {"gemini": agent}, {"gemini": dash, "aicheck": aicheck},
    )
    drop = "assets/emblem/Glory.png"
    rel = gui.dest_for(drop, "gemini")
    gui.PainterGui._maybe_spawn_fixer(
        fake, "gemini", flagged_event(drop, rel, ["new defect"]),
    )

    assert aicheck._flagged["other/img.png"] == ["pre-existing"]
    assert aicheck._flagged[rel] == ["new defect"]


# ---------------------------------------------------------------------
# PainterGui._dispatch — routes item_checked into the fixer
# ---------------------------------------------------------------------


def test_dispatch_routes_item_checked_into_the_fixer(root, tmp_path, monkeypatch):
    monkeypatch.setattr(ai_module, "edit_image", lambda *a, **k: FIXED_PNG)
    out_base = tmp_path / "out"
    drop = "assets/emblem/Glory.png"
    rel = gui.dest_for(drop, "gemini")
    make_png(out_base / rel)

    agent = make_panel(root, "gemini")
    agent.fixer_var.set(True)
    dash = gui.DashPanel(root, "gemini")
    dash.out_base = out_base

    fake = _FakeGuiForFixer(
        {"gemini": agent}, {"gemini": dash},
        job_temps={"gemini": JobTemp("gemini-dispatch", out_base)},
    )
    gui.PainterGui._dispatch(
        fake, ("__event__", "gemini", flagged_event(drop, rel)),
    )
    msg = _wait_for_event(fake._q, "item_fixed")
    assert msg[2]["type"] == "item_fixed"


def test_dispatch_does_not_spawn_fixer_for_item_checking(root, tmp_path):
    """item_checking (the SYNCHRONOUS 'checking…' marker) must never be
    mistaken for a completed check — only item_checked dispatches."""
    agent = make_panel(root, "gemini")
    agent.fixer_var.set(True)
    dash = gui.DashPanel(root, "gemini")
    dash.out_base = tmp_path

    fake = _FakeGuiForFixer({"gemini": agent}, {"gemini": dash})
    gui.PainterGui._dispatch(
        fake, (
            "__event__", "gemini",
            {"type": "item_checking", "drop_path": "assets/x/a.png"},
        ),
    )
    assert fake._q.empty()
    assert fake.log_lines == []


# ---------------------------------------------------------------------
# DashPanel.handle — the "item_fixed" row update
# ---------------------------------------------------------------------


def make_progress_event(drop: str, size: int) -> dict:
    return {
        "type": "item_progress", "idx": 1, "of": 1, "title": drop,
        "drop_path": drop, "gen_s": 5.0, "orig_res": "10x10",
        "final_res": "10x10", "size": size, "actions": "", "retried": False,
    }


def test_dash_panel_item_fixed_refreshes_row_and_appends_marker(root, tmp_path):
    out_base = tmp_path / "out"
    drop = "assets/emblem/Glory.png"
    rel = gui.dest_for(drop, "gemini")
    live = out_base / rel
    make_png(live, 10, 10)

    panel = gui.DashPanel(root, "gemini")
    panel.out_base = out_base
    panel.handle(make_progress_event(drop, live.stat().st_size))
    panel.handle({
        "type": "item_checked", "drop_path": drop, "kind": "flagged",
        "defects": ["x"], "raw": "DEFECTS:\n- x", "rel": rel, "time": 0.1,
    })
    row = panel._child_ids[drop]
    assert panel.tree.set(row, "check") == "flagged 1"

    make_png(live, 40, 30)  # the fixer overwrote it with a new resolution
    panel.handle({"type": "item_fixed", "drop_path": drop, "mode": "api"})

    assert panel.tree.set(row, "res") == "40x30"
    assert panel.tree.set(row, "check") == "flagged 1 → fixed"


def test_dash_panel_item_fixed_for_an_unknown_row_does_not_raise(root, tmp_path):
    panel = gui.DashPanel(root, "gemini")
    panel.out_base = tmp_path
    panel.handle({
        "type": "item_fixed", "drop_path": "never/inserted.png",
        "mode": "api",
    })  # must not raise


# ---------------------------------------------------------------------
# PainterGui._build_fix_workers — site resolution
# ---------------------------------------------------------------------


class _FakeGuiForBuild:
    """Just enough surface for the UNBOUND _build_fix_workers/
    _run_image_fix/_run_website_fix to run — mirrors
    test_gui_api_image.py's own _FakeGuiForCompose convention."""

    _build_fix_workers = gui.PainterGui._build_fix_workers
    _run_image_fix = gui.PainterGui._run_image_fix
    _run_website_fix = gui.PainterGui._run_website_fix
    _backup_before_fix = gui.PainterGui._backup_before_fix

    def __init__(self, job_temps: dict | None = None, running: set | None = None):
        self._job_temps = job_temps if job_temps is not None else {}
        self._running: set[str] = running if running is not None else set()
        self._q: "queue.Queue" = queue.Queue()


def test_build_fix_workers_image_worker_always_offered(tmp_path):
    fake = _FakeGuiForBuild()
    image_worker, website_worker = gui.PainterGui._build_fix_workers(
        fake, "loose/no-site-here.png", tmp_path, ["x"], "raw",
    )
    assert callable(image_worker)
    assert website_worker is None  # no resolvable site


def test_build_fix_workers_website_worker_from_explicit_jobtemp_slot(tmp_path):
    """DashPanel's own call shape — it already knows its slot_key."""
    fake = _FakeGuiForBuild()
    image_worker, website_worker = gui.PainterGui._build_fix_workers(
        fake, "emblem/gemini/Glory.png", tmp_path, ["x"], "raw",
        jobtemp_slot="gemini",
    )
    assert callable(image_worker)
    assert callable(website_worker)


def test_build_fix_workers_website_worker_via_drop_and_site_for_fallback(tmp_path):
    """AiCheckPanel's own call shape — jobtemp_slot=None, resolved via
    ai.drop_and_site_for (the SAME dest_for reverse the re-send plan
    already uses) from a rel matching the real assets-mirror shape."""
    fake = _FakeGuiForBuild()
    rel = gui.dest_for("assets/emblem/Glory.png", "chatgpt")
    image_worker, website_worker = gui.PainterGui._build_fix_workers(
        fake, rel, tmp_path, ["x"], "raw",
    )
    assert callable(image_worker)
    assert callable(website_worker)


def test_build_fix_workers_api_image_slot_has_no_website_worker(tmp_path):
    """"api_image" is a real JobTemp slot but NOT a SITES entry — no
    browser tab to drive, so WEBSITE FIX must not be offered even
    though the JobTemp backup path (jobtemp_slot) is valid."""
    assert "api_image" not in SITES
    fake = _FakeGuiForBuild()
    image_worker, website_worker = gui.PainterGui._build_fix_workers(
        fake, "badge/api_image/Glory.png", tmp_path, ["x"], "raw",
        jobtemp_slot="api_image",
    )
    assert callable(image_worker)
    assert website_worker is None


# ---------------------------------------------------------------------
# PainterGui._run_image_fix — the manual IMAGE FIX button's engine
# ---------------------------------------------------------------------


def test_run_image_fix_success_overwrites_and_backs_up(tmp_path, monkeypatch):
    out_base = tmp_path / "out"
    rel = "emblem/gemini/Glory.png"
    live = out_base / rel
    make_png(live)

    def fake_edit_image(image_path, prompt, *, key=None, model=None, log=print):
        assert image_path == live
        assert "halo" in prompt
        return FIXED_PNG

    monkeypatch.setattr(ai_module, "edit_image", fake_edit_image)
    temp = JobTemp("gemini", out_base)
    fake = _FakeGuiForBuild(job_temps={"gemini": temp})

    result = gui.PainterGui._run_image_fix(
        fake, rel, out_base, "gemini", ["halo off-centre"], "raw",
    )
    assert result[0] == "ok"
    assert live.read_bytes() == FIXED_PNG
    assert temp.has_backup(rel, step="fixer") is True


def test_run_image_fix_paid_feature_required_is_gated_file_untouched(
    tmp_path, monkeypatch,
):
    out_base = tmp_path / "out"
    rel = "emblem/gemini/Glory.png"
    live = out_base / rel
    make_png(live)
    original = live.read_bytes()

    def fake_edit_image(*a, **k):
        raise ai_module.PaidFeatureRequired("free_tier limit: 0")

    monkeypatch.setattr(ai_module, "edit_image", fake_edit_image)
    fake = _FakeGuiForBuild()

    kind, message = gui.PainterGui._run_image_fix(
        fake, rel, out_base, "gemini", ["x"], "raw",
    )
    assert kind == "gated"
    assert live.read_bytes() == original


def test_run_image_fix_other_ai_error_is_a_retryable_error(tmp_path, monkeypatch):
    out_base = tmp_path / "out"
    rel = "emblem/gemini/Glory.png"
    make_png(out_base / rel)

    def fake_edit_image(*a, **k):
        raise ai_module.AiError("Gemini API unreachable")

    monkeypatch.setattr(ai_module, "edit_image", fake_edit_image)
    fake = _FakeGuiForBuild()

    kind, message = gui.PainterGui._run_image_fix(
        fake, rel, out_base, "gemini", ["x"], "raw",
    )
    assert kind == "error"
    assert "unreachable" in message


def test_run_image_fix_without_a_live_jobtemp_still_fixes_but_skips_backup(
    tmp_path, monkeypatch,
):
    """No active JobTemp for the slot (the site's dashboard panel was
    already Closed this session) — the fix still applies; the backup is
    skipped LOUDLY (root Rule #1), never silently."""
    out_base = tmp_path / "out"
    rel = "emblem/gemini/Glory.png"
    live = out_base / rel
    make_png(live)
    monkeypatch.setattr(ai_module, "edit_image", lambda *a, **k: FIXED_PNG)
    fake = _FakeGuiForBuild()  # no job_temps entry for "gemini"

    kind, _ = gui.PainterGui._run_image_fix(
        fake, rel, out_base, "gemini", ["x"], "raw",
    )
    assert kind == "ok"
    assert live.read_bytes() == FIXED_PNG
    log_lines = [m for m in _drain(fake._q) if isinstance(m, str)]
    assert any("no active JobTemp" in line for line in log_lines)


# ---------------------------------------------------------------------
# PainterGui._run_website_fix — the manual WEBSITE FIX button's engine
# ---------------------------------------------------------------------


def test_run_website_fix_refuses_while_the_site_is_running_never_touches_driver(
    tmp_path, monkeypatch,
):
    def _boom(*a, **k):
        raise AssertionError("must never construct a driver while running")

    monkeypatch.setattr(driver_module, "SiteDriver", _boom)
    fake = _FakeGuiForBuild(running={"gemini"})

    kind, message = gui.PainterGui._run_website_fix(
        fake, "emblem/gemini/Glory.png", tmp_path, "gemini", "gemini",
        ["x"], "raw",
    )
    assert kind == "error"  # transient — retry once idle, not permanently gated
    assert "generating" in message.lower()


class _FakeSiteDriverConfigured:
    """Duck-typed SiteDriver stand-in — records the attach -> submit_fix
    -> await_done -> extract_image -> close SEQUENCE, mirrors
    test_driver.py's own FakeLocator/FakePage call-order proofs one
    level up (at the SiteDriver interface, not the Playwright one)."""

    instances: list["_FakeSiteDriverConfigured"] = []

    def __init__(self, site, timing, cdp_url):
        self.site = site
        self.calls: list = []
        _FakeSiteDriverConfigured.instances.append(self)

    def attach(self):
        self.calls.append("attach")
        return "tab"

    def submit_fix(self, image_path, prompt):
        self.calls.append(("submit_fix", image_path, prompt))

    def await_done(self, log=print):
        self.calls.append("await_done")

    def extract_image(self):
        self.calls.append("extract_image")
        return FIXED_PNG

    def close(self):
        self.calls.append("close")


@pytest.fixture(autouse=True)
def _reset_fake_driver_instances():
    _FakeSiteDriverConfigured.instances.clear()
    yield
    _FakeSiteDriverConfigured.instances.clear()


def test_run_website_fix_success_drives_the_configured_sequence(
    tmp_path, monkeypatch,
):
    monkeypatch.setattr(driver_module, "SiteDriver", _FakeSiteDriverConfigured)
    out_base = tmp_path / "out"
    rel = "emblem/gemini/Glory.png"
    live = out_base / rel
    make_png(live)
    temp = JobTemp("gemini", out_base)
    fake = _FakeGuiForBuild(job_temps={"gemini": temp})

    kind, message = gui.PainterGui._run_website_fix(
        fake, rel, out_base, "gemini", "gemini", ["halo off-centre"], "raw",
    )
    assert kind == "ok"
    assert live.read_bytes() == FIXED_PNG
    assert temp.has_backup(rel, step="fixer") is True

    driver = _FakeSiteDriverConfigured.instances[0]
    assert driver.calls[0] == "attach"
    assert driver.calls[1][0] == "submit_fix"
    assert driver.calls[1][1] == str(live)
    assert "halo off-centre" in driver.calls[1][2]
    assert driver.calls[2] == "await_done"
    assert driver.calls[3] == "extract_image"
    assert driver.calls[-1] == "close"  # ALWAYS closed, even on success


class _FakeSiteDriverNotConfigured:
    def __init__(self, site, timing, cdp_url):
        pass

    def attach(self):
        return "tab"

    def submit_fix(self, image_path, prompt):
        raise driver_module.FixNotConfigured("attach_button/file_input empty")

    def close(self):
        pass


def test_run_website_fix_not_configured_is_gated(tmp_path, monkeypatch):
    monkeypatch.setattr(driver_module, "SiteDriver", _FakeSiteDriverNotConfigured)
    out_base = tmp_path / "out"
    rel = "emblem/gemini/Glory.png"
    make_png(out_base / rel)
    fake = _FakeGuiForBuild()

    kind, message = gui.PainterGui._run_website_fix(
        fake, rel, out_base, "gemini", "gemini", ["x"], "raw",
    )
    assert kind == "gated"
    assert "attach_button" in message or "not configured" in message.lower()


def test_run_website_fix_closes_the_driver_even_on_failure(tmp_path, monkeypatch):
    monkeypatch.setattr(driver_module, "SiteDriver", _FakeSiteDriverNotConfigured)
    fake = _FakeGuiForBuild()

    closed = []
    orig_close = _FakeSiteDriverNotConfigured.close
    _FakeSiteDriverNotConfigured.close = lambda self: closed.append(True)
    try:
        gui.PainterGui._run_website_fix(
            fake, "emblem/gemini/Glory.png", tmp_path, "gemini", "gemini",
            ["x"], "raw",
        )
    finally:
        _FakeSiteDriverNotConfigured.close = orig_close
    assert closed == [True]


# ---------------------------------------------------------------------
# gui._fix_result_ui — the pure result-to-UI mapping behind
# DocWindow._apply_fix_result
# ---------------------------------------------------------------------


def test_fix_result_ui_ok_leaves_both_buttons_disabled():
    status, enable_image, enable_website = gui._fix_result_ui(
        "image", ("ok", "the image was overwritten via the API."),
    )
    assert "Fixed" in status
    assert enable_image is None
    assert enable_website is None


def test_fix_result_ui_gated_reenables_only_the_other_button():
    status, enable_image, enable_website = gui._fix_result_ui(
        "image", ("gated", "paid feature required"),
    )
    assert enable_image is None       # the gated one stays off
    assert enable_website is True     # the OTHER path may still work

    status, enable_image, enable_website = gui._fix_result_ui(
        "website", ("gated", "attach_button/file_input empty"),
    )
    assert enable_website is None
    assert enable_image is True


def test_fix_result_ui_error_reenables_both():
    status, enable_image, enable_website = gui._fix_result_ui(
        "website", ("error", "gemini is currently generating"),
    )
    assert "Fix failed" in status
    assert enable_image is True
    assert enable_website is True


# ---------------------------------------------------------------------
# DocWindow's fix buttons appear only when workers were passed — proven
# via DashPanel._show_check/AiCheckPanel._on_activate (mocked DocWindow,
# never a real Toplevel — same convention test_gui_checker.py already
# uses for THIS exact call site).
# ---------------------------------------------------------------------


def test_show_check_passes_fix_workers_only_when_defects_exist(
    root, tmp_path, monkeypatch,
):
    out_base = tmp_path / "out"
    drop = "assets/emblem/Glory.png"
    rel = gui.dest_for(drop, "gemini")
    live = out_base / rel
    make_png(live)

    panel = gui.DashPanel(root, "gemini", on_fix_actions=_fixed_builder())
    panel.out_base = out_base
    panel.handle(make_progress_event(drop, live.stat().st_size))
    panel.handle({
        "type": "item_checked", "drop_path": drop, "kind": "flagged",
        "defects": ["subject cropped"], "raw": "DEFECTS:\n- subject cropped",
        "rel": rel, "time": 0.3,
    })
    row = panel._child_ids[drop]
    panel.tree.selection_set(row)
    panel.tree.focus(row)

    captured = {}

    def fake_docwindow(
        master, title, md, copy_text=None, hint=None, image_path=None,
        on_image_fix=None, on_website_fix=None,
    ):
        captured["on_image_fix"] = on_image_fix
        captured["on_website_fix"] = on_website_fix

    monkeypatch.setattr(gui, "DocWindow", fake_docwindow)
    panel._show_check()

    assert captured["on_image_fix"] is not None
    assert captured["on_website_fix"] is not None  # "gemini" resolves


def test_show_check_passes_no_fix_workers_for_an_ok_result(
    root, tmp_path, monkeypatch,
):
    out_base = tmp_path / "out"
    drop = "assets/emblem/Glory.png"
    rel = gui.dest_for(drop, "gemini")
    live = out_base / rel
    make_png(live)

    panel = gui.DashPanel(root, "gemini", on_fix_actions=_fixed_builder())
    panel.out_base = out_base
    panel.handle(make_progress_event(drop, live.stat().st_size))
    panel.handle({
        "type": "item_checked", "drop_path": drop, "kind": "ok",
        "defects": [], "raw": "OK", "rel": rel, "time": 0.1,
    })
    row = panel._child_ids[drop]
    panel.tree.selection_set(row)
    panel.tree.focus(row)

    captured = {}

    def fake_docwindow(
        master, title, md, copy_text=None, hint=None, image_path=None,
        on_image_fix=None, on_website_fix=None,
    ):
        captured["on_image_fix"] = on_image_fix
        captured["on_website_fix"] = on_website_fix

    monkeypatch.setattr(gui, "DocWindow", fake_docwindow)
    panel._show_check()

    assert captured["on_image_fix"] is None
    assert captured["on_website_fix"] is None


def test_ai_check_panel_on_activate_passes_fix_workers_when_flagged(
    root, tmp_path, monkeypatch,
):
    out_base = tmp_path / "out"
    rel = gui.dest_for("assets/emblem/Glory.png", "chatgpt")
    live = out_base / rel
    make_png(live)

    panel = gui.AiCheckPanel(root, on_fix_actions=_fixed_builder())
    panel.out_base = out_base
    panel.handle({
        "type": "item_flagged", "rel": rel, "defects": ["watermark"],
        "raw": "DEFECTS:\n- watermark", "time": 0.2,
    })
    row = panel._image_rows[rel]
    panel.tree.selection_set(row)
    panel.tree.focus(row)

    captured = {}

    def fake_docwindow(
        master, title, md, copy_text=None, hint=None, image_path=None,
        on_image_fix=None, on_website_fix=None,
    ):
        captured["on_image_fix"] = on_image_fix
        captured["on_website_fix"] = on_website_fix

    monkeypatch.setattr(gui, "DocWindow", fake_docwindow)
    panel._on_activate(None)

    assert captured["on_image_fix"] is not None
    assert captured["on_website_fix"] is not None  # resolved via drop_and_site_for


def _fixed_builder():
    """A REAL PainterGui._build_fix_workers bound to a minimal fake —
    used by the _show_check/_on_activate wiring tests above so they
    exercise the ACTUAL builder (Rule #5 proof: both call sites reach
    the identical function), not a stand-in."""
    fake = _FakeGuiForBuild()
    return lambda rel, out_base, defects, raw, jobtemp_slot=None: (
        gui.PainterGui._build_fix_workers(
            fake, rel, out_base, defects, raw, jobtemp_slot,
        )
    )
