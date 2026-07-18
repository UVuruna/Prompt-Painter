"""PromptPainter GUI — the owner's front door.

A tkinter window over the same engine the CLI uses: queue one or MORE
prompt-sheet `.md` files (each file is a THEME), pick the output
folder, tick Gemini / ChatGPT / both, choose each site's background,
open the automation Chrome (log in once — the profile persists),
check, start. Both sites run in PARALLEL, one thread and one tab
each; each works through the theme queue IN ORDER, so a quota stop on
one site never costs finished work — progress and the report live
beside the images and every run resumes.

Two views (tabs): a **Dashboard** (per-site progress for the current
theme AND the whole task, two average timings, and a collapsible list
of finished themes) and the detailed **Log**.
"""

from __future__ import annotations

import io
import json
import queue
import threading
import time
import tkinter as tk
from dataclasses import replace
from datetime import datetime
from functools import partial
from pathlib import Path, PurePosixPath
from tkinter import filedialog, messagebox, ttk

import customtkinter as ctk
import ttkbootstrap as tb
from PIL import Image

from painter.config import (
    BACKGROUND_CHOICES,
    CDP_URL,
    DEFAULT_OUT_DIR,
    NEW_CHAT_CHOICES,
    PROGRESS_SUFFIX,
    SITES,
    STATE_DIRNAME,
    TIMING,
    fmt_duration,
    fmt_size,
    prompt_suffix,
)
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

# the rounded-control geometry — one place so every control matches
# (RHMH runs CTkButton corner_radius 10–12; hover = colour * 0.75)
BTN_RADIUS = 12
BTN_HEIGHT = 30
INPUT_RADIUS = 8
INPUT_HEIGHT = 28
HOVER_DARKEN = 0.75


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
    if kind in ("secondary-outline", "danger-outline"):
        color = c.danger if kind == "danger-outline" else c.light
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
        font=("Segoe UI", 10, "bold"),
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
        font=("Segoe UI", 10), **opts,
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
        state="readonly", font=("Segoe UI", 10),
        dropdown_font=("Segoe UI", 10), **opts,
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
            text_color=c.fg, font=("Segoe UI", 12, "bold"),
        )
        ctk.CTkButton(
            self, text="−", command=partial(self._bump, -1.0), **btn
        ).pack(side="left", padx=(3, 0), pady=4)
        entry = ctk.CTkEntry(
            self, width=entry_width, height=INPUT_HEIGHT - 10,
            corner_radius=0, border_width=0, fg_color="transparent",
            text_color=c.inputfg, justify="center",
            font=("Segoe UI", 10), textvariable=variable,
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
        font=("Segoe UI", 10),
        fg_color=c.secondary, progress_color=c.success,
        text_color=c.fg, bg_color=c.bg,
    )


def setup_style(root: tk.Tk) -> None:
    """The few named styles the darkly theme does not ship."""
    style = tb.Style()
    colors = style.colors
    style.configure(".", font=("Segoe UI", 10))
    style.configure("Head.TLabel", font=("Segoe UI", 11, "bold"),
                    foreground=colors.info)
    style.configure("Big.TLabel", font=("Segoe UI", 16, "bold"))
    style.configure("Value.TLabel", font=("Segoe UI", 10, "bold"))
    style.configure("Muted.TLabel", foreground=colors.light)
    style.configure("Mono.TLabel", font=("Consolas", 9),
                    foreground=colors.light)
    style.configure("Treeview", rowheight=24)


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
        # dead widget
        self.canvas.bind("<Destroy>", self._unbind_wheel)

    def _on_body(self, _event) -> None:
        self.canvas.configure(scrollregion=self.canvas.bbox("all"))

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
        self.tree.column("#0", width=230, minwidth=140, stretch=True)
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
            folder = self._folder_of(drop)
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
            folder = self._folder_of(drop)
            st = self._folder_stats.get(folder)
            if st is not None:
                st["time"] += event["gen_s"] + over
                self._update_folder(folder)
        elif kind == "item_refused":
            self._theme_refused += 1
            self._task_refused += 1
            drop = event.get("drop_path", "")
            fnode = self._ensure_folder(self._folder_of(drop))
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

    @staticmethod
    def _folder_of(drop_path: str) -> str:
        folder = PurePosixPath(drop_path).parent.as_posix()
        return "(root)" if folder in (".", "") else folder

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

        self._q: queue.Queue = queue.Queue()
        self._stop = threading.Event()
        self._workers: list[threading.Thread] = []
        self._workers_left = 0  # counted down on each __worker_done__
        self._sheets: list[Path] = []
        # (site, source-path, drop-path) -> BooleanVar; missing = ticked
        self._select_vars: dict[tuple[str, str, str], tk.BooleanVar] = {}

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

        root.after(120, self._drain_queue)

    # --- construction --------------------------------------------------

    def _build_queue(self, parent) -> None:
        lf = ttk.Labelframe(
            parent, text="Collections (prompt .md files, one image set each)"
        )
        lf.pack(fill="x", pady=(0, 6))
        self.sheet_list = tk.Listbox(
            lf, height=5, activestyle="none", font=("Consolas", 9)
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

        row = ttk.Frame(lf)
        row.pack(fill="x", pady=2)
        ttk.Label(row, text="Sites:", width=8).pack(side="left")
        self.site_vars = {
            key: tk.BooleanVar(value=True) for key in sorted(SITES)
        }
        self.background_vars: dict[str, tk.StringVar] = {}
        for key in sorted(SITES):
            # the site's logo (owner's svg; gemini via its png sibling)
            # sits beside its switch; the switch keeps the name text
            ctk.CTkLabel(
                row, text="", image=icon(_SITE_ICON[key]), width=22,
                fg_color="transparent", bg_color=tb.Style().colors.bg,
            ).pack(side="left", padx=(6, 3))
            rounded_switch(
                row, SITES[key].name, self.site_vars[key]
            ).pack(side="left", padx=(0, 0))
            var = tk.StringVar(value=SITES[key].default_background)
            self.background_vars[key] = var
            rounded_combo(
                row, BACKGROUND_CHOICES, var, width=110,
            ).pack(side="left", padx=(2, 12))

        row = ttk.Frame(lf)
        row.pack(fill="x", pady=2)
        ttk.Label(row, text="", width=8).pack(side="left")
        self.bgfix_var = tk.BooleanVar(value=True)
        rounded_switch(
            row, "Background fix", self.bgfix_var
        ).pack(side="left")
        self.report_var = tk.BooleanVar(value=True)
        rounded_switch(
            row, "Report txt", self.report_var
        ).pack(side="left", padx=12)
        self.safer_var = tk.BooleanVar(value=True)
        rounded_switch(
            row, "Safer retry on refusal", self.safer_var
        ).pack(side="left", padx=12)
        ttk.Label(row, text="New chat:").pack(side="left", padx=(12, 2))
        self.new_chat_var = tk.StringVar(value="collection")
        rounded_combo(
            row, NEW_CHAT_CHOICES, self.new_chat_var, width=105,
        ).pack(side="left")

        row = ttk.Frame(lf)
        row.pack(fill="x", pady=2)
        ttk.Label(row, text="Pace:", width=8).pack(side="left")
        ttk.Label(row, text="pause").pack(side="left")
        # one Spinner class, four instances (Rule #5): step 1 s for the
        # pauses, 0.1 s for the action delays; typing stays allowed and
        # the ranges are validated on Start, same as before
        self.pause_min_var = tk.StringVar(value=f"{TIMING.pause_min_s:.0f}")
        self.pause_max_var = tk.StringVar(value=f"{TIMING.pause_max_s:.0f}")
        Spinner(row, self.pause_min_var, step=1.0).pack(
            side="left", padx=(4, 0)
        )
        ttk.Label(row, text="–").pack(side="left", padx=2)
        Spinner(row, self.pause_max_var, step=1.0).pack(side="left")
        ttk.Label(row, text="s   action delay").pack(side="left", padx=(2, 0))
        self.act_min_var = tk.StringVar(
            value=f"{TIMING.action_delay_min_s:.1f}"
        )
        self.act_max_var = tk.StringVar(
            value=f"{TIMING.action_delay_max_s:.1f}"
        )
        Spinner(row, self.act_min_var, step=0.1).pack(
            side="left", padx=(4, 0)
        )
        ttk.Label(row, text="–").pack(side="left", padx=2)
        Spinner(row, self.act_max_var, step=0.1).pack(side="left")
        ttk.Label(row, text="s").pack(side="left")

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
        self.btn_start = rounded_button(
            row, "Start", command=self._start, kind="success",
            icon_name="start", width=90,
        )
        self.btn_start.pack(side="left", padx=4)
        self.btn_stop = rounded_button(
            row, "Stop", command=self._request_stop,
            kind="danger-outline", width=70, state="disabled",
        )
        self.btn_stop.pack(side="left", padx=4)
        rounded_button(
            row, "Instructions", command=self._open_instructions,
        ).pack(side="right")
        rounded_button(
            row, "BG removal only…", command=self._bg_remove_only,
        ).pack(side="right", padx=4)

    def _build_views(self, parent) -> None:
        notebook = ttk.Notebook(parent)
        notebook.pack(fill="both", expand=True)

        dash_tab = ttk.Frame(notebook)
        notebook.add(dash_tab, text="Dashboard")
        self.dash: dict[str, DashPanel] = {}
        for i, key in enumerate(sorted(SITES)):
            panel = DashPanel(dash_tab, SITES[key].name, on_show=self._show_node)
            panel.grid(row=0, column=i, sticky="nsew", padx=4, pady=4)
            dash_tab.columnconfigure(i, weight=1)
            self.dash[key] = panel
        dash_tab.rowconfigure(0, weight=1)

        log_tab = ttk.Frame(notebook)
        notebook.add(log_tab, text="Log (detailed)")
        self.log_box = tk.Text(
            log_tab, height=16, state="disabled", font=("Consolas", 9)
        )
        dark_text(self.log_box)
        log_vsb = ttk.Scrollbar(
            log_tab, orient="vertical", command=self.log_box.yview,
            bootstyle="round",
        )
        self.log_box.configure(yscrollcommand=log_vsb.set)
        log_vsb.pack(side="right", fill="y")
        self.log_box.pack(side="left", fill="both", expand=True)

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

    def _show_node(self, info: dict) -> None:
        """A dashboard row's 'Show': a collection/folder opens its whole
        file, an image opens just its own prompt — both in the same
        formatted, selectable viewer."""
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
            DocWindow(
                self.root, item.drop_path, md, copy_text=item.prompt,
                hint="The prompt for this one image.",
            )
        else:
            try:
                text = source.read_text(encoding="utf-8")
            except OSError as exc:
                messagebox.showerror("PromptPainter", str(exc))
                return
            DocWindow(self.root, source.name, text)

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

    def _remove_sheet(self) -> None:
        for index in reversed(self.sheet_list.curselection()):
            self.sheet_list.delete(index)
            del self._sheets[index]

    def _clear_sheets(self) -> None:
        self.sheet_list.delete(0, "end")
        self._sheets.clear()

    def _pick_out(self) -> None:
        path = filedialog.askdirectory(title="Output folder")
        if path:
            self.out_var.set(path)

    def _selected_sites(self) -> list[str]:
        return [k for k, v in self.site_vars.items() if v.get()]

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
        sites = self._selected_sites()
        if not sites:
            messagebox.showerror("PromptPainter", "Tick at least one site.")
            return
        urls = tuple(SITES[k].url for k in sites)
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

    def _bg_remove_only(self) -> None:
        from painter.postprocess import deps_error

        problem = deps_error()
        if problem:
            messagebox.showerror("PromptPainter", problem)
            return
        folder = filedialog.askdirectory(
            title="Folder with images — backgrounds removed IN PLACE"
        )
        if not folder:
            return
        if not messagebox.askyesno(
            "PromptPainter",
            "Remove backgrounds IN PLACE for every image under:\n"
            f"{folder}?\n\n(already-transparent and unclear images are"
            " skipped untouched)",
        ):
            return
        self.status_var.set("BG removal running …")

        def work():
            from painter.bg_remove import iter_images, process_file
            from painter.config import BG_FIX_CROP

            files = list(iter_images(Path(folder)))
            self._q.put(f"BG removal: {len(files)} image(s) under {folder}")
            counts: dict[str, int] = {}
            for i, src in enumerate(files, start=1):
                try:
                    action = process_file(
                        src, src, "auto", BG_FIX_CROP, None, None
                    )
                except Exception as exc:
                    action = "FAILED"
                    self._q.put(f"  BG FAIL {src.name}: {exc}")
                counts[action] = counts.get(action, 0) + 1
                self._q.put(f"  [{i}/{len(files)}] {action:16} {src.name}")
            summary = ", ".join(
                f"{k}={v}" for k, v in sorted(counts.items())
            )
            self._q.put(f"BG removal done: {summary or 'no images'}")
            self._q.put(("__status__", "idle"))

        threading.Thread(target=work, daemon=True).start()

    def _start(self) -> None:
        if not self._sheets:
            messagebox.showerror("PromptPainter", "Add sheet .md files first.")
            return
        sheets = self._parse_all()
        if not sheets:
            messagebox.showerror(
                "PromptPainter", "No usable sheets in the queue."
            )
            return
        sites = self._selected_sites()
        if not sites:
            messagebox.showerror("PromptPainter", "Tick at least one site.")
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

        post_save = None
        if self.bgfix_var.get():
            from painter.postprocess import deps_error, fix_background

            problem = deps_error()
            if problem:
                messagebox.showerror(
                    "PromptPainter",
                    f"{problem}\n\n(or untick 'Background fix')",
                )
                return
            post_save = fix_background

        try:
            pause_min = float(self.pause_min_var.get())
            pause_max = float(self.pause_max_var.get())
            act_min = float(self.act_min_var.get())
            act_max = float(self.act_max_var.get())
        except ValueError:
            messagebox.showerror(
                "PromptPainter", "Pause/delay must be numbers."
            )
            return
        if pause_min > pause_max or act_min > act_max:
            messagebox.showerror(
                "PromptPainter", "FROM must be <= TO (pause and delay)."
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

        # the ticked selection, read in the tk thread: per site, per
        # sheet -> the drop paths to run. None means "the owner never
        # opened Select for this theme+site" (so the runner applies the
        # default advice rule). Once Select has been opened, the ticks
        # are authoritative — including ticked advice items — so we pass
        # the explicit set, never collapsing "all ticked" back to None.
        selections: dict[str, dict[str, set[str] | None]] = {}
        for key in sites:
            per_sheet: dict[str, set[str] | None] = {}
            for sheet in sheets:
                src = str(sheet.source)
                touched = any(
                    site == key and source == src
                    for (site, source, _drop) in self._select_vars
                )
                if touched:
                    per_sheet[src] = {
                        drop
                        for (site, source, drop), var
                        in self._select_vars.items()
                        if site == key and source == src and var.get()
                    }
                else:
                    per_sheet[src] = None
            selections[key] = per_sheet

        self._stop.clear()
        self._workers = []
        self._workers_left = len(sites)
        self.btn_start.configure(state="disabled")
        self.btn_stop.configure(state="normal")
        self.status_var.set("running: " + ", ".join(sites))
        for key, panel in self.dash.items():
            if key in sites:
                total, themes = self._plan(key, sheets, selections[key])
                panel.reset(active=True, task_total=total, task_themes=themes)
            else:
                panel.reset(active=False)
        backgrounds = {key: self.background_vars[key].get() for key in sites}
        self._log(
            f"=== START {', '.join(sites)} | {len(sheets)} sheet(s)"
            f" -> {out_base} | backgrounds: {backgrounds}"
            f" | safer_retry={self.safer_var.get()} ==="
        )

        safer = self.safer_var.get()
        new_chat = self.new_chat_var.get()
        for key in sites:
            worker = threading.Thread(
                target=self._drive_site,
                args=(
                    key,
                    list(sheets),
                    out_base,
                    timing,
                    post_save,
                    partial(prompt_suffix, key, backgrounds[key]),
                    self.report_var.get(),
                    selections[key],
                    safer,
                    new_chat,
                ),
                daemon=True,
            )
            self._workers.append(worker)
            worker.start()

    def _drive_site(
        self, key, sheets, out_base, timing, post_save, suffix, report,
        selection, safer, new_chat,
    ) -> None:
        """One site's whole run — the theme queue in order, one thread."""
        log = lambda msg: self._q.put(f"[{key}] {msg}")
        events = lambda ev: self._q.put(("__event__", key, ev))
        driver = None
        done_sheets = 0
        # the WHOLE body is guarded so __worker_done__ is ALWAYS posted
        # (even if the imports or driver construction fail) — otherwise
        # the Start button would stay disabled forever
        try:
            from painter.driver import DriverError, SiteDriver, TerminalState
            from painter.runner import run_sheet

            driver = SiteDriver(SITES[key], timing, CDP_URL)
            t_site = time.monotonic()
            title = driver.attach()
            log(f"attached to {title!r} — SUPERVISED, watch the window")
            for n, sheet in enumerate(sheets, start=1):
                if self._stop.is_set():
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
                        should_stop=self._stop.is_set,
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
                    log(
                        "site stopped — finished work is saved; start"
                        " again later to resume the remaining collections"
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

    def _request_stop(self) -> None:
        self._stop.set()
        self.status_var.set("stopping after the current item …")

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
                    elif msg[0] == "__worker_done__":
                        self._log(f"[{msg[1]}] worker finished")
                        # count down rather than poll is_alive(): the
                        # worker posts this from its finally block while
                        # its thread is still technically alive
                        self._workers_left -= 1
                        if self._workers_left <= 0:
                            self.btn_start.configure(state="normal")
                            self.btn_stop.configure(state="disabled")
                            self.status_var.set("idle")
                else:
                    self._log(str(msg))
        except queue.Empty:
            pass
        self.root.after(120, self._drain_queue)


# ---------------------------------------------------------------------
# Select-images window
# ---------------------------------------------------------------------

class SelectWindow(tk.Toplevel):
    """Tick which images each site generates — a column per site.

    One collapsible section per theme. Already-done items (per the
    site's progress under the current output folder) show disabled;
    sheet-advised items show unticked with the reason.
    """

    def __init__(self, gui: PainterGui, sheets: list[Sheet]):
        super().__init__(gui.root)
        self.title("Select images per site")
        self.minsize(720, 520)
        self.configure(background=tb.Style().colors.bg)
        self._gui = gui
        site_keys = sorted(SITES)

        done = {
            key: {
                str(sheet.source): gui._progress_done(key, sheet)
                for sheet in sheets
            }
            for key in site_keys
        }

        bar = ttk.Frame(self, padding=6)
        bar.pack(fill="x")
        ttk.Label(
            bar,
            text="Tick = generate.  Already-done disabled;"
            " ⚠ advice unticked by default.",
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

        scroll = ScrollFrame(self, horizontal=True)
        scroll.pack(fill="both", expand=True)
        body = scroll.body

        header = ttk.Frame(body, padding=(2, 2))
        header.pack(fill="x")
        for c, key in enumerate(site_keys):
            ttk.Label(
                header, text=SITES[key].name, style="Head.TLabel", width=10,
                anchor="center",
            ).grid(row=0, column=c, padx=2)
        ttk.Label(header, text="Image", style="Head.TLabel").grid(
            row=0, column=len(site_keys), sticky="w", padx=8
        )

        # each entry: (state dict, toggle callable) for expand/collapse all
        self._sections: list[tuple[dict, object]] = []
        for sheet in sheets:
            self._add_theme(body, sheet, site_keys, done)

    def _add_theme(self, body, sheet: Sheet, site_keys, done) -> None:
        src = str(sheet.source)
        section = ttk.Frame(body)
        section.pack(fill="x", pady=(8, 0))

        head = ttk.Frame(section)
        head.pack(fill="x")
        detail = ttk.Frame(section)
        detail.pack(fill="x", padx=(14, 0))

        state = {"open": True}
        label = f"{sheet.source.name} — {sheet.theme}"
        btn = rounded_button(head, "", kind="expander")

        def render() -> None:
            btn.configure(text=("▼  " if state["open"] else "▶  ") + label)

        def toggle() -> None:
            state["open"] = not state["open"]
            if state["open"]:
                detail.pack(fill="x", padx=(14, 0))
            else:
                detail.forget()
            render()

        btn.configure(command=toggle)
        # all/none buttons first (right), then the toggle fills the rest
        for key in reversed(site_keys):
            rounded_button(
                head, f"{SITES[key].name}: all/none", width=130,
                command=partial(self._toggle_sheet, key, sheet),
                kind="secondary-outline",
            ).pack(side="right", padx=2)
        btn.pack(side="left", fill="x", expand=True)
        render()
        self._sections.append((state, toggle))

        for r, item in enumerate(sheet.items):
            done_sites = [
                k for k in site_keys if item.drop_path in done[k][src]
            ]
            for c, key in enumerate(site_keys):
                var = self._gui._select_var(
                    key, src, item.drop_path, default=item.advice is None
                )
                is_done = item.drop_path in done[key][src]
                if is_done:
                    var.set(False)
                # deliberately plain ttk here: this grid holds hundreds
                # of rows and a CTkCheckBox per cell is too heavy
                cb = ttk.Checkbutton(detail, variable=var)
                if is_done:
                    cb.state(["disabled"])
                cb.grid(row=r, column=c, padx=(20 if c == 0 else 6, 6))
            text = item.drop_path
            if done_sites:
                text += "   ✔ done: " + ", ".join(
                    SITES[k].name for k in done_sites
                )
            if item.advice:
                text += f"   ⚠ {item.advice[:70]}"
            if len(done_sites) == len(site_keys):
                color = C_DONE
            elif item.advice and "supersed" in item.advice.lower():
                color = C_SUPERSEDED
            elif item.advice:
                color = C_ADVICE
            elif done_sites:
                color = C_DONE_SOFT
            else:
                color = ""
            opt = {"foreground": color} if color else {}
            ttk.Label(detail, text=text, **opt).grid(
                row=r, column=len(site_keys), sticky="w", padx=8
            )

    def _toggle_sheet(self, site: str, sheet: Sheet) -> None:
        src = str(sheet.source)
        variables = [
            self._gui._select_var(site, src, item.drop_path)
            for item in sheet.items
        ]
        target = not all(var.get() for var in variables)
        for var in variables:
            var.set(target)

    def _expand_all(self) -> None:
        for state, toggle in self._sections:
            if not state["open"]:
                toggle()

    def _collapse_all(self) -> None:
        for state, toggle in self._sections:
            if state["open"]:
                toggle()


class DocWindow(tk.Toplevel):
    """A readable, selectable in-app viewer for Markdown — for people
    who do not want a code editor. Light formatting (headings, code,
    bullets, bold) plus a one-click 'Copy for AI'. Used for the
    authoring instructions, a whole collection file, and a single
    image's prompt."""

    def __init__(
        self, master, title: str, raw_markdown: str,
        copy_text: str | None = None, hint: str | None = None,
    ):
        super().__init__(master)
        self.title(title)
        self.minsize(720, 560)
        self.configure(background=tb.Style().colors.bg)
        self._raw = raw_markdown
        self._copy_text = copy_text if copy_text is not None else raw_markdown

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
            wrap, wrap="word", font=("Segoe UI", 10), padx=14, pady=12,
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
        self._render(raw_markdown)
        # read-only, but fully selectable and Ctrl+C / Ctrl+A copyable
        self.txt.bind("<Key>", self._readonly_keys)

    def _configure_tags(self) -> None:
        colors = tb.Style().colors
        self.txt.tag_configure("h1", font=("Segoe UI", 15, "bold"),
                               foreground=colors.info,
                               spacing1=10, spacing3=6)
        self.txt.tag_configure("h2", font=("Segoe UI", 12, "bold"),
                               foreground=colors.info,
                               spacing1=8, spacing3=4)
        self.txt.tag_configure("h3", font=("Segoe UI", 11, "bold"),
                               foreground=C_DONE,
                               spacing1=6, spacing3=3)
        self.txt.tag_configure(
            "code", font=("Consolas", 9), background=colors.dark,
            foreground="#a5d6ff", lmargin1=16, lmargin2=16,
        )
        self.txt.tag_configure("bold", font=("Segoe UI", 10, "bold"))
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
