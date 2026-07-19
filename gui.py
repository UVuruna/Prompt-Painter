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
from dataclasses import replace
from tkinter import font as tkfont
from datetime import datetime
from functools import partial
from pathlib import Path, PurePosixPath
from tkinter import filedialog, messagebox, ttk

import customtkinter as ctk
import ttkbootstrap as tb
from PIL import Image, ImageColor, ImageDraw, ImageFilter, ImageGrab, ImageTk

from painter.config import (
    ASPECT_DEFAULT_H,
    ASPECT_DEFAULT_W,
    ASPECT_FILTER_DEFAULT_FROM,
    ASPECT_FILTER_DEFAULT_TO,
    ASPECT_FILTER_IF,
    ASPECT_FILTER_MODES,
    ASPECT_FILTER_OFF,
    BACKGROUND_CHOICES,
    CDP_URL,
    CHECKER_DARK,
    CHECKER_LIGHT,
    CHECKER_TILE_PX,
    DEFAULT_OUT_DIR,
    GRID_COLS_BY_COUNT,
    JOB_LABEL,
    JOB_LOGO,
    JOB_METRIC,
    JOB_ORDER,
    JOB_TOOL_KINDS,
    NEW_CHAT_CHOICES,
    RESIZE_SETTLE_MS,
    SITES,
    STYLE_CHOICES,
    STYLE_DEFAULT,
    SWITCH_ANIM_MS,
    SWITCH_ASPECT,
    SWITCH_COVER_ICON_FRAC,
    SWITCH_COVER_ICON_SS,
    SWITCH_CRATER,
    SWITCH_CRATERS,
    SWITCH_FADE_MS,
    SWITCH_FADE_STEPS,
    SWITCH_FRAME_MS,
    SWITCH_H,
    SWITCH_HOVER_SCALE,
    SWITCH_KNOB_FACTOR,
    SWITCH_KNOB_HILIGHT,
    SWITCH_MOON_CENTER,
    SWITCH_MOON_EDGE,
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
    UPSCALE_ASPECT_DECIMALS,
    UPSCALE_ASPECT_MAX,
    UPSCALE_ASPECT_MIN,
    UPSCALE_ASPECT_STEP,
    UPSCALE_MIN_HEIGHT,
    UPSCALE_MIN_WIDTH,
    UPSCALE_MINDIM_STEP,
    dest_for,
    fmt_duration,
    fmt_op_duration,
    fmt_pct,
    fmt_size,
    iter_images,
    button_fill_pair,
    button_text_pair,
    job_color_pair,
    prompt_suffix,
    selection_base_and_rels,
    status_pair,
    theme_pair,
)
from painter import jobtemp
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

# --- Aspect-ratio prompt (the standalone 'Aspect ratio…' tool) -------
ASPECT_DIALOG_ENTRY_W = 64  # px width of each W / H field in the ratio dialog
ASPECT_DIALOG_PAD_PX = 16   # padding around the ratio dialog body

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
    """The MOON: a silver radial-gradient sphere with 3 darker craters,
    anti-aliased. ``d_px`` = final diameter, ``ss`` = supersample factor."""
    s = d_px * ss
    disc = _radial_disc(
        s, SWITCH_MOON_CENTER, SWITCH_MOON_EDGE, SWITCH_KNOB_HILIGHT
    )
    draw = ImageDraw.Draw(disc)
    crater = (*ImageColor.getrgb(SWITCH_CRATER), 255)
    for cf, cxf, cyf in SWITCH_CRATERS:
        cd = s * cf
        ccx, ccy = cxf * s, cyf * s
        draw.ellipse(
            [ccx - cd / 2, ccy - cd / 2, ccx + cd / 2, ccy + cd / 2],
            fill=crater,
        )
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
    """A rounded read-only dropdown bound to ``variable``."""
    opts = _input_colors()
    opts.update(
        button_color=theme_pair("secondary"),
        button_hover_color=_darken_pair(theme_pair("secondary")),
        dropdown_fg_color=theme_pair("dark"),
        dropdown_hover_color=theme_pair("selectbg"),
        dropdown_text_color=theme_pair("fg"),
    )
    opts.update(kwargs)
    field = ctk.CTkComboBox(
        parent, values=list(values), variable=variable, width=width,
        height=INPUT_HEIGHT, corner_radius=INPUT_RADIUS, border_width=1,
        state="readonly", font=ctk_font("root"),
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


# --- Theme cross-fade (snapshot overlay) -----------------------------
# tkinter has no native colour transitions, so a LIVE flip repaints as a
# visible cascade of half-themed frames (black boxes, half-styled
# spinners). apply_theme(animate=True) hides that cascade: grab the
# OLD-theme window, show it in a borderless topmost overlay, repaint the
# real window underneath in the NEW theme, then fade the overlay's window
# alpha out and destroy it. It is a pure visual nicety — any failure
# (ImageGrab unavailable, alpha unsupported, an occluded window) degrades
# to the plain instant flip, never a stuck overlay or an un-themed app.


def _snapshot_overlay(root: tk.Misc, target_name: str) -> tk.Toplevel:
    """Grab the root window's client area (PIL.ImageGrab), composite the
    NEXT theme's big sun/moon icon centred on it, and mount the result in
    a borderless, topmost, fully-opaque Toplevel placed exactly over the
    window. The icon is baked INTO the snapshot (its transparent
    surroundings blend onto the grab) so the whole cover fades as one.
    The PhotoImage is held on the overlay (tk keeps no ref of its own) so
    it survives the whole fade."""
    x, y = root.winfo_rootx(), root.winfo_rooty()
    w, h = root.winfo_width(), root.winfo_height()
    snap = ImageGrab.grab(bbox=(x, y, x + w, y + h)).convert("RGBA")
    icon = _render_theme_cover_icon(target_name, min(w, h))
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


def _fade_out_overlay(root: tk.Misc, overlay: tk.Toplevel) -> None:
    """Ramp the overlay's window alpha 1.0 -> 0.0 across SWITCH_FADE_STEPS
    root.after ticks (ease-out — the stale snapshot clears fast, then
    eases), then destroy it. A destroyed-mid-fade overlay (TclError) ends
    the ramp cleanly, so no overlay is ever left stuck on screen."""
    steps = max(SWITCH_FADE_STEPS, 1)
    interval = max(round(SWITCH_FADE_MS / steps), 1)

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


def apply_theme(name: str, animate: bool = False) -> None:
    """The ONE coherent flip, used by BOTH startup and the toggle.

    Startup passes ``animate=False`` (no window exists yet) for an
    instant flip. The switch passes ``animate=True``: when the window is
    on-screen the whole repaint cascade is hidden behind a SNAPSHOT
    CROSS-FADE (see _snapshot_overlay / _fade_out_overlay). The cross-fade
    is a visual nicety only — any failure in the snapshot/overlay/alpha
    path is caught, any partial overlay is destroyed, and the plain
    instant flip runs instead (a one-line note is logged, root Rule #1)."""
    root = tb.Style().master
    if not (
        animate and root is not None
        and root.winfo_ismapped() and root.winfo_viewable()
    ):
        _apply_theme_now(name)
        return
    overlay = None
    try:
        overlay = _snapshot_overlay(root, name)
        # FORCE the cover fully mapped + painted by the window manager
        # BEFORE any theme repaint runs, so the half-themed cascade is
        # NEVER seen — only the snapshot + the next theme's sun/moon
        # (owner 2026-07-19; the old order let the cascade flash through).
        overlay.deiconify()
        overlay.lift()
        overlay.update_idletasks()
        overlay.update()            # DWM actually paints the cover now
        _apply_theme_now(name)      # repaint the real window BEHIND the cover
        root.update_idletasks()     # force the cascade to settle, hidden
        _fade_out_overlay(root, overlay)
    except Exception as exc:        # visual nicety — never crash the flip
        if overlay is not None:
            try:
                overlay.destroy()
            except tk.TclError:
                pass
        print(f"[theme] cross-fade unavailable, flipped instantly: {exc}")
        _apply_theme_now(name)


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
        if self._stretch:
            self.canvas.itemconfigure(self._win, width=event.width)
        # DEBOUNCE (owner 2026-07-19): a window drag / maximize fires
        # <Configure> many times a second; running the fill-height +
        # scrollregion bbox scan on EACH is the customtkinter re-render
        # jank. The width track (above) stays live so content follows the
        # window, but the heavy re-fit is deferred. The FIRST configure of
        # a SETTLED window (initial layout / a lone resize) fills height at
        # once so the viewport never shows a dead strip; once a resize is
        # underway (_resizing) the re-fit is deferred and runs ONCE on
        # settle, not per frame.
        if not self._resizing:
            self._apply_fill_height()
        self._arm_settle()

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
        """The size settled — clear the resize flag and run ONE re-fit
        (fill-height + scrollregion), coalesced like ``_on_body``."""
        self._settle_job = None
        self._resizing = False
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
        # per-agent upscale-gate fine-tune (owner 2026-07-19)
        "up_minw", "up_minh", "up_aspmin", "up_aspmax",
        # this agent's own Settings-gear collapse state (owner 2026-07-19)
        "settings_collapsed",
    )

    def __init__(self, master, site_key: str, on_start, on_stop):
        super().__init__(master)
        self.site_key = site_key
        self._on_start = on_start
        self._on_stop = on_stop
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
        # per-agent upscale-gate fine-tune (owner 2026-07-19): min W /
        # min H / aspect from / aspect to. Defaults reproduce the old
        # locked rule; shown only when the Settings collapse is expanded.
        self.up_minw_var = tk.StringVar(value=str(UPSCALE_MIN_WIDTH))
        self.up_minh_var = tk.StringVar(value=str(UPSCALE_MIN_HEIGHT))
        self.up_aspmin_var = tk.StringVar(
            value=f"{UPSCALE_ASPECT_MIN:.{UPSCALE_ASPECT_DECIMALS}f}"
        )
        self.up_aspmax_var = tk.StringVar(
            value=f"{UPSCALE_ASPECT_MAX:.{UPSCALE_ASPECT_DECIMALS}f}"
        )
        # this agent's OWN Settings-gear collapse state (owner 2026-07-19):
        # True = fine-tune hidden (default). A BooleanVar so it persists and
        # auto-saves through the same per-agent trace as every other field.
        self.settings_collapsed_var = tk.BooleanVar(value=True)

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

    def _build_finetune(self) -> None:
        """This agent's collapsible FINE-TUNE area (owner 2026-07-19),
        hidden behind its Settings gear: the PAUSE range, the ACTION-DELAY
        range, and the UPSCALE-GATE fields (min W / min H / aspect from /
        aspect to). Built into ``self._finetune_box`` and left UNPACKED —
        ``_apply_finetune_visibility`` packs it in when the gear expands."""
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

        ttk.Label(
            box, text="Upscale gate (this site):", style="Head.TLabel"
        ).pack(anchor="w", pady=(4, 0))

        row = ttk.Frame(box)
        row.pack(fill="x", pady=2)
        ttk.Label(row, text="min W", width=6).pack(side="left")
        Spinner(row, self.up_minw_var, step=UPSCALE_MINDIM_STEP).pack(
            side="left"
        )
        ttk.Label(row, text="min H", width=6).pack(side="left", padx=(8, 0))
        Spinner(row, self.up_minh_var, step=UPSCALE_MINDIM_STEP).pack(
            side="left"
        )
        ttk.Label(row, text="px").pack(side="left", padx=(2, 0))

        row = ttk.Frame(box)
        row.pack(fill="x", pady=2)
        ttk.Label(row, text="aspect", width=6).pack(side="left")
        Spinner(
            row, self.up_aspmin_var, step=UPSCALE_ASPECT_STEP,
            decimals=UPSCALE_ASPECT_DECIMALS,
        ).pack(side="left")
        ttk.Label(row, text="–").pack(side="left", padx=2)
        Spinner(
            row, self.up_aspmax_var, step=UPSCALE_ASPECT_STEP,
            decimals=UPSCALE_ASPECT_DECIMALS,
        ).pack(side="left")
        ttk.Label(row, text="W/H").pack(side="left", padx=(2, 0))

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
        of the other site. The var change persists via its own trace."""
        self.settings_collapsed_var.set(
            not self.settings_collapsed_var.get()
        )
        self._apply_finetune_visibility()

    def upscale_params(self) -> dict:
        """The four upscale-gate numbers as engine kwargs — ValueError
        propagates to the caller's Start validation."""
        return {
            "min_width": int(float(self.up_minw_var.get())),
            "min_height": int(float(self.up_minh_var.get())),
            "aspect_min": float(self.up_aspmin_var.get()),
            "aspect_max": float(self.up_aspmax_var.get()),
        }

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
            "up_minw": self.up_minw_var,
            "up_minh": self.up_minh_var,
            "up_aspmin": self.up_aspmin_var,
            "up_aspmax": self.up_aspmax_var,
            "settings_collapsed": self.settings_collapsed_var,
        }

    def persist_vars(self) -> list[tk.Variable]:
        return list(self._vars().values())

    def get_settings(self) -> dict:
        return {key: var.get() for key, var in self._vars().items()}

    def apply_settings(self, stored: dict) -> None:
        """Missing keys keep the current defaults; the restored collapse
        state is reflected into the panel."""
        variables = self._vars()
        for key in self._PERSIST:
            if key in stored:
                variables[key].set(stored[key])
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
    show).
    """

    def __init__(self, master, kind: str, on_show=None, on_close=None):
        super().__init__(master, padding=6)
        self.slot_key = kind
        self._on_show = on_show   # called with a node-info dict on 'Show'
        self._on_close = on_close  # called with the slot key on CLOSE
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

        # the state line — quota auto-restart countdown / current item
        self.state_var = tk.StringVar(value="")
        ttk.Label(
            self, textvariable=self.state_var, style="Muted.TLabel"
        ).pack(anchor="w")

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

    def _do_close(self) -> None:
        if self._on_close is not None:
            self._on_close(self.slot_key)


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
            child = self.tree.insert(
                fnode, "end", text=PurePosixPath(drop).name,
                values=(
                    "", f"{event['gen_s']:.0f}s", "…", res, "",
                    fmt_size(event["size"]),
                ),
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

    def __init__(self, master, kind: str, on_close=None):
        super().__init__(master, kind, on_show=None, on_close=on_close)
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

        wrap = ttk.Frame(self)
        wrap.pack(fill="both", expand=True, pady=(2, 0))
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
        self.tree = ttk.Treeview(wrap, columns=self._cols, height=8)
        self.tree.heading("#0", text="Name")
        self.tree.column("#0", width=200, minwidth=120, stretch=False)
        for cid, txt, w, anc in col_specs:
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
        # the SKIPPED-row tag follows the active theme's muted colour and
        # re-tints on a flip (registered in the plain-tk skin registry)
        skin_tree(self.tree)
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
        if self._times:
            total = sum(self._times)
            avg = total / len(self._times)
            self.time_var.set(
                f"⏱ {fmt_op_duration(total)} total"
                f"   ·   {fmt_op_duration(avg)}/img"
            )
        else:
            self.time_var.set("⏱ —")

    # --- tree building -------------------------------------------------

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
        self._restart_jobs: dict[str, str] = {}  # site -> after id
        self._restart_deadline: dict[str, float] = {}  # site -> monotonic
        # the four in-place tools each run as their OWN job (one worker
        # thread + one dashboard panel per kind; one job per kind at a
        # time). Each holds a JobTemp of the originals it backed up.
        self._tool_workers: dict[str, threading.Thread] = {}
        self._tool_temps: dict[str, jobtemp.JobTemp] = {}
        # sweep any crash-orphaned tool backups from a previous session
        jobtemp.clear_all()
        # (site, source-path, drop-path) -> BooleanVar; missing = ticked
        self._select_vars: dict[tuple[str, str, str], tk.BooleanVar] = {}
        self._save_job: str | None = None  # debounced settings save

        # remembered dialog values (owner 2026-07-19): the standalone
        # Upscale dialog's last-used four params and the last aspect W:H —
        # restored in _apply_settings and re-saved on change. Each agent's
        # own Settings-gear collapse state is persisted by the AgentPanel.
        self._upscale_tool_params: dict = {
            "min_width": UPSCALE_MIN_WIDTH,
            "min_height": UPSCALE_MIN_HEIGHT,
            "aspect_min": UPSCALE_ASPECT_MIN,
            "aspect_max": UPSCALE_ASPECT_MAX,
        }
        self._aspect_ratio: tuple[int, int] = (
            ASPECT_DEFAULT_W, ASPECT_DEFAULT_H
        )
        # the aspect tool's remembered optional INPUT FILTER (owner
        # 2026-07-19): a W/H range + a mode (off / IF / IF NOT). Off by
        # default; the dialog pre-fills the ~square band when first used.
        self._aspect_filter: dict = {
            "from": ASPECT_FILTER_DEFAULT_FROM,
            "to": ASPECT_FILTER_DEFAULT_TO,
            "mode": ASPECT_FILTER_OFF,
        }

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
        self._set_collapsed(not self._collapsed)
        self._schedule_save()

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
        clear that job's temp backups (tools only). The panel widget
        survives (build-once) — reset_finished hides its CLOSE for the
        next run, and the next Start re-adds it."""
        self._dashgrid.remove(kind)
        self.panels[kind].reset_finished()
        temp = self._tool_temps.pop(kind, None)
        if temp is not None:
            temp.clear()

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

    def _add_sheets(self) -> None:
        paths = filedialog.askopenfilenames(
            title="Prompt sheets", filetypes=[("Markdown", "*.md")]
        )
        for raw in paths:
            path = Path(raw)
            if path not in self._sheets:
                self._sheets.append(path)
                self.sheet_list.insert("end", path.name)
        self._schedule_save()

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

    def _remember_aspect_filter(self, filt: dict) -> None:
        """Persist the aspect tool's last-used INPUT FILTER (from / to /
        mode) so the dialog pre-fills it next time (owner 2026-07-19)."""
        self._aspect_filter = dict(filt)
        self._schedule_save()

    def _remember_upscale_params(self, params: dict) -> None:
        """Persist the standalone Upscale dialog's last-used four params
        so it pre-fills them next run (owner 2026-07-19)."""
        self._upscale_tool_params = dict(params)
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
                self.root, *self._aspect_ratio, self._aspect_filter
            ).result
            if choice is None:
                return
            ratio_w, ratio_h = choice["ratio"]
            filt = choice["filter"]
            self._remember_aspect_ratio(ratio_w, ratio_h)
            self._remember_aspect_filter(filt)
            from painter.aspect import change_aspect

            func = (
                lambda path, log: change_aspect(
                    path, ratio_w, ratio_h, log,
                    filter_from=filt["from"], filter_to=filt["to"],
                    filter_mode=filt["mode"],
                )
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
            filt_note = (
                f"\nFilter: {filt['mode']} {filt['from']}–{filt['to']} (W/H)"
                if filt["mode"] != ASPECT_FILTER_OFF else ""
            )
            message = (
                f"DEFORM {len(files)} image(s)\n\n"
                f"to a {ratio_w}:{ratio_h} aspect ratio?{filt_note}\n\n"
                "A non-proportional STRETCH written IN PLACE — the"
                " originals are backed up so you can Restore. Images"
                f" already at {ratio_w}:{ratio_h} (or filtered out) are"
                " skipped untouched."
            )
        else:
            if slot == "upscale":
                # Upscale asks its FOUR gate params first (owner
                # 2026-07-19), PRE-FILLED with the last-used values; then
                # runs folder-based like BG/Crop with those params bound.
                params = UpscaleParamsDialog(
                    self.root, self._upscale_tool_params
                ).result
                if params is None:
                    return
                self._remember_upscale_params(params)
                from painter.upscale import upscale_if_small

                func = (
                    lambda path, log: upscale_if_small(path, log, **params)
                )
                label = (
                    f"Upscale ≥{params['min_width']}x{params['min_height']}"
                )
            else:
                func = self._tool_func(slot)
            folder = filedialog.askdirectory(
                title=f"Folder with images — {label} runs IN PLACE"
            )
            if not folder:
                return
            folder_path = Path(folder)
            files = self._iter_images(folder_path)
            message = (
                f"{label} IN PLACE for every image under:\n{folder}?\n\n"
                "(the originals are backed up so you can Restore; files"
                " with nothing to do are skipped untouched)"
            )
        if not messagebox.askyesno("PromptPainter", message):
            return

        # a finished panel for this slot may still be on screen — clear
        # its old temp before the new job takes the slot
        old = self._tool_temps.pop(slot, None)
        if old is not None:
            old.clear()
        temp = jobtemp.JobTemp(slot, folder_path)
        self._tool_temps[slot] = temp

        panel = self.panels[slot]
        panel.folder = folder_path
        panel.jobtemp = temp
        panel.reset(active=True, total=len(files))
        self._dashgrid.add(slot)
        self.notebook.select(0)
        self.status_var.set(f"{label} running …")

        worker = threading.Thread(
            target=self._run_tool_job,
            args=(slot, label, func, folder_path, files, temp),
            daemon=True,
        )
        self._tool_workers[slot] = worker
        worker.start()

    def _run_tool_job(self, slot, label, func, folder, files, temp) -> None:
        """One tool job on its own thread: back up each original, run
        the engine func in place, measure BEFORE→AFTER, and stream item
        events to the slot's panel. A crash on one file is loud and
        counted FAILED (its no-op backup dropped), never kills the job.
        The measure is computed OUTSIDE the engine, from the backup vs
        the in-place result (Rule #10 progress every 25)."""
        emit = lambda ev: self._q.put(("__event__", slot, ev))
        log = lambda msg: self._q.put(f"[{label}]     {msg}")
        try:
            self._q.put(f"[{label}] {len(files)} image(s) under {folder}")
            emit({"type": "sheet_start", "total": len(files)})
            counts: dict[str, int] = {}
            t0 = time.time()
            for i, src in enumerate(files, start=1):
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

    def _compose_post_save(self, key: str):
        """The site's post-save hook per ITS panel switches — the same
        shape the CLI builds: ``post_save(path) -> "REMOVE BG: done,
        CROP: done, ..."`` (the runner logs the description and guards
        the call itself — a failing step never kills the run). Returns
        None when every switch is off, or the deps-problem string when
        the steps cannot run at all."""
        panel = self.agents[key]
        do_bg = panel.bg_removal_var.get()
        do_crop = panel.crop_var.get()
        do_upscale = panel.upscale_var.get()
        if not (do_bg or do_crop or do_upscale):
            return None

        from painter.postprocess import deps_error

        problem = deps_error()
        if problem:
            return problem

        # this agent's four upscale-gate params, read ONCE at Start (like
        # the pace values) — validated by the caller before we get here
        up_params = panel.upscale_params() if do_upscale else {}
        log = lambda msg: self._q.put(f"[{key}]     {msg}")

        def post_save(path: Path) -> str:
            from painter.postprocess import (
                crop_transparent,
                remove_background,
            )

            parts = []
            if do_bg:
                parts.append(f"REMOVE BG: {remove_background(path, log)}")
            if do_crop:
                parts.append(f"CROP: {crop_transparent(path, log)}")
            if do_upscale:
                from painter.upscale import upscale_if_small

                parts.append(
                    f"UPSCALE: {upscale_if_small(path, log, **up_params)}"
                )
            return ", ".join(parts)

        return post_save

    def _start_site(self, key: str) -> None:
        """Start ONE site — the other site's run is never touched."""
        if key in self._running:
            return
        self._cancel_restart(key)  # a manual Start beats the timer
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
                    f"{SITES[key].name}: Upscale-gate values must be numbers.",
                )
                return
            if up["min_width"] <= 0 or up["min_height"] <= 0 or (
                up["aspect_min"] <= 0 or up["aspect_max"] <= 0
            ):
                messagebox.showerror(
                    "PromptPainter",
                    f"{SITES[key].name}: Upscale-gate min W/H and aspect"
                    " bounds must all be positive.",
                )
                return
            if up["aspect_min"] > up["aspect_max"]:
                messagebox.showerror(
                    "PromptPainter",
                    f"{SITES[key].name}: Upscale aspect FROM must be <= TO.",
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
        selection: dict[str, set[str] | None] = {}
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
                panel.report_var.get(),
                selection,
                panel.safer_var.get(),
                panel.continue_nudge_var.get(),
                panel.new_chat_var.get(),
                self._stop_events[key],
            ),
            daemon=True,
        )
        self._workers[key] = worker
        worker.start()

    def _drive_site(
        self, key, sheets, out_base, timing, post_save, suffix, report,
        selection, safer, continue_nudge, new_chat, stop_event,
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
                        post_save=post_save,
                        prompt_suffix=suffix,
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
                        if not self._tool_workers and not self._running:
                            self._update_status()
                    elif msg[0] == "__worker_done__":
                        key = msg[1]
                        self._log(f"[{key}] worker finished")
                        # the worker posts this from its finally block
                        # while its thread is still technically alive
                        self._running.discard(key)
                        self._workers.pop(key, None)
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
        except queue.Empty:
            pass
        self.root.after(120, self._drain_queue)

    # --- settings persistence ------------------------------------------

    def _collect_settings(self) -> dict:
        return {
            "output": self.out_var.get(),
            "font_base": FONT_BASE,
            "theme": ACTIVE_THEME,
            "geometry": self.root.geometry(),
            "controls_collapsed": self._collapsed,
            "upscale_tool": dict(self._upscale_tool_params),
            "aspect_ratio": list(self._aspect_ratio),
            "aspect_filter": dict(self._aspect_filter),
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
            panel.apply_settings(stored.get("agents", {}).get(key, {}))

        # remembered dialog values (owner 2026-07-19): the standalone
        # Upscale params and the last aspect W:H (each agent's own
        # Settings-gear collapse state is restored in panel.apply_settings
        # above). Each falls back to the current default on a missing key.
        saved_up = stored.get("upscale_tool")
        if isinstance(saved_up, dict):
            for k in self._upscale_tool_params:
                if k in saved_up:
                    self._upscale_tool_params[k] = saved_up[k]
        saved_ratio = stored.get("aspect_ratio")
        if (
            isinstance(saved_ratio, (list, tuple)) and len(saved_ratio) == 2
        ):
            self._aspect_ratio = (int(saved_ratio[0]), int(saved_ratio[1]))
        saved_filter = stored.get("aspect_filter")
        if isinstance(saved_filter, dict):
            for k in self._aspect_filter:
                if k in saved_filter:
                    self._aspect_filter[k] = saved_filter[k]

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
        # drop every live tool job's backups, then sweep the whole temp
        # root (belt-and-braces for any orphan)
        for temp in list(self._tool_temps.values()):
            temp.clear()
        self._tool_temps.clear()
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
        self._canvas_width = event.width
        if self._wrap_job is None:
            self._wrap_job = self.after_idle(self._apply_wrap)

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


class AspectRatioDialog(_ModalToolDialog):
    """The MODAL prompt for the standalone 'Aspect ratio…' deform tool.

    Asks THREE things (owner 2026-07-19):
      * the target OUTPUT ratio — two positive-integer fields W and H,
        PRE-FILLED with the last-used ratio (first run 16:9);
      * an optional INPUT FILTER on each image's CURRENT ratio (W/H) —
        a [from, to] range plus a mode (off / IF / IF NOT), remembered;
      * whether the input is individual FILES or a whole FOLDER — the two
        action buttons ('Files…' / 'Folder…') encode the choice.

    ``result`` is ``None`` on Cancel / Escape, else a dict
    ``{"ratio": (w, h), "filter": {"from": float|None, "to": float|None,
    "mode": str}, "input": "files"|"folder"}``. Themed like the app."""

    def __init__(
        self, master,
        default_w: int = ASPECT_DEFAULT_W, default_h: int = ASPECT_DEFAULT_H,
        filter_defaults: dict | None = None,
    ):
        super().__init__(master)
        self.title("Change aspect ratio")
        self.resizable(False, False)
        skin_toplevel(self)  # bg registered so a flip re-tints the window
        self.result: dict | None = None
        self._w_var = tk.StringVar(value=str(default_w))
        self._h_var = tk.StringVar(value=str(default_h))
        fd = filter_defaults or {}
        _dec = UPSCALE_ASPECT_DECIMALS
        self._mode_var = tk.StringVar(
            value=fd.get("mode", ASPECT_FILTER_OFF)
        )
        self._from_var = tk.StringVar(
            value=f"{fd.get('from', ASPECT_FILTER_DEFAULT_FROM):.{_dec}f}"
        )
        self._to_var = tk.StringVar(
            value=f"{fd.get('to', ASPECT_FILTER_DEFAULT_TO):.{_dec}f}"
        )

        body = ttk.Frame(self, padding=ASPECT_DIALOG_PAD_PX)
        body.pack(fill="both", expand=True)
        ttk.Label(
            body, text="Target aspect ratio — stretches every image to it:",
        ).pack(anchor="w", pady=(0, 10))

        fields = ttk.Frame(body)
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

        # --- optional INPUT FILTER on the current ratio ----------------
        ttk.Label(
            body,
            text=(
                "Optional filter on each image's CURRENT ratio (W/H)\n"
                "— off = process every image:"
            ),
        ).pack(anchor="w", pady=(14, 6))
        filt = ttk.Frame(body)
        filt.pack(anchor="w")
        rounded_combo(
            filt, ASPECT_FILTER_MODES, self._mode_var, width=88,
        ).pack(side="left", padx=(0, 10))
        rounded_entry(
            filt, width=ASPECT_DIALOG_ENTRY_W, textvariable=self._from_var,
            justify="center",
        ).pack(side="left")
        ttk.Label(filt, text="–").pack(side="left", padx=6)
        rounded_entry(
            filt, width=ASPECT_DIALOG_ENTRY_W, textvariable=self._to_var,
            justify="center",
        ).pack(side="left")
        ttk.Label(filt, text="W/H").pack(side="left", padx=(4, 0))

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

    def _run(self, input_mode: str) -> None:
        """Validate the ratio (positive whole numbers) and, when the mode
        is not off, the filter range (positive reals, FROM <= TO); then
        close with ``result`` set for the chosen ``input_mode``. A bad
        value stays open with a loud message."""
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

        mode = self._mode_var.get()
        filt_from = filt_to = None
        if mode != ASPECT_FILTER_OFF:
            try:
                filt_from = float(self._from_var.get().strip())
                filt_to = float(self._to_var.get().strip())
            except ValueError:
                messagebox.showerror(
                    "PromptPainter",
                    "The filter range must be numbers (or set the mode to"
                    " off).", parent=self,
                )
                return
            if filt_from <= 0 or filt_to <= 0:
                messagebox.showerror(
                    "PromptPainter",
                    "The filter range must be positive.", parent=self,
                )
                return
            if filt_from > filt_to:
                messagebox.showerror(
                    "PromptPainter",
                    "Filter FROM must be <= TO.", parent=self,
                )
                return

        self.result = {
            "ratio": (ratio_w, ratio_h),
            "filter": {"from": filt_from, "to": filt_to, "mode": mode},
            "input": input_mode,
        }
        self.destroy()


class UpscaleParamsDialog(_ModalToolDialog):
    """The MODAL prompt for the standalone Upscale tool's four gate
    params — min WIDTH, min HEIGHT, aspect FROM, aspect TO — PRE-FILLED
    with the last-used values the caller remembers (first run = config
    defaults 800/800/0.9/1.1). ``result`` is the engine-kwargs dict
    ``{"min_width", "min_height", "aspect_min", "aspect_max"}`` on Run,
    or ``None`` on Cancel / Escape. Themed like the app (skinned Toplevel
    + rounded fields / buttons)."""

    def __init__(self, master, defaults: dict):
        super().__init__(master)
        self.title("Upscale settings")
        self.resizable(False, False)
        skin_toplevel(self)  # bg registered so a flip re-tints the window
        self.result: dict | None = None
        self._minw_var = tk.StringVar(value=str(defaults["min_width"]))
        self._minh_var = tk.StringVar(value=str(defaults["min_height"]))
        self._aspmin_var = tk.StringVar(
            value=f"{defaults['aspect_min']:.{UPSCALE_ASPECT_DECIMALS}f}"
        )
        self._aspmax_var = tk.StringVar(
            value=f"{defaults['aspect_max']:.{UPSCALE_ASPECT_DECIMALS}f}"
        )

        body = ttk.Frame(self, padding=ASPECT_DIALOG_PAD_PX)
        body.pack(fill="both", expand=True)
        ttk.Label(
            body,
            text=(
                "Upscale gate — an image is enlarged only when its\n"
                "aspect W/H is in range AND it is under a minimum:"
            ),
        ).pack(anchor="w", pady=(0, 10))

        dims = ttk.Frame(body)
        dims.pack(anchor="w")
        ttk.Label(dims, text="min W", width=6).pack(side="left")
        self._minw_entry = rounded_entry(
            dims, width=ASPECT_DIALOG_ENTRY_W, textvariable=self._minw_var,
            justify="center",
        )
        self._minw_entry.pack(side="left")
        ttk.Label(dims, text="min H", width=6).pack(side="left", padx=(10, 0))
        rounded_entry(
            dims, width=ASPECT_DIALOG_ENTRY_W, textvariable=self._minh_var,
            justify="center",
        ).pack(side="left")
        ttk.Label(dims, text="px").pack(side="left", padx=(4, 0))

        asp = ttk.Frame(body)
        asp.pack(anchor="w", pady=(8, 0))
        ttk.Label(asp, text="aspect", width=6).pack(side="left")
        rounded_entry(
            asp, width=ASPECT_DIALOG_ENTRY_W, textvariable=self._aspmin_var,
            justify="center",
        ).pack(side="left")
        ttk.Label(asp, text="–").pack(side="left", padx=8)
        rounded_entry(
            asp, width=ASPECT_DIALOG_ENTRY_W, textvariable=self._aspmax_var,
            justify="center",
        ).pack(side="left")
        ttk.Label(asp, text="W/H").pack(side="left", padx=(4, 0))

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
        self._minw_entry.focus_set()
        self.wait_window(self)

    def _run(self) -> None:
        """Validate the four fields as positive numbers (min W/H whole,
        aspect real) with FROM <= TO, then close with ``result`` set as
        engine kwargs; a bad value stays open with a loud message."""
        try:
            min_width = int(float(self._minw_var.get().strip()))
            min_height = int(float(self._minh_var.get().strip()))
            aspect_min = float(self._aspmin_var.get().strip())
            aspect_max = float(self._aspmax_var.get().strip())
        except ValueError:
            messagebox.showerror(
                "PromptPainter",
                "All four fields must be numbers.", parent=self,
            )
            return
        if min(min_width, min_height, aspect_min, aspect_max) <= 0:
            messagebox.showerror(
                "PromptPainter",
                "Min W/H and aspect bounds must all be positive.",
                parent=self,
            )
            return
        if aspect_min > aspect_max:
            messagebox.showerror(
                "PromptPainter",
                "Aspect FROM must be <= aspect TO.", parent=self,
            )
            return
        self.result = {
            "min_width": min_width, "min_height": min_height,
            "aspect_min": aspect_min, "aspect_max": aspect_max,
        }
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
