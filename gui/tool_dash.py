"""``ToolPanel``/``AiCheckPanel``/``DashGrid`` pulled out of
``gui/__init__.py`` (root Rule #20 god-file refactor, step 6/8): the
four standalone in-place tools' dashboard panel (folder>image tree,
before/after viewer + restore), the AI image checker's own dashboard
panel (flagged/OK counts, the defect viewer, resend/clear actions) and
the responsive grid that lays out every active job panel.

Both panels subclass ``JobPanel`` (``gui.dash_panels``) for the shared
header/close/pause plumbing and the folder>image tree-node helpers.

``DocWindow`` is opened via a deferred ``import gui`` (NOT a module-
level ``from .viewers import DocWindow``) inside
``AiCheckPanel._on_activate`` — the same late-binding idiom
``gui.dash_panels.DashPanel`` uses for the identical reason: tests
(``test_gui_checker.py``, ``test_gui_fixer.py``) do
``monkeypatch.setattr(gui, "DocWindow", fake)`` and expect the PATCHED
class to fire, which a bare top-of-module import would never see.
``BeforeAfterWindow`` (``ToolPanel``'s before/after viewer) has no such
test coverage — imported directly, real-path, from ``gui.viewers``.
"""

from __future__ import annotations

import math
import tkinter as tk
from functools import partial
from pathlib import Path, PurePosixPath
from tkinter import messagebox, ttk

from painter.config import (
    GRID_COLS_BY_COUNT,
    JOB_LABEL,
    JOB_METRIC,
    JOB_ORDER,
    fmt_op_duration,
    fmt_pct,
    fmt_size,
)
from .dash_helpers import (
    ai_check_doc_md,
    ai_check_image_file,
    ai_check_tag,
    build_job_tree,
    fmt_time_summary,
)
from .dash_panels import JobPanel
from .theme import TOOL_CHANGED_TAG, TOOL_SKIP_TAG
from .viewers import BeforeAfterWindow
from .widgets import folder_of, rels_in_folder, rounded_button

# --- AI checker (Rule #4) ---------------------------------------------
AI_CHECK_DEFECT_COL_PX = 64   # the checker tree's 'Defects' count column
AI_CHECK_TIME_COL_PX = 64     # the checker tree's per-image 'Time' column
AI_CHECK_FIRST_COL_PX = 230   # the checker tree's 'First defect' column


class ToolPanel(JobPanel):
    """One in-place tool's live view (BG removal / Crop / Upscale /
    Aspect ratio): a progress bar, an aggregate metric label, and a
    collection > folder > image table where each image row shows its
    BEFORE / AFTER resolution and the tool's own % (removed / reduction
    / increase / deformation).

    CHANGED (restorable) rows show in a striking green/teal; SKIPPED
    (unchanged) rows in muted grey. Double-click an image row for a
    BEFORE/AFTER viewer with Restore; double-click a FOLDER node for a
    viewer of ONLY that folder's changed images with RESTORE ALL; double-
    click the collection (top) node for ALL the job's changed images. The
    job's originals are backed up per file (``self.jobtemp``) before the
    op, so a restore always puts the original back.
    """

    def __init__(self, master, kind: str, on_close=None, on_pause=None):
        super().__init__(
            master, kind, on_show=None, on_close=on_close, on_pause=on_pause,
        )
        self._metric_name = JOB_METRIC[kind]
        self.folder: Path | None = None       # the picked folder
        # self.jobtemp: painter.jobtemp.JobTemp | None — inherited from
        # JobPanel (shared with DashPanel, GUI rework Phase 9)

        self.prog = ttk.Progressbar(
            self, bootstyle="info-striped", maximum=1, value=0
        )
        self.prog.pack(fill="x", pady=(6, 4))
        self.metric_var = tk.StringVar(value="—")
        ttk.Label(
            self, textvariable=self.metric_var, style="Value.TLabel"
        ).pack(anchor="w", pady=(0, 2))
        # execution time — total over PROCESSED images + per-image average
        # (skipped images contribute no time), mirroring the gen panels
        self.time_var = tk.StringVar(value="⏱ —")
        ttk.Label(
            self, textvariable=self.time_var, style="Muted.TLabel"
        ).pack(anchor="w", pady=(0, 4))

        # BG removal changes ALPHA, not dimensions — its Before/After
        # resolution are always identical and meaningless, so its panel
        # DROPS those two columns (owner 2026-07-19); the dimensional
        # tools (crop / upscale / aspect) keep them.
        self._is_bg = kind == "bg"
        metric_cols = (
            ("pct", "%", 72 if self._is_bg else 64, "e"),
            ("time", "Time", 64, "e"),
            ("size", "Size", 72, "e"),
        )
        col_specs = metric_cols if self._is_bg else (
            ("before", "Before", 92, "center"),
            ("after", "After", 92, "center"),
            *metric_cols,
        )
        self._cols = tuple(c[0] for c in col_specs)
        self.tree = build_job_tree(self, col_specs)
        self.tree.bind("<Double-1>", self._on_activate)

        self.reset(active=False, total=0)

    # --- state ---------------------------------------------------------

    def reset(self, active: bool = True, total: int = 0) -> None:
        self.reset_finished()
        self._total = total
        self._changed = 0
        self._skipped = 0
        self._pcts: list[float] = []
        self._times: list[float] = []   # per-PROCESSED-image op seconds
        self._tree_root: str | None = None
        self._folder_nodes: dict[str, str] = {}
        self._image_rows: dict[str, str] = {}
        self.tree.delete(*self.tree.get_children())
        self._node_info.clear()
        self.prog.configure(maximum=max(total, 1), value=0)
        self.state_var.set("running …" if active else "idle")
        self._update_metric()

    # --- events (main thread, via the queue pump) ----------------------

    def handle(self, event: dict) -> None:
        kind = event["type"]
        if kind == "sheet_start":
            self._total = event["total"]
            self.prog.configure(
                maximum=max(self._total, 1),
                value=self._changed + self._skipped,
            )
        elif kind == "item_start":
            self.state_var.set(
                f"({event['idx']}/{event['of']}) {event['title'][:50]}"
            )
        elif kind == "item_done":
            self._changed += 1
            self._pcts.append(event["pct"])
            self._times.append(event["time"])
            self._insert_image_row(event["rel"], event)
            self._advance()
        elif kind == "item_refused":
            self._skipped += 1
            self._insert_refused_row(event["rel"])
            self._advance()
        elif kind == "sheet_done":
            self.state_var.set(
                f"done — {self._changed} changed, {self._skipped} skipped"
            )
            self._update_metric()

    def _advance(self) -> None:
        self.prog.configure(value=self._changed + self._skipped)
        self._update_metric()

    def _update_metric(self) -> None:
        counts = f"{self._changed} changed, {self._skipped} skipped"
        if self._pcts:
            avg = sum(self._pcts) / len(self._pcts)
            self.metric_var.set(
                f"avg {fmt_pct(avg)}% {self._metric_name}   ·   {counts}"
            )
        else:
            self.metric_var.set(f"{self._metric_name}: —   ·   {counts}")
        self._update_time()

    def _update_time(self) -> None:
        """Total op time over PROCESSED images + the per-image average
        (skipped images add no time)."""
        self.time_var.set(fmt_time_summary(self._times))

    # --- tree building (root/folder nodes inherited from JobPanel) -----

    def _insert_image_row(self, rel: str, event: dict) -> None:
        fnode = self._ensure_folder(folder_of(rel))
        pct = f"{fmt_pct(event['pct'])}%"
        metric = (pct, fmt_op_duration(event["time"]), fmt_size(event["size"]))
        # the BG panel has no Before/After columns; the dimensional tools do
        values = metric if self._is_bg else (
            event["before"], event["after"], *metric
        )
        # a CHANGED (restorable) row gets the striking green/teal tag so it
        # POPS against the muted-grey SKIPPED rows (owner 2026-07-19)
        row = self.tree.insert(
            fnode, "end", text=PurePosixPath(rel).name, values=values,
            tags=(TOOL_CHANGED_TAG,),
        )
        self._node_info[row] = {"level": "image", "rel": rel, "has_backup": True}
        self._image_rows[rel] = row

    def _insert_refused_row(self, rel: str) -> None:
        fnode = self._ensure_folder(folder_of(rel))
        # the '—' sits in the % column: index 0 (BG) or 2 (dimensional)
        values = ("—", "", "") if self._is_bg else ("", "", "—", "", "")
        # tint the SKIPPED row muted (owner 2026-07-19) — this bucket now
        # also holds the many 0px crops the crop-fix sends to skipped
        self.tree.insert(
            fnode, "end", text=PurePosixPath(rel).name, values=values,
            tags=(TOOL_SKIP_TAG,),
        )

    # --- before/after viewer + restore ---------------------------------

    def _on_activate(self, _event) -> None:
        info = self._node_info.get(self.tree.focus())
        if not info:
            return
        level = info["level"]
        if level == "image":
            self._show_image_beforeafter(info["rel"])
        elif level == "folder":
            # ONLY this folder's images (owner 2026-07-19) — not the union
            self._show_folder_beforeafter(info["folder"])
        else:  # the collection (top) node — the whole job's changed images
            self._show_all_beforeafter()

    def _pair_for(self, rel: str) -> dict | None:
        """The {rel, before, after} pair for one image, or None when
        there is no backup / result on disk (a no-op or a restored
        image)."""
        if self.jobtemp is None or self.folder is None:
            return None
        before = self.jobtemp.before_path(rel)
        after = self.folder / rel
        if before is None or not after.exists():
            return None
        return {"rel": rel, "before": before, "after": after}

    def _show_image_beforeafter(self, rel: str) -> None:
        pair = self._pair_for(rel)
        if pair is None:
            messagebox.showinfo(
                "PromptPainter",
                "No before/after for this image — nothing was changed,"
                " or it was already restored.",
            )
            return
        BeforeAfterWindow(
            self.winfo_toplevel(),
            f"{JOB_LABEL[self.slot_key]} — {PurePosixPath(rel).name}",
            [pair], restore_label="Restore",
            restore_cb=lambda: self.restore_one(rel),
        )

    def _show_folder_beforeafter(self, folder: str) -> None:
        """The before/after viewer scoped to ONE folder's changed images —
        double-clicking a folder node restores JUST that folder, never the
        whole job (owner 2026-07-19)."""
        pairs = [
            pair for rel in rels_in_folder(self._image_rows, folder)
            if (pair := self._pair_for(rel)) is not None
        ]
        if not pairs:
            messagebox.showinfo(
                "PromptPainter",
                "No changed images in this folder — nothing was changed,"
                " or all were already restored.",
            )
            return
        BeforeAfterWindow(
            self.winfo_toplevel(),
            f"{JOB_LABEL[self.slot_key]} — {folder} ({len(pairs)})",
            pairs, restore_label="RESTORE ALL",
            restore_cb=lambda: self.restore_folder(folder),
            subtitle=(
                f"Before / after of every changed image in {folder} —"
                " RESTORE ALL reverts ONLY this folder."
            ),
        )

    def _show_all_beforeafter(self) -> None:
        pairs = [
            pair for rel in self._image_rows
            if (pair := self._pair_for(rel)) is not None
        ]
        if not pairs:
            messagebox.showinfo(
                "PromptPainter",
                "No changed images to show — nothing was changed, or all"
                " were already restored.",
            )
            return
        BeforeAfterWindow(
            self.winfo_toplevel(),
            f"{JOB_LABEL[self.slot_key]} — all changed images ({len(pairs)})",
            pairs, restore_label="RESTORE ALL",
            restore_cb=self.restore_all,
        )

    def restore_one(self, rel: str) -> None:
        if self.jobtemp is not None and self.jobtemp.restore_one(rel):
            self._mark_restored(rel)

    def restore_folder(self, folder: str) -> int:
        """Restore ONLY the images under ``folder`` (the folder-scoped
        RESTORE ALL) — mirrors ``restore_all`` but over that folder's rels,
        so a folder double-click never reverts other folders."""
        if self.jobtemp is None:
            return 0
        count = 0
        for rel in rels_in_folder(self._image_rows, folder):
            if self.jobtemp.restore_one(rel):
                self._mark_restored(rel)
                count += 1
        return count

    def restore_all(self) -> int:
        if self.jobtemp is None:
            return 0
        count = self.jobtemp.restore_all()
        for rel in list(self._image_rows):
            self._mark_restored(rel)
        return count

    def _mark_restored(self, rel: str) -> None:
        row = self._image_rows.get(rel)
        if row is not None:
            self.tree.set(row, "pct", "restored")
            info = self._node_info.get(row)
            if info is not None:
                info["has_backup"] = False


class AiCheckPanel(JobPanel):
    """The AI image checker's dashboard panel (owner 2026-07-20): a
    progress bar, the flagged/OK counts, and a folder > image table —
    FLAGGED rows striking (the changed bucket) with their DEFECT COUNT
    as the row metric, OK rows muted (the skipped bucket), API failures
    counted loudly as errors. Double-click a flagged row for the full
    defect list + the image itself (a DocWindow).

    Two panel actions: **Send flagged to generator** re-queues every
    flagged image that matches a QUEUED collection on its ORIGINAL site
    (``only=`` + a per-item fix note appended to the prompt), and
    **Clear flags** wipes this run's entries from
    ``<out>/_state/ai_flags.json``. The panel never touches the images
    or the flags itself — both actions go through the GUI callbacks.
    """

    def __init__(
        self, master, on_close=None, on_resend=None, on_clear=None,
        on_pause=None, on_fix_actions=None,
    ):
        super().__init__(
            master, "aicheck", on_show=None, on_close=on_close,
            on_pause=on_pause,
        )
        self._on_resend = on_resend  # called with {flag key: [defects]}
        self._on_clear = on_clear    # called with (out_base, keys) -> int
        # the Fixer AI's manual-button builder (GUI rework Phase 20) —
        # PainterGui._build_fix_workers; this standalone panel has no
        # site of its own (it can check ANY folder), so it always passes
        # jobtemp_slot=None and lets that method resolve the site (if
        # any) via ai.drop_and_site_for — see _on_activate below.
        self._on_fix_actions = on_fix_actions
        self.folder: Path | None = None    # the checked folder
        self.out_base: Path | None = None  # the flags' out base

        self.prog = ttk.Progressbar(
            self, bootstyle="info-striped", maximum=1, value=0
        )
        self.prog.pack(fill="x", pady=(6, 4))
        self.metric_var = tk.StringVar(value="—")
        ttk.Label(
            self, textvariable=self.metric_var, style="Value.TLabel"
        ).pack(anchor="w", pady=(0, 2))
        # execution time — total over CHECKED images + the per-image
        # average, mirroring the in-place tool panels (the owner wants to
        # see how long the paced checker actually works)
        self.time_var = tk.StringVar(value="⏱ —")
        ttk.Label(
            self, textvariable=self.time_var, style="Muted.TLabel"
        ).pack(anchor="w", pady=(0, 4))

        col_specs = (
            ("defects", "Defects", AI_CHECK_DEFECT_COL_PX, "e"),
            ("time", "Time", AI_CHECK_TIME_COL_PX, "e"),
            ("first", "First defect", AI_CHECK_FIRST_COL_PX, "w"),
        )
        self._cols = tuple(c[0] for c in col_specs)
        self.tree = build_job_tree(self, col_specs)
        self.tree.bind("<Double-1>", self._on_activate)

        actions = ttk.Frame(self)
        actions.pack(fill="x", pady=(6, 0))
        self.btn_resend = rounded_button(
            actions, "Send flagged to generator",
            command=self._do_resend, kind="info",
        )
        self.btn_resend.pack(side="left")
        self.btn_clear = rounded_button(
            actions, "Clear flags", command=self._do_clear,
            kind="danger-outline",
        )
        self.btn_clear.pack(side="left", padx=6)

        self.reset(active=False, total=0)

    # --- state ---------------------------------------------------------

    def reset(self, active: bool = True, total: int = 0) -> None:
        self.reset_finished()
        self._total = total
        self._flagged: dict[str, list[str]] = {}  # flag key -> defects
        self._raw: dict[str, str | None] = {}     # flag key -> raw answer
        self._times: list[float] = []             # per-CHECKED-image op s
        self._ok = 0
        self._errors = 0
        self._tree_root: str | None = None
        self._folder_nodes: dict[str, str] = {}
        self._image_rows: dict[str, str] = {}
        self.tree.delete(*self.tree.get_children())
        self._node_info.clear()
        self.prog.configure(maximum=max(total, 1), value=0)
        self.state_var.set("running …" if active else "idle")
        self._update_metric()

    # --- events (main thread, via the queue pump) ----------------------

    def handle(self, event: dict) -> None:
        kind = event["type"]
        if kind == "sheet_start":
            self._total = event["total"]
            self.prog.configure(maximum=max(self._total, 1), value=0)
        elif kind == "item_start":
            self.state_var.set(
                f"({event['idx']}/{event['of']}) {event['title'][:50]}"
            )
        elif kind in ("item_flagged", "item_ok", "item_error"):
            rel = event["rel"]
            self._times.append(event["time"])
            self._raw[rel] = event.get("raw")  # verbatim, for the viewer
            if kind == "item_flagged":
                self._flagged[rel] = list(event["defects"])
                self._insert_row(rel, event["defects"], event["time"])
            elif kind == "item_ok":
                self._ok += 1
                self._insert_row(rel, None, event["time"])
            else:
                self._errors += 1
                self._insert_row(rel, None, event["time"], error=True)
            self._advance()
        elif kind == "sheet_done":
            done = f"done — {len(self._flagged)} flagged, {self._ok} OK"
            if self._errors:
                done += f", {self._errors} error(s)"
            self.state_var.set(done)
            self._update_metric()

    def _advance(self) -> None:
        self.prog.configure(
            value=len(self._flagged) + self._ok + self._errors
        )
        self._update_metric()

    def _update_metric(self) -> None:
        text = f"{len(self._flagged)} flagged   ·   {self._ok} OK"
        if self._errors:
            text += f"   ·   {self._errors} error(s)"
        self.metric_var.set(text)
        self.time_var.set(fmt_time_summary(self._times))

    def _insert_row(
        self, rel: str, defects: list | None, time_s: float,
        error: bool = False,
    ) -> None:
        fnode = self._ensure_folder(folder_of(rel))
        time_txt = fmt_op_duration(time_s)
        if defects:
            # the CHANGED (striking) bucket — this image needs work
            values = (str(len(defects)), time_txt, defects[0])
            kind = "flagged"
        elif error:
            values = ("!", time_txt, "API error — see the Log")
            kind = "error"
        else:
            values = ("OK", time_txt, "")
            kind = "ok"
        row = self.tree.insert(
            fnode, "end", text=PurePosixPath(rel).name, values=values,
            tags=(ai_check_tag(kind),),
        )
        self._node_info[row] = {"level": "image", "rel": rel}
        self._image_rows[rel] = row

    # --- the defect viewer + panel actions ------------------------------

    def _on_activate(self, _event) -> None:
        """Double-click ANY checked row (flagged, OK or error) → a
        DocWindow with the parsed defects (when any), the VERBATIM AI
        response and the image itself, so the owner can inspect exactly
        what the model said about this exact image (owner 2026-07-21)."""
        info = self._node_info.get(self.tree.focus())
        if not info or info.get("level") != "image":
            return
        rel = info["rel"]
        defects = self._flagged.get(rel)
        raw = self._raw.get(rel)
        if not defects and raw is None:
            return  # nothing was captured for this row
        md = ai_check_doc_md(rel, defects, raw)
        image = ai_check_image_file(rel, self.out_base or Path("."))
        # the Fixer AI's manual buttons (GUI rework Phase 20) — see
        # DashPanel._show_check's own identical wiring (Rule #5, the
        # SAME _build_fix_workers call); jobtemp_slot=None since this
        # standalone panel has no site of its own to hand over.
        image_worker = website_worker = None
        if defects and self._on_fix_actions is not None and self.out_base:
            image_worker, website_worker = self._on_fix_actions(
                rel, self.out_base, defects, raw or "", None,
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

    def _do_resend(self) -> None:
        if not self._flagged:
            messagebox.showinfo(
                "PromptPainter",
                "No flagged images in this run — nothing to re-send.",
            )
            return
        if self._on_resend is not None:
            self._on_resend(dict(self._flagged))

    def _do_clear(self) -> None:
        if not self._flagged:
            messagebox.showinfo(
                "PromptPainter",
                "No flagged images in this run — nothing to clear.",
            )
            return
        if self._on_clear is None or self.out_base is None:
            return
        count = self._on_clear(self.out_base, list(self._flagged))
        for rel in self._flagged:
            row = self._image_rows.get(rel)
            if row is not None:
                self.tree.set(row, "defects", "cleared")
        self._flagged.clear()
        self._update_metric()
        self.state_var.set(f"{count} flag(s) cleared")


class DashGrid(ttk.Frame):
    """The dashboard's up-to-6 per-job panels in a responsive grid, gen
    sites FIRST.

    Panels are added on job START and removed on CLOSE; the grid
    re-flows by the active count (``GRID_COLS_BY_COUNT``, row-major over
    ``JOB_ORDER`` — so ChatGPT + Gemini always fill the top row and, at
    N=5, the 6th cell stays empty). Cells share a ``uniform`` group so
    they are equal and evenly fill the area. A muted placeholder shows
    when no job has run yet.
    """

    def __init__(self, master):
        super().__init__(master)
        self._panels: dict[str, JobPanel] = {}
        self._active: list[str] = []  # gridded slots (rendered in JOB_ORDER)
        self._placeholder = ttk.Label(
            self,
            text="No jobs yet — press a site Start, or a tool button above.",
            style="Muted.TLabel", anchor="center",
        )

    def attach(self, panels: dict) -> None:
        self._panels = panels
        self.relayout()

    def active(self) -> list[str]:
        return [k for k in JOB_ORDER if k in self._active]

    def add(self, kind: str) -> None:
        if kind not in self._active:
            self._active.append(kind)
        self.relayout()

    def remove(self, kind: str) -> None:
        if kind in self._active:
            self._active.remove(kind)
        self.relayout()

    def relayout(self) -> None:
        self._placeholder.grid_forget()
        for panel in self._panels.values():
            panel.grid_forget()
        for i in range(3):  # reset every row/col this grid can ever use
            self.rowconfigure(i, weight=0, uniform="")
            self.columnconfigure(i, weight=0, uniform="")
        slots = self.active()
        n = len(slots)
        if n == 0:
            self._placeholder.grid(row=0, column=0, sticky="nsew")
            self.rowconfigure(0, weight=1)
            self.columnconfigure(0, weight=1)
            return
        cols = GRID_COLS_BY_COUNT[n]
        rows = math.ceil(n / cols)
        for idx, kind in enumerate(slots):
            r, c = divmod(idx, cols)
            self._panels[kind].grid(
                row=r, column=c, sticky="nsew", padx=4, pady=4
            )
        for c in range(cols):
            self.columnconfigure(c, weight=1, uniform="dashcol")
        for r in range(rows):
            self.rowconfigure(r, weight=1, uniform="dashrow")
