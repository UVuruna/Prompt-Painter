"""Offline tests for the run loop — output paths/suffix, and the basic
save/report/resume flow.

Split from the former ``test_runner.py`` god-file (root Rule #20,
second round — split by concern: this module covers ``dest_for``/
``versioned_dest_for``/``prompt_suffix`` (the output-path contract
every item save goes through) and the plain save/report/resume path
(the assets-mirroring layout, the report txt, safer-retry, the
copyright reframing). See test_runner_images.py (input-image items +
the continue nudge), test_runner_recovery_ladder.py (the
``ImageGenFailed`` recovery ladder) and test_runner_queue_and_control.py
(refusals/resume/redo semantics, stop/pause/terminal states) for the
rest of the former suite.
"""

from dataclasses import replace
from pathlib import Path

import pytest

from painter import runner as runner_module
from painter.config import (
    COPYRIGHT_PREAMBLE,
    REFUSAL_COPYRIGHT,
    REFUSAL_SAFETY,
    SAFER_PREAMBLE,
    SITES,
    STYLES,
    TIMING,
    dest_for,
    prompt_suffix,
    versioned_dest_for,
)
from painter.driver import ItemRefused
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
    """Zero out the image-failure ladder's real-clock waits (1-3 min and
    22-36 min in config) so the recovery tests run instantly. Two
    escalation rounds are kept so their refresh/new-session path is
    exercised; a test needing a different shape re-patches these."""
    monkeypatch.setattr(
        runner_module, "IMAGE_FAILED_RETRY_DELAY_RANGE_S", (0.0, 0.0)
    )
    monkeypatch.setattr(
        runner_module,
        "IMAGE_FAILED_ESCALATION_DELAYS_S",
        ((0.0, 0.0), (0.0, 0.0)),
    )


class FakeDriver:
    """Duck-typed SiteDriver: records prompts, returns PNG bytes.

    ``extract_image`` returns UNIQUE bytes per call (a counter byte
    appended after the valid 1x1 PNG — still sniffs as PNG, the header
    parse at bytes[16:24] is unaffected) so a normal multi-item run
    never trips the F1 duplicate-save guard, which compares SHA1
    digests of consecutive saves. A test that deliberately wants two
    identical saves (to exercise the guard itself) overrides
    ``extract_image`` and returns a literal constant instead."""

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
        # records the attach AND the prompt (so prompt-based test logic
        # keeps working whether an item attached an image or not)
        self.attached.append((image_path, prompt))
        self.submitted.append(prompt)

    def await_done(self, log=print):
        pass

    def extract_image(self):
        self._extract_n += 1
        return PNG_1PX + bytes([self._extract_n % 256])

    # image-failure recovery ladder (owner 2026-07-23) — the base fake
    # has NO native retry button and treats refresh/new-session as no-ops
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


def test_dest_for_mirrors_the_assets_tree():
    # full assets paths: the site lands as the terminal filename
    # suffix (DOMY RESTRUCTURE 2026-07-22) — out/ mirrors assets/
    # byte-for-byte, ready to copy straight in
    assert (
        dest_for("assets/weeks/inner_wheel/mood/Glory.png", "gemini")
        == "weeks/inner_wheel/mood/Glory_gem.png"
    )
    assert (
        dest_for("assets/weeks/faith/bible/primary/dual/x.png", "chatgpt")
        == "weeks/faith/bible/primary/dual/x_gpt.png"
    )
    # legacy relative drops keep the old <site>/<drop> layout
    assert dest_for("fake/img_0.png", "gemini") == "gemini/fake/img_0.png"


def test_dest_for_api_image_suffixes_the_same_way_a_real_site_does():
    """"api_image" is just another site_key to dest_for (it never
    validates against SITES) — the _api filename suffix (owner
    2026-07-22) slots in exactly like _gem/_gpt, so a finished
    API-generated collection copies into the SAME assets/ tree as a
    website-generated one."""
    assert (
        dest_for("assets/emblem/mood/Glory.png", "api_image")
        == "emblem/mood/Glory_api.png"
    )
    assert (
        dest_for("fake/img_0.png", "api_image") == "api_image/fake/img_0.png"
    )


def test_versioned_dest_for_counts_from_the_last_existing(tmp_path):
    """The ticked-redo dest (owner 2026-07-27): the next ``_vN`` after
    the LAST version on disk — canonical alone -> _v2; last _v4 -> _v5
    (gaps never matter); the owner's irregular ``_v`` reads as v1."""
    drop = "assets/emblem/mood/Glory.png"
    folder = tmp_path / "emblem" / "mood"
    folder.mkdir(parents=True)
    (folder / "Glory_gem.png").write_bytes(b"x")

    # only the canonical file -> the first redo is _v2
    assert (
        versioned_dest_for(drop, "gemini", tmp_path)
        == "emblem/mood/Glory_v2_gem.png"
    )
    # last existing version wins, gaps ignored: v2 + v4 -> v5
    (folder / "Glory_v2_gem.png").write_bytes(b"x")
    (folder / "Glory_v4_gem.png").write_bytes(b"x")
    assert (
        versioned_dest_for(drop, "gemini", tmp_path)
        == "emblem/mood/Glory_v5_gem.png"
    )
    # the irregular bare "_v" form reads as version 1 — never a crash,
    # never lifting the max above a real _vN
    (folder / "Glory_v_gem.png").write_bytes(b"x")
    assert (
        versioned_dest_for(drop, "gemini", tmp_path)
        == "emblem/mood/Glory_v5_gem.png"
    )
    # another figure's versions in the same folder never leak in
    (folder / "Glory_Shield_v9_gem.png").write_bytes(b"x")
    assert (
        versioned_dest_for(drop, "gemini", tmp_path)
        == "emblem/mood/Glory_v5_gem.png"
    )
    # per-site independence: the same drop under chatgpt has no
    # versions yet -> _v2
    assert (
        versioned_dest_for(drop, "chatgpt", tmp_path)
        == "emblem/mood/Glory_v2_gpt.png"
    )


def test_prompt_suffix_rules():
    gemini_white = prompt_suffix("gemini", "white")
    # Gemini's remaining laws, forced into every prompt
    assert "PURE WHITE" in gemini_white
    assert "NO reflections" in gemini_white
    # the aspect inference is GONE (owner 2026-07-22) — the sheet
    # prompt states its own aspect ratio, the tool never guesses
    assert "ASPECT RATIO" not in gemini_white

    chatgpt_default = prompt_suffix("chatgpt", "transparent")
    assert "TRANSPARENT" in chatgpt_default
    # ChatGPT's anti-grain law (the Voljin_gpt case, owner 2026-07-27):
    # forced into EVERY ChatGPT prompt, like Gemini's reflections law
    assert "NO film grain" in chatgpt_default
    assert "SOFT and CONTAINED" in chatgpt_default
    assert prompt_suffix("gemini", "none") != ""  # Gemini keeps its laws
    assert "NO film grain" in prompt_suffix("chatgpt", "none")
    # api_image has no site law: no background rule + no style = bare
    assert prompt_suffix("api_image", "none") == ""


def test_style_clause_appended_at_the_end():
    """The chosen style clause is appended at the very END of the suffix,
    AFTER the background rule and the Gemini laws; None appends nothing."""
    base = prompt_suffix("gemini", "white")  # no style
    styled = prompt_suffix("gemini", "white", style="Oil painting")
    # everything the un-styled suffix had, then the style clause appended
    assert styled.startswith(base)
    assert styled.endswith(STYLES["Oil painting"])
    assert "classical oil painting" in styled
    # the style sits AFTER the background rule and the reflections law
    assert styled.index("STYLE:") > styled.index("PURE WHITE")
    assert styled.index("STYLE:") > styled.index("NO reflections")


def test_style_none_appends_nothing():
    base = prompt_suffix("chatgpt", "transparent")
    assert prompt_suffix("chatgpt", "transparent", style="None") == base
    assert prompt_suffix("chatgpt", "transparent", style=None) == base
    assert "STYLE:" not in base


def test_suffix_is_constant_per_site_background_style():
    """The suffix NEVER depends on the prompt text (owner 2026-07-22 —
    the old TALL/lancet inference misfired on 'a tall lotus-tipped
    sceptre' in a ROUND-medallion prompt; the sheet author now states
    the aspect ratio explicitly in the prompt itself)."""
    import inspect

    from painter.config.ai import prompt_suffix as ps

    assert "prompt_text" not in inspect.signature(ps).parameters
    # style with an otherwise-empty suffix still arrives, on its own
    # (api_image — the only site with no law of its own)
    styled_only = prompt_suffix("api_image", "none", style="Oil painting")
    assert styled_only.strip() == STYLES["Oil painting"]


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
    assert (out / "gemini" / "fake" / "img_0.png").read_bytes().startswith(
        PNG_1PX
    )
    # NO progress sidecar any more — "done" is the saved file itself;
    # only the report lives under _state/ (asserted below)
    assert not state(out, "gemini", "fake_prompts.progress.json").exists()
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

    # resume by FILE EXISTENCE: the saved files are on disk, so a
    # second unattended run (only=None) drives nothing
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
    # assets/emblem/mood/Glory.png -> out/emblem/mood/Glory_gpt.png
    # (the site is the terminal filename suffix, RESTRUCTURE 2026-07-22)
    assert (out / "emblem" / "mood" / "Glory_gpt.png").exists()
    # no progress sidecar — resume is by the saved file's existence
    assert not state(out, "chatgpt", "mood_prompts.progress.json").exists()


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
                raise ItemRefused("refused: unsafe", category=REFUSAL_SAFETY)
            if "prompt 1" in last:
                raise ItemRefused("refused: unsafe", category=REFUSAL_SAFETY)  # never recovers
            return super().extract_image()

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


def test_copyright_refusal_uses_the_copyright_preamble(tmp_path):
    """A copyright-category refusal is safer-retried with the HOMAGE
    preamble (COPYRIGHT_PREAMBLE), never the safety allegory one — the
    runner picks the reframing by the refusal's category."""
    class CopyrightPicky(FakeDriver):
        def extract_image(self):
            last = self.submitted[-1]
            if "prompt 0" in last and COPYRIGHT_PREAMBLE not in last:
                raise ItemRefused(
                    "refused: third-party content",
                    category=REFUSAL_COPYRIGHT,
                )
            return super().extract_image()

    sheet = make_sheet(tmp_path, n=1)
    out = tmp_path / "out"
    driver = CopyrightPicky(SITES["chatgpt"])
    generated = run_sheet(
        sheet, driver, out, "chatgpt", FAST, safer_retry=True,
    )
    assert generated == 1
    # the retry carried the copyright reframing, NOT the safety one
    assert driver.submitted[1].startswith(COPYRIGHT_PREAMBLE)
    assert SAFER_PREAMBLE not in driver.submitted[1]


def test_no_safer_retry_by_default(tmp_path):
    class RefuseFirst(FakeDriver):
        def extract_image(self):
            if "prompt 0" in self.submitted[-1]:
                raise ItemRefused("refused: unsafe", category=REFUSAL_SAFETY)
            return super().extract_image()

    sheet = make_sheet(tmp_path, n=2)
    out = tmp_path / "out"
    driver = RefuseFirst(SITES["gemini"])
    generated = run_sheet(sheet, driver, out, "gemini", FAST)
    assert generated == 1
    # no retry: item 0 submitted once, item 1 once
    assert len(driver.submitted) == 2
