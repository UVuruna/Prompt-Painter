"""``DriverLifecycleMixin`` — the attached tab: connect over CDP, adopt
(or open) the site's tab, wait out a login, close; plus the selector
plumbing that turns a config block's fallback tuple into a locator.

This is the ONLY mixin with an ``__init__`` — the other four run on the
attributes it sets, via ``self.`` (the same arrangement
``gui/app.py``'s ``BuildMixin`` already has for ``PainterGui``).

Split from the 1,599-line ``painter/driver.py`` (audit
``docs/AUDIT-OOP-2026-08-18.md`` → R4, owner pre-approved 2026-07-30).
"""

from __future__ import annotations

import time

from playwright.sync_api import Locator, Page, sync_playwright

from painter.config import SiteConfig, Timing

from .errors import DriverError, SelectorRot
from .values import Baseline

from typing import Callable

Log = Callable[[str], None]


class DriverLifecycleMixin:
    """The attached tab and the selector plumbing. Mixed into
    ``SiteDriver`` — never instantiated alone."""

    def __init__(self, site: SiteConfig, timing: Timing, cdp_url: str):
        self.site = site
        self._timing = timing
        self._cdp_url = cdp_url
        self._pw = None
        self._browser = None
        self.page: Page | None = None
        # F1 protocol: the pre-submit snapshot every await/extract is
        # judged against; set by submit_prompt/submit_with_image
        self._baseline: Baseline | None = None
        # F1b (owner 2026-08-04): the normalized head of the LAST
        # CONFIRMED prompt — the anchor every result is paired to. The
        # newest user turn must still hold it, or the send VANISHED.
        self._sent_head: str | None = None
        # 2026-08-14: the FULL normalized prompt beside the head — the
        # anchor verdict is now TEXT-first (see _anchor_state), and the
        # head alone cannot tell identical-head colored variants apart
        self._sent_norm: str | None = None
        # LIVE-RUN FIX (owner 2026-08-04): True when the LAST await_done
        # returned on the image while the busy signal was STILL set —
        # i.e. the site's stop button is provably STUCK, not a running
        # generation. The next _ensure_ready then refreshes at once
        # instead of honestly waiting the signal out (that wait cost a
        # real run 7 minutes between two items).
        self._busy_known_stuck: bool = False
        # TRANSCRIPT (owner 2026-08-11): the FULL text of the LAST
        # assistant answer this driver read — the exceptions truncate
        # it for their messages, the transcript log wants all of it
        self.last_response_text: str = ""
        # True when the LAST ask_text answer came from the anchor
        # fallback (lower confidence) — see ask_text
        self.ask_used_fallback: bool = False

    def attach(self) -> str:
        """Connect over CDP and adopt the open site tab; returns its
        title. F4g (owner 2026-07-29): a MISSING site tab is no longer
        an error — the driver opens one itself (the caller has already
        ensured Chrome is running via ``painter.chrome.ensure_chrome``)
        and the subsequent ``wait_for_login`` covers a login page."""
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
        if matches:
            # several site tabs: drive the last (most recently opened)
            self.page = matches[-1]
        else:
            contexts = self._browser.contexts
            if not contexts:
                self.close()
                raise DriverError(
                    f"{self.site.name}: Chrome has no browser context to"
                    " open a tab in — restart the automation Chrome"
                )
            try:
                self.page = contexts[0].new_page()
                self.page.goto(self.site.url)
            except Exception as exc:
                self.close()
                raise DriverError(
                    f"{self.site.name}: could not open {self.site.url}"
                    f" in the automation Chrome: {exc}"
                ) from exc
        self.page.set_default_timeout(
            self._timing.busy_appear_timeout_s * 1000
        )
        self.page.bring_to_front()
        return self.page.title()

    def wait_for_login(self, log: Log = print) -> None:
        """Block until the site shows its COMPOSER (= logged in) —
        F4g: a freshly opened tab may land on a login page; the owner
        logs in by hand while the run waits (status logged every 15 s).
        Loud after ``login_wait_timeout_s``. An already-logged-in tab
        returns on the first poll."""
        t = self._timing
        deadline = time.monotonic() + t.login_wait_timeout_s
        last_log = 0.0
        while True:
            if self._query(self.site.prompt_box) is not None:
                return
            now = time.monotonic()
            if now > deadline:
                raise DriverError(
                    f"{self.site.name}: no composer after"
                    f" {t.login_wait_timeout_s / 60:.0f} min — still on"
                    " the login page? Log in in the automation Chrome"
                    " window and press Start again."
                )
            if now - last_log >= 15.0:
                log("    waiting for login (the site shows no composer"
                    " yet) ...")
                last_log = now
            time.sleep(t.poll_interval_s)

    def close(self) -> None:
        """Detach from Chrome (never closes the owner's browser)."""
        if self._browser is not None:
            self._browser.close()
            self._browser = None
        if self._pw is not None:
            self._pw.stop()
            self._pw = None
        self.page = None

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
        timeout_s: float | None = None,
    ) -> Locator:
        """Wait for any fallback selector to match; loud after timeout.

        Sites are async SPAs — elements morph a beat after input
        events (the ChatGPT composer button turns into its send
        state only once the pasted text lands), so a one-shot query
        would fail on honest timing. ``require_visible=False`` (the
        attach file input) waits for the selector to be ATTACHED only,
        not visible — Playwright's ``set_input_files`` does not need a
        visible element, and file inputs are commonly hidden by design.
        ``timeout_s`` overrides the default ``selector_timeout_s`` for
        waits that legitimately take longer (the attach preview waits
        out a real upload, up to ``image_ready_timeout_s``).
        """
        limit = (
            self._timing.selector_timeout_s
            if timeout_s is None
            else timeout_s
        )
        deadline = time.monotonic() + limit
        while True:
            loc = self._query(selectors, require_visible=require_visible)
            if loc is not None:
                return loc
            if time.monotonic() > deadline:
                raise SelectorRot(
                    f"{self.site.name}: no selector for {what} matched"
                    f" within {limit:.0f}s —"
                    f" tried: {', '.join(selectors)}"
                )
            time.sleep(self._timing.poll_interval_s)
