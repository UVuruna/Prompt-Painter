"""``painter.driver.recovery`` — one rung of the recovery ladder at a
time.

The site's own error-Retry button (present for ChatGPT, absent for
Gemini) and ``refresh``, which reloads and then waits for the composer —
giving a slow reload one more chance before failing loudly when the
composer is really gone.

Split from ``tests/test_driver.py`` alongside the driver package (audit
``docs/AUDIT-OOP-2026-08-18.md`` -> R4). Shared fakes:
``tests/driver_fakes.py``.
"""

from dataclasses import replace
import pytest
from painter.config import SITES
from painter.driver import DriverError, SiteDriver
from driver_fakes import (
    FAST,
    FakeLocator,
    FakePage,
    _driver,
)


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


def test_refresh_gives_a_slow_reload_one_more_chance():
    """The 14:52:32 ChatGPT stop (UV/prompt.txt:2107): a single slow
    reload — the composer simply not painted within selector_timeout_s
    — ended a run at 38/69 collections. A reload that lands slowly is
    ordinary web behaviour, not selector rot, so it earns ONE more
    reload before the loud raise."""
    site = SITES["chatgpt"]

    class SlowPage(FakePage):
        def reload(self):
            super().reload()
            if len([c for c in self.calls if c == ("reload",)]) >= 2:
                self.locators[site.prompt_box[0]] = FakeLocator(
                    "prompt_box", self
                )

    page = SlowPage()
    driver = SiteDriver(site, replace(FAST, selector_timeout_s=0.05),
                        "http://unused")
    driver.page = page

    driver.refresh(log=lambda s: None)

    assert [c for c in page.calls if c == ("reload",)] == [
        ("reload",), ("reload",)
    ]


def test_refresh_still_fails_loudly_when_the_composer_is_really_gone():
    """The second chance widens the timing tolerance, it never softens
    the verdict: a composer that is gone for good is still loud."""
    site = SITES["chatgpt"]
    page = FakePage()
    driver = SiteDriver(site, replace(FAST, selector_timeout_s=0.05),
                        "http://unused")
    driver.page = page

    with pytest.raises(DriverError):
        driver.refresh(log=lambda s: None)
