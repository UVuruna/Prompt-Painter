"""Website GEN settings-panel polish (GUI rework Phase 12, owner
2026-07-21, spec item 3A from UV/prompt.txt: "moze da se prikaze/sakrije
bilo koji tj da ostane samo jedan vidljiv (od GPT-Gemini)" / "FILTER za
Upscale se pali samo ako je UPSCALE stikliran"). Three halves, matching
gui.py's own "pure helpers get pytest, real Tk/UI wiring gets a
screenshot" split (___tests.md):

* ``gui._visible_agent_columns`` is the pure, Tk-free column resolver
  behind ``PainterGui._relayout_agents`` — no widget construction at
  all.
* ``AgentPanel``'s new ``visible_var``/``build_visibility_toggle``/
  ``set_run_state`` behaviour and the ``upscale_var``-gated fine-tune
  sub-block need a real (withdrawn) Tk root — the SAME ``tk_root``
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
from painter.config import SITES


# ---------------------------------------------------------------------
# gui._visible_agent_columns — pure, no Tk
# ---------------------------------------------------------------------


def test_visible_agent_columns_both_visible_keep_their_order():
    cols = gui._visible_agent_columns(
        ["chatgpt", "gemini"], {"chatgpt": True, "gemini": True}
    )
    assert cols == {"chatgpt": 0, "gemini": 1}


def test_visible_agent_columns_hidden_second_site_leaves_no_gap():
    cols = gui._visible_agent_columns(
        ["chatgpt", "gemini"], {"chatgpt": True, "gemini": False}
    )
    assert cols == {"chatgpt": 0}


def test_visible_agent_columns_hidden_first_site_compacts_the_survivor():
    """The interesting case: hiding the FIRST site must not strand the
    lone survivor in column 1 with a dead column 0 beside it."""
    cols = gui._visible_agent_columns(
        ["chatgpt", "gemini"], {"chatgpt": False, "gemini": True}
    )
    assert cols == {"gemini": 0}


def test_visible_agent_columns_both_hidden_is_a_legal_empty_result():
    cols = gui._visible_agent_columns(
        ["chatgpt", "gemini"], {"chatgpt": False, "gemini": False}
    )
    assert cols == {}


def test_visible_agent_columns_missing_key_defaults_visible():
    cols = gui._visible_agent_columns(["chatgpt", "gemini"], {})
    assert cols == {"chatgpt": 0, "gemini": 1}


# ---------------------------------------------------------------------
# AgentPanel — real (withdrawn) Tk root
# ---------------------------------------------------------------------


@pytest.fixture
def root(tk_root):
    return tk_root


def make_panel(root, site: str = "gemini", on_log=None) -> gui.AgentPanel:
    """A bare AgentPanel, parented directly on the shared root (never
    packed/mapped — same convention test_gui_upscale.py/
    test_gui_pipeline.py already use) with no-op callbacks — never a
    full PainterGui."""
    return gui.AgentPanel(
        root, site,
        on_start=lambda *_a: None, on_stop=lambda *_a: None,
        on_pause=lambda *_a: None, on_log=on_log,
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


# --- upscale-gate sub-block gated on upscale_var -----------------------


def test_upscale_gate_box_visible_by_default(root):
    panel = make_panel(root)
    assert panel.upscale_var.get() is True
    assert panel._upscale_gate_box.winfo_manager() == "pack"


def test_upscale_off_hides_the_gate_box_live(root):
    panel = make_panel(root)
    panel.upscale_var.set(False)
    assert panel._upscale_gate_box.winfo_manager() == ""


def test_upscale_back_on_reshows_the_gate_box(root):
    panel = make_panel(root)
    panel.upscale_var.set(False)
    panel.upscale_var.set(True)
    assert panel._upscale_gate_box.winfo_manager() == "pack"


def test_upscale_gate_visibility_independent_of_the_settings_gear(root):
    """The trace fires (and the sub-block's OWN pack state updates)
    regardless of whether the outer Settings-gear box is expanded —
    packing a child never depends on its parent's own manager state."""
    panel = make_panel(root)
    assert panel.settings_collapsed_var.get() is True  # gear starts collapsed
    panel.upscale_var.set(False)
    assert panel._upscale_gate_box.winfo_manager() == ""
    panel.upscale_var.set(True)
    assert panel._upscale_gate_box.winfo_manager() == "pack"


def test_apply_settings_restoring_upscale_false_hides_the_gate_box(root):
    """A settings-restore .set() fires the SAME trace as an interactive
    click (Tk write-traces do not distinguish the two)."""
    panel = make_panel(root)
    panel.apply_settings({"upscale": False})
    assert panel.upscale_var.get() is False
    assert panel._upscale_gate_box.winfo_manager() == ""


# --- Settings gear -> on_layout_change (owner 2026-07-21 perf fix) ------


def test_toggle_settings_calls_on_layout_change_after_the_reveal(root):
    """The real click path (_toggle_settings, not the bare
    _apply_finetune_visibility): the outer ScrollFrame's refresh hook
    (owner 2026-07-21 perf fix, replacing the old perpetual self-heal
    poll) must fire exactly once per toggle, AFTER the fine-tune box is
    actually packed/forgotten — on a withdrawn root smooth_transition's
    own mapped/viewable guard fails, so mutate runs instantly and
    synchronously, making the ordering directly observable here."""
    calls: list[str] = []
    panel = make_panel(root, on_log=None)
    panel._on_layout_change = lambda: calls.append(
        panel._finetune_box.winfo_manager()
    )

    assert panel.settings_collapsed_var.get() is True  # starts collapsed
    panel._toggle_settings()  # collapsed -> expanded
    assert panel._finetune_box.winfo_manager() == "pack"
    assert calls == ["pack"]

    panel._toggle_settings()  # expanded -> collapsed
    assert panel._finetune_box.winfo_manager() == ""
    assert calls == ["pack", ""]


def test_toggle_settings_on_layout_change_defaults_to_a_harmless_noop(root):
    """Every OTHER make_panel() in this suite passes no on_layout_change
    at all — must not raise."""
    panel = make_panel(root)
    panel._toggle_settings()  # must not raise
    assert panel._finetune_box.winfo_manager() == "pack"


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

    def __init__(self, root):
        self._agents_frame = ttk.Frame(root)
        self.agents = {
            key: make_panel(self._agents_frame, site=key)
            for key in sorted(SITES)
        }
        for i, key in enumerate(sorted(SITES)):
            self.agents[key].grid(row=0, column=i, sticky="nsew", padx=4)
            self._agents_frame.columnconfigure(i, weight=1)
        compact_box = ttk.Frame(root)
        self._compact_clusters = {
            key: ttk.Frame(compact_box) for key in sorted(SITES)
        }
        for cluster in self._compact_clusters.values():
            cluster.pack(side="left")
        self._scroll = SimpleNamespace(refresh=lambda: None)


@pytest.fixture
def fake(root):
    return FakeGui(root)


def test_relayout_both_visible_grids_and_packs_both(fake):
    gui.PainterGui._relayout_agents(fake)
    assert fake.agents["chatgpt"].winfo_manager() == "grid"
    assert fake.agents["gemini"].winfo_manager() == "grid"
    assert fake._compact_clusters["chatgpt"].winfo_manager() == "pack"
    assert fake._compact_clusters["gemini"].winfo_manager() == "pack"


def test_relayout_hiding_gemini_removes_its_panel_and_cluster(fake):
    fake.agents["gemini"].visible_var.set(False)
    gui.PainterGui._relayout_agents(fake)
    assert fake.agents["gemini"].winfo_manager() == ""
    assert fake._compact_clusters["gemini"].winfo_manager() == ""
    # ChatGPT stays exactly where it was
    assert fake.agents["chatgpt"].winfo_manager() == "grid"
    assert fake.agents["chatgpt"].grid_info()["column"] == 0


def test_relayout_hiding_chatgpt_compacts_gemini_into_column_zero(fake):
    fake.agents["chatgpt"].visible_var.set(False)
    gui.PainterGui._relayout_agents(fake)
    assert fake.agents["chatgpt"].winfo_manager() == ""
    assert fake.agents["gemini"].winfo_manager() == "grid"
    assert fake.agents["gemini"].grid_info()["column"] == 0


def test_relayout_reshowing_restores_both_columns(fake):
    fake.agents["gemini"].visible_var.set(False)
    gui.PainterGui._relayout_agents(fake)
    fake.agents["gemini"].visible_var.set(True)
    gui.PainterGui._relayout_agents(fake)
    assert fake.agents["chatgpt"].grid_info()["column"] == 0
    assert fake.agents["gemini"].grid_info()["column"] == 1
    assert fake.agents["gemini"].winfo_manager() == "grid"
