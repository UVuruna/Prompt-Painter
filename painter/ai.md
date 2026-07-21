# AI Client & Flows

**Script:** [AI Client & Flows (script)](ai.py)

## Purpose

The engine behind the three AI features (owner 2026-07-20): a
MINIMAL Gemini REST client over `urllib` (no SDK, free AI Studio
key), the SHEET-GENERATOR flow helpers (clarifying questions →
final `.md` → real-parser validation + one repair round), and the
image checker's FLAG MEMORY (`<out>/_state/ai_flags.json`). All of
it is offline-testable: the HTTP layer is one monkeypatchable alias
(`_urlopen`) and the flow helpers take a `gen` callable resolved at
call time.

Loud failure taxonomy (Rule #1): every HTTP error, API refusal/block
and malformed response raises `AiError`; a missing key raises the
specific `NoKey`, which the GUI answers by AUTO-OPENING the guided
key wizard. Consecutive API calls are PACED `AI_CALL_PAUSE_S` apart
— the free tier allows roughly 10 requests/minute.

TRANSIENT failures RETRY (owner 2026-07-21): the free tier 503s under
load ("model experiencing high demand") and 429s at the rate cap —
those, plus a 500, are retried up to `AI_RETRY_MAX` attempts with a
backoff between them, instead of being counted an error and skipped.
PERMANENT failures (400/401/403/404 — a bad request, bad key or
unknown model) raise on the first try. The retry keys on the numeric
HTTP status, which the client attaches to the raised `AiError`
(`.status`).

## Connections

### Uses
- [Config](config.md) — the whole `GEMINI_*` / `AI_*` block,
  `SITES`, `STATE_DIRNAME`, `PROJECT_ROOT`
- [Settings](settings.md) — `load_settings` (the key lives in
  `settings.json` under `gemini_api_key`)
- [Sheet Parser](sheet_parser.md) — `parse_sheet` validates every
  AI-produced sheet with the REAL contract rules

### Used by
- [GUI](../gui.md) — the key wizard's Test, the New-collection
  dialog, the AI-check job, the re-send mapping
- [Tests (folder)](../tests/___tests.md) — mocked-HTTP client tests,
  flow tests, flag round-trips

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

## Functions — the REST client

- `api_key() -> str` — the key from `settings.json`
  (`GEMINI_KEY_SETTING`); `NoKey` when absent/blank.
- `generate_text(prompt, system=None, *, key=None, model=...,
  log=print)` — one `models/<model>:generateContent` POST (key in the
  `x-goog-api-key` header, `systemInstruction` when given); returns
  the response text. `key=None` reads settings — the wizard's Test
  passes its candidate explicitly. `log` receives the transient-retry
  lines.
- `check_image(image_path, instructions, *, key=None, model=...,
  log=print)` — the vision call: the instructions text part + the
  image as base64 `inlineData` (png/jpg/webp by suffix). `log` receives
  the transient-retry lines.
- Both go through `_call`, which does the pacing + the TRANSIENT-error
  RETRY: on a 503/429/500 it waits and re-POSTs up to `AI_RETRY_MAX`
  attempts (503/500 wait `AI_RETRY_BACKOFF_S`; a 429 honours the
  server's own `retryDelay` / "retry in Xs", capped at
  `AI_RETRY_MAX_WAIT_S`), logging each retry; a permanent code raises
  at once. The HTTP body is parsed ONCE (`_http_error`) for both the
  message and the 429 backoff.
- Response parsing tolerates the candidates/parts structure (empty
  candidates skipped, parts concatenated) and is LOUD on
  `promptFeedback.blockReason`, a non-STOP `finishReason` with no
  text, and any shape carrying no text.

## Functions — the sheet-generator flow (owner's #2)

- `contract_text()` — `instructions.md` verbatim (both system
  prompts embed it).
- `ask_questions(request, contract, gen=None) -> list[str]` — the
  FIRST call (contract + "questions only"); parsed by
  `parse_questions` (numbered / bulleted lines, capped at
  `AI_MAX_QUESTIONS`; a poll-less answer returns `[]` and the
  caller generates directly).
- `generate_sheet(request, questions, answers, contract, work_dir,
  gen=None, log=print) -> (md, problems, theme)` — the SECOND call
  + at most ONE automatic repair round: the produced md (a
  whole-file code fence is unwrapped by `strip_md_fence`, inner
  prompt fences survive) is validated by `validate_sheet_md` with
  the REAL parser on a scratch file; problems are sent back once
  via `AI_REPAIR_PROMPT`. `problems == []` means loadable;
  otherwise the caller must NOT load the md (the GUI shows it for
  manual fixing).
- `save_sheet(md, theme, sheets_dir) -> Path` — writes a VALIDATED
  sheet under `sheets/` (created on demand) as
  `<slug_for(theme)>.md`, `_2`/`_3`… on collision.

## Functions — the checker + flag memory (owner's #3)

- `parse_check_response(text) -> list[str]` — the strict format:
  `OK` → `[]`; `DEFECTS:` + dash lines → the list; anything else is
  a loud `AiError` (never guessed).
- `check_one_image(src, out_base, instructions, *, model=..., log,
  check=None) -> dict` — the pure per-image driver TWO independent GUI
  callers now share (Rule #5, offline-testable — `check` defaults to
  this module's `check_image`, so a test injects a per-image mock): the
  standalone batch checker's worker loop (`_run_ai_check_job`) and, GUI
  rework Phase 16, the SITE dashboard's parallel per-item checker
  (`PainterGui._run_checker_one`, one bare call per saved image, no
  loop of its own). Times
  the call, parses the answer, MERGES the flag (or CLEARS a fixed
  image's old one) and returns the row the panel renders:
  `{rel (=flag_key), kind ('flagged'/'ok'/'error'), defects, raw
  (verbatim), time (seconds)}`. A per-image `AiError` (HTTP after the
  retries, or a malformed answer) is CAUGHT and returned as an
  `error` row — loud in the log, never fatal (the tool-job
  convention); its `raw` is the model's answer when we got one (a
  parse failure) or the error text (an HTTP/network failure), so the
  viewer always shows what happened.
- `fix_note(defects)` — the re-send's per-item extra suffix
  (`AI_FIX_NOTE`, "; "-joined defects).
- Flags file `<out>/_state/ai_flags.json`, atomic writes, keyed by
  `flag_key(image, out_base)` — the image's POSIX path RELATIVE to
  the out base (absolute when the image lives outside it; such keys
  persist but can never match a queued collection):
  `load_flags` / `save_flags` / `record_flag` (defects, the VERBATIM
  raw response, checked_at, model, the file's mtime AT CHECK TIME) /
  `clear_flag` / `clear_flag_keys` / `prune_stale_flags` — the prune
  drops every entry whose file is gone or whose mtime changed (the
  image was REGENERATED), run before each check batch. A corrupt flags
  file is reported loudly and treated as empty (flags are derived
  data — a re-check rebuilds them).
- `flag_file(key, out_base) -> Path` — the EXACT reverse of
  `flag_key` (relative under the base, or absolute when the image was
  outside): the ONE home for the round-trip, used by `prune_stale_flags`
  AND the GUI viewer, so the flag key and the image it opens can never
  drift apart.
- `drop_and_site_for(rel) -> (drop_path, site) | None` — the
  `config.dest_for` REVERSE: `<category>/<site>/<rest>` →
  `('assets/<category>/<rest>', site)`; legacy `<site>/<drop>` →
  `(drop, site)`; `None` when no segment names a site.
- `plan_resend(flagged, drop_to_source) -> (plans, notes,
  unmatched)` — the whole re-send plan, pure and GUI-free:
  `plans[site][sheet-source]` is the drop set that site runs
  (`only=`), `notes[site][drop]` each item's fix note
  (`extra_suffix`), `unmatched` the `(key, reason)` pairs the caller
  logs loudly (no site in the path / not in any queued collection).

## Design Decisions

- **No SDK.** The two calls the features need are one POST each;
  `urllib` keeps the dependency set unchanged and the HTTP layer
  mockable in one line.
- **Model names are config data** (`GEMINI_TEXT_MODEL`,
  `GEMINI_VISION_MODEL`) — Google rotates them; the owner bumps a
  string, not code.
- **Validation is the real parser.** The AI's sheet is held to the
  same contract as a hand-written one — `parse_sheet` on a scratch
  file, problems fed back for exactly ONE repair round, and a still
  broken sheet is NEVER loaded.
- **The flag mtime is the invalidation.** A regenerated image gets
  a new mtime, so its stale defects can never be asserted again —
  no separate bookkeeping when the re-send overwrites a file.
- **Retry transient, raise permanent.** The free tier genuinely 503s
  under load; skipping the image on the first 503 threw away a whole
  paced call for nothing. The retry lives in `_call`, so BOTH the text
  and vision paths get it for free — but only for the codes that a
  wait can fix (503/429/500); a 400/401/403/404 is a real bug in the
  request and fails loudly at once. Honest caveat: a free-tier 503 can
  persist through all the retries under sustained load, and the retry
  adds wall-time.
- **`check_one_image` is the pure seam.** The worker used to hold the
  per-image logic (key, time, parse, flag, emit) inline; extracting it
  makes the response↔image pairing testable WITHOUT a GUI and gives
  the raw/time one place to live.
