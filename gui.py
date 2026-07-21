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

import io
import math
import queue
import random
import re
import threading
import time
import tkinter as tk
import webbrowser
from dataclasses import replace
from tkinter import font as tkfont
from datetime import datetime
from functools import partial
from pathlib import Path, PurePosixPath
from tkinter import filedialog, messagebox, ttk
from types import SimpleNamespace
from typing import Callable

import customtkinter as ctk
import ttkbootstrap as tb
from PIL import Image, ImageColor, ImageDraw, ImageFilter, ImageGrab, ImageTk

from painter.config import (
    AI_CALL_PAUSE_S,
    AI_CHECK_INSTRUCTIONS,
    AI_IMAGE_GATE_MESSAGE,
    AI_IMAGE_PROBE_PROMPT,
    AI_STUDIO_URL,
    AI_TEST_PROMPT,
    ASPECT_DEFAULT_H,
    ASPECT_DEFAULT_W,
    ASPECT_FILTER_DEFAULT_FROM,
    ASPECT_FILTER_DEFAULT_TO,
    ASPECT_FILTER_IF,
    ASPECT_FILTER_IF_NOT,
    ASPECT_FILTER_OFF,
    BACKGROUND_CHOICES,
    BADGES,
    BADGE_DOT_GAP_PX,
    BADGE_DOT_PX,
    BADGE_DOT_SS,
    CDP_URL,
    CHECKER_DARK,
    CHECKER_LIGHT,
    CHECKER_TILE_PX,
    CLEAN_EDGE_ENABLE,
    CROP_INK_ALPHA,
    CROP_MARGIN_PX,
    CROP_MIN_INK_PX,
    DEFAULT_OUT_DIR,
    FILTER_ASPECT_EXACT_TOL,
    FILTER_KIND_ANY_SIDE,
    FILTER_KIND_ASPECT_EXACT,
    FILTER_KIND_ASPECT_RANGE,
    FILTER_KIND_HEIGHT,
    FILTER_KIND_WIDTH,
    FILTER_KINDS,
    FILTER_POLARITY_IF,
    FILTER_POLARITY_IF_NOT,
    FILTER_PRESETS_SETTING,
    GEMINI_IMAGE_MODEL,
    GEMINI_KEY_SETTING,
    GEMINI_VISION_MODEL,
    GRID_COLS_BY_COUNT,
    JOB_LABEL,
    JOB_LOGO,
    JOB_METRIC,
    JOB_ORDER,
    JOB_TOOL_KINDS,
    JOBTEMP_CAP_BANNER_TEXT,
    JOBTEMP_KEEP_ALL_STEPS_DEFAULT,
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
    NEW_CHAT_CHOICES,
    RESIZE_SETTLE_MS,
    SAFETY_MAX_REMOVE_FRAC,
    SAFETY_MAX_REMOVE_FRAC_WHITE,
    SHEETS_DIR,
    SITES,
    STATE_DIRNAME,
    STEP_RESTORE_CURRENT_LABEL,
    STYLE_CHOICES,
    STYLE_DEFAULT,
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
    UPSCALE_MINDIM_STEP,
    dest_for,
    fmt_duration,
    fmt_op_duration,
    fmt_pct,
    fmt_size,
    iter_images,
    iter_md_files,
    badge_keys_for,
    button_fill_pair,
    button_text_pair,
    job_color_pair,
    prompt_suffix,
    selection_base_and_rels,
    status_pair,
    theme_pair,
    tile_for_kind,
)
from painter import aspect, filters, jobtemp
from painter.settings import load_settings, save_settings
from painter.sheet_parser import Sheet, SheetError, parse_sheet

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
ACTIVE_THEME = "night"


def status(role: str) -> str:
    """The ACTIVE theme's semantic status colour for one role (read
    live, so a widget built after a flip gets the right colour)."""
    return THEMES[ACTIVE_THEME]["status"][role]


def job_color(kind: str) -> str:
    """The ACTIVE theme's single hex for one job kind — resolves the
    (day, night) ``JOB_COLORS`` pair the same way ``status()`` resolves
    the status palette, for plain-tk drawing (Canvas shapes) that CTk's
    automatic light/dark tuple resolution can't reach (e.g.
    ``AspectRatioCanvas``)."""
    day, night = job_color_pair(kind)
    return day if ACTIVE_THEME == "day" else night

# button icons — SVG-first (the owner's assets/icons/*.svg), rasterized
# through Qt's QSvgRenderer (PySide6, already a monorepo build dep) at
# 4x and LANCZOS-downscaled for crispness; PNG is the fallback for
# icons with no svg (web, ai) and for svgs Qt cannot render (see
# _QT_UNSUPPORTED_SVG). Resolved beside gui.py, never the CWD.
ICON_DIR = Path(__file__).resolve().parent / "assets" / "icons"
ICON_TARGET_PX = 20  # max icon side inside a button / beside a switch
SVG_OVERSAMPLE = 4  # rasterize at 4x, then LANCZOS down

# QtSvg implements the SVG Tiny profile: clipPath/mask/filter (typical
# of Illustrator raster-trace exports like gemini.svg, 12 embedded
# rasters under 28 clipPaths) render as garbage — such files need a
# pre-rasterized .png sibling (gemini.png was rendered once from the
# svg via chromium, transparent, 512 px).
_QT_UNSUPPORTED_SVG = (b"<clipPath", b"<mask", b"<filter")

# CTk widgets show CTkImage (PIL-backed, smooth downscale) — cached per
# (name, size) for the whole process so every widget reuses one
# instance per icon.
_ICONS: dict[tuple[str, int], ctk.CTkImage] = {}

# QSvgRenderer needs a live QGuiApplication; created lazily on the
# first svg icon and kept for the whole process (never exec()-ed — it
# only serves offscreen painting, tkinter keeps the event loop).
_QT_APP = None

# the site logos (assets/icons stems) now live in config.JOB_LOGO —
# one home shared by the agent panels, dashboard panels and buttons.

# ---------------------------------------------------------------------
# the font registry — CSS-rem style: ONE root size, every role a
# multiplier of it. Ctrl+MouseWheel / Ctrl+(+/-) zoom the root and the
# whole window rescales proportionally (set_font_base).
# ---------------------------------------------------------------------

FONT_SANS = "Segoe UI"
FONT_MONOSPACE = "Consolas"
FONT_BASE_DEFAULT = 10  # the root ("rem") size the GUI ships with
FONT_MIN, FONT_MAX = 7, 20  # zoom clamp
FONT_BASE = FONT_BASE_DEFAULT  # the LIVE root size (zoom mutates it)

# role -> (multiplier, family, weight). The multipliers reproduce the
# pre-zoom look exactly (Big 16/root 10 = 1.6 and so on).
FONT_ROLES: dict[str, tuple[float, str, str]] = {
    "root": (1.0, FONT_SANS, "normal"),   # body text, entries, combos
    "bold": (1.0, FONT_SANS, "bold"),     # buttons, Value labels, **bold**
    "head": (1.1, FONT_SANS, "bold"),     # section headers, doc h3
    "title": (1.6, FONT_SANS, "bold"),    # the site panel titles
    "spin": (1.2, FONT_SANS, "bold"),     # the Spinner +/- glyphs
    "mono": (0.9, FONT_MONOSPACE, "normal"),  # log, queue list, code
    "doc_h1": (1.5, FONT_SANS, "bold"),   # DocWindow headings
    "doc_h2": (1.2, FONT_SANS, "bold"),
}
TREE_ROW_FACTOR = 2.4  # Treeview rowheight = root size * this

# one SHARED font object per role — tk named fonts and CTkFonts both
# propagate a .configure(size=...) to every widget/style/tag that
# references them, so re-applying a zoom is automatic
_TK_FONTS: dict[str, tkfont.Font] = {}
_CTK_FONTS: dict[str, ctk.CTkFont] = {}


def font_size(role: str) -> int:
    """The role's CURRENT pixel size (root size x its multiplier)."""
    return max(round(FONT_BASE * FONT_ROLES[role][0]), 5)


def tk_font(role: str) -> tkfont.Font:
    """The role's shared named tk font — for ttk styles, tk widgets
    and Text tags (created lazily; needs the root window)."""
    if role not in _TK_FONTS:
        _mult, family, weight = FONT_ROLES[role]
        _TK_FONTS[role] = tkfont.Font(
            family=family, size=font_size(role), weight=weight
        )
    return _TK_FONTS[role]


def ctk_font(role: str) -> ctk.CTkFont:
    """The role's shared CTkFont — for every customtkinter widget."""
    if role not in _CTK_FONTS:
        _mult, family, weight = FONT_ROLES[role]
        _CTK_FONTS[role] = ctk.CTkFont(
            family=family, size=font_size(role), weight=weight
        )
    return _CTK_FONTS[role]


def set_font_base(size: int) -> bool:
    """Zoom: move the root size (clamped) and rescale EVERY role.

    Both font families are shared objects, so one .configure(size=...)
    per role updates every widget, ttk style and Text tag at once;
    only the Treeview row height needs an explicit re-apply. Returns
    False when the clamp made it a no-op."""
    global FONT_BASE
    size = min(max(size, FONT_MIN), FONT_MAX)
    if size == FONT_BASE:
        return False
    FONT_BASE = size
    for role, f in _TK_FONTS.items():
        f.configure(size=font_size(role))
    for role, f in _CTK_FONTS.items():
        f.configure(size=font_size(role))
    tb.Style().configure(
        "Treeview", rowheight=round(FONT_BASE * TREE_ROW_FACTOR)
    )
    return True

# the rounded-control geometry — one place so every control matches
# (RHMH runs CTkButton corner_radius 10–12; hover = colour * 0.75)
BTN_RADIUS = 12
BTN_HEIGHT = 30
INPUT_RADIUS = 8
INPUT_HEIGHT = 28
HOVER_DARKEN = 0.75

# --- Select-images window geometry (Rule #4) --------------------------
# The three-level tree (collection -> folder -> image) is a frame-tree
# of plain ttk widgets: names WRAP via ttk.Label(wraplength=), the two
# per-site count/checkbox columns are FIXED width so they stay aligned
# no matter how deep the row is or how far its name wraps.
SELECT_MIN_W = 860          # open + minimum width (hint + bar buttons fit)
SELECT_OPEN_H = 520         # minimum height (the open height is screen-tall)
SELECT_INDENT_PX = 22       # left indent added per tree level (folder, image)
SELECT_TRI_PX = 22          # width reserved for a row's ▶/▼ triangle glyph
SELECT_COUNT_COL_PX = 96    # ONE site count/checkbox column (fits 'NNN/NNN'
#                             at the FONT_MAX zoom without clipping)
SELECT_SCROLLBAR_PX = 18    # v-scrollbar gutter — header cells sit over body
SELECT_WRAP_RESERVE_PX = 300  # indent+triangle+2*count reserve; canvas width
#                               minus this is the label wraplength
SELECT_WRAP_MIN_PX = 140    # never wrap tighter than this
SELECT_ADVICE_TRUNC = 70    # advice text shown on a leaf row, truncated
SELECT_ROW_PADY = 1         # vertical padding per tree row
SELECT_EXPAND_CHUNK = 8     # leaf rows built per Expand-all tick — bounds the
#                             main-thread block (measured median ≈ 120 ms, p90
#                             ≈ 200 ms per tick over the owner's real queue) so
#                             Expand-all fills progressively, never a freeze
SELECT_EXPAND_TICK_MS = 1   # gap between Expand-all chunks — yields to the event
#                             loop so the tree fills in progressively, non-blocked
SELECT_FIT_PAD_PX = 24      # slack added to the widest measured name so a title
#                             that FITS never wraps by a hair (frame borders eat
#                             a few px of the settled canvas width)

# --- DocWindow + shared window sizing (Rule #4) -----------------------
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
DOC_A4_RATIO = 210 / 297    # ISO A4 portrait width:height (~0.707)
DOC_HEIGHT_FRAC = 0.8       # A4 text height (and the Select tall height) = screen_h * this
DOC_MAX_FRAC = 0.9          # clamp ANY window to this fraction of the screen
DOC_MIN_W = 520             # never narrower than this (the top button bar fits)
DOC_MIN_H = 400             # never shorter than this (also the provisional height)
DOC_IMG_PAD_PX = 60         # horizontal padding around the image column (image mode)
DOC_CHROME_PAD_PX = 48      # non-text vertical chrome: Text pady + frame margins

# --- Before/after viewer (the tool panels' Restore viewer) ------------
BEFORE_AFTER_W = 760          # viewer width; before/after images scale into it
BEFORE_AFTER_IMG_PAD_PX = 60  # slack subtracted from the width for the images

# --- Per-step restore viewer (GUI rework Phase 9) ---------------------
# a horizontal filmstrip, so its own width geometry is independent of
# BEFORE_AFTER_W's stacked single-column layout.
STEP_RESTORE_W = 900        # viewer width; grows via horizontal scroll past this
STEP_RESTORE_THUMB_PX = 220  # each stage thumbnail's max width

# --- JobPanel's loud persistent cap-warning strip (GUI rework Phase 8) -
# see JobPanel._show_cap_banner/_hide_cap_banner; wraplength keeps the
# (fairly long) JOBTEMP_CAP_BANNER_TEXT readable inside one dashboard
# panel column instead of stretching it.
JOB_PANEL_BANNER_WRAP_PX = 480

# --- Aspect-ratio prompt (the standalone 'Aspect ratio…' tool) -------
ASPECT_DIALOG_ENTRY_W = 64  # px width of each W / H field in the ratio dialog
ASPECT_DIALOG_PAD_PX = 16   # padding around the ratio dialog body

# --- AspectRatioCanvas — the visual target-ratio editor (GUI rework
# Phase 5). Pure Tk pixel geometry only, same split as the FilterEditor
# block below: the engine-pure ASPECT_LABEL_DECIMALS (the live label's
# rounding) lives in painter/config.py beside the rest of the aspect
# constants, alongside the pure reduced_ratio/decimal_ratio_label
# functions themselves (painter/aspect.py) — this widget only draws.
# Colours are NEVER hardcoded here — job_color("aspect")/THEMES are read
# live at draw time, same as every other themed canvas (DayNightSwitch).
# A FIXED pixel size (it does not track the font zoom, like the switch).
ASPECT_CANVAS_BOX_PX = 200         # arena side — max span either axis can draw
ASPECT_CANVAS_PAD_PX = 26          # margin around the arena (handles + labels)
ASPECT_CANVAS_MIN_PX = 28          # a dragged side never collapses below this
ASPECT_CANVAS_EDGE_GRAB_PX = 10    # hit-test tolerance to start an edge drag
ASPECT_CANVAS_HANDLE_R = 5         # edge-handle marker circle radius
ASPECT_CANVAS_OUTLINE_W = 3        # ratio-box outline stroke width
ASPECT_CANVAS_LABEL_GAP_PX = 10    # gap between the arena and the dual label
ASPECT_CANVAS_LABEL_RESERVE_PX = 24  # vertical space reserved for the label

# --- FilterEditor — the reusable stacked-filter widget (GUI rework
# Phase 4, wraps painter.filters). Pure Tk pixel geometry only; the
# engine-side kind/polarity strings and the exact-aspect tolerance live
# in painter/config.py alongside the rest of the FILTER_* constants —
# this block is gui.py's own Rule #4 home, same split as every other
# dialog's *_ENTRY_W / *_PAD_PX above.
FILTER_ROW_KIND_W = 132      # kind combo (fits "Aspect (exact)")
FILTER_ROW_POLARITY_W = 78   # the IF / IF NOT combo
FILTER_ROW_ENTRY_W = 64      # each lo/hi (or single ratio) numeric field
FILTER_ROW_DECIMALS = 3      # aspect kinds' lo/hi/ratio display precision
FILTER_ROW_GAP_PX = 6        # vertical gap between stacked rows / sections
FILTER_PRESET_COMBO_W = 160  # the saved-preset name combo

# --- AI dialogs: key wizard / sheet generator / checker (Rule #4) -----
AI_KEY_ENTRY_W = 380        # the wizard's key entry width (px)
AI_STATUS_WRAP_PX = 460     # AI dialog status / question label wraplength
AI_REQUEST_LINES = 4        # the request Text height (lines)
AI_STEP_INDENT_PX = 28      # wizard body indent under the numbered steps
AI_POLL_MS = 150            # AI dialog worker-queue poll cadence (ms)
AI_CHECK_DEFECT_COL_PX = 64   # the checker tree's 'Defects' count column
AI_CHECK_TIME_COL_PX = 64     # the checker tree's per-image 'Time' column
AI_CHECK_FIRST_COL_PX = 230   # the checker tree's 'First defect' column
AI_CHECK_LOG_EVERY = 5      # checker progress log cadence (paced calls are slow)
# DashPanel's own check-status column (GUI rework Phase 16) — the
# parallel per-item Checker AI's "checking…"/"OK"/"flagged N"/"error"
# indicator, appended after Size in the site dashboard's image rows.
DASH_CHECK_COL_PX = 92

# --- Main window: min size, on-screen clamp, wheel, collapse (Rule #4) -
# The whole window is vertically scrollable so a stale-tall geometry can
# never hide the bottom, and the upper control area collapses to a thin
# per-agent strip so the Dashboard can take the full height.
WINDOW_MIN_W = 900          # root.minsize width
WINDOW_MIN_H = 640          # root.minsize height
WINDOW_SCREEN_MARGIN_PX = 80  # taskbar + titlebar + slack subtracted from
#                               screen w/h when clamping a restored geometry
WHEEL_DELTA_UNIT = 120      # one mouse-wheel notch (event.delta per detent)
COMPACT_CLUSTER_GAP_PX = 24  # gap between the two agent clusters when collapsed
COLLAPSE_GLYPH_EXPANDED = "▾  Controls"   # toggle label while controls show
COLLAPSE_GLYPH_COLLAPSED = "▸  Controls"  # toggle label while collapsed
ICON_BAR_GAP_PX = 4  # gap between IconBar tile buttons (GUI rework Phase 11)
# each AgentPanel's own Settings gear (owner 2026-07-19) shows/hides THAT
# agent's fine-tune — its pause range, action-delay range and upscale-gate
# fields — independently of the other site; HIDDEN by default so the panel
# stays compact. The gear carries settings.png (a gear icon) + this caret.
SETTINGS_GLYPH_EXPANDED = "▾  Settings"   # gear label while fine-tune shows
SETTINGS_GLYPH_COLLAPSED = "▸  Settings"  # gear label while hidden
# the Treeview row tags for a tool panel's image rows — their foregrounds
# come from the theme's status colours, re-applied on a flip via skin_tree.
# CHANGED (restorable) rows get a BOLD striking green/teal so they POP;
# SKIPPED (unchanged) rows a muted grey so the two never blur together.
TOOL_CHANGED_TAG = "toolchanged"
TOOL_SKIP_TAG = "skip"


def _svg_to_pil(path: Path, target_px: int) -> Image.Image:
    """Rasterize one SVG via QSvgRenderer: aspect-fit ``target_px`` on
    the longer side, rendered at SVG_OVERSAMPLE x and LANCZOS-downscaled
    so ~20 px icons stay crisp."""
    global _QT_APP
    from PySide6.QtCore import QBuffer, Qt
    from PySide6.QtGui import QGuiApplication, QImage, QPainter
    from PySide6.QtSvg import QSvgRenderer

    if _QT_APP is None:
        _QT_APP = QGuiApplication.instance() or QGuiApplication([])
    renderer = QSvgRenderer(str(path))
    if not renderer.isValid():
        raise ValueError(f"unrenderable SVG: {path}")
    base = renderer.defaultSize()
    scale = target_px / max(base.width(), base.height())
    final = (
        max(round(base.width() * scale), 1),
        max(round(base.height() * scale), 1),
    )
    qimg = QImage(
        final[0] * SVG_OVERSAMPLE, final[1] * SVG_OVERSAMPLE,
        QImage.Format.Format_ARGB32,
    )
    qimg.fill(Qt.GlobalColor.transparent)
    painter = QPainter(qimg)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
    renderer.render(painter)
    painter.end()
    buffer = QBuffer()
    buffer.open(QBuffer.OpenModeFlag.ReadWrite)
    qimg.save(buffer, "PNG")
    pil = Image.open(io.BytesIO(bytes(buffer.data()))).convert("RGBA")
    return pil.resize(final, Image.LANCZOS)


def icon(name: str, size: int = ICON_TARGET_PX) -> ctk.CTkImage:
    """The named icon, loaded once per (name, size) and scaled to fit.

    ``name.svg`` wins when Qt can render it; ``name.png`` covers the
    rest (web/ai have no svg; gemini.svg needs its pre-rasterized
    sibling). A missing/unrenderable icon is a loud error (root
    Rule #1) — no silent icon-less fallback.
    """
    key = (name, size)
    if key not in _ICONS:
        svg_path = ICON_DIR / f"{name}.svg"
        png_path = ICON_DIR / f"{name}.png"
        svg_ok = svg_path.is_file() and not any(
            tag in svg_path.read_bytes() for tag in _QT_UNSUPPORTED_SVG
        )
        if svg_ok:
            img = _svg_to_pil(svg_path, size)
        elif png_path.is_file():
            img = Image.open(png_path)
            scale = min(size / max(img.width, img.height), 1.0)
            img = img.convert("RGBA").resize(
                (
                    max(round(img.width * scale), 1),
                    max(round(img.height * scale), 1),
                ),
                Image.LANCZOS,
            )
        elif svg_path.is_file():
            raise FileNotFoundError(
                f"GUI icon {svg_path} uses SVG features QtSvg cannot"
                " render (clipPath/mask/filter) and has no .png sibling"
                " — pre-rasterize it once (e.g. via a browser) and save"
                f" it as {png_path}"
            )
        else:
            raise FileNotFoundError(
                f"GUI icon missing: {svg_path} / {png_path}"
            )
        _ICONS[key] = ctk.CTkImage(
            light_image=img, dark_image=img, size=img.size
        )
    return _ICONS[key]


# --- Day/Night switch art — anti-aliased PIL images (owner 2026-07-18)
# tkinter Canvas has no anti-aliasing, so the switch composites PIL
# images instead of raw ovals: the TWO track pills come straight from the
# owner's website SVGs (reusing the _svg_to_pil path above), the SUN/MOON
# knobs are rendered here as RGBA discs with a radial gradient, at
# SWITCH_SUPERSAMPLE x the final size then LANCZOS-downscaled for smooth
# edges. All four are built ONCE per switch (the switch is a fixed size —
# it does not follow the font zoom) and held on the widget.


def _radial_disc(
    px: int, center_hex: str, edge_hex: str, hilite: tuple[float, float]
) -> Image.Image:
    """A supersampled RGBA disc (``px`` square): a radial gradient from
    ``center_hex`` at the ``hilite`` point (fraction of the box) to
    ``edge_hex`` at the rim, opaque inside the inscribed circle and fully
    transparent outside. Rendered at native ``px`` — the caller LANCZOS-
    downscales the whole knob so the rim anti-aliases smoothly."""
    import numpy as np

    yy, xx = np.mgrid[0:px, 0:px].astype(np.float32)
    r = px / 2.0
    hx, hy = hilite[0] * px, hilite[1] * px
    # distance from the highlight, normalised so the farthest rim point
    # (opposite the highlight) maps to 1.0 — keeps the ramp inside [0, 1]
    dist = np.sqrt((xx - hx) ** 2 + (yy - hy) ** 2)
    far = r + np.sqrt((hx - r) ** 2 + (hy - r) ** 2)
    t = np.clip(dist / far, 0.0, 1.0)[..., None]
    c0 = np.array(ImageColor.getrgb(center_hex), np.float32)
    c1 = np.array(ImageColor.getrgb(edge_hex), np.float32)
    rgb = c0 * (1.0 - t) + c1 * t
    # circular alpha mask (hard here; the downscale smooths the rim)
    dc = np.sqrt((xx - r + 0.5) ** 2 + (yy - r + 0.5) ** 2)
    alpha = np.where(dc <= r, 255.0, 0.0)[..., None]
    out = np.concatenate([rgb, alpha], axis=2).astype(np.uint8)
    return Image.fromarray(out, "RGBA")


def _render_moon_knob(d_px: int, ss: int) -> Image.Image:
    """The MOON — a real moon, not a flat disc (owner 2026-07-20).

    Three layers over the silver radial-gradient sphere, all driven by
    the SWITCH_MOON_* / SWITCH_CRATER* config constants:
      * 7 CRATERS of varied sizes (darker floors), each with a lit RIM
        ARC on the side facing the incoming light;
      * TERMINATOR shading — brightness ramps from the lit limb (the
        SWITCH_MOON_LIGHT_DIR side) down to SWITCH_MOON_DARK_FLOOR on
        the far limb across a soft smoothstep band, darkening crater
        floors and rims with the surface so the sphere reads as lit
        from one side;
      * subtle surface MOTTLING — a low-res value-noise grid (FIXED
        seed, so the moon is identical every build) bicubic-upscaled
        over the disc, ± SWITCH_MOON_NOISE_AMPL brightness steps.
    ``d_px`` = final diameter, ``ss`` = supersample factor (rendered at
    ss x, LANCZOS-downscaled like every knob)."""
    import numpy as np

    s = d_px * ss
    disc = _radial_disc(
        s, SWITCH_MOON_CENTER, SWITCH_MOON_EDGE, SWITCH_KNOB_HILIGHT
    )
    draw = ImageDraw.Draw(disc)
    crater = (*ImageColor.getrgb(SWITCH_CRATER), 255)
    # the rims live on their own layer and alpha-BLEND onto the disc —
    # drawing a translucent fill straight into the RGBA disc would
    # REPLACE the alpha (a see-through ring), and a solid near-white
    # arc read as a pac-man ring instead of a subtle lit rim
    rims = Image.new("RGBA", (s, s), (0, 0, 0, 0))
    rim_draw = ImageDraw.Draw(rims)
    rim = (*ImageColor.getrgb(SWITCH_CRATER_RIM), SWITCH_CRATER_RIM_ALPHA)
    lx, ly = SWITCH_MOON_LIGHT_DIR
    # PIL arc degrees (x right, y down, clockwise from 3 o'clock): the
    # rim arc is centred on the direction the light comes FROM
    light_deg = math.degrees(math.atan2(ly, lx))
    half_arc = SWITCH_CRATER_RIM_ARC_DEG / 2
    for cf, cxf, cyf in SWITCH_CRATERS:
        cd = s * cf
        ccx, ccy = cxf * s, cyf * s
        box = [ccx - cd / 2, ccy - cd / 2, ccx + cd / 2, ccy + cd / 2]
        draw.ellipse(box, fill=crater)
        rim_draw.arc(
            box, start=light_deg - half_arc, end=light_deg + half_arc,
            fill=rim, width=max(round(cd * SWITCH_CRATER_RIM_FRAC), ss),
        )
    disc.alpha_composite(rims)
    # terminator shading x mottling on the RGB channels (alpha untouched)
    arr = np.asarray(disc).astype(np.float32)
    r = s / 2.0
    yy, xx = np.mgrid[0:s, 0:s].astype(np.float32)
    nx, ny = (xx - r + 0.5) / r, (yy - r + 0.5) / r
    # projection onto the light direction: +1 = the lit limb, -1 = far
    proj = (nx * lx + ny * ly) / math.hypot(lx, ly)
    soft = SWITCH_MOON_TERMINATOR_SOFT
    u = np.clip((proj + soft) / (2.0 * soft), 0.0, 1.0)
    u = u * u * (3.0 - 2.0 * u)  # smoothstep across the terminator band
    shade = SWITCH_MOON_DARK_FLOOR + (1.0 - SWITCH_MOON_DARK_FLOOR) * u
    rng = np.random.default_rng(SWITCH_MOON_NOISE_SEED)
    cells = rng.uniform(-1.0, 1.0, (SWITCH_MOON_NOISE_CELLS,) * 2)
    noise = Image.fromarray(
        ((cells + 1.0) * 127.5).astype(np.uint8), "L"
    ).resize((s, s), Image.BICUBIC)
    mottle = (
        np.asarray(noise).astype(np.float32) / 127.5 - 1.0
    ) * SWITCH_MOON_NOISE_AMPL
    arr[..., :3] = np.clip(
        arr[..., :3] * shade[..., None] + mottle[..., None], 0.0, 255.0
    )
    disc = Image.fromarray(arr.astype(np.uint8), "RGBA")
    return disc.resize((d_px, d_px), Image.LANCZOS)


def _render_sun_knob(d_px: int, ss: int) -> Image.Image:
    """The SUN: a gold radial-gradient sphere over a soft blurred gold
    glow. The image is SWITCH_SUN_CELL_SCALE x the knob so the glow has
    room to fade; the sun disc sits centred. ``d_px`` = knob diameter."""
    cell = round(d_px * SWITCH_SUN_CELL_SCALE)
    s = cell * ss
    # glow: a low-alpha gold disc behind, GaussianBlur-ed to a soft halo
    glow = Image.new("RGBA", (s, s), (0, 0, 0, 0))
    gd = d_px * SWITCH_SUN_GLOW_SCALE * ss
    gc = s / 2.0
    ImageDraw.Draw(glow).ellipse(
        [gc - gd / 2, gc - gd / 2, gc + gd / 2, gc + gd / 2],
        fill=(*ImageColor.getrgb(SWITCH_SUN_GLOW), SWITCH_SUN_GLOW_ALPHA),
    )
    glow = glow.filter(
        ImageFilter.GaussianBlur(SWITCH_SUN_GLOW_BLUR * d_px * ss)
    )
    disc = _radial_disc(
        d_px * ss, SWITCH_SUN_CENTER, SWITCH_SUN_EDGE, SWITCH_KNOB_HILIGHT
    )
    off = round((s - d_px * ss) / 2)
    glow.alpha_composite(disc, (off, off))
    return glow.resize((cell, cell), Image.LANCZOS)


def _render_theme_cover_icon(target_name: str, min_dim: int) -> Image.Image:
    """The BIG centred icon that rides the theme cross-fade cover: the
    SUN of the theme being switched TO (day) or the MOON (night), the
    SAME anti-aliased PIL renderers as the switch knob, sized to
    ``SWITCH_COVER_ICON_FRAC`` of the window's min dimension. RGBA with
    transparent surroundings so it composites cleanly onto the snapshot
    (owner 2026-07-19)."""
    d = max(round(min_dim * SWITCH_COVER_ICON_FRAC), 1)
    ss = SWITCH_COVER_ICON_SS
    if THEMES[target_name]["switch_on"]:   # going to day -> the sun
        return _render_sun_knob(d, ss)
    return _render_moon_knob(d, ss)        # going to night -> the moon


def _render_switch_track(stem: str, w: int, h: int) -> Image.Image:
    """One track pill: the owner's website switch SVG (in assets/icons),
    rasterized anti-aliased through the icon SVG->PIL path and sized to
    the exact pill box. A missing SVG is a loud error (Rule #1)."""
    svg_path = ICON_DIR / f"{stem}.svg"
    if not svg_path.is_file():
        raise FileNotFoundError(
            f"Day/Night switch track SVG missing: {svg_path}"
        )
    pil = _svg_to_pil(svg_path, w)
    if pil.size != (w, h):
        pil = pil.resize((w, h), Image.LANCZOS)
    return pil


def _darken(hex_color: str, factor: float = HOVER_DARKEN) -> str:
    """The hover shade RHMH uses: the same colour scaled toward black."""
    r = int(hex_color[1:3], 16)
    g = int(hex_color[3:5], 16)
    b = int(hex_color[5:7], 16)
    return (
        f"#{int(r * factor):02x}{int(g * factor):02x}{int(b * factor):02x}"
    )


def _darken_pair(
    pair: tuple[str, str], factor: float = HOVER_DARKEN
) -> tuple[str, str]:
    """Darken each end of a (day, night) tuple so hover shades stay
    theme-aware tuples the appearance mode can flip."""
    return (_darken(pair[0], factor), _darken(pair[1], factor))


def _button_colors(kind: str) -> dict:
    """CTkButton colour kwargs for one semantic kind, as (day, night)
    tuples — a single ctk.set_appearance_mode() then repaints every
    button with zero re-walk. Solid kinds draw their fill AND label from
    the per-theme BUTTON_FILL / BUTTON_TEXT pairs (owner 2026-07-19): the
    DAY shade differs from NIGHT for every kind, and the neutral
    'secondary' is a LIGHT sand fill with DARK text on day (never the
    dark warm-grey that read brown on the cream window); coloured kinds
    keep a white label in both themes."""
    solid = ("secondary", "success", "danger", "info")
    if kind in solid:
        fill = button_fill_pair(kind)
        return dict(
            fg_color=fill, hover_color=_darken_pair(fill),
            text_color=button_text_pair(kind),
            text_color_disabled=theme_pair("light"),
        )
    outline = {
        "secondary-outline": theme_pair("light"),
        "danger-outline": theme_pair("danger"),
        "success-outline": theme_pair("success"),
    }
    if kind in outline:
        color = outline[kind]
        return dict(
            fg_color="transparent", border_width=1, border_color=color,
            hover_color=_darken_pair(color, 0.35),
            text_color=color, text_color_disabled=theme_pair("secondary"),
        )
    if kind == "link":  # borderless accent button (dashboard 'Show')
        return dict(
            fg_color="transparent", hover_color=theme_pair("dark"),
            text_color=theme_pair("info"),
            text_color_disabled=theme_pair("secondary"),
        )
    if kind == "expander":  # flat left-aligned ▶/▼ section header
        return dict(
            fg_color="transparent", hover_color=theme_pair("dark"),
            text_color=theme_pair("fg"),
            text_color_disabled=theme_pair("secondary"),
            anchor="w",
        )
    raise ValueError(f"unknown button kind: {kind}")


class EdgeIconButton(ctk.CTkButton):
    """A CTkButton whose ICON sits at the left edge while the TEXT
    centers in the remaining width — for stacked equal-width buttons
    (Add…/Remove/Clear), where the default centered icon+text block
    makes the icons jitter with the text length.

    CTkButton lays image and text on an internal 5x5 grid (pad, image,
    spacing, text, pad); this override pins the image column west and
    gives the text cell all the remaining weight, centered."""

    def _create_grid(self):
        super()._create_grid()
        if self._image_label is None or self._text_label is None:
            return  # icon-less (or image-only) — default layout stands
        # col 0 keeps its minsize (the corner inset) but stops growing;
        # col 3 takes ALL the slack so the un-sticky text centers in it
        self.grid_columnconfigure(0, weight=0)
        self.grid_columnconfigure((1, 2), weight=0)
        self.grid_columnconfigure(3, weight=1)
        self.grid_columnconfigure(4, weight=0)
        self._image_label.grid(row=2, column=1, sticky="w")
        self._text_label.grid(row=2, column=3, sticky="")


def rounded_button(
    parent,
    text: str,
    command=None,
    kind: str = "secondary",
    icon_name: str | None = None,
    compound: str = "left",
    width: int = 0,
    icon_edge: bool = False,
    **kwargs,
) -> ctk.CTkButton:
    """Every GUI button: a rounded CTkButton in the darkly palette —
    the RHMH look. ``width`` is a minimum in px (0 = fit the text);
    the button grows to fit longer text either way. ``icon_edge``
    pins the icon to the left edge and centers the text (the stacked
    Collections buttons)."""
    opts = _button_colors(kind)
    opts.setdefault("bg_color", theme_pair("bg"))
    opts.update(kwargs)
    cls = EdgeIconButton if icon_edge else ctk.CTkButton
    return cls(
        parent, text=text, command=command, width=width,
        height=BTN_HEIGHT, corner_radius=BTN_RADIUS,
        font=ctk_font("bold"),
        image=icon(icon_name) if icon_name else None,
        compound=compound, **opts,
    )


def _input_colors() -> dict:
    """Shared colour kwargs for rounded CTk entry/combobox fields, as
    (day, night) tuples.

    ``bg_color`` is pinned to the active window background so the canvas
    corners around the rounded field never show the CTk theme's own gray
    on a ttk parent."""
    return dict(
        fg_color=theme_pair("inputbg"), border_color=theme_pair("secondary"),
        text_color=theme_pair("inputfg"), bg_color=theme_pair("bg"),
    )


def _untheme_inner_entry(field) -> None:
    """Kill the square ring inside CTk entry-like widgets.

    ttkbootstrap wraps EVERY plain-tk widget constructor and re-themes
    the widget right after creation — the tkinter.Entry INSIDE a
    CTkEntry/CTkComboBox gets ``highlightthickness=1`` with the darkly
    selectbg ring, which reads as a lighter SQUARE inside the rounded
    field. Unsubscribe it from ttkbootstrap's re-style publisher and
    drop the ring so the field is one smooth rounded shape."""
    from ttkbootstrap.publisher import Publisher

    inner = field._entry
    Publisher.unsubscribe(str(inner))
    inner.configure(highlightthickness=0)


def rounded_entry(parent, width: int = 140, **kwargs) -> ctk.CTkEntry:
    """A rounded, bordered entry in the darkly palette."""
    opts = _input_colors()
    opts.update(kwargs)
    field = ctk.CTkEntry(
        parent, width=width, height=INPUT_HEIGHT,
        corner_radius=INPUT_RADIUS, border_width=1,
        font=ctk_font("root"), **opts,
    )
    _untheme_inner_entry(field)
    return field


def rounded_combo(
    parent, values, variable, width: int = 140, **kwargs
) -> ctk.CTkComboBox:
    """A rounded dropdown bound to ``variable`` — read-only by default
    (pass ``state="normal"`` to also allow free typing, e.g. the
    FilterEditor preset-name combo, which doubles as a "type a new
    name to save" field)."""
    opts = _input_colors()
    opts.update(
        button_color=theme_pair("secondary"),
        button_hover_color=_darken_pair(theme_pair("secondary")),
        dropdown_fg_color=theme_pair("dark"),
        dropdown_hover_color=theme_pair("selectbg"),
        dropdown_text_color=theme_pair("fg"),
    )
    opts.update(kwargs)
    state = opts.pop("state", "readonly")
    field = ctk.CTkComboBox(
        parent, values=list(values), variable=variable, width=width,
        height=INPUT_HEIGHT, corner_radius=INPUT_RADIUS, border_width=1,
        state=state, font=ctk_font("root"),
        dropdown_font=ctk_font("root"), **opts,
    )
    _untheme_inner_entry(field)
    return field


class Spinner(ctk.CTkFrame):
    """A compact [-][entry][+] spinner as ONE rounded unit (Rule #5:
    one class — the four pace fields are its instances).

    The entry keeps the caller's StringVar, direct typing stays
    allowed and Start's validation is unchanged; +/- steps the value
    (never below 0). Unparsable text is left for Start to report."""

    def __init__(
        self, parent, variable, step: float, entry_width: int = 40,
        decimals: int | None = None,
    ):
        super().__init__(
            parent, corner_radius=INPUT_RADIUS, border_width=1,
            fg_color=theme_pair("inputbg"), border_color=theme_pair("secondary"),
            bg_color=theme_pair("bg"),
        )
        self._var = variable
        self._step = step
        # 1.0 steps show "8", 0.1 steps show "0.6"; an explicit ``decimals``
        # overrides (the aspect fields step 0.05 but want 2 decimals)
        self._decimals = (
            decimals if decimals is not None
            else (0 if float(step).is_integer() else 1)
        )
        # the +/- pads: ~24 px wide (clickable), slightly lower than the
        # frame so their canvases never overpaint the frame's own 1 px
        # border (CTk scales canvases; a 24 px child + 2 px pady used to
        # cover the bottom border row under the buttons)
        btn = dict(
            width=24, height=20, corner_radius=INPUT_RADIUS - 2,
            fg_color="transparent", hover_color=theme_pair("selectbg"),
            text_color=theme_pair("fg"), font=ctk_font("spin"),
        )
        ctk.CTkButton(
            self, text="−", command=partial(self._bump, -1.0), **btn
        ).pack(side="left", padx=(3, 0), pady=4)
        entry = ctk.CTkEntry(
            self, width=entry_width, height=INPUT_HEIGHT - 10,
            corner_radius=0, border_width=0, fg_color="transparent",
            text_color=theme_pair("inputfg"), justify="center",
            font=ctk_font("root"), textvariable=variable,
        )
        _untheme_inner_entry(entry)
        entry.pack(side="left", fill="x", expand=True, pady=4)
        ctk.CTkButton(
            self, text="+", command=partial(self._bump, 1.0), **btn
        ).pack(side="left", padx=(0, 3), pady=4)

    def _bump(self, sign: float) -> None:
        try:
            value = float(self._var.get())
        except ValueError:
            return  # typed garbage — Start's validation reports it
        value = max(value + sign * self._step, 0.0)
        self._var.set(f"{value:.{self._decimals}f}")


def rounded_switch(parent, text: str, variable) -> ctk.CTkSwitch:
    """A rounded on/off switch for the main run options."""
    return ctk.CTkSwitch(
        parent, text=text, variable=variable,
        onvalue=True, offvalue=False,
        font=ctk_font("root"),
        fg_color=theme_pair("secondary"), progress_color=theme_pair("success"),
        text_color=theme_pair("fg"), bg_color=theme_pair("bg"),
    )


def setup_style() -> None:
    """The few named styles the active ttkbootstrap theme does not ship.

    Reads ``style.colors`` LIVE, so re-running it after a theme_use()
    reproduces the styles in the new palette (this is how the ttk half
    of the app flips). Every font comes from the registry's shared named
    fonts, so a zoom (set_font_base) re-renders all of them without
    touching the styles again."""
    style = tb.Style()
    colors = style.colors
    style.configure(".", font=tk_font("root"))
    style.configure("Head.TLabel", font=tk_font("head"),
                    foreground=colors.info)
    style.configure("Big.TLabel", font=tk_font("title"))
    style.configure("Value.TLabel", font=tk_font("bold"))
    style.configure("Muted.TLabel", foreground=colors.light)
    style.configure("Mono.TLabel", font=tk_font("mono"),
                    foreground=colors.light)
    style.configure("Treeview", font=tk_font("root"),
                    rowheight=round(FONT_BASE * TREE_ROW_FACTOR))
    style.configure("Treeview.Heading", font=tk_font("bold"))


# ---------------------------------------------------------------------
# Plain-tk colour registry — the ONLY place plain tk Text/Listbox/
# Canvas/Toplevel colours live. Each widget is created through a skin_*
# helper that colours it AND registers (widget, role); apply_theme()
# then re-walks the flat registry, re-applying each role's skin from the
# now-active palette and pruning dead widgets. ttk styles and CTk tuples
# flip on their own; these do not, so they need the registry.
# ---------------------------------------------------------------------
THEMED_TK: list[tuple[tk.Misc, str]] = []


def _apply_text_skin(widget: tk.Text) -> None:
    colors = tb.Style().colors
    widget.configure(
        background=colors.inputbg, foreground=colors.inputfg,
        insertbackground=colors.inputfg,
        selectbackground=colors.selectbg,
        selectforeground=colors.selectfg,
        relief="flat", highlightthickness=0,
    )


def _apply_listbox_skin(widget: tk.Listbox) -> None:
    colors = tb.Style().colors
    widget.configure(
        background=colors.inputbg, foreground=colors.inputfg,
        selectbackground=colors.selectbg,
        selectforeground=colors.selectfg,
        relief="flat", highlightthickness=1,
        highlightbackground=colors.border,
        highlightcolor=colors.primary,
    )


def _apply_surface_skin(widget: tk.Misc) -> None:
    """Canvas / Toplevel: just the active window background."""
    widget.configure(background=tb.Style().colors.bg)


def _apply_tree_skin(widget: ttk.Treeview) -> None:
    """A tool-panel Treeview: (re-)tint the CHANGED- and SKIPPED-row tags
    from the active theme's status colours. The base row colours follow
    the ttk 'Treeview' style, but a per-widget TAG foreground does not — so
    both are registered here and re-applied on every flip (owner
    2026-07-19): CHANGED rows a striking green/teal, SKIPPED rows muted."""
    widget.tag_configure(TOOL_CHANGED_TAG, foreground=status("toolchanged"))
    widget.tag_configure(TOOL_SKIP_TAG, foreground=status("skip"))


_TK_SKIN = {
    "text": _apply_text_skin,
    "listbox": _apply_listbox_skin,
    "canvas": _apply_surface_skin,
    "toplevel": _apply_surface_skin,
    "tree": _apply_tree_skin,
}


def _skin(widget: tk.Misc, role: str) -> None:
    _TK_SKIN[role](widget)
    THEMED_TK.append((widget, role))


def skin_text(widget: tk.Text) -> None:
    """Colour a plain tk Text from the active palette and register it."""
    _skin(widget, "text")


def skin_listbox(widget: tk.Listbox) -> None:
    _skin(widget, "listbox")


def skin_canvas(widget: tk.Canvas) -> None:
    _skin(widget, "canvas")


def skin_tree(widget: ttk.Treeview) -> None:
    """Configure a tool-panel tree's SKIPPED-row tag and register it so
    the tint re-applies on a theme flip."""
    _skin(widget, "tree")


def skin_toplevel(widget: tk.Misc) -> None:
    _skin(widget, "toplevel")


def recolor_tk_registry() -> None:
    """Re-apply every registered plain-tk widget's role skin from the
    now-active palette; prune widgets destroyed since (the codebase's
    tk.TclError idiom)."""
    alive: list[tuple[tk.Misc, str]] = []
    for widget, role in THEMED_TK:
        try:
            _TK_SKIN[role](widget)
            alive.append((widget, role))
        except tk.TclError:
            pass  # widget destroyed — drop it
    THEMED_TK[:] = alive


# every theme-aware Toplevel (SelectWindow, DocWindow) registers itself
# here on __init__ and unregisters on <Destroy>; apply_theme fires each
# open one's own apply_theme() so it flips coherently with the main
# window (their per-widget foregrounds do not follow ttk styles)
THEME_TOPLEVELS: list = []


def _apply_theme_now(name: str) -> None:
    """The actual coherent flip (no animation): swap the ttkbootstrap
    theme + re-run setup_style (the ttk half), flip the customtkinter
    appearance mode (every CTk tuple re-resolves), recolour the plain-tk
    registry, then fire every open Toplevel's apply_theme. No window
    teardown — an active run's worker threads, dashboard counters and
    quota countdowns all survive."""
    global ACTIVE_THEME
    ACTIVE_THEME = name
    theme = THEMES[name]
    tb.Style().theme_use(theme["ttkname"])
    setup_style()
    ctk.set_appearance_mode(theme["mode"])
    recolor_tk_registry()
    for top in list(THEME_TOPLEVELS):
        try:
            top.apply_theme()
        except tk.TclError:
            pass  # closed mid-flip


# --- Snapshot cover + fade — the ONE transition mechanism ------------
# tkinter cannot animate a relayout or a palette change: a live theme
# flip repaints as a visible cascade of half-themed frames, and a big
# collapse/expand (the Controls toggle, an agent's Settings gear) or a
# window maximize/restore lands as one hard jump. ONE shared mechanism
# hides all of these (owner 2026-07-20, generalizing the theme
# cross-fade — Rule #5): smooth_transition() grabs the window into a
# borderless topmost overlay, FORCES the cover painted, runs the mutate
# callback (the theme flip / the relayout) hidden behind it, then fades
# the overlay's window alpha out. A pure visual nicety — any cover
# failure (ImageGrab unavailable, alpha unsupported, an unmapped
# window) degrades to the plain instant mutate, never a stuck overlay.


def _snapshot_overlay(root: tk.Misc, icon_factory=None) -> tk.Toplevel:
    """Grab the root window's client area (PIL.ImageGrab) and mount it
    in a borderless, topmost, fully-opaque Toplevel placed exactly over
    the window. ``icon_factory(w, h)`` may return a PIL RGBA image (the
    theme flip's big sun/moon) composited centred INTO the snapshot —
    its transparent surroundings blend onto the grab, so the whole
    cover fades as one. The PhotoImage is held on the overlay (tk keeps
    no ref of its own) so it survives the whole fade."""
    x, y = root.winfo_rootx(), root.winfo_rooty()
    w, h = root.winfo_width(), root.winfo_height()
    snap = ImageGrab.grab(bbox=(x, y, x + w, y + h)).convert("RGBA")
    if icon_factory is not None:
        icon = icon_factory(w, h)
        snap.alpha_composite(
            icon, ((w - icon.width) // 2, (h - icon.height) // 2)
        )
    photo = ImageTk.PhotoImage(snap)
    overlay = tk.Toplevel(root)
    overlay.overrideredirect(True)
    overlay.geometry(f"{w}x{h}+{x}+{y}")
    overlay.attributes("-topmost", True)
    overlay.attributes("-alpha", 1.0)
    label = tk.Label(
        overlay, image=photo, borderwidth=0, highlightthickness=0
    )
    label.image = photo          # tk holds no ref — keep it alive here
    label.pack(fill="both", expand=True)
    overlay._snapshot = photo    # belt-and-braces: outlives the whole fade
    overlay.update_idletasks()
    return overlay


def _fade_out_overlay(
    root: tk.Misc, overlay: tk.Toplevel, fade_ms: int, fade_steps: int
) -> None:
    """Ramp the overlay's window alpha 1.0 -> 0.0 across ``fade_steps``
    root.after ticks over ``fade_ms`` (ease-out — the stale snapshot
    clears fast, then eases), then destroy it. A destroyed-mid-fade
    overlay (TclError) ends the ramp cleanly, so no overlay is ever
    left stuck on screen."""
    steps = max(fade_steps, 1)
    interval = max(round(fade_ms / steps), 1)

    def tick(i: int) -> None:
        try:
            frac = i / steps
            if frac >= 1.0:
                overlay.destroy()
                return
            overlay.attributes("-alpha", (1.0 - frac) ** 2)  # ease-out
            root.after(interval, tick, i + 1)
        except tk.TclError:
            try:
                overlay.destroy()
            except tk.TclError:
                pass  # already gone

    tick(1)


def smooth_transition(
    root,
    mutate,
    *,
    icon_factory=None,
    fade_ms: int = TRANSITION_FADE_MS,
    fade_steps: int = TRANSITION_FADE_STEPS,
) -> None:
    """Run ``mutate()`` (a relayout / theme repaint) hidden behind a
    snapshot cover, then fade the cover out — shared by the theme flip,
    the Controls collapse, each agent's Settings gear and the window
    maximize/restore cover.

    The ORDER is what kills the visible jump (owner 2026-07-19): the
    cover is forced fully mapped + painted by the window manager FIRST
    (deiconify → lift → update, so DWM really shows it), only then does
    the mutate run and settle (update_idletasks) behind it, and only
    then does the fade start. With no window on screen — or on ANY
    cover failure — the mutate simply runs instantly with a one-line
    note (root Rule #1): the cover can never be the reason a toggle
    stops working. ``mutate`` itself is NOT guarded — an exception in
    it propagates loudly (never masked), with the overlay still fading
    out via the ``finally`` so nothing sticks."""
    if root is None or not (root.winfo_ismapped() and root.winfo_viewable()):
        mutate()
        return
    overlay = None
    try:
        overlay = _snapshot_overlay(root, icon_factory)
        # FORCE the cover fully mapped + painted BEFORE the mutate, so
        # the relayout/repaint cascade is NEVER seen — only the snapshot.
        overlay.deiconify()
        overlay.lift()
        overlay.update_idletasks()
        overlay.update()            # DWM actually paints the cover now
    except Exception as exc:        # visual nicety — never block the action
        if overlay is not None:
            try:
                overlay.destroy()
            except tk.TclError:
                pass
        print(f"[transition] cover unavailable, mutating instantly: {exc}")
        mutate()
        return
    try:
        mutate()                    # the change, hidden behind the cover
        root.update_idletasks()     # settle the relayout, still hidden
    finally:
        _fade_out_overlay(root, overlay, fade_ms, fade_steps)


def apply_theme(name: str, animate: bool = False) -> None:
    """The ONE coherent theme flip, used by BOTH startup and the toggle.

    Startup passes ``animate=False`` (no window exists yet) for an
    instant flip. The switch passes ``animate=True``: the repaint
    cascade hides behind the shared smooth_transition cover, riding the
    NEXT theme's big sun/moon icon and the theme's own longer
    SWITCH_FADE_* timing (a theme flip is ceremonial; the collapse and
    maximize covers keep the snappier TRANSITION_FADE_* default)."""
    root = tb.Style().master
    if not animate or root is None:
        _apply_theme_now(name)
        return
    smooth_transition(
        root,
        partial(_apply_theme_now, name),
        icon_factory=lambda w, h: _render_theme_cover_icon(name, min(w, h)),
        fade_ms=SWITCH_FADE_MS,
        fade_steps=SWITCH_FADE_STEPS,
    )


def register_painter_day() -> None:
    """Register the custom light theme ONCE (idempotent). No stock light
    theme carries the owner's warm-gold accent, so 'day' is a custom
    ThemeDefinition drawing every ttk widget from the site colours."""
    from ttkbootstrap.style import ThemeDefinition

    style = tb.Style()
    day = THEMES["day"]
    if day["ttkname"] in style.theme_names():
        return
    style.register_theme(
        ThemeDefinition(day["ttkname"], day["ttk"], day["mode"])
    )


def folder_of(drop_path: str) -> str:
    """The POSIX parent directory of a drop path — the L2 folder
    identity shared by the dashboard tree and the Select window
    (e.g. 'assets/archetype/trinity/Jesus.png' -> 'assets/archetype/
    trinity'). A path with no directory collapses to '(root)'."""
    folder = PurePosixPath(drop_path).parent.as_posix()
    return "(root)" if folder in (".", "") else folder


def rels_in_folder(rels, folder: str) -> list[str]:
    """The subset of drop paths whose parent folder is exactly ``folder``
    (by ``folder_of``) — backs the ToolPanel's folder-scoped before/after
    viewer + RESTORE, so double-clicking one folder node touches ONLY that
    folder's images, never the whole job (owner 2026-07-19)."""
    return [rel for rel in rels if folder_of(rel) == folder]


class ScrollFrame(ttk.Frame):
    """A vertically (optionally also horizontally) scrollable frame.

    Add children to ``self.body``. Without horizontal scroll the body
    is stretched to the canvas width (content wraps, no x scrollbar);
    with it the body keeps its natural width and a horizontal bar
    appears.
    """

    def __init__(
        self, master, horizontal: bool = False, fill_height: bool = False
    ):
        super().__init__(master)
        self._stretch = not horizontal
        # fill_height: keep the body AT LEAST as tall as the canvas, so a
        # child packed expand=True (the notebook) fills the whole viewport
        # when the content is shorter than the window (see _apply_fill_height)
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
        like _on_body so a burst of changes triggers one settle."""
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


def style_action_button(
    btn: ctk.CTkButton, kind: str, available: bool
) -> None:
    """Start/Stop availability styling: AVAILABLE = FILLED with its
    colour, UNAVAILABLE = disabled OUTLINE (coloured border, dark
    inside). ``kind`` is a semantic palette key ('success' / 'danger')
    resolved to a (day, night) tuple, so the runtime recolour flips with
    the appearance mode like every other CTk control. Re-applied on
    every run-state change."""
    color = theme_pair(kind)
    if available:
        btn.configure(
            state="normal", fg_color=color, border_width=0,
            hover_color=_darken_pair(color), text_color=status_pair("btn_text"),
        )
    else:
        btn.configure(
            state="disabled", fg_color="transparent", border_width=1,
            border_color=color, text_color=color,
            text_color_disabled=color,
        )


def _style_icon_bar_button(
    btn: ctk.CTkButton, color: tuple[str, str], active: bool
) -> None:
    """IconBar tile colouring (GUI rework Phase 11) — generalizes
    ``style_action_button``'s filled/outline language from a NAMED
    semantic kind to an arbitrary ``(day, night)`` accent pair (a
    ``MENU_TILES``/``JOB_COLORS`` tuple): ACTIVE (one of the tile's
    ``TILE_JOB_KINDS`` has a live job right now) = FILLED with the
    accent; IDLE = a quiet outline in the same accent. UNLIKE
    ``style_action_button``, both states stay ``state="normal"`` — an
    idle tile is exactly what the owner clicks to configure/launch the
    next tool (IconBar itself disables the ONE permanently-disabled
    placeholder tile separately)."""
    if active:
        btn.configure(
            fg_color=color, border_width=0,
            hover_color=_darken_pair(color), text_color=status_pair("btn_text"),
        )
    else:
        btn.configure(
            fg_color="transparent", border_width=1, border_color=color,
            text_color=color, hover_color=theme_pair("dark"),
        )


# the unit suffix shown per kind (a display nicety mirroring the old
# single-filter dialog's trailing "W/H" label) — aspect kinds compare a
# ratio, ANY_SIDE/WIDTH/HEIGHT compare raw pixels
_FILTER_UNIT_LABEL: dict[str, str] = {
    FILTER_KIND_ASPECT_EXACT: "W/H",
    FILTER_KIND_ASPECT_RANGE: "W/H",
    FILTER_KIND_ANY_SIDE: "px",
    FILTER_KIND_WIDTH: "px",
    FILTER_KIND_HEIGHT: "px",
}


def _filter_row_display_bounds(condition: filters.FilterCondition) -> tuple[str, str]:
    """One condition's lo/hi as the STRINGS a row's fields should show.

    "Aspect (exact)" is authored from a single RATIO field (see
    ``_FilterConditionRow.to_condition``, which widens it back out by
    ``FILTER_ASPECT_EXACT_TOL``): displayed here as the MIDPOINT of the
    stored ``[lo, hi]`` band — the inverse operation, so a round-trip
    through set_conditions()/get_conditions() reproduces the same band
    as long as the tolerance constant hasn't changed in between. Aspect
    (range) shows both bounds at ``FILTER_ROW_DECIMALS``; the pixel
    kinds (any side / width / height) show plain integers-if-whole via
    ``:g`` rather than a padded decimal (800, not 800.000)."""
    if condition.kind == FILTER_KIND_ASPECT_EXACT:
        text = f"{(condition.lo + condition.hi) / 2:.{FILTER_ROW_DECIMALS}f}"
        return text, text
    if condition.kind == FILTER_KIND_ASPECT_RANGE:
        return (
            f"{condition.lo:.{FILTER_ROW_DECIMALS}f}",
            f"{condition.hi:.{FILTER_ROW_DECIMALS}f}",
        )
    return f"{condition.lo:g}", f"{condition.hi:g}"


class _FilterConditionRow(ttk.Frame):
    """One stacked row inside a ``FilterEditor``: kind + polarity
    combos, one or two numeric fields, and a remove button — bridges a
    single ``FilterCondition`` to live Tk Vars and back.

    "Aspect (exact)" is special-cased to ONE visible numeric field (a
    target RATIO, not a lo/hi pair): ``to_condition`` widens it into a
    ``[ratio - FILTER_ASPECT_EXACT_TOL, ratio + FILTER_ASPECT_EXACT_TOL]``
    band so a real decoded image actually matches (Phase 3's flagged
    razor-thin-equality caveat — see ``config.FILTER_ASPECT_EXACT_TOL``).
    Every other kind shows both a FROM and a TO field, stored verbatim.
    Switching a row's kind does NOT reinterpret or clear whatever is
    already typed — the field(s) simply show/hide; the owner retypes
    the value for the newly-chosen kind, same as picking a different
    kind was always going to need a different number anyway."""

    def __init__(
        self, parent, condition: filters.FilterCondition,
        on_remove: Callable[["_FilterConditionRow"], None],
    ):
        super().__init__(parent)
        self._on_remove = on_remove
        self.kind_var = tk.StringVar(value=condition.kind)
        self.polarity_var = tk.StringVar(value=condition.polarity)
        lo_text, hi_text = _filter_row_display_bounds(condition)
        self.lo_var = tk.StringVar(value=lo_text)
        self.hi_var = tk.StringVar(value=hi_text)

        rounded_combo(
            self, FILTER_KINDS, self.kind_var, width=FILTER_ROW_KIND_W,
        ).pack(side="left", padx=(0, 6))
        rounded_combo(
            self, (FILTER_POLARITY_IF, FILTER_POLARITY_IF_NOT),
            self.polarity_var, width=FILTER_ROW_POLARITY_W,
        ).pack(side="left", padx=(0, 6))
        self.lo_entry = rounded_entry(
            self, width=FILTER_ROW_ENTRY_W, textvariable=self.lo_var,
            justify="center",
        )
        self.lo_entry.pack(side="left")
        self._dash = ttk.Label(self, text="–")
        self.hi_entry = rounded_entry(
            self, width=FILTER_ROW_ENTRY_W, textvariable=self.hi_var,
            justify="center",
        )
        self._unit = ttk.Label(self, text="")
        rounded_button(
            self, "✕", command=lambda: self._on_remove(self),
            kind="danger-outline", width=INPUT_HEIGHT,
        ).pack(side="right")

        self.kind_var.trace_add("write", lambda *_a: self._sync_layout())
        self._sync_layout()

    def _sync_layout(self) -> None:
        """Show the TO field + unit suffix for every kind except
        "Aspect (exact)" (one ratio field only); re-packed with
        ``after=`` each call so the left-to-right order is correct
        regardless of how many times the kind has flipped back and
        forth."""
        kind = self.kind_var.get()
        exact = kind == FILTER_KIND_ASPECT_EXACT
        self._dash.pack_forget()
        self.hi_entry.pack_forget()
        self._unit.pack_forget()
        last = self.lo_entry
        if not exact:
            self._dash.pack(side="left", padx=4, after=self.lo_entry)
            self.hi_entry.pack(side="left", padx=(0, 6), after=self._dash)
            last = self.hi_entry
        self._unit.configure(text=_FILTER_UNIT_LABEL.get(kind, ""))
        self._unit.pack(side="left", padx=(4, 0), after=last)

    def to_condition(self) -> filters.FilterCondition:
        """This row's live edit -> a ``FilterCondition``. Raises
        ``ValueError`` (naming the offending kind) on an unparsable or
        inverted bound — the caller (``FilterEditor.get_conditions``)
        lets this propagate; ITS caller decides how to surface it."""
        kind = self.kind_var.get()
        polarity = self.polarity_var.get()
        try:
            lo_raw = float(self.lo_var.get().strip())
        except ValueError:
            raise ValueError(
                f"{kind}: the value must be a number."
            ) from None
        if kind == FILTER_KIND_ASPECT_EXACT:
            return filters.FilterCondition(
                kind=kind, polarity=polarity,
                lo=lo_raw - FILTER_ASPECT_EXACT_TOL,
                hi=lo_raw + FILTER_ASPECT_EXACT_TOL,
            )
        try:
            hi_raw = float(self.hi_var.get().strip())
        except ValueError:
            raise ValueError(
                f"{kind}: the TO value must be a number."
            ) from None
        if lo_raw > hi_raw:
            raise ValueError(f"{kind}: FROM must be <= TO.")
        return filters.FilterCondition(
            kind=kind, polarity=polarity, lo=lo_raw, hi=hi_raw,
        )


class FilterEditor(ttk.Frame):
    """Reusable stacked-filter editor (GUI rework Phase 4) — the UI
    half of [Shared Filter Framework](painter/filters.md): zero or
    more removable condition rows, an "+ Add condition" button, and a
    PRESET row (save / load / delete a NAMED condition stack). Stacked
    conditions AND together (``painter.filters.matches``, owner
    decision 2026-07-21) — an empty stack matches everything.

    Public API: ``get_conditions() -> list[FilterCondition]`` (raises
    ``ValueError`` — see ``_FilterConditionRow.to_condition`` — on an
    unparsable row; never returns a partial/best-effort list) and
    ``set_conditions(conditions)`` (rebuilds the row stack from
    scratch).

    Presets are a SHARED library (one settings.json key, every
    FilterEditor instance reads/writes the same names) — optional
    dependency injection, not a hard requirement: pass the owner's
    live ``presets`` dict (mutated IN PLACE by Save/Delete — the
    caller's own reference sees the change immediately) and an
    ``on_presets_changed`` callback to persist through it (e.g.
    ``PainterGui._schedule_save``, mirroring every other "remembered
    choice" setter). Omitted, the widget still works standalone (a
    private in-memory dict for the widget's own lifetime) — this is
    what makes a headless construction in a test possible with no
    PainterGui or settings.json involved at all."""

    def __init__(
        self,
        parent,
        conditions: list[filters.FilterCondition] | None = None,
        presets: dict[str, list[dict]] | None = None,
        on_presets_changed: Callable[[], None] | None = None,
        **kwargs,
    ):
        super().__init__(parent, **kwargs)
        self._presets = presets if presets is not None else {}
        self._on_presets_changed = on_presets_changed
        self._rows: list[_FilterConditionRow] = []

        self._rows_box = ttk.Frame(self)
        self._rows_box.pack(fill="x")

        add_row = ttk.Frame(self)
        add_row.pack(fill="x", pady=(FILTER_ROW_GAP_PX, 0))
        rounded_button(
            add_row, "+ Add condition", command=self._add_default_row,
            icon_name="add", kind="secondary-outline",
        ).pack(side="left")

        preset_row = ttk.Frame(self)
        preset_row.pack(fill="x", pady=(FILTER_ROW_GAP_PX, 0))
        ttk.Label(preset_row, text="Preset").pack(side="left", padx=(0, 6))
        self._preset_var = tk.StringVar(value="")
        self._preset_combo = rounded_combo(
            preset_row, sorted(self._presets), self._preset_var,
            width=FILTER_PRESET_COMBO_W, state="normal",
        )
        self._preset_combo.pack(side="left", padx=(0, 6))
        rounded_button(
            preset_row, "Save", command=self._save_preset, kind="success",
        ).pack(side="left", padx=(0, 4))
        rounded_button(
            preset_row, "Load", command=self._load_preset, kind="info",
        ).pack(side="left", padx=(0, 4))
        rounded_button(
            preset_row, "Delete", command=self._delete_preset,
            kind="danger-outline",
        ).pack(side="left")

        for c in (conditions or []):
            self._add_row(c)

    # --- rows ------------------------------------------------------

    def _add_default_row(self) -> None:
        """The "+ Add condition" button's command — a fresh row seeded
        with the ~square aspect-range band, the same default the OLD
        single-filter dialog pre-filled (owner 2026-07-19)."""
        self._add_row(filters.FilterCondition(
            kind=FILTER_KIND_ASPECT_RANGE, polarity=FILTER_POLARITY_IF,
            lo=ASPECT_FILTER_DEFAULT_FROM, hi=ASPECT_FILTER_DEFAULT_TO,
        ))

    def _add_row(self, condition: filters.FilterCondition) -> None:
        row = _FilterConditionRow(self._rows_box, condition, self._remove_row)
        row.pack(fill="x", pady=(0, FILTER_ROW_GAP_PX))
        self._rows.append(row)

    def _remove_row(self, row: _FilterConditionRow) -> None:
        self._rows.remove(row)
        row.destroy()

    # --- public API ------------------------------------------------

    def get_conditions(self) -> list[filters.FilterCondition]:
        return [row.to_condition() for row in self._rows]

    def set_conditions(self, conditions: list[filters.FilterCondition]) -> None:
        for row in self._rows:
            row.destroy()
        self._rows.clear()
        for c in conditions:
            self._add_row(c)

    # --- presets -----------------------------------------------------

    def _save_preset(self) -> None:
        name = self._preset_var.get().strip()
        if not name:
            messagebox.showerror(
                "PromptPainter", "Enter a preset name first.", parent=self,
            )
            return
        try:
            conditions = self.get_conditions()
        except ValueError as exc:
            messagebox.showerror("PromptPainter", str(exc), parent=self)
            return
        self._presets[name] = [
            filters.condition_to_dict(c) for c in conditions
        ]
        self._refresh_preset_values()
        if self._on_presets_changed is not None:
            self._on_presets_changed()

    def _load_preset(self) -> None:
        name = self._preset_var.get().strip()
        if name not in self._presets:
            messagebox.showerror(
                "PromptPainter", f"No saved preset named {name!r}.",
                parent=self,
            )
            return
        self.set_conditions([
            filters.condition_from_dict(d) for d in self._presets[name]
        ])

    def _delete_preset(self) -> None:
        name = self._preset_var.get().strip()
        if name not in self._presets:
            messagebox.showerror(
                "PromptPainter", f"No saved preset named {name!r}.",
                parent=self,
            )
            return
        del self._presets[name]
        self._preset_var.set("")
        self._refresh_preset_values()
        if self._on_presets_changed is not None:
            self._on_presets_changed()

    def _refresh_preset_values(self) -> None:
        self._preset_combo.configure(values=sorted(self._presets))


class AgentPanel(ttk.Labelframe):
    """One site's OWN control panel (full per-agent separation).

    Each site gets its own background dropdown, the three composable
    post-save switches (BG removal / Crop / Upscale), Report, Safer
    retry, New-chat mode, pause and action-delay ranges, and its own
    Start/Stop pair — only the Collections queue and the Output folder
    stay SHARED (and Select-images was per-site already). A site
    "participates" in a run by being Started; one site running never
    blocks starting the other."""

    # the keys persisted per agent in the settings file
    _PERSIST = (
        "background", "style", "bg_removal", "crop", "upscale", "report",
        "safer_retry", "continue_nudge", "checker", "new_chat", "pause_min",
        "pause_max", "act_min", "act_max",
        # per-agent upscale-gate fine-tune (owner 2026-07-19; GUI rework
        # Phase 6: the old up_minw/up_minh/up_aspmin/up_aspmax four-field
        # gate collapsed into ONE min-side spinner — the embedded
        # FilterEditor's condition stack persists SEPARATELY, as
        # 'up_filter_conditions' (not a plain tk.Variable, so it is
        # handled explicitly in get_settings/apply_settings below, not
        # through this tuple)
        "up_minside",
        # this agent's own Settings-gear collapse state (owner 2026-07-19)
        "settings_collapsed",
        # the Force Aspect Ratio pipeline step (GUI rework Phase 8) — OFF
        # by default; W/H are the target ratio the AspectRatioCanvas
        # edits. "keep_all_steps" is the per-agent "keep every pipeline
        # step" disk-usage toggle (JOBTEMP_KEEP_ALL_STEPS_DEFAULT).
        "force_aspect", "force_aspect_w", "force_aspect_h", "keep_all_steps",
        # this site's show/hide toggle (GUI rework Phase 12, spec item
        # 3A) — default True (both panels visible, today's behaviour);
        # see visible_var's own docstring for the "never hide a live
        # job's only control surface" guarantee.
        "visible",
    )

    def __init__(
        self, master, site_key: str, on_start, on_stop, on_pause,
        filter_presets: dict[str, list[dict]] | None = None,
        on_filter_presets_changed: Callable[[], None] | None = None,
        on_log: Callable[[str], None] | None = None,
    ):
        super().__init__(master)
        self.site_key = site_key
        self._on_start = on_start
        self._on_stop = on_stop
        self._on_pause = on_pause
        # optional so a headless AgentPanel (no PainterGui — every
        # gui_*.py test's own make_panel()) still works, same pattern as
        # on_filter_presets_changed below
        self._on_log = on_log or (lambda _msg: None)
        # the SHARED filter-preset library (GUI rework Phase 6) — the
        # same dict/callback PainterGui hands every FilterEditor
        # instance (see filters.py's module docstring: one preset
        # library, every FilterEditor reads/writes the same names).
        # Optional so a headless AgentPanel (no PainterGui) still works,
        # falling back to FilterEditor's own private in-memory dict.
        self._filter_presets = filter_presets
        self._on_filter_presets_changed = on_filter_presets_changed
        site = SITES[site_key]

        # the labelframe title: the site's logo + name
        head = ttk.Frame(self)
        ctk.CTkLabel(
            head, text="", image=icon(JOB_LOGO[site_key]), width=22,
            fg_color="transparent", bg_color=theme_pair("bg"),
        ).pack(side="left", padx=(0, 4))
        ttk.Label(head, text=site.name, style="Head.TLabel").pack(side="left")
        self.configure(labelwidget=head, padding=6)

        self.background_var = tk.StringVar(value=site.default_background)
        # the rendering STYLE clause appended at the END of this site's
        # prompt suffix (owner 2026-07-19); "None" = nothing appended
        self.style_var = tk.StringVar(value=STYLE_DEFAULT)
        self.bg_removal_var = tk.BooleanVar(value=True)
        self.crop_var = tk.BooleanVar(value=True)
        self.upscale_var = tk.BooleanVar(value=True)
        self.report_var = tk.BooleanVar(value=True)
        self.safer_var = tk.BooleanVar(value=True)
        # one-shot "continue" nudge when ChatGPT stalls on an image
        # (NoImage: done edge fired, empty answer, no marker) — owner
        # 2026-07-20; ON by default so the stuck case self-heals
        self.continue_nudge_var = tk.BooleanVar(value=True)
        # the parallel per-item Checker AI (GUI rework Phase 16, owner's
        # UV/prompt.txt item 1: "dok generise sledecu sliku paralelno
        # ona koja je generisana cek jer provjeri"): OFF by default — it
        # spends a paced Gemini vision call PER SAVED IMAGE, so it is an
        # explicit opt-in cost, not a free default like Safer
        # retry/Continue nudge beside it. See PainterGui.
        # _maybe_spawn_checker for the spawn side.
        self.checker_var = tk.BooleanVar(value=False)
        self.new_chat_var = tk.StringVar(value="collection")
        self.pause_min_var = tk.StringVar(value=f"{TIMING.pause_min_s:.0f}")
        self.pause_max_var = tk.StringVar(value=f"{TIMING.pause_max_s:.0f}")
        self.act_min_var = tk.StringVar(
            value=f"{TIMING.action_delay_min_s:.1f}"
        )
        self.act_max_var = tk.StringVar(
            value=f"{TIMING.action_delay_max_s:.1f}"
        )
        # per-agent upscale-gate fine-tune (owner 2026-07-19; GUI rework
        # Phase 6: ONE min-SIDE spinner — the shipped default reproduces
        # the old locked rule (800px) — plus an embedded FilterEditor
        # (built in _build_finetune, seeded with today's aspect gate as
        # a single Aspect (range) condition) deciding WHICH images
        # qualify. Shown only when the Settings collapse is expanded.
        self.up_minside_var = tk.StringVar(value=str(UPSCALE_MIN_SIDE_DEFAULT))
        # the upscale FilterEditor's SEED conditions — built once here so
        # _build_finetune (called at the end of __init__) and a future
        # re-seed both read the SAME default; not itself persisted (the
        # widget's live get_conditions() is what get_settings() reads).
        self._default_upscale_conditions = [
            filters.FilterCondition(
                kind=FILTER_KIND_ASPECT_RANGE, polarity=FILTER_POLARITY_IF,
                lo=UPSCALE_ASPECT_MIN, hi=UPSCALE_ASPECT_MAX,
            )
        ]
        # this agent's OWN Settings-gear collapse state (owner 2026-07-19):
        # True = fine-tune hidden (default). A BooleanVar so it persists and
        # auto-saves through the same per-agent trace as every other field.
        self.settings_collapsed_var = tk.BooleanVar(value=True)

        # this site's SHOW/HIDE toggle (GUI rework Phase 12, spec item 3A:
        # "moze da se prikaze/sakrije bilo koji ... da ostane samo jedan
        # vidljiv" — either site's panel can be hidden so only the other
        # stays visible). True = shown (default, today's behaviour). The
        # toggle widget itself lives ABOVE both panels (PainterGui.
        # _build_options's "Show:" row, via build_visibility_toggle below)
        # — never INSIDE this panel, or hiding it would hide its own only
        # way back. set_run_state is the single choke point that (a)
        # greys _visible_btn out while this site's job is running or a
        # quota auto-restart is pending (Stop/Pause live only on THIS
        # panel, so hiding it then would strand the job with no control
        # surface) and (b) forces this back to True — logging why — if a
        # HIDDEN site's job goes live without a click (a quota
        # auto-restart, an AI-check resend: both call PainterGui.
        # _start_site directly, bypassing btn_start).
        self.visible_var = tk.BooleanVar(value=True)
        # set once PainterGui builds this site's entry in the "Show:" row
        # (build_visibility_toggle, after __init__ returns) — None until
        # then, exactly like _button_pairs' second (compact) entry is
        # absent until build_compact runs; set_run_state tolerates either.
        self._visible_btn: ctk.CTkSwitch | None = None

        # the Force Aspect Ratio pipeline step (GUI rework Phase 8) — OFF
        # by default (a deliberate DEFORM, not everyone's images need
        # one); W/H are the target ratio, mirrored two-way with the
        # embedded AspectRatioCanvas (built in _build_finetune, reusing
        # Phase 5's editor) exactly like AspectRatioDialog's own W/H
        # entries + canvas.
        self.force_aspect_var = tk.BooleanVar(value=False)
        self.force_aspect_w_var = tk.StringVar(value=str(ASPECT_DEFAULT_W))
        self.force_aspect_h_var = tk.StringVar(value=str(ASPECT_DEFAULT_H))
        # per-agent "keep every pipeline step" disk-usage toggle (owner
        # decision 2026-07-21, GUI rework Phase 8) — ON keeps a
        # restorable backup for EVERY enabled post-save step (BG/Crop/
        # Aspect/Upscale), not just the pristine "original" baseline;
        # OFF (or the job's JobTemp going over JOBTEMP_MAX_BYTES) falls
        # back to original-only. See gui._run_pipeline_steps.
        self.keep_all_steps_var = tk.BooleanVar(
            value=JOBTEMP_KEEP_ALL_STEPS_DEFAULT
        )

        row = ttk.Frame(self)
        row.pack(fill="x", pady=2)
        ttk.Label(row, text="Background:").pack(side="left")
        rounded_combo(
            row, BACKGROUND_CHOICES, self.background_var, width=105,
        ).pack(side="left", padx=(2, 10))
        ttk.Label(row, text="New chat:").pack(side="left")
        rounded_combo(
            row, NEW_CHAT_CHOICES, self.new_chat_var, width=100,
        ).pack(side="left", padx=(2, 0))

        # the Style dropdown — a primary per-generation choice like
        # Background, so it lives in the ALWAYS-VISIBLE area, not under the
        # Settings gear (owner 2026-07-19)
        row = ttk.Frame(self)
        row.pack(fill="x", pady=2)
        ttk.Label(row, text="Style:").pack(side="left")
        rounded_combo(
            row, STYLE_CHOICES, self.style_var, width=150,
        ).pack(side="left", padx=(2, 0))

        row = ttk.Frame(self)
        row.pack(fill="x", pady=2)
        rounded_switch(row, "BG removal", self.bg_removal_var).pack(
            side="left"
        )
        rounded_switch(row, "Crop", self.crop_var).pack(side="left", padx=8)
        rounded_switch(row, "Upscale", self.upscale_var).pack(side="left")

        row = ttk.Frame(self)
        row.pack(fill="x", pady=2)
        rounded_switch(row, "Report txt", self.report_var).pack(side="left")
        rounded_switch(row, "Safer retry", self.safer_var).pack(
            side="left", padx=8
        )
        rounded_switch(row, "Continue nudge", self.continue_nudge_var).pack(
            side="left"
        )
        # the parallel Checker AI (GUI rework Phase 16) sits right beside
        # Safer retry/Continue nudge — the owner's other "watch this run
        # and self-correct" switches — even though it works differently
        # (checks the SAVED image on a background thread instead of
        # reacting to a refusal/stall; see PainterGui._maybe_spawn_checker)
        rounded_switch(row, "AI checker", self.checker_var).pack(
            side="left", padx=8
        )

        row = ttk.Frame(self)
        row.pack(fill="x", pady=(6, 2))
        self.btn_start = rounded_button(
            row, "Start", command=partial(on_start, site_key),
            kind="success", icon_name="start", width=90,
        )
        self.btn_start.pack(side="left")
        # the pause toggle (owner 2026-07-21) — a plain neutral button
        # (no filled/outline availability dance like Start/Stop below):
        # its label alone flips Pause <-> Resume, always clickable.
        self.btn_pause = rounded_button(
            row, "Pause", command=partial(on_pause, site_key),
            kind="secondary", width=70,
        )
        self.btn_pause.pack(side="left", padx=6)
        self.btn_stop = rounded_button(
            row, "Stop", command=partial(on_stop, site_key),
            kind="danger-outline", width=70,
        )
        self.btn_stop.pack(side="left", padx=6)
        # this agent's OWN Settings gear (owner 2026-07-19): the gear icon
        # + a state caret; it shows/hides THIS panel's fine-tune (pause +
        # action delay + upscale gate) independently of the other site.
        self._settings_btn = rounded_button(
            row, SETTINGS_GLYPH_COLLAPSED, command=self._toggle_settings,
            icon_name="settings",
        )
        self._settings_btn.pack(side="right")
        # every Start/Stop pair this agent owns (the panel's own pair plus
        # the collapsed-strip pair added by build_compact); set_run_state
        # styles ALL of them so both views always agree on availability
        self._button_pairs = [(self.btn_start, self.btn_stop)]
        self.set_run_state(running=False)

        # the collapsible fine-tune block (pause + action delay + upscale
        # gate) — built last so it sits at the panel's bottom; hidden until
        # this agent's own Settings gear expands it
        self._build_finetune()
        self._apply_finetune_visibility()

        # this panel's embedded AspectRatioCanvas needs redraw_theme() on
        # every live Day/Night flip (GUI rework Phase 8 — see apply_theme's
        # own docstring for why AgentPanel registers here despite not
        # being a Toplevel); never unregistered — build-once, same
        # lifetime as the app itself, like every dashboard JobPanel.
        THEME_TOPLEVELS.append(self)
        self.bind("<Destroy>", self._on_destroy)

    def _build_finetune(self) -> None:
        """This agent's collapsible FINE-TUNE area (owner 2026-07-19),
        hidden behind its Settings gear: the PAUSE range, the ACTION-DELAY
        range, and the UPSCALE GATE. Built into ``self._finetune_box`` and
        left UNPACKED — ``_apply_finetune_visibility`` packs it in when
        the gear expands.

        The upscale gate (GUI rework Phase 6) is ONE min-SIDE spinner —
        the smaller side's target minimum in px, replacing the old
        separate min-W/min-H fields — plus an embedded ``FilterEditor``
        deciding WHICH images qualify, pre-seeded with today's aspect
        gate as a single Aspect (range) condition. ``upscale_params()``
        resolves the two into ``upscale_if_small``'s kwargs."""
        box = ttk.Frame(self)
        self._finetune_box = box

        row = ttk.Frame(box)
        row.pack(fill="x", pady=2)
        ttk.Label(row, text="pause", width=12).pack(side="left")
        Spinner(row, self.pause_min_var, step=1.0).pack(side="left")
        ttk.Label(row, text="–").pack(side="left", padx=2)
        Spinner(row, self.pause_max_var, step=1.0).pack(side="left")
        ttk.Label(row, text="s").pack(side="left", padx=(2, 0))

        row = ttk.Frame(box)
        row.pack(fill="x", pady=2)
        ttk.Label(row, text="action delay", width=12).pack(side="left")
        Spinner(row, self.act_min_var, step=0.1).pack(side="left")
        ttk.Label(row, text="–").pack(side="left", padx=2)
        Spinner(row, self.act_max_var, step=0.1).pack(side="left")
        ttk.Label(row, text="s").pack(side="left", padx=(2, 0))

        # the Force Aspect Ratio pipeline step (GUI rework Phase 8) — a
        # deliberate DEFORM to an exact target ratio, run AFTER Crop and
        # BEFORE Upscale (PainterGui._compose_post_save's new order:
        # BG -> Crop -> Aspect -> Upscale). Default OFF. The target W/H
        # is edited two-way with the SAME AspectRatioCanvas the
        # standalone 'Aspect ratio…' tool's dialog uses (Phase 5) — the
        # entries drive the canvas, dragging an edge drives them back.
        ttk.Label(
            box, text="Force Aspect Ratio (this site):", style="Head.TLabel"
        ).pack(anchor="w", pady=(4, 0))
        row = ttk.Frame(box)
        row.pack(fill="x", pady=2)
        rounded_switch(row, "Force to ratio", self.force_aspect_var).pack(
            side="left"
        )

        fa_fields = ttk.Frame(box)
        fa_fields.pack(fill="x", pady=2)
        ttk.Label(fa_fields, text="W").pack(side="left", padx=(0, 4))
        self._force_aspect_w_entry = rounded_entry(
            fa_fields, width=ASPECT_DIALOG_ENTRY_W,
            textvariable=self.force_aspect_w_var, justify="center",
        )
        self._force_aspect_w_entry.pack(side="left")
        ttk.Label(fa_fields, text=":", font=tk_font("head")).pack(
            side="left", padx=8
        )
        ttk.Label(fa_fields, text="H").pack(side="left", padx=(0, 4))
        self._force_aspect_h_entry = rounded_entry(
            fa_fields, width=ASPECT_DIALOG_ENTRY_W,
            textvariable=self.force_aspect_h_var, justify="center",
        )
        self._force_aspect_h_entry.pack(side="left")

        # its own row below the W/H fields (not beside them, like the
        # standalone dialog can afford) — this panel's column is
        # narrower than a free-standing modal
        canvas_row = ttk.Frame(box)
        canvas_row.pack(fill="x", pady=(2, 0))
        self._force_aspect_canvas = AspectRatioCanvas(
            canvas_row,
            w=int(self.force_aspect_w_var.get()),
            h=int(self.force_aspect_h_var.get()),
            on_change=self._on_force_aspect_canvas_drag,
        )
        self._force_aspect_canvas.pack(anchor="w")
        self.force_aspect_w_var.trace_add(
            "write", self._on_force_aspect_wh_typed
        )
        self.force_aspect_h_var.trace_add(
            "write", self._on_force_aspect_wh_typed
        )

        # per-agent disk-usage choice for the pipeline's per-step backups
        # (GUI rework Phase 8) — see gui._run_pipeline_steps.
        row = ttk.Frame(box)
        row.pack(fill="x", pady=(6, 2))
        rounded_switch(
            row, "Keep every pipeline step (uses more disk)",
            self.keep_all_steps_var,
        ).pack(side="left")

        # the whole Upscale-gate sub-block (GUI rework Phase 12): makes
        # sense ONLY while the Upscale switch itself is on, so it lives
        # in its OWN sub-frame, packed/unpacked by
        # _apply_upscale_gate_visibility — independently of
        # settings_collapsed_var (this sub-frame is a CHILD of ``box``;
        # hiding/showing ``box`` itself never touches a child's own
        # pack state, so the two toggles compose like a plain AND: only
        # visible when BOTH the Settings gear is expanded AND Upscale
        # is on).
        self._upscale_gate_box = ttk.Frame(box)

        ttk.Label(
            self._upscale_gate_box, text="Upscale gate (this site):",
            style="Head.TLabel",
        ).pack(anchor="w", pady=(4, 0))

        row = ttk.Frame(self._upscale_gate_box)
        row.pack(fill="x", pady=2)
        ttk.Label(row, text="min side", width=8).pack(side="left")
        Spinner(row, self.up_minside_var, step=UPSCALE_MINDIM_STEP).pack(
            side="left"
        )
        ttk.Label(
            row, text="px (the smaller side reaches this)"
        ).pack(side="left", padx=(4, 0))

        # WHICH images qualify — a stacked FilterEditor (Phase 4) sharing
        # the app-wide preset library, seeded with today's aspect gate
        self.upscale_filter = FilterEditor(
            self._upscale_gate_box,
            conditions=self._default_upscale_conditions,
            presets=self._filter_presets,
            on_presets_changed=self._on_filter_presets_changed,
        )
        self.upscale_filter.pack(fill="x", pady=(2, 0))

        # live show/hide as Upscale itself is flipped — even while the
        # Settings gear stays expanded (GUI rework Phase 12); also
        # covers a settings-restore .set() (apply_settings, via _vars())
        # since a trace fires on every write, not only interactive ones
        self.upscale_var.trace_add(
            "write", lambda *_a: self._apply_upscale_gate_visibility()
        )
        self._apply_upscale_gate_visibility()  # correct initial state

    def _apply_upscale_gate_visibility(self) -> None:
        """Reflect ``upscale_var`` onto the Upscale-gate sub-block (GUI
        rework Phase 12): the min-side spinner + its FilterEditor are
        meaningless once Upscale itself is off, so they disappear even
        if the Settings gear stays expanded. Plain pack/pack_forget, no
        smooth_transition — unlike _toggle_settings's own deliberate
        owner-click animation, this fires from a trace on EVERY write
        (an interactive click through the switch AND a silent settings
        restore alike), so it stays as unobtrusive as
        _apply_finetune_visibility's own plain reflect."""
        if self.upscale_var.get():
            self._upscale_gate_box.pack(fill="x")
        else:
            self._upscale_gate_box.pack_forget()

    def _apply_finetune_visibility(self) -> None:
        """Reflect ``settings_collapsed_var``: pack or unpack this agent's
        fine-tune block and set the gear's state caret. The nested body's
        size change lets the outer ScrollFrame recompute its region."""
        collapsed = self.settings_collapsed_var.get()
        if collapsed:
            self._finetune_box.pack_forget()
        else:
            self._finetune_box.pack(fill="x", pady=(2, 0))
        self._settings_btn.configure(
            text=SETTINGS_GLYPH_COLLAPSED if collapsed
            else SETTINGS_GLYPH_EXPANDED
        )

    def _toggle_settings(self) -> None:
        """The gear: flip THIS agent's fine-tune visibility, independently
        of the other site, behind the shared snapshot cover (the reveal
        moves everything below the panel — bare, it lands as one hard
        jump). The var change persists via its own trace."""
        self.settings_collapsed_var.set(
            not self.settings_collapsed_var.get()
        )
        smooth_transition(
            self.winfo_toplevel(), self._apply_finetune_visibility
        )

    def _on_force_aspect_canvas_drag(self, w: int, h: int) -> None:
        """``AspectRatioCanvas.on_change`` — a drag mirrored into the W/H
        entries (whose own trace calls back into ``set_ratio``, a no-op
        echo — see that method's docstring). Same pattern as
        ``AspectRatioDialog._on_canvas_drag``."""
        self.force_aspect_w_var.set(str(w))
        self.force_aspect_h_var.set(str(h))

    def _on_force_aspect_wh_typed(self, *_args) -> None:
        """Live-reshape the canvas as the owner types a new W/H. A bad
        or incomplete value (mid-edit) is a normal typing state, not an
        error — silently skipped, same as
        ``AspectRatioDialog._on_wh_typed``; final validation happens in
        ``force_aspect_ratio()`` on Start."""
        try:
            w = int(self.force_aspect_w_var.get().strip())
            h = int(self.force_aspect_h_var.get().strip())
        except ValueError:
            return
        if w <= 0 or h <= 0:
            return
        self._force_aspect_canvas.set_ratio(w, h)

    def force_aspect_ratio(self) -> tuple[int, int]:
        """The Force-Aspect target ratio — ValueError propagates to the
        caller's Start validation, same contract as ``upscale_params()``
        / ``pace_floats()``."""
        return (
            int(self.force_aspect_w_var.get()),
            int(self.force_aspect_h_var.get()),
        )

    def apply_theme(self) -> None:
        """Registered in ``THEME_TOPLEVELS`` (GUI rework Phase 8) even
        though this panel is not a Toplevel — that list is really just
        "objects with their own apply_theme() a flip must reach", and
        AgentPanel is BUILD-ONCE / never destroyed before app exit, same
        lifetime as every dashboard JobPanel. Needed because
        ``AspectRatioCanvas`` draws its accent/label straight from the
        active theme (see its own docstring) — this host is a normal,
        non-modal part of the main window (like its sibling host,
        ``AspectSettingsPanel``, GUI rework Phase 14), so a Day/Night
        flip while the fine-tune box is expanded must repaint it too."""
        self._force_aspect_canvas.redraw_theme()

    def _on_destroy(self, event) -> None:
        if event.widget is self and self in THEME_TOPLEVELS:
            THEME_TOPLEVELS.remove(self)

    def upscale_params(self) -> dict:
        """The upscale gate's engine kwargs (GUI rework Phase 6):
        ``_upscale_params_from_side_and_filter`` over the min-side
        spinner + the embedded FilterEditor's aspect condition.
        ValueError propagates to the caller's Start validation — from
        EITHER the spinner (not a number) or the FilterEditor (an
        unparsable row, see ``FilterEditor.get_conditions``). Non-aspect
        conditions in the same filter are NOT reflected in this dict —
        see ``upscale_conditions()`` and ``_gate_and_upscale``."""
        min_side = int(float(self.up_minside_var.get()))
        return _upscale_params_from_side_and_filter(
            min_side, self.upscale_filter.get_conditions()
        )

    def upscale_conditions(self) -> list[filters.FilterCondition]:
        """The upscale gate's FULL stacked filter, exactly as currently
        edited (root Rule #1: the caller uses this — not just
        ``upscale_params()``'s narrower kwargs — to honor stacked non-
        aspect conditions via ``filters.matches()``, see
        ``_gate_and_upscale``). ValueError propagates like
        ``upscale_params()``."""
        return self.upscale_filter.get_conditions()

    def set_run_state(
        self, running: bool, pending_restart: bool = False
    ) -> None:
        """Start is available unless the site runs; Stop is available
        while it runs OR while a quota auto-restart is pending (Stop
        then cancels the pending restart). Styles every registered
        button pair (full panel + collapsed strip).

        GUI rework Phase 12: the SAME "running or pending_restart"
        window also (a) greys out the show/hide toggle — this panel is
        the only place Stop/Pause live for this site, so hiding it
        while either is needed would strand the job — and (b), since a
        HIDDEN panel's site can still go live without a click (a quota
        auto-restart, an AI-check resend both call PainterGui.
        _start_site directly), forces visible_var back to True and logs
        why whenever that happens, so the control and what is on screen
        never silently disagree."""
        for start_btn, stop_btn in self._button_pairs:
            style_action_button(start_btn, "success", not running)
            style_action_button(
                stop_btn, "danger", running or pending_restart
            )
        locked = running or pending_restart
        if locked and not self.visible_var.get():
            self._on_log(
                f"{SITES[self.site_key].name}: un-hiding its panel — a"
                " live job needs its Start/Stop/Pause controls"
            )
            self.visible_var.set(True)
        if self._visible_btn is not None:
            self._visible_btn.configure(
                state="disabled" if locked else "normal"
            )

    def set_paused(self, is_paused: bool) -> None:
        """Reflect this agent's pause toggle onto its OWN btn_pause
        label (owner 2026-07-21) — the paused STATE text lives on the
        dashboard DashPanel's state line instead (JobPanel.set_paused,
        reached through PainterGui.panels[site_key]; this panel has no
        state line of its own)."""
        self.btn_pause.configure(text="Resume" if is_paused else "Pause")

    def build_compact(self, parent) -> ttk.Frame:
        """A thin '[logo] Name [Start][Stop]' cluster for the collapsed
        view. Its Start/Stop reuse the panel's own commands and join
        _button_pairs so set_run_state keeps them in the same
        filled/outline availability as the full panel's pair."""
        cluster = ttk.Frame(parent)
        ctk.CTkLabel(
            cluster, text="", image=icon(JOB_LOGO[self.site_key]),
            width=22, fg_color="transparent", bg_color=theme_pair("bg"),
        ).pack(side="left", padx=(0, 4))
        ttk.Label(
            cluster, text=SITES[self.site_key].name, style="Head.TLabel"
        ).pack(side="left", padx=(0, 8))
        start = rounded_button(
            cluster, "Start",
            command=partial(self._on_start, self.site_key),
            kind="success", icon_name="start", width=90,
        )
        start.pack(side="left")
        stop = rounded_button(
            cluster, "Stop",
            command=partial(self._on_stop, self.site_key),
            kind="danger-outline", width=70,
        )
        stop.pack(side="left", padx=6)
        self._button_pairs.append((start, stop))
        return cluster

    def build_visibility_toggle(self, parent) -> ctk.CTkSwitch:
        """This site's entry in the shared "Show:" row above both
        AgentPanels (GUI rework Phase 12, spec item 3A) — a plain switch
        bound to ``visible_var`` so the row and the panel can never
        silently disagree (Tk's ``variable=`` binding keeps them in
        lockstep both ways: a click here flips the var, a programmatic
        ``.set()`` — settings restore, or set_run_state's own forced
        re-show — updates the switch). Kept as ``self._visible_btn`` so
        ``set_run_state`` can grey it out while this site's job needs
        its own panel reachable."""
        self._visible_btn = rounded_switch(
            parent, SITES[self.site_key].name, self.visible_var,
        )
        return self._visible_btn

    def pace_floats(self) -> tuple[float, float, float, float]:
        """The four pace numbers — ValueError propagates to the
        caller's validation message."""
        return (
            float(self.pause_min_var.get()),
            float(self.pause_max_var.get()),
            float(self.act_min_var.get()),
            float(self.act_max_var.get()),
        )

    # --- settings round-trip -------------------------------------------

    def _vars(self) -> dict[str, tk.Variable]:
        return {
            "background": self.background_var,
            "style": self.style_var,
            "bg_removal": self.bg_removal_var,
            "crop": self.crop_var,
            "upscale": self.upscale_var,
            "report": self.report_var,
            "safer_retry": self.safer_var,
            "continue_nudge": self.continue_nudge_var,
            "checker": self.checker_var,
            "new_chat": self.new_chat_var,
            "pause_min": self.pause_min_var,
            "pause_max": self.pause_max_var,
            "act_min": self.act_min_var,
            "act_max": self.act_max_var,
            "up_minside": self.up_minside_var,
            "settings_collapsed": self.settings_collapsed_var,
            "force_aspect": self.force_aspect_var,
            "force_aspect_w": self.force_aspect_w_var,
            "force_aspect_h": self.force_aspect_h_var,
            "keep_all_steps": self.keep_all_steps_var,
            "visible": self.visible_var,
        }

    def persist_vars(self) -> list[tk.Variable]:
        """Every tk.Variable this panel auto-saves on write (see
        ``PainterGui._wire_persistence``). The upscale FilterEditor's
        condition stack is NOT a tk.Variable — it has no per-keystroke
        trace — so an edit there alone waits for the NEXT debounced
        save (triggered by any other field) or the app's close-time
        save (``PainterGui._on_close`` always calls ``_save_now()``,
        which reads ``get_settings()`` fresh); it is never silently
        lost, just not INSTANTLY scheduled like the fields below."""
        return list(self._vars().values())

    def get_settings(self) -> dict:
        data = {key: var.get() for key, var in self._vars().items()}
        # the upscale gate's FilterEditor (GUI rework Phase 6) — read
        # fresh every call, same as every other "live widget state"
        # persisted field; see persist_vars()'s docstring for why this
        # one has no per-keystroke save trace
        data["up_filter_conditions"] = [
            filters.condition_to_dict(c)
            for c in self.upscale_filter.get_conditions()
        ]
        return data

    def apply_settings(
        self, stored: dict,
        upscale_conditions: list[filters.FilterCondition] | None = None,
    ) -> None:
        """Missing keys keep the current defaults; the restored collapse
        state is reflected into the panel.

        ``upscale_conditions`` (GUI rework Phase 6) is the ALREADY-
        PARSED replacement for the upscale FilterEditor's seeded
        default — ``None`` (a fresh settings.json, or a pre-Phase-6 one
        with nothing usable to migrate) leaves the widget's own
        construction-time default untouched, exactly matching every
        other field's "missing key = keep default" contract. The
        CALLER (``PainterGui._apply_settings``) owns parsing/migrating
        the raw JSON — see ``_migrate_legacy_upscale_gate`` and
        ``_parse_condition_dicts`` — because that needs a log sink this
        widget does not carry."""
        variables = self._vars()
        for key in self._PERSIST:
            if key in stored:
                variables[key].set(stored[key])
        if upscale_conditions is not None:
            self.upscale_filter.set_conditions(upscale_conditions)
        self._apply_finetune_visibility()


# ---------------------------------------------------------------------
# Standalone-tool settings panels (GUI rework Phase 13)
# ---------------------------------------------------------------------


def _parse_fraction(text: str, field_name: str) -> float:
    """Parse ONE Advanced-override fraction field (0 < x <= 1) —
    raises ``ValueError`` naming the field, the same "which field
    failed" contract every other panel/dialog validator in this file
    already follows (``_FilterConditionRow.to_condition``,
    ``AgentPanel.pace_floats`` et al.)."""
    try:
        value = float(text.strip())
    except ValueError:
        raise ValueError(f"{field_name}: must be a number.") from None
    if not (0.0 < value <= 1.0):
        raise ValueError(f"{field_name}: must be greater than 0 and at most 1.")
    return value


def _parse_nonneg_int(text: str, field_name: str) -> int:
    """Parse ONE Advanced-override whole-number field (>= 0)."""
    try:
        value = int(float(text.strip()))
    except ValueError:
        raise ValueError(f"{field_name}: must be a whole number.") from None
    if value < 0:
        raise ValueError(f"{field_name}: must not be negative.")
    return value


def _parse_int_range(text: str, field_name: str, lo: int, hi: int) -> int:
    """``_parse_nonneg_int`` plus an inclusive upper bound (the alpha
    fields are 0-255)."""
    value = _parse_nonneg_int(text, field_name)
    if not (lo <= value <= hi):
        raise ValueError(f"{field_name}: must be between {lo} and {hi}.")
    return value


class ToolSettingsPanel(ttk.Frame):
    """Base for a standalone in-place tool's PERSISTENT settings panel
    — all four tools now (BG removal / Crop, GUI rework Phase 13;
    Upscale / Aspect ratio, Phase 14, same treatment). Shown INLINE
    above Dashboard/Log while its tile is toggled open
    (``PainterGui._inline_kind`` — see ``PainterGui.
    _open_tool_panel``), the exact surface website_gen's own
    ``_controls_box`` already occupies (``_apply_running_layout``),
    generalized to a second panel family instead of forked.

    Owns: an input picker (**Folder…** — recursive via the shared
    ``iter_images``, matching every folder-based tool — or **Files…**,
    mirroring the Aspect tool's own Files/Folder choice), an optional
    **always-visible** subclass block (``_build_extra`` — e.g.
    Upscale's min-side spinner, Aspect's target-ratio canvas; base
    no-op), an embedded ``FilterEditor`` (Phase 4) narrowing WHICH
    images the run touches (optionally pre-seeded — ``_default_
    conditions``, base empty), an optional **Advanced** collapsible
    (the Settings-gear idiom ``AgentPanel._toggle_settings`` already
    established; ``HAS_ADVANCED = False`` skips building it entirely —
    Upscale/Aspect have no hidden engine knobs, only always-visible
    primary controls, so a gear that reveals nothing would be a dead
    affordance) exposing engine knobs the subclass contributes, an
    optional **footer** block (``_build_footer`` — e.g. Aspect's
    non-proportional-stretch warning, carried over from the old
    modal's confirm dialog; base no-op) shown just above the button
    row, and a Start/Pause/Stop row — Pause mirrors ``AgentPanel.
    btn_pause``: a plain label-only toggle, always clickable, never
    gated on run state (pausing before a job exists is harmless — a
    fresh Start always clears any stale pre-pause, see ``PainterGui.
    _launch_tool_worker``).

    **Stop** (GUI rework Phase 14, closing Phase 13's own flagged gap)
    mirrors ``AgentPanel.btn_stop``'s availability styling (filled
    while the job runs, disabled outline otherwise) and calls
    ``PainterGui._stop_tool`` — a "smart" stop: the worker
    (``_run_tool_job``, threaded a ``should_stop`` this phase, mirrors
    ``run_sheet``'s own pattern) finishes the in-flight image then
    halts; once it actually confirms the halt (``__tool_done__``, NOT
    synchronously on click — the worker may still be mid-image),
    ``PainterGui`` closes this tool's dashboard panel and clears its
    JobTemp (the existing ``_close_panel``, same as a manual Close)
    and returns to the Main Menu if that was the last active job
    (``_request_menu`` — Phase 11's OWN gate, unmodified: it only ever
    actually navigates once ``_active_kinds()`` is empty). This is a
    deliberate DIVERGENCE from a site's own Stop (which leaves its
    panel up for the owner to review before a manual Close, see
    gui.md's **Running view**) — a quick, disk-based tool run has
    nothing left worth reviewing once stopped, so "smart" here means
    "decisively finish the job", not "linger".

    Subclasses set ``SLOT`` and contribute ``_build_advanced``/
    ``build_func``/``_advanced_settings``/``_apply_advanced_settings``
    (Rule #5 — one shared body, not four near-identical panels);
    ``BgSettingsPanel``/``CropSettingsPanel`` additionally use
    ``_build_advanced`` for real (their engine knobs); ``Upscale
    SettingsPanel``/``AspectSettingsPanel`` set ``HAS_ADVANCED = False``
    and use ``_build_extra``/``_build_footer`` instead (see above) —
    ``_advanced_settings``/``_apply_advanced_settings`` still carry
    their own always-visible fields into the settings round-trip
    regardless (the hook name is about "subclass extra data", not
    literally the collapsible). Public surface ``PainterGui.
    _start_tool_from_panel`` reads: ``resolve_input() -> (Path,
    list[Path])`` (raises ``ValueError`` with an owner-facing
    message), ``get_conditions() -> list[FilterCondition]`` (proxies
    ``FilterEditor.get_conditions``, same raise contract),
    ``build_func() -> Callable[[Path, Log], str]`` (subclass hook —
    the engine call closed over THIS run's Advanced/extra overrides),
    ``set_run_state(running)``/``set_paused(is_paused)`` (mirror
    ``AgentPanel``'s own), and the settings round-trip
    ``get_settings()``/``apply_settings(stored, conditions=...)``.
    """

    SLOT: str = ""  # subclass sets this to a JOB_ORDER tool kind
    # False for Upscale/Aspect (GUI rework Phase 14) — they have no
    # hidden engine knobs, only ALWAYS-VISIBLE primary controls (see
    # _build_extra); building an empty collapsible gear would be a
    # dead affordance (Rule #16 — no pointless chrome).
    HAS_ADVANCED: bool = True

    def __init__(
        self,
        master,
        on_start: Callable[[str], None],
        on_pause: Callable[[str], None],
        on_stop: Callable[[str], None],
        filter_presets: dict[str, list[dict]] | None = None,
        on_filter_presets_changed: Callable[[], None] | None = None,
    ):
        super().__init__(master, padding=8)
        self.slot = self.SLOT
        self._on_start = on_start
        self._on_pause = on_pause
        self._on_stop = on_stop
        self._input_mode = "folder"  # or "files"
        self._folder: Path | None = None
        self._files: list[Path] = []

        head = ttk.Frame(self)
        head.pack(fill="x")
        ctk.CTkLabel(
            head, text="", image=icon(JOB_LOGO[self.slot]), width=22,
            fg_color="transparent", bg_color=theme_pair("bg"),
        ).pack(side="left", padx=(0, 4))
        ttk.Label(
            head, text=f"{JOB_LABEL[self.slot]} — settings",
            style="Head.TLabel",
        ).pack(side="left")

        pick_row = ttk.Frame(self)
        pick_row.pack(fill="x", pady=(8, 2))
        rounded_button(
            pick_row, "Folder…", command=self._pick_folder, kind="info",
            width=90,
        ).pack(side="left")
        rounded_button(
            pick_row, "Files…", command=self._pick_files, kind="info",
            width=90,
        ).pack(side="left", padx=(6, 0))
        self._picked_var = tk.StringVar(value="(pick a folder or files)")
        ttk.Label(
            pick_row, textvariable=self._picked_var, style="Muted.TLabel",
        ).pack(side="left", padx=(10, 0))

        # subclass hook — always-visible PRIMARY controls (Upscale's
        # min-side spinner, Aspect's target-ratio canvas); base no-op,
        # so BG/Crop see no change at all (an empty frame packs at
        # zero height)
        self._extra_box = ttk.Frame(self)
        self._extra_box.pack(fill="x")
        self._build_extra(self._extra_box)

        ttk.Label(
            self,
            text="Filter — which images this run touches (empty = all):",
        ).pack(anchor="w", pady=(8, 2))
        self.filter = FilterEditor(
            self, conditions=self._default_conditions(),
            presets=filter_presets,
            on_presets_changed=on_filter_presets_changed,
        )
        self.filter.pack(fill="x")

        # the Advanced collapsible — the SAME Settings-gear idiom
        # AgentPanel._toggle_settings/_apply_finetune_visibility already
        # established, applied to a subclass-built body instead of the
        # per-agent fine-tune block. Skipped entirely when the subclass
        # has nothing to hide behind it (HAS_ADVANCED = False) — see
        # this class's own docstring.
        if self.HAS_ADVANCED:
            adv_head = ttk.Frame(self)
            adv_head.pack(fill="x", pady=(10, 0))
            ttk.Label(adv_head, text="Advanced", style="Head.TLabel").pack(
                side="left"
            )
            self._advanced_btn = rounded_button(
                adv_head, SETTINGS_GLYPH_COLLAPSED,
                command=self._toggle_advanced, icon_name="settings",
            )
            self._advanced_btn.pack(side="left", padx=(6, 0))
            self._advanced_collapsed_var = tk.BooleanVar(value=True)
            self._advanced_box = ttk.Frame(self)
            self._build_advanced(self._advanced_box)
            self._apply_advanced_visibility()

        # subclass hook — a short always-visible note just above the
        # button row (Aspect's non-proportional-stretch warning); base
        # no-op
        self._footer_box = ttk.Frame(self)
        self._footer_box.pack(fill="x", pady=(6, 0))
        self._build_footer(self._footer_box)

        btn_row = ttk.Frame(self)
        btn_row.pack(fill="x", pady=(10, 0))
        self.btn_start = rounded_button(
            btn_row, "Start", command=lambda: self._on_start(self.slot),
            kind="success", icon_name="start", width=90,
        )
        self.btn_start.pack(side="left")
        # the pause toggle — a plain neutral button, ALWAYS clickable
        # (no filled/outline availability dance), exactly like
        # AgentPanel.btn_pause.
        self.btn_pause = rounded_button(
            btn_row, "Pause", command=lambda: self._on_pause(self.slot),
            kind="secondary", width=70,
        )
        self.btn_pause.pack(side="left", padx=6)
        # Stop (GUI rework Phase 14) — filled/outline availability like
        # AgentPanel.btn_stop, styled by set_run_state below.
        self.btn_stop = rounded_button(
            btn_row, "Stop", command=lambda: self._on_stop(self.slot),
            kind="danger-outline", width=70,
        )
        self.btn_stop.pack(side="left", padx=(0, 6))
        self.set_run_state(running=False)

        # a Day/Night flip must repaint any raw-Canvas content a
        # subclass embeds (AspectSettingsPanel's AspectRatioCanvas —
        # base apply_theme() is a no-op, mirrors AgentPanel's own
        # THEME_TOPLEVELS registration); build-once, never destroyed
        # before app exit, same lifetime as every dashboard JobPanel.
        THEME_TOPLEVELS.append(self)
        self.bind("<Destroy>", self._on_destroy)

    def _on_destroy(self, event) -> None:
        if event.widget is self and self in THEME_TOPLEVELS:
            THEME_TOPLEVELS.remove(self)

    def apply_theme(self) -> None:
        """Subclass hook — repaint any raw-Canvas content on a Day/
        Night flip (e.g. AspectSettingsPanel's AspectRatioCanvas.
        redraw_theme()). Base no-op."""

    # --- input picker ----------------------------------------------

    def _picker_title_suffix(self) -> str:
        """Subclass hook — what this run DOES to the picked images,
        shown after the job label in the folder/file picker dialog
        titles ('Folder with images — <label> <this text>'). Base:
        every one of the four standalone tools modifies files IN
        PLACE. Overridden by ``ImageCheckerSettingsPanel`` (GUI rework
        Phase 15) — a read-only vision pass must never claim to write
        anything (root Rule #1: never mislead)."""
        return "runs IN PLACE"

    def _pick_folder(self) -> None:
        folder = filedialog.askdirectory(
            title=f"Folder with images — {JOB_LABEL[self.slot]}"
            f" {self._picker_title_suffix()}"
        )
        if not folder:
            return
        self._input_mode = "folder"
        self._folder = Path(folder)
        self._files = []
        n = len(iter_images(self._folder))
        self._picked_var.set(f"Folder: {self._folder}  ({n} image(s))")

    def _pick_files(self) -> None:
        picks = filedialog.askopenfilenames(
            title=f"Image files — {JOB_LABEL[self.slot]}"
            f" {self._picker_title_suffix()}",
            filetypes=[
                ("Images", "*.png *.jpg *.jpeg *.webp"),
                ("All files", "*.*"),
            ],
        )
        if not picks:
            return
        self._input_mode = "files"
        self._folder = None
        self._files = [Path(p) for p in picks]
        self._picked_var.set(f"{len(self._files)} file(s) picked")

    def resolve_input(self) -> tuple[Path, list[Path]]:
        """(base folder, candidate files) for THIS run — raises
        ``ValueError`` when nothing has been picked yet. Folder mode
        RE-SCANS live (``iter_images``) so a folder edited since the
        pick is honored, matching every existing folder-based tool;
        Files mode replays the exact picked list, based via
        ``config.selection_base_and_rels`` (a selection spanning
        sub-folders still groups/restores correctly, mirroring the
        Aspect tool)."""
        if self._input_mode == "folder":
            if self._folder is None:
                raise ValueError("Pick a folder or files first.")
            return self._folder, iter_images(self._folder)
        if not self._files:
            raise ValueError("Pick a folder or files first.")
        base, _rels = selection_base_and_rels(self._files)
        return base, list(self._files)

    # --- filter ------------------------------------------------------

    def get_conditions(self) -> list[filters.FilterCondition]:
        return self.filter.get_conditions()

    def _default_conditions(self) -> list[filters.FilterCondition]:
        """Subclass hook — the embedded FilterEditor's SEED conditions
        (e.g. UpscaleSettingsPanel's aspect-range default). Base empty
        (BG/Crop start with no filter, unchanged)."""
        return []

    # --- always-visible subclass content (GUI rework Phase 14) --------

    def _build_extra(self, box: ttk.Frame) -> None:
        """Subclass hook — populate ``box`` with this tool's own
        ALWAYS-VISIBLE primary control(s), shown between the input
        picker and the Filter section (Upscale's min-side spinner,
        Aspect's target-ratio canvas). Base no-op."""

    def _build_footer(self, box: ttk.Frame) -> None:
        """Subclass hook — populate ``box`` with a short note shown
        just above the Start/Pause/Stop row (Aspect's non-proportional-
        stretch warning). Base no-op."""

    # --- Advanced (subclass hooks) ------------------------------------

    def _build_advanced(self, box: ttk.Frame) -> None:
        """Subclass hook — populate ``box`` with this tool's own engine
        knobs. Base no-op (never reached directly — ``SLOT``/this
        method are always overridden together). Only ever called when
        ``HAS_ADVANCED`` is True."""

    def build_func(self) -> Callable[[Path, Callable[[str], None]], str]:
        """Subclass hook — a ``(path, log) -> str`` callable wrapping
        the engine function with THIS run's Advanced overrides. Raises
        ``ValueError`` (naming the field) on an unparsable override."""
        raise NotImplementedError

    def _advanced_settings(self) -> dict:
        """Subclass hook — this tool's Advanced fields as a JSON-safe
        dict, folded into ``get_settings()``."""
        return {}

    def _apply_advanced_settings(self, stored: dict) -> None:
        """Subclass hook — the inverse of ``_advanced_settings``;
        missing keys keep the current defaults."""

    def _apply_advanced_visibility(self) -> None:
        collapsed = self._advanced_collapsed_var.get()
        if collapsed:
            self._advanced_box.pack_forget()
        else:
            self._advanced_box.pack(fill="x", pady=(2, 0))
        self._advanced_btn.configure(
            text=SETTINGS_GLYPH_COLLAPSED if collapsed
            else SETTINGS_GLYPH_EXPANDED
        )

    def _toggle_advanced(self) -> None:
        self._advanced_collapsed_var.set(
            not self._advanced_collapsed_var.get()
        )
        smooth_transition(
            self.winfo_toplevel(), self._apply_advanced_visibility
        )

    # --- run state -----------------------------------------------------

    def set_run_state(self, running: bool) -> None:
        """Start is available unless this slot's job is already
        running; Stop is available exactly while it runs — mirrors
        ``AgentPanel.set_run_state`` (no ``pending_restart`` here, a
        site-only/quota concept a standalone tool never has)."""
        style_action_button(self.btn_start, "success", not running)
        style_action_button(self.btn_stop, "danger", running)

    def set_paused(self, is_paused: bool) -> None:
        self.btn_pause.configure(text="Resume" if is_paused else "Pause")

    # --- settings round-trip -------------------------------------------

    def get_settings(self) -> dict:
        data = {
            "conditions": [
                filters.condition_to_dict(c)
                for c in self.filter.get_conditions()
            ],
        }
        if self.HAS_ADVANCED:
            data["advanced_collapsed"] = self._advanced_collapsed_var.get()
        data.update(self._advanced_settings())
        return data

    def apply_settings(
        self, stored: dict,
        conditions: list[filters.FilterCondition] | None = None,
    ) -> None:
        """Missing keys keep the current defaults — same contract as
        every other panel's ``apply_settings`` in this file.
        ``conditions`` (GUI rework Phase 4 convention) is the ALREADY-
        PARSED replacement for the FilterEditor's stack; ``None`` (a
        fresh settings.json) leaves it at its construction-time
        default (empty, or a subclass's own ``_default_conditions``).
        The CALLER (``PainterGui._apply_settings``) owns parsing the
        raw JSON, same as ``AgentPanel.apply_settings``. ``_apply_
        advanced_settings`` always runs, regardless of ``HAS_
        ADVANCED`` — it also carries a subclass's ALWAYS-VISIBLE extra
        fields (e.g. Upscale's min-side, Aspect's target ratio)."""
        if conditions is not None:
            self.filter.set_conditions(conditions)
        if self.HAS_ADVANCED:
            if "advanced_collapsed" in stored:
                self._advanced_collapsed_var.set(
                    bool(stored["advanced_collapsed"])
                )
            self._apply_advanced_visibility()
        self._apply_advanced_settings(stored)


class BgSettingsPanel(ToolSettingsPanel):
    """BG removal's persistent settings panel (GUI rework Phase 13).

    Advanced exposes the SAFETY GUARD fractions ``remove_background``
    aborts past (owner 2026-07-19's "never destroy an image" rule) —
    NOT the border-halo-cleanup toggle the design's own phase notes
    mention: that constant (``CLEAN_EDGE_ENABLE``) is only ever read by
    ``crop_transparent`` (its docstring: "only serves to ENABLE a
    tighter crop") — ``remove_background`` never calls
    ``clean_edge_halo`` at all, so surfacing it here would silently do
    nothing (root Rule #1). It lives on ``CropSettingsPanel`` instead,
    where it actually affects behaviour; see that class's own
    docstring."""

    SLOT = "bg"

    def _build_advanced(self, box: ttk.Frame) -> None:
        ttk.Label(
            box,
            text="Safety guard — abort a removal that would clear more"
            " than:",
        ).pack(anchor="w", pady=(0, 2))
        row = ttk.Frame(box)
        row.pack(fill="x", pady=2)
        ttk.Label(row, text="black bg", width=10).pack(side="left")
        self.safety_black_var = tk.StringVar(
            value=f"{SAFETY_MAX_REMOVE_FRAC:.2f}"
        )
        rounded_entry(
            row, width=60, textvariable=self.safety_black_var,
            justify="center",
        ).pack(side="left")
        ttk.Label(row, text="(fraction, e.g. 0.40)").pack(
            side="left", padx=(6, 0)
        )
        row2 = ttk.Frame(box)
        row2.pack(fill="x", pady=2)
        ttk.Label(row2, text="white bg", width=10).pack(side="left")
        self.safety_white_var = tk.StringVar(
            value=f"{SAFETY_MAX_REMOVE_FRAC_WHITE:.2f}"
        )
        rounded_entry(
            row2, width=60, textvariable=self.safety_white_var,
            justify="center",
        ).pack(side="left")

    def build_func(self) -> Callable[[Path, Callable[[str], None]], str]:
        from painter.postprocess import remove_background

        black = _parse_fraction(self.safety_black_var.get(), "black bg safety")
        white = _parse_fraction(self.safety_white_var.get(), "white bg safety")
        return lambda path, log: remove_background(
            path, log,
            safety_max_remove_frac=black,
            safety_max_remove_frac_white=white,
        )

    def _advanced_settings(self) -> dict:
        return {
            "safety_black": self.safety_black_var.get(),
            "safety_white": self.safety_white_var.get(),
        }

    def _apply_advanced_settings(self, stored: dict) -> None:
        if "safety_black" in stored:
            self.safety_black_var.set(stored["safety_black"])
        if "safety_white" in stored:
            self.safety_white_var.set(stored["safety_white"])


class CropSettingsPanel(ToolSettingsPanel):
    """Crop's persistent settings panel (GUI rework Phase 13).

    Advanced exposes every knob ``crop_transparent`` actually reads:
    the border-halo cleanup toggle (``clean_edge_enable`` — only ever
    serves to ENABLE a tighter crop, see ``painter/postprocess.md``),
    the safety MARGIN kept around the content box, and the ink-
    detection thresholds (the alpha floor + the minimum ink pixels a
    row/col needs to count as content). ``CLEAN_EDGE_ALPHA`` (the
    halo's OWN alpha threshold, a finer sub-knob of the toggle above)
    stays at its config default — not surfaced as a field this round,
    unlike the other four, which the design explicitly asked for."""

    SLOT = "crop"

    def _build_advanced(self, box: ttk.Frame) -> None:
        self.clean_edge_var = tk.BooleanVar(value=CLEAN_EDGE_ENABLE)
        rounded_switch(
            box, "Clean faint border halo before cropping (tighter crop)",
            self.clean_edge_var,
        ).pack(anchor="w", pady=(0, 4))

        row = ttk.Frame(box)
        row.pack(fill="x", pady=2)
        ttk.Label(row, text="margin px", width=10).pack(side="left")
        self.margin_var = tk.StringVar(value=str(CROP_MARGIN_PX))
        rounded_entry(
            row, width=60, textvariable=self.margin_var, justify="center",
        ).pack(side="left")

        row2 = ttk.Frame(box)
        row2.pack(fill="x", pady=2)
        ttk.Label(row2, text="ink alpha", width=10).pack(side="left")
        self.ink_alpha_var = tk.StringVar(value=str(CROP_INK_ALPHA))
        rounded_entry(
            row2, width=60, textvariable=self.ink_alpha_var, justify="center",
        ).pack(side="left")
        ttk.Label(row2, text="0-255").pack(side="left", padx=(6, 0))

        row3 = ttk.Frame(box)
        row3.pack(fill="x", pady=2)
        ttk.Label(row3, text="min ink px", width=10).pack(side="left")
        self.min_ink_var = tk.StringVar(value=str(CROP_MIN_INK_PX))
        rounded_entry(
            row3, width=60, textvariable=self.min_ink_var, justify="center",
        ).pack(side="left")

    def build_func(self) -> Callable[[Path, Callable[[str], None]], str]:
        from painter.postprocess import crop_transparent

        margin = _parse_nonneg_int(self.margin_var.get(), "margin px")
        ink_alpha = _parse_int_range(
            self.ink_alpha_var.get(), "ink alpha", 0, 255
        )
        min_ink = _parse_nonneg_int(self.min_ink_var.get(), "min ink px")
        clean_enable = self.clean_edge_var.get()
        return lambda path, log: crop_transparent(
            path, log,
            clean_edge_enable=clean_enable,
            crop_margin_px=margin,
            crop_ink_alpha=ink_alpha,
            crop_min_ink_px=min_ink,
        )

    def _advanced_settings(self) -> dict:
        return {
            "clean_edge_enable": self.clean_edge_var.get(),
            "margin_px": self.margin_var.get(),
            "ink_alpha": self.ink_alpha_var.get(),
            "min_ink_px": self.min_ink_var.get(),
        }

    def _apply_advanced_settings(self, stored: dict) -> None:
        if "clean_edge_enable" in stored:
            self.clean_edge_var.set(bool(stored["clean_edge_enable"]))
        if "margin_px" in stored:
            self.margin_var.set(stored["margin_px"])
        if "ink_alpha" in stored:
            self.ink_alpha_var.set(stored["ink_alpha"])
        if "min_ink_px" in stored:
            self.min_ink_var.set(stored["min_ink_px"])


class UpscaleSettingsPanel(ToolSettingsPanel):
    """Upscale's persistent settings panel (GUI rework Phase 14).

    No Advanced section (``HAS_ADVANCED = False``) — Phase 6 already
    reduced the whole gate to ONE min-side spinner plus the base's own
    embedded ``FilterEditor`` (pre-seeded here with the aspect-range
    default via ``_default_conditions``, exactly like ``AgentPanel``'s
    own ``upscale_filter``/``UpscaleParamsDialog``'s old seed), so
    there is nothing left to tuck behind a gear — the spinner is the
    panel's one PRIMARY control, always visible (``_build_extra``),
    right where the old modal put it."""

    SLOT = "upscale"
    HAS_ADVANCED = False

    def _default_conditions(self) -> list[filters.FilterCondition]:
        return [filters.FilterCondition(
            kind=FILTER_KIND_ASPECT_RANGE, polarity=FILTER_POLARITY_IF,
            lo=UPSCALE_ASPECT_MIN, hi=UPSCALE_ASPECT_MAX,
        )]

    def _build_extra(self, box: ttk.Frame) -> None:
        self.up_minside_var = tk.StringVar(
            value=str(UPSCALE_MIN_SIDE_DEFAULT)
        )
        row = ttk.Frame(box)
        row.pack(fill="x", pady=2)
        ttk.Label(row, text="min side", width=8).pack(side="left")
        Spinner(row, self.up_minside_var, step=UPSCALE_MINDIM_STEP).pack(
            side="left"
        )
        ttk.Label(
            row, text="px — the smaller side reaches this; the Filter"
            " below decides WHICH images qualify",
        ).pack(side="left", padx=(4, 0))

    def build_func(self) -> Callable[[Path, Callable[[str], None]], str]:
        """The min-side spinner + the base's OWN FilterEditor resolve
        into ``upscale_if_small``'s kwargs exactly like ``AgentPanel``'s
        own upscale gate (``_upscale_params_from_side_and_filter``).
        ``get_conditions()`` is read AGAIN here (the caller,
        ``PainterGui._start_tool_from_panel``, already reads it once to
        pre-filter the candidate file list) — a harmless duplicate read
        (FilterEditor rows, no side effects): this closure needs the
        SAME conditions to resolve the aspect band, and every
        ``ToolSettingsPanel.build_func()`` has the same fixed no-
        argument signature, so there is no other way to hand them in."""
        from painter.upscale import upscale_if_small

        try:
            min_side = int(float(self.up_minside_var.get().strip()))
        except ValueError:
            raise ValueError("Min side must be a number.")
        if min_side <= 0:
            raise ValueError("Min side must be positive.")
        up_params = _upscale_params_from_side_and_filter(
            min_side, self.get_conditions()
        )
        return lambda path, log: upscale_if_small(path, log, **up_params)

    def _advanced_settings(self) -> dict:
        return {"up_minside": self.up_minside_var.get()}

    def _apply_advanced_settings(self, stored: dict) -> None:
        if "up_minside" in stored:
            self.up_minside_var.set(stored["up_minside"])


class AspectSettingsPanel(ToolSettingsPanel):
    """Aspect ratio's persistent settings panel (GUI rework Phase 14).

    No Advanced section (``HAS_ADVANCED = False``) — the target-ratio
    editor (``_build_extra``: GUI rework Phase 5's ``AspectRatioCanvas``
    two-way synced with plain W/H entries, exactly like ``AgentPanel``'s
    own Force Aspect Ratio block) IS the panel's one PRIMARY control,
    always visible; the base's own embedded ``FilterEditor`` decides
    WHICH images qualify. ``_build_footer`` carries the non-
    proportional-stretch warning the old modal's confirm ``askyesno``
    used to show, so Start — no confirm dialog here; the panel itself,
    deliberately configured then Started, already IS the confirmation,
    same contract as every other panel — never surprises the owner."""

    SLOT = "aspect"
    HAS_ADVANCED = False

    def _build_extra(self, box: ttk.Frame) -> None:
        self._ratio_w_var = tk.StringVar(value=str(ASPECT_DEFAULT_W))
        self._ratio_h_var = tk.StringVar(value=str(ASPECT_DEFAULT_H))
        ttk.Label(
            box, text="Target aspect ratio — stretches every matching"
            " image to it:",
        ).pack(anchor="w", pady=(0, 6))

        row = ttk.Frame(box)
        row.pack(anchor="w")
        fields = ttk.Frame(row)
        fields.pack(side="left", anchor="n")
        ttk.Label(fields, text="W").pack(side="left", padx=(0, 4))
        self._w_entry = rounded_entry(
            fields, width=ASPECT_DIALOG_ENTRY_W,
            textvariable=self._ratio_w_var, justify="center",
        )
        self._w_entry.pack(side="left")
        ttk.Label(fields, text=":", font=tk_font("head")).pack(
            side="left", padx=8
        )
        ttk.Label(fields, text="H").pack(side="left", padx=(0, 4))
        self._h_entry = rounded_entry(
            fields, width=ASPECT_DIALOG_ENTRY_W,
            textvariable=self._ratio_h_var, justify="center",
        )
        self._h_entry.pack(side="left")

        # the visual editor (GUI rework Phase 5), two-way synced with
        # the fields above — the SAME pattern AspectRatioDialog/
        # AgentPanel's own Force Aspect Ratio block already use
        self._ratio_canvas = AspectRatioCanvas(
            row, w=ASPECT_DEFAULT_W, h=ASPECT_DEFAULT_H,
            on_change=self._on_canvas_drag,
        )
        self._ratio_canvas.pack(side="left", padx=(12, 0), anchor="n")
        self._ratio_w_var.trace_add("write", self._on_wh_typed)
        self._ratio_h_var.trace_add("write", self._on_wh_typed)

    def _build_footer(self, box: ttk.Frame) -> None:
        ttk.Label(
            box,
            text="⚠ Deforms every matching image with a non-proportional"
            " STRETCH, written IN PLACE. Originals are backed up so you"
            " can Restore; images already at this ratio are skipped"
            " untouched.",
            style="Muted.TLabel", wraplength=JOB_PANEL_BANNER_WRAP_PX,
        ).pack(anchor="w")

    def _on_canvas_drag(self, w: int, h: int) -> None:
        """``AspectRatioCanvas.on_change`` — mirrors ``AgentPanel.
        _on_force_aspect_canvas_drag``/``AspectRatioDialog.
        _on_canvas_drag`` (Rule #5 — the third instance of the same
        two-way sync)."""
        self._ratio_w_var.set(str(w))
        self._ratio_h_var.set(str(h))

    def _on_wh_typed(self, *_args) -> None:
        """Live-reshape the canvas as the owner types; a bad/mid-edit
        value is silently skipped (final validation happens in
        ``target_ratio()`` on Start) — mirrors ``AgentPanel._on_force_
        aspect_wh_typed``/``AspectRatioDialog._on_wh_typed``."""
        try:
            w = int(self._ratio_w_var.get().strip())
            h = int(self._ratio_h_var.get().strip())
        except ValueError:
            return
        if w <= 0 or h <= 0:
            return
        self._ratio_canvas.set_ratio(w, h)

    def target_ratio(self) -> tuple[int, int]:
        """The target W:H — ``ValueError`` propagates to Start's own
        messagebox, same contract as ``AgentPanel.force_aspect_ratio``."""
        try:
            w = int(self._ratio_w_var.get().strip())
            h = int(self._ratio_h_var.get().strip())
        except ValueError:
            raise ValueError("Width and height must be whole numbers.")
        if w <= 0 or h <= 0:
            raise ValueError("Width and height must both be positive.")
        return (w, h)

    def build_func(self) -> Callable[[Path, Callable[[str], None]], str]:
        from painter.aspect import change_aspect

        ratio_w, ratio_h = self.target_ratio()
        return lambda path, log: change_aspect(path, ratio_w, ratio_h, log)

    def _advanced_settings(self) -> dict:
        return {"ratio": [self._ratio_w_var.get(), self._ratio_h_var.get()]}

    def _apply_advanced_settings(self, stored: dict) -> None:
        ratio = stored.get("ratio")
        if not (isinstance(ratio, (list, tuple)) and len(ratio) == 2):
            return
        try:
            w, h = int(ratio[0]), int(ratio[1])
        except (TypeError, ValueError):
            return
        if w > 0 and h > 0:
            self._ratio_w_var.set(str(w))
            self._ratio_h_var.set(str(h))
            self._ratio_canvas.set_ratio(w, h)

    def apply_theme(self) -> None:
        self._ratio_canvas.redraw_theme()


class ImageCheckerSettingsPanel(ToolSettingsPanel):
    """The AI image checker's persistent settings panel (GUI rework
    Phase 15) — the SAME input-picker + Filter + Start/Pause/Stop
    chrome every standalone tool now has, replacing the Main Menu/
    IconBar's old direct ``_start_ai_check`` launch (its own
    ``askdirectory`` + confirm ``askyesno``, both retired: the panel's
    OWN picker covers the folder/files, and Start — deliberately
    configured then clicked — already IS the confirmation, same
    contract as every sibling panel; see ``ToolSettingsPanel``'s own
    docstring and ``AspectSettingsPanel``'s "no confirm dialog here").

    No Advanced section (``HAS_ADVANCED = False``) — the checker has
    no engine knobs to hide, only the base's own input picker plus an
    OPTIONAL embedded ``FilterEditor`` (unseeded — empty means check
    EVERY image under the folder, same "empty = all" contract BG/Crop
    already use) and a short informational footer carrying what the
    old confirm dialog used to say (model + pacing + where flags
    persist), so the owner still sees that information without a
    blocking dialog.

    Its Start does NOT go through ``build_func``/``PainterGui.
    _start_tool_from_panel``/``_launch_tool_worker`` at all — the
    checker's own worker (``_run_ai_check_job``) has a fundamentally
    different shape from the four tools' shared ``_run_tool_job`` (no
    JobTemp backup — the run is read-only — no per-file engine
    callable, its own event types), so it is wired straight to
    ``PainterGui._start_ai_check`` instead (see that method's own
    docstring for the full flow). **Stop reuses ``PainterGui.
    _stop_tool`` UNCHANGED** — that method never touches
    ``_tool_panels`` and is already fully generic over any slot with a
    ``_tool_workers``/``_stop_events`` entry (it only sets the stop
    event, clears a pending pause and writes a status line), so a
    second near-identical ``_stop_ai_check`` method would only
    duplicate it byte-for-byte (Rule #5) — the constructor below wires
    ``on_stop=PainterGui._stop_tool`` exactly like BG/Crop/Upscale/
    Aspect.

    One asymmetry from its three siblings: this panel's MENU_TILES id
    ("image_checker") differs from its own ``SLOT``/JOB_ORDER kind
    ("aicheck") — the checker already existed as the dashboard's
    seventh job kind (``AiCheckPanel``, owner 2026-07-20) before this
    panel did, so its slot name predates and is independent of the
    tile system Phase 10 introduced. ``PainterGui._tool_panel_key``
    (backed by ``config.tile_for_kind``) is the one translation point
    that bridges the two spaces wherever `_toggle_pause_job`/
    `_dispatch` need to reach THIS panel from the "aicheck" kind."""

    SLOT = "aicheck"
    HAS_ADVANCED = False

    def _picker_title_suffix(self) -> str:
        return "(read-only)"

    def _build_footer(self, box: ttk.Frame) -> None:
        ttk.Label(
            box,
            text="Each image goes to the Gemini vision model"
            f" ({GEMINI_VISION_MODEL}) for banal defects only, paced"
            f" ~{AI_CALL_PAUSE_S:.0f}s per call on the free tier."
            f" Read-only — nothing is modified; flags persist under"
            f" the output folder's {STATE_DIRNAME}/.",
            style="Muted.TLabel", wraplength=JOB_PANEL_BANNER_WRAP_PX,
        ).pack(anchor="w")


class ApiImageGenPanel(ttk.Frame):
    """API Image GEN's persistent settings panel (GUI rework Phase 19)
    — menu-hosted exactly like the ``ToolSettingsPanel`` family
    (``PainterGui._tool_panels["api_image_gen"]``, reached the SAME way
    via ``_open_tool_panel``/``_click_icon_bar_tile``), but this panel
    does NOT subclass ``ToolSettingsPanel``: its input is the SAME
    queued ``.md`` sheet Collections list Website GEN already drives
    (``PainterGui._sheets``), never a folder of already-existing
    images, so a "Folder…/Files…" picker would be actively wrong here.
    It mirrors ``AgentPanel`` instead — background/style dropdowns
    feeding the SAME ``config.prompt_suffix`` machinery, the composable
    post-save switches (BG removal/Crop/Force Aspect Ratio/Upscale,
    see ``PainterGui._compose_post_save``, called with THIS panel
    passed explicitly since it is not one of ``self.agents``), and its
    own Start/Pause/Stop trio — while ``get_settings``/``apply_settings``
    use the SAME ``(stored, conditions=...)`` shape ``ToolSettingsPanel``
    already has, so it round-trips through the EXISTING generic
    "tool_panels" settings loop with no changes there either.

    BG/Crop/Force-Aspect/Upscale default ON — unlike ``AgentPanel``'s
    own defaults (BG/Crop/Upscale ON, Force Aspect OFF) — because the
    paid image model cannot render a REAL transparent background
    (UV/prompt.txt item 3: "ne moze TRANSPARENT pa mora BG removal i
    CROP sve redom"), so every generated image needs the full cleanup
    pipeline by default; the background dropdown defaults to "white"
    (a background the model CAN render, for BG removal to key out)
    instead of borrowing a site's own ``default_background``.

    GATING (owner decision, Phase 19 spec item 5): the owner's key has
    ZERO free-tier quota for the paid image model TODAY
    (``ai.PaidFeatureRequired``) — **Check API access** runs one cheap
    probe call on a background thread (its OWN private queue+poll,
    mirroring ``_AiDialog``'s established pattern — this panel is a
    ``ttk.Frame``, not a ``Toplevel``, so it cannot literally subclass
    that Toplevel-only base) and, when the free-tier-zero signal fires,
    disables Start with a clear message (``AI_IMAGE_GATE_MESSAGE``)
    instead of leaving the owner to discover it mid-run. This is a
    CONVENIENCE, not the only guard: a real run started without probing
    first is caught the SAME way by ``ApiImageAdapter.extract_image``
    (mapped to ``driver.TerminalState`` — the identical quota-stop
    plumbing every site already has)."""

    def __init__(
        self, master,
        on_start: Callable[[], None], on_pause: Callable[[str], None],
        on_stop: Callable[[str], None],
        filter_presets: dict[str, list[dict]] | None = None,
        on_filter_presets_changed: Callable[[], None] | None = None,
    ):
        super().__init__(master, padding=8)
        self._on_start = on_start
        self._on_pause = on_pause
        self._on_stop = on_stop
        self._filter_presets = filter_presets
        self._on_filter_presets_changed = on_filter_presets_changed
        self._running = False
        # set by a Check-API-access probe; gates Start until a probe
        # clears it again (or the app restarts) — see _apply_probe_result
        self.access_gated = False

        head = ttk.Frame(self)
        head.pack(fill="x")
        ctk.CTkLabel(
            head, text="", image=icon(JOB_LOGO["api_image"]), width=22,
            fg_color="transparent", bg_color=theme_pair("bg"),
        ).pack(side="left", padx=(0, 4))
        ttk.Label(
            head, text=f"{JOB_LABEL['api_image']} — settings",
            style="Head.TLabel",
        ).pack(side="left")

        ttk.Label(
            self,
            text="Generates the SAME queued Collections (.md sheets) as"
            " Website GEN, through the paid Gemini image API instead of"
            " a browser tab.",
            style="Muted.TLabel", wraplength=JOB_PANEL_BANNER_WRAP_PX,
        ).pack(anchor="w", pady=(6, 4))

        # background/style — the SAME prompt_suffix machinery every
        # AgentPanel already feeds (Rule #5); "white" default (not a
        # site's own default_background) since the model cannot render
        # real transparency — see this class's own docstring
        self.background_var = tk.StringVar(value="white")
        self.style_var = tk.StringVar(value=STYLE_DEFAULT)
        row = ttk.Frame(self)
        row.pack(fill="x", pady=2)
        ttk.Label(row, text="Background:").pack(side="left")
        rounded_combo(
            row, BACKGROUND_CHOICES, self.background_var, width=105,
        ).pack(side="left", padx=(2, 10))
        ttk.Label(row, text="Style:").pack(side="left")
        rounded_combo(
            row, STYLE_CHOICES, self.style_var, width=150,
        ).pack(side="left", padx=(2, 0))

        # post-save pipeline switches — ALL default ON (no native
        # transparency, spec item 3): _compose_post_save runs whichever
        # are ticked in the fixed BG -> Crop -> Aspect -> Upscale order,
        # identical to every AgentPanel-driven site.
        self.bg_removal_var = tk.BooleanVar(value=True)
        self.crop_var = tk.BooleanVar(value=True)
        self.force_aspect_var = tk.BooleanVar(value=True)
        self.upscale_var = tk.BooleanVar(value=True)
        row = ttk.Frame(self)
        row.pack(fill="x", pady=2)
        rounded_switch(row, "BG removal", self.bg_removal_var).pack(
            side="left"
        )
        rounded_switch(row, "Crop", self.crop_var).pack(side="left", padx=8)
        rounded_switch(
            row, "Force Aspect Ratio", self.force_aspect_var,
        ).pack(side="left", padx=(0, 8))
        rounded_switch(row, "Upscale", self.upscale_var).pack(side="left")

        self.report_var = tk.BooleanVar(value=True)
        self.keep_all_steps_var = tk.BooleanVar(
            value=JOBTEMP_KEEP_ALL_STEPS_DEFAULT
        )
        row = ttk.Frame(self)
        row.pack(fill="x", pady=2)
        rounded_switch(row, "Report txt", self.report_var).pack(side="left")
        rounded_switch(
            row, "Keep every pipeline step (uses more disk)",
            self.keep_all_steps_var,
        ).pack(side="left", padx=8)

        # Force Aspect Ratio target — the SAME AspectRatioCanvas two-way
        # sync AgentPanel's own Force-Aspect block / AspectSettingsPanel
        # already use (Rule #5)
        ttk.Label(
            self, text="Force Aspect Ratio target:", style="Head.TLabel",
        ).pack(anchor="w", pady=(4, 0))
        self.force_aspect_w_var = tk.StringVar(value=str(ASPECT_DEFAULT_W))
        self.force_aspect_h_var = tk.StringVar(value=str(ASPECT_DEFAULT_H))
        fa_box = ttk.Frame(self)
        fa_box.pack(fill="x", pady=2)
        fa_fields = ttk.Frame(fa_box)
        fa_fields.pack(side="left", anchor="n")
        ttk.Label(fa_fields, text="W").pack(side="left", padx=(0, 4))
        rounded_entry(
            fa_fields, width=ASPECT_DIALOG_ENTRY_W,
            textvariable=self.force_aspect_w_var, justify="center",
        ).pack(side="left")
        ttk.Label(fa_fields, text=":", font=tk_font("head")).pack(
            side="left", padx=8
        )
        ttk.Label(fa_fields, text="H").pack(side="left", padx=(0, 4))
        rounded_entry(
            fa_fields, width=ASPECT_DIALOG_ENTRY_W,
            textvariable=self.force_aspect_h_var, justify="center",
        ).pack(side="left")
        self._force_aspect_canvas = AspectRatioCanvas(
            fa_box, w=int(self.force_aspect_w_var.get()),
            h=int(self.force_aspect_h_var.get()),
            on_change=self._on_force_aspect_canvas_drag,
        )
        self._force_aspect_canvas.pack(side="left", padx=(12, 0), anchor="n")
        self.force_aspect_w_var.trace_add(
            "write", self._on_force_aspect_wh_typed
        )
        self.force_aspect_h_var.trace_add(
            "write", self._on_force_aspect_wh_typed
        )

        # the upscale gate — min-side spinner + embedded FilterEditor,
        # the SAME shape AgentPanel/UpscaleSettingsPanel already use
        ttk.Label(
            self, text="Upscale gate:", style="Head.TLabel",
        ).pack(anchor="w", pady=(4, 0))
        self.up_minside_var = tk.StringVar(
            value=str(UPSCALE_MIN_SIDE_DEFAULT)
        )
        row = ttk.Frame(self)
        row.pack(fill="x", pady=2)
        ttk.Label(row, text="min side", width=8).pack(side="left")
        Spinner(row, self.up_minside_var, step=UPSCALE_MINDIM_STEP).pack(
            side="left"
        )
        ttk.Label(
            row, text="px (the smaller side reaches this)"
        ).pack(side="left", padx=(4, 0))
        self.upscale_filter = FilterEditor(
            self,
            conditions=[filters.FilterCondition(
                kind=FILTER_KIND_ASPECT_RANGE, polarity=FILTER_POLARITY_IF,
                lo=UPSCALE_ASPECT_MIN, hi=UPSCALE_ASPECT_MAX,
            )],
            presets=self._filter_presets,
            on_presets_changed=self._on_filter_presets_changed,
        )
        self.upscale_filter.pack(fill="x", pady=(2, 0))

        # pace between prompts — run_sheet's own pacing wait, unrelated
        # to ai.py's internal AI_CALL_PAUSE_S free-tier throttle; no
        # action-delay field (that is SiteDriver._hesitate()'s DOM
        # concept — there is no DOM here).
        self.pause_min_var = tk.StringVar(value=f"{TIMING.pause_min_s:.0f}")
        self.pause_max_var = tk.StringVar(value=f"{TIMING.pause_max_s:.0f}")
        row = ttk.Frame(self)
        row.pack(fill="x", pady=2)
        ttk.Label(row, text="pause", width=12).pack(side="left")
        Spinner(row, self.pause_min_var, step=1.0).pack(side="left")
        ttk.Label(row, text="–").pack(side="left", padx=2)
        Spinner(row, self.pause_max_var, step=1.0).pack(side="left")
        ttk.Label(row, text="s").pack(side="left", padx=(2, 0))

        # --- GATING: the "Check API access" probe (spec item 5) -------
        gate_row = ttk.Frame(self)
        gate_row.pack(fill="x", pady=(8, 2))
        self._gate_btn = rounded_button(
            gate_row, "Check API access", command=self._probe_access,
            kind="info",
        )
        self._gate_btn.pack(side="left")
        self._gate_var = tk.StringVar(value="")
        ttk.Label(
            gate_row, textvariable=self._gate_var, style="Muted.TLabel",
            wraplength=JOB_PANEL_BANNER_WRAP_PX,
        ).pack(side="left", padx=(8, 0))
        self._probe_q: queue.Queue = queue.Queue()
        self._probe_poll_job: str | None = None

        btn_row = ttk.Frame(self)
        btn_row.pack(fill="x", pady=(10, 0))
        self.btn_start = rounded_button(
            btn_row, "Start", command=self._on_start,
            kind="success", icon_name="start", width=90,
        )
        self.btn_start.pack(side="left")
        self.btn_pause = rounded_button(
            btn_row, "Pause", command=partial(self._on_pause, "api_image"),
            kind="secondary", width=70,
        )
        self.btn_pause.pack(side="left", padx=6)
        self.btn_stop = rounded_button(
            btn_row, "Stop", command=partial(self._on_stop, "api_image"),
            kind="danger-outline", width=70,
        )
        self.btn_stop.pack(side="left", padx=(0, 6))
        self.set_run_state(running=False)

        # a Day/Night flip must repaint the embedded AspectRatioCanvas
        # (mirrors AgentPanel/AspectSettingsPanel's own registration —
        # build-once, never destroyed before app exit)
        THEME_TOPLEVELS.append(self)
        self.bind("<Destroy>", self._on_destroy)

    def _on_destroy(self, event) -> None:
        if event.widget is self and self in THEME_TOPLEVELS:
            THEME_TOPLEVELS.remove(self)

    def apply_theme(self) -> None:
        self._force_aspect_canvas.redraw_theme()

    # --- Force Aspect Ratio two-way sync (mirrors AgentPanel's own) ----

    def _on_force_aspect_canvas_drag(self, w: int, h: int) -> None:
        self.force_aspect_w_var.set(str(w))
        self.force_aspect_h_var.set(str(h))

    def _on_force_aspect_wh_typed(self, *_args) -> None:
        try:
            w = int(self.force_aspect_w_var.get().strip())
            h = int(self.force_aspect_h_var.get().strip())
        except ValueError:
            return
        if w <= 0 or h <= 0:
            return
        self._force_aspect_canvas.set_ratio(w, h)

    def force_aspect_ratio(self) -> tuple[int, int]:
        """ValueError propagates to the caller's Start validation, same
        contract as ``AgentPanel.force_aspect_ratio``."""
        return (
            int(self.force_aspect_w_var.get()),
            int(self.force_aspect_h_var.get()),
        )

    # --- upscale gate (mirrors AgentPanel's own) ------------------------

    def upscale_params(self) -> dict:
        min_side = int(float(self.up_minside_var.get()))
        return _upscale_params_from_side_and_filter(
            min_side, self.upscale_filter.get_conditions()
        )

    def upscale_conditions(self) -> list[filters.FilterCondition]:
        return self.upscale_filter.get_conditions()

    def pace_floats(self) -> tuple[float, float]:
        """ValueError propagates to the caller's Start validation, same
        contract as ``AgentPanel.pace_floats`` (narrower here — no
        action-delay pair)."""
        return (float(self.pause_min_var.get()), float(self.pause_max_var.get()))

    # --- gating: "Check API access" probe -------------------------------

    def _probe_access(self) -> None:
        """One cheap ``generate_image`` call on a background thread —
        ``PaidFeatureRequired`` means the free tier is still exhausted
        (gates Start with ``AI_IMAGE_GATE_MESSAGE``); success clears any
        previous gate; any OTHER ``AiError`` (``NoKey``, network) is
        shown but leaves the gate exactly as it was — inconclusive, not
        proof either way. Mirrors ``AiKeyWizard._test``'s own worker
        (no ``log=`` override — the default ``print`` is enough for an
        occasional manual probe, same precedent)."""
        self._gate_btn.configure(state="disabled")
        self._gate_var.set("Checking API access …")

        def work() -> None:
            from painter import ai

            try:
                ai.generate_image(
                    AI_IMAGE_PROBE_PROMPT, model=GEMINI_IMAGE_MODEL,
                )
            except ai.PaidFeatureRequired as exc:
                self._probe_q.put(("gated", str(exc)))
            except ai.AiError as exc:
                self._probe_q.put(("error", str(exc)))
            else:
                self._probe_q.put(("ok", ""))

        threading.Thread(target=work, daemon=True).start()
        self._arm_probe_poll()

    def _arm_probe_poll(self) -> None:
        self._probe_poll_job = self.after(AI_POLL_MS, self._poll_probe)

    def _poll_probe(self) -> None:
        self._probe_poll_job = None
        if not self.winfo_exists():
            return  # closed mid-check — the worker's message is moot
        try:
            msg = self._probe_q.get_nowait()
        except queue.Empty:
            self._arm_probe_poll()
            return
        self._apply_probe_result(msg)

    def _apply_probe_result(self, msg: tuple) -> None:
        kind, text = msg
        self._gate_btn.configure(state="normal")
        if kind == "ok":
            self.access_gated = False
            self._gate_var.set("API access OK — billing is enabled.")
        elif kind == "gated":
            self.access_gated = True
            self._gate_var.set(AI_IMAGE_GATE_MESSAGE)
        else:
            self._gate_var.set(f"Check inconclusive: {text}")
        self._refresh_start_state()

    def _refresh_start_state(self) -> None:
        style_action_button(
            self.btn_start, "success",
            not self._running and not self.access_gated,
        )

    # --- run state -----------------------------------------------------

    def set_run_state(self, running: bool) -> None:
        self._running = running
        self._refresh_start_state()
        style_action_button(self.btn_stop, "danger", running)

    def set_paused(self, is_paused: bool) -> None:
        self.btn_pause.configure(text="Resume" if is_paused else "Pause")

    # --- settings round-trip --------------------------------------------
    # SAME (stored, conditions=...) shape ToolSettingsPanel.apply_settings
    # already has, so PainterGui._apply_settings's existing generic
    # "tool_panels" loop round-trips this panel with NO changes there —
    # "conditions" carries the upscale-gate filter (the ONE FilterEditor
    # this panel owns), exactly the role UpscaleSettingsPanel's own top-
    # level ``self.filter`` already plays under the same key.

    def get_settings(self) -> dict:
        return {
            "background": self.background_var.get(),
            "style": self.style_var.get(),
            "bg_removal": self.bg_removal_var.get(),
            "crop": self.crop_var.get(),
            "force_aspect": self.force_aspect_var.get(),
            "force_aspect_w": self.force_aspect_w_var.get(),
            "force_aspect_h": self.force_aspect_h_var.get(),
            "upscale": self.upscale_var.get(),
            "up_minside": self.up_minside_var.get(),
            "report": self.report_var.get(),
            "keep_all_steps": self.keep_all_steps_var.get(),
            "pause_min": self.pause_min_var.get(),
            "pause_max": self.pause_max_var.get(),
            "conditions": [
                filters.condition_to_dict(c)
                for c in self.upscale_filter.get_conditions()
            ],
        }

    def apply_settings(
        self, stored: dict,
        conditions: list[filters.FilterCondition] | None = None,
    ) -> None:
        """Missing keys keep the current defaults — same contract as
        every other panel's ``apply_settings`` in this file."""
        string_fields = (
            "background", "style", "up_minside", "force_aspect_w",
            "force_aspect_h", "pause_min", "pause_max",
        )
        for key in string_fields:
            if key in stored:
                getattr(self, f"{key}_var").set(stored[key])
        bool_fields = ("bg_removal", "crop", "force_aspect", "upscale",
                       "report", "keep_all_steps")
        for key in bool_fields:
            if key in stored:
                getattr(self, f"{key}_var").set(bool(stored[key]))
        if conditions is not None:
            self.upscale_filter.set_conditions(conditions)
        try:
            w = int(self.force_aspect_w_var.get())
            h = int(self.force_aspect_h_var.get())
            if w > 0 and h > 0:
                self._force_aspect_canvas.set_ratio(w, h)
        except ValueError:
            pass


# ---------------------------------------------------------------------
# Dashboard
# ---------------------------------------------------------------------

# the stat keys shown per scope (the 'Average' group sits between
# Refused and Tempo and collapses)
_STAT_KEYS = ("done", "refused", "total", "gen", "over", "tmin", "tmax",
              "tempo", "eta")


def _scope_stats(
    done, refused, gen_times, over_times, totals, pending, elapsed
):
    """Display strings for one scope (a collection or the whole task).

    ``totals`` are per-image AI+our seconds (only for images whose our
    time is known), so the total average / min / max are exact.
    """
    remaining = max(pending - done - refused, 0)

    def avg(xs):
        return f"{sum(xs) / len(xs):.0f} s" if xs else "—"

    if done and elapsed > 0:
        tempo = f"{done / (elapsed / 3600):.0f} /h"
        eta = (
            f"{remaining * (elapsed / done) / 60:.0f} min"
            if remaining
            else "done"
        )
    else:
        tempo = "—"
        eta = "—"
    return {
        "done": f"{done}/{pending}" if pending else str(done),
        "refused": str(refused),
        "total": avg(totals),
        "gen": avg(gen_times),
        "over": avg(over_times),
        "tmin": f"{min(totals):.0f} s" if totals else "—",
        "tmax": f"{max(totals):.0f} s" if totals else "—",
        "tempo": tempo,
        "eta": eta,
    }


# --- Status badge dots (owner 2026-07-20) ----------------------------
# Small coloured dots beside an image row's name in the gen panels'
# Collections tree — one per post-save step that actually CHANGED the
# image (config.badge_keys_for over the runner's action string), plus
# the safer-retry mark. PIL-DRAWN: Tk 8.6 on Windows renders colour
# emoji as identical monochrome circles (probed live 2026-07-20), so
# glyph badges cannot be told apart — the dots are rasterized
# supersampled + LANCZOS like all GUI art and attached as the row's
# Treeview image (the only per-row colour a ttk.Treeview offers; it
# sits LEFT of the name). Colours/labels are config data (BADGES); one
# PhotoImage per key-combination, cached for the process lifetime so
# tk can never GC a row's image.
_BADGE_DOTS: dict[tuple[str, ...], ImageTk.PhotoImage] = {}


def badge_dots(keys: tuple[str, ...]) -> ImageTk.PhotoImage | None:
    """The cached dot-strip PhotoImage for one badge-key combination —
    None when the image earned no badges (the row then carries no
    image and keeps the plain indent)."""
    if not keys:
        return None
    photo = _BADGE_DOTS.get(keys)
    if photo is None:
        ss = BADGE_DOT_SS
        d, gap = BADGE_DOT_PX * ss, BADGE_DOT_GAP_PX * ss
        strip = Image.new(
            "RGBA", (len(keys) * d + (len(keys) - 1) * gap, d), (0, 0, 0, 0)
        )
        draw = ImageDraw.Draw(strip)
        for i, key in enumerate(keys):
            x = i * (d + gap)
            draw.ellipse([x, 0, x + d - 1, d - 1], fill=BADGES[key][0])
        photo = ImageTk.PhotoImage(
            strip.resize(
                (strip.width // ss, strip.height // ss), Image.LANCZOS
            )
        )
        _BADGE_DOTS[keys] = photo
    return photo


def fmt_time_summary(times: list[float]) -> str:
    """The '⏱ Xs total · Ys/img' stat line shared by the in-place tool
    panels and the AI-check panel (Rule #5): the total op time over the
    processed images and the per-image average; '⏱ —' before anything
    has been timed."""
    if not times:
        return "⏱ —"
    total = sum(times)
    return (
        f"⏱ {fmt_op_duration(total)} total"
        f"   ·   {fmt_op_duration(total / len(times))}/img"
    )


def ai_check_doc_md(
    rel: str, defects: list[str] | None, raw: str | None
) -> str:
    """The DocWindow markdown for one AI-checked image (owner
    2026-07-21): the name + path, the parsed defects (when any) AND the
    VERBATIM raw model response under 'Full AI response:' — so the owner
    sees EXACTLY what the vision model said, not only the parsed
    bullets. The raw goes in a code fence (rendered monospace,
    verbatim). SHARED (GUI rework Phase 16, Rule #5): both
    ``AiCheckPanel``'s own double-click viewer and ``DashPanel``'s
    per-row 'Check…' report viewer call this SAME function, so the two
    surfaces can never render a checked image's report differently."""
    parts = [f"# {PurePosixPath(rel).name}\n", f"`{rel}`\n"]
    if defects:
        bullets = "\n".join(f"- {d}" for d in defects)
        parts.append(f"**AI-flagged defects:**\n\n{bullets}\n")
    if raw is not None:
        parts.append(f"**Full AI response:**\n\n```\n{raw.strip()}\n```\n")
    return "\n".join(parts)


def ai_check_image_file(rel: str, out_base: Path) -> Path:
    """The image file behind one flag key — the SAME round-trip the
    checker's ``flag_key`` reverses (``ai.flag_file``), so a report
    viewer can never open a different image than the one that was
    actually checked. SHARED (GUI rework Phase 16, promoted from
    ``AiCheckPanel``'s own private ``_file_for``, Rule #5): both
    ``AiCheckPanel`` and ``DashPanel``'s per-row 'Check…' viewer
    resolve through this ONE function."""
    from painter import ai

    return ai.flag_file(rel, out_base)


def ai_check_tag(kind: str) -> str:
    """The Treeview status TAG for one checked image's 'kind'
    ('flagged'/'ok'/'error') — SHARED (GUI rework Phase 16, Rule #5) by
    ``AiCheckPanel``'s own defect rows and ``DashPanel``'s per-image
    check-status column, so a flagged image pops the same striking
    colour in both views. Only 'flagged' needs attention (the bright
    CHANGED tag); 'ok' and 'error' both stay muted (SKIP) — the actual
    wording ("OK" vs "error"/"!") already tells them apart, no separate
    colour is needed for that distinction."""
    return TOOL_CHANGED_TAG if kind == "flagged" else TOOL_SKIP_TAG


def build_job_tree(panel, col_specs, height: int = 8) -> ttk.Treeview:
    """The rowed table a job panel shows (ToolPanel + AiCheckPanel —
    Rule #5, one home for the identical plumbing): a Treeview with the
    given ``(id, heading, width, anchor)`` value columns, round v/h
    scrollbars in a grid-managed wrap, and the theme-following row tags
    (skin_tree). The caller keeps the column ids and binds its own
    double-click."""
    wrap = ttk.Frame(panel)
    wrap.pack(fill="both", expand=True, pady=(2, 0))
    tree = ttk.Treeview(
        wrap, columns=tuple(c[0] for c in col_specs), height=height
    )
    tree.heading("#0", text="Name")
    tree.column("#0", width=200, minwidth=120, stretch=False)
    for cid, txt, w, anc in col_specs:
        tree.heading(cid, text=txt)
        tree.column(cid, width=w, minwidth=w, anchor=anc, stretch=False)
    vsb = ttk.Scrollbar(
        wrap, orient="vertical", command=tree.yview, bootstyle="round",
    )
    hsb = ttk.Scrollbar(
        wrap, orient="horizontal", command=tree.xview, bootstyle="round",
    )
    tree.configure(yscrollcommand=vsb.set, xscrollcommand=hsb.set)
    tree.grid(row=0, column=0, sticky="nsew")
    vsb.grid(row=0, column=1, sticky="ns")
    hsb.grid(row=1, column=0, sticky="ew")
    wrap.rowconfigure(0, weight=1)
    wrap.columnconfigure(0, weight=1)
    # the CHANGED/SKIPPED row tags follow the active theme's status
    # colours and re-tint on a flip (the plain-tk skin registry)
    skin_tree(tree)
    return tree


class JobPanel(ttk.Frame):
    """Base for a per-JOB dashboard panel — a generation site or an
    in-place tool.

    Owns the coloured header (an SVG logo for the two gen sites / an
    emoji for the four tools, plus the job NAME in the job colour), the
    muted state line (the quota countdown / current item), and the
    CLOSE button that is hidden until the job FINISHES and then removes
    the panel. The body (progress / stats / table) is built by the
    subclass. A panel appears when its job STARTS and disappears when
    the owner clicks CLOSE (owner 2026-07-19: only running-or-ran jobs
    show). For the FOLDER-BASED panels (ToolPanel, AiCheckPanel) it
    also carries the shared root/folder tree-node plumbing — those
    subclasses own ``self.tree``/``self._cols``/``self.folder`` and the
    per-run node dicts; DashPanel builds its own theme-based nodes and
    never calls these.
    """

    def __init__(
        self, master, kind: str, on_show=None, on_close=None, on_pause=None,
    ):
        super().__init__(master, padding=6)
        self.slot_key = kind
        self._on_show = on_show   # called with a node-info dict on 'Show'
        self._on_close = on_close  # called with the slot key on CLOSE
        self._on_pause = on_pause  # called with the slot key on Pause/Resume
        self._finished = False
        self._node_info: dict[str, dict] = {}  # tree item id -> info
        # every job kind CAN carry a per-step backup store (the four
        # tools always have; the two gen sites since GUI rework Phase
        # 8) — shared here (Rule #5) so DashPanel/ToolPanel both gain
        # it identically instead of each redeclaring the same line;
        # AiCheckPanel simply never populates it. Set by the caller at
        # job start (_launch_tool_worker / _start_site), None otherwise.
        self.jobtemp: "jobtemp.JobTemp | None" = None
        self._build_header(kind)

    def _build_header(self, kind: str) -> None:
        header = ttk.Frame(self)
        header.pack(fill="x")
        # every job — gen site or tool — carries an icon (its
        # config.JOB_LOGO stem, resolved to an svg/png by icon()) beside
        # the coloured job NAME. The four tools got dedicated PNG icons
        # (owner 2026-07-19), replacing the old emoji marks.
        ctk.CTkLabel(
            header, text="", image=icon(JOB_LOGO[kind]), width=24,
            fg_color="transparent", bg_color=theme_pair("bg"),
        ).pack(side="left", padx=(0, 6))
        ctk.CTkLabel(
            header, text=JOB_LABEL[kind], font=ctk_font("title"),
            text_color=job_color_pair(kind),
            fg_color="transparent", bg_color=theme_pair("bg"),
        ).pack(side="left")
        # revealed by finish(); removes the panel + clears its temp
        self._close_btn = rounded_button(
            header, "✕ Close", command=self._do_close,
            kind="danger-outline", width=76,
        )
        # a folder-based job (ToolPanel / AiCheckPanel) owns its OWN
        # pause toggle here, beside Close (owner 2026-07-21) — the two
        # gen sites' button lives on AgentPanel instead, so on_pause
        # stays None for DashPanel and this button is never built there.
        self.btn_pause: ctk.CTkButton | None = None
        if self._on_pause is not None:
            self.btn_pause = rounded_button(
                header, "Pause", command=partial(self._on_pause, kind),
                kind="secondary", width=70,
            )
            self.btn_pause.pack(side="right", padx=(0, 6))

        # the state line — quota auto-restart countdown / current item
        # / paused
        self.state_var = tk.StringVar(value="")
        self._state_label = ttk.Label(
            self, textvariable=self.state_var, style="Muted.TLabel"
        )
        self._state_label.pack(anchor="w")

        # a LOUD, PERSISTENT warning strip (GUI rework Phase 8) — unlike
        # state_var above (MUTED, overwritten by the very next progress
        # event — see set_paused's own docstring), this stays up until
        # something explicitly hides it again (reset() on a fresh run).
        # Built here so its pack POSITION (right after the state line,
        # via after=self._state_label) is fixed no matter what a
        # subclass packs later, but left UNPACKED at construction — a
        # solid "inverse-warning" fill with empty text would still paint
        # a bare colour bar on every panel. Today only DashPanel ever
        # shows it (a site job's JobTemp crossing its backup cap — see
        # DashPanel.handle's "over_cap" branch); the four standalone
        # tools have no per-step backups to cap (Phase 8 scope).
        self._cap_banner_var = tk.StringVar(value="")
        self._cap_banner = ttk.Label(
            self, textvariable=self._cap_banner_var,
            bootstyle="inverse-warning", anchor="w", padding=4,
            wraplength=JOB_PANEL_BANNER_WRAP_PX,
        )

    def _show_cap_banner(self, text: str) -> None:
        """Show (or update the text of) the persistent warning strip.
        Idempotent — Tk's pack() just re-configures an already-mapped
        widget in place, so a repeat call never re-stacks it."""
        self._cap_banner_var.set(text)
        self._cap_banner.pack(fill="x", pady=(2, 0), after=self._state_label)

    def _hide_cap_banner(self) -> None:
        self._cap_banner.pack_forget()
        self._cap_banner_var.set("")

    def finish(self) -> None:
        """The job ended — reveal the CLOSE button."""
        if self._finished:
            return
        self._finished = True
        self._close_btn.pack(side="right")

    def reset_finished(self) -> None:
        """Hide the CLOSE button again (a slot reused for a new run)."""
        self._finished = False
        self._close_btn.pack_forget()

    def set_paused(self, is_paused: bool) -> None:
        """Reflect a pause toggle (owner 2026-07-21): the muted state
        line (every JobPanel has one) and, for a panel that owns a
        btn_pause (ToolPanel / AiCheckPanel — the two gen sites' button
        lives on AgentPanel instead, see AgentPanel.set_paused), its
        Pause/Resume label. The next real progress event (item_start /
        sheet_done) naturally overwrites the state line once the job is
        running or finished again."""
        if self.btn_pause is not None:
            self.btn_pause.configure(text="Resume" if is_paused else "Pause")
        self.state_var.set("paused — waiting to resume" if is_paused else "")

    def _do_close(self) -> None:
        if self._on_close is not None:
            self._on_close(self.slot_key)

    # --- shared folder>image tree nodes (ToolPanel + AiCheckPanel) -----

    def _ensure_root(self) -> str:
        if self._tree_root is None:
            name = self.folder.name if self.folder else JOB_LABEL[self.slot_key]
            self._tree_root = self.tree.insert(
                "", "end", text=f"{name}   · {JOB_LABEL[self.slot_key]}",
                open=True, values=("",) * len(self._cols),
            )
            self._node_info[self._tree_root] = {"level": "collection"}
        return self._tree_root

    def _ensure_folder(self, folder: str) -> str:
        node = self._folder_nodes.get(folder)
        if node is None:
            node = self.tree.insert(
                self._ensure_root(), "end", text=folder, open=True,
                values=("",) * len(self._cols),
            )
            self._folder_nodes[folder] = node
            self._node_info[node] = {"level": "folder", "folder": folder}
        return node


class DashPanel(JobPanel):
    """One generation site's live view: current collection, whole-task
    totals, timings and the collections history table.

    Driven by structured events on the main thread — the runner's own
    (``item_progress``/``item_done``/...) PLUS, since GUI rework Phase
    16, the parallel Checker AI's ``item_checking``/``item_checked``
    (posted by ``PainterGui._maybe_spawn_checker``/``_run_checker_one``
    onto the SAME worker queue, never by the runner itself) — every
    event still funnels through the identical ``handle(event)`` entry
    point regardless of which thread ultimately produced it.
    """

    def __init__(self, master, kind: str, on_show=None, on_close=None):
        super().__init__(master, kind, on_show=on_show, on_close=on_close)
        self._name = JOB_LABEL[kind]
        # this site's output root (GUI rework Phase 9) — mirrors
        # ToolPanel.folder's role: paired with self.jobtemp (JobPanel
        # base) to resolve a row's site-agnostic drop path into the
        # JobTemp rel (dest_for) and the live file on disk. Set by
        # _start_site alongside self.jobtemp, right before reset().
        self.out_base: Path | None = None

        # whole-task progress
        task = ttk.Frame(self)
        task.pack(fill="x", pady=(6, 2))
        ttk.Label(task, text="Task", width=7).pack(side="left")
        self.task_prog_var = tk.StringVar(value="0 / 0")
        ttk.Label(
            task, textvariable=self.task_prog_var, style="Value.TLabel"
        ).pack(side="right")
        self.task_bar = ttk.Progressbar(
            self, bootstyle="success-striped", maximum=1, value=0
        )
        self.task_bar.pack(fill="x", pady=(0, 6))

        # current theme + image + its own bar
        cur = ttk.Frame(self)
        cur.pack(fill="x")
        ttk.Label(cur, text="File:", width=7).grid(row=0, column=0, sticky="w")
        self.theme_name_var = tk.StringVar(value="—")
        ttk.Label(cur, textvariable=self.theme_name_var).grid(
            row=0, column=1, sticky="w"
        )
        ttk.Label(cur, text="Image:", width=7).grid(row=1, column=0, sticky="w")
        self.image_var = tk.StringVar(value="—")
        ttk.Label(cur, textvariable=self.image_var).grid(
            row=1, column=1, sticky="w"
        )
        cur.columnconfigure(1, weight=1)
        self.theme_bar = ttk.Progressbar(
            self, bootstyle="info-striped", maximum=1, value=0
        )
        self.theme_bar.pack(fill="x", pady=(2, 6))

        # the two-scope stats table: Done, Refused, a collapsible
        # 'Average' group (total avg + the AI/processing/min/max
        # breakdown), then Tempo and ETA
        grid = ttk.Frame(self)
        grid.pack(fill="x", pady=(2, 6))
        self.cells: dict[tuple[str, str], tk.StringVar] = {}

        def value_cells(r, key, muted=False):
            for c, scope in ((1, "theme"), (2, "task")):
                var = tk.StringVar(value="—")
                self.cells[(scope, key)] = var
                ttk.Label(
                    grid, textvariable=var,
                    style="" if muted else "Value.TLabel", anchor="e",
                ).grid(row=r, column=c, sticky="e", padx=4)

        def plain_row(r, label, key):
            ttk.Label(grid, text=label).grid(row=r, column=0, sticky="w")
            value_cells(r, key)

        ttk.Label(grid, text="", width=16).grid(row=0, column=0)
        ttk.Label(grid, text="This one", style="Head.TLabel", width=10).grid(
            row=0, column=1, sticky="e"
        )
        ttk.Label(grid, text="Whole run", style="Head.TLabel", width=10).grid(
            row=0, column=2, sticky="e"
        )
        plain_row(1, "Done", "done")
        plain_row(2, "Refused", "refused")

        # the collapsible Average header (its value is the total avg)
        self._avg_open = False
        self._avg_btn = rounded_button(
            grid, "", command=self._toggle_avg, kind="expander"
        )
        self._avg_btn.grid(row=3, column=0, sticky="w")
        value_cells(3, "total")

        self._avg_rows: list[list] = []
        for i, (key, label) in enumerate((
            ("gen", "     AI generation"),
            ("over", "     Our processing"),
            ("tmin", "     Minimum"),
            ("tmax", "     Maximum"),
        )):
            r = 4 + i
            widgets = [ttk.Label(grid, text=label, style="Muted.TLabel")]
            widgets[0].grid(row=r, column=0, sticky="w")
            for c, scope in ((1, "theme"), (2, "task")):
                var = tk.StringVar(value="—")
                self.cells[(scope, key)] = var
                w = ttk.Label(grid, textvariable=var, anchor="e")
                w.grid(row=r, column=c, sticky="e", padx=4)
                widgets.append(w)
            self._avg_rows.append(widgets)

        plain_row(8, "Tempo", "tempo")
        plain_row(9, "ETA", "eta")
        grid.columnconfigure(0, weight=1)
        self._render_avg_btn()
        self._collapse_avg()

        ttk.Separator(self).pack(fill="x", pady=4)
        hdr = ttk.Frame(self)
        hdr.pack(fill="x")
        ttk.Label(
            hdr, text="Collections (running + done)", style="Head.TLabel"
        ).pack(side="left")
        rounded_button(
            hdr, "Show", command=self._show_selected, kind="link",
            icon_name="right", compound="right",
        ).pack(side="right")
        # the per-step restore filmstrip (GUI rework Phase 9) — a
        # SEPARATE button from 'Show' above (same focused-row idiom,
        # never overloaded onto the tree's own double-click, which
        # stays wired to _show_selected/'Show prompt + image'). No
        # dedicated icon exists yet for "restore a pipeline stage", so
        # this is plain text (flagged in the phase report).
        rounded_button(
            hdr, "Steps…", command=self._show_steps, kind="link",
        ).pack(side="right", padx=(0, 6))
        # the parallel Checker AI's per-row report (GUI rework Phase
        # 16) — a THIRD separate surface from 'Show' (prompt+image) and
        # 'Steps…' (pipeline restore), same focused-row idiom, never
        # overloaded onto either (mirrors _show_steps's own reasoning)
        rounded_button(
            hdr, "Check…", command=self._show_check, kind="link",
        ).pack(side="right", padx=(0, 6))
        # the tiny badge legend — one ●+label per config.BADGES entry,
        # each in its own badge colour (theme-agnostic mid-tones, so ONE
        # explicit foreground reads on both the dark and the cream tree)
        legend = ttk.Frame(self)
        legend.pack(fill="x")
        for _key, (color, label) in BADGES.items():
            ttk.Label(
                legend, text=f"● {label}", foreground=color,
                font=tk_font("mono"),
            ).pack(side="left", padx=(0, 10))
        # a real table: each collection is a collapsible parent row, its
        # images the children; the running one shows live, open. Native
        # column headers + both scrollbars
        wrap = ttk.Frame(self)
        wrap.pack(fill="both", expand=True, pady=(2, 0))
        # three levels: collection > folder > image. Aggregate rows
        # (collection, folder) fill Done/Time/Size; image rows fill
        # AI/Ours/Res/Size. Everything stays column-aligned.
        cols = ("done", "ai", "our", "res", "time", "size", "check")
        self.tree = ttk.Treeview(wrap, columns=cols, height=8)
        self.tree.heading("#0", text="Name")
        # stretch=False EVERYWHERE: widening Name grows the tree's
        # total content width and the horizontal scrollbar takes over,
        # instead of squeezing the other columns
        self.tree.column("#0", width=230, minwidth=140, stretch=False)
        for cid, txt, w, anc in (
            ("done", "Done", 56, "center"),
            ("ai", "AI", 52, "e"),
            ("our", "Ours", 52, "e"),
            ("res", "Res", 100, "center"),
            ("time", "Time", 64, "e"),
            ("size", "Size", 72, "e"),
            # the parallel Checker AI's per-image status (GUI rework
            # Phase 16) — "checking…" / "OK" / "flagged N" / "error",
            # blank for a site where the checker never ran
            ("check", "Check", DASH_CHECK_COL_PX, "center"),
        ):
            self.tree.heading(cid, text=txt)
            self.tree.column(cid, width=w, minwidth=w, anchor=anc,
                             stretch=False)
        vsb = ttk.Scrollbar(
            wrap, orient="vertical", command=self.tree.yview,
            bootstyle="round",
        )
        hsb = ttk.Scrollbar(
            wrap, orient="horizontal", command=self.tree.xview,
            bootstyle="round",
        )
        self.tree.configure(yscrollcommand=vsb.set, xscrollcommand=hsb.set)
        self.tree.grid(row=0, column=0, sticky="nsew")
        vsb.grid(row=0, column=1, sticky="ns")
        hsb.grid(row=1, column=0, sticky="ew")
        wrap.rowconfigure(0, weight=1)
        wrap.columnconfigure(0, weight=1)
        self.tree.bind("<Double-1>", lambda _e: self._show_selected())

        self.reset(active=False)

    def _show_selected(self) -> None:
        info = self._node_info.get(self.tree.focus())
        if info and self._on_show is not None:
            self._on_show(info)

    # --- per-step restore viewer (GUI rework Phase 9) -------------------

    def _show_steps(self) -> None:
        """The 'Steps…' button: open the per-step restore filmstrip for
        the SAME focused/selected row 'Show' above would use. Fully
        self-contained (mirrors ToolPanel's own before/after viewer,
        which likewise never routes through an on_show-style callback)
        — resolves the site-specific rel via dest_for and opens
        StepRestoreWindow directly."""
        info = self._node_info.get(self.tree.focus())
        if not info or info["level"] != "image":
            messagebox.showinfo(
                "PromptPainter",
                "Select one image row first — Steps shows the pipeline"
                " history of a single saved image.",
            )
            return
        if self.jobtemp is None or self.out_base is None:
            messagebox.showinfo(
                "PromptPainter", "No per-step history for this run yet.",
            )
            return
        rel = dest_for(info["drop"], self.slot_key)
        if not self.jobtemp.steps_for(rel):
            messagebox.showinfo(
                "PromptPainter",
                "No kept pipeline stages for this image — either no"
                " post-save step ran, or 'Keep every pipeline step' was"
                " off for this run.",
            )
            return
        StepRestoreWindow(
            self.winfo_toplevel(), f"Steps — {PurePosixPath(rel).name}",
            self.jobtemp, rel, self.out_base / rel,
            on_restored=partial(self.refresh_image_row, info["drop"]),
        )

    # --- the parallel Checker AI's per-row report (GUI rework Phase 16) -

    def _show_check(self) -> None:
        """The 'Check…' button: the SAME report a checker batch row's
        double-click shows (``ai_check_doc_md`` + ``ai_check_image_file``
        — the shared module-level helpers, Rule #5), for the focused
        row's PARALLEL check result. A separate surface from 'Show'
        (prompt+image) and 'Steps…' (pipeline restore) — never
        overloaded onto either, same reasoning as ``_show_steps``.
        ``_check_results`` outlives a single collection (cleared only by
        ``reset()``, unlike ``_child_ids`` — see its own assignment in
        ``reset()``), so this works for any past row in the current run,
        not only the one just checked."""
        info = self._node_info.get(self.tree.focus())
        if not info or info["level"] != "image":
            messagebox.showinfo(
                "PromptPainter",
                "Select one image row first — Check shows the AI"
                " checker's report for a single saved image.",
            )
            return
        result = self._check_results.get(info["drop"])
        if result is None:
            messagebox.showinfo(
                "PromptPainter",
                "No AI check for this image — turn on this site's 'AI"
                " checker' switch before Start, or it has not finished"
                " checking this one yet.",
            )
            return
        rel = result["rel"]
        defects = result.get("defects")
        raw = result.get("raw")
        md = ai_check_doc_md(rel, defects, raw)
        image = ai_check_image_file(rel, self.out_base or Path("."))
        DocWindow(
            self.winfo_toplevel(), rel, md,
            copy_text=raw if raw is not None else "\n".join(defects or []),
            hint="Exactly what the vision model reported for this image.",
            image_path=image if image.is_file() else None,
        )

    def refresh_image_row(self, drop: str) -> None:
        """Re-read ONE row's resolution/size straight off disk — the
        per-step viewer's refresh after a 'Restore to here' click.
        Badge dots are NOT retroactively recomputed here (no per-row
        action string survives past insert, only the rendered PIL
        dots) — a known cosmetic gap; the restored FILE itself is
        always correct regardless of what its dots still show."""
        child = self._child_ids.get(drop)
        if child is None or self.out_base is None:
            return
        live_path = self.out_base / dest_for(drop, self.slot_key)
        try:
            with Image.open(live_path) as img:
                res = f"{img.width}x{img.height}"
            size = live_path.stat().st_size
        except OSError:
            return
        self.tree.set(child, "res", res)
        self.tree.set(child, "size", fmt_size(size))

    # --- the collapsible Average group ---------------------------------

    def _render_avg_btn(self) -> None:
        self._avg_btn.configure(
            text=("▼  Average" if self._avg_open else "▶  Average")
        )

    def _expand_avg(self) -> None:
        for widgets in self._avg_rows:
            for w in widgets:
                w.grid()

    def _collapse_avg(self) -> None:
        for widgets in self._avg_rows:
            for w in widgets:
                w.grid_remove()

    def _toggle_avg(self) -> None:
        self._avg_open = not self._avg_open
        (self._expand_avg if self._avg_open else self._collapse_avg)()
        self._render_avg_btn()

    # --- state ---------------------------------------------------------

    def reset(
        self, active: bool = True, task_total: int = 0, task_themes: int = 0
    ) -> None:
        self.reset_finished()  # a fresh run hides the CLOSE button again
        self._hide_cap_banner()  # a fresh run starts with a clean slate
        now = time.monotonic()
        self._task_total = task_total
        self._task_themes = task_themes
        self._task_done = 0
        self._task_refused = 0
        self._task_themes_done = 0
        self._task_gen: list[float] = []
        self._task_over: list[float] = []
        self._task_totals: list[float] = []
        self._t_task = now
        self._new_theme("—", 0)
        self.tree.delete(*self.tree.get_children())
        self._node_info.clear()
        # the parallel Checker AI's results (GUI rework Phase 16) — rel
        # + drop_path -> the full item_checked event, so 'Check…' can
        # open ANY past row's report. Scoped like _node_info (the WHOLE
        # run), NOT like _child_ids (reset every collection, see
        # _new_theme) — a late checker result must stay reachable even
        # after the run has moved on to the next collection.
        self._check_results: dict[str, dict] = {}
        self.task_prog_var.set(f"0 / {task_total}")
        self.task_bar.configure(maximum=max(task_total, 1), value=0)
        self.theme_name_var.set("—")
        self.image_var.set("running ..." if active else "idle")
        self.theme_bar.configure(maximum=1, value=0)
        self._refresh()

    def _new_theme(self, name: str, pending: int) -> None:
        self._theme_name = name
        self._theme_pending = pending
        self._theme_done = 0
        self._theme_refused = 0
        self._theme_gen: list[float] = []
        self._theme_over: list[float] = []
        self._theme_totals: list[float] = []
        self._theme_bytes = 0
        self._theme_folders: set[str] = set()
        self._t_theme = time.monotonic()
        # the collection's live row appears on its first image (lazily,
        # so fully-resumed collections never add an empty row); folders
        # nest under it, images under their folder
        self._tree_item: str | None = None
        self._folder_nodes: dict[str, str] = {}  # folder -> tree row id
        self._folder_stats: dict[str, dict] = {}  # folder -> agg dict
        self._child_ids: dict[str, str] = {}  # drop_path -> tree row id

    # --- events (main thread, via the queue pump) ----------------------

    def handle(self, event: dict) -> None:
        kind = event["type"]
        if kind == "sheet_start":
            self._new_theme(event["sheet"], event["pending"])
            self.theme_name_var.set(
                f"{event['sheet']}  ({event['pending']} pending)"
            )
            self.theme_bar.configure(maximum=max(event["pending"], 1), value=0)
        elif kind == "item_start":
            self.image_var.set(
                f"({event['idx']}/{event['of']}) {event['title'][:50]}"
            )
        elif kind == "item_progress":
            # the image is saved — count it live AND add it to the table
            # under its FOLDER now (our-time fills in at item_done)
            self._theme_done += 1
            self._task_done += 1
            self._theme_gen.append(event["gen_s"])
            self._task_gen.append(event["gen_s"])
            self._theme_bytes += event["size"]
            drop = event["drop_path"]
            folder = folder_of(drop)
            self._theme_folders.add(folder)
            fnode = self._ensure_folder(folder)
            st = self._folder_stats[folder]
            st["done"] += 1
            st["size"] += event["size"]
            res = event["orig_res"]
            if event["final_res"] not in ("", event["orig_res"]):
                res = f"{event['orig_res']}→{event['final_res']}"
            # the status badges this image EARNED (post-save steps that
            # really changed it + the safer retry) as a PIL dot strip on
            # the row — badge_keys_for maps the runner's action string
            dots = badge_dots(
                badge_keys_for(event["actions"], event["retried"])
            )
            child = self.tree.insert(
                fnode, "end", text=PurePosixPath(drop).name,
                values=(
                    "", f"{event['gen_s']:.0f}s", "…", res, "",
                    fmt_size(event["size"]), "",
                ),
                **({"image": dots} if dots is not None else {}),
            )
            self._child_ids[drop] = child
            self._node_info[child] = {
                "level": "image", "sheet": self._theme_name, "drop": drop,
            }
            self._update_folder(folder)
            self._update_parent()
        elif kind == "item_done":
            # our-time known now — fill the image's column + folder time
            over = event["over_s"]
            total = event["gen_s"] + over
            self._theme_over.append(over)
            self._task_over.append(over)
            self._theme_totals.append(total)
            self._task_totals.append(total)
            drop = event["drop_path"]
            child = self._child_ids.get(drop)
            if child is not None:
                self.tree.set(child, "our", f"{over:.0f}s")
            folder = folder_of(drop)
            st = self._folder_stats.get(folder)
            if st is not None:
                st["time"] += event["gen_s"] + over
                self._update_folder(folder)
        elif kind == "item_refused":
            self._theme_refused += 1
            self._task_refused += 1
            drop = event.get("drop_path", "")
            fnode = self._ensure_folder(folder_of(drop))
            rnode = self.tree.insert(
                fnode, "end", text=PurePosixPath(drop).name or "refused",
                values=("", "", "", "REFUSED", "", "", ""),
            )
            if drop:
                self._node_info[rnode] = {
                    "level": "image", "sheet": self._theme_name, "drop": drop,
                }
            self._update_parent()
        elif kind == "item_retry":
            self.image_var.set(self.image_var.get() + "  (safer retry…)")
        elif kind == "item_nudge":
            self.image_var.set(self.image_var.get() + "  (continue nudge…)")
        elif kind == "item_checking":
            # the parallel Checker AI (GUI rework Phase 16) just started
            # for this row — posted SYNCHRONOUSLY by PainterGui.
            # _maybe_spawn_checker (main thread, right after item_progress
            # creates the row), never through the worker queue, so it
            # always lands before the background thread's own eventual
            # item_checked.
            child = self._child_ids.get(event["drop_path"])
            if child is not None:
                self.tree.set(child, "check", "checking…")
        elif kind == "item_checked":
            # the background checker thread's result (ai.check_one_image,
            # via PainterGui._run_checker_one) — kind is 'flagged'/'ok'/
            # 'error' (ai.NoKey/AiError already turned into 'error' by
            # check_one_image itself, or by _run_checker_one's own outer
            # safety net; Rule #1: loud on the row, never fatal to this
            # run). Stored in _check_results REGARDLESS of whether the
            # row is still reachable via _child_ids (a late result after
            # the collection moved on) — see _check_results' own comment
            # in reset().
            drop = event["drop_path"]
            self._check_results[drop] = event
            child = self._child_ids.get(drop)
            if child is not None:
                check_kind = event["kind"]
                if check_kind == "flagged":
                    text = f"flagged {len(event['defects'])}"
                elif check_kind == "error":
                    text = "error"
                else:
                    text = "OK"
                self.tree.set(child, "check", text)
                self.tree.item(child, tags=(ai_check_tag(check_kind),))
        elif kind == "sheet_done":
            self._finalize_theme()
            self.image_var.set("—")
        elif kind == "over_cap":
            # this site's JobTemp crossed JOBTEMP_MAX_BYTES (GUI rework
            # Phase 8) — per-step backups have stopped, original-only
            # from here on; LOUD and PERSISTENT (unlike every branch
            # above, which only ever touches the muted state_var/tree),
            # so it survives every later progress event until reset().
            self._show_cap_banner(JOBTEMP_CAP_BANNER_TEXT)
        self._refresh()

    def _ensure_parent(self) -> str:
        """The collection's row — created (open) the first time an image
        of it lands, so a running collection shows live."""
        if self._tree_item is None:
            name = f"{self._theme_name}   · running…"
            self._tree_item = self.tree.insert(
                "", "end", text=name, open=True,
                values=self._parent_values(),
            )
            self._node_info[self._tree_item] = {
                "level": "collection", "sheet": self._theme_name,
            }
        return self._tree_item

    def _ensure_folder(self, folder: str) -> str:
        node = self._folder_nodes.get(folder)
        if node is None:
            parent = self._ensure_parent()
            self._folder_stats[folder] = {"done": 0, "size": 0, "time": 0.0}
            node = self.tree.insert(
                parent, "end", text=folder, open=True,
                values=("0", "", "", "", "", fmt_size(0), ""),
            )
            self._folder_nodes[folder] = node
            self._node_info[node] = {
                "level": "folder", "sheet": self._theme_name,
                "folder": folder,
            }
        return node

    def _parent_values(self) -> tuple:
        wall = time.monotonic() - self._t_theme
        return (
            f"{self._theme_done}/{self._theme_pending}", "", "", "",
            fmt_duration(wall), fmt_size(self._theme_bytes), "",
        )

    def _update_parent(self) -> None:
        if self._tree_item is not None:
            self.tree.item(self._tree_item, values=self._parent_values())

    def _update_folder(self, folder: str) -> None:
        node = self._folder_nodes.get(folder)
        st = self._folder_stats.get(folder)
        if node is not None and st is not None:
            self.tree.item(
                node,
                values=(
                    str(st["done"]), "", "", "",
                    fmt_duration(st["time"]), fmt_size(st["size"]), "",
                ),
            )

    def _finalize_theme(self) -> None:
        if self._tree_item is None:
            return  # nothing ran this collection (fully resumed / skipped)
        self._task_themes_done += 1
        # stamp the final summary and collapse the finished collection
        self.tree.item(
            self._tree_item, text=self._theme_name,
            values=self._parent_values(), open=False,
        )

    def _refresh(self) -> None:
        now = time.monotonic()
        # bars
        self.theme_bar.configure(
            maximum=max(self._theme_pending, 1),
            value=self._theme_done + self._theme_refused,
        )
        self.task_bar.configure(
            maximum=max(self._task_total, 1),
            value=self._task_done + self._task_refused,
        )
        self.task_prog_var.set(
            f"{self._task_done + self._task_refused} / {self._task_total}"
            f"   ({self._task_themes_done}/{self._task_themes} done)"
        )
        theme = _scope_stats(
            self._theme_done, self._theme_refused, self._theme_gen,
            self._theme_over, self._theme_totals, self._theme_pending,
            now - self._t_theme,
        )
        task = _scope_stats(
            self._task_done, self._task_refused, self._task_gen,
            self._task_over, self._task_totals, self._task_total,
            now - self._t_task,
        )
        for key in _STAT_KEYS:
            self.cells[("theme", key)].set(theme[key])
            self.cells[("task", key)].set(task[key])


def _checkerboard(w: int, h: int) -> Image.Image:
    """A neutral light/dark checkerboard the size WxH — the transparency
    backdrop so a removed (transparent) background reads as removed, not
    as the panel colour."""
    tile = CHECKER_TILE_PX
    board = Image.new("RGB", (w, h), CHECKER_LIGHT)
    dark = Image.new("RGB", (tile, tile), CHECKER_DARK)
    for y in range(0, h, tile):
        for x in range(0, w, tile):
            if ((x // tile) + (y // tile)) % 2:
                board.paste(dark, (x, y))
    return board


def _has_alpha(img: Image.Image) -> bool:
    """Whether an image carries transparency (RGBA/LA, or a palette with
    a transparency entry)."""
    return img.mode in ("RGBA", "LA") or (
        img.mode == "P" and "transparency" in img.info
    )


def _scaled_photo(
    path: Path, avail_px: int, on_checker: bool = False
) -> ImageTk.PhotoImage:
    """One image loaded and scaled to fit ``avail_px`` wide (never
    upscaled), as a live PhotoImage the caller must keep a ref to.
    Shared by DocWindow's prompt image and the BeforeAfterWindow viewer
    (Rule #5). With ``on_checker`` a transparent image is composited over
    a checkerboard so the transparency is VISIBLE (the tool viewer's
    AFTER — a cleared background — otherwise shows the panel colour and
    looks unchanged). Raises OSError on an unreadable file (the caller
    reports it)."""
    img = Image.open(path)
    img.load()
    if img.width > avail_px:
        scale = avail_px / img.width
        img = img.resize(
            (avail_px, max(round(img.height * scale), 1)), Image.LANCZOS
        )
    if on_checker and _has_alpha(img):
        rgba = img.convert("RGBA")
        board = _checkerboard(rgba.width, rgba.height)
        board.paste(rgba, (0, 0), rgba)  # alpha-composite the subject over it
        img = board
    return ImageTk.PhotoImage(img)


class ToolPanel(JobPanel):
    """One in-place tool's live view (BG removal / Crop / Upscale /
    Aspect ratio): a progress bar, an aggregate metric label, and a
    collection > folder > image table where each image row shows its
    BEFORE / AFTER resolution and the tool's own % (removed / reduction
    / increase / deformation).

    CHANGED (restorable) rows show in a striking green/teal; SKIPPED
    (unchanged) rows in muted grey. Double-click an image row for a
    BEFORE/AFTER viewer with Restore; double-click a FOLDER node for a
    viewer of ONLY that folder's changed images with RESTORE ALL; double-
    click the collection (top) node for ALL the job's changed images. The
    job's originals are backed up per file (``self.jobtemp``) before the
    op, so a restore always puts the original back.
    """

    def __init__(self, master, kind: str, on_close=None, on_pause=None):
        super().__init__(
            master, kind, on_show=None, on_close=on_close, on_pause=on_pause,
        )
        self._metric_name = JOB_METRIC[kind]
        self.folder: Path | None = None       # the picked folder
        # self.jobtemp: painter.jobtemp.JobTemp | None — inherited from
        # JobPanel (shared with DashPanel, GUI rework Phase 9)

        self.prog = ttk.Progressbar(
            self, bootstyle="info-striped", maximum=1, value=0
        )
        self.prog.pack(fill="x", pady=(6, 4))
        self.metric_var = tk.StringVar(value="—")
        ttk.Label(
            self, textvariable=self.metric_var, style="Value.TLabel"
        ).pack(anchor="w", pady=(0, 2))
        # execution time — total over PROCESSED images + per-image average
        # (skipped images contribute no time), mirroring the gen panels
        self.time_var = tk.StringVar(value="⏱ —")
        ttk.Label(
            self, textvariable=self.time_var, style="Muted.TLabel"
        ).pack(anchor="w", pady=(0, 4))

        # BG removal changes ALPHA, not dimensions — its Before/After
        # resolution are always identical and meaningless, so its panel
        # DROPS those two columns (owner 2026-07-19); the dimensional
        # tools (crop / upscale / aspect) keep them.
        self._is_bg = kind == "bg"
        metric_cols = (
            ("pct", "%", 72 if self._is_bg else 64, "e"),
            ("time", "Time", 64, "e"),
            ("size", "Size", 72, "e"),
        )
        col_specs = metric_cols if self._is_bg else (
            ("before", "Before", 92, "center"),
            ("after", "After", 92, "center"),
            *metric_cols,
        )
        self._cols = tuple(c[0] for c in col_specs)
        self.tree = build_job_tree(self, col_specs)
        self.tree.bind("<Double-1>", self._on_activate)

        self.reset(active=False, total=0)

    # --- state ---------------------------------------------------------

    def reset(self, active: bool = True, total: int = 0) -> None:
        self.reset_finished()
        self._total = total
        self._changed = 0
        self._skipped = 0
        self._pcts: list[float] = []
        self._times: list[float] = []   # per-PROCESSED-image op seconds
        self._tree_root: str | None = None
        self._folder_nodes: dict[str, str] = {}
        self._image_rows: dict[str, str] = {}
        self.tree.delete(*self.tree.get_children())
        self._node_info.clear()
        self.prog.configure(maximum=max(total, 1), value=0)
        self.state_var.set("running …" if active else "idle")
        self._update_metric()

    # --- events (main thread, via the queue pump) ----------------------

    def handle(self, event: dict) -> None:
        kind = event["type"]
        if kind == "sheet_start":
            self._total = event["total"]
            self.prog.configure(
                maximum=max(self._total, 1),
                value=self._changed + self._skipped,
            )
        elif kind == "item_start":
            self.state_var.set(
                f"({event['idx']}/{event['of']}) {event['title'][:50]}"
            )
        elif kind == "item_done":
            self._changed += 1
            self._pcts.append(event["pct"])
            self._times.append(event["time"])
            self._insert_image_row(event["rel"], event)
            self._advance()
        elif kind == "item_refused":
            self._skipped += 1
            self._insert_refused_row(event["rel"])
            self._advance()
        elif kind == "sheet_done":
            self.state_var.set(
                f"done — {self._changed} changed, {self._skipped} skipped"
            )
            self._update_metric()

    def _advance(self) -> None:
        self.prog.configure(value=self._changed + self._skipped)
        self._update_metric()

    def _update_metric(self) -> None:
        counts = f"{self._changed} changed, {self._skipped} skipped"
        if self._pcts:
            avg = sum(self._pcts) / len(self._pcts)
            self.metric_var.set(
                f"avg {fmt_pct(avg)}% {self._metric_name}   ·   {counts}"
            )
        else:
            self.metric_var.set(f"{self._metric_name}: —   ·   {counts}")
        self._update_time()

    def _update_time(self) -> None:
        """Total op time over PROCESSED images + the per-image average
        (skipped images add no time)."""
        self.time_var.set(fmt_time_summary(self._times))

    # --- tree building (root/folder nodes inherited from JobPanel) -----

    def _insert_image_row(self, rel: str, event: dict) -> None:
        fnode = self._ensure_folder(folder_of(rel))
        pct = f"{fmt_pct(event['pct'])}%"
        metric = (pct, fmt_op_duration(event["time"]), fmt_size(event["size"]))
        # the BG panel has no Before/After columns; the dimensional tools do
        values = metric if self._is_bg else (
            event["before"], event["after"], *metric
        )
        # a CHANGED (restorable) row gets the striking green/teal tag so it
        # POPS against the muted-grey SKIPPED rows (owner 2026-07-19)
        row = self.tree.insert(
            fnode, "end", text=PurePosixPath(rel).name, values=values,
            tags=(TOOL_CHANGED_TAG,),
        )
        self._node_info[row] = {"level": "image", "rel": rel, "has_backup": True}
        self._image_rows[rel] = row

    def _insert_refused_row(self, rel: str) -> None:
        fnode = self._ensure_folder(folder_of(rel))
        # the '—' sits in the % column: index 0 (BG) or 2 (dimensional)
        values = ("—", "", "") if self._is_bg else ("", "", "—", "", "")
        # tint the SKIPPED row muted (owner 2026-07-19) — this bucket now
        # also holds the many 0px crops the crop-fix sends to skipped
        self.tree.insert(
            fnode, "end", text=PurePosixPath(rel).name, values=values,
            tags=(TOOL_SKIP_TAG,),
        )

    # --- before/after viewer + restore ---------------------------------

    def _on_activate(self, _event) -> None:
        info = self._node_info.get(self.tree.focus())
        if not info:
            return
        level = info["level"]
        if level == "image":
            self._show_image_beforeafter(info["rel"])
        elif level == "folder":
            # ONLY this folder's images (owner 2026-07-19) — not the union
            self._show_folder_beforeafter(info["folder"])
        else:  # the collection (top) node — the whole job's changed images
            self._show_all_beforeafter()

    def _pair_for(self, rel: str) -> dict | None:
        """The {rel, before, after} pair for one image, or None when
        there is no backup / result on disk (a no-op or a restored
        image)."""
        if self.jobtemp is None or self.folder is None:
            return None
        before = self.jobtemp.before_path(rel)
        after = self.folder / rel
        if before is None or not after.exists():
            return None
        return {"rel": rel, "before": before, "after": after}

    def _show_image_beforeafter(self, rel: str) -> None:
        pair = self._pair_for(rel)
        if pair is None:
            messagebox.showinfo(
                "PromptPainter",
                "No before/after for this image — nothing was changed,"
                " or it was already restored.",
            )
            return
        BeforeAfterWindow(
            self.winfo_toplevel(),
            f"{JOB_LABEL[self.slot_key]} — {PurePosixPath(rel).name}",
            [pair], restore_label="Restore",
            restore_cb=lambda: self.restore_one(rel),
        )

    def _show_folder_beforeafter(self, folder: str) -> None:
        """The before/after viewer scoped to ONE folder's changed images —
        double-clicking a folder node restores JUST that folder, never the
        whole job (owner 2026-07-19)."""
        pairs = [
            pair for rel in rels_in_folder(self._image_rows, folder)
            if (pair := self._pair_for(rel)) is not None
        ]
        if not pairs:
            messagebox.showinfo(
                "PromptPainter",
                "No changed images in this folder — nothing was changed,"
                " or all were already restored.",
            )
            return
        BeforeAfterWindow(
            self.winfo_toplevel(),
            f"{JOB_LABEL[self.slot_key]} — {folder} ({len(pairs)})",
            pairs, restore_label="RESTORE ALL",
            restore_cb=lambda: self.restore_folder(folder),
            subtitle=(
                f"Before / after of every changed image in {folder} —"
                " RESTORE ALL reverts ONLY this folder."
            ),
        )

    def _show_all_beforeafter(self) -> None:
        pairs = [
            pair for rel in self._image_rows
            if (pair := self._pair_for(rel)) is not None
        ]
        if not pairs:
            messagebox.showinfo(
                "PromptPainter",
                "No changed images to show — nothing was changed, or all"
                " were already restored.",
            )
            return
        BeforeAfterWindow(
            self.winfo_toplevel(),
            f"{JOB_LABEL[self.slot_key]} — all changed images ({len(pairs)})",
            pairs, restore_label="RESTORE ALL",
            restore_cb=self.restore_all,
        )

    def restore_one(self, rel: str) -> None:
        if self.jobtemp is not None and self.jobtemp.restore_one(rel):
            self._mark_restored(rel)

    def restore_folder(self, folder: str) -> int:
        """Restore ONLY the images under ``folder`` (the folder-scoped
        RESTORE ALL) — mirrors ``restore_all`` but over that folder's rels,
        so a folder double-click never reverts other folders."""
        if self.jobtemp is None:
            return 0
        count = 0
        for rel in rels_in_folder(self._image_rows, folder):
            if self.jobtemp.restore_one(rel):
                self._mark_restored(rel)
                count += 1
        return count

    def restore_all(self) -> int:
        if self.jobtemp is None:
            return 0
        count = self.jobtemp.restore_all()
        for rel in list(self._image_rows):
            self._mark_restored(rel)
        return count

    def _mark_restored(self, rel: str) -> None:
        row = self._image_rows.get(rel)
        if row is not None:
            self.tree.set(row, "pct", "restored")
            info = self._node_info.get(row)
            if info is not None:
                info["has_backup"] = False


class AiCheckPanel(JobPanel):
    """The AI image checker's dashboard panel (owner 2026-07-20): a
    progress bar, the flagged/OK counts, and a folder > image table —
    FLAGGED rows striking (the changed bucket) with their DEFECT COUNT
    as the row metric, OK rows muted (the skipped bucket), API failures
    counted loudly as errors. Double-click a flagged row for the full
    defect list + the image itself (a DocWindow).

    Two panel actions: **Send flagged to generator** re-queues every
    flagged image that matches a QUEUED collection on its ORIGINAL site
    (``only=`` + a per-item fix note appended to the prompt), and
    **Clear flags** wipes this run's entries from
    ``<out>/_state/ai_flags.json``. The panel never touches the images
    or the flags itself — both actions go through the GUI callbacks.
    """

    def __init__(
        self, master, on_close=None, on_resend=None, on_clear=None,
        on_pause=None,
    ):
        super().__init__(
            master, "aicheck", on_show=None, on_close=on_close,
            on_pause=on_pause,
        )
        self._on_resend = on_resend  # called with {flag key: [defects]}
        self._on_clear = on_clear    # called with (out_base, keys) -> int
        self.folder: Path | None = None    # the checked folder
        self.out_base: Path | None = None  # the flags' out base

        self.prog = ttk.Progressbar(
            self, bootstyle="info-striped", maximum=1, value=0
        )
        self.prog.pack(fill="x", pady=(6, 4))
        self.metric_var = tk.StringVar(value="—")
        ttk.Label(
            self, textvariable=self.metric_var, style="Value.TLabel"
        ).pack(anchor="w", pady=(0, 2))
        # execution time — total over CHECKED images + the per-image
        # average, mirroring the in-place tool panels (the owner wants to
        # see how long the paced checker actually works)
        self.time_var = tk.StringVar(value="⏱ —")
        ttk.Label(
            self, textvariable=self.time_var, style="Muted.TLabel"
        ).pack(anchor="w", pady=(0, 4))

        col_specs = (
            ("defects", "Defects", AI_CHECK_DEFECT_COL_PX, "e"),
            ("time", "Time", AI_CHECK_TIME_COL_PX, "e"),
            ("first", "First defect", AI_CHECK_FIRST_COL_PX, "w"),
        )
        self._cols = tuple(c[0] for c in col_specs)
        self.tree = build_job_tree(self, col_specs)
        self.tree.bind("<Double-1>", self._on_activate)

        actions = ttk.Frame(self)
        actions.pack(fill="x", pady=(6, 0))
        self.btn_resend = rounded_button(
            actions, "Send flagged to generator",
            command=self._do_resend, kind="info",
        )
        self.btn_resend.pack(side="left")
        self.btn_clear = rounded_button(
            actions, "Clear flags", command=self._do_clear,
            kind="danger-outline",
        )
        self.btn_clear.pack(side="left", padx=6)

        self.reset(active=False, total=0)

    # --- state ---------------------------------------------------------

    def reset(self, active: bool = True, total: int = 0) -> None:
        self.reset_finished()
        self._total = total
        self._flagged: dict[str, list[str]] = {}  # flag key -> defects
        self._raw: dict[str, str | None] = {}     # flag key -> raw answer
        self._times: list[float] = []             # per-CHECKED-image op s
        self._ok = 0
        self._errors = 0
        self._tree_root: str | None = None
        self._folder_nodes: dict[str, str] = {}
        self._image_rows: dict[str, str] = {}
        self.tree.delete(*self.tree.get_children())
        self._node_info.clear()
        self.prog.configure(maximum=max(total, 1), value=0)
        self.state_var.set("running …" if active else "idle")
        self._update_metric()

    # --- events (main thread, via the queue pump) ----------------------

    def handle(self, event: dict) -> None:
        kind = event["type"]
        if kind == "sheet_start":
            self._total = event["total"]
            self.prog.configure(maximum=max(self._total, 1), value=0)
        elif kind == "item_start":
            self.state_var.set(
                f"({event['idx']}/{event['of']}) {event['title'][:50]}"
            )
        elif kind in ("item_flagged", "item_ok", "item_error"):
            rel = event["rel"]
            self._times.append(event["time"])
            self._raw[rel] = event.get("raw")  # verbatim, for the viewer
            if kind == "item_flagged":
                self._flagged[rel] = list(event["defects"])
                self._insert_row(rel, event["defects"], event["time"])
            elif kind == "item_ok":
                self._ok += 1
                self._insert_row(rel, None, event["time"])
            else:
                self._errors += 1
                self._insert_row(rel, None, event["time"], error=True)
            self._advance()
        elif kind == "sheet_done":
            done = f"done — {len(self._flagged)} flagged, {self._ok} OK"
            if self._errors:
                done += f", {self._errors} error(s)"
            self.state_var.set(done)
            self._update_metric()

    def _advance(self) -> None:
        self.prog.configure(
            value=len(self._flagged) + self._ok + self._errors
        )
        self._update_metric()

    def _update_metric(self) -> None:
        text = f"{len(self._flagged)} flagged   ·   {self._ok} OK"
        if self._errors:
            text += f"   ·   {self._errors} error(s)"
        self.metric_var.set(text)
        self.time_var.set(fmt_time_summary(self._times))

    def _insert_row(
        self, rel: str, defects: list | None, time_s: float,
        error: bool = False,
    ) -> None:
        fnode = self._ensure_folder(folder_of(rel))
        time_txt = fmt_op_duration(time_s)
        if defects:
            # the CHANGED (striking) bucket — this image needs work
            values = (str(len(defects)), time_txt, defects[0])
            kind = "flagged"
        elif error:
            values = ("!", time_txt, "API error — see the Log")
            kind = "error"
        else:
            values = ("OK", time_txt, "")
            kind = "ok"
        row = self.tree.insert(
            fnode, "end", text=PurePosixPath(rel).name, values=values,
            tags=(ai_check_tag(kind),),
        )
        self._node_info[row] = {"level": "image", "rel": rel}
        self._image_rows[rel] = row

    # --- the defect viewer + panel actions ------------------------------

    def _on_activate(self, _event) -> None:
        """Double-click ANY checked row (flagged, OK or error) → a
        DocWindow with the parsed defects (when any), the VERBATIM AI
        response and the image itself, so the owner can inspect exactly
        what the model said about this exact image (owner 2026-07-21)."""
        info = self._node_info.get(self.tree.focus())
        if not info or info.get("level") != "image":
            return
        rel = info["rel"]
        defects = self._flagged.get(rel)
        raw = self._raw.get(rel)
        if not defects and raw is None:
            return  # nothing was captured for this row
        md = ai_check_doc_md(rel, defects, raw)
        image = ai_check_image_file(rel, self.out_base or Path("."))
        DocWindow(
            self.winfo_toplevel(), rel, md,
            copy_text=raw if raw is not None else "\n".join(defects or []),
            hint="Exactly what the vision model reported for this image.",
            image_path=image if image.is_file() else None,
        )

    def _do_resend(self) -> None:
        if not self._flagged:
            messagebox.showinfo(
                "PromptPainter",
                "No flagged images in this run — nothing to re-send.",
            )
            return
        if self._on_resend is not None:
            self._on_resend(dict(self._flagged))

    def _do_clear(self) -> None:
        if not self._flagged:
            messagebox.showinfo(
                "PromptPainter",
                "No flagged images in this run — nothing to clear.",
            )
            return
        if self._on_clear is None or self.out_base is None:
            return
        count = self._on_clear(self.out_base, list(self._flagged))
        for rel in self._flagged:
            row = self._image_rows.get(rel)
            if row is not None:
                self.tree.set(row, "defects", "cleared")
        self._flagged.clear()
        self._update_metric()
        self.state_var.set(f"{count} flag(s) cleared")


class DashGrid(ttk.Frame):
    """The dashboard's up-to-6 per-job panels in a responsive grid, gen
    sites FIRST.

    Panels are added on job START and removed on CLOSE; the grid
    re-flows by the active count (``GRID_COLS_BY_COUNT``, row-major over
    ``JOB_ORDER`` — so ChatGPT + Gemini always fill the top row and, at
    N=5, the 6th cell stays empty). Cells share a ``uniform`` group so
    they are equal and evenly fill the area. A muted placeholder shows
    when no job has run yet.
    """

    def __init__(self, master):
        super().__init__(master)
        self._panels: dict[str, JobPanel] = {}
        self._active: list[str] = []  # gridded slots (rendered in JOB_ORDER)
        self._placeholder = ttk.Label(
            self,
            text="No jobs yet — press a site Start, or a tool button above.",
            style="Muted.TLabel", anchor="center",
        )

    def attach(self, panels: dict) -> None:
        self._panels = panels
        self.relayout()

    def active(self) -> list[str]:
        return [k for k in JOB_ORDER if k in self._active]

    def add(self, kind: str) -> None:
        if kind not in self._active:
            self._active.append(kind)
        self.relayout()

    def remove(self, kind: str) -> None:
        if kind in self._active:
            self._active.remove(kind)
        self.relayout()

    def relayout(self) -> None:
        self._placeholder.grid_forget()
        for panel in self._panels.values():
            panel.grid_forget()
        for i in range(3):  # reset every row/col this grid can ever use
            self.rowconfigure(i, weight=0, uniform="")
            self.columnconfigure(i, weight=0, uniform="")
        slots = self.active()
        n = len(slots)
        if n == 0:
            self._placeholder.grid(row=0, column=0, sticky="nsew")
            self.rowconfigure(0, weight=1)
            self.columnconfigure(0, weight=1)
            return
        cols = GRID_COLS_BY_COUNT[n]
        rows = math.ceil(n / cols)
        for idx, kind in enumerate(slots):
            r, c = divmod(idx, cols)
            self._panels[kind].grid(
                row=r, column=c, sticky="nsew", padx=4, pady=4
            )
        for c in range(cols):
            self.columnconfigure(c, weight=1, uniform="dashcol")
        for r in range(rows):
            self.rowconfigure(r, weight=1, uniform="dashrow")


# ---------------------------------------------------------------------
# API Image Generation adapter (GUI rework Phase 19)
# ---------------------------------------------------------------------


class ApiImageAdapter:
    """A ``SiteDriver``-shaped stand-in over the paid Gemini image API —
    lets the "api_image" job reuse ``PainterGui._drive_site``/
    ``painter.runner.run_sheet`` COMPLETELY UNCHANGED (the binding
    design doc's own "biggest risk-reducer": ``run_sheet`` only ever
    calls ``submit_prompt``/``await_done``/``extract_image`` on its
    driver, plus ``attach``/``close`` in ``_drive_site`` and
    ``driver.site.name`` for the report header — see runner.py/
    driver.md). There is no browser tab to drive, so ``attach``/
    ``close``/``await_done`` are no-ops; ``submit_prompt`` only
    REMEMBERS the prompt text — the real call happens in
    ``extract_image``, mirroring the DOM driver's own submit-then-
    await-then-extract shape so ``run_sheet``'s own timing split
    (SEND -> image is "gen_s") stays meaningful. ``new_chat`` is
    deliberately NOT implemented: ``PainterGui._start_api_image``
    always passes ``new_chat="off"``, so ``_drive_site``/``run_sheet``
    never call it on this adapter — there is no chat to open.

    A free-tier-exhausted 429 (``ai.PaidFeatureRequired`` — the
    account has ZERO free quota for the paid image model, see ai.md)
    is remapped to ``driver.TerminalState`` so the EXISTING quota-stop
    plumbing (``_drive_site``'s own ``except TerminalState`` branch,
    the dashboard's state line) handles it with NO new code. The
    free-tier-zero condition is PERMANENT — no wait ever fixes it, only
    billing — so ``retry_after_s`` is always None: unlike a website
    quota with a known reset time, this job never schedules an
    auto-restart timer, exactly like a quota message that named no
    parseable reset time."""

    def __init__(self, log: Callable[[str], None] = print):
        self._log = log
        self._prompt: str = ""
        # run_sheet reads driver.site.name for the report header
        # (RunReport's constructor, only when report=True) — a tiny
        # stand-in, never a real SiteConfig (no DOM field on it is
        # ever read).
        self.site = SimpleNamespace(name=JOB_LABEL["api_image"])

    def attach(self) -> str:
        return "API Image GEN (Gemini paid image model, no browser tab)"

    def close(self) -> None:
        pass

    def submit_prompt(self, prompt: str) -> None:
        self._prompt = prompt

    def await_done(self, log: Callable[[str], None] = print) -> None:
        pass

    def extract_image(self) -> bytes:
        from painter import ai
        from painter.driver import TerminalState

        try:
            return ai.generate_image(
                self._prompt, model=GEMINI_IMAGE_MODEL, log=self._log,
            )
        except ai.PaidFeatureRequired as exc:
            raise TerminalState(str(exc), retry_after_s=None) from exc


# ---------------------------------------------------------------------
# Main window
# ---------------------------------------------------------------------

def _filter_files(
    files: list[Path], conditions: list[filters.FilterCondition],
    log: Callable[[str], None],
) -> list[Path]:
    """Keep only the paths whose CURRENT pixel size passes the stacked
    filter (``painter.filters.matches`` — AND across every condition,
    owner decision 2026-07-21). An empty ``conditions`` list is a
    no-op — the common case — and opens nothing; the raw ``files``
    list comes back unchanged. A path PIL cannot open is EXCLUDED with
    a loud log line rather than aborting the whole picker (root Rule
    #1/#7: the caller's file dialog is external input — e.g. an
    "All files" pick could include a non-image by mistake)."""
    if not conditions:
        return list(files)
    kept = []
    for path in files:
        try:
            with Image.open(path) as im:
                width, height = im.size
        except Exception as exc:
            log(f"FILTER: cannot read {path.name} ({exc}) — excluded")
            continue
        if filters.matches(width, height, conditions):
            kept.append(path)
    return kept


def _parse_condition_dicts(
    dicts: list, log: Callable[[str], None]
) -> list[filters.FilterCondition]:
    """Best-effort parse of a JSON-loaded condition-dict list
    (settings.json's ``aspect_filter_conditions`` or a preset) into
    ``FilterCondition``s. A malformed entry is DROPPED with a loud log
    line rather than crashing the whole settings load — mirrors
    ``painter.settings.load_settings``'s own "a corrupt file loses the
    remembered choice, never the app" precedent, applied to one key."""
    out = []
    for d in dicts:
        try:
            out.append(filters.condition_from_dict(d))
        except (TypeError, KeyError, ValueError) as exc:
            log(f"SETTINGS: dropping unreadable filter condition {d!r} ({exc})")
    return out


def _migrate_legacy_aspect_filter(stored: dict) -> list[dict]:
    """One-time migration (GUI rework Phase 4, owner decision
    2026-07-21): the OLD scalar aspect-tool filter — settings.json's
    ``aspect_filter`` key, ``{"from": float, "to": float, "mode":
    ASPECT_FILTER_OFF/_IF/_IF_NOT}`` — into the NEW stacked-conditions
    shape (a list of ``painter.filters.condition_to_dict`` dicts, the
    same JSON shape ``aspect_filter_conditions`` and a saved preset
    both use).

    ``off`` carried no filtering, so it becomes an EMPTY list — an
    empty conditions list already matches everything, no special-
    casing needed downstream. ``IF``/``IF NOT`` becomes exactly ONE
    ``FILTER_KIND_ASPECT_RANGE`` condition with the SAME from/to/
    polarity numbers: ``matches()``'s ``lo <= ratio <= hi`` containment
    (IF) / its negation (IF NOT) is arithmetically identical to
    ``change_aspect``'s own old ``filter_from <= cur <= filter_to``
    check, so behaviour is preserved exactly, only the container shape
    changes. Pure and Tk-free (no ``self``, no widget) — callable
    straight from a settings dict, e.g. the owner's real
    ``{"from": 0.9, "to": 1.1, "mode": "IF NOT"}``.

    Raises ``ValueError`` loudly (root Rule #1) on an unrecognised
    ``mode`` string — a scenario the OLD dialog itself could never
    have written, so this is corrupt/foreign data, not a case to
    silently coerce; the caller (``PainterGui._apply_settings``)
    catches it and falls back to no filter, same as any other corrupt
    settings.json value."""
    mode = stored.get("mode", ASPECT_FILTER_OFF)
    if mode == ASPECT_FILTER_OFF:
        return []
    if mode not in (ASPECT_FILTER_IF, ASPECT_FILTER_IF_NOT):
        raise ValueError(f"unrecognised legacy aspect_filter mode: {mode!r}")
    lo = float(stored.get("from", ASPECT_FILTER_DEFAULT_FROM))
    hi = float(stored.get("to", ASPECT_FILTER_DEFAULT_TO))
    polarity = (
        FILTER_POLARITY_IF_NOT if mode == ASPECT_FILTER_IF_NOT
        else FILTER_POLARITY_IF
    )
    return [filters.condition_to_dict(filters.FilterCondition(
        kind=FILTER_KIND_ASPECT_RANGE, polarity=polarity, lo=lo, hi=hi,
    ))]


def _upscale_params_from_side_and_filter(
    min_side: int, conditions: list[filters.FilterCondition],
) -> dict:
    """The upscale gate's min-SIDE spinner + its embedded FilterEditor's
    condition stack -> ``upscale_if_small``'s four kwargs (GUI rework
    Phase 6, replacing the old four-field ``up_minw``/``up_minh``/
    ``up_aspmin``/``up_aspmax`` gate). ``min_side`` becomes BOTH
    ``min_width`` and ``min_height`` — the gate no longer distinguishes
    the two axes (owner decision); the shipped default already had them
    equal at 800px, so the default case behaves byte-identically.

    ``aspect_min``/``aspect_max`` are read off the FIRST Aspect (exact
    or range — ``filters.py`` treats the two identically, see its own
    docstring) condition in the stack whose polarity is IF: an exact
    algebraic match for what ``upscale_if_small`` already means by
    "qualifies" (``aspect_min <= W/H <= aspect_max``). NO such
    condition — the owner deleted the aspect row, or set it to IF NOT,
    a shape ``upscale_if_small``'s plain ``[lo, hi]`` pair cannot
    express — widens to ``(0, inf)``: every aspect ratio qualifies for
    the size gate alone.

    IMPORTANT — this is a deliberately PARTIAL translation, never the
    full story (root Rule #1: never silently drop a condition).
    ``upscale_if_small`` has no kwarg for a Width/Height/Any-side
    condition, a SECOND aspect condition, or an IF-NOT aspect condition
    — anything in ``conditions`` beyond the one this function folds in
    is the CALLER's responsibility to enforce separately via
    ``filters.matches()`` against the FULL, unmodified ``conditions``
    list before ever invoking ``upscale_if_small`` with this function's
    output. See ``_gate_and_upscale`` (the per-image site-pipeline
    gate) and ``UpscaleSettingsPanel.build_func``'s caller (the
    standalone tool's pre-filtered file list, via ``_filter_files`` in
    ``PainterGui._start_tool_from_panel``) — both call sites apply
    that gate; this function alone would silently ignore every
    non-aspect condition, so it is never used alone.
    """
    aspect_min, aspect_max = 0.0, float("inf")
    for c in conditions:
        if (
            c.kind in (FILTER_KIND_ASPECT_EXACT, FILTER_KIND_ASPECT_RANGE)
            and c.polarity == FILTER_POLARITY_IF
        ):
            aspect_min, aspect_max = c.lo, c.hi
            break
    return {
        "min_width": min_side,
        "min_height": min_side,
        "aspect_min": aspect_min,
        "aspect_max": aspect_max,
    }


def _gate_and_upscale(
    path: Path, log: Callable[[str], None],
    conditions: list[filters.FilterCondition], params: dict,
) -> str:
    """``upscale_if_small`` for ONE already-saved image, gated on the
    FULL stacked filter FIRST (GUI rework Phase 6, root Rule #1): any
    condition beyond the single aspect row ``_upscale_params_from_
    side_and_filter`` already folded into ``params`` — a stacked Width/
    Height/Any-side row, a second aspect row, or an IF-NOT aspect row —
    must still gate the image, losslessly. Used by the PER-SITE
    pipeline (``PainterGui._compose_post_save``), which has no upfront
    file list to pre-filter (each image is gated as it is saved); the
    STANDALONE Upscale tool instead pre-filters its whole file list
    once via ``_filter_files`` (same ``conditions``, same
    ``filters.matches()`` engine, applied to a list instead of one
    path).

    An empty ``conditions`` list — the FilterEditor's own "no filter,
    process everything" contract — skips the extra ``Image.open`` and
    goes straight to ``upscale_if_small``; the common seeded-default
    gate (one Aspect condition) DOES open the image here as well as
    inside ``upscale_if_small`` itself — a harmless redundant re-check
    (both read the SAME aspect band), not a bug: correctness over a
    micro-optimisation on a path that already waits multiple seconds
    per image for the site's own generation (root Priority A is about
    hot paths; this is not one)."""
    if conditions:
        with Image.open(path) as im:
            width, height = im.size
        if not filters.matches(width, height, conditions):
            return "nothing"
    from painter.upscale import upscale_if_small

    return upscale_if_small(path, log, **params)


def _run_pipeline_steps(
    path: Path,
    steps: list[tuple[str, str, Callable[[Path], str]]],
    temp: "jobtemp.JobTemp | None",
    keep_all_steps: bool,
    on_cap: Callable[[], None],
) -> str:
    """Run each ENABLED post-save STEP over one already-saved image, in
    order, composing the runner's action-string description ("REMOVE
    BG: done, CROP: done, ...") — the per-image engine of
    ``PainterGui._compose_post_save`` (GUI rework Phase 8's reordered
    BG -> Crop -> Aspect -> Upscale pipeline). ``steps`` is the
    caller-built ``(label, step_name, fn)`` triples for whichever
    switches are on, in PIPELINE order; ``fn`` is already a plain
    ``path -> status`` callable (its own log sink bound at the call
    site), so this function stays engine-agnostic — it never imports
    postprocess/aspect/upscale itself.

    When ``temp`` (a JobTemp) is attached, each step's PRE-state is
    backed up first:

    * the FIRST enabled step's pre-state is tagged ``step="original"``
      — the pristine, restore-everything baseline (the runner's raw
      just-saved image, before the pipeline touches it at all) — and is
      ALWAYS taken, cap or toggle or not, so every image keeps at LEAST
      this one restore point. This DELIBERATELY DEDUPS against that
      first step's own name (owner ask, GUI rework Phase 8: "avoid a
      pointless duplicate when original == the first step's pre-
      state") — the two would be byte-identical backups of the exact
      same instant, so only ONE is ever written. A caller reading
      ``steps_for()`` should expect the first ENABLED step's own name
      to be ABSENT from the list — "original" already covers that
      instant; see the ``JOBTEMP_STEP_NAMES`` ordering-contract
      comment in painter/config.py, which already frames "original" as
      captured "before the pipeline touches the file at all" (i.e. not
      tied to any one step's name).
    * every LATER enabled step's pre-state gets its OWN named backup
      ("bg"/"crop"/"aspect"/"upscale") — but only when ``keep_all_
      steps`` is True AND the job is not yet ``over_cap()``. Once over
      cap, NEW per-step backups stop (the "original-only" fallback)
      and ``on_cap()`` fires; when ``keep_all_steps`` is False (the
      owner's own choice, not an emergency), the same skip happens
      SILENTLY — ``on_cap()`` is reserved for the cap, never the
      toggle. The caller turns a real cap hit into the loud persistent
      dashboard banner (see DashPanel's "over_cap" event).
    * a step backed up under its OWN name whose result was "nothing" (a
      genuine no-op — before == after) has that backup DROPPED right
      back, mirroring the four standalone tools' own restore-point
      hygiene (``PainterGui._run_tool_job``): a no-op leaves nothing
      worth restoring. "original" is NEVER dropped, whatever any step's
      own outcome — it is the restore-all target regardless.

    With ``temp is None`` (no JobTemp attached — never happens once
    ``_start_site`` has run, but keeps this function usable headless in
    tests) every step still runs normally; only the backup bookkeeping
    is skipped.
    """
    rel = path.relative_to(temp.folder).as_posix() if temp is not None else ""
    parts = []
    took_original = False
    for label, step_name, fn in steps:
        backed_up_as = None
        if temp is not None:
            if not took_original:
                temp.backup(path, rel, step="original")
                took_original = True
            elif not keep_all_steps:
                pass  # the owner's own choice — silent skip, no banner
            elif not temp.over_cap():
                temp.backup(path, rel, step=step_name)
                backed_up_as = step_name
            else:
                on_cap()
        status = fn(path)
        if backed_up_as is not None and status != "done":
            temp.drop(rel, step=backed_up_as)  # a no-op — nothing to restore
        parts.append(f"{label}: {status}")
    return ", ".join(parts)


def _migrate_legacy_upscale_gate(min_width, aspect_min, aspect_max) -> dict:
    """One-time migration (GUI rework Phase 6, owner decision
    2026-07-21): the OLD three upscale-gate numbers — a min WIDTH (min
    HEIGHT is DROPPED; the two axes collapse into ONE min-SIDE spinner,
    and every shipped default and every real settings.json seen so far
    already had width == height, so nothing observable is lost in
    practice) and an aspect ``[from, to]`` band — into the NEW neutral
    shape ``{"min_side": int, "conditions": [ONE Aspect (range)
    condition dict, IF polarity, the SAME band]}``.

    Shared by BOTH migration call sites — the per-agent ``up_minw``/
    ``up_aspmin``/``up_aspmax`` fields AND the standalone tool's
    ``upscale_tool`` dict's ``min_width``/``aspect_min``/``aspect_max``
    — same numbers, same target shape, only the SOURCE key names
    differ; each caller extracts its own three values (defaulting a
    missing key to today's shipped default) and hands them here. The
    returned dict's field names are neutral (not tied to either
    caller's own persisted-JSON key names — the per-agent caller writes
    them into ``up_minside``/``up_filter_conditions`` as STRINGS/lists,
    the standalone caller keeps ``min_side`` as a plain int matching
    ``UpscaleParamsDialog.result``'s own shape).

    Raises ``ValueError``/``TypeError`` loudly (root Rule #1) when a
    value will not convert to a number — mirrors ``_migrate_legacy_
    aspect_filter``'s own precedent exactly (missing key -> the caller
    already substituted a default before calling this; PRESENT but
    unparsable -> loud, the caller catches and falls back to the
    shipped default gate, never crashes the app on a hand-corrupted
    settings.json)."""
    min_side = int(float(min_width))
    lo = float(aspect_min)
    hi = float(aspect_max)
    return {
        "min_side": min_side,
        "conditions": [
            filters.condition_to_dict(filters.FilterCondition(
                kind=FILTER_KIND_ASPECT_RANGE, polarity=FILTER_POLARITY_IF,
                lo=lo, hi=hi,
            ))
        ],
    }


def _visible_agent_columns(
    order: list[str], visible: dict[str, bool],
) -> dict[str, int]:
    """Left-to-right column index for each VISIBLE key in ``order`` (GUI
    rework Phase 12, spec item 3A: either site's AgentPanel can be
    hidden so only the other stays on screen). A hidden key
    (``visible.get(key, True)`` is False) is simply ABSENT from the
    result — the remaining visible panel(s) compact toward column 0
    instead of leaving a dead gap where the hidden one used to sit, e.g.
    ChatGPT hidden, Gemini alone -> ``{"gemini": 0}``, never
    ``{"gemini": 1}``. Both visible -> ``{"chatgpt": 0, "gemini": 1}``;
    both hidden (never reached in practice — set_run_state forces a
    running site back to visible, and a site that never ran can still
    be hidden by hand, which IS a legal "nothing showing" state) ->
    ``{}``.

    Pure and Tk-free — ``PainterGui._relayout_agents`` is the only
    caller, applying the result to real ``grid()``/``grid_remove()``
    calls plus each column's weight (0 for an unused column so the
    visible one(s) expand into the freed width, the same reset-then-
    reassign technique ``DashGrid.relayout`` already uses)."""
    cols: dict[str, int] = {}
    i = 0
    for key in order:
        if visible.get(key, True):
            cols[key] = i
            i += 1
    return cols


# ---------------------------------------------------------------------
# Main Menu (GUI rework Phase 10)
# ---------------------------------------------------------------------

class MainMenu(ttk.Frame):
    """The startup landing screen: a full-window grid of big tiles, one
    per functionality (``config.MENU_TILES``) — replacing "everything
    visible at once" as the first thing the owner sees. Built ONCE,
    beside the existing controls/notebook tree, and shown/hidden by
    ``PainterGui._set_view``; picking a tile runs the SAME existing,
    unmodified handler the always-visible toolbar already called before
    this phase (see ``PainterGui._select_tile``) — this class only
    decides what the picker looks like, never what a pick DOES."""

    def __init__(self, parent, on_select: Callable[[str], None]):
        super().__init__(parent)
        self._on_select = on_select

        header = ttk.Frame(self)
        header.pack(pady=(24, 4))
        ttk.Label(header, text="PromptPainter", style="Big.TLabel").pack()
        ttk.Label(header, text="Pick what to do", style="Muted.TLabel").pack()

        grid = ttk.Frame(self)
        grid.pack(fill="both", expand=True, padx=24, pady=(8, 24))
        cols = MENU_TILE_COLS
        for i, tile in enumerate(MENU_TILES):
            r, c = divmod(i, cols)
            self._make_tile(grid, tile).grid(
                row=r, column=c, sticky="nsew",
                padx=MENU_TILE_GAP_PX // 2, pady=MENU_TILE_GAP_PX // 2,
            )
        rows = math.ceil(len(MENU_TILES) / cols)
        for c in range(cols):
            grid.columnconfigure(c, weight=1, uniform="menucol")
        for r in range(rows):
            grid.rowconfigure(r, weight=1, uniform="menurow")

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


def _next_view(
    current: str, active_count: int, menu_requested: bool = False,
) -> str:
    """Pure view-transition decision (GUI rework Phase 11) — no Tk, so
    it is unit-testable on its own. ``current`` is today's
    ``PainterGui._view`` ("menu" / "main" / "running"); ``active_count``
    is ``len(PainterGui._active_kinds())`` — every JOB_ORDER kind with a
    live worker right now; ``menu_requested`` is True only on an
    explicit Menu-button click (the pinned top-strip one outside
    "running", IconBar's own copy during it).

    Rules (owner 2026-07-21, binding design doc, Phase 11):

    * a Menu click is honoured ONLY once NOTHING is active — refused
      (view unchanged) otherwise, however many jobs are still running;
    * absent a Menu click, ANY active job forces "running" — the
      auto-enter-on-first-start rule (0 -> >=1 while on "menu" or
      "main" lands on "running");
    * once "running", it STAYS "running" even as jobs finish one by
      one, all the way down to zero — Stop closing the LAST active job
      never auto-navigates by itself; only a SUBSEQUENT explicit Menu
      click does (see the first rule above);
    * otherwise the view is simply unchanged (covers "menu"/"main"
      while genuinely idle — nothing here needs to move).
    """
    if menu_requested:
        return "menu" if active_count == 0 else current
    if active_count > 0:
        return "running"
    return current


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
        if set_font_base(FONT_BASE + step):
            self.status_var.set(
                f"font size {FONT_BASE} (Ctrl+wheel / Ctrl+'+'/'-')"
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
        forgotten."""
        visible = {
            key: panel.visible_var.get() for key, panel in self.agents.items()
        }
        cols = _visible_agent_columns(sorted(SITES), visible)
        for c in range(len(SITES)):
            self._agents_frame.columnconfigure(c, weight=0)
        for key, panel in self.agents.items():
            shown = key in cols
            if shown:
                panel.grid(row=0, column=cols[key], sticky="nsew", padx=4)
                self._agents_frame.columnconfigure(cols[key], weight=1)
            else:
                panel.grid_remove()
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
        view: the IconBar is always shown; AT MOST ONE inline settings
        surface additionally shows, keyed by ``_inline_kind`` —
        ``_controls_box`` for "website_gen", or the matching
        ``ToolSettingsPanel`` from ``_tool_panels`` (GUI rework Phase
        13: bg/crop today, Phase 14 adds upscale/aspect the same way).
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
        if self._inline_kind == "website_gen":
            self._controls_box.pack(fill="x", before=self.notebook)
        elif self._inline_kind in self._tool_panels:
            self._tool_panels[self._inline_kind].pack(
                fill="x", before=self.notebook
            )
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

        A tile whose job kind(s) (``TILE_JOB_KINDS``) are CURRENTLY
        active just focuses the Dashboard tab — it is NOT a settings
        toggle for a running job, and that job's own panel stays
        exactly as hidden as the design requires ("without disturbing
        any running job's own hidden panel"). A NOT-running tile
        toggles its inline settings/launch surface: "website_gen"
        shows/hides the existing ``_controls_box`` (the queue + both
        AgentPanels) right above the Dashboard/Log; "bg"/"crop" route
        through ``_tile_handler`` to ``_open_tool_panel`` (GUI rework
        Phase 13), toggling their OWN persistent ``ToolSettingsPanel``
        the exact same way; every other functionality (upscale/aspect/
        image_checker/ai_sheet_gen) still launches through its EXISTING
        modal/dialog handler (``_tile_handler`` — the SAME mapping the
        Main Menu itself uses), since Phase 14/15 are what give THEM a
        real persistent panel — until then, opening that dialog IS the
        tile's launch surface, and it disturbs nothing else (always its
        own Toplevel)."""
        kinds = TILE_JOB_KINDS.get(tile_id, ())
        if set(kinds) & self._active_kinds():
            self.notebook.select(0)
            return
        if tile_id == "website_gen":
            self._inline_kind = (
                None if self._inline_kind == "website_gen" else "website_gen"
            )
            self._apply_running_layout()
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
        self.btn_chrome = rounded_button(
            row, "Open Chrome (login)", command=self._open_chrome,
            icon_name="web",
        )
        self.btn_chrome.pack(side="left")
        self.btn_check = rounded_button(
            row, "Check", command=self._check_sheets,
        )
        self.btn_check.pack(side="left", padx=4)
        self.btn_select = rounded_button(
            row, "Select images…", command=self._select_images,
        )
        self.btn_select.pack(side="left", padx=4)
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
        path = Path(__file__).resolve().parent / "instructions.md"
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

    # --- settings persistence ------------------------------------------

    def _collect_settings(self) -> dict:
        return {
            "output": self.out_var.get(),
            "font_base": FONT_BASE,
            "theme": ACTIVE_THEME,
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


# ---------------------------------------------------------------------
# Select-images window
# ---------------------------------------------------------------------

class SelectWindow(tk.Toplevel):
    """Tick which images each site generates — a 3-level tree.

    Level 1 is the COLLECTION (the sheet file + theme), level 2 the
    FOLDERS inside it (the drop paths' parent dirs — a sheet may have
    several), level 3 the image files, each carrying one checkbox per
    site. Levels 1 and 2 show a live ``selected/total`` count per site;
    the header shows the grand ``selected/total`` per site over EVERY
    loaded collection.

    Performance model (the owner's "even a big collapsible list must
    not lag" complaint): the body is plain ttk only — NO customtkinter
    inside the scroll canvas (each CTkButton is a drawn canvas that
    re-renders on every configure). L1/L2 nodes are always
    materialised (cheap — a few dozen); L3 leaf rows are BUILT on a
    folder's open and DESTROYED on its close, so the live-widget count
    tracks only what is actually open. ``Expand all`` would otherwise
    materialise EVERY leaf in one synchronous geometry pass (~280 rows
    ≈ 3 s frozen); instead it builds folder-atomic CHUNKS across
    ``after()`` ticks (``SELECT_EXPAND_CHUNK`` leaves per tick, ≈ 120 ms
    median block), with a live progress cue (root Rule #10) — the tree
    fills in progressively and the main thread is never blocked (the
    scrollregion recompute is suspended for the run and scanned once at
    the end, keeping per-tick cost flat as the queue grows). Counts
    live-update through ONE coalesced ``after_idle`` recount driven by a
    dirty flag (a var trace only raises the flag), and ``ScrollFrame``
    coalesces its scrollregion recompute — so one settled user action
    costs one geometry pass, never one per gridded child. Long names WRAP via
    ``ttk.Label(wraplength=)``; the two per-site columns are
    fixed-width so they stay aligned however deep a row is or however
    far its name wraps.
    """

    def __init__(self, gui: PainterGui, sheets: list[Sheet]):
        super().__init__(gui.root)
        self.title("Select images per site")
        self.minsize(SELECT_MIN_W, SELECT_OPEN_H)
        skin_toplevel(self)  # bg registered so a flip re-tints the window
        THEME_TOPLEVELS.append(self)  # flip coherently with the main window
        self._gui = gui
        self._site_keys = sorted(SITES)

        done = {
            key: {
                str(sheet.source): gui._done_on_disk(key, sheet)
                for sheet in sheets
            }
            for key in self._site_keys
        }

        # --- the count model: build the data (vars + scopes) FIRST,
        # before any widget, so counts are pure var-math and correct
        # even for collapsed / never-built subtrees.
        self._all_leaves: list[dict] = []
        self._collections = [
            self._build_collection_data(sheet, done) for sheet in sheets
        ]

        # ONE trace per leaf var -> raise the dirty flag; a single
        # coalesced recount services an all/none over dozens of vars.
        self._dirty = False
        self._recount_job = None
        self._wrap_job = None
        # Expand-all runs as folder-atomic chunks across after() ticks
        self._expand_job = None
        self._expand_queue: list[tuple[dict, dict]] = []
        self._expand_leaves_total = 0
        self._traces: list[tuple[tk.BooleanVar, str]] = []
        for leaf in self._all_leaves:
            for key in self._site_keys:
                var = leaf["sites"][key]["var"]
                token = var.trace_add("write", self._mark_dirty)
                self._traces.append((var, token))

        # --- the top bar (CTk allowed here, OUTSIDE the scroll body)
        bar = ttk.Frame(self, padding=6)
        bar.pack(fill="x")
        ttk.Label(
            bar,
            text="Tick = generate.  Done = green (re-tick to redo)."
            "  ⚠ advice off.  Click a count = all/none.",
            style="Muted.TLabel",
        ).pack(side="left")
        rounded_button(
            bar, "Expand all", command=self._expand_all,
            kind="secondary-outline",
        ).pack(side="right")
        rounded_button(
            bar, "Collapse all", command=self._collapse_all,
            kind="secondary-outline",
        ).pack(side="right", padx=4)
        rounded_button(
            bar, "Close", command=self.destroy,
        ).pack(side="right", padx=4)

        # --- the colour legend (own row under the hint bar so it never
        # crowds the Close/Collapse/Expand buttons off-screen). Each swatch
        # label is painted in its OWN status colour, pulled LIVE from the
        # active theme's palette so a Day/Night flip recolours it too.
        legend = ttk.Frame(self, padding=(8, 0, 8, 2))
        legend.pack(fill="x")
        ttk.Label(legend, text="Legend:", style="Muted.TLabel").pack(
            side="left"
        )
        self._legend_labels: list[tuple[str, ttk.Label]] = []
        for role, text in (
            ("done", "BOTH DONE"),
            ("done_soft", "ONE SITE DONE"),
            ("superseded", "SUPERSEDED"),
            ("advice", "ADVICE"),
        ):
            lbl = ttk.Label(
                legend, text=text, style="Value.TLabel", foreground=status(role)
            )
            lbl.pack(side="left", padx=(14, 0))
            self._legend_labels.append((role, lbl))

        # --- the non-scrolling header: one accent cell per site with
        # the grand selected/total, right-aligned over the body columns
        # (a gutter reserves the body's vertical scrollbar width).
        header = ttk.Frame(self, padding=(8, 4))
        header.pack(fill="x")
        header.columnconfigure(0, weight=1)
        # Expand-all progress cue (root Rule #10) — left of the site-count
        # columns, empty except mid-build; accent + bold so it is unmissable
        self._progress_lbl = ttk.Label(
            header, text="", style="Value.TLabel",
            foreground=tb.Style().colors.info,
        )
        self._progress_lbl.grid(row=0, column=0, sticky="w")
        self._header_labels: dict[str, ttk.Label] = {}
        for i, key in enumerate(self._site_keys):
            lbl = ttk.Label(
                header, style="Head.TLabel", anchor="e", cursor="hand2"
            )
            lbl.grid(row=0, column=1 + i, sticky="e", padx=(16, 0))
            lbl.bind(
                "<Button-1>",
                lambda _e, s=key: self._toggle_scope(self._all_leaves, s),
            )
            self._header_labels[key] = lbl
        ttk.Frame(header, width=SELECT_SCROLLBAR_PX).grid(
            row=0, column=1 + len(self._site_keys)
        )

        # --- the scrolling body (vertical only: names wrap, they never
        # force horizontal growth)
        self._scroll = ScrollFrame(self, horizontal=False)
        self._scroll.pack(fill="both", expand=True)
        self._canvas = self._scroll.canvas
        # FIT CONTENT: size the window to the widest collection title so it
        # stays on ONE line (computed BEFORE the tree so labels are born at
        # the right wraplength, no premature 2-3 line wrapping).
        self._open_width = self._fit_content_width()
        self._canvas_width = self._open_width - SELECT_SCROLLBAR_PX
        self._wrap = self._wraplength_for(self._canvas_width)
        self._canvas.bind("<Configure>", self._on_canvas_configure, add="+")

        # --- the tree: L1 + L2 always materialised, L3 lazy
        self._static_labels: list[ttk.Label] = []  # L1/L2 names (wrap)
        self._count_nodes: list[dict] = []  # L1 + L2 nodes for _recount
        self._collection_nodes: list[dict] = []
        for coll in self._collections:
            self._build_collection_widgets(self._scroll.body, coll)

        # first paint of the counts + the open geometry (FIT-CONTENT width,
        # screen-tall height so the whole queue is visible at once)
        self._dirty = True
        self._recount()
        self.bind("<Destroy>", self._on_destroy)
        height = min(
            max(int(self.winfo_screenheight() * DOC_HEIGHT_FRAC), SELECT_OPEN_H),
            int(self.winfo_screenheight() * DOC_MAX_FRAC),
        )
        self.geometry(f"{self._open_width}x{height}")

    # --- data model (no widgets) --------------------------------------

    def _build_collection_data(self, sheet: Sheet, done: dict) -> dict:
        """One collection's leaf records + its folders (first-seen
        order). Materialises the shared BooleanVars — run-safe: the
        default (advice-free, not-yet-on-disk) set equals the runner's
        own 'never opened Select' rule (file-existence resume)."""
        src = str(sheet.source)
        folders: dict[str, dict] = {}
        leaves: list[dict] = []
        for item in sheet.items:
            drop = item.drop_path
            done_sites = [k for k in self._site_keys if drop in done[k][src]]
            leaf = {
                "name": PurePosixPath(drop).name,
                "advice": item.advice,
                # n_done is retained so apply_theme can RECOMPUTE the
                # status colour for the new theme (the colours differ
                # per theme for contrast on the light background)
                "n_done": len(done_sites),
                "color": self._leaf_color(item.advice, len(done_sites)),
                "sites": {},
            }
            for key in self._site_keys:
                var = self._gui._select_var(
                    key, src, drop, default=item.advice is None
                )
                is_done = drop in done[key][src]
                if is_done:
                    # done -> unticked by DEFAULT, but re-tickable so a
                    # bad image can be regenerated (owner 2026-07-19)
                    var.set(False)
                leaf["sites"][key] = {"var": var, "done": is_done}
            leaves.append(leaf)
            self._all_leaves.append(leaf)
            fname = folder_of(drop)
            fnode = folders.get(fname)
            if fnode is None:
                fnode = {"folder": fname, "leaves": []}
                folders[fname] = fnode
            fnode["leaves"].append(leaf)
        return {
            "label": f"{sheet.source.name} — {sheet.theme}",
            "leaves": leaves,
            "folders": list(folders.values()),
        }

    def _leaf_color(self, advice: str | None, n_done: int) -> str:
        # reads status() live, so a flip recolours the leaves through
        # this same function
        if n_done == len(self._site_keys):
            return status("done")
        if advice and "supersed" in advice.lower():
            return status("superseded")
        if advice:
            return status("advice")
        if n_done:
            return status("done_soft")
        return ""

    def apply_theme(self) -> None:
        """Re-colour this window's PER-WIDGET foregrounds for the active
        theme (they do not follow ttk styles): the built leaf labels and
        the Expand-all progress cue. The toplevel bg + scroll canvas ride
        the global recolour_tk_registry; every ttk widget rides the style
        re-run."""
        self._progress_lbl.configure(foreground=tb.Style().colors.info)
        for role, lbl in self._legend_labels:
            lbl.configure(foreground=status(role))
        default_fg = tb.Style().colors.fg
        for cnode in self._collection_nodes:
            for fnode in cnode["folders"]:
                if not fnode["built"]:
                    continue
                for leaf, lbl in zip(fnode["leaves"], fnode["leaf_labels"]):
                    color = self._leaf_color(leaf["advice"], leaf["n_done"])
                    leaf["color"] = color
                    lbl.configure(foreground=color or default_fg)

    # --- widgets -------------------------------------------------------

    def _new_row(self, parent, level: int) -> ttk.Frame:
        """A tree row: [indent][triangle][wrapped name .....][site0][site1].
        The two right columns are fixed-width so they align across every
        level; the name column takes all the slack."""
        row = ttk.Frame(parent)
        row.pack(fill="x", pady=SELECT_ROW_PADY)
        row.columnconfigure(0, minsize=level * SELECT_INDENT_PX)
        row.columnconfigure(1, minsize=SELECT_TRI_PX)
        row.columnconfigure(2, weight=1)
        row.columnconfigure(3, minsize=SELECT_COUNT_COL_PX)
        row.columnconfigure(4, minsize=SELECT_COUNT_COL_PX)
        return row

    def _count_cell(self, row, col: int, scope: list, key: str) -> ttk.Label:
        lbl = ttk.Label(row, text="0/0", anchor="center", cursor="hand2")
        lbl.grid(row=0, column=col, sticky="n")
        lbl.bind(
            "<Button-1>", lambda _e: self._toggle_scope(scope, key)
        )
        return lbl

    def _build_collection_widgets(self, body, coll: dict) -> None:
        section = ttk.Frame(body)
        section.pack(fill="x", pady=(6, 0))
        row = self._new_row(section, level=0)

        node = {"open": False, "children": ttk.Frame(section), "folders": []}
        tri = ttk.Label(row, text="▶ ", cursor="hand2")
        tri.grid(row=0, column=1, sticky="nw")
        node["triangle"] = tri
        name = ttk.Label(
            row, text=coll["label"], wraplength=self._wrap,
            justify="left", anchor="w", cursor="hand2",
        )
        name.grid(row=0, column=2, sticky="nw")
        self._static_labels.append(name)
        count = {}
        for i, key in enumerate(self._site_keys):
            count[key] = self._count_cell(row, 3 + i, coll["leaves"], key)
        self._count_nodes.append({"leaves": coll["leaves"], "count": count})

        toggle = partial(self._toggle_collection, node)
        for w in (tri, name):
            w.bind("<Button-1>", lambda _e: toggle())

        for folder in coll["folders"]:
            self._build_folder_widgets(node["children"], node, folder)

        self._collection_nodes.append(node)

    def _build_folder_widgets(self, parent, cnode: dict, folder: dict) -> None:
        section = ttk.Frame(parent)
        section.pack(fill="x")
        row = self._new_row(section, level=1)

        fnode = {
            "open": False, "built": False,
            "children": ttk.Frame(section), "leaves": folder["leaves"],
            "leaf_labels": [],
        }
        tri = ttk.Label(row, text="▶ ", cursor="hand2")
        tri.grid(row=0, column=1, sticky="nw")
        fnode["triangle"] = tri
        name = ttk.Label(
            row, text=folder["folder"], wraplength=self._wrap,
            justify="left", anchor="w", cursor="hand2",
        )
        name.grid(row=0, column=2, sticky="nw")
        self._static_labels.append(name)
        count = {}
        for i, key in enumerate(self._site_keys):
            count[key] = self._count_cell(row, 3 + i, folder["leaves"], key)
        self._count_nodes.append({"leaves": folder["leaves"], "count": count})

        toggle = partial(self._toggle_folder, fnode)
        for w in (tri, name):
            w.bind("<Button-1>", lambda _e: toggle())
        cnode["folders"].append(fnode)

    def _build_leaves(self, fnode: dict) -> None:
        """L3 rows — built on the folder's open (destroyed on close)."""
        for leaf in fnode["leaves"]:
            row = self._new_row(fnode["children"], level=2)
            for i, key in enumerate(self._site_keys):
                info = leaf["sites"][key]
                # done items stay ENABLED and re-tickable (owner
                # 2026-07-19) — coloured green/olive, unticked by default,
                # but the owner can tick one to REGENERATE a bad image
                cb = ttk.Checkbutton(row, variable=info["var"])
                cb.grid(row=0, column=3 + i, sticky="n")
            text = leaf["name"]
            if leaf["advice"]:
                text += f"   ⚠ {leaf['advice'][:SELECT_ADVICE_TRUNC]}"
            opt = {"foreground": leaf["color"]} if leaf["color"] else {}
            lbl = ttk.Label(
                row, text=text, wraplength=self._wrap, justify="left",
                anchor="w", **opt,
            )
            lbl.grid(row=0, column=2, sticky="nw")
            fnode["leaf_labels"].append(lbl)

    # --- open / close (low-level: NO expand-cancel — the chunked
    # Expand-all drives these directly and must not cancel itself) -----

    def _set_collection_open(self, node: dict, want_open: bool) -> None:
        if node["open"] == want_open:
            return
        node["open"] = want_open
        node["triangle"].configure(text="▼ " if want_open else "▶ ")
        if want_open:
            node["children"].pack(fill="x")
        else:
            node["children"].forget()

    def _open_folder_now(self, fnode: dict) -> None:
        """Build (atomically) + reveal one folder's leaf rows."""
        if not fnode["built"]:
            self._build_leaves(fnode)
            fnode["built"] = True
        fnode["open"] = True
        fnode["triangle"].configure(text="▼ ")
        fnode["children"].pack(fill="x")

    def _close_folder_now(self, fnode: dict) -> None:
        # DESTROY the leaf rows (virtualization): the live-widget count
        # tracks only currently-open folders
        for w in fnode["children"].winfo_children():
            w.destroy()
        fnode["leaf_labels"].clear()
        fnode["built"] = False
        fnode["open"] = False
        fnode["triangle"].configure(text="▶ ")
        fnode["children"].forget()

    # --- click handlers (cancel any in-flight Expand-all first) -------

    def _toggle_collection(self, node: dict) -> None:
        self._cancel_expand()
        self._set_collection_open(node, not node["open"])

    def _toggle_folder(self, fnode: dict) -> None:
        self._cancel_expand()
        if fnode["open"]:
            self._close_folder_now(fnode)
        else:
            self._open_folder_now(fnode)

    # --- Expand / Collapse all ----------------------------------------

    def _expand_all(self) -> None:
        """Open every node — but build the L3 leaf rows in folder-atomic
        chunks across ``after()`` ticks, never in one synchronous pass
        (that froze the main thread ~3 s at the owner's real queue). Each
        tick builds up to ``SELECT_EXPAND_CHUNK`` leaves (≈ one folder),
        yields to the event loop, and updates the progress cue."""
        self._cancel_expand()
        self._expand_queue = [
            (cnode, fnode)
            for cnode in self._collection_nodes
            for fnode in cnode["folders"]
            if not fnode["built"]
        ]
        self._expand_leaves_total = sum(
            len(fnode["leaves"]) for _c, fnode in self._expand_queue
        )
        if not self._expand_queue:
            # nothing to build — just reveal any collapsed collections
            for cnode in self._collection_nodes:
                self._set_collection_open(cnode, True)
            return
        # ONE scrollregion scan at the end, not one (growing) per tick
        self._scroll.suspend_scrollregion()
        self._expand_step()

    def _expand_step(self) -> None:
        """One chunk: build whole folders until the per-tick leaf budget
        is reached (always at least one, so progress is guaranteed), then
        reschedule. The collection is opened just-in-time before its first
        folder builds."""
        self._expand_job = None
        built = 0
        while self._expand_queue:
            cnode, fnode = self._expand_queue[0]
            n = len(fnode["leaves"])
            if built and built + n > SELECT_EXPAND_CHUNK:
                break  # keep this folder whole — defer to the next tick
            self._expand_queue.pop(0)
            self._set_collection_open(cnode, True)  # idempotent, once/coll
            self._open_folder_now(fnode)
            built += n
        self._update_expand_progress()
        if self._expand_queue:
            self._expand_job = self.after(
                SELECT_EXPAND_TICK_MS, self._expand_step
            )
        else:
            # final sweep: open collections that had no unbuilt folders
            for cnode in self._collection_nodes:
                self._set_collection_open(cnode, True)
            self._scroll.resume_scrollregion()  # the single settling scan
            self._hide_expand_progress()

    def _cancel_expand(self) -> None:
        """Abort an in-flight Expand-all cleanly. Folders are atomic, so
        the tree is always in a consistent state to stop at: whatever was
        built stays open+built, the rest stays closed+unbuilt."""
        if self._expand_job is not None:
            self.after_cancel(self._expand_job)
            self._expand_job = None
        self._expand_queue = []
        self._scroll.resume_scrollregion()  # scan whatever got built
        self._hide_expand_progress()

    def _update_expand_progress(self) -> None:
        remaining = sum(len(fnode["leaves"]) for _c, fnode in self._expand_queue)
        done = self._expand_leaves_total - remaining
        pct = round(done / self._expand_leaves_total * 100)
        self._progress_lbl.configure(
            text=f"Expanding… {done}/{self._expand_leaves_total} ({pct}%)"
        )

    def _hide_expand_progress(self) -> None:
        self._progress_lbl.configure(text="")

    def _collapse_all(self) -> None:
        self._cancel_expand()
        for cnode in self._collection_nodes:
            for fnode in cnode["folders"]:
                if fnode["open"]:
                    self._close_folder_now(fnode)
            self._set_collection_open(cnode, False)

    # --- selection + counts -------------------------------------------

    def _toggle_scope(self, leaves: list, site: str) -> None:
        """All/none over one scope+site: flip every ENABLED (non-done)
        leaf var. The traces coalesce into a single recount."""
        enabled = [
            leaf["sites"][site]["var"]
            for leaf in leaves
            if not leaf["sites"][site]["done"]
        ]
        if not enabled:
            return
        target = not all(v.get() for v in enabled)
        for v in enabled:
            v.set(target)

    def _mark_dirty(self, *_args) -> None:
        self._dirty = True
        if self._recount_job is None:
            self._recount_job = self.after_idle(self._recount)

    def _recount(self) -> None:
        """ONE coalesced pass: pure var-math over the cached scope
        lists. L1/L2/header count labels always exist, so there is never
        a write to a destroyed widget even while folders are collapsed."""
        self._recount_job = None
        if not self._dirty:
            return
        self._dirty = False
        total = len(self._all_leaves)
        for key in self._site_keys:
            sel = sum(
                leaf["sites"][key]["var"].get() for leaf in self._all_leaves
            )
            self._header_labels[key].configure(
                text=f"{SITES[key].name}  {sel}/{total}"
            )
        for cnode in self._count_nodes:
            leaves = cnode["leaves"]
            tot = len(leaves)
            for key in self._site_keys:
                sel = sum(leaf["sites"][key]["var"].get() for leaf in leaves)
                cnode["count"][key].configure(text=f"{sel}/{tot}")

    # --- fit-content sizing + wrapping + teardown ---------------------

    def _fit_content_width(self) -> int:
        """The open width that keeps the widest collection title on ONE
        line. A BOUNDED measure (only the ~30 L1 titles + their L2 folder
        paths, NEVER the leaves — the owner's perf rule): widest name +
        the fixed reserve (indent + triangle + the two count columns) +
        the scrollbar gutter, clamped to [SELECT_MIN_W, screen*MAX]. The
        row labels render in the ttk root font ('.' style)."""
        font = tk_font("root")
        widest = 0
        for coll in self._collections:
            widest = max(widest, font.measure(coll["label"]))
            for folder in coll["folders"]:
                widest = max(
                    widest,
                    font.measure(folder["folder"]) + SELECT_INDENT_PX,
                )
        needed = widest + SELECT_FIT_PAD_PX + SELECT_WRAP_RESERVE_PX
        needed += SELECT_SCROLLBAR_PX
        return int(min(
            max(needed, SELECT_MIN_W),
            self.winfo_screenwidth() * DOC_MAX_FRAC,
        ))

    @staticmethod
    def _wraplength_for(canvas_width: int) -> int:
        return max(canvas_width - SELECT_WRAP_RESERVE_PX, SELECT_WRAP_MIN_PX)

    def _on_canvas_configure(self, event) -> None:
        # settle-debounced like the main window's re-fit (owner
        # 2026-07-20): the wraplength re-flow re-wraps EVERY built
        # label, and the old after_idle coalescing still ran it several
        # times across one drag (the loop goes idle between <Configure>
        # bursts) — now it runs ONCE, RESIZE_SETTLE_MS after the last
        # canvas <Configure>.
        self._canvas_width = event.width
        if self._wrap_job is not None:
            self.after_cancel(self._wrap_job)
        self._wrap_job = self.after(RESIZE_SETTLE_MS, self._apply_wrap)

    def _apply_wrap(self) -> None:
        """Re-flow the wrapped names to the settled canvas width — only
        the currently-built labels (L1/L2 always, L3 only in open
        folders)."""
        self._wrap_job = None
        self._wrap = self._wraplength_for(self._canvas_width)
        for lbl in self._static_labels:
            lbl.configure(wraplength=self._wrap)
        for cnode in self._collection_nodes:
            for fnode in cnode["folders"]:
                if fnode["built"]:
                    for lbl in fnode["leaf_labels"]:
                        lbl.configure(wraplength=self._wrap)

    def _on_destroy(self, event) -> None:
        # <Destroy> bubbles up from every child — act only on our own
        if event.widget is not self:
            return
        if self in THEME_TOPLEVELS:
            THEME_TOPLEVELS.remove(self)
        for var, token in self._traces:
            var.trace_remove("write", token)
        self._traces.clear()
        for job in (self._recount_job, self._wrap_job, self._expand_job):
            if job is not None:
                self.after_cancel(job)
        self._recount_job = self._wrap_job = self._expand_job = None


class _ModalToolDialog(tk.Toplevel):
    """Shared plumbing for a small themed modal dialog: the centre-on-
    parent placement (``_center_on``). Historically shared by the
    standalone Upscale/Aspect tool dialogs too (both retired, GUI
    rework Phase 14 — replaced by ``UpscaleSettingsPanel``/
    ``AspectSettingsPanel``); today's only family is ``_AiDialog``
    (the key wizard, the sheet generator) — kept as its own base
    rather than folded into ``_AiDialog`` directly (Rule #5: a future
    non-AI modal dialog can still reuse just the placement math)."""

    def _center_on(self, master) -> None:
        """Place the dialog over the middle-upper third of the parent."""
        master.update_idletasks()
        x = master.winfo_rootx() + (master.winfo_width() - self.winfo_reqwidth()) // 2
        y = master.winfo_rooty() + (master.winfo_height() - self.winfo_reqheight()) // 3
        self.geometry(f"+{max(x, 0)}+{max(y, 0)}")


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
        palette = THEMES[ACTIVE_THEME]["ttk"]
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


class _AiDialog(_ModalToolDialog):
    """Shared plumbing of the AI dialogs (key wizard, sheet generator):
    a worker→UI queue polled on the tk loop — the worker threads ONLY
    ``self._q.put(...)`` and never touch a widget; ``_on_message``
    applies each message on the main thread. The poll dies quietly with
    the window (Rule #5 — one home for the identical loop)."""

    def _init_ai_queue(self) -> None:
        self._q: queue.Queue = queue.Queue()
        self._poll_job: str | None = None

    def _arm_poll(self) -> None:
        self._poll_job = self.after(AI_POLL_MS, self._poll)

    def _poll(self) -> None:
        self._poll_job = None
        if not self.winfo_exists():
            return  # closed mid-work — the worker's message is moot
        try:
            msg = self._q.get_nowait()
        except queue.Empty:
            self._arm_poll()
            return
        self._on_message(msg)

    def _on_message(self, msg: tuple) -> None:
        raise NotImplementedError  # each dialog applies its own messages


class AiKeyWizard(_AiDialog):
    """The guided Gemini-API-key onboarding (owner 2026-07-20): four
    numbered steps that STEER the user — open AI Studio in the browser,
    sign in with any Google account, create the key, paste it — plus a
    **Test key** that makes one tiny real call and shows OK / the loud
    error, and **Save key** persisting it to settings.json. Opened by
    the toolbar's 'AI key…' button and AUTOMATICALLY whenever an AI
    feature is invoked without a key (``NoKey``)."""

    def __init__(self, master, gui: "PainterGui"):
        super().__init__(master)
        self.title("Gemini API key — guided setup")
        self.resizable(False, False)
        skin_toplevel(self)  # bg registered so a flip re-tints the window
        self._gui = gui
        self._init_ai_queue()

        body = ttk.Frame(self, padding=ASPECT_DIALOG_PAD_PX)
        body.pack(fill="both", expand=True)
        ttk.Label(
            body, text="Get a FREE Gemini API key", style="Head.TLabel",
        ).pack(anchor="w")
        ttk.Label(
            body,
            text=(
                "The AI features (New collection, AI check) need it —"
                " a one-time setup."
            ),
            style="Muted.TLabel", wraplength=AI_STATUS_WRAP_PX,
        ).pack(anchor="w", pady=(0, 10))

        step = ttk.Frame(body)
        step.pack(fill="x", pady=2)
        ttk.Label(step, text="1.", width=3, style="Value.TLabel").pack(
            side="left"
        )
        rounded_button(
            step, "Open aistudio.google.com", command=self._open_browser,
            kind="info", icon_name="web",
        ).pack(side="left")
        for number, text in (
            ("2.", "Sign in with ANY Google account."),
            ("3.", "Press  Get API key  →  Create API key."),
            ("4.", "Copy the key and paste it below:"),
        ):
            row = ttk.Frame(body)
            row.pack(fill="x", pady=2)
            ttk.Label(row, text=number, width=3, style="Value.TLabel").pack(
                side="left"
            )
            ttk.Label(row, text=text).pack(side="left")

        self._key_var = tk.StringVar(value=gui.gemini_key)
        self._entry = rounded_entry(
            body, width=AI_KEY_ENTRY_W, textvariable=self._key_var,
        )
        self._entry.pack(fill="x", pady=(4, 8), padx=(AI_STEP_INDENT_PX, 0))

        self._status_var = tk.StringVar(value="")
        self._status_lbl = ttk.Label(
            body, textvariable=self._status_var,
            wraplength=AI_STATUS_WRAP_PX, justify="left",
        )
        self._status_lbl.pack(
            anchor="w", pady=(0, 6), padx=(AI_STEP_INDENT_PX, 0)
        )

        btns = ttk.Frame(body)
        btns.pack(fill="x", pady=(6, 0))
        rounded_button(
            btns, "Save key", command=self._save, kind="success",
        ).pack(side="right")
        self._test_btn = rounded_button(
            btns, "Test key", command=self._test, kind="info",
        )
        self._test_btn.pack(side="right", padx=6)
        rounded_button(btns, "Cancel", command=self.destroy).pack(
            side="right", padx=(0, 6)
        )

        self.bind("<Escape>", lambda _e: self.destroy())
        self.update_idletasks()
        self._center_on(master)
        self.transient(master)
        self.grab_set()
        self._entry.focus_set()
        self.wait_window(self)

    def _open_browser(self) -> None:
        webbrowser.open(AI_STUDIO_URL)

    def _show_status(self, kind: str, text: str) -> None:
        colors = {
            "ok": status("done"),
            "err": status("superseded"),
            "info": tb.Style().colors.light,
        }
        self._status_lbl.configure(foreground=colors[kind])
        self._status_var.set(text)

    def _test(self) -> None:
        """One tiny REAL call with the pasted key — OK or the loud
        error, on a worker thread so the dialog never blocks."""
        key = self._key_var.get().strip()
        if not key:
            self._show_status("err", "Paste the key first (step 4).")
            return
        self._test_btn.configure(state="disabled")
        self._show_status("info", "testing — one tiny API call …")

        def work():
            from painter import ai

            try:
                answer = ai.generate_text(AI_TEST_PROMPT, key=key)
                self._q.put(
                    ("ok",
                     f"OK — the key works (answered: {answer.strip()[:40]!r})")
                )
            except ai.AiError as exc:
                self._q.put(("err", str(exc)))

        threading.Thread(target=work, daemon=True).start()
        self._arm_poll()

    def _on_message(self, msg: tuple) -> None:
        kind, text = msg
        self._test_btn.configure(state="normal")
        self._show_status(kind, text)

    def _save(self) -> None:
        key = self._key_var.get().strip()
        if not key:
            messagebox.showerror(
                "PromptPainter", "Paste the key first (step 4).",
                parent=self,
            )
            return
        self._gui.set_gemini_key(key)
        self.destroy()


class AiSheetDialog(_AiDialog):
    """'New collection (AI)…' (owner 2026-07-20). Phase 1: the owner
    types the request (any language); the FIRST call returns a short
    clarifying POLL (the contract + questions-only system prompt).
    Phase 2: the answers (each skippable) feed the SECOND call, whose
    ``.md`` is validated with the REAL parser plus ONE automatic repair
    round. Valid → saved under ``sheets/`` (slugged name) and ADDED to
    the Collections queue; still broken → the raw md opens in a
    DocWindow for manual fixing and is NOT loaded. Both calls run on
    worker threads; progress lands in the status line + the main Log.
    Non-modal (registered in ``THEME_TOPLEVELS``) so a long generation
    never grabs the app."""

    def __init__(self, master, gui: "PainterGui"):
        super().__init__(master)
        self.title("New collection (AI)")
        self.resizable(False, False)
        skin_toplevel(self)  # bg registered so a flip re-tints the window
        THEME_TOPLEVELS.append(self)
        self._gui = gui
        self._init_ai_queue()
        self._busy = False
        self._request = ""
        self._contract = ""
        self._questions: list[str] = []
        self._answer_vars: list[tk.StringVar] = []

        body = ttk.Frame(self, padding=ASPECT_DIALOG_PAD_PX)
        body.pack(fill="both", expand=True)

        # --- phase 1: the request --------------------------------------
        self._req_box = ttk.Frame(body)
        self._req_box.pack(fill="x")
        ttk.Label(
            self._req_box, text="What should the new collection generate?",
            style="Head.TLabel",
        ).pack(anchor="w")
        ttk.Label(
            self._req_box,
            text=(
                'e.g. "Napravi mi 12 slika Astrologije" — any language;'
                " the model first asks its clarifying questions, then"
                " writes the sheet per the contract."
            ),
            style="Muted.TLabel", wraplength=AI_STATUS_WRAP_PX,
            justify="left",
        ).pack(anchor="w", pady=(0, 6))
        self._request_txt = tk.Text(
            self._req_box, height=AI_REQUEST_LINES, wrap="word",
            font=tk_font("root"), width=1,  # the pack fill sets the width
        )
        skin_text(self._request_txt)
        self._request_txt.pack(fill="x")

        # --- phase 2: the poll (filled when the questions arrive) ------
        self._poll_box = ttk.Frame(body)

        self._status_var = tk.StringVar(value="")
        ttk.Label(
            body, textvariable=self._status_var, style="Muted.TLabel",
            wraplength=AI_STATUS_WRAP_PX, justify="left",
        ).pack(anchor="w", pady=(8, 4))

        btns = ttk.Frame(body)
        btns.pack(fill="x", pady=(4, 0))
        self._go_btn = rounded_button(
            btns, "Ask questions", command=self._ask, kind="success",
            icon_name="ai",
        )
        self._go_btn.pack(side="right")
        rounded_button(btns, "Cancel", command=self.destroy).pack(
            side="right", padx=6
        )

        self.bind("<Escape>", lambda _e: self.destroy())
        self.bind("<Destroy>", self._on_destroy)
        self.update_idletasks()
        self.minsize(
            max(self.winfo_reqwidth(), AI_STATUS_WRAP_PX + 60), 0
        )
        self._center_on(master)
        self.transient(master)
        self._request_txt.focus_set()

    def apply_theme(self) -> None:
        # ttk children flip via styles; the Text and entries ride the
        # global recolour — nothing per-widget to redo here.
        pass

    def _on_destroy(self, event) -> None:
        if event.widget is self and self in THEME_TOPLEVELS:
            THEME_TOPLEVELS.remove(self)

    # --- phase transitions (main thread) --------------------------------

    def _set_busy(self, text: str) -> None:
        self._busy = True
        self._go_btn.configure(state="disabled")
        self._status_var.set(text)

    def _set_idle(self, text: str) -> None:
        self._busy = False
        self._go_btn.configure(state="normal")
        self._status_var.set(text)

    def _ask(self) -> None:
        """FIRST call — the clarifying questions."""
        if self._busy:
            return
        request = self._request_txt.get("1.0", "end").strip()
        if not request:
            messagebox.showerror(
                "PromptPainter",
                "Type what the collection should be first.", parent=self,
            )
            return
        self._request = request
        self._gui._q.put(f"[AI sheet] request: {request[:80]}")
        self._set_busy("asking the model for its clarifying questions …")

        def work():
            from painter import ai

            try:
                contract = ai.contract_text()
                questions = ai.ask_questions(request, contract)
                self._q.put(("questions", contract, questions))
            except (ai.AiError, OSError) as exc:
                self._q.put(("error", str(exc)))

        threading.Thread(target=work, daemon=True).start()
        self._arm_poll()

    def _show_questions(self, questions: list[str]) -> None:
        self._questions = questions
        self._request_txt.configure(state="disabled")  # the request is set
        ttk.Label(
            self._poll_box,
            text="The model asks (answers optional — empty = its choice):",
            style="Head.TLabel",
        ).pack(anchor="w", pady=(8, 4))
        for question in questions:
            row = ttk.Frame(self._poll_box)
            row.pack(fill="x", pady=2)
            ttk.Label(
                row, text=question, wraplength=AI_STATUS_WRAP_PX,
                justify="left",
            ).pack(anchor="w")
            var = tk.StringVar(value="")
            rounded_entry(row, textvariable=var).pack(fill="x", pady=(1, 0))
            self._answer_vars.append(var)
        self._poll_box.pack(fill="x", after=self._req_box)
        self._go_btn.configure(text="Generate sheet", command=self._generate)
        self._set_idle(
            f"{len(questions)} question(s) — answer what you care about,"
            " then Generate."
        )
        self.update_idletasks()
        self._center_on(self.master)

    def _generate(self) -> None:
        """SECOND call — the sheet + validation + one repair round."""
        if self._busy:
            return
        answers = [var.get() for var in self._answer_vars]
        request, contract = self._request, self._contract
        questions = self._questions
        log = lambda msg: self._gui._q.put(f"[AI sheet] {msg}")
        self._set_busy(
            "generating the sheet (validated with the real parser; one"
            " automatic repair round if needed) …"
        )

        def work():
            import tempfile

            from painter import ai

            try:
                with tempfile.TemporaryDirectory(
                    prefix="painter_ai_"
                ) as tmp:
                    md, problems, theme = ai.generate_sheet(
                        request, questions, answers, contract,
                        Path(tmp), log=log,
                    )
                self._q.put(("sheet", md, problems, theme))
            except ai.AiError as exc:
                self._q.put(("error", str(exc)))

        threading.Thread(target=work, daemon=True).start()
        self._arm_poll()

    def _on_message(self, msg: tuple) -> None:
        kind = msg[0]
        if kind == "error":
            self._gui._log(f"[AI sheet] ERROR: {msg[1]}")
            self._set_idle(f"ERROR: {msg[1]}")
        elif kind == "questions":
            _kind, self._contract, questions = msg
            if questions:
                self._gui._q.put(
                    f"[AI sheet] {len(questions)} clarifying question(s)"
                )
                self._show_questions(questions)
            else:
                # no parseable poll — generate straight from the request
                self._gui._q.put(
                    "[AI sheet] the model asked no questions —"
                    " generating directly"
                )
                self._set_idle("")
                self._generate()
        elif kind == "sheet":
            self._finish(md=msg[1], problems=msg[2], theme=msg[3])

    def _finish(self, md: str, problems: list[str], theme) -> None:
        if problems:
            for problem in problems:
                self._gui._log(f"[AI sheet] PROBLEM: {problem}")
            self._set_idle(
                "the sheet still fails the contract after the repair"
                " round — opened for manual fixing, NOT loaded (the"
                " problems are in the Log)."
            )
            DocWindow(
                self._gui.root, "AI sheet — fix manually (not loaded)",
                md,
                hint=(
                    "This draft fails the sheet contract — Copy it, fix"
                    " it by hand, save it and Add… it to the queue."
                ),
            )
            return  # the dialog stays open — better answers may succeed
        from painter import ai

        path = ai.save_sheet(md, theme, SHEETS_DIR)
        self._gui.add_generated_sheet(path)
        self._gui._log(
            f"[AI sheet] saved {path} — added to the Collections queue"
        )
        self.destroy()


class DocWindow(tk.Toplevel):
    """A readable, selectable in-app viewer for Markdown — for people
    who do not want a code editor. Light formatting (headings, code,
    bullets, bold) plus a one-click 'Copy for AI'. Used for the
    authoring instructions, a whole collection file, and a single
    image's prompt."""

    def __init__(
        self, master, title: str, raw_markdown: str,
        copy_text: str | None = None, hint: str | None = None,
        image_path: Path | None = None,
    ):
        super().__init__(master)
        self.title(title)
        self.minsize(DOC_MIN_W, DOC_MIN_H)
        skin_toplevel(self)  # bg registered so a flip re-tints the window
        THEME_TOPLEVELS.append(self)  # flip coherently with the main window
        self._raw = raw_markdown
        self._copy_text = copy_text if copy_text is not None else raw_markdown
        self._image_path = image_path
        self._img_ref = None  # keeps the PhotoImage alive

        bar = ttk.Frame(self, padding=6)
        bar.pack(fill="x")
        self._bar = bar  # measured by _fit_height for the non-text chrome
        if hint:
            ttk.Label(bar, text=hint, style="Muted.TLabel").pack(side="left")
        rounded_button(
            bar, "Copy (for AI)", command=self._copy_all, kind="info",
            icon_name="ai",
        ).pack(side="right")
        rounded_button(
            bar, "Close", command=self.destroy,
        ).pack(side="right", padx=4)

        wrap = ttk.Frame(self)
        wrap.pack(fill="both", expand=True, padx=6, pady=(0, 6))
        self.txt = tk.Text(
            wrap, wrap="word", font=tk_font("root"), padx=14, pady=12,
            spacing1=2, spacing3=2, cursor="arrow",
        )
        skin_text(self.txt)
        vsb = ttk.Scrollbar(
            wrap, orient="vertical", command=self.txt.yview,
            bootstyle="round",
        )
        self.txt.configure(yscrollcommand=vsb.set)
        vsb.pack(side="right", fill="y")
        self.txt.pack(side="left", fill="both", expand=True)

        self._configure_tags()
        self._apply_width()
        self._render(raw_markdown)
        self._append_image()
        # the PRECISE height needs the Text laid out at its final width,
        # which only happens once the window is MAPPED — measuring in
        # __init__ (unmapped) reads a zero-height Text. So the window opens
        # at a sensible tall provisional and _fit_height snaps it to the
        # real content on first map (one-shot).
        self.bind("<Map>", self._on_first_map)
        # read-only, but fully selectable and Ctrl+C / Ctrl+A copyable
        self.txt.bind("<Key>", self._readonly_keys)
        self.bind("<Destroy>", self._on_destroy)

    def _on_first_map(self, event) -> None:
        if event.widget is not self:
            return
        self.unbind("<Map>")
        self._fit_height()

    def _on_destroy(self, event) -> None:
        # <Destroy> bubbles up from every child — act only on our own
        if event.widget is self and self in THEME_TOPLEVELS:
            THEME_TOPLEVELS.remove(self)

    def apply_theme(self) -> None:
        """Re-run the tag config so the inserted text recolours in place
        (the Text tags carry per-tag foregrounds that do not follow ttk
        styles); the Text body bg/fg rides the global recolour."""
        self._configure_tags()

    def _apply_width(self) -> None:
        """Set the window WIDTH before rendering, so the Text wraps and
        the image scales to it. This REPLACES the old longest-line measure
        that blew the window to near-full-screen when a ~200-word prompt
        sat on one line. Two modes:
          IMAGE (a single image's prompt, image_path set): width follows
            the IMAGE — its native width + padding, clamped to the screen —
            so the picture shows large and the prompt wraps into that
            same column above it.
          TEXT (instructions / whole collection / folder excerpt): a
            portrait A4 proportion, so long one-line prompts wrap into a
            readable column instead of stretching the window."""
        max_w = int(self.winfo_screenwidth() * DOC_MAX_FRAC)
        if self._image_path is not None:
            width = self._image_native_width() + DOC_IMG_PAD_PX
        else:
            width = int(
                self.winfo_screenheight() * DOC_HEIGHT_FRAC * DOC_A4_RATIO
            )
        width = min(max(width, DOC_MIN_W), max_w)
        self._target_w = width
        # a tall provisional height (the natural size of a long doc / a
        # medallion) so the first paint is close to final; _fit_height
        # snaps it to the real content on the first <Map>.
        prov_h = min(
            max(int(self.winfo_screenheight() * DOC_HEIGHT_FRAC), DOC_MIN_H),
            int(self.winfo_screenheight() * DOC_MAX_FRAC),
        )
        self.geometry(f"{width}x{prov_h}")
        self.update_idletasks()

    def _image_native_width(self) -> int:
        """The saved image's native pixel width; a sensible min if the
        file cannot be read (the image section then just shows nothing)."""
        try:
            with Image.open(self._image_path) as img:
                return img.width
        except OSError:
            return DOC_MIN_W

    def _fit_height(self) -> None:
        """Height = the RENDERED content height (wrapped text + the
        image), clamped to a sensible min and the screen fraction; the
        vertical scrollbar takes any overflow. Measured AFTER render +
        append so the real wrapped-line and image extent are known — the
        window is portrait-ish for a tall medallion, short for a stub."""
        self.update_idletasks()
        try:
            content_h = self.txt.count("1.0", "end", "ypixels")[0]
        except (tk.TclError, TypeError, IndexError):
            content_h = 0
        needed = content_h + self._chrome_height()
        height = min(
            max(needed, DOC_MIN_H),
            int(self.winfo_screenheight() * DOC_MAX_FRAC),
        )
        self.geometry(f"{self._target_w}x{height}")

    def _chrome_height(self) -> int:
        """Everything that is NOT the Text's own line flow: the top button
        bar plus the Text padding and frame margins (DOC_CHROME_PAD_PX)."""
        return self._bar.winfo_reqheight() + DOC_CHROME_PAD_PX

    def _append_image(self) -> None:
        """The saved image, below the prompt, scaled to fit the window
        width (the viewer keeps the PhotoImage reference alive). No
        file — no section, the prompt stands alone as before."""
        if self._image_path is None:
            return
        self.update_idletasks()
        avail = max(self.winfo_width() - 80, 320)
        try:
            self._img_ref = _scaled_photo(self._image_path, avail)
        except OSError as exc:
            self._log_line(f"(image unreadable: {exc})")
            return
        self.txt.configure(state="normal")
        self.txt.insert("end", "\n")
        self.txt.image_create("end", image=self._img_ref, padx=8, pady=8)
        self.txt.insert("end", "\n")
        self.txt.configure(state="disabled")

    def _log_line(self, line: str) -> None:
        self.txt.configure(state="normal")
        self.txt.insert("end", line + "\n")
        self.txt.configure(state="disabled")

    def _configure_tags(self) -> None:
        colors = tb.Style().colors
        self.txt.tag_configure("h1", font=tk_font("doc_h1"),
                               foreground=colors.info,
                               spacing1=10, spacing3=6)
        self.txt.tag_configure("h2", font=tk_font("doc_h2"),
                               foreground=colors.info,
                               spacing1=8, spacing3=4)
        self.txt.tag_configure("h3", font=tk_font("head"),
                               foreground=status("done"),
                               spacing1=6, spacing3=3)
        self.txt.tag_configure(
            "code", font=tk_font("mono"), background=colors.dark,
            foreground=status("code_fg"), lmargin1=16, lmargin2=16,
        )
        self.txt.tag_configure("bold", font=tk_font("bold"))
        self.txt.tag_configure("bullet", lmargin1=16, lmargin2=30)

    def _render(self, md: str) -> None:
        self.txt.configure(state="normal")
        in_code = False
        for line in md.split("\n"):
            if line.startswith("```"):
                in_code = not in_code
                continue
            if in_code:
                self.txt.insert("end", line + "\n", "code")
                continue
            if line.startswith("### "):
                self.txt.insert("end", line[4:] + "\n", "h3")
            elif line.startswith("## "):
                self.txt.insert("end", line[3:] + "\n", "h2")
            elif line.startswith("# "):
                self.txt.insert("end", line[2:] + "\n", "h1")
            elif line.lstrip().startswith(("- ", "* ")):
                self._insert_inline("• " + line.lstrip()[2:] + "\n", "bullet")
            else:
                self._insert_inline(line + "\n", None)
        self.txt.configure(state="disabled")

    def _insert_inline(self, text: str, base_tag) -> None:
        """Insert a line, turning **bold** spans into the bold tag."""
        parts = text.split("**")
        for i, part in enumerate(parts):
            tags = [t for t in (base_tag,) if t]
            if i % 2 == 1:  # inside a **...** pair
                tags.append("bold")
            self.txt.insert("end", part, tuple(tags))

    def _readonly_keys(self, event):
        # allow copy/select-all and navigation; block edits
        if event.state & 0x4 and event.keysym.lower() in ("c", "a"):
            return
        if event.keysym in (
            "Left", "Right", "Up", "Down", "Home", "End", "Prior", "Next",
        ):
            return
        return "break"

    def _copy_all(self) -> None:
        self.clipboard_clear()
        self.clipboard_append(self._copy_text)
        messagebox.showinfo(
            "PromptPainter",
            "Copied to the clipboard — paste it to your AI or into a"
            " document.",
            parent=self,
        )


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
        ttk.Label(bar, text=subtitle, style="Muted.TLabel").pack(side="left")
        self._restore_btn = rounded_button(
            bar, restore_label, command=self._do_restore, kind="danger",
        )
        self._restore_btn.pack(side="right")
        rounded_button(bar, "Close", command=self.destroy).pack(
            side="right", padx=4
        )

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
        ttk.Label(
            bar,
            text="Every kept pipeline stage for this image — 'Restore"
            " to here' reverts the LIVE file to that stage.",
            style="Muted.TLabel",
        ).pack(side="left")
        rounded_button(bar, "Close", command=self.destroy).pack(side="right")

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
                    command=partial(self._do_restore, step),
                ).pack()
            else:
                ttk.Label(block, text="(current)", style="Muted.TLabel").pack()

    def _do_restore(self, step: str) -> None:
        if self._temp.restore_to(self._rel, step=step):
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


class DayNightSwitch(tk.Canvas):
    """The mini Day/Night toggle, top-right — an image pill ported from
    the owner's website switch (geometry/colours in the SWITCH_* config).
    OFF/left = MOON on the dark starfield track; ON/right = SUN (with a
    soft glow) on the sky-and-clouds track. A click flips the theme
    SYNCHRONOUSLY (the app is coherent instantly) and persists it, then a
    ~600 ms smoothstep slide runs as flourish.

    CRISP art (owner 2026-07-18): tkinter Canvas has no anti-aliasing, so
    the pill is composited from anti-aliased PIL images — the two track
    pills straight from the website SVGs, the sun/moon knobs rendered with
    a supersampled radial gradient (see the render helpers). The four
    images (+ two hover variants) are built ONCE at construction and held
    on ``self._imgs`` so tkinter cannot garbage-collect them; each redraw
    just re-places the track + knob at the animated x. The track hard-
    swaps at the knob's midpoint. The canvas is registered as a 'canvas'
    surface so its own background re-tints with the window (the pill's
    transparent corners then blend into the top strip in both themes)."""

    def __init__(self, master, gui: "PainterGui"):
        self._h = SWITCH_H
        self._pad = SWITCH_PAD_PX
        self._track_w = round(self._h * SWITCH_ASPECT)
        self._knob_d = round(self._h * SWITCH_KNOB_FACTOR)
        inset = (self._h - self._knob_d) / 2
        super().__init__(
            master,
            width=self._track_w + 2 * self._pad,
            height=self._h + 2 * self._pad,
            highlightthickness=0, bd=0, cursor="hand2",
        )
        skin_canvas(self)  # its background follows the window bg on a flip
        self._gui = gui
        self._x_off = self._pad + inset
        self._x_on = self._pad + self._track_w - self._knob_d - inset
        self._hover = False
        self._anim_job: str | None = None
        self._imgs = self._build_images()  # held so tk can't GC them
        self._on = THEMES[ACTIVE_THEME]["switch_on"]  # reflect the theme
        self._knob_x = self._x_on if self._on else self._x_off
        self.bind("<Button-1>", self._on_click)
        self.bind("<Enter>", self._on_enter)
        self.bind("<Leave>", self._on_leave)
        self._redraw()

    def _build_images(self) -> dict[str, ImageTk.PhotoImage]:
        """Render the two track pills and the sun/moon knobs (each in a
        rest + a 1.05x hover size) ONCE — the switch is a fixed size, so
        this never needs re-running (it does not follow the font zoom)."""
        ss = SWITCH_SUPERSAMPLE
        d = self._knob_d
        dh = max(round(d * SWITCH_HOVER_SCALE), d + 1)
        return {
            "track_night": ImageTk.PhotoImage(
                _render_switch_track(
                    SWITCH_TRACK_NIGHT_SVG, self._track_w, self._h
                )
            ),
            "track_day": ImageTk.PhotoImage(
                _render_switch_track(
                    SWITCH_TRACK_DAY_SVG, self._track_w, self._h
                )
            ),
            "moon": ImageTk.PhotoImage(_render_moon_knob(d, ss)),
            "moon_hover": ImageTk.PhotoImage(_render_moon_knob(dh, ss)),
            "sun": ImageTk.PhotoImage(_render_sun_knob(d, ss)),
            "sun_hover": ImageTk.PhotoImage(_render_sun_knob(dh, ss)),
        }

    # --- public API ----------------------------------------------------

    def set(self, name: str, animate: bool = False) -> None:
        """Reflect a theme name on the knob (used if the theme is set by
        something other than a click); no apply_theme call, no recursion."""
        self._on = THEMES[name]["switch_on"]
        if animate:
            self._animate()
        else:
            self._cancel_anim()
            self._knob_x = self._x_on if self._on else self._x_off
            self._redraw()

    # --- events --------------------------------------------------------

    def _on_click(self, _event=None) -> None:
        self._on = not self._on
        name = "day" if self._on else "night"
        # cross-fade the whole app (snapshot overlay hides the repaint
        # cascade); the knob slide below runs concurrently underneath it
        apply_theme(name, animate=True)
        self._gui._schedule_save()  # persist the choice
        self._animate()            # slide the knob as flourish

    def _on_enter(self, _event) -> None:
        self._hover = True
        self._redraw()

    def _on_leave(self, _event) -> None:
        self._hover = False
        self._redraw()

    # --- animation -----------------------------------------------------

    def _cancel_anim(self) -> None:
        if self._anim_job is not None:
            self.after_cancel(self._anim_job)
            self._anim_job = None

    def _animate(self) -> None:
        self._cancel_anim()
        target = self._x_on if self._on else self._x_off
        start = self._knob_x
        frames = max(round(SWITCH_ANIM_MS / SWITCH_FRAME_MS), 1)
        self._anim_i = 0

        def step():
            self._anim_i += 1
            t = self._anim_i / frames
            ease = t * t * (3 - 2 * t)  # smoothstep
            self._knob_x = start + (target - start) * ease
            self._redraw()
            if self._anim_i < frames:
                self._anim_job = self.after(SWITCH_FRAME_MS, step)
            else:
                self._knob_x = target
                self._anim_job = None
                self._redraw()

        step()

    # --- drawing -------------------------------------------------------

    def _redraw(self) -> None:
        self.delete("all")
        day = self._knob_x > (self._x_off + self._x_on) / 2
        # the track pill fills the canvas centre (transparent corners show
        # the strip bg); it hard-swaps night<->day at the knob's midpoint
        self.create_image(
            self._pad + self._track_w / 2, self._pad + self._h / 2,
            image=self._imgs["track_day" if day else "track_night"],
            anchor="center",
        )
        # the knob, centred on its animated x — the sun/moon image already
        # carries the gradient, craters and glow, so this is one placement
        base = "sun" if day else "moon"
        key = f"{base}_hover" if self._hover else base
        cx = self._knob_x + self._knob_d / 2
        cy = self._pad + self._h / 2
        self.create_image(cx, cy, image=self._imgs[key], anchor="center")


def main() -> None:
    root = tb.Window(themename="darkly")
    PainterGui(root)
    root.mainloop()


if __name__ == "__main__":
    main()
