"""``painter.driver.wait`` — the turn-based done edge, the F1b anchor and
the image bytes.

``await_done``/``extract_image`` are scoped to a pre-submit ``Baseline``
(turn count + last image src), so a leftover busy button or the PREVIOUS
item's image can never be mistaken for OUR result; the anchor proves the
newest user turn still holds the prompt we sent (``SendVanished``), and
survives a virtualized turn-count drop, a collapsed "Show more" prefix
and an attachment chip before the text.

Split from ``tests/test_driver.py`` alongside the driver package (audit
``docs/AUDIT-OOP-2026-08-18.md`` -> R4). Shared fakes:
``tests/driver_fakes.py``.
"""

import base64
import time
from dataclasses import replace
import pytest
from painter.config import (
    REFUSAL_COPYRIGHT,
    SITES,
    TIMING,
)
from painter.driver import (
    Baseline,
    ImageGenFailed,
    ItemRefused,
    ModelDegraded,
    NoImage,
    SendVanished,
    SiteDriver,
    TerminalState,
    normalize_text,
)
from driver_fakes import (
    FAST,
    FakeLocator,
    FakePage,
    PresentLocator,
    _CHATGPT_COPYRIGHT_TEXT,
    _CHATGPT_FAILURE_TEXT,
    _MISSING,
)


class TextLocator:
    """Duck-typed playwright Locator standing for an assistant response
    container holding ONE turn with TEXT and NO image: ``count()`` /
    ``nth`` / ``last`` / ``inner_text()`` stand in for both the
    container (queried by ``_new_turn``) AND the turn itself (the
    object they return); ``locator(sel)`` (queried BY THE TURN, F1's
    ``_turn_image``) always misses — there is no image in this turn.
    ``holder`` is a one-item list so a test can flip the text the
    driver reads mid-poll."""

    def __init__(self, holder: list[str]):
        self._holder = holder

    def count(self):
        return 1

    def nth(self, k):
        return self

    @property
    def last(self):
        return self

    def inner_text(self):
        return self._holder[0]

    def locator(self, sel):
        return _MISSING


class ImageLocator:
    """Duck-typed playwright Locator for ONE generated <img> (F1):
    ``count()``/``nth`` stand for a one-element image list;
    ``evaluate`` answers BOTH calls the driver makes on it — the
    loaded-check (``evaluate(js, min_px)``, called WITH an extra arg)
    returns ``loaded``, the byte-fetch (``evaluate(_FETCH_IMAGE_JS)``,
    called with none) returns the base64 payload; ``get_attribute
    ('src')`` is the fingerprint the F1 baseline compares against."""

    def __init__(self, src: str, *, loaded: bool = True, b64: str = ""):
        self._src = src
        self._loaded = loaded
        self._b64 = b64

    def count(self):
        return 1

    def nth(self, k):
        return self

    def evaluate(self, js, *args):
        return self._loaded if args else self._b64

    def get_attribute(self, name):
        return self._src if name == "src" else None


class TurnLocator:
    """Duck-typed playwright Locator for ONE assistant turn (F1):
    ``locator(sel)`` resolves to the wired image locator for a matched
    selector, else the missing locator (no image inside this turn);
    ``inner_text()`` answers the turn's own text (default none).
    ``order`` (F1b) is the fake DOM position — ``evaluate`` answers the
    driver's ``_follows`` probe (compareDocumentPosition) by comparing
    it against the anchor element's own ``order``."""

    def __init__(
        self, images: dict | None = None, text: str = "", order: int = 0
    ):
        self._images = images or {}
        self._text = text
        self.order = order

    def locator(self, sel):
        return self._images.get(sel, _MISSING)

    def inner_text(self):
        return self._text

    def evaluate(self, js, *args):
        other = args[0] if args else None
        return (
            getattr(other, "order", None) is not None
            and other.order < self.order
        )


class ContainerLocator:
    """Duck-typed playwright Locator standing for
    ``site.response_container`` (F1): a fixed list of turns —
    ``count()``/``nth`` mirror however many are "in the conversation"
    right now, so a baseline turn_count comparison and the "last turn"
    lookup both work exactly like the real fallback-selector Locator."""

    def __init__(self, turns: list):
        self._turns = turns

    def count(self):
        return len(self._turns)

    def nth(self, k):
        return self._turns[k]


def test_await_done_raises_image_gen_failed_without_burning_timeout():
    """The exact real failure (owner's log, BUG 3): the busy/stop
    signal never clears for this ChatGPT state, so ``await_done`` must
    catch the failure text WHILE still polling instead of waiting out
    the whole hard ``generation_timeout_s``."""
    site = SITES["chatgpt"]
    timing = replace(
        TIMING,
        poll_interval_s=0.01,
        progress_log_interval_s=1000.0,
        busy_appear_timeout_s=1.0,
        generation_timeout_s=5.0,
    )
    page = FakePage()
    page.locators[site.busy_signal[0]] = PresentLocator()
    page.locators[site.response_container[0]] = TextLocator(
        [_CHATGPT_FAILURE_TEXT]
    )
    driver = SiteDriver(site, timing, "http://unused")
    driver.page = page
    driver._baseline = Baseline(turn_count=0, last_img_src=None)

    start = time.monotonic()
    with pytest.raises(ImageGenFailed):
        driver.await_done(log=lambda s: None)
    elapsed = time.monotonic() - start
    # caught within a couple of polls, nowhere near the 5s hard timeout
    assert elapsed < 1.0


def test_await_done_returns_on_loaded_image_even_if_busy_signal_stuck():
    """F1 root cause 4 (owner 2026-07-29): the RESULT is the primary
    done edge — a fresh loaded image in a new assistant turn is 'done'
    even while the busy signal (stop button) is STILL PRESENT, which
    used to stall forever on ChatGPT's stuck button."""
    site = SITES["chatgpt"]
    timing = replace(
        TIMING,
        poll_interval_s=0.01,
        progress_log_interval_s=1000.0,
        busy_appear_timeout_s=1.0,
        generation_timeout_s=5.0,
    )
    page = FakePage()
    img = ImageLocator("blob:fresh")
    turn = TurnLocator(images={site.result_image[0]: img})
    page.locators[site.response_container[0]] = ContainerLocator([turn])
    page.locators[site.busy_signal[0]] = PresentLocator()  # never clears
    driver = SiteDriver(site, timing, "http://unused")
    driver.page = page
    driver._baseline = Baseline(turn_count=0, last_img_src=None)

    driver.await_done(log=lambda s: None)  # must return, never hang


def test_await_done_records_a_stuck_busy_signal_for_the_next_submit():
    """The flag the fix above depends on: an image that loads while the
    busy signal is still set marks the button stuck."""
    site = SITES["chatgpt"]
    timing = replace(
        TIMING,
        poll_interval_s=0.01,
        progress_log_interval_s=1000.0,
        busy_appear_timeout_s=1.0,
        generation_timeout_s=5.0,
    )
    page = FakePage()
    img = ImageLocator("blob:fresh")
    turn = TurnLocator(images={site.result_image[0]: img})
    page.locators[site.response_container[0]] = ContainerLocator([turn])
    page.locators[site.busy_signal[0]] = PresentLocator()  # never clears
    driver = SiteDriver(site, timing, "http://unused")
    driver.page = page
    driver._baseline = Baseline(turn_count=0, last_img_src=None)

    driver.await_done(log=lambda s: None)

    assert driver._busy_known_stuck is True


def test_await_done_text_answer_without_image_raises_had_text():
    """A finished turn that answered with TEXT but no image, busy gone
    AND SETTLED (text_settle_s — the busy signal flickers between
    ChatGPT's text and image phases, so the verdict must hold, LIVE-RUN
    HOTFIX 2026-07-29) -> NoImage(had_text=True) — the runner's loud
    skip, never a nudge (F1 root cause 2)."""
    site = SITES["gemini"]
    timing = replace(
        TIMING,
        poll_interval_s=0.01,
        progress_log_interval_s=1000.0,
        busy_appear_timeout_s=1.0,
        generation_timeout_s=2.0,
        text_settle_s=0.05,
    )
    page = FakePage()
    page.locators[site.response_container[0]] = TextLocator(
        ["I can't draw that particular thing today, sorry!"]
    )
    driver = SiteDriver(site, timing, "http://unused")
    driver.page = page
    driver._baseline = Baseline(turn_count=0, last_img_src=None)

    with pytest.raises(NoImage) as exc:
        driver.await_done(log=lambda s: None)
    assert exc.value.had_text is True


def test_extract_image_rejects_the_previous_items_image():
    """The F1 src-differs rule inside extract_image too: an image whose
    src equals the baseline's ``last_img_src`` is the PREVIOUS item's
    result, never ours — extract_image must not return it."""
    site = SITES["chatgpt"]
    timing = replace(FAST, image_ready_timeout_s=0.05)
    page = FakePage()
    img = ImageLocator("blob:same-as-baseline")
    turn = TurnLocator(images={site.result_image[0]: img})
    page.locators[site.response_container[0]] = ContainerLocator([turn])
    driver = SiteDriver(site, timing, "http://unused")
    driver.page = page
    driver._baseline = Baseline(
        turn_count=0, last_img_src="blob:same-as-baseline"
    )

    with pytest.raises(NoImage):
        driver.extract_image()


def test_extract_image_returns_bytes_for_a_fresh_src():
    """The other half: a src DIFFERENT from the baseline's is OURS —
    extract_image reads it and decodes the base64 payload."""
    site = SITES["chatgpt"]
    timing = replace(FAST, image_ready_timeout_s=0.5)
    page = FakePage()
    b64 = base64.b64encode(b"tiny-png-bytes").decode("ascii")
    img = ImageLocator("blob:fresh", b64=b64)
    turn = TurnLocator(images={site.result_image[0]: img})
    page.locators[site.response_container[0]] = ContainerLocator([turn])
    driver = SiteDriver(site, timing, "http://unused")
    driver.page = page
    driver._baseline = Baseline(turn_count=0, last_img_src="blob:old")

    data = driver.extract_image()

    assert data == b"tiny-png-bytes"


_GEMINI_DEGRADE_BANNER_TEXT = (
    "Limit reached. Continuing with Flash-Lite. Some features aren't"
    " available until your limit resets on Jul 25 at 2:18 PM."
)


def test_await_done_raises_model_degraded_when_the_banner_is_up():
    """A text-only turn (no image) WITH the degrade banner wired ->
    ModelDegraded, not a plain NoImage/TerminalState — and its
    retry_after_s is parsed from the banner's own absolute-moment text."""
    site = SITES["gemini"]
    timing = replace(
        TIMING,
        poll_interval_s=0.01,
        progress_log_interval_s=1000.0,
        busy_appear_timeout_s=1.0,
        generation_timeout_s=5.0,
    )
    page = FakePage()
    page.locators[site.response_container[0]] = TextLocator(
        ["Limit reached. Continuing with Flash-Lite."]
    )
    page.locators[site.degrade_banner[0]] = FakeLocator(
        "degrade_banner", page, text=_GEMINI_DEGRADE_BANNER_TEXT,
    )
    driver = SiteDriver(site, timing, "http://unused")
    driver.page = page
    driver._baseline = Baseline(turn_count=0, last_img_src=None)

    with pytest.raises(ModelDegraded) as exc:
        driver.await_done(log=lambda s: None)
    assert exc.value.retry_after_s is not None


def test_await_done_without_degrade_banner_still_classifies_quota_text():
    """No banner wired — ``_check_degrade_banner`` is a silent no-op and
    the ordinary quota classification fires unchanged (no regression)."""
    site = SITES["gemini"]
    timing = replace(
        TIMING,
        poll_interval_s=0.01,
        progress_log_interval_s=1000.0,
        busy_appear_timeout_s=1.0,
        generation_timeout_s=5.0,
    )
    page = FakePage()
    page.locators[site.response_container[0]] = TextLocator(
        ["I can create more images as soon as your limit resets."
         " Check your usage in Settings."]
    )
    driver = SiteDriver(site, timing, "http://unused")
    driver.page = page
    driver._baseline = Baseline(turn_count=0, last_img_src=None)

    with pytest.raises(TerminalState):
        driver.await_done(log=lambda s: None)


class _AnchorEl:
    """ONE user-turn ELEMENT (what ``_last_user_turn_locator`` nth()s
    out): ``inner_text`` backs the head check, ``element_handle`` hands
    itself to the fake ``compareDocumentPosition`` (see TurnLocator),
    ``order`` is its fake DOM position."""

    def __init__(self, text: str, order: int):
        self.text = text
        self.order = order

    def inner_text(self):
        return self.text

    def element_handle(self):
        return self


class _ListLocator:
    """Duck-typed Locator over a prebuilt element list (user turns)."""

    def __init__(self, els: list):
        self._els = els

    def count(self):
        return len(self._els)

    def nth(self, k):
        return self._els[k]

    @property
    def last(self):
        return self._els[-1]


def _anchor_timing(**over):
    base = dict(
        poll_interval_s=0.01,
        progress_log_interval_s=1000.0,
        busy_appear_timeout_s=1.0,
        generation_timeout_s=5.0,
        text_settle_s=0.05,
    )
    base.update(over)
    return replace(TIMING, **base)


def test_await_done_raises_send_vanished_when_our_prompt_left_the_chat():
    """The Gemini face: the newest user turn is the PREVIOUS item's
    prompt and the user-turn count fell back to the baseline — our
    message was dropped after the confirmed send. SendVanished, never
    the nudge-eligible NoImage(had_text=False)."""
    site = SITES["gemini"]
    page = FakePage()
    page.locators[site.user_turn[0]] = _ListLocator(
        [_AnchorEl("Ornate circular badge for the PREVIOUS item", 10)]
    )
    page.locators[site.response_container[0]] = ContainerLocator(
        [TurnLocator(order=11)]
    )
    driver = SiteDriver(site, _anchor_timing(), "http://unused")
    driver.page = page
    driver._baseline = Baseline(
        turn_count=1, last_img_src=None, user_turn_count=1
    )
    driver._sent_norm = normalize_text(
        "ROUND medallion, aged bronze relief — Padmé"
    )
    driver._sent_head = driver._sent_norm[:60]

    with pytest.raises(SendVanished):
        driver.await_done(log=lambda s: None)


def test_send_vanished_even_when_the_previous_prompt_shares_our_head():
    """Two colored-variant prompts share the same 60-char head — the
    head alone cannot see the vanish. Since 2026-08-14 the verdict is
    the FULL-TEXT window (ANCHOR_VERIFY_CHARS): the variants diverge
    right after the shared head, so the newest user turn reading as
    the PREVIOUS variant is a vanish. (The old user-turn COUNT rule is
    gone — ChatGPT's virtualizing UI made the count lie on healthy
    sends.)"""
    site = SITES["gemini"]
    shared = "Ornate circular badge, vivid full-color paint over polished"
    page = FakePage()
    page.locators[site.user_turn[0]] = _ListLocator(
        [_AnchorEl(shared + " bronze-and-blue ... PREVIOUS item", 10)]
    )
    page.locators[site.response_container[0]] = ContainerLocator(
        [TurnLocator(order=11)]
    )
    driver = SiteDriver(site, _anchor_timing(), "http://unused")
    driver.page = page
    driver._baseline = Baseline(
        turn_count=1, last_img_src=None, user_turn_count=1
    )
    driver._sent_norm = normalize_text(
        shared + " gold-and-crimson enamel, OUR item"
    )
    driver._sent_head = driver._sent_norm[:60]

    with pytest.raises(SendVanished):
        driver.await_done(log=lambda s: None)


def test_await_done_accepts_our_result_when_the_turn_count_is_stale():
    """The ChatGPT face: our user turn IS the newest, our answer holds
    a fresh loaded image and FOLLOWS it in the DOM — but the assistant
    turn COUNT equals the baseline (long-chat DOM dropped an old turn).
    The positional anchor accepts it; the old count arithmetic never
    did (that stopped the whole site at 18:43:46)."""
    site = SITES["chatgpt"]
    img = ImageLocator("blob:fresh")
    ours = TurnLocator(images={site.result_image[0]: img}, order=20)
    page = FakePage()
    page.locators[site.response_container[0]] = ContainerLocator(
        [TurnLocator(order=5), ours]  # count == 2 == baseline (stale)
    )
    page.locators[site.user_turn[0]] = _ListLocator(
        [
            _AnchorEl("an earlier prompt", 1),
            _AnchorEl("This is a TRANSFORMATIVE homage retry", 10),
        ]
    )
    driver = SiteDriver(site, _anchor_timing(), "http://unused")
    driver.page = page
    driver._baseline = Baseline(
        turn_count=2, last_img_src=None, user_turn_count=1
    )
    driver._sent_norm = normalize_text(
        "This is a TRANSFORMATIVE homage retry"
    )
    driver._sent_head = driver._sent_norm[:60]

    driver.await_done(log=lambda s: None)  # must return, never raise


def test_await_done_classifies_a_refusal_despite_a_stale_turn_count():
    """Same stale count, but the answer is the copyright refusal TEXT:
    it must classify as ItemRefused (the safer-retry/skip path) instead
    of surfacing as the site-stopping 'nothing happened'."""
    site = SITES["chatgpt"]
    ours = TurnLocator(text=_CHATGPT_COPYRIGHT_TEXT, order=20)
    page = FakePage()
    page.locators[site.response_container[0]] = ContainerLocator(
        [TurnLocator(order=5), ours]
    )
    page.locators[site.user_turn[0]] = _ListLocator(
        [_AnchorEl("This is a TRANSFORMATIVE homage retry", 10)]
    )
    driver = SiteDriver(site, _anchor_timing(), "http://unused")
    driver.page = page
    driver._baseline = Baseline(
        turn_count=2, last_img_src=None, user_turn_count=0
    )
    driver._sent_norm = normalize_text(
        "This is a TRANSFORMATIVE homage retry"
    )
    driver._sent_head = driver._sent_norm[:60]

    with pytest.raises(ItemRefused) as exc:
        driver.await_done(log=lambda s: None)
    assert exc.value.category == REFUSAL_COPYRIGHT


def test_await_done_never_accepts_a_turn_before_our_user_turn():
    """The orphan guard: a leftover assistant turn that sits BEFORE our
    user turn (position!) is never our result — even though the plain
    count comparison (1 > 0) would have accepted it."""
    site = SITES["gemini"]
    img = ImageLocator("blob:leftover-fresh-src")
    leftover = TurnLocator(images={site.result_image[0]: img}, order=5)
    page = FakePage()
    page.locators[site.response_container[0]] = ContainerLocator(
        [leftover]
    )
    page.locators[site.user_turn[0]] = _ListLocator(
        [_AnchorEl("our Padmé prompt, still awaiting its answer", 10)]
    )
    driver = SiteDriver(
        site, _anchor_timing(busy_appear_timeout_s=0.05), "http://unused"
    )
    driver.page = page
    driver._baseline = Baseline(
        turn_count=0, last_img_src=None, user_turn_count=0
    )
    driver._sent_norm = normalize_text(
        "our Padmé prompt, still awaiting its answer"
    )
    driver._sent_head = driver._sent_norm[:60]

    with pytest.raises(NoImage) as exc:
        driver.await_done(log=lambda s: None)
    assert exc.value.had_text is False  # honest "nothing arrived"


class CountLocator:
    """Duck-typed Locator standing for N matches of one selector — the
    thread-error check counts Retry buttons, it never touches them."""

    def __init__(self, n: int):
        self._n = n

    def count(self):
        return self._n


def test_thread_error_on_our_send_raises_image_gen_failed():
    """ChatGPT's "Something went wrong. Please try again." + Retry face
    (owner's DevTools capture 2026-08-11) renders INSIDE the user turn
    and creates NO assistant turn, so no text scan can reach it while
    the busy signal stays set — the item burned the full 420s hard
    timeout (live run 18:47:21-18:52:06). Detected structurally, by the
    Retry button count RISING above the pre-submit baseline, and raised
    as ImageGenFailed so the ordinary ladder (whose first rung clicks
    exactly that button) takes over. SOFTENED 2026-08-14 (Zealandia):
    the banner can coexist with a delivered image, so the raise comes
    only after the error HOLDS image_ready_timeout_s with no image —
    still ImageGenFailed, still the ladder, just patient."""
    site = SITES["chatgpt"]
    page = FakePage()
    page.locators[site.image_error_retry_button[0]] = CountLocator(1)
    driver = SiteDriver(
        site,
        replace(FAST, image_ready_timeout_s=0.05, generation_timeout_s=5.0),
        "http://unused",
    )
    driver.page = page
    driver._baseline = Baseline(
        turn_count=0, last_img_src=None, error_turn_count=0
    )

    with pytest.raises(ImageGenFailed):
        driver.await_done(log=lambda s: None)


def test_an_older_thread_error_is_not_attributed_to_our_send():
    """The other half, and the reason the verdict is a COUNT RISE and
    never mere presence: an error turn from an EARLIER item stays in
    the chat. Treating it as ours would fail every later item in the
    conversation — so with the count unchanged the wait proceeds
    normally (here: to its ordinary no-image verdict)."""
    site = SITES["chatgpt"]
    page = FakePage()
    page.locators[site.image_error_retry_button[0]] = CountLocator(1)
    driver = SiteDriver(
        site, replace(FAST, busy_appear_timeout_s=0.05), "http://unused"
    )
    driver.page = page
    driver._baseline = Baseline(
        turn_count=0, last_img_src=None, error_turn_count=1
    )

    with pytest.raises(NoImage):
        driver.await_done(log=lambda s: None)


def test_image_wins_over_a_risen_thread_error_banner():
    """The Zealandia incident (owner 2026-08-14): ChatGPT showed
    "Something went wrong" + Retry AND still delivered the image in the
    same turn. The old instant ImageGenFailed made the ladder send
    "retry" while the finished globe sat unread — the IMAGE must win
    over the banner."""
    site = SITES["chatgpt"]
    img = ImageLocator("https://chatgpt.example/estuary/zealandia")
    ours = TurnLocator(images={site.result_image[0]: img}, order=20)
    page = FakePage()
    page.locators[site.image_error_retry_button[0]] = CountLocator(1)
    page.locators[site.response_container[0]] = ContainerLocator([ours])
    page.locators[site.user_turn[0]] = _ListLocator(
        [_AnchorEl("Photorealistic satellite view of Earth, Zealandia", 10)]
    )
    driver = SiteDriver(site, _anchor_timing(), "http://unused")
    driver.page = page
    driver._baseline = Baseline(
        turn_count=0,
        last_img_src=None,
        user_turn_count=0,
        error_turn_count=0,  # the banner ROSE on our send…
    )
    driver._sent_norm = normalize_text(
        "Photorealistic satellite view of Earth, Zealandia"
    )
    driver._sent_head = driver._sent_norm[:60]

    driver.await_done(log=lambda s: None)  # …and the image still wins


def test_virtualized_turn_count_drop_is_not_a_vanish():
    """The SendVanished storm (owner 2026-08-14, live CDP probe):
    ChatGPT's new UI virtualizes old turns OUT of the DOM
    (data-is-intersecting), so the user-turn count falls BELOW the
    pre-submit baseline on a perfectly healthy send. The newest user
    turn still reads as OUR prompt — the anchor must stand and the
    result must be accepted, never SendVanished."""
    site = SITES["chatgpt"]
    img = ImageLocator("blob:fresh-after-virtualization")
    ours = TurnLocator(images={site.result_image[0]: img}, order=20)
    page = FakePage()
    page.locators[site.response_container[0]] = ContainerLocator([ours])
    page.locators[site.user_turn[0]] = _ListLocator(
        # ONE user turn left in the DOM — ours; the baseline saw THREE
        [_AnchorEl("Ornate circular medallion, aged bronze relief", 10)]
    )
    driver = SiteDriver(site, _anchor_timing(), "http://unused")
    driver.page = page
    driver._baseline = Baseline(
        turn_count=0, last_img_src=None, user_turn_count=3
    )
    driver._sent_norm = normalize_text(
        "Ornate circular medallion, aged bronze relief"
    )
    driver._sent_head = driver._sent_norm[:60]

    driver.await_done(log=lambda s: None)  # must return, never raise


def test_collapsed_show_more_prefix_still_anchors():
    """The visible text of a long prompt is a COLLAPSED prefix ("Show
    more") — a prefix of the full prompt must read as ours, while an
    identical-head sibling diverging inside ANCHOR_VERIFY_CHARS must
    not (that pair is what the old count rule existed for)."""
    site = SITES["chatgpt"]
    full = (
        "Photorealistic satellite view of Earth from orbit, ONE globe"
        " centred and filling the frame, isolated on a plain"
        " transparent background, no border, no frame, no ornament,"
        " no lettering of any kind. The globe is turned to the"
        " southwest Pacific with New Zealand at the centre of the"
        " disc and the submerged continent shown as it actually is."
    )
    page = FakePage()
    page.locators[site.user_turn[0]] = _ListLocator(
        [_AnchorEl(full[:200], 10)]  # the collapsed visible prefix
    )
    driver = SiteDriver(site, _anchor_timing(), "http://unused")
    driver.page = page
    driver._baseline = Baseline(
        turn_count=0, last_img_src=None, user_turn_count=1
    )
    driver._sent_norm = normalize_text(full)
    driver._sent_head = driver._sent_norm[:60]

    assert driver._anchor_state() == "ok"

    # the sibling variant: same 60-char head, diverges within the window
    sibling = full[:80] + " BUT a wholly different continent and framing"
    page.locators[site.user_turn[0]] = _ListLocator([_AnchorEl(sibling, 10)])
    assert driver._anchor_state() == "vanished"


def test_attachment_chip_before_prompt_still_anchors():
    """A Prompt+Image user turn renders the attached reference chip
    (the filename) BEFORE the prompt text — Gemini's user-query does
    (the 2026-08-14 continents run: every healthy send read as
    vanished and was re-sent, burning quota on duplicate globes). The
    anchor window must start where the head sits, not at position 0;
    a turn holding someone ELSE's prompt must still read vanished."""
    site = SITES["gemini"]
    full = (
        "Photorealistic Earth globe from orbit distance, the single"
        " supercontinent PANGEA centered on the sunlit hemisphere,"
        " wrapped by the single Panthalassa ocean in deep sapphire."
        " Geography copied exactly from the reference image."
    )
    page = FakePage()
    page.locators[site.user_turn[0]] = _ListLocator(
        [_AnchorEl("Pangea_reference.png\n" + full, 10)]
    )
    driver = SiteDriver(site, _anchor_timing(), "http://unused")
    driver.page = page
    driver._baseline = Baseline(
        turn_count=0, last_img_src=None, user_turn_count=1
    )
    driver._sent_norm = normalize_text(full)
    driver._sent_head = driver._sent_norm[:60]

    assert driver._anchor_state() == "ok"

    # a genuinely dropped message: the newest turn is another prompt
    page.locators[site.user_turn[0]] = _ListLocator(
        [_AnchorEl("Zealandia_reference.png\nA wholly different prompt", 10)]
    )
    assert driver._anchor_state() == "vanished"


class _RaisingImageLocator(ImageLocator):
    """An <img> whose IN-PAGE byte read fails the way Gemini's
    googleusercontent results do: tainted canvas + CORS-blocked fetch."""

    def evaluate(self, js, *args):
        if args:  # the loaded-check still answers normally
            return self._loaded
        raise RuntimeError(
            "canvas: SecurityError: Tainted canvases may not be exported"
            " | fetch https://lh3.googleusercontent.com/gg-dl/x:"
            " TypeError: Failed to fetch"
        )


class _FakeRequest:
    def __init__(self, body: bytes, ok: bool = True, status: int = 200):
        self._body, self.ok, self.status = body, ok, status
        self.urls: list[str] = []

    def get(self, url):
        self.urls.append(url)
        return self

    def body(self):
        return self._body


class _FakeContext:
    def __init__(self, request):
        self.request = request


def _page_with_image(site, src, request, img_cls=_RaisingImageLocator):
    page = FakePage()
    img = img_cls(src)
    page.locators[site.response_container[0]] = ContainerLocator(
        [TurnLocator(images={site.result_image[0]: img})]
    )
    page.context = _FakeContext(request)
    return page


def test_extract_image_falls_back_to_the_browser_context_request():
    """The 16:32:13 Gemini stop (UV/prompt.txt:3339): Gemini began
    serving results from lh3.googleusercontent.com instead of a blob:
    src, which taints the canvas AND fails the CORS fetch — the raw
    Playwright error escaped every handler and killed the site
    mid-collection. The context request runs OUTSIDE the page, so no
    CORS applies and the context's cookies still authorize it."""
    site = SITES["gemini"]
    png = bytes.fromhex("89504e470d0a1a0a") + b"rest-of-the-file"
    request = _FakeRequest(png)
    src = "https://lh3.googleusercontent.com/gg-dl/AAQ_wb=s1024-rj"
    page = _page_with_image(site, src, request)
    driver = SiteDriver(site, replace(FAST, image_ready_timeout_s=0.5),
                        "http://unused")
    driver.page = page
    driver._baseline = Baseline(turn_count=0, last_img_src="blob:old")

    assert driver.extract_image() == png
    assert request.urls == [src]


def test_context_fallback_failure_is_a_classified_skip_not_a_crash():
    """When the third path fails too the item is still LOST — but as a
    classified NoImage the runner skips, never the unhandled exception
    that ended the run. Here the GET returns an error page: bytes that
    are not an image are refused rather than saved."""
    site = SITES["gemini"]
    request = _FakeRequest(b"<html>403 Forbidden</html>")
    page = _page_with_image(
        site, "https://lh3.googleusercontent.com/gg-dl/x", request
    )
    driver = SiteDriver(site, replace(FAST, image_ready_timeout_s=0.5),
                        "http://unused")
    driver.page = page
    driver._baseline = Baseline(turn_count=0, last_img_src="blob:old")

    with pytest.raises(NoImage):
        driver.extract_image()
