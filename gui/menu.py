"""``MainMenu``/``IconBar`` pulled out of ``gui/__init__.py`` (root
Rule #20 god-file refactor, step 6/8, GUI rework Phases 10–11): the
startup landing screen's fixed tile grid and the compact top strip
shown on the setup and running views.

``MENU_TILE_CELL_MIN_PX`` (the shared per-column footprint) and
``menu_min_size`` (the tile half of the minsize math) live in
``gui.logic`` — this module imports the constant rather than
re-deriving it.
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
from .logic import MENU_TILE_CELL_MIN_PX
from .widgets import _style_icon_bar_button, ctk_font, rounded_button

# --- Main window: min size, on-screen clamp, wheel, collapse (Rule #4) -
ICON_BAR_GAP_PX = 4  # gap between IconBar tile buttons (GUI rework Phase 11)
# icon-only hysteresis (owner 2026-08-03, UI rework tačka 2): switch
# BACK to text labels only with this much slack past the measured full
# width, so a width sitting exactly on the threshold never flickers
ICON_BAR_HYSTERESIS_PX = 16
# the Main Menu's fixed paddings — shared with BuildMixin._apply_min_size,
# which folds them into menu_min_size's chrome so the computed window
# minsize and the real layout can never disagree (owner 2026-08-03)
MENU_HEADER_PADY = (16, 4)
MENU_GRID_PADX = 24
MENU_GRID_PADY = (8, 24)
# left+right breathing room a tile's widest text keeps INSIDE its card,
# so a title never sits on the accent border (owner 2026-08-03, slika 1)
TILE_TEXT_MARGIN_PX = 24


class MainMenu(ttk.Frame):
    """The startup landing screen: a full-window grid of big tiles, one
    per functionality (``config.MENU_TILES``) — replacing "everything
    visible at once" as the first thing the owner sees. Built ONCE,
    beside the existing controls/notebook tree, and shown/hidden by
    ``PainterGui._set_view``; picking a tile runs the SAME existing,
    unmodified handler the always-visible toolbar already called before
    this phase (see ``PainterGui._select_tile``) — this class only
    decides what the picker looks like, never what a pick DOES.

    FIXED GRID (owner 2026-08-03, UI rework tačka 1): the tiles ALWAYS
    sit at ``MENU_TILE_COLS`` columns — the 2026-07-21 responsive
    reflow (down to 1 column at a narrow width) is REVERTED by owner
    decree ("uvek mora 4x2 grid"): instead of the grid adapting to a
    small window, the WINDOW cannot get that small —
    ``BuildMixin._apply_min_size`` computes ``root.minsize`` from this
    grid's own floor (``gui.logic.menu_min_size`` + the measured
    chrome), so every tile always renders whole, no menu scrolling.
    Tiles are built and gridded ONCE in ``__init__``; every column/row
    carries weight 1 (+ ``minsize``/``uniform``) so the cards grow
    evenly with the window above the floor."""

    def __init__(self, parent, on_select: Callable[[str], None]):
        super().__init__(parent)
        self._on_select = on_select

        # HOTFIX (owner 2026-07-29, slika 1): the big title moved into
        # the top strip (in line with the theme switcher) — the menu
        # keeps only its short instruction line
        self._header = ttk.Frame(self)
        self._header.pack(pady=MENU_HEADER_PADY)
        ttk.Label(
            self._header, text="Pick what to do", style="Muted.TLabel"
        ).pack()

        self._grid = ttk.Frame(self)
        self._grid.pack(
            fill="both", expand=True,
            padx=MENU_GRID_PADX, pady=MENU_GRID_PADY,
        )
        self._tiles = [self._make_tile(self._grid, tile) for tile in MENU_TILES]
        cols = min(MENU_TILE_COLS, max(1, len(self._tiles)))
        rows = math.ceil(len(self._tiles) / cols)
        for i, card in enumerate(self._tiles):
            r, c = divmod(i, cols)
            card.grid(
                row=r, column=c, sticky="nsew",
                padx=MENU_TILE_GAP_PX // 2, pady=MENU_TILE_GAP_PX // 2,
            )
        # minsize is the hard floor Tk actually enforces (weight only
        # ever distributes EXTRA space); the column floor is
        # MENU_TILE_CELL_MIN_PX — the SAME per-column footprint
        # menu_min_size assumes for the window minsize, so the two can
        # never disagree — never the bare MENU_TILE_W (see that
        # constant's own comment for why it needs the extra margin)
        self._cols = cols
        self._cell_min = MENU_TILE_CELL_MIN_PX
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

    def cell_min_px(self) -> int:
        """The per-column footprint that renders EVERY tile whole at the
        CURRENT font zoom (owner 2026-08-03, slika 1: "nijedan karton ne
        sme da bude isečen... i border i sve").

        ``MENU_TILE_CELL_MIN_PX`` is a static floor computed from
        ``MENU_TILE_W``; a tile's real content (its title line — "Website
        Image GEN" is the widest) can be wider than that at a larger
        font, and then the fixed-width card clips it. So the floor is
        RAISED here by the widest measured tile content plus the card's
        own border/breathing room, the value is re-applied as every
        column's Tk ``minsize``, and the SAME number is handed to
        ``gui.logic.menu_min_size`` for the window minsize — one
        measurement, both consumers, so grid and window can never
        disagree. Call after ``update_idletasks`` for honest numbers."""
        widest = max(
            (card.winfo_children()[0].winfo_reqwidth() for card in self._tiles),
            default=0,
        )
        # the card's own chrome around its content frame: the accent
        # border (hovered width, both sides) + a symmetric text margin,
        # then the inter-tile gap the grid pad consumes
        card_min = widest + 2 * MENU_TILE_BORDER_HOVER_PX + TILE_TEXT_MARGIN_PX
        self._cell_min = max(
            MENU_TILE_CELL_MIN_PX, card_min + MENU_TILE_GAP_PX
        )
        for c in range(self._cols):
            self._grid.columnconfigure(c, minsize=self._cell_min)
        return self._cell_min

    def chrome_height(self) -> int:
        """Everything this view adds ABOVE/AROUND the tile grid, at the
        current font zoom: the header's measured height + its pack pady
        + the grid's own pack pady. ``BuildMixin._apply_min_size`` folds
        this into ``menu_min_size``'s chrome — measured here so the
        constants and the measurement live beside the packs they
        describe. Call after ``update_idletasks`` for honest numbers."""
        return (
            self._header.winfo_reqheight()
            + sum(MENU_HEADER_PADY) + sum(MENU_GRID_PADY)
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
    """The compact nav strip shown on the setup ("main") and "running"
    views (GUI rework Phase 11, F4b): the HOME button leftmost, then
    one small button per ``config.MENU_TILES`` functionality.

    HOME (owner 2026-08-03, UI rework tačka 2): the old right-side
    text "Menu" button is GONE — the leftmost button carries the
    ``home.svg`` icon (icon-only, always) and IS the way back to the
    Main Menu (``on_menu`` — still routed through
    ``PainterGui._request_menu``, which refuses while jobs run).

    RESPONSIVE (same decree: "sve opcije uvek vidljive, nikad sečene"):
    the bar NEVER clips a button. Its own ``<Configure>`` compares the
    allocated width against the measured full-text width — too narrow
    and EVERY tile button drops its label at once (icon-only, one
    uniform look, tooltips stay via the button text restored later);
    wide enough again (+``ICON_BAR_HYSTERESIS_PX`` slack, so the
    boundary never flickers) and the labels come back. The full-text
    width is measured lazily on the first ``<Configure>`` in text mode
    and re-measured after a font zoom (``refresh_measure``).

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
        self._icon_only = False
        self._full_w = 0  # measured lazily (first <Configure> in text mode)
        self._home = rounded_button(
            self, "", icon_name="home", command=on_menu,
        )
        self._home.pack(side="left", padx=(0, ICON_BAR_GAP_PX))
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
        self.set_active(set())
        self.bind("<Configure>", self._on_configure)

    def refresh_measure(self) -> None:
        """Font zoom changed — the cached full-text width is stale.
        Cleared here; the next ``<Configure>`` in TEXT mode re-measures
        (while icon-only, the stale value only delays the switch back
        by one extra configure cycle — the re-measure after the labels
        return corrects any overshoot on the very next pass)."""
        self._full_w = 0

    def _on_configure(self, event) -> None:
        if not self._icon_only and self._full_w <= 0:
            self._full_w = self.winfo_reqwidth()
        if self._full_w <= 0:
            return
        if not self._icon_only and event.width < self._full_w:
            self._set_icon_only(True)
        elif self._icon_only and (
            event.width >= self._full_w + ICON_BAR_HYSTERESIS_PX
        ):
            self._set_icon_only(False)

    def _set_icon_only(self, on: bool) -> None:
        """Swap EVERY tile button between icon+label and icon-only in
        one pass (uniform look — never a mixed strip). HOME is
        icon-only by construction and never changes."""
        self._icon_only = on
        labels = {tile.id: tile.label for tile in MENU_TILES}
        for tile_id, btn in self._buttons.items():
            btn.configure(text="" if on else labels[tile_id])
        if not on:
            # labels just returned at the CURRENT font — re-measure on
            # the next configure so a zoom while icon-only heals
            self._full_w = 0

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
