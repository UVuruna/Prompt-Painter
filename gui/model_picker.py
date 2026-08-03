"""``ModelPickerRow`` — one purpose's Gemini-model picker (faza 4,
owner 2026-08-03, UV tačka 5: "podešavanje za TEXT GEN i IMAGE CHECK
treba da bude tamo ko to KORISTI").

The reusable "Refresh models → capable dropdown → curated hint →
persist the pick" row: the AI Check panel hosts the VISION purpose,
the New Collection (AI) panel the TEXT purpose. The API panel keeps
its own specialized Image picker (it composes with the access gate
and the "show all (debug)" switch — documented divergence, see
gui/__about/api_panel.md).

Behaviorally identical to the API panel's F5 plumbing: discovery runs
on a background thread (private queue + ``self.after`` poll — this is
a plain Frame, not the ``_AiDialog`` Toplevel that owns ITS loop);
the dropdown lists only ``purpose``-CAPABLE models; the combo
preselects via ``CTkComboBox.set()`` (which does NOT fire
``command``), so only a GENUINE user pick persists to settings.json's
``MODELS_SETTING``; every pick refreshes the curated one-line hint
(``config.model_hint`` — honest UNKNOWN for anything uncurated). The
hint seeds at build from ``model_for(purpose)`` so the row is honest
before any discovery.
"""

from __future__ import annotations

import queue
import threading
import tkinter as tk
from functools import partial
from tkinter import ttk

import customtkinter as ctk

from .widgets import rounded_button, rounded_combo

MODEL_PICKER_POLL_MS = 150   # worker-queue poll cadence (ms)
MODEL_PICKER_WRAP_PX = 430   # hint/status label wraplength


class ModelPickerRow(ttk.Frame):
    """See the module docstring. Public surface: ``model_var`` (the
    picked name — informational; the actual run always resolves via
    ``ai.model_for(purpose)``, which reads the SAME settings override
    this row writes)."""

    def __init__(self, parent, purpose: str, label: str):
        super().__init__(parent)
        self._purpose = purpose
        self._q: queue.Queue = queue.Queue()
        self._poll_job: str | None = None
        self._discovered: list[dict] = []

        row = ttk.Frame(self)
        row.pack(fill="x", pady=(0, 2))
        self._refresh_btn = rounded_button(
            row, "Refresh models", command=self._refresh, kind="info",
        )
        self._refresh_btn.pack(side="left")
        ttk.Label(row, text=f"{label}:").pack(side="left", padx=(10, 0))
        self.model_var = tk.StringVar(value="")
        self._combo: ctk.CTkComboBox = rounded_combo(
            row, (), self.model_var, width=200, state="disabled",
            command=partial(self._on_pick),
        )
        self._combo.pack(side="left", padx=(2, 8))
        self._status_var = tk.StringVar(value="")
        ttk.Label(
            row, textvariable=self._status_var, style="Muted.TLabel",
        ).pack(side="left")

        self._hint_var = tk.StringVar(value="")
        ttk.Label(
            self, textvariable=self._hint_var, style="Muted.TLabel",
            wraplength=MODEL_PICKER_WRAP_PX, justify="left",
        ).pack(anchor="w")
        self._update_hint(self._current_model())

    # --- discovery ------------------------------------------------------

    def _refresh(self) -> None:
        self._refresh_btn.configure(state="disabled")
        self._status_var.set("Discovering models …")

        def work() -> None:
            from painter import ai

            try:
                models = ai.list_models()
            except ai.AiError as exc:
                self._q.put(("error", str(exc)))
            else:
                self._q.put(("ok", models))

        threading.Thread(target=work, daemon=True).start()
        self._arm_poll()

    def _arm_poll(self) -> None:
        self._poll_job = self.after(MODEL_PICKER_POLL_MS, self._poll)

    def _poll(self) -> None:
        self._poll_job = None
        if not self.winfo_exists():
            return  # host closed mid-discovery
        try:
            msg = self._q.get_nowait()
        except queue.Empty:
            self._arm_poll()
            return
        self._apply_result(msg)

    def _apply_result(self, msg: tuple) -> None:
        self._refresh_btn.configure(state="normal")
        kind, payload = msg
        if kind == "error":
            self._status_var.set(payload)
            return
        self._discovered = payload
        self._status_var.set(f"{len(payload)} model(s).")
        self._populate()

    def _populate(self) -> None:
        from painter import ai
        from painter.config import MODELS_SETTING
        from painter.settings import load_settings

        overrides = load_settings().get(MODELS_SETTING) or {}
        names = [
            m["name"]
            for m in ai.capable_models(self._discovered, self._purpose)
        ]
        self._combo.configure(
            values=names, state="readonly" if names else "disabled",
        )
        override = str(overrides.get(self._purpose, "") or "").strip()
        pick = (
            override if override in names
            else ai.recommend_model(self._discovered, self._purpose)
        )
        if pick:
            self._combo.set(pick)
            self._update_hint(pick)

    # --- the pick -------------------------------------------------------

    def _on_pick(self, choice: str) -> None:
        """A GENUINE user selection — persist IMMEDIATELY (the next AI
        call resolves through ``model_for``, which reads this)."""
        from painter.config import MODELS_SETTING
        from painter.settings import load_settings, save_settings

        settings = load_settings()
        models = dict(settings.get(MODELS_SETTING) or {})
        models[self._purpose] = choice
        settings[MODELS_SETTING] = models
        save_settings(settings)
        self._update_hint(choice)

    def _current_model(self) -> str:
        from painter import ai

        try:
            return ai.model_for(self._purpose)
        except Exception:  # a broken settings.json must not kill build
            return ""

    def _update_hint(self, name: str) -> None:
        from painter.config import model_hint

        self._hint_var.set(model_hint(name) if name else "")
