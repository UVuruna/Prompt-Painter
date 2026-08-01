"""Offline tests for the run loop — input-image items (``← ref``,
owner 2026-07-23) and the ChatGPT continue-nudge stall recovery.

Split from the former ``test_runner.py`` god-file (root Rule #20,
second round — split by concern). See test_runner_paths_and_save.py
for the shared ``FakeDriver``/``make_sheet``/``state`` rationale
(duplicated here — each split module is self-contained by design),
test_runner_recovery_ladder.py for the ``ImageGenFailed`` ladder, and
test_runner_queue_and_control.py for refusals/resume/redo and run
control.
"""

from dataclasses import replace
from pathlib import Path

import pytest

from painter import runner as runner_module
from painter.config import CONTINUE_NUDGE, SITES, TIMING
from painter.driver import ImageGenFailed, NoImage
from painter.runner import run_sheet
from painter.sheet_parser import PromptItem, Sheet, SkippedItem

FAST = replace(TIMING, pause_min_s=0.0, pause_max_s=0.0)

# a real 1x1 PNG so sniff_format and the report see PNG bytes
PNG_1PX = bytes.fromhex(
    "89504e470d0a1a0a0000000d49484452000000010000000108060000001f15c489"
    "0000000d4944415478da63fcffff3f030005fe02fea72d994800000000"
    "49454e44ae426082"
)


@pytest.fixture(autouse=True)
def _fast_recovery(monkeypatch):
    """Zero out the image-failure ladder's real-clock waits — see
    test_runner_paths_and_save.py's own copy for the full rationale."""
    monkeypatch.setattr(
        runner_module, "IMAGE_FAILED_RETRY_DELAY_RANGE_S", (0.0, 0.0)
    )
    monkeypatch.setattr(
        runner_module,
        "IMAGE_FAILED_ESCALATION_DELAYS_S",
        ((0.0, 0.0), (0.0, 0.0)),
    )


class FakeDriver:
    """Duck-typed SiteDriver — see test_runner_paths_and_save.py's own
    copy for the full rationale."""

    def __init__(self, site):
        self.site = site
        self.submitted: list[str] = []
        self.attached: list[tuple[str, str]] = []  # (image_path, prompt)
        self.retry_clicks = 0
        self.refreshes = 0
        self.new_chats = 0
        self._extract_n = 0

    def submit_prompt(self, prompt, log=print):
        self.submitted.append(prompt)

    def submit_with_image(self, image_path, prompt, log=print):
        self.attached.append((image_path, prompt))
        self.submitted.append(prompt)

    def await_done(self, log=print):
        pass

    def extract_image(self):
        self._extract_n += 1
        return PNG_1PX + bytes([self._extract_n % 256])

    def click_error_retry(self, log=print):
        return False

    def refresh(self, log=print):
        self.refreshes += 1

    def new_chat(self, log=print):
        self.new_chats += 1


def make_sheet(tmp_path: Path, n: int = 2) -> Sheet:
    source = tmp_path / "fake_prompts.md"
    source.write_text("# Fake Theme\n", encoding="utf-8")
    items = tuple(
        PromptItem(f"Item {k}", f"fake/img_{k}.png", f"prompt {k}", k)
        for k in range(n)
    )
    skipped = (SkippedItem("Old Seat", "REUSE, no new prompt.", 99),)
    return Sheet("Fake Theme", source, items, skipped, ())


def state(out_base: Path, site: str, name: str) -> Path:
    return out_base / "_state" / site / name


# --- input-image items (← `ref`), owner 2026-07-23 -------------------

def _sheet_with_input(
    tmp_path: Path, ref: str = "refs/hero.png", make_ref: bool = True
) -> Sheet:
    source = tmp_path / "sheet.md"
    source.write_text("# T\n", encoding="utf-8")
    if make_ref:
        ref_path = tmp_path / ref
        ref_path.parent.mkdir(parents=True, exist_ok=True)
        ref_path.write_bytes(PNG_1PX)
    item = PromptItem("Hero", "fake/hero.png", "prompt 0", 1, None, ref)
    return Sheet("T", source, (item,), (), ())


def test_input_image_item_attaches_via_submit_with_image(tmp_path):
    sheet = _sheet_with_input(tmp_path)
    out = tmp_path / "out"
    driver = FakeDriver(SITES["chatgpt"])

    generated = run_sheet(sheet, driver, out, "chatgpt", FAST)

    assert generated == 1
    assert (out / "chatgpt" / "fake" / "hero.png").exists()
    # attached (not plain-submitted), resolved RELATIVE TO THE SHEET FOLDER
    assert len(driver.attached) == 1
    attached_path, prompt = driver.attached[0]
    assert attached_path == str(tmp_path / "refs" / "hero.png")
    assert "prompt 0" in prompt


def test_input_image_missing_is_skipped_loudly(tmp_path):
    source = tmp_path / "sheet.md"
    source.write_text("# T\n", encoding="utf-8")
    items = (
        PromptItem("Hero", "fake/hero.png", "prompt 0", 1, None,
                   "refs/missing.png"),
        PromptItem("Plain", "fake/plain.png", "prompt 1", 2),
    )
    sheet = Sheet("T", source, items, (), ())
    out = tmp_path / "out"
    logs: list[str] = []
    driver = FakeDriver(SITES["chatgpt"])

    generated = run_sheet(
        sheet, driver, out, "chatgpt", FAST, log=logs.append,
    )

    # the missing-input item is skipped; the plain one still runs
    assert generated == 1
    assert not (out / "chatgpt" / "fake" / "hero.png").exists()
    assert (out / "chatgpt" / "fake" / "plain.png").exists()
    assert any("INPUT IMAGE MISSING" in line for line in logs)
    # the missing item never reached the driver — nothing attached
    assert driver.attached == []


def test_plain_item_never_attaches_an_image(tmp_path):
    sheet = make_sheet(tmp_path, n=1)
    out = tmp_path / "out"
    driver = FakeDriver(SITES["chatgpt"])

    run_sheet(sheet, driver, out, "chatgpt", FAST)

    assert driver.attached == []
    assert len(driver.submitted) == 1


def test_input_image_reattached_on_escalation_new_session(tmp_path):
    """The image-failed ladder's escalation rung opens a NEW session with
    no history — an input-image item MUST re-attach its reference there
    (the text-only rungs stay in the same chat where the image already
    sits). Else the fresh chat would generate WITHOUT the reference."""
    class FailsUntilReattach(FakeDriver):
        def extract_image(self):
            # succeeds only once the image has been attached a SECOND
            # time — i.e. in the fresh escalation session
            if len(self.attached) >= 2:
                return super().extract_image()
            raise ImageGenFailed(
                "ChatGPT: image generation failed (matched '...'): ..."
            )

    sheet = _sheet_with_input(tmp_path)
    out = tmp_path / "out"
    driver = FailsUntilReattach(SITES["chatgpt"])

    generated = run_sheet(sheet, driver, out, "chatgpt", FAST)

    assert generated == 1
    # attached twice: the first send + the escalation re-attach (never a
    # bare "retry" in the fresh session)
    assert len(driver.attached) == 2
    for path, _prompt in driver.attached:
        assert path == str(tmp_path / "refs" / "hero.png")
    # the escalation refreshed the page and opened a new session first
    assert driver.refreshes >= 1
    assert driver.new_chats >= 1


def test_continue_nudge_recovers_a_stuck_response(tmp_path):
    # ChatGPT stalls on the item (NoImage: done edge fired, no image, no
    # marker); the one-shot continue nudge makes it finish. extract_image
    # stays stuck until CONTINUE_NUDGE is the last thing submitted.
    class StuckThenNudged(FakeDriver):
        def extract_image(self):
            if CONTINUE_NUDGE in self.submitted[-1]:
                return super().extract_image()
            raise NoImage(
                "ChatGPT: nothing happened after the confirmed send —"
                " empty/interrupted answer",
                had_text=False,
            )

    sheet = make_sheet(tmp_path, n=1)
    out = tmp_path / "out"
    logs: list[str] = []
    events: list[dict] = []
    driver = StuckThenNudged(SITES["chatgpt"])
    # continue_nudge defaults ON — not passed here, so this also proves
    # the default is on out of the box
    generated = run_sheet(
        sheet, driver, out, "chatgpt", FAST,
        log=logs.append, on_event=events.append,
    )
    # the stuck item recovered on the nudge and counts as generated
    assert generated == 1
    assert (out / "chatgpt" / "fake" / "img_0.png").exists()
    assert any("continue nudge RECOVERED" in line for line in logs)
    # the original prompt, then the nudge sent VERBATIM into the same chat
    # (CONTINUE_NUDGE, no prompt suffix) — one nudge attempt per item
    assert len(driver.submitted) == 2
    assert driver.submitted[0].startswith("prompt 0")
    assert driver.submitted[-1] == CONTINUE_NUDGE
    assert any(e["type"] == "item_nudge" for e in events)


def test_noimage_with_text_is_skipped_never_nudged(tmp_path):
    """F1 root cause 2 (owner 2026-07-29): a NoImage carrying
    ``had_text=True`` is a LOUD SKIP, NEVER a nudge — nudging after
    unmatched text made Gemini draw an unrelated image once (the
    market-scene incident). The run continues to the next item."""
    class TextOnlyOnFirst(FakeDriver):
        def extract_image(self):
            if "prompt 0" in self.submitted[-1]:
                raise NoImage(
                    "Gemini: the response answered with TEXT but no"
                    " image, and the text matches no known marker",
                    had_text=True,
                )
            return super().extract_image()

    sheet = make_sheet(tmp_path, n=2)
    out = tmp_path / "out"
    driver = TextOnlyOnFirst(SITES["gemini"])
    generated = run_sheet(sheet, driver, out, "gemini", FAST)

    assert generated == 1
    assert CONTINUE_NUDGE not in driver.submitted
    assert not (out / "gemini" / "fake" / "img_0.png").exists()
    assert (out / "gemini" / "fake" / "img_1.png").exists()
    report = state(out, "gemini", "fake_prompts_report.txt").read_text(
        encoding="utf-8"
    )
    assert "REFUSED" in report


def test_continue_nudge_still_stuck_is_skipped_loudly(tmp_path):
    """F1 (owner 2026-07-29): a NoImage that survives even the one-shot
    nudge is now a LOUD SKIP, never a site-stopping raise — the run
    keeps going to the next item (both items here hit the same stuck
    state, so both end up skipped, and run_sheet never raises)."""
    class AlwaysStuck(FakeDriver):
        def extract_image(self):
            raise NoImage("ChatGPT: DOM state unknown (selector rot?)")

    sheet = make_sheet(tmp_path, n=2)
    out = tmp_path / "out"
    driver = AlwaysStuck(SITES["chatgpt"])
    generated = run_sheet(
        sheet, driver, out, "chatgpt", FAST, continue_nudge=True,
    )
    assert generated == 0  # neither item ever produced an image
    # each item: original submit + one nudge attempt
    assert driver.submitted == [
        "prompt 0", CONTINUE_NUDGE, "prompt 1", CONTINUE_NUDGE,
    ]
    assert not (out / "chatgpt" / "fake" / "img_0.png").exists()
    assert not (out / "chatgpt" / "fake" / "img_1.png").exists()
    report = state(out, "chatgpt", "fake_prompts_report.txt").read_text(
        encoding="utf-8"
    )
    assert "no image after nudge" in report
    assert "Refused: 2" in report


def test_no_continue_nudge_skips_the_item_without_nudging(tmp_path):
    """continue_nudge OFF: the first NoImage is a loud skip with NO
    nudge sent at all — and (F1) the run still continues to the next
    item, never stops."""
    class AlwaysStuck(FakeDriver):
        def extract_image(self):
            raise NoImage("ChatGPT: DOM state unknown (selector rot?)")

    sheet = make_sheet(tmp_path, n=2)
    out = tmp_path / "out"
    driver = AlwaysStuck(SITES["chatgpt"])
    generated = run_sheet(
        sheet, driver, out, "chatgpt", FAST, continue_nudge=False,
    )
    assert generated == 0
    assert driver.submitted == ["prompt 0", "prompt 1"]  # no nudge, ever
    assert CONTINUE_NUDGE not in driver.submitted
