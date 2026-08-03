"""``AgentPanel`` — one site's own control panel (Website GEN).

Split out of ``gui/__init__.py`` (Rule #3, god-file refactor step
4/8). The per-site background/style dropdowns, the three composable
post-save switches (BG removal / Crop / Upscale), Report, Safer
retry, Continue nudge, the parallel Checker/Fixer AI toggles, the
Force Aspect Ratio block and the pause/action-delay fine-tune, plus
its own Start/Pause/Stop.

The shared layout constants (``DENSE_COL_WRAP_PX``,
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
    BACKGROUND_CUSTOM,
    BACKGROUND_DEFAULT,
    BG_COLOR_DEFAULT,
    BG_COLOR_TOLERANCE_PCT,
    BG_MODE_COLOR,
    BG_MODE_DEFAULT,
    BG_MODE_LABEL,
    BG_REACH_DEFAULT,
    BG_REACH_LABEL,
    DEGRADE_ASK,
    HELPER_CHOICES,
    HELPER_DEFAULTS,
    DEGRADE_CHOICES,
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
from .theme import THEME_TOPLEVELS
from .tool_panels import ASPECT_DIALOG_ENTRY_W, DENSE_COL_WRAP_PX
from .widgets import (
    ExpandableSwitch,
    ExpanderAccordion,
    FlowRow,
    Spinner,
    quiet_restore,
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
        "safer_retry", "continue_nudge", "checker", "checker_prompt",
        "fixer", "fixer_mode",
        # F2 (owner 2026-07-29): what a run does when the site drops to
        # a weaker model (Gemini's Flash-Lite banner) — ask / continue /
        # wait; see config.DEGRADE_CHOICES
        "degrade",
        # F7 (owner 2026-07-29): the per-agent prompt-helper toggles +
        # the custom-background hex
        "helper_no_mirror", "helper_no_empty_space", "helper_no_grainy",
        "background_custom",
        # UI-SKETCH (owner 2026-07-29): BG removal's own fine-tune
        "bg_mode", "bg_color", "bg_tolerance", "bg_reach",
        "new_chat", "pause_min",
        "pause_max", "act_min", "act_max",
        # ("settings_collapsed" retired with the gear, UI-SKETCH
        # 2026-07-29 — every fine-tune lives under its own switch's
        # expander now; an old stored key is simply ignored)
        # per-agent upscale-gate fine-tune (owner 2026-07-19; GUI rework
        # Phase 6: the old up_minw/up_minh/up_aspmin/up_aspmax four-field
        # gate collapsed into ONE min-side spinner — the embedded
        # FilterEditor's condition stack persists SEPARATELY, as
        # 'up_filter_conditions' (not a plain tk.Variable, so it is
        # handled explicitly in get_settings/apply_settings below, not
        # through this tuple)
        "up_minside",
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
        self._head_name = ttk.Label(head, text=site.name, style="Head.TLabel")
        self._head_name.pack(side="left")
        # the OTHER sites' logos (owner 2026-08-03: "zašto nema logo
        # Gemini-ja"): the shared header already NAMES both sites, so
        # it must SHOW both — one label per other site, built here and
        # left unpacked; set_shared_header packs them between this
        # panel's own logo and the name, in the same sorted order the
        # names are joined in.
        self._extra_logos = [
            ctk.CTkLabel(
                head, text="", image=icon(JOB_LOGO[key]), width=22,
                fg_color="transparent", bg_color=theme_pair("bg"),
            )
            for key in sorted(SITES)
            if key != site_key
        ]
        # F2 cooldown INFO (owner 2026-07-29): a persisted quota reset
        # shown right beside the site's name during setup — information
        # only, it NEVER gates the Start button
        self.cooldown_var = tk.StringVar(value="")
        ttk.Label(
            head, textvariable=self.cooldown_var, style="Muted.TLabel",
        ).pack(side="left", padx=(8, 0))
        self.configure(labelwidget=head, padding=6)

        # F4c (owner 2026-07-29): "default" resolves per site at Start
        # (chatgpt transparent / gemini white) — ONE shared setup can
        # drive both sites and each still gets its right background
        self.background_var = tk.StringVar(value=BACKGROUND_DEFAULT)
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
        # F6 (REWORK.md, owner 2026-07-29): the checker's own fine-tune —
        # ON by default (the new default behavior: the parallel checker
        # asks for BOTH the banal-defects check AND a prompt-match
        # judgement against the item's own sheet prompt); OFF drops back
        # to yesterday's quality-only check (ai.check_image/
        # check_one_image's prompt=None path). See
        # PainterGui._maybe_spawn_checker/_run_checker_one for how this
        # reaches the actual API call.
        self.checker_prompt_var = tk.BooleanVar(value=True)
        # the Fixer AI (GUI rework Phase 20, owner's UV/prompt.txt item 1:
        # "ako ustanovi gresku salje fikseru da ispravi ... u situaciji ako
        # su oba ukljucena" — "both" being the checker AND the fixer). OFF
        # by default (an opt-in COST layered on TOP of the checker's own
        # opt-in cost); it lives INSIDE the AI-checker switch's own
        # expander (_build_checker_sub), so it is reachable only while
        # the checker itself is on — UI-SKETCH 2026-07-29. "api" mode
        # dispatches ai.edit_image on a background thread the instant a
        # checked image comes back flagged — a plain REST call, so it
        # genuinely runs IN PARALLEL with this site's own next-image
        # generation (see PainterGui._maybe_spawn_fixer/_run_fixer_api).
        # "website" mode never drives driver.submit_with_image from the auto
        # path — the site's browser tab is busy generating the NEXT image
        # at that exact instant (one tab, one operation) — it QUEUES the
        # item instead (see PainterGui._queue_website_fix's own docstring
        # for exactly why, and for the manual WEBSITE FIX button that DOES
        # drive the browser, owner-triggered, see DocWindow/_run_website_fix).
        self.fixer_var = tk.BooleanVar(value=False)
        self.fixer_mode_var = tk.StringVar(value=FIXER_MODE_API)
        # F2: the model-degradation choice (Gemini Flash-Lite banner)
        self.degrade_var = tk.StringVar(value=DEGRADE_ASK)
        # F7 (owner 2026-07-29): the per-agent PROMPT HELPERS — this
        # site's pre-F7 baked law starts ON (HELPER_DEFAULTS), so the
        # default suffix stays byte-identical; the rest start OFF
        self.helper_vars = {
            key: tk.BooleanVar(
                value=key in HELPER_DEFAULTS.get(site_key, ())
            )
            for key in HELPER_CHOICES
        }
        # F7: the "custom" background's picked color (hex)
        self.background_custom_var = tk.StringVar(value="#ffffff")
        # UI-SKETCH (owner 2026-07-29): BG removal's own per-agent
        # fine-tune — the SAME knobs the standalone BG tool exposes,
        # passed straight into painter.postprocess.remove_background
        self.bg_mode_var = tk.StringVar(value=BG_MODE_DEFAULT)
        self.bg_color_var = tk.StringVar(value=BG_COLOR_DEFAULT)
        self.bg_tolerance_var = tk.StringVar(
            value=f"{BG_COLOR_TOLERANCE_PCT:g}"
        )
        self.bg_reach_var = tk.StringVar(value=BG_REACH_DEFAULT)
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
        # (built in _build_upscale_sub, seeded with today's aspect gate
        # as a single Aspect (range) condition) deciding WHICH images
        # qualify. Lives in the Upscale switch's own expander.
        self.up_minside_var = tk.StringVar(value=str(UPSCALE_MIN_SIDE_DEFAULT))
        # the upscale FilterEditor's SEED conditions — built once here so
        # _build_upscale_sub (called from the ExpandableSwitch below) and
        # a future re-seed both read the SAME default; not persisted (the
        # widget's live get_conditions() is what get_settings() reads).
        self._default_upscale_conditions = [
            filters.FilterCondition(
                kind=FILTER_KIND_ASPECT_RANGE, polarity=FILTER_POLARITY_IF,
                lo=UPSCALE_ASPECT_MIN, hi=UPSCALE_ASPECT_MAX,
            )
        ]
        # (the Settings-gear collapse state is GONE — UI-SKETCH
        # 2026-07-29: per-switch expanders replaced the gear)

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
        # embedded AspectRatioCanvas (built in _build_aspect_sub,
        # reusing Phase 5's editor) exactly like AspectRatioDialog's own
        # W/H entries + canvas.
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

        # the four groups below are FULL-WIDTH BANDS stacked vertically
        # (owner 2026-08-03, slika 1 — replacing the 2x2 grid of
        # 2026-08-03 morning): each band's switches FLOW and WRAP
        # (FlowRow) and its fine-tune opens into a full-width host
        # BELOW them, so no element is ever cut off the right edge.
        self._content = ttk.Frame(self)
        self._content.pack(fill="x")
        self._groups: list[ttk.Frame] = []  # Pipeline/Run/Pacing/Prompt
        self._flows: list[FlowRow] = []     # every band's flow row
        # panel-wide "only ONE fine-tune open" (owner 2026-08-03)
        self._accordion = ExpanderAccordion()

        # UI-SKETCH (owner 2026-07-29; regrouped 2026-08-03): the
        # settings are FOUR GROUPS — Pipeline / Run behavior / Pacing /
        # Prompt — each switch that owns fine-tune carrying its OWN
        # indented expand/collapse sub-panel (ExpandableSwitch: turning
        # ON auto-expands, the caret folds). The old global Settings
        # gear is GONE; everything it held now lives under its owning
        # switch — and Pacing, once a folded ExpandableSection inside
        # Run behavior, is now its OWN group, ALWAYS OPEN (owner
        # 2026-08-03: "Pacing uvek otvoren").
        # every ExpandableSwitch/Section is kept as a named field — the
        # expander IS this panel's fine-tune surface now that the gear
        # is gone, so its open/closed state has to stay reachable (the
        # settings round-trip, a future "expand all", and the tests
        # that pin the auto-expand contract all read these).
        flow, host = self._build_group(self._content, "Pipeline")
        self._sw_bg = ExpandableSwitch(
            flow, "BG removal", self.bg_removal_var,
            build_sub=self._build_bg_sub, eager=True,
            on_layout_change=self._on_layout_change,
            sub_host=host, accordion=self._accordion,
        )
        flow.add(self._sw_bg)
        flow.switch("Crop", self.crop_var)
        self._sw_aspect = ExpandableSwitch(
            flow, "Force aspect ratio", self.force_aspect_var,
            build_sub=self._build_aspect_sub, eager=True,
            on_layout_change=self._on_layout_change,
            sub_host=host, accordion=self._accordion,
        )
        flow.add(self._sw_aspect)
        self._sw_upscale = ExpandableSwitch(
            flow, "Upscale", self.upscale_var,
            build_sub=self._build_upscale_sub, eager=True,
            on_layout_change=self._on_layout_change,
            sub_host=host, accordion=self._accordion,
        )
        flow.add(self._sw_upscale)
        flow.switch(
            "Keep every pipeline step (more disk)", self.keep_all_steps_var,
        )

        flow, host = self._build_group(self._content, "Run behavior")
        flow.switch("Report txt", self.report_var)
        flow.switch("Safer retry", self.safer_var)
        flow.switch("Continue nudge", self.continue_nudge_var)
        self._sw_checker = ExpandableSwitch(
            flow, "AI checker", self.checker_var,
            build_sub=self._build_checker_sub, eager=True,
            on_layout_change=self._on_layout_change,
            sub_host=host, accordion=self._accordion,
        )
        flow.add(self._sw_checker)

        # Pacing — its OWN group, ALWAYS OPEN (owner 2026-08-03, UV
        # tačka 3; replacing the folded ExpandableSection that used to
        # sit inside Run behavior): the rows build straight into the
        # group body, no caret, nothing to miss before a Start
        flow, _host = self._build_group(self._content, "Pacing")
        self._build_pacing_sub(flow)

        flow, _host = self._build_group(self._content, "Prompt")
        cell = flow.cell()
        ttk.Label(cell, text="Background:").pack(side="left", padx=(0, 4))
        rounded_combo(
            cell, BACKGROUND_CHOICES, self.background_var, width=105,
        ).pack(side="left")
        # F7: the "custom" background color — picking "custom" opens
        # the color wheel; the swatch shows the hex, click reopens
        self._custom_swatch = tk.Label(cell, text="", width=8, cursor="hand2")
        self._custom_swatch.bind(
            "<Button-1>", lambda _e: self._pick_custom_background()
        )
        cell = flow.cell()
        ttk.Label(cell, text="Style:").pack(side="left", padx=(0, 4))
        rounded_combo(
            cell, STYLE_CHOICES, self.style_var, width=140,
        ).pack(side="left")
        cell = flow.cell()
        ttk.Label(cell, text="New chat:").pack(side="left", padx=(0, 4))
        rounded_combo(
            cell, NEW_CHAT_CHOICES, self.new_chat_var, width=100,
        ).pack(side="left")
        _HELPER_LABEL = {
            "no_mirror": "no mirror",
            "no_empty_space": "no empty space",
            "no_grainy": "no grainy",
        }
        # the helper switches are ordinary flow elements now (owner
        # 2026-08-03, slika 1): each one wraps on its own when the
        # width runs out, so no fixed 2-per-row grid to redo when a
        # fourth helper arrives — and none of them can be cut off.
        flow.add(ttk.Label(flow, text="Helpers:"))
        for key in HELPER_CHOICES:
            flow.switch(_HELPER_LABEL.get(key, key), self.helper_vars[key])

        self.background_var.trace_add(
            "write", lambda *_a: self._on_background_change()
        )
        self.background_custom_var.trace_add(
            "write", lambda *_a: self._render_custom_swatch()
        )
        self._render_custom_swatch()

        self._stack_groups()

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
        # UI-SKETCH (owner 2026-07-29): the global Settings gear is
        # GONE — every fine-tune lives under its owning switch's
        # expander (or the always-open Pacing group) above.
        # every Start/Stop pair this agent owns (the panel's own pair plus
        # the collapsed-strip pair added by build_compact); set_run_state
        # styles ALL of them so both views always agree on availability
        self._button_pairs = [(self.btn_start, self.btn_stop)]
        self.set_run_state(running=False)

        # this panel's embedded AspectRatioCanvas needs redraw_theme() on
        # every live Day/Night flip (GUI rework Phase 8 — see apply_theme's
        # own docstring for why AgentPanel registers here despite not
        # being a Toplevel); never unregistered — build-once, same
        # lifetime as the app itself, like every dashboard JobPanel.
        THEME_TOPLEVELS.append(self)
        self.bind("<Destroy>", self._on_destroy)

    def _build_group(self, parent, title: str):
        """One settings BAND (owner 2026-08-03, slika 1): a heading, a
        wrapping ``FlowRow`` of controls, and the full-width HOST the
        band's fine-tune opens into, below the (possibly wrapped) rows
        of controls. Returns ``(flow, host)``."""
        outer = ttk.Frame(parent)
        ttk.Label(outer, text=title, style="Head.TLabel").pack(
            anchor="w", pady=(2, 2)
        )
        flow = FlowRow(outer)
        flow.pack(fill="x")
        self._flows.append(flow)
        host = ttk.Frame(outer)
        host.pack(fill="x")
        self._groups.append(outer)
        return flow, host

    def _stack_groups(self) -> None:
        """Stack the four BANDS vertically, each at the panel's FULL
        width (owner 2026-08-03, slika 1 — "extra additional setup
        zauzima ceo width levog panela"). The old 2x2 grid halved every
        band's width, which is exactly what pushed Upscale's filter row
        and Force-aspect's canvas off the visible edge."""
        for i, w in enumerate(self._groups):
            w.grid(row=i, column=0, sticky="new", pady=(2, 4))
        self._content.columnconfigure(0, weight=1)

    def reflow(self) -> None:
        """Re-wrap every band for the current width — called on a font
        zoom, where each element's requested width changes but no
        <Configure> of the bands themselves has to follow."""
        for flow in self._flows:
            flow.reflow()

    # --- UI-SKETCH sub-panel builders (owner 2026-07-29) --------------
    # Each builds ONE switch's fine-tune into its ExpandableSwitch.sub
    # (eager: state like the FilterEditor stack and the aspect canvas
    # binding outlives the expander's visibility).

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
        """Run pacing: the paced pause range, the human action-delay
        range and the F2 on-degrade choice — THREE flow CELLS (owner
        2026-08-03, slika 1), so a narrow window wraps them onto
        further rows instead of cutting the last one off. Labels lost
        their fixed width=12 for the same reason: every px of the band
        is width some element can still use."""
        cell = flow.cell()
        ttk.Label(cell, text="pause").pack(side="left", padx=(0, 4))
        Spinner(cell, self.pause_min_var, step=1.0).pack(side="left")
        ttk.Label(cell, text="–").pack(side="left", padx=2)
        Spinner(cell, self.pause_max_var, step=1.0).pack(side="left")
        ttk.Label(cell, text="s").pack(side="left", padx=(2, 0))
        cell = flow.cell()
        ttk.Label(cell, text="action delay").pack(side="left", padx=(0, 4))
        Spinner(cell, self.act_min_var, step=0.1).pack(side="left")
        ttk.Label(cell, text="–").pack(side="left", padx=2)
        Spinner(cell, self.act_max_var, step=0.1).pack(side="left")
        ttk.Label(cell, text="s").pack(side="left", padx=(2, 0))
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

    def bg_params(self) -> dict:
        """BG removal's per-agent kwargs for ``remove_background``
        (UI-SKETCH, owner 2026-07-29) — read once at Start like every
        other setting; a bad tolerance number propagates loudly to the
        caller's validation."""
        return {
            "mode": self.bg_mode_var.get(),
            "color": self.bg_color_var.get() or BG_COLOR_DEFAULT,
            "tolerance_pct": float(self.bg_tolerance_var.get()),
            "reach": self.bg_reach_var.get(),
        }

    def helpers(self) -> tuple[str, ...]:
        """This agent's toggled prompt helpers, in HELPER_CHOICES
        order — what ``prompt_suffix(..., helpers=...)`` consumes."""
        return tuple(
            key for key in HELPER_CHOICES if self.helper_vars[key].get()
        )

    def _on_background_change(self) -> None:
        """Picking "custom" in the Background dropdown opens the color
        wheel once; the swatch beside the helpers row reopens it."""
        self._render_custom_swatch()
        if self.background_var.get() == BACKGROUND_CUSTOM:
            self._pick_custom_background()

    def _pick_custom_background(self) -> None:
        from tkinter import colorchooser

        picked = colorchooser.askcolor(
            initialcolor=self.background_custom_var.get() or "#ffffff",
            parent=self,
            title=f"{SITES[self.site_key].name} — custom background",
        )
        if picked and picked[1]:
            self.background_custom_var.set(picked[1])

    def _render_custom_swatch(self) -> None:
        """The swatch shows ONLY while Background == "custom" — its
        fill is the picked color, its text the hex, its foreground
        black/white by real luminance so the hex always reads."""
        if self.background_var.get() != BACKGROUND_CUSTOM:
            self._custom_swatch.pack_forget()
            return
        hex_color = self.background_custom_var.get() or "#ffffff"
        try:
            r, g, b = (
                int(hex_color[1:3], 16),
                int(hex_color[3:5], 16),
                int(hex_color[5:7], 16),
            )
        except (ValueError, IndexError):
            hex_color, (r, g, b) = "#ffffff", (255, 255, 255)
        luma = 0.299 * r + 0.587 * g + 0.114 * b
        self._custom_swatch.configure(
            text=hex_color, bg=hex_color,
            fg="#000000" if luma > 140 else "#ffffff",
        )
        if not self._custom_swatch.winfo_manager():
            self._custom_swatch.pack(side="left", padx=(10, 0))

    def set_shared_header(self, shared: bool) -> None:
        """F4c (owner 2026-07-29): while the both-sites shared editor
        is active, this (primary) panel's header names BOTH sites so
        it is obvious one setup drives the pair — and SHOWS both
        logos (owner 2026-08-03), not just this panel's own."""
        if shared:
            names = " + ".join(SITES[k].name for k in sorted(SITES))
            self._head_name.configure(text=f"{names} — shared settings")
            for logo in self._extra_logos:
                logo.pack(side="left", padx=(0, 4), before=self._head_name)
        else:
            self._head_name.configure(text=SITES[self.site_key].name)
            for logo in self._extra_logos:
                logo.pack_forget()

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
            "checker_prompt": self.checker_prompt_var,
            "fixer": self.fixer_var,
            "fixer_mode": self.fixer_mode_var,
            "degrade": self.degrade_var,
            "helper_no_mirror": self.helper_vars["no_mirror"],
            "helper_no_empty_space": self.helper_vars["no_empty_space"],
            "helper_no_grainy": self.helper_vars["no_grainy"],
            "background_custom": self.background_custom_var,
            "bg_mode": self.bg_mode_var,
            "bg_color": self.bg_color_var,
            "bg_tolerance": self.bg_tolerance_var,
            "bg_reach": self.bg_reach_var,
            "new_chat": self.new_chat_var,
            "pause_min": self.pause_min_var,
            "pause_max": self.pause_max_var,
            "act_min": self.act_min_var,
            "act_max": self.act_max_var,
            "up_minside": self.up_minside_var,
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
        """Missing keys keep the current defaults.

        The whole round-trip runs under ``quiet_restore`` (UI-SKETCH,
        owner 2026-07-29): a restored-ON switch must NOT auto-expand its
        fine-tune — Tk write-traces cannot tell a restore ``.set()``
        from a click, and without this the app would open with every ON
        switch's sub-panel unfolded instead of the compact panel the
        sketch asks for. A restored-OFF switch still folds an open one.

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
        with quiet_restore(*self._expanders()):
            variables = self._vars()
            for key in self._PERSIST:
                if key in stored:
                    variables[key].set(stored[key])
        if upscale_conditions is not None:
            self.upscale_filter.set_conditions(upscale_conditions)

    def _expanders(self) -> tuple[ExpandableSwitch, ...]:
        """Every switch that owns a fine-tune sub-panel (the UI-SKETCH
        table) — the restore-time auto-expand suppression reaches all
        of them through this ONE list, never four hand-written names."""
        return (
            self._sw_bg, self._sw_aspect, self._sw_upscale, self._sw_checker,
        )
