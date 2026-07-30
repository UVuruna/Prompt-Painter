"""Sizing rules and the tiny read-only-window helpers every viewer
Toplevel shares (root Rule #20 god-file split of ``gui/viewers.py``,
2026-07-30 — one window family per module now: ``gui.doc_window``,
``gui.restore_windows``, ``gui.image_viewer``).

A leaf module: plain tkinter only, no other ``gui`` submodule, so
every viewer can import it without a cycle. ``gui.select_window``
reads the same DOC_* clamps — the single "never bigger than this"
rule for any window the app opens.
"""

from __future__ import annotations

import tkinter as tk
from tkinter import messagebox

# --- Shared window sizing (Rule #4) -----------------------------------
# The old DocWindow sized its WIDTH from the single longest line, so a
# ~200-word prompt on ONE line blew the window to near-full-screen with
# the text on one enormous line. Two modes replace that:
#   IMAGE mode (a single image's prompt viewer, image_path set): width
#     follows the IMAGE — native width + padding, clamped to the screen —
#     so the picture shows large and the prompt WRAPS into that column.
#   TEXT mode (instructions / whole collection / folder excerpt): a
#     portrait A4 proportion, so long one-line prompts wrap into a
#     readable column instead of stretching the window.
# DOC_MAX_FRAC also clamps the Select window and every doc window to a
# fraction of the screen (the single "never bigger than this" rule).
# DOC_IMG_PAD_PX/DOC_CHROME_PAD_PX are DocWindow's own, kept with the
# family so the sizing rules read as one block.
DOC_A4_RATIO = 210 / 297    # ISO A4 portrait width:height (~0.707)
DOC_HEIGHT_FRAC = 0.8       # A4 text height (and the Select tall height) = screen_h * this
DOC_MAX_FRAC = 0.9          # clamp ANY window to this fraction of the screen
DOC_MIN_W = 520             # never narrower than this (the top button bar fits)
DOC_MIN_H = 400             # never shorter than this (also the provisional height)
DOC_IMG_PAD_PX = 60         # horizontal padding around the image column (image mode)
DOC_CHROME_PAD_PX = 48      # non-text vertical chrome: Text pady + frame margins


def _copy_to_clipboard(widget: tk.Misc, text: str) -> None:
    """Clipboard copy + confirmation dialog — shared (Rule #5) by
    DocWindow's 'Copy (for AI)' button and ImageViewer's own prompt
    copy button."""
    widget.clipboard_clear()
    widget.clipboard_append(text)
    messagebox.showinfo(
        "PromptPainter",
        "Copied to the clipboard — paste it to your AI or into a"
        " document.",
        parent=widget,
    )


def _readonly_text_keys(event):
    """Block edits on a read-only Text while keeping copy/select-all and
    navigation working — shared (Rule #5) by every plain-tk Text the
    viewers render read-only (DocWindow's body, ImageViewer's prompt and
    Check blocks)."""
    if event.state & 0x4 and event.keysym.lower() in ("c", "a"):
        return
    if event.keysym in (
        "Left", "Right", "Up", "Down", "Home", "End", "Prior", "Next",
    ):
        return
    return "break"


def _restore_step(temp: "jobtemp.JobTemp", rel: str, step: str) -> bool:
    """Restore ``rel`` to its state right before pipeline ``step`` ran —
    the ONE call ``StepRestoreWindow._do_restore`` and ``ImageViewer``'s
    own Steps section both fire (Rule #5, extracted so neither
    re-implements ``JobTemp.restore_to``'s call site; see
    ``gui.app_settings``'s ``ImageViewer`` wiring, which reaches this
    through the ``restore_cb`` it builds for a dashboard-opened image)."""
    return temp.restore_to(rel, step=step)
