"""The two RESTORE viewers (root Rule #20 god-file split of
``gui/viewers.py``, 2026-07-30) — one cohesive pair: both show what an
image looked like BEFORE a pipeline step and put it back.

* ``BeforeAfterWindow`` — a standalone tool job's before/after viewer
  (the tool panels' Restore door), stacked single column.
* ``_filmstrip_stages`` — the pure per-image pipeline-stage list
  (``(label, path)`` pairs, oldest first, ending with the live file),
  shared with ``ImageViewer``'s own Steps section.
* ``StepRestoreWindow`` — the per-step restore filmstrip built from it
  (GUI rework Phase 9), horizontal.
"""

from __future__ import annotations

import tkinter as tk
from functools import partial
from pathlib import Path
from tkinter import ttk
from typing import Callable

from painter.config import JOBTEMP_STEP_LABEL, STEP_RESTORE_CURRENT_LABEL
from .dash_helpers import _scaled_photo
from .scroll import ScrollFrame
from .theme import THEME_TOPLEVELS, skin_toplevel
from .viewer_shared import (
    DOC_HEIGHT_FRAC,
    DOC_MAX_FRAC,
    DOC_MIN_H,
    DOC_MIN_W,
    _restore_step,
)
from .widgets import rounded_button, wrap_bar_label

# --- Before/after viewer (the tool panels' Restore viewer) ------------
BEFORE_AFTER_W = 760          # viewer width; before/after images scale into it
BEFORE_AFTER_IMG_PAD_PX = 60  # slack subtracted from the width for the images

# --- Per-step restore viewer (GUI rework Phase 9) ---------------------
# a horizontal filmstrip, so its own width geometry is independent of
# BEFORE_AFTER_W's stacked single-column layout.
STEP_RESTORE_W = 900        # viewer width; grows via horizontal scroll past this
STEP_RESTORE_THUMB_PX = 220  # each stage thumbnail's max width


class BeforeAfterWindow(tk.Toplevel):
    """A BEFORE/AFTER viewer for one in-place tool job.

    SINGLE mode (one image) stacks its before + after with a **Restore**
    button; MULTI mode scrolls every changed image of the job with a
    **RESTORE ALL** button. The same viewer style as DocWindow's
    single-image prompt view (a double-click opens it). Themed like the
    app (skinned Toplevel + registered in ``THEME_TOPLEVELS`` so a
    Day/Night flip re-tints it, unregistered on ``<Destroy>``); every
    scaled PhotoImage is held on ``self._photos`` so tk cannot GC it.
    """

    def __init__(
        self, master, title, pairs, *, restore_label, restore_cb,
        subtitle=None,
    ):
        super().__init__(master)
        self.title(title)
        self.minsize(DOC_MIN_W, DOC_MIN_H)
        skin_toplevel(self)  # bg registered so a flip re-tints the window
        THEME_TOPLEVELS.append(self)
        self._restore_cb = restore_cb
        self._photos: list = []  # keep the PhotoImages alive

        width = min(
            int(self.winfo_screenwidth() * DOC_MAX_FRAC),
            max(BEFORE_AFTER_W, DOC_MIN_W),
        )
        height = min(
            max(int(self.winfo_screenheight() * DOC_HEIGHT_FRAC), DOC_MIN_H),
            int(self.winfo_screenheight() * DOC_MAX_FRAC),
        )
        self.geometry(f"{width}x{height}")

        bar = ttk.Frame(self, padding=6)
        bar.pack(fill="x")
        if subtitle is None:
            subtitle = (
                "Before / after — Restore reverts this image to the"
                " original." if len(pairs) == 1 else
                "Before / after of every changed image — RESTORE ALL"
                " reverts the whole job."
            )
        subtitle_lbl = ttk.Label(bar, text=subtitle, style="Muted.TLabel")
        subtitle_lbl.pack(side="left")
        self._restore_btn = rounded_button(
            bar, restore_label, command=self._do_restore, kind="danger",
        )
        self._restore_btn.pack(side="right")
        close_btn = rounded_button(
            bar, "Close", icon_name="close", command=self.destroy,
        )
        close_btn.pack(side="right", padx=4)
        # THE SPACE & LEGIBILITY LAW (rules/GUI.md): the MULTI-mode
        # subtitle is long enough to overflow the window's declared
        # minimum on its own — wrap it into the bar's live remaining
        # width instead (ladder step 2, see gui.widgets.wrap_bar_label).
        wrap_bar_label(bar, subtitle_lbl, self._restore_btn, close_btn)

        self._scroll = ScrollFrame(self, horizontal=False)
        self._scroll.pack(fill="both", expand=True, padx=6, pady=(0, 6))
        avail = max(width - BEFORE_AFTER_IMG_PAD_PX, 320)
        self.update_idletasks()
        for pair in pairs:
            self._add_pair(pair, avail)

        self.bind("<Destroy>", self._on_destroy)

    def _add_pair(self, pair: dict, avail: int) -> None:
        block = ttk.Frame(self._scroll.body, padding=(4, 8))
        block.pack(fill="x", anchor="w")
        ttk.Label(block, text=pair["rel"], style="Head.TLabel").pack(
            anchor="w", pady=(0, 4)
        )
        for tag, path in (
            ("Before", pair["before"]), ("After", pair["after"])
        ):
            ttk.Label(block, text=tag, style="Muted.TLabel").pack(anchor="w")
            try:
                # composite over a checker so a cleared/transparent AFTER
                # reads as removed, not as the window colour
                photo = _scaled_photo(path, avail, on_checker=True)
            except OSError as exc:
                ttk.Label(
                    block, text=f"({tag} unreadable: {exc})"
                ).pack(anchor="w")
                continue
            self._photos.append(photo)
            lbl = ttk.Label(block, image=photo)
            lbl.image = photo  # belt-and-braces ref
            lbl.pack(anchor="w", pady=(0, 6))
        ttk.Separator(block).pack(fill="x", pady=(2, 0))

    def _do_restore(self) -> None:
        self._restore_cb()
        self._restore_btn.configure(state="disabled", text="Restored ✓")

    def apply_theme(self) -> None:
        # ttk children flip via styles; the toplevel + scroll canvas ride
        # the global recolour — nothing per-widget to redo here.
        pass

    def _on_destroy(self, event) -> None:
        if event.widget is self and self in THEME_TOPLEVELS:
            THEME_TOPLEVELS.remove(self)


def _filmstrip_stages(
    temp: "jobtemp.JobTemp", rel: str, live_path: Path,
) -> list[tuple[str, Path]]:
    """The ordered filmstrip ``StepRestoreWindow`` renders for one
    image (GUI rework Phase 9): one ``(label, path)`` pair per NAMED
    pipeline stage ``rel`` still holds a backup for — ``JobTemp.
    steps_for``'s own pipeline order (original -> bg -> crop -> aspect
    -> upscale -> fixer, filtered to whichever actually backed this
    rel up) — followed by exactly ONE final ``(STEP_RESTORE_CURRENT_
    LABEL, live_path)`` entry for the CURRENT live file.

    A caller that needs to know which JobTemp step name a 'Restore to
    here' button targets can zip ``stages[:-1]`` 1:1 against ``temp.
    steps_for(rel)`` — same order, same length; the filmstrip's own
    final entry has no step of its own (it already IS the live file,
    not a backup — see ``StepRestoreWindow._render``).

    Pure/Tk-free — no widget is touched, so a real (or a bare-bones
    fake exposing ``steps_for``/``before_path``) ``JobTemp`` is fully
    pytest-able headless, no display needed."""
    stages = [
        (JOBTEMP_STEP_LABEL[step], temp.before_path(rel, step=step))
        for step in temp.steps_for(rel)
    ]
    stages.append((STEP_RESTORE_CURRENT_LABEL, live_path))
    return stages


class StepRestoreWindow(tk.Toplevel):
    """The per-step restore filmstrip for ONE site-pipeline image (GUI
    rework Phase 9): every pipeline stage ``rel`` still holds a backup
    for, in order (Original -> BG -> Crop -> Aspect -> Upscale ->
    Fixer, whichever exist — see ``_filmstrip_stages``), each with its
    own **Restore to here** button, PLUS the CURRENT live file last (no
    button — it already IS the live state). Restoring calls ``JobTemp.
    restore_to(rel, step)`` and re-renders the filmstrip in place (the
    'Current' thumbnail and the remaining stage list update
    immediately from disk), then tells the caller via ``on_restored``
    so the dashboard row this viewer was opened from can re-read the
    now-restored file too (``DashPanel.refresh_image_row``).

    Non-modal, themed like ``BeforeAfterWindow`` (skinned Toplevel,
    registered in ``THEME_TOPLEVELS``, its scaled PhotoImages held on
    ``self._photos`` so tk cannot GC them) — a HORIZONTAL
    ``ScrollFrame`` instead of BeforeAfterWindow's stacked vertical
    one, since pipeline stages read left-to-right like a real
    filmstrip.
    """

    def __init__(
        self, master, title, temp: "jobtemp.JobTemp", rel: str,
        live_path: Path, *, on_restored: Callable[[], None] | None = None,
    ):
        super().__init__(master)
        self.title(title)
        self.minsize(DOC_MIN_W, DOC_MIN_H)
        skin_toplevel(self)  # bg registered so a flip re-tints the window
        THEME_TOPLEVELS.append(self)
        self._temp = temp
        self._rel = rel
        self._live_path = live_path
        self._on_restored = on_restored
        self._photos: list = []  # keep the PhotoImages alive

        width = min(
            int(self.winfo_screenwidth() * DOC_MAX_FRAC),
            max(STEP_RESTORE_W, DOC_MIN_W),
        )
        height = min(
            max(int(self.winfo_screenheight() * DOC_HEIGHT_FRAC), DOC_MIN_H),
            int(self.winfo_screenheight() * DOC_MAX_FRAC),
        )
        self.geometry(f"{width}x{height}")

        bar = ttk.Frame(self, padding=6)
        bar.pack(fill="x")
        hint_lbl = ttk.Label(
            bar,
            text="Every kept pipeline stage for this image — 'Restore"
            " to here' reverts the LIVE file to that stage.",
            style="Muted.TLabel",
        )
        hint_lbl.pack(side="left")
        close_btn = rounded_button(
            bar, "Close", icon_name="close", command=self.destroy,
        )
        close_btn.pack(side="right")
        # THE SPACE & LEGIBILITY LAW (rules/GUI.md): this hint alone
        # overflows the window's declared minimum — wrap it into the
        # bar's live remaining width (ladder step 2).
        wrap_bar_label(bar, hint_lbl, close_btn)

        self._scroll = ScrollFrame(self, horizontal=True)
        self._scroll.pack(fill="both", expand=True, padx=6, pady=(0, 6))
        self.update_idletasks()
        self._render()

        self.bind("<Destroy>", self._on_destroy)

    def _render(self) -> None:
        """(Re)build every stage block from the CURRENT on-disk state —
        called at construction and again after each restore, so the
        'Current' thumbnail and the remaining restorable stages always
        match what is actually on disk right now."""
        for child in self._scroll.body.winfo_children():
            child.destroy()
        self._photos.clear()
        stages = _filmstrip_stages(self._temp, self._rel, self._live_path)
        steps = self._temp.steps_for(self._rel)  # same order/len as stages[:-1]
        for i, (label, path) in enumerate(stages):
            step = steps[i] if i < len(steps) else None
            block = ttk.Frame(self._scroll.body, padding=8)
            block.pack(side="left", fill="y", anchor="n")
            ttk.Label(block, text=label, style="Head.TLabel").pack(anchor="w")
            try:
                # composite over a checker so a transparent intermediate
                # (a BG-removed stage) reads as removed, not as the
                # window colour — same fix as BeforeAfterWindow's
                photo = _scaled_photo(
                    path, STEP_RESTORE_THUMB_PX, on_checker=True
                )
            except OSError as exc:
                ttk.Label(
                    block, text=f"(unreadable: {exc})",
                    wraplength=STEP_RESTORE_THUMB_PX,
                ).pack(anchor="w")
                continue
            self._photos.append(photo)
            ttk.Label(block, image=photo).pack(pady=(4, 6))
            if step is not None:
                rounded_button(
                    block, "Restore to here", kind="danger",
                    icon_name="restore", command=partial(self._do_restore, step),
                ).pack()
            else:
                ttk.Label(block, text="(current)", style="Muted.TLabel").pack()

    def _do_restore(self, step: str) -> None:
        if _restore_step(self._temp, self._rel, step):
            self._render()
            if self._on_restored is not None:
                self._on_restored()

    def apply_theme(self) -> None:
        # ttk children flip via styles; the toplevel + scroll canvas ride
        # the global recolour — nothing per-widget to redo here (same as
        # BeforeAfterWindow).
        pass

    def _on_destroy(self, event) -> None:
        if event.widget is self and self in THEME_TOPLEVELS:
            THEME_TOPLEVELS.remove(self)
