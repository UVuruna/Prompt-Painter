"""``painter.driver.classify`` — page text in, typed error out.

The refusal markers (copyright before safety), the "image generation
failed" lines, the "something went wrong" variant, and which site ships
which marker set at all. A quota wall must never be blind-retried as if
it were a timeout, and that verdict is made here.

Split from ``tests/test_driver.py`` alongside the driver package (audit
``docs/AUDIT-OOP-2026-08-18.md`` -> R4). Shared fakes:
``tests/driver_fakes.py``.
"""

import pytest
from painter.config import (
    REFUSAL_COPYRIGHT,
    REFUSAL_SAFETY,
    SITES,
)
from painter.driver import ImageGenFailed, ItemRefused
from driver_fakes import (
    FakePage,
    _CHATGPT_COPYRIGHT_TEXT,
    _CHATGPT_FAILURE_TEXT,
    _driver,
)


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


def test_gemini_has_a_degrade_banner_chatgpt_does_not():
    assert SITES["gemini"].degrade_banner != ()
    assert SITES["chatgpt"].degrade_banner == ()
