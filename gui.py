"""PromptPainter GUI — the owner's front door.

A small tkinter window over the same engine the CLI uses: queue one
or MORE sheet `.md` files, pick the output folder, tick Gemini /
ChatGPT / both, choose each site's background, open the automation
Chrome (log in once — the profile persists), check, start. Both
sites run in PARALLEL, one thread and one tab each; each site works
through the sheet queue IN ORDER, finishing folder after folder, so
a quota stop on one site never costs finished work — progress and
the report live beside the images and every run resumes.

Images save DIRECTLY to ``<out>/<site>/<drop-path>`` (no approval
step); an optional per-sheet report txt logs timestamps, per-image
generation times, resolutions, extra actions and totals.
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
from pathlib import Path
from tkinter import filedialog, messagebox, scrolledtext, ttk

from painter.config import (
    BACKGROUND_CHOICES,
    CDP_URL,
    DEFAULT_OUT_DIR,
    PROGRESS_SUFFIX,
    SITES,
    TIMING,
    prompt_suffix,
)
from painter.sheet_parser import Sheet, SheetError, parse_sheet


class PainterGui:
    def __init__(self, root: tk.Tk):
        self.root = root
        root.title("PromptPainter")
        root.minsize(780, 540)

        self._q: queue.Queue = queue.Queue()
        self._stop = threading.Event()
        self._workers: list[threading.Thread] = []
        self._sheets: list[Path] = []
        # (site, source-path, drop-path) -> BooleanVar; missing = ticked
        self._select_vars: dict[tuple[str, str, str], tk.BooleanVar] = {}

        pad = {"padx": 6, "pady": 3}
        frame = ttk.Frame(root)
        frame.pack(fill="both", expand=True, **pad)

        # --- the sheet queue -------------------------------------------
        row = ttk.Frame(frame)
        row.pack(fill="x", **pad)
        ttk.Label(row, text="Sheets (.md):", width=12).pack(
            side="left", anchor="n"
        )
        self.sheet_list = tk.Listbox(row, height=5, activestyle="none")
        self.sheet_list.pack(side="left", fill="x", expand=True)
        col = ttk.Frame(row)
        col.pack(side="left", padx=4, anchor="n")
        ttk.Button(col, text="Add...", command=self._add_sheets).pack(
            fill="x"
        )
        ttk.Button(col, text="Remove", command=self._remove_sheet).pack(
            fill="x", pady=2
        )
        ttk.Button(col, text="Clear", command=self._clear_sheets).pack(
            fill="x"
        )

        # --- output -----------------------------------------------------
        self.out_var = tk.StringVar(value=str(DEFAULT_OUT_DIR))
        row = ttk.Frame(frame)
        row.pack(fill="x", **pad)
        ttk.Label(row, text="Output:", width=12).pack(side="left")
        ttk.Entry(row, textvariable=self.out_var).pack(
            side="left", fill="x", expand=True
        )
        ttk.Button(row, text="Browse...", command=self._pick_out).pack(
            side="left", padx=4
        )

        # --- options ----------------------------------------------------
        row = ttk.Frame(frame)
        row.pack(fill="x", **pad)
        self.site_vars = {
            key: tk.BooleanVar(value=True) for key in sorted(SITES)
        }
        ttk.Label(row, text="Sites:", width=12).pack(side="left")
        self.background_vars: dict[str, tk.StringVar] = {}
        for key in sorted(SITES):
            ttk.Checkbutton(
                row, text=SITES[key].name, variable=self.site_vars[key]
            ).pack(side="left", padx=(2, 0))
            var = tk.StringVar(value=SITES[key].default_background)
            self.background_vars[key] = var
            ttk.Combobox(
                row,
                textvariable=var,
                values=list(BACKGROUND_CHOICES),
                state="readonly",
                width=11,
            ).pack(side="left", padx=(2, 10))

        row = ttk.Frame(frame)
        row.pack(fill="x", **pad)
        ttk.Label(row, text="", width=12).pack(side="left")
        self.bgfix_var = tk.BooleanVar(value=True)
        ttk.Checkbutton(
            row, text="Background fix", variable=self.bgfix_var
        ).pack(side="left")
        self.report_var = tk.BooleanVar(value=True)
        ttk.Checkbutton(
            row, text="Write report txt", variable=self.report_var
        ).pack(side="left", padx=14)
        ttk.Label(row, text="Pause:").pack(side="left", padx=(8, 2))
        self.pause_min_var = tk.StringVar(value=f"{TIMING.pause_min_s:.0f}")
        self.pause_max_var = tk.StringVar(value=f"{TIMING.pause_max_s:.0f}")
        ttk.Spinbox(
            row, from_=0, to=600, width=5, textvariable=self.pause_min_var
        ).pack(side="left")
        ttk.Label(row, text="–").pack(side="left")
        ttk.Spinbox(
            row, from_=0, to=600, width=5, textvariable=self.pause_max_var
        ).pack(side="left")
        ttk.Label(row, text="s (random)").pack(side="left")

        # --- buttons ----------------------------------------------------
        row = ttk.Frame(frame)
        row.pack(fill="x", **pad)
        self.btn_chrome = ttk.Button(
            row, text="Open Chrome (login)", command=self._open_chrome
        )
        self.btn_chrome.pack(side="left", padx=2)
        self.btn_check = ttk.Button(
            row, text="Check sheets", command=self._check_sheets
        )
        self.btn_check.pack(side="left", padx=2)
        self.btn_select = ttk.Button(
            row, text="Select images...", command=self._select_images
        )
        self.btn_select.pack(side="left", padx=2)
        self.btn_start = ttk.Button(row, text="Start", command=self._start)
        self.btn_start.pack(side="left", padx=2)
        self.btn_stop = ttk.Button(
            row, text="Stop", command=self._request_stop, state="disabled"
        )
        self.btn_stop.pack(side="left", padx=2)
        ttk.Button(
            row, text="BG removal only...", command=self._bg_remove_only
        ).pack(side="left", padx=14)

        # --- log --------------------------------------------------------
        self.log_box = scrolledtext.ScrolledText(
            frame, height=16, state="disabled", font=("Consolas", 9)
        )
        self.log_box.pack(fill="both", expand=True, **pad)

        self.status_var = tk.StringVar(value="idle")
        ttk.Label(frame, textvariable=self.status_var, anchor="w").pack(
            fill="x", **pad
        )

        root.after(120, self._drain_queue)

    # --- helpers --------------------------------------------------------

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

    # --- actions --------------------------------------------------------

    def _open_chrome(self) -> None:
        sites = self._selected_sites()
        if not sites:
            messagebox.showerror("PromptPainter", "Tick at least one site.")
            return
        urls = tuple(SITES[k].url for k in sites)
        self.status_var.set("opening Chrome ...")

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
        """Tick which images run — a separate list per site."""
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
        """Standalone background removal over an existing folder."""
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
        self.status_var.set("BG removal running ...")

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
        except ValueError:
            messagebox.showerror("PromptPainter", "Pause must be numbers.")
            return
        if pause_min > pause_max:
            messagebox.showerror(
                "PromptPainter", "Pause FROM must be <= pause TO."
            )
            return
        timing = replace(
            TIMING, pause_min_s=pause_min, pause_max_s=pause_max
        )

        from painter.chrome import cdp_alive

        if not cdp_alive():
            messagebox.showerror(
                "PromptPainter",
                "No debuggable Chrome is running — press"
                " 'Open Chrome (login)' first.",
            )
            return

        self._stop.clear()
        self._workers = []
        self.btn_start.configure(state="disabled")
        self.btn_stop.configure(state="normal")
        self.status_var.set("running: " + ", ".join(sites))
        backgrounds = {
            key: self.background_vars[key].get() for key in sites
        }
        self._log(
            f"=== START {', '.join(sites)} | {len(sheets)} sheet(s)"
            f" -> {out_base} | backgrounds: {backgrounds} ==="
        )

        # the ticked selection, read in the tk thread: per site, per
        # sheet -> the drop paths to run (None = everything)
        selections: dict[str, dict[str, set[str] | None]] = {}
        for key in sites:
            per_sheet: dict[str, set[str] | None] = {}
            for sheet in sheets:
                src = str(sheet.source)
                unticked = {
                    drop
                    for (site, source, drop), var in self._select_vars.items()
                    if site == key and source == src and not var.get()
                }
                per_sheet[src] = (
                    {it.drop_path for it in sheet.items} - unticked
                    if unticked
                    else None
                )
            selections[key] = per_sheet

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
                ),
                daemon=True,
            )
            self._workers.append(worker)
            worker.start()

    def _drive_site(
        self, key, sheets, out_root, timing, post_save, suffix, report,
        selection,
    ) -> None:
        """One site's whole run — the sheet queue in order, one thread."""
        from painter.driver import DriverError, SiteDriver, TerminalState
        from painter.runner import run_sheet

        log = lambda msg: self._q.put(f"[{key}] {msg}")
        driver = SiteDriver(SITES[key], timing, CDP_URL)
        t_site = time.monotonic()
        done_sheets = 0
        try:
            title = driver.attach()
            log(f"attached to {title!r} — SUPERVISED, watch the window")
            for n, sheet in enumerate(sheets, start=1):
                if self._stop.is_set():
                    log("stopped on request — remaining sheets not started")
                    break
                log(f"--- sheet {n}/{len(sheets)}: {sheet.source.name} ---")
                try:
                    generated = run_sheet(
                        sheet,
                        driver,
                        out_root,
                        timing,
                        log=log,
                        should_stop=self._stop.is_set,
                        post_save=post_save,
                        prompt_suffix=suffix,
                        report=report,
                        only=selection.get(str(sheet.source)),
                    )
                    done_sheets += 1
                    log(
                        f"sheet done: {generated} image(s) into"
                        f" {out_root}"
                    )
                except TerminalState as exc:
                    log(f"TERMINAL STATE (quota/refusal): {exc}")
                    log(
                        "site stopped — finished work is saved; start"
                        " again later to resume the remaining sheets"
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
                f"finished {done_sheets}/{len(sheets)} sheet(s) in"
                f" {(time.monotonic() - t_site) / 60:.1f} min"
            )
        except DriverError as exc:
            log(f"DRIVER ERROR: {exc}")
        except Exception as exc:  # surfaced, never swallowed
            log(f"UNEXPECTED ERROR: {type(exc).__name__}: {exc}")
        finally:
            driver.close()
            self._q.put(("__worker_done__", key))

    def _request_stop(self) -> None:
        self._stop.set()
        self.status_var.set("stopping after the current item ...")

    # --- queue pump -----------------------------------------------------

    def _drain_queue(self) -> None:
        try:
            while True:
                msg = self._q.get_nowait()
                if isinstance(msg, tuple):
                    if msg[0] == "__status__":
                        self.status_var.set(msg[1])
                    elif msg[0] == "__worker_done__":
                        self._log(f"[{msg[1]}] worker finished")
                        if all(not w.is_alive() for w in self._workers):
                            self.btn_start.configure(state="normal")
                            self.btn_stop.configure(state="disabled")
                            self.status_var.set("idle")
                else:
                    self._log(str(msg))
        except queue.Empty:
            pass
        self.root.after(120, self._drain_queue)


class SelectWindow(tk.Toplevel):
    """Tick which images each site generates — one column per site.

    Items a site has already finished (per its progress sidecar under
    the current output folder) show disabled and unticked.
    """

    def __init__(self, gui: PainterGui, sheets: list[Sheet]):
        super().__init__(gui.root)
        self.title("Select images per site")
        self.minsize(680, 480)
        self._gui = gui

        out_base = gui._out_base()
        site_keys = sorted(SITES)
        done: dict[str, dict[str, set]] = {k: {} for k in site_keys}
        for key in site_keys:
            for sheet in sheets:
                progress_file = (
                    out_base / key / (sheet.source.stem + PROGRESS_SUFFIX)
                )
                entries: set = set()
                if progress_file.exists():
                    entries = set(
                        json.loads(
                            progress_file.read_text(encoding="utf-8")
                        )["done"]
                    )
                done[key][str(sheet.source)] = entries

        bar = ttk.Frame(self)
        bar.pack(fill="x", padx=6, pady=4)
        ttk.Label(
            bar,
            text="Tick = generate. Already-done items are disabled.",
        ).pack(side="left")
        ttk.Button(bar, text="Close", command=self.destroy).pack(
            side="right"
        )

        canvas = tk.Canvas(self, highlightthickness=0)
        scroll = ttk.Scrollbar(self, orient="vertical", command=canvas.yview)
        inner = ttk.Frame(canvas)
        inner.bind(
            "<Configure>",
            lambda e: canvas.configure(scrollregion=canvas.bbox("all")),
        )
        canvas.create_window((0, 0), window=inner, anchor="nw")
        canvas.configure(yscrollcommand=scroll.set)
        canvas.pack(side="left", fill="both", expand=True, padx=6, pady=4)
        scroll.pack(side="right", fill="y")

        header = ttk.Frame(inner)
        header.pack(fill="x", pady=(0, 2))
        for key in site_keys:
            ttk.Label(header, text=SITES[key].name, width=9).pack(
                side="left"
            )
        ttk.Label(header, text="Image").pack(side="left", padx=8)

        for sheet in sheets:
            src = str(sheet.source)
            head = ttk.Frame(inner)
            head.pack(fill="x", pady=(8, 2))
            ttk.Label(
                head,
                text=f"{sheet.source.name} — {sheet.theme}",
                font=("Segoe UI", 9, "bold"),
            ).pack(side="left")
            for key in site_keys:
                ttk.Button(
                    head,
                    text=f"{SITES[key].name}: all/none",
                    command=partial(self._toggle_sheet, key, sheet),
                ).pack(side="right", padx=2)

            for item in sheet.items:
                row = ttk.Frame(inner)
                row.pack(fill="x")
                for key in site_keys:
                    var = gui._select_var(
                        key, src, item.drop_path,
                        default=item.advice is None,
                    )
                    is_done = item.drop_path in done[key][src]
                    if is_done:
                        var.set(False)
                    cb = ttk.Checkbutton(row, variable=var, width=8)
                    if is_done:
                        cb.state(["disabled"])
                    cb.pack(side="left")
                suffix = ""
                done_sites = [
                    k for k in site_keys if item.drop_path in done[k][src]
                ]
                if done_sites:
                    suffix += "   ✔ done: " + ", ".join(
                        SITES[k].name for k in done_sites
                    )
                if item.advice:
                    suffix += f"   ⚠ {item.advice[:70]}"
                # color by state: green = done everywhere, red =
                # superseded, orange = other advice, default = pending
                if len(done_sites) == len(site_keys):
                    color = "#2e7d32"
                elif item.advice and "supersed" in item.advice.lower():
                    color = "#c62828"
                elif item.advice:
                    color = "#b26a00"
                elif done_sites:
                    color = "#558b2f"
                else:
                    color = ""
                style = {"foreground": color} if color else {}
                ttk.Label(
                    row, text=item.drop_path + suffix, **style
                ).pack(side="left", padx=8)

    def _toggle_sheet(self, site: str, sheet: Sheet) -> None:
        src = str(sheet.source)
        variables = [
            self._gui._select_var(site, src, item.drop_path)
            for item in sheet.items
        ]
        target = not all(var.get() for var in variables)
        for var in variables:
            var.set(target)


def main() -> None:
    root = tk.Tk()
    PainterGui(root)
    root.mainloop()


if __name__ == "__main__":
    main()
