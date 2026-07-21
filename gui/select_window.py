"""``SelectWindow`` pulled out of ``gui/__init__.py`` (root Rule #20
god-file refactor): the per-site tick-list Toplevel over the queued
Collections (3-level tree: collection -> folder -> image).

``DOC_HEIGHT_FRAC``/``DOC_MAX_FRAC`` (this window's tall-open and
never-bigger-than-screen clamps) live in ``gui.viewers`` — the module
that names and owns the ``DOC_*`` sizing family — and are imported
here directly; no circularity, ``gui.viewers`` has no dependency back
on this module.
"""

from __future__ import annotations

from functools import partial
from pathlib import PurePosixPath
from tkinter import ttk
import tkinter as tk

import ttkbootstrap as tb

from painter.config import RESIZE_SETTLE_MS, SITES
from painter.sheet_parser import Sheet
from .scroll import ScrollFrame
from .theme import THEME_TOPLEVELS, skin_toplevel
from .viewers import DOC_HEIGHT_FRAC, DOC_MAX_FRAC
from .widgets import folder_of, rounded_button, status, tk_font

# --- Select-images window geometry (Rule #4) --------------------------
# The three-level tree (collection -> folder -> image) is a frame-tree
# of plain ttk widgets: names WRAP via ttk.Label(wraplength=), the two
# per-site count/checkbox columns are FIXED width so they stay aligned
# no matter how deep the row is or how far its name wraps.
SELECT_MIN_W = 860          # open + minimum width (hint + bar buttons fit)
SELECT_OPEN_H = 520         # minimum height (the open height is screen-tall)
SELECT_INDENT_PX = 22       # left indent added per tree level (folder, image)
SELECT_TRI_PX = 22          # width reserved for a row's ▶/▼ triangle glyph
SELECT_COUNT_COL_PX = 96    # ONE site count/checkbox column (fits 'NNN/NNN'
#                             at the FONT_MAX zoom without clipping)
SELECT_SCROLLBAR_PX = 18    # v-scrollbar gutter — header cells sit over body
SELECT_WRAP_RESERVE_PX = 300  # indent+triangle+2*count reserve; canvas width
#                               minus this is the label wraplength
SELECT_WRAP_MIN_PX = 140    # never wrap tighter than this
SELECT_ADVICE_TRUNC = 70    # advice text shown on a leaf row, truncated
SELECT_ROW_PADY = 1         # vertical padding per tree row
SELECT_EXPAND_CHUNK = 8     # leaf rows built per Expand-all tick — bounds the
#                             main-thread block (measured median ≈ 120 ms, p90
#                             ≈ 200 ms per tick over the owner's real queue) so
#                             Expand-all fills progressively, never a freeze
SELECT_EXPAND_TICK_MS = 1   # gap between Expand-all chunks — yields to the event
#                             loop so the tree fills in progressively, non-blocked
SELECT_FIT_PAD_PX = 24      # slack added to the widest measured name so a title
#                             that FITS never wraps by a hair (frame borders eat
#                             a few px of the settled canvas width)


class SelectWindow(tk.Toplevel):
    """Tick which images each site generates — a 3-level tree.

    Level 1 is the COLLECTION (the sheet file + theme), level 2 the
    FOLDERS inside it (the drop paths' parent dirs — a sheet may have
    several), level 3 the image files, each carrying one checkbox per
    site. Levels 1 and 2 show a live ``selected/total`` count per site;
    the header shows the grand ``selected/total`` per site over EVERY
    loaded collection.

    Performance model (the owner's "even a big collapsible list must
    not lag" complaint): the body is plain ttk only — NO customtkinter
    inside the scroll canvas (each CTkButton is a drawn canvas that
    re-renders on every configure). L1/L2 nodes are always
    materialised (cheap — a few dozen); L3 leaf rows are BUILT on a
    folder's open and DESTROYED on its close, so the live-widget count
    tracks only what is actually open. ``Expand all`` would otherwise
    materialise EVERY leaf in one synchronous geometry pass (~280 rows
    ≈ 3 s frozen); instead it builds folder-atomic CHUNKS across
    ``after()`` ticks (``SELECT_EXPAND_CHUNK`` leaves per tick, ≈ 120 ms
    median block), with a live progress cue (root Rule #10) — the tree
    fills in progressively and the main thread is never blocked (the
    scrollregion recompute is suspended for the run and scanned once at
    the end, keeping per-tick cost flat as the queue grows). Counts
    live-update through ONE coalesced ``after_idle`` recount driven by a
    dirty flag (a var trace only raises the flag), and ``ScrollFrame``
    coalesces its scrollregion recompute — so one settled user action
    costs one geometry pass, never one per gridded child. Long names WRAP via
    ``ttk.Label(wraplength=)``; the two per-site columns are
    fixed-width so they stay aligned however deep a row is or however
    far its name wraps.
    """

    def __init__(self, gui: PainterGui, sheets: list[Sheet]):
        super().__init__(gui.root)
        self.title("Select images per site")
        self.minsize(SELECT_MIN_W, SELECT_OPEN_H)
        skin_toplevel(self)  # bg registered so a flip re-tints the window
        THEME_TOPLEVELS.append(self)  # flip coherently with the main window
        self._gui = gui
        self._site_keys = sorted(SITES)

        done = {
            key: {
                str(sheet.source): gui._done_on_disk(key, sheet)
                for sheet in sheets
            }
            for key in self._site_keys
        }

        # --- the count model: build the data (vars + scopes) FIRST,
        # before any widget, so counts are pure var-math and correct
        # even for collapsed / never-built subtrees.
        self._all_leaves: list[dict] = []
        self._collections = [
            self._build_collection_data(sheet, done) for sheet in sheets
        ]

        # ONE trace per leaf var -> raise the dirty flag; a single
        # coalesced recount services an all/none over dozens of vars.
        self._dirty = False
        self._recount_job = None
        self._wrap_job = None
        # Expand-all runs as folder-atomic chunks across after() ticks
        self._expand_job = None
        self._expand_queue: list[tuple[dict, dict]] = []
        self._expand_leaves_total = 0
        self._traces: list[tuple[tk.BooleanVar, str]] = []
        for leaf in self._all_leaves:
            for key in self._site_keys:
                var = leaf["sites"][key]["var"]
                token = var.trace_add("write", self._mark_dirty)
                self._traces.append((var, token))

        # --- the top bar (CTk allowed here, OUTSIDE the scroll body)
        bar = ttk.Frame(self, padding=6)
        bar.pack(fill="x")
        ttk.Label(
            bar,
            text="Tick = generate.  Done = green (re-tick to redo)."
            "  ⚠ advice off.  Click a count = all/none.",
            style="Muted.TLabel",
        ).pack(side="left")
        rounded_button(
            bar, "Expand all", command=self._expand_all,
            kind="secondary-outline",
        ).pack(side="right")
        rounded_button(
            bar, "Collapse all", command=self._collapse_all,
            kind="secondary-outline",
        ).pack(side="right", padx=4)
        rounded_button(
            bar, "Close", command=self.destroy,
        ).pack(side="right", padx=4)

        # --- the colour legend (own row under the hint bar so it never
        # crowds the Close/Collapse/Expand buttons off-screen). Each swatch
        # label is painted in its OWN status colour, pulled LIVE from the
        # active theme's palette so a Day/Night flip recolours it too.
        legend = ttk.Frame(self, padding=(8, 0, 8, 2))
        legend.pack(fill="x")
        ttk.Label(legend, text="Legend:", style="Muted.TLabel").pack(
            side="left"
        )
        self._legend_labels: list[tuple[str, ttk.Label]] = []
        for role, text in (
            ("done", "BOTH DONE"),
            ("done_soft", "ONE SITE DONE"),
            ("superseded", "SUPERSEDED"),
            ("advice", "ADVICE"),
        ):
            lbl = ttk.Label(
                legend, text=text, style="Value.TLabel", foreground=status(role)
            )
            lbl.pack(side="left", padx=(14, 0))
            self._legend_labels.append((role, lbl))

        # --- the non-scrolling header: one accent cell per site with
        # the grand selected/total, right-aligned over the body columns
        # (a gutter reserves the body's vertical scrollbar width).
        header = ttk.Frame(self, padding=(8, 4))
        header.pack(fill="x")
        header.columnconfigure(0, weight=1)
        # Expand-all progress cue (root Rule #10) — left of the site-count
        # columns, empty except mid-build; accent + bold so it is unmissable
        self._progress_lbl = ttk.Label(
            header, text="", style="Value.TLabel",
            foreground=tb.Style().colors.info,
        )
        self._progress_lbl.grid(row=0, column=0, sticky="w")
        self._header_labels: dict[str, ttk.Label] = {}
        for i, key in enumerate(self._site_keys):
            lbl = ttk.Label(
                header, style="Head.TLabel", anchor="e", cursor="hand2"
            )
            lbl.grid(row=0, column=1 + i, sticky="e", padx=(16, 0))
            lbl.bind(
                "<Button-1>",
                lambda _e, s=key: self._toggle_scope(self._all_leaves, s),
            )
            self._header_labels[key] = lbl
        ttk.Frame(header, width=SELECT_SCROLLBAR_PX).grid(
            row=0, column=1 + len(self._site_keys)
        )

        # --- the scrolling body (vertical only: names wrap, they never
        # force horizontal growth)
        self._scroll = ScrollFrame(self, horizontal=False)
        self._scroll.pack(fill="both", expand=True)
        self._canvas = self._scroll.canvas
        # FIT CONTENT: size the window to the widest collection title so it
        # stays on ONE line (computed BEFORE the tree so labels are born at
        # the right wraplength, no premature 2-3 line wrapping).
        self._open_width = self._fit_content_width()
        self._canvas_width = self._open_width - SELECT_SCROLLBAR_PX
        self._wrap = self._wraplength_for(self._canvas_width)
        self._canvas.bind("<Configure>", self._on_canvas_configure, add="+")

        # --- the tree: L1 + L2 always materialised, L3 lazy
        self._static_labels: list[ttk.Label] = []  # L1/L2 names (wrap)
        self._count_nodes: list[dict] = []  # L1 + L2 nodes for _recount
        self._collection_nodes: list[dict] = []
        for coll in self._collections:
            self._build_collection_widgets(self._scroll.body, coll)

        # first paint of the counts + the open geometry (FIT-CONTENT width,
        # screen-tall height so the whole queue is visible at once)
        self._dirty = True
        self._recount()
        self.bind("<Destroy>", self._on_destroy)
        height = min(
            max(int(self.winfo_screenheight() * DOC_HEIGHT_FRAC), SELECT_OPEN_H),
            int(self.winfo_screenheight() * DOC_MAX_FRAC),
        )
        self.geometry(f"{self._open_width}x{height}")

    # --- data model (no widgets) --------------------------------------

    def _build_collection_data(self, sheet: Sheet, done: dict) -> dict:
        """One collection's leaf records + its folders (first-seen
        order). Materialises the shared BooleanVars — run-safe: the
        default (advice-free, not-yet-on-disk) set equals the runner's
        own 'never opened Select' rule (file-existence resume)."""
        src = str(sheet.source)
        folders: dict[str, dict] = {}
        leaves: list[dict] = []
        for item in sheet.items:
            drop = item.drop_path
            done_sites = [k for k in self._site_keys if drop in done[k][src]]
            leaf = {
                "name": PurePosixPath(drop).name,
                "advice": item.advice,
                # n_done is retained so apply_theme can RECOMPUTE the
                # status colour for the new theme (the colours differ
                # per theme for contrast on the light background)
                "n_done": len(done_sites),
                "color": self._leaf_color(item.advice, len(done_sites)),
                "sites": {},
            }
            for key in self._site_keys:
                var = self._gui._select_var(
                    key, src, drop, default=item.advice is None
                )
                is_done = drop in done[key][src]
                if is_done:
                    # done -> unticked by DEFAULT, but re-tickable so a
                    # bad image can be regenerated (owner 2026-07-19)
                    var.set(False)
                leaf["sites"][key] = {"var": var, "done": is_done}
            leaves.append(leaf)
            self._all_leaves.append(leaf)
            fname = folder_of(drop)
            fnode = folders.get(fname)
            if fnode is None:
                fnode = {"folder": fname, "leaves": []}
                folders[fname] = fnode
            fnode["leaves"].append(leaf)
        return {
            "label": f"{sheet.source.name} — {sheet.theme}",
            "leaves": leaves,
            "folders": list(folders.values()),
        }

    def _leaf_color(self, advice: str | None, n_done: int) -> str:
        # reads status() live, so a flip recolours the leaves through
        # this same function
        if n_done == len(self._site_keys):
            return status("done")
        if advice and "supersed" in advice.lower():
            return status("superseded")
        if advice:
            return status("advice")
        if n_done:
            return status("done_soft")
        return ""

    def apply_theme(self) -> None:
        """Re-colour this window's PER-WIDGET foregrounds for the active
        theme (they do not follow ttk styles): the built leaf labels and
        the Expand-all progress cue. The toplevel bg + scroll canvas ride
        the global recolour_tk_registry; every ttk widget rides the style
        re-run."""
        self._progress_lbl.configure(foreground=tb.Style().colors.info)
        for role, lbl in self._legend_labels:
            lbl.configure(foreground=status(role))
        default_fg = tb.Style().colors.fg
        for cnode in self._collection_nodes:
            for fnode in cnode["folders"]:
                if not fnode["built"]:
                    continue
                for leaf, lbl in zip(fnode["leaves"], fnode["leaf_labels"]):
                    color = self._leaf_color(leaf["advice"], leaf["n_done"])
                    leaf["color"] = color
                    lbl.configure(foreground=color or default_fg)

    # --- widgets -------------------------------------------------------

    def _new_row(self, parent, level: int) -> ttk.Frame:
        """A tree row: [indent][triangle][wrapped name .....][site0][site1].
        The two right columns are fixed-width so they align across every
        level; the name column takes all the slack."""
        row = ttk.Frame(parent)
        row.pack(fill="x", pady=SELECT_ROW_PADY)
        row.columnconfigure(0, minsize=level * SELECT_INDENT_PX)
        row.columnconfigure(1, minsize=SELECT_TRI_PX)
        row.columnconfigure(2, weight=1)
        row.columnconfigure(3, minsize=SELECT_COUNT_COL_PX)
        row.columnconfigure(4, minsize=SELECT_COUNT_COL_PX)
        return row

    def _count_cell(self, row, col: int, scope: list, key: str) -> ttk.Label:
        lbl = ttk.Label(row, text="0/0", anchor="center", cursor="hand2")
        lbl.grid(row=0, column=col, sticky="n")
        lbl.bind(
            "<Button-1>", lambda _e: self._toggle_scope(scope, key)
        )
        return lbl

    def _build_collection_widgets(self, body, coll: dict) -> None:
        section = ttk.Frame(body)
        section.pack(fill="x", pady=(6, 0))
        row = self._new_row(section, level=0)

        node = {"open": False, "children": ttk.Frame(section), "folders": []}
        tri = ttk.Label(row, text="▶ ", cursor="hand2")
        tri.grid(row=0, column=1, sticky="nw")
        node["triangle"] = tri
        name = ttk.Label(
            row, text=coll["label"], wraplength=self._wrap,
            justify="left", anchor="w", cursor="hand2",
        )
        name.grid(row=0, column=2, sticky="nw")
        self._static_labels.append(name)
        count = {}
        for i, key in enumerate(self._site_keys):
            count[key] = self._count_cell(row, 3 + i, coll["leaves"], key)
        self._count_nodes.append({"leaves": coll["leaves"], "count": count})

        toggle = partial(self._toggle_collection, node)
        for w in (tri, name):
            w.bind("<Button-1>", lambda _e: toggle())

        for folder in coll["folders"]:
            self._build_folder_widgets(node["children"], node, folder)

        self._collection_nodes.append(node)

    def _build_folder_widgets(self, parent, cnode: dict, folder: dict) -> None:
        section = ttk.Frame(parent)
        section.pack(fill="x")
        row = self._new_row(section, level=1)

        fnode = {
            "open": False, "built": False,
            "children": ttk.Frame(section), "leaves": folder["leaves"],
            "leaf_labels": [],
        }
        tri = ttk.Label(row, text="▶ ", cursor="hand2")
        tri.grid(row=0, column=1, sticky="nw")
        fnode["triangle"] = tri
        name = ttk.Label(
            row, text=folder["folder"], wraplength=self._wrap,
            justify="left", anchor="w", cursor="hand2",
        )
        name.grid(row=0, column=2, sticky="nw")
        self._static_labels.append(name)
        count = {}
        for i, key in enumerate(self._site_keys):
            count[key] = self._count_cell(row, 3 + i, folder["leaves"], key)
        self._count_nodes.append({"leaves": folder["leaves"], "count": count})

        toggle = partial(self._toggle_folder, fnode)
        for w in (tri, name):
            w.bind("<Button-1>", lambda _e: toggle())
        cnode["folders"].append(fnode)

    def _build_leaves(self, fnode: dict) -> None:
        """L3 rows — built on the folder's open (destroyed on close)."""
        for leaf in fnode["leaves"]:
            row = self._new_row(fnode["children"], level=2)
            for i, key in enumerate(self._site_keys):
                info = leaf["sites"][key]
                # done items stay ENABLED and re-tickable (owner
                # 2026-07-19) — coloured green/olive, unticked by default,
                # but the owner can tick one to REGENERATE a bad image
                cb = ttk.Checkbutton(row, variable=info["var"])
                cb.grid(row=0, column=3 + i, sticky="n")
            text = leaf["name"]
            if leaf["advice"]:
                text += f"   ⚠ {leaf['advice'][:SELECT_ADVICE_TRUNC]}"
            opt = {"foreground": leaf["color"]} if leaf["color"] else {}
            lbl = ttk.Label(
                row, text=text, wraplength=self._wrap, justify="left",
                anchor="w", **opt,
            )
            lbl.grid(row=0, column=2, sticky="nw")
            fnode["leaf_labels"].append(lbl)

    # --- open / close (low-level: NO expand-cancel — the chunked
    # Expand-all drives these directly and must not cancel itself) -----

    def _set_collection_open(self, node: dict, want_open: bool) -> None:
        if node["open"] == want_open:
            return
        node["open"] = want_open
        node["triangle"].configure(text="▼ " if want_open else "▶ ")
        if want_open:
            node["children"].pack(fill="x")
        else:
            node["children"].forget()

    def _open_folder_now(self, fnode: dict) -> None:
        """Build (atomically) + reveal one folder's leaf rows."""
        if not fnode["built"]:
            self._build_leaves(fnode)
            fnode["built"] = True
        fnode["open"] = True
        fnode["triangle"].configure(text="▼ ")
        fnode["children"].pack(fill="x")

    def _close_folder_now(self, fnode: dict) -> None:
        # DESTROY the leaf rows (virtualization): the live-widget count
        # tracks only currently-open folders
        for w in fnode["children"].winfo_children():
            w.destroy()
        fnode["leaf_labels"].clear()
        fnode["built"] = False
        fnode["open"] = False
        fnode["triangle"].configure(text="▶ ")
        fnode["children"].forget()

    # --- click handlers (cancel any in-flight Expand-all first) -------

    def _toggle_collection(self, node: dict) -> None:
        self._cancel_expand()
        self._set_collection_open(node, not node["open"])

    def _toggle_folder(self, fnode: dict) -> None:
        self._cancel_expand()
        if fnode["open"]:
            self._close_folder_now(fnode)
        else:
            self._open_folder_now(fnode)

    # --- Expand / Collapse all ----------------------------------------

    def _expand_all(self) -> None:
        """Open every node — but build the L3 leaf rows in folder-atomic
        chunks across ``after()`` ticks, never in one synchronous pass
        (that froze the main thread ~3 s at the owner's real queue). Each
        tick builds up to ``SELECT_EXPAND_CHUNK`` leaves (≈ one folder),
        yields to the event loop, and updates the progress cue."""
        self._cancel_expand()
        self._expand_queue = [
            (cnode, fnode)
            for cnode in self._collection_nodes
            for fnode in cnode["folders"]
            if not fnode["built"]
        ]
        self._expand_leaves_total = sum(
            len(fnode["leaves"]) for _c, fnode in self._expand_queue
        )
        if not self._expand_queue:
            # nothing to build — just reveal any collapsed collections
            for cnode in self._collection_nodes:
                self._set_collection_open(cnode, True)
            return
        # ONE scrollregion scan at the end, not one (growing) per tick
        self._scroll.suspend_scrollregion()
        self._expand_step()

    def _expand_step(self) -> None:
        """One chunk: build whole folders until the per-tick leaf budget
        is reached (always at least one, so progress is guaranteed), then
        reschedule. The collection is opened just-in-time before its first
        folder builds."""
        self._expand_job = None
        built = 0
        while self._expand_queue:
            cnode, fnode = self._expand_queue[0]
            n = len(fnode["leaves"])
            if built and built + n > SELECT_EXPAND_CHUNK:
                break  # keep this folder whole — defer to the next tick
            self._expand_queue.pop(0)
            self._set_collection_open(cnode, True)  # idempotent, once/coll
            self._open_folder_now(fnode)
            built += n
        self._update_expand_progress()
        if self._expand_queue:
            self._expand_job = self.after(
                SELECT_EXPAND_TICK_MS, self._expand_step
            )
        else:
            # final sweep: open collections that had no unbuilt folders
            for cnode in self._collection_nodes:
                self._set_collection_open(cnode, True)
            self._scroll.resume_scrollregion()  # the single settling scan
            self._hide_expand_progress()

    def _cancel_expand(self) -> None:
        """Abort an in-flight Expand-all cleanly. Folders are atomic, so
        the tree is always in a consistent state to stop at: whatever was
        built stays open+built, the rest stays closed+unbuilt."""
        if self._expand_job is not None:
            self.after_cancel(self._expand_job)
            self._expand_job = None
        self._expand_queue = []
        self._scroll.resume_scrollregion()  # scan whatever got built
        self._hide_expand_progress()

    def _update_expand_progress(self) -> None:
        remaining = sum(len(fnode["leaves"]) for _c, fnode in self._expand_queue)
        done = self._expand_leaves_total - remaining
        pct = round(done / self._expand_leaves_total * 100)
        self._progress_lbl.configure(
            text=f"Expanding… {done}/{self._expand_leaves_total} ({pct}%)"
        )

    def _hide_expand_progress(self) -> None:
        self._progress_lbl.configure(text="")

    def _collapse_all(self) -> None:
        self._cancel_expand()
        for cnode in self._collection_nodes:
            for fnode in cnode["folders"]:
                if fnode["open"]:
                    self._close_folder_now(fnode)
            self._set_collection_open(cnode, False)

    # --- selection + counts -------------------------------------------

    def _toggle_scope(self, leaves: list, site: str) -> None:
        """All/none over one scope+site: flip every ENABLED (non-done)
        leaf var. The traces coalesce into a single recount."""
        enabled = [
            leaf["sites"][site]["var"]
            for leaf in leaves
            if not leaf["sites"][site]["done"]
        ]
        if not enabled:
            return
        target = not all(v.get() for v in enabled)
        for v in enabled:
            v.set(target)

    def _mark_dirty(self, *_args) -> None:
        self._dirty = True
        if self._recount_job is None:
            self._recount_job = self.after_idle(self._recount)

    def _recount(self) -> None:
        """ONE coalesced pass: pure var-math over the cached scope
        lists. L1/L2/header count labels always exist, so there is never
        a write to a destroyed widget even while folders are collapsed."""
        self._recount_job = None
        if not self._dirty:
            return
        self._dirty = False
        total = len(self._all_leaves)
        for key in self._site_keys:
            sel = sum(
                leaf["sites"][key]["var"].get() for leaf in self._all_leaves
            )
            self._header_labels[key].configure(
                text=f"{SITES[key].name}  {sel}/{total}"
            )
        for cnode in self._count_nodes:
            leaves = cnode["leaves"]
            tot = len(leaves)
            for key in self._site_keys:
                sel = sum(leaf["sites"][key]["var"].get() for leaf in leaves)
                cnode["count"][key].configure(text=f"{sel}/{tot}")

    # --- fit-content sizing + wrapping + teardown ---------------------

    def _fit_content_width(self) -> int:
        """The open width that keeps the widest collection title on ONE
        line. A BOUNDED measure (only the ~30 L1 titles + their L2 folder
        paths, NEVER the leaves — the owner's perf rule): widest name +
        the fixed reserve (indent + triangle + the two count columns) +
        the scrollbar gutter, clamped to [SELECT_MIN_W, screen*MAX]. The
        row labels render in the ttk root font ('.' style)."""
        font = tk_font("root")
        widest = 0
        for coll in self._collections:
            widest = max(widest, font.measure(coll["label"]))
            for folder in coll["folders"]:
                widest = max(
                    widest,
                    font.measure(folder["folder"]) + SELECT_INDENT_PX,
                )
        needed = widest + SELECT_FIT_PAD_PX + SELECT_WRAP_RESERVE_PX
        needed += SELECT_SCROLLBAR_PX
        return int(min(
            max(needed, SELECT_MIN_W),
            self.winfo_screenwidth() * DOC_MAX_FRAC,
        ))

    @staticmethod
    def _wraplength_for(canvas_width: int) -> int:
        return max(canvas_width - SELECT_WRAP_RESERVE_PX, SELECT_WRAP_MIN_PX)

    def _on_canvas_configure(self, event) -> None:
        # settle-debounced like the main window's re-fit (owner
        # 2026-07-20): the wraplength re-flow re-wraps EVERY built
        # label, and the old after_idle coalescing still ran it several
        # times across one drag (the loop goes idle between <Configure>
        # bursts) — now it runs ONCE, RESIZE_SETTLE_MS after the last
        # canvas <Configure>.
        self._canvas_width = event.width
        if self._wrap_job is not None:
            self.after_cancel(self._wrap_job)
        self._wrap_job = self.after(RESIZE_SETTLE_MS, self._apply_wrap)

    def _apply_wrap(self) -> None:
        """Re-flow the wrapped names to the settled canvas width — only
        the currently-built labels (L1/L2 always, L3 only in open
        folders)."""
        self._wrap_job = None
        self._wrap = self._wraplength_for(self._canvas_width)
        for lbl in self._static_labels:
            lbl.configure(wraplength=self._wrap)
        for cnode in self._collection_nodes:
            for fnode in cnode["folders"]:
                if fnode["built"]:
                    for lbl in fnode["leaf_labels"]:
                        lbl.configure(wraplength=self._wrap)

    def _on_destroy(self, event) -> None:
        # <Destroy> bubbles up from every child — act only on our own
        if event.widget is not self:
            return
        if self in THEME_TOPLEVELS:
            THEME_TOPLEVELS.remove(self)
        for var, token in self._traces:
            var.trace_remove("write", token)
        self._traces.clear()
        for job in (self._recount_job, self._wrap_job, self._expand_job):
            if job is not None:
                self.after_cancel(job)
        self._recount_job = self._wrap_job = self._expand_job = None
