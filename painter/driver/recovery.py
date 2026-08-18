"""``DriverRecoveryMixin`` — the ladder the runner climbs when a send or
a generation failed: click the site's own Retry, refresh the tab,
re-send the last prompt, or start a NEW CHAT.

Each rung is a separate public step so the runner decides how far to
climb (``painter/recovery.py`` owns that policy); this mixin only knows
how to perform one rung on the DOM.

Split from the 1,599-line ``painter/driver.py`` (audit
``docs/AUDIT-OOP-2026-08-18.md`` → R4).
"""

from __future__ import annotations

from typing import Callable

from .errors import DriverError
from .values import Baseline

Log = Callable[[str], None]


class DriverRecoveryMixin:
    """One rung of the recovery ladder at a time. Mixed into
    ``SiteDriver`` — never instantiated alone."""

    def new_chat(self, log: Log = print) -> None:
        """Open a fresh conversation (the sidebar's New chat control).

        Loud when the control cannot be found — the caller decides
        whether that stops the run (it should not: the old chat still
        works, only longer)."""
        button = self._require(self.site.new_chat, "the New chat control")
        self._hesitate()
        button.click()
        self._hesitate()
        # the fresh composer must be there before the next paste
        self._require(self.site.prompt_box, "the prompt box (new chat)")
        # a fresh conversation restarts the turn numbering — the next
        # submit captures a fresh baseline (F1) and its own anchor (F1b)
        self._baseline = None
        self._sent_head = None
        log("    new chat opened")

    def click_error_retry(self, log: Log = print) -> bool:
        """Click the site's native "Retry" button on an image-error turn.

        The first, cheapest rung of the image-failure ladder (owner
        2026-07-23): ChatGPT's "Hmm...something seems to have gone
        wrong." turn carries a Retry button that regenerates in place.
        Returns True when a button was found AND clicked (the caller
        then waits for the regenerated image); False when the site
        defines no such button, or none is present right now — the
        caller falls through to the next rung. Never loud: a missing
        button is a normal branch, not selector rot.

        F1 note: the regeneration happens IN PLACE (no new user turn;
        the error turn is replaced), so the baseline is re-anchored one
        turn BACK — the regenerated last turn then counts as "new" for
        ``await_done``/``extract_image``."""
        if not self.site.image_error_retry_button:
            return False
        button = self._query(self.site.image_error_retry_button)
        if button is None:
            return False
        self._hesitate()
        button.click()
        self._hesitate()
        prev = self._baseline
        self._baseline = Baseline(
            turn_count=max(0, self._turns_count() - 1),
            last_img_src=(
                prev.last_img_src if prev is not None
                else self._last_image_src()
            ),
            # the regeneration is IN PLACE — no new user turn, so the
            # F1b anchor (our user turn + the pre-submit user count)
            # carries over unchanged
            user_turn_count=(
                prev.user_turn_count if prev is not None
                else max(0, self._user_turns_count() - 1)
            ),
            # the clicked error turn is being replaced by the
            # regeneration; re-read the count NOW so the thread-error
            # check judges the regeneration on its own merits and
            # never re-fires on the error we just handled
            error_turn_count=self._error_turns_count(),
        )
        log("    clicked the site's Retry button")
        return True

    def refresh(self, log: Log = print) -> None:
        """Reload the page, then wait for the composer to come back.

        A last-resort rung of the image-failure ladder (owner
        2026-07-23): the session cookies live in the profile on disk,
        so the reload keeps the login; only the (possibly wedged) page
        state is thrown away. The fresh composer must be present before
        the caller pastes the next prompt — loud if it never returns.

        SECOND CHANCE (owner 2026-08-11, the 14:52:32 stop): a single
        slow reload — the composer simply not painted within
        ``selector_timeout_s`` — ended a ChatGPT run at 38/69
        collections. A reload that lands slowly is ordinary web
        behaviour, not selector rot, so it earns ONE more reload with a
        doubled budget before the loud raise. If the composer is gone
        after that, it is gone for real and the raise stands."""
        self.page.reload()
        try:
            self._require(
                self.site.prompt_box, "the prompt box (after refresh)"
            )
        except DriverError:
            log("    composer did not come back — one more reload ...")
            self.page.reload()
            self._require(
                self.site.prompt_box,
                "the prompt box (after refresh)",
                timeout_s=self._timing.selector_timeout_s * 2,
            )
        log("    page refreshed")

    def _retry_send(self) -> None:
        """Second chance for a submit that did not take: click the send
        button again if present, then Enter in the prompt box (both
        sites send on Enter). Harmless when the text already went —
        Enter on an empty box does nothing.

        LIVE-RUN HOTFIX (owner 2026-07-29): a BUSY site is proof the
        send took — and ChatGPT's composer button IS the Stop button
        while generating (same element id), so clicking it here KILLED
        the running generation. Never retry over a busy signal."""
        if self._busy():
            return
        send = self._query(self.site.send_button)
        if send is not None:
            self._hesitate()
            try:
                send.click()
            except Exception:
                pass  # a blocked click here is fine — the await loop
                # times out loudly if nothing ever takes
        box = self._query(self.site.prompt_box)
        if box is not None:
            self._hesitate()
            box.click()
            self._hesitate()
            self.page.keyboard.press("Enter")
