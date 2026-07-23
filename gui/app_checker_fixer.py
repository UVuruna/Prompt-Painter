"""CheckerFixerMixin — the parallel Checker AI + Fixer AI.

Godfile refactor step 8/8 (see gui/___gui.md): split out of
``gui/app_jobs.py`` (which had grown past the ~1000-line Rule #20
budget) into its OWN mixin, one of PainterGui's six (see gui/app.py).
Owns the parallel Checker AI (``_maybe_spawn_checker``/
``_run_checker_one``, GUI rework Phase 16 — fired off every saved
image, overlapping the next item's generation) and the Fixer AI (GUI
rework Phase 20) — both its auto-dispatch half
(``_maybe_spawn_fixer``/``_run_fixer_api``/``_queue_website_fix``,
wired off the checker's own ``item_checked`` result) and its manual-
button worker builders (``_build_fix_workers``/``_run_image_fix``/
``_run_website_fix``/``_backup_before_fix``), shared with
``AiCheckPanel``'s own report viewer.

``_maybe_spawn_checker`` is called from ``SiteJobsMixin._dispatch``
(gui/app_jobs.py) for every ``item_progress`` event, and
``_maybe_spawn_fixer`` from the same place for every ``item_checked``
event this mixin itself posts — both calls resolve through the shared
``PainterGui`` MRO (``self.``), exactly as when the two mixins' code
lived in one file. No ``__init__`` here — every attribute this mixin
reads (``self.agents``, ``self.panels``, ``self._job_temps``, ``self._q``,
…) is set by ``BuildMixin.__init__``.
"""

from __future__ import annotations

import threading
from functools import partial
from pathlib import Path, PurePosixPath
from typing import Callable

from painter.config import (
    AI_CHECK_INSTRUCTIONS,
    CDP_URL,
    SITES,
    TIMING,
    dest_for,
)
from .logic import _fixer_decision


class CheckerFixerMixin:
    """The parallel Checker AI and the Fixer AI (auto-dispatch +
    manual fix-worker builders)."""

    # --- Checker AI — parallel per-item check (GUI rework Phase 16) ----

    def _maybe_spawn_checker(self, key: str, event: dict) -> None:
        """The owner's "dok generise sledecu sliku paralelno ona koja je
        generisana cek jer provjeri" (UV/prompt.txt item 1): fired from
        ``_dispatch`` for EVERY ``item_progress``, on the site whose
        image it just saved. A no-op unless ``key`` is a SITE (not a
        tool/aicheck slot) with its AgentPanel's ``checker_var`` ON —
        read LIVE at every call (not captured once at Start), so the
        owner can flip it mid-run and it takes effect from the next
        saved image.

        By the time ``item_progress`` fires, ``run_sheet`` has already
        written the FINAL post-processed bytes to disk (the post_save
        hook runs before it emits the event — see runner.py) — so this
        is the earliest possible moment to start the check, and it
        overlaps BOTH the remaining "our time" pause AND the next
        item's whole generation, which is the entire point (ZERO
        runner.py changes: this hangs off an event the dashboard
        already consumes, per the binding design doc's Findings).

        The "checking…" marker is applied SYNCHRONOUSLY here (already
        on the main thread, same as ``panel.handle`` right above this
        call in ``_dispatch``) so it appears instantly; the actual
        vision call runs on a daemon thread (``_run_checker_one``) that
        posts its OWN ``item_checked`` event back onto the SAME queue
        once it completes — never blocking this method or the run
        loop."""
        agent = self.agents.get(key)
        if agent is None or not agent.checker_var.get():
            return  # not a site, or this site's checker is off
        dash = self.panels.get(key)
        if dash is None or dash.out_base is None:
            return  # panel closed, or somehow not started yet
        drop_path = event["drop_path"]
        dash.handle({"type": "item_checking", "drop_path": drop_path})
        src = dash.out_base / dest_for(drop_path, key)
        threading.Thread(
            target=self._run_checker_one,
            args=(key, drop_path, src, dash.out_base),
            daemon=True,
        ).start()

    def _run_checker_one(
        self, key: str, drop_path: str, src: Path, out_base: Path,
    ) -> None:
        """ONE saved image's vision check, entirely on its own daemon
        thread — the background half of ``_maybe_spawn_checker``. Posts
        exactly one ``item_checked`` event back onto the shared GUI
        queue, routed to ``key``'s DashPanel exactly like every other
        site event (``_dispatch``'s ``__event__`` branch).

        ``ai.check_one_image`` already turns a per-image ``AiError``
        (including ``NoKey`` — a subclass, see painter/ai.py) into an
        'error' result dict instead of raising (the same loud-but-
        never-fatal contract the standalone AI-check batch job already
        relies on) — so in the common case this method never needs its
        own except clause for that. The outer ``except Exception`` below
        is the extra safety net for anything ELSE that could escape
        (e.g. the file vanishing under a race, a disk-full flag-file
        write) so a checker thread can NEVER die silently and NEVER
        touches — let alone kills — the generation run it is checking
        (Rule #1: loud, visible on the row, non-fatal)."""
        from painter import ai

        emit = lambda ev: self._q.put(("__event__", key, ev))
        log = lambda msg: self._q.put(f"[{key} checker] {msg}")
        try:
            result = ai.check_one_image(
                src, out_base, AI_CHECK_INSTRUCTIONS, log=log,
            )
            emit({
                "type": "item_checked", "drop_path": drop_path,
                "kind": result["kind"], "defects": result["defects"],
                "raw": result["raw"], "rel": result["rel"],
                "time": result["time"],
            })
        except Exception as exc:
            log(f"FAIL {src.name}: {exc}")
            emit({
                "type": "item_checked", "drop_path": drop_path,
                "kind": "error", "defects": [], "raw": str(exc),
                "rel": ai.flag_key(src, out_base), "time": 0.0,
            })

    # --- Fixer AI (GUI rework Phase 20) ---------------------------------
    # The owner's UV/prompt.txt item 1 ("... salje fikseru da ispravi i to
    # u situaciji ako su oba ukljucena") and item 2 ("Checker double click
    # -> ... buttone za IMAGE FIX i WEBSITE fix ... kreira PROMPT koji
    # salje uz sliku"). Two independent surfaces sharing ai.build_fix_
    # prompt/JobTemp step="fixer": the AUTO-DISPATCH half below
    # (_maybe_spawn_fixer/_run_fixer_api/_queue_website_fix, wired off
    # item_checked in _dispatch) and the MANUAL half
    # (_build_fix_workers/_run_image_fix/_run_website_fix, called by
    # DocWindow's IMAGE FIX/WEBSITE FIX buttons via DashPanel._show_check
    # / AiCheckPanel._on_activate). "Send flagged to generator"
    # (_resend_flagged) stays untouched as the THIRD, pre-existing option.

    def _maybe_spawn_fixer(self, key: str, event: dict) -> None:
        """The owner's UV/prompt.txt item 1, second half: once the
        parallel Checker AI (``_maybe_spawn_checker``/``_run_checker_one``)
        reports an ``item_checked``, dispatch this site's Fixer AI per
        ``_fixer_decision`` — ``fixer_var``/``fixer_mode_var`` are read
        LIVE (inside that pure function), exactly like
        ``_maybe_spawn_checker`` reads ``checker_var`` live, so a mid-run
        toggle takes effect from the NEXT checked image."""
        agent = self.agents.get(key)
        if agent is None:
            return
        decision = _fixer_decision(agent, event)
        if decision == "none":
            return
        dash = self.panels.get(key)
        if dash is None or dash.out_base is None:
            return  # panel closed, or somehow not started yet
        defects = event["defects"]
        raw = event.get("raw") or ""
        if decision == "api":
            threading.Thread(
                target=self._run_fixer_api,
                args=(
                    key, event["drop_path"], event["rel"], dash.out_base,
                    defects, raw,
                ),
                daemon=True,
            ).start()
        else:  # "website_queue"
            self._queue_website_fix(key, event["rel"], defects, raw)

    def _run_fixer_api(
        self, key: str, drop_path: str, rel: str, out_base: Path,
        defects: list[str], raw: str,
    ) -> None:
        """The auto-fixer's API-mode background half (Phase 20) — a
        plain ``ai.edit_image`` REST call, so it genuinely overlaps the
        site's OWN next-image generation on the SAME browser tab (the
        intended parallel flow — the binding design doc's "only the API
        fix can truly run in parallel while generating"). Backs the
        pre-fix file up via THIS site's live JobTemp under
        ``step="fixer"`` before overwriting (best-effort — see
        ``_backup_before_fix``), so it is restorable in the Phase 9
        StepRestore viewer exactly like every pipeline stage. A gated or
        failed call is LOUD (the log line) and NEVER FATAL — it never
        touches the run this image came from (Rule #1, the SAME
        convention ``_run_checker_one`` already established for the
        checker side)."""
        from painter import ai

        log = lambda msg: self._q.put(f"[{key} fixer] {msg}")
        emit = lambda ev: self._q.put(("__event__", key, ev))
        live = out_base / dest_for(drop_path, key)
        prompt = ai.build_fix_prompt(defects, raw)
        try:
            fixed = ai.edit_image(live, prompt, log=log)
        except ai.PaidFeatureRequired as exc:
            log(f"FIXER GATED (no billing for the image model): {exc}")
            return
        except ai.AiError as exc:
            log(f"FIXER FAILED: {live.name}: {exc}")
            return
        self._backup_before_fix(key, rel, live)
        live.write_bytes(fixed)
        log(f"FIXED (API): {live.name}")
        emit({"type": "item_fixed", "drop_path": drop_path, "mode": "api"})

    def _queue_website_fix(
        self, key: str, rel: str, defects: list[str], raw: str,
    ) -> None:
        """WEBSITE-mode auto-fixer choice (owner design, Phase 20) —
        **documented here in full, since the design explicitly asks for
        an unambiguous choice**: the browser tab is BUSY generating this
        site's OWN next image the instant ``item_checked`` fires (the
        checker's background thread reports well before the run
        finishes) — driving ``driver.submit_with_image`` here would
        collide with that in-flight ``submit_prompt``/``await_done`` (one
        tab, one operation). So this method NEVER touches the browser.

        Instead it folds the flagged item into ``AiCheckPanel``'s OWN
        ``_flagged``/``_raw`` bucket via its EXISTING
        ``handle({"type": "item_flagged", ...})`` — the IDENTICAL
        append-only state the standalone batch checker already fills —
        and reveals that panel on the dashboard grid (``DashGrid.add``
        is idempotent) so the queued item is IMMEDIATELY VISIBLE as a
        real row, never a silent internal list (root Rule #1: "never
        silently no-op"). The owner's EXISTING **Send flagged to
        generator** button (``AiCheckPanel._do_resend`` ->
        ``PainterGui._resend_flagged``) is the ONE send path — reused
        VERBATIM, never duplicated — whenever they choose to click it;
        typically once this site is idle again, since
        ``_resend_flagged``'s own ``_start_site`` call already refuses a
        site that is still ``self._running``, so there is no way for a
        click to collide with the still-running generation even if it
        happens immediately."""
        aicheck = self.panels["aicheck"]
        aicheck.handle({
            "type": "item_flagged", "rel": rel, "defects": list(defects),
            "raw": raw, "time": 0.0,
        })
        self._dashgrid.add("aicheck")
        self._log(
            f"[{key}] fixer (website mode): queued"
            f" {PurePosixPath(rel).name} for 'Send flagged to generator'"
            f" — {len(defects)} defect(s)"
        )

    def _backup_before_fix(
        self, jobtemp_slot: str | None, rel: str, live: Path,
    ) -> None:
        """Best-effort pre-fix backup (``step="fixer"``) into the live
        ``JobTemp`` for ``jobtemp_slot`` — the SAME instance
        ``DashPanel.jobtemp``/the site's own pipeline already write into,
        NEVER a freshly constructed one (``JobTemp.__init__`` wipes its
        slot's directory on construction — reusing the live instance is
        the ONLY safe choice here). When that slot has no live JobTemp
        (the site's dashboard panel was already Closed this session, or
        this image came from outside any queued generation), the backup
        is skipped LOUDLY (root Rule #1) rather than silently — the fix
        still applies either way, it simply will not offer a 'Fixer AI'
        stage in the Steps… restore viewer."""
        temp = self._job_temps.get(jobtemp_slot) if jobtemp_slot else None
        if temp is not None:
            temp.backup(live, rel, step="fixer")
        else:
            self._q.put(
                f"[fixer] no active JobTemp for {jobtemp_slot!r} — the"
                f" pre-fix state of {live.name} was not backed up (the"
                " Steps… restore viewer will not offer a Fixer AI stage"
                " for it)"
            )

    def _run_image_fix(
        self, rel: str, out_base: Path, jobtemp_slot: str | None,
        defects: list[str], raw: str,
    ) -> tuple[str, str]:
        """The manual IMAGE FIX button's background-thread body (Rule
        #5: shared by ``DashPanel``'s 'Check…' viewer and
        ``AiCheckPanel``'s own double-click viewer, via
        ``_build_fix_workers``) — a plain ``ai.edit_image`` REST call,
        so it needs no site/browser concept at all: ANY checked image,
        regardless of provenance, can be IMAGE-FIXED. Returns a
        ``(kind, message)`` pair ``DocWindow._apply_fix_result`` reads:
        ``"ok"`` (the image was overwritten), ``"gated"``
        (``PaidFeatureRequired`` — permanent, no billing on the image
        model), or ``"error"`` (any other ``AiError`` — transient,
        retry-able). Runs on a background thread (spawned by
        ``DocWindow._run_fix``), so it logs through ``self._q``, never
        ``self._log`` directly (Rule #1's thread-safety convention every
        other background worker in this file already follows)."""
        from painter import ai

        live = ai.flag_file(rel, out_base)
        prompt = ai.build_fix_prompt(defects, raw)
        log = lambda msg: self._q.put(f"[fixer] {msg}")
        try:
            fixed = ai.edit_image(live, prompt, log=log)
        except ai.PaidFeatureRequired as exc:
            self._q.put(f"[fixer] IMAGE FIX gated: {exc}")
            return ("gated", str(exc))
        except ai.AiError as exc:
            self._q.put(f"[fixer] IMAGE FIX failed on {live.name}: {exc}")
            return ("error", str(exc))
        self._backup_before_fix(jobtemp_slot, rel, live)
        live.write_bytes(fixed)
        self._q.put(f"[fixer] IMAGE FIX applied: {live}")
        return ("ok", "the image was overwritten via the API.")

    def _run_website_fix(
        self, rel: str, out_base: Path, jobtemp_slot: str | None,
        site_key: str, defects: list[str], raw: str,
    ) -> tuple[str, str]:
        """The manual WEBSITE FIX button's background-thread body —
        drives a FRESH ``SiteDriver`` (attach -> submit_with_image ->
        await_done -> extract_image -> close), an OWNER-TRIGGERED one-off
        automation — never the running site's own worker thread. This is
        why it stays safe despite the one-tab constraint: it is only
        ever reached by an explicit click, and refuses outright (a
        transient, retry-able ``"error"``, not a permanent ``"gated"``)
        while THIS site is ``self._running`` — the tab is genuinely busy
        generating the next image then, exactly the collision
        ``_queue_website_fix`` avoids on the auto-dispatch side."""
        if site_key in self._running:
            return (
                "error",
                f"{SITES[site_key].name} is currently generating — stop"
                " it or wait until it finishes, then retry.",
            )
        from painter import ai
        from painter.driver import (
            AttachNotConfigured,
            DriverError,
            SiteDriver,
        )

        live = ai.flag_file(rel, out_base)
        prompt = ai.build_fix_prompt(defects, raw)
        log = lambda msg: self._q.put(f"[fixer] {msg}")
        driver = SiteDriver(SITES[site_key], TIMING, CDP_URL)
        try:
            driver.attach()
            driver.submit_with_image(str(live), prompt)
            driver.await_done(log=log)
            fixed = driver.extract_image()
        except AttachNotConfigured as exc:
            self._q.put(f"[fixer] WEBSITE FIX gated: {exc}")
            return ("gated", str(exc))
        except DriverError as exc:
            self._q.put(f"[fixer] WEBSITE FIX failed: {exc}")
            return ("error", str(exc))
        finally:
            driver.close()
        self._backup_before_fix(jobtemp_slot, rel, live)
        live.write_bytes(fixed)
        self._q.put(f"[fixer] WEBSITE FIX applied: {live}")
        return ("ok", "the image was overwritten via the website.")

    def _build_fix_workers(
        self, rel: str, out_base: Path, defects: list[str], raw: str,
        jobtemp_slot: str | None = None,
    ) -> tuple[
        Callable[[], tuple[str, str]], Callable[[], tuple[str, str]] | None,
    ]:
        """The checker report viewer's manual fix buttons (owner's #2,
        UV/prompt.txt item 2) — Rule #5, the ONE builder both
        ``DashPanel._show_check`` and ``AiCheckPanel._on_activate`` call,
        so the two report-viewer launch surfaces can never diverge.

        ``jobtemp_slot`` is the caller's OWN job kind when it already
        knows it (``DashPanel`` passes its own ``self.slot_key``);
        ``AiCheckPanel`` — the standalone checker, with no site of its
        own — passes ``None``, and this resolves BOTH the site (for
        WEBSITE FIX) and the JobTemp slot (for the pre-fix backup) the
        SAME way ``ai.plan_resend``'s own re-send already does:
        ``ai.drop_and_site_for(rel)``, the ``dest_for`` reverse.

        Returns ``(image_fix_worker, website_fix_worker)`` — zero-arg
        callables ``DocWindow`` runs on a background thread;
        ``website_fix_worker`` is ``None`` when no ``SITES`` entry can
        be resolved for this image (an API Image GEN output, which has
        no browser tab at all, or a standalone-checked image from
        outside any queued generation) — WEBSITE FIX makes no sense
        without a site to drive; IMAGE FIX is always offered (it needs
        no site concept)."""
        from painter import ai

        if jobtemp_slot is None:
            mapped = ai.drop_and_site_for(rel)
            jobtemp_slot = mapped[1] if mapped is not None else None
        site_key = jobtemp_slot if jobtemp_slot in SITES else None

        image_worker = partial(
            self._run_image_fix, rel, out_base, jobtemp_slot, defects, raw,
        )
        website_worker = None
        if site_key is not None:
            website_worker = partial(
                self._run_website_fix, rel, out_base, jobtemp_slot,
                site_key, defects, raw,
            )
        return image_worker, website_worker

