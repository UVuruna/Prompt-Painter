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
import. ``AI_POLL_MS`` is the one exception: it lives in
``gui/dialogs.py`` (``_AiDialog`` owns the poll loop it paces), so
``_arm_probe_poll`` below reaches it through a deferred
``import gui`` instead — the same late-binding indirection
``gui.theme._pkg()`` already established for a callback that must
reach back into a sibling module."""

from __future__ import annotations

import queue
import threading
import tkinter as tk
from functools import partial
from pathlib import Path
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
    JOBTEMP_KEEP_ALL_STEPS_DEFAULT,
    JOB_LABEL,
    JOB_ICON_PX,
    JOB_LOGO,
    PACE_FAST_S,
    PACE_POLITE_DEFAULT,
    PACE_POLITE_S,
    STYLE_CHOICES,
    STYLE_DEFAULT,
    pace_range,
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
    ExpandableSwitch,
    ExpanderAccordion,
    FlowRow,
    quiet_restore,
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
        build_collections: Callable | None = None,
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
            head, text="", image=icon(JOB_LOGO["api_image"], JOB_ICON_PX), width=JOB_ICON_PX + 2,
            fg_color="transparent", bg_color=theme_pair("bg"),
        ).pack(side="left", padx=(0, 4))
        ttk.Label(
            head, text=f"{JOB_LABEL['api_image']} — settings",
            style="Head.TLabel",
        ).pack(side="left")

        # THE SHARED SETUP SKELETON (faza 3, owner 2026-08-03, UV
        # tačka 5: "raspored kao Website Image GEN"): LEFT = settings
        # (Model on top, then the same four groups AgentPanel grids —
        # Pipeline | Run behavior / Pacing | Prompt), RIGHT = the
        # shared CollectionsColumn (queue + output + Select + the
        # Prompt+Image toggle/section) when the host supplies its
        # builder (``build_collections`` — None in headless tests keeps
        # the panel self-contained).
        body = ttk.Frame(self)
        body.pack(fill="both", expand=True, pady=(6, 0))
        # 2:1 in favour of the settings column (owner 2026-08-03,
        # slika 1) — the same split the website setup screen uses
        body.columnconfigure(0, weight=2)
        body.columnconfigure(1, weight=1)
        body.rowconfigure(0, weight=1)
        left = ttk.Frame(body)
        left.grid(row=0, column=0, sticky="new")
        if build_collections is not None:
            column = build_collections(body)
            column.grid(
                row=0, column=1, sticky="nsew", padx=(DENSE_COL_GAP_PX, 0)
            )

        ttk.Label(
            left,
            text="Generates the SAME queued Collections (.md sheets) as"
            " Website Image GEN, through the paid Gemini image API instead of"
            " a browser tab.",
            style="Muted.TLabel", wraplength=DENSE_COL_WRAP_PX,
        ).pack(anchor="w", pady=(0, 4))

        # --- MODEL group (faza 3): ONLY the Image-generation model ----
        # lives here now — the Vision pick belongs to AI Check and the
        # Text pick to New Collection (AI) (owner: "podešavanje za TEXT
        # GEN i IMAGE CHECK ide tamo ko to KORISTI" — they move in faza
        # 4; their settings.json overrides stay untouched meanwhile).
        # "Refresh models" mirrors the gating probe below (its own
        # private queue+poll, same background-thread convention); the
        # dropdown lists IMAGE-CAPABLE models only (P3=A — "show all"
        # is the debug escape hatch), each pick showing its curated
        # one-line hint (config.model_hint). The combo PRESELECTS via
        # ``CTkComboBox.set()`` — which does NOT fire ``command`` — so
        # only a GENUINE user pick ever writes settings.json.
        ttk.Label(
            left, text="Model (image generation)", style="Head.TLabel",
        ).pack(anchor="w", pady=(2, 2))
        models_row = ttk.Frame(left)
        models_row.pack(fill="x", pady=(0, 2))
        self._models_btn = rounded_button(
            models_row, "Refresh models", icon_name="refresh", command=self._refresh_models,
            kind="info",
        )
        self._models_btn.pack(side="left")
        self._models_status_var = tk.StringVar(value="")
        ttk.Label(
            models_row, textvariable=self._models_status_var,
            style="Muted.TLabel", wraplength=DENSE_COL_WRAP_PX,
        ).pack(side="left", padx=(8, 0))
        self._models_q: queue.Queue = queue.Queue()
        self._models_poll_job: str | None = None
        self._discovered_models: list[dict] = []  # cached for the session

        picks_row = ttk.Frame(left)
        picks_row.pack(fill="x", pady=2)
        self.model_image_var = tk.StringVar(value="")
        self._model_vars = {"image": self.model_image_var}
        self._model_combos: dict[str, ctk.CTkComboBox] = {}
        ttk.Label(picks_row, text="Image:").pack(side="left")
        combo = rounded_combo(
            picks_row, (), self.model_image_var, width=200,
            state="disabled",
            command=partial(self._on_model_pick, "image"),
        )
        combo.pack(side="left", padx=(2, 10))
        self._model_combos["image"] = combo
        self.model_show_all_var = tk.BooleanVar(value=False)
        rounded_switch(
            picks_row, "show all (debug)", self.model_show_all_var,
        ).pack(side="left")
        self.model_show_all_var.trace_add(
            "write", lambda *_a: self._populate_model_dropdowns()
        )
        self._model_hint_var = tk.StringVar(value="")
        ttk.Label(
            left, textvariable=self._model_hint_var, style="Muted.TLabel",
            wraplength=DENSE_COL_WRAP_PX,
        ).pack(anchor="w", pady=(0, 2))
        self._update_model_hint(self._current_image_model())

        # --- GATING: the "Check API access" probe (spec item 5) -------
        gate_row = ttk.Frame(left)
        gate_row.pack(fill="x", pady=(2, 4))
        self._gate_btn = rounded_button(
            gate_row, "Check API access", icon_name="testkey", command=self._probe_access,
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

        # --- the groups as FULL-WIDTH BANDS, like AgentPanel (owner
        # 2026-08-03, slika 1) — switches FLOW and WRAP, and each
        # band's fine-tune opens into a full-width host BELOW them, so
        # nothing is ever cut off the right edge. API's Run behavior /
        # Pacing / Prompt hold ONE-TO-TWO controls each ("objedinis ih
        # u jednu kolonu jer imaju malo elemenata"), so all three share
        # ONE band whose flow puts them side by side and wraps them
        # when the window narrows.
        content = ttk.Frame(left)
        content.pack(fill="x", pady=(4, 0))
        content.columnconfigure(0, weight=1)
        self._flows: list[FlowRow] = []
        self._accordion = ExpanderAccordion()
        self._band_row = 0

        def group(title: str):
            outer = ttk.Frame(content)
            outer.grid(row=self._band_row, column=0, sticky="new", pady=(2, 4))
            self._band_row += 1
            ttk.Label(outer, text=title, style="Head.TLabel").pack(
                anchor="w", pady=(2, 2)
            )
            flow_ = FlowRow(outer)
            flow_.pack(fill="x")
            self._flows.append(flow_)
            host_ = ttk.Frame(outer)
            host_.pack(fill="x")
            return flow_, host_

        # Pipeline — ALL switches default ON (no native transparency,
        # spec item 3): _compose_post_save runs whichever are ticked in
        # the fixed BG -> Crop -> Aspect -> Upscale order, identical to
        # every AgentPanel-driven site. The Force-Aspect target and the
        # Upscale gate live right under their switches.
        flow, host = group("Pipeline")
        self.bg_removal_var = tk.BooleanVar(value=True)
        self.crop_var = tk.BooleanVar(value=True)
        self.force_aspect_var = tk.BooleanVar(value=True)
        self.upscale_var = tk.BooleanVar(value=True)
        self.keep_all_steps_var = tk.BooleanVar(
            value=JOBTEMP_KEEP_ALL_STEPS_DEFAULT
        )
        flow.switch("BG removal", self.bg_removal_var)
        flow.switch("Crop", self.crop_var)
        # Force Aspect Ratio + Upscale are EXPANDABLE here, exactly as
        # in AgentPanel (owner 2026-08-03): their fine-tune — the
        # aspect canvas and the upscale FilterEditor — is tall enough
        # that keeping it permanently open stretched this left column
        # past the window, pushing Pacing/Prompt and the whole
        # Start/Pause/Stop row below the fold.
        self.force_aspect_w_var = tk.StringVar(value=str(ASPECT_DEFAULT_W))
        self.force_aspect_h_var = tk.StringVar(value=str(ASPECT_DEFAULT_H))
        self._sw_aspect = ExpandableSwitch(
            flow, "Force Aspect Ratio", self.force_aspect_var,
            build_sub=self._build_aspect_sub, eager=True,
            sub_host=host, accordion=self._accordion,
        )
        flow.add(self._sw_aspect)
        self._sw_upscale = ExpandableSwitch(
            flow, "Upscale", self.upscale_var,
            build_sub=self._build_upscale_sub, eager=True,
            sub_host=host, accordion=self._accordion,
        )
        flow.add(self._sw_upscale)
        flow.switch(
            "Keep every pipeline step (more disk)", self.keep_all_steps_var,
        )

        # Run behavior + Pacing + Prompt — ONE merged band (owner
        # 2026-08-03: "kod API IMAGE GEN objedini ih u jednu kolonu jer
        # imaju malo elemenata"): Report txt, the pause range (run_sheet's
        # own pacing wait, unrelated to ai.py's internal AI_CALL_PAUSE_S
        # free-tier throttle; no action-delay field — that is
        # SiteDriver._hesitate()'s DOM concept and there is no DOM here)
        # and the two prompt dropdowns, which feed the SAME prompt_suffix
        # machinery every AgentPanel already does (Rule #5); "white" is
        # the default (not a site's own default_background) since the
        # model cannot render real transparency.
        flow, _host = group("Run behavior · Pacing · Prompt")
        self.report_var = tk.BooleanVar(value=True)
        # THE PACE is ONE switch (owner 2026-08-07) — the same contract as
        # AgentPanel's, so the two jobs can never pace differently by
        # accident. The pause spinners retired with it.
        self.polite_pace_var = tk.BooleanVar(value=PACE_POLITE_DEFAULT)
        self.background_var = tk.StringVar(value="white")
        self.style_var = tk.StringVar(value=STYLE_DEFAULT)
        flow.switch("Report txt", self.report_var)
        cell = flow.cell()
        rounded_switch(cell, "Polite pace", self.polite_pace_var).pack(side="left")
        ttk.Label(
            cell,
            text=f"{PACE_POLITE_S[0]:.0f}–{PACE_POLITE_S[1]:.0f}s between"
                 f" images; off = {PACE_FAST_S[0]:.0f}–{PACE_FAST_S[1]:.0f}s",
            style="Muted.TLabel",
        ).pack(side="left", padx=(8, 0))
        cell = flow.cell()
        ttk.Label(cell, text="Background:").pack(side="left", padx=(0, 4))
        rounded_combo(
            cell, BACKGROUND_CHOICES, self.background_var, width=105,
        ).pack(side="left")
        cell = flow.cell()
        ttk.Label(cell, text="Style:").pack(side="left", padx=(0, 4))
        rounded_combo(
            cell, STYLE_CHOICES, self.style_var, width=140,
        ).pack(side="left")

        btn_row = ttk.Frame(self)
        btn_row.pack(fill="x", pady=(10, 0))
        self.btn_start = rounded_button(
            btn_row, "Start", command=self._on_start,
            kind="success", icon_name="start", width=90,
        )
        self.btn_start.pack(side="left")
        self.btn_pause = rounded_button(
            btn_row, "Pause", icon_name="pause", command=partial(self._on_pause, "api_image"),
            kind="secondary", width=70,
        )
        self.btn_pause.pack(side="left", padx=6)
        self.btn_stop = rounded_button(
            btn_row, "Stop", icon_name="stop", command=partial(self._on_stop, "api_image"),
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


    def reflow(self) -> None:
        """Re-wrap every band for the current width (font zoom — the
        elements' requested widths change without a <Configure>)."""
        for flow in self._flows:
            flow.reflow()

    def _build_aspect_sub(self, parent) -> None:
        """The Force-Aspect target: W:H entries mirrored two-way with
        an AspectRatioCanvas — AgentPanel's own sub-panel content."""
        # fields + canvas are FLOW cells (owner 2026-08-03, slika 2):
        # side by side while there is room, canvas on its own row the
        # moment there is not — never sliced in half
        fa_box = FlowRow(parent)
        fa_box.pack(fill="x", pady=2)
        self._flows.append(fa_box)
        fa_fields = fa_box.cell()
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
        canvas_cell = fa_box.cell()
        self._force_aspect_canvas = AspectRatioCanvas(
            canvas_cell, w=int(self.force_aspect_w_var.get()),
            h=int(self.force_aspect_h_var.get()),
            on_change=self._on_force_aspect_canvas_drag,
        )
        self._force_aspect_canvas.pack(anchor="nw")
        self.force_aspect_w_var.trace_add(
            "write", self._on_force_aspect_wh_typed
        )
        self.force_aspect_h_var.trace_add(
            "write", self._on_force_aspect_wh_typed
        )

    def _build_upscale_sub(self, parent) -> None:
        """The upscale gate: min-side spinner + the FilterEditor whose
        one default condition is the 0.9-1.1 aspect range."""
        self.up_minside_var = tk.StringVar(
            value=str(UPSCALE_MIN_SIDE_DEFAULT)
        )
        flow = FlowRow(parent)
        flow.pack(fill="x", pady=2)
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
            parent,
            conditions=[filters.FilterCondition(
                kind=FILTER_KIND_ASPECT_RANGE, polarity=FILTER_POLARITY_IF,
                lo=UPSCALE_ASPECT_MIN, hi=UPSCALE_ASPECT_MAX,
            )],
            presets=self._filter_presets,
            on_presets_changed=self._on_filter_presets_changed,
        )
        self.upscale_filter.pack(fill="x", pady=(2, 0))

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

    def pace(self) -> tuple[float, float]:
        """This job's (pause_min, pause_max) — identical contract to
        ``AgentPanel.pace``, so the API job and the site runs read the
        SAME config ranges (owner 2026-08-07)."""
        return pace_range(self.polite_pace_var.get())

    # --- gating: "Check API access" probe -------------------------------

    def _probe_access(self) -> None:
        """One cheap ``generate_image`` call on a background thread —
        ``PaidFeatureRequired`` means the free tier is still exhausted
        (gates Start with ``AI_IMAGE_GATE_MESSAGE``); success clears any
        previous gate; any OTHER ``AiError`` (``NoKey``, network) is
        shown but leaves the gate exactly as it was — inconclusive, not
        proof either way. Mirrors ``AiKeyWizard._test``'s own worker
        (no ``log=`` override — the default ``print`` is enough for an
        occasional manual probe, same precedent). No ``model=`` is
        passed (F5): ``generate_image`` resolves it itself via
        ``model_for("image")``, so the probe tests the SAME model
        (override or fallback) an actual run would use, never a
        hardcoded one."""
        self._gate_btn.configure(state="disabled")
        self._gate_var.set("Checking API access …")

        def work() -> None:
            from painter import ai

            try:
                ai.generate_image(AI_IMAGE_PROBE_PROMPT)
            except ai.PaidFeatureRequired as exc:
                self._probe_q.put(("gated", str(exc)))
            except ai.AiError as exc:
                self._probe_q.put(("error", str(exc)))
            else:
                self._probe_q.put(("ok", ""))

        threading.Thread(target=work, daemon=True).start()
        self._arm_probe_poll()

    def _arm_probe_poll(self) -> None:
        # AI_POLL_MS lives in gui/dialogs.py (_AiDialog owns the poll
        # loop it paces) — a deferred `import gui` here reaches it late,
        # same indirection gui.theme._pkg() already established for a
        # callback that must reach back into a sibling module without a
        # module-level import (a real-path import from gui.api_panel
        # straight to gui.dialogs would work, but the deferred form
        # keeps this call site identical to gui.viewers.DocWindow's own
        # AI_POLL_MS read, which IS circular against gui.dialogs).
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

    # --- Model discovery + per-purpose picks (F5, owner D1/D2) ---------

    def _refresh_models(self) -> None:
        """One ``ai.list_models`` call on a background thread — mirrors
        ``_probe_access``'s own private queue+poll above (this panel is
        a ``ttk.Frame``, not the ``_AiDialog`` Toplevel that owns ITS
        poll loop)."""
        self._models_btn.configure(state="disabled")
        self._models_status_var.set("Discovering models …")

        def work() -> None:
            from painter import ai

            try:
                models = ai.list_models()
            except ai.AiError as exc:
                # a NoKey (or any other AiError) message IS the
                # existing key-gate text (spec item 4) — shown
                # verbatim, no separate copy to keep in sync
                self._models_q.put(("error", str(exc)))
            else:
                self._models_q.put(("ok", models))

        threading.Thread(target=work, daemon=True).start()
        self._arm_models_poll()

    def _arm_models_poll(self) -> None:
        # same late-binding AI_POLL_MS read as _arm_probe_poll above
        import gui
        self._models_poll_job = self.after(gui.AI_POLL_MS, self._poll_models)

    def _poll_models(self) -> None:
        self._models_poll_job = None
        if not self.winfo_exists():
            return  # closed mid-discovery — the worker's message is moot
        try:
            msg = self._models_q.get_nowait()
        except queue.Empty:
            self._arm_models_poll()
            return
        self._apply_models_result(msg)

    def _apply_models_result(self, msg: tuple) -> None:
        self._models_btn.configure(state="normal")
        kind, payload = msg
        if kind == "error":
            self._models_status_var.set(payload)
            return
        self._discovered_models = payload
        self._models_status_var.set(f"{len(payload)} model(s) discovered.")
        self._populate_model_dropdowns()

    def _populate_model_dropdowns(self) -> None:
        """Fill the Image dropdown with the IMAGE-CAPABLE discovered
        models (``ai.capable_models`` — faza 3/P3=A: the models this
        job actually needs, not all 58; the "show all (debug)" switch
        widens the list to everything discovered), preselected to the
        stored override (else ``ai.recommend_model``'s ranked pick) via
        ``combo.set()`` — the widget's OWN method, which edits the
        entry directly and does NOT go through the bound variable's
        ``command`` callback — so populating the list never itself
        persists anything. Also refreshes the curated purpose hint for
        whatever ends up selected."""
        from painter import ai
        from painter.config import MODELS_SETTING
        from painter.settings import load_settings

        overrides = load_settings().get(MODELS_SETTING) or {}
        combo = self._model_combos["image"]
        if self.model_show_all_var.get():
            names = [m["name"] for m in self._discovered_models]
        else:
            names = [
                m["name"]
                for m in ai.capable_models(self._discovered_models, "image")
            ]
        combo.configure(
            values=names, state="readonly" if names else "disabled",
        )
        override = str(overrides.get("image", "") or "").strip()
        pick = (
            override if override in names
            else ai.recommend_model(self._discovered_models, "image")
        )
        if pick:
            combo.set(pick)
            self._update_model_hint(pick)

    def _current_image_model(self) -> str:
        """The model an actual run would call RIGHT NOW —
        ``model_for("image")`` (settings override, else the config
        fallback) — for the hint shown before any discovery."""
        from painter import ai

        try:
            return ai.model_for("image")
        except Exception:  # a broken settings.json must not kill build
            return ""

    def _update_model_hint(self, name: str) -> None:
        """The curated one-line "which model for what" note (faza 3,
        ``config.model_hint`` — substring registry, honest
        MODEL_HINT_UNKNOWN for anything uncurated)."""
        from painter.config import model_hint

        self._model_hint_var.set(model_hint(name) if name else "")

    def _on_model_pick(self, purpose: str, choice: str) -> None:
        """A GENUINE user selection (the combo's ``command=`` fires
        only from a dropdown click, never from a programmatic
        preselect — see ``_populate_model_dropdowns``): persist the
        override IMMEDIATELY, like ``PainterGui.set_gemini_key`` (spec
        item 4) — this panel has no debounced settings hook of its own
        to route through (the generic ``get_settings``/
        ``apply_settings`` round-trip only saves when the OWNER
        explicitly triggers a save/close), and the model the NEXT
        generation actually calls must reflect the pick right away."""
        from painter.config import MODELS_SETTING
        from painter.settings import load_settings, save_settings

        settings = load_settings()
        models = dict(settings.get(MODELS_SETTING) or {})
        models[purpose] = choice
        settings[MODELS_SETTING] = models
        save_settings(settings)
        if purpose == "image":
            self._update_model_hint(choice)

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
            "polite_pace": self.polite_pace_var.get(),
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
            "force_aspect_h",
        )  # "pause_min"/"pause_max" retired 2026-08-07 — the pace is a
        # switch now; an old stored key is simply ignored
        for key in string_fields:
            if key in stored:
                getattr(self, f"{key}_var").set(stored[key])
        bool_fields = ("bg_removal", "crop", "force_aspect", "upscale",
                       "report", "keep_all_steps", "polite_pace")
        # a RESTORE must not auto-expand the two ExpandableSwitches —
        # Tk cannot tell a restoring .set() from a click, and a panel
        # has to open compact (the SAME contract AgentPanel.
        # apply_settings honours; without it this panel reopened with
        # the aspect canvas and the upscale FilterEditor both unfolded,
        # which is what pushed Start/Pause/Stop below the fold).
        with quiet_restore(self._sw_aspect, self._sw_upscale):
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
    parseable reset time.

    ``submit_with_image`` (F5, owner D3; MULTI faza 2) is the API-mode
    counterpart of ``driver.submit_with_image`` — an item carrying
    "← ref" input image(s) (``sheet_parser``'s ``input_images`` field,
    resolved by ``run_sheet``) attaches them exactly like
    ``submit_prompt`` remembers a plain prompt; the ACTUAL call still
    happens in ``extract_image``, same submit-then-await-then-extract
    shape. Closes the audited F5 gap: without this method, an API-mode
    run through a sheet item carrying an input image called a method
    the adapter did not have (``AttributeError`` — a crash-in-waiting,
    never yet hit only because no such run had happened)."""

    def __init__(self, log: Callable[[str], None] = print):
        self._log = log
        self._prompt: str = ""
        self._image_path: Path | list[Path] | None = None
        # run_sheet reads driver.site.name for the report header
        # (RunReport's constructor, only when report=True) — a tiny
        # stand-in, never a real SiteConfig (no DOM field on it is
        # ever read).
        self.site = SimpleNamespace(name=JOB_LABEL["api_image"])

    def attach(self) -> str:
        return "API Image GEN (Gemini paid image model, no browser tab)"

    def close(self) -> None:
        pass

    def submit_prompt(
        self, prompt: str, log: Callable[[str], None] = print,
    ) -> None:
        # ``log`` is unused here (the API job has no composer to narrate)
        # but MUST be accepted: run_sheet's generate_one passes it
        # positionally since 2026-08-04 — the same shape as
        # submit_with_image/await_done below.
        self._prompt = prompt
        # a plain text submit never carries a stale attach forward —
        # without this, a PREVIOUS item's submit_with_image would leak
        # its image into the NEXT plain-text item's extract_image call
        self._image_path = None

    def submit_with_image(
        self, image_path: str | Path | list, prompt: str,
        log: Callable[[str], None] = print,
    ) -> None:
        self._prompt = prompt
        # MULTI-ATTACH (faza 2, owner 2026-08-03): a sheet entry with
        # several ← lines arrives as a LIST (attach order preserved —
        # ai.generate_image builds one inlineData part per path); the
        # long-proven single form stays a bare Path
        if isinstance(image_path, (list, tuple)):
            paths = [Path(p) for p in image_path]
            self._image_path = paths[0] if len(paths) == 1 else paths
        else:
            self._image_path = Path(image_path)

    def await_done(self, log: Callable[[str], None] = print) -> None:
        pass

    def extract_image(self) -> bytes:
        from painter import ai
        from painter.driver import TerminalState

        image_path, self._image_path = self._image_path, None  # clear-after-read
        try:
            return ai.generate_image(
                self._prompt, image_path=image_path, log=self._log,
            )
        except ai.PaidFeatureRequired as exc:
            raise TerminalState(str(exc), retry_after_s=None) from exc
