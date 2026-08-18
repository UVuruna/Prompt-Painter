"""``ModelDiscovery`` — the shared "Refresh models" job: ONE
``ai.list_models()`` call on a worker thread, driving a button and a
status label, handing the discovered list back on the tk main loop.

Two hosts run it: ``ApiImageGenPanel`` (its Image picker, composed with
the access gate and the "show all (debug)" switch) and
``ModelPickerRow`` (the reusable text/vision row). Their
``_refresh_models``/``_refresh`` and ``_apply_models_result``/
``_apply_result`` pairs were TWO of the three ratcheted clone groups
(audit ``docs/AUDIT-OOP-2026-08-18.md`` → R3): the only real
differences are which button and status var they drive, the found-text
wording, and what each does with the list — so those four are
constructor arguments here.

The QUEUE stays with the host: it is the host's own worker channel, and
its tests read it directly to run a discovery synchronously.
"""

from __future__ import annotations

import queue
import threading
import tkinter as tk
from typing import Callable

from .worker_poll import poll_worker_queue


class ModelDiscovery:
    """One host's "Refresh models" job. ``found_text`` is a format
    string with a single ``{n}`` — the two hosts word the result
    differently and that wording is theirs to keep."""

    def __init__(
        self,
        widget: tk.Misc,
        q: queue.Queue,
        *,
        button,
        status_var: tk.StringVar,
        on_models: Callable[[list[dict]], None],
        after_attr: str,
        found_text: str,
    ):
        self._widget = widget
        self._q = q
        self._button = button
        self._status_var = status_var
        self._on_models = on_models
        self._after_attr = after_attr
        self._found_text = found_text

    def start(self, poll_ms: int) -> None:
        """Disable the button, say what is happening, run the one
        ``ai.list_models()`` call on a daemon thread and start polling.

        ``poll_ms`` is passed per call rather than stored because one
        host reads its cadence LATE (a deferred ``import gui`` for
        ``AI_POLL_MS``, which lives in ``gui.dialogs``) — see
        ``ApiImageGenPanel._refresh_models``.
        """
        self._button.configure(state="disabled")
        self._status_var.set("Discovering models …")

        def work() -> None:
            from painter import ai

            try:
                models = ai.list_models()
            except ai.AiError as exc:
                # a NoKey (or any other AiError) message IS the
                # existing key-gate text (spec item 4) — shown
                # verbatim, no separate copy to keep in sync
                self._q.put(("error", str(exc)))
            else:
                self._q.put(("ok", models))

        threading.Thread(target=work, daemon=True).start()
        poll_worker_queue(self._widget, self._q, self.apply,
                          poll_ms=poll_ms, after_attr=self._after_attr)

    def apply(self, msg: tuple) -> None:
        """Re-enable the button, then either show the error verbatim or
        report the count and hand the list to the host."""
        self._button.configure(state="normal")
        kind, payload = msg
        if kind == "error":
            self._status_var.set(payload)
            return
        self._status_var.set(self._found_text.format(n=len(payload)))
        self._on_models(payload)
