"""``ImageViewer`` — the PORTRAIT per-image dashboard viewer (GUI
rework Phase F4f, owner G6/G7: Prev/Next/Delete over one image, its
prompt, its AI check and its pipeline steps). Root Rule #20 god-file
split of ``gui/viewers.py``, 2026-07-30.

It replaces ``DocWindow`` for IMAGE-level dashboard rows only — sheet-
and folder-level rows still open ``gui.doc_window.DocWindow``. See the
class docstring for the lookup callbacks ``gui.app_settings`` wires
into it.
"""

from __future__ import annotations

import tkinter as tk
from functools import partial
from pathlib import Path
from tkinter import messagebox, ttk
from typing import Callable

from .dash_helpers import _scaled_photo, ai_check_doc_md
from .scroll import ScrollFrame
from .theme import THEME_TOPLEVELS, skin_text, skin_toplevel
from .viewer_shared import (
    DOC_MAX_FRAC,
    _copy_to_clipboard,
    _readonly_text_keys,
)
from .widgets import rounded_button, tk_font

# --- Per-image dashboard viewer (GUI rework Phase F4f) -----------------
# PORTRAIT (taller than wide, unlike every other viewer here) — sized so
# Row 1's three buttons (Prev/Next/Delete) are never cut off, clamped to
# the screen like every other DOC_*-family window.
IMAGE_VIEWER_W = 640
IMAGE_VIEWER_H = 920
IMAGE_VIEWER_MIN_W = 420      # Row 1's three buttons + padding fit well inside
IMAGE_VIEWER_MIN_H = 560
IMAGE_VIEWER_IMG_PAD_PX = 40  # horizontal padding around the main image
IMAGE_VIEWER_THUMB_PX = 96    # the Steps filmstrip's own thumbnail size


class ImageViewer(tk.Toplevel):
    """The per-image dashboard viewer (GUI rework Phase F4f, owner
    G6/G7) — replaces ``DocWindow`` ONLY for IMAGE-level dashboard rows
    (sheet/folder rows keep ``DocWindow`` unchanged, see
    ``gui.app_settings.SettingsMixin._show_node``). PORTRAIT (taller
    than wide), sized so Row 1's three buttons are never cut off.

    Layout top -> bottom: ROW 1 (Prev/Next left, Delete right) — always
    visible, outside the scroll area, so the buttons can never scroll
    out of reach; ROW 2 the image's own NAME (its saved file's stem,
    never the full drop path); then, inside one vertical
    ``ScrollFrame``, the main image (or the refusal/missing reason when
    there is no file), the prompt in a read-only monospace block with
    its own 'Copy (for AI)', and two EXPANDABLE sub-sections styled as
    an ▶/▼ sub-title (the ``rounded_button(kind="expander")`` idiom
    ``DashPanel``'s own 'Average' group already uses — the AgentPanel
    Settings-gear IDIOM, not literally its gear icon) — 'Check' and
    'Steps', each entirely ABSENT (not merely collapsed) when its
    lookup has nothing for the current entry.

    Prev/Next walk an ORDERED list of plain-dict ``entries`` — the
    whole collection/folder context the viewer was opened from — IN
    ONE window (no new Toplevels): ``title``, ``drop_path`` (the
    sheet's site-agnostic path), ``rel`` (the actual saved rel, or
    None), ``dest`` (the absolute saved Path, or None — nothing on
    disk), ``prompt`` and ``refused_reason`` (shown where the image
    would be when ``dest`` is None). Buttons disable at the ends (no
    wraparound).

    ``check_lookup(drop_path) -> dict | None`` and ``steps_lookup(rel)
    -> list[(label, Path)]`` are OPTIONAL read callables the caller
    builds from a live ``DashPanel``'s ``_check_results``/``jobtemp``
    (None when not opened from a live dashboard run) — either
    missing, or returning None/empty for the current entry, removes
    its whole section. ``check_lookup`` renders the SAME text
    ``DashPanel._show_check`` already shows (``ai_check_doc_md``).
    ``steps_lookup``'s pairs render as a HORIZONTAL ~``
    IMAGE_VIEWER_THUMB_PX``-px filmstrip (``StepRestoreWindow``'s own
    idiom); clicking one swaps the MAIN image view to that file (a
    'viewing: <label>' note plus a 'Back to current' link).

    ``restore_cb(rel, label) -> bool`` and ``on_restored(entry)`` are a
    DELIBERATE ADDITION beyond the spec's literal ``steps_lookup``
    2-tuple contract (documented here, not silently): actually
    restoring a step needs the raw ``JobTemp`` step key and a
    ``JobTemp`` instance, neither of which travels through a bare
    ``(label, Path)`` display pair — see ``gui/viewers.md``'s Design
    Decisions. The restore call itself REUSES ``_restore_step`` (Rule
    #5) — the exact call ``StepRestoreWindow._do_restore`` also makes,
    so this widget never re-implements ``JobTemp.restore_to``.

    ``on_deleted(entry)`` fires after Delete removes exactly the
    CURRENTLY DISPLAYED version file from disk (never a Step preview —
    Delete always targets ``entry['dest']``, confirmed in the dialog
    text) and the viewer advances to the next entry, or closes when
    there is none left.
    """

    def __init__(
        self, master, entries: list[dict], index: int, *,
        check_lookup: Callable[[str], dict | None] | None = None,
        steps_lookup: Callable[[str], list[tuple[str, Path]]] | None = None,
        restore_cb: Callable[[str, str], bool] | None = None,
        on_restored: Callable[[dict], None] | None = None,
        on_deleted: Callable[[dict], None] | None = None,
    ):
        if not entries:
            raise ValueError("ImageViewer needs at least one entry")
        super().__init__(master)
        self._entries = entries
        self._index = max(0, min(index, len(entries) - 1))
        self._check_lookup = check_lookup
        self._steps_lookup = steps_lookup
        self._restore_cb = restore_cb
        self._on_restored = on_restored
        self._on_deleted = on_deleted

        self._img_ref = None            # keeps the main PhotoImage alive
        self._step_photos: list = []    # keeps the filmstrip thumbnails alive
        self._view_step: tuple[str, Path] | None = None  # step preview override
        self._current_stages: list[tuple[str, Path]] = []
        self._check_open = False
        self._steps_open = False

        self.minsize(IMAGE_VIEWER_MIN_W, IMAGE_VIEWER_MIN_H)
        skin_toplevel(self)  # bg registered so a flip re-tints the window
        THEME_TOPLEVELS.append(self)

        width = min(
            IMAGE_VIEWER_W, int(self.winfo_screenwidth() * DOC_MAX_FRAC)
        )
        height = min(
            IMAGE_VIEWER_H, int(self.winfo_screenheight() * DOC_MAX_FRAC)
        )
        self.geometry(f"{width}x{height}")
        self._img_avail = max(width - IMAGE_VIEWER_IMG_PAD_PX, 240)

        self._build_nav_row()
        self._title_var = tk.StringVar()
        ttk.Label(
            self, textvariable=self._title_var, style="Head.TLabel",
        ).pack(fill="x", padx=10, pady=(0, 4), anchor="w")

        self._scroll = ScrollFrame(self, horizontal=False)
        self._scroll.pack(fill="both", expand=True, padx=6, pady=(0, 6))
        body = self._scroll.body

        self._build_image_block(body)
        self._build_prompt_block(body)
        ttk.Separator(body).pack(fill="x", pady=8)
        self._build_check_section(body)
        self._build_steps_section(body)

        self.bind("<Destroy>", self._on_destroy)
        self._render_entry()

    # --- construction ----------------------------------------------------

    def _build_nav_row(self) -> None:
        nav = ttk.Frame(self, padding=6)
        nav.pack(fill="x")
        self._prev_btn = rounded_button(nav, "◀ Prev", icon_name="back", command=self._go_prev)
        self._prev_btn.pack(side="left")
        self._next_btn = rounded_button(nav, "Next ▶", icon_name="next", command=self._go_next)
        self._next_btn.pack(side="left", padx=(6, 0))
        self._delete_btn = rounded_button(
            nav, "Delete", icon_name="delete", command=self._delete_current, kind="danger",
        )
        self._delete_btn.pack(side="right")

    def _build_image_block(self, body) -> None:
        self._image_block = ttk.Frame(body)
        self._image_block.pack(fill="x")
        self._image_label = ttk.Label(self._image_block)
        self._image_label.pack(pady=(4, 2))
        # only packed while a Steps thumbnail overrides the main view —
        # unpacked (never destroyed) the rest of the time
        self._step_note_var = tk.StringVar(value="")
        self._step_note = ttk.Label(
            self._image_block, textvariable=self._step_note_var,
            style="Muted.TLabel",
        )
        self._back_btn = rounded_button(
            self._image_block, "Back to current", kind="link",
            icon_name="back", command=self._clear_step_view,
        )

    def _build_prompt_block(self, body) -> None:
        bar = ttk.Frame(body)
        bar.pack(fill="x", pady=(6, 2))
        ttk.Label(bar, text="Prompt", style="Head.TLabel").pack(side="left")
        rounded_button(
            bar, "Copy (for AI)", command=self._copy_prompt, kind="info",
            icon_name="copy",
        ).pack(side="right")
        self._prompt_txt = tk.Text(
            body, wrap="word", font=tk_font("mono"), height=8, width=1,
            padx=10, pady=8, cursor="arrow",
        )
        skin_text(self._prompt_txt)
        self._prompt_txt.pack(fill="x")
        self._prompt_txt.bind("<Key>", _readonly_text_keys)

    def _build_check_section(self, body) -> None:
        # the OUTER frame stays packed for the viewer's whole lifetime
        # (fixes this section's vertical SLOT once, before Steps') — only
        # its two children (the expander button + its body) toggle
        # pack/pack_forget per entry, so entry-to-entry presence changes
        # can never re-order Check relative to Steps.
        self._check_frame = ttk.Frame(body)
        self._check_frame.pack(fill="x")
        self._check_btn = rounded_button(
            self._check_frame, "", command=self._toggle_check,
            kind="expander",
        )
        self._check_body = ttk.Frame(
            self._check_frame, padding=(16, 4, 4, 4)
        )
        self._check_txt = tk.Text(
            self._check_body, wrap="word", font=tk_font("mono"), height=8,
            width=1, padx=10, pady=8, cursor="arrow",
        )
        skin_text(self._check_txt)
        self._check_txt.pack(fill="both", expand=True)
        self._check_txt.bind("<Key>", _readonly_text_keys)

    def _build_steps_section(self, body) -> None:
        self._steps_frame = ttk.Frame(body)
        self._steps_frame.pack(fill="x")
        self._steps_btn = rounded_button(
            self._steps_frame, "", command=self._toggle_steps,
            kind="expander",
        )
        self._steps_body = ttk.Frame(
            self._steps_frame, padding=(16, 4, 4, 4)
        )
        self._steps_scroll = ScrollFrame(self._steps_body, horizontal=True)
        self._steps_scroll.pack(fill="x")

    # --- per-entry render --------------------------------------------------

    def _render_entry(self) -> None:
        self._view_step = None
        self._update_title()
        self._update_nav_buttons()
        self._update_delete_button()
        self._render_image()
        self._render_prompt()
        self._refresh_check_section()
        self._refresh_steps_section()
        self._scroll.refresh()

    def _current(self) -> dict:
        return self._entries[self._index]

    def _update_title(self) -> None:
        entry = self._current()
        dest = entry.get("dest")
        stem = (
            Path(dest).stem if dest is not None
            else Path(entry["drop_path"]).stem
        )
        self._title_var.set(stem)
        self.title(stem)

    def _update_nav_buttons(self) -> None:
        self._prev_btn.configure(
            state="normal" if self._index > 0 else "disabled"
        )
        self._next_btn.configure(
            state="normal" if self._index < len(self._entries) - 1
            else "disabled"
        )

    def _update_delete_button(self) -> None:
        self._delete_btn.configure(
            state="normal" if self._current().get("dest") is not None
            else "disabled"
        )

    def _render_image(self) -> None:
        entry = self._current()
        if self._view_step is not None:
            label, path = self._view_step
            self._step_note_var.set(f"viewing: {label}")
            self._step_note.pack(anchor="w", padx=4)
            self._back_btn.pack(anchor="w", padx=4, pady=(0, 4))
            self._show_image_file(path)
            return
        self._step_note.pack_forget()
        self._back_btn.pack_forget()
        self._step_note_var.set("")
        dest = entry.get("dest")
        if dest is not None:
            self._show_image_file(dest)
        else:
            self._img_ref = None
            self._image_label.configure(
                image="",
                text=entry.get("refused_reason") or "No saved image.",
            )

    def _show_image_file(self, path: Path) -> None:
        try:
            self._img_ref = _scaled_photo(path, self._img_avail)
        except OSError as exc:
            self._img_ref = None
            self._image_label.configure(
                image="", text=f"(image unreadable: {exc})"
            )
            return
        self._image_label.configure(image=self._img_ref, text="")

    def _render_prompt(self) -> None:
        self._prompt_txt.configure(state="normal")
        self._prompt_txt.delete("1.0", "end")
        self._prompt_txt.insert("1.0", self._current().get("prompt", ""))
        self._prompt_txt.configure(state="disabled")

    def _copy_prompt(self) -> None:
        _copy_to_clipboard(self, self._current().get("prompt", ""))

    # --- Check sub-section -------------------------------------------------

    def _refresh_check_section(self) -> None:
        entry = self._current()
        result = (
            self._check_lookup(entry["drop_path"])
            if self._check_lookup is not None else None
        )
        if result is None:
            self._check_btn.pack_forget()
            self._check_body.pack_forget()
            return
        rel_for_md = result.get("rel") or entry.get("rel") or entry["drop_path"]
        md = ai_check_doc_md(rel_for_md, result.get("defects"), result.get("raw"))
        self._check_txt.configure(state="normal")
        self._check_txt.delete("1.0", "end")
        self._check_txt.insert("1.0", md)
        self._check_txt.configure(state="disabled")
        self._render_check_btn()
        self._check_btn.pack(fill="x")
        if self._check_open:
            self._check_body.pack(fill="x")
        else:
            self._check_body.pack_forget()

    def _render_check_btn(self) -> None:
        self._check_btn.configure(
            text="▼  Check" if self._check_open else "▶  Check"
        )

    def _toggle_check(self) -> None:
        self._check_open = not self._check_open
        self._render_check_btn()
        if self._check_open:
            self._check_body.pack(fill="x")
        else:
            self._check_body.pack_forget()
        self._scroll.refresh()

    # --- Steps sub-section ---------------------------------------------

    def _refresh_steps_section(self) -> None:
        entry = self._current()
        stages: list[tuple[str, Path]] = []
        rel = entry.get("rel")
        if self._steps_lookup is not None and rel:
            stages = list(self._steps_lookup(rel) or [])
        self._current_stages = stages
        if not stages:
            self._steps_btn.pack_forget()
            self._steps_body.pack_forget()
            return
        self._render_steps_btn()
        self._build_steps_strip()
        self._steps_btn.pack(fill="x")
        if self._steps_open:
            self._steps_body.pack(fill="x")
        else:
            self._steps_body.pack_forget()

    def _render_steps_btn(self) -> None:
        arrow = "▼" if self._steps_open else "▶"
        self._steps_btn.configure(
            text=f"{arrow}  Steps ({len(self._current_stages)})"
        )

    def _toggle_steps(self) -> None:
        self._steps_open = not self._steps_open
        self._render_steps_btn()
        if self._steps_open:
            self._steps_body.pack(fill="x")
        else:
            self._steps_body.pack_forget()
        self._scroll.refresh()

    def _build_steps_strip(self) -> None:
        for child in self._steps_scroll.body.winfo_children():
            child.destroy()
        self._step_photos.clear()
        for label, path in self._current_stages:
            block = ttk.Frame(self._steps_scroll.body, padding=6)
            block.pack(side="left", fill="y", anchor="n")
            ttk.Label(block, text=label, style="Muted.TLabel").pack()
            try:
                # composite over a checker so a transparent intermediate
                # (a BG-removed stage) reads as removed, not as the
                # window colour — same fix as StepRestoreWindow's own
                photo = _scaled_photo(
                    path, IMAGE_VIEWER_THUMB_PX, on_checker=True
                )
            except OSError as exc:
                ttk.Label(
                    block, text=f"(unreadable: {exc})",
                    wraplength=IMAGE_VIEWER_THUMB_PX,
                ).pack()
                continue
            self._step_photos.append(photo)
            thumb = ttk.Label(block, image=photo, cursor="hand2")
            thumb.pack(pady=(2, 2))
            thumb.bind("<Button-1>", partial(self._view_step_thumb, label, path))
            if self._restore_cb is not None:
                rounded_button(
                    block, "Restore to this step", kind="danger",
                    icon_name="restore", command=partial(self._restore_this_step, label),
                ).pack()

    def _view_step_thumb(self, label: str, path: Path, _event=None) -> None:
        self._view_step = (label, path)
        self._render_image()
        self._scroll.refresh()

    def _clear_step_view(self) -> None:
        self._view_step = None
        self._render_image()
        self._scroll.refresh()

    def _restore_this_step(self, label: str) -> None:
        entry = self._current()
        rel = entry.get("rel")
        if rel is None or self._restore_cb is None:
            return
        if self._restore_cb(rel, label):
            self._render_entry()  # the live file changed on disk
            if self._on_restored is not None:
                self._on_restored(entry)

    # --- nav / delete ----------------------------------------------------

    def _go_prev(self) -> None:
        if self._index > 0:
            self._index -= 1
            self._render_entry()

    def _go_next(self) -> None:
        if self._index < len(self._entries) - 1:
            self._index += 1
            self._render_entry()

    def _delete_current(self) -> None:
        entry = self._current()
        dest = entry.get("dest")
        if dest is None:
            return
        if not messagebox.askyesno(
            "Delete image",
            "Delete the SAVED image file for this entry?\n\n"
            f"{dest}\n\n"
            "This targets the currently SAVED version on disk — even"
            " when you are previewing a Steps thumbnail above, Delete"
            " removes the saved file itself, never a pipeline-step"
            " backup.",
            parent=self,
        ):
            return
        try:
            dest.unlink()
        except OSError as exc:
            messagebox.showerror(
                "PromptPainter", f"Could not delete {dest}: {exc}"
            )
            return
        entry["dest"] = None
        entry["rel"] = None
        entry["refused_reason"] = "Deleted from the viewer."
        if self._on_deleted is not None:
            self._on_deleted(entry)
        if self._index < len(self._entries) - 1:
            self._index += 1
            self._render_entry()
        else:
            self.destroy()

    # --- theme / lifecycle -------------------------------------------------

    def apply_theme(self) -> None:
        # ttk children flip via styles; the plain-tk Texts were built via
        # skin_text and re-tint from the registry on their own — nothing
        # per-widget to redo here (same as BeforeAfterWindow/
        # StepRestoreWindow).
        pass

    def _on_destroy(self, event) -> None:
        if event.widget is self and self in THEME_TOPLEVELS:
            THEME_TOPLEVELS.remove(self)
