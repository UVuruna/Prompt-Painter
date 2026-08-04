"""Tests for painter.driver.SiteDriver — the project's FIRST driver
tests (GUI rework Phase 17, WEBSITE FIX; extended for the F1 turn-based
protocol, owner 2026-07-29). Real DOM behavior needs the owner's live
browser session (driver.py has always been verified by supervised runs,
never unit tests); these use minimal duck-typed fakes for playwright's
``Locator``/``Page`` to prove the parts that ARE agent-verifiable:

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
- F1: a submit is not "sent" until CONFIRMED (composer emptied + our
  text is the newest user turn); ``await_done``/``extract_image`` are
  scoped to a pre-submit ``Baseline`` (turn count + last image src), so
  a leftover busy button or the PREVIOUS item's image can never be
  mistaken for OUR result.
"""

import base64
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
    Baseline,
    DriverError,
    ImageGenFailed,
    ItemRefused,
    ModelDegraded,
    NoImage,
    SelectorRot,
    SendVanished,
    SiteDriver,
    TerminalState,
    normalize_text,
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
    actions across several different locators. ``text`` backs
    ``inner_text()`` (the F1 protocol reads composer / user-turn text
    straight off the locator); ``attrs`` backs ``get_attribute()``;
    ``on_click`` (settable via the constructor or assigned afterwards)
    runs AFTER the click is recorded — the confirmed-send flow wires it
    to simulate a real send: copy the composer's text into a user-turn
    locator, then empty the composer.
    """

    def __init__(
        self,
        name: str,
        page: "FakePage",
        *,
        visible: bool = True,
        text: str = "",
        attrs: dict | None = None,
        on_click=None,
    ):
        self.name = name
        self.page = page
        self._visible = visible
        self.set_files = None
        self.text = text
        self.attrs = attrs or {}
        self.on_click = on_click

    def count(self):
        return 1

    def nth(self, k):
        assert k == 0
        return self

    @property
    def first(self):
        return self

    @property
    def last(self):
        return self

    def is_visible(self):
        return self._visible

    def inner_text(self):
        return self.text

    def get_attribute(self, name):
        return self.attrs.get(name)

    def click(self):
        self.page.calls.append(("click", self.name))
        if self.on_click is not None:
            self.on_click()

    def set_input_files(self, path):
        self.set_files = path
        self.page.calls.append(("set_input_files", self.name, path))


class FakeKeyboard:
    """``press("Delete")`` and ``insert_text`` mutate ``page.composer``
    (when set) so the F1 verification reads (``_composer_text`` /
    ``_composer_holds``) see the SAME object the test wired up."""

    def __init__(self, page: "FakePage"):
        self.page = page

    def press(self, key):
        self.page.calls.append(("press", key))
        if key == "Delete" and self.page.composer is not None:
            self.page.composer.text = ""

    def insert_text(self, text):
        self.page.calls.append(("insert_text", text))
        if self.page.composer is not None:
            self.page.composer.text = text


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
    ORDER. ``composer`` (F1) is the FakeLocator the keyboard fakes
    mutate — set directly or via ``_wire_send_flow``."""

    def __init__(self):
        self.locators: dict[str, FakeLocator] = {}
        self.calls: list[tuple] = []
        self.keyboard = FakeKeyboard(self)
        self.chooser_files = None  # set by _FakeFileChooser.set_files
        self.composer: FakeLocator | None = None

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


def _wire_send_flow(site, page, prompt_box, send):
    """Wire the F1 confirmed-send flow onto ``prompt_box``/``send``:
    ``page.composer`` becomes ``prompt_box`` (so the keyboard fakes
    mutate the SAME locator ``_composer_text()`` reads back), and
    ``send``'s click copies the composer's CURRENT text into a
    user-turn FakeLocator registered at ``site.user_turn[0]`` before
    emptying the composer — mirroring a real send: the box clears and
    the text becomes the newest user turn, which is exactly what
    ``_confirm_sent`` polls for. Used by every test that drives
    ``submit_prompt``/``submit_with_image`` all the way through
    confirmation (including the reload-recovery tests, where the hook
    must be re-wired onto the send button injected post-reload)."""
    page.composer = prompt_box

    def _on_send_click():
        page.locators[site.user_turn[0]] = FakeLocator(
            "user_turn", page, text=prompt_box.text
        )
        prompt_box.text = ""

    send.on_click = _on_send_click
    return send


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

    # loud and immediate: no click/attach action was ever taken —
    # _ensure_ready/capture_baseline only READ selectors (safely, on an
    # empty page) before the gate raises
    assert page.calls == []


# --- (b) configured: expand "+" -> pick add-image -> attach -> preview
# -> paste -> send -----------------------------------------------------

def _wire_attach(site, page, *, with_input: bool):
    """Wire the '+' step, the add-image option, the preview, prompt box
    and send onto ``page`` (and the hidden file input when the site uses
    one) — and the F1 confirmed-send flow, so every attach test can
    drive ``submit_with_image`` to completion. Returns the FakeLocator
    map for extra assertions."""
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
    _wire_send_flow(site, page, prompt_box, send)
    loc = {
        "plus": plus,
        "option": option,
        "preview": preview,
        "prompt_box": prompt_box,
        "send": send,
    }
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
    i_files = calls.index(
        ("set_input_files", "file_input", "C:/out/hero.png")
    )
    i_text = calls.index(("insert_text", "put the hero in the scene"))
    i_send = calls.index(("click", "send"))
    # a person's path: expand "+", attach, THEN paste+send. The
    # add-image ROW is never clicked when the input is already there —
    # that click opens the native OS dialog (owner 2026-08-04)
    assert ("click", "option") not in calls
    assert i_plus < i_files < i_text < i_send


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


def test_submit_with_image_lazy_input_falls_back_to_the_chooser():
    """A menu that renders its <input type=file> only on the row click
    still attaches: the driver clicks the row inside file-chooser
    interception, so a native dialog is CONSUMED, never left open."""
    site = SITES["chatgpt"]
    page = FakePage()
    _wire_attach(site, page, with_input=False)
    driver = _driver(site, page)

    driver.submit_with_image("C:/out/hero.png", "put the hero in")

    assert page.chooser_files == "C:/out/hero.png"
    assert ("click", "option") in page.calls


def test_submit_with_image_list_passes_all_paths_in_order():
    """MULTI-ATTACH (faza 2): a list of resolved paths rides ONE picker
    interaction, order preserved — the prompt's "FIRST/SECOND attached
    image" depends on it."""
    site = SITES["chatgpt"]
    page = FakePage()
    loc = _wire_attach(site, page, with_input=True)
    driver = _driver(site, page)

    driver.submit_with_image(
        ["C:/refs/Vader.png", "C:/refs/Luke.png"], "two refs"
    )

    assert loc["file_input"].set_files == [
        "C:/refs/Vader.png", "C:/refs/Luke.png",
    ]


def test_submit_with_image_single_item_list_unwraps_to_the_proven_form():
    site = SITES["chatgpt"]
    page = FakePage()
    loc = _wire_attach(site, page, with_input=True)
    driver = _driver(site, page)

    driver.submit_with_image(["C:/out/hero.png"], "one ref")

    assert loc["file_input"].set_files == "C:/out/hero.png"


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
    # only the "+" expand happens before upload — no prompt-box
    # interaction starts early
    assert before_upload == [("click", "plus")]


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


# --- (c) submit_prompt through the shared _paste_and_send helper -------

def test_submit_prompt_empty_composer_skips_delete():
    """Owner 2026-07-29: "ako je empty ne treba delete" — an EMPTY
    composer gets NO Ctrl+A/Delete, just click, insert_text, send. The
    send is CONFIRMED via the wired flow (composer clears, our text
    becomes the newest user turn)."""
    site = SITES["chatgpt"]
    page = FakePage()
    prompt_box = FakeLocator("prompt_box", page)
    send = FakeLocator("send", page)
    page.locators = {
        site.prompt_box[0]: prompt_box,
        site.send_button[0]: send,
    }
    _wire_send_flow(site, page, prompt_box, send)
    driver = _driver(site, page)

    driver.submit_prompt("hello world")

    assert page.calls == [
        ("click", "prompt_box"),
        ("insert_text", "hello world"),
        ("click", "send"),
    ]


def test_submit_prompt_composer_with_leftover_text_deletes_first():
    """The companion case: the composer STARTS with leftover text — the
    driver clears it (Ctrl+A + Delete) before pasting the new prompt."""
    site = SITES["chatgpt"]
    page = FakePage()
    prompt_box = FakeLocator("prompt_box", page, text="old junk")
    send = FakeLocator("send", page)
    page.locators = {
        site.prompt_box[0]: prompt_box,
        site.send_button[0]: send,
    }
    _wire_send_flow(site, page, prompt_box, send)
    driver = _driver(site, page)

    driver.submit_prompt("hello world")

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
    prompt_box = FakeLocator("prompt_box", page)
    send = FakeLocator("send", page)
    page.locators = {
        site.prompt_box[0]: prompt_box,
        site.send_button[0]: send,
    }
    _wire_send_flow(site, page, prompt_box, send)
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
    page.composer = prompt_box
    base_reload = page.reload

    def reload_and_recover():
        base_reload()
        prompt_box.text = ""  # a reload wipes the unsent composer text
        page.locators[site.send_button[0]] = send
        _wire_send_flow(site, page, prompt_box, send)

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
    loc = _wire_attach(site, page, with_input=True)
    prompt_box = loc["prompt_box"]
    send = FakeLocator("send", page)
    # send button ABSENT until the fake reload "fixes" the DOM
    del page.locators[site.send_button[0]]
    base_reload = page.reload

    def reload_and_recover():
        base_reload()
        prompt_box.text = ""  # a reload wipes the unsent composer text
        page.locators[site.send_button[0]] = send
        _wire_send_flow(site, page, prompt_box, send)

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
    prompt_box = FakeLocator("prompt_box", page)
    page.locators = {site.prompt_box[0]: prompt_box}
    page.composer = prompt_box  # so the typed text actually verifies
    driver = _driver(site, page)

    with pytest.raises(SelectorRot):
        driver.submit_prompt("hello gemini")

    assert page.calls.count(("reload",)) == 1


def test_submit_prompt_normal_path_never_reloads():
    """MUST NOT REGRESS: when the send button is present on the first
    try (the common case), no reload ever happens — proven both by the
    exact-call-list assertion above (test_submit_prompt_empty_composer_
    skips_delete) and explicitly here."""
    site = SITES["chatgpt"]
    page = FakePage()
    prompt_box = FakeLocator("prompt_box", page)
    send = FakeLocator("send", page)
    page.locators = {
        site.prompt_box[0]: prompt_box,
        site.send_button[0]: send,
    }
    _wire_send_flow(site, page, prompt_box, send)
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


class PresentLocator:
    """Duck-typed Locator for a busy/stop signal that is ALWAYS
    present — mirrors ChatGPT's stuck-forever busy state (BUG 3): the
    OLD done edge this stood for never came on its own."""

    def count(self):
        return 1

    def nth(self, k):
        return self

    def is_visible(self):
        return True


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


def test_chatgpt_ships_image_failed_markers_gemini_does_not():
    """The marker set is ChatGPT-specific (SITES data, not invented in
    the driver) — Gemini's tuple stays empty until the owner captures
    a live Gemini failure text."""
    assert SITES["chatgpt"].image_failed_text_markers != ()
    assert SITES["gemini"].image_failed_text_markers == ()


def test_check_image_failed_raises_on_a_marked_response():
    site = SITES["chatgpt"]
    driver = _driver(site, FakePage())

    with pytest.raises(ImageGenFailed):
        driver._check_image_failed(_CHATGPT_FAILURE_TEXT)


def test_check_image_failed_is_a_noop_without_markers_configured():
    """Gemini-safe: the exact same failure text never raises on a site
    whose ``image_failed_text_markers`` is empty."""
    site = SITES["gemini"]
    driver = _driver(site, FakePage())

    driver._check_image_failed(_CHATGPT_FAILURE_TEXT)  # must not raise


def test_check_image_failed_is_a_noop_on_a_normal_response():
    site = SITES["chatgpt"]
    driver = _driver(site, FakePage())

    driver._check_image_failed("Here is your generated image.")  # no raise


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
    driver = _driver(site, FakePage())

    with pytest.raises(ItemRefused) as exc:
        driver._check_markers(_CHATGPT_COPYRIGHT_TEXT)
    assert exc.value.category == REFUSAL_COPYRIGHT


def test_check_markers_classifies_a_plain_safety_refusal():
    site = SITES["chatgpt"]
    driver = _driver(site, FakePage())

    with pytest.raises(ItemRefused) as exc:
        driver._check_markers(_CHATGPT_SAFETY_TEXT)
    assert exc.value.category == REFUSAL_SAFETY


def test_gemini_generic_guideline_refusal_classifies_as_safety():
    """The market-scene incident markers (owner 2026-07-25) — generic
    "against my guidelines" Gemini refusals classify as REFUSAL_SAFETY,
    the category the safer-retry preamble picks off of."""
    site = SITES["gemini"]
    driver = _driver(site, FakePage())

    for text in (
        "I can't help with this particular request, sorry.",
        "Sorry, this may go against my guidelines.",
    ):
        with pytest.raises(ItemRefused) as exc:
            driver._check_markers(text)
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
    driver = _driver(site, FakePage())

    with pytest.raises(ImageGenFailed):
        driver._check_image_failed(_CHATGPT_WENT_WRONG_TEXT)


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


# --- (g) F1 turn-based protocol regressions (owner 2026-07-29) --------

def test_timing_has_the_f1_protocol_fields():
    t = Timing()
    assert t.busy_clear_grace_s > 0
    assert t.send_confirm_timeout_s > 0


def test_sites_declare_a_user_turn_selector():
    assert SITES["chatgpt"].user_turn != ()
    assert SITES["gemini"].user_turn != ()


def test_ensure_ready_refreshes_over_a_stuck_busy_signal():
    """F1 root cause 1 (owner 2026-07-29): a busy signal STILL PRESENT
    from the previous item must never be sent over. LIVE-RUN HOTFIX:
    the driver now WAITS OUT a busy window first (a busy site may
    honestly be finishing the previous item — refreshing early KILLED
    it mid-work); only a busy signal that outlives ``busy_stuck_timeout_s``
    is stuck, and only then does the pre-send REFRESH happen — still
    strictly BEFORE the send click."""
    site = SITES["gemini"]
    timing = replace(FAST, busy_stuck_timeout_s=0.05)
    page = FakePage()
    page.locators[site.busy_signal[0]] = PresentLocator()  # never clears
    prompt_box = FakeLocator("prompt_box", page)
    send = FakeLocator("send", page)
    page.locators[site.prompt_box[0]] = prompt_box
    page.locators[site.send_button[0]] = send
    _wire_send_flow(site, page, prompt_box, send)
    driver = SiteDriver(site, timing, "http://unused")
    driver.page = page
    logs: list[str] = []

    driver.submit_prompt("hello gemini", logs.append)

    i_reload = page.calls.index(("reload",))
    i_send = page.calls.index(("click", "send"))
    assert i_reload < i_send
    assert any("stuck" in line.lower() for line in logs)


# --- the 7-silent-minutes bug (owner 2026-08-04) ----------------------
# A live ChatGPT run lost 7m06s between two items: the previous item's
# stop button stayed set AFTER its image was saved, and the pre-send
# busy wait honestly burned the whole 420s generation_timeout_s — with
# NOTHING in the GUI log, because run_sheet called submit_prompt without
# passing its log. Both halves get a regression test.

def test_ensure_ready_busy_wait_uses_its_own_budget_not_generation():
    """The pre-send busy wait must be bounded by ``busy_stuck_timeout_s``
    — never by the (far longer) ``generation_timeout_s`` it used to
    borrow."""
    site = SITES["gemini"]
    timing = replace(
        FAST, busy_stuck_timeout_s=0.05, generation_timeout_s=600.0
    )
    page = FakePage()
    page.locators[site.busy_signal[0]] = PresentLocator()  # never clears
    prompt_box = FakeLocator("prompt_box", page)
    send = FakeLocator("send", page)
    page.locators[site.prompt_box[0]] = prompt_box
    page.locators[site.send_button[0]] = send
    _wire_send_flow(site, page, prompt_box, send)
    driver = SiteDriver(site, timing, "http://unused")
    driver.page = page

    started = time.monotonic()
    driver.submit_prompt("hello gemini", lambda s: None)

    # bounded by busy_stuck_timeout_s (0.05s), not generation (600s)
    assert time.monotonic() - started < 30.0
    assert ("reload",) in page.calls


def test_ensure_ready_refreshes_at_once_when_busy_is_known_stuck():
    """When ``await_done`` returned on OUR loaded image while the busy
    signal was STILL set, the stop button is PROVABLY stuck — the next
    submit must refresh IMMEDIATELY instead of waiting the signal out
    (the 7 lost minutes)."""
    site = SITES["gemini"]
    timing = replace(FAST, busy_stuck_timeout_s=600.0)
    page = FakePage()
    page.locators[site.busy_signal[0]] = PresentLocator()  # never clears
    prompt_box = FakeLocator("prompt_box", page)
    send = FakeLocator("send", page)
    page.locators[site.prompt_box[0]] = prompt_box
    page.locators[site.send_button[0]] = send
    _wire_send_flow(site, page, prompt_box, send)
    driver = SiteDriver(site, timing, "http://unused")
    driver.page = page
    driver._busy_known_stuck = True  # what await_done recorded
    logs: list[str] = []

    started = time.monotonic()
    driver.submit_prompt("hello gemini", logs.append)

    # no wait at all, despite a 600s busy budget
    assert time.monotonic() - started < 30.0
    assert ("reload",) in page.calls
    assert any("stuck" in line.lower() for line in logs)
    # the flag is consumed, never left latched for the next item
    assert driver._busy_known_stuck is False


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


def test_type_into_box_retypes_once_on_composer_mismatch():
    """A pasted prompt that lands GARBLED (the composer holds something
    else) gets ONE silent retype — the second attempt succeeds and the
    driver proceeds without raising."""
    site = SITES["chatgpt"]
    page = FakePage()
    prompt_box = FakeLocator("prompt_box", page)
    page.locators[site.prompt_box[0]] = prompt_box
    page.composer = prompt_box
    calls = {"n": 0}
    real_insert = page.keyboard.insert_text

    def flaky_insert_text(text):
        calls["n"] += 1
        if calls["n"] == 1:
            page.calls.append(("insert_text", text))
            prompt_box.text = "garbled nonsense"  # landed wrong
        else:
            real_insert(text)

    page.keyboard.insert_text = flaky_insert_text
    driver = _driver(site, page)

    driver._type_into_box("hello world")  # must not raise

    assert calls["n"] == 2
    assert prompt_box.text == "hello world"


def test_confirm_sent_raises_loudly_when_composer_never_empties():
    """No hook wired on ``send`` — the composer never clears and no user
    turn ever appears, so the send can never be CONFIRMED: a loud
    DriverError, never a silent proceed."""
    site = SITES["gemini"]
    timing = replace(FAST, send_confirm_timeout_s=0.05)
    page = FakePage()
    prompt_box = FakeLocator("prompt_box", page)
    send = FakeLocator("send", page)  # on_click does nothing
    page.locators = {
        site.prompt_box[0]: prompt_box,
        site.send_button[0]: send,
    }
    page.composer = prompt_box
    driver = SiteDriver(site, timing, "http://unused")
    driver.page = page

    with pytest.raises(DriverError) as exc:
        driver.submit_prompt("hello gemini")
    assert "NOT confirmed" in str(exc.value)


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


# --- (h) F2 model degradation (owner 2026-07-29) ------------------------
# Gemini's "Limit reached. Continuing with Flash-Lite." banner: the
# image quota is spent but the chat continues on a weaker model.
# ``_check_degrade_banner`` runs BEFORE ``_check_image_failed``/
# ``_check_markers`` in both ``await_done`` and ``extract_image``, so a
# degrade banner classifies as ``ModelDegraded`` even though the same
# response text would also match a plain quota marker.

_GEMINI_DEGRADE_BANNER_TEXT = (
    "Limit reached. Continuing with Flash-Lite. Some features aren't"
    " available until your limit resets on Jul 25 at 2:18 PM."
)


def test_gemini_has_a_degrade_banner_chatgpt_does_not():
    assert SITES["gemini"].degrade_banner != ()
    assert SITES["chatgpt"].degrade_banner == ()


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


# --- (i) F1b user-turn anchoring (owner 2026-08-04) --------------------
# The Padmé/Qui-Gon incident: Gemini silently DROPPED the confirmed
# Padmé prompt; the old "nothing happened" verdict then allowed a blind
# continue nudge, Gemini regenerated the PREVIOUS request, and a
# Qui-Gon badge was saved as Padme_v3_gem.png. Same run, ChatGPT face:
# a safer retry generated for 4 minutes, its refusal WAS in the DOM,
# but the turn COUNT never exceeded the baseline (long-chat DOM) — so
# the site was stopped over "no new turn". The cure for both: pair the
# result to OUR OWN user turn by DOM position, and treat a vanished
# user turn as its own loud verdict (SendVanished -> re-send the item's
# own prompt, never the content-blind nudge).

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


def test_submit_prompt_records_the_sent_head_for_anchoring():
    site = SITES["chatgpt"]
    page = FakePage()
    prompt_box = FakeLocator("prompt_box", page)
    send = FakeLocator("send", page)
    page.locators = {
        site.prompt_box[0]: prompt_box,
        site.send_button[0]: send,
    }
    _wire_send_flow(site, page, prompt_box, send)
    driver = _driver(site, page)

    driver.submit_prompt("Hello   WORLD, anchored")

    assert driver._sent_head == normalize_text(
        "Hello   WORLD, anchored"
    )[:60]


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
    driver._sent_head = normalize_text(
        "ROUND medallion, aged bronze relief — Padmé"
    )[:60]

    with pytest.raises(SendVanished):
        driver.await_done(log=lambda s: None)


def test_send_vanished_even_when_the_previous_prompt_shares_our_head():
    """Two colored-variant prompts share the same 60-char head, so the
    text check alone cannot see the vanish — the user-turn COUNT (no
    growth past the baseline) must catch it."""
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
    driver._sent_head = normalize_text(shared)[:60]

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
    driver._sent_head = normalize_text(
        "This is a TRANSFORMATIVE homage retry"
    )[:60]

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
    driver._sent_head = normalize_text(
        "This is a TRANSFORMATIVE homage retry"
    )[:60]

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
    driver._sent_head = normalize_text(
        "our Padmé prompt, still awaiting its answer"
    )[:60]

    with pytest.raises(NoImage) as exc:
        driver.await_done(log=lambda s: None)
    assert exc.value.had_text is False  # honest "nothing arrived"
