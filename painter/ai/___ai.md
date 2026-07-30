# ai/

The engine behind the AI features (owner 2026-07-20; image generation
added GUI rework Phase 18) — a MINIMAL Gemini REST client over
`urllib` (no SDK), the sheet-generator flow, the image checker and its
flag memory.

Split by responsibility into four submodules (was one 1,198-line
`ai.py`, root Rule #20 god-file split, 2026-07-30). `__init__.py`
re-exports the FULL public API of every submodule — one explicit
`from .client import (...)` block each, the same shape
[Config (subfolder)](../config/___config.md) already uses — so every
existing `from painter import ai` / `ai.generate_image(...)` call site
and every `monkeypatch.setattr(ai_module, "edit_image", fake)` in the
suite kept working UNCHANGED across the split.

Loud failure taxonomy (Rule #1): every HTTP error, API refusal/block
and malformed response raises `AiError`; a missing key raises the
specific `NoKey`, which the GUI answers by AUTO-OPENING the guided key
wizard, and a 429 carrying the free-tier-EXHAUSTED signal raises the
specific `PaidFeatureRequired` (GUI rework Phase 18) instead of
retrying. Consecutive API calls are PACED `AI_CALL_PAUSE_S` apart —
the free tier allows roughly 10 requests/minute.

TRANSIENT failures RETRY (owner 2026-07-21): the free tier 503s under
load ("model experiencing high demand") and 429s at the rate cap —
those, plus a 500, are retried up to `AI_RETRY_MAX` attempts with a
backoff between them, instead of being counted an error and skipped.
PERMANENT failures (400/401/403/404 — a bad request, bad key or
unknown model) raise on the first try. A 429 is checked FIRST for the
free-tier-EXHAUSTED signal (`_is_paid_quota_error` /
`AI_IMAGE_QUOTA_MARKERS`, GUI rework Phase 18) — that one is ALSO
permanent and short-circuits to `PaidFeatureRequired` on the very
first attempt, even though its body also names a "retry in Xs" hint
like an ordinary rate-limit 429 (the trap: classify on the signal,
never that hint — see Design Decisions). The retry keys on the numeric
HTTP status, which the client attaches to the raised `AiError`
(`.status`).

## Files

### `client.py` — Gemini REST Client
The transport every other module calls through: `api_key`, the four
calls (`generate_text`/`check_image`/`generate_image`/`edit_image`),
the ONE retry/pace/classification shell under them
(`_call_raw` -> `_send_request`), the response parsers, and the F5
model discovery (`list_models`/`capable_models`/`recommend_model`/
`model_for`). Owns the `AiError`/`NoKey`/`PaidFeatureRequired`
taxonomy. See [Gemini REST Client](client.md).

### `sheet_flow.py` — Sheet-Generator Flow
The owner's #2: clarifying questions, the two calls built from the
sheet contract, validation with the REAL parser plus ONE automatic
repair round, and the slugged save under `sheets/`. See
[Sheet-Generator Flow](sheet_flow.md).

### `checks.py` — Image Checker
The owner's #3: the checker's strict response format, the fix prompt
built from it, the per-image driver both GUI callers share
(`check_one_image`), and the resend plan (`drop_and_site_for` /
`plan_resend`). See [Image Checker](checks.md).

### `flags.py` — Flag Memory
`<out>/_state/ai_flags.json` — what a check found, keyed by the
image's out-relative path and invalidated by the file's own mtime.
Pure disk state: no HTTP, no model. See [Flag Memory](flags.md).

## Connections

### Uses
- [Config (subfolder)](../config/___config.md) — the whole `GEMINI_*` /
  `AI_*` block, `MODEL_PURPOSE_RANKING`/`MODELS_SETTING` (F5), `SITES`,
  `STATE_DIRNAME`, `PROJECT_ROOT`
- [Settings](../settings.md) — `load_settings` (the key lives in
  `settings.json` under `gemini_api_key`; F5's per-purpose model
  overrides under `MODELS_SETTING`, `"models"`)
- [Sheet Parser](../sheet_parser.md) — `parse_sheet` validates every
  AI-produced sheet with the REAL contract rules

### Used by
- [GUI](../../gui.md) — the key wizard's Test, the New-collection
  dialog, the AI-check job, the re-send mapping, and (F5)
  `ApiImageGenPanel`'s "Models…" picker + `ApiImageAdapter`'s
  `submit_with_image`/`extract_image`
- [Tests (folder)](../../tests/___tests.md) — mocked-HTTP client tests,
  flow tests, flag round-trips

## Design Decisions

- **Why a package, and where the HTTP mock now lives.** The four parts
  were already documented as four cohesive concerns inside one file;
  the split makes that structural (Rule #20). The one call site that
  had to change is the tests' HTTP mock: `_urlopen` is read by
  `_send_request` from its OWN module globals, so it is patched as
  `painter.ai.client._urlopen` (likewise `client.load_settings`,
  `client.time`, `client._last_call_t`). Everything patched through
  the PACKAGE (`ai_module.generate_image`, `ai_module.edit_image`,
  `ai_module.check_one_image`, `ai_module.list_models` — all called by
  the GUI as package attributes) keeps working untouched.
- **No SDK.** The two calls the features need are one POST each;
  `urllib` keeps the dependency set unchanged and the HTTP layer
  mockable in one line.
- **Model names are config data** (`GEMINI_TEXT_MODEL`,
  `GEMINI_VISION_MODEL`) — Google rotates them; the owner bumps a
  string, not code.
- **Retry transient, raise permanent.** The free tier genuinely 503s
  under load; skipping the image on the first 503 threw away a whole
  paced call for nothing. The retry lives in `_call`, so BOTH the text
  and vision paths get it for free — but only for the codes that a
  wait can fix (503/429/500); a 400/401/403/404 is a real bug in the
  request and fails loudly at once. Honest caveat: a free-tier 503 can
  persist through all the retries under sustained load, and the retry
  adds wall-time.
- **Paid-quota classification keys on the signal, never the retry
  hint** (GUI rework Phase 18). The owner's captured free-tier-
  exhausted 429 body ALSO names a "retry in Xs" hint — identical in
  shape to an ordinary transient rate-limit 429's body. Classifying by
  that hint would misfire both ways, so `_is_paid_quota_error` instead
  matches the free-tier-zero substrings (`AI_IMAGE_QUOTA_MARKERS`:
  `"free_tier"` + `"limit: 0"`, or `"check your plan and billing
  details"`). An ambiguous 429 (matches neither) defaults to
  transient — retrying a permanent error wastes a few calls, but
  giving up on a genuinely transient one is worse.
- **`_call_raw` is the ONE shell — and `_send_request` (F5) is now
  the shell UNDER it.** Extracting the retry/pace/HTTP plumbing out of
  `_call` (which now only adds `_response_text`) let the paid image
  calls reuse the exact same shell — including the paid-quota short-
  circuit — instead of a second near-copy of the retry loop (Rule
  #5). F5 pushed the split one layer further: `_call_raw` now only
  BUILDS the POST request and hands it to `_send_request`, which owns
  the actual attempt loop — so `list_models`'s GET request (a
  DIFFERENT method/URL, no JSON body) shares the identical retry/pace/
  classification behavior by building its own request and calling the
  same function, rather than a THIRD near-copy of the loop. Both
  splits are behavior-preserving BY CONSTRUCTION: every existing
  `_call`/`_call_raw` test still passes unchanged.
- **Model resolution is ONE function, read at CALL time, never baked
  into a default argument (F5).** A `model: str = GEMINI_TEXT_MODEL`
  default would freeze the constant at IMPORT time — reading
  settings.json's override needs to happen on every call, since the
  owner can change the pick between two calls in the same run. Every
  public call's `model` parameter is therefore `None` by default, and
  the function body resolves `model or model_for(purpose)` itself.
  `check_one_image` resolves it ONE line earlier than its own `check`
  call specifically so the RESOLVED name (not the literal string
  `"None"`) is what `record_flag` persists.
- **The reference-image part order is the ONE deliberate asymmetry.**
  `_payload_image` (the checker/`edit_image` convention: TEXT then
  the picture) and `_payload_reference_and_prompt` (`generate_image`'s
  new `image_path`: the picture then TEXT) share their per-part
  builders (`_text_part`/`_inline_data_part`, Rule #5) but keep
  DIFFERENT orders on purpose — the new path mirrors the website's own
  `driver.submit_with_image`, which attaches the picture into the
  composer before the prompt is typed and sent; changing `_payload_
  image`'s existing order would have been unrelated scope creep.
