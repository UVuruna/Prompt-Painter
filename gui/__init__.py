"""PromptPainter GUI — the owner's front door.

A tkinter window over the same engine the CLI uses: queue one or MORE
prompt-sheet `.md` files (each file is a COLLECTION), pick the shared
output folder, open the automation Chrome (log in once — the profile
persists), then drive each site from its OWN AgentPanel — background,
the BG-removal/Crop/Upscale post-save switches, report, safer retry,
new-chat mode, pace ranges and its own Start/Stop. The sites run in
PARALLEL, one thread and one tab each, started and stopped
independently; each works through the queue IN ORDER, so a quota stop
on one site never costs finished work — progress and the report live
beside the images, every run resumes, and a quota stop with a known
reset time auto-restarts that site (countdown on its panel). All
remembered choices persist in settings.json.

Two views (tabs): a **Dashboard** (up to eight per-JOB panels — the
two websites, the paid-API image generation job, the four in-place
tools and the AI image checker — in a responsive grid that re-flows
as jobs start and close, each with its own progress, timings and
table) and the detailed **Log**.
"""

from __future__ import annotations

import math
import queue
import random
import re
import threading
import time
import tkinter as tk
import webbrowser
from dataclasses import replace
from datetime import datetime
from functools import partial
from pathlib import Path, PurePosixPath
from tkinter import filedialog, messagebox, ttk
from types import SimpleNamespace
from typing import Callable

import customtkinter as ctk
import ttkbootstrap as tb
from PIL import Image

from painter.config import (
    AI_CALL_PAUSE_S,
    AI_CHECK_INSTRUCTIONS,
    AI_IMAGE_GATE_MESSAGE,
    AI_STUDIO_URL,
    AI_TEST_PROMPT,
    BADGES,
    CDP_URL,
    DEFAULT_OUT_DIR,
    FILTER_PRESETS_SETTING,
    GEMINI_KEY_SETTING,
    GEMINI_VISION_MODEL,
    GRID_COLS_BY_COUNT,
    JOB_LABEL,
    JOB_LOGO,
    JOB_METRIC,
    JOB_ORDER,
    JOB_TOOL_KINDS,
    JOBTEMP_CAP_BANNER_TEXT,
    JOBTEMP_STEP_LABEL,
    MENU_TILES,
    MENU_TILE_BORDER_HOVER_PX,
    MENU_TILE_BORDER_PX,
    MENU_TILE_COLS,
    MENU_TILE_GAP_PX,
    MENU_TILE_H,
    MENU_TILE_ICON_PX,
    MENU_TILE_RADIUS,
    MENU_TILE_W,
    RESIZE_SETTLE_MS,
    SCROLL_FILL_HEIGHT_POLL_MS,
    SHEETS_DIR,
    SITES,
    STEP_RESTORE_CURRENT_LABEL,
    SWITCH_ANIM_MS,
    SWITCH_ASPECT,
    SWITCH_COVER_ICON_FRAC,
    SWITCH_COVER_ICON_SS,
    SWITCH_CRATER,
    SWITCH_CRATER_RIM,
    SWITCH_CRATER_RIM_ALPHA,
    SWITCH_CRATER_RIM_ARC_DEG,
    SWITCH_CRATER_RIM_FRAC,
    SWITCH_CRATERS,
    SWITCH_FADE_MS,
    SWITCH_FADE_STEPS,
    SWITCH_FRAME_MS,
    SWITCH_H,
    SWITCH_HOVER_SCALE,
    SWITCH_KNOB_FACTOR,
    SWITCH_KNOB_HILIGHT,
    SWITCH_MOON_CENTER,
    SWITCH_MOON_DARK_FLOOR,
    SWITCH_MOON_EDGE,
    SWITCH_MOON_LIGHT_DIR,
    SWITCH_MOON_NOISE_AMPL,
    SWITCH_MOON_NOISE_CELLS,
    SWITCH_MOON_NOISE_SEED,
    SWITCH_MOON_TERMINATOR_SOFT,
    SWITCH_PAD_PX,
    SWITCH_SUN_CELL_SCALE,
    SWITCH_SUN_CENTER,
    SWITCH_SUN_EDGE,
    SWITCH_SUN_GLOW,
    SWITCH_SUN_GLOW_ALPHA,
    SWITCH_SUN_GLOW_BLUR,
    SWITCH_SUN_GLOW_SCALE,
    SWITCH_SUPERSAMPLE,
    SWITCH_TRACK_DAY_SVG,
    SWITCH_TRACK_NIGHT_SVG,
    THEMES,
    TILE_JOB_KINDS,
    TIMING,
    TRANSITION_FADE_MS,
    TRANSITION_FADE_STEPS,
    UPSCALE_ASPECT_MAX,
    UPSCALE_ASPECT_MIN,
    UPSCALE_MIN_SIDE_DEFAULT,
    dest_for,
    fmt_duration,
    fmt_op_duration,
    fmt_pct,
    fmt_size,
    iter_md_files,
    badge_keys_for,
    button_fill_pair,
    button_text_pair,
    job_color_pair,
    prompt_suffix,
    status_pair,
    theme_pair,
    tile_for_kind,
)
from painter import aspect, config, jobtemp
from painter.settings import load_settings, save_settings
from painter.sheet_parser import Sheet, SheetError, parse_sheet
from . import widgets
from .agent_panel import AgentPanel
from .api_panel import ApiImageAdapter, ApiImageGenPanel
from .dash_helpers import (
    _checkerboard,
    _has_alpha,
    _scaled_photo,
    ai_check_doc_md,
    ai_check_image_file,
    ai_check_tag,
    badge_dots,
    build_job_tree,
    fmt_time_summary,
)
from .dash_panels import DashPanel, JobPanel
from .dialogs import (
    AI_POLL_MS,
    AiKeyWizard,
    AiSheetDialog,
    _AiDialog,
    _ModalToolDialog,
)
from .filter_editor import FilterEditor
from .icons import (
    ICON_DIR,
    ICON_TARGET_PX,
    SVG_OVERSAMPLE,
    _ICONS,
    _QT_APP,
    _QT_UNSUPPORTED_SVG,
    _radial_disc,
    _render_moon_knob,
    _render_sun_knob,
    _render_switch_track,
    _render_theme_cover_icon,
    _svg_to_pil,
    icon,
)
from .logic import (
    MENU_TILE_CELL_MIN_PX,
    _STAT_KEYS,
    _filter_files,
    _fix_result_ui,
    _fixer_decision,
    _gate_and_upscale,
    _menu_tile_columns,
    _migrate_legacy_aspect_filter,
    _migrate_legacy_upscale_gate,
    _next_view,
    _parse_condition_dicts,
    _run_pipeline_steps,
    _scope_stats,
    # not used by anything left in THIS module — re-exported only so
    # gui._upscale_params_from_side_and_filter (the established test
    # convention, e.g. test_gui_upscale.py) keeps resolving post-split;
    # AgentPanel/ApiImageGenPanel/UpscaleSettingsPanel each import their
    # OWN real-path copy straight from gui.logic instead (Rule #3).
    _upscale_params_from_side_and_filter,
    _visible_agent_columns,
)
from .menu import IconBar, MainMenu
from .scroll import WHEEL_DELTA_UNIT, ScrollFrame
from .select_window import SelectWindow
from .switch import DayNightSwitch
from .theme import (
    THEME_TOPLEVELS,
    THEMED_TK,
    TOOL_CHANGED_TAG,
    TOOL_SKIP_TAG,
    _TK_SKIN,
    _apply_listbox_skin,
    _apply_surface_skin,
    _apply_text_skin,
    _apply_theme_now,
    _apply_tree_skin,
    _fade_out_overlay,
    _skin,
    _snapshot_overlay,
    apply_theme,
    recolor_tk_registry,
    register_painter_day,
    setup_style,
    skin_canvas,
    skin_listbox,
    skin_text,
    skin_toplevel,
    skin_tree,
    smooth_transition,
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
from .viewers import (
    BeforeAfterWindow,
    DocWindow,
    StepRestoreWindow,
    _filmstrip_stages,
)
from .widgets import (
    BTN_HEIGHT,
    BTN_RADIUS,
    FONT_BASE_DEFAULT,
    FONT_MAX,
    FONT_MIN,
    FONT_MONOSPACE,
    FONT_ROLES,
    FONT_SANS,
    HOVER_DARKEN,
    INPUT_HEIGHT,
    INPUT_RADIUS,
    EdgeIconButton,
    Spinner,
    _button_colors,
    _CTK_FONTS,
    _darken,
    _darken_pair,
    _input_colors,
    # not used by anything left in THIS module — re-exported only so
    # gui._parse_fraction/_parse_nonneg_int/_parse_int_range (the
    # established test convention, e.g. test_gui_tool_panels.py) keep
    # resolving post-split; BgSettingsPanel/CropSettingsPanel import
    # their OWN real-path copy straight from gui.widgets instead
    # (Rule #3).
    _parse_fraction,
    _parse_int_range,
    _parse_nonneg_int,
    _style_icon_bar_button,
    _TK_FONTS,
    _untheme_inner_entry,
    ctk_font,
    folder_of,
    font_size,
    job_color,
    rels_in_folder,
    rounded_button,
    rounded_entry,
    set_font_base,
    status,
    style_action_button,
    tk_font,
)

# ---------------------------------------------------------------------
# Theming — TWO coordinated backbones flipped as one (owner 2026-07-18)
# ---------------------------------------------------------------------
# THEMES (painter/config.py) is the single source of truth. Every CTk
# colour kwarg below is a fixed (day, night) tuple via theme_pair(), so
# one ctk.set_appearance_mode() repaints all CTk controls with zero
# re-walk; ttk flips via theme_use() + a re-run of setup_style(); plain
# tk (Text/Listbox/Canvas/Toplevel) goes through the THEMED_TK role
# registry; and open Toplevels each expose apply_theme(). There is NO
# module-level appearance pin — startup applies the saved theme BEFORE
# building any widget, so no widget is ever born in the wrong theme.

# the LIVE theme name — status()/skinners read it at call time, so
# lazily-built widgets never hold a stale global





# --- AI checker (Rule #4) ---------------------------------------------
# The key-wizard/sheet-generator dialog constants (AI_KEY_ENTRY_W,
# AI_STATUS_WRAP_PX, AI_REQUEST_LINES, AI_STEP_INDENT_PX, AI_POLL_MS)
# and ASPECT_DIALOG_PAD_PX moved to gui/dialogs.py with _AiDialog/
# AiKeyWizard/AiSheetDialog (god-file refactor); JOB_PANEL_BANNER_WRAP_PX/
# DASH_CHECK_COL_PX moved to gui/dash_panels.py with JobPanel/DashPanel and
# AI_CHECK_DEFECT_COL_PX/AI_CHECK_TIME_COL_PX/AI_CHECK_FIRST_COL_PX moved to
# gui/tool_dash.py with AiCheckPanel (god-file refactor step 6/8);
# AI_CHECK_LOG_EVERY stays here — read by PainterGui's own checker worker.
AI_CHECK_LOG_EVERY = 5      # checker progress log cadence (paced calls are slow)

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


class PainterGui:
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
            ),
            "crop": CropSettingsPanel(
                self._main_view,
                on_start=self._start_tool_from_panel,
                on_pause=self._toggle_pause_job,
                on_stop=self._stop_tool,
                filter_presets=self._filter_presets,
                on_filter_presets_changed=self._on_filter_presets_changed,
            ),
            "upscale": UpscaleSettingsPanel(
                self._main_view,
                on_start=self._start_tool_from_panel,
                on_pause=self._toggle_pause_job,
                on_stop=self._stop_tool,
                filter_presets=self._filter_presets,
                on_filter_presets_changed=self._on_filter_presets_changed,
            ),
            "aspect": AspectSettingsPanel(
                self._main_view,
                on_start=self._start_tool_from_panel,
                on_pause=self._toggle_pause_job,
                on_stop=self._stop_tool,
                filter_presets=self._filter_presets,
                on_filter_presets_changed=self._on_filter_presets_changed,
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
        if self._view == "running":
            self._icon_bar.set_active(self._active_tile_ids())

    def _apply_running_layout(self) -> None:
        """Reconcile the region above the notebook for the running
        view: the IconBar is always shown, and exactly ONE inline
        surface always shows beneath it.

        ``_controls_box`` (the Collections queue + BOTH ``AgentPanel``s
        + toolbar) is the DEFAULT — owner 2026-07-21 workflow fix: it
        used to show ONLY while ``_inline_kind == "website_gen"``,
        which meant starting either site (their shared Start tail
        unconditionally clears ``_inline_kind`` to ``None``, see
        ``_start_site``) hid it immediately, stranding the owner with
        no visible way to Start the OTHER site and no visible
        Pause/Stop for the one just started. Now ``_controls_box``
        shows whenever ``_inline_kind`` does NOT name an entry in
        ``_tool_panels`` (``None`` or the legacy ``"website_gen"``
        marker alike) — it is superseded ONLY by an explicitly-open
        ``ToolSettingsPanel`` (BG/Crop/Upscale/Aspect, GUI rework Phase
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
        else:
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
        ``_inline_kind`` between "website_gen" and ``None`` (owner
        2026-07-21 workflow fix): it used to fall through to the
        "already active -> just focus the Dashboard" branch below
        whenever EITHER site was running, which dead-ended — the owner
        had no way back to ``_controls_box`` (and the OTHER site's
        Start) once some other inline surface (a tool's own settings
        panel) was showing instead. website_gen's inline surface is
        ``_controls_box`` itself, now the running view's DEFAULT (see
        ``_apply_running_layout``), so this toggle can never truly hide
        it any more either — at worst it is a no-op re-pack — but it
        ALWAYS supersedes whatever tool panel was open, which is the
        fix: the site controls are always one click away.

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

    # --- maximize/restore cover + drag-resize event buffering ----------

    def _on_root_configure(self, event) -> None:
        """The root <Configure> watcher (owner 2026-07-20). Two jobs:

        * a zoomed↔normal STATE change is a DISCRETE size jump
          (maximize / restore) — hide its relayout behind the shared
          snapshot cover. It can never fire mid-drag: the state stays
          'normal' through a whole drag, so a continuous resize is
          never covered;
        * a same-state SIZE change is part of a continuous drag — mark
          the resize active and re-arm the settle timer; while active,
          _drain_queue buffers dashboard events so the trees / live
          labels stop re-rendering per frame (flushed on settle).

        The handler sits on the ROOT bindtag, which every child widget
        carries too — the first line drops child configures, keeping
        the added per-frame cost one identity check."""
        if event.widget is not self.root:
            return
        state = self.root.state()
        size = (event.width, event.height)
        if state != self._win_state:
            prev, self._win_state = self._win_state, state
            self._win_size = size
            if {prev, state} <= {"zoomed", "normal"}:
                # ONE discrete jump — cover it while the relayout
                # settles behind the cover (mutate: nothing to do, the
                # WM already resized us; the settle happens inside)
                smooth_transition(self.root, lambda: None)
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

    def _close_panel(self, kind: str) -> None:
        """A finished panel's CLOSE button: remove it from the grid and
        clear that job's temp backups (any kind — a tool or, since GUI
        rework Phase 8, a gen site's own per-step pipeline backups). The
        panel widget survives (build-once) — reset_finished hides its
        CLOSE for the next run, and the next Start re-adds it."""
        self._dashgrid.remove(kind)
        self.panels[kind].reset_finished()
        temp = self._job_temps.pop(kind, None)
        if temp is not None:
            temp.clear()

    def _tool_panel_key(self, kind: str) -> str | None:
        """The ``_tool_panels`` dict key that owns ``kind``'s
        persistent settings panel, or None when ``kind`` has none
        (chatgpt/gemini use ``_controls_box`` instead — a DIFFERENT
        inline surface, see ``_toggle_pause_job``'s own "website_gen"
        special case). Identical to ``kind`` for the four standalone
        tools (tile id == slot, so ``config.tile_for_kind`` simply
        returns its own input back) and ``"image_checker"`` for
        ``"aicheck"`` (GUI rework Phase 15 — the one job kind whose
        MENU_TILES id differs from its JOB_ORDER slot). Central so a
        future standalone job kind never needs a new branch in
        ``_toggle_pause_job``/``_dispatch`` below, only a
        ``TILE_JOB_KINDS`` data entry."""
        tile_id = tile_for_kind(kind)
        return tile_id if tile_id in self._tool_panels else None

    def _toggle_pause_job(self, kind: str) -> None:
        """Flip ONE job's pause toggle (owner 2026-07-21) — the SAME
        handler wired to every job kind's btn_pause: AgentPanel's own
        (chatgpt/gemini) and ToolPanel's/AiCheckPanel's own (bg/crop/
        upscale/aspect/aicheck). Sets/clears this kind's
        threading.Event, polled by the runner (run_sheet's
        should_pause) or a tool/AI-check worker loop between items/
        images (painter.runner.wait_while_paused) — a Stop always wins
        over a pending pause (should_stop is re-checked on every poll
        tick, and _stop_site / the __worker_done__/__tool_done__
        handlers clear any leftover pause so a finished or freshly
        started job is never silently pre-paused). Reflects the new
        state onto every panel that shows this kind: the AgentPanel
        button for a site AND its DashPanel state line (JobPanel base),
        or the ToolPanel/AiCheckPanel button + state line (the same
        widget) for the other five kinds."""
        is_paused = kind not in self._paused
        if is_paused:
            self._paused.add(kind)
            self._pause_events[kind].set()
        else:
            self._paused.discard(kind)
            self._pause_events[kind].clear()
        if kind in self.agents:
            self.agents[kind].set_paused(is_paused)
        self.panels[kind].set_paused(is_paused)
        panel_key = self._tool_panel_key(kind)
        if panel_key is not None:
            # GUI rework Phase 13/15: keep the persistent panel's OWN
            # Pause/Resume label in sync too — it may be the panel the
            # very next line reveals (see below), or already hidden
            # (the owner navigated elsewhere) and simply catching up
            # for whenever it is opened again.
            self._tool_panels[panel_key].set_paused(is_paused)
        self._log(f"[{kind}] {'paused' if is_paused else 'resumed'}")
        # GUI rework Phase 11 (spec item 4): Pause RETURNS the settings
        # panel "for future tasks" — website_gen (chatgpt/gemini) shows
        # the shared _controls_box; every standalone job (bg/crop, GUI
        # rework Phase 13; upscale/aspect, Phase 14; the AI checker,
        # Phase 15) shows its OWN ToolSettingsPanel via _tool_panels,
        # the same way _open_tool_panel does — _tool_panel_key bridges
        # the AI checker's "aicheck" slot to its "image_checker" tile-
        # id key (see that method). Resuming never hides a revealed
        # panel back — only a fresh Start or the owner's own icon-bar
        # toggle does that.
        if is_paused and self._view == "running":
            if kind in ("chatgpt", "gemini"):
                self._inline_kind = "website_gen"
                self._apply_running_layout()
            elif panel_key is not None:
                self._inline_kind = panel_key
                self._apply_running_layout()

    def _open_instructions(self) -> None:
        path = config.PROJECT_ROOT / "instructions.md"
        try:
            text = path.read_text(encoding="utf-8")
        except OSError as exc:
            messagebox.showerror("PromptPainter", f"Cannot read {path}: {exc}")
            return
        DocWindow(
            self.root, "How to write a prompt sheet", text,
            hint="Give this to whoever (a person or an AI) writes the"
            " next prompt file.",
        )

    def _show_node(self, site_key: str, info: dict) -> None:
        """A dashboard row's 'Show': a collection opens its whole file,
        a FOLDER opens only that folder's excerpt of the sheet, an
        image opens its own prompt PLUS the saved image below it (when
        the destination file already exists)."""
        source = next(
            (p for p in self._sheets if p.name == info["sheet"]), None
        )
        if source is None:
            messagebox.showinfo(
                "PromptPainter",
                f"{info['sheet']} is no longer in the queue.",
            )
            return
        if info["level"] == "image":
            try:
                sheet = parse_sheet(source)
            except (SheetError, OSError) as exc:
                messagebox.showerror("PromptPainter", str(exc))
                return
            item = next(
                (it for it in sheet.items if it.drop_path == info["drop"]),
                None,
            )
            if item is None:
                messagebox.showinfo(
                    "PromptPainter",
                    f"No prompt found for {info['drop']} in {source.name}.",
                )
                return
            md = (
                f"# {item.title}\n\n`{item.drop_path}`\n\n"
                f"```\n{item.prompt}\n```\n"
            )
            dest = self._out_base() / dest_for(item.drop_path, site_key)
            DocWindow(
                self.root, item.drop_path, md, copy_text=item.prompt,
                hint="The prompt for this one image.",
                image_path=dest if dest.is_file() else None,
            )
        elif info["level"] == "folder":
            self._show_folder_excerpt(source, info["folder"])
        else:
            try:
                text = source.read_text(encoding="utf-8")
            except OSError as exc:
                messagebox.showerror("PromptPainter", str(exc))
                return
            DocWindow(self.root, source.name, text)

    def _show_folder_excerpt(self, source: Path, folder: str) -> None:
        """Only the contiguous portion of the sheet covering the
        entries whose drop paths live in ``folder`` — from the first
        such entry's heading line through the last one's prompt
        fence."""
        try:
            sheet = parse_sheet(source)
            lines = source.read_text(encoding="utf-8").splitlines()
        except (SheetError, OSError) as exc:
            messagebox.showerror("PromptPainter", str(exc))
            return
        members = [
            it for it in sheet.items
            if folder_of(it.drop_path) == folder
        ]
        if not members:
            messagebox.showinfo(
                "PromptPainter",
                f"No entries of {folder} found in {source.name}.",
            )
            return
        start = min(it.line for it in members) - 1  # entry line, 0-based
        # the excerpt ends at the closing fence of the LAST member's
        # prompt: scan from its heading for the opening ``` then the
        # closing one
        last = max(it.line for it in members) - 1
        end = len(lines) - 1
        fences = 0
        for i in range(last, len(lines)):
            if lines[i].lstrip().startswith("```"):
                fences += 1
                if fences == 2:
                    end = i
                    break
        excerpt = "\n".join(
            [f"# {sheet.theme} — {folder}", ""] + lines[start:end + 1]
        )
        DocWindow(
            self.root, folder, excerpt,
            hint=f"Only this folder's part of {source.name}.",
        )

    # --- helpers -------------------------------------------------------

    def _log(self, line: str) -> None:
        stamp = datetime.now().strftime("%H:%M:%S")
        self.log_box.configure(state="normal")
        self.log_box.insert("end", f"[{stamp}] {line}\n")
        self.log_box.see("end")
        self.log_box.configure(state="disabled")

    def _queue_sheets(self, paths) -> None:
        """Append PATHS to the collection queue, de-duplicated by path —
        the shared body behind Add… and Add folder… (also reused by the
        AI sheet generator's own queue-one-sheet call)."""
        for raw in paths:
            path = Path(raw)
            if path not in self._sheets:
                self._sheets.append(path)
                self.sheet_list.insert("end", path.name)
        self._schedule_save()

    def _add_sheets(self) -> None:
        paths = filedialog.askopenfilenames(
            title="Prompt sheets", filetypes=[("Markdown", "*.md")]
        )
        self._queue_sheets(paths)

    def _add_sheets_folder(self) -> None:
        """'Add folder…' — every ``.md`` sheet under a chosen folder,
        however nested, queued in one go (recursive, same de-dup rule
        as Add…)."""
        folder = filedialog.askdirectory(
            title="Folder with prompt sheets (.md)"
        )
        if not folder:
            return
        self._queue_sheets(iter_md_files(folder))

    def _remove_sheet(self) -> None:
        for index in reversed(self.sheet_list.curselection()):
            self.sheet_list.delete(index)
            del self._sheets[index]
        self._schedule_save()

    def _clear_sheets(self) -> None:
        self.sheet_list.delete(0, "end")
        self._sheets.clear()
        self._schedule_save()

    def _pick_out(self) -> None:
        path = filedialog.askdirectory(title="Output folder")
        if path:
            self.out_var.set(path)

    def _out_base(self) -> Path:
        return Path(
            self.out_var.get().strip() or str(DEFAULT_OUT_DIR)
        ).resolve()

    def _done_on_disk(self, site: str, sheet: Sheet) -> set:
        """Drop paths whose saved FILE already exists for one
        site+collection — the SAME dest the runner writes to
        (``out_base / dest_for``). "Done" means the image is really on
        disk (owner 2026-07-19), not merely recorded in a sidecar: a
        done item can be re-ticked to regenerate, and an item only
        recorded elsewhere never falsely reads as done."""
        out_base = self._out_base()
        return {
            item.drop_path
            for item in sheet.items
            if (out_base / dest_for(item.drop_path, site)).exists()
        }

    def _parse_all(self) -> list[Sheet]:
        """Parse every queued sheet; broken ones are reported and
        dropped from the run (the fix belongs in the sheet)."""
        good: list[Sheet] = []
        for path in self._sheets:
            try:
                sheet = parse_sheet(path)
            except (SheetError, OSError) as exc:
                self._log(f"SHEET SKIPPED: {exc}")
                continue
            if sheet.problems:
                for pr in sheet.problems:
                    self._log(
                        f"  PROBLEM {path.name} L{pr.line}: {pr.message}"
                    )
                self._log(
                    f"SHEET SKIPPED (contract problems): {path.name} —"
                    " fix the sheet and rerun"
                )
                continue
            self._log(
                f"OK {path.name}: {sheet.theme} —"
                f" {len(sheet.items)} to generate,"
                f" {len(sheet.skipped)} skipped"
            )
            for it in sheet.items:
                if it.advice:
                    self._log(
                        f"    ADVICE (unticked by default, L{it.line})"
                        f" {it.title} — {it.advice}"
                    )
            for sk in sheet.skipped:
                self._log(
                    f"    NO PROMPT in the sheet (L{sk.line})"
                    f" {sk.title} — {sk.reason}"
                )
            good.append(sheet)
        return good

    def _plan(
        self,
        site: str,
        sheets: list[Sheet],
        selection: dict[str, set[str] | None],
    ) -> tuple[int, int]:
        """Mirror run_sheet's queue rule to pre-count this run's scope:
        (total images to generate, number of themes with work). A
        ticked selection generates EXACTLY those items (regenerate
        included — file existence ignored); with no selection the
        runner resumes by FILE EXISTENCE and sits advice out."""
        total = 0
        themes = 0
        for sheet in sheets:
            sel = selection.get(str(sheet.source))
            if sel is not None:
                pending = [it for it in sheet.items if it.drop_path in sel]
            else:
                done = self._done_on_disk(site, sheet)
                pending = [
                    it for it in sheet.items
                    if it.drop_path not in done and not it.advice
                ]
            if pending:
                total += len(pending)
                themes += 1
        return total, themes

    # --- actions -------------------------------------------------------

    def _open_chrome(self) -> None:
        # both sites' tabs — a site "participates" by being Started,
        # and a spare logged-in tab costs nothing
        urls = tuple(SITES[k].url for k in sorted(SITES))
        self.status_var.set("opening Chrome …")

        def work():
            from painter.chrome import ChromeError, ensure_chrome

            try:
                state = ensure_chrome(urls)
            except ChromeError as exc:
                self._q.put(f"CHROME ERROR: {exc}")
                self._q.put(("__status__", "idle"))
                return
            if state == "launched":
                self._q.put(
                    "Chrome opened with the PromptPainter profile — log in"
                    " on each site tab once, then press Start."
                )
            else:
                self._q.put("Chrome already running — ready.")
            self._q.put(("__status__", "idle"))

        threading.Thread(target=work, daemon=True).start()

    def _check_sheets(self) -> None:
        if not self._sheets:
            messagebox.showerror("PromptPainter", "Add sheet .md files first.")
            return
        # show the output happening — Check reports into the log
        self.notebook.select(self._log_tab)
        self._parse_all()

    def _select_var(
        self, site: str, source: str, drop: str, default: bool = True
    ) -> tk.BooleanVar:
        key = (site, source, drop)
        if key not in self._select_vars:
            self._select_vars[key] = tk.BooleanVar(value=default)
        return self._select_vars[key]

    def _select_images(self) -> None:
        if not self._sheets:
            messagebox.showerror("PromptPainter", "Add sheet .md files first.")
            return
        sheets = self._parse_all()
        if not sheets:
            messagebox.showerror(
                "PromptPainter", "No usable sheets in the queue."
            )
            return
        SelectWindow(self, sheets)

    # --- the in-place tools (each its own concurrent job + panel) ------

    def _on_filter_presets_changed(self) -> None:
        """A FilterEditor mutates ``self._filter_presets`` (the shared
        dict reference passed at construction) IN PLACE on Save/Delete
        — this just schedules the debounced settings save (the same
        ``_schedule_save`` every other remembered choice already uses)
        so the change survives the next autosave/close instead of
        being silently dropped by ``_collect_settings``'s next
        full-file rewrite (settings.json is always a full overwrite,
        never a merge — see ``_save_now``)."""
        self._schedule_save()

    def _start_tool_from_panel(self, slot: str) -> None:
        """Start button on a persistent ``ToolSettingsPanel`` — ALL
        FOUR standalone tools since GUI rework Phase 14 (BG/Crop,
        Phase 13; Upscale/Aspect, Phase 14, replacing their old
        UpscaleParamsDialog/AspectRatioDialog modal askdirectory+
        confirm flow, now deleted): reads the panel's OWN input pick +
        filter + Advanced/extra overrides (dropped here: the panel
        itself, deliberately configured then Started, already IS the
        confirmation — no separate askyesno), pre-filters via the
        shared ``_filter_files``, then hands off to ``_launch_tool_
        worker`` (one-job-per-kind guard, JobTemp, worker spawn,
        dashboard reveal) — the ONE tail every tool's Start shares."""
        if slot in self._tool_workers:
            messagebox.showerror(
                "PromptPainter",
                f"{JOB_LABEL[slot]} is already running — wait for it to"
                " finish, or Close its panel.",
            )
            return
        panel = self._tool_panels[slot]
        try:
            folder_path, files = panel.resolve_input()
            conditions = panel.get_conditions()
            func = panel.build_func()
        except ValueError as exc:
            messagebox.showerror("PromptPainter", str(exc))
            return
        files = _filter_files(files, conditions, self._log)
        self._launch_tool_worker(slot, JOB_LABEL[slot], func, folder_path, files)
        panel.set_run_state(running=True)
        # Start hides the launching panel (spec item 4, mirrors
        # _start_site's own "_inline_kind = None" — but ALSO forces an
        # immediate re-layout: _sync_running_state (inside
        # _launch_tool_worker) is a no-op here because the view is
        # ALREADY "running" — the panel can only be visible while it
        # is — so nothing else would re-pack the region above the
        # notebook without this explicit call.
        self._inline_kind = None
        self._apply_running_layout()

    def _launch_tool_worker(
        self, slot: str, label: str, func, folder_path: Path,
        files: list[Path],
    ) -> None:
        """Shared tail for EVERY standalone-tool Start (all four are
        panel-driven since GUI rework Phase 14 — ``_start_tool_from_
        panel``): create this run's JobTemp, reveal the dashboard
        ``ToolPanel``, spawn ``_run_tool_job`` on its own daemon
        thread. A stale Stop flag from a PREVIOUS run of this slot is
        swept here too (mirrors ``_start_site``'s own ``self.
        _stop_events[key].clear()`` — a fresh job must never start
        pre-stopped)."""
        # a finished panel for this slot may still be on screen — clear
        # its old temp before the new job takes the slot
        old = self._job_temps.pop(slot, None)
        if old is not None:
            old.clear()
        temp = jobtemp.JobTemp(slot, folder_path)
        self._job_temps[slot] = temp

        panel = self.panels[slot]
        panel.folder = folder_path
        panel.jobtemp = temp
        panel.reset(active=True, total=len(files))
        self._dashgrid.add(slot)
        self.notebook.select(0)
        self.status_var.set(f"{label} running …")

        if slot in self._paused:
            self._toggle_pause_job(slot)  # a fresh job never starts pre-paused
        self._stop_events[slot].clear()  # ditto for a stale Stop
        worker = threading.Thread(
            target=self._run_tool_job,
            args=(
                slot, label, func, folder_path, files, temp,
                self._pause_events[slot], self._stop_events[slot],
            ),
            daemon=True,
        )
        self._tool_workers[slot] = worker
        worker.start()
        self._sync_running_state()  # GUI rework Phase 11

    def _run_tool_job(
        self, slot, label, func, folder, files, temp, pause_event,
        stop_event,
    ) -> None:
        """One tool job on its own thread: back up each original, run
        the engine func in place, measure BEFORE→AFTER, and stream item
        events to the slot's panel. A crash on one file is loud and
        counted FAILED (its no-op backup dropped), never kills the job.
        The measure is computed OUTSIDE the engine, from the backup vs
        the in-place result (Rule #10 progress every 25). ``pause_event``
        (owner 2026-07-21) blocks BETWEEN images while set. ``stop_event``
        (GUI rework Phase 14, ``PainterGui._stop_tool``) is checked at
        the SAME between-images boundary — mirrors ``run_sheet``'s own
        ``should_stop`` exactly: the in-flight image always finishes
        first, and it is also threaded into ``wait_while_paused`` so a
        Stop wins over a pending Pause instead of hanging until
        Resume."""
        from painter.runner import wait_while_paused

        emit = lambda ev: self._q.put(("__event__", slot, ev))
        log = lambda msg: self._q.put(f"[{label}]     {msg}")
        try:
            self._q.put(f"[{label}] {len(files)} image(s) under {folder}")
            emit({"type": "sheet_start", "total": len(files)})
            counts: dict[str, int] = {}
            t0 = time.time()
            for i, src in enumerate(files, start=1):
                if stop_event.is_set():
                    log(
                        f"STOPPED on request —"
                        f" {sum(counts.values())}/{len(files)} this run"
                    )
                    break
                if wait_while_paused(
                    pause_event.is_set, stop_event.is_set, log, emit
                ):
                    log(
                        f"STOPPED on request —"
                        f" {sum(counts.values())}/{len(files)} this run"
                    )
                    break
                rel = src.relative_to(folder).as_posix()
                emit({
                    "type": "item_start", "idx": i, "of": len(files),
                    "title": src.name,
                })
                temp.backup(src, rel)  # the ORIGINAL, before the op
                t_item = time.time()
                try:
                    status = func(src, log)
                except Exception as exc:
                    status = "FAILED"
                    self._q.put(f"[{label}] FAIL {src.name}: {exc}")
                op_s = time.time() - t_item  # this image's op time
                # "changed" keys on the engine ACTUALLY REWRITING the file
                # ("done"), never on a resolution/metric change (owner
                # 2026-07-19): a 3px crop or a small BG clear rounds the
                # metric to 0% yet the file WAS modified, so its backup +
                # before/after must survive. The engine already returns
                # "nothing" for a true no-op (byte-unchanged), so a "done"
                # is always a real, restorable change.
                metric = (
                    jobtemp.measure(slot, temp.before_path(rel), src)
                    if status == "done" else None
                )
                counts[status] = counts.get(status, 0) + 1
                if status == "done":
                    emit({
                        "type": "item_done", "rel": rel, "time": op_s,
                        "size": src.stat().st_size, **metric,
                    })
                else:  # nothing / unclear / FAILED -> unchanged file
                    temp.drop(rel)  # no restore point for a no-op
                    emit({"type": "item_refused", "rel": rel})
                if i % 25 == 0:
                    self._q.put(
                        f"[{label}] [{time.time() - t0:.0f}s]"
                        f" {i}/{len(files)}"
                    )
            emit({"type": "sheet_done"})
            summary = ", ".join(f"{k}={v}" for k, v in sorted(counts.items()))
            self._q.put(f"[{label}] done: {summary or 'no images'}")
        finally:
            self._q.put(("__tool_done__", slot))

    # --- the AI features (owner 2026-07-20) ----------------------------

    @property
    def gemini_key(self) -> str:
        return self._gemini_key

    def set_gemini_key(self, key: str) -> None:
        """The wizard's Save: remember + persist IMMEDIATELY (painter.ai
        reads the key back from settings.json on every call, so the
        debounced save would race a feature started right after)."""
        self._gemini_key = key
        self._save_now()
        self._log("Gemini API key saved to settings.json")

    def _open_key_wizard(self) -> None:
        AiKeyWizard(self.root, self)

    def _ensure_ai_key(self) -> bool:
        """True when a key is on disk. On ``NoKey`` the guided wizard
        opens AUTOMATICALLY (the spec'd auto-open) and the key is
        re-checked once it closes."""
        from painter import ai

        try:
            ai.api_key()
            return True
        except ai.NoKey:
            self._log("AI: no Gemini API key — opening the guided wizard")
            AiKeyWizard(self.root, self)
        try:
            ai.api_key()
            return True
        except ai.NoKey:
            self._log("AI: still no key — cancelled")
            return False

    def _new_collection_ai(self) -> None:
        """'New collection (AI)…' — the request -> questions -> sheet
        flow lives in its own dialog; only the key gate sits here."""
        if not self._ensure_ai_key():
            return
        AiSheetDialog(self.root, self)

    def add_generated_sheet(self, path: Path) -> None:
        """Queue one AI-generated sheet (the same de-dup rule as Add…)."""
        self._queue_sheets([path])

    def _start_ai_check(self, slot: str) -> None:
        """Start on the AI checker's persistent settings panel
        (``ImageCheckerSettingsPanel``, GUI rework Phase 15) — a batch
        vision pass over a folder/files as its OWN job/panel (read-
        only: it writes NOTHING but the flag file under
        ``<out>/_state/``). One job at a time, like the four tools.

        Previously this method owned its own ``askdirectory`` folder
        pick + a confirm ``askyesno`` — both DELETED here (Rule #6):
        the panel's own input picker + embedded ``FilterEditor`` (see
        ``ToolSettingsPanel``) now cover the folder/files choice, and
        Start — deliberately configured then clicked — already IS the
        confirmation, the same contract ``_start_tool_from_panel``
        established for the four tools (the panel's own footer note
        carries what the confirm dialog used to say about pacing/
        model/where flags persist). Unlike those four, this does NOT
        go through ``_start_tool_from_panel``/``_launch_tool_worker``
        — the checker's worker (``_run_ai_check_job``) has no
        JobTemp/engine-func shape to share with ``_run_tool_job`` (see
        ``ImageCheckerSettingsPanel``'s own docstring), so its spawn is
        inlined here instead, by hand mirroring ``_launch_tool_
        worker``'s own tail (stale-Stop sweep, stale-pause sweep,
        dashboard reveal, thread spawn, ``_sync_running_state``)."""
        if slot in self._tool_workers:
            messagebox.showerror(
                "PromptPainter",
                f"{JOB_LABEL[slot]} is already running — wait for it"
                " to finish, or Close its panel.",
            )
            return
        if not self._ensure_ai_key():
            return
        panel = self._tool_panels["image_checker"]
        try:
            folder_path, files = panel.resolve_input()
            conditions = panel.get_conditions()
        except ValueError as exc:
            messagebox.showerror("PromptPainter", str(exc))
            return
        files = _filter_files(files, conditions, self._log)
        out_base = self._out_base()

        dash = self.panels[slot]
        dash.folder = folder_path
        dash.out_base = out_base
        dash.reset(active=True, total=len(files))
        self._dashgrid.add(slot)
        self.notebook.select(0)
        self.status_var.set(f"{JOB_LABEL[slot]} running …")

        if slot in self._paused:
            self._toggle_pause_job(slot)  # never start pre-paused
        self._stop_events[slot].clear()  # ditto for a stale Stop (Phase 15)
        worker = threading.Thread(
            target=self._run_ai_check_job,
            args=(
                folder_path, files, out_base, self._pause_events[slot],
                self._stop_events[slot],
            ),
            daemon=True,
        )
        self._tool_workers[slot] = worker
        worker.start()
        panel.set_run_state(running=True)
        # Start hides the launching panel (spec item 4, mirrors
        # _start_tool_from_panel's own tail) — the view is already
        # "running" (this panel can only be visible while it is), so
        # _sync_running_state()'s own view-transition check is a no-op
        # here; this explicit call is what actually re-packs the region.
        self._inline_kind = None
        self._apply_running_layout()
        self._sync_running_state()  # GUI rework Phase 11

    def _run_ai_check_job(
        self, folder, files, out_base, pause_event, stop_event,
    ) -> None:
        """The checker worker: prune stale flags (regenerated files),
        then one paced vision call per image — flagged entries are
        recorded (merged) into the flag file as they land, an OK image
        CLEARS any old flag it had, and a per-image API failure is loud
        but never kills the batch (the tool-job convention).
        ``pause_event`` (owner 2026-07-21) blocks BETWEEN images while
        set. ``stop_event`` (GUI rework Phase 15, closing Phase 14's
        own flagged gap for THIS job) is checked at the SAME between-
        images boundary — mirrors ``_run_tool_job``'s/``run_sheet``'s
        own ``should_stop`` exactly: the in-flight vision call always
        finishes first, and it is also threaded into
        ``wait_while_paused`` so a Stop wins over a pending Pause
        instead of hanging until Resume."""
        from painter import ai
        from painter.runner import wait_while_paused

        emit = lambda ev: self._q.put(("__event__", "aicheck", ev))
        log = lambda msg: self._q.put(f"[AI check] {msg}")
        try:
            log(
                f"{len(files)} image(s) under {folder} — model"
                f" {GEMINI_VISION_MODEL}, paced {AI_CALL_PAUSE_S:.0f}s/call"
            )
            ai.prune_stale_flags(out_base, log)
            emit({"type": "sheet_start", "total": len(files)})
            flagged = ok = errors = 0
            # check_one_image's kind -> the panel event type it emits
            event_type = {
                "flagged": "item_flagged",
                "ok": "item_ok",
                "error": "item_error",
            }
            t0 = time.time()
            for i, src in enumerate(files, start=1):
                if stop_event.is_set():
                    log(
                        f"STOPPED on request —"
                        f" {flagged + ok + errors}/{len(files)} this run"
                    )
                    break
                if wait_while_paused(
                    pause_event.is_set, stop_event.is_set, log, emit
                ):
                    log(
                        f"STOPPED on request —"
                        f" {flagged + ok + errors}/{len(files)} this run"
                    )
                    break
                emit({
                    "type": "item_start", "idx": i, "of": len(files),
                    "title": src.name,
                })
                # check_one_image does the timing, parse, flag merge/clear
                # and the FLAGGED/FAIL logging; the loud-but-never-fatal
                # AiError handling lives inside it (the tool-job convention)
                result = ai.check_one_image(
                    src, out_base, AI_CHECK_INSTRUCTIONS, log=log
                )
                kind = result["kind"]
                event = {
                    "type": event_type[kind], "rel": result["rel"],
                    "raw": result["raw"], "time": result["time"],
                }
                if kind == "flagged":
                    flagged += 1
                    event["defects"] = result["defects"]
                elif kind == "ok":
                    ok += 1
                else:
                    errors += 1
                emit(event)
                if i % AI_CHECK_LOG_EVERY == 0:
                    self._q.put(
                        f"[AI check] [{time.time() - t0:.0f}s]"
                        f" {i}/{len(files)} ({i / len(files) * 100:.0f}%)"
                    )
            emit({"type": "sheet_done"})
            log(
                f"done: {flagged} flagged, {ok} OK, {errors} error(s) —"
                f" flags in {ai.flags_path(out_base)}"
            )
        finally:
            self._q.put(("__tool_done__", "aicheck"))

    def _resend_flagged(self, flagged: dict[str, list[str]]) -> None:
        """The AI-check panel's 'Send flagged to generator': map every
        flagged image back to its (site, drop path) — the ``dest_for``
        reverse — match it against the QUEUED collections, and start
        each matched site with ``only=`` exactly those items plus a
        per-item fix note appended to the prompt (the regenerate path,
        overwriting the flawed file). Unmatched images and an
        already-running site are LOUD skips, never silent."""
        from painter import ai

        if not self._sheets:
            messagebox.showerror(
                "PromptPainter",
                "The Collections queue is empty — Add… the sheet(s) the"
                " flagged images came from, then Send again.",
            )
            return
        sheets = self._parse_all()
        drop_to_source = {
            item.drop_path: str(sheet.source)
            for sheet in sheets
            for item in sheet.items
        }
        plans, notes, unmatched = ai.plan_resend(flagged, drop_to_source)
        for key, why in unmatched:
            self._log(f"[AI check] NO MATCH ({why}): {key} — skipped")
        if not plans:
            messagebox.showinfo(
                "PromptPainter",
                "None of the flagged images matches a queued collection"
                " — queue the sheet(s) they came from and Send again.",
            )
            return
        for site in sorted(plans):
            if site in self._running:
                self._log(
                    f"[{site}] already running — flagged re-send skipped"
                    " (Stop it first, then Send again)"
                )
                continue
            count = sum(len(drops) for drops in plans[site].values())
            self._log(
                f"[{site}] AI re-send: {count} flagged image(s), each"
                " with its fix note"
            )
            self._start_site(
                site, override_selection=plans[site],
                extra_suffix=notes[site],
            )

    def _clear_ai_flags(self, out_base: Path, keys: list[str]) -> int:
        """The panel's Clear-flags action — drops the given entries from
        the flag file; returns the number actually removed."""
        from painter import ai

        cleared = ai.clear_flag_keys(out_base, keys, self._log)
        self._log(
            f"[AI check] {cleared} flag(s) cleared from"
            f" {ai.flags_path(out_base)}"
        )
        return cleared

    def _compose_post_save(self, key: str, panel=None):
        """The job's post-save hook per ITS panel switches — the same
        shape the CLI builds: ``post_save(path) -> "REMOVE BG: done,
        CROP: done, ASPECT: done, ..."`` (the runner logs the
        description and guards the call itself — a failing step never
        kills the run). Returns None when every switch is off, or the
        deps-problem string when the steps cannot run at all.

        GUI rework Phase 8: the pipeline order is BG -> Crop ->
        Aspect(force) -> Upscale (``_run_pipeline_steps`` runs whichever
        of those four are enabled, in that fixed order — never
        reordered by which switches happen to be on); with Force Aspect
        OFF (its default) this is BYTE-IDENTICAL to the pre-Phase-8
        pipeline — the new per-step JobTemp backups only ever COPY
        bytes elsewhere, they never touch ``path`` itself, so the final
        saved image is unaffected either way.

        ``panel`` (GUI rework Phase 19, optional): the caller's own
        panel object when it is not one of ``self.agents`` — the API
        Image GEN job's ``ApiImageGenPanel`` lives in ``_tool_panels``
        instead (see ``_start_api_image``), but exposes the EXACT same
        bg_removal_var/crop_var/force_aspect_var/upscale_var/
        upscale_params()/upscale_conditions()/force_aspect_ratio()/
        keep_all_steps_var surface, so this whole method is reused
        UNCHANGED rather than duplicated (Rule #5). ``None`` (every
        existing chatgpt/gemini caller) keeps the exact old lookup."""
        panel = panel if panel is not None else self.agents[key]
        do_bg = panel.bg_removal_var.get()
        do_crop = panel.crop_var.get()
        do_aspect = panel.force_aspect_var.get()
        do_upscale = panel.upscale_var.get()
        if not (do_bg or do_crop or do_aspect or do_upscale):
            return None

        from painter.postprocess import deps_error

        problem = deps_error()
        if problem:
            return problem

        # this agent's upscale-gate kwargs AND its full filter stack, read
        # ONCE at Start (like the pace values) — validated by the caller
        # before we get here. Both are needed: up_params is the simple
        # min-side/aspect kwargs upscale_if_small takes; up_conditions is
        # the FULL stack (aspect AND any stacked Width/Height/Any-side
        # rows), checked via _gate_and_upscale so nothing is silently
        # dropped (root Rule #1 — see _upscale_params_from_side_and_filter).
        up_params = panel.upscale_params() if do_upscale else {}
        up_conditions = panel.upscale_conditions() if do_upscale else []
        # the Force-Aspect target ratio, read ONCE the same way — already
        # validated by the caller's Start checks (see _start_site)
        force_w, force_h = panel.force_aspect_ratio() if do_aspect else (0, 0)
        keep_all_steps = panel.keep_all_steps_var.get()
        log = lambda msg: self._q.put(f"[{key}]     {msg}")
        # this site's JobTemp, created by _start_site right before this
        # method runs (None only in a headless/test caller that never
        # went through _start_site — _run_pipeline_steps treats that as
        # "no backups", the pipeline steps themselves still run normally)
        temp = self._job_temps.get(key)
        emit = lambda ev: self._q.put(("__event__", key, ev))
        cap_warned = False  # the ONE loud banner per Start, never per image

        def on_cap() -> None:
            nonlocal cap_warned
            if not cap_warned:
                cap_warned = True
                emit({"type": "over_cap"})

        def post_save(path: Path) -> str:
            from painter.postprocess import (
                crop_transparent,
                remove_background,
            )

            steps: list[tuple[str, str, Callable[[Path], str]]] = []
            if do_bg:
                steps.append(
                    ("REMOVE BG", "bg", lambda p: remove_background(p, log))
                )
            if do_crop:
                steps.append(
                    ("CROP", "crop", lambda p: crop_transparent(p, log))
                )
            if do_aspect:
                steps.append((
                    "ASPECT", "aspect",
                    lambda p: aspect.change_aspect(p, force_w, force_h, log),
                ))
            if do_upscale:
                steps.append((
                    "UPSCALE", "upscale",
                    lambda p: _gate_and_upscale(
                        p, log, up_conditions, up_params
                    ),
                ))
            return _run_pipeline_steps(
                path, steps, temp, keep_all_steps, on_cap,
            )

        return post_save

    def _start_site(
        self,
        key: str,
        override_selection: dict[str, set[str]] | None = None,
        extra_suffix: dict[str, str] | None = None,
    ) -> None:
        """Start ONE site — the other site's run is never touched.

        ``override_selection`` (the AI checker's re-send, owner
        2026-07-20) replaces the Select-window ticks with an explicit
        per-sheet drop-path set and narrows the run to EXACTLY those
        sheets; ``extra_suffix`` rides along to the runner so each
        re-sent item carries its fix note. The plain Start (buttons,
        quota auto-restart) passes neither.
        """
        if key in self._running:
            return
        self._cancel_restart(key)  # a manual Start beats the timer
        if not self._sheets:
            messagebox.showerror("PromptPainter", "Add sheet .md files first.")
            return
        sheets = self._parse_all()
        if override_selection is not None:
            # the re-send drives ONLY the sheets carrying flagged items
            sheets = [
                s for s in sheets if str(s.source) in override_selection
            ]
        if not sheets:
            messagebox.showerror(
                "PromptPainter", "No usable sheets in the queue."
            )
            return
        out_base = self._out_base()
        for sheet in sheets:
            if sheet.source.resolve().is_relative_to(out_base):
                messagebox.showerror(
                    "PromptPainter",
                    f"{sheet.source.name} lives inside the output folder"
                    " — sources are READ ONLY; pick another output.",
                )
                return
        # the progress sidecar and report are keyed by filename stem, so
        # two queued themes with the same filename would collide
        stems = [s.source.stem for s in sheets]
        dupes = sorted({s for s in stems if stems.count(s) > 1})
        if dupes:
            messagebox.showerror(
                "PromptPainter",
                "Two queued collections share a filename: "
                + ", ".join(dupes)
                + ".\nTheir progress/report files would collide — rename"
                " one before running.",
            )
            return

        panel = self.agents[key]
        try:
            pause_min, pause_max, act_min, act_max = panel.pace_floats()
        except ValueError:
            messagebox.showerror(
                "PromptPainter",
                f"{SITES[key].name}: pause/delay must be numbers.",
            )
            return
        if pause_min > pause_max or act_min > act_max:
            messagebox.showerror(
                "PromptPainter",
                f"{SITES[key].name}: FROM must be <= TO (pause and delay).",
            )
            return
        if panel.upscale_var.get():
            try:
                up = panel.upscale_params()
            except ValueError:
                messagebox.showerror(
                    "PromptPainter",
                    f"{SITES[key].name}: Upscale-gate min side must be a"
                    " number, and every filter row must be a valid"
                    " number (FROM <= TO).",
                )
                return
            if up["min_width"] <= 0:
                messagebox.showerror(
                    "PromptPainter",
                    f"{SITES[key].name}: Upscale-gate min side must be"
                    " positive.",
                )
                return
            # NOTE: no aspect_min/aspect_max positivity/ordering check
            # here (GUI rework Phase 6) — aspect_min=0/aspect_max=inf is
            # now a VALID "no aspect condition" state (see
            # _upscale_params_from_side_and_filter), and lo <= hi is
            # already guaranteed by FilterEditor's own row validation
            # (_FilterConditionRow.to_condition raises before a row with
            # FROM > TO can ever reach get_conditions()) — the old
            # ordering check is unreachable dead code once that upstream
            # guarantee holds, so it is intentionally not reproduced here.
        if panel.force_aspect_var.get():
            try:
                force_w, force_h = panel.force_aspect_ratio()
            except ValueError:
                messagebox.showerror(
                    "PromptPainter",
                    f"{SITES[key].name}: Force Aspect Ratio W/H must be"
                    " whole numbers.",
                )
                return
            if force_w <= 0 or force_h <= 0:
                messagebox.showerror(
                    "PromptPainter",
                    f"{SITES[key].name}: Force Aspect Ratio W/H must"
                    " both be positive.",
                )
                return
        timing = replace(
            TIMING,
            pause_min_s=pause_min,
            pause_max_s=pause_max,
            action_delay_min_s=act_min,
            action_delay_max_s=act_max,
        )

        from painter.chrome import cdp_alive

        if not cdp_alive():
            messagebox.showerror(
                "PromptPainter",
                "No debuggable Chrome is running — press"
                " 'Open Chrome (login)' first.",
            )
            return

        # this site's per-step backup store (GUI rework Phase 8) — a
        # restart while a previous run's panel is still on screen must
        # not inherit its old backups; mirrors _launch_tool_worker's own
        # "clear the old slot first" rule for the four standalone tools.
        # Created here (BEFORE _compose_post_save reads it) so the
        # composed post_save closure captures the temp for this run.
        old_temp = self._job_temps.pop(key, None)
        if old_temp is not None:
            old_temp.clear()
        self._job_temps[key] = jobtemp.JobTemp(key, out_base)

        post_save = self._compose_post_save(key)
        if isinstance(post_save, str):  # a deps problem, not a hook
            messagebox.showerror(
                "PromptPainter",
                f"{post_save}\n\n(or turn the {SITES[key].name}"
                " BG removal / Crop / Upscale switches off)",
            )
            return

        # this site's ticked selection, read in the tk thread: per
        # sheet -> the drop paths to run. None means "the owner never
        # opened Select for this theme+site" (so the runner applies the
        # default advice rule). Once Select has been opened, the ticks
        # are authoritative — including ticked advice items — so we pass
        # the explicit set, never collapsing "all ticked" back to None.
        # An AI re-send bypasses the ticks entirely: its explicit
        # per-sheet sets ARE the selection (the regenerate path).
        selection: dict[str, set[str] | None]
        if override_selection is not None:
            selection = dict(override_selection)
        else:
            selection = {}
            for sheet in sheets:
                src = str(sheet.source)
                touched = any(
                    site == key and source == src
                    for (site, source, _drop) in self._select_vars
                )
                if touched:
                    selection[src] = {
                        drop
                        for (site, source, drop), var
                        in self._select_vars.items()
                        if site == key and source == src and var.get()
                    }
                else:
                    selection[src] = None

        self._stop_events[key].clear()
        if key in self._paused:
            self._toggle_pause_job(key)  # a fresh Start never starts pre-paused
        self._running.add(key)
        panel.set_run_state(running=True)
        total, themes = self._plan(key, sheets, selection)
        # the per-step restore viewer (GUI rework Phase 9) needs BOTH
        # this run's JobTemp and its output root to resolve a row's
        # drop path into a rel/live-file — mirrors _launch_tool_worker's
        # own "panel.folder = ...; panel.jobtemp = ...; panel.reset(...)"
        # grouping for the four standalone tools.
        dash = self.panels[key]
        dash.jobtemp = self._job_temps[key]
        dash.out_base = out_base
        dash.reset(active=True, task_total=total, task_themes=themes)
        self._dashgrid.add(key)  # reveal the panel (idempotent on restart)
        self._update_status()
        background = panel.background_var.get()
        style = panel.style_var.get()
        self._log(
            f"=== START {key} | {len(sheets)} sheet(s) -> {out_base}"
            f" | background: {background} | style: {style}"
            f" | bg_removal={panel.bg_removal_var.get()}"
            f" crop={panel.crop_var.get()}"
            f" upscale={panel.upscale_var.get()}"
            f" | safer_retry={panel.safer_var.get()}"
            f" continue_nudge={panel.continue_nudge_var.get()} ==="
        )
        # GUI rework Phase 19: _drive_site now takes its driver as a
        # parameter (widened to accept an ApiImageAdapter too, see
        # _start_api_image) instead of building a SiteDriver internally
        # off SITES[key] — this is the ONE place chatgpt/gemini still
        # construct the real CDP driver, unchanged from before.
        from painter.driver import SiteDriver

        driver = SiteDriver(SITES[key], timing, CDP_URL)
        worker = threading.Thread(
            target=self._drive_site,
            args=(
                key,
                list(sheets),
                out_base,
                timing,
                driver,
                post_save,
                partial(prompt_suffix, key, background, style=style),
                extra_suffix,
                panel.report_var.get(),
                selection,
                panel.safer_var.get(),
                panel.continue_nudge_var.get(),
                panel.new_chat_var.get(),
                self._stop_events[key],
                self._pause_events[key],
            ),
            daemon=True,
        )
        self._workers[key] = worker
        worker.start()
        # GUI rework Phase 11: Start hides the launching tool's own
        # settings panel (spec item 4) — website_gen's is the whole
        # _controls_box, shared by both sites, so ANY site starting
        # hides it; the owner reopens it (IconBar's website_gen tile)
        # to configure/start the other one while this one runs.
        self._inline_kind = None
        self._sync_running_state()

    def _start_api_image(self) -> None:
        """Start on the API Image GEN panel (GUI rework Phase 19) — the
        SAME queued .md sheets Website GEN drives, generated through
        the paid Gemini image API instead of a browser tab. Reuses the
        proven SITE machinery almost verbatim: ``_drive_site`` (widened
        to accept an ``ApiImageAdapter`` in place of a ``SiteDriver``),
        ``_stop_events``/``_pause_events``/``_running``/``_workers``
        (the SAME dicts chatgpt/gemini use, keyed "api_image" — see
        ``__init__``'s own comment on ``_stop_events`` and
        ``_dispatch``'s ``__worker_done__`` guard for why nothing there
        needed forking), ``_compose_post_save`` (called with THIS
        panel, since it is not one of ``self.agents``). Only its OWN
        validation lives here — no per-site "New chat" or action-delay
        concept (the API has no DOM to hesitate on, no chat to open),
        and a gating check ``_start_site`` has no equivalent of."""
        if "api_image" in self._running:
            return
        if not self._sheets:
            messagebox.showerror("PromptPainter", "Add sheet .md files first.")
            return
        sheets = self._parse_all()
        if not sheets:
            messagebox.showerror(
                "PromptPainter", "No usable sheets in the queue."
            )
            return
        out_base = self._out_base()
        for sheet in sheets:
            if sheet.source.resolve().is_relative_to(out_base):
                messagebox.showerror(
                    "PromptPainter",
                    f"{sheet.source.name} lives inside the output folder"
                    " — sources are READ ONLY; pick another output.",
                )
                return
        stems = [s.source.stem for s in sheets]
        dupes = sorted({s for s in stems if stems.count(s) > 1})
        if dupes:
            messagebox.showerror(
                "PromptPainter",
                "Two queued collections share a filename: "
                + ", ".join(dupes)
                + ".\nTheir progress/report files would collide — rename"
                " one before running.",
            )
            return

        panel = self._tool_panels["api_image_gen"]
        if panel.access_gated:
            messagebox.showerror("PromptPainter", AI_IMAGE_GATE_MESSAGE)
            return
        if not self._ensure_ai_key():
            return
        try:
            pause_min, pause_max = panel.pace_floats()
        except ValueError:
            messagebox.showerror(
                "PromptPainter", "API Image GEN: pause must be numbers."
            )
            return
        if pause_min > pause_max:
            messagebox.showerror(
                "PromptPainter", "API Image GEN: FROM must be <= TO (pause)."
            )
            return
        if panel.upscale_var.get():
            try:
                up = panel.upscale_params()
            except ValueError:
                messagebox.showerror(
                    "PromptPainter",
                    "API Image GEN: Upscale-gate min side must be a"
                    " number, and every filter row must be a valid"
                    " number (FROM <= TO).",
                )
                return
            if up["min_width"] <= 0:
                messagebox.showerror(
                    "PromptPainter",
                    "API Image GEN: Upscale-gate min side must be"
                    " positive.",
                )
                return
        if panel.force_aspect_var.get():
            try:
                force_w, force_h = panel.force_aspect_ratio()
            except ValueError:
                messagebox.showerror(
                    "PromptPainter",
                    "API Image GEN: Force Aspect Ratio W/H must be whole"
                    " numbers.",
                )
                return
            if force_w <= 0 or force_h <= 0:
                messagebox.showerror(
                    "PromptPainter",
                    "API Image GEN: Force Aspect Ratio W/H must both be"
                    " positive.",
                )
                return

        timing = replace(TIMING, pause_min_s=pause_min, pause_max_s=pause_max)

        # this job's per-step backup store (mirrors _start_site's own
        # "clear the old slot first" rule)
        old_temp = self._job_temps.pop("api_image", None)
        if old_temp is not None:
            old_temp.clear()
        self._job_temps["api_image"] = jobtemp.JobTemp("api_image", out_base)

        post_save = self._compose_post_save("api_image", panel=panel)
        if isinstance(post_save, str):  # a deps problem, not a hook
            messagebox.showerror(
                "PromptPainter",
                f"{post_save}\n\n(or turn the API Image GEN BG removal /"
                " Crop / Upscale switches off)",
            )
            return

        # no Select-images ticking for this job (SelectWindow is still
        # per-SITE only — see gui.md) — every sheet resumes by FILE
        # EXISTENCE, sheet-advised items sit out, exactly like a site
        # whose Select window the owner never opened.
        selection: dict[str, set[str] | None] = {
            str(sheet.source): None for sheet in sheets
        }

        self._stop_events["api_image"].clear()
        if "api_image" in self._paused:
            self._toggle_pause_job("api_image")  # never start pre-paused
        self._running.add("api_image")
        panel.set_run_state(running=True)
        total, themes = self._plan("api_image", sheets, selection)
        dash = self.panels["api_image"]
        dash.jobtemp = self._job_temps["api_image"]
        dash.out_base = out_base
        dash.reset(active=True, task_total=total, task_themes=themes)
        self._dashgrid.add("api_image")
        self._update_status()
        background = panel.background_var.get()
        style = panel.style_var.get()
        self._log(
            f"=== START api_image | {len(sheets)} sheet(s) -> {out_base}"
            f" | background: {background} | style: {style}"
            f" | bg_removal={panel.bg_removal_var.get()}"
            f" crop={panel.crop_var.get()}"
            f" force_aspect={panel.force_aspect_var.get()}"
            f" upscale={panel.upscale_var.get()} ==="
        )
        driver = ApiImageAdapter(
            log=lambda msg: self._q.put(f"[api_image]     {msg}")
        )
        worker = threading.Thread(
            target=self._drive_site,
            args=(
                "api_image",
                list(sheets),
                out_base,
                timing,
                driver,
                post_save,
                partial(prompt_suffix, "api_image", background, style=style),
                None,  # extra_suffix — no AI-checker re-send wiring yet
                panel.report_var.get(),
                selection,
                False,  # safer_retry — no ItemRefused path from this driver
                False,  # continue_nudge — no NoImage path from this driver
                "off",  # new_chat — no chat to open; NEW_CHAT_CHOICES value
                self._stop_events["api_image"],
                self._pause_events["api_image"],
            ),
            daemon=True,
        )
        self._workers["api_image"] = worker
        worker.start()
        self._inline_kind = None
        self._sync_running_state()

    def _drive_site(
        self, key, sheets, out_base, timing, driver, post_save, suffix,
        extra_suffix, report, selection, safer, continue_nudge, new_chat,
        stop_event, pause_event,
    ) -> None:
        """One job's whole run — the theme queue in order, one thread.

        GUI rework Phase 19: GENERALIZED, not forked — ``driver`` is
        supplied ALREADY CONSTRUCTED by the caller (``_start_site``'s
        own ``SiteDriver(SITES[key], timing, CDP_URL)`` for chatgpt/
        gemini, ``_start_api_image``'s ``ApiImageAdapter`` for
        "api_image") instead of this method building a ``SiteDriver``
        internally off ``SITES[key]`` — "api_image" is not a browser
        site and has no ``SiteConfig``. This method never branches on
        WHICH kind of driver it got: it only ever calls ``attach()``/
        ``close()`` and hands the object to ``run_sheet`` unchanged,
        exactly as before — only the accepted type widened."""
        log = lambda msg: self._q.put(f"[{key}] {msg}")
        events = lambda ev: self._q.put(("__event__", key, ev))
        done_sheets = 0
        # the WHOLE body is guarded so __worker_done__ is ALWAYS posted
        # (even if the imports fail) — otherwise the job's Start button
        # would stay disabled forever
        try:
            from painter.driver import DriverError, TerminalState
            from painter.runner import run_sheet

            t_site = time.monotonic()
            title = driver.attach()
            log(f"attached to {title!r} — SUPERVISED, watch the window")
            for n, sheet in enumerate(sheets, start=1):
                if stop_event.is_set():
                    log("stopped on request — remaining collections not run")
                    break
                log(
                    f"--- collection {n}/{len(sheets)}:"
                    f" {sheet.source.name} ---"
                )
                try:
                    generated = run_sheet(
                        sheet, driver, out_base, key, timing,
                        log=log,
                        should_stop=stop_event.is_set,
                        should_pause=pause_event.is_set,
                        post_save=post_save,
                        prompt_suffix=suffix,
                        extra_suffix=extra_suffix,
                        report=report,
                        only=selection.get(str(sheet.source)),
                        on_event=events,
                        safer_retry=safer,
                        continue_nudge=continue_nudge,
                        new_chat_per_folder=(new_chat == "folder"),
                    )
                    done_sheets += 1
                    log(f"collection done: {generated} image(s) into {out_base}")
                    if (
                        new_chat in ("collection", "folder")
                        and generated
                        and n < len(sheets)
                    ):
                        try:
                            driver.new_chat(log)
                        except Exception as exc:
                            log(
                                "NEW CHAT FAILED (continuing in the old"
                                f" one): {exc}"
                            )
                except TerminalState as exc:
                    log(f"TERMINAL STATE (quota/rate limit): {exc}")
                    retry = getattr(exc, "retry_after_s", None)
                    if retry is not None:
                        self._q.put(("__terminal__", key, retry))
                        log(
                            "quota window known — this site auto-restarts"
                            " when it elapses (Stop cancels)"
                        )
                    else:
                        log(
                            "site stopped — finished work is saved; start"
                            " again later to resume the remaining"
                            " collections"
                        )
                    break
                except DriverError as exc:
                    log(f"DRIVER ERROR: {exc}")
                    log(
                        "site stopped — progress saved; fix the cause"
                        " and start again to resume"
                    )
                    break
            log(
                f"finished {done_sheets}/{len(sheets)} collection(s) in"
                f" {(time.monotonic() - t_site) / 60:.1f} min"
            )
        except Exception as exc:  # surfaced, never swallowed
            # attach()/construction failures land here (DriverError);
            # so would a missing-playwright ImportError
            kind = type(exc).__name__
            if kind in (
                "DriverError", "TerminalState", "SelectorRot",
                "GenerationTimeout",
            ):
                log(f"DRIVER ERROR: {exc}")
            else:
                log(f"UNEXPECTED ERROR: {kind}: {exc}")
        finally:
            driver.close()
            self._q.put(("__worker_done__", key))

    def _stop_site(self, key: str) -> None:
        """Stop ONE site: a running worker finishes its current item;
        a PENDING quota auto-restart is cancelled."""
        if key in self._restart_jobs:
            self._cancel_restart(key)
            self.agents[key].set_run_state(running=key in self._running)
            self._log(f"[{key}] pending auto-restart cancelled")
            # the site is done now — reveal the panel's CLOSE button
            self.panels[key].finish()
            self._dashgrid.relayout()
            return
        if key in self._running:
            self._stop_events[key].set()
            # Stop must win over a pending pause (MUST NOT REGRESS): the
            # should_stop re-check inside wait_while_paused already lets
            # a PAUSED run stop promptly, but the toggle itself would
            # otherwise linger and silently pre-pause the next Start.
            if key in self._paused:
                self._toggle_pause_job(key)
            self.status_var.set(
                f"{key}: stopping after the current item …"
            )

    def _stop_tool(self, slot: str) -> None:
        """Stop ONE standalone tool job (GUI rework Phase 14, closing
        Phase 13's own flagged gap) — mirrors ``_stop_site``'s request
        half exactly (no quota auto-restart to cancel, tools have
        none): sets the should_stop event ``_run_tool_job`` polls
        BETWEEN images, wins over a pending Pause the same way. This
        method only REQUESTS the stop — it does NOT touch the
        dashboard panel or JobTemp itself; the worker may still be
        mid-image. The "smart" half (close the panel, clear its
        JobTemp, maybe leave "running") runs once the worker actually
        confirms the halt, in ``_dispatch``'s ``__tool_done__`` branch,
        which checks this SAME event to tell a Stop-triggered finish
        apart from a natural one."""
        if slot not in self._tool_workers:
            return
        self._stop_events[slot].set()
        if slot in self._paused:
            self._toggle_pause_job(slot)
        self.status_var.set(
            f"{JOB_LABEL[slot]}: stopping after the current item …"
        )

    def _update_status(self) -> None:
        if self._running:
            self.status_var.set("running: " + ", ".join(sorted(self._running)))
        else:
            self.status_var.set("idle")

    # --- quota auto-restart --------------------------------------------

    def _handle_terminal(self, key: str, retry_after_s: float) -> None:
        """A quota stop with a KNOWN reset time: schedule the site's
        auto-restart at reset + a polite random 30–120 s, with a live
        countdown on its dashboard panel. Runs whenever the app is
        open; manual Stop cancels, manual Start just starts earlier."""
        delay = retry_after_s + random.uniform(30.0, 120.0)
        self._restart_deadline[key] = time.monotonic() + delay
        self._restart_jobs[key] = self.root.after(
            int(delay * 1000), partial(self._auto_restart, key)
        )
        self._tick_restart(key)
        self._log(
            f"[{key}] auto-restart scheduled in {delay / 60:.1f} min"
        )

    def _tick_restart(self, key: str) -> None:
        if key not in self._restart_jobs:
            return  # cancelled — the countdown loop dies with it
        left = max(self._restart_deadline[key] - time.monotonic(), 0.0)
        self.panels[key].state_var.set(
            f"quota — auto-restart in {int(left // 60):02d}:"
            f"{int(left % 60):02d}"
        )
        self.root.after(1000, partial(self._tick_restart, key))

    def _cancel_restart(self, key: str) -> None:
        job = self._restart_jobs.pop(key, None)
        if job is not None:
            self.root.after_cancel(job)
        self._restart_deadline.pop(key, None)
        self.panels[key].state_var.set("")

    def _auto_restart(self, key: str) -> None:
        self._restart_jobs.pop(key, None)
        self.panels[key].state_var.set("")
        self._log(f"[{key}] quota window elapsed — auto-restarting")
        self._start_site(key)

    # --- queue pump ----------------------------------------------------

    def _drain_queue(self) -> None:
        try:
            while True:
                msg = self._q.get_nowait()
                if (
                    self._resize_active
                    and isinstance(msg, tuple)
                    and msg[0] == "__event__"
                ):
                    # mid drag-resize: a dashboard event re-renders tree
                    # rows / live labels per frame on top of the drag's
                    # own relayout work — buffer it, flushed in order by
                    # _resize_settled (owner 2026-07-20)
                    self._pending_events.append(msg)
                    continue
                self._dispatch(msg)
        except queue.Empty:
            pass
        self.root.after(120, self._drain_queue)

    def _dispatch(self, msg) -> None:
        """Apply ONE worker-queue message to the window (main thread)."""
        if isinstance(msg, tuple):
            if msg[0] == "__status__":
                self.status_var.set(msg[1])
            elif msg[0] == "__event__":
                # .get is the defensive guard for a late event
                # arriving after its panel was closed
                panel = self.panels.get(msg[1])
                if panel is not None:
                    panel.handle(msg[2])
                    # GUI rework Phase 16: the parallel Checker AI hangs
                    # off the SAME item_progress event the dashboard row
                    # was just built from — zero runner.py changes (see
                    # _maybe_spawn_checker's own docstring)
                    if msg[2].get("type") == "item_progress":
                        self._maybe_spawn_checker(msg[1], msg[2])
                    # GUI rework Phase 20: the Fixer AI hangs off the
                    # checker's OWN item_checked result (posted by
                    # _run_checker_one onto this SAME queue) — see
                    # _maybe_spawn_fixer's own docstring
                    elif msg[2].get("type") == "item_checked":
                        self._maybe_spawn_fixer(msg[1], msg[2])
            elif msg[0] == "__terminal__":
                self._handle_terminal(msg[1], msg[2])
            elif msg[0] == "__tool_done__":
                slot = msg[1]
                # GUI rework Phase 14: was THIS finish caused by
                # _stop_tool (still set — cleared only at the next
                # Start, see _launch_tool_worker) or a natural
                # completion? Read BEFORE popping _tool_workers below
                # (harmless either order — _stop_events is independent
                # — but keeps the "what happened" read next to the
                # message that reports it).
                stopped = self._stop_events[slot].is_set()
                self._tool_workers.pop(slot, None)
                # a job that finished its last image right as it was
                # paused would otherwise leave a stale "paused" toggle
                # on an idle panel (owner 2026-07-21)
                if slot in self._paused:
                    self._toggle_pause_job(slot)
                panel_key = self._tool_panel_key(slot)
                if panel_key is not None:
                    # GUI rework Phase 13/15: re-enable the panel's own
                    # Start button ("aicheck" resolves to its
                    # "image_checker" ToolSettingsPanel via
                    # _tool_panel_key since GUI rework Phase 15).
                    self._tool_panels[panel_key].set_run_state(running=False)
                if stopped:
                    # the "smart" half of _stop_tool: the worker has
                    # NOW actually halted (not merely requested to,
                    # back on the Stop click — it may have still been
                    # mid-image) — close the panel + clear its JobTemp
                    # (existing _close_panel, same as a manual Close)
                    # and leave "running" for the Main Menu if that was
                    # the LAST active job (_request_menu — Phase 11's
                    # own gate, unmodified: a no-op status hint, never
                    # an auto-jump, while another job is still active).
                    # A natural (unstopped) finish is UNCHANGED — reveal
                    # CLOSE and let the owner review before dismissing.
                    self._close_panel(slot)
                    self._request_menu()
                else:
                    self.panels[slot].finish()  # reveal CLOSE
                if not self._tool_workers and not self._running:
                    self._update_status()
                self._sync_running_state()  # GUI rework Phase 11
            elif msg[0] == "__worker_done__":
                key = msg[1]
                self._log(f"[{key}] worker finished")
                # the worker posts this from its finally block
                # while its thread is still technically alive
                self._running.discard(key)
                self._workers.pop(key, None)
                if key in self._paused:  # same stale-pause guard as above
                    self._toggle_pause_job(key)
                # GUI rework Phase 19: "api_image" also drives through
                # _drive_site (hence __worker_done__) but is NOT one of
                # self.agents (no SiteConfig, no AgentPanel — see
                # _start_api_image) — chatgpt/gemini take the EXACT
                # same branch as before; a key outside self.agents
                # resolves its OWN settings panel via _tool_panel_key,
                # the same bridge __tool_done__ below already uses, and
                # has no pending-restart concept (this job's
                # TerminalState always carries retry_after_s=None, so it
                # never enters self._restart_jobs to begin with).
                if key in self.agents:
                    self.agents[key].set_run_state(
                        running=False,
                        pending_restart=key in self._restart_jobs,
                    )
                else:
                    panel_key = self._tool_panel_key(key)
                    if panel_key is not None:
                        self._tool_panels[panel_key].set_run_state(
                            running=False
                        )
                # a pending quota auto-restart keeps the panel
                # alive (countdown, no CLOSE yet); otherwise the
                # site is done — reveal its CLOSE button
                if key not in self._restart_jobs:
                    self.panels[key].finish()
                self._update_status()
                self._sync_running_state()  # GUI rework Phase 11
        else:
            self._log(str(msg))

    # --- Checker AI — parallel per-item check (GUI rework Phase 16) ----

    def _maybe_spawn_checker(self, key: str, event: dict) -> None:
        """The owner's "dok generise sledecu sliku paralelno ona koja je
        generisana cek jer provjeri" (UV/prompt.txt item 1): fired from
        ``_dispatch`` for EVERY ``item_progress``, on the site whose
        image it just saved. A no-op unless ``key`` is a SITE (not a
        tool/aicheck slot) with its AgentPanel's ``checker_var`` ON —
        read LIVE at every call (not captured once at Start), so the
        owner can flip it mid-run and it takes effect from the next
        saved image.

        By the time ``item_progress`` fires, ``run_sheet`` has already
        written the FINAL post-processed bytes to disk (the post_save
        hook runs before it emits the event — see runner.py) — so this
        is the earliest possible moment to start the check, and it
        overlaps BOTH the remaining "our time" pause AND the next
        item's whole generation, which is the entire point (ZERO
        runner.py changes: this hangs off an event the dashboard
        already consumes, per the binding design doc's Findings).

        The "checking…" marker is applied SYNCHRONOUSLY here (already
        on the main thread, same as ``panel.handle`` right above this
        call in ``_dispatch``) so it appears instantly; the actual
        vision call runs on a daemon thread (``_run_checker_one``) that
        posts its OWN ``item_checked`` event back onto the SAME queue
        once it completes — never blocking this method or the run
        loop."""
        agent = self.agents.get(key)
        if agent is None or not agent.checker_var.get():
            return  # not a site, or this site's checker is off
        dash = self.panels.get(key)
        if dash is None or dash.out_base is None:
            return  # panel closed, or somehow not started yet
        drop_path = event["drop_path"]
        dash.handle({"type": "item_checking", "drop_path": drop_path})
        src = dash.out_base / dest_for(drop_path, key)
        threading.Thread(
            target=self._run_checker_one,
            args=(key, drop_path, src, dash.out_base),
            daemon=True,
        ).start()

    def _run_checker_one(
        self, key: str, drop_path: str, src: Path, out_base: Path,
    ) -> None:
        """ONE saved image's vision check, entirely on its own daemon
        thread — the background half of ``_maybe_spawn_checker``. Posts
        exactly one ``item_checked`` event back onto the shared GUI
        queue, routed to ``key``'s DashPanel exactly like every other
        site event (``_dispatch``'s ``__event__`` branch).

        ``ai.check_one_image`` already turns a per-image ``AiError``
        (including ``NoKey`` — a subclass, see painter/ai.py) into an
        'error' result dict instead of raising (the same loud-but-
        never-fatal contract the standalone AI-check batch job already
        relies on) — so in the common case this method never needs its
        own except clause for that. The outer ``except Exception`` below
        is the extra safety net for anything ELSE that could escape
        (e.g. the file vanishing under a race, a disk-full flag-file
        write) so a checker thread can NEVER die silently and NEVER
        touches — let alone kills — the generation run it is checking
        (Rule #1: loud, visible on the row, non-fatal)."""
        from painter import ai

        emit = lambda ev: self._q.put(("__event__", key, ev))
        log = lambda msg: self._q.put(f"[{key} checker] {msg}")
        try:
            result = ai.check_one_image(
                src, out_base, AI_CHECK_INSTRUCTIONS, log=log,
            )
            emit({
                "type": "item_checked", "drop_path": drop_path,
                "kind": result["kind"], "defects": result["defects"],
                "raw": result["raw"], "rel": result["rel"],
                "time": result["time"],
            })
        except Exception as exc:
            log(f"FAIL {src.name}: {exc}")
            emit({
                "type": "item_checked", "drop_path": drop_path,
                "kind": "error", "defects": [], "raw": str(exc),
                "rel": ai.flag_key(src, out_base), "time": 0.0,
            })

    # --- Fixer AI (GUI rework Phase 20) ---------------------------------
    # The owner's UV/prompt.txt item 1 ("... salje fikseru da ispravi i to
    # u situaciji ako su oba ukljucena") and item 2 ("Checker double click
    # -> ... buttone za IMAGE FIX i WEBSITE fix ... kreira PROMPT koji
    # salje uz sliku"). Two independent surfaces sharing ai.build_fix_
    # prompt/JobTemp step="fixer": the AUTO-DISPATCH half below
    # (_maybe_spawn_fixer/_run_fixer_api/_queue_website_fix, wired off
    # item_checked in _dispatch) and the MANUAL half
    # (_build_fix_workers/_run_image_fix/_run_website_fix, called by
    # DocWindow's IMAGE FIX/WEBSITE FIX buttons via DashPanel._show_check
    # / AiCheckPanel._on_activate). "Send flagged to generator"
    # (_resend_flagged) stays untouched as the THIRD, pre-existing option.

    def _maybe_spawn_fixer(self, key: str, event: dict) -> None:
        """The owner's UV/prompt.txt item 1, second half: once the
        parallel Checker AI (``_maybe_spawn_checker``/``_run_checker_one``)
        reports an ``item_checked``, dispatch this site's Fixer AI per
        ``_fixer_decision`` — ``fixer_var``/``fixer_mode_var`` are read
        LIVE (inside that pure function), exactly like
        ``_maybe_spawn_checker`` reads ``checker_var`` live, so a mid-run
        toggle takes effect from the NEXT checked image."""
        agent = self.agents.get(key)
        if agent is None:
            return
        decision = _fixer_decision(agent, event)
        if decision == "none":
            return
        dash = self.panels.get(key)
        if dash is None or dash.out_base is None:
            return  # panel closed, or somehow not started yet
        defects = event["defects"]
        raw = event.get("raw") or ""
        if decision == "api":
            threading.Thread(
                target=self._run_fixer_api,
                args=(
                    key, event["drop_path"], event["rel"], dash.out_base,
                    defects, raw,
                ),
                daemon=True,
            ).start()
        else:  # "website_queue"
            self._queue_website_fix(key, event["rel"], defects, raw)

    def _run_fixer_api(
        self, key: str, drop_path: str, rel: str, out_base: Path,
        defects: list[str], raw: str,
    ) -> None:
        """The auto-fixer's API-mode background half (Phase 20) — a
        plain ``ai.edit_image`` REST call, so it genuinely overlaps the
        site's OWN next-image generation on the SAME browser tab (the
        intended parallel flow — the binding design doc's "only the API
        fix can truly run in parallel while generating"). Backs the
        pre-fix file up via THIS site's live JobTemp under
        ``step="fixer"`` before overwriting (best-effort — see
        ``_backup_before_fix``), so it is restorable in the Phase 9
        StepRestore viewer exactly like every pipeline stage. A gated or
        failed call is LOUD (the log line) and NEVER FATAL — it never
        touches the run this image came from (Rule #1, the SAME
        convention ``_run_checker_one`` already established for the
        checker side)."""
        from painter import ai

        log = lambda msg: self._q.put(f"[{key} fixer] {msg}")
        emit = lambda ev: self._q.put(("__event__", key, ev))
        live = out_base / dest_for(drop_path, key)
        prompt = ai.build_fix_prompt(defects, raw)
        try:
            fixed = ai.edit_image(live, prompt, log=log)
        except ai.PaidFeatureRequired as exc:
            log(f"FIXER GATED (no billing for the image model): {exc}")
            return
        except ai.AiError as exc:
            log(f"FIXER FAILED: {live.name}: {exc}")
            return
        self._backup_before_fix(key, rel, live)
        live.write_bytes(fixed)
        log(f"FIXED (API): {live.name}")
        emit({"type": "item_fixed", "drop_path": drop_path, "mode": "api"})

    def _queue_website_fix(
        self, key: str, rel: str, defects: list[str], raw: str,
    ) -> None:
        """WEBSITE-mode auto-fixer choice (owner design, Phase 20) —
        **documented here in full, since the design explicitly asks for
        an unambiguous choice**: the browser tab is BUSY generating this
        site's OWN next image the instant ``item_checked`` fires (the
        checker's background thread reports well before the run
        finishes) — driving ``driver.submit_fix`` here would collide
        with that in-flight ``submit_prompt``/``await_done`` (one tab,
        one operation). So this method NEVER touches the browser.

        Instead it folds the flagged item into ``AiCheckPanel``'s OWN
        ``_flagged``/``_raw`` bucket via its EXISTING
        ``handle({"type": "item_flagged", ...})`` — the IDENTICAL
        append-only state the standalone batch checker already fills —
        and reveals that panel on the dashboard grid (``DashGrid.add``
        is idempotent) so the queued item is IMMEDIATELY VISIBLE as a
        real row, never a silent internal list (root Rule #1: "never
        silently no-op"). The owner's EXISTING **Send flagged to
        generator** button (``AiCheckPanel._do_resend`` ->
        ``PainterGui._resend_flagged``) is the ONE send path — reused
        VERBATIM, never duplicated — whenever they choose to click it;
        typically once this site is idle again, since
        ``_resend_flagged``'s own ``_start_site`` call already refuses a
        site that is still ``self._running``, so there is no way for a
        click to collide with the still-running generation even if it
        happens immediately."""
        aicheck = self.panels["aicheck"]
        aicheck.handle({
            "type": "item_flagged", "rel": rel, "defects": list(defects),
            "raw": raw, "time": 0.0,
        })
        self._dashgrid.add("aicheck")
        self._log(
            f"[{key}] fixer (website mode): queued"
            f" {PurePosixPath(rel).name} for 'Send flagged to generator'"
            f" — {len(defects)} defect(s)"
        )

    def _backup_before_fix(
        self, jobtemp_slot: str | None, rel: str, live: Path,
    ) -> None:
        """Best-effort pre-fix backup (``step="fixer"``) into the live
        ``JobTemp`` for ``jobtemp_slot`` — the SAME instance
        ``DashPanel.jobtemp``/the site's own pipeline already write into,
        NEVER a freshly constructed one (``JobTemp.__init__`` wipes its
        slot's directory on construction — reusing the live instance is
        the ONLY safe choice here). When that slot has no live JobTemp
        (the site's dashboard panel was already Closed this session, or
        this image came from outside any queued generation), the backup
        is skipped LOUDLY (root Rule #1) rather than silently — the fix
        still applies either way, it simply will not offer a 'Fixer AI'
        stage in the Steps… restore viewer."""
        temp = self._job_temps.get(jobtemp_slot) if jobtemp_slot else None
        if temp is not None:
            temp.backup(live, rel, step="fixer")
        else:
            self._q.put(
                f"[fixer] no active JobTemp for {jobtemp_slot!r} — the"
                f" pre-fix state of {live.name} was not backed up (the"
                " Steps… restore viewer will not offer a Fixer AI stage"
                " for it)"
            )

    def _run_image_fix(
        self, rel: str, out_base: Path, jobtemp_slot: str | None,
        defects: list[str], raw: str,
    ) -> tuple[str, str]:
        """The manual IMAGE FIX button's background-thread body (Rule
        #5: shared by ``DashPanel``'s 'Check…' viewer and
        ``AiCheckPanel``'s own double-click viewer, via
        ``_build_fix_workers``) — a plain ``ai.edit_image`` REST call,
        so it needs no site/browser concept at all: ANY checked image,
        regardless of provenance, can be IMAGE-FIXED. Returns a
        ``(kind, message)`` pair ``DocWindow._apply_fix_result`` reads:
        ``"ok"`` (the image was overwritten), ``"gated"``
        (``PaidFeatureRequired`` — permanent, no billing on the image
        model), or ``"error"`` (any other ``AiError`` — transient,
        retry-able). Runs on a background thread (spawned by
        ``DocWindow._run_fix``), so it logs through ``self._q``, never
        ``self._log`` directly (Rule #1's thread-safety convention every
        other background worker in this file already follows)."""
        from painter import ai

        live = ai.flag_file(rel, out_base)
        prompt = ai.build_fix_prompt(defects, raw)
        log = lambda msg: self._q.put(f"[fixer] {msg}")
        try:
            fixed = ai.edit_image(live, prompt, log=log)
        except ai.PaidFeatureRequired as exc:
            self._q.put(f"[fixer] IMAGE FIX gated: {exc}")
            return ("gated", str(exc))
        except ai.AiError as exc:
            self._q.put(f"[fixer] IMAGE FIX failed on {live.name}: {exc}")
            return ("error", str(exc))
        self._backup_before_fix(jobtemp_slot, rel, live)
        live.write_bytes(fixed)
        self._q.put(f"[fixer] IMAGE FIX applied: {live}")
        return ("ok", "the image was overwritten via the API.")

    def _run_website_fix(
        self, rel: str, out_base: Path, jobtemp_slot: str | None,
        site_key: str, defects: list[str], raw: str,
    ) -> tuple[str, str]:
        """The manual WEBSITE FIX button's background-thread body —
        drives a FRESH ``SiteDriver`` (attach -> submit_fix -> await_done
        -> extract_image -> close), an OWNER-TRIGGERED one-off
        automation — never the running site's own worker thread. This is
        why it stays safe despite the one-tab constraint: it is only
        ever reached by an explicit click, and refuses outright (a
        transient, retry-able ``"error"``, not a permanent ``"gated"``)
        while THIS site is ``self._running`` — the tab is genuinely busy
        generating the next image then, exactly the collision
        ``_queue_website_fix`` avoids on the auto-dispatch side."""
        if site_key in self._running:
            return (
                "error",
                f"{SITES[site_key].name} is currently generating — stop"
                " it or wait until it finishes, then retry.",
            )
        from painter import ai
        from painter.driver import DriverError, FixNotConfigured, SiteDriver

        live = ai.flag_file(rel, out_base)
        prompt = ai.build_fix_prompt(defects, raw)
        log = lambda msg: self._q.put(f"[fixer] {msg}")
        driver = SiteDriver(SITES[site_key], TIMING, CDP_URL)
        try:
            driver.attach()
            driver.submit_fix(str(live), prompt)
            driver.await_done(log=log)
            fixed = driver.extract_image()
        except FixNotConfigured as exc:
            self._q.put(f"[fixer] WEBSITE FIX gated: {exc}")
            return ("gated", str(exc))
        except DriverError as exc:
            self._q.put(f"[fixer] WEBSITE FIX failed: {exc}")
            return ("error", str(exc))
        finally:
            driver.close()
        self._backup_before_fix(jobtemp_slot, rel, live)
        live.write_bytes(fixed)
        self._q.put(f"[fixer] WEBSITE FIX applied: {live}")
        return ("ok", "the image was overwritten via the website.")

    def _build_fix_workers(
        self, rel: str, out_base: Path, defects: list[str], raw: str,
        jobtemp_slot: str | None = None,
    ) -> tuple[
        Callable[[], tuple[str, str]], Callable[[], tuple[str, str]] | None,
    ]:
        """The checker report viewer's manual fix buttons (owner's #2,
        UV/prompt.txt item 2) — Rule #5, the ONE builder both
        ``DashPanel._show_check`` and ``AiCheckPanel._on_activate`` call,
        so the two report-viewer launch surfaces can never diverge.

        ``jobtemp_slot`` is the caller's OWN job kind when it already
        knows it (``DashPanel`` passes its own ``self.slot_key``);
        ``AiCheckPanel`` — the standalone checker, with no site of its
        own — passes ``None``, and this resolves BOTH the site (for
        WEBSITE FIX) and the JobTemp slot (for the pre-fix backup) the
        SAME way ``ai.plan_resend``'s own re-send already does:
        ``ai.drop_and_site_for(rel)``, the ``dest_for`` reverse.

        Returns ``(image_fix_worker, website_fix_worker)`` — zero-arg
        callables ``DocWindow`` runs on a background thread;
        ``website_fix_worker`` is ``None`` when no ``SITES`` entry can
        be resolved for this image (an API Image GEN output, which has
        no browser tab at all, or a standalone-checked image from
        outside any queued generation) — WEBSITE FIX makes no sense
        without a site to drive; IMAGE FIX is always offered (it needs
        no site concept)."""
        from painter import ai

        if jobtemp_slot is None:
            mapped = ai.drop_and_site_for(rel)
            jobtemp_slot = mapped[1] if mapped is not None else None
        site_key = jobtemp_slot if jobtemp_slot in SITES else None

        image_worker = partial(
            self._run_image_fix, rel, out_base, jobtemp_slot, defects, raw,
        )
        website_worker = None
        if site_key is not None:
            website_worker = partial(
                self._run_website_fix, rel, out_base, jobtemp_slot,
                site_key, defects, raw,
            )
        return image_worker, website_worker

    # --- settings persistence ------------------------------------------

    def _collect_settings(self) -> dict:
        return {
            "output": self.out_var.get(),
            "font_base": widgets.FONT_BASE,
            "theme": widgets.ACTIVE_THEME,
            "geometry": self.root.geometry(),
            "controls_collapsed": self._collapsed,
            # the AI features' credential (owner 2026-07-20): held on
            # the GUI so the whole-dict save round-trips it; painter.ai
            # reads it back from settings.json per call
            GEMINI_KEY_SETTING: self._gemini_key,
            FILTER_PRESETS_SETTING: {
                name: list(rows) for name, rows in self._filter_presets.items()
            },
            "agents": {
                key: panel.get_settings()
                for key, panel in self.agents.items()
            },
            # GUI rework Phase 13/14: each standalone tool's PERSISTENT
            # settings panel (all four now) — its filter stack + Advanced
            # (or always-visible, for upscale/aspect) overrides, same
            # round-trip shape as "agents" above. The picked folder/files
            # are NEVER persisted (every tool has always asked fresh).
            # SUPERSEDES the old top-level 'upscale_tool'/'aspect_ratio'/
            # 'aspect_filter_conditions' keys the standalone Upscale/
            # Aspect MODAL dialogs used to own (both retired this phase)
            # — those old keys are simply no longer emitted here (see
            # _apply_settings's one-time migration INTO this dict below,
            # same "additive, read-old-once, log loudly" contract as
            # every other settings migration in this file).
            "tool_panels": {
                slot: panel.get_settings()
                for slot, panel in self._tool_panels.items()
            },
        }

    def _migrate_upscale_panel_settings(
        self, panel_stored: dict, stored: dict
    ) -> dict:
        """One-time migration (GUI rework Phase 14, same additive/
        read-old-once/log-loudly contract as every other settings
        migration in this file) of the retired standalone Upscale
        dialog's remembered gate — settings.json's old top-level
        ``upscale_tool`` key, EITHER the Phase 6+ ``{"min_side",
        "conditions"}`` shape or the pre-Phase-6 ``{"min_width",
        "min_height", "aspect_min", "aspect_max"}`` one — into
        ``UpscaleSettingsPanel``'s OWN settings shape (``up_minside``/
        ``conditions``, exactly what its ``get_settings``/
        ``apply_settings`` already read/write). A no-op once the panel
        has saved itself at least once under the NEW ``tool_panels``
        key (its own ``up_minside`` already present) — the old
        top-level key is never written back (``_collect_settings`` no
        longer emits it), so it naturally drops off disk over time,
        same as any other stale key."""
        if "up_minside" in panel_stored:
            return panel_stored
        saved_up = stored.get("upscale_tool")
        if isinstance(saved_up, dict) and "min_side" in saved_up:
            panel_stored = dict(panel_stored)
            panel_stored.setdefault("up_minside", str(saved_up["min_side"]))
            raw_conditions = saved_up.get("conditions")
            if isinstance(raw_conditions, list):
                panel_stored.setdefault("conditions", raw_conditions)
            self._log(
                "MIGRATION: standalone Upscale tool's remembered gate"
                " (top-level 'upscale_tool') -> the Upscale panel's own"
                " settings (one-time; the old key stays on disk unread"
                " from now on)"
            )
        elif isinstance(saved_up, dict) and "min_width" in saved_up:
            try:
                migrated = _migrate_legacy_upscale_gate(
                    saved_up.get("min_width", UPSCALE_MIN_SIDE_DEFAULT),
                    saved_up.get("aspect_min", UPSCALE_ASPECT_MIN),
                    saved_up.get("aspect_max", UPSCALE_ASPECT_MAX),
                )
            except (TypeError, ValueError) as exc:
                self._log(
                    f"MIGRATION: legacy 'upscale_tool' dict is unreadable"
                    f" ({exc}) — the Upscale panel keeps its shipped"
                    " default gate"
                )
            else:
                self._log(
                    "MIGRATION: legacy standalone 'upscale_tool'"
                    " (min_width/min_height/aspect_min/aspect_max) -> the"
                    f" Upscale panel's own min_side={migrated['min_side']}"
                    " + 1 filter condition (one-time; the old key stays"
                    " on disk unread from now on)"
                )
                panel_stored = dict(panel_stored)
                panel_stored.setdefault(
                    "up_minside", str(migrated["min_side"])
                )
                panel_stored.setdefault("conditions", migrated["conditions"])
        return panel_stored

    def _migrate_aspect_panel_settings(
        self, panel_stored: dict, stored: dict
    ) -> dict:
        """One-time migration (GUI rework Phase 14) of the retired
        standalone Aspect dialog's remembered ratio/filter —
        settings.json's old top-level ``aspect_ratio`` ([w, h]) and
        ``aspect_filter_conditions`` (or the even older scalar
        ``aspect_filter``, GUI rework Phase 4's own migration source)
        keys — into ``AspectSettingsPanel``'s OWN settings shape
        (``ratio``/``conditions``). A no-op once the panel has saved
        itself at least once under the NEW ``tool_panels`` key (same
        contract as ``_migrate_upscale_panel_settings`` above)."""
        if "ratio" in panel_stored:
            return panel_stored
        panel_stored = dict(panel_stored)
        saved_ratio = stored.get("aspect_ratio")
        if isinstance(saved_ratio, (list, tuple)) and len(saved_ratio) == 2:
            panel_stored["ratio"] = [str(saved_ratio[0]), str(saved_ratio[1])]
            self._log(
                "MIGRATION: standalone Aspect tool's remembered ratio"
                " (top-level 'aspect_ratio') -> the Aspect panel's own"
                " settings (one-time; the old key stays on disk unread"
                " from now on)"
            )

        if "conditions" not in panel_stored:
            saved_conditions = stored.get("aspect_filter_conditions")
            if isinstance(saved_conditions, list):
                panel_stored["conditions"] = saved_conditions
                self._log(
                    "MIGRATION: standalone Aspect tool's remembered"
                    " filter (top-level 'aspect_filter_conditions') ->"
                    " the Aspect panel's own settings (one-time; the old"
                    " key stays on disk unread from now on)"
                )
            else:
                legacy = stored.get("aspect_filter")
                if isinstance(legacy, dict):
                    try:
                        migrated = _migrate_legacy_aspect_filter(legacy)
                    except (TypeError, ValueError) as exc:
                        self._log(
                            f"MIGRATION: legacy aspect_filter {legacy!r} is"
                            f" unreadable ({exc}) — the Aspect panel"
                            " starts with no filter"
                        )
                    else:
                        self._log(
                            "MIGRATION: legacy 'aspect_filter' setting"
                            f" {legacy!r} -> {len(migrated)} condition(s)"
                            " on the Aspect panel (one-time; the old key"
                            " stays on disk unread from now on)"
                        )
                        panel_stored["conditions"] = migrated
        return panel_stored

    def _apply_settings(self, stored: dict) -> None:
        """Missing keys keep the current defaults. The queue is
        intentionally NOT restored — the app starts with an empty
        collection list every launch (owner 2026-07-18); only the
        output folder, per-agent settings, theme, geometry, zoom and
        the collapsed state persist (a stale ``sash`` key from an older
        settings.json is simply ignored)."""
        self._gemini_key = str(stored.get(GEMINI_KEY_SETTING, "") or "")
        saved_out = stored.get("output")
        if saved_out and Path(saved_out).is_dir():
            self.out_var.set(saved_out)
        elif saved_out:
            # never leave the field on a folder that does not exist:
            # done-detection reads <output>/_state and would otherwise
            # find nothing, offering every already-finished image again
            self._log(
                "saved output folder is gone — falling back to the"
                f" default: {DEFAULT_OUT_DIR}"
            )
        for key, panel in self.agents.items():
            agent_stored = dict(stored.get("agents", {}).get(key, {}))
            # per-agent upscale gate (GUI rework Phase 6): the NEW
            # 'up_minside' key wins when present; otherwise a ONE-TIME
            # LOUD migration reads the OLD four scalar fields
            # (up_minw/up_minh/up_aspmin/up_aspmax) exactly once — never
            # written back (up_minh is DROPPED: the two axes collapse
            # into one min-side spinner, and up_minw is used for it —
            # every shipped default and every real settings.json seen so
            # far already had up_minw == up_minh, so nothing observable
            # is lost in practice).
            if "up_minside" not in agent_stored and (
                "up_minw" in agent_stored or "up_minh" in agent_stored
                or "up_aspmin" in agent_stored or "up_aspmax" in agent_stored
            ):
                try:
                    migrated = _migrate_legacy_upscale_gate(
                        agent_stored.get("up_minw", UPSCALE_MIN_SIDE_DEFAULT),
                        agent_stored.get("up_aspmin", UPSCALE_ASPECT_MIN),
                        agent_stored.get("up_aspmax", UPSCALE_ASPECT_MAX),
                    )
                except (TypeError, ValueError) as exc:
                    self._log(
                        f"MIGRATION: {SITES[key].name} legacy upscale gate"
                        f" is unreadable ({exc}) — using the shipped"
                        " default upscale gate"
                    )
                else:
                    self._log(
                        f"MIGRATION: {SITES[key].name} legacy upscale gate"
                        " (up_minw/up_minh/up_aspmin/up_aspmax) ->"
                        f" up_minside={migrated['min_side']} + 1 filter"
                        " condition, now under 'up_minside'/"
                        "'up_filter_conditions' (one-time; the old keys"
                        " stay on disk unread from now on)"
                    )
                    agent_stored["up_minside"] = str(migrated["min_side"])
                    agent_stored["up_filter_conditions"] = migrated[
                        "conditions"
                    ]

            upscale_conditions = None
            saved_up_conditions = agent_stored.get("up_filter_conditions")
            if isinstance(saved_up_conditions, list):
                upscale_conditions = _parse_condition_dicts(
                    saved_up_conditions, self._log
                )
            panel.apply_settings(
                agent_stored, upscale_conditions=upscale_conditions
            )

        # GUI rework Phase 13/14: each standalone tool's PERSISTENT
        # settings panel (all four now) — same "missing key = keep
        # default" contract as every other field, mirroring the
        # "agents" loop above. upscale/aspect additionally get a
        # ONE-TIME LOUD migration from the retired standalone dialogs'
        # OLD top-level keys (_migrate_upscale_panel_settings/
        # _migrate_aspect_panel_settings) — a no-op once each panel has
        # saved itself at least once under this NEW "tool_panels" key.
        for slot, panel in self._tool_panels.items():
            panel_stored = dict(stored.get("tool_panels", {}).get(slot, {}))
            if slot == "upscale":
                panel_stored = self._migrate_upscale_panel_settings(
                    panel_stored, stored
                )
            elif slot == "aspect":
                panel_stored = self._migrate_aspect_panel_settings(
                    panel_stored, stored
                )
            conditions = None
            raw_conditions = panel_stored.get("conditions")
            if isinstance(raw_conditions, list):
                conditions = _parse_condition_dicts(raw_conditions, self._log)
            panel.apply_settings(panel_stored, conditions=conditions)

        saved_presets = stored.get(FILTER_PRESETS_SETTING)
        if isinstance(saved_presets, dict):
            self._filter_presets = {
                str(name): list(rows) for name, rows in saved_presets.items()
                if isinstance(rows, list)
            }

        if stored.get("geometry"):
            self.root.geometry(self._clamp_geometry(stored["geometry"]))

        # restore the collapsed/expanded Controls view LAST — geometry is
        # already sane, so the swap fits into a correctly-sized window (each
        # agent's fine-tune collapse was already applied in apply_settings)
        self._set_collapsed(bool(stored.get("controls_collapsed", False)))

    def _wire_persistence(self) -> None:
        """Meaningful changes debounce into a save; the queue buttons,
        zoom and the theme flip hook in at their own sites."""
        self.out_var.trace_add("write", lambda *_: self._schedule_save())
        for panel in self.agents.values():
            for var in panel.persist_vars():
                var.trace_add(
                    "write", lambda *_: self._schedule_save()
                )

    def _schedule_save(self) -> None:
        if self._save_job is not None:
            self.root.after_cancel(self._save_job)
        self._save_job = self.root.after(1500, self._save_now)

    def _save_now(self) -> None:
        self._save_job = None
        self._settings = self._collect_settings()
        try:
            save_settings(self._settings)
        except OSError as exc:
            self._log(f"SETTINGS SAVE FAILED: {exc}")

    def _on_close(self) -> None:
        self._save_now()
        # drop every live job's backups (tools AND, since GUI rework
        # Phase 8, the two gen sites' own per-step pipeline backups),
        # then sweep the whole temp root (belt-and-braces for any orphan)
        for temp in list(self._job_temps.values()):
            temp.clear()
        self._job_temps.clear()
        jobtemp.clear_all()
        self.root.destroy()


def main() -> None:
    root = tb.Window(themename="darkly")
    PainterGui(root)
    root.mainloop()


if __name__ == "__main__":
    main()
