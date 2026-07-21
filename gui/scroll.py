"""ScrollFrame — a vertically (optionally also horizontally) scrollable
frame: event-driven fill-height (recomputed from the events that
actually change content/viewport height, plus an explicit ``refresh()``
call after a structural change no caller's own ``<Configure>`` would
catch), resize-debounced re-fit (a window drag applies its width/
height/scrollregion pass ONCE, on settle) and mouse-wheel binding
scoped to hover.

Split out of gui/__init__.py (Rule #3, god-file refactor step 2/8)."""

from __future__ import annotations

import tkinter as tk
from tkinter import ttk

from painter.config import RESIZE_SETTLE_MS

from .theme import skin_canvas


WHEEL_DELTA_UNIT = 120      # one mouse-wheel notch (event.delta per detent)



class ScrollFrame(ttk.Frame):
    """A vertically (optionally also horizontally) scrollable frame.

    Add children to ``self.body``. Without horizontal scroll the body
    is stretched to the canvas width (content wraps, no x scrollbar);
    with it the body keeps its natural width and a horizontal bar
    appears.

    ``fill_height=True`` additionally keeps the body at least as tall
    as the canvas (``_apply_fill_height``) so a short window can always
    reach the true bottom of the content by scrollbar or wheel. This
    used to be self-healed by a perpetual ``after()`` poll (owner
    2026-07-21 workflow fix) that re-checked the fit every
    ``SCROLL_FILL_HEIGHT_POLL_MS`` forever, even fully idle — the
    owner's own "scroll renders so badly it's horrible" report (owner
    2026-07-21, workflow-fix follow-up): a constant background timer
    competing with the UI thread's paint/event work. Replaced with
    PURE events (owner 2026-07-21, perf fix): the re-fit fires from
    ``<Configure>`` on the canvas (a real viewport resize) and the body
    (nested content naturally growing) exactly as before, PLUS an
    explicit ``refresh()`` call at every structural change that the
    poll used to catch instead — a Settings-gear/Advanced-section
    reveal nested arbitrarily deep below this ScrollFrame, wired
    through each panel's own ``on_layout_change`` callback (see
    ``AgentPanel``/``ToolSettingsPanel``). No timer runs when idle.
    """

    def __init__(
        self, master, horizontal: bool = False, fill_height: bool = False
    ):
        super().__init__(master)
        self._stretch = not horizontal
        # fill_height: keep the body AT LEAST as tall as the canvas, so a
        # child packed expand=True (the notebook) fills the whole viewport
        # when the content is shorter than the window (see
        # _apply_fill_height) — event-driven re-fit, see the class
        # docstring above (refresh()/on_layout_change for nested reveals).
        self._fill_height = fill_height
        self._fill_h = 0  # last forced body height (change-guarded loop break)
        self._sr_job = None  # coalesced scrollregion pass (see _on_body)
        self._sr_suspended = False  # bulk-build pause (see suspend_...)
        self._resizing = False  # active window-resize debounce (see _on_canvas)
        self._settle_job = None  # the resize-settle after() id
        self._canvas_w = 0   # the newest canvas width (from <Configure>)
        self._applied_w = -1  # the body width actually applied (deferred)
        self.canvas = tk.Canvas(self, highlightthickness=0)
        skin_canvas(self.canvas)  # registered so its bg re-tints on a flip
        vbar = ttk.Scrollbar(
            self, orient="vertical", command=self.canvas.yview,
            bootstyle="round",
        )
        self.canvas.configure(yscrollcommand=vbar.set)
        self.body = ttk.Frame(self.canvas)
        self._win = self.canvas.create_window(
            (0, 0), window=self.body, anchor="nw"
        )
        self.body.bind("<Configure>", self._on_body)
        self.canvas.bind("<Configure>", self._on_canvas)
        vbar.pack(side="right", fill="y")
        if horizontal:
            hbar = ttk.Scrollbar(
                self, orient="horizontal", command=self.canvas.xview,
                bootstyle="round",
            )
            self.canvas.configure(xscrollcommand=hbar.set)
            hbar.pack(side="bottom", fill="x")
        self.canvas.pack(side="left", fill="both", expand=True)
        self.canvas.bind("<Enter>", self._bind_wheel)
        self.canvas.bind("<Leave>", self._unbind_wheel)
        # a global <MouseWheel> binding outlives the widget — drop it
        # when the canvas is destroyed (e.g. the Select window closes
        # while the pointer is still over it) so it never fires on a
        # dead widget; and cancel any pending scrollregion pass
        self.canvas.bind("<Destroy>", self._on_destroy)
        # fill_height's first real fit runs off the canvas's OWN initial
        # <Configure> (every Tk widget gets one on first map) via
        # _on_canvas below — no separate construction-time kick needed.

    def _on_body(self, _event) -> None:
        # COALESCE: one expand that grids dozens of children fires a
        # <Configure> per child — recomputing bbox('all') each time is
        # O(N^2). Instead flag one after_idle pass and let the whole
        # settled layout be scanned exactly ONCE.
        if self._sr_suspended or self._resizing or self._sr_job is not None:
            return
        self._sr_job = self.after_idle(self._recompute_sr)

    def suspend_scrollregion(self) -> None:
        """Pause the per-settle scrollregion recompute for a bulk build.
        Each ``bbox('all')`` scan is O(current content); across a chunked
        Expand-all that is one growing scan PER TICK. Suspend during the
        build, ``resume_scrollregion`` once at the end for a SINGLE scan."""
        self._sr_suspended = True

    def resume_scrollregion(self) -> None:
        if not self._sr_suspended:
            return
        self._sr_suspended = False
        if self._sr_job is None:
            self._sr_job = self.after_idle(self._recompute_sr)

    def _recompute_sr(self) -> None:
        self._sr_job = None
        self._apply_fill_height()
        try:
            self.canvas.configure(scrollregion=self.canvas.bbox("all"))
        except tk.TclError:
            pass  # canvas destroyed between the schedule and the pass

    def _apply_fill_height(self) -> None:
        """Stretch the body window to at least the canvas height so a
        child packed expand=True fills the viewport even when the content
        is shorter than the window. The change-guard (target != self._fill_h)
        is REQUIRED: forcing the window height re-fires the body's
        <Configure>, and re-applying an unchanged height would loop —
        reqheight is driven by child requests and is invariant under the
        forced allocated height, so a single settle converges."""
        if not self._fill_height:
            return
        try:
            target = max(
                self.canvas.winfo_height(), self.body.winfo_reqheight()
            )
            if target != self._fill_h:
                self._fill_h = target
                self.canvas.itemconfigure(self._win, height=target)
        except tk.TclError:
            pass  # canvas destroyed between the schedule and the pass

    def refresh(self) -> None:
        """Re-fit after a structural change (collapse/expand) — coalesced
        like _on_body so a burst of changes triggers one settle. This is
        the explicit event side of fill_height's re-fit: once
        ``_apply_fill_height`` has ever forced ``body``'s actual height
        via canvas ``itemconfigure``, body's OWN ``<Configure>`` stops
        firing from nested content simply growing (the canvas now
        dictates body's real size, decoupled from its children's
        pack-driven request) — so any widget that reveals/hides content
        UNDER a fill_height ScrollFrame (a Settings-gear or Advanced-
        section toggle, arbitrarily deep in the tree) MUST call this
        (or a callback wired to it, e.g. ``on_layout_change``) after the
        reveal. No poll backstops a caller that forgets — see the class
        docstring's 2026-07-21 perf-fix note."""
        if self._sr_job is None:
            self._sr_job = self.after_idle(self._recompute_sr)

    def _on_destroy(self, event) -> None:
        if self._sr_job is not None:
            self.after_cancel(self._sr_job)
            self._sr_job = None
        if self._settle_job is not None:
            self.after_cancel(self._settle_job)
            self._settle_job = None
        self._unbind_wheel(event)

    def _on_canvas(self, event) -> None:
        # DEBOUNCE (owner 2026-07-19; width deferred too 2026-07-20): a
        # window drag / maximize fires <Configure> many times a second.
        # Running the fill-height + scrollregion bbox scan on EACH was
        # the original customtkinter re-render jank; the per-frame body
        # WIDTH itemconfigure that survived that first round was the
        # rest of it — every width write reflows the body and fires a
        # <Configure> into each CTk child (measured over a synthetic
        # 30-step drag: 30 width writes -> 55 CTk _draw re-renders;
        # deferring the width drops both to 0 during the drag). So
        # while a resize is underway NOTHING is applied — the newest
        # width is only remembered — and the whole re-fit (width +
        # fill-height + scrollregion) runs ONCE on settle. The FIRST
        # configure of a SETTLED window (initial layout / a lone
        # resize) still applies immediately so the viewport never opens
        # with a dead strip. Trade-off (owner accepted 2026-07-20): mid
        # drag the content freezes at its pre-drag width — a window-bg
        # strip grows (or the content clips) at the right edge — and
        # snaps to fit RESIZE_SETTLE_MS after release.
        self._canvas_w = event.width
        if not self._resizing:
            self._apply_width()
            self._apply_fill_height()
        self._arm_settle()

    def _apply_width(self) -> None:
        """Stretch the body window to the newest canvas width — only on
        a real change (the write itself is what reflows the body)."""
        if self._stretch and self._canvas_w != self._applied_w:
            self._applied_w = self._canvas_w
            self.canvas.itemconfigure(self._win, width=self._canvas_w)

    def _arm_settle(self) -> None:
        """Flag an active resize and (re)start the settle timer. Gates
        ``_on_body``'s per-<Configure> scheduling; the heavy re-fit is
        deferred to ``_settle`` (RESIZE_SETTLE_MS after the LAST
        <Configure> — 'wait for mouse release')."""
        self._resizing = True
        if self._settle_job is not None:
            self.after_cancel(self._settle_job)
        self._settle_job = self.after(RESIZE_SETTLE_MS, self._settle)

    def _settle(self) -> None:
        """The size settled — clear the resize flag, apply the deferred
        body width, and run ONE re-fit (fill-height + scrollregion),
        coalesced like ``_on_body``."""
        self._settle_job = None
        self._resizing = False
        self._apply_width()
        if self._sr_job is None:
            self._sr_job = self.after_idle(self._recompute_sr)

    def _bind_wheel(self, _event) -> None:
        self.canvas.bind_all("<MouseWheel>", self._on_wheel)

    def _unbind_wheel(self, _event) -> None:
        try:
            self.canvas.unbind_all("<MouseWheel>")
        except tk.TclError:
            pass

    def _on_wheel(self, event) -> None:
        try:
            self.canvas.yview_scroll(
                int(-event.delta / WHEEL_DELTA_UNIT), "units"
            )
        except tk.TclError:
            # the canvas was destroyed but the global binding lingered
            self.canvas.unbind_all("<MouseWheel>")

