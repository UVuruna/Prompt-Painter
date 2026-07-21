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

Two views (tabs): a **Dashboard** (up to six per-JOB panels — the two
sites plus the four in-place tools — in a responsive grid that
re-flows as jobs start and close, each with its own progress, timings
and table) and the detailed **Log**.
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
from typing import Callable

import customtkinter as ctk
import ttkbootstrap as tb
from PIL import Image, ImageColor, ImageDraw, ImageFilter, ImageGrab, ImageTk

from painter.config import (
    AI_CALL_PAUSE_S,
    AI_CHECK_INSTRUCTIONS,
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
    NEW_CHAT_CHOICES,
    RESIZE_SETTLE_MS,
    SHEETS_DIR,
    SITES,
    STATE_DIRNAME,
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
        "safer_retry", "continue_nudge", "new_chat", "pause_min", "pause_max",
        "act_min", "act_max",
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
    )

    def __init__(
        self, master, site_key: str, on_start, on_stop, on_pause,
        filter_presets: dict[str, list[dict]] | None = None,
        on_filter_presets_changed: Callable[[], None] | None = None,
    ):
        super().__init__(master)
        self.site_key = site_key
        self._on_start = on_start
        self._on_stop = on_stop
        self._on_pause = on_pause
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

        ttk.Label(
            box, text="Upscale gate (this site):", style="Head.TLabel"
        ).pack(anchor="w", pady=(4, 0))

        row = ttk.Frame(box)
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
            box, conditions=self._default_upscale_conditions,
            presets=self._filter_presets,
            on_presets_changed=self._on_filter_presets_changed,
        )
        self.upscale_filter.pack(fill="x", pady=(2, 0))

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
        active theme (see its own docstring) and, unlike its ONLY other
        host (the fully modal ``AspectRatioDialog``, which cannot be
        open during a live flip), THIS host is a normal part of the main
        window — a Day/Night flip while the fine-tune box is expanded
        must repaint it too."""
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
        button pair (full panel + collapsed strip)."""
        for start_btn, stop_btn in self._button_pairs:
            style_action_button(start_btn, "success", not running)
            style_action_button(
                stop_btn, "danger", running or pending_restart
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
    verbatim)."""
    parts = [f"# {PurePosixPath(rel).name}\n", f"`{rel}`\n"]
    if defects:
        bullets = "\n".join(f"- {d}" for d in defects)
        parts.append(f"**AI-flagged defects:**\n\n{bullets}\n")
    if raw is not None:
        parts.append(f"**Full AI response:**\n\n```\n{raw.strip()}\n```\n")
    return "\n".join(parts)


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

    Driven only by the runner's structured events (main thread).
    """

    def __init__(self, master, kind: str, on_show=None, on_close=None):
        super().__init__(master, kind, on_show=on_show, on_close=on_close)
        self._name = JOB_LABEL[kind]

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
        cols = ("done", "ai", "our", "res", "time", "size")
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
                    fmt_size(event["size"]),
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
                values=("", "", "", "REFUSED", "", ""),
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
                values=("0", "", "", "", "", fmt_size(0)),
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
            fmt_duration(wall), fmt_size(self._theme_bytes),
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
                    fmt_duration(st["time"]), fmt_size(st["size"]),
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
        self.jobtemp = None                    # painter.jobtemp.JobTemp

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
            tags = (TOOL_CHANGED_TAG,)
        elif error:
            values = ("!", time_txt, "API error — see the Log")
            tags = (TOOL_SKIP_TAG,)
        else:
            values = ("OK", time_txt, "")
            tags = (TOOL_SKIP_TAG,)
        row = self.tree.insert(
            fnode, "end", text=PurePosixPath(rel).name, values=values,
            tags=tags,
        )
        self._node_info[row] = {"level": "image", "rel": rel}
        self._image_rows[rel] = row

    # --- the defect viewer + panel actions ------------------------------

    def _file_for(self, rel: str) -> Path:
        """The image file behind one flag key — the SAME round-trip the
        checker's ``flag_key`` reverses (``ai.flag_file``), so the viewer
        can never open a different image than the one that was flagged."""
        from painter import ai

        return ai.flag_file(rel, self.out_base or Path("."))

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
        image = self._file_for(rel)
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
    gate) and ``PainterGui._start_tool``'s upscale branch (the
    standalone tool's pre-filtered file list, via ``_filter_files``) —
    both call sites apply that gate; this function alone would silently
    ignore every non-aspect condition, so it is never used alone.
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
        # per-site run state: workers, stop events, pending restarts
        self._workers: dict[str, threading.Thread] = {}
        self._stop_events: dict[str, threading.Event] = {
            key: threading.Event() for key in SITES
        }
        self._running: set[str] = set()
        # per-job PAUSE toggle (owner 2026-07-21): one threading.Event per
        # JOB_ORDER kind (all seven — the two sites plus the four tools
        # plus the AI checker), polled by the runner/worker loop between
        # items/images — see _toggle_pause_job. _paused tracks which
        # kinds are CURRENTLY paused so button labels stay in sync.
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

        # remembered dialog values (owner 2026-07-19): the standalone
        # Upscale dialog's last-used gate and the last aspect W:H —
        # restored in _apply_settings and re-saved on change. Each agent's
        # own Settings-gear collapse state is persisted by the AgentPanel.
        # GUI rework Phase 6: the old four scalar params collapsed into a
        # min-SIDE number + a FilterEditor condition stack (mirrors each
        # AgentPanel's own upscale gate) — see
        # _upscale_params_from_side_and_filter for how these resolve into
        # upscale_if_small's kwargs.
        self._upscale_tool_minside: int = UPSCALE_MIN_SIDE_DEFAULT
        self._upscale_tool_conditions: list[filters.FilterCondition] = [
            filters.FilterCondition(
                kind=FILTER_KIND_ASPECT_RANGE, polarity=FILTER_POLARITY_IF,
                lo=UPSCALE_ASPECT_MIN, hi=UPSCALE_ASPECT_MAX,
            )
        ]
        self._aspect_ratio: tuple[int, int] = (
            ASPECT_DEFAULT_W, ASPECT_DEFAULT_H
        )
        # the aspect tool's remembered optional INPUT FILTER — GUI
        # rework Phase 4: a stacked list of FilterCondition (was a
        # single from/to/mode scalar dict through 0.0.094; a one-time
        # migration in _apply_settings converts an owner's already-
        # saved scalar the first time it loads, see
        # _migrate_legacy_aspect_filter). Empty = no filter, process
        # every image — the dialog's own "+ Add condition" is how the
        # owner starts narrowing.
        self._aspect_filter_conditions: list[filters.FilterCondition] = []
        # the shared filter-preset LIBRARY every FilterEditor instance
        # reads/writes (config.FILTER_PRESETS_SETTING) — a plain
        # {name: [condition-dict, ...]} dict, mutated IN PLACE by the
        # widget itself; this reference is what makes a preset saved
        # while e.g. the Aspect dialog is open available to a BG/Crop/
        # Upscale FilterEditor later (Phase 6/13/14) without a reload.
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

        # the whole upper control area — collapsed together into the thin
        # per-agent strip (built but packed by _set_collapsed, so the
        # order is deterministic regardless of build order)
        self._collapsed = False
        self._controls_box = ttk.Frame(outer)
        self._build_queue(self._controls_box)
        self._build_options(self._controls_box)
        self._build_toolbar(self._controls_box)
        self._build_compact(outer)
        self._build_views(outer)

        self.status_var = tk.StringVar(value="idle")
        ttk.Label(
            outer, textvariable=self.status_var, style="Muted.TLabel"
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

        self._bind_zoom()
        self._bind_wheel_routing()
        self._set_collapsed(False)  # deterministic initial packing
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
        the correct availability via each panel's set_run_state."""
        self._compact_box = ttk.Frame(parent)
        for key in sorted(SITES):
            cluster = self.agents[key].build_compact(self._compact_box)
            cluster.pack(side="left", padx=(0, COMPACT_CLUSTER_GAP_PX))
        for key, panel in self.agents.items():
            panel.set_run_state(
                running=key in self._running,
                pending_restart=key in self._restart_jobs,
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

        # the two per-agent panels side by side — everything below the
        # shared Output line is PER SITE (full agent separation)
        agents = ttk.Frame(lf)
        agents.pack(fill="x", pady=(4, 2))
        self.agents: dict[str, AgentPanel] = {}
        for i, key in enumerate(sorted(SITES)):
            panel = AgentPanel(
                agents, key,
                on_start=self._start_site, on_stop=self._stop_site,
                on_pause=self._toggle_pause_job,
                filter_presets=self._filter_presets,
                on_filter_presets_changed=self._on_filter_presets_changed,
            )
            panel.grid(row=0, column=i, sticky="nsew", padx=4)
            agents.columnconfigure(i, weight=1)
            self.agents[key] = panel

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
        # the four in-place tools — each its OWN concurrent job + panel,
        # carrying the panel's colour + its PNG icon (owner 2026-07-19,
        # replacing the old emoji). Packed reversed so they read BG
        # removal / Crop / Upscale / Aspect ratio left→right.
        for slot in reversed(JOB_TOOL_KINDS):
            color = job_color_pair(slot)
            rounded_button(
                row, JOB_LABEL[slot], icon_name=slot,
                command=partial(self._start_tool, slot),
                fg_color=color, hover_color=_darken_pair(color),
                text_color=status_pair("btn_text"),
            ).pack(side="right", padx=4)

        # the AI features row (owner 2026-07-20): the sheet GENERATOR,
        # the batch image CHECKER (its own job/panel like the tools, in
        # its rose job colour) and the guided key wizard — a SECOND row
        # so the tool row never clips at the window minimum.
        ai_row = ttk.Frame(parent)
        ai_row.pack(fill="x", pady=(0, 6))
        rounded_button(
            ai_row, "New collection (AI)…", icon_name="ai",
            command=self._new_collection_ai,
        ).pack(side="left")
        color = job_color_pair("aicheck")
        rounded_button(
            ai_row, f"{JOB_LABEL['aicheck']}…", icon_name=JOB_LOGO["aicheck"],
            command=self._start_ai_check,
            fg_color=color, hover_color=_darken_pair(color),
            text_color=status_pair("btn_text"),
        ).pack(side="left", padx=4)
        rounded_button(
            ai_row, "AI key…", command=self._open_key_wizard,
        ).pack(side="right")

    def _build_views(self, parent) -> None:
        self.notebook = ttk.Notebook(parent)
        self.notebook.pack(fill="both", expand=True)

        dash_tab = ttk.Frame(self.notebook)
        self.notebook.add(dash_tab, text="Dashboard")
        # BUILD-ONCE per-JOB panels in a responsive DashGrid: the two gen
        # sites plus the four tools, NONE gridded until its job starts.
        # A panel appears on Start / a tool click, gets CLOSE when done,
        # and the grid re-flows by active count (gen sites first).
        self._dashgrid = DashGrid(dash_tab)
        self.panels: dict[str, JobPanel] = {}
        for key in ("chatgpt", "gemini"):
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
        self._log(f"[{kind}] {'paused' if is_paused else 'resumed'}")

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

    @staticmethod
    def _tool_func(kind: str):
        """The engine function behind a PARAMETERLESS tool (bg / crop).
        Aspect binds its ratio and Upscale its four gate params in
        _start_tool. Lazy import so the GUI opens even while the engine
        modules build."""
        if kind == "bg":
            from painter.postprocess import remove_background
            return remove_background
        from painter.postprocess import crop_transparent
        return crop_transparent

    @staticmethod
    def _iter_images(folder: Path) -> list[Path]:
        return iter_images(folder)

    def _remember_aspect_ratio(self, ratio_w: int, ratio_h: int) -> None:
        """Persist the last-entered aspect W:H so the dialog pre-fills it
        next time (owner 2026-07-19)."""
        self._aspect_ratio = (ratio_w, ratio_h)
        self._schedule_save()

    def _remember_aspect_filter_conditions(
        self, conditions: list[filters.FilterCondition]
    ) -> None:
        """Persist the aspect tool's last-used stacked FILTER so the
        dialog pre-fills it next time (owner 2026-07-19; conditions
        since GUI rework Phase 4)."""
        self._aspect_filter_conditions = list(conditions)
        self._schedule_save()

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

    def _remember_upscale_tool_params(self, choice: dict) -> None:
        """Persist the standalone Upscale dialog's last-used min-side +
        filter so it pre-fills them next run (owner 2026-07-19; GUI
        rework Phase 6: ``choice`` is ``UpscaleParamsDialog.result`` —
        ``{"min_side": int, "conditions": list[FilterCondition]}``,
        replacing the old four-scalar-dict shape)."""
        self._upscale_tool_minside = choice["min_side"]
        self._upscale_tool_conditions = list(choice["conditions"])
        self._schedule_save()

    def _start_tool(self, slot: str) -> None:
        """Start ONE in-place tool as its OWN job: pick a folder (aspect
        asks for a ratio first), confirm, then back up + process every
        image under it on a dedicated worker thread, reporting into the
        slot's own dashboard panel. One job per kind — a second click
        while it runs is refused; up to all four tools + both sites run
        in parallel (6 panels)."""
        if slot in self._tool_workers:
            messagebox.showerror(
                "PromptPainter",
                f"{JOB_LABEL[slot]} is already running — wait for it to"
                " finish, or Close its panel.",
            )
            return

        label = JOB_LABEL[slot]
        if slot == "aspect":
            # Aspect accepts individual image FILES or a whole FOLDER (the
            # optional input filter makes folders useful — skip the
            # already-good ones). One folder can hold images of DIFFERENT
            # ratios, so a single target is never blanket-applied blindly;
            # the filter gates which images are touched. The other three
            # tools stay folder-based. The dialog PRE-FILLS the last-used
            # ratio + filter (both remembered). (owner 2026-07-19)
            choice = AspectRatioDialog(
                self.root, *self._aspect_ratio,
                conditions=self._aspect_filter_conditions,
                presets=self._filter_presets,
                on_presets_changed=self._on_filter_presets_changed,
            ).result
            if choice is None:
                return
            ratio_w, ratio_h = choice["ratio"]
            conditions = choice["conditions"]
            self._remember_aspect_ratio(ratio_w, ratio_h)
            self._remember_aspect_filter_conditions(conditions)
            from painter.aspect import change_aspect

            # the GUI pre-filters WHICH FILES are touched (below) via
            # filters.matches() itself now — change_aspect's OWN scalar
            # filter_from/filter_to/filter_mode stay at their off
            # defaults, unused (its signature is otherwise untouched —
            # GUI rework Phase 4)
            func = (
                lambda path, log: change_aspect(path, ratio_w, ratio_h, log)
            )
            label = f"Aspect {ratio_w}:{ratio_h}"
            if choice["input"] == "folder":
                folder = filedialog.askdirectory(
                    title=f"Folder with images — {label} runs IN PLACE"
                )
                if not folder:
                    return
                folder_path = Path(folder)
                files = self._iter_images(folder_path)
            else:
                picks = filedialog.askopenfilenames(
                    title=f"Image files to deform — {label} runs IN PLACE",
                    filetypes=[
                        ("Images", "*.png *.jpg *.jpeg *.webp"),
                        ("All files", "*.*"),
                    ],
                )
                if not picks:
                    return
                folder_path, _rels = selection_base_and_rels(picks)
                files = [Path(p) for p in picks]
            total_before = len(files)
            files = _filter_files(files, conditions, self._log)
            filt_note = (
                f"\nFilter: {len(conditions)} condition(s) —"
                f" {len(files)} of {total_before} image(s) match"
                if conditions else ""
            )
            message = (
                f"DEFORM {len(files)} image(s)\n\n"
                f"to a {ratio_w}:{ratio_h} aspect ratio?{filt_note}\n\n"
                "A non-proportional STRETCH written IN PLACE — the"
                " originals are backed up so you can Restore. Images"
                f" already at {ratio_w}:{ratio_h} are skipped untouched."
            )
        else:
            # only the upscale branch below ever populates this; BG/Crop
            # leave it empty, making the shared _filter_files() call a
            # no-op for them (mirrors the Aspect branch's own unconditional
            # call above)
            upscale_conditions: list[filters.FilterCondition] = []
            if slot == "upscale":
                # Upscale asks its min-side + FilterEditor gate first
                # (owner 2026-07-19; GUI rework Phase 6 replaced the old
                # four scalar fields with ONE min-side spinner + a
                # stacked FilterEditor), PRE-FILLED with the last-used
                # values; then runs folder-based like BG/Crop with that
                # gate bound.
                choice = UpscaleParamsDialog(
                    self.root,
                    {
                        "min_side": self._upscale_tool_minside,
                        "conditions": self._upscale_tool_conditions,
                    },
                    presets=self._filter_presets,
                    on_presets_changed=self._on_filter_presets_changed,
                ).result
                if choice is None:
                    return
                self._remember_upscale_tool_params(choice)
                upscale_conditions = choice["conditions"]
                up_params = _upscale_params_from_side_and_filter(
                    choice["min_side"], upscale_conditions
                )
                from painter.upscale import upscale_if_small

                func = (
                    lambda path, log: upscale_if_small(
                        path, log, **up_params
                    )
                )
                label = f"Upscale ≥{up_params['min_width']}px min side"
            else:
                func = self._tool_func(slot)
            folder = filedialog.askdirectory(
                title=f"Folder with images — {label} runs IN PLACE"
            )
            if not folder:
                return
            folder_path = Path(folder)
            files = self._iter_images(folder_path)
            # the standalone Upscale tool pre-filters its candidate file
            # list the SAME way Aspect does above (root Rule #1: this is
            # how a stacked Width/Height/Any-side condition — or a SECOND
            # aspect condition — gets honored, since the simple upscale
            # kwargs above can only express ONE aspect band; see
            # _upscale_params_from_side_and_filter's docstring). A no-op
            # for BG/Crop (upscale_conditions is always [] for them).
            total_before = len(files)
            files = _filter_files(files, upscale_conditions, self._log)
            filt_note = (
                f"\nFilter: {len(upscale_conditions)} condition(s) —"
                f" {len(files)} of {total_before} image(s) match"
                if upscale_conditions else ""
            )
            message = (
                f"{label} IN PLACE for every image under:\n{folder}?"
                f"{filt_note}\n\n"
                "(the originals are backed up so you can Restore; files"
                " with nothing to do are skipped untouched)"
            )
        if not messagebox.askyesno("PromptPainter", message):
            return

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
        worker = threading.Thread(
            target=self._run_tool_job,
            args=(
                slot, label, func, folder_path, files, temp,
                self._pause_events[slot],
            ),
            daemon=True,
        )
        self._tool_workers[slot] = worker
        worker.start()

    def _run_tool_job(
        self, slot, label, func, folder, files, temp, pause_event,
    ) -> None:
        """One tool job on its own thread: back up each original, run
        the engine func in place, measure BEFORE→AFTER, and stream item
        events to the slot's panel. A crash on one file is loud and
        counted FAILED (its no-op backup dropped), never kills the job.
        The measure is computed OUTSIDE the engine, from the backup vs
        the in-place result (Rule #10 progress every 25). ``pause_event``
        (owner 2026-07-21) blocks BETWEEN images while set — tools have
        no Stop, so unlike run_sheet this wait has no should_stop escape
        hatch; it simply waits for Resume."""
        from painter.runner import wait_while_paused

        emit = lambda ev: self._q.put(("__event__", slot, ev))
        log = lambda msg: self._q.put(f"[{label}]     {msg}")
        try:
            self._q.put(f"[{label}] {len(files)} image(s) under {folder}")
            emit({"type": "sheet_start", "total": len(files)})
            counts: dict[str, int] = {}
            t0 = time.time()
            for i, src in enumerate(files, start=1):
                wait_while_paused(pause_event.is_set, None, log, emit)
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

    def _start_ai_check(self) -> None:
        """'AI check…' — a batch vision pass over a folder of images as
        its OWN job/panel (read-only: it writes NOTHING but the flag
        file under <out>/_state/). One job at a time, like the tools."""
        if "aicheck" in self._tool_workers:
            messagebox.showerror(
                "PromptPainter",
                f"{JOB_LABEL['aicheck']} is already running — wait for it"
                " to finish, or Close its panel.",
            )
            return
        if not self._ensure_ai_key():
            return
        folder = filedialog.askdirectory(
            title="Folder with images — AI check (read-only)"
        )
        if not folder:
            return
        folder_path = Path(folder)
        files = iter_images(folder_path)
        if not files:
            messagebox.showinfo(
                "PromptPainter", f"No images under:\n{folder}"
            )
            return
        out_base = self._out_base()
        if not messagebox.askyesno(
            "PromptPainter",
            f"AI-check {len(files)} image(s) under:\n{folder}?\n\n"
            "Each image goes to the Gemini vision model (banal defects"
            f" only), paced ~{AI_CALL_PAUSE_S:.0f}s per call on the free"
            " tier. Nothing is modified; flags persist under\n"
            f"{out_base / STATE_DIRNAME}.",
        ):
            return

        panel = self.panels["aicheck"]
        panel.folder = folder_path
        panel.out_base = out_base
        panel.reset(active=True, total=len(files))
        self._dashgrid.add("aicheck")
        self.notebook.select(0)
        self.status_var.set(f"{JOB_LABEL['aicheck']} running …")

        if "aicheck" in self._paused:
            self._toggle_pause_job("aicheck")  # never start pre-paused
        worker = threading.Thread(
            target=self._run_ai_check_job,
            args=(folder_path, files, out_base, self._pause_events["aicheck"]),
            daemon=True,
        )
        self._tool_workers["aicheck"] = worker
        worker.start()

    def _run_ai_check_job(self, folder, files, out_base, pause_event) -> None:
        """The checker worker: prune stale flags (regenerated files),
        then one paced vision call per image — flagged entries are
        recorded (merged) into the flag file as they land, an OK image
        CLEARS any old flag it had, and a per-image API failure is loud
        but never kills the batch (the tool-job convention). ``pause_event``
        (owner 2026-07-21) blocks BETWEEN images while set, the same
        wait pattern as the in-place tools (no should_stop — there is
        no Stop for this job either)."""
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
                wait_while_paused(pause_event.is_set, None, log, emit)
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

    def _compose_post_save(self, key: str):
        """The site's post-save hook per ITS panel switches — the same
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
        saved image is unaffected either way."""
        panel = self.agents[key]
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
        # not inherit its old backups; mirrors _start_tool's own
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
        self.panels[key].reset(
            active=True, task_total=total, task_themes=themes
        )
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
        worker = threading.Thread(
            target=self._drive_site,
            args=(
                key,
                list(sheets),
                out_base,
                timing,
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

    def _drive_site(
        self, key, sheets, out_base, timing, post_save, suffix,
        extra_suffix, report, selection, safer, continue_nudge, new_chat,
        stop_event, pause_event,
    ) -> None:
        """One site's whole run — the theme queue in order, one thread."""
        log = lambda msg: self._q.put(f"[{key}] {msg}")
        events = lambda ev: self._q.put(("__event__", key, ev))
        driver = None
        done_sheets = 0
        # the WHOLE body is guarded so __worker_done__ is ALWAYS posted
        # (even if the imports or driver construction fail) — otherwise
        # the site's Start button would stay disabled forever
        try:
            from painter.driver import DriverError, SiteDriver, TerminalState
            from painter.runner import run_sheet

            driver = SiteDriver(SITES[key], timing, CDP_URL)
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
            if driver is not None:
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
            elif msg[0] == "__terminal__":
                self._handle_terminal(msg[1], msg[2])
            elif msg[0] == "__tool_done__":
                slot = msg[1]
                self.panels[slot].finish()  # reveal CLOSE
                self._tool_workers.pop(slot, None)
                # a job that finished its last image right as it was
                # paused would otherwise leave a stale "paused" toggle
                # on an idle panel (owner 2026-07-21)
                if slot in self._paused:
                    self._toggle_pause_job(slot)
                if not self._tool_workers and not self._running:
                    self._update_status()
            elif msg[0] == "__worker_done__":
                key = msg[1]
                self._log(f"[{key}] worker finished")
                # the worker posts this from its finally block
                # while its thread is still technically alive
                self._running.discard(key)
                self._workers.pop(key, None)
                if key in self._paused:  # same stale-pause guard as above
                    self._toggle_pause_job(key)
                self.agents[key].set_run_state(
                    running=False,
                    pending_restart=key in self._restart_jobs,
                )
                # a pending quota auto-restart keeps the panel
                # alive (countdown, no CLOSE yet); otherwise the
                # site is done — reveal its CLOSE button
                if key not in self._restart_jobs:
                    self.panels[key].finish()
                self._update_status()
        else:
            self._log(str(msg))

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
            # GUI rework Phase 6: min-side + a FilterEditor condition
            # stack, replacing the old four-scalar shape (see
            # _migrate_legacy_upscale_gate for the one-time inverse)
            "upscale_tool": {
                "min_side": self._upscale_tool_minside,
                "conditions": [
                    filters.condition_to_dict(c)
                    for c in self._upscale_tool_conditions
                ],
            },
            "aspect_ratio": list(self._aspect_ratio),
            "aspect_filter_conditions": [
                filters.condition_to_dict(c)
                for c in self._aspect_filter_conditions
            ],
            FILTER_PRESETS_SETTING: {
                name: list(rows) for name, rows in self._filter_presets.items()
            },
            "agents": {
                key: panel.get_settings()
                for key, panel in self.agents.items()
            },
        }

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

        # remembered dialog values (owner 2026-07-19): the standalone
        # Upscale gate and the last aspect W:H (each agent's own
        # Settings-gear collapse state is restored in panel.apply_settings
        # above). Each falls back to the current default on a missing key.
        #
        # GUI rework Phase 6: the NEW {"min_side", "conditions"} shape
        # wins when present; otherwise a ONE-TIME LOUD migration reads
        # the OLD {"min_width", "min_height", "aspect_min", "aspect_max"}
        # shape exactly once (same up_minh-dropped rationale as the
        # per-agent migration above) — never written back, see
        # _collect_settings, which no longer emits the old field names.
        saved_up = stored.get("upscale_tool")
        if isinstance(saved_up, dict) and "min_side" in saved_up:
            try:
                self._upscale_tool_minside = int(saved_up["min_side"])
            except (TypeError, ValueError):
                self._log(
                    f"SETTINGS: upscale_tool.min_side {saved_up['min_side']!r}"
                    " is not a number — keeping the shipped default"
                )
            raw_conditions = saved_up.get("conditions")
            if isinstance(raw_conditions, list):
                self._upscale_tool_conditions = _parse_condition_dicts(
                    raw_conditions, self._log
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
                    f" ({exc}) — using the shipped default upscale gate"
                )
            else:
                self._log(
                    "MIGRATION: legacy standalone 'upscale_tool'"
                    " (min_width/min_height/aspect_min/aspect_max) ->"
                    f" min_side={migrated['min_side']} + 1 filter"
                    " condition (one-time; the old keys stay on disk"
                    " unread from now on)"
                )
                self._upscale_tool_minside = migrated["min_side"]
                self._upscale_tool_conditions = _parse_condition_dicts(
                    migrated["conditions"], self._log
                )
        saved_ratio = stored.get("aspect_ratio")
        if (
            isinstance(saved_ratio, (list, tuple)) and len(saved_ratio) == 2
        ):
            self._aspect_ratio = (int(saved_ratio[0]), int(saved_ratio[1]))

        # the aspect tool's stacked filter (GUI rework Phase 4): the
        # NEW key wins when present; otherwise a ONE-TIME LOUD
        # migration reads the OLD scalar key exactly once — it is
        # never written back (see _collect_settings, which no longer
        # emits "aspect_filter" at all — the key naturally drops off
        # disk on the next save, the same way a stale "sash" key does)
        saved_conditions = stored.get("aspect_filter_conditions")
        if isinstance(saved_conditions, list):
            self._aspect_filter_conditions = _parse_condition_dicts(
                saved_conditions, self._log
            )
        else:
            legacy = stored.get("aspect_filter")
            if isinstance(legacy, dict):
                try:
                    migrated = _migrate_legacy_aspect_filter(legacy)
                except (TypeError, ValueError) as exc:
                    self._log(
                        f"MIGRATION: legacy aspect_filter {legacy!r} is"
                        f" unreadable ({exc}) — starting with no aspect"
                        " filter"
                    )
                    migrated = []
                else:
                    self._log(
                        "MIGRATION: legacy 'aspect_filter' setting"
                        f" {legacy!r} -> {len(migrated)} condition(s), now"
                        " under 'aspect_filter_conditions' (one-time; the"
                        " old key stays on disk unread from now on)"
                    )
                self._aspect_filter_conditions = _parse_condition_dicts(
                    migrated, self._log
                )

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
    """Shared plumbing for the small themed modal tool dialogs
    (``AspectRatioDialog``, ``UpscaleParamsDialog``): the centre-on-parent
    placement they both use (Rule #5 — one home for the identical
    geometry math)."""

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
    exposes ``redraw_theme()`` for a host to call explicitly. THIS
    widget's host (``AspectRatioDialog``) is fully MODAL (``grab_set``),
    so — exactly like ``AiKeyWizard`` (see its docstring) — a flip
    cannot happen while it is open, and the dialog deliberately does
    NOT register in ``THEME_TOPLEVELS``: there is nothing to wire. A
    FUTURE non-modal host (Phase 14's persistent Aspect-ratio settings
    panel) calls ``redraw_theme()`` from ITS OWN ``apply_theme()`` —
    the pattern every other themed Toplevel already follows."""

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


class AspectRatioDialog(_ModalToolDialog):
    """The MODAL prompt for the standalone 'Aspect ratio…' deform tool.

    Asks THREE things (owner 2026-07-19; the filter became a stacked
    FilterEditor in GUI rework Phase 4):
      * the target OUTPUT ratio — two positive-integer fields W and H,
        PRE-FILLED with the last-used ratio (first run 16:9);
      * an optional stacked INPUT FILTER on each image's CURRENT
        size/ratio — zero or more ANDed conditions, remembered;
      * whether the input is individual FILES or a whole FOLDER — the two
        action buttons ('Files…' / 'Folder…') encode the choice.

    ``result`` is ``None`` on Cancel / Escape, else a dict
    ``{"ratio": (w, h), "conditions": list[FilterCondition],
    "input": "files"|"folder"}``. Themed like the app."""

    def __init__(
        self, master,
        default_w: int = ASPECT_DEFAULT_W, default_h: int = ASPECT_DEFAULT_H,
        conditions: list[filters.FilterCondition] | None = None,
        presets: dict[str, list[dict]] | None = None,
        on_presets_changed: Callable[[], None] | None = None,
    ):
        super().__init__(master)
        self.title("Change aspect ratio")
        self.resizable(False, False)
        skin_toplevel(self)  # bg registered so a flip re-tints the window
        self.result: dict | None = None
        self._w_var = tk.StringVar(value=str(default_w))
        self._h_var = tk.StringVar(value=str(default_h))

        body = ttk.Frame(self, padding=ASPECT_DIALOG_PAD_PX)
        body.pack(fill="both", expand=True)

        top = ttk.Frame(body)
        top.pack(anchor="w", fill="x")

        left_col = ttk.Frame(top)
        left_col.pack(side="left", anchor="n")
        ttk.Label(
            left_col,
            text="Target aspect ratio — stretches every image to it:",
        ).pack(anchor="w", pady=(0, 10))

        fields = ttk.Frame(left_col)
        fields.pack(anchor="w")
        ttk.Label(fields, text="W").pack(side="left", padx=(0, 4))
        self._w_entry = rounded_entry(
            fields, width=ASPECT_DIALOG_ENTRY_W, textvariable=self._w_var,
            justify="center",
        )
        self._w_entry.pack(side="left")
        ttk.Label(fields, text=":", font=tk_font("head")).pack(
            side="left", padx=8
        )
        ttk.Label(fields, text="H").pack(side="left", padx=(0, 4))
        self._h_entry = rounded_entry(
            fields, width=ASPECT_DIALOG_ENTRY_W, textvariable=self._h_var,
            justify="center",
        )
        self._h_entry.pack(side="left")

        # the visual editor (GUI rework Phase 5), beside the fields and
        # TWO-WAY synced with them: dragging an edge writes the W/H vars
        # (_on_canvas_drag), whose trace reshapes the box right back —
        # AspectRatioCanvas.set_ratio's echo-guard makes that a no-op;
        # typing in the fields reshapes the box (_on_wh_typed).
        self._canvas = AspectRatioCanvas(
            top, w=default_w, h=default_h, on_change=self._on_canvas_drag,
        )
        self._canvas.pack(side="left", padx=(ASPECT_DIALOG_PAD_PX, 0), anchor="n")
        self._w_var.trace_add("write", self._on_wh_typed)
        self._h_var.trace_add("write", self._on_wh_typed)

        # --- optional stacked INPUT FILTER on the current size/ratio ---
        ttk.Label(
            body,
            text=(
                "Optional filter on each image's CURRENT size/ratio\n"
                "— no conditions = process every image:"
            ),
        ).pack(anchor="w", pady=(14, 6))
        self._filter_editor = FilterEditor(
            body, conditions=conditions, presets=presets,
            on_presets_changed=on_presets_changed,
        )
        self._filter_editor.pack(fill="x")

        btns = ttk.Frame(body)
        btns.pack(fill="x", pady=(16, 0))
        rounded_button(
            btns, "Files…", command=partial(self._run, "files"),
            kind="success",
        ).pack(side="right")
        rounded_button(
            btns, "Folder…", command=partial(self._run, "folder"),
            kind="info",
        ).pack(side="right", padx=6)
        rounded_button(btns, "Cancel", command=self.destroy).pack(
            side="right", padx=(0, 6)
        )

        # Enter defaults to the multi-FILE pick (the tool's original input)
        self.bind("<Return>", lambda _e: self._run("files"))
        self.bind("<Escape>", lambda _e: self.destroy())
        self.update_idletasks()
        self._center_on(master)
        self.transient(master)
        self.grab_set()
        self._w_entry.focus_set()
        self.wait_window(self)

    def _on_canvas_drag(self, w: int, h: int) -> None:
        """``AspectRatioCanvas.on_change`` — a drag mirrored into the W/H
        entries, which is what ``_run()`` actually reads (and whose own
        trace calls back into ``set_ratio`` — a no-op echo, see that
        method's docstring)."""
        self._w_var.set(str(w))
        self._h_var.set(str(h))

    def _on_wh_typed(self, *_args) -> None:
        """Live-reshape the canvas as the owner types a new W/H. A bad
        or incomplete value (mid-edit — e.g. a momentarily empty field)
        is a normal typing state, not an error: silently skipped, the
        canvas just keeps showing the last valid shape. Final validation
        still happens in ``_run()`` on Files…/Folder…."""
        try:
            w = int(self._w_var.get().strip())
            h = int(self._h_var.get().strip())
        except ValueError:
            return
        if w <= 0 or h <= 0:
            return
        self._canvas.set_ratio(w, h)

    def _run(self, input_mode: str) -> None:
        """Validate the ratio (positive whole numbers) and the filter
        editor's rows, then close with ``result`` set for the chosen
        ``input_mode``. A bad value stays open with a loud message."""
        try:
            ratio_w = int(self._w_var.get().strip())
            ratio_h = int(self._h_var.get().strip())
        except ValueError:
            messagebox.showerror(
                "PromptPainter",
                "Width and height must be whole numbers.", parent=self,
            )
            return
        if ratio_w <= 0 or ratio_h <= 0:
            messagebox.showerror(
                "PromptPainter",
                "Width and height must both be positive.", parent=self,
            )
            return

        try:
            conditions = self._filter_editor.get_conditions()
        except ValueError as exc:
            messagebox.showerror("PromptPainter", str(exc), parent=self)
            return

        self.result = {
            "ratio": (ratio_w, ratio_h),
            "conditions": conditions,
            "input": input_mode,
        }
        self.destroy()


class UpscaleParamsDialog(_ModalToolDialog):
    """The MODAL prompt for the standalone Upscale tool's gate (GUI
    rework Phase 6, replacing the old four-field min-W/min-H/aspect-
    FROM/aspect-TO layout): ONE min-SIDE spinner — the smaller side's
    target minimum, in px — plus an embedded stacked ``FilterEditor``
    deciding WHICH images qualify, PRE-FILLED with the last-used values
    the caller remembers (first run = today's aspect gate, a single
    Aspect (range) 0.9-1.1 condition, config default 800px min side).

    ``result`` is ``{"min_side": int, "conditions":
    list[FilterCondition]}`` on Run, or ``None`` on Cancel / Escape —
    the caller (``PainterGui._start_tool``) resolves this into
    ``upscale_if_small``'s kwargs via
    ``_upscale_params_from_side_and_filter`` AND separately pre-filters
    the candidate file list via the SAME conditions (root Rule #1: a
    stacked Width/Height/Any-side condition — or a second/IF-NOT aspect
    condition the simple kwargs cannot express — must still gate the
    run, never silently dropped). Themed like the app (skinned Toplevel
    + rounded fields / buttons)."""

    def __init__(
        self, master, defaults: dict,
        presets: dict[str, list[dict]] | None = None,
        on_presets_changed: Callable[[], None] | None = None,
    ):
        super().__init__(master)
        self.title("Upscale settings")
        self.resizable(False, False)
        skin_toplevel(self)  # bg registered so a flip re-tints the window
        self.result: dict | None = None
        self._minside_var = tk.StringVar(value=str(defaults["min_side"]))

        body = ttk.Frame(self, padding=ASPECT_DIALOG_PAD_PX)
        body.pack(fill="both", expand=True)
        ttk.Label(
            body,
            text=(
                "Upscale gate — an image is enlarged so its smaller\n"
                "side reaches this minimum, but only when it also\n"
                "matches the filter below:"
            ),
        ).pack(anchor="w", pady=(0, 10))

        dims = ttk.Frame(body)
        dims.pack(anchor="w")
        ttk.Label(dims, text="min side", width=8).pack(side="left")
        Spinner(dims, self._minside_var, step=UPSCALE_MINDIM_STEP).pack(
            side="left"
        )
        ttk.Label(dims, text="px").pack(side="left", padx=(4, 0))

        ttk.Label(
            body,
            text=(
                "Optional filter on each image's CURRENT size/ratio\n"
                "— no conditions = process every image:"
            ),
        ).pack(anchor="w", pady=(14, 6))
        self._filter_editor = FilterEditor(
            body, conditions=defaults["conditions"], presets=presets,
            on_presets_changed=on_presets_changed,
        )
        self._filter_editor.pack(fill="x")

        btns = ttk.Frame(body)
        btns.pack(fill="x", pady=(14, 0))
        rounded_button(btns, "Run", command=self._run, kind="success").pack(
            side="right"
        )
        rounded_button(btns, "Cancel", command=self.destroy).pack(
            side="right", padx=6
        )

        self.bind("<Return>", lambda _e: self._run())
        self.bind("<Escape>", lambda _e: self.destroy())
        self.update_idletasks()
        self._center_on(master)
        self.transient(master)
        self.grab_set()
        self.focus_set()
        self.wait_window(self)

    def _run(self) -> None:
        """Validate the min-side spinner (a positive number) and the
        filter editor's rows, then close with ``result`` set; a bad
        value stays open with a loud message."""
        try:
            min_side = int(float(self._minside_var.get().strip()))
        except ValueError:
            messagebox.showerror(
                "PromptPainter",
                "Min side must be a number.", parent=self,
            )
            return
        if min_side <= 0:
            messagebox.showerror(
                "PromptPainter",
                "Min side must be positive.", parent=self,
            )
            return
        try:
            conditions = self._filter_editor.get_conditions()
        except ValueError as exc:
            messagebox.showerror("PromptPainter", str(exc), parent=self)
            return
        self.result = {"min_side": min_side, "conditions": conditions}
        self.destroy()


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
