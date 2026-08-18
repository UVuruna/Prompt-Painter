"""The CDP driver's typed error vocabulary — what the runner catches.

Every failure the driver can meet has its own class here, so a caller
decides by TYPE rather than by parsing a message: a rotted selector is
not a quota wall, and a refused item is not a timeout. Kept in a leaf
module of its own so every mixin can raise them without importing the
package back (root ``painter/driver/__init__.py`` composes the mixins).

The one rule they all serve: the driver fails LOUDLY and never guesses
(project CLAUDE.md → "Selectors fail LOUDLY").
"""

from __future__ import annotations

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


class ModelDegraded(DriverError):
    """The site's model-degradation banner is up (F2, owner
    2026-07-29 — Gemini's "Limit reached. Continuing with
    Flash-Lite.") and OUR turn produced no image. Not a plain quota
    stop: the RUNNER asks the configured choice — continue on the
    degraded model (per-item skips while images keep failing, or
    plain successes if the degraded model still renders them) or
    wait for the reset (behaves like ``TerminalState``).
    ``retry_after_s`` is parsed from the banner's own text (the
    absolute "on Jul 25 at 2:18 PM" phrasing) when present."""

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
    """No generated image arrived in OUR response turn, and the text
    matches no refusal / quota / image-failed marker — an UNKNOWN DOM
    state. ``had_text`` (F1 protocol, owner 2026-07-29) records whether
    the site DID answer with text: True means the model replied
    something unrecognized — the runner must LOUD-SKIP the item and
    NEVER send the continue nudge (the market-scene incident: a nudge
    after an unmatched refusal made Gemini draw a random image that got
    saved under the item's name). False means a truly empty/interrupted
    answer — the one case where a single continue nudge is allowed."""

    def __init__(self, message: str, had_text: bool = False):
        super().__init__(message)
        self.had_text = had_text


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


class SendVanished(DriverError):
    """Our CONFIRMED user turn is no longer in the conversation — the
    site dropped the message after ``_confirm_sent`` passed (the
    Padmé/Qui-Gon incident, owner 2026-08-04: Gemini silently deleted
    the sent prompt; the old 'nothing happened' verdict then allowed a
    blind continue nudge, which made Gemini REGENERATE THE PREVIOUS
    request and the result was saved under this item's name). The
    runner must RE-SEND the item's OWN prompt — never the content-blind
    nudge."""


class SendNotConfirmed(DriverError):
    """The prompt never became a user turn — the composer still holds
    the text and nothing was submitted (owner 2026-08-11, the 17:10:16
    Gemini stop, which ended a run at 39/69 collections).

    A PER-ITEM verdict, not a site verdict: the send provably did NOT
    take, so nothing is half-generated and re-sending the item's own
    prompt is safe — the same recovery as ``SendVanished``, whose
    handler this rides. It stayed a plain ``DriverError`` (= stop the
    site) only because it was never given a class of its own."""


class AttachNotConfigured(DriverError):
    """Image attach (``submit_with_image``) is disabled for this site —
    its ``attach_menu_path`` is empty in ``SITES``. Used by BOTH the
    input-image sheet entries (the ``← `ref``` reference photo) and
    WEBSITE FIX (re-attaching a flagged output). The owner captures the
    live "+" menu selectors first, the same way every other selector in
    this file was captured, and pastes them into the site's config
    block. Raised immediately, before ``submit_with_image`` touches the
    page at all — never a guessed selector."""
