"""Read-only Toplevel viewers pulled out of ``gui/__init__.py`` (root
Rule #20 god-file refactor): ``DocWindow`` (the Markdown/prompt/image
viewer, with the optional Fixer-AI manual buttons), ``BeforeAfterWindow``
(a tool job's before/after viewer), ``_filmstrip_stages`` (the pure
per-image pipeline-stage list) and ``StepRestoreWindow`` (the per-step
restore filmstrip built from it).

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
from tkinter import messagebox, ttk
from typing import Callable

import customtkinter as ctk
import ttkbootstrap as tb
from PIL import Image

from painter.config import JOBTEMP_STEP_LABEL, STEP_RESTORE_CURRENT_LABEL
from .dash_helpers import _scaled_photo
from .logic import _fix_result_ui
from .scroll import ScrollFrame
from .theme import THEME_TOPLEVELS, skin_text, skin_toplevel
from .widgets import rounded_button, status, tk_font

# --- DocWindow + shared window sizing (Rule #4) -----------------------
# The old DocWindow sized its WIDTH from the single longest line, so a
# ~200-word prompt on ONE line blew the window to near-full-screen with
# the text on one enormous line. Two modes replace that:
#   IMAGE mode (a single image's prompt viewer, image_path set): width
#     follows the IMAGE — native width + padding, clamped to the screen —
#     so the picture shows large and the prompt WRAPS into that column.
#   TEXT mode (instructions / whole collection / folder excerpt): a
#     portrait A4 proportion, so long one-line prompts wrap into a
#     readable column instead of stretching the window.
# DOC_MAX_FRAC also clamps the Select window and every doc window to a
# fraction of the screen (the single "never bigger than this" rule).
DOC_A4_RATIO = 210 / 297    # ISO A4 portrait width:height (~0.707)
DOC_HEIGHT_FRAC = 0.8       # A4 text height (and the Select tall height) = screen_h * this
DOC_MAX_FRAC = 0.9          # clamp ANY window to this fraction of the screen
DOC_MIN_W = 520             # never narrower than this (the top button bar fits)
DOC_MIN_H = 400             # never shorter than this (also the provisional height)
DOC_IMG_PAD_PX = 60         # horizontal padding around the image column (image mode)
DOC_CHROME_PAD_PX = 48      # non-text vertical chrome: Text pady + frame margins

# --- Before/after viewer (the tool panels' Restore viewer) ------------
BEFORE_AFTER_W = 760          # viewer width; before/after images scale into it
BEFORE_AFTER_IMG_PAD_PX = 60  # slack subtracted from the width for the images

# --- Per-step restore viewer (GUI rework Phase 9) ---------------------
# a horizontal filmstrip, so its own width geometry is independent of
# BEFORE_AFTER_W's stacked single-column layout.
STEP_RESTORE_W = 900        # viewer width; grows via horizontal scroll past this
STEP_RESTORE_THUMB_PX = 220  # each stage thumbnail's max width


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
        self.title(title)
        self.minsize(DOC_MIN_W, DOC_MIN_H)
        skin_toplevel(self)  # bg registered so a flip re-tints the window
        THEME_TOPLEVELS.append(self)  # flip coherently with the main window
        self._raw = raw_markdown
        self._copy_text = copy_text if copy_text is not None else raw_markdown
        self._image_path = image_path
        self._img_ref = None  # keeps the PhotoImage alive

        bar = ttk.Frame(self, padding=6)
        bar.pack(fill="x")
        self._bar = bar  # measured by _fit_height for the non-text chrome
        if hint:
            ttk.Label(bar, text=hint, style="Muted.TLabel").pack(side="left")
        rounded_button(
            bar, "Copy (for AI)", command=self._copy_all, kind="info",
            icon_name="ai",
        ).pack(side="right")
        rounded_button(
            bar, "Close", command=self.destroy,
        ).pack(side="right", padx=4)

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
                    command=partial(self._run_fix, "website"), kind="info",
                )
                self.btn_website_fix.pack(side="right")
            if on_image_fix is not None:
                self.btn_image_fix = rounded_button(
                    fix_bar, "IMAGE FIX",
                    command=partial(self._run_fix, "image"), kind="info",
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
        self.txt.bind("<Key>", self._readonly_keys)
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
        self.clipboard_append(self._copy_text)
        messagebox.showinfo(
            "PromptPainter",
            "Copied to the clipboard — paste it to your AI or into a"
            " document.",
            parent=self,
        )

    # --- Fixer AI manual buttons (GUI rework Phase 20) -------------------
    # Mirrors ApiImageGenPanel's own "Check API access" probe shape
    # (_probe_access/_arm_probe_poll/_poll_probe/_apply_probe_result,
    # GUI rework Phase 19) exactly — a background thread posts ONE
    # ("kind", "message") result onto a private queue, polled via
    # self.after(AI_POLL_MS, ...) so the network/browser call never
    # blocks the Tk event loop. ``kind`` is "ok" (the image was
    # overwritten), "gated" (PaidFeatureRequired / FixNotConfigured —
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

        self._fix_poll_job = self.after(gui.AI_POLL_MS, self._poll_fix)

    def _poll_fix(self) -> None:
        self._fix_poll_job = None
        if not self.winfo_exists():
            return  # closed mid-fix — the worker's message is moot
        try:
            msg = self._fix_q.get_nowait()
        except queue.Empty:
            self._arm_fix_poll()
            return
        which, result = msg
        self._apply_fix_result(which, result)

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


class BeforeAfterWindow(tk.Toplevel):
    """A BEFORE/AFTER viewer for one in-place tool job.

    SINGLE mode (one image) stacks its before + after with a **Restore**
    button; MULTI mode scrolls every changed image of the job with a
    **RESTORE ALL** button. The same viewer style as DocWindow's
    single-image prompt view (a double-click opens it). Themed like the
    app (skinned Toplevel + registered in ``THEME_TOPLEVELS`` so a
    Day/Night flip re-tints it, unregistered on ``<Destroy>``); every
    scaled PhotoImage is held on ``self._photos`` so tk cannot GC it.
    """

    def __init__(
        self, master, title, pairs, *, restore_label, restore_cb,
        subtitle=None,
    ):
        super().__init__(master)
        self.title(title)
        self.minsize(DOC_MIN_W, DOC_MIN_H)
        skin_toplevel(self)  # bg registered so a flip re-tints the window
        THEME_TOPLEVELS.append(self)
        self._restore_cb = restore_cb
        self._photos: list = []  # keep the PhotoImages alive

        width = min(
            int(self.winfo_screenwidth() * DOC_MAX_FRAC),
            max(BEFORE_AFTER_W, DOC_MIN_W),
        )
        height = min(
            max(int(self.winfo_screenheight() * DOC_HEIGHT_FRAC), DOC_MIN_H),
            int(self.winfo_screenheight() * DOC_MAX_FRAC),
        )
        self.geometry(f"{width}x{height}")

        bar = ttk.Frame(self, padding=6)
        bar.pack(fill="x")
        if subtitle is None:
            subtitle = (
                "Before / after — Restore reverts this image to the"
                " original." if len(pairs) == 1 else
                "Before / after of every changed image — RESTORE ALL"
                " reverts the whole job."
            )
        ttk.Label(bar, text=subtitle, style="Muted.TLabel").pack(side="left")
        self._restore_btn = rounded_button(
            bar, restore_label, command=self._do_restore, kind="danger",
        )
        self._restore_btn.pack(side="right")
        rounded_button(bar, "Close", command=self.destroy).pack(
            side="right", padx=4
        )

        self._scroll = ScrollFrame(self, horizontal=False)
        self._scroll.pack(fill="both", expand=True, padx=6, pady=(0, 6))
        avail = max(width - BEFORE_AFTER_IMG_PAD_PX, 320)
        self.update_idletasks()
        for pair in pairs:
            self._add_pair(pair, avail)

        self.bind("<Destroy>", self._on_destroy)

    def _add_pair(self, pair: dict, avail: int) -> None:
        block = ttk.Frame(self._scroll.body, padding=(4, 8))
        block.pack(fill="x", anchor="w")
        ttk.Label(block, text=pair["rel"], style="Head.TLabel").pack(
            anchor="w", pady=(0, 4)
        )
        for tag, path in (
            ("Before", pair["before"]), ("After", pair["after"])
        ):
            ttk.Label(block, text=tag, style="Muted.TLabel").pack(anchor="w")
            try:
                # composite over a checker so a cleared/transparent AFTER
                # reads as removed, not as the window colour
                photo = _scaled_photo(path, avail, on_checker=True)
            except OSError as exc:
                ttk.Label(
                    block, text=f"({tag} unreadable: {exc})"
                ).pack(anchor="w")
                continue
            self._photos.append(photo)
            lbl = ttk.Label(block, image=photo)
            lbl.image = photo  # belt-and-braces ref
            lbl.pack(anchor="w", pady=(0, 6))
        ttk.Separator(block).pack(fill="x", pady=(2, 0))

    def _do_restore(self) -> None:
        self._restore_cb()
        self._restore_btn.configure(state="disabled", text="Restored ✓")

    def apply_theme(self) -> None:
        # ttk children flip via styles; the toplevel + scroll canvas ride
        # the global recolour — nothing per-widget to redo here.
        pass

    def _on_destroy(self, event) -> None:
        if event.widget is self and self in THEME_TOPLEVELS:
            THEME_TOPLEVELS.remove(self)


def _filmstrip_stages(
    temp: "jobtemp.JobTemp", rel: str, live_path: Path,
) -> list[tuple[str, Path]]:
    """The ordered filmstrip ``StepRestoreWindow`` renders for one
    image (GUI rework Phase 9): one ``(label, path)`` pair per NAMED
    pipeline stage ``rel`` still holds a backup for — ``JobTemp.
    steps_for``'s own pipeline order (original -> bg -> crop -> aspect
    -> upscale -> fixer, filtered to whichever actually backed this
    rel up) — followed by exactly ONE final ``(STEP_RESTORE_CURRENT_
    LABEL, live_path)`` entry for the CURRENT live file.

    A caller that needs to know which JobTemp step name a 'Restore to
    here' button targets can zip ``stages[:-1]`` 1:1 against ``temp.
    steps_for(rel)`` — same order, same length; the filmstrip's own
    final entry has no step of its own (it already IS the live file,
    not a backup — see ``StepRestoreWindow._render``).

    Pure/Tk-free — no widget is touched, so a real (or a bare-bones
    fake exposing ``steps_for``/``before_path``) ``JobTemp`` is fully
    pytest-able headless, no display needed."""
    stages = [
        (JOBTEMP_STEP_LABEL[step], temp.before_path(rel, step=step))
        for step in temp.steps_for(rel)
    ]
    stages.append((STEP_RESTORE_CURRENT_LABEL, live_path))
    return stages


class StepRestoreWindow(tk.Toplevel):
    """The per-step restore filmstrip for ONE site-pipeline image (GUI
    rework Phase 9): every pipeline stage ``rel`` still holds a backup
    for, in order (Original -> BG -> Crop -> Aspect -> Upscale ->
    Fixer, whichever exist — see ``_filmstrip_stages``), each with its
    own **Restore to here** button, PLUS the CURRENT live file last (no
    button — it already IS the live state). Restoring calls ``JobTemp.
    restore_to(rel, step)`` and re-renders the filmstrip in place (the
    'Current' thumbnail and the remaining stage list update
    immediately from disk), then tells the caller via ``on_restored``
    so the dashboard row this viewer was opened from can re-read the
    now-restored file too (``DashPanel.refresh_image_row``).

    Non-modal, themed like ``BeforeAfterWindow`` (skinned Toplevel,
    registered in ``THEME_TOPLEVELS``, its scaled PhotoImages held on
    ``self._photos`` so tk cannot GC them) — a HORIZONTAL
    ``ScrollFrame`` instead of BeforeAfterWindow's stacked vertical
    one, since pipeline stages read left-to-right like a real
    filmstrip.
    """

    def __init__(
        self, master, title, temp: "jobtemp.JobTemp", rel: str,
        live_path: Path, *, on_restored: Callable[[], None] | None = None,
    ):
        super().__init__(master)
        self.title(title)
        self.minsize(DOC_MIN_W, DOC_MIN_H)
        skin_toplevel(self)  # bg registered so a flip re-tints the window
        THEME_TOPLEVELS.append(self)
        self._temp = temp
        self._rel = rel
        self._live_path = live_path
        self._on_restored = on_restored
        self._photos: list = []  # keep the PhotoImages alive

        width = min(
            int(self.winfo_screenwidth() * DOC_MAX_FRAC),
            max(STEP_RESTORE_W, DOC_MIN_W),
        )
        height = min(
            max(int(self.winfo_screenheight() * DOC_HEIGHT_FRAC), DOC_MIN_H),
            int(self.winfo_screenheight() * DOC_MAX_FRAC),
        )
        self.geometry(f"{width}x{height}")

        bar = ttk.Frame(self, padding=6)
        bar.pack(fill="x")
        ttk.Label(
            bar,
            text="Every kept pipeline stage for this image — 'Restore"
            " to here' reverts the LIVE file to that stage.",
            style="Muted.TLabel",
        ).pack(side="left")
        rounded_button(bar, "Close", command=self.destroy).pack(side="right")

        self._scroll = ScrollFrame(self, horizontal=True)
        self._scroll.pack(fill="both", expand=True, padx=6, pady=(0, 6))
        self.update_idletasks()
        self._render()

        self.bind("<Destroy>", self._on_destroy)

    def _render(self) -> None:
        """(Re)build every stage block from the CURRENT on-disk state —
        called at construction and again after each restore, so the
        'Current' thumbnail and the remaining restorable stages always
        match what is actually on disk right now."""
        for child in self._scroll.body.winfo_children():
            child.destroy()
        self._photos.clear()
        stages = _filmstrip_stages(self._temp, self._rel, self._live_path)
        steps = self._temp.steps_for(self._rel)  # same order/len as stages[:-1]
        for i, (label, path) in enumerate(stages):
            step = steps[i] if i < len(steps) else None
            block = ttk.Frame(self._scroll.body, padding=8)
            block.pack(side="left", fill="y", anchor="n")
            ttk.Label(block, text=label, style="Head.TLabel").pack(anchor="w")
            try:
                # composite over a checker so a transparent intermediate
                # (a BG-removed stage) reads as removed, not as the
                # window colour — same fix as BeforeAfterWindow's
                photo = _scaled_photo(
                    path, STEP_RESTORE_THUMB_PX, on_checker=True
                )
            except OSError as exc:
                ttk.Label(
                    block, text=f"(unreadable: {exc})",
                    wraplength=STEP_RESTORE_THUMB_PX,
                ).pack(anchor="w")
                continue
            self._photos.append(photo)
            ttk.Label(block, image=photo).pack(pady=(4, 6))
            if step is not None:
                rounded_button(
                    block, "Restore to here", kind="danger",
                    command=partial(self._do_restore, step),
                ).pack()
            else:
                ttk.Label(block, text="(current)", style="Muted.TLabel").pack()

    def _do_restore(self, step: str) -> None:
        if self._temp.restore_to(self._rel, step=step):
            self._render()
            if self._on_restored is not None:
                self._on_restored()

    def apply_theme(self) -> None:
        # ttk children flip via styles; the toplevel + scroll canvas ride
        # the global recolour — nothing per-widget to redo here (same as
        # BeforeAfterWindow).
        pass

    def _on_destroy(self, event) -> None:
        if event.widget is self and self in THEME_TOPLEVELS:
            THEME_TOPLEVELS.remove(self)
