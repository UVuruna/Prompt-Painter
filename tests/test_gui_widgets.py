"""The shared themed-widget primitives in ``gui/widgets.py`` that carry
real BEHAVIOUR of their own (owner's UI-SKETCH, 2026-07-29) — as
opposed to the file's many pure factory helpers (``rounded_button`` et
al.), which are colour/geometry plumbing verified by screenshot.

Two halves, matching the suite's own "pure helpers get pytest, real
Tk/UI wiring gets a screenshot" split (___tests.md):

* ``ExpandableSwitch`` — the switch whose fine-tune lives in an
  indented sub-panel: turning it ON auto-expands, the ▸/▾ caret folds
  by hand, turning it OFF hides the sub-panel entirely. Its host
  (``AgentPanel``) pins WHICH switch owns which sub-panel in
  test_gui_agent_visibility.py; this file pins the MECHANICS, once,
  where they live (Rule #5 — one primitive, one test home).
* ``ExpandableSection`` — the switch-LESS variant (the Pacing row):
  a clickable label + caret over the same indented sub-panel.

Both need a real (withdrawn) Tk root — the shared ``tk_root`` fixture,
same convention as every other gui_* test module. ``winfo_manager()``
is the visibility probe throughout (empty = unmanaged/pack_forget'd,
"pack" = packed): the shared root is withdrawn, so ``winfo_ismapped()``
is always False here.
"""

from __future__ import annotations

import tkinter as tk
from tkinter import ttk

import pytest

from gui.widgets import ExpandableSection, ExpandableSwitch, quiet_restore


@pytest.fixture
def root(tk_root):
    return tk_root


def make_switch(root, on: bool = False, build_sub=None, **kwargs):
    """One ExpandableSwitch on a fresh parent frame, with its variable
    returned beside it (the caller flips it to simulate a click)."""
    var = tk.BooleanVar(value=on)
    built: list[ttk.Frame] = []

    def default_build(box):
        built.append(box)
        ttk.Label(box, text="fine-tune").pack()

    switch = ExpandableSwitch(
        ttk.Frame(root), "Upscale", var,
        build_sub=build_sub or default_build, **kwargs,
    )
    switch.pack(fill="x")
    return switch, var, built


# ---------------------------------------------------------------------
# ExpandableSwitch — the OFF/ON/auto-expand/caret mechanics
# ---------------------------------------------------------------------


def test_off_switch_starts_with_no_sub_and_no_caret(root):
    switch, _var, _built = make_switch(root, on=False)
    assert switch.sub.winfo_manager() == ""
    assert switch._caret.cget("text") == ""  # a caret would promise a sub


def test_an_already_on_switch_still_starts_collapsed(root):
    """A RESTORED setting (settings.json applied at build time) must
    open the panel COMPACT — the auto-expand is a live-click reaction,
    never a construction-time one."""
    switch, _var, _built = make_switch(root, on=True)
    assert switch.sub.winfo_manager() == ""
    assert switch._caret.cget("text") == "▸"  # collapsed caret


def test_turning_the_switch_on_auto_expands_once(root):
    switch, var, _built = make_switch(root, on=False)
    var.set(True)
    assert switch.sub.winfo_manager() == "pack"
    assert switch._caret.cget("text") == "▾"


def test_turning_the_switch_off_hides_the_sub_and_the_caret(root):
    switch, var, _built = make_switch(root, on=True)
    switch.toggle(open_=True)
    var.set(False)
    assert switch.sub.winfo_manager() == ""
    assert switch._caret.cget("text") == ""


def test_caret_folds_and_unfolds_while_the_switch_stays_on(root):
    switch, var, _built = make_switch(root, on=False)
    var.set(True)                     # auto-expanded
    switch.toggle()                   # the caret click: fold
    assert switch.sub.winfo_manager() == ""
    assert var.get() is True          # folding NEVER touches the switch
    switch.toggle()                   # unfold
    assert switch.sub.winfo_manager() == "pack"


def test_expanding_while_the_switch_is_off_is_refused(root):
    """The sub-panel exists only while the switch is ON — a stray
    toggle() (a caret click racing a turn-off) must not resurrect it."""
    switch, _var, _built = make_switch(root, on=False)
    switch.toggle(open_=True)
    assert switch.sub.winfo_manager() == ""


def test_re_expanding_an_open_sub_is_a_no_op(root):
    calls: list[int] = []
    switch, var, _built = make_switch(
        root, on=False, on_layout_change=lambda: calls.append(1)
    )
    var.set(True)
    assert calls == [1]
    switch.toggle(open_=True)  # already open
    assert calls == [1]        # no second layout call, no re-pack


def test_turning_an_already_collapsed_switch_off_never_calls_layout(root):
    """OFF while already collapsed changes no geometry — only the caret
    text — so the (expensive) ScrollFrame refresh must not fire."""
    calls: list[int] = []
    switch, var, _built = make_switch(
        root, on=True, on_layout_change=lambda: calls.append(1)
    )
    var.set(False)
    assert calls == []
    assert switch._caret.cget("text") == ""


def test_switch_without_a_sub_is_a_plain_switch(root):
    var = tk.BooleanVar(value=False)
    switch = ExpandableSwitch(ttk.Frame(root), "Crop", var, build_sub=None)
    switch.toggle(open_=True)  # must not raise
    assert switch.sub.winfo_manager() == ""
    assert switch._caret.cget("text") == ""
    var.set(True)
    assert switch.sub.winfo_manager() == ""


# --- lazy vs eager sub-panel construction ------------------------------


def test_lazy_sub_is_built_on_the_first_expand_only(root):
    switch, var, built = make_switch(root, on=False)
    assert built == []          # nothing built yet
    var.set(True)
    assert len(built) == 1      # built on the first reveal
    switch.toggle()             # fold
    switch.toggle()             # unfold again
    assert len(built) == 1      # never rebuilt


def test_eager_sub_is_built_at_construction(root):
    """``eager=True`` is for content whose STATE outlives its
    visibility (a FilterEditor's condition stack, a canvas two-way
    binding): built once at construction, expand/collapse only ever
    packs/unpacks it."""
    switch, var, built = make_switch(root, on=True, eager=True)
    assert len(built) == 1      # already built, still collapsed
    assert switch.sub.winfo_manager() == ""
    var.set(False)
    var.set(True)
    assert len(built) == 1


# --- quiet_restore: a settings restore never unfolds anything ---------


def test_quiet_restore_keeps_a_restored_on_switch_folded(root):
    """The defect this exists for (found on the live window): the app
    restores settings.json AFTER building the panel, and Tk cannot tell
    that .set() from a click — every ON switch used to open its
    fine-tune, so the panel came up as a wall of controls."""
    switch, var, _built = make_switch(root, on=False)
    with quiet_restore(switch):
        var.set(True)
    assert switch.sub.winfo_manager() == ""
    assert switch._caret.cget("text") == "▸"  # foldable, just not unfolded


def test_quiet_restore_still_hides_a_sub_whose_switch_is_restored_off(root):
    """Only the auto-EXPAND is suppressed — restoring OFF must never
    leave an orphan sub-panel packed under a dead switch."""
    switch, var, _built = make_switch(root, on=False)
    var.set(True)  # a real click: expanded
    with quiet_restore(switch):
        var.set(False)
    assert switch.sub.winfo_manager() == ""
    assert switch._caret.cget("text") == ""


def test_quiet_restore_is_released_after_the_block(root):
    switch, var, _built = make_switch(root, on=False)
    with quiet_restore(switch):
        var.set(True)
    var.set(False)
    var.set(True)  # a live click again — auto-expands as always
    assert switch.sub.winfo_manager() == "pack"


def test_quiet_restore_releases_even_when_the_block_raises(root):
    switch, var, _built = make_switch(root, on=False)
    with pytest.raises(ValueError):
        with quiet_restore(switch):
            raise ValueError("a corrupt settings value, say")
    assert switch.quiet is False


# ---------------------------------------------------------------------
# ExpandableSection — the switch-less variant (Pacing)
# ---------------------------------------------------------------------


def test_section_starts_collapsed_with_its_content_built(root):
    built: list[ttk.Frame] = []
    section = ExpandableSection(
        ttk.Frame(root), "Pacing", lambda box: built.append(box)
    )
    assert len(built) == 1  # eager by construction (plain fields, no lazy state)
    assert section.sub.winfo_manager() == ""
    assert section._head.cget("text") == "▸ Pacing"


def test_section_toggles_both_ways_and_reports_layout_changes(root):
    calls: list[str] = []
    section = ExpandableSection(
        ttk.Frame(root), "Pacing", lambda box: None,
        on_layout_change=lambda: calls.append("x"),
    )
    section.toggle()
    assert section.sub.winfo_manager() == "pack"
    assert section._head.cget("text") == "▾ Pacing"
    section.toggle()
    assert section.sub.winfo_manager() == ""
    assert section._head.cget("text") == "▸ Pacing"
    assert calls == ["x", "x"]


def test_section_re_toggling_the_same_state_is_a_no_op(root):
    calls: list[str] = []
    section = ExpandableSection(
        ttk.Frame(root), "Pacing", lambda box: None,
        on_layout_change=lambda: calls.append("x"),
    )
    section.toggle(open_=False)  # already collapsed
    assert calls == []


# --- FlowRow: the NEVER-CLIP primitive (owner 2026-08-03, slika 1) ----
# The owner's binding rule for the setup screen: an element may shrink
# or move to a new row, but "ni pod kojim uslovima ne smeš da sečeš
# elemente da oni izlaze iz vidokruga". These pin exactly that.


def _flow_with(root, widths, avail):
    """A FlowRow of fixed-width children, laid out for ``avail`` px."""
    from gui.widgets import FlowRow

    host = ttk.Frame(root, width=avail, height=200)
    host.pack_propagate(False)
    host.pack()
    flow = FlowRow(host, gap=0, row_gap=0)
    flow.pack(fill="x")
    for w in widths:
        flow.add(tk.Frame(flow, width=w, height=10))
    root.update_idletasks()
    flow.reflow(avail)  # withdrawn root: winfo_width stays 1, pass it
    return flow


def test_flow_row_wraps_instead_of_running_off_the_edge(root):
    flow = _flow_with(root, [100, 100, 100], avail=250)
    rows = [w.place_info()["y"] for w in flow._items]
    assert rows[0] == rows[1]      # two fit on the first row
    assert rows[2] != rows[0]      # the third WRAPS, never clipped
    for w in flow._items:
        assert int(w.place_info()["x"]) + int(w.winfo_reqwidth()) <= 250


def test_flow_row_never_truncates_an_oversized_element(root):
    """A child wider than the whole row keeps its FULL width on a row
    of its own — shrinking is the caller's job, cutting is nobody's."""
    flow = _flow_with(root, [60, 400], avail=200)
    assert int(flow._items[1].winfo_reqwidth()) == 400
    assert flow._items[1].place_info()["y"] != flow._items[0].place_info()["y"]


def test_flow_row_requests_room_for_its_widest_element(root):
    """The frame reports the widest child as its own requested width —
    that is the floor the window's computed minsize rests on."""
    flow = _flow_with(root, [60, 180, 90], avail=400)
    assert flow.winfo_reqwidth() >= 180


def test_flow_row_reflows_when_the_width_changes(root):
    flow = _flow_with(root, [100, 100], avail=250)
    assert flow._items[0].place_info()["y"] == flow._items[1].place_info()["y"]
    flow.reflow(150)
    assert flow._items[0].place_info()["y"] != flow._items[1].place_info()["y"]


def test_accordion_folds_the_previously_open_switch(root):
    from gui.widgets import ExpanderAccordion

    acc = ExpanderAccordion()
    host = ttk.Frame(root)
    a, _va, _ba = make_switch(
        root, on=True, build_sub=lambda box: None, accordion=acc,
        sub_host=host,
    )
    b, _vb, _bb = make_switch(
        root, on=True, build_sub=lambda box: None, accordion=acc,
        sub_host=host,
    )
    a.toggle(open_=True)
    b.toggle(open_=True)
    assert b.is_open
    assert not a.is_open
    assert a.sub.winfo_manager() == ""


def test_sub_host_opens_the_fine_tune_unindented(root):
    host = ttk.Frame(root)
    sw, _var, _built = make_switch(
        root, on=True, build_sub=lambda box: None, sub_host=host,
    )
    sw.toggle(open_=True)
    assert sw.sub.winfo_parent() == str(host)
    assert int(sw.sub.pack_info()["padx"]) == 0
