"""Quota reset-time parsing (owner's #2) — config patterns only.

The two live-captured quota messages (2026-07-17/18) are the golden
inputs; the no-time Gemini message must yield None, never a guess.
"""

from painter.config import parse_quota_reset
from painter.driver import TerminalState

CHATGPT_MINUTES = (
    "You've hit the Plus plan limit for image generations requests."
    " You can create more images when the limit resets in 27 minutes."
)
CHATGPT_HOURS = (
    "You've hit the Plus plan limit for image generations requests."
    " You can create more images when the limit resets in 14 hours."
)
GEMINI_NO_TIME = (
    "I can create more images as soon as your limit resets."
    " Check your usage in Settings."
)


def test_minutes_from_the_live_chatgpt_message():
    assert parse_quota_reset(CHATGPT_MINUTES) == 27 * 60.0


def test_hours_from_the_live_chatgpt_message():
    assert parse_quota_reset(CHATGPT_HOURS) == 14 * 3600.0


def test_short_unit_and_case():
    assert parse_quota_reset("Limit resets in 5 min.") == 300.0
    assert parse_quota_reset("resets IN 1 HOUR") == 3600.0


def test_serbian_variants():
    assert parse_quota_reset("Ograničenje se resetuje za 27 minuta.") == 1620.0
    assert parse_quota_reset("Pokušajte ponovo za 2 sata.") == 7200.0


def test_no_time_yields_none():
    assert parse_quota_reset(GEMINI_NO_TIME) is None
    assert parse_quota_reset("") is None
    assert parse_quota_reset("too many requests") is None


def test_terminal_state_carries_the_field():
    exc = TerminalState("quota", retry_after_s=1620.0)
    assert exc.retry_after_s == 1620.0
    assert TerminalState("quota").retry_after_s is None


# --- F2 (owner 2026-07-29): the ABSOLUTE banner phrasing ("... on Jul
# 25 at 2:18 PM") — Gemini's model-degradation banner names a moment,
# not a relative wait. The moment can be earlier THIS year or already
# passed (rolling to next year), so the exact seconds value is not
# reproducible here — only that it parses to a positive, real offset.

GEMINI_DEGRADE_BANNER = (
    "Limit reached. Continuing with Flash-Lite. Some features aren't"
    " available until your limit resets on Jul 25 at 2:18 PM."
)


def test_absolute_banner_phrasing_parses_to_a_positive_offset():
    result = parse_quota_reset(GEMINI_DEGRADE_BANNER)
    assert result is not None
    assert result > 0


def test_relative_phrase_still_wins_when_both_are_present():
    """A message carrying BOTH a relative wait and the absolute banner
    phrasing must use the relative sum — the absolute parse is only a
    fallback for when no relative phrase matched."""
    text = (
        "Limit resets in 27 minutes (full reset on Jul 25 at 2:18 PM)."
    )
    assert parse_quota_reset(text) == 27 * 60.0


def test_absolute_phrasing_unparseable_stays_none():
    # names no month/day/time at all — neither pattern matches
    assert parse_quota_reset("until your limit resets soon") is None
