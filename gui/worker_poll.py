"""``poll_worker_queue`` — the one home for the worker-thread → tk
main-loop handoff every AI panel and dialog in this GUI performs.

A background thread may never touch a widget, so each job puts its
result on a private ``queue.Queue`` and the tk loop drains it on a
``widget.after`` tick. Six methods across five classes carried that
identical eight-statement loop — ``ApiImageGenPanel._poll_probe`` and
``._poll_models``, ``_AiDialog._poll``, ``ModelPickerRow._poll``,
``SheetGenPanel._poll`` and ``DocWindow._poll_fix`` — three of them
ratcheted as an accepted clone in ``tests/clone_ratchet.json``.

``gui/__about/api_panel.md`` used to DEFEND the copies: the hosts' base
classes differ (``ttk.Frame`` panels vs. the ``tk.Toplevel``-derived
``_AiDialog``), so no mixin could hold them all. That objection was
real, and this module is the answer to it — a FREE FUNCTION needs no
shared base at all. The owner accepted reversing that note on
2026-08-18 (audit ``docs/AUDIT-OOP-2026-08-18.md`` → R3).

Each host keeps its OWN queue, its own cadence constant and its own
one-line arming method: those genuinely differ, and they are what makes
each loop that host's.
"""

from __future__ import annotations

import queue
import tkinter as tk
from typing import Callable


def poll_worker_queue(
    widget: tk.Misc,
    q: queue.Queue,
    on_result: Callable[[tuple], None],
    *,
    poll_ms: int,
    after_attr: str,
) -> None:
    """Drain ``q`` on ``widget``'s tk loop every ``poll_ms`` ms until a
    message lands, then hand it to ``on_result`` — on the main thread,
    where touching a widget is legal.

    The pending ``after`` id is kept ON THE WIDGET under ``after_attr``
    (``None`` while a tick is executing), so a host that cancels its own
    loop on teardown keeps working exactly as before.

    A widget destroyed mid-work ends the loop silently: once the window
    is gone the worker's message is moot.
    """
    def arm() -> None:
        setattr(widget, after_attr, widget.after(poll_ms, tick))

    def tick() -> None:
        setattr(widget, after_attr, None)
        if not widget.winfo_exists():
            return  # closed mid-work — the worker's message is moot
        try:
            msg = q.get_nowait()
        except queue.Empty:
            arm()
            return
        on_result(msg)

    arm()
