# Gemini REST Client

**Script:** [Gemini REST Client (script)](client.py)

## Purpose
The transport every AI feature calls through, plus the model
discovery that decides WHICH model each purpose uses. Split out of the
single-file `painter/ai.py` (root Rule #20, 2026-07-30) — see
[AI (subfolder)](___ai.md) for the failure taxonomy and the retry
policy every call here obeys.

Offline-testable: the HTTP layer is one monkeypatchable alias,
`painter.ai.client._urlopen` — patched on THIS module, which is where
`_send_request` reads the name.

## Connections

### Uses
- [Config (subfolder)](../config/___config.md) — the `GEMINI_*`/`AI_*`
  block, `MODEL_PURPOSE_RANKING`/`MODELS_SETTING`
- [Settings](../settings.md) — `load_settings` (the key and the
  per-purpose model overrides)

### Used by
- [Sheet-Generator Flow](sheet_flow.md) — `generate_text`
- [Image Checker](checks.md) — `check_image`, `model_for`, `AiError`
- [AI (subfolder)](___ai.md) — `__init__.py` re-exports the whole
  public surface
- [GUI](../../gui.md) — the key wizard's Test, the API image job, the
  "Models…" picker

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
`AiError` subclass (GUI rework Phase 18): a 429 carried the free-
tier-EXHAUSTED signal (`_is_paid_quota_error` /
`AI_IMAGE_QUOTA_MARKERS`) — the account has ZERO free quota for the
requested model. PERMANENT: raised on the FIRST attempt inside
`_call_raw`, never retried like an ordinary rate-limit 429.

## Functions — the REST client

- `api_key() -> str` — the key from `settings.json`
  (`GEMINI_KEY_SETTING`); `NoKey` when absent/blank.
- `generate_text(prompt, system=None, *, key=None, model=None,
  log=print)` — one `models/<model>:generateContent` POST (key in the
  `x-goog-api-key` header, `systemInstruction` when given); returns
  the response text. `key=None` reads settings — the wizard's Test
  passes its candidate explicitly. `model=None` resolves via
  `model_for("text")` (F5). `log` receives the transient-retry lines.
- `check_image(image_path, instructions, *, prompt=None, key=None,
  model=None, log=print)` — the vision call: the instructions text part +
  the image as base64 `inlineData` (png/jpg/webp by suffix, via
  `_mime_for`). `model=None` resolves via `model_for("vision")` (F5).
  `log` receives the transient-retry lines. `prompt` (F6, REWORK.md) is
  OPTIONAL — the item's own sheet prompt: when given,
  `config.AI_CHECK_PROMPT_MATCH` (formatted with it) is appended to
  `instructions`, so the model ALSO judges whether the image shows what
  the prompt describes (the tilted-cosmos case: a flat medallion
  rendered as a tilted 3D view from above) on top of the banal-defects
  check `instructions` already asks for; `None` sends `instructions`
  unchanged.
- `generate_image(prompt, *, image_path=None, key=None, model=None,
  log=print) -> bytes` (GUI rework Phase 18; `image_path` F5, owner
  D3) — one IMAGE-GENERATION call against the PAID image model
  (`model=None` resolves via `model_for("image")`). With no
  `image_path`: the SAME text payload `generate_text` builds
  (`_payload_text`, no system instruction), widened with
  `generationConfig.responseModalities: ["TEXT", "IMAGE"]` so the
  model returns an inline image part. With `image_path` given: the
  saved image at that path rides along as an `inlineData` part BEFORE
  the prompt text (`_payload_reference_and_prompt` — mirrors
  [CDP Driver](driver.md)'s own `submit_with_image` order, picture
  attached before the prompt is sent) — closes the audited gap where
  an API-mode sheet item carrying a "← ref" input image had no method
  to call (`gui.ApiImageAdapter.submit_with_image`). Returns the
  decoded PNG bytes (`_response_image`).
- `edit_image(image_path, prompt, *, key=None, model=None,
  log=print) -> bytes` (GUI rework Phase 18) —
  one image EDIT call: the source image embedded exactly like
  `check_image` (`_payload_image` + `_mime_for`, TEXT part first, then
  the image) plus the edit instruction, same `responseModalities`
  widening. `model=None` resolves via `model_for("image")` (F5).
  Returns the decoded edited PNG bytes.
- `generate_text`/`check_image` go through `_call`, a THIN wrapper
  over `_call_raw(model, payload, key, *, log) -> dict` applying
  `_response_text`; `generate_image`/`edit_image` call `_call_raw`
  directly and apply `_response_image` themselves (GUI rework Phase
  18 split — Rule #5, one retry/pace/HTTP shell instead of two
  near-identical copies; behavior-preserving for the text/vision
  path — every prior `_call` test still passes unchanged against the
  new split). `_call_raw` builds the POST request and delegates to
  `_send_request(req, label, *, log) -> dict` (F5 split — Rule #5:
  `list_models`'s GET calls share the SAME shell instead of a second
  near-copy of the retry loop). `_send_request` does the pacing + the
  TRANSIENT-error RETRY: on a 503/429/500 it waits and re-sends up to
  `AI_RETRY_MAX` attempts (503/500 wait `AI_RETRY_BACKOFF_S`; a 429
  honours the server's own `retryDelay` / "retry in Xs", capped at
  `AI_RETRY_MAX_WAIT_S`), logging each retry; a permanent code raises
  at once — EXCEPT a 429 carrying the free-tier-EXHAUSTED signal
  (`_is_paid_quota_error`), checked BEFORE the transient branch, which
  raises `PaidFeatureRequired` immediately instead. The HTTP body is
  parsed ONCE (`_http_error`) for both the message and the 429
  backoff.
- Response parsing: `_response_text` (text calls) tolerates the
  candidates/parts structure (empty candidates skipped, parts
  concatenated) and is LOUD on `promptFeedback.blockReason`, a
  non-STOP `finishReason` with no text, and any shape carrying no
  text. `_response_image` (GUI rework Phase 18) mirrors it for the
  image calls — reads the first `inlineData` part instead of text
  (an image-gen answer often carries both a caption text part and the
  image part; only the latter counts), LOUD when no candidate carries
  an image part at all.

## Functions — model discovery + purpose recommendation (F5, owner D1/D2)

- `list_models(*, key=None, log=print) -> list[dict]` — GETs the
  ListModels endpoint (`{GEMINI_API_BASE}/models`), following
  `nextPageToken` across every page, via `_send_request` (the SAME
  auth header + retry/backoff shell every POST call uses). Each
  returned dict: `{"name": <id without the "models/" prefix>,
  "methods": <tuple of supportedGenerationMethods>, "display":
  <displayName>}`. `key=None` reads settings.json (`NoKey` when
  absent); any HTTP failure raises the usual `AiError` taxonomy.
- `capable_models(models, purpose) -> list[dict]` — the subset of
  `models` (as `list_models` returns them) CAPABLE of `purpose`
  (`"image"`/`"vision"`/`"text"`; any other string raises
  `ValueError` loudly). `"image"`: the name contains `"image"` OR a
  `supportedGenerationMethods` entry does (the API names no single
  canonical "image output" method). `"vision"`/`"text"`: the SAME
  filter — `"generateContent"` among the methods AND the name carries
  none of `_NON_TEXT_NAME_MARKERS` (`"image"`/`"embed"`/`"tts"`/
  `"audio"`/`"video"`) — only the RANKING differs per purpose, not the
  capability test. PURE, offline-testable.
- `recommend_model(models, purpose) -> str | None` — the BEST-FOR-
  THE-JOB model for `purpose` (owner D2: never one model for every
  job): filters via `capable_models`, then walks
  `config.MODEL_PURPOSE_RANKING[purpose]` (best substring first) and
  returns the first capable name containing it; when nothing in the
  ranking matches, falls back to the NEWEST by name (sorted
  descending — an honest, undocumented-but-logged proxy, never a
  guess at a specific unlisted name); `None` when nothing is capable
  at all. PURE.
- `model_for(purpose) -> str` — the model actually used by every call
  above when its own `model=` is left `None`: `settings.json`'s
  `MODELS_SETTING` (`"models"`) per-purpose override when present and
  non-blank, else the matching hardcoded `GEMINI_*_MODEL` constant
  (now a FALLBACK only). EVERY internal call site that used to
  default to one of those three constants routes through here (Rule
  #6) — the constants themselves are unchanged.
- The "Models…" picker in [GUI](../gui.md)'s `ApiImageGenPanel`
  (`gui/api_panel.py`) drives `list_models`/`capable_models`/
  `recommend_model` on a background thread and writes a pick straight
  to `settings.json` via `painter.settings` (immediate, like
  `PainterGui.set_gemini_key` — see that panel's own Design
  Decisions).

## Design Decisions
See [AI (subfolder)](___ai.md) — the no-SDK choice, the retry policy,
the paid-quota classification, the `_call_raw`/`_send_request` shell,
call-time model resolution and the reference-image part order all live
there, since they describe the package's shared behaviour.
