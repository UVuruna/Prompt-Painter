"""PromptPainter GUI — the owner's front door.

A small tkinter window over the same engine the CLI uses: pick the
sheet, pick the output folder, tick Gemini / ChatGPT / both, choose
the background mode, open the automation Chrome (log in once — the
profile persists), check the sheet, start. Both sites run in
PARALLEL, one thread and one tab each; the log pane interleaves
them with [site] prefixes.

Output is TWO-PHASE: generation stages every image under
``<out>/_staging/<site>/``, and when the run ends a review window
shows them — only the owner's Approve moves an image to its final
``<out>/<site>/<drop-path>``; Reject deletes it and clears its
progress mark so the next run regenerates it (usually after the
prompt was reworked in the sheet).
"""

from __future__ import annotations

import queue
import threading
import tkinter as tk
from dataclasses import replace
from pathlib import Path
from tkinter import filedialog, messagebox, scrolledtext, ttk

from painter.config import (
    BACKGROUND_MODES,
    CDP_URL,
    DEFAULT_OUT_DIR,
    SITES,
    TIMING,
    background_suffix,
)
from painter.review import approve, reject, staged_images, staging_root
from painter.sheet_parser import SheetError, parse_sheet

THUMB_PX = 160


class PainterGui:
    def __init__(self, root: tk.Tk):
        self.root = root
        root.title("PromptPainter")
        root.minsize(760, 500)

        self._q: queue.Queue = queue.Queue()
        self._stop = threading.Event()
        self._workers: list[threading.Thread] = []

        pad = {"padx": 6, "pady": 3}
        frame = ttk.Frame(root)
        frame.pack(fill="both", expand=True, **pad)

        # --- paths -----------------------------------------------------
        self.sheet_var = tk.StringVar()
        self.out_var = tk.StringVar(value=str(DEFAULT_OUT_DIR))

        row = ttk.Frame(frame)
        row.pack(fill="x", **pad)
        ttk.Label(row, text="Sheet (.md):", width=12).pack(side="left")
        ttk.Entry(row, textvariable=self.sheet_var).pack(
            side="left", fill="x", expand=True
        )
        ttk.Button(row, text="Browse...", command=self._pick_sheet).pack(
            side="left", padx=4
        )

        row = ttk.Frame(frame)
        row.pack(fill="x", **pad)
        ttk.Label(row, text="Output:", width=12).pack(side="left")
        ttk.Entry(row, textvariable=self.out_var).pack(
            side="left", fill="x", expand=True
        )
        ttk.Button(row, text="Browse...", command=self._pick_out).pack(
            side="left", padx=4
        )

        # --- options ---------------------------------------------------
        row = ttk.Frame(frame)
        row.pack(fill="x", **pad)
        self.site_vars = {
            key: tk.BooleanVar(value=True) for key in sorted(SITES)
        }
        ttk.Label(row, text="Sites:", width=12).pack(side="left")
        for key in sorted(SITES):
            ttk.Checkbutton(
                row, text=SITES[key].name, variable=self.site_vars[key]
            ).pack(side="left", padx=2)

        ttk.Label(row, text="Background:").pack(side="left", padx=(14, 2))
        self.background_var = tk.StringVar(value="auto")
        ttk.Combobox(
            row,
            textvariable=self.background_var,
            values=list(BACKGROUND_MODES),
            state="readonly",
            width=11,
        ).pack(side="left")

        self.bgfix_var = tk.BooleanVar(value=True)
        ttk.Checkbutton(
            row, text="Background fix", variable=self.bgfix_var
        ).pack(side="left", padx=14)

        ttk.Label(row, text="Pause:").pack(side="left", padx=(8, 2))
        self.pause_var = tk.StringVar(
            value=f"{TIMING.pause_between_prompts_s:.0f}"
        )
        ttk.Spinbox(
            row, from_=0, to=600, width=5, textvariable=self.pause_var
        ).pack(side="left")
        ttk.Label(row, text="s").pack(side="left")

        # --- buttons ---------------------------------------------------
        row = ttk.Frame(frame)
        row.pack(fill="x", **pad)
        self.btn_chrome = ttk.Button(
            row, text="Open Chrome (login)", command=self._open_chrome
        )
        self.btn_chrome.pack(side="left", padx=2)
        self.btn_check = ttk.Button(
            row, text="Check sheet", command=self._check_sheet
        )
        self.btn_check.pack(side="left", padx=2)
        self.btn_start = ttk.Button(row, text="Start", command=self._start)
        self.btn_start.pack(side="left", padx=2)
        self.btn_stop = ttk.Button(
            row, text="Stop", command=self._request_stop, state="disabled"
        )
        self.btn_stop.pack(side="left", padx=2)
        self.btn_review = ttk.Button(
            row, text="Review staged", command=self._open_review
        )
        self.btn_review.pack(side="left", padx=14)

        # --- log -------------------------------------------------------
        self.log_box = scrolledtext.ScrolledText(
            frame, height=18, state="disabled", font=("Consolas", 9)
        )
        self.log_box.pack(fill="both", expand=True, **pad)

        self.status_var = tk.StringVar(value="idle")
        ttk.Label(frame, textvariable=self.status_var, anchor="w").pack(
            fill="x", **pad
        )

        root.after(120, self._drain_queue)

    # --- helpers --------------------------------------------------------

    def _log(self, line: str) -> None:
        self.log_box.configure(state="normal")
        self.log_box.insert("end", line + "\n")
        self.log_box.see("end")
        self.log_box.configure(state="disabled")

    def _pick_sheet(self) -> None:
        path = filedialog.askopenfilename(
            title="Prompt sheet", filetypes=[("Markdown", "*.md")]
        )
        if path:
            self.sheet_var.set(path)

    def _pick_out(self) -> None:
        path = filedialog.askdirectory(title="Output folder")
        if path:
            self.out_var.set(path)

    def _selected_sites(self) -> list[str]:
        return [k for k, v in self.site_vars.items() if v.get()]

    def _out_base(self) -> Path:
        return Path(self.out_var.get().strip() or str(DEFAULT_OUT_DIR)).resolve()

    def _parse_checked(self):
        """Parse + report the sheet; None when it must not run."""
        raw = self.sheet_var.get().strip()
        if not raw:
            messagebox.showerror("PromptPainter", "Pick a sheet .md first.")
            return None
        try:
            sheet = parse_sheet(Path(raw))
        except (SheetError, OSError) as exc:
            messagebox.showerror("PromptPainter", str(exc))
            return None
        self._log(f"THEME: {sheet.theme}")
        self._log(
            f"  {len(sheet.items)} to generate,"
            f" {len(sheet.skipped)} skipped,"
            f" {len(sheet.problems)} problem(s)"
        )
        for it in sheet.items:
            self._log(f"  GEN  L{it.line:<4} {it.drop_path}")
        for sk in sheet.skipped:
            self._log(f"  SKIP L{sk.line:<4} {sk.title} — {sk.reason}")
        for pr in sheet.problems:
            self._log(f"  PROBLEM L{pr.line}: {pr.message}")
        if sheet.problems:
            messagebox.showerror(
                "PromptPainter",
                "The sheet violates the contract — fix the sheet first"
                " (problems are listed in the log).",
            )
            return None
        return sheet

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

    def _check_sheet(self) -> None:
        self._parse_checked()

    def _start(self) -> None:
        sheet = self._parse_checked()
        if sheet is None:
            return
        sites = self._selected_sites()
        if not sites:
            messagebox.showerror("PromptPainter", "Tick at least one site.")
            return
        out_base = self._out_base()

        if sheet.source.resolve().is_relative_to(out_base):
            messagebox.showerror(
                "PromptPainter",
                "The sheet lives inside the output folder — sources"
                " are READ ONLY; pick another output folder.",
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
            pause = float(self.pause_var.get())
        except ValueError:
            messagebox.showerror("PromptPainter", "Pause must be a number.")
            return
        timing = replace(TIMING, pause_between_prompts_s=pause)

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
        mode = self.background_var.get()
        self._log(
            f"=== START {', '.join(sites)} -> {out_base}"
            f" (background: {mode}) ==="
        )

        for key in sites:
            worker = threading.Thread(
                target=self._drive_site,
                args=(
                    key,
                    sheet,
                    staging_root(out_base, key),
                    timing,
                    post_save,
                    background_suffix(mode, SITES[key]),
                ),
                daemon=True,
            )
            self._workers.append(worker)
            worker.start()

    def _drive_site(self, key, sheet, out_root, timing, post_save, suffix):
        """One site's whole run — its own thread, driver and log prefix."""
        from painter.driver import DriverError, SiteDriver, TerminalState
        from painter.runner import run_sheet

        log = lambda msg: self._q.put(f"[{key}] {msg}")
        driver = SiteDriver(SITES[key], timing, CDP_URL)
        try:
            title = driver.attach()
            log(f"attached to {title!r} — SUPERVISED, watch the window")
            generated = run_sheet(
                sheet,
                driver,
                out_root,
                timing,
                log=log,
                should_stop=self._stop.is_set,
                post_save=post_save,
                prompt_suffix=suffix,
            )
            log(f"done: {generated} image(s) staged in {out_root}")
        except TerminalState as exc:
            log(f"TERMINAL STATE: {exc}")
            log("run stopped; progress saved — start again later to resume")
        except DriverError as exc:
            log(f"DRIVER ERROR: {exc}")
            log("progress saved — fix the cause and start again to resume")
        except Exception as exc:  # surfaced, never swallowed
            log(f"UNEXPECTED ERROR: {type(exc).__name__}: {exc}")
        finally:
            driver.close()
            self._q.put(("__worker_done__", key))

    def _request_stop(self) -> None:
        self._stop.set()
        self.status_var.set("stopping after the current item ...")

    # --- phase two: review ----------------------------------------------

    def _open_review(self) -> None:
        out_base = self._out_base()
        staged = staged_images(out_base, tuple(sorted(SITES)))
        if not staged:
            messagebox.showinfo(
                "PromptPainter", f"Nothing staged under {out_base}."
            )
            return
        ReviewWindow(self.root, out_base, staged, self._log)

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
                            self._open_review_if_staged()
                else:
                    self._log(str(msg))
        except queue.Empty:
            pass
        self.root.after(120, self._drain_queue)

    def _open_review_if_staged(self) -> None:
        out_base = self._out_base()
        staged = staged_images(out_base, tuple(sorted(SITES)))
        if staged:
            self._log(f"{len(staged)} image(s) staged — opening review")
            ReviewWindow(self.root, out_base, staged, self._log)


class ReviewWindow(tk.Toplevel):
    """Phase two: thumbnails of staged images, Approve / Reject each."""

    def __init__(self, master, out_base: Path, staged, log):
        super().__init__(master)
        self.title(f"Review staged — {len(staged)} image(s)")
        self.minsize(560, 420)
        self._out_base = out_base
        self._log = log
        self._thumbs = []  # keep PhotoImage references alive

        bar = ttk.Frame(self)
        bar.pack(fill="x", padx=6, pady=4)
        ttk.Button(
            bar, text="Approve ALL remaining", command=self._approve_all
        ).pack(side="left")
        ttk.Button(bar, text="Close", command=self.destroy).pack(side="right")

        canvas = tk.Canvas(self, highlightthickness=0)
        scroll = ttk.Scrollbar(self, orient="vertical", command=canvas.yview)
        self._list = ttk.Frame(canvas)
        self._list.bind(
            "<Configure>",
            lambda e: canvas.configure(scrollregion=canvas.bbox("all")),
        )
        canvas.create_window((0, 0), window=self._list, anchor="nw")
        canvas.configure(yscrollcommand=scroll.set)
        canvas.pack(side="left", fill="both", expand=True, padx=6, pady=4)
        scroll.pack(side="right", fill="y")

        self._rows: dict[object, ttk.Frame] = {}
        for item in staged:
            self._add_row(item)

    def _add_row(self, item) -> None:
        row = ttk.Frame(self._list)
        row.pack(fill="x", pady=3)
        self._rows[item] = row

        thumb = self._thumbnail(item.path)
        if thumb is not None:
            self._thumbs.append(thumb)
            ttk.Label(row, image=thumb).pack(side="left", padx=4)
        else:
            ttk.Label(row, text="(no preview)").pack(side="left", padx=4)

        ttk.Label(
            row, text=f"[{item.site}] {item.drop_path}", anchor="w"
        ).pack(side="left", fill="x", expand=True, padx=6)
        ttk.Button(
            row, text="Approve", command=lambda: self._approve(item)
        ).pack(side="left", padx=2)
        ttk.Button(
            row, text="Reject", command=lambda: self._reject(item)
        ).pack(side="left", padx=2)

    def _thumbnail(self, path: Path):
        try:
            from PIL import Image, ImageTk

            with Image.open(path) as img:
                img.thumbnail((THUMB_PX, THUMB_PX))
                return ImageTk.PhotoImage(img, master=self)
        except Exception:
            return None  # no preview; Approve/Reject still work

    def _drop_row(self, item) -> None:
        self._rows.pop(item).destroy()
        if not self._rows:
            self.destroy()

    def _approve(self, item) -> None:
        dest = approve(self._out_base, item)
        self._log(f"[{item.site}] APPROVED -> {dest}")
        self._drop_row(item)

    def _reject(self, item) -> None:
        if not messagebox.askyesno(
            "Reject image",
            f"Delete {item.drop_path} ({item.site})?\n"
            "The next run will regenerate it.",
            parent=self,
        ):
            return
        reject(self._out_base, item)
        self._log(f"[{item.site}] REJECTED {item.drop_path} — will regenerate")
        self._drop_row(item)

    def _approve_all(self) -> None:
        for item in list(self._rows):
            dest = approve(self._out_base, item)
            self._log(f"[{item.site}] APPROVED -> {dest}")
            self._drop_row(item)


def main() -> None:
    root = tk.Tk()
    PainterGui(root)
    root.mainloop()


if __name__ == "__main__":
    main()
