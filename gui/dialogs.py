"""Modal dialogs pulled out of ``gui/__init__.py`` (root Rule #20
god-file refactor): ``_ModalToolDialog`` (shared centre-on-parent
placement), ``_AiDialog`` (the worker-queue poll loop shared by the AI
dialogs), ``AiKeyWizard`` (the guided Gemini-API-key onboarding) and
``AiSheetDialog`` ('New collection (AI)…').

``AI_POLL_MS`` (the AI-dialog worker-queue poll cadence) moves HERE
with ``_AiDialog`` — the class that owns the poll loop it paces. It is
re-exported from ``gui/__init__.py`` so ``gui.AI_POLL_MS`` keeps
resolving for ``gui.api_panel``'s deferred ``import gui`` (its
``ApiImageGenPanel._arm_probe_poll``) and for ``gui.viewers.DocWindow``'s
own unrelated Fixer poll (``_arm_fix_poll``) — both reach it the same
late-binding way rather than a real-path import, since a real-path
import from ``gui.viewers`` back to this module would be circular
(this module imports ``DocWindow`` from ``gui.viewers`` for
``AiSheetDialog._finish``'s "not loaded" viewer)."""

from __future__ import annotations

import queue
import threading
import tkinter as tk
import webbrowser
from pathlib import Path
from tkinter import messagebox, ttk

import ttkbootstrap as tb

from painter.config import AI_STUDIO_URL, AI_TEST_PROMPT, SHEETS_DIR
from .theme import THEME_TOPLEVELS, skin_text, skin_toplevel
from .viewers import DocWindow
from .widgets import rounded_button, rounded_entry, status, tk_font

# --- Aspect-ratio prompt (the standalone 'Aspect ratio…' tool) -------
ASPECT_DIALOG_PAD_PX = 16   # padding around the ratio dialog body

# --- AI dialogs: key wizard / sheet generator (Rule #4) ---------------
AI_KEY_ENTRY_W = 380        # the wizard's key entry width (px)
AI_STATUS_WRAP_PX = 460     # AI dialog status / question label wraplength
AI_REQUEST_LINES = 4        # the request Text height (lines)
AI_STEP_INDENT_PX = 28      # wizard body indent under the numbered steps
AI_POLL_MS = 150            # AI dialog worker-queue poll cadence (ms)


class _ModalToolDialog(tk.Toplevel):
    """Shared plumbing for a small themed modal dialog: the centre-on-
    parent placement (``_center_on``). Historically shared by the
    standalone Upscale/Aspect tool dialogs too (both retired, GUI
    rework Phase 14 — replaced by ``UpscaleSettingsPanel``/
    ``AspectSettingsPanel``); today's only family is ``_AiDialog``
    (the key wizard, the sheet generator) — kept as its own base
    rather than folded into ``_AiDialog`` directly (Rule #5: a future
    non-AI modal dialog can still reuse just the placement math)."""

    def _center_on(self, master) -> None:
        """Place the dialog over the middle-upper third of the parent."""
        master.update_idletasks()
        x = master.winfo_rootx() + (master.winfo_width() - self.winfo_reqwidth()) // 2
        y = master.winfo_rooty() + (master.winfo_height() - self.winfo_reqheight()) // 3
        self.geometry(f"+{max(x, 0)}+{max(y, 0)}")


class _AiDialog(_ModalToolDialog):
    """Shared plumbing of the AI dialogs (key wizard, sheet generator):
    a worker→UI queue polled on the tk loop — the worker threads ONLY
    ``self._q.put(...)`` and never touch a widget; ``_on_message``
    applies each message on the main thread. The poll dies quietly with
    the window (Rule #5 — one home for the identical loop)."""

    def _init_ai_queue(self) -> None:
        self._q: queue.Queue = queue.Queue()
        self._poll_job: str | None = None

    def _arm_poll(self) -> None:
        self._poll_job = self.after(AI_POLL_MS, self._poll)

    def _poll(self) -> None:
        self._poll_job = None
        if not self.winfo_exists():
            return  # closed mid-work — the worker's message is moot
        try:
            msg = self._q.get_nowait()
        except queue.Empty:
            self._arm_poll()
            return
        self._on_message(msg)

    def _on_message(self, msg: tuple) -> None:
        raise NotImplementedError  # each dialog applies its own messages


class AiKeyWizard(_AiDialog):
    """The guided Gemini-API-key onboarding (owner 2026-07-20): four
    numbered steps that STEER the user — open AI Studio in the browser,
    sign in with any Google account, create the key, paste it — plus a
    **Test key** that makes one tiny real call and shows OK / the loud
    error, and **Save key** persisting it to settings.json. Opened by
    the toolbar's 'AI key…' button and AUTOMATICALLY whenever an AI
    feature is invoked without a key (``NoKey``)."""

    def __init__(self, master, gui: "PainterGui"):
        super().__init__(master)
        self.title("Gemini API key — guided setup")
        self.resizable(False, False)
        skin_toplevel(self)  # bg registered so a flip re-tints the window
        self._gui = gui
        self._init_ai_queue()

        body = ttk.Frame(self, padding=ASPECT_DIALOG_PAD_PX)
        body.pack(fill="both", expand=True)
        ttk.Label(
            body, text="Get a FREE Gemini API key", style="Head.TLabel",
        ).pack(anchor="w")
        ttk.Label(
            body,
            text=(
                "The AI features (New collection, AI check) need it —"
                " a one-time setup."
            ),
            style="Muted.TLabel", wraplength=AI_STATUS_WRAP_PX,
        ).pack(anchor="w", pady=(0, 10))

        step = ttk.Frame(body)
        step.pack(fill="x", pady=2)
        ttk.Label(step, text="1.", width=3, style="Value.TLabel").pack(
            side="left"
        )
        rounded_button(
            step, "Open aistudio.google.com", command=self._open_browser,
            kind="info", icon_name="web",
        ).pack(side="left")
        for number, text in (
            ("2.", "Sign in with ANY Google account."),
            ("3.", "Press  Get API key  →  Create API key."),
            ("4.", "Copy the key and paste it below:"),
        ):
            row = ttk.Frame(body)
            row.pack(fill="x", pady=2)
            ttk.Label(row, text=number, width=3, style="Value.TLabel").pack(
                side="left"
            )
            ttk.Label(row, text=text).pack(side="left")

        self._key_var = tk.StringVar(value=gui.gemini_key)
        self._entry = rounded_entry(
            body, width=AI_KEY_ENTRY_W, textvariable=self._key_var,
        )
        self._entry.pack(fill="x", pady=(4, 8), padx=(AI_STEP_INDENT_PX, 0))

        self._status_var = tk.StringVar(value="")
        self._status_lbl = ttk.Label(
            body, textvariable=self._status_var,
            wraplength=AI_STATUS_WRAP_PX, justify="left",
        )
        self._status_lbl.pack(
            anchor="w", pady=(0, 6), padx=(AI_STEP_INDENT_PX, 0)
        )

        btns = ttk.Frame(body)
        btns.pack(fill="x", pady=(6, 0))
        rounded_button(
            btns, "Save key", command=self._save, kind="success",
        ).pack(side="right")
        self._test_btn = rounded_button(
            btns, "Test key", command=self._test, kind="info",
        )
        self._test_btn.pack(side="right", padx=6)
        rounded_button(btns, "Cancel", command=self.destroy).pack(
            side="right", padx=(0, 6)
        )

        self.bind("<Escape>", lambda _e: self.destroy())
        self.update_idletasks()
        self._center_on(master)
        self.transient(master)
        self.grab_set()
        self._entry.focus_set()
        self.wait_window(self)

    def _open_browser(self) -> None:
        webbrowser.open(AI_STUDIO_URL)

    def _show_status(self, kind: str, text: str) -> None:
        colors = {
            "ok": status("done"),
            "err": status("superseded"),
            "info": tb.Style().colors.light,
        }
        self._status_lbl.configure(foreground=colors[kind])
        self._status_var.set(text)

    def _test(self) -> None:
        """One tiny REAL call with the pasted key — OK or the loud
        error, on a worker thread so the dialog never blocks."""
        key = self._key_var.get().strip()
        if not key:
            self._show_status("err", "Paste the key first (step 4).")
            return
        self._test_btn.configure(state="disabled")
        self._show_status("info", "testing — one tiny API call …")

        def work():
            from painter import ai

            try:
                answer = ai.generate_text(AI_TEST_PROMPT, key=key)
                self._q.put(
                    ("ok",
                     f"OK — the key works (answered: {answer.strip()[:40]!r})")
                )
            except ai.AiError as exc:
                self._q.put(("err", str(exc)))

        threading.Thread(target=work, daemon=True).start()
        self._arm_poll()

    def _on_message(self, msg: tuple) -> None:
        kind, text = msg
        self._test_btn.configure(state="normal")
        self._show_status(kind, text)

    def _save(self) -> None:
        key = self._key_var.get().strip()
        if not key:
            messagebox.showerror(
                "PromptPainter", "Paste the key first (step 4).",
                parent=self,
            )
            return
        self._gui.set_gemini_key(key)
        self.destroy()


class AiSheetDialog(_AiDialog):
    """'New collection (AI)…' (owner 2026-07-20). Phase 1: the owner
    types the request (any language); the FIRST call returns a short
    clarifying POLL (the contract + questions-only system prompt).
    Phase 2: the answers (each skippable) feed the SECOND call, whose
    ``.md`` is validated with the REAL parser plus ONE automatic repair
    round. Valid → saved under ``sheets/`` (slugged name) and ADDED to
    the Collections queue; still broken → the raw md opens in a
    DocWindow for manual fixing and is NOT loaded. Both calls run on
    worker threads; progress lands in the status line + the main Log.
    Non-modal (registered in ``THEME_TOPLEVELS``) so a long generation
    never grabs the app."""

    def __init__(self, master, gui: "PainterGui"):
        super().__init__(master)
        self.title("New collection (AI)")
        self.resizable(False, False)
        skin_toplevel(self)  # bg registered so a flip re-tints the window
        THEME_TOPLEVELS.append(self)
        self._gui = gui
        self._init_ai_queue()
        self._busy = False
        self._request = ""
        self._contract = ""
        self._questions: list[str] = []
        self._answer_vars: list[tk.StringVar] = []

        body = ttk.Frame(self, padding=ASPECT_DIALOG_PAD_PX)
        body.pack(fill="both", expand=True)

        # --- phase 1: the request --------------------------------------
        self._req_box = ttk.Frame(body)
        self._req_box.pack(fill="x")
        ttk.Label(
            self._req_box, text="What should the new collection generate?",
            style="Head.TLabel",
        ).pack(anchor="w")
        ttk.Label(
            self._req_box,
            text=(
                'e.g. "Napravi mi 12 slika Astrologije" — any language;'
                " the model first asks its clarifying questions, then"
                " writes the sheet per the contract."
            ),
            style="Muted.TLabel", wraplength=AI_STATUS_WRAP_PX,
            justify="left",
        ).pack(anchor="w", pady=(0, 6))
        self._request_txt = tk.Text(
            self._req_box, height=AI_REQUEST_LINES, wrap="word",
            font=tk_font("root"), width=1,  # the pack fill sets the width
        )
        skin_text(self._request_txt)
        self._request_txt.pack(fill="x")

        # --- phase 2: the poll (filled when the questions arrive) ------
        self._poll_box = ttk.Frame(body)

        self._status_var = tk.StringVar(value="")
        ttk.Label(
            body, textvariable=self._status_var, style="Muted.TLabel",
            wraplength=AI_STATUS_WRAP_PX, justify="left",
        ).pack(anchor="w", pady=(8, 4))

        btns = ttk.Frame(body)
        btns.pack(fill="x", pady=(4, 0))
        self._go_btn = rounded_button(
            btns, "Ask questions", command=self._ask, kind="success",
            icon_name="ai",
        )
        self._go_btn.pack(side="right")
        rounded_button(btns, "Cancel", command=self.destroy).pack(
            side="right", padx=6
        )

        self.bind("<Escape>", lambda _e: self.destroy())
        self.bind("<Destroy>", self._on_destroy)
        self.update_idletasks()
        self.minsize(
            max(self.winfo_reqwidth(), AI_STATUS_WRAP_PX + 60), 0
        )
        self._center_on(master)
        self.transient(master)
        self._request_txt.focus_set()

    def apply_theme(self) -> None:
        # ttk children flip via styles; the Text and entries ride the
        # global recolour — nothing per-widget to redo here.
        pass

    def _on_destroy(self, event) -> None:
        if event.widget is self and self in THEME_TOPLEVELS:
            THEME_TOPLEVELS.remove(self)

    # --- phase transitions (main thread) --------------------------------

    def _set_busy(self, text: str) -> None:
        self._busy = True
        self._go_btn.configure(state="disabled")
        self._status_var.set(text)

    def _set_idle(self, text: str) -> None:
        self._busy = False
        self._go_btn.configure(state="normal")
        self._status_var.set(text)

    def _ask(self) -> None:
        """FIRST call — the clarifying questions."""
        if self._busy:
            return
        request = self._request_txt.get("1.0", "end").strip()
        if not request:
            messagebox.showerror(
                "PromptPainter",
                "Type what the collection should be first.", parent=self,
            )
            return
        self._request = request
        self._gui._q.put(f"[AI sheet] request: {request[:80]}")
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
        self._questions = questions
        self._request_txt.configure(state="disabled")  # the request is set
        ttk.Label(
            self._poll_box,
            text="The model asks (answers optional — empty = its choice):",
            style="Head.TLabel",
        ).pack(anchor="w", pady=(8, 4))
        for question in questions:
            row = ttk.Frame(self._poll_box)
            row.pack(fill="x", pady=2)
            ttk.Label(
                row, text=question, wraplength=AI_STATUS_WRAP_PX,
                justify="left",
            ).pack(anchor="w")
            var = tk.StringVar(value="")
            rounded_entry(row, textvariable=var).pack(fill="x", pady=(1, 0))
            self._answer_vars.append(var)
        self._poll_box.pack(fill="x", after=self._req_box)
        self._go_btn.configure(text="Generate sheet", command=self._generate)
        self._set_idle(
            f"{len(questions)} question(s) — answer what you care about,"
            " then Generate."
        )
        self.update_idletasks()
        self._center_on(self.master)

    def _generate(self) -> None:
        """SECOND call — the sheet + validation + one repair round."""
        if self._busy:
            return
        answers = [var.get() for var in self._answer_vars]
        request, contract = self._request, self._contract
        questions = self._questions
        log = lambda msg: self._gui._q.put(f"[AI sheet] {msg}")
        self._set_busy(
            "generating the sheet (validated with the real parser; one"
            " automatic repair round if needed) …"
        )

        def work():
            import tempfile

            from painter import ai

            try:
                with tempfile.TemporaryDirectory(
                    prefix="painter_ai_"
                ) as tmp:
                    md, problems, theme = ai.generate_sheet(
                        request, questions, answers, contract,
                        Path(tmp), log=log,
                    )
                self._q.put(("sheet", md, problems, theme))
            except ai.AiError as exc:
                self._q.put(("error", str(exc)))

        threading.Thread(target=work, daemon=True).start()
        self._arm_poll()

    def _on_message(self, msg: tuple) -> None:
        kind = msg[0]
        if kind == "error":
            self._gui._log(f"[AI sheet] ERROR: {msg[1]}")
            self._set_idle(f"ERROR: {msg[1]}")
        elif kind == "questions":
            _kind, self._contract, questions = msg
            if questions:
                self._gui._q.put(
                    f"[AI sheet] {len(questions)} clarifying question(s)"
                )
                self._show_questions(questions)
            else:
                # no parseable poll — generate straight from the request
                self._gui._q.put(
                    "[AI sheet] the model asked no questions —"
                    " generating directly"
                )
                self._set_idle("")
                self._generate()
        elif kind == "sheet":
            self._finish(md=msg[1], problems=msg[2], theme=msg[3])

    def _finish(self, md: str, problems: list[str], theme) -> None:
        if problems:
            for problem in problems:
                self._gui._log(f"[AI sheet] PROBLEM: {problem}")
            self._set_idle(
                "the sheet still fails the contract after the repair"
                " round — opened for manual fixing, NOT loaded (the"
                " problems are in the Log)."
            )
            DocWindow(
                self._gui.root, "AI sheet — fix manually (not loaded)",
                md,
                hint=(
                    "This draft fails the sheet contract — Copy it, fix"
                    " it by hand, save it and Add… it to the queue."
                ),
            )
            return  # the dialog stays open — better answers may succeed
        from painter import ai

        path = ai.save_sheet(md, theme, SHEETS_DIR)
        self._gui.add_generated_sheet(path)
        self._gui._log(
            f"[AI sheet] saved {path} — added to the Collections queue"
        )
        self.destroy()
