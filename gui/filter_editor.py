"""``FilterEditor`` — the reusable stacked-filter widget (GUI rework
Phase 4, wraps ``painter.filters``) — pulled out of ``gui/__init__.py``
(god-file refactor, Rule #20). Pure Tk pixel geometry only; the
engine-side kind/polarity strings and the exact-aspect tolerance live
in ``painter/config.py`` alongside the rest of the FILTER_* constants —
this module is gui's own Rule #4 home for the row/editor geometry.
"""

from __future__ import annotations

import tkinter as tk
from tkinter import messagebox, ttk
from typing import Callable

from painter import filters
from painter.config import (
    ASPECT_FILTER_DEFAULT_FROM,
    ASPECT_FILTER_DEFAULT_TO,
    FILTER_ASPECT_EXACT_TOL,
    FILTER_KIND_ANY_SIDE,
    FILTER_KIND_ASPECT_EXACT,
    FILTER_KIND_ASPECT_RANGE,
    FILTER_KIND_HEIGHT,
    FILTER_KIND_WIDTH,
    FILTER_KINDS,
    FILTER_POLARITY_IF,
    FILTER_POLARITY_IF_NOT,
)
from .widgets import INPUT_HEIGHT, rounded_button, rounded_combo, rounded_entry

FILTER_ROW_KIND_W = 132      # kind combo (fits "Aspect (exact)")
FILTER_ROW_POLARITY_W = 78   # the IF / IF NOT combo
FILTER_ROW_ENTRY_W = 64      # each lo/hi (or single ratio) numeric field
FILTER_ROW_DECIMALS = 3      # aspect kinds' lo/hi/ratio display precision
FILTER_ROW_GAP_PX = 6        # vertical gap between stacked rows / sections
FILTER_PRESET_COMBO_W = 160  # the saved-preset name combo

# the unit suffix shown per kind (a display nicety mirroring the old
# single-filter dialog's trailing "W/H" label) — aspect kinds compare a
# ratio, ANY_SIDE/WIDTH/HEIGHT compare raw pixels
_FILTER_UNIT_LABEL: dict[str, str] = {
    FILTER_KIND_ASPECT_EXACT: "W/H",
    FILTER_KIND_ASPECT_RANGE: "W/H",
    FILTER_KIND_ANY_SIDE: "px",
    FILTER_KIND_WIDTH: "px",
    FILTER_KIND_HEIGHT: "px",
}


def _filter_row_display_bounds(condition: filters.FilterCondition) -> tuple[str, str]:
    """One condition's lo/hi as the STRINGS a row's fields should show.

    "Aspect (exact)" is authored from a single RATIO field (see
    ``_FilterConditionRow.to_condition``, which widens it back out by
    ``FILTER_ASPECT_EXACT_TOL``): displayed here as the MIDPOINT of the
    stored ``[lo, hi]`` band — the inverse operation, so a round-trip
    through set_conditions()/get_conditions() reproduces the same band
    as long as the tolerance constant hasn't changed in between. Aspect
    (range) shows both bounds at ``FILTER_ROW_DECIMALS``; the pixel
    kinds (any side / width / height) show plain integers-if-whole via
    ``:g`` rather than a padded decimal (800, not 800.000)."""
    if condition.kind == FILTER_KIND_ASPECT_EXACT:
        text = f"{(condition.lo + condition.hi) / 2:.{FILTER_ROW_DECIMALS}f}"
        return text, text
    if condition.kind == FILTER_KIND_ASPECT_RANGE:
        return (
            f"{condition.lo:.{FILTER_ROW_DECIMALS}f}",
            f"{condition.hi:.{FILTER_ROW_DECIMALS}f}",
        )
    return f"{condition.lo:g}", f"{condition.hi:g}"


class _FilterConditionRow(ttk.Frame):
    """One stacked row inside a ``FilterEditor``: kind + polarity
    combos, one or two numeric fields, and a remove button — bridges a
    single ``FilterCondition`` to live Tk Vars and back.

    "Aspect (exact)" is special-cased to ONE visible numeric field (a
    target RATIO, not a lo/hi pair): ``to_condition`` widens it into a
    ``[ratio - FILTER_ASPECT_EXACT_TOL, ratio + FILTER_ASPECT_EXACT_TOL]``
    band so a real decoded image actually matches (Phase 3's flagged
    razor-thin-equality caveat — see ``config.FILTER_ASPECT_EXACT_TOL``).
    Every other kind shows both a FROM and a TO field, stored verbatim.
    Switching a row's kind does NOT reinterpret or clear whatever is
    already typed — the field(s) simply show/hide; the owner retypes
    the value for the newly-chosen kind, same as picking a different
    kind was always going to need a different number anyway."""

    def __init__(
        self, parent, condition: filters.FilterCondition,
        on_remove: Callable[["_FilterConditionRow"], None],
    ):
        super().__init__(parent)
        self._on_remove = on_remove
        self.kind_var = tk.StringVar(value=condition.kind)
        self.polarity_var = tk.StringVar(value=condition.polarity)
        lo_text, hi_text = _filter_row_display_bounds(condition)
        self.lo_var = tk.StringVar(value=lo_text)
        self.hi_var = tk.StringVar(value=hi_text)

        rounded_combo(
            self, FILTER_KINDS, self.kind_var, width=FILTER_ROW_KIND_W,
        ).pack(side="left", padx=(0, 6))
        rounded_combo(
            self, (FILTER_POLARITY_IF, FILTER_POLARITY_IF_NOT),
            self.polarity_var, width=FILTER_ROW_POLARITY_W,
        ).pack(side="left", padx=(0, 6))
        self.lo_entry = rounded_entry(
            self, width=FILTER_ROW_ENTRY_W, textvariable=self.lo_var,
            justify="center",
        )
        self.lo_entry.pack(side="left")
        self._dash = ttk.Label(self, text="–")
        self.hi_entry = rounded_entry(
            self, width=FILTER_ROW_ENTRY_W, textvariable=self.hi_var,
            justify="center",
        )
        self._unit = ttk.Label(self, text="")
        rounded_button(
            self, "✕", command=lambda: self._on_remove(self),
            kind="danger-outline", width=INPUT_HEIGHT,
        ).pack(side="right")

        self.kind_var.trace_add("write", lambda *_a: self._sync_layout())
        self._sync_layout()

    def _sync_layout(self) -> None:
        """Show the TO field + unit suffix for every kind except
        "Aspect (exact)" (one ratio field only); re-packed with
        ``after=`` each call so the left-to-right order is correct
        regardless of how many times the kind has flipped back and
        forth."""
        kind = self.kind_var.get()
        exact = kind == FILTER_KIND_ASPECT_EXACT
        self._dash.pack_forget()
        self.hi_entry.pack_forget()
        self._unit.pack_forget()
        last = self.lo_entry
        if not exact:
            self._dash.pack(side="left", padx=4, after=self.lo_entry)
            self.hi_entry.pack(side="left", padx=(0, 6), after=self._dash)
            last = self.hi_entry
        self._unit.configure(text=_FILTER_UNIT_LABEL.get(kind, ""))
        self._unit.pack(side="left", padx=(4, 0), after=last)

    def to_condition(self) -> filters.FilterCondition:
        """This row's live edit -> a ``FilterCondition``. Raises
        ``ValueError`` (naming the offending kind) on an unparsable or
        inverted bound — the caller (``FilterEditor.get_conditions``)
        lets this propagate; ITS caller decides how to surface it."""
        kind = self.kind_var.get()
        polarity = self.polarity_var.get()
        try:
            lo_raw = float(self.lo_var.get().strip())
        except ValueError:
            raise ValueError(
                f"{kind}: the value must be a number."
            ) from None
        if kind == FILTER_KIND_ASPECT_EXACT:
            return filters.FilterCondition(
                kind=kind, polarity=polarity,
                lo=lo_raw - FILTER_ASPECT_EXACT_TOL,
                hi=lo_raw + FILTER_ASPECT_EXACT_TOL,
            )
        try:
            hi_raw = float(self.hi_var.get().strip())
        except ValueError:
            raise ValueError(
                f"{kind}: the TO value must be a number."
            ) from None
        if lo_raw > hi_raw:
            raise ValueError(f"{kind}: FROM must be <= TO.")
        return filters.FilterCondition(
            kind=kind, polarity=polarity, lo=lo_raw, hi=hi_raw,
        )


class FilterEditor(ttk.Frame):
    """Reusable stacked-filter editor (GUI rework Phase 4) — the UI
    half of [Shared Filter Framework](painter/filters.md): zero or
    more removable condition rows, an "+ Add condition" button, and a
    PRESET row (save / load / delete a NAMED condition stack). Stacked
    conditions AND together (``painter.filters.matches``, owner
    decision 2026-07-21) — an empty stack matches everything.

    Public API: ``get_conditions() -> list[FilterCondition]`` (raises
    ``ValueError`` — see ``_FilterConditionRow.to_condition`` — on an
    unparsable row; never returns a partial/best-effort list) and
    ``set_conditions(conditions)`` (rebuilds the row stack from
    scratch).

    Presets are a SHARED library (one settings.json key, every
    FilterEditor instance reads/writes the same names) — optional
    dependency injection, not a hard requirement: pass the owner's
    live ``presets`` dict (mutated IN PLACE by Save/Delete — the
    caller's own reference sees the change immediately) and an
    ``on_presets_changed`` callback to persist through it (e.g.
    ``PainterGui._schedule_save``, mirroring every other "remembered
    choice" setter). Omitted, the widget still works standalone (a
    private in-memory dict for the widget's own lifetime) — this is
    what makes a headless construction in a test possible with no
    PainterGui or settings.json involved at all."""

    def __init__(
        self,
        parent,
        conditions: list[filters.FilterCondition] | None = None,
        presets: dict[str, list[dict]] | None = None,
        on_presets_changed: Callable[[], None] | None = None,
        **kwargs,
    ):
        super().__init__(parent, **kwargs)
        self._presets = presets if presets is not None else {}
        self._on_presets_changed = on_presets_changed
        self._rows: list[_FilterConditionRow] = []

        self._rows_box = ttk.Frame(self)
        self._rows_box.pack(fill="x")

        add_row = ttk.Frame(self)
        add_row.pack(fill="x", pady=(FILTER_ROW_GAP_PX, 0))
        rounded_button(
            add_row, "+ Add condition", command=self._add_default_row,
            icon_name="add", kind="secondary-outline",
        ).pack(side="left")

        preset_row = ttk.Frame(self)
        preset_row.pack(fill="x", pady=(FILTER_ROW_GAP_PX, 0))
        ttk.Label(preset_row, text="Preset").pack(side="left", padx=(0, 6))
        self._preset_var = tk.StringVar(value="")
        self._preset_combo = rounded_combo(
            preset_row, sorted(self._presets), self._preset_var,
            width=FILTER_PRESET_COMBO_W, state="normal",
        )
        self._preset_combo.pack(side="left", padx=(0, 6))
        rounded_button(
            preset_row, "Save", command=self._save_preset, kind="success",
        ).pack(side="left", padx=(0, 4))
        rounded_button(
            preset_row, "Load", command=self._load_preset, kind="info",
        ).pack(side="left", padx=(0, 4))
        rounded_button(
            preset_row, "Delete", command=self._delete_preset,
            kind="danger-outline",
        ).pack(side="left")

        for c in (conditions or []):
            self._add_row(c)

    # --- rows ------------------------------------------------------

    def _add_default_row(self) -> None:
        """The "+ Add condition" button's command — a fresh row seeded
        with the ~square aspect-range band, the same default the OLD
        single-filter dialog pre-filled (owner 2026-07-19)."""
        self._add_row(filters.FilterCondition(
            kind=FILTER_KIND_ASPECT_RANGE, polarity=FILTER_POLARITY_IF,
            lo=ASPECT_FILTER_DEFAULT_FROM, hi=ASPECT_FILTER_DEFAULT_TO,
        ))

    def _add_row(self, condition: filters.FilterCondition) -> None:
        row = _FilterConditionRow(self._rows_box, condition, self._remove_row)
        row.pack(fill="x", pady=(0, FILTER_ROW_GAP_PX))
        self._rows.append(row)

    def _remove_row(self, row: _FilterConditionRow) -> None:
        self._rows.remove(row)
        row.destroy()

    # --- public API ------------------------------------------------

    def get_conditions(self) -> list[filters.FilterCondition]:
        return [row.to_condition() for row in self._rows]

    def set_conditions(self, conditions: list[filters.FilterCondition]) -> None:
        for row in self._rows:
            row.destroy()
        self._rows.clear()
        for c in conditions:
            self._add_row(c)

    # --- presets -----------------------------------------------------

    def _save_preset(self) -> None:
        name = self._preset_var.get().strip()
        if not name:
            messagebox.showerror(
                "PromptPainter", "Enter a preset name first.", parent=self,
            )
            return
        try:
            conditions = self.get_conditions()
        except ValueError as exc:
            messagebox.showerror("PromptPainter", str(exc), parent=self)
            return
        self._presets[name] = [
            filters.condition_to_dict(c) for c in conditions
        ]
        self._refresh_preset_values()
        if self._on_presets_changed is not None:
            self._on_presets_changed()

    def _load_preset(self) -> None:
        name = self._preset_var.get().strip()
        if name not in self._presets:
            messagebox.showerror(
                "PromptPainter", f"No saved preset named {name!r}.",
                parent=self,
            )
            return
        self.set_conditions([
            filters.condition_from_dict(d) for d in self._presets[name]
        ])

    def _delete_preset(self) -> None:
        name = self._preset_var.get().strip()
        if name not in self._presets:
            messagebox.showerror(
                "PromptPainter", f"No saved preset named {name!r}.",
                parent=self,
            )
            return
        del self._presets[name]
        self._preset_var.set("")
        self._refresh_preset_values()
        if self._on_presets_changed is not None:
            self._on_presets_changed()

    def _refresh_preset_values(self) -> None:
        self._preset_combo.configure(values=sorted(self._presets))
