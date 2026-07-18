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
