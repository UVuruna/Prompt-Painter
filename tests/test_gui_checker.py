"""Checker AI — parallel per-item check (GUI rework Phase 16, owner
2026-07-21, UV/prompt.txt item 1: "dok generise sledecu sliku
paralelno ona koja je generisana cek jer provjeri ... ako je ukljucen
samo cek jer onda samo dobije pored slike i riport"). Four halves,
matching gui.py's own "pure helpers get pytest, real Tk/UI wiring gets
a screenshot" split (___tests.md):

* ``AgentPanel``'s new ``checker_var`` — a real (withdrawn) Tk root,
  the SAME ``make_panel``/``root`` convention every other GUI-phase
  test file already uses: default OFF, in ``_PERSIST``/``_vars()``,
  round-trips through ``get_settings``/``apply_settings`` (a missing
  key on an old settings.json keeps the default, like every other
  field).
* The SHARED module-level report helpers ``ai_check_tag`` (pure) and
  ``ai_check_image_file`` (promoted from ``AiCheckPanel``'s own
  private ``_file_for``) plus a Rule #5 proof that ``AiCheckPanel``'s
  double-click viewer and ``DashPanel``'s new 'Check…' viewer render
  the IDENTICAL report for the identical checked image (both ultimately
  call the SAME ``ai_check_doc_md``/``ai_check_image_file``).
* ``DashPanel``'s new check-status column: ``item_checking``/
  ``item_checked`` handling (the "checking…"/"OK"/"flagged N"/"error"
  text + the shared CHANGED/SKIP tag), ``_check_results``' lifetime
  (survives a ``sheet_start`` new-collection reset, unlike
  ``_child_ids`` — cleared only by ``reset()``, mirroring
  ``_node_info``), and ``_show_check`` (the three-state button: no row
  selected / no result yet / the happy path opening a real DocWindow —
  monkeypatched, never a real Toplevel, same convention
  test_gui_pipeline.py's own ``_show_steps`` tests use).
* ``PainterGui._maybe_spawn_checker``/``_run_checker_one`` — the
  engine side, run for REAL through a small duck-typed ``FakeGui``
  (``.agents``/``.panels``/``._q``, the same minimal-surface
  convention test_gui_tool_panels.py's own ``_FakeGuiForJob`` uses)
  carrying a REAL ``DashPanel``: checker OFF spawns nothing (proven
  deterministically — the method returns before touching the queue or
  starting any thread); checker ON applies the "checking…" marker
  SYNCHRONOUSLY then the (mocked, no network/API quota spent)
  background thread posts ``item_checked`` back onto the queue,
  awaited with a bounded ``Queue.get(timeout=...)`` — never a sleep
  loop; a non-site key and a panel with no ``out_base`` yet are both
  no-ops; ``_dispatch`` itself is proven to route ``item_progress``
  (and ONLY that event type) through the spawn. ``_run_checker_one``'s
  own outer safety net (anything OTHER than the ``AiError``/``NoKey``
  ``ai.check_one_image`` already turns into a graceful 'error' result)
  is proven by mocking ``check_one_image`` to RAISE directly — the
  posted event is still a loud-but-non-fatal 'error', never an
  unhandled thread exception.
"""

from __future__ import annotations

import queue
from pathlib import Path
from types import SimpleNamespace

import pytest
from PIL import Image

import gui

# ---------------------------------------------------------------------
# Shared helpers (mirrors test_gui_pipeline.py's/test_gui_tool_panels.py's
# own make_panel/make_png/make_progress_event conventions)
# ---------------------------------------------------------------------


@pytest.fixture
def root(tk_root):
    return tk_root


def make_panel(root, site: str = "gemini") -> gui.AgentPanel:
    """A bare AgentPanel, parented directly on the shared root (never
    packed/mapped), no-op callbacks — never a full PainterGui."""
    return gui.AgentPanel(
        root, site,
        on_start=lambda *_a: None, on_stop=lambda *_a: None,
        on_pause=lambda *_a: None,
    )


def make_png(path: Path, width: int = 10, height: int = 10) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    Image.new("RGBA", (width, height)).save(path, "PNG")


def make_progress_event(drop: str, size: int) -> dict:
    """The minimal item_progress payload DashPanel.handle needs to add
    one image row — mirrors runner.py's own emitted shape (identical to
    test_gui_pipeline.py's own helper of the same name)."""
    return {
        "type": "item_progress", "idx": 1, "of": 1, "title": drop,
        "drop_path": drop, "gen_s": 5.0, "orig_res": "10x10",
        "final_res": "10x10", "size": size, "actions": "", "retried": False,
    }


def _fake_check(kind: str, defects=(), raw: str = "OK", time_s: float = 0.05):
    """A mocked ``ai.check_one_image`` returning a fixed result — the
    SAME dict shape the real function returns, so both
    ``_run_checker_one`` and ``DashPanel.handle`` see production data."""

    def _check(src, out_base, instructions, *, log=print, **_kw):
        return {
            "rel": gui.PurePosixPath(src.name).as_posix(), "kind": kind,
            "defects": list(defects), "raw": raw, "time": time_s,
        }

    return _check


# ---------------------------------------------------------------------
# AgentPanel.checker_var — default, persistence round-trip
# ---------------------------------------------------------------------


def test_checker_var_defaults_false(root):
    panel = make_panel(root)
    assert panel.checker_var.get() is False


def test_checker_is_in_persist_and_vars(root):
    panel = make_panel(root)
    assert "checker" in panel._PERSIST
    assert panel._vars()["checker"] is panel.checker_var


def test_get_settings_round_trips_checker_true(root):
    panel = make_panel(root)
    panel.checker_var.set(True)
    stored = panel.get_settings()
    assert stored["checker"] is True

    fresh = make_panel(root)
    assert fresh.checker_var.get() is False  # a fresh panel still defaults OFF
    fresh.apply_settings(stored)
    assert fresh.checker_var.get() is True


def test_apply_settings_missing_checker_key_keeps_the_default(root):
    """An old settings.json predating Phase 16 has no 'checker' key at
    all — the generic _PERSIST loop's "missing key keeps the current
    default" contract must leave it OFF, same as every other field."""
    panel = make_panel(root)
    panel.apply_settings({"background": "white"})  # no 'checker' key
    assert panel.checker_var.get() is False


# ---------------------------------------------------------------------
# Shared module-level report helpers (Rule #5)
# ---------------------------------------------------------------------


def test_ai_check_tag_flagged_is_changed_others_are_skip():
    assert gui.ai_check_tag("flagged") == gui.TOOL_CHANGED_TAG
    assert gui.ai_check_tag("ok") == gui.TOOL_SKIP_TAG
    assert gui.ai_check_tag("error") == gui.TOOL_SKIP_TAG


def test_ai_check_image_file_relative_key_joins_out_base(tmp_path):
    out_base = tmp_path / "out"
    assert (
        gui.ai_check_image_file("a/b/c.png", out_base)
        == out_base / "a" / "b" / "c.png"
    )


def test_ai_check_image_file_absolute_key_returned_as_is(tmp_path):
    absolute = (tmp_path / "elsewhere" / "c.png").resolve()
    assert (
        gui.ai_check_image_file(str(absolute), tmp_path / "out") == absolute
    )


def test_shared_report_helper_identical_output_from_both_panels(
    root, tmp_path, monkeypatch,
):
    """The core Rule #5 proof this phase adds: AiCheckPanel's own
    double-click viewer and DashPanel's NEW 'Check…' viewer both
    resolve through the SAME ai_check_doc_md/ai_check_image_file
    module-level functions — captured by monkeypatching DocWindow and
    comparing what each panel hands it for the IDENTICAL
    (rel, defects, raw) triple."""
    out_base = tmp_path / "out"
    rel = "emblem/mood/Glory_gem.png"
    live = out_base / rel
    make_png(live)
    defects = ["subject cropped at the shoulder"]
    raw = "DEFECTS:\n- subject cropped at the shoulder"

    captured: list[dict] = []

    def fake_docwindow(
        master, title, md, copy_text=None, hint=None, image_path=None,
        on_image_fix=None, on_website_fix=None,
    ):
        captured.append(
            {"title": title, "md": md, "image_path": image_path}
        )

    monkeypatch.setattr(gui, "DocWindow", fake_docwindow)

    # AiCheckPanel's own (Phase 15) path
    ai_panel = gui.AiCheckPanel(root)
    ai_panel.out_base = out_base
    ai_panel.handle({
        "type": "item_flagged", "rel": rel, "defects": defects, "raw": raw,
        "time": 0.5,
    })
    row = ai_panel._image_rows[rel]
    ai_panel.tree.selection_set(row)
    ai_panel.tree.focus(row)
    ai_panel._on_activate(None)

    # DashPanel's own (Phase 16) path
    drop = "assets/emblem/mood/Glory.png"
    assert gui.dest_for(drop, "gemini") == rel  # sanity: same file
    dash = gui.DashPanel(root, "gemini")
    dash.out_base = out_base
    dash.handle(make_progress_event(drop, live.stat().st_size))
    dash.handle({
        "type": "item_checked", "drop_path": drop, "kind": "flagged",
        "defects": defects, "raw": raw, "rel": rel, "time": 0.5,
    })
    drow = dash._child_ids[drop]
    dash.tree.selection_set(drow)
    dash.tree.focus(drow)
    dash._show_check()

    assert len(captured) == 2
    assert captured[0]["md"] == captured[1]["md"]
    assert captured[0]["image_path"] == captured[1]["image_path"] == live


# ---------------------------------------------------------------------
# DashPanel — the check-status column (item_checking / item_checked)
# ---------------------------------------------------------------------


def test_dash_panel_item_checking_sets_the_marker(root, tmp_path):
    drop = "assets/emblem/Glory.png"
    panel = gui.DashPanel(root, "gemini")
    panel.out_base = tmp_path
    panel.handle(make_progress_event(drop, 100))
    row = panel._child_ids[drop]
    assert panel.tree.set(row, "check") == ""

    panel.handle({"type": "item_checking", "drop_path": drop})
    assert panel.tree.set(row, "check") == "checking…"


def test_dash_panel_item_checked_ok(root, tmp_path):
    drop = "assets/emblem/Glory.png"
    panel = gui.DashPanel(root, "gemini")
    panel.out_base = tmp_path
    panel.handle(make_progress_event(drop, 100))
    row = panel._child_ids[drop]

    panel.handle({
        "type": "item_checked", "drop_path": drop, "kind": "ok",
        "defects": [], "raw": "OK", "rel": "r", "time": 0.1,
    })
    assert panel.tree.set(row, "check") == "OK"
    assert gui.TOOL_SKIP_TAG in panel.tree.item(row, "tags")
    assert panel._check_results[drop]["kind"] == "ok"


def test_dash_panel_item_checked_flagged(root, tmp_path):
    drop = "assets/emblem/Glory.png"
    panel = gui.DashPanel(root, "gemini")
    panel.out_base = tmp_path
    panel.handle(make_progress_event(drop, 100))
    row = panel._child_ids[drop]

    panel.handle({
        "type": "item_checked", "drop_path": drop, "kind": "flagged",
        "defects": ["reflection visible", "off-centre"], "raw": "DEFECTS: ...",
        "rel": "r", "time": 0.2,
    })
    assert panel.tree.set(row, "check") == "flagged 2"
    assert gui.TOOL_CHANGED_TAG in panel.tree.item(row, "tags")


def test_dash_panel_item_checked_error_is_shown_non_fatally(root, tmp_path):
    """The graceful ai.NoKey/AiError path: check_one_image already
    turns it into an 'error' result dict (never raises) — the row must
    show it plainly, never raise, never touch anything else on the
    panel."""
    drop = "assets/emblem/Glory.png"
    panel = gui.DashPanel(root, "gemini")
    panel.out_base = tmp_path
    panel.handle(make_progress_event(drop, 100))
    row = panel._child_ids[drop]

    panel.handle({
        "type": "item_checked", "drop_path": drop, "kind": "error",
        "defects": [], "raw": "no Gemini API key in settings.json ...",
        "rel": "r", "time": 0.0,
    })
    assert panel.tree.set(row, "check") == "error"
    assert gui.TOOL_SKIP_TAG in panel.tree.item(row, "tags")


def test_dash_panel_item_checked_for_an_unknown_row_does_not_raise(
    root, tmp_path,
):
    """A late item_checked whose row is gone (reset() ran, or it was
    never inserted at all) must silently no-op the tree update — same
    tolerant '.get() may be None' pattern item_done already uses."""
    panel = gui.DashPanel(root, "gemini")
    panel.out_base = tmp_path
    panel.handle({
        "type": "item_checked", "drop_path": "never/inserted.png",
        "kind": "ok", "defects": [], "raw": "OK", "rel": "r", "time": 0.1,
    })  # must not raise
    assert "never/inserted.png" in panel._check_results


def test_dash_panel_check_results_persist_across_a_new_collection(
    root, tmp_path,
):
    """_check_results is scoped like _node_info (the WHOLE run), NOT
    like _child_ids (reset every sheet_start) — a 'Check…' click must
    still find an OLDER collection's result even after the run has
    moved on."""
    drop = "assets/emblem/Glory.png"
    panel = gui.DashPanel(root, "gemini")
    panel.out_base = tmp_path
    panel.handle(make_progress_event(drop, 100))
    panel.handle({
        "type": "item_checked", "drop_path": drop, "kind": "ok",
        "defects": [], "raw": "OK", "rel": "r", "time": 0.1,
    })
    assert drop in panel._check_results

    panel.handle({"type": "sheet_start", "sheet": "Next Theme", "pending": 1})
    assert drop not in panel._child_ids  # rotated away, as _new_theme always has
    assert drop in panel._check_results  # but the result itself survives


def test_dash_panel_reset_clears_check_results(root, tmp_path):
    drop = "assets/emblem/Glory.png"
    panel = gui.DashPanel(root, "gemini")
    panel.out_base = tmp_path
    panel.handle(make_progress_event(drop, 100))
    panel.handle({
        "type": "item_checked", "drop_path": drop, "kind": "ok",
        "defects": [], "raw": "OK", "rel": "r", "time": 0.1,
    })
    assert panel._check_results

    panel.reset(active=True, task_total=1, task_themes=1)
    assert panel._check_results == {}


# ---------------------------------------------------------------------
# DashPanel._show_check — the 'Check…' button
# ---------------------------------------------------------------------


def test_dash_panel_show_check_with_no_row_selected_shows_info(
    root, monkeypatch,
):
    panel = gui.DashPanel(root, "gemini")
    calls = []
    monkeypatch.setattr(
        gui.messagebox, "showinfo", lambda *a, **k: calls.append(a)
    )
    panel._show_check()  # nothing focused in a brand-new tree
    assert len(calls) == 1


def test_dash_panel_show_check_with_no_result_yet_shows_info(
    root, tmp_path, monkeypatch,
):
    drop = "assets/emblem/Glory.png"
    panel = gui.DashPanel(root, "gemini")
    panel.out_base = tmp_path
    panel.handle(make_progress_event(drop, 100))
    row = panel._child_ids[drop]
    panel.tree.selection_set(row)
    panel.tree.focus(row)

    calls = []
    monkeypatch.setattr(
        gui.messagebox, "showinfo", lambda *a, **k: calls.append(a)
    )
    panel._show_check()  # item_checked never arrived for this row
    assert len(calls) == 1


def test_dash_panel_show_check_opens_doc_window_with_the_report(
    root, tmp_path, monkeypatch,
):
    out_base = tmp_path / "out"
    drop = "assets/emblem/Glory.png"
    rel = gui.dest_for(drop, "gemini")
    live = out_base / rel
    make_png(live)

    panel = gui.DashPanel(root, "gemini")
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
        captured.update(
            master=master, title=title, md=md, copy_text=copy_text,
            hint=hint, image_path=image_path,
        )

    monkeypatch.setattr(gui, "DocWindow", fake_docwindow)
    panel._show_check()

    assert captured["title"] == rel
    assert "subject cropped" in captured["md"]
    assert captured["image_path"] == live


# ---------------------------------------------------------------------
# PainterGui._maybe_spawn_checker / _run_checker_one — the engine side
# ---------------------------------------------------------------------


class _FakeGuiForChecker:
    """Just enough surface for the UNBOUND _maybe_spawn_checker/
    _run_checker_one/_dispatch to run for real: a genuine queue.Queue
    (so their emit/log closures have somewhere to land) plus
    .agents/.panels — the same minimal-surface FakeGui convention
    every other GUI-phase test file already uses (never a full
    PainterGui). _run_checker_one/_maybe_spawn_checker are ALIASED
    onto the class (the SAME test_gui_running_view.py convention: its
    own docstring explains why) so ``self._run_checker_one(...)``
    inside the UNBOUND ``_maybe_spawn_checker``/``_dispatch`` resolves
    even though ``self`` is this fake, not a real PainterGui."""

    _maybe_spawn_checker = gui.PainterGui._maybe_spawn_checker
    _run_checker_one = gui.PainterGui._run_checker_one

    def __init__(self, agents: dict, panels: dict):
        self.agents = agents
        self.panels = panels
        self._q: "queue.Queue" = queue.Queue()


def test_maybe_spawn_checker_off_does_nothing(root, tmp_path):
    dash = gui.DashPanel(root, "gemini")
    dash.out_base = tmp_path
    agent = make_panel(root, "gemini")
    assert agent.checker_var.get() is False  # the default

    fake = _FakeGuiForChecker({"gemini": agent}, {"gemini": dash})
    gui.PainterGui._maybe_spawn_checker(
        fake, "gemini", {"type": "item_progress", "drop_path": "assets/x/a.png"},
    )

    # a synchronous no-op: nothing was ever spawned, so nothing can
    # ever land on the queue — no sleep/poll needed to prove it
    assert fake._q.empty()


def test_maybe_spawn_checker_ignores_non_site_keys(root):
    """'bg'/'crop'/etc. never have an AgentPanel — agents.get returns
    None regardless of what (if anything) .panels holds for that key."""
    fake = _FakeGuiForChecker({"gemini": make_panel(root, "gemini")}, {})
    gui.PainterGui._maybe_spawn_checker(
        fake, "bg", {"type": "item_progress", "drop_path": "x"},
    )
    assert fake._q.empty()


def test_maybe_spawn_checker_noop_without_out_base(root):
    """checker ON but the panel never got its out_base yet (Start
    sets both together in production — see _start_site) — must not
    crash trying to build a path from None."""
    agent = make_panel(root, "gemini")
    agent.checker_var.set(True)
    dash = gui.DashPanel(root, "gemini")  # out_base still None

    fake = _FakeGuiForChecker({"gemini": agent}, {"gemini": dash})
    gui.PainterGui._maybe_spawn_checker(
        fake, "gemini", {"type": "item_progress", "drop_path": "assets/x/a.png"},
    )
    assert fake._q.empty()


def test_maybe_spawn_checker_on_marks_checking_then_completes(
    root, tmp_path, monkeypatch,
):
    """The core Phase-16 promise: checker ON on item_progress (a) marks
    the row 'checking…' SYNCHRONOUSLY, before this call even returns,
    and (b) the background thread (mocked ai.check_one_image — no
    network, no API quota spent) posts item_checked back onto the
    SAME queue shortly after, which — applied exactly like _dispatch
    would — flips the row to its final status."""
    import painter.ai as ai_module

    monkeypatch.setattr(ai_module, "check_one_image", _fake_check("ok"))

    out_base = tmp_path / "out"
    drop = "assets/emblem/Glory.png"
    rel = gui.dest_for(drop, "gemini")
    live = out_base / rel
    make_png(live)

    dash = gui.DashPanel(root, "gemini")
    dash.out_base = out_base
    dash.handle(make_progress_event(drop, live.stat().st_size))
    row = dash._child_ids[drop]

    agent = make_panel(root, "gemini")
    agent.checker_var.set(True)

    fake = _FakeGuiForChecker({"gemini": agent}, {"gemini": dash})
    gui.PainterGui._maybe_spawn_checker(
        fake, "gemini", {"type": "item_progress", "drop_path": drop},
    )

    # (a) synchronous — true the instant the call above returns
    assert dash.tree.set(row, "check") == "checking…"

    # (b) the daemon thread's own event — bounded wait, never a sleep loop
    msg = fake._q.get(timeout=5)
    assert msg[0] == "__event__"
    assert msg[1] == "gemini"
    assert msg[2]["type"] == "item_checked"
    assert msg[2]["kind"] == "ok"
    assert msg[2]["drop_path"] == drop

    dash.handle(msg[2])
    assert dash.tree.set(row, "check") == "OK"


def test_maybe_spawn_checker_flagged_result_reaches_the_row(
    root, tmp_path, monkeypatch,
):
    import painter.ai as ai_module

    monkeypatch.setattr(
        ai_module, "check_one_image",
        _fake_check("flagged", defects=["reflection visible"]),
    )

    out_base = tmp_path / "out"
    drop = "assets/emblem/Glory.png"
    live = out_base / gui.dest_for(drop, "gemini")
    make_png(live)

    dash = gui.DashPanel(root, "gemini")
    dash.out_base = out_base
    dash.handle(make_progress_event(drop, live.stat().st_size))
    row = dash._child_ids[drop]

    agent = make_panel(root, "gemini")
    agent.checker_var.set(True)
    fake = _FakeGuiForChecker({"gemini": agent}, {"gemini": dash})
    gui.PainterGui._maybe_spawn_checker(
        fake, "gemini", {"type": "item_progress", "drop_path": drop},
    )

    msg = fake._q.get(timeout=5)
    dash.handle(msg[2])
    assert dash.tree.set(row, "check") == "flagged 1"


def test_maybe_spawn_checker_error_result_is_non_fatal(
    root, tmp_path, monkeypatch,
):
    """The realistic ai.NoKey path: check_one_image itself already
    turns it into an 'error' dict rather than raising — proving that
    shape reaches the row untouched, no exception anywhere."""
    import painter.ai as ai_module

    monkeypatch.setattr(
        ai_module, "check_one_image",
        _fake_check("error", raw="no Gemini API key in settings.json"),
    )

    out_base = tmp_path / "out"
    drop = "assets/emblem/Glory.png"
    live = out_base / gui.dest_for(drop, "gemini")
    make_png(live)

    dash = gui.DashPanel(root, "gemini")
    dash.out_base = out_base
    dash.handle(make_progress_event(drop, live.stat().st_size))
    row = dash._child_ids[drop]

    agent = make_panel(root, "gemini")
    agent.checker_var.set(True)
    fake = _FakeGuiForChecker({"gemini": agent}, {"gemini": dash})
    gui.PainterGui._maybe_spawn_checker(
        fake, "gemini", {"type": "item_progress", "drop_path": drop},
    )

    msg = fake._q.get(timeout=5)
    assert msg[2]["kind"] == "error"
    dash.handle(msg[2])
    assert dash.tree.set(row, "check") == "error"


def test_run_checker_one_wraps_a_raised_exception_as_a_graceful_error(
    tmp_path, monkeypatch,
):
    """_run_checker_one's OWN outer safety net (Rule #1): even if
    something OTHER than the AiError/NoKey check_one_image already
    handles internally somehow escapes (a file vanishing mid-race, a
    flag-file disk-full write), the checker thread must still post a
    loud-but-non-fatal item_checked 'error' — never an unhandled
    thread exception, never silence."""
    import painter.ai as ai_module

    def _raises(src, out_base, instructions, *, log=print, **_kw):
        raise OSError("file vanished")

    monkeypatch.setattr(ai_module, "check_one_image", _raises)

    fake = SimpleNamespace(_q=queue.Queue())
    out_base = tmp_path / "out"
    src = out_base / "gemini" / "img.png"
    gui.PainterGui._run_checker_one(
        fake, "gemini", "assets/x/img.png", src, out_base,
    )

    # drain everything — a plain log string (the FAIL line) precedes the
    # __event__ tuple, same "text lines + events" split every other
    # worker method in this suite posts (mirrors test_gui_tool_panels.py's
    # own _drain helper)
    msgs = []
    while True:
        try:
            msgs.append(fake._q.get_nowait())
        except queue.Empty:
            break
    text_lines = [m for m in msgs if isinstance(m, str)]
    events = [m for m in msgs if isinstance(m, tuple) and m[0] == "__event__"]
    assert any("file vanished" in line for line in text_lines)
    assert len(events) == 1
    msg = events[0]
    assert msg[1] == "gemini"
    event = msg[2]
    assert event["type"] == "item_checked"
    assert event["kind"] == "error"
    assert event["drop_path"] == "assets/x/img.png"
    assert "file vanished" in event["raw"]


# ---------------------------------------------------------------------
# PainterGui._dispatch — the wiring itself (item_progress ONLY)
# ---------------------------------------------------------------------


def test_dispatch_routes_item_progress_into_the_checker(
    root, tmp_path, monkeypatch,
):
    import painter.ai as ai_module

    monkeypatch.setattr(ai_module, "check_one_image", _fake_check("ok"))

    out_base = tmp_path / "out"
    drop = "assets/emblem/Glory.png"
    live = out_base / gui.dest_for(drop, "gemini")
    make_png(live)

    dash = gui.DashPanel(root, "gemini")
    dash.out_base = out_base
    agent = make_panel(root, "gemini")
    agent.checker_var.set(True)

    fake = _FakeGuiForChecker({"gemini": agent}, {"gemini": dash})
    event = make_progress_event(drop, live.stat().st_size)
    gui.PainterGui._dispatch(fake, ("__event__", "gemini", event))

    row = dash._child_ids[drop]
    assert dash.tree.set(row, "check") == "checking…"
    msg = fake._q.get(timeout=5)
    assert msg[2]["type"] == "item_checked"


def test_dispatch_does_not_spawn_checker_for_item_done(root, tmp_path):
    """item_done (our-time known, no NEW image saved) must NEVER spawn
    a second check for the same image — only item_progress does."""
    dash = gui.DashPanel(root, "gemini")
    dash.out_base = tmp_path
    agent = make_panel(root, "gemini")
    agent.checker_var.set(True)

    fake = _FakeGuiForChecker({"gemini": agent}, {"gemini": dash})
    gui.PainterGui._dispatch(
        fake, (
            "__event__", "gemini",
            {
                "type": "item_done", "drop_path": "assets/x/a.png",
                "gen_s": 1.0, "over_s": 1.0,
            },
        ),
    )
    assert fake._q.empty()  # no thread was ever started


def test_dispatch_does_not_spawn_checker_for_tool_events(root, tmp_path):
    """A tool panel ('bg') is not in .agents at all — _dispatch must
    not blow up looking up its checker switch."""
    tool_panel = gui.ToolPanel(root, "bg")
    fake = _FakeGuiForChecker({"gemini": make_panel(root, "gemini")}, {"bg": tool_panel})
    gui.PainterGui._dispatch(
        fake, ("__event__", "bg", {"type": "item_progress", "rel": "a.png"}),
    )
    assert fake._q.empty()
