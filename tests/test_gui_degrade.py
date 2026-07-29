"""F2 model-degradation choice (owner 2026-07-29): ``AgentPanel``'s new
``degrade_var`` (ask/continue/wait, persisted key "degrade") behaves
like every other per-agent settings field, and ``cooldown_var`` (an
info-only label beside the site name — NEVER gates Start) defaults to
empty. Same ``tk_root``/``make_panel`` convention as
test_gui_agent_visibility.py — a bare ``AgentPanel`` on the shared
withdrawn root, never a full ``PainterGui`` (see that file's own
docstring for why). Deliberately just TWO panel constructions in this
whole file (every assertion that can share one does) — each
``AgentPanel`` leaks several Tk dropdown ``Menu`` handles for the
lifetime of the SESSION-scoped ``tk_root`` (never reclaimed, a known
Windows/Tcl constraint the whole suite already runs close to), and this
file's tests do not need more than that to prove the contract.

The deeper F2 plumbing — ``PainterGui``'s "site_cooldowns" persistence,
the 30s ``_refresh_cooldown_labels`` poll, the ``"__ask_degrade__"``
queue message — needs a full ``PainterGui``/real timers and is left to
manual/screenshot verification, same as the rest of that "barely
Tk-unit-tested by design" surface (see ___tests.md).
"""

import pytest

import gui
from painter.config import DEGRADE_ASK, DEGRADE_CONTINUE


@pytest.fixture
def root(tk_root):
    return tk_root


def make_panel(root, site: str = "gemini") -> gui.AgentPanel:
    """A bare AgentPanel, parented directly on the shared root (never
    packed/mapped — same convention as every other GUI-phase file's own
    make_panel) with no-op callbacks — never a full PainterGui."""
    return gui.AgentPanel(
        root, site,
        on_start=lambda *_a: None, on_stop=lambda *_a: None,
        on_pause=lambda *_a: None,
    )


def test_degrade_and_cooldown_defaults_and_persist_wiring(root):
    panel = make_panel(root)
    assert panel.degrade_var.get() == DEGRADE_ASK
    assert panel.cooldown_var.get() == ""
    assert "degrade" in panel._PERSIST
    assert panel._vars()["degrade"] is panel.degrade_var
    # an old settings.json predating F2 has no 'degrade' key at all —
    # the generic _PERSIST loop's "missing key keeps the current
    # default" contract must leave it "ask", same as every other field
    panel.apply_settings({"background": "white"})
    assert panel.degrade_var.get() == DEGRADE_ASK


def test_get_settings_round_trips_degrade_choice(root):
    panel = make_panel(root)
    panel.degrade_var.set(DEGRADE_CONTINUE)
    stored = panel.get_settings()
    assert stored["degrade"] == DEGRADE_CONTINUE

    panel.degrade_var.set(DEGRADE_ASK)  # back to the construction-time default
    panel.apply_settings(stored)
    assert panel.degrade_var.get() == DEGRADE_CONTINUE
