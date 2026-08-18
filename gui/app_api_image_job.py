"""``ApiImageJobMixin`` — the paid-API image job (``_start_api_image``).

One of ``PainterGui``'s responsibility slices (see ``gui/app.py``). The
job that generates through the paid Gemini API instead of driving a
browser tab: it checks the panel's access gate, builds an
``ApiImageAdapter`` (a ``SiteDriver``-shaped stand-in whose
``extract_image`` makes the real ``ai.generate_image`` call), and hands
it to the SAME ``run_sheet`` loop the browser sites use — so pacing,
post-save, the dashboard and the report are one code path, not two.

Split from ``gui/app_jobs.py`` (audit
``docs/AUDIT-OOP-2026-08-18.md`` -> R5, the exact three-way split the
structure ratchet already named). It sits beside the site run loop
rather than inside it because the two share only ``run_sheet``: one
speaks CDP to a tab, this one speaks HTTP to an API, and neither
branches on the other.

No ``__init__`` here — every attribute it reads is set by
``BuildMixin.__init__``, and the site-loop helpers it calls
(``_compose_post_save``, ``_update_status``, ``_sync_running_state``)
resolve through the shared ``PainterGui`` MRO exactly as before.
"""

from __future__ import annotations

import threading
from dataclasses import replace
from tkinter import messagebox

from painter import jobtemp
from painter.config import (
    AI_IMAGE_GATE_MESSAGE,
    TIMING,
    prompt_suffix,
)

from .api_panel import ApiImageAdapter


class ApiImageJobMixin:
    """The paid-API image job. Mixed into ``PainterGui`` —
    never instantiated alone."""

    def _start_api_image(self) -> None:
        """Start on the API Image GEN panel (GUI rework Phase 19) — the
        SAME queued .md sheets Website GEN drives, generated through
        the paid Gemini image API instead of a browser tab. Reuses the
        proven SITE machinery almost verbatim: ``_drive_site`` (widened
        to accept an ``ApiImageAdapter`` in place of a ``SiteDriver``),
        ``_stop_events``/``_pause_events``/``_running``/``_workers``
        (the SAME dicts chatgpt/gemini use, keyed "api_image" — see
        ``__init__``'s own comment on ``_stop_events`` and
        ``_dispatch``'s ``__worker_done__`` guard for why nothing there
        needed forking), ``_compose_post_save`` (called with THIS
        panel, since it is not one of ``self.agents``). Only its OWN
        validation lives here — no per-site "New chat" or action-delay
        concept (the API has no DOM to hesitate on, no chat to open),
        and a gating check ``_start_site`` has no equivalent of."""
        if "api_image" in self._running:
            return
        if not self._sheets:
            messagebox.showerror("PromptPainter", "Add sheet .md files first.")
            return
        sheets = self._parse_all()
        if not sheets:
            messagebox.showerror(
                "PromptPainter", "No usable sheets in the queue."
            )
            return
        out_base = self._out_base()
        # NO containment check (owner decree 2026-08-14): the Output IS
        # the consuming project's root and its sheets live INSIDE it
        # (Watch Academy: shared/research/prompts/), so "the sheet is
        # under the output folder" is the NORMAL, correct setup — it
        # refused every real run. READ ONLY is guaranteed by what the
        # tool writes, not by where the sheet sits: image dests,
        # _state/, EXTRA/ and <stem>_report.txt. A .md is never a write
        # target.
        # NO rename demand (owner 2026-08-14) — same-named sheets are
        # disambiguated per queue (unique_report_stems), never refused.

        panel = self._tool_panels["api_image_gen"]
        if panel.access_gated:
            messagebox.showerror("PromptPainter", AI_IMAGE_GATE_MESSAGE)
            return
        if not self._ensure_ai_key():
            return
        pause_min, pause_max = panel.pace()  # the Polite pace switch
        if panel.upscale_var.get():
            try:
                up = panel.upscale_params()
            except ValueError:
                messagebox.showerror(
                    "PromptPainter",
                    "API Image GEN: Upscale-gate min side must be a"
                    " number, and every filter row must be a valid"
                    " number (FROM <= TO).",
                )
                return
            if up["min_width"] <= 0:
                messagebox.showerror(
                    "PromptPainter",
                    "API Image GEN: Upscale-gate min side must be"
                    " positive.",
                )
                return
        if panel.force_aspect_var.get():
            try:
                force_w, force_h = panel.force_aspect_ratio()
            except ValueError:
                messagebox.showerror(
                    "PromptPainter",
                    "API Image GEN: Force Aspect Ratio W/H must be whole"
                    " numbers.",
                )
                return
            if force_w <= 0 or force_h <= 0:
                messagebox.showerror(
                    "PromptPainter",
                    "API Image GEN: Force Aspect Ratio W/H must both be"
                    " positive.",
                )
                return

        timing = replace(TIMING, pause_min_s=pause_min, pause_max_s=pause_max)

        # this job's per-step backup store (mirrors _start_site's own
        # "clear the old slot first" rule)
        old_temp = self._job_temps.pop("api_image", None)
        if old_temp is not None:
            old_temp.clear()
        self._job_temps["api_image"] = jobtemp.JobTemp("api_image", out_base)

        post_save = self._compose_post_save("api_image", panel=panel)
        if isinstance(post_save, str):  # a deps problem, not a hook
            messagebox.showerror(
                "PromptPainter",
                f"{post_save}\n\n(or turn the API Image GEN BG removal /"
                " Crop / Upscale switches off)",
            )
            return

        # no Select-images ticking for this job (SelectWindow is still
        # per-SITE only — see gui.md) — every sheet resumes by FILE
        # EXISTENCE, sheet-advised items sit out, exactly like a site
        # whose Select window the owner never opened.
        selection: dict[str, set[str] | None] = {
            str(sheet.source): None for sheet in sheets
        }

        self._stop_events["api_image"].clear()
        if "api_image" in self._paused:
            self._toggle_pause_job("api_image")  # never start pre-paused
        self._running.add("api_image")
        panel.set_run_state(running=True)
        total, themes = self._plan("api_image", sheets, selection)
        dash = self.panels["api_image"]
        dash.jobtemp = self._job_temps["api_image"]
        dash.out_base = out_base
        dash.begin_run(task_total=total, task_themes=themes)  # F3: appends
        self._dashgrid.add("api_image")
        self._update_status()
        background = panel.background_var.get()
        style = panel.style_var.get()
        self._log(
            f"=== START api_image | {len(sheets)} sheet(s) -> {out_base}"
            f" | background: {background} | style: {style}"
            f" | bg_removal={panel.bg_removal_var.get()}"
            f" crop={panel.crop_var.get()}"
            f" force_aspect={panel.force_aspect_var.get()}"
            f" upscale={panel.upscale_var.get()} ==="
        )
        driver = ApiImageAdapter(
            log=lambda msg: self._q.put(f"[api_image]     {msg}")
        )
        worker = threading.Thread(
            target=self._drive_site,
            args=(
                "api_image",
                list(sheets),
                out_base,
                timing,
                driver,
                post_save,
                prompt_suffix("api_image", background, style=style),
                None,  # extra_suffix — no AI-checker re-send wiring yet
                panel.report_var.get(),
                selection,
                False,  # safer_retry — no ItemRefused path from this driver
                False,  # continue_nudge — no NoImage path from this driver
                "off",  # new_chat — no chat to open; NEW_CHAT_CHOICES value
                self._stop_events["api_image"],
                self._pause_events["api_image"],
            ),
            kwargs={
                # PROMPT + IMAGE mode (faza 2): the API run honours the
                # SAME section — one mode, every generator
                "reference_dir": self._pi_section.reference_dir(),
                "require_input_image": self._pi_section.enabled(),
            },
            daemon=True,
        )
        self._workers["api_image"] = worker
        worker.start()
        self._inline_kind = None
        self._sync_running_state()
