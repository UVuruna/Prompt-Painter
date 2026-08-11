"""Offline tests for the run loop — the ``ImageGenFailed`` recovery
ladder (BUG 3, owner 2026-07-21 + escalation 2026-07-23): native Retry
button -> paced "retry" text resends -> escalation rounds (refresh ->
new session -> whole prompt), plus the F1 duplicate-save guard (owner
2026-07-29).

Split from the former ``test_runner.py`` god-file (root Rule #20,
second round — split by concern). See test_runner_paths_and_save.py
for the shared ``FakeDriver``/``make_sheet``/``state`` rationale
(duplicated here — each split module is self-contained by design).
"""

from dataclasses import replace
from pathlib import Path

import pytest

from painter import recovery as recovery_module
from painter import runner as runner_module
from painter.config import (
    CONTINUE_NUDGE,
    IMAGE_FAILED_RETRY_MAX,
    IMAGE_RETRY_NUDGE,
    REFUSAL_SAFETY,
    SITES,
    TIMING,
)
from painter.driver import (
    GenerationTimeout,
    ImageGenFailed,
    ItemRefused,
    NoImage,
    SendNotConfirmed,
    SendVanished,
)
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
        recovery_module, "IMAGE_FAILED_RETRY_DELAY_RANGE_S", (0.0, 0.0)
    )
    monkeypatch.setattr(
        recovery_module,
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
                return super().extract_image()
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
    assert (out / "chatgpt" / "fake" / "img_0.png").exists()
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
                return super().extract_image()
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
                return super().extract_image()
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


def test_refusal_inside_ladder_skips_item_not_site(tmp_path):
    """F1 fix (owner 2026-07-29): an ItemRefused surfacing INSIDE the
    image-failed recovery ladder used to escape and stop the WHOLE
    site; now it is caught exactly like a first-attempt refusal — one
    safer retry when enabled (none here), else a loud per-item skip —
    and the run continues to the next item."""
    class RefusedInLadder(FakeDriver):
        def submit_prompt(self, prompt, log=print):
            super().submit_prompt(prompt)
            if prompt == IMAGE_RETRY_NUDGE:
                # the site refuses the "retry" resend itself, mid-ladder
                raise ItemRefused(
                    "ChatGPT: prompt refused mid-ladder",
                    category=REFUSAL_SAFETY,
                )

        def extract_image(self):
            if "prompt 0" in self.submitted[-1]:
                raise ImageGenFailed(
                    "ChatGPT: image generation failed: ..."
                )
            return super().extract_image()

    sheet = make_sheet(tmp_path, n=2)
    out = tmp_path / "out"
    logs: list[str] = []
    driver = RefusedInLadder(SITES["chatgpt"])
    generated = run_sheet(
        sheet, driver, out, "chatgpt", FAST, log=logs.append,
    )  # must not raise — the refusal skips item 0, never stops the site

    assert generated == 1  # item 0 refused mid-ladder, item 1 still ran
    assert not (out / "chatgpt" / "fake" / "img_0.png").exists()
    assert (out / "chatgpt" / "fake" / "img_1.png").exists()
    report = state(out, "chatgpt", "fake_prompts_report.txt").read_text(
        encoding="utf-8"
    )
    assert "REFUSED" in report


def test_duplicate_bytes_retries_once_then_skips(tmp_path):
    """F1 duplicate guard (owner 2026-07-29): the site re-serving the
    PREVIOUS item's exact bytes gets ONE fresh re-submit; still
    identical afterwards -> a loud per-item skip, never a silent
    duplicate file. Item 0 (unique bytes) saves normally; item 1
    re-serves item 0's bytes both times and ends up skipped."""
    class DuplicateOnSecond(FakeDriver):
        def __init__(self, site):
            super().__init__(site)
            self._first_bytes = None

        def extract_image(self):
            if "prompt 0" in self.submitted[-1]:
                self._first_bytes = super().extract_image()
                return self._first_bytes
            # item 1 (and its one fresh re-submit) both re-serve item
            # 0's exact bytes — the site handing back a stale image
            return self._first_bytes

    sheet = make_sheet(tmp_path, n=2)
    out = tmp_path / "out"
    logs: list[str] = []
    driver = DuplicateOnSecond(SITES["chatgpt"])
    generated = run_sheet(sheet, driver, out, "chatgpt", FAST, log=logs.append)

    assert generated == 1  # only item 0 saved
    assert (out / "chatgpt" / "fake" / "img_0.png").exists()
    assert not (out / "chatgpt" / "fake" / "img_1.png").exists()
    # item 1's duplicate triggered exactly ONE fresh re-submit
    assert driver.submitted.count("prompt 1") == 2
    assert any("DUPLICATE IMAGE" in line for line in logs)
    report = state(out, "chatgpt", "fake_prompts_report.txt").read_text(
        encoding="utf-8"
    )
    assert "REFUSED" in report


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


# --- F1b (owner 2026-08-04) — the 18:43:46 stop + the Padmé incident --

def test_safer_retry_failing_with_no_image_skips_only_the_item(tmp_path):
    """The 18:43:46 stop: a NoImage raised INSIDE the safer retry used
    to fly past the outer per-item catches (Python never routes an
    exception from one ``except`` block to its siblings) and stop the
    WHOLE site. Now it is the same loud per-item skip as any other
    failed retry — the next item still runs."""
    class RefusedThenNoImage(FakeDriver):
        def __init__(self, site):
            super().__init__(site)
            self._n = 0

        def extract_image(self):
            self._n += 1
            if self._n == 1:
                raise ItemRefused(
                    "ChatGPT: prompt refused", category=REFUSAL_SAFETY
                )
            if self._n == 2:  # the safer retry's own verdict
                raise NoImage("TEXT but no image", had_text=True)
            return super().extract_image()

    sheet = make_sheet(tmp_path, n=2)
    out = tmp_path / "out"
    logs: list[str] = []
    driver = RefusedThenNoImage(SITES["chatgpt"])
    generated = run_sheet(
        sheet, driver, out, "chatgpt", FAST,
        log=logs.append, safer_retry=True,
    )  # must not raise — the site survives the failed retry

    assert generated == 1  # item 0 skipped, item 1 saved
    assert not (out / "chatgpt" / "fake" / "img_0.png").exists()
    assert (out / "chatgpt" / "fake" / "img_1.png").exists()
    assert any("REFUSED/SKIPPED" in line for line in logs)


def test_send_vanished_resends_the_items_own_prompt(tmp_path):
    """The Padmé/Qui-Gon incident: the site DROPPED our confirmed
    message. The recovery re-sends the item's OWN prompt — never the
    content-blind continue nudge (which regenerated the PREVIOUS
    request and saved a Qui-Gon badge under Padmé's name)."""
    class VanishesOnce(FakeDriver):
        def __init__(self, site):
            super().__init__(site)
            self._n = 0

        def await_done(self, log=print):
            self._n += 1
            if self._n == 1:
                raise SendVanished(
                    "Gemini: our sent prompt is NO LONGER the newest"
                    " user turn"
                )

    sheet = make_sheet(tmp_path, n=1)
    out = tmp_path / "out"
    logs: list[str] = []
    events: list[dict] = []
    driver = VanishesOnce(SITES["gemini"])
    generated = run_sheet(
        sheet, driver, out, "gemini", FAST,
        log=logs.append, on_event=events.append,
    )

    assert generated == 1
    # the item's own prompt went out twice — and the nudge NEVER did
    assert driver.submitted == ["prompt 0", "prompt 0"]
    assert CONTINUE_NUDGE not in driver.submitted
    assert any("SENT PROMPT VANISHED" in line for line in logs)
    assert any("re-send RECOVERED" in line for line in logs)
    assert any(e["type"] == "item_retry" for e in events)


def test_send_vanished_twice_skips_the_item_not_the_site(tmp_path):
    """The re-send gets ONE try: a second vanish is a loud per-item
    skip and the run continues."""
    class AlwaysVanishes(FakeDriver):
        def await_done(self, log=print):
            raise SendVanished("Gemini: our sent prompt vanished")

    sheet = make_sheet(tmp_path, n=2)
    out = tmp_path / "out"
    logs: list[str] = []
    driver = AlwaysVanishes(SITES["gemini"])
    generated = run_sheet(
        sheet, driver, out, "gemini", FAST, log=logs.append,
    )  # must not raise

    assert generated == 0
    # per item: the original send + exactly ONE re-send
    assert driver.submitted == [
        "prompt 0", "prompt 0", "prompt 1", "prompt 1",
    ]
    assert sum(
        1 for line in logs if "REFUSED/SKIPPED" in line
    ) == 2


# ---------------------------------------------------------------
# owner 2026-08-11 — the four site-stops of the 2026-08-11 live run
# (UV/prompt.txt): every one of them was a PER-ITEM failure that
# escaped its handler and ended the whole run. These fix that.
# ---------------------------------------------------------------


def test_image_gen_failed_inside_vanished_resend_skips_the_item(tmp_path):
    """The 18:55:54 ChatGPT stop (UV/prompt.txt:5241): the vanished-
    prompt re-send's own answer was the site's "Image generation
    failed" turn. ``ImageGenFailed`` was missing from that handler's
    except tuple — Python never routes an exception from one ``except``
    block to its siblings — so it flew past every per-item catch and
    ended the run at 38/69 collections. It must skip THIS item and let
    the next one run."""
    class VanishesThenImageFails(FakeDriver):
        def extract_image(self):
            # only item 0 misbehaves: first its send vanishes, then the
            # re-send's own answer is the image-failure turn
            if self.submitted[-1] != "prompt 0":
                return super().extract_image()
            if self.submitted.count("prompt 0") == 1:
                raise SendVanished("ChatGPT: our sent prompt is NO LONGER")
            raise ImageGenFailed("ChatGPT: image generation failed")

    sheet = make_sheet(tmp_path, n=2)
    out = tmp_path / "out"
    logs: list[str] = []
    driver = VanishesThenImageFails(SITES["chatgpt"])
    generated = run_sheet(
        sheet, driver, out, "chatgpt", FAST, log=logs.append,
    )

    # item 0 skipped, item 1 still generated — the site did NOT stop
    assert generated == 1
    assert not (out / "chatgpt" / "fake" / "img_0.png").exists()
    assert (out / "chatgpt" / "fake" / "img_1.png").exists()
    assert any("REFUSED/SKIPPED" in line for line in logs)


def test_generation_timeout_on_the_first_attempt_skips_the_item(tmp_path):
    """The hard timeout was catchable in every NESTED handler but not
    on the first attempt (owner 2026-08-11) — one item whose result
    never arrives must be a per-item skip, never the end of the site."""
    class TimesOutOnce(FakeDriver):
        def await_done(self, log=print):
            if self.submitted == ["prompt 0"]:
                raise GenerationTimeout(
                    "ChatGPT: no result for OUR turn after 420s"
                )

    sheet = make_sheet(tmp_path, n=2)
    out = tmp_path / "out"
    logs: list[str] = []
    driver = TimesOutOnce(SITES["chatgpt"])
    generated = run_sheet(
        sheet, driver, out, "chatgpt", FAST, log=logs.append,
    )

    assert generated == 1
    assert not (out / "chatgpt" / "fake" / "img_0.png").exists()
    assert (out / "chatgpt" / "fake" / "img_1.png").exists()
    assert any("timed out" in line for line in logs)


def test_send_not_confirmed_resends_then_continues(tmp_path):
    """The 17:10:16 Gemini stop (UV/prompt.txt:4590): "send NOT
    confirmed within 20s" was a bare ``DriverError``, so one unaccepted
    send ended the run at 39/69 collections. The send provably did NOT
    take, so it rides the SendVanished recovery — re-send our own
    prompt once — and the run goes on either way."""
    class SendDoesNotTakeOnce(FakeDriver):
        def await_done(self, log=print):
            if self.submitted == ["prompt 0"]:
                raise SendNotConfirmed("Gemini: send NOT confirmed within 20s")

    sheet = make_sheet(tmp_path, n=2)
    out = tmp_path / "out"
    logs: list[str] = []
    driver = SendDoesNotTakeOnce(SITES["gemini"])
    generated = run_sheet(
        sheet, driver, out, "gemini", FAST, log=logs.append,
    )

    # the re-send recovered item 0, and item 1 ran normally
    assert generated == 2
    assert driver.submitted == ["prompt 0", "prompt 0", "prompt 1"]
    assert any("SEND NOT CONFIRMED" in line for line in logs)
