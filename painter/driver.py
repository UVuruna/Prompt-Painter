"""CDP driver — drives the owner's already-open, logged-in tab.

Chrome runs with ``--remote-debugging-port=9222`` (the launcher
opens it with the dedicated automation profile); the driver
attaches over CDP and works the DOM. No Download
clicks: when the generated <img> appears, its bytes are read straight
from the DOM (fetch inside the page, base64 back) — the tool names
and saves files itself.

Every DOM hook comes from the site's config block; when no fallback
selector matches, the driver fails LOUDLY (SelectorRot) instead of
guessing. Quota/refusal responses are TERMINAL (TerminalState) —
reported and stopped, never blind-retried.
"""

from __future__ import annotations

import base64
import random
import time
from typing import Callable

from playwright.sync_api import Locator, Page, sync_playwright

from painter.config import (
    MIN_IMAGE_PX,
    SEND_RELOAD_RECOVERY,
    SiteConfig,
    Timing,
    parse_quota_reset,
)

Log = Callable[[str], None]


class DriverError(RuntimeError):
    """The DOM is not in a state the config block recognizes."""


class SelectorRot(DriverError):
    """No fallback selector matched — the site reskinned; fix config."""


class TerminalState(DriverError):
    """Quota/rate limit — stop the whole site, never blind-retry.

    ``retry_after_s`` is the wait the site itself named ("limit
    resets in 27 minutes"), parsed via the config's
    ``QUOTA_RESET_PATTERNS``; None when the message carried no
    parseable time.
    """

    def __init__(self, message: str, retry_after_s: float | None = None):
        super().__init__(message)
        self.retry_after_s = retry_after_s


class ItemRefused(DriverError):
    """The site refused THIS prompt — the runner reports it, then either
    skips the item or SAFER-RETRIES it once, and continues with the rest.

    ``category`` names the refusal SCENARIO it was classified into
    (``REFUSAL_SAFETY`` / ``REFUSAL_COPYRIGHT``, the keys of the site's
    ``refusal_markers``) so the runner can pick the matching retry
    preamble from ``RETRY_PREAMBLES`` — a violence block and a
    copyright block need opposite reframings (owner 2026-07-23)."""

    def __init__(self, message: str, category: str):
        super().__init__(message)
        self.category = category


class GenerationTimeout(DriverError):
    """The done edge never came within the hard timeout."""


class NoImage(DriverError):
    """The done edge fired (or the busy signal never appeared) but no
    generated image loaded, and the response text matches no refusal /
    quota marker — an UNKNOWN DOM state (empty answer, selector rot, or
    ChatGPT simply stalling mid-generation). Distinct from the generic
    ``DriverError`` so the runner can catch JUST this and try a one-shot
    "continue" nudge before giving up (the owner's recurring stuck-
    ChatGPT case). If the nudge does not recover it, it propagates like
    any other ``DriverError`` and the site stops loudly."""


class ImageGenFailed(DriverError):
    """ChatGPT's image tool failed outright — the assistant's OWN text
    already names the failure (e.g. "Image generation failed ... I
    can't retry it automatically after this kind of failure ... reply
    with 'retry'"), matched against the site's
    ``image_failed_text_markers`` (owner 2026-07-21, BUG 3). Distinct
    from ``NoImage`` (matches NO known marker — an unknown DOM state)
    and from ``ItemRefused``/``TerminalState`` (real refusal/quota
    markers): this state is recognized WHILE the busy/stop signal is
    still present (it never clears for this failure, so the done edge
    would never come) — ``await_done`` raises it immediately instead
    of burning the whole ``generation_timeout_s``. The runner catches
    it and resends the site's own suggested word ("retry") into the
    same chat, up to a configured number of attempts, before giving up
    on the item."""


class FixNotConfigured(DriverError):
    """WEBSITE FIX (``submit_fix``, GUI rework Phase 17) is disabled
    for this site — its ``attach_button``/``file_input`` selectors are
    empty in ``SITES`` (the shipped default for BOTH chatgpt and
    gemini). The owner must capture the live selectors first, the same
    way every other selector in this file was captured, and paste them
    into the site's config block. Raised immediately, before
    ``submit_fix`` touches the page at all — never a guessed
    selector."""


# Runs on the <img> element inside the page. Canvas first: site CSP
# (Gemini's connect-src) blocks fetch() of blob: URLs, while drawing
# the already-loaded <img> onto a canvas needs no request at all —
# and always yields real PNG bytes. fetch() stays as the fallback
# for images a canvas cannot read (cross-origin without CORS).
_FETCH_IMAGE_JS = """
async (el) => {
  const errors = [];
  try {
    const c = document.createElement('canvas');
    c.width = el.naturalWidth;
    c.height = el.naturalHeight;
    c.getContext('2d').drawImage(el, 0, 0);
    return c.toDataURL('image/png').split(',', 2)[1];
  } catch (e) { errors.push(`canvas: ${e}`); }
  try {
    const resp = await fetch(el.src);
    if (!resp.ok) throw new Error(`HTTP ${resp.status}`);
    const blob = await resp.blob();
    return await new Promise((resolve, reject) => {
      const r = new FileReader();
      r.onload = () => resolve(r.result.split(',', 2)[1]);
      r.onerror = () => reject(r.error);
      r.readAsDataURL(blob);
    });
  } catch (e) { errors.push(`fetch ${el.src}: ${e}`); }
  throw new Error(errors.join(' | '));
}
"""

_MAGIC = (
    (b"\x89PNG\r\n\x1a\n", "png"),
    (b"\xff\xd8\xff", "jpeg"),
    (b"GIF8", "gif"),
    (b"RIFF", "webp"),  # RIFF....WEBP, checked further below
)


def sniff_format(data: bytes) -> str | None:
    """Best-effort image format from magic bytes; None if unknown."""
    for magic, name in _MAGIC:
        if data.startswith(magic):
            if name == "webp" and data[8:12] != b"WEBP":
                continue
            return name
    return None


class SiteDriver:
    """One attached tab of one site, driven through its config block."""

    def __init__(self, site: SiteConfig, timing: Timing, cdp_url: str):
        self.site = site
        self._timing = timing
        self._cdp_url = cdp_url
        self._pw = None
        self._browser = None
        self.page: Page | None = None

    # --- lifecycle ----------------------------------------------------

    def attach(self) -> str:
        """Connect over CDP and adopt the open site tab; returns its title."""
        self._pw = sync_playwright().start()
        try:
            self._browser = self._pw.chromium.connect_over_cdp(self._cdp_url)
        except Exception as exc:
            self._pw.stop()
            self._pw = None
            raise DriverError(
                f"cannot attach to Chrome at {self._cdp_url} — start Chrome"
                " once with: chrome.exe --remote-debugging-port=9222"
            ) from exc

        pages = [p for ctx in self._browser.contexts for p in ctx.pages]
        matches = [p for p in pages if self.site.url_fragment in p.url]
        if not matches:
            open_tabs = ", ".join(p.url for p in pages) or "(none)"
            self.close()
            raise DriverError(
                f"no open {self.site.name} tab — looked for"
                f" '{self.site.url_fragment}' among: {open_tabs}"
            )
        # several site tabs: drive the last (most recently opened) one
        self.page = matches[-1]
        self.page.set_default_timeout(
            self._timing.busy_appear_timeout_s * 1000
        )
        self.page.bring_to_front()
        return self.page.title()

    def close(self) -> None:
        """Detach from Chrome (never closes the owner's browser)."""
        if self._browser is not None:
            self._browser.close()
            self._browser = None
        if self._pw is not None:
            self._pw.stop()
            self._pw = None
        self.page = None

    # --- the per-item protocol -----------------------------------------

    def _hesitate(self) -> None:
        """A human-like random pause between UI actions (config range)."""
        time.sleep(
            random.uniform(
                self._timing.action_delay_min_s,
                self._timing.action_delay_max_s,
            )
        )

    def _type_into_box(self, prompt: str) -> None:
        """Click the prompt box, select-all + delete, paste ``prompt``
        verbatim — the typing half of ``_paste_and_send``, factored out
        so the send-button reload recovery (below) can re-type after a
        ``page.reload()`` wipes the composer's unsent text."""
        box = self._require(self.site.prompt_box, "the prompt box")
        self._hesitate()
        box.click()
        self._hesitate()
        self.page.keyboard.press("Control+A")
        self._hesitate()
        self.page.keyboard.press("Delete")
        self._hesitate()
        self.page.keyboard.insert_text(prompt)
        self._hesitate()

    def _click_send(
        self, prompt: str, log: Log, *, retrying: bool = False
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
            self._type_into_box(prompt)
            self._click_send(prompt, log, retrying=True)
            return
        send.click()

    def _paste_and_send(self, prompt: str, log: Log = print) -> None:
        """Type the prompt then click send — the paste+send tail
        shared by ``submit_prompt`` (text only) and ``submit_fix``
        (image attach + follow-up prompt, GUI rework Phase 17). This is
        ``submit_prompt``'s original body, extracted unchanged (plus
        the send-button reload recovery in ``_click_send``) so both
        entry points end the same human-paced way."""
        self._type_into_box(prompt)
        self._click_send(prompt, log)

    def submit_prompt(self, prompt: str, log: Log = print) -> None:
        """Paste the prompt byte-identical and press send — with a
        person's rhythm (click ... paste ... send), never instant."""
        self._paste_and_send(prompt, log)

    def submit_fix(
        self, image_path: str, prompt: str, log: Log = print
    ) -> None:
        """WEBSITE FIX (GUI rework Phase 17): re-attach a previously
        generated image into the SAME chat and paste+send a follow-up
        ``prompt`` asking the site to correct it — the AI Checker's
        flagged defects turned into a focused fix note instead of a
        blind full regeneration.

        GATED: raises ``FixNotConfigured`` immediately — before
        touching the page at all — while this site's
        ``attach_button``/``file_input`` are empty (the shipped
        default for both chatgpt and gemini). Real selectors are the
        OWNER's job: capture them from the live DOM, exactly like
        every other selector in ``SITES``, and paste them into the
        site's config block; this method never guesses them.

        Only SUBMITS the fix (attaches the image, pastes+sends the
        prompt). Awaiting the done edge and reading the corrected
        image back reuse the EXISTING ``await_done``/``extract_image``
        unchanged — the caller invokes them next, exactly as after
        ``submit_prompt``.
        """
        if not self.site.attach_button or not self.site.file_input:
            raise FixNotConfigured(
                f"{self.site.name}: WEBSITE FIX is not configured —"
                " attach_button/file_input are empty in SITES; the"
                " owner must capture the live selectors first (see"
                " config.py's SiteConfig comment) before this feature"
                " can run"
            )
        attach = self._require(
            self.site.attach_button, "the attach/upload control"
        )
        self._hesitate()
        attach.click()
        self._hesitate()
        # File inputs are routinely hidden by design (a styled attach
        # button drives them via JS) — Playwright's set_input_files
        # does not require visibility the way a real click does, so
        # this lookup does not filter on is_visible() either.
        file_input = self._require(
            self.site.file_input, "the file input", require_visible=False
        )
        file_input.set_input_files(image_path)
        # No dedicated "upload complete" selector is configured (only
        # attach_button/file_input, per this phase's scope) — the same
        # human-rhythm pause used everywhere else in this driver
        # stands in for "let it settle". If a real site needs a
        # stronger signal (e.g. a thumbnail preview appearing), that
        # is a follow-up config addition once the owner captures it
        # live.
        self._hesitate()
        self._paste_and_send(prompt, log)

    def await_done(self, log: Log = print) -> None:
        """Watch the done edge: the busy signal appears, then goes.

        A submit does not always take (the send button can be
        momentarily blocked) — while the busy signal is missing, the
        send is retried every ``send_retry_after_s`` before the loud
        give-up at the hard timeout.
        """
        t = self._timing
        start = time.monotonic()

        deadline = start + t.busy_appear_timeout_s
        next_retry = start + t.send_retry_after_s
        while self._query(self.site.busy_signal) is None:
            now = time.monotonic()
            if now > deadline:
                self._raise_no_image(
                    "the busy signal never appeared after submit"
                    " (send retried)"
                )
            if now >= next_retry:
                log("    send did not take — retrying (click + Enter)")
                self._retry_send()
                next_retry = time.monotonic() + t.send_retry_after_s
            time.sleep(t.poll_interval_s)

        deadline = time.monotonic() + t.generation_timeout_s
        last_log = time.monotonic()
        while self._query(self.site.busy_signal) is not None:
            now = time.monotonic()
            if now > deadline:
                raise GenerationTimeout(
                    f"{self.site.name}: no done edge after"
                    f" {t.generation_timeout_s:.0f}s (hard timeout)"
                )
            # BUG 3 (owner 2026-07-21): ChatGPT's "Image generation
            # failed" answer leaves the busy/stop signal stuck FOREVER
            # — the done edge this loop waits for never comes. Scan the
            # response text on EVERY poll so the failure is caught in
            # seconds instead of burning the whole hard timeout; a
            # no-op wherever the site names no such marker (Gemini).
            self._check_image_failed()
            if now - last_log >= t.progress_log_interval_s:
                log(f"    ... still generating ({now - start:.0f}s)")
                last_log = now
            time.sleep(t.poll_interval_s)

    def extract_image(self) -> bytes:
        """Read the generated image's bytes straight from the DOM.

        While waiting for a real <img>, the response text is checked
        every poll — a refusal or quota answer raises immediately
        instead of burning the whole image timeout.
        """
        t = self._timing
        deadline = time.monotonic() + t.image_ready_timeout_s
        while True:
            try:
                img = self._last_result_image()
            except SelectorRot:
                # the response container can be TRANSIENTLY absent
                # (route transition, list virtualization) — keep
                # polling; the deadline below stays the loud stop
                img = None
            if img is not None:
                break
            self._check_markers()
            if time.monotonic() > deadline:
                self._raise_no_image(
                    "the response holds no loaded generated image"
                )
            time.sleep(t.poll_interval_s)
        b64 = img.evaluate(_FETCH_IMAGE_JS)
        return base64.b64decode(b64)

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
        button is a normal branch, not selector rot."""
        if not self.site.image_error_retry_button:
            return False
        button = self._query(self.site.image_error_retry_button)
        if button is None:
            return False
        self._hesitate()
        button.click()
        self._hesitate()
        log("    clicked the site's Retry button")
        return True

    def refresh(self, log: Log = print) -> None:
        """Reload the page, then wait for the composer to come back.

        A last-resort rung of the image-failure ladder (owner
        2026-07-23): the session cookies live in the profile on disk,
        so the reload keeps the login; only the (possibly wedged) page
        state is thrown away. The fresh composer must be present before
        the caller pastes the next prompt — loud if it never returns."""
        self.page.reload()
        self._require(self.site.prompt_box, "the prompt box (after refresh)")
        log("    page refreshed")

    def _retry_send(self) -> None:
        """Second chance for a submit that did not take: click the send
        button again if present, then Enter in the prompt box (both
        sites send on Enter). Harmless when the text already went —
        Enter on an empty box does nothing."""
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

    # --- DOM plumbing ---------------------------------------------------

    def _query(
        self, selectors: tuple[str, ...], require_visible: bool = True
    ) -> Locator | None:
        """First match across the fallback selectors, else None.

        ``require_visible=False`` skips the ``is_visible()`` filter —
        for elements legitimately hidden by design (see ``_require``).
        """
        for sel in selectors:
            loc = self.page.locator(sel)
            for k in range(loc.count()):
                cand = loc.nth(k)
                if not require_visible or cand.is_visible():
                    return cand
        return None

    def _require(
        self,
        selectors: tuple[str, ...],
        what: str,
        require_visible: bool = True,
    ) -> Locator:
        """Wait for any fallback selector to match; loud after timeout.

        Sites are async SPAs — elements morph a beat after input
        events (the ChatGPT composer button turns into its send
        state only once the pasted text lands), so a one-shot query
        would fail on honest timing. ``require_visible=False`` (GUI
        rework Phase 17's file input) waits for the selector to be
        ATTACHED only, not visible — Playwright's ``set_input_files``
        does not need a visible element, and file inputs are commonly
        hidden by design.
        """
        deadline = time.monotonic() + self._timing.selector_timeout_s
        while True:
            loc = self._query(selectors, require_visible=require_visible)
            if loc is not None:
                return loc
            if time.monotonic() > deadline:
                raise SelectorRot(
                    f"{self.site.name}: no selector for {what} matched"
                    f" within {self._timing.selector_timeout_s:.0f}s —"
                    f" tried: {', '.join(selectors)}"
                )
            time.sleep(self._timing.poll_interval_s)

    def _last_response(self) -> Locator:
        for sel in self.site.response_container:
            loc = self.page.locator(sel)
            if loc.count():
                return loc.last
        raise SelectorRot(
            f"{self.site.name}: no response container matched — tried:"
            f" {', '.join(self.site.response_container)}"
        )

    def _last_result_image(self) -> Locator | None:
        """The last fully loaded, non-placeholder <img> of the last turn."""
        container = self._last_response()
        for sel in self.site.result_image:
            imgs = container.locator(sel)
            for k in range(imgs.count() - 1, -1, -1):
                img = imgs.nth(k)
                loaded = img.evaluate(
                    "(el, min) => el.complete && el.naturalWidth >= min",
                    MIN_IMAGE_PX,
                )
                if loaded:
                    return img
        return None

    def _response_text(self) -> str:
        try:
            return self._last_response().inner_text()
        except DriverError:
            return ""

    def _check_markers(self) -> None:
        """Raise on a quota (TerminalState) or refusal (ItemRefused)
        answer; silent when the response matches neither."""
        text = self._response_text()
        lowered = text.lower()
        for marker in self.site.quota_text_markers:
            if marker in lowered:
                raise TerminalState(
                    f"{self.site.name}: quota/rate-limit response"
                    f" (matched '{marker}'): {text[:300]}",
                    retry_after_s=parse_quota_reset(text),
                )
        # categories are checked IN ORDER, most specific first (the
        # copyright message also contains generic safety substrings) —
        # the first matching category wins and names the scenario
        for category, markers in self.site.refusal_markers.items():
            for marker in markers:
                if marker in lowered:
                    raise ItemRefused(
                        f"{self.site.name}: prompt refused [{category}]"
                        f" (matched '{marker}'): {text[:200]}",
                        category=category,
                    )

    def _check_image_failed(self) -> None:
        """Raise ``ImageGenFailed`` when the CURRENT response text
        already names a known image-generation failure (BUG 3, owner
        2026-07-21) — a silent no-op wherever
        ``site.image_failed_text_markers`` is empty (Gemini today), so
        this is safe to call unconditionally from ``await_done``'s
        wait loop for every site. Distinct from ``_check_markers``
        (refusal/quota) — an entirely different failure mode, with its
        own recovery (the runner resends the site's own "retry" word)."""
        if not self.site.image_failed_text_markers:
            return
        text = self._response_text()
        lowered = text.lower()
        for marker in self.site.image_failed_text_markers:
            if marker in lowered:
                raise ImageGenFailed(
                    f"{self.site.name}: image generation failed"
                    f" (matched '{marker}'): {text[:300]}"
                )

    def _raise_no_image(self, situation: str) -> None:
        """No image and no recognized marker — an unknown DOM state.

        Raises ``NoImage`` (a ``DriverError`` subclass) so the runner
        can catch exactly this and try a one-shot continue nudge; a
        matched refusal/quota marker still wins first (``_check_markers``
        raises ``ItemRefused`` / ``TerminalState`` instead)."""
        self._check_markers()
        raise NoImage(
            f"{self.site.name}: {situation}, and the response matches no"
            f" known refusal/quota marker — DOM state unknown (selector"
            f" rot?). Response starts: {self._response_text()[:300]!r}"
        )
