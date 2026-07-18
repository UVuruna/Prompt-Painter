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

Two views (tabs): a **Dashboard** (per-site panels in a draggable
paned layout — progress for the current collection AND the whole
task, timings, and the collections table) and the detailed **Log**.
"""

from __future__ import annotations

import io
import json
import queue
import random
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
from PIL import Image, ImageTk

from painter.config import (
    BACKGROUND_CHOICES,
    CDP_URL,
    DEFAULT_OUT_DIR,
    NEW_CHAT_CHOICES,
    PROGRESS_SUFFIX,
    SITES,
    STATE_DIRNAME,
    TIMING,
    dest_for,
    fmt_duration,
    fmt_size,
    prompt_suffix,
)
from painter.settings import load_settings, save_settings
from painter.sheet_parser import Sheet, SheetError, parse_sheet

# the rounded controls are customtkinter (the SAME mix RHMH runs:
# CTk widgets living inside a ttkbootstrap window); their colours are
# pulled from the live darkly palette so both families read as one.
# Appearance is pinned dark — never the OS light mode over darkly.
ctk.set_appearance_mode("dark")

# semantic STATUS colours only — the widget look itself comes from
# ttkbootstrap's darkly theme. These colour-code Selection-window
# rows and DocWindow tags, aligned to darkly's own accents
C_DONE = "#00bc8c"        # green — finished (darkly 'success')
C_DONE_SOFT = "#9ccc65"   # olive — done on one site only
C_ADVICE = "#f39c12"      # orange — sheet advice (darkly 'warning')
C_SUPERSEDED = "#e74c3c"  # red — superseded (darkly 'danger')

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

# the site-switch logos: SITES key -> icon file stem (the owner's
# capitalisation in assets/icons/)
_SITE_ICON = {"chatgpt": "chatGPT", "gemini": "gemini"}

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
SELECT_OPEN_H = 520         # open + minimum height
SELECT_SCREEN_FRAC = 0.9    # clamp the open width to this fraction of screen
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


def _darken(hex_color: str, factor: float = HOVER_DARKEN) -> str:
    """The hover shade RHMH uses: the same colour scaled toward black."""
    r = int(hex_color[1:3], 16)
    g = int(hex_color[3:5], 16)
    b = int(hex_color[5:7], 16)
    return (
        f"#{int(r * factor):02x}{int(g * factor):02x}{int(b * factor):02x}"
    )


def _button_colors(kind: str) -> dict:
    """CTkButton colour kwargs for one semantic kind, pulled from the
    LIVE darkly palette so the CTk/ttk mix stays one colour family."""
    c = tb.Style().colors
    solid = {
        "secondary": c.secondary,
        "success": c.success,
        "danger": c.danger,
        "info": c.info,
    }
    if kind in solid:
        color = solid[kind]
        return dict(
            fg_color=color, hover_color=_darken(color),
            text_color=c.fg, text_color_disabled=c.light,
        )
    outline = {
        "secondary-outline": c.light,
        "danger-outline": c.danger,
        "success-outline": c.success,
    }
    if kind in outline:
        color = outline[kind]
        return dict(
            fg_color="transparent", border_width=1, border_color=color,
            hover_color=_darken(color, 0.35),
            text_color=color, text_color_disabled=c.secondary,
        )
    if kind == "link":  # borderless accent button (dashboard 'Show')
        return dict(
            fg_color="transparent", hover_color=c.dark,
            text_color=c.info, text_color_disabled=c.secondary,
        )
    if kind == "expander":  # flat left-aligned ▶/▼ section header
        return dict(
            fg_color="transparent", hover_color=c.dark,
            text_color=c.fg, text_color_disabled=c.secondary,
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
    opts.setdefault("bg_color", tb.Style().colors.bg)
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
    """Shared colour kwargs for rounded CTk entry/combobox fields.

    ``bg_color`` is pinned to the darkly window background so the
    canvas corners around the rounded field never show the CTk theme's
    own gray on a ttk parent."""
    c = tb.Style().colors
    return dict(
        fg_color=c.inputbg, border_color=c.secondary,
        text_color=c.inputfg, bg_color=c.bg,
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
    c = tb.Style().colors
    opts = _input_colors()
    opts.update(
        button_color=c.secondary,
        button_hover_color=_darken(c.secondary),
        dropdown_fg_color=c.dark,
        dropdown_hover_color=c.selectbg,
        dropdown_text_color=c.fg,
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

    def __init__(self, parent, variable, step: float, entry_width: int = 40):
        c = tb.Style().colors
        super().__init__(
            parent, corner_radius=INPUT_RADIUS, border_width=1,
            fg_color=c.inputbg, border_color=c.secondary, bg_color=c.bg,
        )
        self._var = variable
        self._step = step
        # 1.0 steps show "8", 0.1 steps show "0.6"
        self._decimals = 0 if float(step).is_integer() else 1
        # the +/- pads: ~24 px wide (clickable), slightly lower than the
        # frame so their canvases never overpaint the frame's own 1 px
        # border (CTk scales canvases; a 24 px child + 2 px pady used to
        # cover the bottom border row under the buttons)
        btn = dict(
            width=24, height=20, corner_radius=INPUT_RADIUS - 2,
            fg_color="transparent", hover_color=c.selectbg,
            text_color=c.fg, font=ctk_font("spin"),
        )
        ctk.CTkButton(
            self, text="−", command=partial(self._bump, -1.0), **btn
        ).pack(side="left", padx=(3, 0), pady=4)
        entry = ctk.CTkEntry(
            self, width=entry_width, height=INPUT_HEIGHT - 10,
            corner_radius=0, border_width=0, fg_color="transparent",
            text_color=c.inputfg, justify="center",
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
    c = tb.Style().colors
    return ctk.CTkSwitch(
        parent, text=text, variable=variable,
        onvalue=True, offvalue=False,
        font=ctk_font("root"),
        fg_color=c.secondary, progress_color=c.success,
        text_color=c.fg, bg_color=c.bg,
    )


def setup_style(root: tk.Tk) -> None:
    """The few named styles the darkly theme does not ship.

    Every font comes from the registry's shared named fonts, so a
    zoom (set_font_base) re-renders all of them without touching the
    styles again."""
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


def dark_text(widget: tk.Text) -> None:
    """The theme skin for plain tk Text/ScrolledText widgets."""
    colors = tb.Style().colors
    widget.configure(
        background=colors.inputbg, foreground=colors.inputfg,
        insertbackground=colors.inputfg,
        selectbackground=colors.selectbg,
        selectforeground=colors.selectfg,
        relief="flat", highlightthickness=0,
    )


def dark_listbox(widget: tk.Listbox) -> None:
    colors = tb.Style().colors
    widget.configure(
        background=colors.inputbg, foreground=colors.inputfg,
        selectbackground=colors.selectbg,
        selectforeground=colors.selectfg,
        relief="flat", highlightthickness=1,
        highlightbackground=colors.border,
        highlightcolor=colors.primary,
    )


def folder_of(drop_path: str) -> str:
    """The POSIX parent directory of a drop path — the L2 folder
    identity shared by the dashboard tree and the Select window
    (e.g. 'assets/archetype/trinity/Jesus.png' -> 'assets/archetype/
    trinity'). A path with no directory collapses to '(root)'."""
    folder = PurePosixPath(drop_path).parent.as_posix()
    return "(root)" if folder in (".", "") else folder


class ScrollFrame(ttk.Frame):
    """A vertically (optionally also horizontally) scrollable frame.

    Add children to ``self.body``. Without horizontal scroll the body
    is stretched to the canvas width (content wraps, no x scrollbar);
    with it the body keeps its natural width and a horizontal bar
    appears.
    """

    def __init__(self, master, horizontal: bool = False):
        super().__init__(master)
        self._stretch = not horizontal
        self._sr_job = None  # coalesced scrollregion pass (see _on_body)
        self._sr_suspended = False  # bulk-build pause (see suspend_...)
        self.canvas = tk.Canvas(
            self, highlightthickness=0, background=tb.Style().colors.bg
        )
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
        if self._sr_suspended or self._sr_job is not None:
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
        try:
            self.canvas.configure(scrollregion=self.canvas.bbox("all"))
        except tk.TclError:
            pass  # canvas destroyed between the schedule and the pass

    def _on_destroy(self, event) -> None:
        if self._sr_job is not None:
            self.after_cancel(self._sr_job)
            self._sr_job = None
        self._unbind_wheel(event)

    def _on_canvas(self, event) -> None:
        if self._stretch:
            self.canvas.itemconfigure(self._win, width=event.width)

    def _bind_wheel(self, _event) -> None:
        self.canvas.bind_all("<MouseWheel>", self._on_wheel)

    def _unbind_wheel(self, _event) -> None:
        try:
            self.canvas.unbind_all("<MouseWheel>")
        except tk.TclError:
            pass

    def _on_wheel(self, event) -> None:
        try:
            self.canvas.yview_scroll(int(-event.delta / 120), "units")
        except tk.TclError:
            # the canvas was destroyed but the global binding lingered
            self.canvas.unbind_all("<MouseWheel>")


def style_action_button(btn: ctk.CTkButton, color: str, available: bool) -> None:
    """Start/Stop availability styling: AVAILABLE = FILLED with its
    colour, UNAVAILABLE = disabled OUTLINE (coloured border, dark
    inside). Re-applied on every run-state change."""
    c = tb.Style().colors
    if available:
        btn.configure(
            state="normal", fg_color=color, border_width=0,
            hover_color=_darken(color), text_color=c.fg,
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
        "background", "bg_removal", "crop", "upscale", "report",
        "safer_retry", "new_chat", "pause_min", "pause_max",
        "act_min", "act_max",
    )

    def __init__(self, master, site_key: str, on_start, on_stop):
        super().__init__(master)
        self.site_key = site_key
        site = SITES[site_key]

        # the labelframe title: the site's logo + name
        head = ttk.Frame(self)
        ctk.CTkLabel(
            head, text="", image=icon(_SITE_ICON[site_key]), width=22,
            fg_color="transparent", bg_color=tb.Style().colors.bg,
        ).pack(side="left", padx=(0, 4))
        ttk.Label(head, text=site.name, style="Head.TLabel").pack(side="left")
        self.configure(labelwidget=head, padding=6)

        self.background_var = tk.StringVar(value=site.default_background)
        self.bg_removal_var = tk.BooleanVar(value=True)
        self.crop_var = tk.BooleanVar(value=True)
        self.upscale_var = tk.BooleanVar(value=True)
        self.report_var = tk.BooleanVar(value=True)
        self.safer_var = tk.BooleanVar(value=True)
        self.new_chat_var = tk.StringVar(value="collection")
        self.pause_min_var = tk.StringVar(value=f"{TIMING.pause_min_s:.0f}")
        self.pause_max_var = tk.StringVar(value=f"{TIMING.pause_max_s:.0f}")
        self.act_min_var = tk.StringVar(
            value=f"{TIMING.action_delay_min_s:.1f}"
        )
        self.act_max_var = tk.StringVar(
            value=f"{TIMING.action_delay_max_s:.1f}"
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

        row = ttk.Frame(self)
        row.pack(fill="x", pady=2)
        ttk.Label(row, text="pause", width=12).pack(side="left")
        Spinner(row, self.pause_min_var, step=1.0).pack(side="left")
        ttk.Label(row, text="–").pack(side="left", padx=2)
        Spinner(row, self.pause_max_var, step=1.0).pack(side="left")
        ttk.Label(row, text="s").pack(side="left", padx=(2, 0))

        row = ttk.Frame(self)
        row.pack(fill="x", pady=2)
        ttk.Label(row, text="action delay", width=12).pack(side="left")
        Spinner(row, self.act_min_var, step=0.1).pack(side="left")
        ttk.Label(row, text="–").pack(side="left", padx=2)
        Spinner(row, self.act_max_var, step=0.1).pack(side="left")
        ttk.Label(row, text="s").pack(side="left", padx=(2, 0))

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
        self.set_run_state(running=False)

    def set_run_state(
        self, running: bool, pending_restart: bool = False
    ) -> None:
        """Start is available unless the site runs; Stop is available
        while it runs OR while a quota auto-restart is pending (Stop
        then cancels the pending restart)."""
        c = tb.Style().colors
        style_action_button(self.btn_start, c.success, not running)
        style_action_button(
            self.btn_stop, c.danger, running or pending_restart
        )

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
            "bg_removal": self.bg_removal_var,
            "crop": self.crop_var,
            "upscale": self.upscale_var,
            "report": self.report_var,
            "safer_retry": self.safer_var,
            "new_chat": self.new_chat_var,
            "pause_min": self.pause_min_var,
            "pause_max": self.pause_max_var,
            "act_min": self.act_min_var,
            "act_max": self.act_max_var,
        }

    def persist_vars(self) -> list[tk.Variable]:
        return list(self._vars().values())

    def get_settings(self) -> dict:
        return {key: var.get() for key, var in self._vars().items()}

    def apply_settings(self, stored: dict) -> None:
        """Missing keys keep the current defaults."""
        variables = self._vars()
        for key in self._PERSIST:
            if key in stored:
                variables[key].set(stored[key])


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


class DashPanel(ttk.Frame):
    """One site's live view: current theme, whole-task totals, history.

    Driven only by the runner's structured events (main thread).
    """

    def __init__(self, master, site_name: str, on_show=None):
        super().__init__(master, padding=6)
        self._name = site_name
        self._on_show = on_show  # called with a node-info dict on 'Show'
        self._node_info: dict[str, dict] = {}  # tree item id -> info

        ttk.Label(self, text=site_name, style="Big.TLabel").pack(anchor="w")

        # the site's state line — quota auto-restart countdown etc.
        self.state_var = tk.StringVar(value="")
        ttk.Label(
            self, textvariable=self.state_var, style="Muted.TLabel"
        ).pack(anchor="w")

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

    @property
    def has_data(self) -> bool:
        """True once the panel shows anything worth screen space —
        the adaptive dashboard hides data-less panels of idle sites."""
        return self._task_total > 0 or bool(self.tree.get_children())

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


# ---------------------------------------------------------------------
# Main window
# ---------------------------------------------------------------------

class PainterGui:
    def __init__(self, root: tk.Tk):
        self.root = root
        root.title("PromptPainter")
        root.minsize(900, 640)
        setup_style(root)

        # persisted state first — the saved font zoom must apply
        # BEFORE any widget is built (fonts are created lazily)
        self._settings = load_settings()
        if "font_base" in self._settings:
            set_font_base(int(self._settings["font_base"]))

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
        self._standalone_busy = False  # one standalone tool at a time
        # (site, source-path, drop-path) -> BooleanVar; missing = ticked
        self._select_vars: dict[tuple[str, str, str], tk.BooleanVar] = {}
        self._save_job: str | None = None  # debounced settings save

        outer = ttk.Frame(root, padding=8)
        outer.pack(fill="both", expand=True)

        self._build_queue(outer)
        self._build_options(outer)
        self._build_toolbar(outer)
        self._build_views(outer)

        self.status_var = tk.StringVar(value="idle")
        ttk.Label(
            outer, textvariable=self.status_var, style="Muted.TLabel"
        ).pack(fill="x", pady=(4, 0))

        self._bind_zoom()
        self._apply_settings(self._settings)
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

    # --- construction --------------------------------------------------

    def _build_queue(self, parent) -> None:
        lf = ttk.Labelframe(
            parent, text="Collections (prompt .md files, one image set each)"
        )
        lf.pack(fill="x", pady=(0, 6))
        self.sheet_list = tk.Listbox(
            lf, height=5, activestyle="none", font=tk_font("mono")
        )
        dark_listbox(self.sheet_list)
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
        # the three standalone in-place tools (site-less; run one at a
        # time, reported on the first visible dashboard panel)
        rounded_button(
            row, "UPSCALE only…", command=partial(
                self._standalone_tool, "Upscale", "upscale"
            ),
        ).pack(side="right", padx=4)
        rounded_button(
            row, "CROP only…", command=partial(
                self._standalone_tool, "Crop", "crop"
            ),
        ).pack(side="right")
        rounded_button(
            row, "BG removal only…", command=partial(
                self._standalone_tool, "BG removal", "bg_removal"
            ),
        ).pack(side="right", padx=4)

    def _build_views(self, parent) -> None:
        self.notebook = ttk.Notebook(parent)
        self.notebook.pack(fill="both", expand=True)

        dash_tab = ttk.Frame(self.notebook)
        self.notebook.add(dash_tab, text="Dashboard")
        # the two site panels live in a horizontal PanedWindow so the
        # owner can DRAG the divider to give one panel more width; the
        # sash position persists in the settings
        self.dash_pane = ttk.PanedWindow(dash_tab, orient="horizontal")
        self.dash_pane.pack(fill="both", expand=True, padx=4, pady=4)
        self.dash_pane.bind(
            "<ButtonRelease-1>", lambda _e: self._schedule_save()
        )
        self.dash: dict[str, DashPanel] = {}
        for key in sorted(SITES):
            self.dash[key] = DashPanel(
                self.dash_pane, SITES[key].name,
                on_show=partial(self._show_node, key),
            )
        self._update_dash_layout()

        log_tab = ttk.Frame(self.notebook)
        self.notebook.add(log_tab, text="Log (detailed)")
        self._log_tab = log_tab
        self.log_box = tk.Text(
            log_tab, height=16, state="disabled", font=tk_font("mono")
        )
        dark_text(self.log_box)
        log_vsb = ttk.Scrollbar(
            log_tab, orient="vertical", command=self.log_box.yview,
            bootstyle="round",
        )
        self.log_box.configure(yscrollcommand=log_vsb.set)
        log_vsb.pack(side="right", fill="y")
        self.log_box.pack(side="left", fill="both", expand=True)

    def _update_dash_layout(self) -> None:
        """Adaptive dashboard: a site's panel shows only while the
        site is RUNNING (or waiting on a quota restart) or once it HAS
        DATA; a single visible panel takes the full width (no sash).
        When nothing runs and nothing has data yet, both show."""
        shown = [
            k for k in sorted(SITES)
            if k in self._running or k in self._restart_jobs
            or self.dash[k].has_data
        ]
        if not shown:
            shown = sorted(SITES)
        current = list(self.dash_pane.panes())
        wanted = [str(self.dash[k]) for k in shown]
        if current != wanted:
            for pane in current:
                self.dash_pane.forget(pane)
            for key in shown:
                self.dash_pane.add(self.dash[key], weight=1)

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

    def _progress_done(self, site: str, sheet: Sheet) -> set:
        """Drop paths already generated for one site+collection."""
        progress_file = (
            self._out_base() / STATE_DIRNAME / site
            / (sheet.source.stem + PROGRESS_SUFFIX)
        )
        if progress_file.exists():
            return set(
                json.loads(progress_file.read_text(encoding="utf-8"))["done"]
            )
        return set()

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
        (total images to generate, number of themes with work)."""
        total = 0
        themes = 0
        for sheet in sheets:
            done = self._progress_done(site, sheet)
            pending = [it for it in sheet.items if it.drop_path not in done]
            sel = selection.get(str(sheet.source))
            if sel is not None:
                pending = [it for it in pending if it.drop_path in sel]
            else:
                pending = [it for it in pending if not it.advice]
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

    # --- the standalone in-place tools ---------------------------------

    @staticmethod
    def _standalone_func(kind: str):
        """The engine function behind one standalone tool. Lazy import:
        the GUI opens even while the engine modules are being built."""
        if kind == "bg_removal":
            from painter.postprocess import remove_background
            return remove_background
        if kind == "crop":
            from painter.postprocess import crop_transparent
            return crop_transparent
        from painter.upscale import upscale_if_small
        return upscale_if_small

    @staticmethod
    def _iter_images(folder: Path) -> list[Path]:
        return sorted(
            p for p in folder.rglob("*")
            if p.suffix.lower() in (".png", ".jpg", ".jpeg", ".webp")
        )

    def _standalone_tool(self, label: str, kind: str) -> None:
        """One of the three standalone runs (BG removal / Crop /
        Upscale): pick a folder, confirm, process IN PLACE in order.
        Site-less — progress and the done/refused counts feed the
        FIRST VISIBLE dashboard panel ("refused" = the engine said
        "nothing"/"unclear": nothing to do for that file)."""
        if self._standalone_busy:
            messagebox.showerror(
                "PromptPainter", "A standalone tool is already running."
            )
            return
        folder = filedialog.askdirectory(
            title=f"Folder with images — {label} runs IN PLACE"
        )
        if not folder:
            return
        if not messagebox.askyesno(
            "PromptPainter",
            f"{label} IN PLACE for every image under:\n{folder}?\n\n"
            "(files with nothing to do are skipped untouched and"
            " counted as Refused)",
        ):
            return
        # the reporting panel: the first visible one (they're site-less)
        panes = self.dash_pane.panes()
        target = next(
            (k for k in sorted(SITES) if str(self.dash[k]) in panes),
            sorted(SITES)[0],
        )
        self._standalone_busy = True
        self.status_var.set(f"{label} running …")
        self.notebook.select(0)

        def work():
            emit = lambda ev: self._q.put(("__event__", target, ev))
            try:
                func = self._standalone_func(kind)
                files = self._iter_images(Path(folder))
                self._q.put(
                    f"{label}: {len(files)} image(s) under {folder}"
                )
                # the borrowed panel restarts its counters so the
                # done/refused totals read x / N for THIS run
                self._q.put(("__reset_panel__", target, len(files)))
                emit({
                    "type": "sheet_start",
                    "sheet": f"{label} (standalone)",
                    "pending": len(files),
                })
                log = lambda msg: self._q.put(f"  {msg}")
                counts: dict[str, int] = {}
                t0 = time.time()
                for i, src in enumerate(files, start=1):
                    drop = src.relative_to(folder).as_posix()
                    emit({
                        "type": "item_start", "idx": i, "of": len(files),
                        "title": src.name,
                    })
                    t_item = time.time()
                    try:
                        status = func(src, log)
                    except Exception as exc:
                        status = "FAILED"
                        self._q.put(f"  {label} FAIL {src.name}: {exc}")
                    counts[status] = counts.get(status, 0) + 1
                    if status == "done":
                        emit({
                            "type": "item_progress",
                            "drop_path": drop,
                            "gen_s": time.time() - t_item,
                            "size": src.stat().st_size,
                            "orig_res": "", "final_res": "",
                        })
                        emit({
                            "type": "item_done", "drop_path": drop,
                            "gen_s": time.time() - t_item, "over_s": 0.0,
                        })
                    else:  # nothing / unclear / FAILED -> the
                        emit({  # refused (nothing-to-do) bucket
                            "type": "item_refused", "drop_path": drop,
                        })
                    if i % 25 == 0:
                        self._q.put(
                            f"{label}: [{time.time() - t0:.0f}s]"
                            f" {i}/{len(files)}"
                        )
                emit({"type": "sheet_done"})
                summary = ", ".join(
                    f"{k}={v}" for k, v in sorted(counts.items())
                )
                self._q.put(f"{label} done: {summary or 'no images'}")
            finally:
                self._q.put(("__standalone_done__",))
                self._q.put(("__status__", "idle"))

        threading.Thread(target=work, daemon=True).start()

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

                parts.append(f"UPSCALE: {upscale_if_small(path, log)}")
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
        self.dash[key].reset(
            active=True, task_total=total, task_themes=themes
        )
        self._update_dash_layout()
        self._update_status()
        background = panel.background_var.get()
        self._log(
            f"=== START {key} | {len(sheets)} sheet(s) -> {out_base}"
            f" | background: {background}"
            f" | bg_removal={panel.bg_removal_var.get()}"
            f" crop={panel.crop_var.get()}"
            f" upscale={panel.upscale_var.get()}"
            f" | safer_retry={panel.safer_var.get()} ==="
        )
        worker = threading.Thread(
            target=self._drive_site,
            args=(
                key,
                list(sheets),
                out_base,
                timing,
                post_save,
                partial(prompt_suffix, key, background),
                panel.report_var.get(),
                selection,
                panel.safer_var.get(),
                panel.new_chat_var.get(),
                self._stop_events[key],
            ),
            daemon=True,
        )
        self._workers[key] = worker
        worker.start()

    def _drive_site(
        self, key, sheets, out_base, timing, post_save, suffix, report,
        selection, safer, new_chat, stop_event,
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
            self._update_dash_layout()
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
        self.dash[key].state_var.set(
            f"quota — auto-restart in {int(left // 60):02d}:"
            f"{int(left % 60):02d}"
        )
        self.root.after(1000, partial(self._tick_restart, key))

    def _cancel_restart(self, key: str) -> None:
        job = self._restart_jobs.pop(key, None)
        if job is not None:
            self.root.after_cancel(job)
        self._restart_deadline.pop(key, None)
        self.dash[key].state_var.set("")

    def _auto_restart(self, key: str) -> None:
        self._restart_jobs.pop(key, None)
        self.dash[key].state_var.set("")
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
                        self.dash[msg[1]].handle(msg[2])
                    elif msg[0] == "__terminal__":
                        self._handle_terminal(msg[1], msg[2])
                    elif msg[0] == "__reset_panel__":
                        self.dash[msg[1]].reset(
                            active=True, task_total=msg[2], task_themes=1
                        )
                    elif msg[0] == "__standalone_done__":
                        self._standalone_busy = False
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
                        self._update_dash_layout()
                        self._update_status()
                else:
                    self._log(str(msg))
        except queue.Empty:
            pass
        self.root.after(120, self._drain_queue)

    # --- settings persistence ------------------------------------------

    def _collect_settings(self) -> dict:
        sash = self._settings.get("sash")
        if len(self.dash_pane.panes()) > 1:
            try:
                sash = self.dash_pane.sashpos(0)
            except tk.TclError:
                pass
        return {
            "queue": [str(p) for p in self._sheets],
            "output": self.out_var.get(),
            "font_base": FONT_BASE,
            "sash": sash,
            "geometry": self.root.geometry(),
            "agents": {
                key: panel.get_settings()
                for key, panel in self.agents.items()
            },
        }

    def _apply_settings(self, stored: dict) -> None:
        """Missing keys keep the current defaults; queued files that
        no longer exist are reported and dropped."""
        for raw in stored.get("queue", ()):
            path = Path(raw)
            if not path.is_file():
                self._log(f"saved queue entry gone, dropped: {raw}")
                continue
            if path not in self._sheets:
                self._sheets.append(path)
                self.sheet_list.insert("end", path.name)
        if stored.get("output"):
            self.out_var.set(stored["output"])
        for key, panel in self.agents.items():
            panel.apply_settings(stored.get("agents", {}).get(key, {}))
        if stored.get("geometry"):
            self.root.geometry(stored["geometry"])
        if stored.get("sash") is not None:
            # the sash needs realised pane widths — apply once mapped
            def place_sash(pos=int(stored["sash"])):
                try:
                    if len(self.dash_pane.panes()) > 1:
                        self.dash_pane.sashpos(0, pos)
                except tk.TclError:
                    pass  # single pane right now — position kept stored

            self.root.after(300, place_sash)

    def _wire_persistence(self) -> None:
        """Meaningful changes debounce into a save; the queue buttons,
        zoom and the sash release hook in at their own sites."""
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
        self.configure(background=tb.Style().colors.bg)
        self._gui = gui
        self._site_keys = sorted(SITES)

        done = {
            key: {
                str(sheet.source): gui._progress_done(key, sheet)
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
            text="Tick = generate.  Done = disabled.  ⚠ advice off."
            "  Click a count = all/none.",
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
        self._canvas_width = SELECT_MIN_W - SELECT_SCROLLBAR_PX
        self._wrap = self._wraplength_for(self._canvas_width)
        self._canvas.bind("<Configure>", self._on_canvas_configure, add="+")

        # --- the tree: L1 + L2 always materialised, L3 lazy
        self._static_labels: list[ttk.Label] = []  # L1/L2 names (wrap)
        self._count_nodes: list[dict] = []  # L1 + L2 nodes for _recount
        self._collection_nodes: list[dict] = []
        for coll in self._collections:
            self._build_collection_widgets(self._scroll.body, coll)

        # first paint of the counts + the open geometry
        self._dirty = True
        self._recount()
        self.bind("<Destroy>", self._on_destroy)
        width = min(
            SELECT_MIN_W, int(self.winfo_screenwidth() * SELECT_SCREEN_FRAC)
        )
        self.geometry(f"{width}x{SELECT_OPEN_H}")

    # --- data model (no widgets) --------------------------------------

    def _build_collection_data(self, sheet: Sheet, done: dict) -> dict:
        """One collection's leaf records + its folders (first-seen
        order). Materialises the shared BooleanVars — run-safe: the
        default (advice-free, not-done) set equals the runner's own
        'never opened Select' rule."""
        src = str(sheet.source)
        folders: dict[str, dict] = {}
        leaves: list[dict] = []
        for item in sheet.items:
            drop = item.drop_path
            done_sites = [k for k in self._site_keys if drop in done[k][src]]
            leaf = {
                "name": PurePosixPath(drop).name,
                "advice": item.advice,
                "color": self._leaf_color(item.advice, len(done_sites)),
                "sites": {},
            }
            for key in self._site_keys:
                var = self._gui._select_var(
                    key, src, drop, default=item.advice is None
                )
                is_done = drop in done[key][src]
                if is_done:
                    var.set(False)  # done -> never ticked, always disabled
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
        if n_done == len(self._site_keys):
            return C_DONE
        if advice and "supersed" in advice.lower():
            return C_SUPERSEDED
        if advice:
            return C_ADVICE
        if n_done:
            return C_DONE_SOFT
        return ""

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
                cb = ttk.Checkbutton(row, variable=info["var"])
                if info["done"]:
                    cb.state(["disabled"])
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

    # --- wrapping + teardown ------------------------------------------

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
        for var, token in self._traces:
            var.trace_remove("write", token)
        self._traces.clear()
        for job in (self._recount_job, self._wrap_job, self._expand_job):
            if job is not None:
                self.after_cancel(job)
        self._recount_job = self._wrap_job = self._expand_job = None


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
        self.minsize(600, 560)
        self.configure(background=tb.Style().colors.bg)
        self._raw = raw_markdown
        self._copy_text = copy_text if copy_text is not None else raw_markdown
        self._image_path = image_path
        self._img_ref = None  # keeps the PhotoImage alive

        bar = ttk.Frame(self, padding=6)
        bar.pack(fill="x")
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
        dark_text(self.txt)
        vsb = ttk.Scrollbar(
            wrap, orient="vertical", command=self.txt.yview,
            bootstyle="round",
        )
        self.txt.configure(yscrollcommand=vsb.set)
        vsb.pack(side="right", fill="y")
        self.txt.pack(side="left", fill="both", expand=True)

        self._configure_tags()
        self._size_to_content(raw_markdown)
        self._render(raw_markdown)
        self._append_image()
        # read-only, but fully selectable and Ctrl+C / Ctrl+A copyable
        self.txt.bind("<Key>", self._readonly_keys)

    def _size_to_content(self, md: str) -> None:
        """Width follows the text (longest line, roughly per-role
        fonts), clamped to 90 % of the screen — one rule for every
        opening (instructions, collection, folder excerpt, prompt)."""
        widest = 0
        in_code = False
        for line in md.split("\n"):
            if line.startswith("```"):
                in_code = not in_code
                continue
            if in_code:
                role = "mono"
            elif line.startswith("# "):
                role = "doc_h1"
            elif line.startswith("## "):
                role = "doc_h2"
            elif line.startswith("### "):
                role = "head"
            else:
                role = "root"
            widest = max(
                widest, tk_font(role).measure(line.lstrip("# ")),
            )
        width = widest + 2 * 14 + 40  # text padx + scrollbar/margins
        if self._image_path is not None:
            try:
                with Image.open(self._image_path) as img:
                    width = max(width, min(img.width + 60, 1400))
            except OSError:
                pass
        width = min(max(width, 600), int(self.winfo_screenwidth() * 0.9))
        self.geometry(f"{width}x{max(560, self.winfo_height())}")

    def _append_image(self) -> None:
        """The saved image, below the prompt, scaled to fit the window
        width (the viewer keeps the PhotoImage reference alive). No
        file — no section, the prompt stands alone as before."""
        if self._image_path is None:
            return
        try:
            img = Image.open(self._image_path)
            img.load()
        except OSError as exc:
            self._log_line(f"(image unreadable: {exc})")
            return
        self.update_idletasks()
        avail = max(self.winfo_width() - 80, 320)
        if img.width > avail:
            scale = avail / img.width
            img = img.resize(
                (avail, max(round(img.height * scale), 1)), Image.LANCZOS
            )
        self._img_ref = ImageTk.PhotoImage(img)
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
                               foreground=C_DONE,
                               spacing1=6, spacing3=3)
        self.txt.tag_configure(
            "code", font=tk_font("mono"), background=colors.dark,
            foreground="#a5d6ff", lmargin1=16, lmargin2=16,
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


def main() -> None:
    root = tb.Window(themename="darkly")
    PainterGui(root)
    root.mainloop()


if __name__ == "__main__":
    main()
