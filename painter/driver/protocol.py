"""``DriverProtocolMixin`` — putting ONE prompt into the composer and
proving it was sent.

The composer conversation: wait until the page is ready, type or paste
the prompt, attach an image when the item carries one, click send, then
CONFIRM the send actually landed (a vanished or unconfirmed send is its
own typed error, never a silent retry). ``capture_baseline`` takes the
pre-submit snapshot the wait half is judged against.

Split from the 1,599-line ``painter/driver.py`` (audit
``docs/AUDIT-OOP-2026-08-18.md`` → R4).
"""

from __future__ import annotations

import random
import time
from typing import Callable

from playwright.sync_api import TimeoutError as PlaywrightTimeoutError

from painter.config import SEND_RELOAD_RECOVERY

from .errors import (
    AttachNotConfigured,
    DriverError,
    SelectorRot,
    SendNotConfirmed,
)
from .values import Baseline, normalize_text

Log = Callable[[str], None]

# how much of the prompt's normalized head must be found when
# verifying the composer content / the sent user turn (F1 protocol)
VERIFY_PREFIX_CHARS = 60


class DriverProtocolMixin:
    """One prompt in, provably sent. Mixed into ``SiteDriver`` —
    never instantiated alone."""

    def _hesitate(self) -> None:
        """A human-like random pause between UI actions (config range)."""
        time.sleep(
            random.uniform(
                self._timing.action_delay_min_s,
                self._timing.action_delay_max_s,
            )
        )

    def _composer_text(self) -> str | None:
        """The prompt box's current text; None when the box itself is
        missing (selector rot territory — callers stay loud)."""
        box = self._query(self.site.prompt_box)
        return None if box is None else box.inner_text()

    def _busy(self) -> bool:
        """Is the site generating right now (stop button visible)?"""
        return self._query(self.site.busy_signal) is not None

    def capture_baseline(self) -> Baseline:
        """Snapshot the page BEFORE a submit (F1 protocol)."""
        # a fresh submit starts a fresh answer — never let the PREVIOUS
        # item's text pose as this one's in the transcript log
        self.last_response_text = ""
        self._baseline = Baseline(
            turn_count=self._turns_count(),
            last_img_src=self._last_image_src(),
            user_turn_count=self._user_turns_count(),
            error_turn_count=self._error_turns_count(),
        )
        return self._baseline

    def _ensure_ready(self, log: Log) -> None:
        """Never send over a busy composer (F1, root cause 1 — the
        STUCK button). LIVE-RUN HOTFIX (owner 2026-07-29): a busy
        signal here can be a PREVIOUS generation still honestly
        running (e.g. after a per-item skip) — refreshing after a
        short grace KILLED it mid-work. Now the driver WAITS it out —
        but only for ``busy_stuck_timeout_s``, its OWN budget, never
        the full ``generation_timeout_s``.

        LIVE-RUN FIX (owner 2026-08-04, read off a real run's log): the
        previous item's stop button stayed set AFTER its image had been
        saved, and this wait honestly burned the whole 420s generation
        timeout — 7 silent minutes between two ChatGPT items. Two
        changes: (a) when ``await_done`` already saw the busy signal set
        at the moment OUR image loaded, the button is PROVABLY stuck and
        the page is refreshed AT ONCE — no wait at all; (b) an otherwise
        unexplained busy signal gets ``busy_stuck_timeout_s`` and then a
        refresh. Every branch says out loud what it is doing and how
        long it intends to wait."""
        if not self._busy():
            self._busy_known_stuck = False
            return
        t = self._timing
        if self._busy_known_stuck:
            log(
                f"    {self.site.name}: busy signal STILL set although"
                " our previous image already arrived — the stop button"
                " is stuck, not a running generation; refreshing the"
                " page now instead of waiting it out"
            )
            self._busy_known_stuck = False
            self.refresh(log)
            return
        log(
            f"    {self.site.name}: site still busy before send —"
            " waiting up to"
            f" {t.busy_stuck_timeout_s:.0f}s for the previous"
            " generation to finish (then a page refresh)"
        )
        start = time.monotonic()
        deadline = start + t.busy_stuck_timeout_s
        last_log = start
        while time.monotonic() < deadline:
            if not self._busy():
                log(
                    "    the previous generation finished after"
                    f" {time.monotonic() - start:.0f}s — sending now"
                )
                return
            now = time.monotonic()
            if now - last_log >= t.progress_log_interval_s:
                log(
                    "    ... still busy before send"
                    f" ({now - start:.0f}s of"
                    f" {t.busy_stuck_timeout_s:.0f}s)"
                )
                last_log = now
            time.sleep(t.poll_interval_s)
        log(
            "    busy signal outlived its"
            f" {t.busy_stuck_timeout_s:.0f}s budget — treating it as"
            " stuck; refreshing the page before send"
        )
        self.refresh(log)

    def _type_into_box(self, prompt: str) -> None:
        """Click the prompt box, clear it ONLY when it holds text
        (owner 2026-07-29: "ako je empty ne treba delete"), paste
        ``prompt`` verbatim, then VERIFY the composer really holds our
        text — one silent re-type on mismatch, loud failure after."""
        box = self._require(self.site.prompt_box, "the prompt box")
        self._hesitate()
        box.click()
        self._hesitate()
        current = self._composer_text()
        if current is not None and current.strip():
            self.page.keyboard.press("Control+A")
            self._hesitate()
            self.page.keyboard.press("Delete")
            self._hesitate()
        self.page.keyboard.insert_text(prompt)
        self._hesitate()
        if self._composer_holds(prompt):
            return
        # one retype: clear whatever landed and paste again
        self.page.keyboard.press("Control+A")
        self._hesitate()
        self.page.keyboard.press("Delete")
        self._hesitate()
        self.page.keyboard.insert_text(prompt)
        self._hesitate()
        if not self._composer_holds(prompt):
            raise DriverError(
                f"{self.site.name}: the composer does not hold the"
                " typed prompt after two attempts — box state:"
                f" {str(self._composer_text())[:120]!r}"
            )

    def _composer_holds(self, prompt: str) -> bool:
        """Does the composer text start with our prompt's head?"""
        text = self._composer_text()
        if text is None:
            return False
        head = normalize_text(prompt)[:VERIFY_PREFIX_CHARS]
        return normalize_text(text).startswith(head)

    def _click_send(
        self,
        prompt: str,
        log: Log,
        *,
        retrying: bool = False,
        reattach: Callable[[], None] | None = None,
    ) -> None:
        """Locate + click the send button.

        Owner 2026-07-21 (a real run's exact failure): "no selector
        for the send button matched within 10s ... site stopped" — a
        manual page REFRESH fixed it. So on THIS specific miss (not
        any other selector), do a ONE-TIME recovery instead of raising
        straight away: reload the page, re-type the prompt (the reload
        wipes it), and retry the send lookup exactly once. ``retrying``
        guards the recursion to a single attempt — a second miss (or
        ``SEND_RELOAD_RECOVERY`` off) raises ``SelectorRot`` same as
        always.

        ``reattach`` (owner 2026-07-23 / review finding) RE-RUNS the
        image attach after the reload: a ``reload()`` wipes not only the
        composer text but any attached image, so for ``submit_with_image``
        the recovery must re-attach BEFORE re-typing — otherwise it would
        silently send a text-only prompt under the reference-image
        filename (a Rule #1 violation). None for a plain text submit.
        """
        try:
            send = self._require(self.site.send_button, "the send button")
        except SelectorRot:
            if retrying or not SEND_RELOAD_RECOVERY:
                raise
            log(
                f"    {self.site.name}: send button missing — reloading"
                " the page and re-pasting once (recovery)"
            )
            self.page.reload()
            if reattach is not None:
                log("    re-attaching the image the reload dropped")
                reattach()
            self._type_into_box(prompt)
            self._click_send(prompt, log, retrying=True, reattach=reattach)
            return
        send.click()

    def _paste_and_send(
        self,
        prompt: str,
        log: Log = print,
        reattach: Callable[[], None] | None = None,
    ) -> None:
        """Type the prompt then click send — the paste+send tail
        shared by ``submit_prompt`` (text only) and ``submit_with_image``
        (image attach + prompt). ``reattach`` re-runs the image attach on
        the send-button reload recovery (see ``_click_send``); None for a
        plain text submit."""
        self._type_into_box(prompt)
        self._click_send(prompt, log, reattach=reattach)

    def submit_prompt(self, prompt: str, log: Log = print) -> None:
        """Paste the prompt byte-identical and press send — with a
        person's rhythm — then CONFIRM the send took (F1 protocol):
        composer emptied AND our text visible as the newest user turn.
        Never assumes; a send that cannot be confirmed fails loudly."""
        self._ensure_ready(log)
        self.capture_baseline()
        self._paste_and_send(prompt, log)
        self._confirm_sent(prompt, log)
        self._sent_norm = normalize_text(prompt)
        self._sent_head = self._sent_norm[:VERIFY_PREFIX_CHARS]

    def _confirm_sent(self, prompt: str, log: Log) -> None:
        """Block until the send is CONFIRMED (owner 2026-07-29): the
        composer is empty again AND the newest USER turn holds our
        prompt's head. When the site's ``user_turn`` selector matches
        nothing (not configured / rotted), the documented LOUD fallback
        is "composer emptied + busy signal appeared". At half the
        confirm window the send is retried once (click + Enter). A
        window spent without confirmation raises — the runner never
        proceeds on an unsent prompt (root cause of the silent-skip
        and duplicate-save bugs)."""
        t = self._timing
        head = normalize_text(prompt)[:VERIFY_PREFIX_CHARS]
        deadline = time.monotonic() + t.send_confirm_timeout_s
        halfway = time.monotonic() + t.send_confirm_timeout_s / 2
        retried = False
        user_turn_seen = False
        while time.monotonic() < deadline:
            composer = self._composer_text()
            composer_empty = composer is not None and not composer.strip()
            busy = self._busy()
            user_text = self._last_user_turn_text()
            if user_text is not None:
                user_turn_seen = True
                # LIVE-RUN HOTFIX (owner 2026-07-29): a BUSY signal is
                # as good as an emptied composer — the site is already
                # generating our turn (a lingering placeholder/ghost in
                # the composer read must not block confirmation)
                if (composer_empty or busy) and (
                    head in normalize_text(user_text)
                ):
                    return  # confirmed: our text IS the newest user turn
            elif composer_empty and busy:
                # documented fallback: no user-turn selector matched —
                # loud, never silent (the run continues on the weaker
                # "composer emptied + busy appeared" evidence)
                log(
                    f"    {self.site.name}: user-turn selector matched"
                    " nothing — confirming send by composer+busy only"
                    " (verify user_turn selectors in config.sites)"
                )
                return
            # LIVE-RUN HOTFIX: never retry while the site is BUSY —
            # the morphed composer button is a STOP button then, and
            # clicking it KILLED the very generation we started
            if not retried and not busy and time.monotonic() >= halfway:
                log("    send not confirmed yet — retrying (click + Enter)")
                self._retry_send()
                retried = True
            time.sleep(t.poll_interval_s)
        raise SendNotConfirmed(
            f"{self.site.name}: send NOT confirmed within"
            f" {t.send_confirm_timeout_s:.0f}s — composer:"
            f" {str(self._composer_text())[:80]!r}, newest user turn"
            f" {'seen' if user_turn_seen else 'NOT seen'} — the prompt"
            " was not accepted; nothing was submitted silently"
        )

    def submit_with_image(
        self, image_path: str | list[str], prompt: str, log: Log = print
    ) -> None:
        """Attach image(s) into the composer, then paste+send ``prompt``.

        The shared "image + text" submit, used BOTH by input-image sheet
        entries (the ``← `ref``` reference photo — "put THIS character
        into that scene", owner 2026-07-23) and by WEBSITE FIX
        (re-attaching a flagged output for a focused correction). The
        prompt text carries the intent; the mechanics are identical.

        MULTI-ATTACH (faza 2, owner 2026-08-03): ``image_path`` may be a
        LIST of resolved paths (a sheet entry with several ``←`` lines —
        the dual plates attach two references); list order is attach
        order, matching the prompt's "FIRST/SECOND attached image". All
        files ride ONE picker interaction (``set_input_files``/
        ``set_files`` accept a list) — a site whose picker refuses
        multiple files raises loudly there (Rule #1), never silently
        attaching fewer than the sheet declared.

        Acts like a PERSON (owner 2026-07-23): EXPAND the composer's "+"
        menu, THEN pick the add-image option — never click a hidden
        upload item directly. Every step is paced by the same
        human-rhythm ``_hesitate`` used across this driver (honouring the
        owner's configured action-delay range). Then:
        - if the site exposes the hidden ``file_input`` (ChatGPT's
          ``#upload-photos``), set files on it directly — robust, no OS
          dialog;
        - else (Gemini) the last menu click opens the OS file dialog,
          caught with Playwright's file-chooser interception.
        Once the file is set the driver WAITS for the composer's
        attachment ``attach_preview`` (up to ``image_ready_timeout_s``)
        before sending, so the prompt never goes out ahead of the image.

        GATED: raises ``AttachNotConfigured`` immediately — before
        touching the page at all — while this site's ``attach_menu_path``
        is empty. Real selectors are the OWNER's job (see the SiteConfig
        field comment); this method never guesses them.

        Only SUBMITS. Awaiting the done edge and reading the image back
        reuse the EXISTING ``await_done``/``extract_image`` unchanged —
        the caller invokes them next, exactly as after ``submit_prompt``.
        """
        self._ensure_ready(log)
        self.capture_baseline()
        self._attach_image(image_path)
        self._hesitate()
        # reattach: a send-button reload recovery would drop the image, so
        # re-run the whole attach before re-typing (review finding)
        self._paste_and_send(
            prompt, log, reattach=lambda: self._attach_image(image_path)
        )
        self._confirm_sent(prompt, log)
        self._sent_norm = normalize_text(prompt)
        self._sent_head = self._sent_norm[:VERIFY_PREFIX_CHARS]

    def _attach_image(self, image_path: str | list[str]) -> None:
        """Walk the "+" menu like a person and attach ``image_path`` (one
        path, or a LIST in attach order — faza 2 multi-attach), then
        wait for the composer preview — the attach half of
        ``submit_with_image``, extracted so the send-button reload
        recovery can RE-ATTACH after a ``reload()`` drops the image
        (owner 2026-07-23 / review finding). Idempotent: re-opening the
        menu and re-setting the file(s) is exactly what the recovery
        needs. A single path is passed through UNWRAPPED (the picker
        APIs accept both forms; the single form is the long-proven one).

        GATED: raises ``AttachNotConfigured`` immediately while this
        site's ``attach_menu_path`` is empty — never a guessed selector.
        """
        if isinstance(image_path, list) and len(image_path) == 1:
            image_path = image_path[0]
        if not self.site.attach_menu_path:
            raise AttachNotConfigured(
                f"{self.site.name}: image attach is not configured —"
                " attach_menu_path is empty in SITES; the owner must"
                " capture the live '+' menu selectors first (see"
                " config.py's SiteConfig comment) before this can run"
            )
        steps = self.site.attach_menu_path
        # walk the "+" menu like a person: expand, then every step but
        # the last (the add-image option itself is handled below, since
        # its click either reveals the input or opens the file dialog)
        for selectors in steps[:-1]:
            control = self._require(selectors, "an attach-menu control")
            self._hesitate()
            control.click()
            self._hesitate()
        if self.site.file_input:
            # the option drives a hidden <input type=file>. LIVE-RUN FIX
            # (owner 2026-08-04): ChatGPT's "Add photos & files" row is
            # itself the "Upload from computer" action — clicking it
            # opens the NATIVE OS file dialog, which Playwright cannot
            # close, so every attach left an Explorer window standing
            # open beside the browser. The input is already in the DOM
            # once the "+" menu is expanded, so we set files on it
            # DIRECTLY and never click the row. The click stays only as
            # the fallback for a menu that renders its input lazily —
            # wrapped in file-chooser interception so a dialog that does
            # open is consumed, not left on screen.
            file_input = self._query(
                self.site.file_input, require_visible=False
            )
            if file_input is None:
                option = self._require(
                    steps[-1], "the add-image menu option"
                )
                self._hesitate()
                try:
                    with self.page.expect_file_chooser() as chooser:
                        option.click()
                    chooser.value.set_files(image_path)
                except PlaywrightTimeoutError:
                    # the click only REVEALED the input, no dialog
                    self._require(
                        self.site.file_input, "the file input",
                        require_visible=False,
                    ).set_input_files(image_path)
            else:
                file_input.set_input_files(image_path)
                # the "+" menu is still expanded — close it so the
                # composer is clean before the prompt is typed
                self.page.keyboard.press("Escape")
            self._hesitate()
        else:
            option = self._require(steps[-1], "the add-image menu option")
            # no exposed input — the option opens the OS file dialog;
            # Playwright intercepts it and we set the file programmatically
            self._hesitate()
            with self.page.expect_file_chooser() as chooser:
                option.click()
            chooser.value.set_files(image_path)
        # wait for the upload to FINISH (its preview appears) before send
        # — a large reference photo can take a few seconds, so this uses
        # the image-ready timeout, not the short selector timeout
        if self.site.attach_preview:
            self._require(
                self.site.attach_preview,
                "the attached-image preview",
                timeout_s=self._timing.image_ready_timeout_s,
            )
