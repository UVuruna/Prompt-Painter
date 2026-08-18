"""``AgentSubPanelsMixin`` — the fine-tune sub-panel behind each of an
``AgentPanel`` switch's expanders (owner's UI-SKETCH, 2026-07-29).

Every one of the five builders fills ONE ``ExpandableSwitch.sub`` box —
BG removal, Force Aspect Ratio, the upscale gate, the Checker/Fixer AI
and the run pacing — eagerly, because state like the ``FilterEditor``
stack and the aspect canvas binding must outlive the expander's
visibility. Beside them live the callbacks those widgets alone use: the
BG colour picker and its swatch renderer, and the aspect canvas/entry
two-way sync.

Split from ``gui/agent_panel.py`` (audit ``docs/AUDIT-OOP-2026-08-18.md``
→ R6, owner chose SPLIT over "irreducible"). What stays in
``agent_panel.py`` is the panel ITSELF — its bands, its vars, its
Start/Pause/Stop, its settings round-trip and its public readers
(``force_aspect_ratio``, ``upscale_params``, ``pace_floats``); what
moved here is what the switches OPEN INTO.

A mixin rather than a helper module because every builder reads and
writes the panel's own tk vars and widget registry (``self._flows``,
``self.bg_mode_var``, ``self.upscale_filter`` …) — the same composition
``gui/app.py`` already uses for ``PainterGui``'s six responsibility
slices. ``AgentPanel`` is the only user; ``ApiImageGenPanel`` has its
own, differently-composed aspect/upscale sub-panels by design (see
``gui/__about/api_panel.md``).
"""

from __future__ import annotations

import tkinter as tk
from tkinter import ttk

from painter.config import (
    BG_COLOR_DEFAULT,
    BG_MODE_COLOR,
    BG_MODE_LABEL,
    BG_REACH_LABEL,
    DEGRADE_CHOICES,
    FIXER_MODE_CHOICES,
    PACE_FAST_S,
    PACE_POLITE_S,
    SITES,
    UPSCALE_MINDIM_STEP,
)

from .aspect_canvas import AspectRatioCanvas, apply_typed_wh
from .filter_editor import FilterEditor
from .tool_panels import ASPECT_DIALOG_ENTRY_W, DENSE_COL_WRAP_PX
from .widgets import (
    FlowRow,
    Spinner,
    rounded_combo,
    rounded_entry,
    rounded_switch,
    tk_font,
)


class AgentSubPanelsMixin:
    """The five fine-tune sub-panels of an ``AgentPanel``. Mixed into
    it — never instantiated alone; every method reads the panel's own
    vars and appends to its ``_flows`` registry."""

    def _build_bg_sub(self, box) -> None:
        """BG removal's own knobs — the SAME set the standalone BG tool
        exposes, passed into ``remove_background`` (see ``bg_params``)."""
        # mode / tolerance / reach are three flow cells — side by side
        # across the full band, wrapping when the window narrows
        flow = FlowRow(box)
        flow.pack(fill="x")
        self._flows.append(flow)
        cell = flow.cell()
        ttk.Label(cell, text="mode").pack(side="left", padx=(0, 4))
        rounded_combo(
            cell, tuple(BG_MODE_LABEL), self.bg_mode_var, width=100,
        ).pack(side="left")
        self._bg_swatch = tk.Label(cell, text="", width=8, cursor="hand2")
        self._bg_swatch.pack(side="left", padx=(8, 0))
        self._bg_swatch.bind("<Button-1>", lambda _e: self._pick_bg_color())
        cell = flow.cell()
        ttk.Label(cell, text="tolerance").pack(side="left", padx=(0, 4))
        Spinner(cell, self.bg_tolerance_var, step=1.0).pack(side="left")
        ttk.Label(cell, text="% per channel").pack(side="left", padx=(4, 0))
        cell = flow.cell()
        ttk.Label(cell, text="reach").pack(side="left", padx=(0, 4))
        rounded_combo(
            cell, tuple(BG_REACH_LABEL), self.bg_reach_var, width=110,
        ).pack(side="left")
        self.bg_mode_var.trace_add(
            "write", lambda *_a: self._render_bg_swatch()
        )
        self.bg_color_var.trace_add(
            "write", lambda *_a: self._render_bg_swatch()
        )
        self._render_bg_swatch()

    def _build_aspect_sub(self, box) -> None:
        """Force Aspect Ratio's target — W/H entries mirrored two-way
        with the SAME AspectRatioCanvas the standalone tool uses."""
        # W/H fields and the canvas are two FLOW cells (owner
        # 2026-08-03, slika 2 — the canvas used to be cut in half):
        # side by side while the band is wide, canvas on its own row
        # the moment it no longer fits.
        flow = FlowRow(box)
        flow.pack(fill="x")
        self._flows.append(flow)
        fa_fields = flow.cell()
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
        canvas_row = flow.cell()
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

    def _build_upscale_sub(self, box) -> None:
        """The upscale gate (GUI rework Phase 6): one min-SIDE spinner
        + the FilterEditor stack deciding WHICH images qualify;
        ``upscale_params()`` resolves both into ``upscale_if_small``'s
        kwargs."""
        # min side + its explanation are two flow cells (owner
        # 2026-08-03, slika 3: the sentence used to be sliced mid-word)
        flow = FlowRow(box)
        flow.pack(fill="x")
        self._flows.append(flow)
        cell = flow.cell()
        ttk.Label(cell, text="min side").pack(side="left", padx=(0, 4))
        Spinner(cell, self.up_minside_var, step=UPSCALE_MINDIM_STEP).pack(
            side="left"
        )
        flow.add(ttk.Label(
            flow, text="px (the smaller side reaches this)"
        ))
        self.upscale_filter = FilterEditor(
            box,
            conditions=self._default_upscale_conditions,
            presets=self._filter_presets,
            on_presets_changed=self._on_filter_presets_changed,
        )
        self.upscale_filter.pack(fill="x", pady=(2, 0))

    def _build_checker_sub(self, box) -> None:
        """The parallel Checker AI's fine-tune (F6): the prompt-match
        toggle + the Fixer AI (auto-fix + api/website mode)."""
        flow = FlowRow(box)
        flow.pack(fill="x")
        self._flows.append(flow)
        flow.switch("Check prompt match too", self.checker_prompt_var)
        cell = flow.cell()
        rounded_switch(cell, "Auto-fix flagged images", self.fixer_var).pack(
            side="left"
        )
        ttk.Label(cell, text="via").pack(side="left", padx=(8, 4))
        rounded_combo(
            cell, FIXER_MODE_CHOICES, self.fixer_mode_var, width=90,
        ).pack(side="left")
        ttk.Label(
            box,
            text="API fix runs alongside the next generation; Website"
            " is QUEUED for 'Send flagged to generator'.",
            style="Muted.TLabel", wraplength=DENSE_COL_WRAP_PX,
        ).pack(anchor="w", pady=(0, 2))

    def _build_pacing_sub(self, flow) -> None:
        """Run pacing: the Polite pace switch and the F2 on-degrade
        choice — flow CELLS (owner 2026-08-03, slika 1), so a narrow
        window wraps them onto further rows instead of cutting the last
        one off. Labels lost their fixed width=12 for the same reason:
        every px of the band is width some element can still use.

        The four pace spinners this group used to hold retired
        2026-08-07 — see `polite_var` and `config.pace_range`."""
        cell = flow.cell()
        rounded_switch(cell, "Polite pace", self.polite_pace_var).pack(side="left")
        ttk.Label(
            cell,
            text=f"{PACE_POLITE_S[0]:.0f}–{PACE_POLITE_S[1]:.0f}s between"
                 f" images; off = {PACE_FAST_S[0]:.0f}–{PACE_FAST_S[1]:.0f}s",
            style="Muted.TLabel",
        ).pack(side="left", padx=(8, 0))
        cell = flow.cell()
        ttk.Label(cell, text="on degrade").pack(side="left", padx=(0, 4))
        rounded_combo(
            cell, DEGRADE_CHOICES, self.degrade_var, width=110,
        ).pack(side="left")

    def _pick_bg_color(self) -> None:
        from tkinter import colorchooser

        picked = colorchooser.askcolor(
            initialcolor=self.bg_color_var.get() or BG_COLOR_DEFAULT,
            parent=self,
            title=f"{SITES[self.site_key].name} — BG color to remove",
        )
        if picked and picked[1]:
            self.bg_color_var.set(picked[1])

    def _render_bg_swatch(self) -> None:
        """The removal-color swatch shows only in COLOR mode."""
        if self.bg_mode_var.get() != BG_MODE_COLOR:
            self._bg_swatch.pack_forget()
            return
        hex_color = self.bg_color_var.get() or BG_COLOR_DEFAULT
        try:
            r, g, b = (
                int(hex_color[1:3], 16),
                int(hex_color[3:5], 16),
                int(hex_color[5:7], 16),
            )
        except (ValueError, IndexError):
            hex_color, (r, g, b) = BG_COLOR_DEFAULT, (255, 255, 255)
        luma = 0.299 * r + 0.587 * g + 0.114 * b
        self._bg_swatch.configure(
            text=hex_color, bg=hex_color,
            fg="#000000" if luma > 140 else "#ffffff",
        )
        if not self._bg_swatch.winfo_manager():
            self._bg_swatch.pack(side="left", padx=(8, 0))

    def _on_force_aspect_canvas_drag(self, w: int, h: int) -> None:
        """``AspectRatioCanvas.on_change`` — a drag mirrored into the W/H
        entries (whose own trace calls back into ``set_ratio``, a no-op
        echo — see that method's docstring). Same pattern as
        ``AspectRatioDialog._on_canvas_drag``."""
        self.force_aspect_w_var.set(str(w))
        self.force_aspect_h_var.set(str(h))

    def _on_force_aspect_wh_typed(self, *_args) -> None:
        """Live-reshape the canvas as the owner types a new W/H — the
        shared ``apply_typed_wh`` does the read-parse-guard-apply; final
        validation happens in ``force_aspect_ratio()`` on Start."""
        apply_typed_wh(
            self.force_aspect_w_var, self.force_aspect_h_var,
            self._force_aspect_canvas,
        )
