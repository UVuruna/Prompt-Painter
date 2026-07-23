"""Offline tests for the run loop — a fake driver, a temp out folder.

Covers what needs no browser: the per-site rule suffix, the
assets-mirroring output layout, the report txt, resume by FILE
EXISTENCE (a saved dest file = done; the folder is ALWAYS the source
of truth — `only` narrows the candidates but never overwrites a file
already on disk), the stop flag, and the loud-but-not-fatal
background-fix hook.
"""

from dataclasses import replace
from pathlib import Path

import pytest

from painter import runner as runner_module
from painter.config import (
    CONTINUE_NUDGE,
    COPYRIGHT_PREAMBLE,
    IMAGE_FAILED_RETRY_MAX,
    IMAGE_RETRY_NUDGE,
    REFUSAL_COPYRIGHT,
    REFUSAL_SAFETY,
    SAFER_PREAMBLE,
    SITES,
    STYLES,
    TIMING,
    dest_for,
    prompt_suffix,
)
from painter.driver import ImageGenFailed, ItemRefused, NoImage, TerminalState
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
    """Duck-typed SiteDriver: records prompts, returns PNG bytes."""

    def __init__(self, site):
        self.site = site
        self.submitted: list[str] = []
        self.attached: list[tuple[str, str]] = []  # (image_path, prompt)
        self.retry_clicks = 0
        self.refreshes = 0
        self.new_chats = 0

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
        return PNG_1PX

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
    assert prompt_suffix("gemini", "none") != ""  # Gemini keeps its laws
    # chatgpt with no background rule and no style has NO suffix at all
    assert prompt_suffix("chatgpt", "none") == ""


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
    styled_only = prompt_suffix("chatgpt", "none", style="Oil painting")
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
    assert (out / "gemini" / "fake" / "img_0.png").read_bytes() == PNG_1PX
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
            return PNG_1PX

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
            return PNG_1PX

    sheet = make_sheet(tmp_path, n=2)
    out = tmp_path / "out"
    driver = RefuseFirst(SITES["gemini"])
    generated = run_sheet(sheet, driver, out, "gemini", FAST)
    assert generated == 1
    # no retry: item 0 submitted once, item 1 once
    assert len(driver.submitted) == 2


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
                return PNG_1PX
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
                return PNG_1PX
            raise NoImage(
                "ChatGPT: the response holds no loaded generated image,"
                " and the response matches no known refusal/quota marker"
                " — DOM state unknown (selector rot?). Response starts: ''"
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
    assert (out / "chatgpt" / "fake" / "img_0.png").read_bytes() == PNG_1PX
    assert any("continue nudge RECOVERED" in line for line in logs)
    # the original prompt, then the nudge sent VERBATIM into the same chat
    # (CONTINUE_NUDGE, no prompt suffix) — one nudge attempt per item
    assert len(driver.submitted) == 2
    assert driver.submitted[0].startswith("prompt 0")
    assert driver.submitted[-1] == CONTINUE_NUDGE
    assert any(e["type"] == "item_nudge" for e in events)


def test_continue_nudge_still_stuck_stops_the_site(tmp_path):
    # the nudge does not recover it either -> NoImage propagates and the
    # whole site stops loudly, exactly as before the nudge existed
    class AlwaysStuck(FakeDriver):
        def extract_image(self):
            raise NoImage("ChatGPT: DOM state unknown (selector rot?)")

    sheet = make_sheet(tmp_path, n=2)
    out = tmp_path / "out"
    driver = AlwaysStuck(SITES["chatgpt"])
    with pytest.raises(NoImage):
        run_sheet(sheet, driver, out, "chatgpt", FAST, continue_nudge=True)
    # ONE item attempted: its original submit + one nudge submit, then stop
    assert len(driver.submitted) == 2
    assert driver.submitted[-1] == CONTINUE_NUDGE
    assert not (out / "chatgpt" / "fake" / "img_0.png").exists()
    # the report records the honest stop reason
    report = state(out, "chatgpt", "fake_prompts_report.txt").read_text(
        encoding="utf-8"
    )
    assert "no image — DOM state unknown" in report


def test_no_continue_nudge_stops_on_the_first_no_image(tmp_path):
    # continue_nudge OFF: the first NoImage stops the site, no nudge sent
    class AlwaysStuck(FakeDriver):
        def extract_image(self):
            raise NoImage("ChatGPT: DOM state unknown (selector rot?)")

    sheet = make_sheet(tmp_path, n=2)
    out = tmp_path / "out"
    driver = AlwaysStuck(SITES["chatgpt"])
    with pytest.raises(NoImage):
        run_sheet(sheet, driver, out, "chatgpt", FAST, continue_nudge=False)
    # only the original submit — no nudge at all
    assert len(driver.submitted) == 1
    assert CONTINUE_NUDGE not in driver.submitted


def test_image_gen_failed_recovers_on_a_later_retry(tmp_path):
    """BUG 3: ChatGPT's own "Image generation failed" answer — the
    driver already caught it (ImageGenFailed) WITHOUT burning the hard
    timeout (see test_driver.py); the runner resends IMAGE_RETRY_NUDGE
    ("retry") into the same chat and recovers once the site finally
    produces the image."""
    class FailsTwiceThenWorks(FakeDriver):
        def extract_image(self):
            retries = [
                s for s in self.submitted if s == IMAGE_RETRY_NUDGE
            ]
            if len(retries) >= 2:  # succeeds on the 2nd "retry" resend
                return PNG_1PX
            raise ImageGenFailed(
                "ChatGPT: image generation failed (matched 'image"
                " generation failed'): ..."
            )

    sheet = make_sheet(tmp_path, n=1)
    out = tmp_path / "out"
    logs: list[str] = []
    events: list[dict] = []
    driver = FailsTwiceThenWorks(SITES["chatgpt"])
    generated = run_sheet(
        sheet, driver, out, "chatgpt", FAST,
        log=logs.append, on_event=events.append,
    )
    assert generated == 1
    assert (out / "chatgpt" / "fake" / "img_0.png").read_bytes() == PNG_1PX
    assert any("retry RECOVERED" in line for line in logs)
    # original submit + 2 "retry" resends
    assert driver.submitted == [
        "prompt 0", IMAGE_RETRY_NUDGE, IMAGE_RETRY_NUDGE,
    ]
    assert any(e["type"] == "item_retry" for e in events)


def test_image_gen_failed_exhausts_ladder_then_stops(tmp_path):
    """Every rung of the recovery ladder fails (button, both text
    retries, both escalation rounds) -> the ladder re-raises and the
    WHOLE site STOPS (owner 2026-07-23, "GASI"). The item is NOT
    silently skipped, and the next item never runs — a restart resumes
    from disk. Between the text retries and the two escalation rounds
    the page is refreshed and a new session opened."""
    class AlwaysFails(FakeDriver):
        def extract_image(self):
            raise ImageGenFailed("ChatGPT: image generation failed: ...")

    sheet = make_sheet(tmp_path, n=2)
    out = tmp_path / "out"
    logs: list[str] = []
    driver = AlwaysFails(SITES["chatgpt"])
    with pytest.raises(ImageGenFailed):
        run_sheet(sheet, driver, out, "chatgpt", FAST, log=logs.append)

    # neither item produced a file; the second item was never reached
    assert not (out / "chatgpt" / "fake" / "img_0.png").exists()
    assert not (out / "chatgpt" / "fake" / "img_1.png").exists()
    assert any("RECOVERY EXHAUSTED" in line for line in logs)
    # item 0: original submit + 2 text retries, then 2 escalation rounds
    # each resend the WHOLE original prompt in a fresh session
    assert driver.submitted[: 1 + IMAGE_FAILED_RETRY_MAX] == [
        "prompt 0"
    ] + [IMAGE_RETRY_NUDGE] * IMAGE_FAILED_RETRY_MAX
    assert driver.refreshes == 2 and driver.new_chats == 2
    report = state(out, "chatgpt", "fake_prompts_report.txt").read_text(
        encoding="utf-8"
    )
    assert "image generation failed" in report

    # a rerun resumes ONLY the unfinished items (file-existence resume)
    driver2 = FakeDriver(SITES["chatgpt"])
    assert run_sheet(sheet, driver2, out, "chatgpt", FAST) == 2


def test_image_gen_failed_recovers_via_the_retry_button(tmp_path):
    """Rung 1 of the ladder: the site's native Retry button clears the
    error in place, no text is re-typed, no escalation needed."""
    class ButtonRecovers(FakeDriver):
        def __init__(self, site):
            super().__init__(site)
            self._clicked = False

        def click_error_retry(self, log=print):
            self._clicked = True
            self.retry_clicks += 1
            return True

        def extract_image(self):
            # fails until the Retry button has been clicked
            if self._clicked:
                return PNG_1PX
            raise ImageGenFailed("ChatGPT: image generation failed: ...")

    sheet = make_sheet(tmp_path, n=1)
    out = tmp_path / "out"
    logs: list[str] = []
    driver = ButtonRecovers(SITES["chatgpt"])
    assert run_sheet(sheet, driver, out, "chatgpt", FAST, log=logs.append) == 1
    assert (out / "chatgpt" / "fake" / "img_0.png").exists()
    assert driver.retry_clicks == 1
    # recovered on the button alone — no "retry" text, no new session
    assert driver.submitted == ["prompt 0"]
    assert driver.new_chats == 0
    assert any("Retry button RECOVERED" in line for line in logs)


def test_image_gen_failed_recovers_in_a_fresh_session(tmp_path):
    """Rungs 1-2 fail but escalation round 1 (refresh -> new session ->
    whole prompt) succeeds — the run continues, no stop."""
    class FreshSessionRecovers(FakeDriver):
        def extract_image(self):
            # succeeds only once a new session has been opened
            if self.new_chats >= 1:
                return PNG_1PX
            raise ImageGenFailed("ChatGPT: image generation failed: ...")

    sheet = make_sheet(tmp_path, n=1)
    out = tmp_path / "out"
    logs: list[str] = []
    driver = FreshSessionRecovers(SITES["chatgpt"])
    assert run_sheet(sheet, driver, out, "chatgpt", FAST, log=logs.append) == 1
    assert (out / "chatgpt" / "fake" / "img_0.png").exists()
    # button skipped, both text retries spent, then ONE escalation round
    assert driver.refreshes == 1 and driver.new_chats == 1
    # the escalation round resends the WHOLE original prompt (run_sheet
    # here uses the default empty suffix, so base == the bare prompt)
    assert driver.submitted[-1] == "prompt 0"
    assert any("RECOVERED (fresh session)" in line for line in logs)


def test_image_gen_failed_stop_during_recovery_aborts(tmp_path, monkeypatch):
    """A Stop request while the ladder is waiting abandons recovery
    immediately (it does not sit out the 1-3 / 22-36 min wait)."""
    class AlwaysFails(FakeDriver):
        def extract_image(self):
            raise ImageGenFailed("ChatGPT: image generation failed: ...")

    # a real (tiny) wait so _sleep actually enters its poll loop and
    # sees the stop flag mid-wait (a 0s wait would never poll)
    monkeypatch.setattr(
        runner_module, "IMAGE_FAILED_RETRY_DELAY_RANGE_S", (0.6, 0.6)
    )
    sheet = make_sheet(tmp_path, n=1)
    out = tmp_path / "out"
    logs: list[str] = []
    driver = AlwaysFails(SITES["chatgpt"])
    # False at the loop's top-of-iteration check (submitted empty), True
    # once prompt 0 has been sent and the ladder starts waiting
    should_stop = lambda: bool(driver.submitted)  # noqa: E731
    with pytest.raises(ImageGenFailed):
        run_sheet(
            sheet, driver, out, "chatgpt", FAST,
            should_stop=should_stop, log=logs.append,
        )
    # stop won on the FIRST wait — no text retry ever sent
    assert driver.submitted == ["prompt 0"]
    assert any("STOPPED on request during recovery" in line for line in logs)


def test_image_failed_retry_off_stops_the_site_immediately(tmp_path):
    """image_failed_retry=False: the FIRST ImageGenFailed propagates
    and stops the site, no "retry" ever sent — same shape as
    continue_nudge=False for NoImage."""
    class AlwaysFails(FakeDriver):
        def extract_image(self):
            raise ImageGenFailed("ChatGPT: image generation failed: ...")

    sheet = make_sheet(tmp_path, n=2)
    out = tmp_path / "out"
    driver = AlwaysFails(SITES["chatgpt"])
    with pytest.raises(ImageGenFailed):
        run_sheet(
            sheet, driver, out, "chatgpt", FAST, image_failed_retry=False,
        )
    # only the original submit — no "retry" resend at all
    assert driver.submitted == ["prompt 0"]
    report = state(out, "chatgpt", "fake_prompts_report.txt").read_text(
        encoding="utf-8"
    )
    assert "image generation failed" in report


def test_image_gen_failed_does_not_regress_a_normal_run(tmp_path):
    """A normal run (no ImageGenFailed ever raised) is byte-behavior
    unchanged: no "retry" resend, no extra events, plain success."""
    sheet = make_sheet(tmp_path, n=2)
    out = tmp_path / "out"
    driver = FakeDriver(SITES["chatgpt"])
    events: list[dict] = []
    generated = run_sheet(
        sheet, driver, out, "chatgpt", FAST, on_event=events.append,
    )
    assert generated == 2
    assert IMAGE_RETRY_NUDGE not in driver.submitted
    assert not any(e["type"] == "item_retry" for e in events)


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
                raise ItemRefused(
                    "Gemini: prompt refused ('unsafe')",
                    category=REFUSAL_SAFETY,
                )
            return PNG_1PX

    driver = RefusingDriver(SITES["gemini"])
    logs: list[str] = []
    generated = run_sheet(sheet, driver, out, "gemini", FAST, log=logs.append)

    assert generated == 2  # items 0 and 2 made it
    assert len(driver.submitted) == 3  # the refusal did not stop the run
    # the refused item left NO file, so a rerun retries it by
    # file-existence; the two generated items ARE on disk
    assert not (out / "gemini" / "fake" / "img_1.png").exists()
    assert (out / "gemini" / "fake" / "img_0.png").exists()
    assert (out / "gemini" / "fake" / "img_2.png").exists()
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


def test_file_existence_resume_skips_saved_and_runs_missing(tmp_path):
    """No `only` (unattended/CLI): an item whose dest FILE already
    exists is skipped and left UNTOUCHED; the missing ones generate —
    resume is by the files on disk, not a sidecar record."""
    sheet = make_sheet(tmp_path, n=3)
    out = tmp_path / "out"
    # pre-place img_0's dest file (the "already done" one)
    dest0 = out / dest_for("fake/img_0.png", "chatgpt")
    dest0.parent.mkdir(parents=True, exist_ok=True)
    dest0.write_bytes(b"OLD")

    driver = FakeDriver(SITES["chatgpt"])
    logs: list[str] = []
    generated = run_sheet(
        sheet, driver, out, "chatgpt", FAST, log=logs.append
    )
    # img_0 already on disk -> skipped and NOT overwritten; 1 & 2 run
    assert generated == 2
    assert dest0.read_bytes() == b"OLD"  # a done item is never touched
    assert (out / dest_for("fake/img_1.png", "chatgpt")).read_bytes() == PNG_1PX
    assert (out / dest_for("fake/img_2.png", "chatgpt")).read_bytes() == PNG_1PX
    assert len(driver.submitted) == 2  # only the two missing ones ran
    assert any("RESUME: 1/3 already saved" in line for line in logs)


def test_only_never_overwrites_an_existing_file(tmp_path):
    """BUG 1 fix (owner 2026-07-21): the folder is the source of truth
    even under a ticked `only` selection — a ticked item whose dest
    file already exists is SKIPPED, never overwritten. This was the
    exact bug from a real run: 18 already-saved images got regenerated
    after a restart because the old `only` branch queued straight from
    the ticks, never checking the disk."""
    sheet = make_sheet(tmp_path, n=2)
    out = tmp_path / "out"
    # both dests already exist from a prior run, with stale bytes
    for k in (0, 1):
        d = out / dest_for(f"fake/img_{k}.png", "gemini")
        d.parent.mkdir(parents=True, exist_ok=True)
        d.write_bytes(b"STALE")

    driver = FakeDriver(SITES["gemini"])
    logs: list[str] = []
    # tick BOTH -> both already saved on disk -> neither regenerates
    generated = run_sheet(
        sheet, driver, out, "gemini", FAST,
        only={"fake/img_0.png", "fake/img_1.png"}, log=logs.append,
    )
    assert generated == 0
    assert driver.submitted == []  # nothing was regenerated
    assert (out / dest_for("fake/img_0.png", "gemini")).read_bytes() == b"STALE"
    assert (out / dest_for("fake/img_1.png", "gemini")).read_bytes() == b"STALE"
    assert any("RESUME: 2/2 already saved" in line for line in logs)
    report = state(out, "gemini", "fake_prompts_report.txt").read_text(
        encoding="utf-8"
    )
    assert "already saved on disk" in report


def test_only_still_queues_a_ticked_item_missing_on_disk(tmp_path):
    """The other half of the same fix: `only` still narrows candidates
    normally — a ticked item with NO dest file on disk is queued and
    generated exactly as before."""
    sheet = make_sheet(tmp_path, n=2)
    out = tmp_path / "out"
    driver = FakeDriver(SITES["gemini"])
    generated = run_sheet(
        sheet, driver, out, "gemini", FAST, only={"fake/img_0.png"}
    )
    assert generated == 1
    assert (out / dest_for("fake/img_0.png", "gemini")).read_bytes() == PNG_1PX
    assert not (out / dest_for("fake/img_1.png", "gemini")).exists()


def test_extra_suffix_appends_the_per_item_note(tmp_path):
    """The AI checker's re-send path (owner 2026-07-20): ``extra_suffix``
    maps a drop path to EXTRA text appended after the site suffix for
    exactly that item; unmapped items get none, and the note also rides
    the SAFER-RETRY resend (the preamble is prepended to the same base)."""
    sheet = make_sheet(tmp_path, n=3)
    out = tmp_path / "out"
    driver = FakeDriver(SITES["gemini"])
    suffix = prompt_suffix("gemini", "white")
    note = "The previous attempt had these flaws: subject cut. Regenerate."
    generated = run_sheet(
        sheet, driver, out, "gemini", FAST,
        prompt_suffix=suffix,
        extra_suffix={"fake/img_1.png": note},
        only={"fake/img_0.png", "fake/img_1.png"},
    )
    assert generated == 2
    # item 0: prompt + site suffix only; item 1: ... + the fix note
    assert driver.submitted[0] == "prompt 0" + suffix
    assert driver.submitted[1] == "prompt 1" + suffix + "\n\n" + note


def test_extra_suffix_survives_the_safer_retry(tmp_path):
    class RefuseOnce(FakeDriver):
        def extract_image(self):
            if SAFER_PREAMBLE not in self.submitted[-1]:
                raise ItemRefused("refused: unsafe", category=REFUSAL_SAFETY)
            return PNG_1PX

    sheet = make_sheet(tmp_path, n=1)
    out = tmp_path / "out"
    driver = RefuseOnce(SITES["gemini"])
    note = "Fix the stray line."
    generated = run_sheet(
        sheet, driver, out, "gemini", FAST,
        extra_suffix={"fake/img_0.png": note},
        safer_retry=True,
    )
    assert generated == 1
    # both the original send and the safer retry carry the note
    assert all(s.endswith("\n\n" + note) for s in driver.submitted)
    assert driver.submitted[1].startswith(SAFER_PREAMBLE)


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


def test_pause_flag_waits_between_items_then_resumes(tmp_path, monkeypatch):
    """The GUI Pause toggle (should_pause): the loop blocks BETWEEN
    items, poll-waiting (tiny interval here, so the test stays fast)
    until should_pause flips False, then generates normally. The
    paused/resumed events fire exactly ONCE each, before the first
    item, never once per poll."""
    monkeypatch.setattr(runner_module, "PAUSE_POLL_INTERVAL_S", 0.01)
    sheet = make_sheet(tmp_path, n=2)
    out = tmp_path / "out"
    driver = FakeDriver(SITES["chatgpt"])
    events: list[dict] = []
    polls = {"n": 0}

    def should_pause():
        polls["n"] += 1
        return polls["n"] < 4  # True the first 3 calls, False afterwards

    generated = run_sheet(
        sheet, driver, out, "chatgpt", FAST,
        should_pause=should_pause, on_event=events.append,
    )
    assert generated == 2
    assert len(driver.submitted) == 2  # both items still ran
    kinds = [e["type"] for e in events]
    assert kinds.count("sheet_paused") == 1   # once, not per poll
    assert kinds.count("sheet_resumed") == 1
    # paused/resumed resolve BEFORE the first item starts (checked at
    # the top of the per-item loop, the same boundary as should_stop)
    assert kinds.index("sheet_resumed") < kinds.index("item_start")


def test_stop_interrupts_a_paused_run(tmp_path, monkeypatch):
    """MUST NOT REGRESS: Stop always wins over a pending pause — a run
    stuck paused (should_pause never flips off on its own) still stops
    promptly once should_stop fires, instead of hanging forever. No
    item runs and 'sheet_resumed' never fires (the run is ending, not
    continuing)."""
    monkeypatch.setattr(runner_module, "PAUSE_POLL_INTERVAL_S", 0.01)
    sheet = make_sheet(tmp_path, n=2)
    out = tmp_path / "out"
    driver = FakeDriver(SITES["chatgpt"])
    events: list[dict] = []
    polls = {"n": 0}

    def should_stop():
        polls["n"] += 1
        return polls["n"] > 3  # a few poll ticks pass, then Stop wins

    generated = run_sheet(
        sheet, driver, out, "chatgpt", FAST,
        should_pause=lambda: True,  # never resumes on its own
        should_stop=should_stop,
        on_event=events.append,
    )
    assert generated == 0
    assert driver.submitted == []  # stopped before any item ran
    kinds = [e["type"] for e in events]
    assert "sheet_paused" in kinds
    assert "sheet_resumed" not in kinds  # Stop wins — never "resumed"
    report = state(out, "chatgpt", "fake_prompts_report.txt").read_text(
        encoding="utf-8"
    )
    assert "stopped on request" in report
