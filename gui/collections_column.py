"""``CollectionsColumn`` — the setup screens' shared RIGHT column
(faza 3, owner 2026-08-03, UV/prompt.txt tačka 5: "raspored elemenata
na levi i desni panel treba da ima isto kao i Website Image GEN").

ONE component, two hosts (root Rule C — never two copies): the Website
Image GEN setup screen and the API Image GEN panel each show this
column — the Collections queue view (with Add/Remove/Clear/Add
folder), the shared Output folder, the Select-images door, the
Prompt + Image toggle, and the ``PromptImageSection`` in the column's
lower half (visible while the mode is ON). The column splits its own
height 50-50 between the queue half and the section (the owner's
tačka 3 rule), so any host that gives it ``fill=both`` gets the same
look.

STATE IS SHARED, WIDGETS ARE NOT: every column renders the SAME
``PainterGui._sheets`` queue (mutations repaint every registered
column — see ``SettingsMixin._queue_sheets``/``_remove_sheet``/
``_clear_sheets``), the SAME ``out_var`` StringVar (two entries, one
variable — Tk keeps them in lockstep for free), and the SAME
Prompt+Image mode/folder vars (each column carries its own
``PromptImageSection`` instance over those shared vars, so the mode
flips everywhere at once). Remove uses THIS column's own listbox
selection (``gui._remove_sheet(listbox=…)``).
"""

from __future__ import annotations

import tkinter as tk
from tkinter import ttk

from .prompt_image import PromptImageSection
from .theme import skin_listbox
from .widgets import rounded_button, rounded_entry, tk_font


class CollectionsColumn(ttk.Frame):
    """One rendered instance of the shared right column — see the
    module docstring. ``gui`` is the PainterGui host (duck-typed: the
    shared vars + the command methods every button calls). The host
    packs/grids this frame; construction also self-registers into
    ``gui._collections_columns`` so queue repaints and the
    Prompt+Image reconcile reach every instance."""

    def __init__(self, parent, gui):
        super().__init__(parent)
        self._gui = gui
        self.columnconfigure(0, weight=1)
        self.rowconfigure(0, weight=1, uniform="colrow")
        self.rowconfigure(1, weight=1, uniform="colrow")

        top = ttk.Frame(self)
        top.grid(row=0, column=0, sticky="nsew")

        lf = ttk.Labelframe(
            top, text="Collections (prompt .md files, one image set each)"
        )
        lf.pack(fill="both", expand=True, pady=(0, 6))
        self.sheet_list = tk.Listbox(
            lf, height=5, activestyle="none", font=tk_font("mono")
        )
        skin_listbox(self.sheet_list)
        self.sheet_list.pack(side="left", fill="both", expand=True)
        col = ttk.Frame(lf)
        col.pack(side="left", padx=(8, 0), anchor="n")
        rounded_button(
            col, "Add…", command=gui._add_sheets, icon_name="add",
            width=110, icon_edge=True,
        ).pack(fill="x")
        rounded_button(
            col, "Remove",
            command=lambda: gui._remove_sheet(self.sheet_list),
            icon_name="remove", width=110, icon_edge=True,
        ).pack(fill="x", pady=4)
        rounded_button(
            col, "Clear", command=gui._clear_sheets, icon_name="clear",
            width=110, icon_edge=True,
        ).pack(fill="x")
        rounded_button(
            col, "Add folder…", command=gui._add_sheets_folder,
            icon_name="add", width=110, icon_edge=True,
        ).pack(fill="x", pady=(4, 0))

        row = ttk.Frame(top)
        row.pack(fill="x", pady=(4, 2))
        ttk.Label(row, text="Output:", width=8).pack(side="left")
        rounded_entry(row, textvariable=gui.out_var).pack(
            side="left", fill="x", expand=True
        )
        rounded_button(
            row, "Browse…", command=gui._pick_out,
        ).pack(side="left", padx=(8, 0))

        row = ttk.Frame(top)
        row.pack(fill="x", pady=(4, 0))
        self.btn_select = rounded_button(
            row, "Select images…", command=gui._select_images,
        )
        self.btn_select.pack(side="left")
        self.btn_prompt_image = rounded_button(
            row, "Prompt + Image", command=gui._toggle_prompt_image,
        )
        self.btn_prompt_image.pack(side="left", padx=(8, 0))

        self.pi_section = PromptImageSection(
            self,
            get_sheet_paths=lambda: list(gui._sheets),
            on_change=gui._schedule_save,
            enabled_var=gui._pi_enabled_var,
            ref_dir_var=gui._pi_ref_dir_var,
        )
        self.pi_section.grid(row=1, column=0, sticky="nsew", pady=(6, 0))
        self.pi_section.grid_remove()  # hidden until the mode is ON

        gui._collections_columns.append(self)

    def repaint_queue(self, paths) -> None:
        """Refill this column's queue view from the ONE shared
        ``PainterGui._sheets`` list — called by every queue mutation,
        for every registered column."""
        self.sheet_list.delete(0, "end")
        for path in paths:
            self.sheet_list.insert("end", path.name)
