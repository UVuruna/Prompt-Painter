"""The fake Playwright surface the whole ``painter.driver`` suite drives.

Real DOM behaviour needs the owner's live browser session (the driver has
always been verified by supervised runs, never unit tests); these minimal
duck-typed stand-ins for playwright's ``Locator``/``Page`` are what makes
the AGENT-verifiable parts testable at all.

ONE module rather than a copy per suite: when ``tests/test_driver.py``
split alongside the ``painter/driver/`` package (audit
``docs/AUDIT-OOP-2026-08-18.md`` -> R4), four suites would otherwise have
carried the same ~240 lines of fakes.
"""

from dataclasses import replace
from painter.config import TIMING, Timing
from painter.driver import SiteDriver


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


_CHATGPT_FAILURE_TEXT = (
    "I wasn't able to generate the image because the image generation"
    " tool encountered an error. I can't retry it automatically after"
    " this kind of failure. Please send the same prompt again (or"
    " simply reply with 'retry'), and I'll generate it on the new"
    " request."
)


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


# The live COPYRIGHT block from the Star Wars run (UV/prompt.txt): note
# it ALSO carries generic safety substrings ("may violate", "retry or
# edit your prompt"), so it proves the most-specific-first ordering — a
# naive scan would misclassify it as safety and pick the wrong preamble.
_CHATGPT_COPYRIGHT_TEXT = (
    "We're so sorry, but the image we created may violate our guardrails"
    " concerning similarity to third-party content. If you think we got"
    " it wrong, please retry or edit your prompt."
)
