"""``BgSettingsPanel`` — the BG-removal tool's own settings panel (GUI
rework Phase 13; the mode + custom-colour block owner 2026-07-28): the
always-visible mode dropdown (auto / white / black / a CUSTOM colour
with its wheel, live swatch and ±% tolerance), the reach choice (flood
from the frame vs everywhere) and the three per-path safety guards in
Advanced.

Split out of the single-file ``gui/tool_panels.py`` (root Rule #20,
2026-07-30).
"""

from __future__ import annotations

import tkinter as tk
from pathlib import Path
from tkinter import ttk
from typing import Callable

import customtkinter as ctk

from painter.config import (
    BG_COLOR_DEFAULT,
    BG_COLOR_TOLERANCE_PCT,
    BG_MODE_COLOR,
    BG_MODE_DEFAULT,
    BG_MODE_LABEL,
    BG_REACH_ALL,
    BG_REACH_DEFAULT,
    BG_REACH_LABEL,
    SAFETY_MAX_REMOVE_FRAC,
    SAFETY_MAX_REMOVE_FRAC_COLOR,
    SAFETY_MAX_REMOVE_FRAC_WHITE,
    theme_pair,
)
from ..widgets import (
    Spinner,
    _parse_percent,
    rounded_combo,
    rounded_entry,
)
from .base import ToolSettingsPanel
from .layout import DENSE_COL_WRAP_PX

# BG panel's mode dropdown: the SHOWN label back to the stored mode key
# (settings.json always carries the KEY, so relabelling never
# invalidates a saved run — see config's own BG_MODE_LABEL note).
BG_MODE_BY_LABEL = {label: mode for mode, label in BG_MODE_LABEL.items()}
BG_REACH_BY_LABEL = {label: r for r, label in BG_REACH_LABEL.items()}
BG_SWATCH_PX = 24  # the custom-colour live preview chip


class BgSettingsPanel(ToolSettingsPanel):
    """BG removal's persistent settings panel (GUI rework Phase 13;
    the mode + custom-colour block owner 2026-07-28).

    ``_build_extra`` — ALWAYS VISIBLE, the panel's PRIMARY control —
    answers "which background is this?": Auto (white/black, then the
    colour the four corners agree on), forced Black, forced White, or
    **Custom colour** plus a ± tolerance, which clears ANY background
    colour. The colour and tolerance fields show only in Custom mode (a
    dead colour field beside "Auto" would read as if it applied — Rule
    #1); a live swatch previews the typed hex and a live hint spells
    the tolerance out in colour LEVELS and the actual span it covers,
    because "% of 255" means nothing at a glance. Tolerance 0 is legal
    and keys the typed colour exactly.

    Advanced keeps the SAFETY GUARD ceilings ``remove_background``
    aborts past (owner 2026-07-19's "never destroy an image" rule), now
    THREE — one per path, since custom colour has its own high guard —
    expressed as PERCENT of the image, not as the raw fraction the
    engine compares against (owner 2026-07-28: a bare "0.40" in a box
    tells the reader nothing). They are the engine's fine-tune, and the
    abort message names the guard that fired and points back here: the
    owner's "pointers" case (a legitimate 42 %-background plate bailing
    on black's 40 %) was unreadable precisely because the old message
    named neither.

    Not here: the border-halo-cleanup toggle the design's own phase
    notes mention. That constant (``CLEAN_EDGE_ENABLE``) is only ever
    read by ``crop_transparent`` (its docstring: "only serves to ENABLE
    a tighter crop") — ``remove_background`` never calls
    ``clean_edge_halo`` at all, so surfacing it here would silently do
    nothing (root Rule #1). It lives on ``CropSettingsPanel`` instead,
    where it actually affects behaviour; see that class's own
    docstring."""

    SLOT = "bg"

    def _build_extra(self, box: ttk.Frame) -> None:
        ttk.Label(
            box, text="Background — which color the removal clears:",
        ).pack(anchor="w", pady=(0, 2))
        row = ttk.Frame(box)
        row.pack(fill="x", pady=2)
        self.bg_mode_var = tk.StringVar(value=BG_MODE_LABEL[BG_MODE_DEFAULT])
        rounded_combo(
            row, list(BG_MODE_LABEL.values()), self.bg_mode_var, width=150,
            command=lambda _label: self._apply_color_visibility(),
        ).pack(side="left")
        # worded to stay TRUE in every mode — it sits beside the
        # dropdown, so a note describing only Auto would read as a
        # claim about whatever is currently selected
        ttk.Label(
            row,
            text="Auto reads white/black, then the color the four"
            " corners agree on",
            wraplength=DENSE_COL_WRAP_PX,
        ).pack(side="left", padx=(6, 0))

        # color + tolerance: Custom mode only (see _apply_color_visibility)
        self._color_box = ttk.Frame(box)
        crow = ttk.Frame(self._color_box)
        crow.pack(fill="x", pady=2)
        ttk.Label(crow, text="color", width=8).pack(side="left")
        self.bg_color_var = tk.StringVar(value=BG_COLOR_DEFAULT)
        rounded_entry(
            crow, width=90, textvariable=self.bg_color_var, justify="center",
        ).pack(side="left")
        # the swatch is a BUTTON, not decoration (owner 2026-07-28):
        # clicking it opens the color picker. hand2 + the note beside it
        # say so, since a plain chip reads as a read-only preview.
        self._color_swatch = ctk.CTkLabel(
            crow, text="", width=BG_SWATCH_PX, height=BG_SWATCH_PX,
            corner_radius=6, bg_color=theme_pair("bg"), cursor="hand2",
        )
        self._color_swatch.pack(side="left", padx=(6, 0))
        self._color_swatch.bind("<Button-1>", self._pick_color)
        ttk.Label(
            crow, text="← click to pick", style="Muted.TLabel",
        ).pack(side="left", padx=(6, 0))

        trow = ttk.Frame(self._color_box)
        trow.pack(fill="x", pady=2)
        ttk.Label(trow, text="±", width=8).pack(side="left")
        self.bg_tolerance_var = tk.StringVar(
            value=f"{BG_COLOR_TOLERANCE_PCT:.2f}"
        )
        # decimals=2 (not the step-derived 0): the tolerance's own
        # canonical value is 6.67, and a whole-number spinner would
        # silently round a typed 6.67 to 7 on the first +/- click
        Spinner(
            trow, self.bg_tolerance_var, step=1.0, entry_width=52,
            decimals=2,
        ).pack(side="left")
        # the % is meaningless on its own — show what it MEANS in the
        # units the colour is written in (owner 2026-07-28)
        self._tolerance_hint = tk.StringVar()
        ttk.Label(
            trow, textvariable=self._tolerance_hint,
            wraplength=DENSE_COL_WRAP_PX,
        ).pack(side="left", padx=(4, 0))

        # both traces LAST, once every widget and var they touch exists
        # (the colour drives the swatch AND the tolerance hint's span)
        self.bg_color_var.trace_add("write", self._sync_color_fields)
        self.bg_tolerance_var.trace_add("write", self._sync_tolerance_hint)
        # REACH — orthogonal to the mode, so its own row, always shown
        # (owner 2026-07-28). It answers a question the flood fill
        # silently decided for him: does an ENCLOSED patch of the
        # background colour — the counters inside HOPE's O and P — go
        # too, or stay?
        ttk.Label(
            box, text="Remove matching pixels:",
        ).pack(anchor="w", pady=(8, 2))
        rrow = ttk.Frame(box)
        rrow.pack(fill="x", pady=2)
        self.bg_reach_var = tk.StringVar(
            value=BG_REACH_LABEL[BG_REACH_DEFAULT]
        )
        rounded_combo(
            rrow, list(BG_REACH_LABEL.values()), self.bg_reach_var,
            width=190, command=lambda _label: self._sync_reach_hint(),
        ).pack(side="left")
        self._reach_hint = tk.StringVar()
        ttk.Label(
            rrow, textvariable=self._reach_hint,
            wraplength=DENSE_COL_WRAP_PX,
        ).pack(side="left", padx=(6, 0))

        self._sync_color_fields()
        self._sync_reach_hint()
        self._apply_color_visibility()

    def _sync_reach_hint(self, *_args) -> None:
        everywhere = (
            BG_REACH_BY_LABEL[self.bg_reach_var.get()] == BG_REACH_ALL
        )
        self._reach_hint.set(
            "every matching pixel — enclosed ones too (letters become"
            " outlines)"
            if everywhere else
            "only what connects to the frame — enclosed patches stay"
        )

    def _sync_color_fields(self, *_args) -> None:
        self._sync_color_swatch()
        self._sync_tolerance_hint()

    def _pick_color(self, *_event) -> None:
        """Open the color picker on the swatch (owner 2026-07-28).

        ttkbootstrap's own ``ColorChooserDialog`` rather than tkinter's
        bare OS dialog: it is THEMED like the rest of the app (Rule
        #16), and it carries an EYEDROPPER — the fastest way to answer
        "what colour is this background?" is to pick it off the image
        on screen instead of reading a hex out of another tool.

        Cancel leaves the field untouched. Whatever the dialog returns
        is normalised through the same parser the run uses, so the
        field only ever holds a form the engine accepts."""
        from ttkbootstrap.dialogs.colorchooser import ColorChooserDialog

        from painter.bg_remove import format_hex_color, parse_hex_color

        try:
            initial = format_hex_color(parse_hex_color(self.bg_color_var.get()))
        except ValueError:
            initial = BG_COLOR_DEFAULT  # half-typed field — start neutral
        dialog = ColorChooserDialog(
            self.winfo_toplevel(), "Background color", initial
        )
        dialog.show()
        if dialog.result is None:
            return  # cancelled
        self.bg_color_var.set(
            format_hex_color(parse_hex_color(dialog.result.hex))
        )

    def _sync_tolerance_hint(self, *_args) -> None:
        """Spell the tolerance out in colour levels: '% of 255' means
        nothing at a glance, '± 17 levels · #EE0000…#FF1111' does."""
        from painter.bg_remove import (
            format_hex_color, parse_hex_color, tolerance_to_distance,
        )

        try:
            levels = tolerance_to_distance(
                float(self.bg_tolerance_var.get().strip())
            )
        except ValueError:
            self._tolerance_hint.set("% per channel")
            return
        if levels == 0:
            self._tolerance_hint.set("% — EXACTLY the color above")
            return
        span = ""
        try:
            rgb = parse_hex_color(self.bg_color_var.get())
            lo = tuple(max(0, c - levels) for c in rgb)
            hi = tuple(min(255, c + levels) for c in rgb)
            span = (f" · {format_hex_color(lo)}…{format_hex_color(hi)}")
        except ValueError:
            pass  # half-typed colour — the levels alone still inform
        self._tolerance_hint.set(f"% — ± {levels} levels per channel{span}")

    def _sync_color_swatch(self, *_args) -> None:
        """Preview the typed hex. An unparsable colour greys the chip
        rather than raising — the LOUD report is ``build_func``'s, at
        Start, where a bad colour actually stops the run (Rule #1); a
        live preview of half-typed text must not throw on every
        keystroke."""
        from painter.bg_remove import parse_hex_color

        try:
            rgb = parse_hex_color(self.bg_color_var.get())
        except ValueError:
            self._color_swatch.configure(fg_color=theme_pair("secondary"))
            return
        self._color_swatch.configure(fg_color="#%02X%02X%02X" % rgb)

    def _apply_color_visibility(self) -> None:
        """The colour/tolerance fields belong to Custom mode alone."""
        if BG_MODE_BY_LABEL[self.bg_mode_var.get()] == BG_MODE_COLOR:
            self._color_box.pack(fill="x", pady=(2, 0))
        else:
            self._color_box.pack_forget()
        self._on_layout_change()

    def _build_advanced(self, box: ttk.Frame) -> None:
        # PERCENT, not the raw fraction the engine compares against
        # (owner 2026-07-28: a bare "0.40" in a box says nothing; "40 %
        # of the image" says exactly what it does). Converted back at
        # build_func, so the engine contract is unchanged.
        ttk.Label(
            box,
            text="Safety guard — refuse the removal when it would clear"
            " more than this much of the image:",
            wraplength=DENSE_COL_WRAP_PX * 2,
        ).pack(anchor="w", pady=(0, 2))
        self.safety_black_var = tk.StringVar(
            value=f"{SAFETY_MAX_REMOVE_FRAC * 100:g}"
        )
        self.safety_white_var = tk.StringVar(
            value=f"{SAFETY_MAX_REMOVE_FRAC_WHITE * 100:g}"
        )
        self.safety_color_var = tk.StringVar(
            value=f"{SAFETY_MAX_REMOVE_FRAC_COLOR * 100:g}"
        )
        for label, var, note in (
            ("black bg", self.safety_black_var,
             "% — tight: black is a GUESS, and a dark subject reads as"
             " background"),
            ("white bg", self.safety_white_var,
             "% — high: real white plates legitimately clear ~57 %"),
            ("custom bg", self.safety_color_var,
             "% — high: the color is known, not inferred"),
        ):
            row = ttk.Frame(box)
            row.pack(fill="x", pady=2)
            ttk.Label(row, text=label, width=10).pack(side="left")
            Spinner(row, var, step=5.0, entry_width=52).pack(side="left")
            ttk.Label(
                row, text=note, wraplength=DENSE_COL_WRAP_PX,
            ).pack(side="left", padx=(6, 0))

    def build_func(self) -> Callable[[Path, Callable[[str], None]], str]:
        from painter.bg_remove import parse_hex_color
        from painter.postprocess import remove_background

        mode = BG_MODE_BY_LABEL[self.bg_mode_var.get()]
        color = self.bg_color_var.get()
        tolerance = _parse_percent(
            self.bg_tolerance_var.get(), "background tolerance"
        )
        if mode == BG_MODE_COLOR:
            parse_hex_color(color)  # loud at Start, not per image
        # the fields are PERCENT; the engine takes the fraction
        black = _parse_percent(
            self.safety_black_var.get(), "black bg safety"
        ) / 100.0
        white = _parse_percent(
            self.safety_white_var.get(), "white bg safety"
        ) / 100.0
        custom = _parse_percent(
            self.safety_color_var.get(), "custom bg safety"
        ) / 100.0
        reach = BG_REACH_BY_LABEL[self.bg_reach_var.get()]
        return lambda path, log: remove_background(
            path, log,
            mode=mode, color=color, tolerance_pct=tolerance, reach=reach,
            safety_max_remove_frac=black,
            safety_max_remove_frac_white=white,
            safety_max_remove_frac_color=custom,
        )

    def _advanced_settings(self) -> dict:
        # the guard keys carry the _pct SUFFIX because their UNIT
        # changed (fraction -> percent, owner 2026-07-28). A settings
        # file written by the fraction build stores "0.40" under the old
        # bare key; read as percent that would be 0.4 % — a guard that
        # refuses everything. The renamed key simply is not there, so
        # such a file falls back to the correct defaults instead of
        # being silently misread (Rule #6 — no translating shim).
        return {
            "bg_mode": BG_MODE_BY_LABEL[self.bg_mode_var.get()],
            "bg_color": self.bg_color_var.get(),
            "bg_tolerance": self.bg_tolerance_var.get(),
            "bg_reach": BG_REACH_BY_LABEL[self.bg_reach_var.get()],
            "safety_black_pct": self.safety_black_var.get(),
            "safety_white_pct": self.safety_white_var.get(),
            "safety_color_pct": self.safety_color_var.get(),
        }

    def _apply_advanced_settings(self, stored: dict) -> None:
        # an UNKNOWN stored mode (a settings.json from a build whose
        # mode list differed) keeps the current default rather than
        # putting a label the dropdown cannot resolve into the var
        if stored.get("bg_mode") in BG_MODE_LABEL:
            self.bg_mode_var.set(BG_MODE_LABEL[stored["bg_mode"]])
        if "bg_color" in stored:
            self.bg_color_var.set(stored["bg_color"])
        if "bg_tolerance" in stored:
            self.bg_tolerance_var.set(stored["bg_tolerance"])
        if stored.get("bg_reach") in BG_REACH_LABEL:
            self.bg_reach_var.set(BG_REACH_LABEL[stored["bg_reach"]])
        self._sync_reach_hint()
        if "safety_black_pct" in stored:
            self.safety_black_var.set(stored["safety_black_pct"])
        if "safety_white_pct" in stored:
            self.safety_white_var.set(stored["safety_white_pct"])
        if "safety_color_pct" in stored:
            self.safety_color_var.set(stored["safety_color_pct"])
        self._apply_color_visibility()

