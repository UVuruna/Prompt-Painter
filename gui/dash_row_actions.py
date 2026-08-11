"""What a selected dashboard ROW can open — the tree's row actions.

Split out of ``dash_panels.py`` (THE STRUCTURE LAW, owner 2026-08-11):
the live progress panel's job is to SHOW a run as it happens, while
these three are what the owner reaches for once a row is already
there — the image viewer (double-click), the per-step restore viewer
("Steps…") and the parallel Checker AI's per-row report ("Check…").
Different responsibility, different lifetime: they read finished state
off disk and open windows, they never touch the event stream.

``RowActionsMixin`` is mixed into ``DashPanel`` ahead of ``JobPanel``,
so it may rely on the panel's own attributes (``tree``, ``_node_info``,
``out_base``, ``slot_key``, ``_check_results``, ``_on_show`` …). It is
never instantiated alone.
"""

from __future__ import annotations

from functools import partial
from pathlib import Path, PurePosixPath
from tkinter import messagebox

from painter.config import dest_for

from .dash_helpers import ai_check_doc_md, ai_check_image_file


class RowActionsMixin:
    """The three row-opening actions of a dashboard tree row."""

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
        # the stored rel is the file that really got saved (a _vN
        # version for a ticked redo — owner 2026-07-27); dest_for is
        # only the fallback for rows without one (a REFUSED row)
        rel = info.get("rel") or dest_for(info["drop"], self.slot_key)
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
