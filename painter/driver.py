"""CDP driver — drives the owner's already-open, logged-in tab.

Chrome runs once with ``--remote-debugging-port=9222``; the driver
attaches over CDP to the real profile and works the DOM. No Download
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
    """Quota or refusal — report and stop the run, never blind-retry."""


class GenerationTimeout(DriverError):
    """The done edge never came within the hard timeout."""


# Runs on the <img> element inside the page: fetch its src (blob:,
# data: or https:) and hand the bytes back as base64.
_FETCH_IMAGE_JS = """
async (el) => {
  const resp = await fetch(el.src);
  if (!resp.ok) throw new Error(`fetch ${el.src}: HTTP ${resp.status}`);
  const blob = await resp.blob();
  return await new Promise((resolve, reject) => {
    const r = new FileReader();
    r.onload = () => resolve(r.result.split(',', 2)[1]);
    r.onerror = () => reject(r.error);
    r.readAsDataURL(blob);
  });
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
        self._site = site
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
        matches = [p for p in pages if self._site.url_fragment in p.url]
        if not matches:
            open_tabs = ", ".join(p.url for p in pages) or "(none)"
            self.close()
            raise DriverError(
                f"no open {self._site.name} tab — looked for"
                f" '{self._site.url_fragment}' among: {open_tabs}"
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
        box = self._require(self._site.prompt_box, "the prompt box")
        box.click()
        self.page.keyboard.press("Control+A")
        self.page.keyboard.press("Delete")
        self.page.keyboard.insert_text(prompt)
        send = self._require(self._site.send_button, "the send button")
        send.click()

    def await_done(self, log: Log = print) -> None:
        """Watch the done edge: the busy signal appears, then goes."""
        t = self._timing
        start = time.monotonic()

        deadline = start + t.busy_appear_timeout_s
        while self._query(self._site.busy_signal) is None:
            if time.monotonic() > deadline:
                self._raise_no_image(
                    "the busy signal never appeared after submit"
                )
            time.sleep(t.poll_interval_s)

        deadline = time.monotonic() + t.generation_timeout_s
        last_log = time.monotonic()
        while self._query(self._site.busy_signal) is not None:
            now = time.monotonic()
            if now > deadline:
                raise GenerationTimeout(
                    f"{self._site.name}: no done edge after"
                    f" {t.generation_timeout_s:.0f}s (hard timeout)"
                )
            if now - last_log >= t.progress_log_interval_s:
                log(f"    ... still generating ({now - start:.0f}s)")
                last_log = now
            time.sleep(t.poll_interval_s)

    def extract_image(self) -> bytes:
        """Read the generated image's bytes straight from the DOM."""
        t = self._timing
        deadline = time.monotonic() + t.image_ready_timeout_s
        while True:
            img = self._last_result_image()
            if img is not None:
                break
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
        loc = self._query(selectors)
        if loc is None:
            raise SelectorRot(
                f"{self._site.name}: no selector for {what} matched —"
                f" tried: {', '.join(selectors)}"
            )
        return loc

    def _last_response(self) -> Locator:
        for sel in self._site.response_container:
            loc = self.page.locator(sel)
            if loc.count():
                return loc.last
        raise SelectorRot(
            f"{self._site.name}: no response container matched — tried:"
            f" {', '.join(self._site.response_container)}"
        )

    def _last_result_image(self) -> Locator | None:
        """The last fully loaded, non-placeholder <img> of the last turn."""
        container = self._last_response()
        for sel in self._site.result_image:
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

    def _raise_no_image(self, situation: str) -> None:
        """Classify a no-image state: terminal refusal or unknown DOM."""
        try:
            response_text = self._last_response().inner_text()
        except DriverError:
            response_text = ""
        lowered = response_text.lower()
        for marker in self._site.refusal_text_markers:
            if marker in lowered:
                raise TerminalState(
                    f"{self._site.name}: refusal/quota response"
                    f" (matched '{marker}'): {response_text[:300]}"
                )
        raise DriverError(
            f"{self._site.name}: {situation}, and the response matches no"
            f" known refusal — DOM state unknown (selector rot?)."
            f" Response starts: {response_text[:300]!r}"
        )
