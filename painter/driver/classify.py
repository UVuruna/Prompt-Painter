"""``DriverClassifyMixin`` — reading the page's own signals and naming
what went wrong: a quota/refusal marker, a degraded-model banner, a
thread-level error, an "image generation failed" line.

This is where a page's TEXT becomes a typed error. Keeping it apart from
the wait half is the point: the wait mixin decides WHEN a turn is
finished, this one decides WHAT that turn means — and a quota wall must
never be blind-retried as if it were a timeout.

Split from the 1,599-line ``painter/driver.py`` (audit
``docs/AUDIT-OOP-2026-08-18.md`` → R4).
"""

from __future__ import annotations

from painter.config import parse_quota_reset

from .errors import (
    ImageGenFailed,
    ItemRefused,
    ModelDegraded,
    TerminalState,
)


class DriverClassifyMixin:
    """Page text in, typed error out. Mixed into ``SiteDriver`` —
    never instantiated alone."""

    def degrade_banner_text(self) -> str | None:
        """Non-raising probe of the degradation banner (F2 gap fix,
        owner 2026-07-29): Gemini's Flash-Lite banner can be up while
        images STILL arrive (the weaker model renders them) — the
        runner probes this after every save and asks the owner's
        choice even then, once per run. None = no banner / site has
        none configured."""
        if not self.site.degrade_banner:
            return None
        banner = self._query(self.site.degrade_banner)
        if banner is None:
            return None
        try:
            return banner.inner_text() or ""
        except Exception:
            return ""  # transiently detached — treat as present, no text

    def _check_degrade_banner(self) -> None:
        """Raise ``ModelDegraded`` when the site's degradation banner
        is up (F2) — checked BEFORE the quota text markers, because the
        banner's accompanying response text also matches them and would
        otherwise always classify as a plain ``TerminalState``. A
        silent no-op for sites with no ``degrade_banner``."""
        if not self.site.degrade_banner:
            return
        banner = self._query(self.site.degrade_banner)
        if banner is None:
            return
        try:
            text = banner.inner_text()
        except Exception:
            text = ""
        raise ModelDegraded(
            f"{self.site.name}: model-degradation banner present"
            f" (quota) — {text[:200]}",
            retry_after_s=parse_quota_reset(text),
        )

    def _check_markers(self, text: str) -> None:
        """Raise on a quota (TerminalState) or refusal (ItemRefused)
        answer in ``text``; silent when it matches neither."""
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

    def _thread_error_risen(self) -> bool:
        """Did the site put a NATIVE thread error on OUR send? (owner
        2026-08-11, the 420s dead waits; SOFTENED 2026-08-14, the
        Zealandia incident — the banner can now coexist with a
        delivered image, so this only REPORTS; ``await_done`` raises
        ``ImageGenFailed`` after the error holds with no image.)

        ChatGPT's second error face — orange "Something went wrong.
        Please try again." beside a Retry button — is rendered INSIDE
        the ``[data-message-author-role="user"]`` block and creates NO
        assistant turn, so ``_new_turn`` never sees it and
        ``_check_image_failed`` (which reads assistant text only) never
        gets the string to match. Meanwhile the busy signal stays set,
        so the item burned the FULL ``generation_timeout_s`` — 420s per
        occurrence, live run 2026-08-11 18:47:21-18:52:06 — before
        dying as an unattributed timeout.

        The verdict is a COUNT RISE, never mere presence: an error turn
        from an earlier item stays in the chat, and treating that as
        ours would fail every later item in the conversation. The raise
        feeds the ordinary image-failure ladder, whose FIRST rung is a
        click on exactly this button.

        Silent no-op wherever the site names no such button (Gemini)."""
        if not self.site.image_error_retry_button:
            return False
        base = self._baseline
        if base is None:
            return False
        return self._error_turns_count() > base.error_turn_count

    def _check_image_failed(self, text: str) -> None:
        """Raise ``ImageGenFailed`` when ``text`` names a known
        image-generation failure (BUG 3, owner 2026-07-21) — a silent
        no-op wherever ``site.image_failed_text_markers`` is empty
        (Gemini today). Distinct from ``_check_markers``
        (refusal/quota) — an entirely different failure mode, with its
        own recovery (the runner resends the site's own "retry" word)."""
        if not self.site.image_failed_text_markers:
            return
        lowered = text.lower()
        for marker in self.site.image_failed_text_markers:
            if marker in lowered:
                raise ImageGenFailed(
                    f"{self.site.name}: image generation failed"
                    f" (matched '{marker}'): {text[:300]}"
                )
