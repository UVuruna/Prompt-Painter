"""The image-failure RECOVERY LADDER (BUG 3, owner 2026-07-21 +
escalation 2026-07-23) — its own responsibility, split out of
``painter/runner.py`` when the run loop crossed the god-file line
guard (THE STRUCTURE LAW, 2026-08-11).

ChatGPT's image tool fails in two faces, both matched by
``image_failed_text_markers`` and both arriving here as
``ImageGenFailed``: its own "reply with 'retry'" text, and the generic
"Hmm...something seems to have gone wrong." error turn (which also
renders a native Retry BUTTON). One ladder serves both, cheapest rung
first — see ``recover_image_failed``. ``interruptible_sleep`` is the
Stop-aware wait the ladder's minute-long rounds ride on; the runner's
own paced ``_pause`` shares it.
"""

from __future__ import annotations

import random
import time
from typing import Callable

from painter.config import (
    IMAGE_FAILED_ESCALATION_DELAYS_S,
    IMAGE_FAILED_RETRY_DELAY_RANGE_S,
    IMAGE_FAILED_RETRY_MAX,
    IMAGE_RETRY_NUDGE,
)
from painter.driver import (
    GenerationTimeout,
    ImageGenFailed,
    NoImage,
    SendNotConfirmed,
    SendVanished,
    SiteDriver,
)

# The verdicts a RUNG may fail with and still hand the ladder to the
# next rung (owner 2026-08-14, the 15:56:37 stop: rung 1's own
# await_done timed out after the Retry click, and only ImageGenFailed
# was caught — the GenerationTimeout flew past the runner's per-item
# handlers, which wrap this ladder in `except ItemRefused` alone, and
# killed the whole site. 0.0.271 fixed the runner's except sets but
# left the ladder's inside untouched). Quota (TerminalState) and
# refusals (ItemRefused) still propagate: the quota stop is correct,
# and the runner routes a mid-ladder refusal into the safer retry.
RUNG_FAILURES = (
    ImageGenFailed,
    GenerationTimeout,
    NoImage,
    SendVanished,
    SendNotConfirmed,
)

# structural aliases matching painter.runner's own (kept local — the
# runner imports THIS module, never the other way around)
Log = Callable[[str], None]
ShouldStop = Callable[[], bool]
OnEvent = Callable[[dict], None]


def interruptible_sleep(
    seconds: float, should_stop: ShouldStop | None, log: Log
) -> bool:
    """Sleep ``seconds``, waking every half-second to honour Stop.

    Shared by the runner's ``_pause`` (short paced waits) and the
    image-failure recovery ladder below (its retries and escalation
    rounds wait MINUTES — up to ~36 — so a Stop must never hang behind
    them). Returns True when Stop cut the wait short, False when it ran
    to completion; the ladder uses that to abandon the recovery
    immediately."""
    end = time.monotonic() + seconds
    while time.monotonic() < end:
        if should_stop is not None and should_stop():
            return True
        time.sleep(0.5)
    return False


def recover_image_failed(
    exc: ImageGenFailed,
    driver: SiteDriver,
    generate_one: Callable[..., tuple[bytes, float]],
    base: str,
    should_stop: ShouldStop | None,
    log: Log,
    emit: OnEvent,
    input_image_paths: list[str] | None = None,
) -> tuple[bytes, float]:
    """Walk the image-failure recovery ladder (owner 2026-07-23).

    Cheapest rung first:

      1. click the site's native Retry button, if it has one for this
         state and it is present — regenerates in place, no re-typing;
      2. resend ``IMAGE_RETRY_NUDGE`` up to ``IMAGE_FAILED_RETRY_MAX``
         times, each after a random ``IMAGE_FAILED_RETRY_DELAY_RANGE_S``
         wait (server hiccups and soft rate-limits clear on their own —
         hammering just re-fails);
      3. one escalation ROUND per ``IMAGE_FAILED_ESCALATION_DELAYS_S``
         entry: wait a random duration in that entry's range, then
         REFRESH the page, open a NEW SESSION, and resend the WHOLE
         original prompt (a fresh chat has no context, so "retry" alone
         would mean nothing) — RE-ATTACHING ``input_image_paths`` when
         the item carried "← `ref`" input image(s) (owner 2026-07-23;
         the earlier rungs stay in the same chat where the image(s)
         already sit, so only this new-session rung re-attaches).

    Returns ``(image bytes, send timestamp)`` from the first rung that
    yields an image. When every rung is spent the ladder re-raises
    ``ImageGenFailed`` — the worker STOPS (owner's "GASI"): finished
    items are safe on disk, so a restart resumes past them. A Stop
    request during any wait abandons the ladder the same way. Every
    per-item verdict in ``RUNG_FAILURES`` hands the ladder to the next
    rung (owner 2026-08-14 — rung 1's timeout used to kill the site); a
    quota/refusal that surfaces mid-recovery propagates loudly, exactly
    as on a first attempt."""
    reason = str(exc)

    # rung 1 — the site's own Retry button (same chat, no re-typing)
    try:
        if driver.click_error_retry(log):
            emit({"type": "item_retry"})
            t_send = time.monotonic()
            driver.await_done(log)
            data = driver.extract_image()
            log("    site Retry button RECOVERED")
            return data, t_send
    except RUNG_FAILURES as again:
        reason = str(again)

    # rung 2 — resend the site's own "retry" word, paced
    for attempt in range(1, IMAGE_FAILED_RETRY_MAX + 1):
        wait = random.uniform(*IMAGE_FAILED_RETRY_DELAY_RANGE_S)
        log(
            "    IMAGE GENERATION FAILED — waiting"
            f" {wait:.0f}s then sending '{IMAGE_RETRY_NUDGE}'"
            f" ({attempt}/{IMAGE_FAILED_RETRY_MAX}) ..."
        )
        if interruptible_sleep(wait, should_stop, log):
            log("    STOPPED on request during recovery")
            raise ImageGenFailed(reason)
        emit({"type": "item_retry"})
        try:
            data, t_send = generate_one(IMAGE_RETRY_NUDGE)
            log("    retry RECOVERED")
            return data, t_send
        except RUNG_FAILURES as again:
            reason = str(again)

    # rung 3 — escalation rounds: wait -> refresh -> new session ->
    # resend the whole original prompt. The new session has NO history,
    # so an input-image item must RE-ATTACH its reference here (the
    # earlier rungs stayed in the same chat where the image already sat).
    rounds = len(IMAGE_FAILED_ESCALATION_DELAYS_S)
    for rnd, (lo, hi) in enumerate(IMAGE_FAILED_ESCALATION_DELAYS_S, start=1):
        wait = random.uniform(lo, hi)
        log(
            f"    escalation round {rnd}/{rounds} — waiting"
            f" {wait / 60:.0f} min, then refresh + new session ..."
        )
        if interruptible_sleep(wait, should_stop, log):
            log("    STOPPED on request during recovery")
            raise ImageGenFailed(reason)
        emit({"type": "item_retry"})
        driver.refresh(log)
        driver.new_chat(log)
        try:
            data, t_send = generate_one(base, attach=input_image_paths)
            log(f"    escalation round {rnd} RECOVERED (fresh session)")
            return data, t_send
        except RUNG_FAILURES as again:
            reason = str(again)

    # every rung spent — stop the worker (finished work is safe on disk)
    log(f"    RECOVERY EXHAUSTED — stopping the site: {reason}")
    raise ImageGenFailed(reason)
