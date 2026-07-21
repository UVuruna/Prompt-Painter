"""DayNightSwitch — the mini Day/Night toggle, top-right: an anti-
aliased PIL-composited image pill (dark starfield + moon / sky + sun)
ported from the owner's website switch. A click flips the theme
synchronously (via the shared snapshot-cover transition) while the
knob itself slides as a smoothstep-eased flourish.

Split out of gui/__init__.py (Rule #3, god-file refactor step 2/8)."""

from __future__ import annotations

import tkinter as tk

from PIL import ImageTk

from painter.config import (
    SWITCH_ANIM_MS,
    SWITCH_ASPECT,
    SWITCH_FRAME_MS,
    SWITCH_H,
    SWITCH_HOVER_SCALE,
    SWITCH_KNOB_FACTOR,
    SWITCH_PAD_PX,
    SWITCH_SUPERSAMPLE,
    SWITCH_TRACK_DAY_SVG,
    SWITCH_TRACK_NIGHT_SVG,
    THEMES,
)

from . import widgets
from .icons import _render_moon_knob, _render_sun_knob, _render_switch_track
from .theme import apply_theme, skin_canvas


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
        self._on = THEMES[widgets.ACTIVE_THEME]["switch_on"]  # reflect the theme
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

