"""``SheetGenPanel`` — New Collection (AI) as a REAL setup panel
(faza 4, owner 2026-08-03, UV/prompt.txt tačka 4 + predlog P2=A: the
wizard ① Zahtev → ② Pitanja → ③ Draft & Save, replacing the old
``AiSheetDialog`` popup).

Menu-hosted exactly like the ``ToolSettingsPanel`` family
(``PainterGui._tool_panels["ai_sheet_gen"]``, reached via
``_open_tool_panel``): LEFT = the SETUP that stays visible through
every step (the request text, where the ``.md`` saves, the TEXT-GEN
model picker — moved HERE from the API panel per the owner's "tamo ko
to KORISTI" — and **Ask questions**); RIGHT = the working surface the
steps drive (② the model's clarifying questions, each with its answer
entry; ③ the draft sheet, EDITABLE, with Regenerate / Save / Save +
queue).

The engine is unchanged (``painter.ai``: ``contract_text`` /
``ask_questions`` / ``generate_sheet`` / ``save_sheet`` — the same
two-call flow + one automatic repair round the dialog drove); workers
run on background threads with the private queue + ``self.after``
poll convention every non-Toplevel AI surface here uses. ③'s draft
box is editable ON PURPOSE: **Save re-validates whatever is in the
box with the REAL parser** — a draft that still fails the contract
lists its problems in the status line and is NOT saved (the owner
fixes it right there, no DocWindow detour); a clean save lands under
the picked folder (slugged theme name) and "Save + Add to queue" also
queues it into the ONE shared Collections queue (faza 3 unified the
website/API queues, so the owner's "Website or API?" question answers
itself — both hosts see it).

"Add to queue" gating and the Gemini-key gate both live on the ACTION
(Ask questions checks ``gui._ensure_ai_key()`` at click time), never
on merely opening the panel.
"""

from __future__ import annotations

import queue
import threading
import tkinter as tk
from pathlib import Path
from tkinter import filedialog, messagebox, ttk

import customtkinter as ctk

from painter.config import SHEETS_DIR, theme_pair
from .icons import icon
from .model_picker import ModelPickerRow
from .theme import skin_text
from .widgets import rounded_button, rounded_entry, tk_font

SHEETGEN_POLL_MS = 150     # worker-queue poll cadence (ms)
SHEETGEN_WRAP_PX = 430     # status/question wraplength
SHEETGEN_REQUEST_LINES = 4
SHEETGEN_DRAFT_LINES = 16

_STEPS = ("① Zahtev", "② Pitanja", "③ Draft & Save")


class SheetGenPanel(ttk.Frame):
    """See the module docstring. ``gui`` is the PainterGui host
    (duck-typed: ``_ensure_ai_key``, ``_q`` log queue,
    ``add_generated_sheet``, ``_scroll.refresh``)."""

    def __init__(self, master, gui):
        super().__init__(master, padding=8)
        self._gui = gui
        self._q: queue.Queue = queue.Queue()
        self._poll_job: str | None = None
        self._busy = False
        self._request = ""
        self._contract = ""
        self._questions: list[str] = []
        self._answer_vars: list[tk.StringVar] = []
        self._theme = None  # the parsed draft's theme (for save_sheet)

        head = ttk.Frame(self)
        head.pack(fill="x")
        ctk.CTkLabel(
            head, text="", image=icon("sheetgen"), width=22,
            fg_color="transparent", bg_color=theme_pair("bg"),
        ).pack(side="left", padx=(0, 4))
        ttk.Label(
            head, text="New collection (AI) — setup", style="Head.TLabel",
        ).pack(side="left")
        # the wizard's step indicator — the CURRENT step reads accented
        self._step_labels: list[ttk.Label] = []
        steps = ttk.Frame(head)
        steps.pack(side="right")
        for i, text in enumerate(_STEPS):
            if i:
                ttk.Label(steps, text="  →  ", style="Muted.TLabel").pack(
                    side="left"
                )
            lbl = ttk.Label(steps, text=text, style="Muted.TLabel")
            lbl.pack(side="left")
            self._step_labels.append(lbl)

        body = ttk.Frame(self)
        body.pack(fill="both", expand=True, pady=(6, 0))
        body.columnconfigure(0, weight=1, uniform="sheetgencol")
        body.columnconfigure(1, weight=1, uniform="sheetgencol")
        body.rowconfigure(0, weight=1)
        left = ttk.Frame(body)
        left.grid(row=0, column=0, sticky="new")
        right = ttk.Frame(body)
        right.grid(row=0, column=1, sticky="nsew", padx=(16, 0))

        # --- LEFT: the SETUP (visible through every step) --------------
        ttk.Label(
            left, text="What should the new collection generate?",
            style="Head.TLabel",
        ).pack(anchor="w")
        ttk.Label(
            left,
            text=(
                'e.g. "Napravi mi 12 slika Astrologije" — any language;'
                " the model first asks its clarifying questions, then"
                " writes the sheet per the contract."
            ),
            style="Muted.TLabel", wraplength=SHEETGEN_WRAP_PX,
            justify="left",
        ).pack(anchor="w", pady=(0, 4))
        self._request_txt = tk.Text(
            left, height=SHEETGEN_REQUEST_LINES, wrap="word",
            font=tk_font("root"), width=1,
        )
        skin_text(self._request_txt)
        self._request_txt.pack(fill="x")

        row = ttk.Frame(left)
        row.pack(fill="x", pady=(6, 2))
        ttk.Label(row, text="Save to:", width=8).pack(side="left")
        self.save_dir_var = tk.StringVar(value=str(SHEETS_DIR))
        rounded_entry(row, textvariable=self.save_dir_var).pack(
            side="left", fill="x", expand=True
        )
        rounded_button(row, "Browse…", icon_name="browse", command=self._pick_save_dir).pack(
            side="left", padx=(8, 0)
        )

        ttk.Label(
            left, text="Text model (sheet drafting)", style="Head.TLabel",
        ).pack(anchor="w", pady=(8, 2))
        self.model_picker = ModelPickerRow(left, "text", "Text")
        self.model_picker.pack(fill="x")

        self._status_var = tk.StringVar(value="")
        ttk.Label(
            left, textvariable=self._status_var, style="Muted.TLabel",
            wraplength=SHEETGEN_WRAP_PX, justify="left",
        ).pack(anchor="w", pady=(8, 4))
        self._ask_btn = rounded_button(
            left, "Ask questions", command=self._ask, kind="success",
            # step ① -> ②: this button MOVES the wizard on, so it wears
            # the nav arrow — "sheetgen" belongs to the one button that
            # actually produces the sheet (owner 2026-08-04)
            icon_name="next",
        )
        self._ask_btn.pack(anchor="w", pady=(2, 0))

        # --- RIGHT: the working surface (steps ② and ③) ----------------
        self._questions_box = ttk.Frame(right)   # step ② — built on demand
        self._draft_box = ttk.Frame(right)       # step ③ — built once below
        ttk.Label(
            self._draft_box,
            text="Draft sheet (editable — Save re-validates it):",
            style="Head.TLabel",
        ).pack(anchor="w", pady=(0, 2))
        self._draft_txt = tk.Text(
            self._draft_box, height=SHEETGEN_DRAFT_LINES, wrap="none",
            font=tk_font("mono"), width=1,
        )
        skin_text(self._draft_txt)
        self._draft_txt.pack(fill="both", expand=True)
        btns = ttk.Frame(self._draft_box)
        btns.pack(fill="x", pady=(6, 0))
        rounded_button(
            btns, "Regenerate", icon_name="refresh", command=self._generate, kind="info",
        ).pack(side="left")
        rounded_button(
            btns, "Save .md", icon_name="save", command=lambda: self._save(queue_it=False),
        ).pack(side="left", padx=8)
        rounded_button(
            btns, "Save + Add to queue",
            icon_name="add", command=lambda: self._save(queue_it=True), kind="success",
        ).pack(side="left")

        self._set_step(0)

    # --- small helpers --------------------------------------------------

    def _set_step(self, index: int) -> None:
        for i, lbl in enumerate(self._step_labels):
            lbl.configure(
                style="Head.TLabel" if i == index else "Muted.TLabel"
            )

    def _pick_save_dir(self) -> None:
        folder = filedialog.askdirectory(title="Where the .md saves")
        if folder:
            self.save_dir_var.set(folder)

    def _log(self, msg: str) -> None:
        self._gui._q.put(f"[AI sheet] {msg}")

    def _set_busy(self, text: str) -> None:
        self._busy = True
        self._ask_btn.configure(state="disabled")
        self._status_var.set(text)

    def _set_idle(self, text: str) -> None:
        self._busy = False
        self._ask_btn.configure(state="normal")
        self._status_var.set(text)

    def _arm_poll(self) -> None:
        self._poll_job = self.after(SHEETGEN_POLL_MS, self._poll)

    def _poll(self) -> None:
        self._poll_job = None
        if not self.winfo_exists():
            return
        try:
            msg = self._q.get_nowait()
        except queue.Empty:
            self._arm_poll()
            return
        self._on_message(msg)

    # --- step ①: the request → the clarifying questions -----------------

    def _ask(self) -> None:
        if self._busy:
            return
        if not self._gui._ensure_ai_key():
            return
        request = self._request_txt.get("1.0", "end").strip()
        if not request:
            messagebox.showerror(
                "PromptPainter",
                "Type what the collection should be first.",
                parent=self.winfo_toplevel(),
            )
            return
        self._request = request
        self._log(f"request: {request[:80]}")
        self._set_busy("asking the model for its clarifying questions …")

        def work():
            from painter import ai

            try:
                contract = ai.contract_text()
                questions = ai.ask_questions(request, contract)
                self._q.put(("questions", contract, questions))
            except (ai.AiError, OSError) as exc:
                self._q.put(("error", str(exc)))

        threading.Thread(target=work, daemon=True).start()
        self._arm_poll()

    def _show_questions(self, questions: list[str]) -> None:
        self._set_step(1)
        for child in self._questions_box.winfo_children():
            child.destroy()
        self._answer_vars = []
        self._questions = questions
        ttk.Label(
            self._questions_box,
            text="The model asks (answers optional — empty = its choice):",
            style="Head.TLabel",
        ).pack(anchor="w", pady=(0, 4))
        for question in questions:
            row = ttk.Frame(self._questions_box)
            row.pack(fill="x", pady=2)
            ttk.Label(
                row, text=question, wraplength=SHEETGEN_WRAP_PX,
                justify="left",
            ).pack(anchor="w")
            var = tk.StringVar(value="")
            rounded_entry(row, textvariable=var).pack(fill="x", pady=(1, 0))
            self._answer_vars.append(var)
        rounded_button(
            self._questions_box, "Generate sheet", command=self._generate,
            kind="success", icon_name="sheetgen",
        ).pack(anchor="w", pady=(6, 0))
        self._draft_box.pack_forget()
        self._questions_box.pack(fill="x")
        # the ASK worker is finished — clear busy here (owner 2026-08-04:
        # "Generate sheet" did nothing, because _busy was still True from
        # _ask and _generate's first line returns on it)
        self._set_idle(
            "Answer what you care about (empty = the model's choice),"
            " then Generate sheet."
        )
        self._gui._scroll.refresh()

    # --- step ②→③: generate + preview -----------------------------------

    def _generate(self) -> None:
        if self._busy:
            return
        answers = [var.get() for var in self._answer_vars]
        request, contract = self._request, self._contract
        questions = self._questions
        self._set_busy(
            "generating the sheet (validated with the real parser; one"
            " automatic repair round if needed) …"
        )

        def work():
            import tempfile

            from painter import ai

            try:
                with tempfile.TemporaryDirectory(prefix="painter_ai_") as tmp:
                    md, problems, theme = ai.generate_sheet(
                        request, questions, answers, contract,
                        Path(tmp), log=self._log,
                    )
                self._q.put(("sheet", md, problems, theme))
            except ai.AiError as exc:
                self._q.put(("error", str(exc)))

        threading.Thread(target=work, daemon=True).start()
        self._arm_poll()

    def _show_draft(self, md: str, problems: list[str], theme) -> None:
        self._set_step(2)
        self._theme = theme
        self._draft_txt.delete("1.0", "end")
        self._draft_txt.insert("1.0", md)
        self._questions_box.pack_forget()
        self._draft_box.pack(fill="both", expand=True)
        if problems:
            for problem in problems:
                self._log(f"PROBLEM: {problem}")
            self._set_idle(
                f"{len(problems)} contract problem(s) — listed in the"
                " Log; fix the draft here (or answer differently and"
                " Regenerate), then Save."
            )
        else:
            self._set_idle("Draft is contract-clean — review, then Save.")
        self._gui._scroll.refresh()

    def _on_message(self, msg: tuple) -> None:
        kind = msg[0]
        if kind == "error":
            self._log(f"ERROR: {msg[1]}")
            self._set_idle(f"ERROR: {msg[1]}")
        elif kind == "questions":
            _kind, self._contract, questions = msg
            if questions:
                self._log(f"{len(questions)} clarifying question(s)")
                self._show_questions(questions)
            else:
                self._log("the model asked no questions — generating directly")
                self._set_idle("")
                self._generate()
        elif kind == "sheet":
            self._show_draft(md=msg[1], problems=msg[2], theme=msg[3])

    # --- step ③: validate whatever is in the box, save, maybe queue -----

    def _save(self, queue_it: bool) -> None:
        """Re-validate the (possibly hand-edited) draft with the REAL
        parser; problems block the save loudly. A clean sheet saves
        under the picked folder (slugged theme) and optionally joins
        the ONE shared Collections queue."""
        import tempfile

        from painter import ai
        from painter.sheet_parser import SheetError, parse_sheet

        md = self._draft_txt.get("1.0", "end").strip() + "\n"
        if not md.strip():
            self._set_idle("Nothing to save — the draft box is empty.")
            return
        with tempfile.TemporaryDirectory(prefix="painter_ai_") as tmp:
            probe = Path(tmp) / "draft.md"
            probe.write_text(md, encoding="utf-8")
            try:
                sheet = parse_sheet(probe)
            except SheetError as exc:
                self._set_idle(f"NOT SAVED — {exc}")
                return
        if sheet.problems:
            for problem in sheet.problems:
                self._log(f"PROBLEM: {problem.message} (L{problem.line})")
            self._set_idle(
                f"NOT SAVED — {len(sheet.problems)} contract problem(s),"
                " listed in the Log."
            )
            return
        save_dir = Path(
            self.save_dir_var.get().strip() or str(SHEETS_DIR)
        )
        path = ai.save_sheet(md, sheet.theme, save_dir)
        self._log(f"saved {path}")
        if queue_it:
            self._gui.add_generated_sheet(path)
            self._log("added to the Collections queue")
            self._set_idle(f"Saved {path.name} + queued.")
        else:
            self._set_idle(f"Saved {path.name}.")

    # --- the generic tool_panels settings round-trip ---------------------

    def get_settings(self) -> dict:
        return {"save_dir": self.save_dir_var.get()}

    def apply_settings(self, stored: dict, conditions=None) -> None:
        if "save_dir" in stored:
            self.save_dir_var.set(stored["save_dir"])
