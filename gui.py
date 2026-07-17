"""PromptPainter GUI — the owner's front door.

A tkinter window over the same engine the CLI uses: queue one or MORE
prompt-sheet `.md` files (each file is a THEME), pick the output
folder, tick Gemini / ChatGPT / both, choose each site's background,
open the automation Chrome (log in once — the profile persists),
check, start. Both sites run in PARALLEL, one thread and one tab
each; each works through the theme queue IN ORDER, so a quota stop on
one site never costs finished work — progress and the report live
beside the images and every run resumes.

Two views (tabs): a **Dashboard** (per-site progress for the current
theme AND the whole task, two average timings, and a collapsible list
of finished themes) and the detailed **Log**.
"""

from __future__ import annotations

import json
import queue
import threading
import time
import tkinter as tk
from dataclasses import replace
from datetime import datetime
from functools import partial
from pathlib import Path, PurePosixPath
from tkinter import filedialog, messagebox, scrolledtext, ttk

from painter.config import (
    BACKGROUND_CHOICES,
    CDP_URL,
    DEFAULT_OUT_DIR,
    PROGRESS_SUFFIX,
    SITES,
    TIMING,
    fmt_duration,
    fmt_size,
    prompt_suffix,
)
from painter.sheet_parser import Sheet, SheetError, parse_sheet

# accent colours (shared by the dashboard and the selection list)
C_DONE = "#2e7d32"      # green — finished
C_DONE_SOFT = "#558b2f"  # olive — partly done
C_ADVICE = "#b26a00"     # orange — sheet advice (REUSE / not approved)
C_SUPERSEDED = "#c62828"  # red — superseded
C_MUTED = "#666666"


def setup_style(root: tk.Tk) -> None:
    """A light, consistent ttk look — Segoe UI, roomy padding, accents."""
    style = ttk.Style(root)
    try:
        style.theme_use("clam")
    except tk.TclError:
        pass
    base = ("Segoe UI", 10)
    style.configure(".", font=base)
    style.configure("TButton", padding=(10, 5))
    style.configure("TLabelframe", padding=8)
    style.configure("TLabelframe.Label", font=("Segoe UI", 10, "bold"))
    style.configure("Head.TLabel", font=("Segoe UI", 11, "bold"))
    style.configure("Big.TLabel", font=("Segoe UI", 15, "bold"))
    style.configure("Value.TLabel", font=("Segoe UI", 10, "bold"))
    style.configure("Muted.TLabel", foreground=C_MUTED)
    style.configure("Mono.TLabel", font=("Consolas", 9), foreground=C_MUTED)
    style.configure(
        "Expander.TButton", anchor="w", padding=(6, 4),
        font=("Segoe UI", 10, "bold"),
    )
    style.configure(
        "Task.Horizontal.TProgressbar", troughcolor="#e6e6e6",
        background=C_DONE,
    )
    style.configure(
        "Theme.Horizontal.TProgressbar", troughcolor="#e6e6e6",
        background="#1565c0",
    )


class ScrollFrame(ttk.Frame):
    """A vertically (optionally also horizontally) scrollable frame.

    Add children to ``self.body``. Without horizontal scroll the body
    is stretched to the canvas width (content wraps, no x scrollbar);
    with it the body keeps its natural width and a horizontal bar
    appears.
    """

    def __init__(self, master, horizontal: bool = False):
        super().__init__(master)
        self._stretch = not horizontal
        self.canvas = tk.Canvas(self, highlightthickness=0)
        vbar = ttk.Scrollbar(
            self, orient="vertical", command=self.canvas.yview
        )
        self.canvas.configure(yscrollcommand=vbar.set)
        self.body = ttk.Frame(self.canvas)
        self._win = self.canvas.create_window(
            (0, 0), window=self.body, anchor="nw"
        )
        self.body.bind("<Configure>", self._on_body)
        self.canvas.bind("<Configure>", self._on_canvas)
        vbar.pack(side="right", fill="y")
        if horizontal:
            hbar = ttk.Scrollbar(
                self, orient="horizontal", command=self.canvas.xview
            )
            self.canvas.configure(xscrollcommand=hbar.set)
            hbar.pack(side="bottom", fill="x")
        self.canvas.pack(side="left", fill="both", expand=True)
        self.canvas.bind("<Enter>", self._bind_wheel)
        self.canvas.bind("<Leave>", self._unbind_wheel)
        # a global <MouseWheel> binding outlives the widget — drop it
        # when the canvas is destroyed (e.g. the Select window closes
        # while the pointer is still over it) so it never fires on a
        # dead widget
        self.canvas.bind("<Destroy>", self._unbind_wheel)

    def _on_body(self, _event) -> None:
        self.canvas.configure(scrollregion=self.canvas.bbox("all"))

    def _on_canvas(self, event) -> None:
        if self._stretch:
            self.canvas.itemconfigure(self._win, width=event.width)

    def _bind_wheel(self, _event) -> None:
        self.canvas.bind_all("<MouseWheel>", self._on_wheel)

    def _unbind_wheel(self, _event) -> None:
        try:
            self.canvas.unbind_all("<MouseWheel>")
        except tk.TclError:
            pass

    def _on_wheel(self, event) -> None:
        try:
            self.canvas.yview_scroll(int(-event.delta / 120), "units")
        except tk.TclError:
            # the canvas was destroyed but the global binding lingered
            self.canvas.unbind_all("<MouseWheel>")


# ---------------------------------------------------------------------
# Dashboard
# ---------------------------------------------------------------------

_METRICS = [
    ("done", "Done"),
    ("refused", "Refused"),
    ("gen", "AI generate avg"),
    ("over", "Our time avg"),
    ("tempo", "Tempo"),
    ("eta", "ETA"),
]


def _scope_stats(done, refused, gen_times, over_times, total, elapsed):
    """Display strings for one scope (a collection or the whole task)."""
    remaining = max(total - done - refused, 0)
    gen = f"{sum(gen_times) / len(gen_times):.0f} s" if gen_times else "—"
    over = f"{sum(over_times) / len(over_times):.0f} s" if over_times else "—"
    if done and elapsed > 0:
        tempo = f"{done / (elapsed / 3600):.0f} /h"
        eta = (
            f"{remaining * (elapsed / done) / 60:.0f} min"
            if remaining
            else "done"
        )
    else:
        tempo = "—"
        eta = "—"
    return {
        "done": f"{done}/{total}" if total else str(done),
        "refused": str(refused),
        "gen": gen,
        "over": over,
        "tempo": tempo,
        "eta": eta,
    }


class DashPanel(ttk.Frame):
    """One site's live view: current theme, whole-task totals, history.

    Driven only by the runner's structured events (main thread).
    """

    def __init__(self, master, site_name: str):
        super().__init__(master, padding=6)
        self._name = site_name

        ttk.Label(self, text=site_name, style="Big.TLabel").pack(anchor="w")

        # whole-task progress
        task = ttk.Frame(self)
        task.pack(fill="x", pady=(6, 2))
        ttk.Label(task, text="Task", width=7).pack(side="left")
        self.task_prog_var = tk.StringVar(value="0 / 0")
        ttk.Label(
            task, textvariable=self.task_prog_var, style="Value.TLabel"
        ).pack(side="right")
        self.task_bar = ttk.Progressbar(
            self, style="Task.Horizontal.TProgressbar", maximum=1, value=0
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
            self, style="Theme.Horizontal.TProgressbar", maximum=1, value=0
        )
        self.theme_bar.pack(fill="x", pady=(2, 6))

        # the two-scope stats table
        grid = ttk.Frame(self)
        grid.pack(fill="x", pady=(2, 6))
        ttk.Label(grid, text="", width=14).grid(row=0, column=0)
        ttk.Label(
            grid, text="This one", style="Head.TLabel", width=11
        ).grid(row=0, column=1, sticky="e")
        ttk.Label(grid, text="Whole run", style="Head.TLabel", width=11).grid(
            row=0, column=2, sticky="e"
        )
        self.cells: dict[tuple[str, str], tk.StringVar] = {}
        for r, (key, label) in enumerate(_METRICS, start=1):
            ttk.Label(grid, text=label).grid(row=r, column=0, sticky="w")
            for c, scope in ((1, "theme"), (2, "task")):
                var = tk.StringVar(value="—")
                self.cells[(scope, key)] = var
                ttk.Label(
                    grid, textvariable=var, style="Value.TLabel", anchor="e"
                ).grid(row=r, column=c, sticky="e", padx=4)
        grid.columnconfigure(0, weight=1)

        ttk.Separator(self).pack(fill="x", pady=4)
        ttk.Label(
            self, text="Collections (running + done)", style="Head.TLabel"
        ).pack(anchor="w")
        # a real table: each collection is a collapsible parent row, its
        # images the children; the running one shows live, open. Native
        # column headers + both scrollbars
        wrap = ttk.Frame(self)
        wrap.pack(fill="both", expand=True, pady=(2, 0))
        # three levels: collection > folder > image. Aggregate rows
        # (collection, folder) fill Done/Time/Size; image rows fill
        # AI/Ours/Res/Size. Everything stays column-aligned.
        cols = ("done", "ai", "our", "res", "time", "size")
        self.tree = ttk.Treeview(wrap, columns=cols, height=8)
        self.tree.heading("#0", text="Name")
        self.tree.column("#0", width=230, minwidth=140, stretch=True)
        for cid, txt, w, anc in (
            ("done", "Done", 56, "center"),
            ("ai", "AI", 52, "e"),
            ("our", "Ours", 52, "e"),
            ("res", "Res", 100, "center"),
            ("time", "Time", 64, "e"),
            ("size", "Size", 72, "e"),
        ):
            self.tree.heading(cid, text=txt)
            self.tree.column(cid, width=w, minwidth=w, anchor=anc,
                             stretch=False)
        vsb = ttk.Scrollbar(wrap, orient="vertical", command=self.tree.yview)
        hsb = ttk.Scrollbar(
            wrap, orient="horizontal", command=self.tree.xview
        )
        self.tree.configure(yscrollcommand=vsb.set, xscrollcommand=hsb.set)
        self.tree.grid(row=0, column=0, sticky="nsew")
        vsb.grid(row=0, column=1, sticky="ns")
        hsb.grid(row=1, column=0, sticky="ew")
        wrap.rowconfigure(0, weight=1)
        wrap.columnconfigure(0, weight=1)

        self.reset(active=False)

    # --- state ---------------------------------------------------------

    def reset(
        self, active: bool = True, task_total: int = 0, task_themes: int = 0
    ) -> None:
        now = time.monotonic()
        self._task_total = task_total
        self._task_themes = task_themes
        self._task_done = 0
        self._task_refused = 0
        self._task_themes_done = 0
        self._task_gen: list[float] = []
        self._task_over: list[float] = []
        self._t_task = now
        self._new_theme("—", 0)
        self.tree.delete(*self.tree.get_children())
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
            folder = self._folder_of(drop)
            self._theme_folders.add(folder)
            fnode = self._ensure_folder(folder)
            st = self._folder_stats[folder]
            st["done"] += 1
            st["size"] += event["size"]
            res = event["orig_res"]
            if event["final_res"] not in ("", event["orig_res"]):
                res = f"{event['orig_res']}→{event['final_res']}"
            child = self.tree.insert(
                fnode, "end", text=PurePosixPath(drop).name,
                values=(
                    "", f"{event['gen_s']:.0f}s", "…", res, "",
                    fmt_size(event["size"]),
                ),
            )
            self._child_ids[drop] = child
            self._update_folder(folder)
            self._update_parent()
        elif kind == "item_done":
            # our-time known now — fill the image's column + folder time
            over = event["over_s"]
            self._theme_over.append(over)
            self._task_over.append(over)
            drop = event["drop_path"]
            child = self._child_ids.get(drop)
            if child is not None:
                self.tree.set(child, "our", f"{over:.0f}s")
            folder = self._folder_of(drop)
            st = self._folder_stats.get(folder)
            if st is not None:
                st["time"] += event["gen_s"] + over
                self._update_folder(folder)
        elif kind == "item_refused":
            self._theme_refused += 1
            self._task_refused += 1
            drop = event.get("drop_path", "")
            fnode = self._ensure_folder(self._folder_of(drop))
            self.tree.insert(
                fnode, "end", text=PurePosixPath(drop).name or "refused",
                values=("", "", "", "REFUSED", "", ""),
            )
            self._update_parent()
        elif kind == "item_retry":
            self.image_var.set(self.image_var.get() + "  (safer retry…)")
        elif kind == "sheet_done":
            self._finalize_theme()
            self.image_var.set("—")
        self._refresh()

    @staticmethod
    def _folder_of(drop_path: str) -> str:
        folder = PurePosixPath(drop_path).parent.as_posix()
        return "(root)" if folder in (".", "") else folder

    def _ensure_parent(self) -> str:
        """The collection's row — created (open) the first time an image
        of it lands, so a running collection shows live."""
        if self._tree_item is None:
            name = f"{self._theme_name}   · running…"
            self._tree_item = self.tree.insert(
                "", "end", text=name, open=True,
                values=self._parent_values(),
            )
        return self._tree_item

    def _ensure_folder(self, folder: str) -> str:
        node = self._folder_nodes.get(folder)
        if node is None:
            parent = self._ensure_parent()
            self._folder_stats[folder] = {"done": 0, "size": 0, "time": 0.0}
            node = self.tree.insert(
                parent, "end", text=folder, open=True,
                values=("0", "", "", "", "", fmt_size(0)),
            )
            self._folder_nodes[folder] = node
        return node

    def _parent_values(self) -> tuple:
        wall = time.monotonic() - self._t_theme
        return (
            f"{self._theme_done}/{self._theme_pending}", "", "", "",
            fmt_duration(wall), fmt_size(self._theme_bytes),
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
                    fmt_duration(st["time"]), fmt_size(st["size"]),
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
            self._theme_over, self._theme_pending, now - self._t_theme,
        )
        task = _scope_stats(
            self._task_done, self._task_refused, self._task_gen,
            self._task_over, self._task_total, now - self._t_task,
        )
        for key, _label in _METRICS:
            self.cells[("theme", key)].set(theme[key])
            self.cells[("task", key)].set(task[key])


# ---------------------------------------------------------------------
# Main window
# ---------------------------------------------------------------------

class PainterGui:
    def __init__(self, root: tk.Tk):
        self.root = root
        root.title("PromptPainter")
        root.minsize(900, 640)
        setup_style(root)

        self._q: queue.Queue = queue.Queue()
        self._stop = threading.Event()
        self._workers: list[threading.Thread] = []
        self._workers_left = 0  # counted down on each __worker_done__
        self._sheets: list[Path] = []
        # (site, source-path, drop-path) -> BooleanVar; missing = ticked
        self._select_vars: dict[tuple[str, str, str], tk.BooleanVar] = {}

        outer = ttk.Frame(root, padding=8)
        outer.pack(fill="both", expand=True)

        self._build_queue(outer)
        self._build_options(outer)
        self._build_toolbar(outer)
        self._build_views(outer)

        self.status_var = tk.StringVar(value="idle")
        ttk.Label(
            outer, textvariable=self.status_var, style="Muted.TLabel"
        ).pack(fill="x", pady=(4, 0))

        root.after(120, self._drain_queue)

    # --- construction --------------------------------------------------

    def _build_queue(self, parent) -> None:
        lf = ttk.Labelframe(
            parent, text="Collections (prompt .md files, one image set each)"
        )
        lf.pack(fill="x", pady=(0, 6))
        self.sheet_list = tk.Listbox(
            lf, height=5, activestyle="none", font=("Consolas", 9)
        )
        self.sheet_list.pack(side="left", fill="x", expand=True)
        col = ttk.Frame(lf)
        col.pack(side="left", padx=(8, 0), anchor="n")
        ttk.Button(col, text="Add…", command=self._add_sheets).pack(fill="x")
        ttk.Button(col, text="Remove", command=self._remove_sheet).pack(
            fill="x", pady=4
        )
        ttk.Button(col, text="Clear", command=self._clear_sheets).pack(
            fill="x"
        )

    def _build_options(self, parent) -> None:
        lf = ttk.Labelframe(parent, text="Output & run options")
        lf.pack(fill="x", pady=(0, 6))

        row = ttk.Frame(lf)
        row.pack(fill="x", pady=2)
        ttk.Label(row, text="Output:", width=8).pack(side="left")
        self.out_var = tk.StringVar(value=str(DEFAULT_OUT_DIR))
        ttk.Entry(row, textvariable=self.out_var).pack(
            side="left", fill="x", expand=True
        )
        ttk.Button(row, text="Browse…", command=self._pick_out).pack(
            side="left", padx=(8, 0)
        )

        row = ttk.Frame(lf)
        row.pack(fill="x", pady=2)
        ttk.Label(row, text="Sites:", width=8).pack(side="left")
        self.site_vars = {
            key: tk.BooleanVar(value=True) for key in sorted(SITES)
        }
        self.background_vars: dict[str, tk.StringVar] = {}
        for key in sorted(SITES):
            ttk.Checkbutton(
                row, text=SITES[key].name, variable=self.site_vars[key]
            ).pack(side="left", padx=(2, 0))
            var = tk.StringVar(value=SITES[key].default_background)
            self.background_vars[key] = var
            ttk.Combobox(
                row, textvariable=var, values=list(BACKGROUND_CHOICES),
                state="readonly", width=11,
            ).pack(side="left", padx=(2, 12))

        row = ttk.Frame(lf)
        row.pack(fill="x", pady=2)
        ttk.Label(row, text="", width=8).pack(side="left")
        self.bgfix_var = tk.BooleanVar(value=True)
        ttk.Checkbutton(
            row, text="Background fix", variable=self.bgfix_var
        ).pack(side="left")
        self.report_var = tk.BooleanVar(value=True)
        ttk.Checkbutton(
            row, text="Report txt", variable=self.report_var
        ).pack(side="left", padx=12)
        self.safer_var = tk.BooleanVar(value=True)
        ttk.Checkbutton(
            row, text="Safer retry on refusal", variable=self.safer_var
        ).pack(side="left", padx=12)

        row = ttk.Frame(lf)
        row.pack(fill="x", pady=2)
        ttk.Label(row, text="Pace:", width=8).pack(side="left")
        ttk.Label(row, text="pause").pack(side="left")
        self.pause_min_var = tk.StringVar(value=f"{TIMING.pause_min_s:.0f}")
        self.pause_max_var = tk.StringVar(value=f"{TIMING.pause_max_s:.0f}")
        ttk.Spinbox(
            row, from_=0, to=600, width=5, textvariable=self.pause_min_var
        ).pack(side="left", padx=(4, 0))
        ttk.Label(row, text="–").pack(side="left")
        ttk.Spinbox(
            row, from_=0, to=600, width=5, textvariable=self.pause_max_var
        ).pack(side="left")
        ttk.Label(row, text="s   action delay").pack(side="left", padx=(2, 0))
        self.act_min_var = tk.StringVar(
            value=f"{TIMING.action_delay_min_s:.1f}"
        )
        self.act_max_var = tk.StringVar(
            value=f"{TIMING.action_delay_max_s:.1f}"
        )
        ttk.Spinbox(
            row, from_=0, to=5, increment=0.1, width=4,
            textvariable=self.act_min_var,
        ).pack(side="left", padx=(4, 0))
        ttk.Label(row, text="–").pack(side="left")
        ttk.Spinbox(
            row, from_=0, to=5, increment=0.1, width=4,
            textvariable=self.act_max_var,
        ).pack(side="left")
        ttk.Label(row, text="s").pack(side="left")

    def _build_toolbar(self, parent) -> None:
        row = ttk.Frame(parent)
        row.pack(fill="x", pady=(0, 6))
        self.btn_chrome = ttk.Button(
            row, text="Open Chrome (login)", command=self._open_chrome
        )
        self.btn_chrome.pack(side="left")
        self.btn_check = ttk.Button(
            row, text="Check", command=self._check_sheets
        )
        self.btn_check.pack(side="left", padx=4)
        self.btn_select = ttk.Button(
            row, text="Select images…", command=self._select_images
        )
        self.btn_select.pack(side="left", padx=4)
        self.btn_start = ttk.Button(row, text="Start", command=self._start)
        self.btn_start.pack(side="left", padx=4)
        self.btn_stop = ttk.Button(
            row, text="Stop", command=self._request_stop, state="disabled"
        )
        self.btn_stop.pack(side="left", padx=4)
        ttk.Button(
            row, text="Instructions", command=self._open_instructions
        ).pack(side="right")
        ttk.Button(
            row, text="BG removal only…", command=self._bg_remove_only
        ).pack(side="right", padx=4)

    def _build_views(self, parent) -> None:
        notebook = ttk.Notebook(parent)
        notebook.pack(fill="both", expand=True)

        dash_tab = ttk.Frame(notebook)
        notebook.add(dash_tab, text="Dashboard")
        self.dash: dict[str, DashPanel] = {}
        for i, key in enumerate(sorted(SITES)):
            panel = DashPanel(dash_tab, SITES[key].name)
            panel.grid(row=0, column=i, sticky="nsew", padx=4, pady=4)
            dash_tab.columnconfigure(i, weight=1)
            self.dash[key] = panel
        dash_tab.rowconfigure(0, weight=1)

        log_tab = ttk.Frame(notebook)
        notebook.add(log_tab, text="Log (detailed)")
        self.log_box = scrolledtext.ScrolledText(
            log_tab, height=16, state="disabled", font=("Consolas", 9)
        )
        self.log_box.pack(fill="both", expand=True)

    def _open_instructions(self) -> None:
        path = Path(__file__).resolve().parent / "instructions.md"
        try:
            text = path.read_text(encoding="utf-8")
        except OSError as exc:
            messagebox.showerror("PromptPainter", f"Cannot read {path}: {exc}")
            return
        InstructionsWindow(self.root, text)

    # --- helpers -------------------------------------------------------

    def _log(self, line: str) -> None:
        stamp = datetime.now().strftime("%H:%M:%S")
        self.log_box.configure(state="normal")
        self.log_box.insert("end", f"[{stamp}] {line}\n")
        self.log_box.see("end")
        self.log_box.configure(state="disabled")

    def _add_sheets(self) -> None:
        paths = filedialog.askopenfilenames(
            title="Prompt sheets", filetypes=[("Markdown", "*.md")]
        )
        for raw in paths:
            path = Path(raw)
            if path not in self._sheets:
                self._sheets.append(path)
                self.sheet_list.insert("end", path.name)

    def _remove_sheet(self) -> None:
        for index in reversed(self.sheet_list.curselection()):
            self.sheet_list.delete(index)
            del self._sheets[index]

    def _clear_sheets(self) -> None:
        self.sheet_list.delete(0, "end")
        self._sheets.clear()

    def _pick_out(self) -> None:
        path = filedialog.askdirectory(title="Output folder")
        if path:
            self.out_var.set(path)

    def _selected_sites(self) -> list[str]:
        return [k for k, v in self.site_vars.items() if v.get()]

    def _out_base(self) -> Path:
        return Path(
            self.out_var.get().strip() or str(DEFAULT_OUT_DIR)
        ).resolve()

    def _progress_done(self, site: str, sheet: Sheet) -> set:
        """Drop paths already generated for one site+theme (per sidecar)."""
        progress_file = (
            self._out_base() / site / (sheet.source.stem + PROGRESS_SUFFIX)
        )
        if progress_file.exists():
            return set(
                json.loads(progress_file.read_text(encoding="utf-8"))["done"]
            )
        return set()

    def _parse_all(self) -> list[Sheet]:
        """Parse every queued sheet; broken ones are reported and
        dropped from the run (the fix belongs in the sheet)."""
        good: list[Sheet] = []
        for path in self._sheets:
            try:
                sheet = parse_sheet(path)
            except (SheetError, OSError) as exc:
                self._log(f"SHEET SKIPPED: {exc}")
                continue
            if sheet.problems:
                for pr in sheet.problems:
                    self._log(
                        f"  PROBLEM {path.name} L{pr.line}: {pr.message}"
                    )
                self._log(
                    f"SHEET SKIPPED (contract problems): {path.name} —"
                    " fix the sheet and rerun"
                )
                continue
            self._log(
                f"OK {path.name}: {sheet.theme} —"
                f" {len(sheet.items)} to generate,"
                f" {len(sheet.skipped)} skipped"
            )
            for it in sheet.items:
                if it.advice:
                    self._log(
                        f"    ADVICE (unticked by default, L{it.line})"
                        f" {it.title} — {it.advice}"
                    )
            for sk in sheet.skipped:
                self._log(
                    f"    NO PROMPT in the sheet (L{sk.line})"
                    f" {sk.title} — {sk.reason}"
                )
            good.append(sheet)
        return good

    def _plan(
        self,
        site: str,
        sheets: list[Sheet],
        selection: dict[str, set[str] | None],
    ) -> tuple[int, int]:
        """Mirror run_sheet's queue rule to pre-count this run's scope:
        (total images to generate, number of themes with work)."""
        total = 0
        themes = 0
        for sheet in sheets:
            done = self._progress_done(site, sheet)
            pending = [it for it in sheet.items if it.drop_path not in done]
            sel = selection.get(str(sheet.source))
            if sel is not None:
                pending = [it for it in pending if it.drop_path in sel]
            else:
                pending = [it for it in pending if not it.advice]
            if pending:
                total += len(pending)
                themes += 1
        return total, themes

    # --- actions -------------------------------------------------------

    def _open_chrome(self) -> None:
        sites = self._selected_sites()
        if not sites:
            messagebox.showerror("PromptPainter", "Tick at least one site.")
            return
        urls = tuple(SITES[k].url for k in sites)
        self.status_var.set("opening Chrome …")

        def work():
            from painter.chrome import ChromeError, ensure_chrome

            try:
                state = ensure_chrome(urls)
            except ChromeError as exc:
                self._q.put(f"CHROME ERROR: {exc}")
                self._q.put(("__status__", "idle"))
                return
            if state == "launched":
                self._q.put(
                    "Chrome opened with the PromptPainter profile — log in"
                    " on each site tab once, then press Start."
                )
            else:
                self._q.put("Chrome already running — ready.")
            self._q.put(("__status__", "idle"))

        threading.Thread(target=work, daemon=True).start()

    def _check_sheets(self) -> None:
        if not self._sheets:
            messagebox.showerror("PromptPainter", "Add sheet .md files first.")
            return
        self._parse_all()

    def _select_var(
        self, site: str, source: str, drop: str, default: bool = True
    ) -> tk.BooleanVar:
        key = (site, source, drop)
        if key not in self._select_vars:
            self._select_vars[key] = tk.BooleanVar(value=default)
        return self._select_vars[key]

    def _select_images(self) -> None:
        if not self._sheets:
            messagebox.showerror("PromptPainter", "Add sheet .md files first.")
            return
        sheets = self._parse_all()
        if not sheets:
            messagebox.showerror(
                "PromptPainter", "No usable sheets in the queue."
            )
            return
        SelectWindow(self, sheets)

    def _bg_remove_only(self) -> None:
        from painter.postprocess import deps_error

        problem = deps_error()
        if problem:
            messagebox.showerror("PromptPainter", problem)
            return
        folder = filedialog.askdirectory(
            title="Folder with images — backgrounds removed IN PLACE"
        )
        if not folder:
            return
        if not messagebox.askyesno(
            "PromptPainter",
            "Remove backgrounds IN PLACE for every image under:\n"
            f"{folder}?\n\n(already-transparent and unclear images are"
            " skipped untouched)",
        ):
            return
        self.status_var.set("BG removal running …")

        def work():
            from painter.bg_remove import iter_images, process_file
            from painter.config import BG_FIX_CROP

            files = list(iter_images(Path(folder)))
            self._q.put(f"BG removal: {len(files)} image(s) under {folder}")
            counts: dict[str, int] = {}
            for i, src in enumerate(files, start=1):
                try:
                    action = process_file(
                        src, src, "auto", BG_FIX_CROP, None, None
                    )
                except Exception as exc:
                    action = "FAILED"
                    self._q.put(f"  BG FAIL {src.name}: {exc}")
                counts[action] = counts.get(action, 0) + 1
                self._q.put(f"  [{i}/{len(files)}] {action:16} {src.name}")
            summary = ", ".join(
                f"{k}={v}" for k, v in sorted(counts.items())
            )
            self._q.put(f"BG removal done: {summary or 'no images'}")
            self._q.put(("__status__", "idle"))

        threading.Thread(target=work, daemon=True).start()

    def _start(self) -> None:
        if not self._sheets:
            messagebox.showerror("PromptPainter", "Add sheet .md files first.")
            return
        sheets = self._parse_all()
        if not sheets:
            messagebox.showerror(
                "PromptPainter", "No usable sheets in the queue."
            )
            return
        sites = self._selected_sites()
        if not sites:
            messagebox.showerror("PromptPainter", "Tick at least one site.")
            return
        out_base = self._out_base()
        for sheet in sheets:
            if sheet.source.resolve().is_relative_to(out_base):
                messagebox.showerror(
                    "PromptPainter",
                    f"{sheet.source.name} lives inside the output folder"
                    " — sources are READ ONLY; pick another output.",
                )
                return
        # the progress sidecar and report are keyed by filename stem, so
        # two queued themes with the same filename would collide
        stems = [s.source.stem for s in sheets]
        dupes = sorted({s for s in stems if stems.count(s) > 1})
        if dupes:
            messagebox.showerror(
                "PromptPainter",
                "Two queued collections share a filename: "
                + ", ".join(dupes)
                + ".\nTheir progress/report files would collide — rename"
                " one before running.",
            )
            return

        post_save = None
        if self.bgfix_var.get():
            from painter.postprocess import deps_error, fix_background

            problem = deps_error()
            if problem:
                messagebox.showerror(
                    "PromptPainter",
                    f"{problem}\n\n(or untick 'Background fix')",
                )
                return
            post_save = fix_background

        try:
            pause_min = float(self.pause_min_var.get())
            pause_max = float(self.pause_max_var.get())
            act_min = float(self.act_min_var.get())
            act_max = float(self.act_max_var.get())
        except ValueError:
            messagebox.showerror(
                "PromptPainter", "Pause/delay must be numbers."
            )
            return
        if pause_min > pause_max or act_min > act_max:
            messagebox.showerror(
                "PromptPainter", "FROM must be <= TO (pause and delay)."
            )
            return
        timing = replace(
            TIMING,
            pause_min_s=pause_min,
            pause_max_s=pause_max,
            action_delay_min_s=act_min,
            action_delay_max_s=act_max,
        )

        from painter.chrome import cdp_alive

        if not cdp_alive():
            messagebox.showerror(
                "PromptPainter",
                "No debuggable Chrome is running — press"
                " 'Open Chrome (login)' first.",
            )
            return

        # the ticked selection, read in the tk thread: per site, per
        # sheet -> the drop paths to run. None means "the owner never
        # opened Select for this theme+site" (so the runner applies the
        # default advice rule). Once Select has been opened, the ticks
        # are authoritative — including ticked advice items — so we pass
        # the explicit set, never collapsing "all ticked" back to None.
        selections: dict[str, dict[str, set[str] | None]] = {}
        for key in sites:
            per_sheet: dict[str, set[str] | None] = {}
            for sheet in sheets:
                src = str(sheet.source)
                touched = any(
                    site == key and source == src
                    for (site, source, _drop) in self._select_vars
                )
                if touched:
                    per_sheet[src] = {
                        drop
                        for (site, source, drop), var
                        in self._select_vars.items()
                        if site == key and source == src and var.get()
                    }
                else:
                    per_sheet[src] = None
            selections[key] = per_sheet

        self._stop.clear()
        self._workers = []
        self._workers_left = len(sites)
        self.btn_start.configure(state="disabled")
        self.btn_stop.configure(state="normal")
        self.status_var.set("running: " + ", ".join(sites))
        for key, panel in self.dash.items():
            if key in sites:
                total, themes = self._plan(key, sheets, selections[key])
                panel.reset(active=True, task_total=total, task_themes=themes)
            else:
                panel.reset(active=False)
        backgrounds = {key: self.background_vars[key].get() for key in sites}
        self._log(
            f"=== START {', '.join(sites)} | {len(sheets)} sheet(s)"
            f" -> {out_base} | backgrounds: {backgrounds}"
            f" | safer_retry={self.safer_var.get()} ==="
        )

        safer = self.safer_var.get()
        for key in sites:
            worker = threading.Thread(
                target=self._drive_site,
                args=(
                    key,
                    list(sheets),
                    out_base / key,
                    timing,
                    post_save,
                    partial(prompt_suffix, key, backgrounds[key]),
                    self.report_var.get(),
                    selections[key],
                    safer,
                ),
                daemon=True,
            )
            self._workers.append(worker)
            worker.start()

    def _drive_site(
        self, key, sheets, out_root, timing, post_save, suffix, report,
        selection, safer,
    ) -> None:
        """One site's whole run — the theme queue in order, one thread."""
        log = lambda msg: self._q.put(f"[{key}] {msg}")
        events = lambda ev: self._q.put(("__event__", key, ev))
        driver = None
        done_sheets = 0
        # the WHOLE body is guarded so __worker_done__ is ALWAYS posted
        # (even if the imports or driver construction fail) — otherwise
        # the Start button would stay disabled forever
        try:
            from painter.driver import DriverError, SiteDriver, TerminalState
            from painter.runner import run_sheet

            driver = SiteDriver(SITES[key], timing, CDP_URL)
            t_site = time.monotonic()
            title = driver.attach()
            log(f"attached to {title!r} — SUPERVISED, watch the window")
            for n, sheet in enumerate(sheets, start=1):
                if self._stop.is_set():
                    log("stopped on request — remaining collections not run")
                    break
                log(
                    f"--- collection {n}/{len(sheets)}:"
                    f" {sheet.source.name} ---"
                )
                try:
                    generated = run_sheet(
                        sheet, driver, out_root, timing,
                        log=log,
                        should_stop=self._stop.is_set,
                        post_save=post_save,
                        prompt_suffix=suffix,
                        report=report,
                        only=selection.get(str(sheet.source)),
                        on_event=events,
                        safer_retry=safer,
                    )
                    done_sheets += 1
                    log(f"collection done: {generated} image(s) into {out_root}")
                except TerminalState as exc:
                    log(f"TERMINAL STATE (quota/rate limit): {exc}")
                    log(
                        "site stopped — finished work is saved; start"
                        " again later to resume the remaining collections"
                    )
                    break
                except DriverError as exc:
                    log(f"DRIVER ERROR: {exc}")
                    log(
                        "site stopped — progress saved; fix the cause"
                        " and start again to resume"
                    )
                    break
            log(
                f"finished {done_sheets}/{len(sheets)} collection(s) in"
                f" {(time.monotonic() - t_site) / 60:.1f} min"
            )
        except Exception as exc:  # surfaced, never swallowed
            # attach()/construction failures land here (DriverError);
            # so would a missing-playwright ImportError
            kind = type(exc).__name__
            if kind in (
                "DriverError", "TerminalState", "SelectorRot",
                "GenerationTimeout",
            ):
                log(f"DRIVER ERROR: {exc}")
            else:
                log(f"UNEXPECTED ERROR: {kind}: {exc}")
        finally:
            if driver is not None:
                driver.close()
            self._q.put(("__worker_done__", key))

    def _request_stop(self) -> None:
        self._stop.set()
        self.status_var.set("stopping after the current item …")

    # --- queue pump ----------------------------------------------------

    def _drain_queue(self) -> None:
        try:
            while True:
                msg = self._q.get_nowait()
                if isinstance(msg, tuple):
                    if msg[0] == "__status__":
                        self.status_var.set(msg[1])
                    elif msg[0] == "__event__":
                        self.dash[msg[1]].handle(msg[2])
                    elif msg[0] == "__worker_done__":
                        self._log(f"[{msg[1]}] worker finished")
                        # count down rather than poll is_alive(): the
                        # worker posts this from its finally block while
                        # its thread is still technically alive
                        self._workers_left -= 1
                        if self._workers_left <= 0:
                            self.btn_start.configure(state="normal")
                            self.btn_stop.configure(state="disabled")
                            self.status_var.set("idle")
                else:
                    self._log(str(msg))
        except queue.Empty:
            pass
        self.root.after(120, self._drain_queue)


# ---------------------------------------------------------------------
# Select-images window
# ---------------------------------------------------------------------

class SelectWindow(tk.Toplevel):
    """Tick which images each site generates — a column per site.

    One collapsible section per theme. Already-done items (per the
    site's progress under the current output folder) show disabled;
    sheet-advised items show unticked with the reason.
    """

    def __init__(self, gui: PainterGui, sheets: list[Sheet]):
        super().__init__(gui.root)
        self.title("Select images per site")
        self.minsize(720, 520)
        self._gui = gui
        site_keys = sorted(SITES)

        done = {
            key: {
                str(sheet.source): gui._progress_done(key, sheet)
                for sheet in sheets
            }
            for key in site_keys
        }

        bar = ttk.Frame(self, padding=6)
        bar.pack(fill="x")
        ttk.Label(
            bar,
            text="Tick = generate.  Already-done disabled;"
            " ⚠ advice unticked by default.",
            style="Muted.TLabel",
        ).pack(side="left")
        ttk.Button(bar, text="Expand all", command=self._expand_all).pack(
            side="right"
        )
        ttk.Button(
            bar, text="Collapse all", command=self._collapse_all
        ).pack(side="right", padx=4)
        ttk.Button(bar, text="Close", command=self.destroy).pack(
            side="right", padx=4
        )

        scroll = ScrollFrame(self, horizontal=True)
        scroll.pack(fill="both", expand=True)
        body = scroll.body

        header = ttk.Frame(body, padding=(2, 2))
        header.pack(fill="x")
        for c, key in enumerate(site_keys):
            ttk.Label(
                header, text=SITES[key].name, style="Head.TLabel", width=10,
                anchor="center",
            ).grid(row=0, column=c, padx=2)
        ttk.Label(header, text="Image", style="Head.TLabel").grid(
            row=0, column=len(site_keys), sticky="w", padx=8
        )

        # each entry: (state dict, toggle callable) for expand/collapse all
        self._sections: list[tuple[dict, object]] = []
        for sheet in sheets:
            self._add_theme(body, sheet, site_keys, done)

    def _add_theme(self, body, sheet: Sheet, site_keys, done) -> None:
        src = str(sheet.source)
        section = ttk.Frame(body)
        section.pack(fill="x", pady=(8, 0))

        head = ttk.Frame(section)
        head.pack(fill="x")
        detail = ttk.Frame(section)
        detail.pack(fill="x", padx=(14, 0))

        state = {"open": True}
        label = f"{sheet.source.name} — {sheet.theme}"
        btn = ttk.Button(head, style="Expander.TButton")

        def render() -> None:
            btn.configure(text=("▼  " if state["open"] else "▶  ") + label)

        def toggle() -> None:
            state["open"] = not state["open"]
            if state["open"]:
                detail.pack(fill="x", padx=(14, 0))
            else:
                detail.forget()
            render()

        btn.configure(command=toggle)
        # all/none buttons first (right), then the toggle fills the rest
        for key in reversed(site_keys):
            ttk.Button(
                head, text=f"{SITES[key].name}: all/none", width=16,
                command=partial(self._toggle_sheet, key, sheet),
            ).pack(side="right", padx=2)
        btn.pack(side="left", fill="x", expand=True)
        render()
        self._sections.append((state, toggle))

        for r, item in enumerate(sheet.items):
            done_sites = [
                k for k in site_keys if item.drop_path in done[k][src]
            ]
            for c, key in enumerate(site_keys):
                var = self._gui._select_var(
                    key, src, item.drop_path, default=item.advice is None
                )
                is_done = item.drop_path in done[key][src]
                if is_done:
                    var.set(False)
                cb = ttk.Checkbutton(detail, variable=var)
                if is_done:
                    cb.state(["disabled"])
                cb.grid(row=r, column=c, padx=(20 if c == 0 else 6, 6))
            text = item.drop_path
            if done_sites:
                text += "   ✔ done: " + ", ".join(
                    SITES[k].name for k in done_sites
                )
            if item.advice:
                text += f"   ⚠ {item.advice[:70]}"
            if len(done_sites) == len(site_keys):
                color = C_DONE
            elif item.advice and "supersed" in item.advice.lower():
                color = C_SUPERSEDED
            elif item.advice:
                color = C_ADVICE
            elif done_sites:
                color = C_DONE_SOFT
            else:
                color = ""
            opt = {"foreground": color} if color else {}
            ttk.Label(detail, text=text, **opt).grid(
                row=r, column=len(site_keys), sticky="w", padx=8
            )

    def _toggle_sheet(self, site: str, sheet: Sheet) -> None:
        src = str(sheet.source)
        variables = [
            self._gui._select_var(site, src, item.drop_path)
            for item in sheet.items
        ]
        target = not all(var.get() for var in variables)
        for var in variables:
            var.set(target)

    def _expand_all(self) -> None:
        for state, toggle in self._sections:
            if not state["open"]:
                toggle()

    def _collapse_all(self) -> None:
        for state, toggle in self._sections:
            if state["open"]:
                toggle()


class InstructionsWindow(tk.Toplevel):
    """A readable, selectable in-app viewer for instructions.md — for
    people who do not want a code editor. Light Markdown formatting
    (headings, code, bullets, bold) plus a one-click 'Copy for AI'."""

    def __init__(self, master, raw_markdown: str):
        super().__init__(master)
        self.title("How to write a prompt sheet")
        self.minsize(720, 560)
        self._raw = raw_markdown

        bar = ttk.Frame(self, padding=6)
        bar.pack(fill="x")
        ttk.Label(
            bar,
            text="Give this to whoever (a person or an AI) writes the"
            " next prompt file.",
            style="Muted.TLabel",
        ).pack(side="left")
        ttk.Button(
            bar, text="Copy all (for AI)", command=self._copy_all
        ).pack(side="right")
        ttk.Button(bar, text="Close", command=self.destroy).pack(
            side="right", padx=4
        )

        wrap = ttk.Frame(self)
        wrap.pack(fill="both", expand=True, padx=6, pady=(0, 6))
        self.txt = tk.Text(
            wrap, wrap="word", font=("Segoe UI", 10), padx=12, pady=10,
            spacing1=2, spacing3=2, background="white", relief="flat",
            cursor="arrow",
        )
        vsb = ttk.Scrollbar(wrap, orient="vertical", command=self.txt.yview)
        self.txt.configure(yscrollcommand=vsb.set)
        vsb.pack(side="right", fill="y")
        self.txt.pack(side="left", fill="both", expand=True)

        self._configure_tags()
        self._render(raw_markdown)
        # read-only, but fully selectable and Ctrl+C / Ctrl+A copyable
        self.txt.bind("<Key>", self._readonly_keys)

    def _configure_tags(self) -> None:
        self.txt.tag_configure("h1", font=("Segoe UI", 15, "bold"),
                               spacing1=10, spacing3=6)
        self.txt.tag_configure("h2", font=("Segoe UI", 12, "bold"),
                               spacing1=8, spacing3=4)
        self.txt.tag_configure("h3", font=("Segoe UI", 11, "bold"),
                               spacing1=6, spacing3=3)
        self.txt.tag_configure(
            "code", font=("Consolas", 9), background="#f2f2f2",
            lmargin1=16, lmargin2=16,
        )
        self.txt.tag_configure("bold", font=("Segoe UI", 10, "bold"))
        self.txt.tag_configure("bullet", lmargin1=16, lmargin2=30)

    def _render(self, md: str) -> None:
        self.txt.configure(state="normal")
        in_code = False
        for line in md.split("\n"):
            if line.startswith("```"):
                in_code = not in_code
                continue
            if in_code:
                self.txt.insert("end", line + "\n", "code")
                continue
            if line.startswith("### "):
                self.txt.insert("end", line[4:] + "\n", "h3")
            elif line.startswith("## "):
                self.txt.insert("end", line[3:] + "\n", "h2")
            elif line.startswith("# "):
                self.txt.insert("end", line[2:] + "\n", "h1")
            elif line.lstrip().startswith(("- ", "* ")):
                self._insert_inline("• " + line.lstrip()[2:] + "\n", "bullet")
            else:
                self._insert_inline(line + "\n", None)
        self.txt.configure(state="disabled")

    def _insert_inline(self, text: str, base_tag) -> None:
        """Insert a line, turning **bold** spans into the bold tag."""
        parts = text.split("**")
        for i, part in enumerate(parts):
            tags = [t for t in (base_tag,) if t]
            if i % 2 == 1:  # inside a **...** pair
                tags.append("bold")
            self.txt.insert("end", part, tuple(tags))

    def _readonly_keys(self, event):
        # allow copy/select-all and navigation; block edits
        if event.state & 0x4 and event.keysym.lower() in ("c", "a"):
            return
        if event.keysym in (
            "Left", "Right", "Up", "Down", "Home", "End", "Prior", "Next",
        ):
            return
        return "break"

    def _copy_all(self) -> None:
        self.clipboard_clear()
        self.clipboard_append(self._raw)
        messagebox.showinfo(
            "PromptPainter",
            "The full instructions were copied — paste them to your AI"
            " (or into a document).",
            parent=self,
        )


def main() -> None:
    root = tk.Tk()
    PainterGui(root)
    root.mainloop()


if __name__ == "__main__":
    main()
