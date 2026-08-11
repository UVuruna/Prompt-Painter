"""Offline tests for the AI response TRANSCRIPT + the refusal
diagnostic question (owner 2026-08-11): every text the site answered is
written to ``_state/<site>/transcript.jsonl`` verbatim, and a refusal
that survives the safer retry triggers ONE text-only "why was this
blocked" question whose answer lands in the transcript, the report txt
and the ``item_refused`` event (the dashboard's double-click view).

Same self-contained FakeDriver/make_sheet idiom as the other runner
suites (see test_runner_paths_and_save.py for the rationale).
"""

import json
from pathlib import Path

import pytest

from painter import recovery as recovery_module
from painter.config import REFUSAL_DIAGNOSTIC_QUESTION, SITES, TIMING
from painter.driver import ItemRefused
from painter.runner import run_sheet
from painter.sheet_parser import PromptItem, Sheet, SkippedItem
from painter.transcript import Transcript

from dataclasses import replace

FAST = replace(TIMING, pause_min_s=0.0, pause_max_s=0.0)

PNG_1PX = bytes.fromhex(
    "89504e470d0a1a0a0000000d49484452000000010000000108060000001f15c489"
    "0000000d4944415478da63fcffff3f030005fe02fea72d994800000000"
    "49454e44ae426082"
)


@pytest.fixture(autouse=True)
def _fast_recovery(monkeypatch):
    monkeypatch.setattr(
        recovery_module, "IMAGE_FAILED_RETRY_DELAY_RANGE_S", (0.0, 0.0)
    )
    monkeypatch.setattr(
        recovery_module,
        "IMAGE_FAILED_ESCALATION_DELAYS_S",
        ((0.0, 0.0), (0.0, 0.0)),
    )


class FakeDriver:
    def __init__(self, site):
        self.site = site
        self.submitted: list[str] = []
        self.asked: list[str] = []
        self.last_response_text = ""
        self._extract_n = 0

    def submit_prompt(self, prompt, log=print):
        self.submitted.append(prompt)

    def submit_with_image(self, image_path, prompt, log=print):
        self.submitted.append(prompt)

    def await_done(self, log=print):
        pass

    def extract_image(self):
        self._extract_n += 1
        return PNG_1PX + bytes([self._extract_n % 256])

    def click_error_retry(self, log=print):
        return False

    def refresh(self, log=print):
        pass

    def new_chat(self, log=print):
        pass

    def ask_text(self, question, log=print):
        self.asked.append(question)
        self.last_response_text = "The likeness in the prompt is blocked."
        return self.last_response_text


def make_sheet(tmp_path: Path, n: int = 1) -> Sheet:
    source = tmp_path / "fake_prompts.md"
    source.write_text("# Fake Theme\n", encoding="utf-8")
    items = tuple(
        PromptItem(f"Item {k}", f"fake/img_{k}.png", f"prompt {k}", k)
        for k in range(n)
    )
    return Sheet("Fake Theme", source, items, (), ())


def read_transcript(out: Path, site: str) -> list[dict]:
    path = out / "_state" / site / "transcript.jsonl"
    return [
        json.loads(line)
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]


def test_transcript_record_appends_jsonl(tmp_path):
    t = Transcript(tmp_path / "deep" / "transcript.jsonl")
    t.record("refused", sheet="s.md", item="a/b.png",
             raw_text="I can't do that", matched="safety", action="skip")
    t.record("saved", sheet="s.md", item="a/b.png", action="a/b_gpt.png")
    rows = [
        json.loads(line)
        for line in (tmp_path / "deep" / "transcript.jsonl")
        .read_text(encoding="utf-8").splitlines()
    ]
    assert [r["event"] for r in rows] == ["refused", "saved"]
    assert rows[0]["raw_text"] == "I can't do that"
    assert rows[0]["matched"] == "safety"
    assert rows[1]["matched"] is None
    assert all(r["sheet"] == "s.md" for r in rows)


def test_transcript_write_failure_is_loud_but_nonfatal(tmp_path):
    # point the transcript AT a directory — the open() must fail
    target = tmp_path / "transcript.jsonl"
    target.mkdir()
    logs: list[str] = []
    Transcript(target).record("saved", log=logs.append)
    assert any("TRANSCRIPT WRITE FAILED" in line for line in logs)


def test_saved_item_lands_in_the_transcript(tmp_path):
    sheet = make_sheet(tmp_path, n=1)
    out = tmp_path / "out"
    driver = FakeDriver(SITES["chatgpt"])
    assert run_sheet(sheet, driver, out, "chatgpt", FAST) == 1
    rows = read_transcript(out, "chatgpt")
    assert [r["event"] for r in rows] == ["saved"]
    assert rows[0]["item"] == "fake/img_0.png"


def test_double_refusal_asks_the_diagnostic_question(tmp_path):
    """First attempt refused (copyright) -> safer retry refused too ->
    the runner asks ONE text-only diagnostic question; its answer lands
    in the transcript, the report txt (WHY line) and the item_refused
    event's ``diagnosis`` field (owner 2026-08-11)."""
    class AlwaysRefuses(FakeDriver):
        def await_done(self, log=print):
            self.last_response_text = (
                "This image generation request did not follow our"
                " content policy (third-party content)."
            )
            raise ItemRefused(
                "ChatGPT: prompt refused [copyright] (matched"
                " 'content policy'): ...",
                category="copyright",
            )

    sheet = make_sheet(tmp_path, n=1)
    out = tmp_path / "out"
    events: list[dict] = []
    driver = AlwaysRefuses(SITES["chatgpt"])
    generated = run_sheet(
        sheet, driver, out, "chatgpt", FAST,
        safer_retry=True, on_event=events.append,
    )
    assert generated == 0
    # exactly ONE diagnostic question, the configured one
    assert driver.asked == [REFUSAL_DIAGNOSTIC_QUESTION]

    rows = read_transcript(out, "chatgpt")
    assert [r["event"] for r in rows] == [
        "refused", "retry_failed", "skipped", "diagnosis",
    ]
    assert rows[0]["matched"] == "copyright"
    assert rows[0]["action"] == "safer retry"
    assert "third-party content" in rows[0]["raw_text"]
    assert rows[3]["raw_text"] == "The likeness in the prompt is blocked."

    refused_events = [e for e in events if e["type"] == "item_refused"]
    assert len(refused_events) == 1
    assert "copyright" in refused_events[0]["reason"]
    assert refused_events[0]["diagnosis"] == (
        "The likeness in the prompt is blocked."
    )

    report = (out / "_state" / "chatgpt" / "fake_prompts_report.txt")
    text = report.read_text(encoding="utf-8")
    assert "REFUSED" in text
    assert "WHY (site's answer)" in text
    assert "The likeness in the prompt is blocked." in text


def test_unmatched_text_answer_is_mined_as_matched_null(tmp_path):
    """The transcript's whole point: a NoImage(had_text=True) answer —
    text our markers do NOT know — is recorded verbatim with
    ``matched: null``, the row new markers are mined from."""
    from painter.driver import NoImage

    class UnknownText(FakeDriver):
        def await_done(self, log=print):
            self.last_response_text = (
                "Here is a poem about your emblem instead."
            )
            raise NoImage("ChatGPT: TEXT but no image", had_text=True)

    sheet = make_sheet(tmp_path, n=1)
    out = tmp_path / "out"
    driver = UnknownText(SITES["chatgpt"])
    assert run_sheet(sheet, driver, out, "chatgpt", FAST) == 0
    rows = read_transcript(out, "chatgpt")
    assert rows[0]["event"] == "no_image"
    assert rows[0]["matched"] is None
    assert rows[0]["raw_text"] == "Here is a poem about your emblem instead."
    assert rows[0]["action"] == "skip"
