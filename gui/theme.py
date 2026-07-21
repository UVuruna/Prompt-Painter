"""The theme engine — the coordinated ttk/CTk/plain-tk Day/Night flip,
the plain-tk skin registry (Text/Listbox/Canvas/Toplevel colours CTk's
automatic tuple resolution can't reach) and the shared snapshot-cover
transition (``smooth_transition``) that hides every big repaint: the
theme flip itself, the Controls collapse, each agent's Settings gear
and a window maximize/restore.

Split out of gui/__init__.py (Rule #3, god-file refactor step 2/8).
Depends on ``gui.widgets`` (``status`` for tree-tag colours, ``tk_font``/
``TREE_ROW_FACTOR`` for ``setup_style``, and the LIVE ``ACTIVE_THEME``/
``FONT_BASE`` globals via module-attribute access — see the note in
``gui/widgets.py``) and ``gui.icons`` (the big sun/moon cover icon)."""

from __future__ import annotations

import tkinter as tk
from functools import partial
from tkinter import ttk

import customtkinter as ctk
import ttkbootstrap as tb
from PIL import ImageGrab, ImageTk

from painter.config import (
    SWITCH_FADE_MS,
    SWITCH_FADE_STEPS,
    THEMES,
    TRANSITION_FADE_MS,
    TRANSITION_FADE_STEPS,
)

from . import widgets
from .icons import _render_theme_cover_icon
from .widgets import TREE_ROW_FACTOR, status, tk_font


# the Treeview row tags for a tool panel's image rows — their foregrounds
# come from the theme's status colours, re-applied on a flip via skin_tree.
# CHANGED (restorable) rows get a BOLD striking green/teal so they POP;
# SKIPPED (unchanged) rows a muted grey so the two never blur together.
TOOL_CHANGED_TAG = "toolchanged"
TOOL_SKIP_TAG = "skip"



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
                    rowheight=round(widgets.FONT_BASE * TREE_ROW_FACTOR))
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
    widgets.ACTIVE_THEME = name
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
# collapse/expand (the Controls toggle, an agent's Settings gear, a
# tool panel's Advanced section) lands as one hard jump. ONE shared
# mechanism hides all of these (owner 2026-07-20, generalizing the
# theme cross-fade — Rule #5): smooth_transition() grabs the window
# into a borderless topmost overlay, FORCES the cover painted, runs the
# mutate callback (the theme flip / the relayout) hidden behind it,
# then fades the overlay's window alpha out. A pure visual nicety — any
# cover failure (ImageGrab unavailable, alpha unsupported, an unmapped
# window) degrades to the plain instant mutate, never a stuck overlay.
#
# NOT used for a window maximize/restore (owner 2026-07-21 perf fix,
# reverting owner 2026-07-20's own use of it there): a real Windows
# repro proved covering that OS-level state jump breaks it — creating
# the topmost overlay while the WM is mid-transition interrupts the
# real resize/repaint, leaving the window visibly stuck at its old
# size (or corrupted on restore) despite Tk's own state()/winfo_*
# insisting the change already happened. The OS/DWM already animates
# maximize/restore smoothly on its own; see
# ``BuildMixin._on_root_configure`` in gui/app_build.py for the full
# story and the fix.


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


def _pkg():
    """The ``gui`` package namespace. ``smooth_transition`` calls its two
    collaborators through this indirection (rather than this module's own
    globals) so ``monkeypatch.setattr(gui, "_snapshot_overlay"/"_fade_out_
    overlay", ...)`` stays effective post-split, exactly as it was when
    both lived in one module (mechanical adaptation, GUI refactor step
    2/8 — no behavior change for any real caller, since ``gui.X`` is the
    same function object as ``gui.theme.X`` unless a test overrides it)."""
    import gui
    return gui


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
    the Controls collapse, each agent's Settings gear and each tool
    panel's Advanced section (NOT the window maximize/restore — see the
    module-level note above this function's own section header).

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
        overlay = _pkg()._snapshot_overlay(root, icon_factory)
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
        _pkg()._fade_out_overlay(root, overlay, fade_ms, fade_steps)


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

