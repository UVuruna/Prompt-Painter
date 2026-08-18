"""``DocWindow`` — the readable in-app Markdown/prompt/image viewer,
with the optional Fixer-AI manual buttons (root Rule #20 god-file
split of ``gui/viewers.py``, 2026-07-30). Used for sheet- and
folder-level dashboard rows; IMAGE-level rows open
``gui.image_viewer.ImageViewer`` instead (GUI rework Phase F4f).

``AI_POLL_MS`` (the AI-dialog worker-queue poll cadence) lives in
``gui.dialogs`` — ``_AiDialog`` owns it — but ``DocWindow``'s OWN Fixer
poll (``_arm_fix_poll``, unrelated to any AI dialog) reads the same
constant. A direct ``from .dialogs import AI_POLL_MS`` would be
circular: ``gui.dialogs`` imports ``DocWindow`` from THIS module (its
``AiSheetDialog._finish`` opens one on an unrepairable draft). So
``_arm_fix_poll`` reaches it through a deferred ``import gui`` instead —
the same late-binding idiom ``gui.theme._pkg()`` and ``gui.api_panel``'s
``_arm_probe_poll`` already established for a callback that must reach
back into a sibling module without a module-level cycle.
"""

from __future__ import annotations

import queue
import threading
import tkinter as tk
from functools import partial
from pathlib import Path
from tkinter import ttk
from typing import Callable

import customtkinter as ctk
import ttkbootstrap as tb
from PIL import Image

from .dash_helpers import _scaled_photo
from .logic import _fix_result_ui
from .theme import THEME_TOPLEVELS, finish_toplevel, skin_text
from .viewer_shared import (
    DOC_A4_RATIO,
    DOC_CHROME_PAD_PX,
    DOC_HEIGHT_FRAC,
    DOC_IMG_PAD_PX,
    DOC_MAX_FRAC,
    DOC_MIN_H,
    DOC_MIN_W,
    _copy_to_clipboard,
    _readonly_text_keys,
)
from .widgets import rounded_button, status, tk_font, wrap_bar_label
from .worker_poll import poll_worker_queue


class DocWindow(tk.Toplevel):
    """A readable, selectable in-app viewer for Markdown — for people
    who do not want a code editor. Light formatting (headings, code,
    bullets, bold) plus a one-click 'Copy for AI'. Used for the
    authoring instructions, a whole collection file, and a single
    image's prompt."""

    def __init__(
        self, master, title: str, raw_markdown: str,
        copy_text: str | None = None, hint: str | None = None,
        image_path: Path | None = None,
        on_image_fix: Callable[[], tuple[str, str]] | None = None,
        on_website_fix: Callable[[], tuple[str, str]] | None = None,
    ):
        super().__init__(master)
        finish_toplevel(self, title=title, minsize=(DOC_MIN_W, DOC_MIN_H))
        self._raw = raw_markdown
        self._copy_text = copy_text if copy_text is not None else raw_markdown
        self._image_path = image_path
        self._img_ref = None  # keeps the PhotoImage alive

        bar = ttk.Frame(self, padding=6)
        bar.pack(fill="x")
        self._bar = bar  # measured by _fit_height for the non-text chrome
        hint_lbl = None
        if hint:
            hint_lbl = ttk.Label(bar, text=hint, style="Muted.TLabel")
            hint_lbl.pack(side="left")
        copy_btn = rounded_button(
            bar, "Copy (for AI)", command=self._copy_all, kind="info",
            icon_name="copy",
        )
        copy_btn.pack(side="right")
        close_btn = rounded_button(
            bar, "Close", icon_name="close", command=self.destroy,
        )
        close_btn.pack(side="right", padx=4)
        # THE SPACE & LEGIBILITY LAW (rules/GUI.md): the hint can be
        # longer than the window's declared minimum leaves room for on
        # one line — wrap it into the bar's live remaining width instead
        # of forcing the bar (and DOC_MIN_W) wider (ladder step 2).
        if hint_lbl is not None:
            wrap_bar_label(bar, hint_lbl, copy_btn, close_btn)

        # the Fixer AI's manual buttons (GUI rework Phase 20, owner's
        # UV/prompt.txt item 2: "Checker double click -> ... gore buttone
        # za IMAGE FIX i WEBSITE fix ako je procenio gresku") — a SECOND
        # bar, shown only when the CALLER (DashPanel._show_check /
        # AiCheckPanel._on_activate, via PainterGui._build_fix_workers)
        # determined this report carries defects; a report with none
        # passes both callbacks as None and this bar is never built —
        # "shown only when the report has defects". Generic: DocWindow
        # itself knows nothing about ai.py/driver.py, only that it was
        # handed zero-arg workers to run on a background thread and a
        # ("ok"/"gated"/"error", message) pair to react to.
        self._on_image_fix = on_image_fix
        self._on_website_fix = on_website_fix
        self._fix_bar = None
        self.btn_image_fix: ctk.CTkButton | None = None
        self.btn_website_fix: ctk.CTkButton | None = None
        if on_image_fix is not None or on_website_fix is not None:
            fix_bar = ttk.Frame(self, padding=(6, 0, 6, 6))
            fix_bar.pack(fill="x")
            self._fix_bar = fix_bar
            if on_website_fix is not None:
                self.btn_website_fix = rounded_button(
                    fix_bar, "WEBSITE FIX",
                    icon_name="web", command=partial(self._run_fix, "website"), kind="info",
                )
                self.btn_website_fix.pack(side="right")
            if on_image_fix is not None:
                self.btn_image_fix = rounded_button(
                    fix_bar, "IMAGE FIX",
                    icon_name="reference", command=partial(self._run_fix, "image"), kind="info",
                )
                self.btn_image_fix.pack(side="right", padx=(0, 4))
            self._fix_status_var = tk.StringVar(value="")
            ttk.Label(
                fix_bar, textvariable=self._fix_status_var,
                style="Muted.TLabel", wraplength=DOC_MIN_W,
            ).pack(side="left")
        self._fix_q: queue.Queue = queue.Queue()
        self._fix_poll_job: str | None = None

        wrap = ttk.Frame(self)
        wrap.pack(fill="both", expand=True, padx=6, pady=(0, 6))
        self.txt = tk.Text(
            wrap, wrap="word", font=tk_font("root"), padx=14, pady=12,
            spacing1=2, spacing3=2, cursor="arrow",
            # width=1/height=1 (the same convention gui.sheetgen_panel
            # already uses): Tk's Text defaults to an 80x24 CHARACTER
            # GRID request, unrelated to real content - this widget's
            # real size is fully driven by _apply_width/_fit_height
            # below, so its own default request must never act as a
            # hidden minimum the window can't shrink under (THE SPACE &
            # LEGIBILITY LAW, rules/GUI.md).
            width=1, height=1,
        )
        skin_text(self.txt)
        vsb = ttk.Scrollbar(
            wrap, orient="vertical", command=self.txt.yview,
            bootstyle="round",
        )
        self.txt.configure(yscrollcommand=vsb.set)
        vsb.pack(side="right", fill="y")
        self.txt.pack(side="left", fill="both", expand=True)

        self._configure_tags()
        self._apply_width()
        self._render(raw_markdown)
        self._append_image()
        # the PRECISE height needs the Text laid out at its final width,
        # which only happens once the window is MAPPED — measuring in
        # __init__ (unmapped) reads a zero-height Text. So the window opens
        # at a sensible tall provisional and _fit_height snaps it to the
        # real content on first map (one-shot).
        self.bind("<Map>", self._on_first_map)
        # read-only, but fully selectable and Ctrl+C / Ctrl+A copyable
        self.txt.bind("<Key>", _readonly_text_keys)
        self.bind("<Destroy>", self._on_destroy)

    def _on_first_map(self, event) -> None:
        if event.widget is not self:
            return
        self.unbind("<Map>")
        self._fit_height()

    def _on_destroy(self, event) -> None:
        # <Destroy> bubbles up from every child — act only on our own
        if event.widget is self and self in THEME_TOPLEVELS:
            THEME_TOPLEVELS.remove(self)

    def apply_theme(self) -> None:
        """Re-run the tag config so the inserted text recolours in place
        (the Text tags carry per-tag foregrounds that do not follow ttk
        styles); the Text body bg/fg rides the global recolour."""
        self._configure_tags()

    def _apply_width(self) -> None:
        """Set the window WIDTH before rendering, so the Text wraps and
        the image scales to it. This REPLACES the old longest-line measure
        that blew the window to near-full-screen when a ~200-word prompt
        sat on one line. Two modes:
          IMAGE (a single image's prompt, image_path set): width follows
            the IMAGE — its native width + padding, clamped to the screen —
            so the picture shows large and the prompt wraps into that
            same column above it.
          TEXT (instructions / whole collection / folder excerpt): a
            portrait A4 proportion, so long one-line prompts wrap into a
            readable column instead of stretching the window."""
        max_w = int(self.winfo_screenwidth() * DOC_MAX_FRAC)
        if self._image_path is not None:
            width = self._image_native_width() + DOC_IMG_PAD_PX
        else:
            width = int(
                self.winfo_screenheight() * DOC_HEIGHT_FRAC * DOC_A4_RATIO
            )
        width = min(max(width, DOC_MIN_W), max_w)
        self._target_w = width
        # a tall provisional height (the natural size of a long doc / a
        # medallion) so the first paint is close to final; _fit_height
        # snaps it to the real content on the first <Map>.
        prov_h = min(
            max(int(self.winfo_screenheight() * DOC_HEIGHT_FRAC), DOC_MIN_H),
            int(self.winfo_screenheight() * DOC_MAX_FRAC),
        )
        self.geometry(f"{width}x{prov_h}")
        self.update_idletasks()

    def _image_native_width(self) -> int:
        """The saved image's native pixel width; a sensible min if the
        file cannot be read (the image section then just shows nothing)."""
        try:
            with Image.open(self._image_path) as img:
                return img.width
        except OSError:
            return DOC_MIN_W

    def _fit_height(self) -> None:
        """Height = the RENDERED content height (wrapped text + the
        image), clamped to a sensible min and the screen fraction; the
        vertical scrollbar takes any overflow. Measured AFTER render +
        append so the real wrapped-line and image extent are known — the
        window is portrait-ish for a tall medallion, short for a stub."""
        self.update_idletasks()
        try:
            content_h = self.txt.count("1.0", "end", "ypixels")[0]
        except (tk.TclError, TypeError, IndexError):
            content_h = 0
        needed = content_h + self._chrome_height()
        height = min(
            max(needed, DOC_MIN_H),
            int(self.winfo_screenheight() * DOC_MAX_FRAC),
        )
        self.geometry(f"{self._target_w}x{height}")

    def _chrome_height(self) -> int:
        """Everything that is NOT the Text's own line flow: the top button
        bar, the OPTIONAL Fixer-AI action bar (GUI rework Phase 20 —
        present only when on_image_fix/on_website_fix was given), plus
        the Text padding and frame margins (DOC_CHROME_PAD_PX)."""
        height = self._bar.winfo_reqheight()
        if self._fix_bar is not None:
            height += self._fix_bar.winfo_reqheight()
        return height + DOC_CHROME_PAD_PX

    def _append_image(self) -> None:
        """The saved image, below the prompt, scaled to fit the window
        width (the viewer keeps the PhotoImage reference alive). No
        file — no section, the prompt stands alone as before."""
        if self._image_path is None:
            return
        self.update_idletasks()
        avail = max(self.winfo_width() - 80, 320)
        try:
            self._img_ref = _scaled_photo(self._image_path, avail)
        except OSError as exc:
            self._log_line(f"(image unreadable: {exc})")
            return
        self.txt.configure(state="normal")
        self.txt.insert("end", "\n")
        self.txt.image_create("end", image=self._img_ref, padx=8, pady=8)
        self.txt.insert("end", "\n")
        self.txt.configure(state="disabled")

    def _log_line(self, line: str) -> None:
        self.txt.configure(state="normal")
        self.txt.insert("end", line + "\n")
        self.txt.configure(state="disabled")

    def _configure_tags(self) -> None:
        colors = tb.Style().colors
        self.txt.tag_configure("h1", font=tk_font("doc_h1"),
                               foreground=colors.info,
                               spacing1=10, spacing3=6)
        self.txt.tag_configure("h2", font=tk_font("doc_h2"),
                               foreground=colors.info,
                               spacing1=8, spacing3=4)
        self.txt.tag_configure("h3", font=tk_font("head"),
                               foreground=status("done"),
                               spacing1=6, spacing3=3)
        self.txt.tag_configure(
            "code", font=tk_font("mono"), background=colors.dark,
            foreground=status("code_fg"), lmargin1=16, lmargin2=16,
        )
        self.txt.tag_configure("bold", font=tk_font("bold"))
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

    def _copy_all(self) -> None:
        _copy_to_clipboard(self, self._copy_text)

    # --- Fixer AI manual buttons (GUI rework Phase 20) -------------------
    # Mirrors ApiImageGenPanel's own "Check API access" probe shape
    # (_probe_access/_arm_probe_poll/_poll_probe/_apply_probe_result,
    # GUI rework Phase 19) exactly — a background thread posts ONE
    # ("kind", "message") result onto a private queue, polled via
    # self.after(AI_POLL_MS, ...) so the network/browser call never
    # blocks the Tk event loop. ``kind`` is "ok" (the image was
    # overwritten), "gated" (PaidFeatureRequired / AttachNotConfigured —
    # PERMANENT for this ONE path), or "error" (anything else —
    # transient, retry-able; e.g. the site is currently generating).

    def _run_fix(self, which: str) -> None:
        worker = self._on_image_fix if which == "image" else self._on_website_fix
        if worker is None:
            return
        btn = self.btn_image_fix if which == "image" else self.btn_website_fix
        other = self.btn_website_fix if which == "image" else self.btn_image_fix
        # both buttons disable together while ONE is in flight — a second
        # fix started before the first lands would race the same file
        if btn is not None:
            btn.configure(state="disabled")
        if other is not None:
            other.configure(state="disabled")
        self._fix_status_var.set("Fixing …")

        def work() -> None:
            self._fix_q.put((which, worker()))

        threading.Thread(target=work, daemon=True).start()
        self._arm_fix_poll()

    def _arm_fix_poll(self) -> None:
        # AI_POLL_MS lives in gui.dialogs (_AiDialog owns it); a real-path
        # import here would be circular (gui.dialogs imports DocWindow
        # from this module) — see the module docstring.
        import gui

        poll_worker_queue(
            self, self._fix_q, lambda msg: self._apply_fix_result(*msg),
            poll_ms=gui.AI_POLL_MS, after_attr="_fix_poll_job",
        )

    def _apply_fix_result(self, which: str, result: tuple[str, str]) -> None:
        """Apply ``_fix_result_ui``'s PURE decision (module-level, Tk-
        free, headlessly tested — see its own docstring) to the real
        buttons: this method itself does nothing but read that 3-tuple
        and configure widget state, the "real Tk/UI wiring gets a
        screenshot" half of gui.py's own established split."""
        status, enable_image, enable_website = _fix_result_ui(which, result)
        self._fix_status_var.set(status)
        if enable_image is not None and self.btn_image_fix is not None:
            self.btn_image_fix.configure(
                state="normal" if enable_image else "disabled"
            )
        if enable_website is not None and self.btn_website_fix is not None:
            self.btn_website_fix.configure(
                state="normal" if enable_website else "disabled"
            )
