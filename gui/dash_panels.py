"""``JobPanel``/``DashPanel`` pulled out of ``gui/__init__.py`` (root
Rule #20 god-file refactor, step 6/8): the shared per-JOB dashboard
panel base (``JobPanel`` — header, close/pause, the folder>image tree
node plumbing shared with ``gui.tool_dash``) and ``DashPanel`` (one
generation site's live view — task/theme progress, the two-scope
stats table, the collections history tree, the per-step restore
viewer and the parallel Checker AI's per-row report).

``DocWindow``/``StepRestoreWindow`` are opened via a deferred ``import
gui`` (NOT a module-level ``from .viewers import ...``) inside
``DashPanel._show_check``/``_show_steps`` — the established late-
binding idiom this codebase already uses for exactly this reason (see
``gui.viewers``'s own ``AI_POLL_MS`` read, ``gui.api_panel``'s
``_arm_probe_poll``): several tests (``test_gui_checker.py``,
``test_gui_fixer.py``, ``test_gui_pipeline.py``) do
``monkeypatch.setattr(gui, "DocWindow", fake)`` /
``monkeypatch.setattr(gui, "StepRestoreWindow", fake)`` and expect the
PATCHED class to fire — a bare top-of-module import would bind the
real class at import time and never see the patch.
"""

from __future__ import annotations

import time
import tkinter as tk
from functools import partial
from pathlib import Path, PurePosixPath
from tkinter import messagebox, ttk

import customtkinter as ctk
from PIL import Image

from painter import jobtemp
from painter.config import (
    BADGES,
    JOB_LABEL,
    JOB_LOGO,
    JOBTEMP_CAP_BANNER_TEXT,
    badge_keys_for,
    dest_for,
    fmt_duration,
    fmt_size,
    job_color_pair,
    theme_pair,
)
from .dash_helpers import ai_check_doc_md, ai_check_image_file, ai_check_tag, badge_dots
from .icons import icon
from .logic import _STAT_KEYS, _scope_stats
from .widgets import ctk_font, folder_of, rounded_button, tk_font

# --- JobPanel's loud persistent cap-warning strip (GUI rework Phase 8) -
# see JobPanel._show_cap_banner/_hide_cap_banner; wraplength keeps the
# (fairly long) JOBTEMP_CAP_BANNER_TEXT readable inside one dashboard
# panel column instead of stretching it.
JOB_PANEL_BANNER_WRAP_PX = 480

# DashPanel's own check-status column (GUI rework Phase 16) — the
# parallel per-item Checker AI's "checking…"/"OK"/"flagged N"/"error"
# indicator, appended after Size in the site dashboard's image rows.
DASH_CHECK_COL_PX = 92


class JobPanel(ttk.Frame):
    """Base for a per-JOB dashboard panel — a generation site or an
    in-place tool.

    Owns the coloured header (an SVG logo for the two gen sites / an
    emoji for the four tools, plus the job NAME in the job colour), the
    muted state line (the quota countdown / current item), and the
    CLOSE button that is hidden until the job FINISHES and then removes
    the panel. The body (progress / stats / table) is built by the
    subclass. A panel appears when its job STARTS and disappears when
    the owner clicks CLOSE (owner 2026-07-19: only running-or-ran jobs
    show). For the FOLDER-BASED panels (ToolPanel, AiCheckPanel) it
    also carries the shared root/folder tree-node plumbing — those
    subclasses own ``self.tree``/``self._cols``/``self.folder`` and the
    per-run node dicts; DashPanel builds its own theme-based nodes and
    never calls these.
    """

    def __init__(
        self, master, kind: str, on_show=None, on_close=None, on_pause=None,
    ):
        super().__init__(master, padding=6)
        self.slot_key = kind
        self._on_show = on_show   # called with a node-info dict on 'Show'
        self._on_close = on_close  # called with the slot key on CLOSE
        self._on_pause = on_pause  # called with the slot key on Pause/Resume
        self._finished = False
        self._node_info: dict[str, dict] = {}  # tree item id -> info
        # every job kind CAN carry a per-step backup store (the four
        # tools always have; the two gen sites since GUI rework Phase
        # 8) — shared here (Rule #5) so DashPanel/ToolPanel both gain
        # it identically instead of each redeclaring the same line;
        # AiCheckPanel simply never populates it. Set by the caller at
        # job start (_launch_tool_worker / _start_site), None otherwise.
        self.jobtemp: "jobtemp.JobTemp | None" = None
        self._build_header(kind)

    def _build_header(self, kind: str) -> None:
        header = ttk.Frame(self)
        header.pack(fill="x")
        # every job — gen site or tool — carries an icon (its
        # config.JOB_LOGO stem, resolved to an svg/png by icon()) beside
        # the coloured job NAME. The four tools got dedicated PNG icons
        # (owner 2026-07-19), replacing the old emoji marks.
        ctk.CTkLabel(
            header, text="", image=icon(JOB_LOGO[kind]), width=24,
            fg_color="transparent", bg_color=theme_pair("bg"),
        ).pack(side="left", padx=(0, 6))
        ctk.CTkLabel(
            header, text=JOB_LABEL[kind], font=ctk_font("title"),
            text_color=job_color_pair(kind),
            fg_color="transparent", bg_color=theme_pair("bg"),
        ).pack(side="left")
        # revealed by finish(); removes the panel + clears its temp
        self._close_btn = rounded_button(
            header, "✕ Close", command=self._do_close,
            kind="danger-outline", width=76,
        )
        # a folder-based job (ToolPanel / AiCheckPanel) owns its OWN
        # pause toggle here, beside Close (owner 2026-07-21) — the two
        # gen sites' button lives on AgentPanel instead, so on_pause
        # stays None for DashPanel and this button is never built there.
        self.btn_pause: ctk.CTkButton | None = None
        if self._on_pause is not None:
            self.btn_pause = rounded_button(
                header, "Pause", command=partial(self._on_pause, kind),
                kind="secondary", width=70,
            )
            self.btn_pause.pack(side="right", padx=(0, 6))

        # the state line — quota auto-restart countdown / current item
        # / paused
        self.state_var = tk.StringVar(value="")
        self._state_label = ttk.Label(
            self, textvariable=self.state_var, style="Muted.TLabel"
        )
        self._state_label.pack(anchor="w")

        # a LOUD, PERSISTENT warning strip (GUI rework Phase 8) — unlike
        # state_var above (MUTED, overwritten by the very next progress
        # event — see set_paused's own docstring), this stays up until
        # something explicitly hides it again (reset() on a fresh run).
        # Built here so its pack POSITION (right after the state line,
        # via after=self._state_label) is fixed no matter what a
        # subclass packs later, but left UNPACKED at construction — a
        # solid "inverse-warning" fill with empty text would still paint
        # a bare colour bar on every panel. Today only DashPanel ever
        # shows it (a site job's JobTemp crossing its backup cap — see
        # DashPanel.handle's "over_cap" branch); the four standalone
        # tools have no per-step backups to cap (Phase 8 scope).
        self._cap_banner_var = tk.StringVar(value="")
        self._cap_banner = ttk.Label(
            self, textvariable=self._cap_banner_var,
            bootstyle="inverse-warning", anchor="w", padding=4,
            wraplength=JOB_PANEL_BANNER_WRAP_PX,
        )

    def _show_cap_banner(self, text: str) -> None:
        """Show (or update the text of) the persistent warning strip.
        Idempotent — Tk's pack() just re-configures an already-mapped
        widget in place, so a repeat call never re-stacks it."""
        self._cap_banner_var.set(text)
        self._cap_banner.pack(fill="x", pady=(2, 0), after=self._state_label)

    def _hide_cap_banner(self) -> None:
        self._cap_banner.pack_forget()
        self._cap_banner_var.set("")

    def finish(self) -> None:
        """The job ended — reveal the CLOSE button."""
        if self._finished:
            return
        self._finished = True
        self._close_btn.pack(side="right")

    def reset_finished(self) -> None:
        """Hide the CLOSE button again (a slot reused for a new run)."""
        self._finished = False
        self._close_btn.pack_forget()

    def set_paused(self, is_paused: bool) -> None:
        """Reflect a pause toggle (owner 2026-07-21): the muted state
        line (every JobPanel has one) and, for a panel that owns a
        btn_pause (ToolPanel / AiCheckPanel — the two gen sites' button
        lives on AgentPanel instead, see AgentPanel.set_paused), its
        Pause/Resume label. The next real progress event (item_start /
        sheet_done) naturally overwrites the state line once the job is
        running or finished again."""
        if self.btn_pause is not None:
            self.btn_pause.configure(text="Resume" if is_paused else "Pause")
        self.state_var.set("paused — waiting to resume" if is_paused else "")

    def _do_close(self) -> None:
        if self._on_close is not None:
            self._on_close(self.slot_key)

    # --- shared folder>image tree nodes (ToolPanel + AiCheckPanel) -----

    def _ensure_root(self) -> str:
        if self._tree_root is None:
            name = self.folder.name if self.folder else JOB_LABEL[self.slot_key]
            self._tree_root = self.tree.insert(
                "", "end", text=f"{name}   · {JOB_LABEL[self.slot_key]}",
                open=True, values=("",) * len(self._cols),
            )
            self._node_info[self._tree_root] = {"level": "collection"}
        return self._tree_root

    def _ensure_folder(self, folder: str) -> str:
        node = self._folder_nodes.get(folder)
        if node is None:
            node = self.tree.insert(
                self._ensure_root(), "end", text=folder, open=True,
                values=("",) * len(self._cols),
            )
            self._folder_nodes[folder] = node
            self._node_info[node] = {"level": "folder", "folder": folder}
        return node


class DashPanel(JobPanel):
    """One generation site's live view: current collection, whole-task
    totals, timings and the collections history table.

    Driven by structured events on the main thread — the runner's own
    (``item_progress``/``item_done``/...) PLUS, since GUI rework Phase
    16, the parallel Checker AI's ``item_checking``/``item_checked``
    (posted by ``PainterGui._maybe_spawn_checker``/``_run_checker_one``
    onto the SAME worker queue, never by the runner itself) — every
    event still funnels through the identical ``handle(event)`` entry
    point regardless of which thread ultimately produced it.
    """

    def __init__(
        self, master, kind: str, on_show=None, on_close=None,
        on_fix_actions=None,
    ):
        super().__init__(master, kind, on_show=on_show, on_close=on_close)
        self._name = JOB_LABEL[kind]
        # the Fixer AI's manual-button builder (GUI rework Phase 20) —
        # PainterGui._build_fix_workers, called with THIS site's own
        # slot_key (JobPanel base) so it never has to re-derive the site
        # from the rel the way AiCheckPanel's own standalone flow must.
        # None only in a headless/test caller that never went through
        # PainterGui._build_views (see _show_check's own guard).
        self._on_fix_actions = on_fix_actions
        # this site's output root (GUI rework Phase 9) — mirrors
        # ToolPanel.folder's role: paired with self.jobtemp (JobPanel
        # base) to resolve a row's site-agnostic drop path into the
        # JobTemp rel (dest_for) and the live file on disk. Set by
        # _start_site alongside self.jobtemp, right before reset().
        self.out_base: Path | None = None

        # whole-task progress
        task = ttk.Frame(self)
        task.pack(fill="x", pady=(6, 2))
        ttk.Label(task, text="Task", width=7).pack(side="left")
        self.task_prog_var = tk.StringVar(value="0 / 0")
        ttk.Label(
            task, textvariable=self.task_prog_var, style="Value.TLabel"
        ).pack(side="right")
        self.task_bar = ttk.Progressbar(
            self, bootstyle="success-striped", maximum=1, value=0
        )
        self.task_bar.pack(fill="x", pady=(0, 6))

        # current theme + image + its own bar
        cur = ttk.Frame(self)
        cur.pack(fill="x")
        ttk.Label(cur, text="File:", width=7).grid(row=0, column=0, sticky="w")
        self.theme_name_var = tk.StringVar(value="—")
        ttk.Label(cur, textvariable=self.theme_name_var).grid(
            row=0, column=1, sticky="w"
        )
        ttk.Label(cur, text="Image:", width=7).grid(row=1, column=0, sticky="w")
        self.image_var = tk.StringVar(value="—")
        ttk.Label(cur, textvariable=self.image_var).grid(
            row=1, column=1, sticky="w"
        )
        cur.columnconfigure(1, weight=1)
        self.theme_bar = ttk.Progressbar(
            self, bootstyle="info-striped", maximum=1, value=0
        )
        self.theme_bar.pack(fill="x", pady=(2, 6))

        # the two-scope stats table: Done, Refused, a collapsible
        # 'Average' group (total avg + the AI/processing/min/max
        # breakdown), then Tempo and ETA
        grid = ttk.Frame(self)
        grid.pack(fill="x", pady=(2, 6))
        self.cells: dict[tuple[str, str], tk.StringVar] = {}

        def value_cells(r, key, muted=False):
            for c, scope in ((1, "theme"), (2, "task")):
                var = tk.StringVar(value="—")
                self.cells[(scope, key)] = var
                ttk.Label(
                    grid, textvariable=var,
                    style="" if muted else "Value.TLabel", anchor="e",
                ).grid(row=r, column=c, sticky="e", padx=4)

        def plain_row(r, label, key):
            ttk.Label(grid, text=label).grid(row=r, column=0, sticky="w")
            value_cells(r, key)

        ttk.Label(grid, text="", width=16).grid(row=0, column=0)
        ttk.Label(grid, text="This one", style="Head.TLabel", width=10).grid(
            row=0, column=1, sticky="e"
        )
        ttk.Label(grid, text="Whole run", style="Head.TLabel", width=10).grid(
            row=0, column=2, sticky="e"
        )
        plain_row(1, "Done", "done")
        plain_row(2, "Refused", "refused")

        # the collapsible Average header (its value is the total avg)
        self._avg_open = False
        self._avg_btn = rounded_button(
            grid, "", command=self._toggle_avg, kind="expander"
        )
        self._avg_btn.grid(row=3, column=0, sticky="w")
        value_cells(3, "total")

        self._avg_rows: list[list] = []
        for i, (key, label) in enumerate((
            ("gen", "     AI generation"),
            ("over", "     Our processing"),
            ("tmin", "     Minimum"),
            ("tmax", "     Maximum"),
        )):
            r = 4 + i
            widgets = [ttk.Label(grid, text=label, style="Muted.TLabel")]
            widgets[0].grid(row=r, column=0, sticky="w")
            for c, scope in ((1, "theme"), (2, "task")):
                var = tk.StringVar(value="—")
                self.cells[(scope, key)] = var
                w = ttk.Label(grid, textvariable=var, anchor="e")
                w.grid(row=r, column=c, sticky="e", padx=4)
                widgets.append(w)
            self._avg_rows.append(widgets)

        plain_row(8, "Tempo", "tempo")
        plain_row(9, "ETA", "eta")
        grid.columnconfigure(0, weight=1)
        self._render_avg_btn()
        self._collapse_avg()

        ttk.Separator(self).pack(fill="x", pady=4)
        hdr = ttk.Frame(self)
        hdr.pack(fill="x")
        ttk.Label(
            hdr, text="Collections (running + done)", style="Head.TLabel"
        ).pack(side="left")
        rounded_button(
            hdr, "Show", command=self._show_selected, kind="link",
            icon_name="right", compound="right",
        ).pack(side="right")
        # the per-step restore filmstrip (GUI rework Phase 9) — a
        # SEPARATE button from 'Show' above (same focused-row idiom,
        # never overloaded onto the tree's own double-click, which
        # stays wired to _show_selected/'Show prompt + image'). No
        # dedicated icon exists yet for "restore a pipeline stage", so
        # this is plain text (flagged in the phase report).
        rounded_button(
            hdr, "Steps…", command=self._show_steps, kind="link",
        ).pack(side="right", padx=(0, 6))
        # the parallel Checker AI's per-row report (GUI rework Phase
        # 16) — a THIRD separate surface from 'Show' (prompt+image) and
        # 'Steps…' (pipeline restore), same focused-row idiom, never
        # overloaded onto either (mirrors _show_steps's own reasoning)
        rounded_button(
            hdr, "Check…", command=self._show_check, kind="link",
        ).pack(side="right", padx=(0, 6))
        # the tiny badge legend — one ●+label per config.BADGES entry,
        # each in its own badge colour (theme-agnostic mid-tones, so ONE
        # explicit foreground reads on both the dark and the cream tree)
        legend = ttk.Frame(self)
        legend.pack(fill="x")
        for _key, (color, label) in BADGES.items():
            ttk.Label(
                legend, text=f"● {label}", foreground=color,
                font=tk_font("mono"),
            ).pack(side="left", padx=(0, 10))
        # a real table: each collection is a collapsible parent row, its
        # images the children; the running one shows live, open. Native
        # column headers + both scrollbars
        wrap = ttk.Frame(self)
        wrap.pack(fill="both", expand=True, pady=(2, 0))
        # three levels: collection > folder > image. Aggregate rows
        # (collection, folder) fill Done/Time/Size; image rows fill
        # AI/Ours/Res/Size. Everything stays column-aligned.
        cols = ("done", "ai", "our", "res", "time", "size", "check")
        self.tree = ttk.Treeview(wrap, columns=cols, height=8)
        self.tree.heading("#0", text="Name")
        # stretch=False EVERYWHERE: widening Name grows the tree's
        # total content width and the horizontal scrollbar takes over,
        # instead of squeezing the other columns
        self.tree.column("#0", width=230, minwidth=140, stretch=False)
        for cid, txt, w, anc in (
            ("done", "Done", 56, "center"),
            ("ai", "AI", 52, "e"),
            ("our", "Ours", 52, "e"),
            ("res", "Res", 100, "center"),
            ("time", "Time", 64, "e"),
            ("size", "Size", 72, "e"),
            # the parallel Checker AI's per-image status (GUI rework
            # Phase 16) — "checking…" / "OK" / "flagged N" / "error",
            # blank for a site where the checker never ran
            ("check", "Check", DASH_CHECK_COL_PX, "center"),
        ):
            self.tree.heading(cid, text=txt)
            self.tree.column(cid, width=w, minwidth=w, anchor=anc,
                             stretch=False)
        vsb = ttk.Scrollbar(
            wrap, orient="vertical", command=self.tree.yview,
            bootstyle="round",
        )
        hsb = ttk.Scrollbar(
            wrap, orient="horizontal", command=self.tree.xview,
            bootstyle="round",
        )
        self.tree.configure(yscrollcommand=vsb.set, xscrollcommand=hsb.set)
        self.tree.grid(row=0, column=0, sticky="nsew")
        vsb.grid(row=0, column=1, sticky="ns")
        hsb.grid(row=1, column=0, sticky="ew")
        wrap.rowconfigure(0, weight=1)
        wrap.columnconfigure(0, weight=1)
        self.tree.bind("<Double-1>", lambda _e: self._show_selected())

        self.reset(active=False)

    def _show_selected(self) -> None:
        info = self._node_info.get(self.tree.focus())
        if info and self._on_show is not None:
            self._on_show(info)

    # --- per-step restore viewer (GUI rework Phase 9) -------------------

    def _show_steps(self) -> None:
        """The 'Steps…' button: open the per-step restore filmstrip for
        the SAME focused/selected row 'Show' above would use. Fully
        self-contained (mirrors ToolPanel's own before/after viewer,
        which likewise never routes through an on_show-style callback)
        — resolves the site-specific rel via dest_for and opens
        StepRestoreWindow directly."""
        info = self._node_info.get(self.tree.focus())
        if not info or info["level"] != "image":
            messagebox.showinfo(
                "PromptPainter",
                "Select one image row first — Steps shows the pipeline"
                " history of a single saved image.",
            )
            return
        if self.jobtemp is None or self.out_base is None:
            messagebox.showinfo(
                "PromptPainter", "No per-step history for this run yet.",
            )
            return
        rel = dest_for(info["drop"], self.slot_key)
        if not self.jobtemp.steps_for(rel):
            messagebox.showinfo(
                "PromptPainter",
                "No kept pipeline stages for this image — either no"
                " post-save step ran, or 'Keep every pipeline step' was"
                " off for this run.",
            )
            return
        # deferred import (see module docstring) — reaches the class
        # tests monkeypatch through the gui package object
        import gui
        gui.StepRestoreWindow(
            self.winfo_toplevel(), f"Steps — {PurePosixPath(rel).name}",
            self.jobtemp, rel, self.out_base / rel,
            on_restored=partial(self.refresh_image_row, info["drop"]),
        )

    # --- the parallel Checker AI's per-row report (GUI rework Phase 16) -

    def _show_check(self) -> None:
        """The 'Check…' button: the SAME report a checker batch row's
        double-click shows (``ai_check_doc_md`` + ``ai_check_image_file``
        — the shared module-level helpers, Rule #5), for the focused
        row's PARALLEL check result. A separate surface from 'Show'
        (prompt+image) and 'Steps…' (pipeline restore) — never
        overloaded onto either, same reasoning as ``_show_steps``.
        ``_check_results`` outlives a single collection (cleared only by
        ``reset()``, unlike ``_child_ids`` — see its own assignment in
        ``reset()``), so this works for any past row in the current run,
        not only the one just checked."""
        info = self._node_info.get(self.tree.focus())
        if not info or info["level"] != "image":
            messagebox.showinfo(
                "PromptPainter",
                "Select one image row first — Check shows the AI"
                " checker's report for a single saved image.",
            )
            return
        result = self._check_results.get(info["drop"])
        if result is None:
            messagebox.showinfo(
                "PromptPainter",
                "No AI check for this image — turn on this site's 'AI"
                " checker' switch before Start, or it has not finished"
                " checking this one yet.",
            )
            return
        rel = result["rel"]
        defects = result.get("defects")
        raw = result.get("raw")
        md = ai_check_doc_md(rel, defects, raw)
        image = ai_check_image_file(rel, self.out_base or Path("."))
        # the Fixer AI's manual buttons (GUI rework Phase 20) — shown
        # only when THIS report actually carries defects; this site's
        # own slot_key (chatgpt/gemini/api_image) is already known, so
        # _build_fix_workers needs no ai.drop_and_site_for guesswork
        # the way AiCheckPanel's own standalone flow does.
        image_worker = website_worker = None
        if defects and self._on_fix_actions is not None and self.out_base:
            image_worker, website_worker = self._on_fix_actions(
                rel, self.out_base, defects, raw or "", self.slot_key,
            )
        # deferred import (see module docstring) — reaches the class
        # tests monkeypatch through the gui package object
        import gui
        gui.DocWindow(
            self.winfo_toplevel(), rel, md,
            copy_text=raw if raw is not None else "\n".join(defects or []),
            hint="Exactly what the vision model reported for this image.",
            image_path=image if image.is_file() else None,
            on_image_fix=image_worker, on_website_fix=website_worker,
        )

    def refresh_image_row(self, drop: str) -> None:
        """Re-read ONE row's resolution/size straight off disk — the
        per-step viewer's refresh after a 'Restore to here' click.
        Badge dots are NOT retroactively recomputed here (no per-row
        action string survives past insert, only the rendered PIL
        dots) — a known cosmetic gap; the restored FILE itself is
        always correct regardless of what its dots still show."""
        child = self._child_ids.get(drop)
        if child is None or self.out_base is None:
            return
        live_path = self.out_base / dest_for(drop, self.slot_key)
        try:
            with Image.open(live_path) as img:
                res = f"{img.width}x{img.height}"
            size = live_path.stat().st_size
        except OSError:
            return
        self.tree.set(child, "res", res)
        self.tree.set(child, "size", fmt_size(size))

    # --- the collapsible Average group ---------------------------------

    def _render_avg_btn(self) -> None:
        self._avg_btn.configure(
            text=("▼  Average" if self._avg_open else "▶  Average")
        )

    def _expand_avg(self) -> None:
        for widgets in self._avg_rows:
            for w in widgets:
                w.grid()

    def _collapse_avg(self) -> None:
        for widgets in self._avg_rows:
            for w in widgets:
                w.grid_remove()

    def _toggle_avg(self) -> None:
        self._avg_open = not self._avg_open
        (self._expand_avg if self._avg_open else self._collapse_avg)()
        self._render_avg_btn()

    # --- state ---------------------------------------------------------

    def reset(
        self, active: bool = True, task_total: int = 0, task_themes: int = 0
    ) -> None:
        self.reset_finished()  # a fresh run hides the CLOSE button again
        self._hide_cap_banner()  # a fresh run starts with a clean slate
        now = time.monotonic()
        self._task_total = task_total
        self._task_themes = task_themes
        self._task_done = 0
        self._task_refused = 0
        self._task_themes_done = 0
        self._task_gen: list[float] = []
        self._task_over: list[float] = []
        self._task_totals: list[float] = []
        self._t_task = now
        self._new_theme("—", 0)
        self.tree.delete(*self.tree.get_children())
        self._node_info.clear()
        # the parallel Checker AI's results (GUI rework Phase 16) — rel
        # + drop_path -> the full item_checked event, so 'Check…' can
        # open ANY past row's report. Scoped like _node_info (the WHOLE
        # run), NOT like _child_ids (reset every collection, see
        # _new_theme) — a late checker result must stay reachable even
        # after the run has moved on to the next collection.
        self._check_results: dict[str, dict] = {}
        self.task_prog_var.set(f"0 / {task_total}")
        self.task_bar.configure(maximum=max(task_total, 1), value=0)
        self.theme_name_var.set("—")
        self.image_var.set("running ..." if active else "idle")
        self.theme_bar.configure(maximum=1, value=0)
        self._refresh()

    def _new_theme(self, name: str, pending: int) -> None:
        self._theme_name = name
        self._theme_pending = pending
        self._theme_done = 0
        self._theme_refused = 0
        self._theme_gen: list[float] = []
        self._theme_over: list[float] = []
        self._theme_totals: list[float] = []
        self._theme_bytes = 0
        self._theme_folders: set[str] = set()
        self._t_theme = time.monotonic()
        # the collection's live row appears on its first image (lazily,
        # so fully-resumed collections never add an empty row); folders
        # nest under it, images under their folder
        self._tree_item: str | None = None
        self._folder_nodes: dict[str, str] = {}  # folder -> tree row id
        self._folder_stats: dict[str, dict] = {}  # folder -> agg dict
        self._child_ids: dict[str, str] = {}  # drop_path -> tree row id

    # --- events (main thread, via the queue pump) ----------------------

    def handle(self, event: dict) -> None:
        kind = event["type"]
        if kind == "sheet_start":
            self._new_theme(event["sheet"], event["pending"])
            self.theme_name_var.set(
                f"{event['sheet']}  ({event['pending']} pending)"
            )
            self.theme_bar.configure(maximum=max(event["pending"], 1), value=0)
        elif kind == "item_start":
            self.image_var.set(
                f"({event['idx']}/{event['of']}) {event['title'][:50]}"
            )
        elif kind == "item_progress":
            # the image is saved — count it live AND add it to the table
            # under its FOLDER now (our-time fills in at item_done)
            self._theme_done += 1
            self._task_done += 1
            self._theme_gen.append(event["gen_s"])
            self._task_gen.append(event["gen_s"])
            self._theme_bytes += event["size"]
            drop = event["drop_path"]
            folder = folder_of(drop)
            self._theme_folders.add(folder)
            fnode = self._ensure_folder(folder)
            st = self._folder_stats[folder]
            st["done"] += 1
            st["size"] += event["size"]
            res = event["orig_res"]
            if event["final_res"] not in ("", event["orig_res"]):
                res = f"{event['orig_res']}→{event['final_res']}"
            # the status badges this image EARNED (post-save steps that
            # really changed it + the safer retry) as a PIL dot strip on
            # the row — badge_keys_for maps the runner's action string
            dots = badge_dots(
                badge_keys_for(event["actions"], event["retried"])
            )
            child = self.tree.insert(
                fnode, "end", text=PurePosixPath(drop).name,
                values=(
                    "", f"{event['gen_s']:.0f}s", "…", res, "",
                    fmt_size(event["size"]), "",
                ),
                **({"image": dots} if dots is not None else {}),
            )
            self._child_ids[drop] = child
            self._node_info[child] = {
                "level": "image", "sheet": self._theme_name, "drop": drop,
            }
            self._update_folder(folder)
            self._update_parent()
        elif kind == "item_done":
            # our-time known now — fill the image's column + folder time
            over = event["over_s"]
            total = event["gen_s"] + over
            self._theme_over.append(over)
            self._task_over.append(over)
            self._theme_totals.append(total)
            self._task_totals.append(total)
            drop = event["drop_path"]
            child = self._child_ids.get(drop)
            if child is not None:
                self.tree.set(child, "our", f"{over:.0f}s")
            folder = folder_of(drop)
            st = self._folder_stats.get(folder)
            if st is not None:
                st["time"] += event["gen_s"] + over
                self._update_folder(folder)
        elif kind == "item_refused":
            self._theme_refused += 1
            self._task_refused += 1
            drop = event.get("drop_path", "")
            fnode = self._ensure_folder(folder_of(drop))
            rnode = self.tree.insert(
                fnode, "end", text=PurePosixPath(drop).name or "refused",
                values=("", "", "", "REFUSED", "", "", ""),
            )
            if drop:
                self._node_info[rnode] = {
                    "level": "image", "sheet": self._theme_name, "drop": drop,
                }
            self._update_parent()
        elif kind == "item_retry":
            self.image_var.set(self.image_var.get() + "  (safer retry…)")
        elif kind == "item_nudge":
            self.image_var.set(self.image_var.get() + "  (continue nudge…)")
        elif kind == "item_checking":
            # the parallel Checker AI (GUI rework Phase 16) just started
            # for this row — posted SYNCHRONOUSLY by PainterGui.
            # _maybe_spawn_checker (main thread, right after item_progress
            # creates the row), never through the worker queue, so it
            # always lands before the background thread's own eventual
            # item_checked.
            child = self._child_ids.get(event["drop_path"])
            if child is not None:
                self.tree.set(child, "check", "checking…")
        elif kind == "item_checked":
            # the background checker thread's result (ai.check_one_image,
            # via PainterGui._run_checker_one) — kind is 'flagged'/'ok'/
            # 'error' (ai.NoKey/AiError already turned into 'error' by
            # check_one_image itself, or by _run_checker_one's own outer
            # safety net; Rule #1: loud on the row, never fatal to this
            # run). Stored in _check_results REGARDLESS of whether the
            # row is still reachable via _child_ids (a late result after
            # the collection moved on) — see _check_results' own comment
            # in reset().
            drop = event["drop_path"]
            self._check_results[drop] = event
            child = self._child_ids.get(drop)
            if child is not None:
                check_kind = event["kind"]
                if check_kind == "flagged":
                    text = f"flagged {len(event['defects'])}"
                elif check_kind == "error":
                    text = "error"
                else:
                    text = "OK"
                self.tree.set(child, "check", text)
                self.tree.item(child, tags=(ai_check_tag(check_kind),))
        elif kind == "sheet_done":
            self._finalize_theme()
            self.image_var.set("—")
        elif kind == "over_cap":
            # this site's JobTemp crossed JOBTEMP_MAX_BYTES (GUI rework
            # Phase 8) — per-step backups have stopped, original-only
            # from here on; LOUD and PERSISTENT (unlike every branch
            # above, which only ever touches the muted state_var/tree),
            # so it survives every later progress event until reset().
            self._show_cap_banner(JOBTEMP_CAP_BANNER_TEXT)
        elif kind == "item_fixed":
            # the API-mode auto-fixer overwrote this image (GUI rework
            # Phase 20, PainterGui._run_fixer_api) — re-read its
            # resolution/size straight off disk (the SAME refresh the
            # Steps… restore viewer's own on_restored callback already
            # uses) and mark the Check column so the row visibly
            # reflects the fix, without disturbing its flagged-count
            # wording (a fresh Check… still shows the ORIGINAL report —
            # a known, deliberate scope boundary, see gui.md).
            drop = event["drop_path"]
            self.refresh_image_row(drop)
            child = self._child_ids.get(drop)
            if child is not None:
                current = self.tree.set(child, "check")
                self.tree.set(
                    child, "check",
                    f"{current} → fixed" if current else "fixed",
                )
        self._refresh()

    def _ensure_parent(self) -> str:
        """The collection's row — created (open) the first time an image
        of it lands, so a running collection shows live."""
        if self._tree_item is None:
            name = f"{self._theme_name}   · running…"
            self._tree_item = self.tree.insert(
                "", "end", text=name, open=True,
                values=self._parent_values(),
            )
            self._node_info[self._tree_item] = {
                "level": "collection", "sheet": self._theme_name,
            }
        return self._tree_item

    def _ensure_folder(self, folder: str) -> str:
        node = self._folder_nodes.get(folder)
        if node is None:
            parent = self._ensure_parent()
            self._folder_stats[folder] = {"done": 0, "size": 0, "time": 0.0}
            node = self.tree.insert(
                parent, "end", text=folder, open=True,
                values=("0", "", "", "", "", fmt_size(0), ""),
            )
            self._folder_nodes[folder] = node
            self._node_info[node] = {
                "level": "folder", "sheet": self._theme_name,
                "folder": folder,
            }
        return node

    def _parent_values(self) -> tuple:
        wall = time.monotonic() - self._t_theme
        return (
            f"{self._theme_done}/{self._theme_pending}", "", "", "",
            fmt_duration(wall), fmt_size(self._theme_bytes), "",
        )

    def _update_parent(self) -> None:
        if self._tree_item is not None:
            self.tree.item(self._tree_item, values=self._parent_values())

    def _update_folder(self, folder: str) -> None:
        node = self._folder_nodes.get(folder)
        st = self._folder_stats.get(folder)
        if node is not None and st is not None:
            self.tree.item(
                node,
                values=(
                    str(st["done"]), "", "", "",
                    fmt_duration(st["time"]), fmt_size(st["size"]), "",
                ),
            )

    def _finalize_theme(self) -> None:
        if self._tree_item is None:
            return  # nothing ran this collection (fully resumed / skipped)
        self._task_themes_done += 1
        # stamp the final summary and collapse the finished collection
        self.tree.item(
            self._tree_item, text=self._theme_name,
            values=self._parent_values(), open=False,
        )

    def _refresh(self) -> None:
        now = time.monotonic()
        # bars
        self.theme_bar.configure(
            maximum=max(self._theme_pending, 1),
            value=self._theme_done + self._theme_refused,
        )
        self.task_bar.configure(
            maximum=max(self._task_total, 1),
            value=self._task_done + self._task_refused,
        )
        self.task_prog_var.set(
            f"{self._task_done + self._task_refused} / {self._task_total}"
            f"   ({self._task_themes_done}/{self._task_themes} done)"
        )
        theme = _scope_stats(
            self._theme_done, self._theme_refused, self._theme_gen,
            self._theme_over, self._theme_totals, self._theme_pending,
            now - self._t_theme,
        )
        task = _scope_stats(
            self._task_done, self._task_refused, self._task_gen,
            self._task_over, self._task_totals, self._task_total,
            now - self._t_task,
        )
        for key in _STAT_KEYS:
            self.cells[("theme", key)].set(theme[key])
            self.cells[("task", key)].set(task[key])
