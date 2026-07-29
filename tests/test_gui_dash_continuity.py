"""F3 regression tests (owner 2026-07-29, REWORK.md) — dashboard
continuity + the live selection.

Root cause 5 pinned: Start used to wipe the whole DashPanel
(``reset()`` on every ``_start_site``, including the quota
auto-restart) — a mid-batch stop cost the entire visual history.
Now ``begin_run`` APPENDS (rows + counters survive) and the only
wipe is the explicit Clear button's ``clear()``.

Root cause 7 pinned (the ``_vN`` landmine, owner's C4): a selection
was a static snapshot — after a mid-run stop, still-ticked items that
had ALREADY saved came back as unwanted ``_vN`` redo versions. Now
``_dispatch`` unticks an item's selection var the moment its
``item_progress`` (file saved) arrives, so a restart re-submits only
the remainder.
"""

import queue
import tkinter as tk

import pytest

import gui


@pytest.fixture
def root(tk_root):
    return tk_root


def _progress_event(idx: int, drop: str) -> dict:
    return {
        "type": "item_progress",
        "idx": idx,
        "of": 2,
        "title": f"Item {idx}",
        "drop_path": drop,
        "rel": drop.removeprefix("assets/"),
        "gen_s": 40.0,
        "orig_res": "1024x1024",
        "final_res": "1000x1000",
        "size": 1_000_000,
        "actions": "",
        "retried": False,
    }


def _done_event(idx: int, drop: str) -> dict:
    ev = _progress_event(idx, drop)
    ev["type"] = "item_done"
    ev["over_s"] = 10.0
    return ev


def _feed_one_finished_item(dash, drop: str) -> None:
    dash.begin_run(task_total=1, task_themes=1)
    dash.handle({"type": "sheet_start", "sheet": "t.md", "pending": 1,
                 "total": 1})
    dash.handle(_progress_event(1, drop))
    dash.handle(_done_event(1, drop))
    dash.handle({"type": "sheet_done", "generated": 1})


def test_begin_run_keeps_rows_and_continues_counters(root):
    """A restart's begin_run APPENDS: the finished row and the done
    counter survive, and the new pending total stacks on top."""
    dash = gui.DashPanel(root, "gemini")
    _feed_one_finished_item(dash, "assets/a/One.png")
    assert dash.tree.get_children()  # the collection row exists
    assert dash._task_done == 1

    dash.begin_run(task_total=2, task_themes=1)  # the restart

    assert dash.tree.get_children()  # F3: nothing wiped
    assert dash._task_done == 1  # history continues
    assert dash._task_total == 3  # 1 done + 2 newly pending
    assert dash.task_prog_var.get().startswith("1 / 3")


def test_clear_wipes_everything_and_is_the_only_wipe(root):
    dash = gui.DashPanel(root, "gemini")
    _feed_one_finished_item(dash, "assets/a/One.png")

    dash.clear()

    assert not dash.tree.get_children()
    assert dash._task_done == 0
    assert dash.task_prog_var.get().startswith("0 / 0")


class _FakeGuiForDispatch:
    """Minimal surface for the UNBOUND ``_dispatch`` __event__ branch
    (same convention as every other GUI-phase test file): panels +
    _select_vars + no-op checker/fixer spawns."""

    _dispatch = gui.PainterGui._dispatch

    def __init__(self, panels: dict, select_vars: dict):
        self.panels = panels
        self._select_vars = select_vars
        self._q: "queue.Queue" = queue.Queue()

    def _maybe_spawn_checker(self, key, event):
        pass

    def _maybe_spawn_fixer(self, key, event):
        pass


def test_item_progress_unticks_the_saved_items_selection_var(root):
    """The _vN landmine fix: the saved item's tick clears itself; the
    other item's tick (and the other site's same drop) stay put."""
    dash = gui.DashPanel(root, "gemini")
    dash.begin_run(task_total=2, task_themes=1)
    dash.handle({"type": "sheet_start", "sheet": "t.md", "pending": 2,
                 "total": 2})
    saved = tk.BooleanVar(master=root, value=True)
    pending = tk.BooleanVar(master=root, value=True)
    other_site = tk.BooleanVar(master=root, value=True)
    fake = _FakeGuiForDispatch(
        {"gemini": dash},
        {
            ("gemini", "s.md", "assets/a/One.png"): saved,
            ("gemini", "s.md", "assets/a/Two.png"): pending,
            ("chatgpt", "s.md", "assets/a/One.png"): other_site,
        },
    )

    fake._dispatch(
        ("__event__", "gemini", _progress_event(1, "assets/a/One.png"))
    )

    assert saved.get() is False  # unticked the moment the file saved
    assert pending.get() is True
    assert other_site.get() is True
