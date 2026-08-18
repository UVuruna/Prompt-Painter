"""``QueuePumpMixin`` — the worker-queue pump and its dispatch table.

One of ``PainterGui``'s responsibility slices (see ``gui/app.py``). Every
background worker in this app — the site run loops, the API image job,
the standalone tools, the Checker AI and the Fixer AI — speaks to the
window through ONE ``queue.Queue``, and never touches a widget itself.
This module is the other end of that pipe: ``_drain_queue`` runs on the
tk loop every 120 ms and ``_dispatch`` applies exactly one message.

The message TAGS are the table: ``__status__`` (the status bar),
``__event__`` (a dashboard panel's own ``handle``, plus the two AI
hooks that hang off ``item_progress``/``item_checked``),
``__terminal__`` (quota — hand to the auto-restart timers), the
per-site finish tags, and a bare string, which is a log line.

Mid drag-resize, ``__event__`` messages are BUFFERED rather than
applied (owner 2026-07-20): a dashboard event re-renders tree rows and
live labels per frame on top of the drag's own relayout work.
``_resize_settled`` flushes them in order.

Split from ``gui/app_jobs.py`` (audit
``docs/AUDIT-OOP-2026-08-18.md`` -> R5, the exact three-way split the
structure ratchet already named). The tag chain moved VERBATIM: turning
it into a literal table is a separate change with its own risk, and this
refactor changes no behaviour.

No ``__init__`` here — every attribute it reads is set by
``BuildMixin.__init__``, and ``_handle_terminal`` /
``_maybe_spawn_checker`` / ``_maybe_spawn_fixer`` / ``_tool_panel_key``
resolve through the shared ``PainterGui`` MRO onto their sibling mixins.
"""

from __future__ import annotations

import queue
from tkinter import messagebox
from painter.config import DEGRADE_CONTINUE, DEGRADE_WAIT


class QueuePumpMixin:
    """The worker-queue pump and its dispatch table. Mixed into
    ``PainterGui`` — never instantiated alone."""

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
                        # F3 (owner 2026-07-29, the _vN landmine): the
                        # selection is LIVE — a saved item unticks
                        # itself, so a restart re-submits only the
                        # REMAINDER and a leftover tick can never turn
                        # into an unwanted redo version. A deliberate
                        # redo is a NEW tick on a green (done) row in
                        # Select — that one the owner makes himself.
                        drop = msg[2].get("drop_path")
                        for (site, _src, d), var in (
                            self._select_vars.items()
                        ):
                            if site == msg[1] and d == drop and var.get():
                                var.set(False)
                    # GUI rework Phase 20: the Fixer AI hangs off the
                    # checker's OWN item_checked result (posted by
                    # _run_checker_one onto this SAME queue) — see
                    # _maybe_spawn_fixer's own docstring
                    elif msg[2].get("type") == "item_checked":
                        self._maybe_spawn_fixer(msg[1], msg[2])
            elif msg[0] == "__terminal__":
                self._handle_terminal(msg[1], msg[2])
            elif msg[0] == "__ask_degrade__":
                # F2: the worker blocks on `done` while the owner picks
                _tag, key, retry, holder, done = msg
                mins = (
                    f" (reset in ~{retry / 60:.0f} min)" if retry else ""
                )
                cont = messagebox.askyesno(
                    "Model degraded",
                    f"{key}: the site dropped to a weaker model —"
                    f" image quota reached{mins}.\n\n"
                    "YES — continue on the weaker model\n"
                    "NO  — wait for the reset (auto-restart)",
                    parent=self.root,
                )
                holder["choice"] = (
                    DEGRADE_CONTINUE if cont else DEGRADE_WAIT
                )
                done.set()
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
