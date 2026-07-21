"""Themed widget toolkit — status/job-colour lookups, the font-zoom
registry, dark-palette rounded CTk controls (buttons/entries/combos/
Spinner/switch), Start/Stop button styling, the folder-grouping
helpers used by the tool panels, and the Advanced-override numeric
field parsers.

Split out of gui/__init__.py (Rule #3, god-file refactor step 2/8) —
a leaf module: no dependency on any other ``gui`` submodule except
``gui.icons`` (``rounded_button`` draws its optional icon via
``icon()``). ``ACTIVE_THEME`` and ``FONT_BASE`` are the two LIVE
mutable globals every theme flip / zoom rewrites — every OTHER module
that needs their current value reads ``widgets.ACTIVE_THEME`` /
``widgets.FONT_BASE`` (a module-attribute access) rather than
importing the bare name, which would freeze a stale copy at import
time."""

from __future__ import annotations

from functools import partial
from pathlib import PurePosixPath
from tkinter import font as tkfont

import customtkinter as ctk
import ttkbootstrap as tb

from painter.config import (
    THEMES,
    button_fill_pair,
    button_text_pair,
    job_color_pair,
    status_pair,
    theme_pair,
)

from .icons import icon


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

