"""SiteJobsMixin — Website GEN / API Image GEN run loop + dashboard glue.

Godfile refactor step 8/8 (see gui/___gui.md): one of PainterGui's six
mixins (see gui/app.py). Owns the two browser-driven SITE jobs plus the
paid-API image job (``_start_site``/``_start_api_image``/``_drive_site``/
``_stop_site``), the shared queue-message pump (``_drain_queue``/
``_dispatch``), the per-job Pause toggle (``_toggle_pause_job``) and
dashboard-panel close (``_close_panel``/``_tool_panel_key``), the quota
auto-restart timers, and the post-save pipeline composer
(``_compose_post_save``). No ``__init__`` here — every attribute it
reads is set by ``BuildMixin.__init__``.

The Checker AI and Fixer AI (auto-dispatch half plus the manual
fix-worker builders) used to live in this file too — this module had
grown past the ~1000-line Rule #20 budget, so they moved out to
``gui/app_checker_fixer.py``'s ``CheckerFixerMixin`` (see that module's
own docstring). ``_dispatch`` below still calls
``self._maybe_spawn_checker``/``self._maybe_spawn_fixer`` exactly as
before — both resolve through the shared ``PainterGui`` MRO onto that
sibling mixin, so nothing here changed behaviorally.

``_compose_post_save``'s ``post_save`` closure reaches ``_gate_and_
upscale`` (gui/logic.py) through a deferred ``import gui`` (the SAME
late-binding idiom already used in gui/dash_panels.py, gui/viewers.py,
gui/tool_dash.py and gui/api_panel.py) so that
tests/test_gui_pipeline.py's ``monkeypatch.setattr(gui,
"_gate_and_upscale", ...)`` reaches the call actually made here, instead
of a module-level copy frozen at import time.
"""

from __future__ import annotations

import queue
import random
import threading
import time
from dataclasses import replace
from functools import partial
from pathlib import Path
from tkinter import messagebox
from typing import Callable

from painter import aspect, jobtemp
from painter.config import (
    AI_IMAGE_GATE_MESSAGE,
    CDP_URL,
    SITES,
    TIMING,
    prompt_suffix,
    tile_for_kind,
)
from .api_panel import ApiImageAdapter
from .logic import _run_pipeline_steps


class SiteJobsMixin:
    """The site/API-image run loop, dashboard dispatch, quota
    auto-restart, Checker AI and Fixer AI."""

    def _close_panel(self, kind: str) -> None:
        """A finished panel's CLOSE button: remove it from the grid and
        clear that job's temp backups (any kind — a tool or, since GUI
        rework Phase 8, a gen site's own per-step pipeline backups). The
        panel widget survives (build-once) — reset_finished hides its
        CLOSE for the next run, and the next Start re-adds it."""
        self._dashgrid.remove(kind)
        self.panels[kind].reset_finished()
        temp = self._job_temps.pop(kind, None)
        if temp is not None:
            temp.clear()

    def _tool_panel_key(self, kind: str) -> str | None:
        """The ``_tool_panels`` dict key that owns ``kind``'s
        persistent settings panel, or None when ``kind`` has none
        (chatgpt/gemini use ``_controls_box`` instead — a DIFFERENT
        inline surface, see ``_toggle_pause_job``'s own "website_gen"
        special case). Identical to ``kind`` for the four standalone
        tools (tile id == slot, so ``config.tile_for_kind`` simply
        returns its own input back) and ``"image_checker"`` for
        ``"aicheck"`` (GUI rework Phase 15 — the one job kind whose
        MENU_TILES id differs from its JOB_ORDER slot). Central so a
        future standalone job kind never needs a new branch in
        ``_toggle_pause_job``/``_dispatch`` below, only a
        ``TILE_JOB_KINDS`` data entry."""
        tile_id = tile_for_kind(kind)
        return tile_id if tile_id in self._tool_panels else None

    def _toggle_pause_job(self, kind: str) -> None:
        """Flip ONE job's pause toggle (owner 2026-07-21) — the SAME
        handler wired to every job kind's btn_pause: AgentPanel's own
        (chatgpt/gemini) and ToolPanel's/AiCheckPanel's own (bg/crop/
        upscale/aspect/aicheck). Sets/clears this kind's
        threading.Event, polled by the runner (run_sheet's
        should_pause) or a tool/AI-check worker loop between items/
        images (painter.runner.wait_while_paused) — a Stop always wins
        over a pending pause (should_stop is re-checked on every poll
        tick, and _stop_site / the __worker_done__/__tool_done__
        handlers clear any leftover pause so a finished or freshly
        started job is never silently pre-paused). Reflects the new
        state onto every panel that shows this kind: the AgentPanel
        button for a site AND its DashPanel state line (JobPanel base),
        or the ToolPanel/AiCheckPanel button + state line (the same
        widget) for the other five kinds."""
        is_paused = kind not in self._paused
        if is_paused:
            self._paused.add(kind)
            self._pause_events[kind].set()
        else:
            self._paused.discard(kind)
            self._pause_events[kind].clear()
        if kind in self.agents:
            self.agents[kind].set_paused(is_paused)
        self.panels[kind].set_paused(is_paused)
        panel_key = self._tool_panel_key(kind)
        if panel_key is not None:
            # GUI rework Phase 13/15: keep the persistent panel's OWN
            # Pause/Resume label in sync too — it may be the panel the
            # very next line reveals (see below), or already hidden
            # (the owner navigated elsewhere) and simply catching up
            # for whenever it is opened again.
            self._tool_panels[panel_key].set_paused(is_paused)
        self._log(f"[{kind}] {'paused' if is_paused else 'resumed'}")
        # GUI rework Phase 11 (spec item 4): Pause RETURNS the settings
        # panel "for future tasks" — website_gen (chatgpt/gemini) shows
        # the shared _controls_box; every standalone job (bg/crop, GUI
        # rework Phase 13; upscale/aspect, Phase 14; the AI checker,
        # Phase 15) shows its OWN ToolSettingsPanel via _tool_panels,
        # the same way _open_tool_panel does — _tool_panel_key bridges
        # the AI checker's "aicheck" slot to its "image_checker" tile-
        # id key (see that method). Resuming never hides a revealed
        # panel back — only a fresh Start or the owner's own icon-bar
        # toggle does that.
        if is_paused and self._view == "running":
            if kind in ("chatgpt", "gemini"):
                self._inline_kind = "website_gen"
                self._apply_running_layout()
            elif panel_key is not None:
                self._inline_kind = panel_key
                self._apply_running_layout()

    def _compose_post_save(self, key: str, panel=None):
        """The job's post-save hook per ITS panel switches — the same
        shape the CLI builds: ``post_save(path) -> "REMOVE BG: done,
        CROP: done, ASPECT: done, ..."`` (the runner logs the
        description and guards the call itself — a failing step never
        kills the run). Returns None when every switch is off, or the
        deps-problem string when the steps cannot run at all.

        GUI rework Phase 8: the pipeline order is BG -> Crop ->
        Aspect(force) -> Upscale (``_run_pipeline_steps`` runs whichever
        of those four are enabled, in that fixed order — never
        reordered by which switches happen to be on); with Force Aspect
        OFF (its default) this is BYTE-IDENTICAL to the pre-Phase-8
        pipeline — the new per-step JobTemp backups only ever COPY
        bytes elsewhere, they never touch ``path`` itself, so the final
        saved image is unaffected either way.

        ``panel`` (GUI rework Phase 19, optional): the caller's own
        panel object when it is not one of ``self.agents`` — the API
        Image GEN job's ``ApiImageGenPanel`` lives in ``_tool_panels``
        instead (see ``_start_api_image``), but exposes the EXACT same
        bg_removal_var/crop_var/force_aspect_var/upscale_var/
        upscale_params()/upscale_conditions()/force_aspect_ratio()/
        keep_all_steps_var surface, so this whole method is reused
        UNCHANGED rather than duplicated (Rule #5). ``None`` (every
        existing chatgpt/gemini caller) keeps the exact old lookup."""
        panel = panel if panel is not None else self.agents[key]
        do_bg = panel.bg_removal_var.get()
        do_crop = panel.crop_var.get()
        do_aspect = panel.force_aspect_var.get()
        do_upscale = panel.upscale_var.get()
        if not (do_bg or do_crop or do_aspect or do_upscale):
            return None

        from painter.postprocess import deps_error

        problem = deps_error()
        if problem:
            return problem

        # this agent's upscale-gate kwargs AND its full filter stack, read
        # ONCE at Start (like the pace values) — validated by the caller
        # before we get here. Both are needed: up_params is the simple
        # min-side/aspect kwargs upscale_if_small takes; up_conditions is
        # the FULL stack (aspect AND any stacked Width/Height/Any-side
        # rows), checked via _gate_and_upscale so nothing is silently
        # dropped (root Rule #1 — see _upscale_params_from_side_and_filter).
        up_params = panel.upscale_params() if do_upscale else {}
        up_conditions = panel.upscale_conditions() if do_upscale else []
        # the Force-Aspect target ratio, read ONCE the same way — already
        # validated by the caller's Start checks (see _start_site)
        force_w, force_h = panel.force_aspect_ratio() if do_aspect else (0, 0)
        keep_all_steps = panel.keep_all_steps_var.get()
        log = lambda msg: self._q.put(f"[{key}]     {msg}")
        # this site's JobTemp, created by _start_site right before this
        # method runs (None only in a headless/test caller that never
        # went through _start_site — _run_pipeline_steps treats that as
        # "no backups", the pipeline steps themselves still run normally)
        temp = self._job_temps.get(key)
        emit = lambda ev: self._q.put(("__event__", key, ev))
        cap_warned = False  # the ONE loud banner per Start, never per image

        def on_cap() -> None:
            nonlocal cap_warned
            if not cap_warned:
                cap_warned = True
                emit({"type": "over_cap"})

        def post_save(path: Path) -> str:
            from painter.postprocess import (
                crop_transparent,
                remove_background,
            )

            # deferred import (see module docstring) — reaches the
            # function tests monkeypatch through the gui package object
            import gui

            steps: list[tuple[str, str, Callable[[Path], str]]] = []
            if do_bg:
                steps.append(
                    ("REMOVE BG", "bg", lambda p: remove_background(p, log))
                )
            if do_crop:
                steps.append(
                    ("CROP", "crop", lambda p: crop_transparent(p, log))
                )
            if do_aspect:
                steps.append((
                    "ASPECT", "aspect",
                    lambda p: aspect.change_aspect(p, force_w, force_h, log),
                ))
            if do_upscale:
                steps.append((
                    "UPSCALE", "upscale",
                    lambda p: gui._gate_and_upscale(
                        p, log, up_conditions, up_params
                    ),
                ))
            return _run_pipeline_steps(
                path, steps, temp, keep_all_steps, on_cap,
            )

        return post_save

    def _start_site(
        self,
        key: str,
        override_selection: dict[str, set[str]] | None = None,
        extra_suffix: dict[str, str] | None = None,
    ) -> None:
        """Start ONE site — the other site's run is never touched.

        ``override_selection`` (the AI checker's re-send, owner
        2026-07-20) replaces the Select-window ticks with an explicit
        per-sheet drop-path set and narrows the run to EXACTLY those
        sheets; ``extra_suffix`` rides along to the runner so each
        re-sent item carries its fix note. The plain Start (buttons,
        quota auto-restart) passes neither.
        """
        if key in self._running:
            return
        self._cancel_restart(key)  # a manual Start beats the timer
        if not self._sheets:
            messagebox.showerror("PromptPainter", "Add sheet .md files first.")
            return
        sheets = self._parse_all()
        if override_selection is not None:
            # the re-send drives ONLY the sheets carrying flagged items
            sheets = [
                s for s in sheets if str(s.source) in override_selection
            ]
        if not sheets:
            messagebox.showerror(
                "PromptPainter", "No usable sheets in the queue."
            )
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

        panel = self.agents[key]
        try:
            pause_min, pause_max, act_min, act_max = panel.pace_floats()
        except ValueError:
            messagebox.showerror(
                "PromptPainter",
                f"{SITES[key].name}: pause/delay must be numbers.",
            )
            return
        if pause_min > pause_max or act_min > act_max:
            messagebox.showerror(
                "PromptPainter",
                f"{SITES[key].name}: FROM must be <= TO (pause and delay).",
            )
            return
        if panel.upscale_var.get():
            try:
                up = panel.upscale_params()
            except ValueError:
                messagebox.showerror(
                    "PromptPainter",
                    f"{SITES[key].name}: Upscale-gate min side must be a"
                    " number, and every filter row must be a valid"
                    " number (FROM <= TO).",
                )
                return
            if up["min_width"] <= 0:
                messagebox.showerror(
                    "PromptPainter",
                    f"{SITES[key].name}: Upscale-gate min side must be"
                    " positive.",
                )
                return
            # NOTE: no aspect_min/aspect_max positivity/ordering check
            # here (GUI rework Phase 6) — aspect_min=0/aspect_max=inf is
            # now a VALID "no aspect condition" state (see
            # _upscale_params_from_side_and_filter), and lo <= hi is
            # already guaranteed by FilterEditor's own row validation
            # (_FilterConditionRow.to_condition raises before a row with
            # FROM > TO can ever reach get_conditions()) — the old
            # ordering check is unreachable dead code once that upstream
            # guarantee holds, so it is intentionally not reproduced here.
        if panel.force_aspect_var.get():
            try:
                force_w, force_h = panel.force_aspect_ratio()
            except ValueError:
                messagebox.showerror(
                    "PromptPainter",
                    f"{SITES[key].name}: Force Aspect Ratio W/H must be"
                    " whole numbers.",
                )
                return
            if force_w <= 0 or force_h <= 0:
                messagebox.showerror(
                    "PromptPainter",
                    f"{SITES[key].name}: Force Aspect Ratio W/H must"
                    " both be positive.",
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

        # this site's per-step backup store (GUI rework Phase 8) — a
        # restart while a previous run's panel is still on screen must
        # not inherit its old backups; mirrors _launch_tool_worker's own
        # "clear the old slot first" rule for the four standalone tools.
        # Created here (BEFORE _compose_post_save reads it) so the
        # composed post_save closure captures the temp for this run.
        old_temp = self._job_temps.pop(key, None)
        if old_temp is not None:
            old_temp.clear()
        self._job_temps[key] = jobtemp.JobTemp(key, out_base)

        post_save = self._compose_post_save(key)
        if isinstance(post_save, str):  # a deps problem, not a hook
            messagebox.showerror(
                "PromptPainter",
                f"{post_save}\n\n(or turn the {SITES[key].name}"
                " BG removal / Crop / Upscale switches off)",
            )
            return

        # this site's ticked selection, read in the tk thread: per
        # sheet -> the drop paths to run. None means "the owner never
        # opened Select for this theme+site" (so the runner applies the
        # default advice rule). Once Select has been opened, the ticks
        # are authoritative — including ticked advice items — so we pass
        # the explicit set, never collapsing "all ticked" back to None.
        # An AI re-send bypasses the ticks entirely: its explicit
        # per-sheet sets ARE the selection (the regenerate path).
        selection: dict[str, set[str] | None]
        if override_selection is not None:
            selection = dict(override_selection)
        else:
            selection = {}
            for sheet in sheets:
                src = str(sheet.source)
                touched = any(
                    site == key and source == src
                    for (site, source, _drop) in self._select_vars
                )
                if touched:
                    selection[src] = {
                        drop
                        for (site, source, drop), var
                        in self._select_vars.items()
                        if site == key and source == src and var.get()
                    }
                else:
                    selection[src] = None

        self._stop_events[key].clear()
        if key in self._paused:
            self._toggle_pause_job(key)  # a fresh Start never starts pre-paused
        self._running.add(key)
        panel.set_run_state(running=True)
        total, themes = self._plan(key, sheets, selection)
        # the per-step restore viewer (GUI rework Phase 9) needs BOTH
        # this run's JobTemp and its output root to resolve a row's
        # drop path into a rel/live-file — mirrors _launch_tool_worker's
        # own "panel.folder = ...; panel.jobtemp = ...; panel.reset(...)"
        # grouping for the four standalone tools.
        dash = self.panels[key]
        dash.jobtemp = self._job_temps[key]
        dash.out_base = out_base
        dash.reset(active=True, task_total=total, task_themes=themes)
        self._dashgrid.add(key)  # reveal the panel (idempotent on restart)
        self._update_status()
        background = panel.background_var.get()
        style = panel.style_var.get()
        self._log(
            f"=== START {key} | {len(sheets)} sheet(s) -> {out_base}"
            f" | background: {background} | style: {style}"
            f" | bg_removal={panel.bg_removal_var.get()}"
            f" crop={panel.crop_var.get()}"
            f" upscale={panel.upscale_var.get()}"
            f" | safer_retry={panel.safer_var.get()}"
            f" continue_nudge={panel.continue_nudge_var.get()} ==="
        )
        # GUI rework Phase 19: _drive_site now takes its driver as a
        # parameter (widened to accept an ApiImageAdapter too, see
        # _start_api_image) instead of building a SiteDriver internally
        # off SITES[key] — this is the ONE place chatgpt/gemini still
        # construct the real CDP driver, unchanged from before.
        from painter.driver import SiteDriver

        driver = SiteDriver(SITES[key], timing, CDP_URL)
        worker = threading.Thread(
            target=self._drive_site,
            args=(
                key,
                list(sheets),
                out_base,
                timing,
                driver,
                post_save,
                partial(prompt_suffix, key, background, style=style),
                extra_suffix,
                panel.report_var.get(),
                selection,
                panel.safer_var.get(),
                panel.continue_nudge_var.get(),
                panel.new_chat_var.get(),
                self._stop_events[key],
                self._pause_events[key],
            ),
            daemon=True,
        )
        self._workers[key] = worker
        worker.start()
        # GUI rework Phase 11: Start hides the launching tool's own
        # settings panel (spec item 4) — website_gen's is the whole
        # _controls_box, shared by both sites, so ANY site starting
        # hides it; the owner reopens it (IconBar's website_gen tile)
        # to configure/start the other one while this one runs.
        self._inline_kind = None
        self._sync_running_state()

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
        for sheet in sheets:
            if sheet.source.resolve().is_relative_to(out_base):
                messagebox.showerror(
                    "PromptPainter",
                    f"{sheet.source.name} lives inside the output folder"
                    " — sources are READ ONLY; pick another output.",
                )
                return
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

        panel = self._tool_panels["api_image_gen"]
        if panel.access_gated:
            messagebox.showerror("PromptPainter", AI_IMAGE_GATE_MESSAGE)
            return
        if not self._ensure_ai_key():
            return
        try:
            pause_min, pause_max = panel.pace_floats()
        except ValueError:
            messagebox.showerror(
                "PromptPainter", "API Image GEN: pause must be numbers."
            )
            return
        if pause_min > pause_max:
            messagebox.showerror(
                "PromptPainter", "API Image GEN: FROM must be <= TO (pause)."
            )
            return
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
        dash.reset(active=True, task_total=total, task_themes=themes)
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
                partial(prompt_suffix, "api_image", background, style=style),
                None,  # extra_suffix — no AI-checker re-send wiring yet
                panel.report_var.get(),
                selection,
                False,  # safer_retry — no ItemRefused path from this driver
                False,  # continue_nudge — no NoImage path from this driver
                "off",  # new_chat — no chat to open; NEW_CHAT_CHOICES value
                self._stop_events["api_image"],
                self._pause_events["api_image"],
            ),
            daemon=True,
        )
        self._workers["api_image"] = worker
        worker.start()
        self._inline_kind = None
        self._sync_running_state()

    def _drive_site(
        self, key, sheets, out_base, timing, driver, post_save, suffix,
        extra_suffix, report, selection, safer, continue_nudge, new_chat,
        stop_event, pause_event,
    ) -> None:
        """One job's whole run — the theme queue in order, one thread.

        GUI rework Phase 19: GENERALIZED, not forked — ``driver`` is
        supplied ALREADY CONSTRUCTED by the caller (``_start_site``'s
        own ``SiteDriver(SITES[key], timing, CDP_URL)`` for chatgpt/
        gemini, ``_start_api_image``'s ``ApiImageAdapter`` for
        "api_image") instead of this method building a ``SiteDriver``
        internally off ``SITES[key]`` — "api_image" is not a browser
        site and has no ``SiteConfig``. This method never branches on
        WHICH kind of driver it got: it only ever calls ``attach()``/
        ``close()`` and hands the object to ``run_sheet`` unchanged,
        exactly as before — only the accepted type widened."""
        log = lambda msg: self._q.put(f"[{key}] {msg}")
        events = lambda ev: self._q.put(("__event__", key, ev))
        done_sheets = 0
        # the WHOLE body is guarded so __worker_done__ is ALWAYS posted
        # (even if the imports fail) — otherwise the job's Start button
        # would stay disabled forever
        try:
            from painter.driver import DriverError, TerminalState
            from painter.runner import run_sheet

            t_site = time.monotonic()
            title = driver.attach()
            log(f"attached to {title!r} — SUPERVISED, watch the window")
            for n, sheet in enumerate(sheets, start=1):
                if stop_event.is_set():
                    log("stopped on request — remaining collections not run")
                    break
                log(
                    f"--- collection {n}/{len(sheets)}:"
                    f" {sheet.source.name} ---"
                )
                try:
                    generated = run_sheet(
                        sheet, driver, out_base, key, timing,
                        log=log,
                        should_stop=stop_event.is_set,
                        should_pause=pause_event.is_set,
                        post_save=post_save,
                        prompt_suffix=suffix,
                        extra_suffix=extra_suffix,
                        report=report,
                        only=selection.get(str(sheet.source)),
                        on_event=events,
                        safer_retry=safer,
                        continue_nudge=continue_nudge,
                        new_chat_per_folder=(new_chat == "folder"),
                    )
                    done_sheets += 1
                    log(f"collection done: {generated} image(s) into {out_base}")
                    if (
                        new_chat in ("collection", "folder")
                        and generated
                        and n < len(sheets)
                    ):
                        try:
                            driver.new_chat(log)
                        except Exception as exc:
                            log(
                                "NEW CHAT FAILED (continuing in the old"
                                f" one): {exc}"
                            )
                except TerminalState as exc:
                    log(f"TERMINAL STATE (quota/rate limit): {exc}")
                    retry = getattr(exc, "retry_after_s", None)
                    if retry is not None:
                        self._q.put(("__terminal__", key, retry))
                        log(
                            "quota window known — this site auto-restarts"
                            " when it elapses (Stop cancels)"
                        )
                    else:
                        log(
                            "site stopped — finished work is saved; start"
                            " again later to resume the remaining"
                            " collections"
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
            driver.close()
            self._q.put(("__worker_done__", key))

    def _stop_site(self, key: str) -> None:
        """Stop ONE site: a running worker finishes its current item;
        a PENDING quota auto-restart is cancelled."""
        if key in self._restart_jobs:
            self._cancel_restart(key)
            self.agents[key].set_run_state(running=key in self._running)
            self._log(f"[{key}] pending auto-restart cancelled")
            # the site is done now — reveal the panel's CLOSE button
            self.panels[key].finish()
            self._dashgrid.relayout()
            return
        if key in self._running:
            self._stop_events[key].set()
            # Stop must win over a pending pause (MUST NOT REGRESS): the
            # should_stop re-check inside wait_while_paused already lets
            # a PAUSED run stop promptly, but the toggle itself would
            # otherwise linger and silently pre-pause the next Start.
            if key in self._paused:
                self._toggle_pause_job(key)
            self.status_var.set(
                f"{key}: stopping after the current item …"
            )

    def _update_status(self) -> None:
        if self._running:
            self.status_var.set("running: " + ", ".join(sorted(self._running)))
        else:
            self.status_var.set("idle")

    # --- quota auto-restart --------------------------------------------

    def _handle_terminal(self, key: str, retry_after_s: float) -> None:
        """A quota stop with a KNOWN reset time: schedule the site's
        auto-restart at reset + a polite random 30–120 s, with a live
        countdown on its dashboard panel. Runs whenever the app is
        open; manual Stop cancels, manual Start just starts earlier."""
        delay = retry_after_s + random.uniform(30.0, 120.0)
        self._restart_deadline[key] = time.monotonic() + delay
        self._restart_jobs[key] = self.root.after(
            int(delay * 1000), partial(self._auto_restart, key)
        )
        self._tick_restart(key)
        self._log(
            f"[{key}] auto-restart scheduled in {delay / 60:.1f} min"
        )

    def _tick_restart(self, key: str) -> None:
        if key not in self._restart_jobs:
            return  # cancelled — the countdown loop dies with it
        left = max(self._restart_deadline[key] - time.monotonic(), 0.0)
        self.panels[key].state_var.set(
            f"quota — auto-restart in {int(left // 60):02d}:"
            f"{int(left % 60):02d}"
        )
        self.root.after(1000, partial(self._tick_restart, key))

    def _cancel_restart(self, key: str) -> None:
        job = self._restart_jobs.pop(key, None)
        if job is not None:
            self.root.after_cancel(job)
        self._restart_deadline.pop(key, None)
        self.panels[key].state_var.set("")

    def _auto_restart(self, key: str) -> None:
        self._restart_jobs.pop(key, None)
        self.panels[key].state_var.set("")
        self._log(f"[{key}] quota window elapsed — auto-restarting")
        self._start_site(key)

    # --- queue pump ----------------------------------------------------

    def _drain_queue(self) -> None:
        try:
            while True:
                msg = self._q.get_nowait()
                if (
                    self._resize_active
                    and isinstance(msg, tuple)
                    and msg[0] == "__event__"
                ):
                    # mid drag-resize: a dashboard event re-renders tree
                    # rows / live labels per frame on top of the drag's
                    # own relayout work — buffer it, flushed in order by
                    # _resize_settled (owner 2026-07-20)
                    self._pending_events.append(msg)
                    continue
                self._dispatch(msg)
        except queue.Empty:
            pass
        self.root.after(120, self._drain_queue)

    def _dispatch(self, msg) -> None:
        """Apply ONE worker-queue message to the window (main thread)."""
        if isinstance(msg, tuple):
            if msg[0] == "__status__":
                self.status_var.set(msg[1])
            elif msg[0] == "__event__":
                # .get is the defensive guard for a late event
                # arriving after its panel was closed
                panel = self.panels.get(msg[1])
                if panel is not None:
                    panel.handle(msg[2])
                    # GUI rework Phase 16: the parallel Checker AI hangs
                    # off the SAME item_progress event the dashboard row
                    # was just built from — zero runner.py changes (see
                    # _maybe_spawn_checker's own docstring)
                    if msg[2].get("type") == "item_progress":
                        self._maybe_spawn_checker(msg[1], msg[2])
                    # GUI rework Phase 20: the Fixer AI hangs off the
                    # checker's OWN item_checked result (posted by
                    # _run_checker_one onto this SAME queue) — see
                    # _maybe_spawn_fixer's own docstring
                    elif msg[2].get("type") == "item_checked":
                        self._maybe_spawn_fixer(msg[1], msg[2])
            elif msg[0] == "__terminal__":
                self._handle_terminal(msg[1], msg[2])
            elif msg[0] == "__tool_done__":
                slot = msg[1]
                # GUI rework Phase 14: was THIS finish caused by
                # _stop_tool (still set — cleared only at the next
                # Start, see _launch_tool_worker) or a natural
                # completion? Read BEFORE popping _tool_workers below
                # (harmless either order — _stop_events is independent
                # — but keeps the "what happened" read next to the
                # message that reports it).
                stopped = self._stop_events[slot].is_set()
                self._tool_workers.pop(slot, None)
                # a job that finished its last image right as it was
                # paused would otherwise leave a stale "paused" toggle
                # on an idle panel (owner 2026-07-21)
                if slot in self._paused:
                    self._toggle_pause_job(slot)
                panel_key = self._tool_panel_key(slot)
                if panel_key is not None:
                    # GUI rework Phase 13/15: re-enable the panel's own
                    # Start button ("aicheck" resolves to its
                    # "image_checker" ToolSettingsPanel via
                    # _tool_panel_key since GUI rework Phase 15).
                    self._tool_panels[panel_key].set_run_state(running=False)
                if stopped:
                    # the "smart" half of _stop_tool: the worker has
                    # NOW actually halted (not merely requested to,
                    # back on the Stop click — it may have still been
                    # mid-image) — close the panel + clear its JobTemp
                    # (existing _close_panel, same as a manual Close)
                    # and leave "running" for the Main Menu if that was
                    # the LAST active job (_request_menu — Phase 11's
                    # own gate, unmodified: a no-op status hint, never
                    # an auto-jump, while another job is still active).
                    # A natural (unstopped) finish is UNCHANGED — reveal
                    # CLOSE and let the owner review before dismissing.
                    self._close_panel(slot)
                    self._request_menu()
                else:
                    self.panels[slot].finish()  # reveal CLOSE
                if not self._tool_workers and not self._running:
                    self._update_status()
                self._sync_running_state()  # GUI rework Phase 11
            elif msg[0] == "__worker_done__":
                key = msg[1]
                self._log(f"[{key}] worker finished")
                # the worker posts this from its finally block
                # while its thread is still technically alive
                self._running.discard(key)
                self._workers.pop(key, None)
                if key in self._paused:  # same stale-pause guard as above
                    self._toggle_pause_job(key)
                # GUI rework Phase 19: "api_image" also drives through
                # _drive_site (hence __worker_done__) but is NOT one of
                # self.agents (no SiteConfig, no AgentPanel — see
                # _start_api_image) — chatgpt/gemini take the EXACT
                # same branch as before; a key outside self.agents
                # resolves its OWN settings panel via _tool_panel_key,
                # the same bridge __tool_done__ below already uses, and
                # has no pending-restart concept (this job's
                # TerminalState always carries retry_after_s=None, so it
                # never enters self._restart_jobs to begin with).
                if key in self.agents:
                    self.agents[key].set_run_state(
                        running=False,
                        pending_restart=key in self._restart_jobs,
                    )
                else:
                    panel_key = self._tool_panel_key(key)
                    if panel_key is not None:
                        self._tool_panels[panel_key].set_run_state(
                            running=False
                        )
                # a pending quota auto-restart keeps the panel
                # alive (countdown, no CLOSE yet); otherwise the
                # site is done — reveal its CLOSE button
                if key not in self._restart_jobs:
                    self.panels[key].finish()
                self._update_status()
                self._sync_running_state()  # GUI rework Phase 11
        else:
            self._log(str(msg))

