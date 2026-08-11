"""The checker's GIVE-UP streak (owner 2026-08-11).

Split from ``test_gui_checker.py`` under THE STRUCTURE LAW — that file
covers what ONE check does; this one covers when the checker stops
checking AT ALL for the rest of a run.

The checker never could stop a RUN: it lives on its own daemon thread
behind a blanket except (``_run_checker_one``). But when the cause is
STANDING rather than per-image — an exhausted API quota, a missing key
— every later image still spent a call to fail identically: the
2026-08-11 live log carries ~80 identical "free tier has zero quota"
lines, one per saved image, none saying anything the first had not.
Generation is never affected by any of this.
"""

from __future__ import annotations

import queue
from types import SimpleNamespace

import gui


# --- the give-up streak (owner 2026-08-11) ----------------------------
# The checker never could stop a RUN, but a standing failure (exhausted
# API quota, missing key) used to burn one call per saved image forever
# — ~80 identical "free tier has zero quota" lines in the 2026-08-11 log.


class _StreakGui:
    """Minimal surface for the streak bookkeeping alone."""

    _note_checker_result = gui.PainterGui._note_checker_result
    _maybe_spawn_checker = gui.PainterGui._maybe_spawn_checker

    def __init__(self):
        self._q = queue.Queue()
        self.agents: dict = {}
        self.panels: dict = {}


def _drain(q):
    out = []
    while not q.empty():
        out.append(q.get_nowait())
    return out


def test_checker_gives_up_after_consecutive_errors():
    """CHECKER_ERROR_GIVE_UP failures in a row stop the checking for the
    rest of the run — ONE loud line and one item_checked_stopped event,
    not one more per image."""
    from painter.config import CHECKER_ERROR_GIVE_UP

    fake = _StreakGui()
    logs: list[str] = []
    for _ in range(CHECKER_ERROR_GIVE_UP + 3):
        fake._note_checker_result("gemini", "error", "zero quota", logs.append)

    assert "gemini" in fake._checker_stopped
    # said ONCE, however many failures followed
    assert len([m for m in logs if "STOPPED" in m]) == 1
    events = [
        ev for _tag, _key, ev in _drain(fake._q)
        if ev.get("type") == "item_checked_stopped"
    ]
    assert len(events) == 1


def test_a_good_check_resets_the_streak():
    """A run that recovers keeps checking — the streak counts only
    CONSECUTIVE failures."""
    from painter.config import CHECKER_ERROR_GIVE_UP

    fake = _StreakGui()
    for _ in range(CHECKER_ERROR_GIVE_UP - 1):
        fake._note_checker_result("gemini", "error", "boom", lambda _m: None)
    fake._note_checker_result("gemini", "ok", "", lambda _m: None)
    for _ in range(CHECKER_ERROR_GIVE_UP - 1):
        fake._note_checker_result("gemini", "error", "boom", lambda _m: None)

    assert not getattr(fake, "_checker_stopped", set())


def test_a_stopped_checker_spawns_nothing_more(tmp_path):
    """The point of giving up: no further vision call is even started.
    Generation is untouched — this method only ever declines to CHECK."""
    agent = SimpleNamespace(
        checker_var=SimpleNamespace(get=lambda: True),
        checker_prompt_var=SimpleNamespace(get=lambda: False),
    )
    dash = SimpleNamespace(out_base=tmp_path, handle=lambda ev: None)
    fake = _StreakGui()
    fake.agents = {"gemini": agent}
    fake.panels = {"gemini": dash}
    fake._checker_stopped = {"gemini"}
    fake._checker_errors = {}

    fake._maybe_spawn_checker(
        "gemini",
        {"type": "item_progress", "drop_path": "a/b.png", "rel": "a/b.png"},
    )

    assert _drain(fake._q) == []
