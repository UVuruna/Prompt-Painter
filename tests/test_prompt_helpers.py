"""F7 regression tests (owner 2026-07-29, REWORK.md) — the per-agent
prompt helpers.

The pre-F7 baked site laws (ChatGPT anti-grain, Gemini no-mirror)
moved VERBATIM into ``PROMPT_HELPERS`` with ``HELPER_DEFAULTS``
keeping them ON for their sites — so the DEFAULT suffix must stay
byte-identical to the old behavior, while every helper is now a
per-agent switch.
"""

from painter.config import (
    BACKGROUND_CUSTOM,
    HELPER_CHOICES,
    HELPER_DEFAULTS,
    PROMPT_HELPERS,
    prompt_suffix,
)


def test_default_helpers_keep_the_old_site_laws():
    """helpers=None resolves HELPER_DEFAULTS — the old baked laws."""
    gpt = prompt_suffix("chatgpt", "none")
    gem = prompt_suffix("gemini", "none")
    assert "NO film grain" in gpt  # the anti-grain law, still on
    assert "NO reflections" in gem  # the no-mirror law, still on
    assert "NO reflections" not in gpt
    assert "NO film grain" not in gem


def test_helpers_off_strips_the_law():
    """The owner can now switch a site's old law OFF."""
    assert prompt_suffix("chatgpt", "none", helpers=()) == ""
    assert prompt_suffix("gemini", "none", helpers=()) == ""


def test_no_empty_space_is_new_and_default_off():
    assert "no_empty_space" in PROMPT_HELPERS
    for site, defaults in HELPER_DEFAULTS.items():
        assert "no_empty_space" not in defaults, site
    on = prompt_suffix("gemini", "none", helpers=("no_empty_space",))
    assert "FILLS the canvas" in on
    assert "NO reflections" not in on  # only the asked-for helper


def test_helpers_append_in_stable_choice_order():
    both = prompt_suffix(
        "chatgpt", "none", helpers=("no_grainy", "no_mirror"),
    )
    # HELPER_CHOICES order wins regardless of the input tuple's order
    assert both.index("NO reflections") < both.index("NO film grain")
    assert tuple(HELPER_CHOICES)[0] == "no_mirror"


def test_custom_background_uses_the_picked_hex():
    suffix = prompt_suffix(
        "gemini", BACKGROUND_CUSTOM, helpers=(), custom_hex="#22aa55",
    )
    assert "#22aa55" in suffix
    assert "one flat color" in suffix


def test_custom_background_without_hex_falls_back_white():
    suffix = prompt_suffix("gemini", BACKGROUND_CUSTOM, helpers=())
    assert "#ffffff" in suffix
