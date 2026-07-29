"""Gemini API client + the AI features' engine (owner 2026-07-20).

Three cohesive parts, all offline-testable with a mocked HTTP layer
(the tests monkeypatch ``_urlopen`` — no SDK, no live calls):

* the MINIMAL REST CLIENT over urllib against the AI Studio key:
  ``generate_text``/``check_image`` (free tier) and, GUI rework Phase
  18, ``generate_image``/``edit_image`` (the PAID image model) all
  POST ``v1beta models/<model>:generateContent`` with the key in the
  ``x-goog-api-key`` header. Every HTTP error, refusal/block and
  malformed response raises a loud ``AiError`` (Rule #1); a missing
  key raises the specific ``NoKey`` so the GUI can open its guided
  wizard, and a 429 carrying the free-tier-EXHAUSTED signal raises the
  specific ``PaidFeatureRequired`` instead of retrying (the owner's
  key has ZERO free quota for the image model today). Consecutive
  calls are PACED ``AI_CALL_PAUSE_S`` apart (the free tier is ~10
  requests/minute). ``generate_image`` optionally attaches a
  REFERENCE image (F5, owner D3) as an ``inlineData`` part BEFORE the
  prompt text.
* MODEL DISCOVERY + per-purpose recommendation (F5, owner D1/D2):
  ``list_models`` GETs the ListModels endpoint (paged);
  ``capable_models``/``recommend_model`` filter and rank the result
  per PURPOSE ("image"/"vision"/"text") against
  ``config.MODEL_PURPOSE_RANKING``; ``model_for`` resolves the model
  actually used by every call above — settings.json's ``"models"``
  per-purpose override when set, else the matching hardcoded
  ``GEMINI_*_MODEL`` constant (now a FALLBACK only).
* the SHEET-GENERATOR flow helpers (owner's #2): parse the model's
  numbered clarifying questions, build the two calls from the sheet
  contract (instructions.md), validate a produced ``.md`` with the
  REAL sheet parser and drive ONE automatic repair round, then save
  the clean sheet under ``sheets/`` with a slugged filename.
* the SHEET-GENERATOR flow helpers (owner's #2): parse the model's
  numbered clarifying questions, build the two calls from the sheet
  contract (instructions.md), validate a produced ``.md`` with the
  REAL sheet parser and drive ONE automatic repair round, then save
  the clean sheet under ``sheets/`` with a slugged filename.
* the FLAG MEMORY (owner's #3): ``<out>/_state/ai_flags.json`` keyed
  by the image's path RELATIVE to the out base; each entry carries the
  defects, the check time, the model and the file's mtime — a changed
  mtime (the image was REGENERATED) invalidates the flag on the next
  prune. ``drop_and_site_for`` reverses ``dest_for`` so a flagged
  image can be re-sent to the SITE that generated it.
"""

from __future__ import annotations

import base64
import json
import re
import time
import urllib.error
import urllib.request
from datetime import datetime
from pathlib import Path, PurePosixPath

from painter.config import (
    AI_CALL_PAUSE_S,
    AI_CHECK_PROMPT_MATCH,
    AI_FLAGS_FILENAME,
    AI_FIX_NOTE,
    AI_FIX_PROMPT_NO_DEFECTS,
    AI_FIX_PROMPT_RAW_SUFFIX,
    AI_FIX_PROMPT_WITH_DEFECTS,
    AI_IMAGE_QUOTA_MARKERS,
    AI_MAX_QUESTIONS,
    AI_QUESTIONS_SYSTEM,
    AI_REPAIR_PROMPT,
    AI_RETRY_BACKOFF_S,
    AI_RETRY_MAX,
    AI_RETRY_MAX_WAIT_S,
    AI_SHEET_REQUEST,
    AI_SHEET_SYSTEM,
    AI_TIMEOUT_S,
    AI_TRANSIENT_STATUS,
    GEMINI_API_BASE,
    GEMINI_IMAGE_MODEL,
    GEMINI_KEY_SETTING,
    GEMINI_TEXT_MODEL,
    GEMINI_VISION_MODEL,
    MODEL_PURPOSE_RANKING,
    MODELS_SETTING,
    PROJECT_ROOT,
    SITES,
    STATE_DIRNAME,
)
from painter.settings import load_settings
from painter.sheet_parser import SheetError, parse_sheet


class AiError(Exception):
    """A Gemini API call failed — HTTP error, refusal/block or a
    malformed response. Loud (Rule #1); the CALLER decides whether one
    failure skips an image or stops a flow — it is never swallowed.

    ``status`` is the numeric HTTP code when the failure was an HTTP
    error (None for a refusal/block/malformed/network failure) — the
    retry logic and callers key on it instead of parsing the message."""

    status: int | None = None


class NoKey(AiError):
    """settings.json holds no Gemini API key — the GUI reacts by
    opening the guided key wizard (the documented auto-open path)."""


class PaidFeatureRequired(AiError):
    """A 429 carried the free-tier-EXHAUSTED signal
    (``_is_paid_quota_error`` / ``AI_IMAGE_QUOTA_MARKERS``) — the
    account has ZERO free quota for the requested model (GUI rework
    Phase 18: verified live against the owner's key on
    ``GEMINI_IMAGE_MODEL``, 2026-07-21). PERMANENT: raised on the
    FIRST attempt inside ``_call_raw``, never retried like an ordinary
    rate-limit 429 — no wait ever fixes a zero quota, the account
    needs billing enabled on the AI Studio project. ``status`` is
    always 429 (set by the raise site, inherited from ``AiError``)."""


# ---------------------------------------------------------------------
# The REST client
# ---------------------------------------------------------------------

# module alias so tests can monkeypatch the HTTP layer in ONE place
_urlopen = urllib.request.urlopen

# image suffix -> request mime type (the checker feeds saved outputs,
# and GUI rework Phase 18's edit_image feeds the source to be edited)
_MIME = {
    ".png": "image/png",
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".webp": "image/webp",
}


def _mime_for(image_path: Path, *, purpose: str) -> str:
    """The MIME type for one image FILE, by suffix (``_MIME``); a loud
    ``AiError`` naming ``purpose`` ("the checker" / "editing") when the
    suffix is unsupported. Shared by every call that embeds a saved
    image as inline base64 — ``check_image`` and ``edit_image`` (Rule
    #5: one lookup+raise, not two copies of the same four lines)."""
    mime = _MIME.get(image_path.suffix.lower())
    if mime is None:
        raise AiError(
            f"{image_path.name}: unsupported image type for {purpose}"
        )
    return mime


_last_call_t: float | None = None  # monotonic time of the last API call


def api_key() -> str:
    """The Gemini key from settings.json; ``NoKey`` when absent/blank."""
    key = str(load_settings().get(GEMINI_KEY_SETTING, "") or "").strip()
    if not key:
        raise NoKey(
            "no Gemini API key in settings.json — run the 'AI key…'"
            " wizard (a free key from aistudio.google.com)"
        )
    return key


def _pace() -> None:
    """Keep consecutive API calls ``AI_CALL_PAUSE_S`` apart (free-tier
    requests-per-minute); the FIRST call of a session never waits."""
    global _last_call_t
    if _last_call_t is not None:
        wait = _last_call_t + AI_CALL_PAUSE_S - time.monotonic()
        if wait > 0:
            time.sleep(wait)
    _last_call_t = time.monotonic()


def _payload_text(prompt: str, system: str | None) -> dict:
    payload: dict = {"contents": [{"parts": [{"text": prompt}]}]}
    if system:
        payload["systemInstruction"] = {"parts": [{"text": system}]}
    return payload


def _text_part(text: str) -> dict:
    return {"text": text}


def _inline_data_part(image_bytes: bytes, mime: str) -> dict:
    return {
        "inlineData": {
            "mimeType": mime,
            "data": base64.b64encode(image_bytes).decode("ascii"),
        }
    }


def _payload_image(image_bytes: bytes, mime: str, instructions: str) -> dict:
    """TEXT part first, then the image — the checker/``edit_image``
    convention (read the instructions, then look at the picture).
    Shares the per-part builders with ``_payload_reference_and_prompt``
    (Rule #5) but keeps its OWN part order; UNCHANGED by F5 (existing
    callers/tests keep this exact shape)."""
    return {
        "contents": [
            {"parts": [
                _text_part(instructions),
                _inline_data_part(image_bytes, mime),
            ]}
        ]
    }


def _payload_reference_and_prompt(
    image_bytes: bytes, mime: str, prompt: str
) -> dict:
    """``generate_image``'s OPTIONAL reference-image path (F5, owner
    D3): the IMAGE part comes FIRST, the prompt text SECOND — mirrors
    the website flow's own order (``driver.submit_with_image`` attaches
    the picture into the composer BEFORE the prompt text is typed and
    sent), unlike ``_payload_image`` above (text first, the checker/
    edit convention). Shares the per-part builders with it (Rule #5)."""
    return {
        "contents": [
            {"parts": [
                _inline_data_part(image_bytes, mime),
                _text_part(prompt),
            ]}
        ]
    }


# a "38s" / "37.9s" / "retry in 5s" seconds value the server names
_SECONDS_RE = re.compile(r"(\d+(?:\.\d+)?)\s*s\b")


def _seconds_from(text: str) -> float | None:
    """The first "<number>s" in ``text`` (a server-named backoff), or
    None — best-effort, used only to honour a 429's requested wait."""
    m = _SECONDS_RE.search(text)
    return float(m.group(1)) if m else None


def _http_error(exc: urllib.error.HTTPError) -> tuple[str, float | None]:
    """Parse a Gemini HTTPError body ONCE (the fp is single-read):
    the API's error message (or the plain HTTP reason) and, for a 429,
    the server's requested backoff in seconds — from
    ``error.details[].retryDelay`` ('38s') or, failing that, a
    "please retry in Xs" the message names; None when absent.
    Best-effort; the caller raises the loud AiError either way."""
    try:
        body = json.loads(exc.read())
    except Exception:
        return str(exc.reason), None
    err = body.get("error") or {}
    message = err.get("message") or str(exc.reason)
    retry_s = None
    for detail in err.get("details") or ():
        if isinstance(detail, dict) and detail.get("retryDelay"):
            retry_s = _seconds_from(str(detail["retryDelay"]))
            if retry_s is not None:
                break
    if retry_s is None:
        retry_s = _seconds_from(message)
    return message, retry_s


def _retry_wait(code: int, retry_s: float | None) -> float:
    """The backoff before the next attempt: a 429 honours the server's
    requested delay (capped at ``AI_RETRY_MAX_WAIT_S``); 503/500 use the
    fixed ``AI_RETRY_BACKOFF_S``."""
    if code == 429 and retry_s is not None:
        return min(retry_s, AI_RETRY_MAX_WAIT_S)
    return AI_RETRY_BACKOFF_S


def _is_paid_quota_error(status: int, message: str) -> bool:
    """True when a 429's message carries the free-tier-EXHAUSTED
    signal (``AI_IMAGE_QUOTA_MARKERS``) rather than an ordinary rate
    limit — PERMANENT, so ``_call_raw`` raises ``PaidFeatureRequired``
    immediately instead of retrying.

    Classifies on THESE substrings only — never the "retry in Xs" hint
    the SAME body also carries (the trap: that hint sits on both a
    genuinely transient rate-limit 429 and this permanent free-tier-
    zero one, so it cannot tell them apart). Only a 429 is ever
    checked — every other status is False, already handled by the
    existing transient/permanent status split. A 429 matching NEITHER
    marker group is AMBIGUOUS and defaults to False/transient (owner
    decision, Phase 18): retrying a permanent error wastes a few
    calls, but giving up on a genuinely transient one is worse."""
    if status != 429:
        return False
    lowered = message.lower()
    return any(
        all(marker in lowered for marker in group)
        for group in AI_IMAGE_QUOTA_MARKERS
    )


def _response_text(data: dict, model: str) -> str:
    """The first candidate's concatenated text parts.

    Tolerates the candidates/parts structure (empty candidates are
    skipped); LOUD on prompt blocks, non-STOP stops with no text, and
    any shape carrying no text at all.
    """
    if not isinstance(data, dict):
        raise AiError(f"{model}: malformed response (not a JSON object)")
    block = (data.get("promptFeedback") or {}).get("blockReason")
    if block:
        raise AiError(f"{model}: prompt blocked by the API ({block})")
    for cand in data.get("candidates") or ():
        if not isinstance(cand, dict):
            continue
        parts = (cand.get("content") or {}).get("parts") or ()
        text = "".join(
            p.get("text", "") for p in parts if isinstance(p, dict)
        )
        if text.strip():
            return text
        finish = cand.get("finishReason")
        if finish and finish != "STOP":
            raise AiError(
                f"{model}: generation stopped ({finish}) with no text"
            )
    raise AiError(
        f"{model}: response carries no text (keys: {sorted(data)})"
    )


def _response_image(data: dict, model: str) -> bytes:
    """The first ``inlineData`` (base64) part found across the
    response's candidates, decoded to bytes — the image-generation
    counterpart of ``_response_text``: tolerates the SAME candidates/
    parts shape (empty candidates skipped) but reads the IMAGE part
    instead of the text part (an image-gen answer often carries both a
    caption/refusal text part AND the inlineData part; only the latter
    is the picture). LOUD on a prompt block, a non-STOP stop with no
    image, or a response that carries no image part at all (Rule #1)
    — a text-only answer is not a valid result here."""
    if not isinstance(data, dict):
        raise AiError(f"{model}: malformed response (not a JSON object)")
    block = (data.get("promptFeedback") or {}).get("blockReason")
    if block:
        raise AiError(f"{model}: prompt blocked by the API ({block})")
    for cand in data.get("candidates") or ():
        if not isinstance(cand, dict):
            continue
        parts = (cand.get("content") or {}).get("parts") or ()
        for part in parts:
            if isinstance(part, dict):
                inline = part.get("inlineData")
                if inline and inline.get("data"):
                    return base64.b64decode(inline["data"])
        finish = cand.get("finishReason")
        if finish and finish != "STOP":
            raise AiError(
                f"{model}: generation stopped ({finish}) with no image"
            )
    raise AiError(
        f"{model}: response carries no image part (keys: {sorted(data)})"
    )


def _raise_http(model: str, exc: urllib.error.HTTPError, message: str) -> None:
    """Raise the loud ``AiError`` for an HTTP failure, carrying the
    numeric ``.status`` so callers key on the code, not the message."""
    err = AiError(f"Gemini API HTTP {exc.code} on {model}: {message}")
    err.status = exc.code
    raise err from exc


def _raise_paid_quota(
    model: str, exc: urllib.error.HTTPError, message: str
) -> None:
    """Raise the loud ``PaidFeatureRequired`` for a free-tier-exhausted
    429 — mirrors ``_raise_http`` (carries ``.status``) but as the
    PERMANENT paid-quota subtype instead of a plain ``AiError``."""
    err = PaidFeatureRequired(
        f"{model}: paid feature required — the free tier has zero"
        f" quota for this model ({message})"
    )
    err.status = exc.code
    raise err from exc


def _send_request(
    req: urllib.request.Request, label: str, *, log=print
) -> dict:
    """Drive an ALREADY-BUILT request through the retry/pace/HTTP SHELL
    shared by every caller (Rule #5, F5): ``_call_raw`` (POST
    generateContent, for ``generate_text``/``check_image``/
    ``generate_image``/``edit_image``) and ``list_models`` (GET
    models) both build their own request and hand it here instead of
    each carrying a near-identical copy of this loop. ``label`` names
    the call in every log/error line — a model name for a
    generateContent call, ``"models.list"`` for ``list_models``; this
    function has no opinion on the URL/method, only on the shared
    retry machinery.

    TRANSIENT API failures (``AI_TRANSIENT_STATUS`` — 503 high-demand,
    429 rate-limit, 500) are RETRIED up to ``AI_RETRY_MAX`` attempts,
    with a backoff between them (503/500 a fixed ``AI_RETRY_BACKOFF_S``;
    429 the server's own "retry in Xs", capped at ``AI_RETRY_MAX_WAIT_S``)
    — each retry is logged. PERMANENT failures (400/401/403/404: a bad
    request, bad key or unknown model) raise on the FIRST try.

    A 429 is checked FIRST for the free-tier-EXHAUSTED signal
    (``_is_paid_quota_error``): that one SHORT-CIRCUITS straight to a
    loud ``PaidFeatureRequired`` on the FIRST attempt, before the
    transient-retry branch even runs — its body also carries a "retry
    in Xs" hint just like an ordinary rate-limit 429, but no wait ever
    fixes a ZERO free-tier quota. A 429 without the signal is an
    ordinary rate limit and retries exactly as before.

    Every attempt is PACED like any other call (``_pace``)."""
    for attempt in range(1, AI_RETRY_MAX + 1):
        _pace()
        try:
            with _urlopen(req, timeout=AI_TIMEOUT_S) as resp:
                raw = resp.read()
        except urllib.error.HTTPError as exc:
            message, retry_s = _http_error(exc)
            if _is_paid_quota_error(exc.code, message):
                _raise_paid_quota(label, exc, message)
            if exc.code not in AI_TRANSIENT_STATUS or attempt >= AI_RETRY_MAX:
                _raise_http(label, exc, message)
            wait = _retry_wait(exc.code, retry_s)
            log(
                f"Gemini API HTTP {exc.code} on {label} ({message}) —"
                f" retry {attempt + 1}/{AI_RETRY_MAX} in {wait:.0f}s"
            )
            time.sleep(wait)
            continue
        except urllib.error.URLError as exc:
            raise AiError(f"Gemini API unreachable: {exc.reason}") from exc
        try:
            return json.loads(raw)
        except (json.JSONDecodeError, UnicodeDecodeError) as exc:
            raise AiError(
                f"Gemini API returned non-JSON: {raw[:200]!r}"
            ) from exc
    # unreachable: the final transient attempt raises above (Rule #7)
    raise AiError(f"{label}: retries exhausted")


def _call_raw(model: str, payload: dict, key: str, *, log=print) -> dict:
    """POST one generateContent request; returns the PARSED JSON body —
    builds the request and delegates the retry/pace/HTTP SHELL to
    ``_send_request`` (shared with ``list_models``'s GET calls). See
    ``_send_request`` for the retry/pace/HTTP-classification
    behavior."""
    req = urllib.request.Request(
        f"{GEMINI_API_BASE}/models/{model}:generateContent",
        data=json.dumps(payload).encode("utf-8"),
        headers={
            "Content-Type": "application/json",
            "x-goog-api-key": key,
        },
        method="POST",
    )
    return _send_request(req, model, log=log)


def list_models(*, key: str | None = None, log=print) -> list[dict]:
    """GET the ListModels endpoint (owner D1, F5), following
    ``nextPageToken`` across every page, and return one dict per
    model: ``{"name": <id without the "models/" prefix>, "methods":
    <tuple of supportedGenerationMethods>, "display": <displayName>}``.
    Reuses the SAME auth header + retry/backoff shell as every POST
    call (``_send_request``, Rule #5 — one retry loop, not two).
    ``key=None`` reads settings.json (``NoKey`` when absent), like
    every other call in this module. A malformed/missing ``models``
    list on a page is tolerated (treated as empty for that page,
    matching ``_response_text``'s own "skip what does not parse"
    stance); any HTTP failure raises the loud ``AiError`` taxonomy."""
    resolved_key = key or api_key()
    models: list[dict] = []
    page_token: str | None = None
    while True:
        url = f"{GEMINI_API_BASE}/models"
        if page_token:
            url += f"?pageToken={page_token}"
        req = urllib.request.Request(
            url, headers={"x-goog-api-key": resolved_key}, method="GET",
        )
        data = _send_request(req, "models.list", log=log)
        for entry in data.get("models") or ():
            if not isinstance(entry, dict):
                continue
            name = str(entry.get("name", ""))
            models.append({
                "name": name.removeprefix("models/"),
                "methods": tuple(
                    entry.get("supportedGenerationMethods") or ()
                ),
                "display": str(entry.get("displayName") or name),
            })
        page_token = data.get("nextPageToken") or None
        if not page_token:
            return models


# purposes recommend_model/model_for/capable_models understand — every
# OTHER string raises loudly (a caller typo, never guessed at)
_MODEL_PURPOSES = ("image", "vision", "text")
# a model whose NAME carries one of these is never a plain text/vision
# candidate (image generation, embeddings, TTS, audio/video-only) —
# used to EXCLUDE such models from the "vision"/"text" capability filter
_NON_TEXT_NAME_MARKERS = ("image", "embed", "tts", "audio", "video")


def capable_models(models: list[dict], purpose: str) -> list[dict]:
    """The subset of ``models`` (as ``list_models`` returns them)
    CAPABLE of ``purpose`` — "image" (generation), "vision" (image
    checking) or "text" (sheet generation). PURE, offline-testable;
    ``recommend_model`` applies this SAME filter before walking the
    ranking (Rule #5), and the "Models…" picker (``gui/api_panel.py``)
    calls it directly to list every capable option per dropdown, not
    just the top pick.

    "image": the model's name contains "image" OR one of its
    ``supportedGenerationMethods`` names does (the API names no
    single canonical "image output" method, so both signals count).
    "vision"/"text": ``"generateContent"`` is among its methods AND
    its name carries none of ``_NON_TEXT_NAME_MARKERS`` — a text-
    capable model that is explicitly NOT an image-generation/
    embedding/TTS/audio-video-only model."""
    if purpose not in _MODEL_PURPOSES:
        raise ValueError(f"unknown model purpose: {purpose!r}")
    if purpose == "image":
        return [
            m for m in models
            if "image" in m["name"].lower()
            or any("image" in method.lower() for method in m["methods"])
        ]
    return [
        m for m in models
        if any(method.lower() == "generatecontent" for method in m["methods"])
        and not any(
            marker in m["name"].lower() for marker in _NON_TEXT_NAME_MARKERS
        )
    ]


def recommend_model(models: list[dict], purpose: str) -> str | None:
    """The BEST-FOR-THE-JOB model name for one purpose (owner D2:
    never one model for every job) — filters ``models`` down to those
    CAPABLE of ``purpose`` (``capable_models``), then walks
    ``MODEL_PURPOSE_RANKING[purpose]`` (best substring first) and
    returns the first capable model whose name contains it. When no
    ranking entry matches ANY capable model, falls back to the NEWEST
    by name (sorted descending — an honest proxy for "most recent",
    see the config comment on ``MODEL_PURPOSE_RANKING``). ``None``
    when NOTHING in ``models`` is capable of ``purpose`` at all. PURE
    — no I/O, offline-testable."""
    capable = capable_models(models, purpose)
    if not capable:
        return None
    for substring in MODEL_PURPOSE_RANKING.get(purpose, ()):
        for entry in capable:
            if substring in entry["name"].lower():
                return entry["name"]
    return max(capable, key=lambda m: m["name"])["name"]


# purpose -> the hardcoded constant used when settings.json carries no
# override — F5: these three constants are now FALLBACKS ONLY
_PURPOSE_FALLBACK = {
    "image": GEMINI_IMAGE_MODEL,
    "vision": GEMINI_VISION_MODEL,
    "text": GEMINI_TEXT_MODEL,
}


def model_for(purpose: str) -> str:
    """The model name to use for ``purpose`` ("image"/"vision"/
    "text"): settings.json's ``MODELS_SETTING`` ("models") override
    when present and non-blank, else the matching hardcoded constant
    (``_PURPOSE_FALLBACK`` — F5, owner D1/D3). EVERY internal call
    site in this module that used to default to one of
    ``GEMINI_IMAGE_MODEL``/``GEMINI_VISION_MODEL``/``GEMINI_TEXT_MODEL``
    now routes through here (Rule #6) — the constants themselves are
    UNCHANGED and still the fallback of first resort."""
    if purpose not in _PURPOSE_FALLBACK:
        raise ValueError(f"unknown model purpose: {purpose!r}")
    overrides = load_settings().get(MODELS_SETTING) or {}
    value = str(overrides.get(purpose, "") or "").strip()
    return value or _PURPOSE_FALLBACK[purpose]


def _call(model: str, payload: dict, key: str, *, log=print) -> str:
    """POST one generateContent request; returns the response TEXT — a
    thin wrapper over ``_call_raw`` applying ``_response_text``. See
    ``_call_raw`` for the retry/pace/HTTP-classification shell."""
    return _response_text(_call_raw(model, payload, key, log=log), model)


def generate_text(
    prompt: str,
    system: str | None = None,
    *,
    key: str | None = None,
    model: str | None = None,
    log=print,
) -> str:
    """One text generation; ``key=None`` reads settings.json (NoKey
    when absent) — the wizard's Test passes its candidate explicitly.
    ``model=None`` resolves via ``model_for("text")`` (F5, owner D1/
    D3): settings.json's override, else ``GEMINI_TEXT_MODEL``. ``log``
    receives any transient-retry lines (see ``_call``)."""
    return _call(
        model or model_for("text"), _payload_text(prompt, system),
        key or api_key(), log=log,
    )


def check_image(
    image_path: Path,
    instructions: str,
    *,
    prompt: str | None = None,
    key: str | None = None,
    model: str | None = None,
    log=print,
) -> str:
    """One vision call over a saved image file; returns the raw text.
    ``model=None`` resolves via ``model_for("vision")`` (F5). ``log``
    receives any transient-retry lines (see ``_call``).

    ``prompt`` (F6, REWORK.md) is the item's OWN sheet prompt — OPTIONAL:
    when given, ``AI_CHECK_PROMPT_MATCH`` (formatted with it) is appended
    to ``instructions`` so the model ALSO judges whether the image shows
    what the prompt describes, on top of whatever banal-defects check
    ``instructions`` already asks for. ``None`` (the default) sends
    ``instructions`` unchanged — today's quality-only check."""
    image_path = Path(image_path)
    mime = _mime_for(image_path, purpose="the checker")
    full_instructions = instructions
    if prompt is not None:
        full_instructions = (
            f"{instructions}\n\n{AI_CHECK_PROMPT_MATCH.format(prompt=prompt)}"
        )
    payload = _payload_image(image_path.read_bytes(), mime, full_instructions)
    return _call(model or model_for("vision"), payload, key or api_key(), log=log)


def generate_image(
    prompt: str,
    *,
    image_path: Path | None = None,
    key: str | None = None,
    model: str | None = None,
    log=print,
) -> bytes:
    """One IMAGE GENERATION call (the PAID image model — see
    ``GEMINI_IMAGE_MODEL``'s config comment). ``model=None`` resolves
    via ``model_for("image")`` (F5, owner D1/D3): settings.json's
    override, else ``GEMINI_IMAGE_MODEL``.

    ``image_path`` (owner D3, F5) — OPTIONAL: when given, the saved
    image at this path rides along as an ``inlineData`` part BEFORE
    the prompt text (``_payload_reference_and_prompt`` — mirrors the
    website flow's own order, ``driver.submit_with_image`` attaches
    the picture into the composer before the prompt is sent). This
    closes the audited gap where an API-mode sheet item carrying a
    "← ref" input image had no method to call
    (``ApiImageAdapter.submit_with_image``, see ``gui/api_panel.py``).
    With no ``image_path`` this reuses ``_payload_text`` (the prompt,
    no system instruction) exactly as before, widened with
    ``responseModalities: ["TEXT", "IMAGE"]`` so the model returns an
    inline image part instead of (or alongside) text. Returns the
    decoded image BYTES; ``_response_image`` raises loudly when none
    comes back. A free-tier-exhausted 429 raises ``PaidFeatureRequired``
    instead of retrying (see ``_call_raw``). ``key=None`` reads
    settings.json (``NoKey`` when absent), like every other call in
    this module."""
    resolved_model = model or model_for("image")
    if image_path is not None:
        image_path = Path(image_path)
        mime = _mime_for(image_path, purpose="the reference image")
        payload = _payload_reference_and_prompt(
            image_path.read_bytes(), mime, prompt
        )
    else:
        payload = _payload_text(prompt, None)
    payload["generationConfig"] = {"responseModalities": ["TEXT", "IMAGE"]}
    data = _call_raw(resolved_model, payload, key or api_key(), log=log)
    return _response_image(data, resolved_model)


def edit_image(
    image_path: Path,
    prompt: str,
    *,
    key: str | None = None,
    model: str | None = None,
    log=print,
) -> bytes:
    """One IMAGE EDIT call: reuses ``_payload_image`` (the source image
    as inline base64 + the edit instruction text) widened with the
    same ``responseModalities`` as ``generate_image``. ``model=None``
    resolves via ``model_for("image")`` (F5). Returns the decoded
    edited image BYTES."""
    resolved_model = model or model_for("image")
    image_path = Path(image_path)
    mime = _mime_for(image_path, purpose="editing")
    payload = _payload_image(image_path.read_bytes(), mime, prompt)
    payload["generationConfig"] = {"responseModalities": ["TEXT", "IMAGE"]}
    data = _call_raw(resolved_model, payload, key or api_key(), log=log)
    return _response_image(data, resolved_model)


# ---------------------------------------------------------------------
# The sheet-generator flow (owner's #2)
# ---------------------------------------------------------------------

# "1. q" / "1) q" / "- q" / "* q" — the poll lines the model returns
_QUESTION_LINE = re.compile(r"^\s*(?:\d+[.)]\s*|[-*•]\s+)(.+?)\s*$")
_SLUG_STRIP = re.compile(r"[^a-z0-9]+")


def contract_text() -> str:
    """instructions.md verbatim — the authoring contract both system
    prompts embed (the same doc the Instructions button shows)."""
    return (PROJECT_ROOT / "instructions.md").read_text(encoding="utf-8")


def parse_questions(text: str) -> list[str]:
    """The model's clarifying questions, capped at ``AI_MAX_QUESTIONS``.

    Accepts numbered ('1.' / '1)') and dash/star bullet lines; plain
    prose lines are ignored. An answer with NO parseable question
    lines returns [] — the caller then skips the poll and generates
    from the request alone.
    """
    questions: list[str] = []
    for line in text.splitlines():
        m = _QUESTION_LINE.match(line)
        if m and m.group(1).strip():
            questions.append(m.group(1).strip())
    return questions[:AI_MAX_QUESTIONS]


def ask_questions(request: str, contract: str, gen=None) -> list[str]:
    """FIRST call: the contract + 'questions only' system prompt.

    ``gen`` defaults to THIS module's ``generate_text`` resolved at
    CALL time, so tests (and a mocked GUI run) can monkeypatch
    ``ai.generate_text`` and the flow follows."""
    gen = gen or generate_text
    system = AI_QUESTIONS_SYSTEM.format(
        contract=contract, max_q=AI_MAX_QUESTIONS
    )
    return parse_questions(gen(request, system))


def qa_block(questions: list[str], answers: list[str]) -> str:
    """The answered poll as Q/A lines; a skipped (blank) answer is an
    explicit 'no preference' so the model still decides something."""
    lines: list[str] = []
    for question, answer in zip(questions, answers):
        lines.append(f"Q: {question}")
        lines.append(f"A: {answer.strip() or '(no preference — your choice)'}")
    return "\n".join(lines) or "(no questions were asked)"


def strip_md_fence(text: str) -> str:
    """Unwrap a whole-file ``` fence pair (models wrap the sheet in one
    despite instructions). ONLY the exact wrapper case is touched — a
    body not starting with a fence, or not ending with a bare closing
    fence, passes through byte-identical so the sheet's own inner
    prompt fences always survive."""
    body = text.strip()
    if not body.startswith("```"):
        return text
    lines = body.splitlines()
    if len(lines) < 2 or lines[-1].strip() != "```":
        return text
    return "\n".join(lines[1:-1])


def validate_sheet_md(md: str, work_dir: Path) -> tuple[list[str], str | None]:
    """Parse ``md`` with the REAL parser (on a scratch file under
    ``work_dir``) and return ``(problem strings, theme)`` — an empty
    problem list means the sheet is contract-clean and loadable."""
    tmp = Path(work_dir) / "_ai_sheet_validate.md"
    tmp.write_text(md, encoding="utf-8")
    try:
        sheet = parse_sheet(tmp)
    except SheetError:
        return ["no '# ' H1 theme heading — not a prompt sheet"], None
    return (
        [f"L{p.line}: {p.message}" for p in sheet.problems],
        sheet.theme,
    )


def generate_sheet(
    request: str,
    questions: list[str],
    answers: list[str],
    contract: str,
    work_dir: Path,
    gen=None,
    log=print,
) -> tuple[str, list[str], str | None]:
    """SECOND call + at most ONE automatic repair round.

    Returns ``(md, problems, theme)``: ``problems == []`` means the md
    passed the real parser and may be saved/loaded; otherwise ``md`` is
    the best (repaired) attempt for the owner to fix manually — the
    caller must NOT load it. ``gen`` resolves to ``generate_text`` at
    CALL time (monkeypatch-friendly, like ``ask_questions``).
    """
    gen = gen or generate_text
    system = AI_SHEET_SYSTEM.format(contract=contract)
    user = AI_SHEET_REQUEST.format(
        request=request, qa=qa_block(questions, answers)
    )
    md = strip_md_fence(gen(user, system))
    problems, theme = validate_sheet_md(md, work_dir)
    if problems:
        log(
            f"AI sheet fails the parser ({len(problems)} problem(s)) —"
            " one automatic repair round"
        )
        repair = AI_REPAIR_PROMPT.format(
            problems="\n".join(problems), md=md
        )
        md = strip_md_fence(gen(repair, system))
        problems, theme = validate_sheet_md(md, work_dir)
    return md, problems, theme


def slug_for(theme: str) -> str:
    """A filesystem-safe stem from the sheet's H1 theme."""
    slug = _SLUG_STRIP.sub("_", theme.lower()).strip("_")
    return slug or "ai_sheet"


def save_sheet(md: str, theme: str, sheets_dir: Path) -> Path:
    """Write a VALIDATED sheet under ``sheets_dir`` (created on demand)
    with a slugged, collision-free filename; returns the path."""
    sheets_dir = Path(sheets_dir)
    sheets_dir.mkdir(parents=True, exist_ok=True)
    base = slug_for(theme)
    path = sheets_dir / f"{base}.md"
    n = 2
    while path.exists():
        path = sheets_dir / f"{base}_{n}.md"
        n += 1
    path.write_text(md, encoding="utf-8")
    return path


# ---------------------------------------------------------------------
# The image checker + flag memory (owner's #3)
# ---------------------------------------------------------------------


def parse_check_response(text: str) -> list[str]:
    """The checker's strict format -> the defect list ([] = clean).

    'OK' (alone on the first line, any case, trailing '.' tolerated)
    means clean; 'DEFECTS:' followed by dash lines lists them. Any
    OTHER shape is a malformed model answer — loud, never guessed.
    """
    body = text.strip()
    if not body:
        raise AiError("empty check response")
    first, _, rest = body.partition("\n")
    head = first.strip().rstrip(".").upper()
    if head == "OK":
        return []
    if head.startswith("DEFECTS"):
        defects = [
            stripped
            for line in rest.splitlines()
            if (stripped := line.strip().lstrip("-*• ").strip())
        ]
        if not defects:
            # everything on the header line: "DEFECTS: subject cut"
            after = first.split(":", 1)[1].strip() if ":" in first else ""
            if after:
                return [after]
            raise AiError(
                f"check response names no defects: {body[:120]!r}"
            )
        return defects
    raise AiError(f"unexpected check response: {body[:120]!r}")


def fix_note(defects: list[str]) -> str:
    """The per-item extra suffix for a re-sent flagged image."""
    return AI_FIX_NOTE.format(defects="; ".join(defects))


def build_fix_prompt(defects: list[str], raw: str | None = None) -> str:
    """The Fixer AI's instruction (GUI rework Phase 20, owner's
    UV/prompt.txt item 2: "u oba slucaja kreira PROMPT koji salje uz
    sliku") — turns one checked image's parsed defect list (+ its
    VERBATIM raw response, for extra context the parsed bullets can
    lose) into the text sent ALONGSIDE the flagged image. PURE: no I/O,
    no network — offline-testable.

    Shared by every fixer surface (Rule #5, one prompt-builder instead
    of several near-copies): the manual IMAGE FIX / WEBSITE FIX buttons
    in the checker's report viewer (both call ``ai.edit_image``/
    ``driver.submit_with_image`` with THIS text) and the API-mode
    auto-fixer (``PainterGui._run_fixer_api``).

    An EMPTY ``defects`` list still returns a sensible, non-blank
    instruction (``AI_FIX_PROMPT_NO_DEFECTS``) rather than raising or
    returning "" — ``edit_image``/``submit_with_image`` always need SOME
    instruction text, and this function stays honest about ANY input
    regardless of whether the caller already gates on defects existing
    (root Rule #1: never assume an upstream gate held). ``raw`` — when
    given and non-blank — is appended VERBATIM after the instruction,
    never in place of it (the parsed bullets are the actionable part;
    the raw response is grounding context alongside them).
    """
    if defects:
        bullets = "\n".join(f"- {d}" for d in defects)
        instruction = AI_FIX_PROMPT_WITH_DEFECTS.format(bullets=bullets)
    else:
        instruction = AI_FIX_PROMPT_NO_DEFECTS
    if raw and raw.strip():
        instruction += AI_FIX_PROMPT_RAW_SUFFIX.format(raw=raw.strip())
    return instruction


def flags_path(out_base: Path) -> Path:
    return Path(out_base) / STATE_DIRNAME / AI_FLAGS_FILENAME


def flag_key(image_path: Path, out_base: Path) -> str:
    """The flag dict's key for one image: its POSIX path RELATIVE to
    the out base. An image OUTSIDE the base keys by its absolute POSIX
    path — the flag still persists, but ``drop_and_site_for`` cannot
    match it to a queued collection (the re-send logs and skips it)."""
    resolved = Path(image_path).resolve()
    try:
        return resolved.relative_to(Path(out_base).resolve()).as_posix()
    except ValueError:
        return resolved.as_posix()


def flag_file(key: str, out_base: Path) -> Path:
    """The image file a flag key points at — the EXACT reverse of
    ``flag_key`` (relative to the out base, or absolute when the image
    lived outside it). One home for the round-trip so the checker's
    flag key and the panel's viewer file can never drift apart."""
    path = Path(key)
    return path if path.is_absolute() else Path(out_base) / path


def load_flags(out_base: Path, log=print) -> dict:
    """The saved flags dict; {} on a missing file. A corrupt file is
    reported LOUDLY and treated as empty — flags are derived data (a
    re-check rebuilds them), so losing them never loses work."""
    path = flags_path(out_base)
    if not path.exists():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        log(f"AI FLAGS: cannot read {path} ({exc}) — starting empty")
        return {}
    if not isinstance(data, dict):
        log(
            f"AI FLAGS: {path} does not hold a JSON object — starting"
            " empty"
        )
        return {}
    return data


def save_flags(out_base: Path, flags: dict) -> Path:
    """Atomic write (tmp + replace), mirroring settings.py."""
    path = flags_path(out_base)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_text(
        json.dumps(flags, indent=2, ensure_ascii=False), encoding="utf-8"
    )
    tmp.replace(path)
    return path


def record_flag(
    out_base: Path,
    image_path: Path,
    defects: list[str],
    model: str,
    raw: str,
    log=print,
) -> str:
    """Load-merge-save one image's flag entry; returns its key. The
    stored mtime is the file's AT CHECK TIME — a later regeneration
    changes it and ``prune_stale_flags`` drops the entry. ``raw`` is the
    VERBATIM model response, persisted alongside the parsed defects so
    the owner can inspect exactly what the vision model said."""
    flags = load_flags(out_base, log)
    key = flag_key(image_path, out_base)
    flags[key] = {
        "defects": list(defects),
        "raw": raw,
        "checked_at": datetime.now().isoformat(timespec="seconds"),
        "model": model,
        "mtime": Path(image_path).stat().st_mtime,
    }
    save_flags(out_base, flags)
    return key


def clear_flag_keys(out_base: Path, keys: list[str], log=print) -> int:
    """Drop the given flag ENTRIES by key (the panel's Clear-flags
    action); returns the number actually removed."""
    flags = load_flags(out_base, log)
    removed = sum(1 for key in keys if flags.pop(key, None) is not None)
    if removed:
        save_flags(out_base, flags)
    return removed


def clear_flag(out_base: Path, image_path: Path, log=print) -> bool:
    """Drop one image's entry (an OK re-check clears the old flag);
    True when an entry existed."""
    return clear_flag_keys(
        out_base, [flag_key(image_path, out_base)], log
    ) == 1


def prune_stale_flags(out_base: Path, log=print) -> int:
    """Drop every entry whose file is GONE or whose mtime CHANGED since
    the check (the image was regenerated / retouched) — run before a
    check batch so the memory never asserts stale defects. Returns the
    number dropped."""
    flags = load_flags(out_base, log)
    keep: dict = {}
    dropped = 0
    for key, entry in flags.items():
        file = flag_file(key, out_base)
        try:
            same = file.stat().st_mtime == float(entry.get("mtime", -1.0))
        except (OSError, TypeError, ValueError):
            same = False  # gone or malformed entry -> stale
        if same:
            keep[key] = entry
        else:
            dropped += 1
    if dropped:
        save_flags(out_base, keep)
        log(
            f"AI FLAGS: {dropped} stale flag(s) cleared (file changed"
            " or gone since the check)"
        )
    return dropped


def check_one_image(
    src: Path,
    out_base: Path,
    instructions: str,
    *,
    prompt: str | None = None,
    model: str | None = None,
    log=print,
    check=None,
) -> dict:
    """Drive ONE image through the vision checker and the flag memory —
    the pure core the GUI worker loops over (Rule #5, and offline-
    testable: ``check`` defaults to this module's ``check_image``, so a
    test injects a per-image mock).

    ``model=None`` resolves via ``model_for("vision")`` (F5) BEFORE
    the call, not left for ``check_image`` to default itself — the
    RESOLVED name is what ``record_flag`` persists, so a flag entry
    never stores the literal string "None".

    ``prompt`` (F6, REWORK.md) passes straight through to ``check`` —
    ``None`` (the default) is NOT forwarded at all, so an older/simpler
    ``check`` double with no ``prompt`` parameter of its own (existing
    tests, callers) keeps working unchanged; only a caller that actually
    supplies a prompt needs ``check`` to accept it.

    Times the call, parses the strict OK/DEFECTS answer, MERGES a flag
    (or CLEARS a fixed image's old flag) and returns the row the panel
    renders — the flag ``key`` (``flag_key``, which ``flag_file``
    reverses back to THIS exact file), the ``kind``
    ('flagged'/'ok'/'error'), the parsed ``defects``, the VERBATIM
    ``raw`` model text and the elapsed ``time`` seconds. A per-image
    ``AiError`` (HTTP after the retries, or a malformed answer) is
    CAUGHT and returned as an 'error' row — loud in the log, never
    fatal (the tool-job convention); ``raw`` then carries the model's
    answer when we got one (a parse failure) or the error text (a
    network/HTTP failure), so the viewer always shows what happened."""
    check = check or check_image
    model = model or model_for("vision")
    key = flag_key(src, out_base)
    t0 = time.monotonic()
    raw: str | None = None
    call_kwargs = {"model": model, "log": log}
    if prompt is not None:
        call_kwargs["prompt"] = prompt
    try:
        raw = check(src, instructions, **call_kwargs)
        defects = parse_check_response(raw)
    except AiError as exc:
        op_s = time.monotonic() - t0
        log(f"FAIL {Path(src).name}: {exc}")
        return {
            "rel": key, "kind": "error", "defects": [],
            "raw": raw if raw is not None else str(exc), "time": op_s,
        }
    op_s = time.monotonic() - t0
    if defects:
        record_flag(out_base, src, defects, model, raw, log)
        log(f"FLAGGED {Path(src).name}: {'; '.join(defects)}")
        return {
            "rel": key, "kind": "flagged", "defects": defects,
            "raw": raw, "time": op_s,
        }
    clear_flag(out_base, src, log)  # a fixed image loses its stale flag
    return {"rel": key, "kind": "ok", "defects": [], "raw": raw, "time": op_s}


def drop_and_site_for(rel: str) -> tuple[str, str] | None:
    """Reverse ``config.dest_for``: the (drop_path, site) one
    out-relative save path came from.

    Assets mirror ``<rest>/<File>[_vN]_<sfx>.png`` ->
    ``('assets/<rest>/<File>.png', site)`` (the DOMY RESTRUCTURE
    filename-suffix convention, 2026-07-22; a ``_vN`` version sibling
    — the ticked-redo output, owner 2026-07-27 — reverses to the SAME
    canonical drop as its master, so a flagged version re-sends
    through the sheet entry it came from); the pre-RESTRUCTURE
    ``<category>/<site>/<rest>`` folder layout and legacy
    ``<site>/<drop>`` still reverse for old out/ trees. ``None`` when
    nothing names a site (an absolute flag key, or a folder that was
    never a generator output).
    """
    from painter.config import SITE_FILE_SUFFIX

    parts = PurePosixPath(rel).parts
    if parts:
        name = parts[-1]
        stem, dot, ext = name.rpartition(".")
        core = stem if dot else name
        for site, sfx in SITE_FILE_SUFFIX.items():
            if core.endswith(sfx) and len(core) > len(sfx):
                bare = core[: -len(sfx)]
                version = re.fullmatch(r"(.+)_v\d*", bare)
                if version is not None:
                    bare = version.group(1)
                bare += f".{ext}" if dot else ""
                return "assets/" + "/".join((*parts[:-1], bare)), site
    if len(parts) >= 3 and parts[1] in SITES:
        return "assets/" + "/".join((parts[0], *parts[2:])), parts[1]
    if len(parts) >= 2 and parts[0] in SITES:
        return "/".join(parts[1:]), parts[0]
    return None


def plan_resend(
    flagged: dict[str, list[str]],
    drop_to_source: dict[str, str],
) -> tuple[dict, dict, list[tuple[str, str]]]:
    """The re-send plan for a batch of flagged images (owner's #3).

    ``flagged`` maps a FLAG KEY to its defect list; ``drop_to_source``
    maps every QUEUED item's drop path to its sheet source (str).
    Returns ``(plans, notes, unmatched)``:

    * ``plans[site][source]`` — the drop-path set that site must run
      (the ``only=`` regenerate selection, grouped per sheet);
    * ``notes[site][drop]`` — the per-item fix note
      (``run_sheet``'s ``extra_suffix``);
    * ``unmatched`` — ``(flag key, reason)`` pairs the caller reports
      LOUDLY: the path names no site, or no queued collection carries
      the reversed drop path.
    """
    plans: dict[str, dict[str, set]] = {}
    notes: dict[str, dict[str, str]] = {}
    unmatched: list[tuple[str, str]] = []
    for key, defects in flagged.items():
        mapped = drop_and_site_for(key)
        if mapped is None:
            unmatched.append((key, "no site in the path"))
            continue
        drop, site = mapped
        source = drop_to_source.get(drop)
        if source is None:
            unmatched.append((key, "not in any queued collection"))
            continue
        plans.setdefault(site, {}).setdefault(source, set()).add(drop)
        notes.setdefault(site, {})[drop] = fix_note(defects)
    return plans, notes, unmatched
