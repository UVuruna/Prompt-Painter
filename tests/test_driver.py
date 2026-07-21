"""Tests for painter.driver.SiteDriver — the project's FIRST driver
tests (GUI rework Phase 17, WEBSITE FIX). Real DOM behavior needs the
owner's live browser session (driver.py has always been verified by
supervised runs, never unit tests); these use minimal duck-typed fakes
for playwright's ``Locator``/``Page`` to prove the parts that ARE
agent-verifiable:

- ``submit_fix`` raises ``FixNotConfigured`` LOUDLY and IMMEDIATELY
  (before touching the page at all) while a site's
  ``attach_button``/``file_input`` are empty — the shipped default
  for both ``SITES`` entries today.
- With fake non-empty selectors, ``submit_fix`` runs the expected
  click-attach -> set_input_files -> paste -> send sequence.
- ``submit_prompt``'s existing text-only flow is byte-identical after
  being routed through the new shared ``_paste_and_send`` helper.
"""

from dataclasses import replace

import pytest

from painter.config import SITES, TIMING, Timing
from painter.driver import FixNotConfigured, SelectorRot, SiteDriver

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


class FakePage:
    """Duck-typed playwright Page: resolves ``locator(selector)`` from
    a dict the test wires up, records every meaningful action (click /
    set_input_files / keyboard press / insert_text) IN ORDER."""

    def __init__(self):
        self.locators: dict[str, FakeLocator] = {}
        self.calls: list[tuple] = []
        self.keyboard = FakeKeyboard(self)

    def locator(self, sel):
        return self.locators.get(sel, _MISSING)

    def reload(self):
        self.calls.append(("reload",))


def _driver(site, page: FakePage) -> SiteDriver:
    driver = SiteDriver(site, FAST, "http://unused")
    driver.page = page
    return driver


# --- (a) the gate: FixNotConfigured, loud + immediate ------------------

@pytest.mark.parametrize("site_key", ["chatgpt", "gemini"])
def test_shipped_sites_ship_website_fix_disabled(site_key):
    """Both real SITES entries are the shipped gated default — no
    invented selectors snuck in."""
    site = SITES[site_key]
    assert site.attach_button == ()
    assert site.file_input == ()


@pytest.mark.parametrize("site_key", ["chatgpt", "gemini"])
def test_submit_fix_raises_loudly_when_not_configured(site_key):
    page = FakePage()
    driver = _driver(SITES[site_key], page)

    with pytest.raises(FixNotConfigured):
        driver.submit_fix("C:/out/img.png", "fix the halo")

    # IMMEDIATE: no selector was even queried before the raise.
    assert page.calls == []


def test_submit_fix_raises_when_only_attach_button_set():
    """Both selectors are required — one alone must not be enough."""
    site = replace(
        SITES["chatgpt"], attach_button=('button[aria-label="Attach"]',)
    )
    page = FakePage()
    driver = _driver(site, page)

    with pytest.raises(FixNotConfigured):
        driver.submit_fix("C:/out/img.png", "fix the halo")
    assert page.calls == []


def test_submit_fix_raises_when_only_file_input_set():
    site = replace(SITES["chatgpt"], file_input=('input[type="file"]',))
    page = FakePage()
    driver = _driver(site, page)

    with pytest.raises(FixNotConfigured):
        driver.submit_fix("C:/out/img.png", "fix the halo")
    assert page.calls == []


# --- (b) configured: the click -> set_input_files -> paste -> send
# sequence -------------------------------------------------------------

def _fixable_site():
    """A copy of the real chatgpt config with WEBSITE FIX selectors
    filled in — exactly the shape the owner will paste in later."""
    return replace(
        SITES["chatgpt"],
        attach_button=('button[aria-label="Attach"]',),
        file_input=('input[type="file"]',),
    )


def test_submit_fix_sequence_when_configured():
    site = _fixable_site()
    page = FakePage()
    attach = FakeLocator("attach", page)
    # A real <input type=file> is routinely hidden by design — prove
    # submit_fix still finds it (require_visible=False), unlike every
    # other selector in the driver.
    file_input = FakeLocator("file_input", page, visible=False)
    prompt_box = FakeLocator("prompt_box", page)
    send = FakeLocator("send", page)
    page.locators = {
        site.attach_button[0]: attach,
        site.file_input[0]: file_input,
        site.prompt_box[0]: prompt_box,
        site.send_button[0]: send,
    }
    driver = _driver(site, page)

    driver.submit_fix("C:/out/img.png", "fix the halo")

    assert file_input.set_files == "C:/out/img.png"
    calls = page.calls
    # click attach -> set_input_files -> paste (insert_text) -> send
    assert calls[0] == ("click", "attach")
    assert calls[1] == ("set_input_files", "file_input", "C:/out/img.png")
    i_attach = calls.index(("click", "attach"))
    i_files = calls.index(("set_input_files", "file_input", "C:/out/img.png"))
    i_text = calls.index(("insert_text", "fix the halo"))
    i_send = calls.index(("click", "send"))
    assert i_attach < i_files < i_text < i_send
    # the follow-up prompt reused the SAME paste path as submit_prompt:
    # click prompt box, select-all, delete, insert_text, click send.
    assert ("click", "prompt_box") in calls
    assert ("press", "Control+A") in calls
    assert ("press", "Delete") in calls


def test_submit_fix_never_touches_prompt_box_before_upload():
    """The image must be attached before the fix note is typed — a
    stricter ordering check than the interleaved index asserts above."""
    site = _fixable_site()
    page = FakePage()
    page.locators = {
        site.attach_button[0]: FakeLocator("attach", page),
        site.file_input[0]: FakeLocator("file_input", page, visible=False),
        site.prompt_box[0]: FakeLocator("prompt_box", page),
        site.send_button[0]: FakeLocator("send", page),
    }
    driver = _driver(site, page)

    driver.submit_fix("C:/out/img.png", "fix the halo")

    kinds_before_upload = []
    for call in page.calls:
        if call[0] == "set_input_files":
            break
        kinds_before_upload.append(call)
    # only the attach click happens before the upload — no prompt-box
    # interaction starts early
    assert kinds_before_upload == [("click", "attach")]


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
    """submit_prompt must not accidentally start requiring the new
    attach_button/file_input selectors — it stays text-only."""
    site = SITES["gemini"]
    assert site.attach_button == ()  # shipped default
    page = FakePage()
    page.locators = {
        site.prompt_box[0]: FakeLocator("prompt_box", page),
        site.send_button[0]: FakeLocator("send", page),
    }
    driver = _driver(site, page)

    driver.submit_prompt("hello gemini")  # must not raise / must not hang

    assert ("insert_text", "hello gemini") in page.calls


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
