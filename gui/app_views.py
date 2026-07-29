"""ViewMixin — the Main Menu / running-view state machine.

Godfile refactor step 7/8 (see gui/___gui.md): the second of PainterGui's
six mixins (see gui/app.py — a sixth, CheckerFixerMixin, split out of
SiteJobsMixin in step 8/8). Owns the three-way ``_view`` switch (menu /
main / running — ``_set_view``/``_go_view``), the Main Menu tile router
(``_select_tile``/``_tile_handler``), the running view's IconBar wiring
(``_apply_running_layout``/``_open_tool_panel``/``_click_icon_bar_tile``),
the "which jobs are active" queries (``_active_kinds``/``_active_tile_ids``/
``_sync_running_state``) and the Controls collapse toggle
(``_set_collapsed``/``_toggle_collapsed``). No ``__init__`` here — every
attribute it reads (``self._view``, ``self._controls_box``, ``self.
_tool_panels``, ...) is set by ``BuildMixin.__init__``.
"""

from __future__ import annotations

from functools import partial
from typing import Callable

from painter.config import (
    DASH_MODE_GRID,
    DASH_MODE_SLIDER,
    TILE_JOB_KINDS,
)
from .app_build import COLLAPSE_GLYPH_COLLAPSED, COLLAPSE_GLYPH_EXPANDED
from .logic import _next_view
from .theme import smooth_transition


class ViewMixin:
    """The Main Menu / "main" / "running" view switch + running-view
    layout reconciliation."""

    def _toggle_dash_mode(self) -> None:
        """F4e (owner 2026-07-29): flip the dashboard between the
        width-responsive GRID and the one-card SLIDER; persisted as
        'dash_mode' by the normal debounced settings save."""
        new = (
            DASH_MODE_SLIDER
            if self._dashgrid.mode == DASH_MODE_GRID
            else DASH_MODE_GRID
        )
        self._dashgrid.set_mode(new)
        self._render_dash_mode_btn()
        self._schedule_save()

    def _render_dash_mode_btn(self) -> None:
        slider = self._dashgrid.mode == DASH_MODE_SLIDER
        self._dash_mode_btn.configure(
            text="▭ slider" if slider else "▦ grid"
        )

    def _set_collapsed(self, collapsed: bool) -> None:
        """Swap the full controls for the thin per-agent strip (or back).
        Nothing is destroyed — every StringVar/BooleanVar/Listbox/Spinner
        keeps its state; 'before=self.notebook' pins the vertical order
        [controls|compact] above the notebook regardless of pack order."""
        self._collapsed = collapsed
        if collapsed:
            self._controls_box.pack_forget()
            self._compact_box.pack(fill="x", before=self.notebook)
        else:
            self._compact_box.pack_forget()
            self._controls_box.pack(fill="x", before=self.notebook)
        self._collapse_btn.configure(
            text=COLLAPSE_GLYPH_COLLAPSED if collapsed
            else COLLAPSE_GLYPH_EXPANDED
        )
        self._scroll.refresh()

    def _toggle_collapsed(self) -> None:
        # the swap moves the whole upper window — run it behind the
        # shared snapshot cover so it fades instead of jumping
        smooth_transition(
            self.root, partial(self._set_collapsed, not self._collapsed)
        )
        self._schedule_save()

    # --- Main Menu (GUI rework Phase 10) --------------------------------

    def _set_view(self, view: str) -> None:
        """Swap the Main Menu for the existing controls/queue/dashboard
        tree, or back — ``_set_collapsed``'s pack_forget/pack technique,
        one level up: nothing is destroyed, every StringVar/Listbox/
        panel/worker thread keeps its state, only which CONTAINER is
        packed into 'outer' changes. Not persisted (every launch starts
        at "menu", see __init__) and deliberately its OWN state, never
        entangled with ``_collapsed`` — the Controls toggle keeps
        working unmodified, independently, in either view.

        GUI rework Phase 11 adds a THIRD value, "running": at THIS
        level it packs exactly like "main" (the else branch below is
        byte-identical to Phase 10) — the difference lives ONE
        container down, inside ``_main_view``, where
        ``_apply_running_layout`` swaps the controls_box/compact_box
        region for the IconBar (plus the optional website_gen inline
        panel). Entering "running" also disables the Controls-collapse
        toggle (collapsed/expanded is meaningless when neither
        controls_box nor compact_box is what's showing) and hands the
        Menu affordance to IconBar's own copy; leaving it restores
        both via the SAME ``_set_collapsed`` Phase 10 already proves
        safe."""
        was_running = self._view == "running"
        self._view = view
        if view == "menu":
            self._main_view.pack_forget()
            self._menu_view.pack(fill="both", expand=True)
        else:
            self._menu_view.pack_forget()
            self._main_view.pack(fill="both", expand=True)
        if view == "running":
            if not was_running:
                # Start hides the LAUNCHING tool's own settings panel
                # (spec item 4) — a fresh entry into "running" never
                # inherits a stale inline toggle from a previous run
                self._inline_kind = None
            self._menu_btn.pack_forget()
            self._collapse_btn.configure(state="disabled")
            self._apply_running_layout()
        elif was_running:
            self._icon_bar.pack_forget()
            self._menu_btn.pack(side="left")
            self._collapse_btn.configure(state="normal")
            self._set_collapsed(self._collapsed)
        # F4b (owner 2026-07-29): the icon strip shows on the SETUP
        # screen too — icons-only, above the settings; its own Menu
        # button serves as HOME there. HOTFIX (owner 2026-07-29,
        # slika 2): entering the setup screen ALWAYS expands the full
        # controls — a persisted collapsed state used to leave only
        # the thin compact strip, i.e. NO settings and no way to
        # start; the Controls toggle still collapses afterwards.
        if view == "main":
            if self._collapsed:
                self._set_collapsed(False)
            target = self._controls_box
            if not target.winfo_manager():
                target = self.notebook
            self._icon_bar.pack(fill="x", pady=(2, 4), before=target)
        elif view == "menu":
            self._icon_bar.pack_forget()
        # HOTFIX (owner 2026-07-29, slika 1): the MENU screen shows a
        # CLEAN top strip — title + theme switch only; Check/Controls/
        # grid-slider (and the legacy Menu button, permanently) belong
        # to the working views and hide here.
        self._menu_btn.pack_forget()  # IconBar's Menu is the one HOME
        if view == "menu":
            self.btn_check.pack_forget()
            self._collapse_btn.pack_forget()
            self._dash_mode_btn.pack_forget()
        else:
            if not self.btn_check.winfo_manager():
                self.btn_check.pack(side="left", padx=(8, 0))
            if not self._dash_mode_btn.winfo_manager():
                self._dash_mode_btn.pack(
                    side="right", padx=(0, 8), after=self.switch
                )
            if not self._collapse_btn.winfo_manager():
                self._collapse_btn.pack(
                    side="right", padx=(0, 8), after=self._dash_mode_btn
                )
        self._scroll.refresh()

    def _go_view(self, view: str) -> None:
        if view == self._view:
            return
        # the swap moves the whole window's content — run it behind the
        # shared snapshot cover so it fades instead of jumping, exactly
        # like _toggle_collapsed
        smooth_transition(self.root, partial(self._set_view, view))

    def _select_tile(self, tile_id: str) -> None:
        """One Main Menu tile picked: reveal the existing app and, for
        every functionality but Website GEN, invoke the SAME existing
        handler the old always-visible toolbar button already called —
        UNMODIFIED, Phase 10 only changed what is VISIBLE when it runs.
        Website GEN has no single handler of its own — the owner drives
        the now-visible queue + per-site Start buttons, same as always.
        ``_tile_handler`` is shared with the running view's IconBar
        (``_click_icon_bar_tile``, GUI rework Phase 11) — ONE mapping,
        not two copies (Rule #5).

        GUI rework Phase 13: bg/crop now have their OWN persistent
        panel (``_tool_panels``) and skip the "main" hop entirely,
        going straight to "running" with it shown inline
        (``_open_tool_panel``) — routing them through ``_go_view
        ("main")`` first, like every other tile, would reveal-then-
        immediately-hide the old controls box behind a wasted extra
        fade (``_open_tool_panel`` transitions straight to "running"
        itself). Every other tile's routing is UNCHANGED."""
        if tile_id in self._tool_panels:
            self._open_tool_panel(tile_id)
            return
        self._go_view("main")
        handler = self._tile_handler(tile_id)
        if handler is not None:
            handler()

    def _tile_handler(self, tile_id: str) -> Callable[[], None] | None:
        """The existing, unmodified action one ``MENU_TILES`` id runs.
        ``None`` only for "website_gen" (no single handler — see
        ``_select_tile``'s docstring).

        GUI rework Phase 13/14/15/19: all SIX standalone-job tiles
        (bg/crop/upscale/aspect/image_checker, and now api_image_gen)
        route to ``_open_tool_panel`` — their persistent settings panel
        — instead of an old modal/dialog launch (``_start_tool``,
        deleted Phase 14; the AI checker's own ``askdirectory``+confirm
        inline in ``_start_ai_check``, deleted Phase 15; see gui.md). In
        practice neither ``_select_tile`` nor ``_click_icon_bar_tile``
        ever reaches this dict entry for any of the six (both special-
        case the panel toggle before falling through here —
        ``_select_tile`` to skip a wasted view hop, ``_click_icon_bar_
        tile`` implicitly via this same mapping), but this stays a
        COMPLETE, truthful "tile id -> its action" table regardless of
        which caller consults it."""
        return {
            "website_gen": None,
            "ai_sheet_gen": self._new_collection_ai,
            "api_image_gen": partial(self._open_tool_panel, "api_image_gen"),
            "image_checker": partial(self._open_tool_panel, "image_checker"),
            "bg": partial(self._open_tool_panel, "bg"),
            "crop": partial(self._open_tool_panel, "crop"),
            "upscale": partial(self._open_tool_panel, "upscale"),
            "aspect": partial(self._open_tool_panel, "aspect"),
        }[tile_id]

    # --- Running view (GUI rework Phase 11) -----------------------------

    def _active_kinds(self) -> set[str]:
        """Every JOB_ORDER kind with a live worker right now — sites via
        ``_running``, tools + the AI checker via ``_tool_workers``. The
        single source of truth ``_next_view``/``_apply_running_layout``/
        ``_request_menu`` all read; call after any change to either
        set (``_sync_running_state`` is that call site)."""
        return self._running | set(self._tool_workers)

    def _active_tile_ids(self) -> set[str]:
        """Which ``MENU_TILES`` ids currently have at least one active
        job — drives ``IconBar.set_active`` via ``config.TILE_JOB_KINDS``."""
        active = self._active_kinds()
        return {
            tile_id for tile_id, kinds in TILE_JOB_KINDS.items()
            if set(kinds) & active
        }

    def _sync_running_state(self) -> None:
        """Call after ANY change to ``_running``/``_tool_workers`` (a
        job started, or its worker finished): reconciles the view via
        the pure ``_next_view`` and, whenever the result IS "running",
        refreshes the IconBar's live-status colours. Never itself
        decides to LEAVE "running" — that only happens through
        ``_request_menu`` (an explicit Menu click), per ``_next_view``'s
        own rules."""
        target = _next_view(self._view, len(self._active_kinds()))
        if target != self._view:
            self._go_view(target)
        elif self._view == "running":
            # already running: a Start from the reopened settings just
            # cleared _inline_kind — re-reconcile so the screen drops
            # back to the dashboard (owner 2026-07-29)
            self._apply_running_layout()
        if self._view == "running":
            self._icon_bar.set_active(self._active_tile_ids())

    def _apply_running_layout(self) -> None:
        """Reconcile the region above the notebook for the running
        view: the IconBar is always shown, and exactly ONE inline
        surface always shows beneath it.

        The DEFAULT after Start is the DASHBOARD ALONE (owner
        2026-07-29: "posle Starta samo dashboard") — ``_inline_kind``
        is ``None`` then and NO settings surface packs. The Website
        GEN icon toggles ``_controls_box`` back
        (``_inline_kind == "website_gen"``); a running job's
        Pause/Stop stays reachable through it, one click away, and
        each tool icon shows its own ``ToolSettingsPanel``
        (BG/Crop/Upscale/Aspect, GUI rework Phase
        13/14; the AI checker, Phase 15; API Image GEN, Phase 19) while
        ``_inline_kind`` names one of them via ``_open_tool_panel``.
        Every functionality WITHOUT an entry in ``_tool_panels`` still
        launches through its existing modal/dialog handler (see
        ``_click_icon_bar_tile``). The SAME pack_forget/pack(before=
        self.notebook) technique ``_set_collapsed`` already proves
        safe, one container lower — nothing destroyed, only shown/
        hidden. Callable repeatedly (every inline toggle re-runs it);
        only meaningful while ``_view == "running"``."""
        self._controls_box.pack_forget()
        self._compact_box.pack_forget()
        for panel in self._tool_panels.values():
            panel.pack_forget()
        self._icon_bar.pack(fill="x", before=self.notebook)
        if self._inline_kind in self._tool_panels:
            self._tool_panels[self._inline_kind].pack(
                fill="x", before=self.notebook
            )
        elif self._inline_kind == "website_gen":
            # settings return ONLY on an explicit Website GEN icon
            # click (owner 2026-07-29: after Start the screen is the
            # DASHBOARD — the icon strip is the way back to setup)
            self._controls_box.pack(fill="x", before=self.notebook)
        self._icon_bar.set_active(self._active_tile_ids())
        self._scroll.refresh()

    def _open_tool_panel(self, tile_id: str) -> None:
        """Toggle ONE standalone tool's persistent settings panel
        (``_tool_panels`` — BG/Crop today, GUI rework Phase 13) inline
        above Dashboard/Log — generalizes website_gen's own
        ``_controls_box`` toggle (``_click_icon_bar_tile``, Phase 11)
        to a second panel family. Reached from BOTH the Main Menu
        (``_select_tile``, always ``_view == "menu"``) and the running
        view's IconBar (``_click_icon_bar_tile``'s generic
        ``_tile_handler`` fallthrough, always already ``_view ==
        "running"``) — ONE method, not two copies (Rule #5).

        Entering "running" for the FIRST time with NO job active yet
        (the Main Menu path) is a new but SAFE transition: ``_next_view``
        keeps the view "running" even at zero active jobs once entered
        (see its own docstring), and ``_active_kinds()`` only ever
        counts REAL workers — an open settings panel with nothing
        started yet is invisible to it, so an explicit Menu click still
        navigates away cleanly."""
        if self._view != "running":
            self._go_view("running")  # resets _inline_kind to None
        self._inline_kind = None if self._inline_kind == tile_id else tile_id
        self._apply_running_layout()

    def _request_menu(self) -> None:
        """The Menu affordance's shared handler (the pinned top-strip
        button outside "running", IconBar's own copy during it) —
        routed through ``_next_view`` so a click while any job is still
        active is a safe, clearly-explained no-op (design: "back to
        menu only once nothing is running, and only on an explicit
        Menu click")."""
        active = self._active_kinds()
        target = _next_view(self._view, len(active), menu_requested=True)
        if target == self._view:
            if active:
                self.status_var.set(
                    "Stop every running job before returning to the menu."
                )
            return
        self._go_view(target)

    def _click_icon_bar_tile(self, tile_id: str) -> None:
        """One IconBar tile clicked while ``_view == "running"``.

        "website_gen" is checked FIRST and unconditionally toggles
        ``_inline_kind`` between "website_gen" and ``None``: the
        running view's default is the DASHBOARD ALONE (owner
        2026-07-29), so this icon IS the way to bring the site
        settings/controls back above it — and to dismiss them again.
        It always supersedes whatever tool panel was open; the site
        controls stay one click away.

        Every OTHER tile keeps the pre-existing rule: a tile whose job
        kind(s) (``TILE_JOB_KINDS``) are CURRENTLY active just focuses
        the Dashboard tab — it is NOT a settings toggle for a running
        job, and that job's own panel stays exactly as hidden as the
        design requires ("without disturbing any running job's own
        hidden panel"). A NOT-running tool tile ("bg"/"crop"/"upscale"/
        "aspect"/"image_checker"/"api_image_gen") routes through
        ``_tile_handler`` to ``_open_tool_panel``, toggling its OWN
        persistent ``ToolSettingsPanel``; "ai_sheet_gen" (no persistent
        panel of its own) always launches through its existing dialog
        handler (``_tile_handler`` — the SAME mapping the Main Menu
        itself uses), and it disturbs nothing else (always its own
        Toplevel)."""
        if tile_id == "website_gen":
            self._inline_kind = (
                None if self._inline_kind == "website_gen" else "website_gen"
            )
            self._apply_running_layout()
            return
        kinds = TILE_JOB_KINDS.get(tile_id, ())
        if set(kinds) & self._active_kinds():
            self.notebook.select(0)
            return
        handler = self._tile_handler(tile_id)
        if handler is not None:
            handler()

