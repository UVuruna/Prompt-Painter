"""The three PIXEL-GEOMETRY tools' settings panels — one cohesive
family, each a thin subclass over the shared
[Base Tool Settings Panel](base.md):

* ``CropSettingsPanel`` (GUI rework Phase 13) — autocrop to the content
  box; Advanced exposes every knob ``crop_transparent`` reads.
* ``UpscaleSettingsPanel`` (Phase 14) — the min-SIDE spinner over the
  shared filter gate; no Advanced section.
* ``AspectSettingsPanel`` (Phase 14) — the target W:H editor with the
  live ``AspectRatioCanvas``; no Advanced section.

Split out of the single-file ``gui/tool_panels.py`` (root Rule #20,
2026-07-30). They share a module because all three are the same
responsibility in three shapes — change the pixel GEOMETRY of an
already-saved image — and each panel body is thin (the engine does the
work).
"""

from __future__ import annotations

import tkinter as tk
from pathlib import Path
from tkinter import ttk
from typing import Callable

from painter import filters
from painter.config import (
    ASPECT_DEFAULT_H,
    ASPECT_DEFAULT_W,
    CLEAN_EDGE_ENABLE,
    CROP_INK_ALPHA,
    CROP_MARGIN_PX,
    CROP_MIN_INK_PX,
    FILTER_KIND_ASPECT_RANGE,
    FILTER_POLARITY_IF,
    UPSCALE_ASPECT_MAX,
    UPSCALE_ASPECT_MIN,
    UPSCALE_MINDIM_STEP,
    UPSCALE_MIN_SIDE_DEFAULT,
)
from ..aspect_canvas import AspectRatioCanvas
from ..logic import _upscale_params_from_side_and_filter
from ..widgets import (
    Spinner,
    _parse_int_range,
    _parse_nonneg_int,
    rounded_entry,
    rounded_switch,
    tk_font,
)
from .base import ToolSettingsPanel
from .layout import ASPECT_DIALOG_ENTRY_W, DENSE_COL_WRAP_PX


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
            wraplength=DENSE_COL_WRAP_PX,
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
            style="Muted.TLabel", wraplength=DENSE_COL_WRAP_PX,
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

