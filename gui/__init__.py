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
from .app import PainterGui, main
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
