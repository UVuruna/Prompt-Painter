"""``ToolSettingsPanel`` — the shared chrome every standalone in-place
tool's settings panel is built from (GUI rework Phase 13): the input
picker (Folder… / Files… + the picked-input label), the shared
`FilterEditor` gate, the optional Advanced collapsible, and the
Start/Pause/Stop row with its run-state styling.

Split out of the single-file ``gui/tool_panels.py`` (root Rule #20,
2026-07-30) — one tool family per module now: [BG](bg.md),
[Geometry](geometry.md), [Image Checker](image_checker.md).

A subclass fills in the hooks: ``_build_extra`` (its own primary
control), ``_build_advanced`` (the engine knobs, only when
``HAS_ADVANCED``), ``build_func`` (the per-image callable the job runs)
and the ``_advanced_settings``/``_apply_advanced_settings`` pair for
persistence.
"""

from __future__ import annotations

import tkinter as tk
from pathlib import Path
from tkinter import filedialog, ttk
from typing import Callable

import customtkinter as ctk

from painter import filters
from painter.config import (
    JOB_LABEL,
    JOB_LOGO,
    iter_images,
    selection_base_and_rels,
    theme_pair,
)
from ..filter_editor import FilterEditor
from ..icons import icon
from ..theme import THEME_TOPLEVELS, smooth_transition
from ..widgets import rounded_button, style_action_button
from .layout import (
    DENSE_COL_GAP_PX,
    DENSE_COL_WRAP_PX,
    SETTINGS_GLYPH_COLLAPSED,
    SETTINGS_GLYPH_EXPANDED,
)


# ---------------------------------------------------------------------
# Standalone-tool settings panels (GUI rework Phase 13)
# ---------------------------------------------------------------------




class ToolSettingsPanel(ttk.Frame):
    """Base for a standalone in-place tool's PERSISTENT settings panel
    — all four tools now (BG removal / Crop, GUI rework Phase 13;
    Upscale / Aspect ratio, Phase 14, same treatment). Shown INLINE
    above Dashboard/Log while its tile is toggled open
    (``PainterGui._inline_kind`` — see ``PainterGui.
    _open_tool_panel``), the exact surface website_gen's own
    ``_controls_box`` already occupies (``_apply_running_layout``),
    generalized to a second panel family instead of forked.

    Owns: an input picker (**Folder…** — recursive via the shared
    ``iter_images``, matching every folder-based tool — or **Files…**,
    mirroring the Aspect tool's own Files/Folder choice), an optional
    **always-visible** subclass block (``_build_extra`` — e.g.
    Upscale's min-side spinner, Aspect's target-ratio canvas; base
    no-op), an embedded ``FilterEditor`` (Phase 4) narrowing WHICH
    images the run touches (optionally pre-seeded — ``_default_
    conditions``, base empty), an optional **Advanced** collapsible
    (the Settings-gear idiom ``AgentPanel._toggle_settings`` already
    established; ``HAS_ADVANCED = False`` skips building it entirely —
    Upscale/Aspect have no hidden engine knobs, only always-visible
    primary controls, so a gear that reveals nothing would be a dead
    affordance) exposing engine knobs the subclass contributes, an
    optional **footer** block (``_build_footer`` — e.g. Aspect's
    non-proportional-stretch warning, carried over from the old
    modal's confirm dialog; base no-op) shown just above the button
    row, and a Start/Pause/Stop row — Pause mirrors ``AgentPanel.
    btn_pause``: a plain label-only toggle, always clickable, never
    gated on run state (pausing before a job exists is harmless — a
    fresh Start always clears any stale pre-pause, see ``PainterGui.
    _launch_tool_worker``).

    **Stop** (GUI rework Phase 14, closing Phase 13's own flagged gap)
    mirrors ``AgentPanel.btn_stop``'s availability styling (filled
    while the job runs, disabled outline otherwise) and calls
    ``PainterGui._stop_tool`` — a "smart" stop: the worker
    (``_run_tool_job``, threaded a ``should_stop`` this phase, mirrors
    ``run_sheet``'s own pattern) finishes the in-flight image then
    halts; once it actually confirms the halt (``__tool_done__``, NOT
    synchronously on click — the worker may still be mid-image),
    ``PainterGui`` closes this tool's dashboard panel and clears its
    JobTemp (the existing ``_close_panel``, same as a manual Close)
    and returns to the Main Menu if that was the last active job
    (``_request_menu`` — Phase 11's OWN gate, unmodified: it only ever
    actually navigates once ``_active_kinds()`` is empty). This is a
    deliberate DIVERGENCE from a site's own Stop (which leaves its
    panel up for the owner to review before a manual Close, see
    gui.md's **Running view**) — a quick, disk-based tool run has
    nothing left worth reviewing once stopped, so "smart" here means
    "decisively finish the job", not "linger".

    Subclasses set ``SLOT`` and contribute ``_build_advanced``/
    ``build_func``/``_advanced_settings``/``_apply_advanced_settings``
    (Rule #5 — one shared body, not four near-identical panels);
    ``BgSettingsPanel``/``CropSettingsPanel`` additionally use
    ``_build_advanced`` for real (their engine knobs); ``Upscale
    SettingsPanel``/``AspectSettingsPanel`` set ``HAS_ADVANCED = False``
    and use ``_build_extra``/``_build_footer`` instead (see above) —
    ``_advanced_settings``/``_apply_advanced_settings`` still carry
    their own always-visible fields into the settings round-trip
    regardless (the hook name is about "subclass extra data", not
    literally the collapsible). Public surface ``PainterGui.
    _start_tool_from_panel`` reads: ``resolve_input() -> (Path,
    list[Path])`` (raises ``ValueError`` with an owner-facing
    message), ``get_conditions() -> list[FilterCondition]`` (proxies
    ``FilterEditor.get_conditions``, same raise contract),
    ``build_func() -> Callable[[Path, Log], str]`` (subclass hook —
    the engine call closed over THIS run's Advanced/extra overrides),
    ``set_run_state(running)``/``set_paused(is_paused)`` (mirror
    ``AgentPanel``'s own), and the settings round-trip
    ``get_settings()``/``apply_settings(stored, conditions=...)``.
    """

    SLOT: str = ""  # subclass sets this to a JOB_ORDER tool kind
    # False for Upscale/Aspect (GUI rework Phase 14) — they have no
    # hidden engine knobs, only ALWAYS-VISIBLE primary controls (see
    # _build_extra); building an empty collapsible gear would be a
    # dead affordance (Rule #16 — no pointless chrome).
    HAS_ADVANCED: bool = True

    def __init__(
        self,
        master,
        on_start: Callable[[str], None],
        on_pause: Callable[[str], None],
        on_stop: Callable[[str], None],
        filter_presets: dict[str, list[dict]] | None = None,
        on_filter_presets_changed: Callable[[], None] | None = None,
        on_layout_change: Callable[[], None] | None = None,
    ):
        super().__init__(master, padding=8)
        self.slot = self.SLOT
        self._on_start = on_start
        self._on_pause = on_pause
        self._on_stop = on_stop
        # PainterGui wires this to the outer fill_height ScrollFrame's
        # own refresh() (owner 2026-07-21 perf fix — see AgentPanel's
        # identical field for the full rationale): the Advanced-section
        # reveal below changes this panel's own content height with no
        # reference of its own to that ScrollFrame. A no-op default
        # keeps every headless make_panel()-style test working.
        self._on_layout_change = on_layout_change or (lambda: None)
        self._input_mode = "folder"  # or "files"
        self._folder: Path | None = None
        self._files: list[Path] = []

        head = ttk.Frame(self)
        head.pack(fill="x")
        ctk.CTkLabel(
            head, text="", image=icon(JOB_LOGO[self.slot]), width=22,
            fg_color="transparent", bg_color=theme_pair("bg"),
        ).pack(side="left", padx=(0, 4))
        ttk.Label(
            head, text=f"{JOB_LABEL[self.slot]} — settings",
            style="Head.TLabel",
        ).pack(side="left")

        # two-column-dense body (owner 2026-07-21 layout fix): this panel
        # is ALWAYS shown full-width (unlike AgentPanel, which shares the
        # row with its sibling site), so a single left-hugging stack left
        # the right half dead (Rule #16). LEFT holds the input picker plus
        # the Filter narrowing WHICH images the run touches; RIGHT holds
        # this tool's own primary knobs (_extra_box), the Advanced
        # collapsible and the footer note.
        body = ttk.Frame(self)
        body.pack(fill="x", pady=(8, 0))
        body.columnconfigure(0, weight=1)
        body.columnconfigure(1, weight=1)
        left = ttk.Frame(body)
        left.grid(row=0, column=0, sticky="new")
        right = ttk.Frame(body)
        right.grid(row=0, column=1, sticky="new", padx=(DENSE_COL_GAP_PX, 0))

        pick_row = ttk.Frame(left)
        pick_row.pack(fill="x")
        rounded_button(
            pick_row, "Folder…", icon_name="browse", command=self._pick_folder, kind="info",
            width=90,
        ).pack(side="left")
        rounded_button(
            pick_row, "Files…", icon_name="file", command=self._pick_files, kind="info",
            width=90,
        ).pack(side="left", padx=(6, 0))
        # its OWN row, full LEFT-column width to wrap into (owner 2026-07-21
        # layout fix) — inline beside the two buttons, an unwrapped long
        # path used to be free to force the whole column wider than its
        # two-column-dense budget, squeezing RIGHT's content near-clipped
        self._picked_var = tk.StringVar(value="(pick a folder or files)")
        ttk.Label(
            left, textvariable=self._picked_var, style="Muted.TLabel",
            wraplength=DENSE_COL_WRAP_PX,
        ).pack(anchor="w", pady=(4, 0))

        ttk.Label(
            left,
            text="Filter — which images this run touches (empty = all):",
        ).pack(anchor="w", pady=(8, 2))
        self.filter = FilterEditor(
            left, conditions=self._default_conditions(),
            presets=filter_presets,
            on_presets_changed=on_filter_presets_changed,
        )
        self.filter.pack(fill="x")

        # subclass hook — always-visible PRIMARY controls (Upscale's
        # min-side spinner, Aspect's target-ratio canvas); base no-op,
        # so BG/Crop see no change at all (an empty frame packs at
        # zero height)
        self._extra_box = ttk.Frame(right)
        self._extra_box.pack(fill="x")
        self._build_extra(self._extra_box)

        # the Advanced collapsible — the SAME Settings-gear idiom
        # AgentPanel._toggle_settings/_apply_finetune_visibility already
        # established, applied to a subclass-built body instead of the
        # per-agent fine-tune block. Skipped entirely when the subclass
        # has nothing to hide behind it (HAS_ADVANCED = False) — see
        # this class's own docstring.
        if self.HAS_ADVANCED:
            adv_head = ttk.Frame(right)
            adv_head.pack(fill="x", pady=(10, 0))
            ttk.Label(adv_head, text="Advanced", style="Head.TLabel").pack(
                side="left"
            )
            self._advanced_btn = rounded_button(
                adv_head, SETTINGS_GLYPH_COLLAPSED,
                command=self._toggle_advanced, icon_name="settings",
            )
            self._advanced_btn.pack(side="left", padx=(6, 0))
            self._advanced_collapsed_var = tk.BooleanVar(value=True)
            self._advanced_box = ttk.Frame(right)
            self._build_advanced(self._advanced_box)
            self._apply_advanced_visibility()

        # subclass hook — a short always-visible note just above the
        # button row (Aspect's non-proportional-stretch warning); base
        # no-op
        self._footer_box = ttk.Frame(right)
        self._footer_box.pack(fill="x", pady=(6, 0))
        self._build_footer(self._footer_box)

        btn_row = ttk.Frame(self)
        btn_row.pack(fill="x", pady=(10, 0))
        self.btn_start = rounded_button(
            btn_row, "Start", command=lambda: self._on_start(self.slot),
            kind="success", icon_name="start", width=90,
        )
        self.btn_start.pack(side="left")
        # the pause toggle — a plain neutral button, ALWAYS clickable
        # (no filled/outline availability dance), exactly like
        # AgentPanel.btn_pause.
        self.btn_pause = rounded_button(
            btn_row, "Pause", icon_name="pause", command=lambda: self._on_pause(self.slot),
            kind="secondary", width=70,
        )
        self.btn_pause.pack(side="left", padx=6)
        # Stop (GUI rework Phase 14) — filled/outline availability like
        # AgentPanel.btn_stop, styled by set_run_state below.
        self.btn_stop = rounded_button(
            btn_row, "Stop", icon_name="stop", command=lambda: self._on_stop(self.slot),
            kind="danger-outline", width=70,
        )
        self.btn_stop.pack(side="left", padx=(0, 6))
        self.set_run_state(running=False)

        # a Day/Night flip must repaint any raw-Canvas content a
        # subclass embeds (AspectSettingsPanel's AspectRatioCanvas —
        # base apply_theme() is a no-op, mirrors AgentPanel's own
        # THEME_TOPLEVELS registration); build-once, never destroyed
        # before app exit, same lifetime as every dashboard JobPanel.
        THEME_TOPLEVELS.append(self)
        self.bind("<Destroy>", self._on_destroy)

    def _on_destroy(self, event) -> None:
        if event.widget is self and self in THEME_TOPLEVELS:
            THEME_TOPLEVELS.remove(self)

    def apply_theme(self) -> None:
        """Subclass hook — repaint any raw-Canvas content on a Day/
        Night flip (e.g. AspectSettingsPanel's AspectRatioCanvas.
        redraw_theme()). Base no-op."""

    # --- input picker ----------------------------------------------

    def _picker_title_suffix(self) -> str:
        """Subclass hook — what this run DOES to the picked images,
        shown after the job label in the folder/file picker dialog
        titles ('Folder with images — <label> <this text>'). Base:
        every one of the four standalone tools modifies files IN
        PLACE. Overridden by ``ImageCheckerSettingsPanel`` (GUI rework
        Phase 15) — a read-only vision pass must never claim to write
        anything (root Rule #1: never mislead)."""
        return "runs IN PLACE"

    def _pick_folder(self) -> None:
        folder = filedialog.askdirectory(
            title=f"Folder with images — {JOB_LABEL[self.slot]}"
            f" {self._picker_title_suffix()}"
        )
        if not folder:
            return
        self._input_mode = "folder"
        self._folder = Path(folder)
        self._files = []
        n = len(iter_images(self._folder))
        self._picked_var.set(f"Folder: {self._folder}  ({n} image(s))")

    def _pick_files(self) -> None:
        picks = filedialog.askopenfilenames(
            title=f"Image files — {JOB_LABEL[self.slot]}"
            f" {self._picker_title_suffix()}",
            filetypes=[
                ("Images", "*.png *.jpg *.jpeg *.webp"),
                ("All files", "*.*"),
            ],
        )
        if not picks:
            return
        self._input_mode = "files"
        self._folder = None
        self._files = [Path(p) for p in picks]
        self._picked_var.set(f"{len(self._files)} file(s) picked")

    def resolve_input(self) -> tuple[Path, list[Path]]:
        """(base folder, candidate files) for THIS run — raises
        ``ValueError`` when nothing has been picked yet. Folder mode
        RE-SCANS live (``iter_images``) so a folder edited since the
        pick is honored, matching every existing folder-based tool;
        Files mode replays the exact picked list, based via
        ``config.selection_base_and_rels`` (a selection spanning
        sub-folders still groups/restores correctly, mirroring the
        Aspect tool)."""
        if self._input_mode == "folder":
            if self._folder is None:
                raise ValueError("Pick a folder or files first.")
            return self._folder, iter_images(self._folder)
        if not self._files:
            raise ValueError("Pick a folder or files first.")
        base, _rels = selection_base_and_rels(self._files)
        return base, list(self._files)

    # --- filter ------------------------------------------------------

    def get_conditions(self) -> list[filters.FilterCondition]:
        return self.filter.get_conditions()

    def _default_conditions(self) -> list[filters.FilterCondition]:
        """Subclass hook — the embedded FilterEditor's SEED conditions
        (e.g. UpscaleSettingsPanel's aspect-range default). Base empty
        (BG/Crop start with no filter, unchanged)."""
        return []

    # --- always-visible subclass content (GUI rework Phase 14) --------

    def _build_extra(self, box: ttk.Frame) -> None:
        """Subclass hook — populate ``box`` with this tool's own
        ALWAYS-VISIBLE primary control(s), shown between the input
        picker and the Filter section (Upscale's min-side spinner,
        Aspect's target-ratio canvas). Base no-op."""

    def _build_footer(self, box: ttk.Frame) -> None:
        """Subclass hook — populate ``box`` with a short note shown
        just above the Start/Pause/Stop row (Aspect's non-proportional-
        stretch warning). Base no-op."""

    # --- Advanced (subclass hooks) ------------------------------------

    def _build_advanced(self, box: ttk.Frame) -> None:
        """Subclass hook — populate ``box`` with this tool's own engine
        knobs. Base no-op (never reached directly — ``SLOT``/this
        method are always overridden together). Only ever called when
        ``HAS_ADVANCED`` is True."""

    def build_func(self) -> Callable[[Path, Callable[[str], None]], str]:
        """Subclass hook — a ``(path, log) -> str`` callable wrapping
        the engine function with THIS run's Advanced overrides. Raises
        ``ValueError`` (naming the field) on an unparsable override."""
        raise NotImplementedError

    def _advanced_settings(self) -> dict:
        """Subclass hook — this tool's Advanced fields as a JSON-safe
        dict, folded into ``get_settings()``."""
        return {}

    def _apply_advanced_settings(self, stored: dict) -> None:
        """Subclass hook — the inverse of ``_advanced_settings``;
        missing keys keep the current defaults."""

    def _apply_advanced_visibility(self) -> None:
        collapsed = self._advanced_collapsed_var.get()
        if collapsed:
            self._advanced_box.pack_forget()
        else:
            self._advanced_box.pack(fill="x", pady=(2, 0))
        self._advanced_btn.configure(
            text=SETTINGS_GLYPH_COLLAPSED if collapsed
            else SETTINGS_GLYPH_EXPANDED
        )

    def _toggle_advanced(self) -> None:
        self._advanced_collapsed_var.set(
            not self._advanced_collapsed_var.get()
        )

        def mutate() -> None:
            self._apply_advanced_visibility()
            self._on_layout_change()

        smooth_transition(self.winfo_toplevel(), mutate)

    # --- run state -----------------------------------------------------

    def set_run_state(self, running: bool) -> None:
        """Start is available unless this slot's job is already
        running; Stop is available exactly while it runs — mirrors
        ``AgentPanel.set_run_state`` (no ``pending_restart`` here, a
        site-only/quota concept a standalone tool never has)."""
        style_action_button(self.btn_start, "success", not running)
        style_action_button(self.btn_stop, "danger", running)

    def set_paused(self, is_paused: bool) -> None:
        self.btn_pause.configure(text="Resume" if is_paused else "Pause")

    # --- settings round-trip -------------------------------------------

    def get_settings(self) -> dict:
        data = {
            "conditions": [
                filters.condition_to_dict(c)
                for c in self.filter.get_conditions()
            ],
        }
        if self.HAS_ADVANCED:
            data["advanced_collapsed"] = self._advanced_collapsed_var.get()
        data.update(self._advanced_settings())
        return data

    def apply_settings(
        self, stored: dict,
        conditions: list[filters.FilterCondition] | None = None,
    ) -> None:
        """Missing keys keep the current defaults — same contract as
        every other panel's ``apply_settings`` in this file.
        ``conditions`` (GUI rework Phase 4 convention) is the ALREADY-
        PARSED replacement for the FilterEditor's stack; ``None`` (a
        fresh settings.json) leaves it at its construction-time
        default (empty, or a subclass's own ``_default_conditions``).
        The CALLER (``PainterGui._apply_settings``) owns parsing the
        raw JSON, same as ``AgentPanel.apply_settings``. ``_apply_
        advanced_settings`` always runs, regardless of ``HAS_
        ADVANCED`` — it also carries a subclass's ALWAYS-VISIBLE extra
        fields (e.g. Upscale's min-side, Aspect's target ratio)."""
        if conditions is not None:
            self.filter.set_conditions(conditions)
        if self.HAS_ADVANCED:
            if "advanced_collapsed" in stored:
                self._advanced_collapsed_var.set(
                    bool(stored["advanced_collapsed"])
                )
            self._apply_advanced_visibility()
        self._apply_advanced_settings(stored)

