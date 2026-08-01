# Gemini REST Client

**Script:** [Gemini REST Client (script)](../client.py) ·
**Flow:** [diagram](../__flow/client.md)

## Purpose

The transport every AI feature calls through, plus the model
discovery that decides WHICH model each purpose uses. Split out of the
single-file `painter/ai.py` (root Rule #20, 2026-07-30) — see
[AI (subfolder)](../___ai.md) for the failure taxonomy and the retry
policy every call here obeys.

Offline-testable: the HTTP layer is one monkeypatchable alias,
`painter.ai.client._urlopen` — patched on THIS module, which is where
`_send_request` reads the name.

## Connections

### Uses
- [Config (subfolder)](../../config/___config.md) — the
  `GEMINI_*`/`AI_*` block, `MODEL_PURPOSE_RANKING`/`MODELS_SETTING`
- [Settings](../../__about/settings.md) — `load_settings` (the key and
  the per-purpose model overrides)

### Used by
- [Sheet-Generator Flow](sheet_flow.md) — `generate_text`
- [Image Checker](checks.md) — `check_image`, `model_for`, `AiError`
- [AI (subfolder)](../___ai.md) — `__init__.py` re-exports the whole
  public surface
- [GUI (folder)](../../../gui/___gui.md) — the key wizard's Test, the
  API image job, the "Models…" picker

## Classes

### AiError
A Gemini API call failed — HTTP error, refusal/block or malformed
response. Loud; the CALLER decides whether one failure skips an
image (the checker's per-item convention) or stops a flow. Carries
`status` — the numeric HTTP code on an HTTP failure (None otherwise) —
so the retry logic and callers key on the code, not the message.

### NoKey
`AiError` subclass: `settings.json` holds no key. The GUI's
documented reaction is opening the guided wizard.

### PaidFeatureRequired
`AiError` subclass: a 429 carried the free-tier-EXHAUSTED signal
(`_is_paid_quota_error` / `AI_IMAGE_QUOTA_MARKERS`) — the account has
ZERO free quota for the requested model. PERMANENT: raised on the
FIRST attempt inside `_call_raw`, never retried like an ordinary
rate-limit 429.

## Functions — the REST client

- `api_key() -> str` — the key from `settings.json`
  (`GEMINI_KEY_SETTING`); `NoKey` when absent/blank.
- `generate_text(prompt, system=None, *, key=None, model=None,
  log=print)` — one `models/<model>:generateContent` POST (key in the
  `x-goog-api-key` header, `systemInstruction` when given); returns
  the response text. `key=None` reads settings — the wizard's Test
  passes its candidate explicitly. `model=None` resolves via
  `model_for("text")`. `log` receives the transient-retry lines.
- `check_image(image_path, instructions, *, prompt=None, key=None,
  model=None, log=print)` — the vision call: the instructions text
  part + the image as base64 `inlineData` (png/jpg/webp by suffix, via
  `_mime_for`). `model=None` resolves via `model_for("vision")`.
  `prompt` is OPTIONAL — the item's own sheet prompt: when given,
  `config.AI_CHECK_PROMPT_MATCH` (formatted with it) is appended to
  `instructions`, so the model ALSO judges whether the image shows
  what the prompt describes on top of the banal-defects check
  `instructions` already asks for; `None` sends `instructions`
  unchanged.
- `generate_image(prompt, *, image_path=None, key=None, model=None,
  log=print) -> bytes` — one IMAGE-GENERATION call against the PAID
  image model (`model=None` resolves via `model_for("image")`). With
  no `image_path`: the SAME text payload `generate_text` builds
  (`_payload_text`, no system instruction), widened with
  `generationConfig.responseModalities: ["TEXT", "IMAGE"]`. With
  `image_path` given: the saved image at that path rides along as an
  `inlineData` part BEFORE the prompt text (`_payload_reference_and_
  prompt` — mirrors [CDP Driver](../../__about/driver.md)'s own
  `submit_with_image` order, picture attached before the prompt is
  sent) — closes the gap where an API-mode sheet item carrying a
  "← ref" input image had no method to call. Returns the decoded PNG
  bytes (`_response_image`).
- `edit_image(image_path, prompt, *, key=None, model=None,
  log=print) -> bytes` — one image EDIT call: the source image
  embedded exactly like `check_image` (`_payload_image` + `_mime_for`,
  TEXT part first, then the image) plus the edit instruction, same
  `responseModalities` widening. `model=None` resolves via
  `model_for("image")`. Returns the decoded edited PNG bytes.
- `generate_text`/`check_image` go through `_call`, a THIN wrapper
  over `_call_raw(model, payload, key, *, log) -> dict` applying
  `_response_text`; `generate_image`/`edit_image` call `_call_raw`
  directly and apply `_response_image` themselves. `_call_raw` builds
  the POST request and delegates to `_send_request(req, label, *,
  log) -> dict` — `list_models`'s GET calls share the SAME shell
  instead of a second near-copy of the retry loop. `_send_request`
  does the pacing + the TRANSIENT-error RETRY: on a 503/429/500 it
  waits and re-sends up to `AI_RETRY_MAX` attempts (503/500 wait
  `AI_RETRY_BACKOFF_S`; a 429 honours the server's own `retryDelay` /
  "retry in Xs", capped at `AI_RETRY_MAX_WAIT_S`), logging each retry;
  a permanent code raises at once — EXCEPT a 429 carrying the
  free-tier-EXHAUSTED signal (`_is_paid_quota_error`), checked BEFORE
  the transient branch, which raises `PaidFeatureRequired` immediately
  instead. The HTTP body is parsed ONCE (`_http_error`) for both the
  message and the 429 backoff.
- Response parsing: `_response_text` (text calls) tolerates the
  candidates/parts structure (empty candidates skipped, parts
  concatenated) and is LOUD on `promptFeedback.blockReason`, a
  non-STOP `finishReason` with no text, and any shape carrying no
  text. `_response_image` mirrors it for the image calls — reads the
  first `inlineData` part instead of text, LOUD when no candidate
  carries an image part at all.

## Functions — model discovery + purpose recommendation

- `list_models(*, key=None, log=print) -> list[dict]` — GETs the
  ListModels endpoint (`{GEMINI_API_BASE}/models`), following
  `nextPageToken` across every page, via `_send_request`. Each
  returned dict: `{"name": <id without the "models/" prefix>,
  "methods": <tuple of supportedGenerationMethods>, "display":
  <displayName>}`. `key=None` reads settings.json (`NoKey` when
  absent); any HTTP failure raises the usual `AiError` taxonomy.
- `capable_models(models, purpose) -> list[dict]` — the subset of
  `models` CAPABLE of `purpose` (`"image"`/`"vision"`/`"text"`; any
  other string raises `ValueError` loudly). `"image"`: the name
  contains `"image"` OR a `supportedGenerationMethods` entry does.
  `"vision"`/`"text"`: `"generateContent"` among the methods AND the
  name carries none of `_NON_TEXT_NAME_MARKERS` (`"image"`/`"embed"`/
  `"tts"`/`"audio"`/`"video"`) — only the RANKING differs per purpose,
  not the capability test. PURE, offline-testable.
- `recommend_model(models, purpose) -> str | None` — the BEST-FOR-
  THE-JOB model for `purpose`: filters via `capable_models`, then
  walks `config.MODEL_PURPOSE_RANKING[purpose]` (best substring first)
  and returns the first capable name containing it; when nothing in
  the ranking matches, falls back to the NEWEST by name (sorted
  descending); `None` when nothing is capable at all. PURE.
- `model_for(purpose) -> str` — the model actually used by every call
  above when its own `model=` is left `None`: `settings.json`'s
  `MODELS_SETTING` (`"models"`) per-purpose override when present and
  non-blank, else the matching hardcoded `GEMINI_*_MODEL` constant
  (a FALLBACK only).
- The "Models…" picker in the GUI's `ApiImageGenPanel` drives
  `list_models`/`capable_models`/`recommend_model` on a background
  thread and writes a pick straight to `settings.json` via
  [Settings](../../__about/settings.md).

## Design Decisions

- **No SDK.** The two calls the features need are one POST each;
  `urllib` keeps the dependency set unchanged and the HTTP layer
  mockable in one line.
- **Model names are config data** (`GEMINI_TEXT_MODEL`,
  `GEMINI_VISION_MODEL`) — Google rotates them; the owner bumps a
  string, not code.
- **Retry transient, raise permanent.** The free tier genuinely 503s
  under load; skipping the image on the first 503 threw away a whole
  paced call for nothing. The retry lives in `_send_request`, so BOTH
  the text and vision paths get it for free — but only for the codes
  that a wait can fix (503/429/500); a 400/401/403/404 is a real bug
  in the request and fails loudly at once.
- **Paid-quota classification keys on the signal, never the retry
  hint.** The owner's captured free-tier-exhausted 429 body ALSO names
  a "retry in Xs" hint — identical in shape to an ordinary transient
  rate-limit 429's body. Classifying by that hint would misfire both
  ways, so `_is_paid_quota_error` instead matches the free-tier-zero
  substrings (`AI_IMAGE_QUOTA_MARKERS`). An ambiguous 429 (matches
  neither) defaults to transient — retrying a permanent error wastes a
  few calls, but giving up on a genuinely transient one is worse.
- **`_call_raw` is the ONE shell — and `_send_request` is now the
  shell UNDER it.** `_call_raw` only BUILDS the POST request and hands
  it to `_send_request`, which owns the actual attempt loop — so
  `list_models`'s GET request (a DIFFERENT method/URL, no JSON body)
  shares the identical retry/pace/classification behavior by building
  its own request and calling the same function, rather than a THIRD
  near-copy of the loop.
- **Model resolution is ONE function, read at CALL time, never baked
  into a default argument.** A `model: str = GEMINI_TEXT_MODEL`
  default would freeze the constant at IMPORT time — reading
  settings.json's override needs to happen on every call. Every
  public call's `model` parameter is therefore `None` by default, and
  the function body resolves `model or model_for(purpose)` itself.
  `check_one_image` (in [Image Checker](checks.md)) resolves it ONE
  line earlier than its own `check` call specifically so the RESOLVED
  name (not the literal string `"None"`) is what `record_flag`
  persists.
- **The reference-image part order is the ONE deliberate asymmetry.**
  `_payload_image` (the checker/`edit_image` convention: TEXT then
  the picture) and `_payload_reference_and_prompt` (`generate_image`'s
  `image_path`: the picture then TEXT) share their per-part builders
  (`_text_part`/`_inline_data_part`) but keep DIFFERENT orders on
  purpose — the new path mirrors the website's own
  `driver.submit_with_image`, which attaches the picture into the
  composer before the prompt is typed and sent.
