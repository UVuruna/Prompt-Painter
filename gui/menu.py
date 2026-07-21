"""``MainMenu``/``IconBar`` pulled out of ``gui/__init__.py`` (root
Rule #20 god-file refactor, step 6/8, GUI rework Phases 10–11): the
startup landing screen's responsive tile grid and the compact top
strip shown while a job is running.

``_menu_tile_columns``/``MENU_TILE_CELL_MIN_PX`` (the reflow math and
the shared per-column footprint) already live in ``gui.logic`` — this
module imports them from there rather than re-deriving them.
"""

from __future__ import annotations

import math
from functools import partial
from typing import Callable

import customtkinter as ctk
from tkinter import ttk

from painter.config import (
    MENU_TILES,
    MENU_TILE_BORDER_HOVER_PX,
    MENU_TILE_BORDER_PX,
    MENU_TILE_COLS,
    MENU_TILE_GAP_PX,
    MENU_TILE_H,
    MENU_TILE_ICON_PX,
    MENU_TILE_RADIUS,
    MENU_TILE_W,
    theme_pair,
)
from .icons import icon
from .logic import MENU_TILE_CELL_MIN_PX, _menu_tile_columns
from .widgets import _style_icon_bar_button, ctk_font, rounded_button

# --- Main window: min size, on-screen clamp, wheel, collapse (Rule #4) -
ICON_BAR_GAP_PX = 4  # gap between IconBar tile buttons (GUI rework Phase 11)


class MainMenu(ttk.Frame):
    """The startup landing screen: a full-window grid of big tiles, one
    per functionality (``config.MENU_TILES``) — replacing "everything
    visible at once" as the first thing the owner sees. Built ONCE,
    beside the existing controls/notebook tree, and shown/hidden by
    ``PainterGui._set_view``; picking a tile runs the SAME existing,
    unmodified handler the always-visible toolbar already called before
    this phase (see ``PainterGui._select_tile``) — this class only
    decides what the picker looks like, never what a pick DOES.

    RESPONSIVE (owner 2026-07-21 workflow fix): the tiles no longer sit
    at a hardcoded ``MENU_TILE_COLS`` — ``_grid``'s own ``<Configure>``
    drives ``_menu_tile_columns``/``_reflow`` so the grid never clips or
    overflows at a narrow window width, reflowing to fewer columns (down
    to 1) as the width shrinks. Tiles are built ONCE in ``__init__``
    (``self._tiles``); ``_reflow`` only re-``grid()``s them at a new
    row/column and resets/reassigns column-and-row weights — the SAME
    reset-then-reassign technique ``PainterGui._relayout_agents`` already
    uses for the agent panels, one level up. No timer-debounce (unlike
    ``ScrollFrame``'s drag handling): the change-guard in
    ``_on_grid_configure`` already skips the real reflow work on every
    ``<Configure>`` that does not actually change the column count — a
    per-pixel resize very rarely crosses one of the few integer
    thresholds, so this is not the same per-frame cost class."""

    def __init__(self, parent, on_select: Callable[[str], None]):
        super().__init__(parent)
        self._on_select = on_select

        header = ttk.Frame(self)
        header.pack(pady=(24, 4))
        ttk.Label(header, text="PromptPainter", style="Big.TLabel").pack()
        ttk.Label(header, text="Pick what to do", style="Muted.TLabel").pack()

        self._grid = ttk.Frame(self)
        self._grid.pack(fill="both", expand=True, padx=24, pady=(8, 24))
        self._tiles = [self._make_tile(self._grid, tile) for tile in MENU_TILES]
        self._cols = _menu_tile_columns(0, len(self._tiles))  # deterministic first pack
        self._reflow(self._cols)
        self._grid.bind("<Configure>", self._on_grid_configure)

    def _on_grid_configure(self, event) -> None:
        cols = _menu_tile_columns(event.width, len(self._tiles))
        if cols != self._cols:
            self._reflow(cols)

    def _reflow(self, cols: int) -> None:
        """(Re)grid every tile at ``cols`` columns. Resets EVERY column
        up to ``MENU_TILE_COLS`` and EVERY row up to the 1-column worst
        case to weight 0 AND clears their ``uniform`` tag first, then
        reassigns weight 1 (+ ``minsize``/``uniform``) only to the
        columns/rows actually in use this pass.

        BOTH resets are load-bearing, not belt-and-suspenders — caught
        by a real screenshot, not pytest (owner 2026-07-21 workflow
        fix): a stale column left in the "menucol" ``uniform`` GROUP
        from a PREVIOUS, larger ``cols`` (weight reset to 0 alone does
        NOT detach it from the group) skews Tk's shared-width
        calculation for the group's OTHER, still-active members —
        observed shrinking cards to ~117px, well under
        ``MENU_TILE_W``'s supposed 180px floor, silently clipping their
        title text. ``minsize`` is the actual hard floor Tk enforces
        (unlike ``weight``, which only ever distributes EXTRA space);
        the column minsize is ``MENU_TILE_CELL_MIN_PX`` — the SAME
        per-column footprint ``_menu_tile_columns`` already assumed
        when it decided ``cols`` fits, so the two can never disagree —
        never the bare ``MENU_TILE_W`` (see that constant's own
        comment for why it needs the extra margin)."""
        self._cols = cols
        rows = math.ceil(len(self._tiles) / cols)
        for c in range(MENU_TILE_COLS):
            self._grid.columnconfigure(c, weight=0, uniform="")
        for r in range(len(self._tiles)):  # 1-column layout: one row each
            self._grid.rowconfigure(r, weight=0, uniform="")
        for i, card in enumerate(self._tiles):
            r, c = divmod(i, cols)
            card.grid(
                row=r, column=c, sticky="nsew",
                padx=MENU_TILE_GAP_PX // 2, pady=MENU_TILE_GAP_PX // 2,
            )
        for c in range(cols):
            self._grid.columnconfigure(
                c, weight=1, uniform="menucol",
                minsize=MENU_TILE_CELL_MIN_PX,
            )
        for r in range(rows):
            self._grid.rowconfigure(
                r, weight=1, uniform="menurow",
                minsize=MENU_TILE_H + MENU_TILE_GAP_PX,
            )

    def _make_tile(self, parent, tile) -> ctk.CTkFrame:
        """One tile: icon + title + description in a rounded, accent-
        bordered card (DESIGN.md "cards, panels" radius bracket + Rule
        #16 hover/depth), built from the SAME primitives every other
        rounded surface in this file uses (``icon()``/``theme_pair``/
        ``ctk_font``) — a factory, not 8 copy-pasted blocks (Rule #5).
        The one thing that changes on hover is the border width (a
        cheap, artifact-free "focus ring" — anything touching fill
        colour would also have to walk every child label in lockstep).
        A disabled tile (``tile.enabled`` False) renders muted, with no
        hover/click binding at all."""
        surface = theme_pair("dark")      # elevated "card" surface
        window_bg = theme_pair("bg")      # what's behind the card's OWN
        #                                   rounded corners (its ttk parent)
        accent = tile.color if tile.enabled else theme_pair("light")

        card = ctk.CTkFrame(
            parent, corner_radius=MENU_TILE_RADIUS,
            fg_color=surface, bg_color=window_bg,
            border_width=MENU_TILE_BORDER_PX, border_color=accent,
            width=MENU_TILE_W, height=MENU_TILE_H,
        )
        card.grid_propagate(False)
        content = ctk.CTkFrame(card, fg_color=surface, bg_color=surface)
        content.pack(expand=True)
        ctk.CTkLabel(
            content, text="", image=icon(tile.icon, MENU_TILE_ICON_PX),
            fg_color=surface, bg_color=surface,
        ).pack(pady=(0, 8))
        ctk.CTkLabel(
            content, text=tile.label, font=ctk_font("title"),
            text_color=accent, fg_color=surface, bg_color=surface,
        ).pack()
        ctk.CTkLabel(
            content, text=tile.description, font=ctk_font("root"),
            text_color=theme_pair("light"), fg_color=surface,
            bg_color=surface, wraplength=MENU_TILE_W - 24, justify="center",
        ).pack(pady=(4, 0))

        if not tile.enabled:
            return card  # placeholder — no hover, no click (Phase 19)

        def _hover(active: bool, _event=None) -> None:
            card.configure(
                border_width=MENU_TILE_BORDER_HOVER_PX if active
                else MENU_TILE_BORDER_PX
            )

        def _click(_event=None) -> None:
            self._on_select(tile.id)

        for w in (card, content, *content.winfo_children()):
            w.configure(cursor="hand2")
            w.bind("<Button-1>", _click)
            w.bind("<Enter>", lambda _e: _hover(True))
            w.bind("<Leave>", lambda _e: _hover(False))
        return card


class IconBar(ttk.Frame):
    """The compact top strip shown while ``PainterGui._view ==
    "running"`` (GUI rework Phase 11): one small button per
    ``config.MENU_TILES`` functionality, plus a "Menu" button on the
    right (the pinned top-strip one steps aside while this is up — see
    ``PainterGui._set_view``, one Menu affordance visible at a time).

    A tile's colour FILLS IN while any of its ``config.TILE_JOB_KINDS``
    has a live job right now (``_style_icon_bar_button`` — the SAME
    filled/outline language ``style_action_button`` already uses for
    Start/Stop, generalized to an arbitrary accent pair) and sits as a
    quiet outline otherwise; clicking a lit tile focuses the Dashboard
    instead of a settings toggle (``PainterGui._click_icon_bar_tile``
    decides — this class only renders, it never decides). Built ONCE
    alongside the rest of the app; ``PainterGui`` packs/unpacks the
    whole bar and calls ``set_active`` after every job start/stop so
    the colours stay live."""

    def __init__(
        self, parent,
        on_select: Callable[[str], None], on_menu: Callable[[], None],
    ):
        super().__init__(parent, padding=(0, 4))
        self._buttons: dict[str, ctk.CTkButton] = {}
        for tile in MENU_TILES:
            btn = rounded_button(
                self, tile.label, icon_name=tile.icon,
                command=partial(on_select, tile.id) if tile.enabled else None,
            )
            btn.pack(side="left", padx=(0, ICON_BAR_GAP_PX))
            self._buttons[tile.id] = btn
            if not tile.enabled:
                # the one permanently-disabled placeholder (api_image_gen,
                # same as MainMenu's own tile — Phase 19 wires it up):
                # muted and inert, never touched by set_active again
                _style_icon_bar_button(btn, tile.color, active=False)
                btn.configure(state="disabled")
        # plain text, no icon — same constraint the pinned top-strip
        # Menu button already documents (no "menu/home" icon asset
        # exists, and DESIGN.md's emoji policy rules out a hamburger
        # glyph standing in for one); "controls" would be actively
        # WRONG here — that stem is the gamepad glyph the UNRELATED
        # Controls-collapse toggle already owns, right beside this bar
        rounded_button(self, "Menu", command=on_menu).pack(side="right")
        self.set_active(set())

    def set_active(self, active_ids: set[str]) -> None:
        """Recolour every ENABLED tile: FILLED while its id is in
        ``active_ids``, a quiet outline otherwise. Called by
        ``PainterGui`` after every change to the running job set."""
        for tile in MENU_TILES:
            if not tile.enabled:
                continue
            _style_icon_bar_button(
                self._buttons[tile.id], tile.color, tile.id in active_ids
            )
