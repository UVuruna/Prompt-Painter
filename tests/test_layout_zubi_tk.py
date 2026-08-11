"""Zubi v2 — the Tk rollout entry (owner's order 2026-08-11, after the
BobaFett_v2 refused-view shots shipped through the pre-v2 audit).

Runs the algorithmic checks in ``layout_checks_tk`` (ALG-5 uniform
siblings, ALG-6 radius tiers, ALG-7 empty band) over the SAME window
registry the Space & Legibility audit already builds — plus the
LONG-CONTENT ImageViewer case the old fixtures missed: a refused entry
carrying a real multi-paragraph refusal + WHY diagnosis (the exact
content class whose clipping the owner had to report by hand).

Also carries the mandatory GUARD SELF-TEST (MIGRATE-LAYOUT Step 5.3):
a permanently planted violation window that the checks MUST flag —
a guard never seen failing reports success by never running.
"""

from __future__ import annotations

import tkinter as tk
from tkinter import ttk

import test_layout_audit_tk as base
from layout_checks_tk import (
    check_empty_band,
    check_uniform_siblings,
    run_zubi,
)


LONG_REFUSAL = (
    "REFUSED — Gemini: prompt refused [safety] (matched 'go against my"
    " guidelines'): Gemini said\n\nI can help with many kinds of"
    " requests, but it appears this one would go against my guidelines."
    " Is there something else I can try for you?\n\n"
    "WHY (site's own answer):\nGemini said\n\n"
    "I declined the request due to the combination of elements"
    " describing the central figure: \"masked bounty hunter standing"
    " motionless in scarred clan-forged armor\" and \"visored helm.\""
    " These specific descriptors, in combination, too closely resemble"
    " existing copyrighted characters and established intellectual"
    " property (specifically from the Star Wars franchise)."
)
LONG_PROMPT = (
    "ROUND medallion, aged bronze relief, photorealistic render,"
    " isolated background, the circular shape IS the frame. " * 4
)


def _refused_viewer_win(gui, tmp_path):
    """The long-refusal ImageViewer — the fixture gap that let the
    owner's screenshots through: content class = LONG text, no image."""
    from gui.image_viewer import ImageViewer

    entries = [{
        "title": "BobaFett_v2", "drop_path": "a/BobaFett_v2.png",
        "rel": None, "dest": None, "prompt": LONG_PROMPT,
        "refused_reason": LONG_REFUSAL,
    }]
    return ImageViewer(gui.root, entries, 0)


def test_zubi_v2_windows(tk_root, tmp_path) -> None:
    """Every registered window + the long-refusal viewer, at minimum
    and minimum+50%, through the Zubi v2 Tk checks."""
    from gui.app import PainterGui
    from gui import app_settings

    was_withdrawn = tk_root.state() == "withdrawn"
    if was_withdrawn:
        tk_root.deiconify()
    tk_root.geometry("+9000+40")
    tk_root.attributes("-alpha", 0.0)
    orig_save = app_settings.save_settings
    app_settings.save_settings = lambda *_a, **_kw: None
    problems: list[str] = []
    try:
        gui = PainterGui(tk_root)
        tk_root.update_idletasks()
        tk_root.update()
        min_w, min_h = tk_root.wm_minsize()
        for view in base.VIEWS:
            gui._set_view(view)
            for size_label, w, h in (
                ("minimum", min_w, min_h),
                ("minimum+50%", int(min_w * 1.5), int(min_h * 1.5)),
            ):
                base.settle(tk_root, w, h)
                problems += run_zubi(
                    tk_root, f"PainterGui/{view} @ {size_label}"
                )
        registry = base.DIALOG_WINDOWS + (
            ("ImageViewer(long refusal)", False, _refused_viewer_win),
        )
        with base._OffscreenToplevels():
            for name, fixed, builder in registry:
                win = builder(gui, tmp_path)
                win.update_idletasks()
                win.update()
                d_w, d_h = base._effective_minimum(win)
                sizes = [("minimum", d_w, d_h)]
                if not fixed:
                    sizes.append(
                        ("minimum+50%", int(d_w * 1.5), int(d_h * 1.5))
                    )
                for size_label, w, h in sizes:
                    base.settle(win, w, h)
                    problems += run_zubi(win, f"{name} @ {size_label}")
                win.destroy()
    finally:
        app_settings.save_settings = orig_save
        for child in list(tk_root.winfo_children()):
            try:
                child.destroy()
            except tk.TclError:
                pass
        if was_withdrawn:
            tk_root.withdraw()
    assert not problems, (
        "Zubi v2 (rules/GUI.md) - algorithmic checks failed:\n  "
        + "\n  ".join(problems)
    )


def test_zubi_self_test_catches_planted_violations(tk_root) -> None:
    """MIGRATE-LAYOUT Step 5.3: the checks are SHOWN failing on real
    planted violations — uneven sibling buttons in one row, and a
    scrolling Text under a dead band of empty space."""
    win = tk.Toplevel(tk_root)
    win.withdraw()
    win.geometry("500x600+9000+40")
    win.attributes("-alpha", 0.0)
    win.deiconify()
    row = ttk.Frame(win)
    row.pack(anchor="nw")
    tk.Button(row, text="ok", height=1).pack(side="left")
    tk.Button(row, text="tall", height=4).pack(side="left")
    txt = tk.Text(win, height=2)
    txt.insert("1.0", "line\n" * 40)
    txt.pack(anchor="nw", fill="x")
    # the rest of the 600px window stays EMPTY below the 2-row Text
    win.update_idletasks()
    win.update()
    try:
        assert check_uniform_siblings(win, "plant"), (
            "ALG-5 failed to flag two side-by-side buttons of visibly"
            " different heights"
        )
        assert check_empty_band(win, "plant"), (
            "ALG-7 failed to flag a scrolling Text under a dead band of"
            " empty window space"
        )
    finally:
        win.destroy()
