"""``ApiImageGenPanel`` (the paid Gemini image-API job's own settings
panel) and ``ApiImageAdapter`` (a ``SiteDriver``-shaped stand-in that
lets that job reuse ``PainterGui._drive_site``/``painter.runner.
run_sheet`` unchanged).

Split out of ``gui/__init__.py`` (Rule #3, god-file refactor step
4/8). The two-column-dense layout constants (``DENSE_COL_GAP_PX``/
``DENSE_COL_WRAP_PX``/``ASPECT_DIALOG_ENTRY_W``) come from
``gui.tool_panels`` — the SAME constants the ToolSettingsPanel family
and ``AgentPanel`` already share (Rule #5); importing them from that
leaf module (rather than ``gui/__init__.py``) avoids a circular
import. ``AI_POLL_MS`` is the one exception: it stays defined in
``gui/__init__.py`` (also read by ``_AiDialog``, which never moved),
so ``_arm_probe_poll`` below reaches it through a deferred
``import gui`` instead — the same late-binding indirection
``gui.theme._pkg()`` already established for a callback that must
reach back into the still-monolithic part of the package."""

from __future__ import annotations

import queue
import threading
import tkinter as tk
from functools import partial
from tkinter import ttk
from types import SimpleNamespace
from typing import Callable

import customtkinter as ctk

from painter import filters
from painter.config import (
    AI_IMAGE_GATE_MESSAGE,
    AI_IMAGE_PROBE_PROMPT,
    ASPECT_DEFAULT_H,
    ASPECT_DEFAULT_W,
    BACKGROUND_CHOICES,
    FILTER_KIND_ASPECT_RANGE,
    FILTER_POLARITY_IF,
    GEMINI_IMAGE_MODEL,
    JOBTEMP_KEEP_ALL_STEPS_DEFAULT,
    JOB_LABEL,
    JOB_LOGO,
    STYLE_CHOICES,
    STYLE_DEFAULT,
    TIMING,
    UPSCALE_ASPECT_MAX,
    UPSCALE_ASPECT_MIN,
    UPSCALE_MINDIM_STEP,
    UPSCALE_MIN_SIDE_DEFAULT,
    theme_pair,
)
from .aspect_canvas import AspectRatioCanvas
from .filter_editor import FilterEditor
from .icons import icon
from .logic import _upscale_params_from_side_and_filter
from .theme import THEME_TOPLEVELS
from .tool_panels import ASPECT_DIALOG_ENTRY_W, DENSE_COL_GAP_PX, DENSE_COL_WRAP_PX
from .widgets import (
    Spinner,
    rounded_button,
    rounded_combo,
    rounded_entry,
    rounded_switch,
    style_action_button,
    tk_font,
)


class ApiImageGenPanel(ttk.Frame):
    """API Image GEN's persistent settings panel (GUI rework Phase 19)
    — menu-hosted exactly like the ``ToolSettingsPanel`` family
    (``PainterGui._tool_panels["api_image_gen"]``, reached the SAME way
    via ``_open_tool_panel``/``_click_icon_bar_tile``), but this panel
    does NOT subclass ``ToolSettingsPanel``: its input is the SAME
    queued ``.md`` sheet Collections list Website GEN already drives
    (``PainterGui._sheets``), never a folder of already-existing
    images, so a "Folder…/Files…" picker would be actively wrong here.
    It mirrors ``AgentPanel`` instead — background/style dropdowns
    feeding the SAME ``config.prompt_suffix`` machinery, the composable
    post-save switches (BG removal/Crop/Force Aspect Ratio/Upscale,
    see ``PainterGui._compose_post_save``, called with THIS panel
    passed explicitly since it is not one of ``self.agents``), and its
    own Start/Pause/Stop trio — while ``get_settings``/``apply_settings``
    use the SAME ``(stored, conditions=...)`` shape ``ToolSettingsPanel``
    already has, so it round-trips through the EXISTING generic
    "tool_panels" settings loop with no changes there either.

    BG/Crop/Force-Aspect/Upscale default ON — unlike ``AgentPanel``'s
    own defaults (BG/Crop/Upscale ON, Force Aspect OFF) — because the
    paid image model cannot render a REAL transparent background
    (UV/prompt.txt item 3: "ne moze TRANSPARENT pa mora BG removal i
    CROP sve redom"), so every generated image needs the full cleanup
    pipeline by default; the background dropdown defaults to "white"
    (a background the model CAN render, for BG removal to key out)
    instead of borrowing a site's own ``default_background``.

    GATING (owner decision, Phase 19 spec item 5): the owner's key has
    ZERO free-tier quota for the paid image model TODAY
    (``ai.PaidFeatureRequired``) — **Check API access** runs one cheap
    probe call on a background thread (its OWN private queue+poll,
    mirroring ``_AiDialog``'s established pattern — this panel is a
    ``ttk.Frame``, not a ``Toplevel``, so it cannot literally subclass
    that Toplevel-only base) and, when the free-tier-zero signal fires,
    disables Start with a clear message (``AI_IMAGE_GATE_MESSAGE``)
    instead of leaving the owner to discover it mid-run. This is a
    CONVENIENCE, not the only guard: a real run started without probing
    first is caught the SAME way by ``ApiImageAdapter.extract_image``
    (mapped to ``driver.TerminalState`` — the identical quota-stop
    plumbing every site already has)."""

    def __init__(
        self, master,
        on_start: Callable[[], None], on_pause: Callable[[str], None],
        on_stop: Callable[[str], None],
        filter_presets: dict[str, list[dict]] | None = None,
        on_filter_presets_changed: Callable[[], None] | None = None,
    ):
        super().__init__(master, padding=8)
        self._on_start = on_start
        self._on_pause = on_pause
        self._on_stop = on_stop
        self._filter_presets = filter_presets
        self._on_filter_presets_changed = on_filter_presets_changed
        self._running = False
        # set by a Check-API-access probe; gates Start until a probe
        # clears it again (or the app restarts) — see _apply_probe_result
        self.access_gated = False

        head = ttk.Frame(self)
        head.pack(fill="x")
        ctk.CTkLabel(
            head, text="", image=icon(JOB_LOGO["api_image"]), width=22,
            fg_color="transparent", bg_color=theme_pair("bg"),
        ).pack(side="left", padx=(0, 4))
        ttk.Label(
            head, text=f"{JOB_LABEL['api_image']} — settings",
            style="Head.TLabel",
        ).pack(side="left")

        # two-column-dense body (owner 2026-07-21 layout fix): this panel
        # is ALWAYS shown full-width, exactly like the ToolSettingsPanel
        # family, so a single left-hugging stack left the right half dead
        # (Rule #16). LEFT mirrors AgentPanel's own quick controls —
        # description, Background/Style, the post-save switches, pacing,
        # the API-access gate; RIGHT holds the two detailed editor blocks
        # (the Force-Aspect canvas, the Upscale gate's FilterEditor).
        body = ttk.Frame(self)
        body.pack(fill="x", pady=(6, 0))
        body.columnconfigure(0, weight=1)
        body.columnconfigure(1, weight=1)
        left = ttk.Frame(body)
        left.grid(row=0, column=0, sticky="new")
        right = ttk.Frame(body)
        right.grid(row=0, column=1, sticky="new", padx=(DENSE_COL_GAP_PX, 0))

        ttk.Label(
            left,
            text="Generates the SAME queued Collections (.md sheets) as"
            " Website GEN, through the paid Gemini image API instead of"
            " a browser tab.",
            style="Muted.TLabel", wraplength=DENSE_COL_WRAP_PX,
        ).pack(anchor="w", pady=(0, 4))

        # background/style — the SAME prompt_suffix machinery every
        # AgentPanel already feeds (Rule #5); "white" default (not a
        # site's own default_background) since the model cannot render
        # real transparency — see this class's own docstring
        self.background_var = tk.StringVar(value="white")
        self.style_var = tk.StringVar(value=STYLE_DEFAULT)
        row = ttk.Frame(left)
        row.pack(fill="x", pady=2)
        ttk.Label(row, text="Background:").pack(side="left")
        rounded_combo(
            row, BACKGROUND_CHOICES, self.background_var, width=105,
        ).pack(side="left", padx=(2, 10))
        ttk.Label(row, text="Style:").pack(side="left")
        rounded_combo(
            row, STYLE_CHOICES, self.style_var, width=150,
        ).pack(side="left", padx=(2, 0))

        # post-save pipeline switches — ALL default ON (no native
        # transparency, spec item 3): _compose_post_save runs whichever
        # are ticked in the fixed BG -> Crop -> Aspect -> Upscale order,
        # identical to every AgentPanel-driven site.
        self.bg_removal_var = tk.BooleanVar(value=True)
        self.crop_var = tk.BooleanVar(value=True)
        self.force_aspect_var = tk.BooleanVar(value=True)
        self.upscale_var = tk.BooleanVar(value=True)
        row = ttk.Frame(left)
        row.pack(fill="x", pady=2)
        rounded_switch(row, "BG removal", self.bg_removal_var).pack(
            side="left"
        )
        rounded_switch(row, "Crop", self.crop_var).pack(side="left", padx=8)
        rounded_switch(
            row, "Force Aspect Ratio", self.force_aspect_var,
        ).pack(side="left", padx=(0, 8))
        rounded_switch(row, "Upscale", self.upscale_var).pack(side="left")

        self.report_var = tk.BooleanVar(value=True)
        self.keep_all_steps_var = tk.BooleanVar(
            value=JOBTEMP_KEEP_ALL_STEPS_DEFAULT
        )
        row = ttk.Frame(left)
        row.pack(fill="x", pady=2)
        rounded_switch(row, "Report txt", self.report_var).pack(side="left")
        rounded_switch(
            row, "Keep every pipeline step (uses more disk)",
            self.keep_all_steps_var,
        ).pack(side="left", padx=8)

        # pace between prompts — run_sheet's own pacing wait, unrelated
        # to ai.py's internal AI_CALL_PAUSE_S free-tier throttle; no
        # action-delay field (that is SiteDriver._hesitate()'s DOM
        # concept — there is no DOM here).
        self.pause_min_var = tk.StringVar(value=f"{TIMING.pause_min_s:.0f}")
        self.pause_max_var = tk.StringVar(value=f"{TIMING.pause_max_s:.0f}")
        row = ttk.Frame(left)
        row.pack(fill="x", pady=2)
        ttk.Label(row, text="pause", width=12).pack(side="left")
        Spinner(row, self.pause_min_var, step=1.0).pack(side="left")
        ttk.Label(row, text="–").pack(side="left", padx=2)
        Spinner(row, self.pause_max_var, step=1.0).pack(side="left")
        ttk.Label(row, text="s").pack(side="left", padx=(2, 0))

        # --- GATING: the "Check API access" probe (spec item 5) -------
        gate_row = ttk.Frame(left)
        gate_row.pack(fill="x", pady=(8, 2))
        self._gate_btn = rounded_button(
            gate_row, "Check API access", command=self._probe_access,
            kind="info",
        )
        self._gate_btn.pack(side="left")
        self._gate_var = tk.StringVar(value="")
        ttk.Label(
            gate_row, textvariable=self._gate_var, style="Muted.TLabel",
            wraplength=DENSE_COL_WRAP_PX,
        ).pack(side="left", padx=(8, 0))
        self._probe_q: queue.Queue = queue.Queue()
        self._probe_poll_job: str | None = None

        # Force Aspect Ratio target — the SAME AspectRatioCanvas two-way
        # sync AgentPanel's own Force-Aspect block / AspectSettingsPanel
        # already use (Rule #5)
        ttk.Label(
            right, text="Force Aspect Ratio target:", style="Head.TLabel",
        ).pack(anchor="w")
        self.force_aspect_w_var = tk.StringVar(value=str(ASPECT_DEFAULT_W))
        self.force_aspect_h_var = tk.StringVar(value=str(ASPECT_DEFAULT_H))
        fa_box = ttk.Frame(right)
        fa_box.pack(fill="x", pady=2)
        fa_fields = ttk.Frame(fa_box)
        fa_fields.pack(side="left", anchor="n")
        ttk.Label(fa_fields, text="W").pack(side="left", padx=(0, 4))
        rounded_entry(
            fa_fields, width=ASPECT_DIALOG_ENTRY_W,
            textvariable=self.force_aspect_w_var, justify="center",
        ).pack(side="left")
        ttk.Label(fa_fields, text=":", font=tk_font("head")).pack(
            side="left", padx=8
        )
        ttk.Label(fa_fields, text="H").pack(side="left", padx=(0, 4))
        rounded_entry(
            fa_fields, width=ASPECT_DIALOG_ENTRY_W,
            textvariable=self.force_aspect_h_var, justify="center",
        ).pack(side="left")
        self._force_aspect_canvas = AspectRatioCanvas(
            fa_box, w=int(self.force_aspect_w_var.get()),
            h=int(self.force_aspect_h_var.get()),
            on_change=self._on_force_aspect_canvas_drag,
        )
        self._force_aspect_canvas.pack(side="left", padx=(12, 0), anchor="n")
        self.force_aspect_w_var.trace_add(
            "write", self._on_force_aspect_wh_typed
        )
        self.force_aspect_h_var.trace_add(
            "write", self._on_force_aspect_wh_typed
        )

        # the upscale gate — min-side spinner + embedded FilterEditor,
        # the SAME shape AgentPanel/UpscaleSettingsPanel already use
        ttk.Label(
            right, text="Upscale gate:", style="Head.TLabel",
        ).pack(anchor="w", pady=(8, 0))
        self.up_minside_var = tk.StringVar(
            value=str(UPSCALE_MIN_SIDE_DEFAULT)
        )
        row = ttk.Frame(right)
        row.pack(fill="x", pady=2)
        ttk.Label(row, text="min side", width=8).pack(side="left")
        Spinner(row, self.up_minside_var, step=UPSCALE_MINDIM_STEP).pack(
            side="left"
        )
        ttk.Label(
            row, text="px (the smaller side reaches this)",
            wraplength=DENSE_COL_WRAP_PX,
        ).pack(side="left", padx=(4, 0))
        self.upscale_filter = FilterEditor(
            right,
            conditions=[filters.FilterCondition(
                kind=FILTER_KIND_ASPECT_RANGE, polarity=FILTER_POLARITY_IF,
                lo=UPSCALE_ASPECT_MIN, hi=UPSCALE_ASPECT_MAX,
            )],
            presets=self._filter_presets,
            on_presets_changed=self._on_filter_presets_changed,
        )
        self.upscale_filter.pack(fill="x", pady=(2, 0))

        btn_row = ttk.Frame(self)
        btn_row.pack(fill="x", pady=(10, 0))
        self.btn_start = rounded_button(
            btn_row, "Start", command=self._on_start,
            kind="success", icon_name="start", width=90,
        )
        self.btn_start.pack(side="left")
        self.btn_pause = rounded_button(
            btn_row, "Pause", command=partial(self._on_pause, "api_image"),
            kind="secondary", width=70,
        )
        self.btn_pause.pack(side="left", padx=6)
        self.btn_stop = rounded_button(
            btn_row, "Stop", command=partial(self._on_stop, "api_image"),
            kind="danger-outline", width=70,
        )
        self.btn_stop.pack(side="left", padx=(0, 6))
        self.set_run_state(running=False)

        # a Day/Night flip must repaint the embedded AspectRatioCanvas
        # (mirrors AgentPanel/AspectSettingsPanel's own registration —
        # build-once, never destroyed before app exit)
        THEME_TOPLEVELS.append(self)
        self.bind("<Destroy>", self._on_destroy)

    def _on_destroy(self, event) -> None:
        if event.widget is self and self in THEME_TOPLEVELS:
            THEME_TOPLEVELS.remove(self)

    def apply_theme(self) -> None:
        self._force_aspect_canvas.redraw_theme()

    # --- Force Aspect Ratio two-way sync (mirrors AgentPanel's own) ----

    def _on_force_aspect_canvas_drag(self, w: int, h: int) -> None:
        self.force_aspect_w_var.set(str(w))
        self.force_aspect_h_var.set(str(h))

    def _on_force_aspect_wh_typed(self, *_args) -> None:
        try:
            w = int(self.force_aspect_w_var.get().strip())
            h = int(self.force_aspect_h_var.get().strip())
        except ValueError:
            return
        if w <= 0 or h <= 0:
            return
        self._force_aspect_canvas.set_ratio(w, h)

    def force_aspect_ratio(self) -> tuple[int, int]:
        """ValueError propagates to the caller's Start validation, same
        contract as ``AgentPanel.force_aspect_ratio``."""
        return (
            int(self.force_aspect_w_var.get()),
            int(self.force_aspect_h_var.get()),
        )

    # --- upscale gate (mirrors AgentPanel's own) ------------------------

    def upscale_params(self) -> dict:
        min_side = int(float(self.up_minside_var.get()))
        return _upscale_params_from_side_and_filter(
            min_side, self.upscale_filter.get_conditions()
        )

    def upscale_conditions(self) -> list[filters.FilterCondition]:
        return self.upscale_filter.get_conditions()

    def pace_floats(self) -> tuple[float, float]:
        """ValueError propagates to the caller's Start validation, same
        contract as ``AgentPanel.pace_floats`` (narrower here — no
        action-delay pair)."""
        return (float(self.pause_min_var.get()), float(self.pause_max_var.get()))

    # --- gating: "Check API access" probe -------------------------------

    def _probe_access(self) -> None:
        """One cheap ``generate_image`` call on a background thread —
        ``PaidFeatureRequired`` means the free tier is still exhausted
        (gates Start with ``AI_IMAGE_GATE_MESSAGE``); success clears any
        previous gate; any OTHER ``AiError`` (``NoKey``, network) is
        shown but leaves the gate exactly as it was — inconclusive, not
        proof either way. Mirrors ``AiKeyWizard._test``'s own worker
        (no ``log=`` override — the default ``print`` is enough for an
        occasional manual probe, same precedent)."""
        self._gate_btn.configure(state="disabled")
        self._gate_var.set("Checking API access …")

        def work() -> None:
            from painter import ai

            try:
                ai.generate_image(
                    AI_IMAGE_PROBE_PROMPT, model=GEMINI_IMAGE_MODEL,
                )
            except ai.PaidFeatureRequired as exc:
                self._probe_q.put(("gated", str(exc)))
            except ai.AiError as exc:
                self._probe_q.put(("error", str(exc)))
            else:
                self._probe_q.put(("ok", ""))

        threading.Thread(target=work, daemon=True).start()
        self._arm_probe_poll()

    def _arm_probe_poll(self) -> None:
        # AI_POLL_MS still lives in gui/__init__.py (also read by
        # _AiDialog, which never moved out of that module) — a deferred
        # `import gui` here reaches it late, same indirection
        # gui.theme._pkg() already established for a callback that must
        # reach back into the still-monolithic part of the package.
        import gui
        self._probe_poll_job = self.after(gui.AI_POLL_MS, self._poll_probe)

    def _poll_probe(self) -> None:
        self._probe_poll_job = None
        if not self.winfo_exists():
            return  # closed mid-check — the worker's message is moot
        try:
            msg = self._probe_q.get_nowait()
        except queue.Empty:
            self._arm_probe_poll()
            return
        self._apply_probe_result(msg)

    def _apply_probe_result(self, msg: tuple) -> None:
        kind, text = msg
        self._gate_btn.configure(state="normal")
        if kind == "ok":
            self.access_gated = False
            self._gate_var.set("API access OK — billing is enabled.")
        elif kind == "gated":
            self.access_gated = True
            self._gate_var.set(AI_IMAGE_GATE_MESSAGE)
        else:
            self._gate_var.set(f"Check inconclusive: {text}")
        self._refresh_start_state()

    def _refresh_start_state(self) -> None:
        style_action_button(
            self.btn_start, "success",
            not self._running and not self.access_gated,
        )

    # --- run state -----------------------------------------------------

    def set_run_state(self, running: bool) -> None:
        self._running = running
        self._refresh_start_state()
        style_action_button(self.btn_stop, "danger", running)

    def set_paused(self, is_paused: bool) -> None:
        self.btn_pause.configure(text="Resume" if is_paused else "Pause")

    # --- settings round-trip --------------------------------------------
    # SAME (stored, conditions=...) shape ToolSettingsPanel.apply_settings
    # already has, so PainterGui._apply_settings's existing generic
    # "tool_panels" loop round-trips this panel with NO changes there —
    # "conditions" carries the upscale-gate filter (the ONE FilterEditor
    # this panel owns), exactly the role UpscaleSettingsPanel's own top-
    # level ``self.filter`` already plays under the same key.

    def get_settings(self) -> dict:
        return {
            "background": self.background_var.get(),
            "style": self.style_var.get(),
            "bg_removal": self.bg_removal_var.get(),
            "crop": self.crop_var.get(),
            "force_aspect": self.force_aspect_var.get(),
            "force_aspect_w": self.force_aspect_w_var.get(),
            "force_aspect_h": self.force_aspect_h_var.get(),
            "upscale": self.upscale_var.get(),
            "up_minside": self.up_minside_var.get(),
            "report": self.report_var.get(),
            "keep_all_steps": self.keep_all_steps_var.get(),
            "pause_min": self.pause_min_var.get(),
            "pause_max": self.pause_max_var.get(),
            "conditions": [
                filters.condition_to_dict(c)
                for c in self.upscale_filter.get_conditions()
            ],
        }

    def apply_settings(
        self, stored: dict,
        conditions: list[filters.FilterCondition] | None = None,
    ) -> None:
        """Missing keys keep the current defaults — same contract as
        every other panel's ``apply_settings`` in this file."""
        string_fields = (
            "background", "style", "up_minside", "force_aspect_w",
            "force_aspect_h", "pause_min", "pause_max",
        )
        for key in string_fields:
            if key in stored:
                getattr(self, f"{key}_var").set(stored[key])
        bool_fields = ("bg_removal", "crop", "force_aspect", "upscale",
                       "report", "keep_all_steps")
        for key in bool_fields:
            if key in stored:
                getattr(self, f"{key}_var").set(bool(stored[key]))
        if conditions is not None:
            self.upscale_filter.set_conditions(conditions)
        try:
            w = int(self.force_aspect_w_var.get())
            h = int(self.force_aspect_h_var.get())
            if w > 0 and h > 0:
                self._force_aspect_canvas.set_ratio(w, h)
        except ValueError:
            pass




class ApiImageAdapter:
    """A ``SiteDriver``-shaped stand-in over the paid Gemini image API —
    lets the "api_image" job reuse ``PainterGui._drive_site``/
    ``painter.runner.run_sheet`` COMPLETELY UNCHANGED (the binding
    design doc's own "biggest risk-reducer": ``run_sheet`` only ever
    calls ``submit_prompt``/``await_done``/``extract_image`` on its
    driver, plus ``attach``/``close`` in ``_drive_site`` and
    ``driver.site.name`` for the report header — see runner.py/
    driver.md). There is no browser tab to drive, so ``attach``/
    ``close``/``await_done`` are no-ops; ``submit_prompt`` only
    REMEMBERS the prompt text — the real call happens in
    ``extract_image``, mirroring the DOM driver's own submit-then-
    await-then-extract shape so ``run_sheet``'s own timing split
    (SEND -> image is "gen_s") stays meaningful. ``new_chat`` is
    deliberately NOT implemented: ``PainterGui._start_api_image``
    always passes ``new_chat="off"``, so ``_drive_site``/``run_sheet``
    never call it on this adapter — there is no chat to open.

    A free-tier-exhausted 429 (``ai.PaidFeatureRequired`` — the
    account has ZERO free quota for the paid image model, see ai.md)
    is remapped to ``driver.TerminalState`` so the EXISTING quota-stop
    plumbing (``_drive_site``'s own ``except TerminalState`` branch,
    the dashboard's state line) handles it with NO new code. The
    free-tier-zero condition is PERMANENT — no wait ever fixes it, only
    billing — so ``retry_after_s`` is always None: unlike a website
    quota with a known reset time, this job never schedules an
    auto-restart timer, exactly like a quota message that named no
    parseable reset time."""

    def __init__(self, log: Callable[[str], None] = print):
        self._log = log
        self._prompt: str = ""
        # run_sheet reads driver.site.name for the report header
        # (RunReport's constructor, only when report=True) — a tiny
        # stand-in, never a real SiteConfig (no DOM field on it is
        # ever read).
        self.site = SimpleNamespace(name=JOB_LABEL["api_image"])

    def attach(self) -> str:
        return "API Image GEN (Gemini paid image model, no browser tab)"

    def close(self) -> None:
        pass

    def submit_prompt(self, prompt: str) -> None:
        self._prompt = prompt

    def await_done(self, log: Callable[[str], None] = print) -> None:
        pass

    def extract_image(self) -> bytes:
        from painter import ai
        from painter.driver import TerminalState

        try:
            return ai.generate_image(
                self._prompt, model=GEMINI_IMAGE_MODEL, log=self._log,
            )
        except ai.PaidFeatureRequired as exc:
            raise TerminalState(str(exc), retry_after_s=None) from exc
