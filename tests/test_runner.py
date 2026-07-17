"""Offline tests for the run loop — a fake driver, a temp out folder.

Covers what needs no browser: the per-site background suffix, the
out/<drop-path> layout, resume via the progress sidecar, the stop
flag, and the loud-but-not-fatal background-fix hook.
"""

from dataclasses import replace
from pathlib import Path

from painter.config import SITES, TIMING
from painter.runner import run_sheet
from painter.sheet_parser import PromptItem, Sheet, SkippedItem

FAST = replace(TIMING, pause_between_prompts_s=0.0)

# a real 1x1 PNG so sniff_format sees PNG bytes
PNG_1PX = bytes.fromhex(
    "89504e470d0a1a0a0000000d49484452000000010000000108060000001f15c489"
    "0000000d4944415478da63fcffff3f030005fe02fea72d994800000000"
    "49454e44ae426082"
)


class FakeDriver:
    """Duck-typed SiteDriver: records prompts, returns PNG bytes."""

    def __init__(self, site):
        self.site = site
        self.submitted: list[str] = []

    def submit_prompt(self, prompt):
        self.submitted.append(prompt)

    def await_done(self, log=print):
        pass

    def extract_image(self):
        return PNG_1PX


def make_sheet(tmp_path: Path, n: int = 2) -> Sheet:
    source = tmp_path / "fake_prompts.md"
    source.write_text("# Fake Theme\n", encoding="utf-8")
    items = tuple(
        PromptItem(f"Item {k}", f"fake/img_{k}.png", f"prompt {k}", k)
        for k in range(n)
    )
    skipped = (SkippedItem("Old Seat", "REUSE, no new prompt.", 99),)
    return Sheet("Fake Theme", source, items, skipped, ())


def test_suffix_layout_progress_and_resume(tmp_path):
    sheet = make_sheet(tmp_path)
    out = tmp_path / "out" / "gemini"
    driver = FakeDriver(SITES["gemini"])
    logs: list[str] = []

    generated = run_sheet(sheet, driver, out, FAST, log=logs.append)
    assert generated == 2
    # per-site background suffix appended to every submitted prompt
    assert driver.submitted[0] == "prompt 0" + SITES["gemini"].prompt_suffix
    # the drop path IS the out path
    assert (out / "fake" / "img_0.png").read_bytes() == PNG_1PX
    assert (out / "fake_prompts.progress.json").exists()
    # skipped entries are logged, never driven
    assert any("Old Seat" in line for line in logs)

    # resume: a second run drives nothing
    driver2 = FakeDriver(SITES["gemini"])
    assert run_sheet(sheet, driver2, out, FAST) == 0
    assert driver2.submitted == []


def test_stop_flag_stops_between_items(tmp_path):
    sheet = make_sheet(tmp_path, n=3)
    out = tmp_path / "out" / "chatgpt"
    driver = FakeDriver(SITES["chatgpt"])
    calls = {"n": 0}

    def stop_after_first():
        calls["n"] += 1
        return calls["n"] > 1  # first check passes, second stops

    generated = run_sheet(
        sheet, driver, out, FAST, should_stop=stop_after_first
    )
    assert generated == 1
    assert len(driver.submitted) == 1


def test_bgfix_hook_runs_and_failure_is_loud_not_fatal(tmp_path):
    sheet = make_sheet(tmp_path)
    out = tmp_path / "out" / "gemini"
    driver = FakeDriver(SITES["gemini"])
    logs: list[str] = []
    fixed: list[Path] = []

    def post_save(path: Path) -> str:
        fixed.append(path)
        if len(fixed) == 2:
            raise RuntimeError("boom on the second image")
        return "white"

    generated = run_sheet(
        sheet, driver, out, FAST, log=logs.append, post_save=post_save
    )
    assert generated == 2  # the failure never kills the run
    assert len(fixed) == 2
    assert any("bgfix: white" in line for line in logs)
    assert any("BGFIX FAILED" in line for line in logs)
    assert any("failed on 1 image(s)" in line for line in logs)
