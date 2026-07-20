"""Offline tests for the Gemini client + AI flows — NO live API.

The HTTP layer is one monkeypatchable alias (``painter.ai._urlopen``);
every test feeds canned response dicts through it and asserts the
REQUEST the client built (url, headers, payload) and the loud failure
taxonomy (``AiError`` on HTTP/refusal/malformed, ``NoKey`` on a
missing key). The sheet-generator flow and the flag memory run against
tmp_path with a mocked ``generate_text``.
"""

import io
import json
import urllib.error
from pathlib import Path

import pytest

from painter import ai
from painter.config import (
    AI_MAX_QUESTIONS,
    GEMINI_API_BASE,
    GEMINI_TEXT_MODEL,
    GEMINI_VISION_MODEL,
)

# a real 1x1 PNG (same fixture bytes as test_runner)
PNG_1PX = bytes.fromhex(
    "89504e470d0a1a0a0000000d49484452000000010000000108060000001f15c489"
    "0000000d4944415478da63fcffff3f030005fe02fea72d994800000000"
    "49454e44ae426082"
)


class FakeResponse:
    def __init__(self, payload: dict):
        self._raw = json.dumps(payload).encode("utf-8")

    def read(self) -> bytes:
        return self._raw

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False


def text_response(text: str) -> dict:
    return {
        "candidates": [
            {
                "content": {"parts": [{"text": text}]},
                "finishReason": "STOP",
            }
        ]
    }


@pytest.fixture(autouse=True)
def fast_and_keyless(monkeypatch):
    """No pacing sleeps and no reading of the OWNER'S settings.json:
    every test either passes ``key=`` explicitly or monkeypatches
    ``load_settings`` itself."""
    monkeypatch.setattr(ai, "AI_CALL_PAUSE_S", 0.0)
    monkeypatch.setattr(ai, "_last_call_t", None)
    monkeypatch.setattr(ai, "load_settings", lambda: {})


def capture_call(monkeypatch, response: dict) -> list:
    """Route ``_urlopen`` into a recorder; returns the request list."""
    requests: list = []

    def fake_urlopen(req, timeout):
        requests.append((req, timeout))
        return FakeResponse(response)

    monkeypatch.setattr(ai, "_urlopen", fake_urlopen)
    return requests


# --- request building -------------------------------------------------


def test_generate_text_builds_the_request(monkeypatch):
    requests = capture_call(monkeypatch, text_response("hello"))
    answer = ai.generate_text("the prompt", "the system", key="KEY123")
    assert answer == "hello"
    (req, timeout), = requests
    assert req.full_url == (
        f"{GEMINI_API_BASE}/models/{GEMINI_TEXT_MODEL}:generateContent"
    )
    assert req.get_header("X-goog-api-key") == "KEY123"
    assert req.get_header("Content-type") == "application/json"
    body = json.loads(req.data)
    assert body["contents"][0]["parts"][0]["text"] == "the prompt"
    assert body["systemInstruction"]["parts"][0]["text"] == "the system"
    assert timeout > 0


def test_generate_text_without_system_omits_the_instruction(monkeypatch):
    requests = capture_call(monkeypatch, text_response("x"))
    ai.generate_text("p", key="k")
    body = json.loads(requests[0][0].data)
    assert "systemInstruction" not in body


def test_check_image_embeds_the_base64_png(monkeypatch, tmp_path):
    img = tmp_path / "plate.png"
    img.write_bytes(PNG_1PX)
    requests = capture_call(monkeypatch, text_response("OK"))
    ai.check_image(img, "find defects", key="k")
    req = requests[0][0]
    assert req.full_url == (
        f"{GEMINI_API_BASE}/models/{GEMINI_VISION_MODEL}:generateContent"
    )
    parts = json.loads(req.data)["contents"][0]["parts"]
    assert parts[0]["text"] == "find defects"
    inline = parts[1]["inlineData"]
    assert inline["mimeType"] == "image/png"
    import base64

    assert base64.b64decode(inline["data"]) == PNG_1PX


def test_check_image_refuses_a_non_image_suffix(tmp_path):
    with pytest.raises(ai.AiError, match="unsupported image type"):
        ai.check_image(tmp_path / "notes.txt", "x", key="k")


# --- response parsing --------------------------------------------------


def test_response_concatenates_parts_and_skips_empty_candidates(monkeypatch):
    capture_call(
        monkeypatch,
        {
            "candidates": [
                {"content": {"parts": []}, "finishReason": "STOP"},
                {
                    "content": {
                        "parts": [{"text": "two "}, {"text": "parts"}]
                    }
                },
            ]
        },
    )
    assert ai.generate_text("p", key="k") == "two parts"


def test_blocked_prompt_is_loud(monkeypatch):
    capture_call(
        monkeypatch, {"promptFeedback": {"blockReason": "SAFETY"}}
    )
    with pytest.raises(ai.AiError, match="blocked.*SAFETY"):
        ai.generate_text("p", key="k")


def test_non_stop_finish_with_no_text_is_loud(monkeypatch):
    capture_call(
        monkeypatch,
        {"candidates": [{"content": {"parts": []},
                         "finishReason": "MAX_TOKENS"}]},
    )
    with pytest.raises(ai.AiError, match="MAX_TOKENS"):
        ai.generate_text("p", key="k")


def test_malformed_response_is_loud(monkeypatch):
    capture_call(monkeypatch, {"unexpected": True})
    with pytest.raises(ai.AiError, match="no text"):
        ai.generate_text("p", key="k")


def test_http_error_carries_the_api_message(monkeypatch):
    def fake_urlopen(req, timeout):
        raise urllib.error.HTTPError(
            req.full_url, 400, "Bad Request", None,
            io.BytesIO(json.dumps(
                {"error": {"message": "API key not valid"}}
            ).encode()),
        )

    monkeypatch.setattr(ai, "_urlopen", fake_urlopen)
    with pytest.raises(ai.AiError, match="HTTP 400.*API key not valid"):
        ai.generate_text("p", key="bad")


def test_network_error_is_loud(monkeypatch):
    def fake_urlopen(req, timeout):
        raise urllib.error.URLError("no route to host")

    monkeypatch.setattr(ai, "_urlopen", fake_urlopen)
    with pytest.raises(ai.AiError, match="unreachable"):
        ai.generate_text("p", key="k")


# --- key handling ------------------------------------------------------


def test_missing_key_raises_nokey(monkeypatch):
    monkeypatch.setattr(ai, "load_settings", lambda: {})
    with pytest.raises(ai.NoKey):
        ai.api_key()
    monkeypatch.setattr(
        ai, "load_settings", lambda: {"gemini_api_key": "   "}
    )
    with pytest.raises(ai.NoKey):
        ai.api_key()


def test_saved_key_is_read_from_settings(monkeypatch):
    monkeypatch.setattr(
        ai, "load_settings", lambda: {"gemini_api_key": " abc "}
    )
    assert ai.api_key() == "abc"


def test_generate_without_key_raises_nokey_before_any_http(monkeypatch):
    called = []
    monkeypatch.setattr(
        ai, "_urlopen", lambda *a, **k: called.append(1)
    )
    with pytest.raises(ai.NoKey):
        ai.generate_text("p")
    assert called == []  # NoKey fires BEFORE any network traffic


def test_pacing_sleeps_between_calls(monkeypatch):
    monkeypatch.setattr(ai, "AI_CALL_PAUSE_S", 60.0)
    sleeps: list[float] = []
    monkeypatch.setattr(ai.time, "sleep", sleeps.append)
    capture_call(monkeypatch, text_response("x"))
    ai.generate_text("one", key="k")   # first call: no wait
    ai.generate_text("two", key="k")   # second: paced
    assert len(sleeps) == 1
    assert 0 < sleeps[0] <= 60.0


# --- the sheet-generator flow ------------------------------------------


def test_parse_questions_reads_numbered_and_bulleted_lines():
    text = (
        "Here is what I need to know:\n"
        "1. How many images?\n"
        "2) Which drop folder?\n"
        "- Transparent or white background?\n"
        "* Rondel or lancet shape?\n"
        "Thanks!\n"
    )
    assert ai.parse_questions(text) == [
        "How many images?",
        "Which drop folder?",
        "Transparent or white background?",
        "Rondel or lancet shape?",
    ]


def test_parse_questions_caps_at_the_config_maximum():
    text = "\n".join(f"{n}. Question {n}?" for n in range(1, 11))
    assert len(ai.parse_questions(text)) == AI_MAX_QUESTIONS


def test_parse_questions_empty_on_prose():
    assert ai.parse_questions("I have no questions, generating now.") == []


def test_qa_block_marks_skipped_answers():
    block = ai.qa_block(["Count?", "Folder?"], ["12", "  "])
    assert "Q: Count?" in block and "A: 12" in block
    assert "A: (no preference — your choice)" in block


def test_strip_md_fence_unwraps_only_the_whole_file_wrapper():
    inner = "# Theme\n\n**A** → `assets/badge/t/A.png`\n\n```\nprompt\n```\n"
    wrapped = f"```markdown\n{inner}```"
    out = ai.strip_md_fence(wrapped)
    assert out == inner.rstrip("\n")
    # the unwrap keeps the INNER prompt fence pair intact
    assert out.count("```") == 2
    assert out.lstrip().startswith("# Theme")
    # an unwrapped sheet passes through byte-identical
    assert ai.strip_md_fence(inner) == inner


VALID_MD = (
    "# Astro Test\n\n"
    "**Sun** → `assets/zodiac/astro/Sun.png`\n\n"
    "```\nA radiant sun rondel.\n```\n\n"
    "**Moon** → `assets/zodiac/astro/Moon.png`\n\n"
    "```\nA silver moon rondel.\n```\n"
)
BROKEN_MD = (
    "# Astro Test\n\n"
    "**Sun** → `assets/zodiac/astro/Sun.png`\n\n"
    "no prompt block follows — a contract violation\n"
)


def test_validate_sheet_md_clean_and_broken(tmp_path):
    problems, theme = ai.validate_sheet_md(VALID_MD, tmp_path)
    assert problems == []
    assert theme == "Astro Test"
    problems, _theme = ai.validate_sheet_md(BROKEN_MD, tmp_path)
    assert problems and "no prompt block" in problems[0]
    problems, theme = ai.validate_sheet_md("just prose\n", tmp_path)
    assert theme is None and "H1" in problems[0]


def test_generate_sheet_repairs_once_and_validates(tmp_path):
    calls: list[tuple[str, str]] = []

    def gen(prompt, system=None, **_kw):
        calls.append((prompt, system))
        # first (generation) call returns a BROKEN sheet, the repair
        # call returns the fixed one — wrapped in a fence the flow strips
        if len(calls) == 1:
            return BROKEN_MD
        return f"```markdown\n{VALID_MD}```"

    logs: list[str] = []
    md, problems, theme = ai.generate_sheet(
        "12 astrology images", ["Count?"], ["12"], "THE CONTRACT",
        tmp_path, gen=gen, log=logs.append,
    )
    assert problems == []
    assert theme == "Astro Test"
    assert md.lstrip().startswith("# Astro Test")
    assert len(calls) == 2
    # the generation call carries the request + the answered poll in the
    # user prompt and the contract in the system prompt
    assert "12 astrology images" in calls[0][0]
    assert "Q: Count?" in calls[0][0] and "A: 12" in calls[0][0]
    assert "THE CONTRACT" in calls[0][1]
    # the repair call feeds the parser problems + the broken md back
    assert "no prompt block" in calls[1][0]
    assert BROKEN_MD.strip() in calls[1][0]
    assert any("repair round" in line for line in logs)


def test_generate_sheet_still_broken_reports_problems(tmp_path):
    md, problems, _theme = ai.generate_sheet(
        "req", [], [], "contract", tmp_path,
        gen=lambda p, s=None, **_k: BROKEN_MD, log=lambda _l: None,
    )
    assert problems  # the caller must NOT load this md
    assert md == BROKEN_MD


def test_generate_sheet_valid_first_try_skips_the_repair(tmp_path):
    calls = []

    def gen(prompt, system=None, **_kw):
        calls.append(prompt)
        return VALID_MD

    _md, problems, _theme = ai.generate_sheet(
        "req", [], [], "contract", tmp_path, gen=gen, log=lambda _l: None
    )
    assert problems == []
    assert len(calls) == 1  # no repair round needed


def test_save_sheet_slugs_and_never_collides(tmp_path):
    sheets = tmp_path / "sheets"
    first = ai.save_sheet("# x\n", "Astrology — Zodiac Set!", sheets)
    second = ai.save_sheet("# y\n", "Astrology — Zodiac Set!", sheets)
    assert first.name == "astrology_zodiac_set.md"
    assert second.name == "astrology_zodiac_set_2.md"
    assert first.read_text(encoding="utf-8") == "# x\n"


# --- the checker's response format -------------------------------------


def test_parse_check_response_ok_variants():
    assert ai.parse_check_response("OK") == []
    assert ai.parse_check_response("ok.") == []
    assert ai.parse_check_response("  OK\n") == []


def test_parse_check_response_defect_lines():
    text = (
        "DEFECTS:\n"
        "- subject slightly cut at the left edge\n"
        "- leftover white patch near the top\n"
    )
    assert ai.parse_check_response(text) == [
        "subject slightly cut at the left edge",
        "leftover white patch near the top",
    ]
    # a single defect on the header line is tolerated
    assert ai.parse_check_response("DEFECTS: watermark bottom-right") == [
        "watermark bottom-right"
    ]


def test_parse_check_response_garbage_is_loud():
    with pytest.raises(ai.AiError, match="unexpected check response"):
        ai.parse_check_response("The image looks quite nice overall.")
    with pytest.raises(ai.AiError):
        ai.parse_check_response("")


def test_fix_note_joins_the_defects():
    note = ai.fix_note(["cut at edge", "stray line"])
    assert "cut at edge; stray line" in note
    assert "Regenerate" in note


# --- flag memory --------------------------------------------------------


def _make_image(out: Path, rel: str) -> Path:
    path = out / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(PNG_1PX)
    return path


def test_flags_round_trip(tmp_path):
    out = tmp_path / "out"
    img = _make_image(out, "emblem/gemini/mood/Glory.png")
    key = ai.record_flag(
        out, img, ["subject cut"], "gemini-test", log=lambda _l: None
    )
    assert key == "emblem/gemini/mood/Glory.png"
    flags = ai.load_flags(out)
    entry = flags[key]
    assert entry["defects"] == ["subject cut"]
    assert entry["model"] == "gemini-test"
    assert entry["checked_at"]
    assert entry["mtime"] == img.stat().st_mtime
    # the file lives under <out>/_state/ai_flags.json
    assert ai.flags_path(out).is_file()
    # clear drops it; clearing again reports nothing to do
    assert ai.clear_flag(out, img) is True
    assert ai.clear_flag(out, img) is False
    assert ai.load_flags(out) == {}


def test_flags_merge_never_clobbers_other_entries(tmp_path):
    out = tmp_path / "out"
    a = _make_image(out, "badge/chatgpt/a.png")
    b = _make_image(out, "badge/chatgpt/b.png")
    ai.record_flag(out, a, ["x"], "m", log=lambda _l: None)
    ai.record_flag(out, b, ["y"], "m", log=lambda _l: None)
    assert set(ai.load_flags(out)) == {
        "badge/chatgpt/a.png", "badge/chatgpt/b.png",
    }


def test_prune_drops_regenerated_and_missing_files(tmp_path):
    import os

    out = tmp_path / "out"
    keep = _make_image(out, "badge/chatgpt/keep.png")
    regen = _make_image(out, "badge/chatgpt/regen.png")
    gone = _make_image(out, "badge/chatgpt/gone.png")
    for img in (keep, regen, gone):
        ai.record_flag(out, img, ["d"], "m", log=lambda _l: None)
    # regenerate one (mtime changes), delete another
    os.utime(regen, (regen.stat().st_atime, regen.stat().st_mtime + 60))
    gone.unlink()
    dropped = ai.prune_stale_flags(out, log=lambda _l: None)
    assert dropped == 2
    assert set(ai.load_flags(out)) == {"badge/chatgpt/keep.png"}
    # a second prune finds nothing stale
    assert ai.prune_stale_flags(out, log=lambda _l: None) == 0


def test_corrupt_flags_file_is_loud_but_empty(tmp_path):
    out = tmp_path / "out"
    path = ai.flags_path(out)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("{broken json", encoding="utf-8")
    logs: list[str] = []
    assert ai.load_flags(out, log=logs.append) == {}
    assert any("cannot read" in line for line in logs)


def test_flag_key_relative_inside_absolute_outside(tmp_path):
    out = tmp_path / "out"
    inside = _make_image(out, "emblem/gemini/x.png")
    outside = tmp_path / "elsewhere" / "y.png"
    outside.parent.mkdir(parents=True)
    outside.write_bytes(PNG_1PX)
    assert ai.flag_key(inside, out) == "emblem/gemini/x.png"
    key = ai.flag_key(outside, out)
    assert Path(key).is_absolute()
    assert key.endswith("elsewhere/y.png")


# --- the re-send reverse mapping ----------------------------------------


def test_drop_and_site_for_reverses_dest_for():
    from painter.config import dest_for

    # the assets mirror: out rel -> the original site-agnostic drop
    rel = dest_for("assets/emblem/mood/Glory.png", "gemini")
    assert ai.drop_and_site_for(rel) == (
        "assets/emblem/mood/Glory.png", "gemini",
    )
    # the legacy layout: <site>/<drop>
    rel = dest_for("fake/img_0.png", "chatgpt")
    assert ai.drop_and_site_for(rel) == ("fake/img_0.png", "chatgpt")


def test_drop_and_site_for_none_when_no_site_segment():
    assert ai.drop_and_site_for("random/folder/pic.png") is None
    assert ai.drop_and_site_for("pic.png") is None
    # an ABSOLUTE flag key (image outside the out base) never matches
    assert ai.drop_and_site_for("C:/somewhere/else/pic.png") is None


def test_plan_resend_groups_by_site_and_sheet():
    flagged = {
        "emblem/gemini/mood/Glory.png": ["subject cut"],
        "emblem/gemini/mood/Anger.png": ["stray line", "halo"],
        "chatgpt/fake/img_0.png": ["watermark"],  # the legacy layout
    }
    drop_to_source = {
        "assets/emblem/mood/Glory.png": "C:/sheets/mood.md",
        "assets/emblem/mood/Anger.png": "C:/sheets/mood.md",
        "fake/img_0.png": "C:/sheets/fake.md",
    }
    plans, notes, unmatched = ai.plan_resend(flagged, drop_to_source)
    assert unmatched == []
    assert plans["gemini"] == {
        "C:/sheets/mood.md": {
            "assets/emblem/mood/Glory.png",
            "assets/emblem/mood/Anger.png",
        }
    }
    assert plans["chatgpt"] == {"C:/sheets/fake.md": {"fake/img_0.png"}}
    # each item carries ITS OWN fix note with its ';'-joined defects
    assert "subject cut" in notes["gemini"]["assets/emblem/mood/Glory.png"]
    assert "stray line; halo" in notes["gemini"]["assets/emblem/mood/Anger.png"]
    assert "watermark" in notes["chatgpt"]["fake/img_0.png"]


def test_plan_resend_reports_unmatched_loudly():
    flagged = {
        "nosite/pic.png": ["x"],                 # no site segment
        "emblem/gemini/mood/Ghost.png": ["y"],   # site, but not queued
    }
    plans, notes, unmatched = ai.plan_resend(flagged, {})
    assert plans == {} and notes == {}
    reasons = dict(unmatched)
    assert reasons["nosite/pic.png"] == "no site in the path"
    assert (
        reasons["emblem/gemini/mood/Ghost.png"]
        == "not in any queued collection"
    )
