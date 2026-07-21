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
    yield root
    root.destroy()
