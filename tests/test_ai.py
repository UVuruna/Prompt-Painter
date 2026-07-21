"""Offline tests for the Gemini client + AI flows — NO live API.

The HTTP layer is one monkeypatchable alias (``painter.ai._urlopen``);
every test feeds canned response dicts through it and asserts the
REQUEST the client built (url, headers, payload) and the loud failure
taxonomy (``AiError`` on HTTP/refusal/malformed, ``NoKey`` on a
missing key). The sheet-generator flow and the flag memory run against
tmp_path with a mocked ``generate_text``.
"""

import base64
import io
import json
import urllib.error
from pathlib import Path

import pytest

from painter import ai
from painter.config import (
    AI_MAX_QUESTIONS,
    GEMINI_API_BASE,
    GEMINI_IMAGE_MODEL,
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


def image_response(png_bytes: bytes, text: str | None = None) -> dict:
    """A generateContent body carrying an ``inlineData`` image part —
    optionally preceded by a caption/text part, since a real image-gen
    answer often carries both (only the inlineData part is the picture,
    ``_response_image`` skips the rest)."""
    parts = []
    if text is not None:
        parts.append({"text": text})
    parts.append({
        "inlineData": {
            "mimeType": "image/png",
            "data": base64.b64encode(png_bytes).decode("ascii"),
        }
    })
    return {
        "candidates": [
            {"content": {"parts": parts}, "finishReason": "STOP"}
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


# --- transient-error retry (owner 2026-07-21) --------------------------


def http_error(code, message="boom", retry_delay=None):
    """An HTTPError whose JSON body carries error.message (+ an optional
    RetryInfo.retryDelay), read ONCE by the client (single-read fp)."""
    err = {"message": message}
    if retry_delay is not None:
        err["details"] = [{
            "@type": "type.googleapis.com/google.rpc.RetryInfo",
            "retryDelay": retry_delay,
        }]
    body = json.dumps({"error": err}).encode()
    return urllib.error.HTTPError(
        "http://x", code, message, None, io.BytesIO(body)
    )


def urlopen_sequence(monkeypatch, *outcomes):
    """Each ``_urlopen`` call yields the next outcome: a dict → a
    FakeResponse, an Exception → raised. Returns the recorded call list
    so a test can assert how many ATTEMPTS the retry loop made."""
    calls: list = []
    it = iter(outcomes)

    def fake(req, timeout):
        calls.append((req, timeout))
        outcome = next(it)
        if isinstance(outcome, Exception):
            raise outcome
        return FakeResponse(outcome)

    monkeypatch.setattr(ai, "_urlopen", fake)
    return calls


@pytest.fixture
def backoff_sleeps(monkeypatch):
    """Record the retry BACKOFF sleeps instead of really waiting. The
    autouse fixture zeroes the free-tier pace, so every recorded sleep
    is a retry backoff (``_pace`` never sleeps here)."""
    sleeps: list[float] = []
    monkeypatch.setattr(ai.time, "sleep", sleeps.append)
    return sleeps


def test_transient_503_retries_then_recovers(monkeypatch, backoff_sleeps):
    from painter.config import AI_RETRY_BACKOFF_S

    calls = urlopen_sequence(
        monkeypatch,
        http_error(503, "The model is overloaded, try again later."),
        text_response("recovered"),
    )
    assert ai.generate_text("p", key="k") == "recovered"
    assert len(calls) == 2                       # exactly one retry
    assert backoff_sleeps == [AI_RETRY_BACKOFF_S]  # the fixed 503 backoff


def test_permanent_400_raises_immediately(monkeypatch, backoff_sleeps):
    calls = urlopen_sequence(monkeypatch, http_error(400, "API key not valid"))
    with pytest.raises(ai.AiError) as excinfo:
        ai.generate_text("p", key="bad")
    assert excinfo.value.status == 400           # the code is on the AiError
    assert len(calls) == 1                        # no retry on a permanent error
    assert backoff_sleeps == []


def test_429_honours_the_servers_retry_delay(monkeypatch, backoff_sleeps):
    calls = urlopen_sequence(
        monkeypatch,
        http_error(429, "Rate limit. Please retry in 4s.", retry_delay="4s"),
        text_response("ok"),
    )
    assert ai.generate_text("p", key="k") == "ok"
    assert len(calls) == 2
    assert backoff_sleeps == [4.0]               # the server's own backoff


def test_429_retry_delay_is_capped(monkeypatch, backoff_sleeps):
    from painter.config import AI_RETRY_MAX_WAIT_S

    urlopen_sequence(
        monkeypatch,
        http_error(429, "slow down", retry_delay="999s"),
        text_response("ok"),
    )
    ai.generate_text("p", key="k")
    assert backoff_sleeps == [AI_RETRY_MAX_WAIT_S]  # never longer than the cap


def test_transient_retries_exhaust_and_raise(monkeypatch, backoff_sleeps):
    from painter.config import AI_RETRY_MAX

    calls = urlopen_sequence(
        monkeypatch,
        *[http_error(503, "overloaded") for _ in range(AI_RETRY_MAX)],
    )
    with pytest.raises(ai.AiError) as excinfo:
        ai.generate_text("p", key="k")
    assert excinfo.value.status == 503
    assert len(calls) == AI_RETRY_MAX             # every attempt was made
    assert len(backoff_sleeps) == AI_RETRY_MAX - 1  # a backoff between each


def test_check_image_retries_transient_too(monkeypatch, backoff_sleeps, tmp_path):
    """The retry wraps the shared ``_call``, so the vision path recovers
    identically — this is the delilah/herod 503 skip fix."""
    img = tmp_path / "plate.png"
    img.write_bytes(PNG_1PX)
    urlopen_sequence(
        monkeypatch, http_error(503, "high demand"), text_response("OK")
    )
    assert ai.check_image(img, "find defects", key="k") == "OK"
    assert len(backoff_sleeps) == 1


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


# --- API image generation (owner 2026-07-21, GUI rework Phase 18) ------

# the EXACT 429 body captured against the owner's key on
# GEMINI_IMAGE_MODEL, 2026-07-21 — carries BOTH the free-tier-zero
# signal ("free_tier" + "limit: 0", "check your plan and billing
# details") AND a "Please retry in Xs" hint. The hint is the TRAP:
# classification must key on the free-tier-zero signal, never the hint.
PAID_QUOTA_MESSAGE = (
    "You exceeded your current quota, please check your plan and"
    " billing details. For more information on this error, head to:"
    " https://ai.google.dev/gemini-api/docs/rate-limits."
    " * Quota exceeded for metric:"
    " generativelanguage.googleapis.com/generate_content_free_tier_input_token_count,"
    " limit: 0, model: gemini-2.5-flash-preview-image"
    " * Quota exceeded for metric:"
    " generativelanguage.googleapis.com/generate_content_free_tier_requests,"
    " limit: 0, model: gemini-2.5-flash-preview-image"
    " Please retry in 15.776751513s."
)


def test_generate_image_returns_decoded_bytes(monkeypatch):
    requests = capture_call(
        monkeypatch, image_response(PNG_1PX, text="a caption")
    )
    result = ai.generate_image("a stained-glass rondel", key="k")
    assert result == PNG_1PX
    (req, _timeout), = requests
    assert req.full_url == (
        f"{GEMINI_API_BASE}/models/{GEMINI_IMAGE_MODEL}:generateContent"
    )
    body = json.loads(req.data)
    assert body["contents"][0]["parts"][0]["text"] == "a stained-glass rondel"
    assert "systemInstruction" not in body
    assert body["generationConfig"]["responseModalities"] == ["TEXT", "IMAGE"]


def test_edit_image_embeds_the_source_image(monkeypatch, tmp_path):
    img = tmp_path / "plate.png"
    img.write_bytes(PNG_1PX)
    requests = capture_call(monkeypatch, image_response(PNG_1PX))
    result = ai.edit_image(img, "make the frame gold", key="k")
    assert result == PNG_1PX
    req = requests[0][0]
    assert req.full_url == (
        f"{GEMINI_API_BASE}/models/{GEMINI_IMAGE_MODEL}:generateContent"
    )
    body = json.loads(req.data)
    parts = body["contents"][0]["parts"]
    assert parts[0]["text"] == "make the frame gold"
    inline = parts[1]["inlineData"]
    assert inline["mimeType"] == "image/png"
    assert base64.b64decode(inline["data"]) == PNG_1PX
    assert body["generationConfig"]["responseModalities"] == ["TEXT", "IMAGE"]


def test_edit_image_refuses_a_non_image_suffix(tmp_path):
    with pytest.raises(ai.AiError, match="unsupported image type"):
        ai.edit_image(tmp_path / "notes.txt", "x", key="k")


def test_response_image_raises_when_no_inlinedata_part(monkeypatch):
    capture_call(monkeypatch, text_response("just words, no picture"))
    with pytest.raises(ai.AiError, match="no image part"):
        ai.generate_image("p", key="k")


def test_paid_quota_429_raises_PaidFeatureRequired_immediately_without_retry(
    monkeypatch, backoff_sleeps
):
    """The owner's captured body ALSO names 'Please retry in 15.77...s'
    — the trap. Classification keys on the free-tier-zero signal, not
    that hint, so this raises on attempt ONE with zero sleeps/retries."""
    calls = urlopen_sequence(
        monkeypatch,
        http_error(429, PAID_QUOTA_MESSAGE, retry_delay="15.776751513s"),
    )
    with pytest.raises(ai.PaidFeatureRequired) as excinfo:
        ai.generate_image("p", key="k")
    assert excinfo.value.status == 429
    assert len(calls) == 1        # NO retry despite the "retry in Xs" hint
    assert backoff_sleeps == []   # never slept/backed off


def test_transient_429_without_free_tier_zero_still_retries(
    monkeypatch, backoff_sleeps
):
    """A NORMAL rate-limit 429 (no free-tier-zero signal) on the SAME
    image path still retries exactly like text/vision — only the
    free-tier-exhausted body short-circuits."""
    calls = urlopen_sequence(
        monkeypatch,
        http_error(429, "Rate limit. Please retry in 4s.", retry_delay="4s"),
        image_response(PNG_1PX),
    )
    result = ai.generate_image("p", key="k")
    assert result == PNG_1PX
    assert len(calls) == 2
    assert backoff_sleeps == [4.0]


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


# --- build_fix_prompt (GUI rework Phase 20 — the Fixer AI) --------------


def test_build_fix_prompt_with_defects_lists_each_as_a_bullet():
    prompt = ai.build_fix_prompt(
        ["subject cropped at the shoulder", "stray line near the halo"],
    )
    assert "- subject cropped at the shoulder" in prompt
    assert "- stray line near the halo" in prompt


def test_build_fix_prompt_empty_defects_is_never_blank():
    """A caller that (against the gate) calls this with no defects still
    gets a SENSIBLE, non-empty instruction — edit_image/submit_fix
    always need SOME text; this function stays honest about ANY input
    regardless of whether an upstream gate held (root Rule #1)."""
    prompt = ai.build_fix_prompt([])
    assert prompt.strip()
    assert "no specific defect" in prompt.lower()


def test_build_fix_prompt_appends_raw_verbatim_when_given():
    raw = "DEFECTS:\n- the halo is off-centre to the left"
    prompt = ai.build_fix_prompt(["halo off-centre"], raw)
    assert "halo off-centre" in prompt          # the parsed bullet
    assert "off-centre to the left" in prompt   # the verbatim raw, too
    assert prompt.index("halo off-centre") < prompt.index("off-centre to the left")


def test_build_fix_prompt_omits_raw_section_when_raw_is_none_or_blank():
    base = ai.build_fix_prompt(["x"])
    assert base == ai.build_fix_prompt(["x"], None)
    assert base == ai.build_fix_prompt(["x"], "   ")  # whitespace-only


def test_build_fix_prompt_is_pure_and_deterministic():
    a = ai.build_fix_prompt(["x", "y"], "raw text")
    b = ai.build_fix_prompt(["x", "y"], "raw text")
    assert a == b


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
        out, img, ["subject cut"], "gemini-test",
        "DEFECTS:\n- subject cut", log=lambda _l: None,
    )
    assert key == "emblem/gemini/mood/Glory.png"
    flags = ai.load_flags(out)
    entry = flags[key]
    assert entry["defects"] == ["subject cut"]
    assert entry["raw"] == "DEFECTS:\n- subject cut"  # verbatim, persisted
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
    ai.record_flag(out, a, ["x"], "m", "DEFECTS:\n- x", log=lambda _l: None)
    ai.record_flag(out, b, ["y"], "m", "DEFECTS:\n- y", log=lambda _l: None)
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
        ai.record_flag(out, img, ["d"], "m", "DEFECTS:\n- d", log=lambda _l: None)
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


# --- the per-image checker orchestrator (owner 2026-07-21) -------------


def test_check_one_image_flags_records_raw_and_times(tmp_path, monkeypatch):
    out = tmp_path / "out"
    img = _make_image(out, "emblem/gemini/mood/Glory.png")
    clock = [100.0]
    monkeypatch.setattr(ai.time, "monotonic", lambda: clock[0])
    raw = "DEFECTS:\n- subject cut at the left edge"

    def fake_check(src, instructions, *, model=None, log=None):
        clock[0] += 0.5           # the "call" takes half a second
        return raw

    result = ai.check_one_image(
        img, out, "instr", check=fake_check, log=lambda _l: None
    )
    assert result["kind"] == "flagged"
    assert result["rel"] == "emblem/gemini/mood/Glory.png"
    assert result["defects"] == ["subject cut at the left edge"]
    assert result["raw"] == raw
    assert result["time"] == 0.5  # timing is plumbed, not a hardcoded 0
    # the raw is PERSISTED alongside the defects for later inspection
    assert ai.load_flags(out)["emblem/gemini/mood/Glory.png"]["raw"] == raw


def test_check_one_image_ok_clears_stale_flag_and_carries_raw(tmp_path):
    out = tmp_path / "out"
    img = _make_image(out, "emblem/gemini/mood/Clean.png")
    # a pre-existing flag a now-clean re-check must drop
    ai.record_flag(out, img, ["old"], "m", "DEFECTS:\n- old", log=lambda _l: None)
    result = ai.check_one_image(
        img, out, "instr", check=lambda *a, **k: "OK", log=lambda _l: None
    )
    assert result["kind"] == "ok"
    assert result["defects"] == []
    assert result["raw"] == "OK"
    assert ai.load_flags(out) == {}   # the stale flag was cleared


def test_check_one_image_error_is_caught_never_fatal(tmp_path):
    out = tmp_path / "out"
    img = _make_image(out, "emblem/gemini/x.png")

    def boom(*a, **k):
        raise ai.AiError("Gemini API HTTP 503 on gemini: high demand")

    result = ai.check_one_image(
        img, out, "instr", check=boom, log=lambda _l: None
    )
    assert result["kind"] == "error"  # returned, never raised (tool-job rule)
    assert "503" in result["raw"]     # the error text, shown in the viewer
    assert ai.load_flags(out) == {}   # nothing recorded on an error


def test_check_pairing_maps_each_response_to_the_right_image(tmp_path):
    """FIX 5: over a batch, each image's flag / raw / viewer-file maps to
    THAT exact image — no off-by-one — including an image OUTSIDE the out
    base (an absolute key that ``flag_file`` still round-trips, the run
    that checked DOMY Watch while the out base was Downloads)."""
    out = tmp_path / "out"
    serpent = _make_image(out, "emblem/gemini/mood/Serpent.png")
    glory = _make_image(out, "emblem/gemini/mood/Glory.png")
    herod = tmp_path / "DOMY" / "assets" / "Herod.png"
    herod.parent.mkdir(parents=True)
    herod.write_bytes(PNG_1PX)
    images = [serpent, glory, herod]

    # a DISTINCT response per image, keyed by the file stem
    responses = {
        "Serpent": "DEFECTS:\n- frame cut on the left",
        "Glory": "OK",
        "Herod": "DEFECTS:\n- watermark bottom-right",
    }

    def fake_check(src, instructions, *, model=None, log=None):
        return responses[Path(src).stem]

    results = {
        src: ai.check_one_image(
            src, out, "instr", check=fake_check, log=lambda _l: None
        )
        for src in images
    }
    for src, result in results.items():
        # the raw is THIS image's response, not a neighbour's
        assert result["raw"] == responses[src.stem]
        # the flag key round-trips (flag_file — the SAME function the
        # panel's viewer uses) back to THIS exact file
        assert ai.flag_file(result["rel"], out).resolve() == src.resolve()

    # the persisted flags carry each image's OWN defects; the OK image none
    flags = ai.load_flags(out)
    assert flags[results[serpent]["rel"]]["defects"] == ["frame cut on the left"]
    assert flags[results[herod]["rel"]]["defects"] == ["watermark bottom-right"]
    assert results[glory]["rel"] not in flags
    # the outside image keyed by an ABSOLUTE path (never matches a queue)
    assert Path(results[herod]["rel"]).is_absolute()


def test_ai_check_doc_md_shows_defects_and_verbatim_raw():
    """FIX 3: the viewer markdown carries the name + path, the parsed
    defects AND the verbatim raw response — and an OK row is viewable
    too (its raw shows, no defect section)."""
    import gui

    md = gui.ai_check_doc_md(
        "emblem/gemini/mood/Glory.png",
        ["subject cut left"],
        "DEFECTS:\n- subject cut left",
    )
    assert "Glory.png" in md                        # the image name heading
    assert "`emblem/gemini/mood/Glory.png`" in md   # the full path
    assert "- subject cut left" in md               # the parsed defect bullet
    assert "**Full AI response:**" in md            # the raw section
    assert "DEFECTS:\n- subject cut left" in md      # the verbatim response

    ok = gui.ai_check_doc_md("emblem/gemini/mood/Clean.png", None, "OK")
    assert "AI-flagged defects" not in ok           # nothing parsed
    assert "**Full AI response:**" in ok and "OK" in ok


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
