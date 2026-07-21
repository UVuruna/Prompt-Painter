"""Standalone in-place tools' persistent settings panels — the shared
``ToolSettingsPanel`` base plus its four concrete subclasses (BG
removal / Crop / Upscale / Aspect ratio) and the AI image checker's
own panel.

Split out of ``gui/__init__.py`` (Rule #3, god-file refactor step
4/8). A leaf-ish module: depends only on ``painter.*`` and the
already-split ``gui.aspect_canvas``/``gui.filter_editor``/
``gui.icons``/``gui.logic``/``gui.theme``/``gui.widgets`` submodules —
never on ``gui/__init__.py`` itself, so ``gui.agent_panel`` and
``gui.api_panel`` can import the two-column-dense layout constants
below (``DENSE_COL_GAP_PX``/``DENSE_COL_WRAP_PX``, the Settings-gear
caret glyphs, ``ASPECT_DIALOG_ENTRY_W``) from HERE with no circular
import — all three panel families share this "room to spare, fill the
width in two columns" layout (owner 2026-07-21 layout fix)."""

from __future__ import annotations

import tkinter as tk
from pathlib import Path
from tkinter import filedialog, ttk
from typing import Callable

import customtkinter as ctk

from painter import filters
from painter.config import (
    AI_CALL_PAUSE_S,
    ASPECT_DEFAULT_H,
    ASPECT_DEFAULT_W,
    CLEAN_EDGE_ENABLE,
    CROP_INK_ALPHA,
    CROP_MARGIN_PX,
    CROP_MIN_INK_PX,
    FILTER_KIND_ASPECT_RANGE,
    FILTER_POLARITY_IF,
    GEMINI_VISION_MODEL,
    JOB_LABEL,
    JOB_LOGO,
    SAFETY_MAX_REMOVE_FRAC,
    SAFETY_MAX_REMOVE_FRAC_WHITE,
    STATE_DIRNAME,
    UPSCALE_ASPECT_MAX,
    UPSCALE_ASPECT_MIN,
    UPSCALE_MINDIM_STEP,
    UPSCALE_MIN_SIDE_DEFAULT,
    iter_images,
    selection_base_and_rels,
    theme_pair,
)
from .aspect_canvas import AspectRatioCanvas
from .filter_editor import FilterEditor
from .icons import icon
from .logic import _upscale_params_from_side_and_filter
from .theme import THEME_TOPLEVELS, smooth_transition
from .widgets import (
    Spinner,
    _parse_fraction,
    _parse_int_range,
    _parse_nonneg_int,
    rounded_button,
    rounded_entry,
    rounded_switch,
    style_action_button,
    tk_font,
)

# --- Aspect-ratio prompt (the standalone 'Aspect ratio…' tool) -------
ASPECT_DIALOG_ENTRY_W = 64  # px width of each W / H field in the ratio dialog

# each AgentPanel's own Settings gear (owner 2026-07-19) shows/hides THAT
# agent's fine-tune — its pause range, action-delay range and upscale-gate
# fields — independently of the other site; HIDDEN by default so the panel
# stays compact. The gear carries settings.png (a gear icon) + this caret.
SETTINGS_GLYPH_EXPANDED = "▾  Settings"   # gear label while fine-tune shows
SETTINGS_GLYPH_COLLAPSED = "▸  Settings"  # gear label while hidden

# --- Two-column-dense settings-panel layout (owner 2026-07-21 layout
# fix — Rule #16: a settings panel with room to spare fills the width in
# TWO logical columns instead of cramming everything into the left half
# with the right sitting dead). AgentPanel switches to this arrangement
# ONLY while it is the SOLE visible site (PainterGui._relayout_agents,
# driven off the KNOWN visible-count state — see
# AgentPanel.set_dense_columns — never a fragile <Configure> width
# probe); the ToolSettingsPanel family and ApiImageGenPanel are ALWAYS
# full-width single panels, so they use it unconditionally.
DENSE_COL_GAP_PX = 16    # gap between the two columns (DESIGN.md 8pt grid,
#                          same 2-unit gap MENU_TILE_GAP_PX already uses)
DENSE_COL_WRAP_PX = 320  # wraplength for a caption/note living in ONE
#                          column instead of the panel's old full width
#                          (narrower than JOB_PANEL_BANNER_WRAP_PX, which
#                          still wraps a full-width dashboard banner)


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
    ):
        super().__init__(master, padding=8)
        self.slot = self.SLOT
        self._on_start = on_start
        self._on_pause = on_pause
        self._on_stop = on_stop
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
            pick_row, "Folder…", command=self._pick_folder, kind="info",
            width=90,
        ).pack(side="left")
        rounded_button(
            pick_row, "Files…", command=self._pick_files, kind="info",
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
            btn_row, "Pause", command=lambda: self._on_pause(self.slot),
            kind="secondary", width=70,
        )
        self.btn_pause.pack(side="left", padx=6)
        # Stop (GUI rework Phase 14) — filled/outline availability like
        # AgentPanel.btn_stop, styled by set_run_state below.
        self.btn_stop = rounded_button(
            btn_row, "Stop", command=lambda: self._on_stop(self.slot),
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
        smooth_transition(
            self.winfo_toplevel(), self._apply_advanced_visibility
        )

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


class BgSettingsPanel(ToolSettingsPanel):
    """BG removal's persistent settings panel (GUI rework Phase 13).

    Advanced exposes the SAFETY GUARD fractions ``remove_background``
    aborts past (owner 2026-07-19's "never destroy an image" rule) —
    NOT the border-halo-cleanup toggle the design's own phase notes
    mention: that constant (``CLEAN_EDGE_ENABLE``) is only ever read by
    ``crop_transparent`` (its docstring: "only serves to ENABLE a
    tighter crop") — ``remove_background`` never calls
    ``clean_edge_halo`` at all, so surfacing it here would silently do
    nothing (root Rule #1). It lives on ``CropSettingsPanel`` instead,
    where it actually affects behaviour; see that class's own
    docstring."""

    SLOT = "bg"

    def _build_advanced(self, box: ttk.Frame) -> None:
        ttk.Label(
            box,
            text="Safety guard — abort a removal that would clear more"
            " than:",
        ).pack(anchor="w", pady=(0, 2))
        row = ttk.Frame(box)
        row.pack(fill="x", pady=2)
        ttk.Label(row, text="black bg", width=10).pack(side="left")
        self.safety_black_var = tk.StringVar(
            value=f"{SAFETY_MAX_REMOVE_FRAC:.2f}"
        )
        rounded_entry(
            row, width=60, textvariable=self.safety_black_var,
            justify="center",
        ).pack(side="left")
        ttk.Label(row, text="(fraction, e.g. 0.40)").pack(
            side="left", padx=(6, 0)
        )
        row2 = ttk.Frame(box)
        row2.pack(fill="x", pady=2)
        ttk.Label(row2, text="white bg", width=10).pack(side="left")
        self.safety_white_var = tk.StringVar(
            value=f"{SAFETY_MAX_REMOVE_FRAC_WHITE:.2f}"
        )
        rounded_entry(
            row2, width=60, textvariable=self.safety_white_var,
            justify="center",
        ).pack(side="left")

    def build_func(self) -> Callable[[Path, Callable[[str], None]], str]:
        from painter.postprocess import remove_background

        black = _parse_fraction(self.safety_black_var.get(), "black bg safety")
        white = _parse_fraction(self.safety_white_var.get(), "white bg safety")
        return lambda path, log: remove_background(
            path, log,
            safety_max_remove_frac=black,
            safety_max_remove_frac_white=white,
        )

    def _advanced_settings(self) -> dict:
        return {
            "safety_black": self.safety_black_var.get(),
            "safety_white": self.safety_white_var.get(),
        }

    def _apply_advanced_settings(self, stored: dict) -> None:
        if "safety_black" in stored:
            self.safety_black_var.set(stored["safety_black"])
        if "safety_white" in stored:
            self.safety_white_var.set(stored["safety_white"])


class CropSettingsPanel(ToolSettingsPanel):
    """Crop's persistent settings panel (GUI rework Phase 13).

    Advanced exposes every knob ``crop_transparent`` actually reads:
    the border-halo cleanup toggle (``clean_edge_enable`` — only ever
    serves to ENABLE a tighter crop, see ``painter/postprocess.md``),
    the safety MARGIN kept around the content box, and the ink-
    detection thresholds (the alpha floor + the minimum ink pixels a
    row/col needs to count as content). ``CLEAN_EDGE_ALPHA`` (the
    halo's OWN alpha threshold, a finer sub-knob of the toggle above)
    stays at its config default — not surfaced as a field this round,
    unlike the other four, which the design explicitly asked for."""

    SLOT = "crop"

    def _build_advanced(self, box: ttk.Frame) -> None:
        self.clean_edge_var = tk.BooleanVar(value=CLEAN_EDGE_ENABLE)
        rounded_switch(
            box, "Clean faint border halo before cropping (tighter crop)",
            self.clean_edge_var,
        ).pack(anchor="w", pady=(0, 4))

        row = ttk.Frame(box)
        row.pack(fill="x", pady=2)
        ttk.Label(row, text="margin px", width=10).pack(side="left")
        self.margin_var = tk.StringVar(value=str(CROP_MARGIN_PX))
        rounded_entry(
            row, width=60, textvariable=self.margin_var, justify="center",
        ).pack(side="left")

        row2 = ttk.Frame(box)
        row2.pack(fill="x", pady=2)
        ttk.Label(row2, text="ink alpha", width=10).pack(side="left")
        self.ink_alpha_var = tk.StringVar(value=str(CROP_INK_ALPHA))
        rounded_entry(
            row2, width=60, textvariable=self.ink_alpha_var, justify="center",
        ).pack(side="left")
        ttk.Label(row2, text="0-255").pack(side="left", padx=(6, 0))

        row3 = ttk.Frame(box)
        row3.pack(fill="x", pady=2)
        ttk.Label(row3, text="min ink px", width=10).pack(side="left")
        self.min_ink_var = tk.StringVar(value=str(CROP_MIN_INK_PX))
        rounded_entry(
            row3, width=60, textvariable=self.min_ink_var, justify="center",
        ).pack(side="left")

    def build_func(self) -> Callable[[Path, Callable[[str], None]], str]:
        from painter.postprocess import crop_transparent

        margin = _parse_nonneg_int(self.margin_var.get(), "margin px")
        ink_alpha = _parse_int_range(
            self.ink_alpha_var.get(), "ink alpha", 0, 255
        )
        min_ink = _parse_nonneg_int(self.min_ink_var.get(), "min ink px")
        clean_enable = self.clean_edge_var.get()
        return lambda path, log: crop_transparent(
            path, log,
            clean_edge_enable=clean_enable,
            crop_margin_px=margin,
            crop_ink_alpha=ink_alpha,
            crop_min_ink_px=min_ink,
        )

    def _advanced_settings(self) -> dict:
        return {
            "clean_edge_enable": self.clean_edge_var.get(),
            "margin_px": self.margin_var.get(),
            "ink_alpha": self.ink_alpha_var.get(),
            "min_ink_px": self.min_ink_var.get(),
        }

    def _apply_advanced_settings(self, stored: dict) -> None:
        if "clean_edge_enable" in stored:
            self.clean_edge_var.set(bool(stored["clean_edge_enable"]))
        if "margin_px" in stored:
            self.margin_var.set(stored["margin_px"])
        if "ink_alpha" in stored:
            self.ink_alpha_var.set(stored["ink_alpha"])
        if "min_ink_px" in stored:
            self.min_ink_var.set(stored["min_ink_px"])


class UpscaleSettingsPanel(ToolSettingsPanel):
    """Upscale's persistent settings panel (GUI rework Phase 14).

    No Advanced section (``HAS_ADVANCED = False``) — Phase 6 already
    reduced the whole gate to ONE min-side spinner plus the base's own
    embedded ``FilterEditor`` (pre-seeded here with the aspect-range
    default via ``_default_conditions``, exactly like ``AgentPanel``'s
    own ``upscale_filter``/``UpscaleParamsDialog``'s old seed), so
    there is nothing left to tuck behind a gear — the spinner is the
    panel's one PRIMARY control, always visible (``_build_extra``),
    right where the old modal put it."""

    SLOT = "upscale"
    HAS_ADVANCED = False

    def _default_conditions(self) -> list[filters.FilterCondition]:
        return [filters.FilterCondition(
            kind=FILTER_KIND_ASPECT_RANGE, polarity=FILTER_POLARITY_IF,
            lo=UPSCALE_ASPECT_MIN, hi=UPSCALE_ASPECT_MAX,
        )]

    def _build_extra(self, box: ttk.Frame) -> None:
        self.up_minside_var = tk.StringVar(
            value=str(UPSCALE_MIN_SIDE_DEFAULT)
        )
        row = ttk.Frame(box)
        row.pack(fill="x", pady=2)
        ttk.Label(row, text="min side", width=8).pack(side="left")
        Spinner(row, self.up_minside_var, step=UPSCALE_MINDIM_STEP).pack(
            side="left"
        )
        ttk.Label(
            row, text="px — the smaller side reaches this; the Filter"
            " below decides WHICH images qualify",
            wraplength=DENSE_COL_WRAP_PX,
        ).pack(side="left", padx=(4, 0))

    def build_func(self) -> Callable[[Path, Callable[[str], None]], str]:
        """The min-side spinner + the base's OWN FilterEditor resolve
        into ``upscale_if_small``'s kwargs exactly like ``AgentPanel``'s
        own upscale gate (``_upscale_params_from_side_and_filter``).
        ``get_conditions()`` is read AGAIN here (the caller,
        ``PainterGui._start_tool_from_panel``, already reads it once to
        pre-filter the candidate file list) — a harmless duplicate read
        (FilterEditor rows, no side effects): this closure needs the
        SAME conditions to resolve the aspect band, and every
        ``ToolSettingsPanel.build_func()`` has the same fixed no-
        argument signature, so there is no other way to hand them in."""
        from painter.upscale import upscale_if_small

        try:
            min_side = int(float(self.up_minside_var.get().strip()))
        except ValueError:
            raise ValueError("Min side must be a number.")
        if min_side <= 0:
            raise ValueError("Min side must be positive.")
        up_params = _upscale_params_from_side_and_filter(
            min_side, self.get_conditions()
        )
        return lambda path, log: upscale_if_small(path, log, **up_params)

    def _advanced_settings(self) -> dict:
        return {"up_minside": self.up_minside_var.get()}

    def _apply_advanced_settings(self, stored: dict) -> None:
        if "up_minside" in stored:
            self.up_minside_var.set(stored["up_minside"])


class AspectSettingsPanel(ToolSettingsPanel):
    """Aspect ratio's persistent settings panel (GUI rework Phase 14).

    No Advanced section (``HAS_ADVANCED = False``) — the target-ratio
    editor (``_build_extra``: GUI rework Phase 5's ``AspectRatioCanvas``
    two-way synced with plain W/H entries, exactly like ``AgentPanel``'s
    own Force Aspect Ratio block) IS the panel's one PRIMARY control,
    always visible; the base's own embedded ``FilterEditor`` decides
    WHICH images qualify. ``_build_footer`` carries the non-
    proportional-stretch warning the old modal's confirm ``askyesno``
    used to show, so Start — no confirm dialog here; the panel itself,
    deliberately configured then Started, already IS the confirmation,
    same contract as every other panel — never surprises the owner."""

    SLOT = "aspect"
    HAS_ADVANCED = False

    def _build_extra(self, box: ttk.Frame) -> None:
        self._ratio_w_var = tk.StringVar(value=str(ASPECT_DEFAULT_W))
        self._ratio_h_var = tk.StringVar(value=str(ASPECT_DEFAULT_H))
        ttk.Label(
            box, text="Target aspect ratio — stretches every matching"
            " image to it:",
        ).pack(anchor="w", pady=(0, 6))

        row = ttk.Frame(box)
        row.pack(anchor="w")
        fields = ttk.Frame(row)
        fields.pack(side="left", anchor="n")
        ttk.Label(fields, text="W").pack(side="left", padx=(0, 4))
        self._w_entry = rounded_entry(
            fields, width=ASPECT_DIALOG_ENTRY_W,
            textvariable=self._ratio_w_var, justify="center",
        )
        self._w_entry.pack(side="left")
        ttk.Label(fields, text=":", font=tk_font("head")).pack(
            side="left", padx=8
        )
        ttk.Label(fields, text="H").pack(side="left", padx=(0, 4))
        self._h_entry = rounded_entry(
            fields, width=ASPECT_DIALOG_ENTRY_W,
            textvariable=self._ratio_h_var, justify="center",
        )
        self._h_entry.pack(side="left")

        # the visual editor (GUI rework Phase 5), two-way synced with
        # the fields above — the SAME pattern AspectRatioDialog/
        # AgentPanel's own Force Aspect Ratio block already use
        self._ratio_canvas = AspectRatioCanvas(
            row, w=ASPECT_DEFAULT_W, h=ASPECT_DEFAULT_H,
            on_change=self._on_canvas_drag,
        )
        self._ratio_canvas.pack(side="left", padx=(12, 0), anchor="n")
        self._ratio_w_var.trace_add("write", self._on_wh_typed)
        self._ratio_h_var.trace_add("write", self._on_wh_typed)

    def _build_footer(self, box: ttk.Frame) -> None:
        ttk.Label(
            box,
            text="⚠ Deforms every matching image with a non-proportional"
            " STRETCH, written IN PLACE. Originals are backed up so you"
            " can Restore; images already at this ratio are skipped"
            " untouched.",
            style="Muted.TLabel", wraplength=DENSE_COL_WRAP_PX,
        ).pack(anchor="w")

    def _on_canvas_drag(self, w: int, h: int) -> None:
        """``AspectRatioCanvas.on_change`` — mirrors ``AgentPanel.
        _on_force_aspect_canvas_drag``/``AspectRatioDialog.
        _on_canvas_drag`` (Rule #5 — the third instance of the same
        two-way sync)."""
        self._ratio_w_var.set(str(w))
        self._ratio_h_var.set(str(h))

    def _on_wh_typed(self, *_args) -> None:
        """Live-reshape the canvas as the owner types; a bad/mid-edit
        value is silently skipped (final validation happens in
        ``target_ratio()`` on Start) — mirrors ``AgentPanel._on_force_
        aspect_wh_typed``/``AspectRatioDialog._on_wh_typed``."""
        try:
            w = int(self._ratio_w_var.get().strip())
            h = int(self._ratio_h_var.get().strip())
        except ValueError:
            return
        if w <= 0 or h <= 0:
            return
        self._ratio_canvas.set_ratio(w, h)

    def target_ratio(self) -> tuple[int, int]:
        """The target W:H — ``ValueError`` propagates to Start's own
        messagebox, same contract as ``AgentPanel.force_aspect_ratio``."""
        try:
            w = int(self._ratio_w_var.get().strip())
            h = int(self._ratio_h_var.get().strip())
        except ValueError:
            raise ValueError("Width and height must be whole numbers.")
        if w <= 0 or h <= 0:
            raise ValueError("Width and height must both be positive.")
        return (w, h)

    def build_func(self) -> Callable[[Path, Callable[[str], None]], str]:
        from painter.aspect import change_aspect

        ratio_w, ratio_h = self.target_ratio()
        return lambda path, log: change_aspect(path, ratio_w, ratio_h, log)

    def _advanced_settings(self) -> dict:
        return {"ratio": [self._ratio_w_var.get(), self._ratio_h_var.get()]}

    def _apply_advanced_settings(self, stored: dict) -> None:
        ratio = stored.get("ratio")
        if not (isinstance(ratio, (list, tuple)) and len(ratio) == 2):
            return
        try:
            w, h = int(ratio[0]), int(ratio[1])
        except (TypeError, ValueError):
            return
        if w > 0 and h > 0:
            self._ratio_w_var.set(str(w))
            self._ratio_h_var.set(str(h))
            self._ratio_canvas.set_ratio(w, h)

    def apply_theme(self) -> None:
        self._ratio_canvas.redraw_theme()


class ImageCheckerSettingsPanel(ToolSettingsPanel):
    """The AI image checker's persistent settings panel (GUI rework
    Phase 15) — the SAME input-picker + Filter + Start/Pause/Stop
    chrome every standalone tool now has, replacing the Main Menu/
    IconBar's old direct ``_start_ai_check`` launch (its own
    ``askdirectory`` + confirm ``askyesno``, both retired: the panel's
    OWN picker covers the folder/files, and Start — deliberately
    configured then clicked — already IS the confirmation, same
    contract as every sibling panel; see ``ToolSettingsPanel``'s own
    docstring and ``AspectSettingsPanel``'s "no confirm dialog here").

    No Advanced section (``HAS_ADVANCED = False``) — the checker has
    no engine knobs to hide, only the base's own input picker plus an
    OPTIONAL embedded ``FilterEditor`` (unseeded — empty means check
    EVERY image under the folder, same "empty = all" contract BG/Crop
    already use) and a short informational footer carrying what the
    old confirm dialog used to say (model + pacing + where flags
    persist), so the owner still sees that information without a
    blocking dialog.

    Its Start does NOT go through ``build_func``/``PainterGui.
    _start_tool_from_panel``/``_launch_tool_worker`` at all — the
    checker's own worker (``_run_ai_check_job``) has a fundamentally
    different shape from the four tools' shared ``_run_tool_job`` (no
    JobTemp backup — the run is read-only — no per-file engine
    callable, its own event types), so it is wired straight to
    ``PainterGui._start_ai_check`` instead (see that method's own
    docstring for the full flow). **Stop reuses ``PainterGui.
    _stop_tool`` UNCHANGED** — that method never touches
    ``_tool_panels`` and is already fully generic over any slot with a
    ``_tool_workers``/``_stop_events`` entry (it only sets the stop
    event, clears a pending pause and writes a status line), so a
    second near-identical ``_stop_ai_check`` method would only
    duplicate it byte-for-byte (Rule #5) — the constructor below wires
    ``on_stop=PainterGui._stop_tool`` exactly like BG/Crop/Upscale/
    Aspect.

    One asymmetry from its three siblings: this panel's MENU_TILES id
    ("image_checker") differs from its own ``SLOT``/JOB_ORDER kind
    ("aicheck") — the checker already existed as the dashboard's
    seventh job kind (``AiCheckPanel``, owner 2026-07-20) before this
    panel did, so its slot name predates and is independent of the
    tile system Phase 10 introduced. ``PainterGui._tool_panel_key``
    (backed by ``config.tile_for_kind``) is the one translation point
    that bridges the two spaces wherever `_toggle_pause_job`/
    `_dispatch` need to reach THIS panel from the "aicheck" kind."""

    SLOT = "aicheck"
    HAS_ADVANCED = False

    def _picker_title_suffix(self) -> str:
        return "(read-only)"

    def _build_footer(self, box: ttk.Frame) -> None:
        ttk.Label(
            box,
            text="Each image goes to the Gemini vision model"
            f" ({GEMINI_VISION_MODEL}) for banal defects only, paced"
            f" ~{AI_CALL_PAUSE_S:.0f}s per call on the free tier."
            f" Read-only — nothing is modified; flags persist under"
            f" the output folder's {STATE_DIRNAME}/.",
            style="Muted.TLabel", wraplength=DENSE_COL_WRAP_PX,
        ).pack(anchor="w")
