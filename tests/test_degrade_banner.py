"""F2 gap fix (owner 2026-07-29) — the degradation banner asks EVEN
WHILE images still arrive (Gemini quietly rendering on Flash-Lite),
once per run, after the save (the made image is never wasted)."""

from dataclasses import replace
from pathlib import Path

import pytest

from painter.config import SITES, TIMING
from painter.driver import TerminalState
from painter.runner import run_sheet
from painter.sheet_parser import PromptItem, Sheet

from test_runner_paths_and_save import FakeDriver

FAST = replace(TIMING, pause_min_s=0.0, pause_max_s=0.0)

BANNER = (
    "Limit reached. Continuing with Flash-Lite. Some features aren't"
    " available until your limit resets on Jul 25 at 2:18 PM."
)


class BannerDriver(FakeDriver):
    """Images WORK, but the degradation banner is up the whole time."""

    def degrade_banner_text(self):
        return BANNER


def make_sheet(tmp_path: Path, n: int = 2) -> Sheet:
    source = tmp_path / "fake_prompts.md"
    source.write_text("# Fake Theme\n", encoding="utf-8")
    items = tuple(
        PromptItem(f"Item {k}", f"fake/img_{k}.png", f"prompt {k}", k)
        for k in range(n)
    )
    return Sheet("Fake Theme", source, items, (), ())


def test_banner_with_continue_choice_keeps_the_run_alive(tmp_path):
    driver = BannerDriver(SITES["gemini"])
    asked: list = []

    def on_degrade(reset_s):
        asked.append(reset_s)
        return "continue"

    done = run_sheet(
        make_sheet(tmp_path), driver, tmp_path, "gemini", FAST,
        log=lambda *_a: None, report=False, on_degrade=on_degrade,
    )

    assert done == 2  # both items generated on the weaker model
    assert len(asked) == 1  # asked ONCE per run, not per image
    assert asked[0] is not None and asked[0] > 0  # reset time parsed


def test_banner_with_wait_choice_stops_after_the_saved_image(tmp_path):
    driver = BannerDriver(SITES["gemini"])

    with pytest.raises(TerminalState) as exc:
        run_sheet(
            make_sheet(tmp_path), driver, tmp_path, "gemini", FAST,
            log=lambda *_a: None, report=False,
            on_degrade=lambda _r: "wait",
        )

    assert exc.value.retry_after_s is not None
    # the image that already ARRIVED was saved first — never wasted
    # (a bare non-assets drop path lands in the legacy per-site layout)
    assert (tmp_path / "fake" / "img_0_gem.png").exists()
    assert not (tmp_path / "fake" / "img_1_gem.png").exists()


def test_no_banner_never_asks(tmp_path):
    driver = FakeDriver(SITES["gemini"])  # has no degrade_banner_text
    asked: list = []

    done = run_sheet(
        make_sheet(tmp_path), driver, tmp_path, "gemini", FAST,
        log=lambda *_a: None, report=False,
        on_degrade=lambda r: asked.append(r) or "continue",
    )

    assert done == 2
    assert asked == []
