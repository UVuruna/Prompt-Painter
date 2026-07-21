"""``BuildMixin._on_root_configure``/``_resize_settled``/``_clamp_geometry``
(gui/app_build.py) — pure/duck-typed, no real Tk needed (same convention
test_gui_agent_visibility.py/test_gui_running_view.py already use for an
unbound PainterGui method run against a small ``FakeGui``).

Owner 2026-07-21 perf fix: a real-window repro (screenshots, see the
session's own diagnosis) proved that wrapping the zoomed<->normal window
STATE change (maximize/restore) in the shared ``smooth_transition``
snapshot cover — added 2026-07-20 — actively BREAKS the OS-level
transition: the real window gets stuck at its old size (maximize) or
renders a corrupted frame (restore), while Tk's own ``state()``/
``winfo_*`` insist the change already happened. The fix removes the
cover call entirely for that branch; these tests lock in that the
handler still does its OTHER job correctly (continuous-drag debounce +
event buffering) and no longer touches any cover machinery on a state
jump."""

from __future__ import annotations

import gui
from painter.config import RESIZE_SETTLE_MS


class FakeRoot:
    """A stand-in root: state()/after()/after_cancel()/screen size,
    no real Tk window."""

    def __init__(self, state: str = "normal", screen=(1920, 1080)):
        self._state = state
        self._screen = screen
        self.after_calls: list[tuple[int, object, int]] = []
        self.cancelled: list[int] = []
        self._next_id = 0

    def state(self):
        return self._state

    def winfo_screenwidth(self):
        return self._screen[0]

    def winfo_screenheight(self):
        return self._screen[1]

    def after(self, ms, cb):
        self._next_id += 1
        job = self._next_id
        self.after_calls.append((ms, cb, job))
        return job

    def after_cancel(self, job):
        self.cancelled.append(job)


class FakeEvent:
    def __init__(self, widget, width, height):
        self.widget = widget
        self.width = width
        self.height = height


class FakeGui:
    """Duck-typed ``PainterGui`` stand-in carrying just the attributes
    ``_on_root_configure``/``_resize_settled`` touch."""

    def __init__(self, root, win_state=None, win_size=(0, 0)):
        self.root = root
        self._win_state = win_state if win_state is not None else root.state()
        self._win_size = win_size
        self._resize_active = False
        self._resize_settle_job = None
        self._pending_events: list[tuple] = []
        self.dispatched: list = []

    def _dispatch(self, msg):
        self.dispatched.append(msg)

    def _resize_settled(self):
        """Real implementation, delegated — ``_on_root_configure`` only
        ever stores this as a callback reference in these tests (it is
        never actually invoked by the fake ``root.after``), but it must
        exist as a genuine bound method for that reference to resolve."""
        return gui.PainterGui._resize_settled(self)


# --- child-widget events are ignored ------------------------------------


def test_child_widget_configure_is_ignored():
    root = FakeRoot()
    fake = FakeGui(root, win_state="normal", win_size=(100, 100))
    other_widget = object()
    gui.PainterGui._on_root_configure(
        fake, FakeEvent(other_widget, 999, 999)
    )
    assert fake._win_state == "normal"
    assert fake._win_size == (100, 100)
    assert fake._resize_active is False
    assert root.after_calls == []


# --- the maximize/restore state jump: bookkeeping ONLY, no cover --------


def test_maximize_updates_bookkeeping_and_never_arms_the_resize_timer():
    root = FakeRoot(state="zoomed")  # the WM already resized us
    fake = FakeGui(root, win_state="normal", win_size=(900, 640))
    gui.PainterGui._on_root_configure(
        fake, FakeEvent(root, 3840, 2071)
    )
    assert fake._win_state == "zoomed"
    assert fake._win_size == (3840, 2071)
    # NOT treated as a continuous drag — no settle timer, no buffering
    assert fake._resize_active is False
    assert root.after_calls == []


def test_restore_updates_bookkeeping_and_never_arms_the_resize_timer():
    root = FakeRoot(state="normal")
    fake = FakeGui(root, win_state="zoomed", win_size=(3840, 2071))
    gui.PainterGui._on_root_configure(
        fake, FakeEvent(root, 900, 640)
    )
    assert fake._win_state == "normal"
    assert fake._win_size == (900, 640)
    assert fake._resize_active is False
    assert root.after_calls == []


# --- a continuous drag (same state, size changing) ----------------------


def test_same_state_size_change_arms_the_settle_timer():
    root = FakeRoot(state="normal")
    fake = FakeGui(root, win_state="normal", win_size=(900, 640))
    gui.PainterGui._on_root_configure(
        fake, FakeEvent(root, 950, 640)
    )
    assert fake._win_size == (950, 640)
    assert fake._resize_active is True
    assert len(root.after_calls) == 1
    ms, cb, _job = root.after_calls[0]
    assert ms == RESIZE_SETTLE_MS
    assert cb == fake._resize_settled


def test_a_second_configure_mid_drag_cancels_and_rearms_the_settle_timer():
    root = FakeRoot(state="normal")
    fake = FakeGui(root, win_state="normal", win_size=(900, 640))
    gui.PainterGui._on_root_configure(fake, FakeEvent(root, 950, 640))
    first_job = fake._resize_settle_job
    gui.PainterGui._on_root_configure(fake, FakeEvent(root, 960, 640))
    assert root.cancelled == [first_job]
    assert len(root.after_calls) == 2


def test_same_state_same_size_is_a_pure_move_and_does_nothing():
    root = FakeRoot(state="normal")
    fake = FakeGui(root, win_state="normal", win_size=(900, 640))
    gui.PainterGui._on_root_configure(fake, FakeEvent(root, 900, 640))
    assert fake._resize_active is False
    assert root.after_calls == []


# --- _resize_settled: flush buffered events in arrival order ------------


def test_resize_settled_flushes_pending_events_in_order_and_clears_state():
    root = FakeRoot()
    fake = FakeGui(root)
    fake._resize_active = True
    fake._resize_settle_job = 42
    fake._pending_events = [("__event__", "chatgpt", {"n": 1}),
                             ("__event__", "gemini", {"n": 2})]
    gui.PainterGui._resize_settled(fake)
    assert fake._resize_settle_job is None
    assert fake._resize_active is False
    assert fake._pending_events == []
    assert fake.dispatched == [
        ("__event__", "chatgpt", {"n": 1}),
        ("__event__", "gemini", {"n": 2}),
    ]


# --- _clamp_geometry: unrelated to the maximize bug, still exercised ----


def test_clamp_geometry_leaves_a_small_geometry_untouched():
    root = FakeRoot(screen=(1920, 1080))
    fake = FakeGui(root)
    assert gui.PainterGui._clamp_geometry(fake, "900x640+80+80") == "900x640+80+80"


def test_clamp_geometry_shrinks_an_oversized_geometry_to_the_screen():
    root = FakeRoot(screen=(1920, 1080))
    fake = FakeGui(root)
    out = gui.PainterGui._clamp_geometry(fake, "3000x2000+0+0")
    assert out.startswith("1840x1000")  # screen - WINDOW_SCREEN_MARGIN_PX


def test_clamp_geometry_pulls_an_offscreen_position_back_on_screen():
    root = FakeRoot(screen=(1920, 1080))
    fake = FakeGui(root)
    out = gui.PainterGui._clamp_geometry(fake, "900x640+5000+5000")
    # x/y clamped so the window still fits on screen
    assert out == "900x640+1020+440"


def test_clamp_geometry_passes_through_an_unparsable_string():
    root = FakeRoot(screen=(1920, 1080))
    fake = FakeGui(root)
    assert gui.PainterGui._clamp_geometry(fake, "not-a-geometry") == (
        "not-a-geometry"
    )
