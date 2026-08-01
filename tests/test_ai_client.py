"""Offline tests for the Gemini REST client — NO live API.

Split from the former ``test_ai.py`` god-file (root Rule #20, second
round — the source split into ``painter/ai/`` 2026-07-30, this test
module follows it 1:1: everything ``painter/ai/client.py`` exports).

The HTTP layer is one monkeypatchable alias (``painter.ai.client._urlopen``);
every test feeds canned response dicts through it and asserts the REQUEST
the client built (url, headers, payload) and the loud failure taxonomy
(``AiError`` on HTTP/refusal/malformed, ``NoKey`` on a missing key,
``PaidFeatureRequired`` on a free-tier-exhausted quota body).
"""

import base64
import io
import json
import urllib.error

import pytest

from painter import ai
from painter.config import (
    GEMINI_API_BASE,
    GEMINI_IMAGE_MODEL,
    GEMINI_TEXT_MODEL,
    GEMINI_VISION_MODEL,
)
from painter.config import AI_CHECK_PROMPT_MATCH

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
    monkeypatch.setattr(ai.client, "AI_CALL_PAUSE_S", 0.0)
    monkeypatch.setattr(ai.client, "_last_call_t", None)
    monkeypatch.setattr(ai.client, "load_settings", lambda: {})


def capture_call(monkeypatch, response: dict) -> list:
    """Route ``_urlopen`` into a recorder; returns the request list."""
    requests: list = []

    def fake_urlopen(req, timeout):
        requests.append((req, timeout))
        return FakeResponse(response)

    monkeypatch.setattr(ai.client, "_urlopen", fake_urlopen)
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


def test_check_image_with_prompt_embeds_both_instruction_blocks(
    monkeypatch, tmp_path,
):
    """F6 (REWORK.md): the ``prompt`` kwarg APPENDS
    AI_CHECK_PROMPT_MATCH (formatted with the prompt text) after the
    caller's own instructions — never replaces them — so a single
    request carries the banal-defects check AND the prompt-match
    clause AND the prompt itself, verbatim."""
    img = tmp_path / "plate.png"
    img.write_bytes(PNG_1PX)
    requests = capture_call(monkeypatch, text_response("OK"))
    ai.check_image(
        img, "find defects", key="k",
        prompt="a round gold medallion, flat, no tilt",
    )
    parts = json.loads(requests[0][0].data)["contents"][0]["parts"]
    text = parts[0]["text"]
    assert "find defects" in text
    assert AI_CHECK_PROMPT_MATCH.format(
        prompt="a round gold medallion, flat, no tilt"
    ) in text
    # the instructions block precedes the prompt-match block
    assert text.index("find defects") < text.index("ADDITIONALLY")


def test_check_image_without_prompt_sends_instructions_unchanged(
    monkeypatch, tmp_path,
):
    """The default (``prompt=None``) path is BYTE-IDENTICAL to before
    F6 — no prompt-match clause, no regression for the quality-only
    checker."""
    img = tmp_path / "plate.png"
    img.write_bytes(PNG_1PX)
    requests = capture_call(monkeypatch, text_response("OK"))
    ai.check_image(img, "find defects", key="k")
    parts = json.loads(requests[0][0].data)["contents"][0]["parts"]
    assert parts[0]["text"] == "find defects"


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

    monkeypatch.setattr(ai.client, "_urlopen", fake_urlopen)
    with pytest.raises(ai.AiError, match="HTTP 400.*API key not valid"):
        ai.generate_text("p", key="bad")


def test_network_error_is_loud(monkeypatch):
    def fake_urlopen(req, timeout):
        raise urllib.error.URLError("no route to host")

    monkeypatch.setattr(ai.client, "_urlopen", fake_urlopen)
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

    monkeypatch.setattr(ai.client, "_urlopen", fake)
    return calls


@pytest.fixture
def backoff_sleeps(monkeypatch):
    """Record the retry BACKOFF sleeps instead of really waiting. The
    autouse fixture zeroes the free-tier pace, so every recorded sleep
    is a retry backoff (``_pace`` never sleeps here)."""
    sleeps: list[float] = []
    monkeypatch.setattr(ai.client.time, "sleep", sleeps.append)
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
    monkeypatch.setattr(ai.client, "load_settings", lambda: {})
    with pytest.raises(ai.NoKey):
        ai.api_key()
    monkeypatch.setattr(
        ai.client, "load_settings", lambda: {"gemini_api_key": "   "}
    )
    with pytest.raises(ai.NoKey):
        ai.api_key()


def test_saved_key_is_read_from_settings(monkeypatch):
    monkeypatch.setattr(
        ai.client, "load_settings", lambda: {"gemini_api_key": " abc "}
    )
    assert ai.api_key() == "abc"


def test_generate_without_key_raises_nokey_before_any_http(monkeypatch):
    called = []
    monkeypatch.setattr(
        ai.client, "_urlopen", lambda *a, **k: called.append(1)
    )
    with pytest.raises(ai.NoKey):
        ai.generate_text("p")
    assert called == []  # NoKey fires BEFORE any network traffic


def test_pacing_sleeps_between_calls(monkeypatch):
    monkeypatch.setattr(ai.client, "AI_CALL_PAUSE_S", 60.0)
    sleeps: list[float] = []
    monkeypatch.setattr(ai.client.time, "sleep", sleeps.append)
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


# --- generate_image's optional reference image (F5, owner D3) ----------


def test_generate_image_with_image_path_attaches_the_reference_before_the_prompt(
    monkeypatch, tmp_path,
):
    ref = tmp_path / "photo.png"
    ref.write_bytes(PNG_1PX)
    requests = capture_call(monkeypatch, image_response(PNG_1PX))
    result = ai.generate_image(
        "put this figure into the scene", image_path=ref, key="k",
    )
    assert result == PNG_1PX
    req = requests[0][0]
    assert req.full_url == (
        f"{GEMINI_API_BASE}/models/{GEMINI_IMAGE_MODEL}:generateContent"
    )
    body = json.loads(req.data)
    parts = body["contents"][0]["parts"]
    # the IMAGE comes FIRST, the prompt text SECOND — the opposite order
    # of _payload_image (edit_image/check_image, text-first) — mirrors
    # the website flow's own submit_with_image (attach before send)
    inline = parts[0]["inlineData"]
    assert inline["mimeType"] == "image/png"
    assert base64.b64decode(inline["data"]) == PNG_1PX
    assert parts[1]["text"] == "put this figure into the scene"
    assert body["generationConfig"]["responseModalities"] == ["TEXT", "IMAGE"]


def test_generate_image_without_image_path_stays_text_only(monkeypatch):
    """No ``image_path`` -> the plain text-only payload, exactly as
    before F5 (regression guard against the new parameter changing the
    default path): exactly ONE part, no ``inlineData``."""
    requests = capture_call(monkeypatch, image_response(PNG_1PX))
    ai.generate_image("a stained-glass rondel", key="k")
    parts = json.loads(requests[0][0].data)["contents"][0]["parts"]
    assert parts == [{"text": "a stained-glass rondel"}]


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


# --- model discovery + purpose-based recommendation (F5) ---------------


def two_page_models_response() -> tuple[dict, dict]:
    """Page 1 carries a ``nextPageToken``; page 2 does not — the shape
    ``list_models`` must follow to the end and stop at."""
    page1 = {
        "models": [
            {
                "name": "models/gemini-2.5-flash-image",
                "supportedGenerationMethods": ["generateContent"],
                "displayName": "Gemini 2.5 Flash Image",
            },
            {
                "name": "models/gemini-flash-latest",
                "supportedGenerationMethods": ["generateContent"],
                "displayName": "Gemini Flash",
            },
        ],
        "nextPageToken": "PAGE2TOKEN",
    }
    page2 = {
        "models": [
            {
                "name": "models/text-embedding-004",
                "supportedGenerationMethods": ["embedContent"],
                "displayName": "Embedding 004",
            },
        ],
    }
    return page1, page2


def test_list_models_follows_the_next_page_token(monkeypatch):
    page1, page2 = two_page_models_response()
    calls = urlopen_sequence(monkeypatch, page1, page2)
    models = ai.list_models(key="k")
    assert len(calls) == 2
    # page 1 has no pageToken; page 2's URL carries the one page 1 named
    assert "pageToken" not in calls[0][0].full_url
    assert "PAGE2TOKEN" in calls[1][0].full_url
    # the "models/" prefix is stripped; methods/display carried through
    assert models == [
        {
            "name": "gemini-2.5-flash-image",
            "methods": ("generateContent",),
            "display": "Gemini 2.5 Flash Image",
        },
        {
            "name": "gemini-flash-latest",
            "methods": ("generateContent",),
            "display": "Gemini Flash",
        },
        {
            "name": "text-embedding-004",
            "methods": ("embedContent",),
            "display": "Embedding 004",
        },
    ]
    # the key rides in the SAME auth header as every other call
    assert calls[0][0].get_header("X-goog-api-key") == "k"


def test_list_models_without_key_raises_nokey_before_any_http(monkeypatch):
    called = []
    monkeypatch.setattr(ai.client, "_urlopen", lambda *a, **k: called.append(1))
    with pytest.raises(ai.NoKey):
        ai.list_models()
    assert called == []


def test_list_models_retries_transient_like_every_other_call(
    monkeypatch, backoff_sleeps,
):
    calls = urlopen_sequence(
        monkeypatch, http_error(503, "high demand"), {"models": []},
    )
    ai.list_models(key="k")
    assert len(calls) == 2
    assert len(backoff_sleeps) == 1


CAPABLE_FIXTURE = [
    {"name": "gemini-2.5-flash-image", "methods": ("generateContent",), "display": ""},
    {"name": "gemini-3.1-flash-image", "methods": ("generateContent",), "display": ""},
    {"name": "gemini-flash-latest", "methods": ("generateContent",), "display": ""},
    {"name": "gemini-3.1-pro", "methods": ("generateContent",), "display": ""},
    {"name": "text-embedding-004", "methods": ("embedContent",), "display": ""},
    {"name": "gemini-tts-preview", "methods": ("generateContent",), "display": ""},
]


def test_capable_models_filters_image_purpose_by_name_or_method():
    capable = ai.capable_models(CAPABLE_FIXTURE, "image")
    assert {m["name"] for m in capable} == {
        "gemini-2.5-flash-image", "gemini-3.1-flash-image",
    }
    # a model whose METHOD (not name) names image output also counts
    method_only = [
        {"name": "some-model", "methods": ("generateImage",), "display": ""},
    ]
    assert ai.capable_models(method_only, "image") == method_only


def test_capable_models_filters_vision_and_text_purposes_identically():
    for purpose in ("vision", "text"):
        capable = ai.capable_models(CAPABLE_FIXTURE, purpose)
        names = {m["name"] for m in capable}
        # excludes image-generation, embedding AND tts-named models
        assert names == {"gemini-flash-latest", "gemini-3.1-pro"}


def test_capable_models_unknown_purpose_is_loud():
    with pytest.raises(ValueError, match="unknown model purpose"):
        ai.capable_models(CAPABLE_FIXTURE, "audio")


def test_recommend_model_picks_the_best_ranked_capable_model():
    # image: "gemini-3.1-flash-image" outranks "gemini-2.5-flash-image"
    # in MODEL_PURPOSE_RANKING (best-first)
    assert ai.recommend_model(CAPABLE_FIXTURE, "image") == "gemini-3.1-flash-image"
    # vision: "gemini-3.1-pro" outranks "gemini-flash-latest"
    assert ai.recommend_model(CAPABLE_FIXTURE, "vision") == "gemini-3.1-pro"
    assert ai.recommend_model(CAPABLE_FIXTURE, "text") == "gemini-3.1-pro"


def test_recommend_model_falls_back_to_newest_by_name_when_ranking_matches_nothing():
    unranked = [
        {"name": "zz-future-model", "methods": ("generateContent",), "display": ""},
        {"name": "aa-older-model", "methods": ("generateContent",), "display": ""},
    ]
    # neither name matches any MODEL_PURPOSE_RANKING["text"] substring —
    # falls back to the NEWEST by name, sorted descending
    assert ai.recommend_model(unranked, "text") == "zz-future-model"


def test_recommend_model_none_when_nothing_is_capable():
    only_embeddings = [
        {"name": "text-embedding-004", "methods": ("embedContent",), "display": ""},
    ]
    assert ai.recommend_model(only_embeddings, "image") is None
    assert ai.recommend_model(only_embeddings, "vision") is None
    assert ai.recommend_model([], "text") is None


def test_model_for_falls_back_to_the_hardcoded_constant_when_no_override(
    monkeypatch,
):
    monkeypatch.setattr(ai.client, "load_settings", lambda: {})
    assert ai.model_for("image") == GEMINI_IMAGE_MODEL
    assert ai.model_for("vision") == GEMINI_VISION_MODEL
    assert ai.model_for("text") == GEMINI_TEXT_MODEL


def test_model_for_reads_the_stored_override(monkeypatch):
    from painter.config import MODELS_SETTING

    monkeypatch.setattr(
        ai.client, "load_settings",
        lambda: {MODELS_SETTING: {"image": "gemini-3.1-flash-image"}},
    )
    assert ai.model_for("image") == "gemini-3.1-flash-image"
    # a purpose with NO stored override still falls back
    assert ai.model_for("vision") == GEMINI_VISION_MODEL


def test_model_for_blank_override_falls_back_like_a_missing_one(monkeypatch):
    from painter.config import MODELS_SETTING

    monkeypatch.setattr(
        ai.client, "load_settings",
        lambda: {MODELS_SETTING: {"text": "   "}},
    )
    assert ai.model_for("text") == GEMINI_TEXT_MODEL


def test_model_for_unknown_purpose_is_loud(monkeypatch):
    monkeypatch.setattr(ai.client, "load_settings", lambda: {})
    with pytest.raises(ValueError, match="unknown model purpose"):
        ai.model_for("audio")


def test_generate_text_routes_the_default_model_through_model_for(monkeypatch):
    """A caller that never passes ``model=`` gets settings.json's
    override when one is stored — proving the internal call sites
    really route through ``model_for`` (Rule #6), not just the
    function existing in isolation."""
    from painter.config import MODELS_SETTING

    monkeypatch.setattr(
        ai.client, "load_settings",
        lambda: {MODELS_SETTING: {"text": "gemini-3.1-pro"}},
    )
    requests = capture_call(monkeypatch, text_response("hi"))
    ai.generate_text("p", key="k")
    assert requests[0][0].full_url == (
        f"{GEMINI_API_BASE}/models/gemini-3.1-pro:generateContent"
    )
