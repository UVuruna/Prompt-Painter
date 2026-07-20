"""smooth_transition fallback paths — callable with NO window on screen.

The snapshot cover (overlay + alpha fade) behind the theme flip, the
Controls collapse, the Settings gears and maximize/restore is a visual
nicety; what MUST hold everywhere — headless included — is that the
mutate callback runs EXACTLY ONCE whether the cover works, is
unavailable, or fails mid-build (root Rule #1: the cover can never be
the reason a toggle stops working), and that a mutate exception is
never masked. No Tk window or ImageGrab ever starts here: a ``None``
root plus unmapped / failing fakes exercise every branch.
"""

import pytest

import gui
from painter.config import TRANSITION_FADE_MS, TRANSITION_FADE_STEPS


class _Root:
    """A stand-in root: mapped/viewable flags without any real Tk."""

    def __init__(self, mapped: bool = True, viewable: bool = True):
        self._mapped, self._viewable = mapped, viewable
        self.idle_settles = 0

    def winfo_ismapped(self):
        return self._mapped

    def winfo_viewable(self):
        return self._viewable

    def update_idletasks(self):
        self.idle_settles += 1


class _Overlay:
    """A stand-in overlay that records the forced-paint sequence."""

    def __init__(self):
        self.calls: list[str] = []
        self.destroyed = False

    def deiconify(self):
        self.calls.append("deiconify")

    def lift(self):
        self.calls.append("lift")

    def update_idletasks(self):
        self.calls.append("update_idletasks")

    def update(self):
        self.calls.append("update")

    def destroy(self):
        self.destroyed = True


# --- the instant-mutate fallbacks --------------------------------------


def test_none_root_mutates_instantly():
    ran = []
    gui.smooth_transition(None, lambda: ran.append(1))
    assert ran == [1]


def test_unmapped_root_mutates_instantly():
    ran = []
    gui.smooth_transition(_Root(mapped=False), lambda: ran.append(1))
    assert ran == [1]


def test_unviewable_root_mutates_instantly():
    ran = []
    gui.smooth_transition(_Root(viewable=False), lambda: ran.append(1))
    assert ran == [1]


def test_cover_failure_still_mutates_exactly_once(monkeypatch):
    """ImageGrab/alpha failing must never block the action NOR run the
    mutate twice."""
    def boom(_root, _icon_factory):
        raise RuntimeError("no grab on this display")

    monkeypatch.setattr(gui, "_snapshot_overlay", boom)
    ran = []
    gui.smooth_transition(_Root(), lambda: ran.append(1))
    assert ran == [1]


# --- the covered path (faked overlay — no real Tk) ----------------------


def test_cover_paints_before_mutate_and_fades_after(monkeypatch):
    overlay = _Overlay()
    fades: list[tuple] = []
    order: list[str] = []
    monkeypatch.setattr(
        gui, "_snapshot_overlay", lambda _r, _f: overlay
    )
    monkeypatch.setattr(
        gui, "_fade_out_overlay",
        lambda _r, o, ms, steps: fades.append((o, ms, steps)),
    )
    root = _Root()
    gui.smooth_transition(root, lambda: order.append("mutate"))
    # forced fully painted BEFORE the mutate ran
    assert overlay.calls == ["deiconify", "lift", "update_idletasks", "update"]
    assert order == ["mutate"]
    assert root.idle_settles == 1  # the relayout settled behind the cover
    # the fade got the overlay and the default (snappy) transition timing
    assert fades == [(overlay, TRANSITION_FADE_MS, TRANSITION_FADE_STEPS)]


def test_theme_flip_timing_is_passed_through(monkeypatch):
    """apply_theme rides the SAME helper but with the ceremonial
    SWITCH_FADE_* timing."""
    fades: list[tuple] = []
    monkeypatch.setattr(gui, "_snapshot_overlay", lambda _r, _f: _Overlay())
    monkeypatch.setattr(
        gui, "_fade_out_overlay",
        lambda _r, _o, ms, steps: fades.append((ms, steps)),
    )
    gui.smooth_transition(
        _Root(), lambda: None,
        fade_ms=gui.SWITCH_FADE_MS, fade_steps=gui.SWITCH_FADE_STEPS,
    )
    assert fades == [(gui.SWITCH_FADE_MS, gui.SWITCH_FADE_STEPS)]


def test_mutate_exception_propagates_and_cover_still_fades(monkeypatch):
    """Rule #1: a failing mutate is LOUD — and the overlay still leaves
    the screen (the fade runs from the finally)."""
    overlay = _Overlay()
    fades: list = []
    monkeypatch.setattr(gui, "_snapshot_overlay", lambda _r, _f: overlay)
    monkeypatch.setattr(
        gui, "_fade_out_overlay", lambda _r, o, _ms, _st: fades.append(o)
    )

    def bad_mutate():
        raise ValueError("relayout blew up")

    with pytest.raises(ValueError, match="relayout blew up"):
        gui.smooth_transition(_Root(), bad_mutate)
    assert fades == [overlay]  # never a stuck cover
