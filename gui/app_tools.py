"""ToolJobsMixin — the four standalone tools + the AI image checker.

Godfile refactor step 7/8 (see gui/___gui.md): the fifth of PainterGui's
six mixins (see gui/app.py — a sixth, CheckerFixerMixin, split out of
SiteJobsMixin in step 8/8). Owns every standalone-tool job's Start/Stop
(BG removal / Crop / Upscale / Aspect ratio — ``_start_tool_from_panel``/
``_launch_tool_worker``/``_run_tool_job``/``_stop_tool``) and the AI
image checker's own job (``_start_ai_check``/``_run_ai_check_job``),
plus its two report-viewer actions (``_resend_flagged``/
``_clear_ai_flags``). No ``__init__`` here — every attribute it reads
is set by ``BuildMixin.__init__``.
"""

from __future__ import annotations

import threading
import time
from pathlib import Path
from tkinter import messagebox

from painter import jobtemp
from painter.config import (
    AI_CALL_PAUSE_S,
    AI_CHECK_INSTRUCTIONS,
    GEMINI_VISION_MODEL,
    JOB_LABEL,
)
from .logic import _filter_files

# --- AI checker (Rule #4) ---------------------------------------------
AI_CHECK_LOG_EVERY = 5      # checker progress log cadence (paced calls are slow)


class ToolJobsMixin:
    """The four standalone tools' Start/Stop/worker loop and the AI
    image checker's own job + report-viewer actions."""

    def _start_tool_from_panel(self, slot: str) -> None:
        """Start button on a persistent ``ToolSettingsPanel`` — ALL
        FOUR standalone tools since GUI rework Phase 14 (BG/Crop,
        Phase 13; Upscale/Aspect, Phase 14, replacing their old
        UpscaleParamsDialog/AspectRatioDialog modal askdirectory+
        confirm flow, now deleted): reads the panel's OWN input pick +
        filter + Advanced/extra overrides (dropped here: the panel
        itself, deliberately configured then Started, already IS the
        confirmation — no separate askyesno), pre-filters via the
        shared ``_filter_files``, then hands off to ``_launch_tool_
        worker`` (one-job-per-kind guard, JobTemp, worker spawn,
        dashboard reveal) — the ONE tail every tool's Start shares."""
        if slot in self._tool_workers:
            messagebox.showerror(
                "PromptPainter",
                f"{JOB_LABEL[slot]} is already running — wait for it to"
                " finish, or Close its panel.",
            )
            return
        panel = self._tool_panels[slot]
        try:
            folder_path, files = panel.resolve_input()
            conditions = panel.get_conditions()
            func = panel.build_func()
        except ValueError as exc:
            messagebox.showerror("PromptPainter", str(exc))
            return
        files = _filter_files(files, conditions, self._log)
        self._launch_tool_worker(slot, JOB_LABEL[slot], func, folder_path, files)
        panel.set_run_state(running=True)
        # Start hides the launching panel (spec item 4, mirrors
        # _start_site's own "_inline_kind = None" — but ALSO forces an
        # immediate re-layout: _sync_running_state (inside
        # _launch_tool_worker) is a no-op here because the view is
        # ALREADY "running" — the panel can only be visible while it
        # is — so nothing else would re-pack the region above the
        # notebook without this explicit call.
        self._inline_kind = None
        self._apply_running_layout()

    def _launch_tool_worker(
        self, slot: str, label: str, func, folder_path: Path,
        files: list[Path],
    ) -> None:
        """Shared tail for EVERY standalone-tool Start (all four are
        panel-driven since GUI rework Phase 14 — ``_start_tool_from_
        panel``): create this run's JobTemp, reveal the dashboard
        ``ToolPanel``, spawn ``_run_tool_job`` on its own daemon
        thread. A stale Stop flag from a PREVIOUS run of this slot is
        swept here too (mirrors ``_start_site``'s own ``self.
        _stop_events[key].clear()`` — a fresh job must never start
        pre-stopped)."""
        # a finished panel for this slot may still be on screen — clear
        # its old temp before the new job takes the slot
        old = self._job_temps.pop(slot, None)
        if old is not None:
            old.clear()
        temp = jobtemp.JobTemp(slot, folder_path)
        self._job_temps[slot] = temp

        panel = self.panels[slot]
        panel.folder = folder_path
        panel.jobtemp = temp
        panel.reset(active=True, total=len(files))
        self._dashgrid.add(slot)
        self.notebook.select(0)
        self.status_var.set(f"{label} running …")

        if slot in self._paused:
            self._toggle_pause_job(slot)  # a fresh job never starts pre-paused
        self._stop_events[slot].clear()  # ditto for a stale Stop
        worker = threading.Thread(
            target=self._run_tool_job,
            args=(
                slot, label, func, folder_path, files, temp,
                self._pause_events[slot], self._stop_events[slot],
            ),
            daemon=True,
        )
        self._tool_workers[slot] = worker
        worker.start()
        self._sync_running_state()  # GUI rework Phase 11

    def _run_tool_job(
        self, slot, label, func, folder, files, temp, pause_event,
        stop_event,
    ) -> None:
        """One tool job on its own thread: back up each original, run
        the engine func in place, measure BEFORE→AFTER, and stream item
        events to the slot's panel. A crash on one file is loud and
        counted FAILED (its no-op backup dropped), never kills the job.
        The measure is computed OUTSIDE the engine, from the backup vs
        the in-place result (Rule #10 progress every 25). ``pause_event``
        (owner 2026-07-21) blocks BETWEEN images while set. ``stop_event``
        (GUI rework Phase 14, ``PainterGui._stop_tool``) is checked at
        the SAME between-images boundary — mirrors ``run_sheet``'s own
        ``should_stop`` exactly: the in-flight image always finishes
        first, and it is also threaded into ``wait_while_paused`` so a
        Stop wins over a pending Pause instead of hanging until
        Resume."""
        from painter.runner import wait_while_paused

        emit = lambda ev: self._q.put(("__event__", slot, ev))
        log = lambda msg: self._q.put(f"[{label}]     {msg}")
        try:
            self._q.put(f"[{label}] {len(files)} image(s) under {folder}")
            emit({"type": "sheet_start", "total": len(files)})
            counts: dict[str, int] = {}
            t0 = time.time()
            for i, src in enumerate(files, start=1):
                if stop_event.is_set():
                    log(
                        f"STOPPED on request —"
                        f" {sum(counts.values())}/{len(files)} this run"
                    )
                    break
                if wait_while_paused(
                    pause_event.is_set, stop_event.is_set, log, emit
                ):
                    log(
                        f"STOPPED on request —"
                        f" {sum(counts.values())}/{len(files)} this run"
                    )
                    break
                rel = src.relative_to(folder).as_posix()
                emit({
                    "type": "item_start", "idx": i, "of": len(files),
                    "title": src.name,
                })
                temp.backup(src, rel)  # the ORIGINAL, before the op
                t_item = time.time()
                try:
                    status = func(src, log)
                except Exception as exc:
                    status = "FAILED"
                    self._q.put(f"[{label}] FAIL {src.name}: {exc}")
                op_s = time.time() - t_item  # this image's op time
                # "changed" keys on the engine ACTUALLY REWRITING the file
                # ("done"), never on a resolution/metric change (owner
                # 2026-07-19): a 3px crop or a small BG clear rounds the
                # metric to 0% yet the file WAS modified, so its backup +
                # before/after must survive. The engine already returns
                # "nothing" for a true no-op (byte-unchanged), so a "done"
                # is always a real, restorable change.
                metric = (
                    jobtemp.measure(slot, temp.before_path(rel), src)
                    if status == "done" else None
                )
                counts[status] = counts.get(status, 0) + 1
                if status == "done":
                    emit({
                        "type": "item_done", "rel": rel, "time": op_s,
                        "size": src.stat().st_size, **metric,
                    })
                else:  # nothing / unclear / FAILED -> unchanged file
                    temp.drop(rel)  # no restore point for a no-op
                    emit({"type": "item_refused", "rel": rel})
                if i % 25 == 0:
                    self._q.put(
                        f"[{label}] [{time.time() - t0:.0f}s]"
                        f" {i}/{len(files)}"
                    )
            emit({"type": "sheet_done"})
            summary = ", ".join(f"{k}={v}" for k, v in sorted(counts.items()))
            self._q.put(f"[{label}] done: {summary or 'no images'}")
        finally:
            self._q.put(("__tool_done__", slot))

    # --- the AI checker job (owner 2026-07-20) --------------------------

    def _start_ai_check(self, slot: str) -> None:
        """Start on the AI checker's persistent settings panel
        (``ImageCheckerSettingsPanel``, GUI rework Phase 15) — a batch
        vision pass over a folder/files as its OWN job/panel (read-
        only: it writes NOTHING but the flag file under
        ``<out>/_state/``). One job at a time, like the four tools.

        Previously this method owned its own ``askdirectory`` folder
        pick + a confirm ``askyesno`` — both DELETED here (Rule #6):
        the panel's own input picker + embedded ``FilterEditor`` (see
        ``ToolSettingsPanel``) now cover the folder/files choice, and
        Start — deliberately configured then clicked — already IS the
        confirmation, the same contract ``_start_tool_from_panel``
        established for the four tools (the panel's own footer note
        carries what the confirm dialog used to say about pacing/
        model/where flags persist). Unlike those four, this does NOT
        go through ``_start_tool_from_panel``/``_launch_tool_worker``
        — the checker's worker (``_run_ai_check_job``) has no
        JobTemp/engine-func shape to share with ``_run_tool_job`` (see
        ``ImageCheckerSettingsPanel``'s own docstring), so its spawn is
        inlined here instead, by hand mirroring ``_launch_tool_
        worker``'s own tail (stale-Stop sweep, stale-pause sweep,
        dashboard reveal, thread spawn, ``_sync_running_state``)."""
        if slot in self._tool_workers:
            messagebox.showerror(
                "PromptPainter",
                f"{JOB_LABEL[slot]} is already running — wait for it"
                " to finish, or Close its panel.",
            )
            return
        if not self._ensure_ai_key():
            return
        panel = self._tool_panels["image_checker"]
        try:
            folder_path, files = panel.resolve_input()
            conditions = panel.get_conditions()
        except ValueError as exc:
            messagebox.showerror("PromptPainter", str(exc))
            return
        files = _filter_files(files, conditions, self._log)
        out_base = self._out_base()

        dash = self.panels[slot]
        dash.folder = folder_path
        dash.out_base = out_base
        dash.reset(active=True, total=len(files))
        self._dashgrid.add(slot)
        self.notebook.select(0)
        self.status_var.set(f"{JOB_LABEL[slot]} running …")

        if slot in self._paused:
            self._toggle_pause_job(slot)  # never start pre-paused
        self._stop_events[slot].clear()  # ditto for a stale Stop (Phase 15)
        worker = threading.Thread(
            target=self._run_ai_check_job,
            args=(
                folder_path, files, out_base, self._pause_events[slot],
                self._stop_events[slot],
            ),
            daemon=True,
        )
        self._tool_workers[slot] = worker
        worker.start()
        panel.set_run_state(running=True)
        # Start hides the launching panel (spec item 4, mirrors
        # _start_tool_from_panel's own tail) — the view is already
        # "running" (this panel can only be visible while it is), so
        # _sync_running_state()'s own view-transition check is a no-op
        # here; this explicit call is what actually re-packs the region.
        self._inline_kind = None
        self._apply_running_layout()
        self._sync_running_state()  # GUI rework Phase 11

    def _run_ai_check_job(
        self, folder, files, out_base, pause_event, stop_event,
    ) -> None:
        """The checker worker: prune stale flags (regenerated files),
        then one paced vision call per image — flagged entries are
        recorded (merged) into the flag file as they land, an OK image
        CLEARS any old flag it had, and a per-image API failure is loud
        but never kills the batch (the tool-job convention).
        ``pause_event`` (owner 2026-07-21) blocks BETWEEN images while
        set. ``stop_event`` (GUI rework Phase 15, closing Phase 14's
        own flagged gap for THIS job) is checked at the SAME between-
        images boundary — mirrors ``_run_tool_job``'s/``run_sheet``'s
        own ``should_stop`` exactly: the in-flight vision call always
        finishes first, and it is also threaded into
        ``wait_while_paused`` so a Stop wins over a pending Pause
        instead of hanging until Resume."""
        from painter import ai
        from painter.runner import wait_while_paused

        emit = lambda ev: self._q.put(("__event__", "aicheck", ev))
        log = lambda msg: self._q.put(f"[AI check] {msg}")
        try:
            log(
                f"{len(files)} image(s) under {folder} — model"
                f" {GEMINI_VISION_MODEL}, paced {AI_CALL_PAUSE_S:.0f}s/call"
            )
            ai.prune_stale_flags(out_base, log)
            emit({"type": "sheet_start", "total": len(files)})
            flagged = ok = errors = 0
            # check_one_image's kind -> the panel event type it emits
            event_type = {
                "flagged": "item_flagged",
                "ok": "item_ok",
                "error": "item_error",
            }
            t0 = time.time()
            for i, src in enumerate(files, start=1):
                if stop_event.is_set():
                    log(
                        f"STOPPED on request —"
                        f" {flagged + ok + errors}/{len(files)} this run"
                    )
                    break
                if wait_while_paused(
                    pause_event.is_set, stop_event.is_set, log, emit
                ):
                    log(
                        f"STOPPED on request —"
                        f" {flagged + ok + errors}/{len(files)} this run"
                    )
                    break
                emit({
                    "type": "item_start", "idx": i, "of": len(files),
                    "title": src.name,
                })
                # check_one_image does the timing, parse, flag merge/clear
                # and the FLAGGED/FAIL logging; the loud-but-never-fatal
                # AiError handling lives inside it (the tool-job convention)
                result = ai.check_one_image(
                    src, out_base, AI_CHECK_INSTRUCTIONS, log=log
                )
                kind = result["kind"]
                event = {
                    "type": event_type[kind], "rel": result["rel"],
                    "raw": result["raw"], "time": result["time"],
                }
                if kind == "flagged":
                    flagged += 1
                    event["defects"] = result["defects"]
                elif kind == "ok":
                    ok += 1
                else:
                    errors += 1
                emit(event)
                if i % AI_CHECK_LOG_EVERY == 0:
                    self._q.put(
                        f"[AI check] [{time.time() - t0:.0f}s]"
                        f" {i}/{len(files)} ({i / len(files) * 100:.0f}%)"
                    )
            emit({"type": "sheet_done"})
            log(
                f"done: {flagged} flagged, {ok} OK, {errors} error(s) —"
                f" flags in {ai.flags_path(out_base)}"
            )
        finally:
            self._q.put(("__tool_done__", "aicheck"))

    def _resend_flagged(self, flagged: dict[str, list[str]]) -> None:
        """The AI-check panel's 'Send flagged to generator': map every
        flagged image back to its (site, drop path) — the ``dest_for``
        reverse — match it against the QUEUED collections, and start
        each matched site with ``only=`` exactly those items plus a
        per-item fix note appended to the prompt (the regenerate path,
        overwriting the flawed file). Unmatched images and an
        already-running site are LOUD skips, never silent."""
        from painter import ai

        if not self._sheets:
            messagebox.showerror(
                "PromptPainter",
                "The Collections queue is empty — Add… the sheet(s) the"
                " flagged images came from, then Send again.",
            )
            return
        sheets = self._parse_all()
        drop_to_source = {
            item.drop_path: str(sheet.source)
            for sheet in sheets
            for item in sheet.items
        }
        plans, notes, unmatched = ai.plan_resend(flagged, drop_to_source)
        for key, why in unmatched:
            self._log(f"[AI check] NO MATCH ({why}): {key} — skipped")
        if not plans:
            messagebox.showinfo(
                "PromptPainter",
                "None of the flagged images matches a queued collection"
                " — queue the sheet(s) they came from and Send again.",
            )
            return
        for site in sorted(plans):
            if site in self._running:
                self._log(
                    f"[{site}] already running — flagged re-send skipped"
                    " (Stop it first, then Send again)"
                )
                continue
            count = sum(len(drops) for drops in plans[site].values())
            self._log(
                f"[{site}] AI re-send: {count} flagged image(s), each"
                " with its fix note"
            )
            self._start_site(
                site, override_selection=plans[site],
                extra_suffix=notes[site],
            )

    def _clear_ai_flags(self, out_base: Path, keys: list[str]) -> int:
        """The panel's Clear-flags action — drops the given entries from
        the flag file; returns the number actually removed."""
        from painter import ai

        cleared = ai.clear_flag_keys(out_base, keys, self._log)
        self._log(
            f"[AI check] {cleared} flag(s) cleared from"
            f" {ai.flags_path(out_base)}"
        )
        return cleared

    def _stop_tool(self, slot: str) -> None:
        """Stop ONE standalone tool job (GUI rework Phase 14, closing
        Phase 13's own flagged gap) — mirrors ``_stop_site``'s request
        half exactly (no quota auto-restart to cancel, tools have
        none): sets the should_stop event ``_run_tool_job`` polls
        BETWEEN images, wins over a pending Pause the same way. This
        method only REQUESTS the stop — it does NOT touch the
        dashboard panel or JobTemp itself; the worker may still be
        mid-image. The "smart" half (close the panel, clear its
        JobTemp, maybe leave "running") runs once the worker actually
        confirms the halt, in ``_dispatch``'s ``__tool_done__`` branch,
        which checks this SAME event to tell a Stop-triggered finish
        apart from a natural one."""
        if slot not in self._tool_workers:
            return
        self._stop_events[slot].set()
        if slot in self._paused:
            self._toggle_pause_job(slot)
        self.status_var.set(
            f"{JOB_LABEL[slot]}: stopping after the current item …"
        )
