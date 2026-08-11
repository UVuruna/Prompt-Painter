"""``PromptImageSection`` — the PROMPT + IMAGE mode's setup surface
(faza 2, owner 2026-08-03, UV/prompt.txt tačka 3).

The owner's rule: with the mode ON, a run generates ONLY the items
that have BOTH a prompt and their declared reference image(s) on disk
— "ako učitam sve promptove i samo 1 sliku, radi se tačno 1 slika".
The pairing itself is AUTHORED IN THE SHEET (the ``←`` line(s) per
entry — see instructions.md rule 3c; a reference sheet's prompt says
"the ATTACHED IMAGE" and the likeness arrives as the attachment),
never guessed here by filename matching.

This section owns the run's REFERENCE FOLDER — the second rung of the
binding resolution order (sheet folder → Reference folder → absolute,
``painter.sheet_parser.resolve_input_images`` — the ONE resolution truth
this widget deliberately reuses instead of re-deriving) — and a live
eligibility view over the queued collections: per entry ✔ complete /
✖ reference missing / — no ``←`` line, plus the summary count the
owner reads before Start. The section only REPORTS; the actual
narrowing happens in ``run_sheet(require_input_image=True)`` at Start,
against the disk state of that moment.

Shared by design: Website Image GEN hosts it now; API Image GEN gets
the same section when its panel moves onto the shared setup skeleton
(faza 3) — one widget, never two copies (root Rule C).
"""

from __future__ import annotations

import tkinter as tk
from pathlib import Path
from tkinter import filedialog, ttk
from typing import Callable

from painter.sheet_parser import resolve_input_images
from painter.sheet_parser import SheetError, parse_sheet
from .theme import skin_listbox
from .widgets import rounded_button, rounded_entry, tk_font

# debounce for the Reference-folder entry's trace — a keystroke per
# refresh would re-parse every queued sheet on each typed character
_REFRESH_DEBOUNCE_MS = 350


class PromptImageSection(ttk.Labelframe):
    """The Prompt + Image mode's own settings/status section — see the
    module docstring. Built once, shown only while the mode is ON
    (``PainterGui._apply_prompt_image_state`` grids/hides it beneath
    the Collections queue, the right column's lower half)."""

    def __init__(
        self,
        parent,
        get_sheet_paths: Callable[[], list[Path]],
        on_change: Callable[[], None] | None = None,
        enabled_var: tk.BooleanVar | None = None,
        ref_dir_var: tk.StringVar | None = None,
    ):
        super().__init__(parent, text="Prompt + Image (reference sheets)")
        self._get_sheet_paths = get_sheet_paths
        self._on_change = on_change or (lambda: None)
        self._refresh_job: str | None = None

        # the mode toggle's STATE (the button that flips it sits beside
        # "Select images…" in every CollectionsColumn). ``enabled_var``/
        # ``ref_dir_var`` may be SHARED vars passed in (faza 3 — the
        # website and API columns each render their own section over
        # the ONE mode state); a standalone section (tests) makes its
        # own.
        self.enabled_var = enabled_var or tk.BooleanVar(value=False)
        self.ref_dir_var = ref_dir_var or tk.StringVar(value="")

        row = ttk.Frame(self)
        row.pack(fill="x", pady=(2, 2))
        ttk.Label(row, text="Reference folder:").pack(side="left")
        rounded_entry(row, textvariable=self.ref_dir_var).pack(
            side="left", fill="x", expand=True, padx=(6, 0)
        )
        rounded_button(row, "Browse…", icon_name="browse", command=self._pick_ref_dir).pack(
            side="left", padx=(8, 0)
        )

        self.summary_var = tk.StringVar(value="")
        ttk.Label(
            self, textvariable=self.summary_var, style="Muted.TLabel",
        ).pack(anchor="w", pady=(2, 2))

        self.status_list = tk.Listbox(
            self, height=6, activestyle="none", font=tk_font("mono")
        )
        skin_listbox(self.status_list)
        self.status_list.pack(fill="both", expand=True)

        self.ref_dir_var.trace_add("write", self._on_ref_dir_typed)

    # --- inputs --------------------------------------------------------

    def _pick_ref_dir(self) -> None:
        folder = filedialog.askdirectory(
            title="Reference-images folder (the ← paths resolve here"
                  " when not found beside the sheet)"
        )
        if folder:
            self.ref_dir_var.set(folder)

    def _on_ref_dir_typed(self, *_args) -> None:
        self._on_change()
        if self._refresh_job is not None:
            self.after_cancel(self._refresh_job)
        self._refresh_job = self.after(_REFRESH_DEBOUNCE_MS, self.refresh)

    def enabled(self) -> bool:
        return self.enabled_var.get()

    def reference_dir(self) -> Path | None:
        """The picked folder as a Path, or None while blank. A set but
        NONEXISTENT folder still returns (and ``refresh`` flags it) —
        the resolver simply finds nothing there, loudly per item."""
        raw = self.ref_dir_var.get().strip()
        return Path(raw) if raw else None

    # --- the live eligibility view ------------------------------------

    def refresh(self) -> None:
        """Re-parse the queued collections and rebuild the per-entry
        eligibility list + summary against the CURRENT disk state.
        Called on: mode ON, Reference-folder change (debounced), and
        every queue mutation while the mode is on (PainterGui's
        _queue_sheets/_remove_sheet/_clear_sheets hooks)."""
        self._refresh_job = None
        box = self.status_list
        box.delete(0, "end")
        ref_dir = self.reference_dir()
        prompts = 0
        complete = 0
        if ref_dir is not None and not ref_dir.is_dir():
            box.insert("end", f"⚠ Reference folder not found: {ref_dir}")
        for path in self._get_sheet_paths():
            try:
                sheet = parse_sheet(path)
            except (SheetError, OSError) as exc:
                box.insert("end", f"⚠ {path.name}: {exc}")
                continue
            box.insert("end", f"— {path.name} —")
            for item in sheet.items:
                prompts += 1
                if not item.input_images:
                    box.insert(
                        "end", f"  — {item.title} — no ← reference line"
                    )
                    continue
                resolved, missing = resolve_input_images(
                    item.input_images, sheet.source.parent, ref_dir
                )
                if missing:
                    box.insert(
                        "end",
                        f"  ✖ {item.title} — MISSING: {', '.join(missing)}",
                    )
                else:
                    names = ", ".join(Path(p).name for p in resolved)
                    box.insert("end", f"  ✔ {item.title} — {names}")
                    complete += 1
        self.summary_var.set(
            f"{prompts} prompt(s) · {complete} complete pair(s)"
            f" → {complete} will run"
        )

    # --- persistence (the same round-trip shape every panel uses) ------

    def get_settings(self) -> dict:
        return {
            "enabled": self.enabled_var.get(),
            "reference_dir": self.ref_dir_var.get(),
        }

    def apply_settings(self, stored: dict) -> None:
        if "enabled" in stored:
            self.enabled_var.set(bool(stored["enabled"]))
        if "reference_dir" in stored:
            self.ref_dir_var.set(stored["reference_dir"])
