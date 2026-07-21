"""``AgentPanel`` — one site's own control panel (Website GEN).

Split out of ``gui/__init__.py`` (Rule #3, god-file refactor step
4/8). The per-site background/style dropdowns, the three composable
post-save switches (BG removal / Crop / Upscale), Report, Safer
retry, Continue nudge, the parallel Checker/Fixer AI toggles, the
Force Aspect Ratio block and the pause/action-delay fine-tune, plus
its own Start/Pause/Stop.

The two-column-dense layout constants (``DENSE_COL_GAP_PX``/
``DENSE_COL_WRAP_PX``, the Settings-gear caret glyphs,
``ASPECT_DIALOG_ENTRY_W``) come from ``gui.tool_panels`` — the
ToolSettingsPanel family and ``ApiImageGenPanel`` share the exact same
constants (Rule #5), and importing them from that leaf module (rather
than ``gui/__init__.py``) avoids a circular import."""

from __future__ import annotations

import tkinter as tk
from functools import partial
from tkinter import ttk
from typing import Callable

import customtkinter as ctk

from painter import filters
from painter.config import (
    ASPECT_DEFAULT_H,
    ASPECT_DEFAULT_W,
    BACKGROUND_CHOICES,
    FILTER_KIND_ASPECT_RANGE,
    FILTER_POLARITY_IF,
    FIXER_MODE_API,
    FIXER_MODE_CHOICES,
    JOBTEMP_KEEP_ALL_STEPS_DEFAULT,
    JOB_LOGO,
    NEW_CHAT_CHOICES,
    SITES,
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
from .theme import THEME_TOPLEVELS, smooth_transition
from .tool_panels import (
    ASPECT_DIALOG_ENTRY_W,
    DENSE_COL_GAP_PX,
    DENSE_COL_WRAP_PX,
    SETTINGS_GLYPH_COLLAPSED,
    SETTINGS_GLYPH_EXPANDED,
)
from .widgets import (
    Spinner,
    rounded_button,
    rounded_combo,
    rounded_entry,
    rounded_switch,
    style_action_button,
    tk_font,
)


class AgentPanel(ttk.Labelframe):
    """One site's OWN control panel (full per-agent separation).

    Each site gets its own background dropdown, the three composable
    post-save switches (BG removal / Crop / Upscale), Report, Safer
    retry, New-chat mode, pause and action-delay ranges, and its own
    Start/Stop pair — only the Collections queue and the Output folder
    stay SHARED (and Select-images was per-site already). A site
    "participates" in a run by being Started; one site running never
    blocks starting the other."""

    # the keys persisted per agent in the settings file
    _PERSIST = (
        "background", "style", "bg_removal", "crop", "upscale", "report",
        "safer_retry", "continue_nudge", "checker", "fixer", "fixer_mode",
        "new_chat", "pause_min",
        "pause_max", "act_min", "act_max",
        # per-agent upscale-gate fine-tune (owner 2026-07-19; GUI rework
        # Phase 6: the old up_minw/up_minh/up_aspmin/up_aspmax four-field
        # gate collapsed into ONE min-side spinner — the embedded
        # FilterEditor's condition stack persists SEPARATELY, as
        # 'up_filter_conditions' (not a plain tk.Variable, so it is
        # handled explicitly in get_settings/apply_settings below, not
        # through this tuple)
        "up_minside",
        # this agent's own Settings-gear collapse state (owner 2026-07-19)
        "settings_collapsed",
        # the Force Aspect Ratio pipeline step (GUI rework Phase 8) — OFF
        # by default; W/H are the target ratio the AspectRatioCanvas
        # edits. "keep_all_steps" is the per-agent "keep every pipeline
        # step" disk-usage toggle (JOBTEMP_KEEP_ALL_STEPS_DEFAULT).
        "force_aspect", "force_aspect_w", "force_aspect_h", "keep_all_steps",
        # this site's show/hide toggle (GUI rework Phase 12, spec item
        # 3A) — default True (both panels visible, today's behaviour);
        # see visible_var's own docstring for the "never hide a live
        # job's only control surface" guarantee.
        "visible",
    )

    def __init__(
        self, master, site_key: str, on_start, on_stop, on_pause,
        filter_presets: dict[str, list[dict]] | None = None,
        on_filter_presets_changed: Callable[[], None] | None = None,
        on_log: Callable[[str], None] | None = None,
        on_layout_change: Callable[[], None] | None = None,
    ):
        super().__init__(master)
        self.site_key = site_key
        self._on_start = on_start
        self._on_stop = on_stop
        self._on_pause = on_pause
        # optional so a headless AgentPanel (no PainterGui — every
        # gui_*.py test's own make_panel()) still works, same pattern as
        # on_filter_presets_changed below
        self._on_log = on_log or (lambda _msg: None)
        # PainterGui wires this to the outer fill_height ScrollFrame's
        # own refresh() (owner 2026-07-21 perf fix, replacing the old
        # perpetual self-heal poll): the Settings-gear reveal below
        # changes this panel's own content height, several parents deep
        # under that ScrollFrame, with no reference of its own to it —
        # see ScrollFrame.refresh's own docstring for why this call is
        # required. A no-op default keeps every headless make_panel() in
        # the test suite working unchanged.
        self._on_layout_change = on_layout_change or (lambda: None)
        # the SHARED filter-preset library (GUI rework Phase 6) — the
        # same dict/callback PainterGui hands every FilterEditor
        # instance (see filters.py's module docstring: one preset
        # library, every FilterEditor reads/writes the same names).
        # Optional so a headless AgentPanel (no PainterGui) still works,
        # falling back to FilterEditor's own private in-memory dict.
        self._filter_presets = filter_presets
        self._on_filter_presets_changed = on_filter_presets_changed
        site = SITES[site_key]

        # the labelframe title: the site's logo + name
        head = ttk.Frame(self)
        ctk.CTkLabel(
            head, text="", image=icon(JOB_LOGO[site_key]), width=22,
            fg_color="transparent", bg_color=theme_pair("bg"),
        ).pack(side="left", padx=(0, 4))
        ttk.Label(head, text=site.name, style="Head.TLabel").pack(side="left")
        self.configure(labelwidget=head, padding=6)

        self.background_var = tk.StringVar(value=site.default_background)
        # the rendering STYLE clause appended at the END of this site's
        # prompt suffix (owner 2026-07-19); "None" = nothing appended
        self.style_var = tk.StringVar(value=STYLE_DEFAULT)
        self.bg_removal_var = tk.BooleanVar(value=True)
        self.crop_var = tk.BooleanVar(value=True)
        self.upscale_var = tk.BooleanVar(value=True)
        self.report_var = tk.BooleanVar(value=True)
        self.safer_var = tk.BooleanVar(value=True)
        # one-shot "continue" nudge when ChatGPT stalls on an image
        # (NoImage: done edge fired, empty answer, no marker) — owner
        # 2026-07-20; ON by default so the stuck case self-heals
        self.continue_nudge_var = tk.BooleanVar(value=True)
        # the parallel per-item Checker AI (GUI rework Phase 16, owner's
        # UV/prompt.txt item 1: "dok generise sledecu sliku paralelno
        # ona koja je generisana cek jer provjeri"): OFF by default — it
        # spends a paced Gemini vision call PER SAVED IMAGE, so it is an
        # explicit opt-in cost, not a free default like Safer
        # retry/Continue nudge beside it. See PainterGui.
        # _maybe_spawn_checker for the spawn side.
        self.checker_var = tk.BooleanVar(value=False)
        # the Fixer AI (GUI rework Phase 20, owner's UV/prompt.txt item 1:
        # "ako ustanovi gresku salje fikseru da ispravi ... u situaciji ako
        # su oba ukljucena" — "both" being the checker AND the fixer). OFF
        # by default (an opt-in COST layered on TOP of the checker's own
        # opt-in cost); visible only while checker_var is on (see
        # _apply_fixer_visibility, built in _build_finetune). "api" mode
        # dispatches ai.edit_image on a background thread the instant a
        # checked image comes back flagged — a plain REST call, so it
        # genuinely runs IN PARALLEL with this site's own next-image
        # generation (see PainterGui._maybe_spawn_fixer/_run_fixer_api).
        # "website" mode never drives driver.submit_fix from the auto
        # path — the site's browser tab is busy generating the NEXT image
        # at that exact instant (one tab, one operation) — it QUEUES the
        # item instead (see PainterGui._queue_website_fix's own docstring
        # for exactly why, and for the manual WEBSITE FIX button that DOES
        # drive the browser, owner-triggered, see DocWindow/_run_website_fix).
        self.fixer_var = tk.BooleanVar(value=False)
        self.fixer_mode_var = tk.StringVar(value=FIXER_MODE_API)
        self.new_chat_var = tk.StringVar(value="collection")
        self.pause_min_var = tk.StringVar(value=f"{TIMING.pause_min_s:.0f}")
        self.pause_max_var = tk.StringVar(value=f"{TIMING.pause_max_s:.0f}")
        self.act_min_var = tk.StringVar(
            value=f"{TIMING.action_delay_min_s:.1f}"
        )
        self.act_max_var = tk.StringVar(
            value=f"{TIMING.action_delay_max_s:.1f}"
        )
        # per-agent upscale-gate fine-tune (owner 2026-07-19; GUI rework
        # Phase 6: ONE min-SIDE spinner — the shipped default reproduces
        # the old locked rule (800px) — plus an embedded FilterEditor
        # (built in _build_finetune, seeded with today's aspect gate as
        # a single Aspect (range) condition) deciding WHICH images
        # qualify. Shown only when the Settings collapse is expanded.
        self.up_minside_var = tk.StringVar(value=str(UPSCALE_MIN_SIDE_DEFAULT))
        # the upscale FilterEditor's SEED conditions — built once here so
        # _build_finetune (called at the end of __init__) and a future
        # re-seed both read the SAME default; not itself persisted (the
        # widget's live get_conditions() is what get_settings() reads).
        self._default_upscale_conditions = [
            filters.FilterCondition(
                kind=FILTER_KIND_ASPECT_RANGE, polarity=FILTER_POLARITY_IF,
                lo=UPSCALE_ASPECT_MIN, hi=UPSCALE_ASPECT_MAX,
            )
        ]
        # this agent's OWN Settings-gear collapse state (owner 2026-07-19):
        # True = fine-tune hidden (default). A BooleanVar so it persists and
        # auto-saves through the same per-agent trace as every other field.
        self.settings_collapsed_var = tk.BooleanVar(value=True)

        # this site's SHOW/HIDE toggle (GUI rework Phase 12, spec item 3A:
        # "moze da se prikaze/sakrije bilo koji ... da ostane samo jedan
        # vidljiv" — either site's panel can be hidden so only the other
        # stays visible). True = shown (default, today's behaviour). The
        # toggle widget itself lives ABOVE both panels (PainterGui.
        # _build_options's "Show:" row, via build_visibility_toggle below)
        # — never INSIDE this panel, or hiding it would hide its own only
        # way back. set_run_state is the single choke point that (a)
        # greys _visible_btn out while this site's job is running or a
        # quota auto-restart is pending (Stop/Pause live only on THIS
        # panel, so hiding it then would strand the job with no control
        # surface) and (b) forces this back to True — logging why — if a
        # HIDDEN site's job goes live without a click (a quota
        # auto-restart, an AI-check resend: both call PainterGui.
        # _start_site directly, bypassing btn_start).
        self.visible_var = tk.BooleanVar(value=True)
        # set once PainterGui builds this site's entry in the "Show:" row
        # (build_visibility_toggle, after __init__ returns) — None until
        # then, exactly like _button_pairs' second (compact) entry is
        # absent until build_compact runs; set_run_state tolerates either.
        self._visible_btn: ctk.CTkSwitch | None = None

        # the Force Aspect Ratio pipeline step (GUI rework Phase 8) — OFF
        # by default (a deliberate DEFORM, not everyone's images need
        # one); W/H are the target ratio, mirrored two-way with the
        # embedded AspectRatioCanvas (built in _build_finetune, reusing
        # Phase 5's editor) exactly like AspectRatioDialog's own W/H
        # entries + canvas.
        self.force_aspect_var = tk.BooleanVar(value=False)
        self.force_aspect_w_var = tk.StringVar(value=str(ASPECT_DEFAULT_W))
        self.force_aspect_h_var = tk.StringVar(value=str(ASPECT_DEFAULT_H))
        # per-agent "keep every pipeline step" disk-usage toggle (owner
        # decision 2026-07-21, GUI rework Phase 8) — ON keeps a
        # restorable backup for EVERY enabled post-save step (BG/Crop/
        # Aspect/Upscale), not just the pristine "original" baseline;
        # OFF (or the job's JobTemp going over JOBTEMP_MAX_BYTES) falls
        # back to original-only. See gui._run_pipeline_steps.
        self.keep_all_steps_var = tk.BooleanVar(
            value=JOBTEMP_KEEP_ALL_STEPS_DEFAULT
        )

        # the four content rows below live in ONE grid container so their
        # order can flip between the narrow single-column stack (today's
        # order — correct while both AgentPanels share the row, GUI rework
        # Phase 12's ~half-width columns) and a two-column-dense fill —
        # switches LEFT, dropdowns RIGHT — used while THIS is the sole
        # visible panel (owner 2026-07-21 layout fix). See
        # _apply_dense_columns/set_dense_columns below: only grid() calls
        # move these FOUR EXISTING frames — every widget inside keeps its
        # exact parent row, variable and command.
        self._content = ttk.Frame(self)
        self._content.pack(fill="x")

        self._row_dropdowns = ttk.Frame(self._content)
        ttk.Label(self._row_dropdowns, text="Background:").pack(side="left")
        rounded_combo(
            self._row_dropdowns, BACKGROUND_CHOICES, self.background_var,
            width=105,
        ).pack(side="left", padx=(2, 10))
        ttk.Label(self._row_dropdowns, text="New chat:").pack(side="left")
        rounded_combo(
            self._row_dropdowns, NEW_CHAT_CHOICES, self.new_chat_var,
            width=100,
        ).pack(side="left", padx=(2, 0))

        # the Style dropdown — a primary per-generation choice like
        # Background, so it lives in the ALWAYS-VISIBLE area, not under the
        # Settings gear (owner 2026-07-19)
        self._row_style = ttk.Frame(self._content)
        ttk.Label(self._row_style, text="Style:").pack(side="left")
        rounded_combo(
            self._row_style, STYLE_CHOICES, self.style_var, width=150,
        ).pack(side="left", padx=(2, 0))

        self._row_switches1 = ttk.Frame(self._content)
        rounded_switch(
            self._row_switches1, "BG removal", self.bg_removal_var,
        ).pack(side="left")
        rounded_switch(self._row_switches1, "Crop", self.crop_var).pack(
            side="left", padx=8
        )
        rounded_switch(
            self._row_switches1, "Upscale", self.upscale_var,
        ).pack(side="left")

        self._row_switches2 = ttk.Frame(self._content)
        rounded_switch(
            self._row_switches2, "Report txt", self.report_var,
        ).pack(side="left")
        rounded_switch(
            self._row_switches2, "Safer retry", self.safer_var,
        ).pack(side="left", padx=8)
        rounded_switch(
            self._row_switches2, "Continue nudge", self.continue_nudge_var,
        ).pack(side="left")
        # the parallel Checker AI (GUI rework Phase 16) sits right beside
        # Safer retry/Continue nudge — the owner's other "watch this run
        # and self-correct" switches — even though it works differently
        # (checks the SAVED image on a background thread instead of
        # reacting to a refusal/stall; see PainterGui._maybe_spawn_checker)
        rounded_switch(
            self._row_switches2, "AI checker", self.checker_var,
        ).pack(side="left", padx=8)

        # narrow (both sites visible) by default — matches the grid this
        # constructor just built above byte-for-byte; PainterGui.
        # _relayout_agents flips this the moment a visibility change makes
        # this the sole visible panel (or restores both).
        self._dense = False
        self._apply_dense_columns()

        row = ttk.Frame(self)
        row.pack(fill="x", pady=(6, 2))
        self.btn_start = rounded_button(
            row, "Start", command=partial(on_start, site_key),
            kind="success", icon_name="start", width=90,
        )
        self.btn_start.pack(side="left")
        # the pause toggle (owner 2026-07-21) — a plain neutral button
        # (no filled/outline availability dance like Start/Stop below):
        # its label alone flips Pause <-> Resume, always clickable.
        self.btn_pause = rounded_button(
            row, "Pause", command=partial(on_pause, site_key),
            kind="secondary", width=70,
        )
        self.btn_pause.pack(side="left", padx=6)
        self.btn_stop = rounded_button(
            row, "Stop", command=partial(on_stop, site_key),
            kind="danger-outline", width=70,
        )
        self.btn_stop.pack(side="left", padx=6)
        # this agent's OWN Settings gear (owner 2026-07-19): the gear icon
        # + a state caret; it shows/hides THIS panel's fine-tune (pause +
        # action delay + upscale gate) independently of the other site.
        self._settings_btn = rounded_button(
            row, SETTINGS_GLYPH_COLLAPSED, command=self._toggle_settings,
            icon_name="settings",
        )
        self._settings_btn.pack(side="right")
        # every Start/Stop pair this agent owns (the panel's own pair plus
        # the collapsed-strip pair added by build_compact); set_run_state
        # styles ALL of them so both views always agree on availability
        self._button_pairs = [(self.btn_start, self.btn_stop)]
        self.set_run_state(running=False)

        # the collapsible fine-tune block (pause + action delay + upscale
        # gate) — built last so it sits at the panel's bottom; hidden until
        # this agent's own Settings gear expands it
        self._build_finetune()
        self._apply_finetune_visibility()

        # this panel's embedded AspectRatioCanvas needs redraw_theme() on
        # every live Day/Night flip (GUI rework Phase 8 — see apply_theme's
        # own docstring for why AgentPanel registers here despite not
        # being a Toplevel); never unregistered — build-once, same
        # lifetime as the app itself, like every dashboard JobPanel.
        THEME_TOPLEVELS.append(self)
        self.bind("<Destroy>", self._on_destroy)

    def _apply_dense_columns(self) -> None:
        """Regrid the four content rows (``_row_dropdowns``,
        ``_row_style``, ``_row_switches1``, ``_row_switches2``) between
        the narrow single-column stack (today's order — correct while
        both AgentPanels share the row, GUI rework Phase 12's
        ~half-width columns) and a two-column-dense fill — switches
        LEFT, dropdowns RIGHT — used while this is the SOLE visible
        panel (owner 2026-07-21 layout fix: the panel then spans the
        WHOLE controls width, and the old single stack left it half
        empty). Only ``grid()`` calls on these four EXISTING frames —
        nothing is created, destroyed or reparented, so every
        switch/combo inside keeps its exact variable and command."""
        rows = (
            self._row_dropdowns, self._row_style,
            self._row_switches1, self._row_switches2,
        )
        for w in rows:
            w.grid_forget()
        if self._dense:
            self._row_switches1.grid(row=0, column=0, sticky="ew", pady=2)
            self._row_switches2.grid(row=1, column=0, sticky="ew", pady=2)
            self._row_dropdowns.grid(
                row=0, column=1, sticky="ew", pady=2,
                padx=(DENSE_COL_GAP_PX, 0),
            )
            self._row_style.grid(
                row=1, column=1, sticky="ew", pady=2,
                padx=(DENSE_COL_GAP_PX, 0),
            )
            self._content.columnconfigure(0, weight=1)
            self._content.columnconfigure(1, weight=1)
        else:
            self._row_dropdowns.grid(row=0, column=0, sticky="ew", pady=2)
            self._row_style.grid(row=1, column=0, sticky="ew", pady=2)
            self._row_switches1.grid(row=2, column=0, sticky="ew", pady=2)
            self._row_switches2.grid(row=3, column=0, sticky="ew", pady=2)
            self._content.columnconfigure(0, weight=1)
            self._content.columnconfigure(1, weight=0)

    def set_dense_columns(self, dense: bool) -> None:
        """``PainterGui._relayout_agents`` drives this off the KNOWN
        visible-count state (GUI rework Phase 12's own
        ``_visible_agent_columns``) — ``dense=True`` only while this is
        the SOLE visible AgentPanel (the panel then spans the full
        controls width); ``dense=False`` — the original stacked order —
        while both sites share the row (each panel is already only
        ~half width there, so the old left-hugging layout is not a
        Rule #16 problem). A deliberate visible-COUNT switch, never a
        ``<Configure>`` width probe (fragile, and this state is already
        known exactly)."""
        if dense == self._dense:
            return
        self._dense = dense
        self._apply_dense_columns()

    def _build_finetune(self) -> None:
        """This agent's collapsible FINE-TUNE area (owner 2026-07-19),
        hidden behind its Settings gear: the PAUSE range, the ACTION-DELAY
        range, and the UPSCALE GATE. Built into ``self._finetune_box`` and
        left UNPACKED — ``_apply_finetune_visibility`` packs it in when
        the gear expands.

        The upscale gate (GUI rework Phase 6) is ONE min-SIDE spinner —
        the smaller side's target minimum in px, replacing the old
        separate min-W/min-H fields — plus an embedded ``FilterEditor``
        deciding WHICH images qualify, pre-seeded with today's aspect
        gate as a single Aspect (range) condition. ``upscale_params()``
        resolves the two into ``upscale_if_small``'s kwargs."""
        box = ttk.Frame(self)
        self._finetune_box = box

        row = ttk.Frame(box)
        row.pack(fill="x", pady=2)
        ttk.Label(row, text="pause", width=12).pack(side="left")
        Spinner(row, self.pause_min_var, step=1.0).pack(side="left")
        ttk.Label(row, text="–").pack(side="left", padx=2)
        Spinner(row, self.pause_max_var, step=1.0).pack(side="left")
        ttk.Label(row, text="s").pack(side="left", padx=(2, 0))

        row = ttk.Frame(box)
        row.pack(fill="x", pady=2)
        ttk.Label(row, text="action delay", width=12).pack(side="left")
        Spinner(row, self.act_min_var, step=0.1).pack(side="left")
        ttk.Label(row, text="–").pack(side="left", padx=2)
        Spinner(row, self.act_max_var, step=0.1).pack(side="left")
        ttk.Label(row, text="s").pack(side="left", padx=(2, 0))

        # the Force Aspect Ratio pipeline step (GUI rework Phase 8) — a
        # deliberate DEFORM to an exact target ratio, run AFTER Crop and
        # BEFORE Upscale (PainterGui._compose_post_save's new order:
        # BG -> Crop -> Aspect -> Upscale). Default OFF. The target W/H
        # is edited two-way with the SAME AspectRatioCanvas the
        # standalone 'Aspect ratio…' tool's dialog uses (Phase 5) — the
        # entries drive the canvas, dragging an edge drives them back.
        ttk.Label(
            box, text="Force Aspect Ratio (this site):", style="Head.TLabel"
        ).pack(anchor="w", pady=(4, 0))
        row = ttk.Frame(box)
        row.pack(fill="x", pady=2)
        rounded_switch(row, "Force to ratio", self.force_aspect_var).pack(
            side="left"
        )

        fa_fields = ttk.Frame(box)
        fa_fields.pack(fill="x", pady=2)
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

        # its own row below the W/H fields (not beside them, like the
        # standalone dialog can afford) — this panel's column is
        # narrower than a free-standing modal
        canvas_row = ttk.Frame(box)
        canvas_row.pack(fill="x", pady=(2, 0))
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

        # per-agent disk-usage choice for the pipeline's per-step backups
        # (GUI rework Phase 8) — see gui._run_pipeline_steps.
        row = ttk.Frame(box)
        row.pack(fill="x", pady=(6, 2))
        rounded_switch(
            row, "Keep every pipeline step (uses more disk)",
            self.keep_all_steps_var,
        ).pack(side="left")

        # the whole Upscale-gate sub-block (GUI rework Phase 12): makes
        # sense ONLY while the Upscale switch itself is on, so it lives
        # in its OWN sub-frame, packed/unpacked by
        # _apply_upscale_gate_visibility — independently of
        # settings_collapsed_var (this sub-frame is a CHILD of ``box``;
        # hiding/showing ``box`` itself never touches a child's own
        # pack state, so the two toggles compose like a plain AND: only
        # visible when BOTH the Settings gear is expanded AND Upscale
        # is on).
        self._upscale_gate_box = ttk.Frame(box)

        ttk.Label(
            self._upscale_gate_box, text="Upscale gate (this site):",
            style="Head.TLabel",
        ).pack(anchor="w", pady=(4, 0))

        row = ttk.Frame(self._upscale_gate_box)
        row.pack(fill="x", pady=2)
        ttk.Label(row, text="min side", width=8).pack(side="left")
        Spinner(row, self.up_minside_var, step=UPSCALE_MINDIM_STEP).pack(
            side="left"
        )
        ttk.Label(
            row, text="px (the smaller side reaches this)"
        ).pack(side="left", padx=(4, 0))

        # WHICH images qualify — a stacked FilterEditor (Phase 4) sharing
        # the app-wide preset library, seeded with today's aspect gate
        self.upscale_filter = FilterEditor(
            self._upscale_gate_box,
            conditions=self._default_upscale_conditions,
            presets=self._filter_presets,
            on_presets_changed=self._on_filter_presets_changed,
        )
        self.upscale_filter.pack(fill="x", pady=(2, 0))

        # live show/hide as Upscale itself is flipped — even while the
        # Settings gear stays expanded (GUI rework Phase 12); also
        # covers a settings-restore .set() (apply_settings, via _vars())
        # since a trace fires on every write, not only interactive ones
        self.upscale_var.trace_add(
            "write", lambda *_a: self._apply_upscale_gate_visibility()
        )
        self._apply_upscale_gate_visibility()  # correct initial state

        # the Fixer AI (GUI rework Phase 20) — makes sense only while the
        # parallel Checker AI is on (nothing to fix without a check), so
        # it lives in its OWN sub-frame, packed/unpacked by
        # _apply_fixer_visibility on a checker_var trace — the SAME
        # "independent of the gear's own collapse" composition the
        # Upscale gate sub-block above already uses.
        self._fixer_box = ttk.Frame(box)
        ttk.Label(
            self._fixer_box, text="Fixer AI (this site):",
            style="Head.TLabel",
        ).pack(anchor="w", pady=(4, 0))
        row = ttk.Frame(self._fixer_box)
        row.pack(fill="x", pady=2)
        rounded_switch(row, "Auto-fix flagged images", self.fixer_var).pack(
            side="left"
        )
        ttk.Label(row, text="via", width=4).pack(side="left", padx=(8, 0))
        rounded_combo(
            row, FIXER_MODE_CHOICES, self.fixer_mode_var, width=90,
        ).pack(side="left")
        ttk.Label(
            self._fixer_box,
            text="API runs alongside the next generation; Website is"
            " QUEUED for 'Send flagged to generator' (the tab is busy"
            " generating).",
            style="Muted.TLabel", wraplength=DENSE_COL_WRAP_PX,
        ).pack(anchor="w", pady=(0, 2))

        self.checker_var.trace_add(
            "write", lambda *_a: self._apply_fixer_visibility()
        )
        self._apply_fixer_visibility()  # correct initial state

    def _apply_fixer_visibility(self) -> None:
        """Reflect ``checker_var`` onto the Fixer-AI sub-block (GUI
        rework Phase 20) — mirrors ``_apply_upscale_gate_visibility``
        exactly: plain pack/pack_forget on every trace fire (an
        interactive click through the checker switch AND a silent
        settings restore alike), independent of the gear's own
        collapse state."""
        if self.checker_var.get():
            self._fixer_box.pack(fill="x")
        else:
            self._fixer_box.pack_forget()

    def _apply_upscale_gate_visibility(self) -> None:
        """Reflect ``upscale_var`` onto the Upscale-gate sub-block (GUI
        rework Phase 12): the min-side spinner + its FilterEditor are
        meaningless once Upscale itself is off, so they disappear even
        if the Settings gear stays expanded. Plain pack/pack_forget, no
        smooth_transition — unlike _toggle_settings's own deliberate
        owner-click animation, this fires from a trace on EVERY write
        (an interactive click through the switch AND a silent settings
        restore alike), so it stays as unobtrusive as
        _apply_finetune_visibility's own plain reflect."""
        if self.upscale_var.get():
            self._upscale_gate_box.pack(fill="x")
        else:
            self._upscale_gate_box.pack_forget()

    def _apply_finetune_visibility(self) -> None:
        """Reflect ``settings_collapsed_var``: pack or unpack this agent's
        fine-tune block and set the gear's state caret. The nested body's
        size change lets the outer ScrollFrame recompute its region."""
        collapsed = self.settings_collapsed_var.get()
        if collapsed:
            self._finetune_box.pack_forget()
        else:
            self._finetune_box.pack(fill="x", pady=(2, 0))
        self._settings_btn.configure(
            text=SETTINGS_GLYPH_COLLAPSED if collapsed
            else SETTINGS_GLYPH_EXPANDED
        )

    def _toggle_settings(self) -> None:
        """The gear: flip THIS agent's fine-tune visibility, independently
        of the other site, behind the shared snapshot cover (the reveal
        moves everything below the panel — bare, it lands as one hard
        jump). The var change persists via its own trace. The re-fit
        (``_on_layout_change``) runs INSIDE the covered mutate, alongside
        the pack/pack_forget itself, so the outer ScrollFrame's
        scrollregion settles hidden behind the same cover — never a
        visible post-fade jump."""
        self.settings_collapsed_var.set(
            not self.settings_collapsed_var.get()
        )

        def mutate() -> None:
            self._apply_finetune_visibility()
            self._on_layout_change()

        smooth_transition(self.winfo_toplevel(), mutate)

    def _on_force_aspect_canvas_drag(self, w: int, h: int) -> None:
        """``AspectRatioCanvas.on_change`` — a drag mirrored into the W/H
        entries (whose own trace calls back into ``set_ratio``, a no-op
        echo — see that method's docstring). Same pattern as
        ``AspectRatioDialog._on_canvas_drag``."""
        self.force_aspect_w_var.set(str(w))
        self.force_aspect_h_var.set(str(h))

    def _on_force_aspect_wh_typed(self, *_args) -> None:
        """Live-reshape the canvas as the owner types a new W/H. A bad
        or incomplete value (mid-edit) is a normal typing state, not an
        error — silently skipped, same as
        ``AspectRatioDialog._on_wh_typed``; final validation happens in
        ``force_aspect_ratio()`` on Start."""
        try:
            w = int(self.force_aspect_w_var.get().strip())
            h = int(self.force_aspect_h_var.get().strip())
        except ValueError:
            return
        if w <= 0 or h <= 0:
            return
        self._force_aspect_canvas.set_ratio(w, h)

    def force_aspect_ratio(self) -> tuple[int, int]:
        """The Force-Aspect target ratio — ValueError propagates to the
        caller's Start validation, same contract as ``upscale_params()``
        / ``pace_floats()``."""
        return (
            int(self.force_aspect_w_var.get()),
            int(self.force_aspect_h_var.get()),
        )

    def apply_theme(self) -> None:
        """Registered in ``THEME_TOPLEVELS`` (GUI rework Phase 8) even
        though this panel is not a Toplevel — that list is really just
        "objects with their own apply_theme() a flip must reach", and
        AgentPanel is BUILD-ONCE / never destroyed before app exit, same
        lifetime as every dashboard JobPanel. Needed because
        ``AspectRatioCanvas`` draws its accent/label straight from the
        active theme (see its own docstring) — this host is a normal,
        non-modal part of the main window (like its sibling host,
        ``AspectSettingsPanel``, GUI rework Phase 14), so a Day/Night
        flip while the fine-tune box is expanded must repaint it too."""
        self._force_aspect_canvas.redraw_theme()

    def _on_destroy(self, event) -> None:
        if event.widget is self and self in THEME_TOPLEVELS:
            THEME_TOPLEVELS.remove(self)

    def upscale_params(self) -> dict:
        """The upscale gate's engine kwargs (GUI rework Phase 6):
        ``_upscale_params_from_side_and_filter`` over the min-side
        spinner + the embedded FilterEditor's aspect condition.
        ValueError propagates to the caller's Start validation — from
        EITHER the spinner (not a number) or the FilterEditor (an
        unparsable row, see ``FilterEditor.get_conditions``). Non-aspect
        conditions in the same filter are NOT reflected in this dict —
        see ``upscale_conditions()`` and ``_gate_and_upscale``."""
        min_side = int(float(self.up_minside_var.get()))
        return _upscale_params_from_side_and_filter(
            min_side, self.upscale_filter.get_conditions()
        )

    def upscale_conditions(self) -> list[filters.FilterCondition]:
        """The upscale gate's FULL stacked filter, exactly as currently
        edited (root Rule #1: the caller uses this — not just
        ``upscale_params()``'s narrower kwargs — to honor stacked non-
        aspect conditions via ``filters.matches()``, see
        ``_gate_and_upscale``). ValueError propagates like
        ``upscale_params()``."""
        return self.upscale_filter.get_conditions()

    def set_run_state(
        self, running: bool, pending_restart: bool = False
    ) -> None:
        """Start is available unless the site runs; Stop is available
        while it runs OR while a quota auto-restart is pending (Stop
        then cancels the pending restart). Styles every registered
        button pair (full panel + collapsed strip).

        GUI rework Phase 12: the SAME "running or pending_restart"
        window also (a) greys out the show/hide toggle — this panel is
        the only place Stop/Pause live for this site, so hiding it
        while either is needed would strand the job — and (b), since a
        HIDDEN panel's site can still go live without a click (a quota
        auto-restart, an AI-check resend both call PainterGui.
        _start_site directly), forces visible_var back to True and logs
        why whenever that happens, so the control and what is on screen
        never silently disagree."""
        for start_btn, stop_btn in self._button_pairs:
            style_action_button(start_btn, "success", not running)
            style_action_button(
                stop_btn, "danger", running or pending_restart
            )
        locked = running or pending_restart
        if locked and not self.visible_var.get():
            self._on_log(
                f"{SITES[self.site_key].name}: un-hiding its panel — a"
                " live job needs its Start/Stop/Pause controls"
            )
            self.visible_var.set(True)
        if self._visible_btn is not None:
            self._visible_btn.configure(
                state="disabled" if locked else "normal"
            )

    def set_paused(self, is_paused: bool) -> None:
        """Reflect this agent's pause toggle onto its OWN btn_pause
        label (owner 2026-07-21) — the paused STATE text lives on the
        dashboard DashPanel's state line instead (JobPanel.set_paused,
        reached through PainterGui.panels[site_key]; this panel has no
        state line of its own)."""
        self.btn_pause.configure(text="Resume" if is_paused else "Pause")

    def build_compact(self, parent) -> ttk.Frame:
        """A thin '[logo] Name [Start][Stop]' cluster for the collapsed
        view. Its Start/Stop reuse the panel's own commands and join
        _button_pairs so set_run_state keeps them in the same
        filled/outline availability as the full panel's pair."""
        cluster = ttk.Frame(parent)
        ctk.CTkLabel(
            cluster, text="", image=icon(JOB_LOGO[self.site_key]),
            width=22, fg_color="transparent", bg_color=theme_pair("bg"),
        ).pack(side="left", padx=(0, 4))
        ttk.Label(
            cluster, text=SITES[self.site_key].name, style="Head.TLabel"
        ).pack(side="left", padx=(0, 8))
        start = rounded_button(
            cluster, "Start",
            command=partial(self._on_start, self.site_key),
            kind="success", icon_name="start", width=90,
        )
        start.pack(side="left")
        stop = rounded_button(
            cluster, "Stop",
            command=partial(self._on_stop, self.site_key),
            kind="danger-outline", width=70,
        )
        stop.pack(side="left", padx=6)
        self._button_pairs.append((start, stop))
        return cluster

    def build_visibility_toggle(self, parent) -> ctk.CTkSwitch:
        """This site's entry in the shared "Show:" row above both
        AgentPanels (GUI rework Phase 12, spec item 3A) — a plain switch
        bound to ``visible_var`` so the row and the panel can never
        silently disagree (Tk's ``variable=`` binding keeps them in
        lockstep both ways: a click here flips the var, a programmatic
        ``.set()`` — settings restore, or set_run_state's own forced
        re-show — updates the switch). Kept as ``self._visible_btn`` so
        ``set_run_state`` can grey it out while this site's job needs
        its own panel reachable."""
        self._visible_btn = rounded_switch(
            parent, SITES[self.site_key].name, self.visible_var,
        )
        return self._visible_btn

    def pace_floats(self) -> tuple[float, float, float, float]:
        """The four pace numbers — ValueError propagates to the
        caller's validation message."""
        return (
            float(self.pause_min_var.get()),
            float(self.pause_max_var.get()),
            float(self.act_min_var.get()),
            float(self.act_max_var.get()),
        )

    # --- settings round-trip -------------------------------------------

    def _vars(self) -> dict[str, tk.Variable]:
        return {
            "background": self.background_var,
            "style": self.style_var,
            "bg_removal": self.bg_removal_var,
            "crop": self.crop_var,
            "upscale": self.upscale_var,
            "report": self.report_var,
            "safer_retry": self.safer_var,
            "continue_nudge": self.continue_nudge_var,
            "checker": self.checker_var,
            "fixer": self.fixer_var,
            "fixer_mode": self.fixer_mode_var,
            "new_chat": self.new_chat_var,
            "pause_min": self.pause_min_var,
            "pause_max": self.pause_max_var,
            "act_min": self.act_min_var,
            "act_max": self.act_max_var,
            "up_minside": self.up_minside_var,
            "settings_collapsed": self.settings_collapsed_var,
            "force_aspect": self.force_aspect_var,
            "force_aspect_w": self.force_aspect_w_var,
            "force_aspect_h": self.force_aspect_h_var,
            "keep_all_steps": self.keep_all_steps_var,
            "visible": self.visible_var,
        }

    def persist_vars(self) -> list[tk.Variable]:
        """Every tk.Variable this panel auto-saves on write (see
        ``PainterGui._wire_persistence``). The upscale FilterEditor's
        condition stack is NOT a tk.Variable — it has no per-keystroke
        trace — so an edit there alone waits for the NEXT debounced
        save (triggered by any other field) or the app's close-time
        save (``PainterGui._on_close`` always calls ``_save_now()``,
        which reads ``get_settings()`` fresh); it is never silently
        lost, just not INSTANTLY scheduled like the fields below."""
        return list(self._vars().values())

    def get_settings(self) -> dict:
        data = {key: var.get() for key, var in self._vars().items()}
        # the upscale gate's FilterEditor (GUI rework Phase 6) — read
        # fresh every call, same as every other "live widget state"
        # persisted field; see persist_vars()'s docstring for why this
        # one has no per-keystroke save trace
        data["up_filter_conditions"] = [
            filters.condition_to_dict(c)
            for c in self.upscale_filter.get_conditions()
        ]
        return data

    def apply_settings(
        self, stored: dict,
        upscale_conditions: list[filters.FilterCondition] | None = None,
    ) -> None:
        """Missing keys keep the current defaults; the restored collapse
        state is reflected into the panel.

        ``upscale_conditions`` (GUI rework Phase 6) is the ALREADY-
        PARSED replacement for the upscale FilterEditor's seeded
        default — ``None`` (a fresh settings.json, or a pre-Phase-6 one
        with nothing usable to migrate) leaves the widget's own
        construction-time default untouched, exactly matching every
        other field's "missing key = keep default" contract. The
        CALLER (``PainterGui._apply_settings``) owns parsing/migrating
        the raw JSON — see ``_migrate_legacy_upscale_gate`` and
        ``_parse_condition_dicts`` — because that needs a log sink this
        widget does not carry."""
        variables = self._vars()
        for key in self._PERSIST:
            if key in stored:
                variables[key].set(stored[key])
        if upscale_conditions is not None:
            self.upscale_filter.set_conditions(upscale_conditions)
        self._apply_finetune_visibility()
