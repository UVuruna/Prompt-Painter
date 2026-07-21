"""BuildMixin — PainterGui's constructor and widget construction.

Godfile refactor step 7/8 (see gui/___gui.md): PainterGui used to be one
~3350-line class; it is now composed from six responsibility mixins, one
file each (see gui/app.py for the composition — a sixth,
CheckerFixerMixin, split out of SiteJobsMixin in step 8/8). BuildMixin is
the ONLY
mixin that defines ``__init__`` — every other mixin's methods run on the
attributes this constructor sets, via ``self.``. It also owns the
``_build_*`` widget-construction helpers, the global font-zoom/wheel-
routing bindings, ``_relayout_agents`` (the per-site visibility
reconciler wired up in ``_build_compact``), and the drag-resize event-
buffering watcher (``_on_root_configure`` / ``_resize_settled`` /
``_clamp_geometry`` — maximize/restore is tracked for bookkeeping only,
see ``_on_root_configure``'s own docstring on why it is NOT covered) —
all bound at the tail of ``__init__``, so they naturally live beside
the constructor that arms them.
"""

from __future__ import annotations

import queue
import re
import threading
import tkinter as tk
from functools import partial
from pathlib import Path
from tkinter import ttk

from painter import jobtemp
from painter.config import (
    DEFAULT_OUT_DIR,
    JOB_ORDER,
    JOB_TOOL_KINDS,
    RESIZE_SETTLE_MS,
    SITES,
    THEMES,
)
from painter.settings import load_settings
from . import widgets
from .agent_panel import AgentPanel
from .api_panel import ApiImageGenPanel
from .dash_panels import DashPanel, JobPanel
from .logic import _visible_agent_columns
from .menu import IconBar, MainMenu
from .scroll import WHEEL_DELTA_UNIT, ScrollFrame
from .switch import DayNightSwitch
from .theme import (
    apply_theme,
    register_painter_day,
    skin_listbox,
    skin_text,
)
from .tool_dash import AiCheckPanel, DashGrid, ToolPanel
from .tool_panels import (
    AspectSettingsPanel,
    BgSettingsPanel,
    CropSettingsPanel,
    ImageCheckerSettingsPanel,
    ToolSettingsPanel,
    UpscaleSettingsPanel,
)
from .widgets import rounded_button, rounded_entry, set_font_base, tk_font

# --- Main window: min size, on-screen clamp, wheel, collapse (Rule #4) -
# The whole window is vertically scrollable so a stale-tall geometry can
# never hide the bottom, and the upper control area collapses to a thin
# per-agent strip so the Dashboard can take the full height.
WINDOW_MIN_W = 900          # root.minsize width
WINDOW_MIN_H = 640          # root.minsize height
WINDOW_SCREEN_MARGIN_PX = 80  # taskbar + titlebar + slack subtracted from
#                               screen w/h when clamping a restored geometry
COMPACT_CLUSTER_GAP_PX = 24  # gap between the two agent clusters when collapsed
COLLAPSE_GLYPH_EXPANDED = "▾  Controls"   # toggle label while controls show
COLLAPSE_GLYPH_COLLAPSED = "▸  Controls"  # toggle label while collapsed


class BuildMixin:
    """``PainterGui``'s constructor + all widget-construction helpers."""

    def __init__(self, root: tk.Tk):
        self.root = root
        root.title("PromptPainter")
        root.minsize(WINDOW_MIN_W, WINDOW_MIN_H)

        # register the custom light theme before anything can apply it
        register_painter_day()

        # persisted state first — the saved font zoom must apply BEFORE
        # any widget is built (fonts are created lazily), and the saved
        # theme must be APPLIED before building so every widget is born
        # in the right theme (no first-frame flash, no half-theme window)
        self._settings = load_settings()
        if "font_base" in self._settings:
            set_font_base(int(self._settings["font_base"]))
        theme = self._settings.get("theme", "night")
        if theme not in THEMES:
            theme = "night"
        apply_theme(theme)  # sets the ttk theme + CTk mode BEFORE build

        self._q: queue.Queue = queue.Queue()
        self._sheets: list[Path] = []
        # per-site run state: workers, stop events, pending restarts.
        # GUI rework Phase 14: also spans the four standalone tools
        # (bg/crop/upscale/aspect — a real should_stop for _run_tool_job,
        # closing Phase 13's own flagged gap; see _stop_tool). GUI rework
        # Phase 15 adds "aicheck" too (_run_ai_check_job's own should_stop,
        # closing Phase 14's own flagged gap for THIS job); Phase 19 adds
        # "api_image" explicitly (it is not in SITES — no SiteConfig, no
        # browser tab — but it DOES drive through _drive_site, exactly
        # like chatgpt/gemini, and needs the same stop_event) — so this
        # now covers every _tool_workers key PLUS "api_image", still
        # short of the full JOB_ORDER (_pause_events' own span, which
        # also spans the two sites + api_image via a DIFFERENT mechanism
        # — _drive_site's should_stop comes from this SAME dict under
        # its job key).
        self._workers: dict[str, threading.Thread] = {}
        self._stop_events: dict[str, threading.Event] = {
            key: threading.Event()
            for key in (*SITES, "api_image", *JOB_TOOL_KINDS, "aicheck")
        }
        self._running: set[str] = set()
        # per-job PAUSE toggle (owner 2026-07-21): one threading.Event per
        # JOB_ORDER kind (all eight, GUI rework Phase 19 — the two sites,
        # API Image GEN, the four tools and the AI checker), polled by
        # the runner/worker loop between items/images — see
        # _toggle_pause_job. _paused tracks which kinds are CURRENTLY
        # paused so button labels stay in sync.
        self._pause_events: dict[str, threading.Event] = {
            key: threading.Event() for key in JOB_ORDER
        }
        self._paused: set[str] = set()
        self._restart_jobs: dict[str, str] = {}  # site -> after id
        self._restart_deadline: dict[str, float] = {}  # site -> monotonic
        # the four in-place tools each run as their OWN job (one worker
        # thread + one dashboard panel per kind; one job per kind at a
        # time). GUI rework Phase 8: the two gen-SITE jobs now ALSO get
        # a JobTemp each (per-step pipeline backups — created in
        # _start_site), so this dict — renamed _tool_temps -> _job_temps
        # — holds up to six slots (bg/crop/upscale/aspect + chatgpt/
        # gemini), keyed the same way _close_panel already pops any
        # kind generically.
        self._tool_workers: dict[str, threading.Thread] = {}
        self._job_temps: dict[str, jobtemp.JobTemp] = {}
        # sweep any crash-orphaned backups from a previous session
        jobtemp.clear_all()
        # (site, source-path, drop-path) -> BooleanVar; missing = ticked
        self._select_vars: dict[tuple[str, str, str], tk.BooleanVar] = {}
        self._save_job: str | None = None  # debounced settings save
        # the Gemini API key (owner 2026-07-20): held here so the whole-
        # dict settings save round-trips it; the wizard writes it and
        # painter.ai reads it back from settings.json per call
        self._gemini_key: str = ""
        # drag-resize / maximize mitigation (owner 2026-07-20): the
        # root's own <Configure> stream drives (a) a cover+fade on the
        # DISCRETE maximize/restore jump and (b) buffering of dashboard
        # events during a continuous drag, flushed on settle — see
        # _on_root_configure (bound at the end of __init__, after the
        # saved geometry is restored, so startup never arms it).
        self._win_state = ""            # root.state() at the last configure
        self._win_size = (0, 0)         # root WxH at the last configure
        self._resize_active = False     # a continuous drag is underway
        self._resize_settle_job = None  # its settle after() id
        self._pending_events: list[tuple] = []  # buffered __event__ msgs

        # the shared filter-preset LIBRARY every FilterEditor instance
        # reads/writes (config.FILTER_PRESETS_SETTING) — a plain
        # {name: [condition-dict, ...]} dict, mutated IN PLACE by the
        # widget itself; this reference is what makes a preset saved
        # while e.g. the Aspect panel is open available to a BG/Crop/
        # Upscale FilterEditor later (Phase 6/13/14) without a reload.
        # (The standalone tools' own remembered LAST-USED values — the
        # Upscale min-side/gate, the Aspect target ratio — used to live
        # here as separate PainterGui attributes feeding the old modal
        # dialogs' pre-fill; GUI rework Phase 14 retired both dialogs
        # and moved that state INTO UpscaleSettingsPanel/
        # AspectSettingsPanel themselves — see each panel's own
        # ``get_settings``/``apply_settings`` and _apply_settings's
        # "tool_panels" loop below, which also carries the one-time
        # migration from the old settings.json keys.)
        self._filter_presets: dict[str, list[dict]] = {}

        # the top strip (theme switch + collapse toggle) is PINNED outside
        # the scroll so the toggle is reachable even when the content
        # overflows a short window; everything else lives in ONE
        # fill_height ScrollFrame so the bottom is never unreachable
        shell = ttk.Frame(root)
        shell.pack(fill="both", expand=True)
        self._top_strip = ttk.Frame(shell, padding=(8, 6, 8, 0))
        self._top_strip.pack(fill="x")
        self._scroll = ScrollFrame(shell, fill_height=True)
        self._scroll.pack(fill="both", expand=True)
        outer = ttk.Frame(self._scroll.body, padding=8)
        outer.pack(fill="both", expand=True)

        # GUI rework Phase 10: the Main Menu and the whole existing app
        # are SIBLINGS inside 'outer', each its own frame — nothing
        # below moves, only its PARENT changes ('outer' -> _main_view),
        # so _set_view can pack_forget/pack the entire existing tree as
        # ONE unit, the exact technique _set_collapsed already proves
        # safe one level down. _view is deliberately its OWN, orthogonal
        # state — _collapsed (the Controls toggle) keeps working
        # unmodified, independently, in either view.
        self._view = "menu"
        # GUI rework Phase 11: which tile's inline settings surface (if
        # any) shows above the Dashboard/Log while _view == "running" —
        # "website_gen" (_controls_box) or one of the four standalone
        # tools (_tool_panels — all four now, GUI rework Phase 14; only
        # bg/crop had one through Phase 13). image_checker/ai_sheet_gen
        # still launch through their existing modal/dialog handler —
        # see _click_icon_bar_tile. Inert, never read, outside "running".
        self._inline_kind: str | None = None
        self._main_view = ttk.Frame(outer)
        self._menu_view = MainMenu(outer, on_select=self._select_tile)

        # the whole upper control area — collapsed together into the thin
        # per-agent strip (built but packed by _set_collapsed, so the
        # order is deterministic regardless of build order)
        self._collapsed = False
        self._controls_box = ttk.Frame(self._main_view)
        self._build_queue(self._controls_box)
        self._build_options(self._controls_box)
        self._build_toolbar(self._controls_box)
        self._build_compact(self._main_view)
        self._build_views(self._main_view)
        # GUI rework Phase 11: the running view's icon bar — a child of
        # _main_view like _controls_box/_compact_box/self.notebook, so
        # _apply_running_layout can pack/forget it with the exact same
        # before=self.notebook technique (needs self.notebook to exist,
        # hence built AFTER _build_views); left unpacked here — only
        # _set_view("running") ever packs it.
        self._icon_bar = IconBar(
            self._main_view,
            on_select=self._click_icon_bar_tile, on_menu=self._request_menu,
        )
        # PERSISTENT settings panels for all FOUR standalone tools (BG
        # removal / Crop, GUI rework Phase 13; Upscale / Aspect ratio,
        # Phase 14 — replacing the old UpscaleParamsDialog/
        # AspectRatioDialog modals). Children of _main_view like
        # _controls_box/_icon_bar, shown/hidden by _apply_running_layout
        # via _inline_kind (generalizing website_gen's own single-panel
        # toggle to this dict); left unpacked here. Each gets
        # on_stop=self._stop_tool (Phase 14) alongside on_start/on_pause
        # — the SAME "smart stop" handler for all four (one shared
        # implementation, see ToolSettingsPanel's own docstring).
        self._tool_panels: dict[str, ToolSettingsPanel] = {
            "bg": BgSettingsPanel(
                self._main_view,
                on_start=self._start_tool_from_panel,
                on_pause=self._toggle_pause_job,
                on_stop=self._stop_tool,
                filter_presets=self._filter_presets,
                on_filter_presets_changed=self._on_filter_presets_changed,
                on_layout_change=self._scroll.refresh,
            ),
            "crop": CropSettingsPanel(
                self._main_view,
                on_start=self._start_tool_from_panel,
                on_pause=self._toggle_pause_job,
                on_stop=self._stop_tool,
                filter_presets=self._filter_presets,
                on_filter_presets_changed=self._on_filter_presets_changed,
                on_layout_change=self._scroll.refresh,
            ),
            "upscale": UpscaleSettingsPanel(
                self._main_view,
                on_start=self._start_tool_from_panel,
                on_pause=self._toggle_pause_job,
                on_stop=self._stop_tool,
                filter_presets=self._filter_presets,
                on_filter_presets_changed=self._on_filter_presets_changed,
                on_layout_change=self._scroll.refresh,
            ),
            "aspect": AspectSettingsPanel(
                self._main_view,
                on_start=self._start_tool_from_panel,
                on_pause=self._toggle_pause_job,
                on_stop=self._stop_tool,
                filter_presets=self._filter_presets,
                on_filter_presets_changed=self._on_filter_presets_changed,
                on_layout_change=self._scroll.refresh,
            ),
            # the AI checker's own persistent panel (GUI rework Phase
            # 15) — keyed by its MENU_TILES id ("image_checker"), NOT
            # its JOB_ORDER slot ("aicheck") the panel's own SLOT
            # carries: _inline_kind/_open_tool_panel/_tile_handler all
            # operate in TILE-id space (like every other entry here,
            # where tile id happens to equal slot), and
            # PainterGui._tool_panel_key is the one bridge back from a
            # JOB_ORDER kind to this dict's key (see that method).
            # Start is NOT _start_tool_from_panel (this job has no
            # build_func/JobTemp — see ImageCheckerSettingsPanel's own
            # docstring); Stop reuses _stop_tool VERBATIM, same as the
            # four tools above (Rule #5 — already fully generic).
            "image_checker": ImageCheckerSettingsPanel(
                self._main_view,
                on_start=self._start_ai_check,
                on_pause=self._toggle_pause_job,
                on_stop=self._stop_tool,
                filter_presets=self._filter_presets,
                on_filter_presets_changed=self._on_filter_presets_changed,
                on_layout_change=self._scroll.refresh,
            ),
            # API Image GEN (GUI rework Phase 19) — keyed by its
            # MENU_TILES id ("api_image_gen"), NOT its JOB_ORDER slot
            # ("api_image"), the SAME asymmetry image_checker/"aicheck"
            # already has above (tile_for_kind bridges the two). Start
            # is its OWN _start_api_image (this job has no folder/
            # build_func shape to share with _start_tool_from_panel —
            # it drives the SAME queued .md sheets Website GEN does, via
            # _drive_site, not _run_tool_job); Stop reuses _stop_site
            # UNCHANGED — api_image's worker lives in self._workers/
            # self._running (_drive_site's own tracking), the SAME
            # dicts chatgpt/gemini use, NOT self._tool_workers, so
            # _stop_tool's own "if slot not in self._tool_workers:
            # return" guard would silently no-op here; _stop_site's
            # generic "if key in self._running: ..." branch already
            # covers ANY key (its OTHER branch, the quota-auto-restart
            # cancel, is simply unreachable for api_image — its
            # TerminalState always carries retry_after_s=None, so it
            # never enters self._restart_jobs to begin with).
            "api_image_gen": ApiImageGenPanel(
                self._main_view,
                on_start=self._start_api_image,
                on_pause=self._toggle_pause_job,
                on_stop=self._stop_site,
                filter_presets=self._filter_presets,
                on_filter_presets_changed=self._on_filter_presets_changed,
            ),
        }

        self.status_var = tk.StringVar(value="idle")
        ttk.Label(
            self._main_view, textvariable=self.status_var,
            style="Muted.TLabel",
        ).pack(fill="x", pady=(4, 0))

        # the mini Day/Night switch — reflects the already-applied theme
        self.switch = DayNightSwitch(self._top_strip, self)
        self.switch.pack(side="right")
        # the Controls collapse toggle, packed AFTER the switch so
        # side='right' places it to the switch's LEFT; carries the gamepad
        # icon (owner 2026-07-19) beside a state caret. The per-agent
        # Settings gear moved INTO each AgentPanel (no global toggle).
        self._collapse_btn = rounded_button(
            self._top_strip, COLLAPSE_GLYPH_EXPANDED,
            command=self._toggle_collapsed, icon_name="controls",
        )
        self._collapse_btn.pack(side="right", padx=(0, 8))
        # "back to the Main Menu" affordance (GUI rework Phase 10): one
        # plain-text button (no icon asset fits "menu/home" yet, and
        # DESIGN.md's emoji policy rules out a hamburger glyph standing
        # in for one) in the pinned top strip, like the switch/collapse
        # toggle either side of it — reachable from "menu"/"main".
        # GUI rework Phase 11: while "running", IconBar shows its OWN
        # Menu button instead (one Menu affordance on screen at a time —
        # see _set_view) and this one steps aside; both route through
        # _request_menu, which REFUSES the jump while any job is still
        # active (design: "back to menu only once nothing is running,
        # and only on an explicit Menu click").
        self._menu_btn = rounded_button(
            self._top_strip, "Menu", command=self._request_menu,
        )
        self._menu_btn.pack(side="left")
        # the #1 prerequisite, PINNED (owner 2026-07-21 workflow fix):
        # moved here from _build_toolbar (Rule #5 — one copy, not two)
        # because _build_toolbar's row lives inside _controls_box,
        # itself inside _main_view — invisible on the very FIRST screen
        # the owner sees ("menu", where _main_view as a whole is
        # pack_forgotten for _menu_view) and, before this same session's
        # running-view fix, invisible again the instant a job started.
        # _top_strip is a sibling of the whole _scroll/_main_view/
        # _menu_view tree, so these two are reachable from every view.
        # The rest of the toolbar (Select images…/Instructions/New
        # collection/AI key) stays exactly where it was.
        self.btn_chrome = rounded_button(
            self._top_strip, "Open Chrome (login)", command=self._open_chrome,
            icon_name="web",
        )
        self.btn_chrome.pack(side="left", padx=(8, 0))
        self.btn_check = rounded_button(
            self._top_strip, "Check", command=self._check_sheets,
        )
        self.btn_check.pack(side="left", padx=4)

        self._bind_zoom()
        self._bind_wheel_routing()
        self._set_collapsed(False)  # deterministic initial packing
        self._set_view("menu")      # ditto — every launch lands on the menu
        self._apply_settings(self._settings)  # may restore a saved state
        self._wire_persistence()
        # the maximize/restore + drag-resize watcher — seeded and bound
        # AFTER the saved geometry is applied, so startup's own
        # geometry writes never read as a drag or a state jump
        self._win_state = root.state()
        self._win_size = (root.winfo_width(), root.winfo_height())
        root.bind("<Configure>", self._on_root_configure, add="+")
        root.protocol("WM_DELETE_WINDOW", self._on_close)
        root.after(120, self._drain_queue)

    # --- global font zoom (CSS-rem style, see the font registry) -------

    def _bind_zoom(self) -> None:
        """Ctrl+MouseWheel and Ctrl+(numpad or plain) +/- zoom EVERY
        font from the one root size — bound on 'all', so SelectWindow
        and DocWindow answer too. The scrollable classes get the same
        wheel binding on their CLASS tag: their class <MouseWheel>
        handler would otherwise scroll BEFORE the 'all' handler runs
        (class tags come first), and within one tag the Control-
        qualified binding wins over the plain one."""
        self.root.bind_all("<Control-MouseWheel>", self._zoom_wheel)
        for cls in ("Text", "Listbox", "Treeview"):
            self.root.bind_class(
                cls, "<Control-MouseWheel>", self._zoom_wheel
            )
        for seq, step in (
            ("<Control-KP_Add>", 1),
            ("<Control-KP_Subtract>", -1),
            ("<Control-plus>", 1),
            ("<Control-minus>", -1),
            ("<Control-equal>", 1),  # the un-shifted + on main keyboards
        ):
            self.root.bind_all(seq, partial(self._zoom_key, step))

    def _zoom_wheel(self, event):
        self._zoom_step(1 if event.delta > 0 else -1)
        return "break"  # never ALSO scroll whatever is under the mouse

    def _zoom_key(self, step: int, _event):
        self._zoom_step(step)
        return "break"

    def _zoom_step(self, step: int) -> None:
        if set_font_base(widgets.FONT_BASE + step):
            self.status_var.set(
                f"font size {widgets.FONT_BASE} (Ctrl+wheel / Ctrl+'+'/'-')"
            )
            self._schedule_save()

    # --- global vertical scroll + collapse -----------------------------

    def _bind_wheel_routing(self) -> None:
        """Route the wheel so the pointer's widget scrolls, once. The
        inner scrollables (both dashboard Treeviews, the Log/DocWindow
        Text, the Collections Listbox) get a PERMANENT class <MouseWheel>
        that scrolls that widget and returns 'break', halting the
        bindtag chain BEFORE the outer ScrollFrame's 'all'-tag handler —
        so the inner widget scrolls and the outer view never also does.
        Everything else has no class wheel binding, so it bubbles to the
        outer view. Ctrl+wheel is unaffected: _bind_zoom's
        <Control-MouseWheel> on these same class tags is more specific
        than this plain <MouseWheel>, so a Ctrl event fires only zoom."""
        for cls in ("Treeview", "Text", "Listbox"):
            self.root.bind_class(cls, "<MouseWheel>", self._inner_wheel)

    def _inner_wheel(self, event):
        event.widget.yview_scroll(
            int(-event.delta / WHEEL_DELTA_UNIT), "units"
        )
        return "break"

    def _build_compact(self, parent) -> None:
        """The collapsed strip: one '[logo] Name [Start][Stop]' cluster
        per site. Built once (unpacked); _set_collapsed swaps it in for
        the full controls. The freshly-created Start/Stop buttons inherit
        the correct availability via each panel's set_run_state.

        GUI rework Phase 12: this is also where each site's visible_var
        starts driving _relayout_agents — wired here (not in
        _build_options) because _relayout_agents also hides/shows THESE
        clusters, so it needs them to already exist; both this method's
        own reassert loop and the fresh trace read/observe the SAME
        settled state, in the SAME loop, once."""
        self._compact_box = ttk.Frame(parent)
        self._compact_clusters: dict[str, ttk.Frame] = {}
        for key in sorted(SITES):
            cluster = self.agents[key].build_compact(self._compact_box)
            cluster.pack(side="left", padx=(0, COMPACT_CLUSTER_GAP_PX))
            self._compact_clusters[key] = cluster
        for key, panel in self.agents.items():
            panel.set_run_state(
                running=key in self._running,
                pending_restart=key in self._restart_jobs,
            )
            panel.visible_var.trace_add(
                "write", lambda *_a: self._relayout_agents()
            )

    def _relayout_agents(self) -> None:
        """Reconcile BOTH per-site surfaces — the full ``agents`` grid
        AND the collapsed strip's ``build_compact`` clusters — with the
        current ``visible_var`` of each (GUI rework Phase 12, spec item
        3A). Driven by the trace ``_build_compact`` wires on every
        panel's ``visible_var``, so a toggle click, a settings restore,
        and ``set_run_state``'s own forced re-show (a hidden site's job
        going live) all reach here the SAME way — one reconciliation
        function, not three call sites re-deriving it.

        ``_visible_agent_columns`` (pure, Tk-free) decides which column
        each VISIBLE site lands in, compacting toward 0 so hiding one
        site never leaves the other stuck in a half-width column with a
        dead gap beside it — the unused column's weight drops to 0 (the
        same reset-then-reassign technique ``DashGrid.relayout`` already
        uses) so the remaining panel's column takes all the freed width.
        The compact strip needs no such column bookkeeping: ``pack``
        already closes the gap on its own when one cluster is
        forgotten.

        GUI rework (owner 2026-07-21 layout fix): the SAME ``cols``
        result also drives each panel's OWN internal two-column-dense
        layout (``AgentPanel.set_dense_columns``) — exactly one visible
        panel means it spans the whole controls width, so its content
        switches from the narrow stack to switches-left/dropdowns-right;
        two visible panels keep today's narrow stack (each already only
        ~half width). A hidden panel is told the same way (harmless —
        it is not on screen) so it is already correctly laid out the
        moment a later toggle re-shows it."""
        visible = {
            key: panel.visible_var.get() for key, panel in self.agents.items()
        }
        cols = _visible_agent_columns(sorted(SITES), visible)
        dense = len(cols) == 1
        for c in range(len(SITES)):
            self._agents_frame.columnconfigure(c, weight=0)
        for key, panel in self.agents.items():
            shown = key in cols
            if shown:
                panel.grid(row=0, column=cols[key], sticky="nsew", padx=4)
                self._agents_frame.columnconfigure(cols[key], weight=1)
            else:
                panel.grid_remove()
            panel.set_dense_columns(dense)
            cluster = self._compact_clusters[key]
            if shown:
                cluster.pack(side="left", padx=(0, COMPACT_CLUSTER_GAP_PX))
            else:
                cluster.pack_forget()
        self._scroll.refresh()

    def _on_root_configure(self, event) -> None:
        """The root <Configure> watcher. One job now:

        * a same-state SIZE change is part of a continuous drag — mark
          the resize active and re-arm the settle timer; while active,
          _drain_queue buffers dashboard events so the trees / live
          labels stop re-rendering per frame (flushed on settle).

        A zoomed<->normal STATE change (maximize/restore) is tracked
        for bookkeeping ONLY (owner 2026-07-21 perf fix — previously
        wrapped in the shared smooth_transition snapshot cover, owner
        2026-07-20). Measured with a real window: covering it BREAKS
        the maximize/restore instead of hiding it — creating and
        force-painting the borderless topmost overlay Toplevel while
        Windows is mid-transition interrupts the OS's own resize/
        repaint, leaving the real window stuck at its OLD size (or,
        on restore, a corrupted double-painted frame) while Tk's own
        ``state()``/``winfo_width``/``winfo_height`` insist the change
        already happened. The OS/DWM already animates maximize/restore
        smoothly on its own — no cover was ever needed here, only for
        our OWN discrete Tk-level jumps (theme flip, Controls collapse,
        a Settings gear) where no native transition exists. Removing
        the cover fixes both the visible 'stuck small window' and the
        'lag' the owner reported, with zero loss (the ScrollFrame's own
        settle-debounced re-fit still runs off the canvas's real
        <Configure>, converging in one frame — no visible cascade).

        The handler sits on the ROOT bindtag, which every child widget
        carries too — the first line drops child configures, keeping
        the added per-frame cost one identity check."""
        if event.widget is not self.root:
            return
        state = self.root.state()
        size = (event.width, event.height)
        if state != self._win_state:
            self._win_state = state
            self._win_size = size
            return
        if size == self._win_size:
            return  # a pure move — nothing relayouts, nothing to do
        self._win_size = size
        self._resize_active = True
        if self._resize_settle_job is not None:
            self.root.after_cancel(self._resize_settle_job)
        self._resize_settle_job = self.root.after(
            RESIZE_SETTLE_MS, self._resize_settled
        )

    def _resize_settled(self) -> None:
        """The drag ended (RESIZE_SETTLE_MS after the last root
        <Configure>): flush every dashboard event buffered mid-drag, in
        arrival order, on the main thread."""
        self._resize_settle_job = None
        self._resize_active = False
        pending, self._pending_events = self._pending_events, []
        for msg in pending:
            self._dispatch(msg)

    def _clamp_geometry(self, geo: str) -> str:
        """Clamp a restored 'WxH' or 'WxH+X+Y' geometry so it never
        exceeds the screen (minus a margin) or sits off-screen — a stale
        too-tall geometry can otherwise hide the bottom past the screen
        edge. Unparseable strings pass through for Tk to try verbatim."""
        m = re.match(r"(\d+)x(\d+)(?:([+-]\d+)([+-]\d+))?$", geo)
        if not m:
            return geo
        w, h = int(m.group(1)), int(m.group(2))
        sw = self.root.winfo_screenwidth()
        sh = self.root.winfo_screenheight()
        w = max(WINDOW_MIN_W, min(w, max(WINDOW_MIN_W,
                                         sw - WINDOW_SCREEN_MARGIN_PX)))
        h = max(WINDOW_MIN_H, min(h, max(WINDOW_MIN_H,
                                         sh - WINDOW_SCREEN_MARGIN_PX)))
        if m.group(3) is None:
            return f"{w}x{h}"
        x, y = int(m.group(3)), int(m.group(4))
        x = min(max(x, 0), max(sw - w, 0))
        y = min(max(y, 0), max(sh - h, 0))
        return f"{w}x{h}+{x}+{y}"

    # --- construction --------------------------------------------------

    def _build_queue(self, parent) -> None:
        lf = ttk.Labelframe(
            parent, text="Collections (prompt .md files, one image set each)"
        )
        lf.pack(fill="x", pady=(0, 6))
        self.sheet_list = tk.Listbox(
            lf, height=5, activestyle="none", font=tk_font("mono")
        )
        skin_listbox(self.sheet_list)
        self.sheet_list.pack(side="left", fill="x", expand=True)
        col = ttk.Frame(lf)
        col.pack(side="left", padx=(8, 0), anchor="n")
        rounded_button(
            col, "Add…", command=self._add_sheets, icon_name="add",
            width=110, icon_edge=True,
        ).pack(fill="x")
        rounded_button(
            col, "Remove", command=self._remove_sheet, icon_name="remove",
            width=110, icon_edge=True,
        ).pack(fill="x", pady=4)
        rounded_button(
            col, "Clear", command=self._clear_sheets, icon_name="clear",
            width=110, icon_edge=True,
        ).pack(fill="x")
        rounded_button(
            col, "Add folder…", command=self._add_sheets_folder,
            icon_name="add", width=110, icon_edge=True,
        ).pack(fill="x", pady=(4, 0))

    def _build_options(self, parent) -> None:
        lf = ttk.Labelframe(parent, text="Output & run options")
        lf.pack(fill="x", pady=(0, 6))

        row = ttk.Frame(lf)
        row.pack(fill="x", pady=2)
        ttk.Label(row, text="Output:", width=8).pack(side="left")
        self.out_var = tk.StringVar(value=str(DEFAULT_OUT_DIR))
        rounded_entry(row, textvariable=self.out_var).pack(
            side="left", fill="x", expand=True
        )
        rounded_button(
            row, "Browse…", command=self._pick_out,
        ).pack(side="left", padx=(8, 0))

        # the shared "Show:" row (GUI rework Phase 12, spec item 3A) —
        # ABOVE both panels, deliberately never INSIDE either one: a
        # control that could hide itself would strand the owner with no
        # way back. Built once both panels exist below (loop first, row
        # second) since it needs each AgentPanel's build_visibility_
        # toggle; relayout wiring (the trace that actually grids/hides
        # the panels) is registered in _build_compact, once the
        # collapsed-strip clusters it also drives exist too.
        show_row = ttk.Frame(lf)
        show_row.pack(fill="x", pady=(0, 2))
        ttk.Label(show_row, text="Show:").pack(side="left")

        # the two per-agent panels side by side — everything below the
        # shared Output line is PER SITE (full agent separation)
        self._agents_frame = ttk.Frame(lf)
        self._agents_frame.pack(fill="x", pady=(4, 2))
        self.agents: dict[str, AgentPanel] = {}
        for i, key in enumerate(sorted(SITES)):
            panel = AgentPanel(
                self._agents_frame, key,
                on_start=self._start_site, on_stop=self._stop_site,
                on_pause=self._toggle_pause_job,
                filter_presets=self._filter_presets,
                on_filter_presets_changed=self._on_filter_presets_changed,
                on_log=self._log,
                on_layout_change=self._scroll.refresh,
            )
            panel.grid(row=0, column=i, sticky="nsew", padx=4)
            self._agents_frame.columnconfigure(i, weight=1)
            self.agents[key] = panel
            panel.build_visibility_toggle(show_row).pack(
                side="left", padx=(6, 0)
            )

    def _build_toolbar(self, parent) -> None:
        row = ttk.Frame(parent)
        row.pack(fill="x", pady=(0, 6))
        # "Open Chrome (login)"/"Check" used to live here — PINNED into
        # the always-visible _top_strip instead (owner 2026-07-21
        # workflow fix, Rule #5 — moved, not duplicated); see __init__'s
        # own comment beside self.btn_chrome/self.btn_check for why.
        self.btn_select = rounded_button(
            row, "Select images…", command=self._select_images,
        )
        self.btn_select.pack(side="left")
        rounded_button(
            row, "Instructions", command=self._open_instructions,
        ).pack(side="right")
        # the four in-place tools (BG removal / Crop / Upscale / Aspect
        # ratio) had their own quick-access buttons here through GUI
        # rework Phase 13, each opening the OLD _start_tool modal.
        # Deleted (Phase 14, _start_tool itself is gone): the IconBar
        # (GUI rework Phase 11) sits ABOVE this whole controls box
        # whenever it is visible and already carries all four tiles,
        # routed to their persistent ToolSettingsPanel via
        # _open_tool_panel — one click away regardless of which inline
        # panel (this one or a tool's own) currently shows below it, so
        # a second copy of the same four buttons here would be pure
        # duplication (Rule #5), not a shortcut. The AI checker's own
        # quick button below joined them in this deletion GUI rework
        # Phase 15, for the identical reason, once IT ALSO gained a
        # persistent ToolSettingsPanel (ImageCheckerSettingsPanel) the
        # IconBar reaches the same one-click way.

        # the AI features row (owner 2026-07-20): the sheet GENERATOR
        # and the guided key wizard — a SECOND row so the tool row
        # never clips at the window minimum. The batch image CHECKER's
        # own quick button used to sit here too (`_start_ai_check`
        # directly popping its folder dialog + confirm) — deleted GUI
        # rework Phase 15 alongside that dialog itself: the Main Menu/
        # IconBar's "image_checker" tile now opens
        # ImageCheckerSettingsPanel instead (see _tile_handler), the
        # same persistent-panel surface bg/crop/upscale/aspect already
        # have, so a second door to it here would be pure duplication
        # (Rule #5), not a shortcut — same reasoning as the four tools
        # above.
        ai_row = ttk.Frame(parent)
        ai_row.pack(fill="x", pady=(0, 6))
        rounded_button(
            ai_row, "New collection (AI)…", icon_name="ai",
            command=self._new_collection_ai,
        ).pack(side="left")
        rounded_button(
            ai_row, "AI key…", command=self._open_key_wizard,
        ).pack(side="right")

    def _build_views(self, parent) -> None:
        self.notebook = ttk.Notebook(parent)
        self.notebook.pack(fill="both", expand=True)

        dash_tab = ttk.Frame(self.notebook)
        self.notebook.add(dash_tab, text="Dashboard")
        # BUILD-ONCE per-JOB panels in a responsive DashGrid: the two gen
        # sites, the API Image GEN job (GUI rework Phase 19 — same
        # DashPanel the sites use, driven by the SAME run_sheet event
        # shape via _drive_site) plus the four tools, NONE gridded until
        # its job starts. A panel appears on Start / a tool click, gets
        # CLOSE when done, and the grid re-flows by active count (gen
        # sites first).
        self._dashgrid = DashGrid(dash_tab)
        self.panels: dict[str, JobPanel] = {}
        for key in ("chatgpt", "gemini", "api_image"):
            self.panels[key] = DashPanel(
                self._dashgrid, key,
                on_show=partial(self._show_node, key),
                on_close=self._close_panel,
                on_fix_actions=self._build_fix_workers,
            )
        for kind in JOB_TOOL_KINDS:
            self.panels[kind] = ToolPanel(
                self._dashgrid, kind, on_close=self._close_panel,
                on_pause=self._toggle_pause_job,
            )
        # the AI checker's own job slot (owner 2026-07-20) — the seventh
        # panel; its two actions call back into the GUI's engine glue
        self.panels["aicheck"] = AiCheckPanel(
            self._dashgrid, on_close=self._close_panel,
            on_resend=self._resend_flagged, on_clear=self._clear_ai_flags,
            on_pause=self._toggle_pause_job,
            on_fix_actions=self._build_fix_workers,
        )
        self._dashgrid.attach(self.panels)
        self._dashgrid.pack(fill="both", expand=True, padx=4, pady=4)

        log_tab = ttk.Frame(self.notebook)
        self.notebook.add(log_tab, text="Log (detailed)")
        self._log_tab = log_tab
        self.log_box = tk.Text(
            log_tab, height=16, state="disabled", font=tk_font("mono")
        )
        skin_text(self.log_box)
        log_vsb = ttk.Scrollbar(
            log_tab, orient="vertical", command=self.log_box.yview,
            bootstyle="round",
        )
        self.log_box.configure(yscrollcommand=log_vsb.set)
        log_vsb.pack(side="right", fill="y")
        self.log_box.pack(side="left", fill="both", expand=True)
