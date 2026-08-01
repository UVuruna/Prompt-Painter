"""Offline tests for the run loop — refusals/advice/resume/redo queue
semantics, and run control: stop, pause, the post-save hook, terminal
states (quota) and the F2 model-degradation banner.

Split from the former ``test_runner.py`` god-file (root Rule #20,
second round — split by concern). See test_runner_paths_and_save.py
for the shared ``FakeDriver``/``make_sheet``/``state`` rationale
(duplicated here — each split module is self-contained by design).
"""

from dataclasses import replace
from pathlib import Path

import pytest

from painter import runner as runner_module
from painter.config import (
    IMAGE_FAILED_ESCALATION_DELAYS_S,
    IMAGE_FAILED_RETRY_DELAY_RANGE_S,
    IMAGE_FAILED_RETRY_MAX,
    REFUSAL_SAFETY,
    SAFER_PREAMBLE,
    SITES,
    TIMING,
    dest_for,
    prompt_suffix,
)
from painter.driver import ItemRefused, ModelDegraded, TerminalState
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
            return super().extract_image()

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
    assert (
        out / dest_for("fake/img_1.png", "chatgpt")
    ).read_bytes().startswith(PNG_1PX)
    assert (
        out / dest_for("fake/img_2.png", "chatgpt")
    ).read_bytes().startswith(PNG_1PX)
    assert len(driver.submitted) == 2  # only the two missing ones ran
    assert any("RESUME: 1/3 already saved" in line for line in logs)


def test_only_ticked_existing_redoes_as_a_new_version(tmp_path):
    """A ticked item whose dest file already exists is a deliberate
    REDO (owner 2026-07-27): it generates again and saves as the next
    ``_vN`` sibling — the file already on disk is NEVER touched (the
    BUG 1 no-overwrite guarantee of 2026-07-21 survives; what changed
    is that the tick now produces a new version instead of a silent
    skip). Legacy dests carry no generator suffix in the name, so the
    version slots in before the extension: ``img_0_v2.png``."""
    sheet = make_sheet(tmp_path, n=2)
    out = tmp_path / "out"
    # both dests already exist from a prior run, with stale bytes
    for k in (0, 1):
        d = out / dest_for(f"fake/img_{k}.png", "gemini")
        d.parent.mkdir(parents=True, exist_ok=True)
        d.write_bytes(b"STALE")

    driver = FakeDriver(SITES["gemini"])
    logs: list[str] = []
    # tick BOTH -> both redo, each landing as its _v2 version file
    generated = run_sheet(
        sheet, driver, out, "gemini", FAST,
        only={"fake/img_0.png", "fake/img_1.png"}, log=logs.append,
    )
    assert generated == 2
    assert len(driver.submitted) == 2
    # the saved files are untouched; the redos landed beside them
    assert (out / dest_for("fake/img_0.png", "gemini")).read_bytes() == b"STALE"
    assert (out / dest_for("fake/img_1.png", "gemini")).read_bytes() == b"STALE"
    assert (
        out / "gemini" / "fake" / "img_0_v2.png"
    ).read_bytes().startswith(PNG_1PX)
    assert (
        out / "gemini" / "fake" / "img_1_v2.png"
    ).read_bytes().startswith(PNG_1PX)
    assert any("NEW VERSION: 2/2" in line for line in logs)
    report = state(out, "gemini", "fake_prompts_report.txt").read_text(
        encoding="utf-8"
    )
    assert "NEW VERSION: img_0_v2.png" in report


def test_ticked_redo_saves_domy_form_and_events_carry_the_rel(tmp_path):
    """The assets-mirroring redo: ``Glory_gem.png`` on disk + a tick ->
    the redo saves as ``Glory_v2_gem.png`` (the DOMY ``<File>[_vN]_
    <sfx>.png`` form, version BEFORE the generator suffix), and every
    ``item_progress``/``item_done`` event carries ``rel`` — the ACTUAL
    saved path — so the dashboard/checker follow the version file. A
    ticked item NOT yet on disk still saves canonically."""
    source = tmp_path / "assets_prompts.md"
    source.write_text("# Assets Theme\n", encoding="utf-8")
    sheet = Sheet(
        "Assets Theme", source,
        (
            PromptItem("Glory", "assets/emblem/mood/Glory.png", "p1", 1),
            PromptItem("Hope", "assets/emblem/mood/Hope.png", "p2", 2),
        ),
        (), (),
    )
    out = tmp_path / "out"
    done = out / "emblem" / "mood" / "Glory_gem.png"
    done.parent.mkdir(parents=True, exist_ok=True)
    done.write_bytes(b"STALE")

    driver = FakeDriver(SITES["gemini"])
    events: list[dict] = []
    generated = run_sheet(
        sheet, driver, out, "gemini", FAST,
        only={"assets/emblem/mood/Glory.png", "assets/emblem/mood/Hope.png"},
        on_event=events.append,
    )
    assert generated == 2
    assert done.read_bytes() == b"STALE"  # the master is never touched
    assert (
        out / "emblem/mood/Glory_v2_gem.png"
    ).read_bytes().startswith(PNG_1PX)
    assert (
        out / "emblem/mood/Hope_gem.png"
    ).read_bytes().startswith(PNG_1PX)

    rels = {
        ev["drop_path"]: ev["rel"]
        for ev in events
        if ev["type"] == "item_progress"
    }
    assert rels["assets/emblem/mood/Glory.png"] == "emblem/mood/Glory_v2_gem.png"
    assert rels["assets/emblem/mood/Hope.png"] == "emblem/mood/Hope_gem.png"
    done_rels = {
        ev["drop_path"]: ev["rel"]
        for ev in events
        if ev["type"] == "item_done"
    }
    assert done_rels == rels
    # the version note rides the actions string (report + dashboard);
    # the canonical save carries none
    acts = {
        ev["drop_path"]: ev["actions"]
        for ev in events
        if ev["type"] == "item_progress"
    }
    assert "NEW VERSION: Glory_v2_gem.png" in acts["assets/emblem/mood/Glory.png"]
    assert "NEW VERSION" not in acts["assets/emblem/mood/Hope.png"]


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
    assert (
        out / dest_for("fake/img_0.png", "gemini")
    ).read_bytes().startswith(PNG_1PX)
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
            return super().extract_image()

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


# --- F2 model degradation (owner 2026-07-29) --------------------------
# Gemini's "Limit reached. Continuing with Flash-Lite." banner: the
# driver raises ModelDegraded when its turn yields no image while the
# banner is up. The runner asks on_degrade(retry_after_s) for a choice:
# "continue" loud-skips the item and keeps the run going; anything
# else (including no callback at all) re-raises as TerminalState with
# the same retry_after_s, exactly like an ordinary quota stop.

def test_model_degraded_continue_choice_skips_item_and_run_continues(tmp_path):
    class DegradesOnFirst(FakeDriver):
        def extract_image(self):
            if "prompt 0" in self.submitted[-1]:
                raise ModelDegraded(
                    "Gemini: model-degradation banner present (quota)"
                    " — Limit reached. Continuing with Flash-Lite.",
                    retry_after_s=1620.0,
                )
            return super().extract_image()

    sheet = make_sheet(tmp_path, n=2)
    out = tmp_path / "out"
    driver = DegradesOnFirst(SITES["gemini"])
    generated = run_sheet(
        sheet, driver, out, "gemini", FAST,
        on_degrade=lambda retry_after_s: "continue",
    )  # must not raise — "continue" keeps the run alive

    assert generated == 1  # item 0 skipped (degraded), item 1 still ran
    assert not (out / "gemini" / "fake" / "img_0.png").exists()
    assert (out / "gemini" / "fake" / "img_1.png").exists()
    report = state(out, "gemini", "fake_prompts_report.txt").read_text(
        encoding="utf-8"
    )
    assert "REFUSED" in report


def test_model_degraded_no_callback_raises_terminal_state(tmp_path):
    """No on_degrade wired (the CLI path, or the GUI choice = "wait") —
    ModelDegraded re-raises as TerminalState carrying the SAME
    retry_after_s, so the caller's ordinary quota-stop handling (an
    auto-restart at the parsed reset time) applies unchanged."""
    class AlwaysDegrades(FakeDriver):
        def extract_image(self):
            raise ModelDegraded(
                "Gemini: model-degradation banner present (quota)"
                " — Limit reached. Continuing with Flash-Lite.",
                retry_after_s=900.0,
            )

    sheet = make_sheet(tmp_path, n=1)
    out = tmp_path / "out"
    driver = AlwaysDegrades(SITES["gemini"])
    with pytest.raises(TerminalState) as excinfo:
        run_sheet(sheet, driver, out, "gemini", FAST)  # on_degrade=None
    assert excinfo.value.retry_after_s == 900.0


def test_ladder_constants_are_the_f2_retimed_values():
    """Pin the F2 retiming (owner 2026-07-29): retry x3 (3-6 min), then
    3 escalation rounds of 12-15 min each — worst case ~54-63 min before
    the site stops. Imported directly from painter.config (NOT via
    runner_module) so the autouse _fast_recovery fixture's monkeypatch
    of runner_module's copies never masks the REAL shipped values."""
    assert IMAGE_FAILED_RETRY_MAX == 3
    assert IMAGE_FAILED_RETRY_DELAY_RANGE_S == (180.0, 360.0)
    assert len(IMAGE_FAILED_ESCALATION_DELAYS_S) == 3
    assert all(
        rng == (720.0, 900.0) for rng in IMAGE_FAILED_ESCALATION_DELAYS_S
    )


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
