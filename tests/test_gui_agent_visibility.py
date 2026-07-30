"""Website GEN settings-panel polish (GUI rework Phase 12, owner
2026-07-21, spec item 3A from UV/prompt.txt: "moze da se prikaze/sakrije
bilo koji tj da ostane samo jedan vidljiv (od GPT-Gemini)" / "FILTER za
Upscale se pali samo ako je UPSCALE stikliran"). Three halves, matching
gui.py's own "pure helpers get pytest, real Tk/UI wiring gets a
screenshot" split (___tests.md):

* ``gui._visible_agent_slots`` is the pure, Tk-free slot (row) resolver
  behind ``PainterGui._relayout_agents`` — no widget construction at
  all.
* ``AgentPanel``'s ``visible_var``/``build_visibility_toggle``/
  ``set_run_state`` behaviour and the per-switch fine-tune expanders
  (UI-SKETCH 2026-07-29, which retired the global Settings gear — the
  ``ExpandableSwitch`` primitive itself is pinned in
  test_gui_widgets.py) need a real (withdrawn) Tk root — the SAME ``tk_root``
  fixture and bare-``AgentPanel`` ``make_panel`` convention
  test_gui_upscale.py/test_gui_pipeline.py already established (never a
  full ``PainterGui`` — see those files' own docstrings on why).
* ``PainterGui._relayout_agents`` itself runs unbound against a small
  duck-typed ``FakeGui`` carrying REAL ``AgentPanel``/``ttk.Frame``
  widgets — the same convention test_gui_running_view.py's own
  ``FakeGui`` uses for the running-view methods.
"""

from __future__ import annotations

from tkinter import ttk
from types import SimpleNamespace

import pytest

import gui
from painter.config import ASPECT_DEFAULT_H, ASPECT_DEFAULT_W, SITES


# ---------------------------------------------------------------------
# gui._visible_agent_slots — pure, no Tk
# ---------------------------------------------------------------------


def test_visible_agent_slots_both_visible_keep_their_order():
    cols = gui._visible_agent_slots(
        ["chatgpt", "gemini"], {"chatgpt": True, "gemini": True}
    )
    assert cols == {"chatgpt": 0, "gemini": 1}


def test_visible_agent_slots_hidden_second_site_leaves_no_gap():
    cols = gui._visible_agent_slots(
        ["chatgpt", "gemini"], {"chatgpt": True, "gemini": False}
    )
    assert cols == {"chatgpt": 0}


def test_visible_agent_slots_hidden_first_site_compacts_the_survivor():
    """The interesting case: hiding the FIRST site must not strand the
    lone survivor in slot 1 with a dead slot 0 beside it."""
    cols = gui._visible_agent_slots(
        ["chatgpt", "gemini"], {"chatgpt": False, "gemini": True}
    )
    assert cols == {"gemini": 0}


def test_visible_agent_slots_both_hidden_is_a_legal_empty_result():
    cols = gui._visible_agent_slots(
        ["chatgpt", "gemini"], {"chatgpt": False, "gemini": False}
    )
    assert cols == {}


def test_visible_agent_slots_missing_key_defaults_visible():
    cols = gui._visible_agent_slots(["chatgpt", "gemini"], {})
    assert cols == {"chatgpt": 0, "gemini": 1}


# ---------------------------------------------------------------------
# AgentPanel — real (withdrawn) Tk root
# ---------------------------------------------------------------------


@pytest.fixture
def root(tk_root):
    return tk_root


def make_panel(
    root, site: str = "gemini", on_log=None, on_layout_change=None
) -> gui.AgentPanel:
    """A bare AgentPanel, parented directly on the shared root (never
    packed/mapped — same convention test_gui_upscale.py/
    test_gui_pipeline.py already use) with no-op callbacks — never a
    full PainterGui. ``on_layout_change`` has to be passed HERE (not
    assigned onto the panel afterwards): every ExpandableSwitch takes
    the callable by value at construction, exactly like the real
    PainterGui wiring hands it its ScrollFrame.refresh."""
    return gui.AgentPanel(
        root, site,
        on_start=lambda *_a: None, on_stop=lambda *_a: None,
        on_pause=lambda *_a: None, on_log=on_log,
        on_layout_change=on_layout_change,
    )


# --- visible_var: default, persistence round-trip --------------------


def test_agent_panel_visible_var_defaults_true(root):
    panel = make_panel(root)
    assert panel.visible_var.get() is True


def test_visible_is_in_persist_and_vars(root):
    panel = make_panel(root)
    assert "visible" in panel._PERSIST
    assert panel._vars()["visible"] is panel.visible_var


def test_get_settings_round_trips_visible_false(root):
    panel = make_panel(root)
    panel.visible_var.set(False)
    stored = panel.get_settings()
    assert stored["visible"] is False

    fresh = make_panel(root)
    assert fresh.visible_var.get() is True  # a fresh panel still defaults True
    fresh.apply_settings(stored)
    assert fresh.visible_var.get() is False


def test_apply_settings_missing_visible_key_keeps_the_default(root):
    """An old settings.json predating Phase 12 has no 'visible' key at
    all — the generic _PERSIST loop's "missing key keeps the current
    default" contract must leave it True, same as every other field."""
    panel = make_panel(root)
    panel.apply_settings({"background": "white"})  # no 'visible' key
    assert panel.visible_var.get() is True


# --- build_visibility_toggle + set_run_state locking ------------------


def test_set_run_state_tolerates_no_toggle_built_yet(root):
    """__init__ itself calls set_run_state(running=False) before
    PainterGui ever calls build_visibility_toggle — must not raise."""
    panel = make_panel(root)  # would already have raised in __init__
    assert panel._visible_btn is None


def test_visibility_toggle_starts_enabled(root):
    panel = make_panel(root)
    parent = ttk.Frame(root)
    toggle = panel.build_visibility_toggle(parent)
    assert toggle is panel._visible_btn
    assert toggle.cget("state") == "normal"


def test_running_disables_the_visibility_toggle(root):
    panel = make_panel(root)
    panel.build_visibility_toggle(ttk.Frame(root))
    panel.set_run_state(running=True)
    assert panel._visible_btn.cget("state") == "disabled"
    panel.set_run_state(running=False)
    assert panel._visible_btn.cget("state") == "normal"


def test_pending_restart_alone_also_disables_the_toggle(root):
    """A quota auto-restart countdown needs Stop just as much as a live
    run — same lock window as Stop's own availability."""
    panel = make_panel(root)
    panel.build_visibility_toggle(ttk.Frame(root))
    panel.set_run_state(running=False, pending_restart=True)
    assert panel._visible_btn.cget("state") == "disabled"


def test_running_forces_a_hidden_panel_back_to_visible_and_logs(root):
    logged = []
    panel = make_panel(root, on_log=logged.append)
    panel.build_visibility_toggle(ttk.Frame(root))
    panel.visible_var.set(False)  # the owner hid it while idle
    logged.clear()  # drop the .set() itself — nothing to do with set_run_state

    panel.set_run_state(running=True)  # a quota auto-restart, say
    assert panel.visible_var.get() is True
    assert len(logged) == 1
    assert SITES[panel.site_key].name in logged[0]


def test_run_state_change_while_already_visible_never_logs(root):
    """The forced un-hide + log path fires ONLY on the False->True
    transition — a normal Start on an already-visible panel is silent."""
    logged = []
    panel = make_panel(root, on_log=logged.append)
    panel.build_visibility_toggle(ttk.Frame(root))
    panel.set_run_state(running=True)
    panel.set_run_state(running=False)
    assert logged == []


def test_on_log_defaults_to_a_harmless_noop(root):
    """No on_log passed (every headless make_panel() elsewhere in the
    suite, and the two OTHER test files' own make_panel helpers) must
    not raise when a forced un-hide fires."""
    panel = make_panel(root, on_log=None)
    panel.build_visibility_toggle(ttk.Frame(root))
    panel.visible_var.set(False)
    panel.set_run_state(running=True)  # must not raise
    assert panel.visible_var.get() is True


# --- the per-switch expanders (UI-SKETCH, owner 2026-07-29) -----------
# The global Settings gear is GONE: every fine-tune lives in its own
# switch's ExpandableSwitch sub-panel. These tests pin the AgentPanel
# WIRING of that primitive (which switch owns which sub-panel, and that
# the eager sub-panels' state exists from construction); the primitive's
# own open/collapse mechanics are pinned in test_gui_widgets.py.


def test_the_gear_is_gone(root):
    """Rule #6: the retired gear left NO stump behind — no collapse
    var, no toggle method, no fine-tune box."""
    panel = make_panel(root)
    assert not hasattr(panel, "settings_collapsed_var")
    assert not hasattr(panel, "_toggle_settings")
    assert not hasattr(panel, "_finetune_box")
    assert "settings_collapsed" not in panel._PERSIST


def test_upscale_sub_starts_collapsed_even_though_upscale_is_on(root):
    """A panel built with Upscale already ON (its default, and every
    restored settings.json) opens COMPACT — the auto-expand fires only
    on a live OFF->ON click, see ExpandableSwitch's own docstring."""
    panel = make_panel(root)
    assert panel.upscale_var.get() is True
    assert panel._sw_upscale.sub.winfo_manager() == ""


def test_turning_upscale_off_then_on_auto_expands_its_sub(root):
    panel = make_panel(root)
    panel.upscale_var.set(False)
    assert panel._sw_upscale.sub.winfo_manager() == ""
    panel.upscale_var.set(True)  # a live turn-ON auto-expands
    assert panel._sw_upscale.sub.winfo_manager() == "pack"


def test_upscale_off_hides_an_expanded_sub_live(root):
    panel = make_panel(root)
    panel._sw_upscale.toggle(open_=True)  # the caret click
    assert panel._sw_upscale.sub.winfo_manager() == "pack"
    panel.upscale_var.set(False)
    assert panel._sw_upscale.sub.winfo_manager() == ""


def test_eager_upscale_sub_carries_its_filter_before_any_expand(root):
    """The upscale gate's FilterEditor stack (and the aspect canvas's
    two-way binding) outlive the expander's visibility — they are built
    EAGERLY at construction, so upscale_params() works on a panel whose
    sub-panel was never opened."""
    panel = make_panel(root)
    assert panel._sw_upscale.sub.winfo_manager() == ""  # never opened
    params = panel.upscale_params()
    assert params["min_width"] == params["min_height"] == 800
    assert panel.upscale_conditions()  # the seeded aspect gate is there
    assert panel.force_aspect_ratio() == (ASPECT_DEFAULT_W, ASPECT_DEFAULT_H)


def test_apply_settings_restoring_upscale_false_leaves_the_sub_hidden(root):
    """A settings-restore .set() fires the SAME trace as an interactive
    click (Tk write-traces do not distinguish the two) — restoring OFF
    must never leave an orphan sub-panel packed."""
    panel = make_panel(root)
    panel._sw_upscale.toggle(open_=True)
    panel.apply_settings({"upscale": False})
    assert panel.upscale_var.get() is False
    assert panel._sw_upscale.sub.winfo_manager() == ""


def test_apply_settings_never_auto_expands_a_restored_on_switch(root):
    """The live-window defect (owner's settings.json, 2026-07-29): the
    app applies the stored settings AFTER building the panel, so every
    ON switch used to auto-expand and the setup screen opened as a wall
    of fine-tune. apply_settings runs under quiet_restore — the panel
    opens COMPACT, whatever is stored."""
    panel = make_panel(root)
    panel.apply_settings({
        "bg_removal": True, "upscale": True, "force_aspect": True,
        "checker": True,
    })
    for switch in panel._expanders():
        assert switch.sub.winfo_manager() == ""


def test_every_finetune_switch_owns_its_own_expander(root):
    """The UI-SKETCH map: BG removal / Force aspect ratio / Upscale /
    AI checker each carry their own sub-panel, plus the switch-less
    Pacing section. Crop and the plain Run-behavior switches carry
    none — they have nothing to fine-tune."""
    panel = make_panel(root)
    owners = {
        panel._sw_bg: panel.bg_removal_var,
        panel._sw_aspect: panel.force_aspect_var,
        panel._sw_upscale: panel.upscale_var,
        panel._sw_checker: panel.checker_var,
    }
    for switch, var in owners.items():
        assert switch._var is var
        assert switch.sub.winfo_manager() == ""  # all start collapsed
    assert panel._sec_pacing.sub.winfo_manager() == ""


# --- expanders -> on_layout_change (owner 2026-07-21 perf fix) ---------


def test_expanding_a_switch_calls_on_layout_change_after_the_reveal(root):
    """The outer ScrollFrame's refresh hook (owner 2026-07-21 perf fix,
    replacing the old perpetual self-heal poll) must fire exactly once
    per toggle, AFTER the sub-panel is actually packed/forgotten — the
    panel's own content height changes several parents below that
    ScrollFrame, which has no other way to learn of it."""
    calls: list[str] = []
    panel = make_panel(
        root,
        on_layout_change=lambda: calls.append(
            panel._sw_upscale.sub.winfo_manager()
        ),
    )

    panel._sw_upscale.toggle()  # collapsed -> expanded
    assert panel._sw_upscale.sub.winfo_manager() == "pack"
    assert calls == ["pack"]

    panel._sw_upscale.toggle()  # expanded -> collapsed
    assert panel._sw_upscale.sub.winfo_manager() == ""
    assert calls == ["pack", ""]


def test_pacing_section_also_reports_its_layout_change(root):
    """The switch-LESS Pacing section (ExpandableSection) is wired to
    the same hook — a plain label + caret, no switch to gate it."""
    calls: list[str] = []
    panel = make_panel(root, on_layout_change=lambda: calls.append("x"))
    panel._sec_pacing.toggle()
    assert panel._sec_pacing.sub.winfo_manager() == "pack"
    assert calls == ["x"]


def test_expander_on_layout_change_defaults_to_a_harmless_noop(root):
    """Every OTHER make_panel() in this suite passes no on_layout_change
    at all — must not raise."""
    panel = make_panel(root)
    panel._sw_upscale.toggle()  # must not raise
    assert panel._sw_upscale.sub.winfo_manager() == "pack"


# ---------------------------------------------------------------------
# PainterGui._relayout_agents — via a duck-typed FakeGui
# ---------------------------------------------------------------------


class FakeGui:
    """Duck-typed ``PainterGui`` stand-in — just enough attribute
    surface for the UNBOUND ``_relayout_agents`` to run for real (never
    a full ``PainterGui`` — see this module's docstring). Mirrors the
    REAL widget hierarchy's two SEPARATE containers (``_agents_frame``
    grid-managed, the compact strip pack-managed) — Tk refuses to mix
    geometry managers on the SAME parent, exactly like
    ``_build_options``/``_build_compact`` keep them apart for real."""

    # F4c: _relayout_agents now consults the run state and drives the
    # shared both-sites editor — the fake carries that surface too,
    # with the REAL _set_agent_mirror aliased on (same unbound-method
    # convention as every other FakeGui in the suite)
    _set_agent_mirror = gui.PainterGui._set_agent_mirror

    def __init__(self, root):
        self._agents_frame = ttk.Frame(root)
        self.agents = {
            key: make_panel(self._agents_frame, site=key)
            for key in sorted(SITES)
        }
        for i, key in enumerate(sorted(SITES)):
            self.agents[key].grid(row=i, column=0, sticky="new", pady=(0, 6))
            self._agents_frame.columnconfigure(0, weight=1)
        compact_box = ttk.Frame(root)
        self._compact_clusters = {
            key: ttk.Frame(compact_box) for key in sorted(SITES)
        }
        for cluster in self._compact_clusters.values():
            cluster.pack(side="left")
        self._scroll = SimpleNamespace(refresh=lambda: None)
        self._running: set = set()
        self._restart_jobs: dict = {}
        self._agent_mirror_on = False
        self._mirror_traces: list = []


@pytest.fixture
def fake(root):
    return FakeGui(root)


def test_relayout_both_ticked_idle_shows_the_single_shared_editor(fake):
    """F4c (owner 2026-07-29): BOTH ticked and idle = ONE shared
    editor — only the primary (chatgpt) panel shows, mirroring is on,
    and edits flow to the hidden site's vars live."""
    gui.PainterGui._relayout_agents(fake)
    assert fake.agents["chatgpt"].winfo_manager() == "grid"
    assert fake.agents["gemini"].winfo_manager() == ""  # hidden, mirrored
    assert fake._agent_mirror_on is True
    fake.agents["chatgpt"].crop_var.set(False)
    assert fake.agents["gemini"].crop_var.get() is False  # mirrored live


def test_relayout_both_ticked_but_running_shows_both_panels(fake):
    """A live job always gets its own per-site panel back — the shared
    editor never hides a running site's controls."""
    fake._running = {"gemini"}
    gui.PainterGui._relayout_agents(fake)
    assert fake.agents["chatgpt"].winfo_manager() == "grid"
    assert fake.agents["gemini"].winfo_manager() == "grid"
    assert fake._agent_mirror_on is False
    assert fake._compact_clusters["chatgpt"].winfo_manager() == "pack"
    assert fake._compact_clusters["gemini"].winfo_manager() == "pack"


def test_relayout_hiding_gemini_removes_its_panel_and_cluster(fake):
    fake.agents["gemini"].visible_var.set(False)
    gui.PainterGui._relayout_agents(fake)
    assert fake.agents["gemini"].winfo_manager() == ""
    assert fake._compact_clusters["gemini"].winfo_manager() == ""
    # ChatGPT stays exactly where it was
    assert fake.agents["chatgpt"].winfo_manager() == "grid"
    assert fake.agents["chatgpt"].grid_info()["row"] == 0


def test_relayout_hiding_chatgpt_compacts_gemini_into_row_zero(fake):
    """UI-SKETCH (owner 2026-07-29): the panels STACK in the setup
    screen's left settings column, so the survivor compacts into ROW 0
    — hiding the first site must not strand the other below an empty
    row."""
    fake.agents["chatgpt"].visible_var.set(False)
    gui.PainterGui._relayout_agents(fake)
    assert fake.agents["chatgpt"].winfo_manager() == ""
    assert fake.agents["gemini"].winfo_manager() == "grid"
    assert fake.agents["gemini"].grid_info()["row"] == 0


def test_relayout_reshowing_both_reenters_the_shared_editor(fake):
    """Re-ticking the second site while idle goes back to the F4c
    shared editor (primary only), never the old two-panel layout."""
    fake.agents["gemini"].visible_var.set(False)
    gui.PainterGui._relayout_agents(fake)
    assert fake._agent_mirror_on is False
    fake.agents["gemini"].visible_var.set(True)
    gui.PainterGui._relayout_agents(fake)
    assert fake.agents["chatgpt"].grid_info()["row"] == 0
    assert fake.agents["gemini"].winfo_manager() == ""
    assert fake._agent_mirror_on is True
