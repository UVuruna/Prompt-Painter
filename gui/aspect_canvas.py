"""``AspectRatioCanvas`` — the visual target-ratio editor (GUI rework
Phase 5) — pulled out of ``gui/__init__.py`` (god-file refactor, Rule
#20). Pure Tk pixel geometry only: the engine-pure
``ASPECT_LABEL_DECIMALS`` (the live label's rounding) lives in
``painter/config.py`` beside the rest of the aspect constants,
alongside the pure ``reduced_ratio``/``decimal_ratio_label`` functions
themselves (``painter/aspect.py``) — this widget only draws. Colours
are NEVER hardcoded here — ``job_color("aspect")``/``THEMES`` are read
live at draw time, same as every other themed canvas
(``DayNightSwitch``). A FIXED pixel size (it does not track the font
zoom, like the switch).
"""

from __future__ import annotations

import tkinter as tk
from typing import Callable

from painter import aspect
from painter.config import ASPECT_DEFAULT_H, ASPECT_DEFAULT_W, THEMES

from . import widgets
from .theme import skin_canvas
from .widgets import job_color, tk_font

ASPECT_CANVAS_BOX_PX = 200         # arena side — max span either axis can draw
ASPECT_CANVAS_PAD_PX = 26          # margin around the arena (handles + labels)
ASPECT_CANVAS_MIN_PX = 28          # a dragged side never collapses below this
ASPECT_CANVAS_EDGE_GRAB_PX = 10    # hit-test tolerance to start an edge drag
ASPECT_CANVAS_HANDLE_R = 5         # edge-handle marker circle radius
ASPECT_CANVAS_OUTLINE_W = 3        # ratio-box outline stroke width
ASPECT_CANVAS_LABEL_GAP_PX = 10    # gap between the arena and the dual label
ASPECT_CANVAS_LABEL_RESERVE_PX = 24  # vertical space reserved for the label


class AspectRatioCanvas(tk.Canvas):
    """A live, draggable preview of the TARGET output ratio (GUI rework
    Phase 5) — separate from Phase 4's ``FilterEditor`` (which picks
    WHICH images a tool touches); this widget shapes WHAT ratio the
    tool deforms them TO. A rectangle, centred in a fixed square arena,
    represents ``w:h``; grabbing any of its 4 edges reshapes it — LEFT/
    RIGHT change WIDTH, TOP/BOTTOM change HEIGHT, the box always stays
    CENTRED so one half-distance-from-centre formula covers all four. A
    live label below shows BOTH forms: the decimal
    (``aspect.decimal_ratio_label`` — owner-decision standard rounding,
    e.g. "1.778:1") and the smallest-integer form
    (``aspect.reduced_ratio``, e.g. "16:9").

    Public API: ``set_ratio(w, h)`` — a PROGRAMMATIC reshape (e.g. the
    dialog's W/H entries) that re-FITS the box to the arena (the larger
    side exactly fills it); and the ``on_change(w, h)`` callback, fired
    once per drag tick that actually changes the rounded ratio, so the
    caller can mirror it into its own fields. ``set_ratio`` no-ops when
    passed the SAME ``(w, h)`` it already holds — the echo a drag's own
    ``on_change`` round-trips back through the caller's entry-var trace
    — so a live drag never gets yanked back into a box-edge "fit" snap
    mid-gesture.

    A FIXED pixel size (like ``DayNightSwitch``, it does not track the
    font zoom — once is enough). Its background is a ``skin_canvas``
    surface (re-tints automatically on a flip); its DRAWN content (box,
    handles, label) is NOT part of that background-only registry, so it
    exposes ``redraw_theme()`` for a host to call explicitly. Both of
    today's hosts are non-modal, LIVE parts of the main window — each
    calls ``redraw_theme()`` from ITS OWN ``apply_theme()``, registered
    in ``THEME_TOPLEVELS`` (the pattern every other themed Toplevel
    already follows): ``AgentPanel``'s Force Aspect Ratio block (GUI
    rework Phase 8) and ``AspectSettingsPanel`` (GUI rework Phase 14,
    replacing the old fully-modal ``AspectRatioDialog``, which never
    needed this — a flip cannot happen while a ``grab_set`` dialog is
    open)."""

    def __init__(
        self,
        master,
        w: int = ASPECT_DEFAULT_W,
        h: int = ASPECT_DEFAULT_H,
        on_change: Callable[[int, int], None] | None = None,
    ):
        box, pad = ASPECT_CANVAS_BOX_PX, ASPECT_CANVAS_PAD_PX
        width = box + 2 * pad
        height = (
            box + 2 * pad
            + ASPECT_CANVAS_LABEL_GAP_PX + ASPECT_CANVAS_LABEL_RESERVE_PX
        )
        super().__init__(
            master, width=width, height=height, highlightthickness=0, bd=0,
        )
        skin_canvas(self)  # background follows the window bg on a flip
        self._on_change = on_change
        self._cx = pad + box / 2
        self._cy = pad + box / 2
        # NOTE: NOT named self._w/self._h — tkinter's own BaseWidget
        # already owns self._w (the widget's Tcl path string); shadowing
        # it breaks every canvas method (create_*, delete, ...) that
        # calls into Tcl through it. self._ratio_w/_h are the target
        # ratio's own width/height units instead.
        self._ratio_w = max(int(w), 1)
        self._ratio_h = max(int(h), 1)
        self._px_per_unit = 1.0
        self._rect_w_px = 0.0
        self._rect_h_px = 0.0
        self._drag_edge: str | None = None  # "left"/"right"/"top"/"bottom"
        self._fit_to_box()

        self.bind("<ButtonPress-1>", self._on_press)
        self.bind("<B1-Motion>", self._on_drag)
        self.bind("<ButtonRelease-1>", self._on_release)
        self.bind("<Motion>", self._on_hover)
        self.redraw_theme()

    # --- geometry --------------------------------------------------------

    def _fit_to_box(self) -> None:
        """Recompute the render scale so the LARGER side exactly fills
        the arena (``ASPECT_CANVAS_BOX_PX``) and the smaller side shrinks
        proportionally — the "contain fit" every programmatic set_ratio
        re-applies. A live drag does NOT call this (see ``_on_drag``), so
        the box only re-snaps to the arena edge on the NEXT programmatic
        value, never mid-gesture."""
        self._px_per_unit = ASPECT_CANVAS_BOX_PX / max(self._ratio_w, self._ratio_h)
        self._rect_w_px = self._ratio_w * self._px_per_unit
        self._rect_h_px = self._ratio_h * self._px_per_unit

    # --- public API --------------------------------------------------------

    def set_ratio(self, w: int, h: int) -> None:
        """Programmatic reshape (typing in the dialog's W/H entries) —
        see the class docstring for why a same-value call is a no-op."""
        w, h = max(int(w), 1), max(int(h), 1)
        if (w, h) == (self._ratio_w, self._ratio_h):
            return
        self._ratio_w, self._ratio_h = w, h
        self._fit_to_box()
        self.redraw_theme()

    # --- events --------------------------------------------------------

    def _edge_hit(self, x: float, y: float) -> str | None:
        """Which SPECIFIC edge (if any) the point is within grab
        tolerance of — "left"/"right" (drag WIDTH), "top"/"bottom" (drag
        HEIGHT), else None (a click inside the box or out in the margin
        grabs nothing). The side matters, not just the axis (see
        ``_on_drag``): it is what lets a drag past the centre HOLD at
        the minimum instead of "growing" again on the other side."""
        tol = ASPECT_CANVAS_EDGE_GRAB_PX
        left = self._cx - self._rect_w_px / 2
        right = self._cx + self._rect_w_px / 2
        top = self._cy - self._rect_h_px / 2
        bottom = self._cy + self._rect_h_px / 2
        in_v_span = top - tol <= y <= bottom + tol
        in_h_span = left - tol <= x <= right + tol
        if abs(x - left) <= tol and in_v_span:
            return "left"
        if abs(x - right) <= tol and in_v_span:
            return "right"
        if abs(y - top) <= tol and in_h_span:
            return "top"
        if abs(y - bottom) <= tol and in_h_span:
            return "bottom"
        return None

    def _on_press(self, event) -> None:
        self._drag_edge = self._edge_hit(event.x, event.y)

    def _on_drag(self, event) -> None:
        if self._drag_edge is None:
            return
        half_min = ASPECT_CANVAS_MIN_PX / 2
        half_max = ASPECT_CANVAS_BOX_PX / 2
        if self._drag_edge in ("left", "right"):
            # clamp the EFFECTIVE coordinate to never cross the centre —
            # a fast/overshot drag holds at the minimum instead of
            # "growing" again once the cursor passes the opposite side
            eff = (
                max(event.x, self._cx) if self._drag_edge == "right"
                else min(event.x, self._cx)
            )
            half = min(max(abs(eff - self._cx), half_min), half_max)
            self._rect_w_px = half * 2
        else:
            eff = (
                max(event.y, self._cy) if self._drag_edge == "bottom"
                else min(event.y, self._cy)
            )
            half = min(max(abs(eff - self._cy), half_min), half_max)
            self._rect_h_px = half * 2
        new_w = max(round(self._rect_w_px / self._px_per_unit), 1)
        new_h = max(round(self._rect_h_px / self._px_per_unit), 1)
        changed = (new_w, new_h) != (self._ratio_w, self._ratio_h)
        self._ratio_w, self._ratio_h = new_w, new_h
        self.redraw_theme()  # state is fully updated BEFORE painting it
        if changed and self._on_change is not None:
            self._on_change(new_w, new_h)

    def _on_release(self, _event) -> None:
        self._drag_edge = None

    def _on_hover(self, event) -> None:
        edge = self._edge_hit(event.x, event.y)
        cursor_by_edge = {
            "left": "sb_h_double_arrow", "right": "sb_h_double_arrow",
            "top": "sb_v_double_arrow", "bottom": "sb_v_double_arrow",
        }
        self.configure(cursor=cursor_by_edge.get(edge, ""))

    # --- drawing --------------------------------------------------------

    def redraw_theme(self) -> None:
        """Full redraw from the ACTIVE theme + the current w/h — called
        at construction, after every set_ratio/drag, and (a future non-
        modal host, see the class docstring) on a Day/Night flip."""
        self.delete("all")
        accent = job_color("aspect")
        palette = THEMES[widgets.ACTIVE_THEME]["ttk"]
        box, pad = ASPECT_CANVAS_BOX_PX, ASPECT_CANVAS_PAD_PX

        # the arena guide — the max extent either edge can be dragged to
        self.create_rectangle(
            pad, pad, pad + box, pad + box,
            outline=palette["light"], dash=(3, 3),
        )

        left = self._cx - self._rect_w_px / 2
        right = self._cx + self._rect_w_px / 2
        top = self._cy - self._rect_h_px / 2
        bottom = self._cy + self._rect_h_px / 2
        # a live drag EMPHASIZES the box (thicker outline, bigger handles)
        # — cheap, live feedback that something is actively being grabbed,
        # so a mid-drag frame reads differently from the settled one
        dragging = self._drag_edge is not None
        self.create_rectangle(
            left, top, right, bottom,
            outline=accent,
            width=ASPECT_CANVAS_OUTLINE_W + (2 if dragging else 0),
            fill=palette["dark"],
        )
        r = ASPECT_CANVAS_HANDLE_R + (2 if dragging else 0)
        for hx, hy in (
            (left, self._cy), (right, self._cy),
            (self._cx, top), (self._cx, bottom),
        ):
            self.create_oval(
                hx - r, hy - r, hx + r, hy + r, fill=accent, outline="",
            )

        label_y = pad + box + ASPECT_CANVAS_LABEL_GAP_PX
        decimal = aspect.decimal_ratio_label(self._ratio_w, self._ratio_h)
        rw, rh = aspect.reduced_ratio(self._ratio_w, self._ratio_h)
        self.create_text(
            pad + box / 2, label_y,
            text=f"{decimal}   ({rw}:{rh})",
            fill=palette["fg"], font=tk_font("bold"), anchor="n",
        )
