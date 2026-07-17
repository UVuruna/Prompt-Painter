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
import time
from typing import Callable

from playwright.sync_api import Locator, Page, sync_playwright

from painter.config import MIN_IMAGE_PX, SiteConfig, Timing

Log = Callable[[str], None]


class DriverError(RuntimeError):
    """The DOM is not in a state the config block recognizes."""


class SelectorRot(DriverError):
    """No fallback selector matched — the site reskinned; fix config."""


class TerminalState(DriverError):
    """Quota/rate limit — stop the whole site, never blind-retry."""


class ItemRefused(DriverError):
    """The site refused THIS prompt (safety) — the runner reports it,
    skips the item and continues with the rest."""


class GenerationTimeout(DriverError):
    """The done edge never came within the hard timeout."""


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

    def submit_prompt(self, prompt: str) -> None:
        """Paste the prompt byte-identical and press send."""
        box = self._require(self.site.prompt_box, "the prompt box")
        box.click()
        self.page.keyboard.press("Control+A")
        self.page.keyboard.press("Delete")
        self.page.keyboard.insert_text(prompt)
        send = self._require(self.site.send_button, "the send button")
        send.click()

    def await_done(self, log: Log = print) -> None:
        """Watch the done edge: the busy signal appears, then goes."""
        t = self._timing
        start = time.monotonic()

        deadline = start + t.busy_appear_timeout_s
        while self._query(self.site.busy_signal) is None:
            if time.monotonic() > deadline:
                self._raise_no_image(
                    "the busy signal never appeared after submit"
                )
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
            img = self._last_result_image()
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

    # --- DOM plumbing ---------------------------------------------------

    def _query(self, selectors: tuple[str, ...]) -> Locator | None:
        """First visible match across the fallback selectors, else None."""
        for sel in selectors:
            loc = self.page.locator(sel)
            for k in range(loc.count()):
                cand = loc.nth(k)
                if cand.is_visible():
                    return cand
        return None

    def _require(self, selectors: tuple[str, ...], what: str) -> Locator:
        """Wait for any fallback selector to match; loud after timeout.

        Sites are async SPAs — elements morph a beat after input
        events (the ChatGPT composer button turns into its send
        state only once the pasted text lands), so a one-shot query
        would fail on honest timing.
        """
        deadline = time.monotonic() + self._timing.selector_timeout_s
        while True:
            loc = self._query(selectors)
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
                    f" (matched '{marker}'): {text[:300]}"
                )
        for marker in self.site.refusal_text_markers:
            if marker in lowered:
                raise ItemRefused(
                    f"{self.site.name}: prompt refused"
                    f" (matched '{marker}'): {text[:200]}"
                )

    def _raise_no_image(self, situation: str) -> None:
        """No image and no recognized marker — an unknown DOM state."""
        self._check_markers()
        raise DriverError(
            f"{self.site.name}: {situation}, and the response matches no"
            f" known refusal/quota marker — DOM state unknown (selector"
            f" rot?). Response starts: {self._response_text()[:300]!r}"
        )
