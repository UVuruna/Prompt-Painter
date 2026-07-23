"""Tests for painter.driver.SiteDriver — the project's FIRST driver
tests (GUI rework Phase 17, WEBSITE FIX). Real DOM behavior needs the
owner's live browser session (driver.py has always been verified by
supervised runs, never unit tests); these use minimal duck-typed fakes
for playwright's ``Locator``/``Page`` to prove the parts that ARE
agent-verifiable:

- ``submit_with_image`` raises ``AttachNotConfigured`` LOUDLY and
  IMMEDIATELY (before touching the page at all) when a site's
  ``attach_menu_path`` is empty.
- With the real captured selectors, ``submit_with_image`` runs the
  human path: expand the "+" menu, pick the add-image option, attach
  the file (set_input_files for ChatGPT's hidden input; the file-chooser
  interception for Gemini's OS dialog), WAIT for the composer preview,
  then paste + send — and never sends when the preview never appears.
- ``submit_prompt``'s existing text-only flow is byte-identical after
  being routed through the shared ``_paste_and_send`` helper.
"""

import time
from dataclasses import replace

import pytest

from painter.config import (
    REFUSAL_COPYRIGHT,
    REFUSAL_SAFETY,
    SITES,
    TIMING,
    Timing,
)
from painter.driver import (
    AttachNotConfigured,
    ImageGenFailed,
    ItemRefused,
    SelectorRot,
    SiteDriver,
)

# Zero out every human-rhythm pause and shrink the selector-timeout
# polling step so these tests run instantly — only the LOOKUP logic is
# under test, never real timing.
FAST: Timing = replace(
    TIMING,
    action_delay_min_s=0.0,
    action_delay_max_s=0.0,
    selector_timeout_s=1.0,
    poll_interval_s=0.01,
)


class _MissingLocator:
    """Duck-typed playwright Locator matching nothing (count() == 0),
    same as a real Locator built from a selector absent from the DOM."""

    def count(self):
        return 0


_MISSING = _MissingLocator()


class FakeLocator:
    """Duck-typed playwright Locator: one already-matched element.

    Records every ``click``/``set_input_files`` onto the owning
    ``FakePage.calls`` list so a test can assert the exact ORDER of
    actions across several different locators.
    """

    def __init__(self, name: str, page: "FakePage", *, visible: bool = True):
        self.name = name
        self.page = page
        self._visible = visible
        self.set_files = None

    def count(self):
        return 1

    def nth(self, k):
        assert k == 0
        return self

    @property
    def first(self):
        return self

    def is_visible(self):
        return self._visible

    def click(self):
        self.page.calls.append(("click", self.name))

    def set_input_files(self, path):
        self.set_files = path
        self.page.calls.append(("set_input_files", self.name, path))


class FakeKeyboard:
    def __init__(self, page: "FakePage"):
        self.page = page

    def press(self, key):
        self.page.calls.append(("press", key))

    def insert_text(self, text):
        self.page.calls.append(("insert_text", text))


class _FakeFileChooser:
    """Duck-typed playwright FileChooser: ``set_files(path)`` records the
    programmatic file selection that replaces the native OS dialog."""

    def __init__(self, page: "FakePage"):
        self._page = page

    def set_files(self, path):
        self._page.chooser_files = path
        self._page.calls.append(("file_chooser_set_files", path))


class _FakeChooserCtx:
    """Duck-typed result of ``page.expect_file_chooser()`` — a context
    manager whose ``.value`` is the FileChooser, mirroring Playwright's
    EventInfo (the click that opens the dialog runs inside the block)."""

    def __init__(self, page: "FakePage"):
        self.value = _FakeFileChooser(page)

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False


class FakePage:
    """Duck-typed playwright Page: resolves ``locator(selector)`` from
    a dict the test wires up, records every meaningful action (click /
    set_input_files / keyboard press / insert_text / file-chooser) IN
    ORDER."""

    def __init__(self):
        self.locators: dict[str, FakeLocator] = {}
        self.calls: list[tuple] = []
        self.keyboard = FakeKeyboard(self)
        self.chooser_files = None  # set by _FakeFileChooser.set_files

    def locator(self, sel):
        return self.locators.get(sel, _MISSING)

    def reload(self):
        self.calls.append(("reload",))

    def expect_file_chooser(self):
        return _FakeChooserCtx(self)


def _driver(site, page: FakePage) -> SiteDriver:
    driver = SiteDriver(site, FAST, "http://unused")
    driver.page = page
    return driver


# --- (a) the gate: AttachNotConfigured, loud + immediate --------------

@pytest.mark.parametrize("site_key", ["chatgpt", "gemini"])
def test_shipped_sites_have_image_attach_configured(site_key):
    """The owner captured the '+' menu selectors (UV/Add Photo), so
    image attach is ENABLED for both sites: a "+" step, an add-image
    option step, and a preview to wait for."""
    site = SITES[site_key]
    assert len(site.attach_menu_path) >= 2
    assert all(step for step in site.attach_menu_path)  # no empty step
    assert site.attach_preview != ()


def test_chatgpt_uses_a_hidden_input_gemini_uses_the_file_chooser():
    """ChatGPT exposes #upload-photos (set_input_files, no OS dialog);
    Gemini opens an OS dialog with no exposed input (file-chooser)."""
    assert SITES["chatgpt"].file_input != ()
    assert SITES["gemini"].file_input == ()


def test_submit_with_image_raises_loudly_when_not_configured():
    site = replace(SITES["chatgpt"], attach_menu_path=())
    page = FakePage()
    driver = _driver(site, page)

    with pytest.raises(AttachNotConfigured):
        driver.submit_with_image("C:/out/img.png", "put the hero in")

    # IMMEDIATE: no selector was even queried before the raise.
    assert page.calls == []


# --- (b) configured: expand "+" -> pick add-image -> attach -> preview
# -> paste -> send -----------------------------------------------------

def _wire_attach(site, page, *, with_input: bool):
    """Wire the '+' step, the add-image option, the preview, prompt box
    and send onto ``page`` (and the hidden file input when the site uses
    one). Returns the FakeLocator map for extra assertions."""
    plus = FakeLocator("plus", page)
    option = FakeLocator("option", page)
    preview = FakeLocator("preview", page)
    prompt_box = FakeLocator("prompt_box", page)
    send = FakeLocator("send", page)
    page.locators = {
        site.attach_menu_path[0][0]: plus,
        site.attach_menu_path[1][0]: option,
        site.attach_preview[0]: preview,
        site.prompt_box[0]: prompt_box,
        site.send_button[0]: send,
    }
    loc = {"plus": plus, "option": option, "preview": preview}
    if with_input:
        # a real <input type=file> is routinely hidden by design — prove
        # the driver still finds it (require_visible=False)
        file_input = FakeLocator("file_input", page, visible=False)
        page.locators[site.file_input[0]] = file_input
        loc["file_input"] = file_input
    return loc


def test_submit_with_image_sequence_chatgpt_hidden_input():
    site = SITES["chatgpt"]
    page = FakePage()
    loc = _wire_attach(site, page, with_input=True)
    driver = _driver(site, page)

    driver.submit_with_image("C:/out/hero.png", "put the hero in the scene")

    assert loc["file_input"].set_files == "C:/out/hero.png"
    calls = page.calls
    i_plus = calls.index(("click", "plus"))
    i_option = calls.index(("click", "option"))
    i_files = calls.index(
        ("set_input_files", "file_input", "C:/out/hero.png")
    )
    i_text = calls.index(("insert_text", "put the hero in the scene"))
    i_send = calls.index(("click", "send"))
    # a person's path: expand "+", pick add-image, attach, THEN paste+send
    assert i_plus < i_option < i_files < i_text < i_send
    # the follow-up prompt reused the SAME paste path as submit_prompt
    assert ("press", "Control+A") in calls
    assert ("press", "Delete") in calls


def test_submit_with_image_sequence_gemini_file_chooser():
    site = SITES["gemini"]
    page = FakePage()
    _wire_attach(site, page, with_input=False)
    driver = _driver(site, page)

    driver.submit_with_image("C:/out/hero.png", "put the hero in")

    # no exposed input -> the file went through the file-chooser
    assert page.chooser_files == "C:/out/hero.png"
    calls = page.calls
    i_plus = calls.index(("click", "plus"))
    i_option = calls.index(("click", "option"))
    i_files = calls.index(("file_chooser_set_files", "C:/out/hero.png"))
    i_text = calls.index(("insert_text", "put the hero in"))
    i_send = calls.index(("click", "send"))
    assert i_plus < i_option < i_files < i_text < i_send


def test_submit_with_image_attaches_before_typing():
    """The image must be attached before the prompt is typed — the
    person expands the menu and attaches first, never types early."""
    site = SITES["chatgpt"]
    page = FakePage()
    _wire_attach(site, page, with_input=True)
    driver = _driver(site, page)

    driver.submit_with_image("C:/out/hero.png", "put the hero in")

    before_upload = []
    for call in page.calls:
        if call[0] in ("set_input_files", "file_chooser_set_files"):
            break
        before_upload.append(call)
    # only the "+" expand and the add-image click happen before upload —
    # no prompt-box interaction starts early
    assert before_upload == [("click", "plus"), ("click", "option")]


def test_submit_with_image_waits_for_the_preview_before_sending():
    """When the upload preview never appears, the driver must NOT send —
    it waits it out and fails loudly (the prompt never races the image)."""
    site = SITES["chatgpt"]
    page = FakePage()
    loc = _wire_attach(site, page, with_input=True)
    del page.locators[site.attach_preview[0]]  # preview never shows up
    # shrink the preview wait so the loud failure is instant
    fast_preview = replace(FAST, image_ready_timeout_s=0.05)
    driver = SiteDriver(site, fast_preview, "http://unused")
    driver.page = page

    with pytest.raises(SelectorRot):
        driver.submit_with_image("C:/out/hero.png", "put the hero in")

    # the file WAS attached, but no prompt/send ever happened
    assert loc["file_input"].set_files == "C:/out/hero.png"
    assert not any(c[0] == "insert_text" for c in page.calls)
    assert ("click", "send") not in page.calls


# --- (c) submit_prompt unchanged through the shared helper -------------

def test_submit_prompt_unchanged_through_shared_helper():
    site = SITES["chatgpt"]
    page = FakePage()
    prompt_box = FakeLocator("prompt_box", page)
    send = FakeLocator("send", page)
    page.locators = {
        site.prompt_box[0]: prompt_box,
        site.send_button[0]: send,
    }
    driver = _driver(site, page)

    driver.submit_prompt("hello world")

    # byte-for-byte the original submit_prompt body: click, Ctrl+A,
    # Delete, insert_text, click send — no extra steps introduced by
    # the _paste_and_send extraction.
    assert page.calls == [
        ("click", "prompt_box"),
        ("press", "Control+A"),
        ("press", "Delete"),
        ("insert_text", "hello world"),
        ("click", "send"),
    ]


def test_submit_prompt_still_uses_only_prompt_box_and_send_selectors():
    """submit_prompt must not accidentally start requiring the image
    attach selectors — it stays text-only."""
    site = SITES["gemini"]
    page = FakePage()
    page.locators = {
        site.prompt_box[0]: FakeLocator("prompt_box", page),
        site.send_button[0]: FakeLocator("send", page),
    }
    driver = _driver(site, page)

    driver.submit_prompt("hello gemini")  # must not raise / must not hang

    assert ("insert_text", "hello gemini") in page.calls
    # no attach-menu / file interaction happened on a plain text submit
    assert not any(
        c[0] in ("set_input_files", "file_chooser_set_files")
        for c in page.calls
    )


# --- (d) send-button reload recovery (owner 2026-07-21) ----------------
# A real run's exact failure: "no selector for the send button matched
# within 10s ... site stopped" — a manual page refresh fixed it. The
# driver now does that refresh itself, ONCE, before giving up.

def test_submit_prompt_recovers_via_reload_when_send_button_missing():
    site = SITES["gemini"]
    page = FakePage()
    prompt_box = FakeLocator("prompt_box", page)
    send = FakeLocator("send", page)
    # the send button is ABSENT until the fake reload "fixes" the DOM —
    # mirrors the real site coming back sane after a refresh
    page.locators = {site.prompt_box[0]: prompt_box}
    base_reload = page.reload

    def reload_and_recover():
        base_reload()
        page.locators[site.send_button[0]] = send

    page.reload = reload_and_recover
    driver = _driver(site, page)
    logs: list[str] = []

    driver.submit_prompt("hello gemini", logs.append)

    assert page.calls.count(("reload",)) == 1  # exactly one recovery attempt
    assert ("click", "send") in page.calls
    # the prompt was lost by the reload and re-pasted: typed twice
    # (the failed first attempt, then the post-reload retry)
    assert page.calls.count(("insert_text", "hello gemini")) == 2
    assert any("reloading the page" in line for line in logs)


def test_submit_with_image_reattaches_on_send_reload_recovery():
    """Review finding (owner 2026-07-23): a send-button reload recovery
    mid-``submit_with_image`` drops the attached image. The recovery must
    RE-ATTACH (re-walk the menu, re-set the file) before re-typing —
    otherwise it would silently send a TEXT-ONLY prompt under the
    reference-image filename (a Rule #1 violation)."""
    site = SITES["chatgpt"]
    page = FakePage()
    _wire_attach(site, page, with_input=True)
    send = FakeLocator("send", page)
    # send button ABSENT until the fake reload "fixes" the DOM
    del page.locators[site.send_button[0]]
    base_reload = page.reload

    def reload_and_recover():
        base_reload()
        page.locators[site.send_button[0]] = send

    page.reload = reload_and_recover
    driver = _driver(site, page)

    driver.submit_with_image("C:/out/hero.png", "put the hero in", lambda s: None)

    assert page.calls.count(("reload",)) == 1
    # the image was attached TWICE — initial + re-attach after the reload
    assert page.calls.count(
        ("set_input_files", "file_input", "C:/out/hero.png")
    ) == 2
    # and the prompt DID go out with the image (send clicked), never
    # text-only-without-image
    assert ("click", "send") in page.calls
    assert ("insert_text", "put the hero in") in page.calls
    # the prompt was re-typed after the reload (the failed first attempt,
    # then the post-reload retry)
    assert page.calls.count(("insert_text", "put the hero in")) == 2


def test_submit_prompt_reload_recovery_gives_up_when_still_missing():
    """The send button is STILL missing after the reload -> the
    original SelectorRot propagates (stops the site), exactly as
    before this recovery existed — and only ONE reload is attempted,
    never a retry loop."""
    site = SITES["gemini"]
    page = FakePage()
    page.locators = {site.prompt_box[0]: FakeLocator("prompt_box", page)}
    driver = _driver(site, page)

    with pytest.raises(SelectorRot):
        driver.submit_prompt("hello gemini")

    assert page.calls.count(("reload",)) == 1


def test_submit_prompt_normal_path_never_reloads():
    """MUST NOT REGRESS: when the send button is present on the first
    try (the common case), no reload ever happens — proven both by the
    exact-call-list assertion above (test_submit_prompt_unchanged_
    through_shared_helper) and explicitly here."""
    site = SITES["chatgpt"]
    page = FakePage()
    page.locators = {
        site.prompt_box[0]: FakeLocator("prompt_box", page),
        site.send_button[0]: FakeLocator("send", page),
    }
    driver = _driver(site, page)

    driver.submit_prompt("hello world")

    assert ("reload",) not in page.calls


# --- (e) BUG 3 — "Image generation failed" caught DURING the wait,
# never burning the whole hard timeout (owner 2026-07-21) --------------

_CHATGPT_FAILURE_TEXT = (
    "I wasn't able to generate the image because the image generation"
    " tool encountered an error. I can't retry it automatically after"
    " this kind of failure. Please send the same prompt again (or"
    " simply reply with 'retry'), and I'll generate it on the new"
    " request."
)


class TextLocator:
    """Duck-typed playwright Locator standing for a response
    container: ``count()``/``last``/``inner_text()`` — enough for
    ``_last_response``/``_response_text``. ``holder`` is a one-item
    list so a test can flip the text the driver reads mid-poll."""

    def __init__(self, holder: list[str]):
        self._holder = holder

    def count(self):
        return 1

    @property
    def last(self):
        return self

    def inner_text(self):
        return self._holder[0]


class PresentLocator:
    """Duck-typed Locator for a busy/stop signal that is ALWAYS
    present — mirrors ChatGPT's stuck-forever busy state (BUG 3): the
    done edge this stands for never comes on its own."""

    def count(self):
        return 1

    def nth(self, k):
        return self

    def is_visible(self):
        return True


class FlipLocator:
    """Duck-typed Locator present for ``n_present`` polls, then gone —
    a normal busy signal that clears once generation finishes."""

    def __init__(self, n_present: int):
        self._n = n_present

    def count(self):
        if self._n > 0:
            self._n -= 1
            return 1
        return 0

    def nth(self, k):
        return self

    def is_visible(self):
        return True


def test_chatgpt_ships_image_failed_markers_gemini_does_not():
    """The marker set is ChatGPT-specific (SITES data, not invented in
    the driver) — Gemini's tuple stays empty until the owner captures
    a live Gemini failure text."""
    assert SITES["chatgpt"].image_failed_text_markers != ()
    assert SITES["gemini"].image_failed_text_markers == ()


def test_check_image_failed_raises_on_a_marked_response():
    site = SITES["chatgpt"]
    page = FakePage()
    page.locators[site.response_container[0]] = TextLocator(
        [_CHATGPT_FAILURE_TEXT]
    )
    driver = _driver(site, page)

    with pytest.raises(ImageGenFailed):
        driver._check_image_failed()


def test_check_image_failed_is_a_noop_without_markers_configured():
    """Gemini-safe: the exact same failure text never raises on a site
    whose ``image_failed_text_markers`` is empty."""
    site = SITES["gemini"]
    page = FakePage()
    page.locators[site.response_container[0]] = TextLocator(
        [_CHATGPT_FAILURE_TEXT]
    )
    driver = _driver(site, page)

    driver._check_image_failed()  # must not raise


def test_check_image_failed_is_a_noop_on_a_normal_response():
    site = SITES["chatgpt"]
    page = FakePage()
    page.locators[site.response_container[0]] = TextLocator(
        ["Here is your generated image."]
    )
    driver = _driver(site, page)

    driver._check_image_failed()  # must not raise


# --- refusal scenario classification (owner 2026-07-23) --------------

# The live COPYRIGHT block from the Star Wars run (UV/prompt.txt): note
# it ALSO carries generic safety substrings ("may violate", "retry or
# edit your prompt"), so it proves the most-specific-first ordering — a
# naive scan would misclassify it as safety and pick the wrong preamble.
_CHATGPT_COPYRIGHT_TEXT = (
    "We're so sorry, but the image we created may violate our guardrails"
    " concerning similarity to third-party content. If you think we got"
    " it wrong, please retry or edit your prompt."
)
_CHATGPT_SAFETY_TEXT = (
    "We're so sorry, but the prompt may violate our content policies. If"
    " you think we got it wrong, please retry or edit your prompt."
)


def test_check_markers_classifies_copyright_before_safety():
    """The copyright message must classify as REFUSAL_COPYRIGHT even
    though it also contains the generic safety substrings — categories
    are checked most-specific-first."""
    site = SITES["chatgpt"]
    page = FakePage()
    page.locators[site.response_container[0]] = TextLocator(
        [_CHATGPT_COPYRIGHT_TEXT]
    )
    driver = _driver(site, page)

    with pytest.raises(ItemRefused) as exc:
        driver._check_markers()
    assert exc.value.category == REFUSAL_COPYRIGHT


def test_check_markers_classifies_a_plain_safety_refusal():
    site = SITES["chatgpt"]
    page = FakePage()
    page.locators[site.response_container[0]] = TextLocator(
        [_CHATGPT_SAFETY_TEXT]
    )
    driver = _driver(site, page)

    with pytest.raises(ItemRefused) as exc:
        driver._check_markers()
    assert exc.value.category == REFUSAL_SAFETY


def test_chatgpt_ships_a_copyright_category_gemini_does_not():
    """Copyright markers are ChatGPT SITES data (only ChatGPT has shown
    the third-party-content block); Gemini stays safety-only until a
    live Gemini copyright refusal is captured."""
    assert REFUSAL_COPYRIGHT in SITES["chatgpt"].refusal_markers
    assert REFUSAL_COPYRIGHT not in SITES["gemini"].refusal_markers
    assert REFUSAL_SAFETY in SITES["gemini"].refusal_markers


def test_await_done_raises_image_gen_failed_without_burning_timeout():
    """The exact real failure (owner's log, BUG 3): the busy/stop
    signal never clears for this ChatGPT state, so the SECOND await
    loop ("still generating ...") must catch the failure text WHILE
    still polling instead of waiting out the whole hard
    ``generation_timeout_s``."""
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

    start = time.monotonic()
    with pytest.raises(ImageGenFailed):
        driver.await_done(log=lambda s: None)
    elapsed = time.monotonic() - start
    # caught within a couple of polls, nowhere near the 5s hard timeout
    assert elapsed < 1.0


def test_await_done_normal_response_never_raises_image_gen_failed():
    """MUST NOT REGRESS: a normal successful generation (busy signal
    appears, then clears on its own after a few polls) is byte-behavior
    unchanged — the new text scan never fires on ordinary response
    text."""
    site = SITES["chatgpt"]
    timing = replace(
        TIMING,
        poll_interval_s=0.01,
        progress_log_interval_s=1000.0,
        busy_appear_timeout_s=1.0,
        generation_timeout_s=5.0,
    )
    page = FakePage()
    page.locators[site.busy_signal[0]] = FlipLocator(3)
    page.locators[site.response_container[0]] = TextLocator(
        ["Here is your generated image."]
    )
    driver = SiteDriver(site, timing, "http://unused")
    driver.page = page

    driver.await_done(log=lambda s: None)  # must not raise


# --- (f) BUG 3, second face — "something went wrong" + Retry button
# (owner 2026-07-23) ----------------------------------------------------

# The generic red error turn from the owner's 17/24 stop: no "reply
# retry" text, a native Retry button instead.
_CHATGPT_WENT_WRONG_TEXT = (
    "I wasn't able to generate the image due to an error on my side."
    " Hmm...something seems to have gone wrong."
)


def test_went_wrong_text_is_an_image_failed_marker():
    """The second failure face rides the SAME ImageGenFailed path (its
    markers were folded into image_failed_text_markers), so the driver
    catches it during the wait instead of dropping to a hard-stop
    NoImage as it did live at 17/24."""
    site = SITES["chatgpt"]
    page = FakePage()
    page.locators[site.response_container[0]] = TextLocator(
        [_CHATGPT_WENT_WRONG_TEXT]
    )
    driver = _driver(site, page)

    with pytest.raises(ImageGenFailed):
        driver._check_image_failed()


def test_chatgpt_ships_the_error_retry_button_gemini_does_not():
    """The native Retry button is ChatGPT-specific SITES data; Gemini
    has none, so its ladder simply skips rung 1."""
    assert SITES["chatgpt"].image_error_retry_button != ()
    assert SITES["gemini"].image_error_retry_button == ()


def test_click_error_retry_clicks_the_button_when_present():
    site = SITES["chatgpt"]
    page = FakePage()
    button = FakeLocator("error_retry", page)
    page.locators[site.image_error_retry_button[0]] = button
    driver = _driver(site, page)

    assert driver.click_error_retry(log=lambda s: None) is True
    assert ("click", "error_retry") in page.calls


def test_click_error_retry_false_when_button_absent():
    """ChatGPT has the selector but the button is not on the page right
    now — a normal branch (fall through to the next rung), never loud."""
    site = SITES["chatgpt"]
    page = FakePage()  # nothing wired -> selector matches nothing
    driver = _driver(site, page)

    assert driver.click_error_retry(log=lambda s: None) is False
    assert page.calls == []


def test_click_error_retry_false_when_site_has_no_button():
    """Gemini defines no such selector — the method returns False without
    even querying the DOM."""
    site = SITES["gemini"]
    page = FakePage()
    driver = _driver(site, page)

    assert driver.click_error_retry(log=lambda s: None) is False
    assert page.calls == []


def test_refresh_reloads_then_waits_for_the_composer():
    site = SITES["chatgpt"]
    page = FakePage()
    page.locators[site.prompt_box[0]] = FakeLocator("prompt_box", page)
    driver = _driver(site, page)

    driver.refresh(log=lambda s: None)

    assert ("reload",) in page.calls
