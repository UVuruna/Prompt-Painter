"""PromptPainter GUI — the owner's front door.

A small tkinter window over the same engine the CLI uses: pick the
sheet, pick the output folder, tick Gemini / ChatGPT / both, open
the automation Chrome (log in once — the profile persists), check
the sheet, start. Both sites run in PARALLEL, one thread and one tab
each, each at its own pace; the log pane interleaves them with
[site] prefixes. Stop finishes the current item, then stops — every
finished image is already in the progress sidecar, so nothing is
ever lost.
"""

from __future__ import annotations

import queue
import threading
import tkinter as tk
from dataclasses import replace
from pathlib import Path
from tkinter import filedialog, messagebox, scrolledtext, ttk

from painter.config import DEFAULT_OUT_DIR, CDP_URL, SITES, TIMING
from painter.sheet_parser import SheetError, parse_sheet


class PainterGui:
    def __init__(self, root: tk.Tk):
        self.root = root
        root.title("PromptPainter")
        root.minsize(720, 480)

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
        self.bgfix_var = tk.BooleanVar(value=True)
        ttk.Checkbutton(
            row, text="Background fix (DOMY tool)", variable=self.bgfix_var
        ).pack(side="left", padx=14)
        ttk.Label(row, text="Pause:").pack(side="left", padx=(14, 2))
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
        out_base = Path(self.out_var.get().strip() or str(DEFAULT_OUT_DIR))

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

        for key in sites:
            out_root = out_base.resolve() / key
            if sheet.source.resolve().is_relative_to(out_root):
                messagebox.showerror(
                    "PromptPainter",
                    "The sheet lives inside the output folder — sources"
                    " are READ ONLY; pick another output folder.",
                )
                return

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
        self._log(f"=== START {', '.join(sites)} -> {out_base} ===")

        for key in sites:
            worker = threading.Thread(
                target=self._drive_site,
                args=(key, sheet, out_base.resolve() / key, timing, post_save),
                daemon=True,
            )
            self._workers.append(worker)
            worker.start()

    def _drive_site(self, key, sheet, out_root, timing, post_save) -> None:
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
            )
            log(f"done: {generated} image(s) into {out_root}")
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


def main() -> None:
    root = tk.Tk()
    PainterGui(root)
    root.mainloop()


if __name__ == "__main__":
    main()
