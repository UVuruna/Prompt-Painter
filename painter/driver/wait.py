"""``DriverWaitMixin`` — waiting out one turn and reading its result:
the turn-based DONE EDGE, the F1b prompt ANCHOR, and the image bytes.

The site never says "finished", so the driver watches the turn model
instead: how many turns exist, which one follows the anchor the last
confirmed prompt left, whether it carries an image, and whether the busy
signal has dropped. When the edge lands, the <img> is read straight out
of the DOM (fetch inside the page, base64 back) — no Download click.
``ask_text`` is the same wait with a text answer instead of an image.

Split from the 1,599-line ``painter/driver.py`` (audit
``docs/AUDIT-OOP-2026-08-18.md`` → R4).
"""

from __future__ import annotations

import base64
import time
from typing import Callable

from playwright.sync_api import Locator

from painter.config import MIN_IMAGE_PX

from .errors import (
    DriverError,
    GenerationTimeout,
    ImageGenFailed,
    NoImage,
    SendVanished,
)
from .values import Baseline, normalize_text, sniff_format

Log = Callable[[str], None]

# how far the ANCHOR compares the newest user turn's visible text
# against the full sent prompt (owner 2026-08-14, the SendVanished
# storm): far enough that identical-head colored variants diverge
# inside the window, short enough to stay clear of the collapsed
# "Show more" cut and any trailing UI text the turn may append
ANCHOR_VERIFY_CHARS = 300

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


class DriverWaitMixin:
    """The done edge, the anchor and the result bytes. Mixed into
    ``SiteDriver`` — never instantiated alone."""

    def _turns_count(self) -> int:
        """How many assistant turns the conversation currently holds."""
        for sel in self.site.response_container:
            loc = self.page.locator(sel)
            n = loc.count()
            if n:
                return n
        return 0

    def _last_user_turn_text(self) -> str | None:
        """Text of the newest USER turn; None when the site names no
        ``user_turn`` selector or none matches (the caller falls back
        LOUDLY — see ``_confirm_sent``)."""
        if not self.site.user_turn:
            return None
        for sel in self.site.user_turn:
            loc = self.page.locator(sel)
            if loc.count():
                return loc.last.inner_text()
        return None

    def _user_turns_count(self) -> int:
        """How many USER turns the conversation currently holds."""
        if not self.site.user_turn:
            return 0
        for sel in self.site.user_turn:
            n = self.page.locator(sel).count()
            if n:
                return n
        return 0

    def _last_user_turn_locator(self) -> Locator | None:
        """The newest USER turn element (the F1b anchor); None when no
        selector matches."""
        for sel in self.site.user_turn:
            loc = self.page.locator(sel)
            n = loc.count()
            if n:
                return loc.nth(n - 1)
        return None

    def _last_image_src(self) -> str | None:
        """src of the last generated image anywhere on the page — the
        pre-submit fingerprint a result image must DIFFER from."""
        for sel in self.site.result_image:
            loc = self.page.locator(sel)
            n = loc.count()
            if n:
                return loc.nth(n - 1).get_attribute("src")
        return None

    def _error_turns_count(self) -> int:
        """How many of the site's native thread-error turns the chat
        currently holds — counted by their Retry button, the one
        element the error face always carries (owner 2026-08-11). Zero
        wherever the site names no such button (Gemini today)."""
        if not self.site.image_error_retry_button:
            return 0
        total = 0
        for sel in self.site.image_error_retry_button:
            total += self.page.locator(sel).count()
        return total

    def await_done(self, log: Log = print) -> None:
        """Wait until OUR result exists (F1 protocol, owner 2026-07-29).

        The old done edge was button-only ("stop button disappears") —
        which stalls forever on ChatGPT's stuck button and cannot tell
        OUR generation from a leftover one. Now the primary signal is
        the RESULT itself: an assistant turn NEWER than the pre-submit
        baseline holding a loaded image whose src differs from the
        baseline's. The busy button is only secondary evidence:

        - new turn + fresh loaded image  -> done (even if the busy
          signal is stuck — root cause 4);
        - new turn text matching quota / refusal / image-failed
          markers -> classified raise (checked on EVERY poll);
        - new turn with final text, NO image, busy gone ->
          ``NoImage(had_text=True)`` — the runner LOUD-SKIPS, never
          nudges (root cause 2);
        - nothing new and busy never appeared within the appear
          window -> ``NoImage(had_text=False)`` (empty/interrupted —
          the one nudge-eligible case);
        - our confirmed user turn GONE from the chat (settled
          ``text_settle_s``) -> ``SendVanished`` — the runner re-sends
          the item's OWN prompt (F1b, owner 2026-08-04);
        - the hard ``generation_timeout_s`` still bounds everything.
        """
        t = self._timing
        start = time.monotonic()
        deadline = start + t.generation_timeout_s
        quiet_deadline = start + t.busy_appear_timeout_s
        last_log = start
        # LIVE-RUN HOTFIX (owner 2026-07-29): "text + not busy" must
        # HOLD for text_settle_s continuously before it is terminal —
        # ChatGPT's busy signal flickers between its text phase and
        # its image-tool phase, and the instant verdict skipped items
        # whose generation was mid-flight (then the next submit killed
        # it — the send/interrupt/send loop caught live).
        text_only_since: float | None = None
        # F1b (owner 2026-08-04): "our sent prompt left the chat" must
        # HOLD for text_settle_s before it is terminal — a re-rendering
        # conversation can transiently mis-read the newest user turn.
        vanished_since: float | None = None
        # 2026-08-14 (the Zealandia incident): the thread-error banner
        # is no longer an instant verdict — ChatGPT now shows
        # "Something went wrong" + Retry AND STILL DELIVERS the image
        # in the same turn (owner's screenshot: banner up, globe 1/2
        # rendered below it). The 2026-08-11 assumption ("error = no
        # assistant turn will ever come") raised ImageGenFailed on
        # sight, the ladder sent "retry", and the finished image was
        # never extracted. Now: the IMAGE wins (checked first, every
        # poll); the risen error becomes terminal only after it holds
        # image_ready_timeout_s with no image arriving.
        error_since: float | None = None
        while True:
            now = time.monotonic()
            if now > deadline:
                raise GenerationTimeout(
                    f"{self.site.name}: no result for OUR turn after"
                    f" {t.generation_timeout_s:.0f}s (hard timeout)"
                )
            turn = self._new_turn()
            busy = self._busy()
            if turn is not None and self._turn_image(turn) is not None:
                # our image is loaded — done, banner and button
                # ignored. When the busy signal is STILL set at this
                # moment it is provably stuck (our result exists), so
                # record it for the next _ensure_ready (owner
                # 2026-08-04).
                self._busy_known_stuck = busy
                return
            if self._thread_error_risen():
                if error_since is None:
                    error_since = now
                elif now - error_since >= t.image_ready_timeout_s:
                    raise ImageGenFailed(
                        f"{self.site.name}: the site put a native"
                        " thread error on our send (its Retry button"
                        " appeared) and no image arrived within"
                        f" {t.image_ready_timeout_s:.0f}s of it"
                    )
            else:
                error_since = None
            vanished = self._anchor_state() == "vanished"
            if vanished:
                if vanished_since is None:
                    vanished_since = now
                elif now - vanished_since >= t.text_settle_s:
                    raise SendVanished(
                        f"{self.site.name}: our sent prompt is NO"
                        " LONGER the newest user turn — the site"
                        " dropped the message after the confirmed send"
                        f" (noticed {now - start:.0f}s in, held"
                        f" {t.text_settle_s:.0f}s). Re-send the item's"
                        " own prompt; a blind continue nudge here would"
                        " regenerate the PREVIOUS request."
                    )
            else:
                vanished_since = None
            if turn is not None:
                text = self._safe_text(turn)
                if text:
                    self.last_response_text = text
                    self._check_degrade_banner()
                    self._check_image_failed(text)
                    self._check_markers(text)
                if text and not busy:
                    if text_only_since is None:
                        text_only_since = now
                    elif now - text_only_since >= t.text_settle_s:
                        raise NoImage(
                            f"{self.site.name}: the response answered"
                            " with TEXT but no image (settled"
                            f" {t.text_settle_s:.0f}s), and the text"
                            " matches no known marker — loud skip,"
                            f" never a nudge. Text starts: {text[:300]!r}",
                            had_text=True,
                        )
                else:
                    text_only_since = None  # busy again / image incoming
            elif (
                not vanished
                and not busy
                and error_since is None  # a pending thread error owns
                # this wait — its verdict is ImageGenFailed (the
                # ladder), never the nudge-eligible quiet NoImage
                and now > quiet_deadline
            ):
                # the message used to hardcode busy_appear_timeout_s,
                # which read as "gave up after 30s" even when a stale
                # busy signal had honestly held this branch off for
                # minutes (the 18:43:46 stop) — report REAL elapsed
                raise NoImage(
                    f"{self.site.name}: nothing arrived for OUR turn"
                    f" ({now - start:.0f}s after the confirmed send:"
                    " no new turn, and no busy signal within"
                    f" {t.busy_appear_timeout_s:.0f}s) —"
                    " empty/interrupted answer",
                    had_text=False,
                )
            if now - last_log >= t.progress_log_interval_s:
                log(f"    ... still generating ({now - start:.0f}s)")
                last_log = now
            time.sleep(t.poll_interval_s)

    def extract_image(self) -> bytes:
        """Read OUR generated image's bytes straight from the DOM.

        F1 protocol: the image is taken ONLY from an assistant turn
        newer than the pre-submit baseline, and only when its src
        differs from the baseline's last image — never "the last
        visible image on the page" (the duplicate-save root cause).
        """
        t = self._timing
        deadline = time.monotonic() + t.image_ready_timeout_s
        while True:
            turn = self._new_turn()
            img = None if turn is None else self._turn_image(turn)
            if img is not None:
                break
            text = "" if turn is None else self._safe_text(turn)
            if text:
                self.last_response_text = text
                self._check_degrade_banner()
                self._check_markers(text)
            if time.monotonic() > deadline:
                raise NoImage(
                    f"{self.site.name}: OUR response turn holds no"
                    " loaded generated image, and its text matches no"
                    f" known marker. Text starts: {text[:300]!r}",
                    had_text=bool(text),
                )
            time.sleep(t.poll_interval_s)
        try:
            b64 = img.evaluate(_FETCH_IMAGE_JS)
        except Exception as exc:
            return self._fetch_via_context(img, exc)
        return base64.b64decode(b64)

    def _fetch_via_context(self, img: Locator, exc: Exception) -> bytes:
        """Third extraction path: pull the image over the BROWSER
        CONTEXT's own request API (owner 2026-08-11, the 16:32:13
        Gemini crash).

        Both in-page paths are same-origin bound: Gemini began serving
        results from ``lh3.googleusercontent.com`` instead of a
        ``blob:`` src, which TAINTS the canvas (``toDataURL`` throws
        SecurityError) while the ``fetch()`` fallback dies on CORS —
        and the resulting raw Playwright error escaped every handler
        and killed the whole site mid-collection. ``context.request``
        issues the GET OUTSIDE the page, so no CORS policy applies to
        it, and it carries the context's cookies, so a signed/auth'd
        CDN URL still resolves.

        Loud on failure, exactly like before — this widens what can be
        read, it never invents bytes — but the failure now arrives as a
        classified ``NoImage`` the runner skips the item on, instead of
        an unhandled crash that ends the run."""
        src = img.get_attribute("src") or ""
        if not src.startswith(("http://", "https://")):
            # blob:/data: srcs are page-local — the context request
            # cannot resolve them, so there is nothing further to try
            raise NoImage(
                f"{self.site.name}: could not read the image bytes"
                f" from the DOM ({exc})",
                had_text=False,
            )
        try:
            resp = self.page.context.request.get(src)
            if not resp.ok:
                raise DriverError(f"HTTP {resp.status}")
            data = resp.body()
        except Exception as exc2:
            raise NoImage(
                f"{self.site.name}: could not read the image bytes —"
                f" in-page ({exc}); browser-context GET of {src[:120]}"
                f" ({exc2})",
                had_text=False,
            ) from exc2
        if sniff_format(data) is None:
            raise NoImage(
                f"{self.site.name}: the browser-context GET of"
                f" {src[:120]} returned {len(data)} bytes that are not"
                " an image (an error page, most likely)",
                had_text=False,
            )
        return data

    def ask_text(self, question: str, log: Log = print) -> str:
        """Send a TEXT-ONLY question and return the answer's full text
        — the refusal diagnostic (owner 2026-08-11). No image is
        expected and NO marker classification runs: the whole point is
        to read the site's own explanation of a refusal, and that
        explanation legitimately contains the very words the refusal
        markers match (classifying it would raise ``ItemRefused`` on
        the diagnosis itself). Done = the newest assistant turn's text
        STABLE for ``text_settle_s`` with the busy signal gone (the
        same settle idiom as ``await_done``'s text-only branch).
        Returns whatever arrived by ``generation_timeout_s`` — "" when
        nothing did; the SUBMIT itself still fails loudly (the caller
        decides that a failed diagnostic never fails the run).

        ANCHOR FALLBACK (owner-approved 2026-08-11, the Obi-Wan case):
        when the deadline passes with NOTHING anchored — a vanished
        composer breaks the anchor while the answer renders anyway —
        the fallback reads the LAST assistant turn on the page, anchor
        ignored, and returns it IF it differs from the text that stood
        there BEFORE the question (so a still-visible refusal never
        poses as its own diagnosis). ``ask_used_fallback`` tells the
        caller to mark the row's lower confidence (``anchor=fallback``
        in the transcript). Acceptable ONLY here: a mis-attributed
        diagnostic is a mislabeled log line, never a saved image."""
        self.ask_used_fallback = False
        # the page's answer text BEFORE the question — the fallback's
        # "is this actually new?" yardstick
        prior = self._last_turn_text_any()
        self.submit_prompt(question, log)
        t = self._timing
        deadline = time.monotonic() + t.generation_timeout_s
        stable_since: float | None = None
        last = ""
        while time.monotonic() < deadline:
            turn = self._new_turn()
            busy = self._busy()
            text = "" if turn is None else self._safe_text(turn)
            if text and not busy:
                if text != last:
                    last = text
                    stable_since = time.monotonic()
                elif (
                    stable_since is not None
                    and time.monotonic() - stable_since >= t.text_settle_s
                ):
                    self.last_response_text = text
                    return text
            else:
                stable_since = None
            time.sleep(t.poll_interval_s)
        if not last:
            fallback = self._last_turn_text_any()
            if fallback and fallback != prior:
                log(
                    "    diagnostic answer taken from the LAST assistant"
                    " turn (anchor lost — lower confidence)"
                )
                self.ask_used_fallback = True
                self.last_response_text = fallback
                return fallback
        if last:
            self.last_response_text = last
        return last  # "" = the site answered nothing in time

    def _require_baseline(self) -> Baseline:
        if self._baseline is None:
            raise DriverError(
                f"{self.site.name}: await/extract called without a"
                " submit — no baseline captured (internal call-order"
                " bug, never a site state)"
            )
        return self._baseline

    def _anchor_state(self) -> str:
        """Is our confirmed prompt still the newest USER turn? (F1b,
        owner 2026-08-04 — the Padmé/Qui-Gon incident.)

        - ``"ok"``: the newest user turn holds our prompt's head AND the
          user-turn count grew past the baseline — the anchor stands.
        - ``"vanished"``: the site DROPPED our message after the send
          was confirmed (the newest user turn is someone else's, or the
          count fell back to the pre-submit value — two colored-variant
          prompts share the same 60-char head, so the count check is
          what catches a vanish between IDENTICAL heads).
        - ``"unavailable"``: no anchor possible (no ``user_turn``
          selector configured / matching, or nothing confirmed yet) —
          callers fall back to the count-based F1 comparison.
        """
        if not self._sent_head or not self.site.user_turn:
            return "unavailable"
        base = self._require_baseline()
        for sel in self.site.user_turn:
            loc = self.page.locator(sel)
            n = loc.count()
            if not n:
                continue
            try:
                text = loc.nth(n - 1).inner_text()
            except Exception:
                return "unavailable"  # transiently detached — this
                # poll falls back; the next one re-reads
            norm = normalize_text(text)
            if self._sent_norm is not None:
                # 2026-08-14 (the SendVanished storm, live CDP probe):
                # ChatGPT's new UI VIRTUALIZES turns out of the DOM
                # (data-is-intersecting) — the user-turn count falls
                # BELOW the baseline on perfectly healthy sends, so the
                # count is a liar and the TEXT is the verdict. The
                # newest user turn must read as OUR prompt: the head,
                # then the visible text agreeing with the full prompt
                # for as far as both go (the collapsed "Show more" view
                # is a prefix; ANCHOR_VERIFY_CHARS keeps the window
                # clear of trailing UI text). Identical-head colored
                # variants diverge inside that window, so a DROPPED
                # message still reads vanished — the case the old
                # count check existed for.
                # 2026-08-14 (the continents Prompt+Image run): the
                # turn's visible text may PRECEDE our prompt with UI
                # text — Gemini's user-query renders the attached
                # reference chip (the filename) before the prompt — so
                # the window is anchored WHERE THE HEAD SITS, never at
                # position 0 (a position-0 compare read every healthy
                # attachment send as vanished and re-sent it, burning
                # quota on duplicates the whole run long).
                i = norm.find(self._sent_head)
                if i < 0:
                    return "vanished"
                tail = norm[i:]
                k = min(len(tail), len(self._sent_norm), ANCHOR_VERIFY_CHARS)
                if tail[:k] != self._sent_norm[:k]:
                    return "vanished"
                return "ok"
            # legacy path (no full prompt recorded — ask_text and other
            # non-submit flows): the pre-2026-08-14 count-then-head rule
            if n <= base.user_turn_count:
                return "vanished"
            if self._sent_head in norm:
                return "ok"
            return "vanished"
        return "unavailable"

    def _follows(self, anchor: Locator, turn: Locator) -> bool:
        """Does ``turn`` come AFTER ``anchor`` in the DOM? The pairing
        test that replaces turn-count arithmetic (F1b): the accepted
        result must FOLLOW our own user turn — a leftover earlier
        answer never can. False on any transient failure (the next
        poll re-checks)."""
        try:
            handle = anchor.element_handle()
            return bool(
                turn.evaluate(
                    "(el, other) => !!(other.compareDocumentPosition(el)"
                    " & Node.DOCUMENT_POSITION_FOLLOWING)",
                    handle,
                )
            )
        except Exception:
            return False

    def _new_turn(self) -> Locator | None:
        """The assistant turn holding OUR result, else None.

        F1b (owner 2026-08-04): when the user-turn anchor is available,
        the verdict is POSITIONAL — the last assistant turn counts as
        ours only when it FOLLOWS our own user turn in the DOM. The old
        count comparison ("more turns than the baseline") stays only as
        the fallback for an unavailable anchor: in a long chat the site
        VIRTUALIZES old turns out of the DOM, so the count can stand
        still while our answer is right there (the ChatGPT retry that
        killed the whole site after 4 minutes of honest generation).
        """
        base = self._require_baseline()
        for sel in self.site.response_container:
            loc = self.page.locator(sel)
            n = loc.count()
            if not n:
                continue
            turn = loc.nth(n - 1)
            state = self._anchor_state()
            if state == "ok":
                anchor = self._last_user_turn_locator()
                if anchor is not None and self._follows(anchor, turn):
                    return turn
                return None
            if state == "vanished":
                return None  # await_done raises SendVanished (settled)
            return turn if n > base.turn_count else None
        return None

    def _turn_image(self, turn: Locator) -> Locator | None:
        """The last fully loaded, non-placeholder <img> INSIDE ``turn``
        whose src differs from the baseline's last image src."""
        base = self._require_baseline()
        for sel in self.site.result_image:
            imgs = turn.locator(sel)
            for k in range(imgs.count() - 1, -1, -1):
                img = imgs.nth(k)
                loaded = img.evaluate(
                    "(el, min) => el.complete && el.naturalWidth >= min",
                    MIN_IMAGE_PX,
                )
                if not loaded:
                    continue
                if (
                    base.last_img_src is not None
                    and img.get_attribute("src") == base.last_img_src
                ):
                    continue  # the PREVIOUS item's image — never ours
                return img
        return None

    def _safe_text(self, turn: Locator) -> str:
        try:
            return turn.inner_text()
        except Exception:
            return ""  # transiently detached turn — next poll re-reads

    def _last_turn_text_any(self) -> str:
        """The LAST assistant turn's text, anchor and baseline IGNORED
        — ``ask_text``'s fallback yardstick/source ONLY (a result this
        loosely attributed must never feed an image save)."""
        for sel in self.site.response_container:
            loc = self.page.locator(sel)
            n = loc.count()
            if n:
                return self._safe_text(loc.nth(n - 1))
        return ""
