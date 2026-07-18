"""Offline tests for the run loop — a fake driver, a temp out folder.

Covers what needs no browser: the per-site rule suffix, the
assets-mirroring output layout, the report txt, resume via the
progress sidecar (under _state/), the stop flag, and the
loud-but-not-fatal background-fix hook.
"""

import json
from dataclasses import replace
from pathlib import Path

import pytest

from painter.config import (
    SAFER_PREAMBLE,
    SITES,
    TIMING,
    dest_for,
    prompt_suffix,
)
from painter.driver import ItemRefused, TerminalState
from painter.runner import run_sheet
from painter.sheet_parser import PromptItem, Sheet, SkippedItem

FAST = replace(TIMING, pause_min_s=0.0, pause_max_s=0.0)

# a real 1x1 PNG so sniff_format and the report see PNG bytes
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


def state(out_base: Path, site: str, name: str) -> Path:
    return out_base / "_state" / site / name


def test_dest_for_mirrors_the_assets_tree():
    # full assets paths: the site slots in after the category
    assert (
        dest_for("assets/emblem/mood/Glory.png", "gemini")
        == "emblem/gemini/mood/Glory.png"
    )
    assert (
        dest_for("assets/weekday/bible/primary/dual/x.png", "chatgpt")
        == "weekday/chatgpt/bible/primary/dual/x.png"
    )
    # legacy relative drops keep the old <site>/<drop> layout
    assert dest_for("fake/img_0.png", "gemini") == "gemini/fake/img_0.png"


def test_prompt_suffix_rules():
    gemini_white = prompt_suffix("gemini", "white")
    # the owner's three laws for Gemini, forced into every prompt
    assert "PURE WHITE" in gemini_white
    assert "1:1" in gemini_white
    assert "NO reflections" in gemini_white

    chatgpt_default = prompt_suffix("chatgpt", "transparent")
    assert "TRANSPARENT" in chatgpt_default
    assert prompt_suffix("gemini", "none") != ""  # Gemini keeps its laws


def test_gemini_aspect_depends_on_the_prompt():
    lancet = prompt_suffix(
        "gemini",
        "white",
        "TALL pointed-arch lancet stained-glass window, night-window"
        " register ...",
    )
    assert "PORTRAIT" in lancet
    assert "1:1" not in lancet

    rondel = prompt_suffix(
        "gemini", "white", "SMALL round stained-glass rondel ..."
    )
    assert "1:1" in rondel
    assert "PORTRAIT" not in rondel


def test_suffix_layout_report_and_resume(tmp_path):
    sheet = make_sheet(tmp_path)
    out = tmp_path / "out"
    driver = FakeDriver(SITES["gemini"])
    logs: list[str] = []
    suffix = prompt_suffix("gemini", "white")

    generated = run_sheet(
        sheet, driver, out, "gemini", FAST,
        log=logs.append, prompt_suffix=suffix,
    )
    assert generated == 2
    assert driver.submitted[0] == "prompt 0" + suffix
    # legacy drops keep the <site>/<drop> layout
    assert (out / "gemini" / "fake" / "img_0.png").read_bytes() == PNG_1PX
    # sidecars live under _state/, out of the copy-ready tree
    assert state(out, "gemini", "fake_prompts.progress.json").exists()
    # skipped entries are logged, never driven
    assert any("Old Seat" in line for line in logs)

    # the report: header, one line per image with resolution, summary
    report = state(out, "gemini", "fake_prompts_report.txt").read_text(
        encoding="utf-8"
    )
    assert "Fake Theme  [Gemini]" in report
    assert report.count("fake/img_") == 2
    assert "1x1" in report  # the PNG's parsed resolution
    assert "average generation" in report
    assert "average our time" in report  # the second timing (incl. pause)
    assert " B" in report or "KB" in report  # a size column per image
    assert "Run finished" in report

    # resume: a second run drives nothing
    driver2 = FakeDriver(SITES["gemini"])
    assert run_sheet(sheet, driver2, out, "gemini", FAST) == 0
    assert driver2.submitted == []


def test_assets_paths_save_into_the_mirrored_tree(tmp_path):
    source = tmp_path / "mood_prompts.md"
    source.write_text("# Mood\n", encoding="utf-8")
    sheet = Sheet(
        "Mood", source,
        (PromptItem("Glory", "assets/emblem/mood/Glory.png", "p", 1),),
        (), (),
    )
    out = tmp_path / "out"
    run_sheet(sheet, FakeDriver(SITES["chatgpt"]), out, "chatgpt", FAST)
    # assets/emblem/mood/Glory.png -> out/emblem/chatgpt/mood/Glory.png
    assert (out / "emblem" / "chatgpt" / "mood" / "Glory.png").exists()
    # progress keys stay the SHEET's drop path (stable across layouts)
    progress = json.loads(
        state(out, "chatgpt", "mood_prompts.progress.json").read_text(
            encoding="utf-8"
        )
    )["done"]
    assert list(progress) == ["assets/emblem/mood/Glory.png"]


def test_events_carry_both_timings_and_size(tmp_path):
    sheet = make_sheet(tmp_path, n=1)
    out = tmp_path / "out"
    events: list[dict] = []
    run_sheet(
        sheet, FakeDriver(SITES["gemini"]), out, "gemini", FAST,
        on_event=events.append,
    )
    kinds = [e["type"] for e in events]
    # item_progress counts it live; item_done carries our-time + size
    assert kinds == [
        "sheet_start", "item_start", "item_progress", "item_done",
        "sheet_done",
    ]
    prog = next(e for e in events if e["type"] == "item_progress")
    assert prog["gen_s"] >= 0
    done = next(e for e in events if e["type"] == "item_done")
    assert done["gen_s"] >= 0
    assert done["over_s"] >= 0
    assert done["size"] > 0
    assert done["orig_res"] == "1x1"
    assert done["drop_path"] == "fake/img_0.png"


def test_safer_retry_recovers_then_gives_up(tmp_path):
    # a driver that refuses unless the SAFER_PREAMBLE is present
    class PickyDriver(FakeDriver):
        def extract_image(self):
            last = self.submitted[-1]
            if "prompt 0" in last and SAFER_PREAMBLE not in last:
                raise ItemRefused("refused: unsafe")
            if "prompt 1" in last:
                raise ItemRefused("refused: unsafe")  # never recovers
            return PNG_1PX

    sheet = make_sheet(tmp_path, n=2)
    out = tmp_path / "out"
    logs: list[str] = []
    driver = PickyDriver(SITES["gemini"])
    generated = run_sheet(
        sheet, driver, out, "gemini", FAST,
        log=logs.append, safer_retry=True,
    )
    # item 0 recovered on the safer retry; item 1 refused twice -> skipped
    assert generated == 1
    assert (out / "gemini" / "fake" / "img_0.png").exists()
    assert not (out / "gemini" / "fake" / "img_1.png").exists()
    assert any("safer retry SUCCEEDED" in line for line in logs)
    # item 0: original + safer; item 1: original + safer = 4 submits
    assert len(driver.submitted) == 4


def test_no_safer_retry_by_default(tmp_path):
    class RefuseFirst(FakeDriver):
        def extract_image(self):
            if "prompt 0" in self.submitted[-1]:
                raise ItemRefused("refused: unsafe")
            return PNG_1PX

    sheet = make_sheet(tmp_path, n=2)
    out = tmp_path / "out"
    driver = RefuseFirst(SITES["gemini"])
    generated = run_sheet(sheet, driver, out, "gemini", FAST)
    assert generated == 1
    # no retry: item 0 submitted once, item 1 once
    assert len(driver.submitted) == 2


def test_no_report_flag(tmp_path):
    sheet = make_sheet(tmp_path)
    out = tmp_path / "out"
    run_sheet(
        sheet, FakeDriver(SITES["chatgpt"]), out, "chatgpt", FAST,
        report=False,
    )
    assert not state(out, "chatgpt", "fake_prompts_report.txt").exists()


def test_refusal_skips_the_item_and_the_run_continues(tmp_path):
    sheet = make_sheet(tmp_path, n=3)
    out = tmp_path / "out"

    class RefusingDriver(FakeDriver):
        def extract_image(self):
            if "prompt 1" in self.submitted[-1]:
                raise ItemRefused("Gemini: prompt refused ('unsafe')")
            return PNG_1PX

    driver = RefusingDriver(SITES["gemini"])
    logs: list[str] = []
    generated = run_sheet(sheet, driver, out, "gemini", FAST, log=logs.append)

    assert generated == 2  # items 0 and 2 made it
    assert len(driver.submitted) == 3  # the refusal did not stop the run
    assert not (out / "gemini" / "fake" / "img_1.png").exists()
    progress = json.loads(
        state(out, "gemini", "fake_prompts.progress.json").read_text(
            encoding="utf-8"
        )
    )["done"]
    assert "fake/img_1.png" not in progress  # a rerun retries it
    assert len(progress) == 2
    report = state(out, "gemini", "fake_prompts_report.txt").read_text(
        encoding="utf-8"
    )
    assert "REFUSED" in report
    assert "Refused: 1" in report

    # the rerun drives ONLY the refused item
    driver2 = FakeDriver(SITES["gemini"])
    assert run_sheet(sheet, driver2, out, "gemini", FAST) == 1
    assert "prompt 1" in driver2.submitted[0]


def test_advised_items_sit_out_unless_ticked(tmp_path):
    source = tmp_path / "adv_prompts.md"
    source.write_text("# Advice Theme\n", encoding="utf-8")
    sheet = Sheet(
        "Advice Theme",
        source,
        (
            PromptItem("Normal", "adv/normal.png", "p0", 1),
            PromptItem(
                "Optional", "adv/optional.png", "p1", 2,
                advice="Not yet approved — do not generate.",
            ),
        ),
        (),
        (),
    )
    out = tmp_path / "out"

    # default run: the advised item sits out, loudly
    driver = FakeDriver(SITES["gemini"])
    logs: list[str] = []
    assert run_sheet(sheet, driver, out, "gemini", FAST, log=logs.append) == 1
    assert not (out / "gemini" / "adv" / "optional.png").exists()
    assert any("NOT RUN (sheet advice)" in line for line in logs)
    report = state(out, "gemini", "adv_prompts_report.txt").read_text(
        encoding="utf-8"
    )
    assert "advice, not ticked" in report

    # explicitly ticked: it generates like any other item
    driver2 = FakeDriver(SITES["gemini"])
    assert run_sheet(
        sheet, driver2, out, "gemini", FAST, only={"adv/optional.png"}
    ) == 1
    assert (out / "gemini" / "adv" / "optional.png").exists()


def test_only_filter_drives_just_the_ticked_items(tmp_path):
    sheet = make_sheet(tmp_path, n=3)
    out = tmp_path / "out"
    driver = FakeDriver(SITES["chatgpt"])
    generated = run_sheet(
        sheet, driver, out, "chatgpt", FAST, only={"fake/img_2.png"}
    )
    assert generated == 1
    assert (out / "chatgpt" / "fake" / "img_2.png").exists()
    assert not (out / "chatgpt" / "fake" / "img_0.png").exists()


def test_stop_flag_stops_between_items(tmp_path):
    sheet = make_sheet(tmp_path, n=3)
    out = tmp_path / "out"
    driver = FakeDriver(SITES["chatgpt"])
    calls = {"n": 0}

    def stop_after_first():
        calls["n"] += 1
        return calls["n"] > 1  # first check passes, second stops

    generated = run_sheet(
        sheet, driver, out, "chatgpt", FAST, should_stop=stop_after_first
    )
    assert generated == 1
    assert len(driver.submitted) == 1
    report = state(out, "chatgpt", "fake_prompts_report.txt").read_text(
        encoding="utf-8"
    )
    assert "stopped on request" in report


def test_post_save_hook_runs_and_failure_is_loud_not_fatal(tmp_path):
    sheet = make_sheet(tmp_path)
    out = tmp_path / "out"
    driver = FakeDriver(SITES["gemini"])
    logs: list[str] = []
    fixed: list[Path] = []

    def post_save(path: Path) -> str:
        # the hook composes its own steps and describes them all
        fixed.append(path)
        if len(fixed) == 2:
            raise RuntimeError("boom on the second image")
        return "REMOVE BG: done, CROP: done"

    generated = run_sheet(
        sheet, driver, out, "gemini", FAST,
        log=logs.append, post_save=post_save,
    )
    assert generated == 2  # the failure never kills the run
    assert len(fixed) == 2
    assert any("REMOVE BG: done, CROP: done" in line for line in logs)
    assert any("POSTPROCESS FAILED" in line for line in logs)
    assert any("failed on 1 image(s)" in line for line in logs)
    # the report carries the hook's full description per image
    report = state(out, "gemini", "fake_prompts_report.txt").read_text(
        encoding="utf-8"
    )
    assert "REMOVE BG: done, CROP: done" in report
    assert "POSTPROCESS: FAILED" in report


def test_terminal_state_propagates_retry_after(tmp_path):
    # a quota answer mid-run: the runner logs the parsed reset time,
    # writes it into the report's stop reason, and re-raises the
    # SAME exception so callers (GUI/CLI) can read retry_after_s
    sheet = make_sheet(tmp_path, n=2)
    out = tmp_path / "out"

    class QuotaDriver(FakeDriver):
        def extract_image(self):
            raise TerminalState(
                "ChatGPT: quota/rate-limit response (matched 'plan"
                " limit'): ... limit resets in 27 minutes.",
                retry_after_s=27 * 60.0,
            )

    logs: list[str] = []
    with pytest.raises(TerminalState) as excinfo:
        run_sheet(
            sheet, QuotaDriver(SITES["chatgpt"]), out, "chatgpt", FAST,
            log=logs.append,
        )
    assert excinfo.value.retry_after_s == 27 * 60.0
    assert any("quota — reset in ~27 min" in line for line in logs)
    report = state(out, "chatgpt", "fake_prompts_report.txt").read_text(
        encoding="utf-8"
    )
    assert "quota / rate limit — stopped (reset in ~27m 00s)" in report
