"""Make the painter package importable from any pytest invocation."""

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))


@pytest.fixture(scope="session")
def tk_root():
    """ONE real (withdrawn, never mapped/mainloop'd) Tk root, shared by
    every test in the session that needs to construct an actual gui.py
    widget (GUI rework Phase 4 on: gui.py is otherwise tested via pure
    helpers + fakes, see test_smooth_transition.py/test_viewer.py).

    gui.py's icon() cache (``_ICONS``) is process-lifetime and ties
    each cached CTkImage's underlying Tk PhotoImage to the Tcl
    interpreter that was live when it was first rendered — exactly
    like the real app, which only ever constructs ONE root for its
    whole run. A second, independently created-and-destroyed root
    would try to reuse those cached images against a DIFFERENT (or by
    then already-torn-down) interpreter and raise ``TclError: image
    "pyimageN" doesn't exist`` — confirmed by hand while writing the
    Phase 4 FilterEditor tests. Sharing this ONE session-scoped root
    sidesteps it, and matches production reality besides."""
    import ttkbootstrap as tb

    root = tb.Window(themename="darkly")
    root.withdraw()
    _ROOT_HOLDER.append(root)
    yield root
    _ROOT_HOLDER.clear()
    root.destroy()


# the live shared root, for the per-module handle reclaim below —
# empty until (and unless) some test asked for tk_root at all
_ROOT_HOLDER: list = []


@pytest.fixture(autouse=True, scope="module")
def _reclaim_tk_handles():
    """Destroy every widget left on the shared root after each test
    MODULE (F2 session, 2026-07-29). Windows never reclaims a menu
    handle while its Menu widget lives, and the GUI suite leaks one
    dropdown Menu per CTk combobox it constructs — enough modules in
    ONE pytest process used to hit the OS ceiling loudly
    ('_tkinter.TclError: No more menus can be allocated', 5 tests +
    1 error before this fixture). Destroying the widgets frees the
    handles; the session root itself (and gui.py's process-lifetime
    icon cache, which lives on it — see tk_root above) stays alive."""
    yield
    for root in _ROOT_HOLDER:
        for child in list(root.winfo_children()):
            try:
                child.destroy()
            except Exception:
                pass  # a test may have destroyed its own widgets
