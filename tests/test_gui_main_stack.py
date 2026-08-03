"""``_pack_main_stack`` — the ONE packer for the working views' layout.

Split out of test_gui_running_view.py (THE STRUCTURE LAW): that module
tests the running view's SEMANTICS (which view, which job, which tile);
this one tests the LAYOUT those semantics render into — what sits above
what inside ``_main_view``.

Regression cover for the class of bug that kept coming back (owner
2026-08-03: "dosta smo imali tako pretvorbenih kaotičnih elemenata koje
smo morali da vraćamo"). Three separate packers used to share the job —
``_set_collapsed`` (controls/compact), ``_set_view``'s own "main" branch
(icon bar + notebook) and ``_apply_running_layout`` (icon bar + inline
panel) — each anchoring off whatever happened to be packed at the time
(``before=self.notebook``, ``before=self._controls_box``, or nothing),
so the SAME three widgets ended up in different vertical orders
depending on the route taken: returning from a run to the setup screen
re-packed the controls AFTER the notebook, putting the DASHBOARD above
the icon bar and the settings. ``_pack_main_stack`` is now the single
decider — it forgets everything and re-packs in a fixed order — and
these tests pin that order.

``FakeGui`` is imported from test_gui_running_view rather than
re-declared (Rule #5 — one duck-typed stand-in, not two); see that
module's own docstring for the convention.
"""

from __future__ import annotations

from types import SimpleNamespace

import pytest

import gui
from test_gui_running_view import FakeGui


@pytest.fixture
def root(tk_root):
    return tk_root


def _stack(fake) -> list[str]:
    """The packed children of the container ``_pack_main_stack`` owns,
    in their real top-to-bottom order, labelled by role."""
    role = {
        str(fake._icon_bar): "iconbar",
        str(fake._controls_box): "controls",
        str(fake._compact_box): "compact",
        str(fake.notebook): "dashboard",
    }
    for tile_id, panel in fake._tool_panels.items():
        role[str(panel)] = f"panel:{tile_id}"
    return [
        role[str(w)]
        for w in fake._icon_bar.master.pack_slaves()
        if str(w) in role
    ]


def test_pack_main_stack_order_is_iconbar_then_surface_then_dashboard(root):
    """The nav strip is ALWAYS on top (owner 2026-08-03, slika 2:
    "GLAVNI MENI LINE TREBA UVEK DA BUDE GORE"), the one setup surface
    sits under it, and the dashboard is last."""
    fake = FakeGui(root)
    fake._view = "running"
    fake._inline_kind = "crop"

    gui.PainterGui._pack_main_stack(fake)

    assert _stack(fake) == ["iconbar", "panel:crop", "dashboard"]


def test_pack_main_stack_setup_view_keeps_the_dashboard_last(root):
    """Returning from a run to the setup screen used to re-pack the
    controls AFTER the notebook, so the DASHBOARD rendered above the
    icon bar and the settings. The order must not depend on the route."""
    fake = FakeGui(root)
    fake._dashgrid = SimpleNamespace(active=lambda: ["gemini"])  # a job ran
    fake._view = "running"
    fake._inline_kind = "bg"
    gui.PainterGui._pack_main_stack(fake)

    fake._view = "main"          # ... and back to setup
    fake._inline_kind = None
    gui.PainterGui._pack_main_stack(fake)

    assert _stack(fake) == ["iconbar", "controls", "dashboard"]


def test_pack_main_stack_never_shows_two_setup_surfaces(root):
    """Owner 2026-08-03, slika 2: "NIKADA ne smeju da budu OTVORENA 2
    različita SETUPA". Whatever the previous view left packed, exactly
    one surface survives the next pass."""
    fake = FakeGui(root)
    fake._view = "running"
    fake._inline_kind = "crop"
    gui.PainterGui._pack_main_stack(fake)

    fake._inline_kind = "website_gen"
    gui.PainterGui._pack_main_stack(fake)

    assert _stack(fake) == ["iconbar", "controls", "dashboard"]
    assert fake._tool_panels["crop"].winfo_manager() == ""


def test_pack_main_stack_on_the_menu_packs_nothing(root):
    """The Main Menu is a different container entirely — _main_view's
    own children must all be forgotten, never left packed behind it."""
    fake = FakeGui(root)
    fake._view = "running"
    fake._inline_kind = "upscale"
    gui.PainterGui._pack_main_stack(fake)

    fake._view = "menu"
    gui.PainterGui._pack_main_stack(fake)

    assert _stack(fake) == []

